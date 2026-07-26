from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import add_review_decision_apply_tools as apply_generator
from scripts import add_review_decision_save_tools as save_generator
from scripts.review_decision_transaction_template import (
    APPLY_HELPERS_END,
    APPLY_HELPERS_START,
    REVIEW_OUTPUT_TRANSACTION_HELPER,
    SAVE_HELPERS_END,
    SAVE_HELPERS_START,
    TRANSACTION_HELPER_END,
    TRANSACTION_HELPER_START,
    upsert_marked_javascript_block,
    upsert_review_output_transaction,
)

ROOT = Path(__file__).resolve().parents[2]
TRANSACTION_RUNTIME = (
    ROOT
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "vera_assurance"
    / "review_output_transaction.cjs"
)

GENERIC_SERVER = r"""const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

const TOOL_NAMES = {
  validateReview: "validate_journal_sampling_review",
  renderReview: "render_journal_sampling_review",
};
const ALLOWED_ACTIONS = new Set([
  "accept",
  "reject",
  "edit",
  "mark_unclear",
  "request_more_documents",
  "skip",
]);
const ITEM_TYPES = new Set(["sampling_control"]);
const MAX_PAYLOAD_BYTES = 2_000_000;

function isPlainObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function objectSchema(properties, required = []) {
  return { type: "object", properties, required };
}

function toolDefinitions() {
  const reviewPayload = objectSchema(
    {
      schema_version: { type: "string" },
      plugin: { type: "string" },
      workflow: { type: "string" },
      run_id: { type: "string" },
      items: { type: "array", items: { type: "object" } },
      item_count: { type: "number" },
    },
    ["schema_version", "plugin", "workflow", "run_id", "items", "item_count"],
  );
  return [
    {
      name: TOOL_NAMES.validateReview,
      inputSchema: reviewPayload,
    },
  ];
}

function resources() {
  return [];
}

function payloadBytes(payload) {
  return Buffer.byteLength(JSON.stringify(payload), "utf8");
}

function validateItem(item, index) {
  if (!isPlainObject(item)) throw new Error(`invalid item ${index}`);
}

function validateReviewPayload(inputArgs) {
  const reviewPayload = inputArgs.review_payload;
  reviewPayload.items.forEach((item, index) => validateItem(item, index));
  const payload = {
    widget_type: "journal_sampling_review",
    run_intake: isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null,
    review_payload: reviewPayload,
  };
  if (payloadBytes(payload) > MAX_PAYLOAD_BYTES) {
    throw new Error("payload too large");
  }
  return payload;
}

function callTool(name, args = {}) {
  if (name === TOOL_NAMES.validateReview) return validateReviewPayload(args);
  throw new Error(`unknown Journal Sampling widget tool: ${name}`);
}

function toolResult(payload) {
  return payload;
}
"""


CUSTOM_REVIEW_HELPERS = r"""function resolveDecisionOutputPath(inputArgs) {
  return path.join(path.resolve(inputArgs.run_intake.output_dir), "ui_decisions.json");
}

function saveDecisionPayload(inputArgs) {
  return { ok: true, custom_save_hook: inputArgs.review_payload.run_id };
}

function resolveRunOutputDir(inputArgs) {
  return path.resolve(inputArgs.run_intake.output_dir);
}

function customAssurancePreflight(inputArgs) {
  return { report_ready: false, run_id: inputArgs.review_payload.run_id };
}

function validatePersistedWorkflowApplication(result) {
  if (!result.persisted_receipt) throw new Error("missing persisted receipt");
  return result;
}

function applyDecisionPayload(inputArgs) {
  const preflight = customAssurancePreflight(inputArgs);
  return validatePersistedWorkflowApplication({
    ok: true,
    persisted_receipt: "custom",
    preflight,
  });
}

function applyWorkflowSpecificReviewApplication() {
  return { custom_workflow_hook: true };
}

"""


def _target(
    targets: list[save_generator.Target] | list[apply_generator.Target],
    plugin: str,
) -> save_generator.Target | apply_generator.Target:
    return next(target for target in targets if target.plugin == plugin)


def _generate_generic_server() -> str:
    save_target = _target(save_generator.TARGETS, "journal-sampling")
    apply_target = _target(apply_generator.TARGETS, "journal-sampling")
    with_save = save_generator.patch_server(GENERIC_SERVER, save_target)
    return apply_generator.patch_server(with_save, apply_target)


def test_embedded_transaction_helper_matches_the_canonical_runtime_body() -> None:
    source = TRANSACTION_RUNTIME.read_text(encoding="utf-8")
    start = "// BEGIN EMBEDDABLE REVIEW OUTPUT TRANSACTION"
    end = "// END EMBEDDABLE REVIEW OUTPUT TRANSACTION"
    runtime_body = source.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]

    assert REVIEW_OUTPUT_TRANSACTION_HELPER.strip() == runtime_body.strip()


@pytest.mark.parametrize(
    "server_owned_runtime",
    [
        "const runtime = require(REVIEW_TRANSACTION_RUNTIME);\n",
        "function withOutputDirectoryTransaction(outputDir, operation) {}\n",
    ],
)
def test_transaction_generator_does_not_duplicate_imported_or_custom_runtime(
    server_owned_runtime: str,
) -> None:
    assert (
        upsert_review_output_transaction(
            server_owned_runtime,
            insert_before=("function missingAnchor() {}",),
        )
        == server_owned_runtime
    )


def test_report_builder_alone_owns_report_audit_transaction_authorization() -> None:
    runtime = TRANSACTION_RUNTIME.read_text(encoding="utf-8")
    collector = runtime.split(
        "function generatedReviewCollectApplicationWritePaths",
        maxsplit=1,
    )[1].split("function generatedReviewWorkflowTransactionOptions", maxsplit=1,)[0]
    server_matches = [
        server.relative_to(ROOT).as_posix()
        for server in sorted((ROOT / "plugins").glob("*/mcp/server.cjs"))
        if '"report_audit.json"' in server.read_text(encoding="utf-8")
    ]

    assert '"report_audit.json"' not in collector
    assert server_matches == ["plugins/report-builder/mcp/server.cjs"]


def test_generic_round_trip_emits_one_transaction_wrapped_save_and_apply_block(
    tmp_path: Path,
) -> None:
    generated = _generate_generic_server()

    assert generated.count(TRANSACTION_HELPER_START) == 1
    assert generated.count(TRANSACTION_HELPER_END) == 1
    assert generated.count(SAVE_HELPERS_START) == 1
    assert generated.count(SAVE_HELPERS_END) == 1
    assert generated.count(APPLY_HELPERS_START) == 1
    assert generated.count(APPLY_HELPERS_END) == 1
    assert "withGeneratedReviewOutputTransaction(" in generated
    assert 'generatedReviewWorkflowTransactionOptions(\n    "save",' in generated
    assert 'generatedReviewWorkflowTransactionOptions(\n    "apply",' in generated
    assert "generatedReviewTransactionEnvelope(" in generated
    assert "generatedReviewCollectApplicationWritePaths(" in generated
    assert "generatedReviewAtomicWriteFileSync(" in generated
    assert "function applyDecisionPayloadWrites(inputArgs)" in generated
    assert "fs.writeFileSync(decisionOutputPath" not in generated
    assert "maxEntryCount: 20_000" in generated
    assert "maxFileBytes: 128 * 1024 * 1024" in generated
    assert "maxTotalBytes: 512 * 1024 * 1024" in generated
    assert "O_NOFOLLOW" in generated
    assert "observed.nlink !== 1" in generated
    assert "trustedImage" in generated
    assert "authorizedWritePaths" in generated
    assert "validateWholeTree" in generated
    assert "bounded transaction contract, not an OS sandbox" in generated
    assert "arbitrary external copies" in generated

    second_save = save_generator.patch_server(
        generated,
        _target(save_generator.TARGETS, "journal-sampling"),
    )
    second_apply = apply_generator.patch_server(
        second_save,
        _target(apply_generator.TARGETS, "journal-sampling"),
    )

    assert second_apply == generated
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for generated JavaScript syntax checks.")
    server_path = tmp_path / "server.cjs"
    server_path.write_text(generated, encoding="utf-8")
    completed = subprocess.run(
        [node, "--check", str(server_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    "plugin",
    ["check-entries", "journal-bank-reconciliation", "report-builder"],
)
def test_round_trip_preserves_unmarked_workflow_specific_hooks(
    plugin: str,
) -> None:
    custom_server = GENERIC_SERVER.replace(
        "function callTool(name, args = {}) {",
        f"{CUSTOM_REVIEW_HELPERS}function callTool(name, args = {{}}) {{",
    )
    apply_target = _target(apply_generator.TARGETS, plugin)

    generated = custom_server
    save_target = next(
        (target for target in save_generator.TARGETS if target.plugin == plugin),
        None,
    )
    if save_target is not None:
        generated = save_generator.patch_server(generated, save_target)
    else:
        generated = generated.replace(
            '  renderReview: "render_journal_sampling_review",\n',
            '  renderReview: "render_journal_sampling_review",\n'
            f'  saveDecisions: "{apply_target.save_tool}",\n',
            1,
        )
    generated = apply_generator.patch_server(generated, apply_target)

    assert generated.count("function saveDecisionPayload(inputArgs)") == 1
    assert generated.count("function applyDecisionPayload(inputArgs)") == 1
    assert generated.count("function customAssurancePreflight(inputArgs)") == 1
    assert generated.count("function validatePersistedWorkflowApplication(result)") == 1
    assert generated.count("function applyWorkflowSpecificReviewApplication()") == 1
    assert 'persisted_receipt: "custom"' in generated
    assert "custom_workflow_hook: true" in generated
    assert generated.count(TRANSACTION_HELPER_START) == 1
    assert SAVE_HELPERS_START not in generated
    assert APPLY_HELPERS_START not in generated


def test_marker_refresh_replaces_only_generator_owned_content() -> None:
    source = "\n".join(
        [
            "const before = 'preserve-before';",
            TRANSACTION_HELPER_START,
            "const staleGeneratedHelper = true;",
            TRANSACTION_HELPER_END,
            "function customAssurancePostcondition() {",
            "  return 'preserve-after';",
            "}",
            "function callTool(name, args = {}) { return { name, args }; }",
            "",
        ]
    )

    refreshed = upsert_marked_javascript_block(
        source,
        start=TRANSACTION_HELPER_START,
        body=REVIEW_OUTPUT_TRANSACTION_HELPER,
        end=TRANSACTION_HELPER_END,
        insert_before=("function callTool(name, args = {}) {",),
    )

    assert "staleGeneratedHelper" not in refreshed
    assert "preserve-before" in refreshed
    assert "function customAssurancePostcondition()" in refreshed
    assert "preserve-after" in refreshed
    assert refreshed.count(TRANSACTION_HELPER_START) == 1
    assert refreshed.count(TRANSACTION_HELPER_END) == 1


def test_incomplete_generator_marker_fails_closed() -> None:
    source = f"{TRANSACTION_HELPER_START}\nconst incomplete = true;\n"

    with pytest.raises(RuntimeError, match="Incomplete generated block"):
        upsert_marked_javascript_block(
            source,
            start=TRANSACTION_HELPER_START,
            body=REVIEW_OUTPUT_TRANSACTION_HELPER,
            end=TRANSACTION_HELPER_END,
            insert_before=("function callTool(name, args = {}) {",),
        )


def test_duplicate_generator_marker_fails_closed() -> None:
    block = (
        f"{TRANSACTION_HELPER_START}\nconst duplicate = true;\n"
        f"{TRANSACTION_HELPER_END}\n"
    )

    with pytest.raises(RuntimeError, match="Duplicate generated block"):
        upsert_marked_javascript_block(
            block + block,
            start=TRANSACTION_HELPER_START,
            body=REVIEW_OUTPUT_TRANSACTION_HELPER,
            end=TRANSACTION_HELPER_END,
            insert_before=("function callTool(name, args = {}) {",),
        )


def test_transaction_helper_restores_trusted_bytes_and_modes_and_gates_writes(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for transaction helper execution.")
    harness = f"""const fs = require("node:fs");
const path = require("node:path");
function isPlainObject(value) {{
  return value != null && typeof value === "object" && !Array.isArray(value);
}}
{REVIEW_OUTPUT_TRANSACTION_HELPER}

const root = process.argv[2];
const output = path.join(root, "output");
fs.mkdirSync(output, {{ mode: 0o750 }});
const prior = path.join(output, "prior.txt");
fs.writeFileSync(prior, "ORIGINAL\\n", {{ mode: 0o640 }});
fs.chmodSync(prior, 0o640);
const priorInode = fs.statSync(prior).ino;
const realMkdirSync = fs.mkdirSync;
let setupFailure = null;
try {{
  fs.mkdirSync = (targetPath, ...args) => {{
    if (
      path.basename(targetPath) === "working" &&
      path.basename(path.dirname(targetPath)).startsWith(
        ".generated-review-transaction-",
      )
    ) {{
      throw new Error("/private/client/path materialization failed");
    }}
    return realMkdirSync(targetPath, ...args);
  }};
  withGeneratedReviewOutputTransaction(
    output,
    () => generatedReviewTransactionEnvelope({{ ok: true }}, []),
    {{ failureMessage: "fixed setup failure" }},
  );
}} catch (error) {{
  setupFailure = error.message;
}} finally {{
  fs.mkdirSync = realMkdirSync;
}}
if (setupFailure !== "fixed setup failure") {{
  throw new Error(`unexpected setup failure: ${{setupFailure}}`);
}}
if (fs.statSync(prior).ino !== priorInode) {{
  throw new Error("pre-detach failure replaced the canonical output");
}}

let failure = null;
try {{
  withGeneratedReviewOutputTransaction(
    output,
    ({{ workingOutputDir }}) => {{
      generatedReviewAtomicWriteFileSync(
        path.join(workingOutputDir, "prior.txt"),
        "REJECTED\\n",
        "utf8",
      );
      throw new Error("/private/client/path must not escape");
    }},
    {{ failureMessage: "fixed path-free failure" }},
  );
}} catch (error) {{
  failure = error.message;
}}
if (failure !== "fixed path-free failure") {{
  throw new Error(`unexpected failure: ${{failure}}`);
}}
if (fs.readFileSync(prior, "utf8") !== "ORIGINAL\\n") {{
  throw new Error("rollback bytes changed");
}}
if ((fs.statSync(prior).mode & 0o777) !== 0o640) {{
  throw new Error("rollback file mode changed");
}}
if ((fs.statSync(output).mode & 0o777) !== 0o750) {{
  throw new Error("rollback root mode changed");
}}

let mappedFailure = null;
try {{
  withGeneratedReviewOutputTransaction(
    output,
    () => {{
      throw new Error("safe workflow failure");
    }},
    {{
      failureMessage: "mapped failure fallback",
      mapOperationError(error) {{
        return error.message;
      }},
    }},
  );
}} catch (error) {{
  mappedFailure = error.message;
}}
if (mappedFailure !== "safe workflow failure") {{
  throw new Error(`unexpected mapped failure: ${{mappedFailure}}`);
}}

let unsafeMappedFailure = null;
try {{
  withGeneratedReviewOutputTransaction(
    output,
    () => {{
      throw new Error("/private/client/path must not escape");
    }},
    {{
      failureMessage: "unsafe mapped failure fallback",
      mapOperationError(error) {{
        return error.message;
      }},
    }},
  );
}} catch (error) {{
  unsafeMappedFailure = error.message;
}}
if (unsafeMappedFailure !== "unsafe mapped failure fallback") {{
  throw new Error(`unexpected unsafe mapped failure: ${{unsafeMappedFailure}}`);
}}

const unsafeOutput = path.join(root, "unsafe-output");
fs.mkdirSync(unsafeOutput);
fs.symlinkSync(prior, path.join(unsafeOutput, "poison-link"));
let unsafeFailure = null;
try {{
  withGeneratedReviewOutputTransaction(
    unsafeOutput,
    () => generatedReviewTransactionEnvelope({{ ok: true }}, []),
    {{ failureMessage: "fixed unsafe preflight failure" }},
  );
}} catch (error) {{
  unsafeFailure = error.message;
}}
if (unsafeFailure !== "fixed unsafe preflight failure") {{
  throw new Error(`unexpected unsafe preflight result: ${{unsafeFailure}}`);
}}
if (!fs.lstatSync(path.join(unsafeOutput, "poison-link")).isSymbolicLink()) {{
  throw new Error("unsafe preflight changed the canonical output");
}}

const hardLinkOutput = path.join(root, "hard-link-output");
fs.mkdirSync(hardLinkOutput);
const hardLinkSource = path.join(root, "hard-link-source.txt");
fs.writeFileSync(hardLinkSource, "LINKED\\n");
fs.linkSync(hardLinkSource, path.join(hardLinkOutput, "linked.txt"));
let hardLinkFailure = null;
try {{
  withGeneratedReviewOutputTransaction(
    hardLinkOutput,
    () => generatedReviewTransactionEnvelope({{ ok: true }}, []),
    {{ failureMessage: "fixed hard-link preflight failure" }},
  );
}} catch (error) {{
  hardLinkFailure = error.message;
}}
if (hardLinkFailure !== "fixed hard-link preflight failure") {{
  throw new Error(`unexpected hard-link result: ${{hardLinkFailure}}`);
}}

const acceptPaths = generatedReviewCollectApplicationWritePaths({{
  applied_decisions: {{
    effects: [
      {{
        action: "accept",
        target_artifact: "must-not-be-authorized.txt",
      }},
    ],
  }},
}});
if (acceptPaths.includes("must-not-be-authorized.txt")) {{
  throw new Error("manifest-only target was incorrectly authorized");
}}

let unauthorized = null;
try {{
  withGeneratedReviewOutputTransaction(
    output,
    ({{ workingOutputDir }}) => {{
      generatedReviewAtomicWriteFileSync(
        path.join(workingOutputDir, "rogue.txt"),
        "ROGUE\\n",
        "utf8",
      );
      return generatedReviewTransactionEnvelope({{ ok: true }}, []);
    }},
    {{ failureMessage: "unauthorized write rejected" }},
  );
}} catch (error) {{
  unauthorized = error.message;
}}
if (unauthorized !== "unauthorized write rejected") {{
  throw new Error(`unexpected authorization result: ${{unauthorized}}`);
}}
if (fs.existsSync(path.join(output, "rogue.txt"))) {{
  throw new Error("unauthorized file survived");
}}

const preRelocationImage = generatedReviewCaptureDirectoryImage(output);
const preRelocationInode = fs.statSync(output).ino;
let relocationFailure = null;
try {{
  withGeneratedReviewOutputTransaction(
    output,
    ({{ workingOutputDir }}) => {{
      generatedReviewAtomicWriteFileSync(
        path.join(workingOutputDir, "prior.txt"),
        "RELOCATED\\n",
        "utf8",
      );
      const transactionRoot = path.dirname(workingOutputDir);
      fs.renameSync(transactionRoot, `${{transactionRoot}}-moved`);
      return generatedReviewTransactionEnvelope(
        {{ ok: true }},
        ["prior.txt"],
      );
    }},
    {{ failureMessage: "relocated transaction rejected" }},
  );
}} catch (error) {{
  relocationFailure = error.message;
}}
if (relocationFailure !== "relocated transaction rejected") {{
  throw new Error(`unexpected relocation result: ${{relocationFailure}}`);
}}
if (fs.statSync(output).ino !== preRelocationInode) {{
  throw new Error("transaction-root relocation replaced canonical output");
}}
if (
  !generatedReviewImagesEqual(
    preRelocationImage,
    generatedReviewCaptureDirectoryImage(output),
  )
) {{
  throw new Error("transaction-root relocation changed canonical output");
}}
if (
  fs.readdirSync(root).some((name) =>
    name.startsWith(".generated-review-transaction-"),
  )
) {{
  throw new Error("relocated transaction sibling survived");
}}

let hookCalled = false;
const priorUmask = process.umask(0o077);
let committed;
try {{
  committed = withGeneratedReviewOutputTransaction(
    output,
    ({{ workingOutputDir }}) => {{
      generatedReviewAtomicWriteFileSync(
        path.join(workingOutputDir, "prior.txt"),
        "COMMITTED\\n",
        "utf8",
      );
      return generatedReviewTransactionEnvelope(
        {{ ok: true }},
        ["prior.txt"],
      );
    }},
    {{
      validateWholeTree(context) {{
        hookCalled = context.authorizedWritePaths.has("prior.txt");
      }},
    }},
  );
}} finally {{
  process.umask(priorUmask);
}}
if (!committed.ok || !hookCalled) {{
  throw new Error("authorized transaction did not close");
}}
if (fs.readFileSync(prior, "utf8") !== "COMMITTED\\n") {{
  throw new Error("authorized bytes did not commit");
}}
if ((fs.statSync(prior).mode & 0o777) !== 0o640) {{
  throw new Error("commit file mode changed");
}}
if (
  fs.readdirSync(root).some((name) =>
    name.startsWith(".generated-review-transaction-"),
  )
) {{
  throw new Error("transaction root leaked");
}}
"""
    harness_path = tmp_path / "transaction-harness.cjs"
    harness_path.write_text(harness, encoding="utf-8")

    completed = subprocess.run(
        [node, str(harness_path), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
