"""Verify portable review UI, evidence identity and durable decision handoff."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def pipeline_module() -> ModuleType:
    path = ROOT / "plugins/deep-research-validator/scripts/pipeline_review.py"
    spec = importlib.util.spec_from_file_location("pipeline_review_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _case(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "outputs"
    root.mkdir()
    record = {
        "method": "shared_agentic_legal_tax_research",
        "issues": [
            {
                "id": "issue-1",
                "question": "Does the exception apply?",
                "status": "open",
                "evidence": ["capture.txt paragraph 1"],
            }
        ],
        "cycles": [
            {
                "id": "cycle-1",
                "purpose": "Test the exception",
                "challenge": "An adverse authority remains unresolved",
            }
        ],
        "completion": {"status": "in_progress", "limits": ["Client evidence missing"]},
    }
    (root / "research_review.json").write_text(json.dumps(record))
    (root / "research_record.md").write_text("Actual investigations only")
    return root, {
        "run_root": str(tmp_path),
        "run_id": "research-case",
        "language": "en",
    }


def test_pipeline_review_displays_open_issues_without_inventing_closure(
    tmp_path, pipeline_module
):
    root, context = _case(tmp_path)

    result = pipeline_module.write_pipeline_review(root, context)

    payload = json.loads((root / "review_payload.json").read_text())
    assert result["declared_research_status"] == "in_progress"
    assert payload["items"][0]["data"]["status"] == "open"
    assert (
        payload["items"][1]["data"]["challenge"]
        == "An adverse authority remains unresolved"
    )
    assert "edit" not in payload["items"][0]["allowed_actions"]
    assert (
        json.loads((root / "final_artifacts.json").read_text())["status"]
        == "written_pending_review"
    )


def test_pipeline_review_includes_both_opinions_comparison_and_source_identity(
    tmp_path, pipeline_module
):
    root, context = _case(tmp_path)
    for name, text in (
        ("position/validated_document.md", "Original opinion"),
        ("adversarial/validated_document.md", "Opposing opinion"),
        ("opinion_comparison.md", "Professional choice remains"),
        ("adversarial_assessment.json", '{"outcome":"evidence_limited"}'),
        ("research/sources/capture.txt", "Actual captured source"),
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    pipeline_module.write_pipeline_review(root, context)

    payload = json.loads((root / "review_payload.json").read_text())
    views = {item["source_path"]: item for item in payload["items"]}
    assert views["position/validated_document.md"]["data"]["text"] == "Original opinion"
    assert (
        views["adversarial/validated_document.md"]["data"]["text"] == "Opposing opinion"
    )
    assert (
        views["opinion_comparison.md"]["data"]["text"] == "Professional choice remains"
    )
    assert "research/sources/capture.txt" in {
        binding["path"] for binding in payload["source_bindings"]
    }


def test_pipeline_review_labels_an_excerpt_and_binds_the_complete_source(
    tmp_path, pipeline_module
):
    root, context = _case(tmp_path)
    source = root / "research/sources/long.txt"
    source.parent.mkdir(parents=True)
    source.write_text("x" * 13000 + "Decisive qualification at the end")

    pipeline_module.write_pipeline_review(root, context)

    payload = json.loads((root / "review_payload.json").read_text())
    view = next(
        item
        for item in payload["items"]
        if item["source_path"] == "research/sources/long.txt"
    )
    assert view["data"]["preview_is_excerpt"] is True
    assert len(view["data"]["text"]) == 12000
    assert "complete text" in view["data"]["preview_notice"]
    binding = next(
        binding
        for binding in payload["source_bindings"]
        if binding["path"] == "research/sources/long.txt"
    )
    assert binding["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


@pytest.mark.parametrize("changed", [False, True])
def test_pipeline_review_retains_decisions_or_archives_the_previous_revision(
    tmp_path, pipeline_module, changed
):
    root, context = _case(tmp_path)
    pipeline_module.write_pipeline_review(root, context)
    decisions_path = root / "ui_decisions.json"
    decisions = json.loads(decisions_path.read_text())
    decisions["decisions"] = [{"item_id": "issues-issue-1", "action": "reject"}]
    decisions_path.write_text(json.dumps(decisions))
    if changed:
        (root / "research_record.md").write_text("New investigation after rejection")

    pipeline_module.write_pipeline_review(root, context)

    current = json.loads(decisions_path.read_text())
    if changed:
        history = list((root / "review_history").glob("*/ui_decisions.json"))
        assert len(history) == 1
        assert json.loads(history[0].read_text())["decisions"] == decisions["decisions"]
        assert current["decisions"] == []
    else:
        assert current["decisions"] == decisions["decisions"]


@pytest.mark.parametrize("relative", ["review_payload.json", "research_record.md"])
def test_pipeline_review_rejects_symlinks_outside_the_output_before_writing(
    tmp_path, pipeline_module, relative
):
    root, context = _case(tmp_path)
    outside = tmp_path / "private.txt"
    outside.write_text("Unrelated file")
    candidate = root / relative
    candidate.unlink(missing_ok=True)
    candidate.symlink_to(outside)

    with pytest.raises(ValueError, match="escapes"):
        pipeline_module.write_pipeline_review(root, context)

    assert outside.read_text() == "Unrelated file"
    assert not (root / "run_intake.json").exists()


@pytest.mark.parametrize("legacy", [False, True])
def test_review_bridge_calls_tools_with_standard_or_compatibility_host(legacy):
    node = shutil.which("node")
    assert node is not None
    script = r"""
const fs = require("node:fs"), vm = require("node:vm");
const listeners = {}, calls = [], legacy = process.argv[2] === "true";
const window = {addEventListener:(name, fn)=>listeners[name]=fn, dispatchEvent:()=>{}};
if (legacy) {
  window.parent = window;
  window.openai = {callTool: async (name,args)=>{calls.push({name,arguments:args});return {ok:true};}};
} else {
  window.parent = {postMessage(message){
    calls.push(message);
    if (message.id) queueMicrotask(()=>listeners.message({source:window.parent,origin:"https://host.example",data:{jsonrpc:"2.0",id:message.id,result: message.method==="tools/call" ? {structuredContent:{ok:true}} : {}}}));
  }};
}
const context = {window, setTimeout, clearTimeout, Event, console, Map, Set, Promise};
vm.runInNewContext(fs.readFileSync(process.argv[1],"utf8"),context);
(async()=>{
 const result=await window.mparanzaReviewHost.callTool("save_review",{decisions:[{item_id:"issue-1",action:"reject"}]});
 process.stdout.write(JSON.stringify({calls,result,available:window.mparanzaReviewHost.canCallTools()}));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""

    response = subprocess.run(
        [
            node,
            "-e",
            script,
            str(ROOT / "scripts/review_mcp_apps_bridge.js"),
            str(legacy).lower(),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )

    output = json.loads(response.stdout)
    assert output["available"] is True
    if legacy:
        assert output["calls"][0]["name"] == "save_review"
    else:
        assert output["calls"][0]["method"] == "ui/initialize"
        assert output["calls"][2]["method"] == "tools/call"
        assert (
            output["calls"][2]["params"]["arguments"]["decisions"][0]["action"]
            == "reject"
        )


@pytest.mark.parametrize(
    "changed,action",
    [
        (None, "reject"),
        (None, "accept"),
        ("research_review.json", "accept"),
        ("answer_contract.json", "accept"),
        ("bound-source.txt", "accept"),
    ],
)
def test_native_pipeline_decisions_persist_and_reject_changed_evidence(
    tmp_path, pipeline_module, changed, action
):
    spec = importlib.util.spec_from_file_location(
        "native_ui_ledger", ROOT / "plugins/studio-archive/scripts/client_ledger.py"
    )
    assert spec is not None and spec.loader is not None
    ledger = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ledger
    spec.loader.exec_module(ledger)
    client_root = tmp_path / "Client"
    client_root.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client_root, client_id)
    engagement = ledger.create_engagement(client_root, client_id, "Research UI")
    source = tmp_path / "question.txt"
    source.write_text("Is the condition met?")
    imported = ledger.import_document(
        client_root, client_id, engagement["engagement_id"], source, "source"
    )
    prepared = ledger.prepare_run(
        client_root,
        client_id,
        engagement["engagement_id"],
        "deep-research-validator",
        "test-version",
        input_ids=[imported["receipt"]["input_id"]],
    )
    running = ledger.start_run(
        client_root, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    root = Path(running["output_dir"])
    (root / "answer_contract.json").write_text('{"scope":"Condition X only"}')
    (root / "bound-source.txt").write_text(
        "Fictional source outside the default capture folder"
    )
    (root / "research_review.json").write_text(
        json.dumps(
            {
                "method": "shared_agentic_legal_tax_research",
                "issues": [
                    {"id": "i1", "question": "Which condition?", "status": "open"}
                ],
                "cycles": [],
                "completion": {"status": "in_progress"},
                "binding": {
                    "artifacts": [{"role": "source", "path": "bound-source.txt"}]
                },
            }
        )
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins/deep-research-validator/scripts/research_record.py"),
            "review-ui",
            "--output-dir",
            str(root),
            "--client-engagement",
            running["context"]["context_path"],
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    intake = json.loads((root / "run_intake.json").read_text())
    final = json.loads((root / "final_artifacts.json").read_text())
    reference = {
        "path": "review_payload.json",
        "run_id": intake["run_id"],
        "review_payload_sha256": final["review_payload_sha256"],
    }
    args = {
        "run_intake": intake,
        "client_engagement": running["context"]["context_path"],
        "review_reference": reference,
    }
    node = shutil.which("node")
    assert node is not None
    process = subprocess.Popen(
        [node, str(ROOT / "plugins/deep-research-validator/mcp/server.cjs")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None and process.stdout is not None
    try:
        process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "render_deep_research_review",
                        "arguments": args,
                    },
                }
            )
            + "\n"
        )
        process.stdin.flush()
        rendered = json.loads(process.stdout.readline())["result"]
        assert not rendered.get("isError"), rendered
        token = rendered["structuredContent"]["review_reference"]["persistence_token"]
        if changed:
            (root / changed).write_text("Changed evidence")
        payload = json.loads((root / "review_payload.json").read_text())
        decision_args = {
            "persistence_token": token,
            "decisions": [
                {"item_id": item["id"], "action": action} for item in payload["items"]
            ],
        }

        process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "apply_deep_research_decisions",
                        "arguments": decision_args,
                    },
                }
            )
            + "\n"
        )
        process.stdin.flush()
        response = json.loads(process.stdout.readline())["result"]

        if changed:
            assert response["isError"] is True
            assert "Research evidence changed" in response["content"][0]["text"]
            assert not (root / "applied_decisions.json").exists()
        else:
            assert not response.get("isError"), response
            applied = json.loads((root / "applied_decisions.json").read_text())
            assert applied["application_status"] == (
                "blocked" if action == "reject" else "research_review_applied"
            )
            assert (
                json.loads((root / "research_review.json").read_text())["issues"][0][
                    "status"
                ]
                == "open"
            )
    finally:
        process.stdin.close()
        process.wait(timeout=20)
