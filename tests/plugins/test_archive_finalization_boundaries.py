"""Archive path handoffs and the exact failed-response reporting boundary."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_archive_automatic_reporting import (
    USER_ID,
    archive_core,
    archive_script_imports,
    client_case,
    finish,
    reporting_runtime,
    start,
)
from tests.plugins.test_vera_studio_archive_component import (
    _mcp_tool,
    isolated_mcp_launcher,
)


def result_case(core, case):
    loaded = start(core, case)
    output = Path(loaded["output_dir"])
    (output / "result.txt").write_text("Professional result\n", encoding="utf-8")
    declaration = {
        "artifact_id": "result",
        "path": "result.txt",
        "purpose": "Professional result",
        "audience": "review",
        "media_type": "text/plain",
    }
    return loaded, output, declaration


@pytest.mark.parametrize("path_base", ["output", "run", "absolute"])
def test_finalize_accepts_owned_file_paths_and_seals_canonical_paths(
    archive_core, client_case, path_base
):
    loaded, output, declaration = result_case(archive_core, client_case)
    declaration["path"] = {
        "output": "result.txt",
        "run": "outputs/result.txt",
        "absolute": str(output / "result.txt"),
    }[path_base]

    result = archive_core.finalize_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        loaded["run"]["run_id"],
        [declaration],
        state_dir=client_case.state_dir,
    )

    assert result["status"] == "ready_for_review"
    assert {item["path"] for item in result["artifact_manifest"]["artifacts"]} == {
        "result.txt",
        "model_data_report.json",
        "model_data_report.md",
    }


def declaration_revision_case(core, case):
    """Retain a review-ready output already selected by a downstream run."""
    loaded, output, declaration = result_case(core, case)
    initial = core.finalize_studio_client_workflow(
        case.client_id,
        case.engagement_id,
        loaded["run"]["run_id"],
        [declaration],
        state_dir=case.state_dir,
    )
    downstream = core.prepare_studio_client_workflow(
        case.engagement_id,
        "variance-analysis",
        input_ids=[case.imported["input_id"]],
        upstream_artifacts=[
            {
                "run_id": loaded["run"]["run_id"],
                "artifact_id": "result",
                "role": "reviewed-prior-result",
            }
        ],
        new_run=True,
        state_dir=case.state_dir,
    )
    return loaded, output, declaration, initial, downstream


def revise_declaration(core, case, loaded, declaration, initial):
    return core.finalize_studio_client_workflow(
        case.client_id,
        case.engagement_id,
        loaded["run"]["run_id"],
        [{**declaration, "audience": "internal", "purpose": "Retained technical copy"}],
        expected_declaration_sha256=initial["declaration_sha256"],
        state_dir=case.state_dir,
    )


def test_review_ready_metadata_correction_preserves_existing_handoff(
    archive_core, client_case
):
    loaded, output, declaration, initial, downstream = declaration_revision_case(
        archive_core, client_case
    )
    prior_manifest = (Path(loaded["run_root"]) / "artifact_manifest.json").read_bytes()
    prior_result = (output / "result.txt").read_bytes()

    revised = revise_declaration(
        archive_core, client_case, loaded, declaration, initial
    )

    result = next(
        item
        for item in revised["artifact_manifest"]["artifacts"]
        if item["artifact_id"] == "result"
    )
    assert revised["status"] == "ready_for_review"
    assert result["audience"] == "internal"
    assert result["purpose"] == "Retained technical copy"
    assert revised["declaration_sha256"] != initial["declaration_sha256"]
    assert (output / "result.txt").read_bytes() == prior_result
    history = Path(loaded["run_root"]) / "artifact-manifest-history"
    assert (
        history / f"{initial['artifact_manifest']['content_sha256']}.json"
    ).read_bytes() == prior_manifest
    replayed = archive_core.ledger.load_run(
        client_case.client_root, client_case.engagement_id, downstream["run"]["run_id"]
    )
    assert replayed["run"]["status"] == "prepared"


def test_reporting_closure_preserves_handoffs_before_and_after_metadata_revision(
    archive_core, client_case
):
    loaded, _, declaration, initial, earlier = declaration_revision_case(
        archive_core, client_case
    )
    revise_declaration(archive_core, client_case, loaded, declaration, initial)
    later = archive_core.prepare_studio_client_workflow(
        client_case.engagement_id,
        "variance-analysis",
        input_ids=[client_case.imported["input_id"]],
        upstream_artifacts=[
            {
                "run_id": loaded["run"]["run_id"],
                "artifact_id": "result",
                "role": "prior",
            }
        ],
        new_run=True,
        state_dir=client_case.state_dir,
    )

    completed = archive_core.complete_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        loaded["run"]["run_id"],
        state_dir=client_case.state_dir,
    )

    assert completed["run"]["status"] == "completed"
    assert (
        archive_core.ledger.load_run(
            client_case.client_root, client_case.engagement_id, earlier["run"]["run_id"]
        )["run"]["status"]
        == "prepared"
    )
    assert (
        archive_core.ledger.load_run(
            client_case.client_root, client_case.engagement_id, later["run"]["run_id"]
        )["run"]["status"]
        == "prepared"
    )


def test_stale_declaration_revision_cannot_overwrite_another_review(
    archive_core, client_case
):
    loaded, _, declaration, initial, _ = declaration_revision_case(
        archive_core, client_case
    )
    revise_declaration(archive_core, client_case, loaded, declaration, initial)
    manifest = Path(loaded["run_root"]) / "artifact_manifest.json"
    retained = manifest.read_bytes()

    with pytest.raises(archive_core.ArchiveError, match="declarations changed"):
        archive_core.finalize_studio_client_workflow(
            client_case.client_id,
            client_case.engagement_id,
            loaded["run"]["run_id"],
            [declaration],
            expected_declaration_sha256=initial["declaration_sha256"],
            state_dir=client_case.state_dir,
        )

    assert manifest.read_bytes() == retained


def test_declaration_revision_cannot_reseal_changed_professional_bytes(
    archive_core, client_case
):
    loaded, output, declaration, initial, _ = declaration_revision_case(
        archive_core, client_case
    )
    (output / "result.txt").write_text("Different calculation\n")

    with pytest.raises(archive_core.ArchiveError, match="changed|no longer matches"):
        revise_declaration(archive_core, client_case, loaded, declaration, initial)


def test_later_upstream_receipt_tampering_preserves_the_admitted_handoff(
    archive_core, client_case
):
    loaded, output, declaration, initial, downstream = declaration_revision_case(
        archive_core, client_case
    )
    revise_declaration(archive_core, client_case, loaded, declaration, initial)
    history = Path(loaded["run_root"]) / "artifact-manifest-history"
    receipt = history / f"{initial['artifact_manifest']['content_sha256']}.json"
    payload = json.loads(receipt.read_text())
    payload["artifacts"][0]["purpose"] = "Unrecorded replacement"
    receipt.write_text(json.dumps(payload))

    replayed = archive_core.ledger.load_run(
        client_case.client_root,
        client_case.engagement_id,
        downstream["run"]["run_id"],
    )

    assert replayed["run"]["run_id"] == downstream["run"]["run_id"]
    assert replayed["run"]["status"] == "prepared"
    bound = next(
        item
        for item in replayed["context"]["input_bindings"]
        if item.get("upstream_artifact_id") == "result"
    )
    assert Path(bound["path"]).read_bytes() == (output / "result.txt").read_bytes()
    assert (
        json.loads(receipt.read_text())["artifacts"][0]["purpose"]
        == "Unrecorded replacement"
    )


def test_public_mcp_can_correct_review_ready_declarations(
    archive_core, client_case, isolated_mcp_launcher
):
    loaded, output, declaration, initial, _ = declaration_revision_case(
        archive_core, client_case
    )
    archive_core._release_state_leases()

    response = _mcp_tool(
        "finalize_studio_client_workflow",
        {
            "client_id": client_case.client_id,
            "engagement_id": client_case.engagement_id,
            "run_id": loaded["run"]["run_id"],
            "artifacts": [{**declaration, "audience": "internal"}],
            "expected_declaration_sha256": initial["declaration_sha256"],
        },
        state_dir=client_case.state_dir,
    )

    assert not response.get("isError"), response
    result = response["structuredContent"]
    assert result["status"] == "ready_for_review"
    assert result["declaration_sha256"] != initial["declaration_sha256"]
    assert (output / "result.txt").read_text() == "Professional result\n"
    assert (
        next(
            item
            for item in result["artifact_manifest"]["artifacts"]
            if item["artifact_id"] == "result"
        )["audience"]
        == "internal"
    )


def test_completed_run_rejects_declaration_correction_without_changing_its_receipt(
    archive_core, client_case
):
    loaded, _, declaration, initial, _ = declaration_revision_case(
        archive_core, client_case
    )
    archive_core.complete_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        loaded["run"]["run_id"],
        state_dir=client_case.state_dir,
    )
    manifest = Path(loaded["run_root"]) / "artifact_manifest.json"
    before = manifest.read_bytes()

    with pytest.raises(
        archive_core.ArchiveError, match="Only a running or review-ready run"
    ):
        revise_declaration(archive_core, client_case, loaded, declaration, initial)

    assert manifest.read_bytes() == before


@pytest.mark.parametrize("failure_phase", ["mcp_validation", "worker"])
def test_failed_archive_tool_records_exact_error_and_cannot_claim_complete_coverage(
    archive_core, client_case, isolated_mcp_launcher, failure_phase
):
    from archive_report_store import RunStore, digest

    loaded, _, declaration = result_case(archive_core, client_case)
    if failure_phase == "mcp_validation":
        del declaration["purpose"]
    else:
        declaration["path"] = "missing.txt"
    arguments = {
        "client_id": client_case.client_id,
        "engagement_id": client_case.engagement_id,
        "run_id": loaded["run"]["run_id"],
        "artifacts": [declaration],
    }
    archive_core._release_state_leases()

    response = _mcp_tool(
        "finalize_studio_client_workflow", arguments, state_dir=client_case.state_dir
    )

    assert response["isError"] is True, response
    sends = [
        event
        for event in RunStore(Path(loaded["run_root"])).events()
        if event.get("channel") == "mcp:studio-archive:error"
    ]
    assert len(sends) == 1
    assert sends[0]["response_sha256"] == digest(response)
    assert sends[0]["unmapped"] is True
    report = finish(archive_core, client_case, loaded)
    assert report["user_id"] == USER_ID
    assert report["run_id"] == loaded["run"]["run_id"]
    assert report["collection_status"] == "incomplete"
    assert "sent_data_has_no_source_coordinates" in report["errors"]


@pytest.mark.parametrize("input_available", [True, False])
def test_bound_error_recorder_retains_actual_payload_without_inventing_provenance(
    archive_core, client_case, input_available
):
    from archive_error_reporting import record_error
    from archive_report_store import RunStore, digest

    loaded, _, _ = result_case(archive_core, client_case)
    if not input_available:
        Path(loaded["context"]["input_bindings"][0]["path"]).unlink()
    archive_core._release_state_leases()
    payload = {"error": {"message": "Potential client content in an exception"}}

    recorded = record_error(
        {
            "client_id": client_case.client_id,
            "engagement_id": client_case.engagement_id,
            "run_id": loaded["run"]["run_id"],
        },
        payload,
        channel="cli",
        state_dir=client_case.state_dir,
    )

    assert recorded is True
    sends = [
        item
        for item in RunStore(Path(loaded["run_root"])).events()
        if item.get("channel") == "cli:studio-archive:error"
    ]
    assert len(sends) == 1
    assert sends[0]["response_sha256"] == digest(payload)
    assert sends[0]["unmapped"] is True


def test_error_recorder_rejects_reporting_state_from_another_run(
    archive_core, client_case
):
    from archive_error_reporting import record_error
    from archive_report_store import RunStore

    loaded, _, _ = result_case(archive_core, client_case)
    store = RunStore(Path(loaded["run_root"]))
    store.save({**store.state(), "run_id": "run_" + "0" * 24})
    archive_core._release_state_leases()
    before = store.events()

    with pytest.raises(ValueError, match="another Archive run"):
        record_error(
            {
                "client_id": client_case.client_id,
                "engagement_id": client_case.engagement_id,
                "run_id": loaded["run"]["run_id"],
            },
            {"error": "unknown"},
            channel="cli",
            state_dir=client_case.state_dir,
        )

    assert store.events() == before


@pytest.mark.parametrize(
    "scope",
    [
        "missing_identity",
        "wrong_client",
        "unselected",
        "prepared",
        "closed",
        "other_product",
    ],
)
def test_error_recorder_preserves_unrelated_or_inactive_report_state(
    archive_core, client_case, monkeypatch, scope
):
    from types import SimpleNamespace

    import client_ledger
    from archive_error_reporting import record_error

    if scope == "prepared":
        prepared = archive_core.prepare_studio_client_workflow(
            client_case.engagement_id,
            "variance-analysis",
            input_ids=[client_case.imported["input_id"]],
            state_dir=client_case.state_dir,
        )
        loaded = archive_core.ledger.load_run(
            client_case.client_root,
            client_case.engagement_id,
            prepared["run"]["run_id"],
        )
    else:
        loaded = start(
            archive_core,
            client_case,
            "financial-analysis" if scope == "unselected" else "variance-analysis",
        )
    if scope == "closed":
        finish(archive_core, client_case, loaded)
    if scope == "other_product":
        monkeypatch.setattr(
            client_ledger,
            "_reporting_runtime",
            lambda: SimpleNamespace(selective_reporting_enabled=lambda: False),
        )
    arguments = {
        "client_id": client_case.client_id,
        "engagement_id": client_case.engagement_id,
        "run_id": loaded["run"]["run_id"],
    }
    if scope == "missing_identity":
        del arguments["run_id"]
    if scope == "wrong_client":
        arguments["client_id"] = "client_" + "0" * 24
    archive_core._release_state_leases()
    root = Path(loaded["run_root"])
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    recorded = record_error(
        arguments, {"error": "unknown"}, channel="cli", state_dir=client_case.state_dir
    )

    assert recorded is False
    assert {
        path: path.read_bytes() for path in root.rglob("*") if path.is_file()
    } == before


@pytest.mark.parametrize("recorder_exit", [0, 1])
def test_mcp_retains_operation_error_when_recording_write_fails(
    tmp_path, monkeypatch, recorder_exit
):
    import tests.plugins.test_vera_studio_archive_component as component_tests

    product = tmp_path / "product"
    server = product / "modules/studio-archive/mcp/server.cjs"
    server.parent.mkdir(parents=True)
    source = Path(__file__).resolve().parents[2] / "plugins/studio-archive"
    shutil.copy2(source / "mcp/server.cjs", server)
    (server.parent.parent / ".codex-plugin").mkdir()
    shutil.copy2(
        source / ".codex-plugin/plugin.json",
        server.parent.parent / ".codex-plugin/plugin.json",
    )
    scripts = product / "scripts"
    scripts.mkdir()
    (scripts / "managed_python_runtime.py").write_text(
        "import json,sys\n"
        f"if 'record-error' in sys.argv: raise SystemExit({recorder_exit})\n"
        "print(json.dumps({'error': {'message': 'PRIVATE_UNRECORDED_ERROR'}}))\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(component_tests, "MCP_SERVER_PATH", server)

    response = _mcp_tool(
        "complete_studio_client_workflow",
        {
            "client_id": "client_" + "0" * 24,
            "engagement_id": "eng_" + "0" * 24,
            "run_id": "run_" + "0" * 24,
        },
        state_dir=tmp_path / "state",
    )

    assert response["isError"] is True
    assert response["structuredContent"]["error"]["code"] == "archive_operation_failed"
    assert "PRIVATE_UNRECORDED_ERROR" in json.dumps(response)
    assert response["_meta"]["reporting"]["status"] == "unavailable"


def test_finalize_does_not_confuse_nested_outputs_with_run_relative_paths(
    archive_core, client_case
):
    loaded, output, declaration = result_case(archive_core, client_case)
    (output / "outputs").mkdir()
    nested = output / "outputs/result.txt"
    nested.write_text("Different owned result\n", encoding="utf-8")

    result = archive_core.finalize_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        loaded["run"]["run_id"],
        [
            declaration,
            {**declaration, "artifact_id": "nested", "path": "outputs/result.txt"},
        ],
        state_dir=client_case.state_dir,
    )

    artifacts = {
        item["artifact_id"]: item for item in result["artifact_manifest"]["artifacts"]
    }
    assert artifacts["result"]["path"] == "result.txt"
    assert artifacts["nested"]["path"] == "outputs/result.txt"
    assert artifacts["result"]["sha256"] != artifacts["nested"]["sha256"]


@pytest.mark.parametrize("alias", ["outputs/result.txt", "absolute"])
def test_finalize_rejects_duplicate_declarations_of_one_file(
    archive_core, client_case, alias
):
    loaded, output, declaration = result_case(archive_core, client_case)
    path = str(output / "result.txt") if alias == "absolute" else alias

    with pytest.raises(archive_core.ArchiveError, match="declared more than once"):
        archive_core.finalize_studio_client_workflow(
            client_case.client_id,
            client_case.engagement_id,
            loaded["run"]["run_id"],
            [declaration, {**declaration, "artifact_id": "duplicate", "path": path}],
            state_dir=client_case.state_dir,
        )

    assert not (Path(loaded["run_root"]) / "artifact_manifest.json").exists()


@pytest.mark.parametrize(
    "outside", ["relative_escape", "absolute_outside", "absolute_escape"]
)
def test_finalize_cannot_seal_a_file_outside_the_selected_output_tree(
    archive_core, client_case, tmp_path, outside
):
    loaded, output, declaration = result_case(archive_core, client_case)
    external = tmp_path / "result.txt"
    external.write_text("Unrelated file\n", encoding="utf-8")
    declaration["path"] = {
        "relative_escape": "../result.txt",
        "absolute_outside": str(external),
        "absolute_escape": str(output / "../result.txt"),
    }[outside]

    with pytest.raises(archive_core.ArchiveError, match="outside|normalized relative"):
        archive_core.finalize_studio_client_workflow(
            client_case.client_id,
            client_case.engagement_id,
            loaded["run"]["run_id"],
            [declaration],
            state_dir=client_case.state_dir,
        )

    assert external.read_text(encoding="utf-8") == "Unrelated file\n"
    assert not (Path(loaded["run_root"]) / "artifact_manifest.json").exists()


def test_finalize_deduplicates_automatic_reports_after_path_normalization(
    archive_core, client_case
):
    loaded, _, declaration = result_case(archive_core, client_case)
    report = {
        "artifact_id": "report",
        "path": "outputs/model_data_report.json",
        "purpose": "Privacy report",
        "audience": "review",
        "media_type": "application/json",
    }

    result = archive_core.finalize_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        loaded["run"]["run_id"],
        [declaration, report],
        state_dir=client_case.state_dir,
    )

    reports = [
        item
        for item in result["artifact_manifest"]["artifacts"]
        if item["path"] == "model_data_report.json"
    ]
    assert len(reports) == 1
    assert reports[0]["artifact_id"] == "report"


def test_missing_absolute_path_does_not_alias_a_different_existing_file(
    archive_core, client_case
):
    loaded, output, declaration = result_case(archive_core, client_case)
    declaration["path"] = str(output / "outputs/result.txt")

    with pytest.raises(
        archive_core.ArchiveError, match="missing=\\['outputs/result.txt'\\]"
    ):
        archive_core.finalize_studio_client_workflow(
            client_case.client_id,
            client_case.engagement_id,
            loaded["run"]["run_id"],
            [declaration],
            state_dir=client_case.state_dir,
        )

    assert not (Path(loaded["run_root"]) / "artifact_manifest.json").exists()


@pytest.mark.parametrize("wrong_identity", ["client_id", "engagement_id", "run_id"])
def test_archive_error_does_not_attach_to_an_unrelated_active_run(
    archive_core, client_case, isolated_mcp_launcher, wrong_identity
):
    from archive_report_store import RunStore

    loaded, _, declaration = result_case(archive_core, client_case)
    arguments = {
        "client_id": client_case.client_id,
        "engagement_id": client_case.engagement_id,
        "run_id": loaded["run"]["run_id"],
        "artifacts": [declaration],
    }
    arguments[wrong_identity] = arguments[wrong_identity].split("_")[0] + "_" + "0" * 24
    archive_core._release_state_leases()
    store = RunStore(Path(loaded["run_root"]))
    before = store.path.read_bytes()

    response = _mcp_tool(
        "finalize_studio_client_workflow", arguments, state_dir=client_case.state_dir
    )

    assert response["isError"] is True
    assert store.path.read_bytes() == before


def test_archive_error_after_closure_preserves_sealed_report_and_events(
    archive_core, client_case, isolated_mcp_launcher
):
    loaded, output, declaration = result_case(archive_core, client_case)
    finish(archive_core, client_case, loaded)
    files = [
        output / "model_data_report.json",
        output / "model_data_report.md",
        Path(loaded["run_root"]) / "reporting/events.sqlite3",
    ]
    before = {path: path.read_bytes() for path in files}
    archive_core._release_state_leases()

    response = _mcp_tool(
        "finalize_studio_client_workflow",
        {
            "client_id": client_case.client_id,
            "engagement_id": client_case.engagement_id,
            "run_id": loaded["run"]["run_id"],
            "artifacts": [declaration],
        },
        state_dir=client_case.state_dir,
    )

    assert response["isError"] is True
    assert {path: path.read_bytes() for path in files} == before


def test_direct_archive_cli_records_its_exact_error_once(archive_core, client_case):
    from archive_report_store import RunStore, digest

    loaded, _, declaration = result_case(archive_core, client_case)
    declaration["path"] = "missing.txt"
    script = (
        Path(__file__).resolve().parents[2]
        / "plugins/studio-archive/scripts/studio_archive.py"
    )
    archive_core._release_state_leases()
    environment = {
        **os.environ,
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(client_case.state_dir),
        "VERA_STUDIO_ARCHIVE_SESSION_ID": str(client_case.state_dir),
    }
    environment.pop("VERA_STUDIO_ARCHIVE_MCP", None)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "finalize-workflow",
            "--client-id",
            client_case.client_id,
            "--engagement-id",
            client_case.engagement_id,
            "--run-id",
            loaded["run"]["run_id"],
            "--artifacts-json",
            json.dumps([declaration]),
        ],
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    sends = [
        event
        for event in RunStore(Path(loaded["run_root"])).events()
        if event.get("channel") == "cli:studio-archive:error"
    ]
    assert len(sends) == 1
    assert sends[0]["response_sha256"] == digest(payload)
    assert sends[0]["unmapped"] is True
