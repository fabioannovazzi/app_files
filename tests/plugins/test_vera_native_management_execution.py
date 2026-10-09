"""Actual public reporting/costing execution before shared MCP/UI integration."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

from tests.plugins.test_management_control_pack import (
    _reviewed_recipe,
    _write_workbook,
    build_inspection,
    load_source_tables,
)
from tests.plugins.test_management_costing import payload, reference
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_workspace import configure, workspace_module

__all__ = []


@pytest.fixture
def management_run(tmp_path, monkeypatch, request):
    variant = getattr(request, "param", "reporting")
    ledger = _load_customer_ledger()
    client = tmp_path / "Synthetic management client"
    client.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(
        client, client_id, "Fictional management reporting and costing"
    )["engagement_id"]
    mode = "costing" if variant == "costing" else "reporting"
    if mode == "costing":
        source = tmp_path / "synthetic-source.json"
        source.write_text(json.dumps(reference()["case"]))
        recipe = payload(methods=["direct_costing_evoluto"])
        recipe["case"]["meta"].update(clientId=client_id, engagementId=engagement)
        recipe["case"]["evidence"][0]["source_sha256"] = hashlib.sha256(
            source.read_bytes()
        ).hexdigest()
    else:
        source = tmp_path / "management.xlsx"
        _write_workbook(source, full=variant != "partial")
        inspected, _, _ = build_inspection(load_source_tables([source]))
        recipe = _reviewed_recipe(inspected, full=variant != "partial")
        if variant == "blocked":
            recipe["control_totals"]["general_ledger"] = "1001"
    prepared_case = tmp_path / "reviewed-case.json"
    prepared_case.write_text(json.dumps(recipe))
    ids = [
        ledger.import_document(client, client_id, engagement, p, "source")["receipt"][
            "input_id"
        ]
        for p in (source, prepared_case)
    ]
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement,
        "management-control-pack",
        "development",
        input_ids=ids,
    )
    running = ledger.start_run(client, engagement, prepared["run"]["run_id"])
    binding = {
        "work_ref": "fictional-management",
        "client_root": str(client),
        "client_id": client_id,
        "engagement_id": engagement,
        "run_id": running["run"]["run_id"],
        "workflow_id": "management-control-pack",
    }
    configure(monkeypatch, tmp_path, [binding])
    api = workspace_module()
    service = importlib.import_module("native_management_execution")
    root = api.module_root("management-control-pack")

    def call(action, args=None):
        return service.dispatch(
            "vera_workspace_management_" + action,
            {"work_ref": binding["work_ref"], **(args or {})},
            binding,
            api.load_binding(binding),
            root,
            api,
        )

    choices = {"mode": mode, "input_ids": [ids[0]], "recipe_input_id": ids[1]}
    return call, Path(running["output_dir"]), binding, choices, api


def calculate(fixture):
    call, _, _, choices, _ = fixture
    page = call("setup")
    call(
        "draft_save",
        {
            "revision": page["revision"],
            "expected_draft_revision": page["draft_revision"],
            "fields": choices,
        },
    )
    fresh = call("setup")
    args = {
        "revision": fresh["revision"],
        "expected_draft_revision": fresh["draft_revision"],
        "fields": choices,
        "confirmed": True,
        "idempotency_key": "fictional-management-calculate",
    }
    result = call("prepare", args)
    return result, args


@pytest.mark.parametrize(
    "management_run,expected",
    [
        ("reporting", "ready_for_review"),
        ("costing", "ready_for_review"),
        ("partial", "partial"),
        ("blocked", "blocked"),
    ],
    indirect=["management_run"],
)
def test_management_native_service_preserves_both_public_paths_and_all_normal_outputs(
    management_run, expected
):
    call, output, _, choices, _ = management_run
    result, args = calculate(management_run)
    repeated = call("prepare", args)
    setup = call("setup")
    exact = {"revision": setup["revision"], "source_ref": result["source_ref"]}
    files = call("outputs", exact)
    folder = output / result["source_ref"]
    pack = json.loads((folder / "management_control_pack.json").read_bytes())
    assert result == repeated
    assert result["status"] == pack["status"] == expected
    assert result["ordinary_exit_code"] == (2 if expected == "blocked" else 0)
    assert result["mode"] == choices["mode"]
    assert result["context_receipt_verified"] is True
    assert len(files["outputs"]) == 8
    assert {p.name for p in folder.iterdir()} == {
        "management_control_pack.json",
        "management_control_pack.xlsx",
        "management_control_facts.md",
        "management_control_dashboard.html",
        "execution_receipt.json",
        "model_context.json",
        "model_context_receipt.json",
        "commentary_template.json",
    }
    assert setup["can_prepare"] is False
    assert result["report_status"] == "draft_pending_professional_review"
    assert result["professional_approval"] is False
    assert result["run_completed"] is False
    if choices["mode"] == "costing":
        assert (
            pack["metrics"]["costing.direct_costing_evoluto.A.margin"]["value"]
            == "21000.00"
        )
    for row in files["outputs"]:
        assert (
            hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest() == row["sha256"]
        )


@pytest.mark.parametrize("management_run", ["reporting", "costing"], indirect=True)
def test_management_native_context_is_the_whole_existing_bounded_projection(
    management_run,
):
    call, output, _, _, _ = management_run
    result, _ = calculate(management_run)
    page = call("setup")
    context = call(
        "context", {"revision": page["revision"], "source_ref": result["source_ref"]}
    )
    folder = output / result["source_ref"]
    assert context["model_context"] == json.loads(
        (folder / "model_context.json").read_bytes()
    )
    assert context["model_context_receipt"] == json.loads(
        (folder / "model_context_receipt.json").read_bytes()
    )
    assert context["execution_receipt"] == json.loads(
        (folder / "execution_receipt.json").read_bytes()
    )
    assert context["commentary_template"] == json.loads(
        (folder / "commentary_template.json").read_bytes()
    )
    assert "management_control_pack" not in context
    assert "management.xlsx" not in json.dumps(context)
    assert "synthetic-source.json" not in json.dumps(context)
    assert context["actual_model_reads_verified"] is False
    assert context["record_actual_model_reads_in_run_report"] is True


def test_management_native_service_draft_cas_preserves_other_window_and_empty_choices(
    management_run,
):
    call, output, _, choices, _ = management_run
    before = call("setup")
    saved = call(
        "draft_save",
        {
            "revision": before["revision"],
            "expected_draft_revision": before["draft_revision"],
            "fields": choices,
        },
    )
    with pytest.raises(ValueError, match="draft changed"):
        call(
            "draft_save",
            {
                "revision": before["revision"],
                "expected_draft_revision": before["draft_revision"],
                "fields": {"mode": "", "input_ids": [], "recipe_input_id": ""},
            },
        )
    fresh = call("setup")
    assert fresh["draft"] == choices
    assert fresh["draft_revision"] == saved["draft_revision"]
    call(
        "draft_save",
        {
            "revision": fresh["revision"],
            "expected_draft_revision": fresh["draft_revision"],
            "fields": {"mode": "", "input_ids": [], "recipe_input_id": ""},
        },
    )
    assert call("setup")["draft"] == {
        "mode": "",
        "input_ids": [],
        "recipe_input_id": "",
    }
    assert list(output.glob("management-*")) == []


def test_management_native_service_requires_renewed_confirmation_before_calculation(
    management_run,
):
    call, output, _, choices, _ = management_run
    page = call("setup")
    call(
        "draft_save",
        {
            "revision": page["revision"],
            "expected_draft_revision": page["draft_revision"],
            "fields": choices,
        },
    )
    fresh = call("setup")
    with pytest.raises(PermissionError, match="confirmation"):
        call(
            "prepare",
            {
                "revision": fresh["revision"],
                "expected_draft_revision": fresh["draft_revision"],
                "fields": choices,
                "confirmed": False,
                "idempotency_key": "unconfirmed-management",
            },
        )
    assert list(output.glob("management-*")) == []
    assert (
        list((output.parent / ".native-workspace").glob("management-request-*.json"))
        == []
    )
