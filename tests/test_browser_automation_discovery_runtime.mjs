import assert from "node:assert/strict";
import test from "node:test";
import { runInNewContext } from "node:vm";

import {
  DISCOVERY_RUNTIME_VERSION,
  captureControlState,
  diffControlStates,
  observeGuidedWindow,
  queryFreeUrl,
} from "../plugins/browser-automation/scripts/discovery_runtime.mjs";

function control(name, role = "button") {
  return {
    tag: role === "link" ? "a" : "button",
    role,
    name,
    label: null,
    placeholder: null,
    test_id: null,
    type: null,
    disabled: false,
    structured_context: false,
  };
}

function inventory(controls) {
  return {
    controls,
    total_control_count: controls.length,
    truncated: false,
  };
}

function fakeTab({ urls, inventories }) {
  let index = 0;
  return {
    async url() {
      return urls[Math.min(index, urls.length - 1)];
    },
    playwright: {
      async evaluate() {
        return inventories[Math.min(index, inventories.length - 1)];
      },
      async waitForTimeout() {
        index += 1;
      },
    },
  };
}

test("captureControlState keeps query values out of the captured state", async () => {
  const tab = fakeTab({
    urls: ["https://example.test/process?client=private#step"],
    inventories: [inventory([control("Continue")])],
  });

  const state = await captureControlState({
    tab,
    allowedOrigins: ["https://example.test"],
  });

  assert.equal(state.runtime_version, DISCOVERY_RUNTIME_VERSION);
  assert.equal(state.origin, "https://example.test");
  assert.equal(state.path, "/process");
  assert.equal(state.controls[0].name, "Continue");
  assert.match(state.control_fingerprint, /^[a-f0-9]{64}$/);
  assert.doesNotMatch(JSON.stringify(state), /client=private|#step/);
});

test("diffControlStates reports structural control changes", async () => {
  const before = {
    origin: "https://example.test",
    path: "/start",
    controls: [control("Continue")],
  };
  const after = {
    origin: "https://example.test",
    path: "/finish",
    controls: [control("Download", "link")],
  };

  const delta = diffControlStates(before, after);

  assert.equal(delta.path_changed, true);
  assert.deepEqual(delta.added_controls, [control("Download", "link")]);
  assert.deepEqual(delta.removed_controls, [control("Continue")]);
});

test("observeGuidedWindow captures bounded operator-visible state changes", async () => {
  const tab = fakeTab({
    urls: [
      "https://example.test/start",
      "https://example.test/form",
      "https://example.test/finish",
    ],
    inventories: [
      inventory([control("Begin")]),
      inventory([control("Save")]),
      inventory([control("Download", "link")]),
    ],
  });

  const capture = await observeGuidedWindow({
    tab,
    allowedOrigins: ["https://example.test"],
    durationMs: 1_000,
    pollIntervalMs: 100,
    maxTransitions: 2,
  });

  assert.equal(capture.transitions.length, 2);
  assert.equal(capture.observing, false);
  assert.equal(capture.stop_reason, "transition_limit");
  assert.equal(capture.interpretation_required, true);
  assert.equal(capture.transitions[0].before.path, "/start");
  assert.equal(capture.transitions[1].after.path, "/finish");
  assert.deepEqual(capture.capture_policy, {
    query_free_paths_only: true,
    form_values_excluded: true,
    structured_rows_excluded: true,
    screenshots_excluded: true,
    structured_control_values_excluded: true,
    private_identifier_tokens_redacted: true,
  });
});

test("guided observation reports a pause without pretending to watch afterward", async () => {
  const controller = new AbortController();
  controller.abort();
  const capture = await observeGuidedWindow({
    tab: fakeTab({ urls: ["https://example.test/"], inventories: [inventory([])] }),
    allowedOrigins: ["https://example.test"],
    signal: controller.signal,
  });
  assert.equal(capture.stop_reason, "operator_pause");
  assert.equal(capture.observing, false);
  assert.deepEqual(capture.transitions, []);
});

test("a timed window without changes still ends observation", async () => {
  const capture = await observeGuidedWindow({
    tab: fakeTab({ urls: ["https://example.test/"], inventories: [inventory([])] }),
    allowedOrigins: ["https://example.test"],
    durationMs: 1000,
  });
  assert.equal(capture.stop_reason, "time_limit");
  assert.equal(capture.observing, false);
  assert.equal(capture.transitions.length, 0);
});

function documentWithFrame(nested, url = "https://example.test/process") {
  return {
    URL: url,
    querySelectorAll(selector) {
      return selector === "iframe" && nested !== undefined
        ? [{ tagName: "IFRAME", contentDocument: nested }] : [];
    },
  };
}

function domTab(document) {
  return {
    async url() { return "https://example.test/process"; },
    playwright: {
      async evaluate(fn, args) {
        return runInNewContext(`(${fn.toString()})(args)`, { document, URL, args });
      },
    },
  };
}

test("the observer selects nested same-origin frames without scanning their siblings", async () => {
  const inner = documentWithFrame(undefined);
  const tab = domTab(documentWithFrame(documentWithFrame(inner)));
  const state = await captureControlState({
    tab, allowedOrigins: ["https://example.test"], frameSelectors: ["iframe", "iframe"],
  });
  assert.equal(state.frame_depth, 2);
  assert.equal(state.unobserved_frame_count, 0);
  assert.equal(state.total_control_count, 0);
});

test("top-level capture reports frames it did not observe", async () => {
  const state = await captureControlState({
    tab: domTab(documentWithFrame(documentWithFrame(undefined))),
    allowedOrigins: ["https://example.test"],
  });
  assert.equal(state.frame_depth, 0);
  assert.equal(state.unobserved_frame_count, 1);
});

test("selected frame controls use the same redaction and exclude field values", async () => {
  const button = {
    tagName: "BUTTON", innerText: "Confirm 01234567890", value: "private-value",
    getAttribute() { return null; },
    getBoundingClientRect() { return { width: 20, height: 20 }; },
    closest() { return null; },
    matches() { return false; },
  };
  const nested = {
    URL: "https://example.test/accounting?private=query",
    defaultView: { getComputedStyle() { return { visibility: "visible", display: "block" }; } },
    querySelectorAll(selector) { return selector.includes("button") ? [button] : []; },
  };
  const state = await captureControlState({
    tab: domTab(documentWithFrame(nested)), allowedOrigins: ["https://example.test"],
    frameSelectors: ["iframe"],
  });
  assert.equal(state.controls[0].name, "Confirm [private identifier]");
  assert.equal(state.frame_path, "/accounting");
  assert.equal(state.frame_origin, "https://example.test");
  assert.doesNotMatch(JSON.stringify(state), /01234567890|private-value|private=query/);
});

test("ambiguous frame selectors are rejected before any child is read", async () => {
  const document = {
    URL: "https://example.test/process",
    querySelectorAll() { return [{ tagName: "IFRAME" }, { tagName: "IFRAME" }]; },
  };
  await assert.rejects(captureControlState({
    tab: domTab(document), allowedOrigins: ["https://example.test"], frameSelectors: ["iframe"],
  }), { message: "guided discovery: frame_not_unique" });
});

test("a frame outside the boundary is rejected before control inspection", async () => {
  const nested = { URL: "https://outside.test/private?token=secret" };
  await assert.rejects(captureControlState({
    tab: domTab(documentWithFrame(nested)),
    allowedOrigins: ["https://example.test"], frameSelectors: ["iframe"],
  }), { message: "guided discovery: frame_origin_not_allowed" });
});

test("an inaccessible cross-origin frame reports a bounded gap", async () => {
  await assert.rejects(captureControlState({
    tab: domTab(documentWithFrame(null)),
    allowedOrigins: ["https://example.test"], frameSelectors: ["iframe"],
  }), { message: "guided discovery: frame_unavailable" });
});

test("a missing frame does not silently fall back to the top-level page", async () => {
  await assert.rejects(captureControlState({
    tab: domTab(documentWithFrame(undefined)),
    allowedOrigins: ["https://example.test"], frameSelectors: ["iframe"],
  }), { message: "guided discovery: frame_not_unique" });
});

test("captureControlState redacts identifiers embedded in control metadata", async () => {
  const privateIdentifier = "01234567890";
  const fiscalCode = "RSSMRA80A01H501U";
  const emailAddress = "private.person@example.test";
  const uuid = "0f4d8b6a-2e65-4d3f-9b0c-6f99d08b4b72";
  const iban = "IT60X0542811101000000123456";
  const tab = fakeTab({
    urls: ["https://example.test/invoices"],
    inventories: [
      inventory([
        {
          ...control(`Download invoice ${privateIdentifier}`),
          label: `Payment ${fiscalCode}`,
          placeholder: "Reference 2026/000123",
          test_id: `download-${privateIdentifier}`,
        },
        control(`Send to ${emailAddress}`),
        control(`Open ${uuid}`),
        control(`Account ${iban}`),
      ]),
    ],
  });

  const state = await captureControlState({
    tab,
    allowedOrigins: ["https://example.test"],
  });

  assert.equal(state.controls[0].name, "Download invoice [private identifier]");
  assert.equal(state.controls[0].label, "Payment [private identifier]");
  assert.equal(state.controls[0].placeholder, "Reference [private identifier]");
  assert.equal(state.controls[0].test_id, null);
  assert.deepEqual(state.controls[0].redacted_fields, [
    "name",
    "label",
    "placeholder",
    "test_id",
  ]);
  assert.doesNotMatch(JSON.stringify(state), new RegExp(privateIdentifier));
  assert.doesNotMatch(JSON.stringify(state), new RegExp(fiscalCode));
  assert.doesNotMatch(JSON.stringify(state), new RegExp(emailAddress));
  assert.doesNotMatch(JSON.stringify(state), new RegExp(uuid));
  assert.doesNotMatch(JSON.stringify(state), new RegExp(iban));
  assert.equal(state.controls[1].name, "Send to [private identifier]");
  assert.equal(state.controls[2].name, "Open [private identifier]");
  assert.equal(state.controls[3].name, "Account [private identifier]");
});

test("control redaction preserves short functional numbers", async () => {
  const tab = fakeTab({
    urls: ["https://example.test/payments"],
    inventories: [inventory([control("Pay F24 for step 2")])],
  });

  const state = await captureControlState({
    tab,
    allowedOrigins: ["https://example.test"],
  });

  assert.equal(state.controls[0].name, "Pay F24 for step 2");
  assert.equal("redacted_fields" in state.controls[0], false);
});

test("private identifier changes do not alter the sanitized fingerprint", async () => {
  const first = await captureControlState({
    tab: fakeTab({
      urls: ["https://example.test/invoices"],
      inventories: [inventory([control("Download invoice 01234567890")])],
    }),
    allowedOrigins: ["https://example.test"],
  });
  const second = await captureControlState({
    tab: fakeTab({
      urls: ["https://example.test/invoices"],
      inventories: [inventory([control("Download invoice 10987654321")])],
    }),
    allowedOrigins: ["https://example.test"],
  });

  assert.equal(first.control_fingerprint, second.control_fingerprint);
});

test("captureControlState rejects a page outside the declared origins", async () => {
  const tab = fakeTab({
    urls: ["https://outside.test/process"],
    inventories: [inventory([])],
  });

  await assert.rejects(
    captureControlState({ tab, allowedOrigins: ["https://example.test"] }),
    /left allowed origins/,
  );
});

test("guided capture can opt into structured controls without enabling value capture", async () => {
  const structuredControl = {
    ...control("Invoice line"),
    structured_context: true,
  };
  const tab = fakeTab({
    urls: ["https://example.test/form", "https://example.test/form"],
    inventories: [
      inventory([structuredControl]),
      inventory([{ ...structuredControl, name: "Add invoice line" }]),
    ],
  });

  const capture = await observeGuidedWindow({
    tab,
    allowedOrigins: ["https://example.test"],
    durationMs: 1_000,
    pollIntervalMs: 100,
    maxTransitions: 1,
    includeStructuredControls: true,
  });

  assert.equal(capture.capture_policy.structured_rows_excluded, false);
  assert.equal(capture.capture_policy.structured_control_values_excluded, true);
  assert.equal("value" in capture.initial.controls[0], false);
});

test("queryFreeUrl removes query strings and fragments", () => {
  assert.equal(
    queryFreeUrl("https://example.test/path?private=value#step"),
    "https://example.test/path",
  );
});
