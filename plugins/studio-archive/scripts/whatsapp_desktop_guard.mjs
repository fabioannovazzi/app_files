const DEFAULT_APP = "net.whatsapp.WhatsApp";

const SEARCH_DESCRIPTIONS = new Set([
  "search",
  "search chats",
  "search chats and channels",
  "search contact name or number",
  "search field",
]);

function stripDirectionalMarks(value) {
  return value.replace(/[\u200e\u200f]/gu, "").trim();
}

function normalizedText(value) {
  return stripDirectionalMarks(String(value))
    .normalize("NFKC")
    .replace(/\s+/gu, " ")
    .trim()
    .toLocaleLowerCase("en-US");
}

function normalizeConfirmedPhone(value) {
  const raw = String(value ?? "").trim();
  if (!/^(?:\+|00)[0-9 ()-]+$/u.test(raw)) {
    return null;
  }
  const digits = raw.replace(/\D/gu, "").replace(/^00/u, "");
  return digits.length >= 8 && digits.length <= 15 ? digits : null;
}

function parseElementLine(line) {
  const match = line.match(/^\s*(\d+)\s+(.+?)\s+Description:\s*(.*)$/u);
  if (!match) {
    return null;
  }
  const attributes = match[3];
  const description = attributes
    .split(/,\s+(?=(?:Help|ID|Secondary Actions|Value|Role|Enabled|Selected|Title):)/u, 1)[0];
  const valueMatch = line.match(
    /,\s+Value:\s*(.*?)(?=,\s+(?:Help|ID|Secondary Actions|Role|Enabled|Selected|Title):|$)/u,
  );
  return {
    index: Number(match[1]),
    role: normalizedText(match[2]),
    description: stripDirectionalMarks(description),
    value: valueMatch ? stripDirectionalMarks(valueMatch[1]) : "",
    line,
  };
}

function isKnownSearchDescription(description) {
  return SEARCH_DESCRIPTIONS.has(normalizedText(description));
}

function parseAccessibilityState(text) {
  const lines = String(text ?? "").split("\n");
  const elements = lines.map(parseElementLine).filter(Boolean);
  const searchByIndex = new Map();
  for (const element of elements) {
    if (
      isKnownSearchDescription(element.description) ||
      /ID:\s*(?:TokenizedSearchBar_TextView|WAChatListSearchBar(?:InputView)?)(?:,|$)/u.test(
        element.line,
      )
    ) {
      searchByIndex.set(element.index, element);
    }
  }
  const composers = elements.filter((element) =>
    /ID:\s*(?:ChatBar_ComposerTextView|WAChatBarInputTextView)(?:,|$)/u.test(
      element.line,
    ),
  );
  const focusedMatch = lines
    .map((line) =>
      line.match(/^The focused UI element is\s+(\d+)\s+.*Description:\s*(.*)$/u),
    )
    .find(Boolean);
  const focusedDescription = focusedMatch
    ? stripDirectionalMarks(
        focusedMatch[2].split(
          /,\s+(?=(?:Help|ID|Secondary Actions|Value|Role|Enabled|Selected|Title):)/u,
          1,
        )[0],
      )
    : null;

  return {
    lines,
    elements,
    searchCandidates: [...searchByIndex.values()],
    composers,
    focusedIndex: focusedMatch ? Number(focusedMatch[1]) : null,
    focusedDescription,
    sendControlPresent: lines.some((line) =>
      /ID:\s*ChatBar_SendButton(?:,|$)/u.test(line),
    ),
  };
}

function selectTargetResult(parsed, expectedChatName, phoneDigits) {
  const semanticResults = new Map();
  for (const element of parsed.elements) {
    const resultMatch = element.line.match(
      /ID:\s*ChatListSearchView_(Contact|Chat)Result(?:,|$)/u,
    );
    if (!resultMatch) {
      continue;
    }
    const kind = resultMatch[1].toLocaleLowerCase("en-US");
    const description = normalizedText(element.description);
    const key = `${kind}:${description}`;
    const current = semanticResults.get(key);
    const roleRank = element.role === "text" ? 0 : 1;
    if (!current || roleRank > current.roleRank) {
      semanticResults.set(key, { element, kind, description, roleRank });
    }
  }

  const results = [...semanticResults.values()];
  const expectedName = expectedChatName
    ? normalizedText(expectedChatName)
    : null;
  const exactMatches = results.filter(({ description }) => {
    const descriptionDigits = description.replace(/\D/gu, "");
    return (
      (expectedName && description === expectedName) ||
      (descriptionDigits && descriptionDigits === phoneDigits)
    );
  });
  const uniqueContacts = results.filter(({ kind }) => kind === "contact");
  const selected =
    exactMatches.length === 1
      ? { ...exactMatches[0], matchedBy: "exact_confirmed_identity" }
      : uniqueContacts.length === 1
        ? { ...uniqueContacts[0], matchedBy: "unique_contact_result" }
        : null;

  return {
    targetResult: selected
      ? {
          elementIndex: selected.element.index,
          kind: selected.kind,
          matchedBy: selected.matchedBy,
        }
      : null,
    resultCount: results.length,
    contactResultCount: uniqueContacts.length,
  };
}

function exactElements(parsed, predicate) {
  return parsed.elements.filter(predicate);
}

function exactTargetTable(parsed, expectedChatName) {
  const expectedDescription = normalizedText(
    `Messages in chat with ${expectedChatName}`,
  );
  return exactElements(
    parsed,
    (element) =>
      /ID:\s*ChatMessagesTableView(?:,|$)/u.test(element.line) &&
      normalizedText(element.description) === expectedDescription,
  );
}

function exactTargetHeader(parsed, expectedChatName) {
  const expectedDescription = normalizedText(expectedChatName);
  return exactElements(
    parsed,
    (element) =>
      /ID:\s*NavigationBar_HeaderViewButton(?:,|$)/u.test(element.line) &&
      normalizedText(element.description) === expectedDescription,
  );
}

function parseVerifiedContactCard(parsed, expectedChatName, phoneDigits) {
  const expectedName = normalizedText(expectedChatName);
  const nameHeadings = exactElements(
    parsed,
    (element) =>
      element.role.includes("heading") &&
      normalizedText(element.description) === expectedName,
  );
  const phoneElements = exactElements(parsed, (element) => {
    const descriptionDigits = element.description.replace(/\D/gu, "");
    const valueDigits = element.value.replace(/\D/gu, "");
    const isSearch = /ID:\s*TokenizedSearchBar_TextView(?:,|$)/u.test(
      element.line,
    );
    return (
      !isSearch &&
      element.role.includes("text") &&
      (descriptionDigits === phoneDigits || valueDigits === phoneDigits)
    );
  });
  const profileMarkers = exactElements(parsed, (element) =>
    /ID:\s*contact-info-header-profile-image(?:,|$)/u.test(element.line),
  );
  const doneButtons = exactElements(
    parsed,
    (element) =>
      element.role.includes("button") &&
      normalizedText(element.description) === "done",
  );
  return {
    verified:
      nameHeadings.length === 1 &&
      phoneElements.length === 1 &&
      profileMarkers.length === 1 &&
      parsed.searchCandidates.length === 0 &&
      parsed.composers.length === 0 &&
      exactTargetTable(parsed, expectedChatName).length === 0,
    doneElementIndex:
      doneButtons.length === 1 ? doneButtons[0].index : null,
  };
}

async function readUntil(sky, app, predicate, attempts = 3) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const state = await readFullState(sky, app);
    if (!state) {
      continue;
    }
    const parsed = parseAccessibilityState(state.text);
    if (predicate(parsed)) {
      return { state, parsed };
    }
  }
  return null;
}

function response(status, overrides = {}) {
  return {
    status,
    reason: null,
    digitsEntered: 0,
    composerEmpty: null,
    cleanup: "not_needed",
    targetResult: null,
    resultCount: 0,
    contactResultCount: 0,
    ...overrides,
  };
}

async function readFullState(sky, app) {
  try {
    return await sky.get_app_state({ app, disableDiff: true });
  } catch {
    return null;
  }
}

/**
 * Enter one confirmed phone in WhatsApp's chat-list search with a postcondition
 * after every digit. Raw accessibility state never leaves this function.
 */
export async function guardedPhoneSearch({
  sky,
  confirmedPhone,
  expectedChatName = null,
  app = DEFAULT_APP,
}) {
  const phoneDigits = normalizeConfirmedPhone(confirmedPhone);
  if (!phoneDigits) {
    return response("blocked", { reason: "invalid_international_phone" });
  }
  if (
    !sky ||
    typeof sky.list_apps !== "function" ||
    typeof sky.get_app_state !== "function" ||
    typeof sky.click !== "function" ||
    typeof sky.press_key !== "function" ||
    typeof sky.set_value !== "function"
  ) {
    return response("blocked", { reason: "computer_use_api_unavailable" });
  }

  let apps;
  try {
    apps = await sky.list_apps();
  } catch {
    return response("blocked", { reason: "app_inventory_unavailable" });
  }
  const whatsapp = apps.find(
    (candidate) => candidate.id === app || candidate.displayName === app,
  );
  if (!whatsapp?.isRunning) {
    return response("blocked", { reason: "whatsapp_not_already_running" });
  }

  let state = await readFullState(sky, app);
  if (!state) {
    return response("blocked", { reason: "accessibility_state_unavailable" });
  }
  let parsed = parseAccessibilityState(state.text);
  if (parsed.searchCandidates.length !== 1 || parsed.composers.length !== 1) {
    return response("blocked", { reason: "search_or_composer_not_unique" });
  }
  if (
    parsed.searchCandidates[0].value !== "" ||
    parsed.composers[0].value !== "" ||
    parsed.sendControlPresent
  ) {
    return response("blocked", {
      reason: "search_or_composer_not_empty",
      composerEmpty: parsed.composers[0].value === "",
    });
  }

  try {
    await sky.press_key({ app, key: "super+f" });
  } catch {
    // Some Computer Use builds reject modifier chords. The fresh empty-control
    // checks and exact indexed click below mechanically preserve safe routing.
  }
  state = await readFullState(sky, app);
  if (!state) {
    return response("blocked", { reason: "post_shortcut_state_unavailable" });
  }
  parsed = parseAccessibilityState(state.text);
  if (parsed.searchCandidates.length !== 1 || parsed.composers.length !== 1) {
    return response("blocked", { reason: "post_shortcut_controls_not_unique" });
  }
  if (
    parsed.searchCandidates[0].value !== "" ||
    parsed.composers[0].value !== "" ||
    parsed.sendControlPresent
  ) {
    return response("blocked", {
      reason: "search_focus_not_proven",
      composerEmpty: parsed.composers[0].value === "",
    });
  }
  try {
    await sky.click({ app, element_index: parsed.searchCandidates[0].index });
  } catch {
    return response("blocked", { reason: "search_control_click_failed" });
  }
  state = await readFullState(sky, app);
  if (!state) {
    return response("blocked", { reason: "post_search_click_state_unavailable" });
  }
  parsed = parseAccessibilityState(state.text);
  if (parsed.searchCandidates.length !== 1 || parsed.composers.length !== 1) {
    return response("blocked", { reason: "post_search_click_controls_not_unique" });
  }
  const exposedFocusIsSearch =
    parsed.focusedIndex === null ||
    (parsed.focusedIndex === parsed.searchCandidates[0].index &&
      isKnownSearchDescription(parsed.focusedDescription ?? ""));
  if (
    !exposedFocusIsSearch ||
    parsed.searchCandidates[0].value !== "" ||
    parsed.composers[0].value !== "" ||
    parsed.sendControlPresent
  ) {
    return response("blocked", {
      reason: "indexed_search_focus_not_proven",
      composerEmpty: parsed.composers[0].value === "",
    });
  }

  let verifiedPrefix = "";
  for (const digit of phoneDigits) {
    try {
      await sky.press_key({ app, key: digit });
    } catch {
      return response("blocked", {
        reason: "digit_key_failed",
        digitsEntered: verifiedPrefix.length,
        composerEmpty: true,
      });
    }
    state = await readFullState(sky, app);
    if (!state) {
      return response("blocked", {
        reason: "post_digit_state_unavailable",
        digitsEntered: verifiedPrefix.length,
        composerEmpty: null,
      });
    }
    parsed = parseAccessibilityState(state.text);
    if (parsed.searchCandidates.length !== 1 || parsed.composers.length !== 1) {
      return response("blocked", {
        reason: "post_digit_controls_not_unique",
        digitsEntered: verifiedPrefix.length,
        composerEmpty: null,
      });
    }

    const search = parsed.searchCandidates[0];
    const composer = parsed.composers[0];
    const expectedPrefix = `${verifiedPrefix}${digit}`;
    const safeTransition =
      search.value === expectedPrefix &&
      composer.value === "" &&
      !parsed.sendControlPresent &&
      (parsed.focusedIndex === null ||
        (parsed.focusedIndex === search.index &&
          isKnownSearchDescription(parsed.focusedDescription ?? "")));
    if (safeTransition) {
      verifiedPrefix = expectedPrefix;
      continue;
    }

    const exactSingleDigitMisdirection =
      search.value === verifiedPrefix && composer.value === digit;
    if (!exactSingleDigitMisdirection) {
      return response("blocked", {
        reason: "unsafe_text_transition",
        digitsEntered: verifiedPrefix.length,
        composerEmpty: composer.value === "",
        cleanup: "not_attempted_unknown_content",
      });
    }

    try {
      await sky.set_value({ app, element_index: composer.index, value: "" });
    } catch {
      return response("blocked", {
        reason: "misdirected_digit_cleanup_failed",
        digitsEntered: verifiedPrefix.length,
        composerEmpty: false,
        cleanup: "failed",
      });
    }
    const cleanupState = await readFullState(sky, app);
    if (!cleanupState) {
      return response("blocked", {
        reason: "cleanup_state_unavailable",
        digitsEntered: verifiedPrefix.length,
        composerEmpty: null,
        cleanup: "unverified",
      });
    }
    const cleanupParsed = parseAccessibilityState(cleanupState.text);
    const cleanupSearch = cleanupParsed.searchCandidates[0];
    const cleanupComposer = cleanupParsed.composers[0];
    const cleanupVerified =
      cleanupParsed.searchCandidates.length === 1 &&
      cleanupParsed.composers.length === 1 &&
      cleanupSearch?.value === verifiedPrefix &&
      cleanupComposer?.value === "" &&
      !cleanupParsed.sendControlPresent;
    return response("blocked", {
      reason: cleanupVerified
        ? "misdirected_digit_removed"
        : "misdirected_digit_cleanup_unverified",
      digitsEntered: verifiedPrefix.length,
      composerEmpty: cleanupVerified,
      cleanup: cleanupVerified ? "completed" : "unverified",
    });
  }

  const target = selectTargetResult(parsed, expectedChatName, phoneDigits);
  return response(target.targetResult ? "ready_to_open_target" : "blocked", {
    reason: target.targetResult ? null : "no_unique_target_result",
    digitsEntered: verifiedPrefix.length,
    composerEmpty: true,
    targetResult: target.targetResult,
    resultCount: target.resultCount,
    contactResultCount: target.contactResultCount,
  });
}

/**
 * Verify the guarded result through WhatsApp's exposed More Info action, then
 * open the exact contact and leave only its chat visible. Call immediately
 * after guardedPhoneSearch so the returned result index is still fresh.
 */
export async function verifyAndOpenGuardedTarget({
  sky,
  searchResult,
  confirmedPhone,
  expectedChatName,
  app = DEFAULT_APP,
}) {
  const phoneDigits = normalizeConfirmedPhone(confirmedPhone);
  if (
    !phoneDigits ||
    !expectedChatName ||
    searchResult?.status !== "ready_to_open_target" ||
    !Number.isInteger(searchResult?.targetResult?.elementIndex)
  ) {
    return {
      status: "blocked",
      reason: "guarded_target_input_invalid",
      phoneVerified: false,
      composerEmpty: null,
      targetTableAvailable: false,
    };
  }
  if (
    typeof sky?.perform_secondary_action !== "function" ||
    typeof sky?.click !== "function"
  ) {
    return {
      status: "blocked",
      reason: "computer_use_target_api_unavailable",
      phoneVerified: false,
      composerEmpty: null,
      targetTableAvailable: false,
    };
  }

  try {
    await sky.perform_secondary_action({
      app,
      element_index: searchResult.targetResult.elementIndex,
      action: "More Info",
    });
  } catch {
    return {
      status: "blocked",
      reason: "contact_info_action_failed",
      phoneVerified: false,
      composerEmpty: null,
      targetTableAvailable: false,
    };
  }
  const cardState = await readFullState(sky, app);
  if (!cardState) {
    return {
      status: "blocked",
      reason: "contact_info_state_unavailable",
      phoneVerified: false,
      composerEmpty: null,
      targetTableAvailable: false,
    };
  }
  const card = parseVerifiedContactCard(
    parseAccessibilityState(cardState.text),
    expectedChatName,
    phoneDigits,
  );
  if (!card.verified || card.doneElementIndex === null) {
    if (card.doneElementIndex !== null) {
      try {
        await sky.click({ app, element_index: card.doneElementIndex });
      } catch {
        // The workflow remains blocked even if WhatsApp will not close the card.
      }
    }
    return {
      status: "blocked",
      reason: card.verified
        ? "contact_card_dismiss_unavailable"
        : "contact_identity_not_verified",
      phoneVerified: false,
      composerEmpty: null,
      targetTableAvailable: false,
    };
  }

  try {
    await sky.click({ app, element_index: card.doneElementIndex });
  } catch {
    return {
      status: "blocked",
      reason: "contact_card_dismiss_failed",
      phoneVerified: true,
      composerEmpty: null,
      targetTableAvailable: false,
    };
  }
  const restored = await readUntil(sky, app, (parsed) => {
    const target = selectTargetResult(parsed, expectedChatName, phoneDigits);
    return (
      parsed.searchCandidates.length === 1 &&
      parsed.searchCandidates[0].value === phoneDigits &&
      parsed.composers.length === 1 &&
      parsed.composers[0].value === "" &&
      !parsed.sendControlPresent &&
      target.targetResult !== null
    );
  });
  if (!restored) {
    return {
      status: "blocked",
      reason: "verified_search_result_not_restored",
      phoneVerified: true,
      composerEmpty: null,
      targetTableAvailable: false,
    };
  }
  const freshTarget = selectTargetResult(
    restored.parsed,
    expectedChatName,
    phoneDigits,
  ).targetResult;
  try {
    await sky.click({ app, element_index: freshTarget.elementIndex });
  } catch {
    return {
      status: "blocked",
      reason: "verified_target_open_failed",
      phoneVerified: true,
      composerEmpty: null,
      targetTableAvailable: false,
    };
  }

  const openedState = await readFullState(sky, app);
  if (!openedState) {
    return {
      status: "blocked",
      reason: "opened_target_state_unavailable",
      phoneVerified: true,
      composerEmpty: null,
      targetTableAvailable: false,
    };
  }
  const opened = parseAccessibilityState(openedState.text);
  const deleteButtons = exactElements(opened, (element) =>
    /ID:\s*TokenizedSearchBar_DeleteButton(?:,|$)/u.test(element.line),
  );
  const openedIsExactTarget =
    exactTargetHeader(opened, expectedChatName).length === 1 &&
    exactTargetTable(opened, expectedChatName).length === 1 &&
    opened.searchCandidates.length === 1 &&
    opened.searchCandidates[0].value === phoneDigits &&
    opened.composers.length === 1 &&
    opened.composers[0].value === "" &&
    !opened.sendControlPresent &&
    deleteButtons.length === 1;
  if (!openedIsExactTarget) {
    return {
      status: "blocked",
      reason: "opened_target_postcondition_failed",
      phoneVerified: true,
      composerEmpty:
        opened.composers.length === 1
          ? opened.composers[0].value === ""
          : null,
      targetTableAvailable: false,
    };
  }

  try {
    await sky.click({ app, element_index: deleteButtons[0].index });
  } catch {
    return {
      status: "blocked",
      reason: "verified_search_clear_failed",
      phoneVerified: true,
      composerEmpty: true,
      targetTableAvailable: false,
    };
  }
  const final = await readUntil(sky, app, (parsed) => {
    const searchIsEmpty =
      parsed.searchCandidates.length === 1 &&
      parsed.searchCandidates[0].value === "";
    const overlayIsClosed = !parsed.lines.some((line) =>
      /ID:\s*ChatListSearchView_(?:Contact|Chat)Result(?:,|$)/u.test(line),
    );
    return (
      searchIsEmpty &&
      overlayIsClosed &&
      exactTargetHeader(parsed, expectedChatName).length === 1 &&
      exactTargetTable(parsed, expectedChatName).length === 1 &&
      parsed.composers.length === 1 &&
      parsed.composers[0].value === "" &&
      !parsed.sendControlPresent
    );
  });
  if (!final) {
    return {
      status: "blocked",
      reason: "verified_target_final_state_failed",
      phoneVerified: true,
      composerEmpty: null,
      targetTableAvailable: false,
    };
  }

  return {
    status: "verified_target_open",
    reason: null,
    phoneVerified: true,
    composerEmpty: true,
    targetTableAvailable: true,
  };
}

/**
 * Return only the verified chat's accessibility subtree. The caller must first
 * verify the exact phone in WhatsApp's contact information panel.
 */
export function extractVerifiedChatTable(
  accessibilityText,
  { expectedChatName, phoneVerified },
) {
  if (!phoneVerified || !expectedChatName) {
    return null;
  }
  const lines = String(accessibilityText ?? "").split("\n");
  const expectedDescription = normalizedText(
    `Messages in chat with ${expectedChatName}`,
  );
  const candidates = lines
    .map((line, index) => ({ line, index, element: parseElementLine(line) }))
    .filter(
      ({ line, element }) =>
        element &&
        /ID:\s*ChatMessagesTableView(?:,|$)/u.test(line) &&
        normalizedText(element.description) === expectedDescription,
    );
  if (candidates.length !== 1) {
    return null;
  }
  const start = candidates[0].index;
  const parentIndent = lines[start].match(/^\s*/u)[0].length;
  let end = lines.length;
  for (let index = start + 1; index < lines.length; index += 1) {
    if (!lines[index].trim()) {
      continue;
    }
    const indent = lines[index].match(/^\s*/u)[0].length;
    if (indent <= parentIndent) {
      end = index;
      break;
    }
  }
  return lines.slice(start, end).join("\n");
}
