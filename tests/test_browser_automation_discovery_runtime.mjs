import assert from "node:assert/strict";
import test from "node:test";

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
  assert.equal(capture.transitions[0].before.path, "/start");
  assert.equal(capture.transitions[1].after.path, "/finish");
  assert.deepEqual(capture.capture_policy, {
    query_free_paths_only: true,
    form_values_excluded: true,
    structured_rows_excluded: true,
    screenshots_excluded: true,
    structured_control_values_excluded: true,
  });
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
