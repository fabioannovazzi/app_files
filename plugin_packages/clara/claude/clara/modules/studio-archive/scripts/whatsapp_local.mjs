import { guardedPhoneSearch, normalizeConfirmedPhone, parseAccessibilityState } from "./whatsapp_desktop_guard.mjs";

// Fixed checks are for exact identity/focus, never for interpreting message meaning.
const byId = (state, id) => state.elements.filter(e => e.line.includes(`ID: ${id},`) || e.line.endsWith(`ID: ${id}`));
const one = values => values.length === 1 ? values[0] : null;
const clean = value => String(value).replace(/[\u200e\u200f\u2066-\u2069]/gu, "").trim();
const snapshot = async app => parseAccessibilityState(await app.getAXState({ disableDiffing: true, emit: false }));
const usedDispatches = new Set();

async function transition(app, predicate) {
  // Native sheets can return the preceding window once after an action. Observe
  // a bounded number of fresh states, without repeating the action itself.
  let state;
  for (let attempt = 0; attempt < 3; attempt++) {
    state = await snapshot(app);
    if (predicate(state)) return state;
  }
  return state;
}

/** Probe actual APIs/controls, with no version allowlist and no input actions.
 * Windows may expose screenshots only; report that as a visual candidate requiring
 * live verification, never manufacture macOS selectors or native acceptance.
 */
export async function compatibility({ cua, app }) {
  const platform = cua.computer.target;
  const methods = ["getAXState", "getScreenshot", "click", "pressKey", "typeText"];
  const missing = methods.filter(name => typeof app?.[name] !== "function");
  if (!["mac", "windows"].includes(platform) || missing.length) return { platform, status: "unavailable", missing };
  let state;
  try { state = await snapshot(app); }
  catch { return { platform, status: "visual_check_required", reason: "accessibility_unavailable", liveVerified: false }; }
  const composer = one(state.composers);
  const search = one(state.searchCandidates);
  const header = one(byId(state, "NavigationBar_HeaderViewButton"));
  const table = one(byId(state, "ChatMessagesTableView"));
  return { platform, status: composer && search && header && table ? "indexed_controls_available" : "visual_check_required",
    composerEmpty: composer ? composer.value === "" : null, searchEmpty: search ? search.value === "" : null,
    existingDraft: Boolean(composer?.value || state.sendControlPresent), liveVerified: false };
}

/** Bridge current documented cua APIs to the bounded, digit-at-a-time search. */
export async function searchLocalChat({ cua, app, confirmedPhone, expectedChatName }) {
  if (cua.computer.target !== "mac") return { status: "visual_check_required", phoneVerified: false };
  const sky = {
    list_apps: () => cua.listApps({ emit: false }),
    get_app_state: async () => ({ text: await app.getAXState({ disableDiffing: true, emit: false }) }),
    click: ({ element_index }) => app.click(element_index),
    press_key: ({ key }) => app.pressKey(key),
    set_value: ({ element_index, value }) => app.setValue(element_index, value),
  };
  return guardedPhoneSearch({ sky, confirmedPhone, expectedChatName, allowUniqueChatCandidate: true });
}

/** Verify an already-open one-to-one chat using the actual contact-info sheet.
 * A unique search candidate is only a candidate: no message content is returned
 * until its exact contact phone is checked. Saved nicknames/self chats are valid.
 */
export async function verifyOpenChat({ app, confirmedPhone }) {
  const digits = normalizeConfirmedPhone(confirmedPhone);
  if (!digits) return { status: "blocked", reason: "invalid_phone" };
  let state = await snapshot(app);
  const header = one(byId(state, "NavigationBar_HeaderViewButton"));
  const table = one(byId(state, "ChatMessagesTableView"));
  const composer = one(state.composers);
  if (!header || !table || !composer || composer.value || state.sendControlPresent) return { status: "blocked", reason: "controls_ambiguous_or_existing_draft" };
  await app.click(header.index);
  state = await transition(app, value => Boolean(one(byId(value, "ContactInfo_CloseButton"))));
  const close = one(byId(state, "ContactInfo_CloseButton"));
  const sheetStart = state.lines.findIndex(l => /^\s*\d+ sheet(?:\s|$)/u.test(l));
  let verified = false;
  if (close && sheetStart >= 0) {
    const indent = state.lines[sheetStart].match(/^\s*/u)[0].length;
    let end = state.lines.length;
    for (let i = sheetStart + 1; i < end; i++) {
      if (state.lines[i].trim() && state.lines[i].match(/^\s*/u)[0].length <= indent) { end = i; break; }
    }
    const card = parseAccessibilityState(state.lines.slice(sheetStart, end).join("\n"));
    const phones = card.elements.filter(e => /^\+[\d ,()-]+$/u.test(clean(e.description)));
    const headings = card.elements.filter(e => e.role === "heading");
    const alias = clean(header.description);
    verified = phones.length === 1 && phones[0].description.replace(/\D/gu, "") === digits &&
      headings.some(e => clean(e.description) === alias || clean(e.description) === `${alias} (You)`);
  }
  if (close) {
    await app.click(close.index);
    state = await transition(app, value => Boolean(one(byId(value, "NavigationBar_HeaderViewButton"))) && !one(byId(value, "ContactInfo_CloseButton")));
  }
  if (!verified) return { status: "blocked", reason: "contact_phone_not_verified" };
  return finishVerification({ app, verification: { status: "phone_verified_pending_chat", phone: `+${digits}`, alias: header.description, tableDescription: table.description } });
}

/** Some native hosts expose an empty SceneWindow until the next tool call after
 * dismissing a sheet. Keep the proven identity but do not permit reads/writes
 * until a subsequent call observes the same chat again. No repeated UI action.
 */
export async function finishVerification({ app, verification }) {
  if (verification?.status !== "phone_verified_pending_chat") throw new Error("No pending contact verification");
  let state = await snapshot(app);
  let currentHeader = one(byId(state, "NavigationBar_HeaderViewButton"));
  let currentTable = one(byId(state, "ChatMessagesTableView"));
  if (!currentHeader && !currentTable) return verification;
  if (currentHeader?.description !== verification.alias || currentTable?.description !== verification.tableDescription) return { status: "blocked", reason: "chat_changed" };
  const search = one(state.searchCandidates);
  const clear = one(byId(state, "TokenizedSearchBar_DeleteButton"));
  if (search?.value === verification.phone.slice(1) && clear) {
    await app.click(clear.index);
    state = await transition(app, value => one(value.searchCandidates)?.value === "" && Boolean(one(byId(value, "NavigationBar_HeaderViewButton"))));
    currentHeader = one(byId(state, "NavigationBar_HeaderViewButton"));
    currentTable = one(byId(state, "ChatMessagesTableView"));
  }
  if (!currentHeader && !currentTable) return verification;
  if (currentHeader?.description !== verification.alias || currentTable?.description !== verification.tableDescription || one(state.composers)?.value !== "") return { status: "blocked", reason: "chat_changed" };
  return { ...verification, status: "verified" };
}

function targetState(state, verification) {
  return verification?.status === "verified" && one(byId(state, "NavigationBar_HeaderViewButton"))?.description === verification.alias &&
    one(byId(state, "ChatMessagesTableView"))?.description === verification.tableDescription;
}

/** Return only the selected table; sidebar previews stay outside model output. */
export async function readVerifiedChat({ app, verification }) {
  const state = await snapshot(app);
  if (!targetState(state, verification)) throw new Error("Verified chat changed");
  const table = one(byId(state, "ChatMessagesTableView"));
  const start = state.lines.findIndex(l => l === table.line);
  const indent = table.line.match(/^\s*/u)[0].length;
  let end = start + 1;
  while (end < state.lines.length && (!state.lines[end].trim() || state.lines[end].match(/^\s*/u)[0].length > indent)) end++;
  return state.lines.slice(start, end).join("\n");
}

/** Compose ONLY the exact body of a persisted execute=true dispatch claim.
 * Keep existing user drafts untouched. A failed postcondition never sends.
 */
export async function composeClaimedText({ app, verification, claim }) {
  if (claim?.execute !== true || claim.operation.status !== "submitting" || claim.operation.phone !== verification.phone || claim.operation.attachments.length) throw new Error("A text-only dispatch claim for this verified phone is required");
  const state = await snapshot(app);
  const composer = one(state.composers);
  if (!targetState(state, verification) || !composer || composer.value || state.sendControlPresent) throw new Error("Chat changed or existing draft; no text entered");
  await app.click(composer.index);
  const focused = await snapshot(app);
  if (!targetState(focused, verification) || one(focused.composers)?.value !== "" || focused.focusedIndex !== one(focused.composers)?.index) throw new Error("Composer focus not verified");
  await app.typeText(claim.operation.body);
  const composed = await transition(app, value => one(value.composers)?.value === claim.operation.body);
  if (!targetState(composed, verification) || one(composed.composers)?.value !== claim.operation.body) throw new Error("Composition unverified; do not send or clear unknown text");
  return { status: "composed", operationId: claim.operation.id };
}

export async function sendClaimedText({ app, verification, claim }) {
  const operation = claim?.operation;
  if (claim?.execute !== true || operation?.status !== "submitting" || operation.phone !== verification.phone || operation.attachments.length || usedDispatches.has(operation.id)) throw new Error("Dispatch unavailable; inspect persisted outcome before any retry");
  const state = await snapshot(app);
  const send = one(byId(state, "ChatBar_SendButton"));
  if (!targetState(state, verification) || one(state.composers)?.value !== operation.body || !send) throw new Error("Exact composed message unavailable");
  usedDispatches.add(operation.id); // A lost click response must never cause a second click.
  await app.click(send.index);
  const after = await snapshot(app);
  return { status: "inspect_outcome", composerEmpty: one(after.composers)?.value === "", chatUnchanged: targetState(after, verification) };
}
