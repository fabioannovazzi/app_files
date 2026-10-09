"""Financial native inspection through real fictional ledger and maintained packs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_financial_analysis import (
    ROOT,
    _load_pack_module,
    _vera_case,
)
from tests.plugins.test_vera_native_archive_navigation import (
    archive_cli,
    native_call,
    process_environment,
    selected_run,
)


def fdd_case(root: Path, pack: str) -> Path:
    """Use maintained reviewed fictional FDD builders, including sealed upstream metrics."""
    from tests.plugins.test_vera_fdd_machinery import (
        ARTIFACT_REF,
        _build_case,
        _bundle,
        _capex_inputs,
        _context,
        _net_debt_inputs,
        _qoe_inputs,
        _working_capital_inputs,
        build_fdd_metric_receipt,
        execute_fdd_case,
    )

    root.mkdir()
    context = _context(root)
    inputs = {
        "quality_of_earnings": _qoe_inputs(),
        "net_debt": _net_debt_inputs(),
        "normalized_working_capital": _working_capital_inputs(),
        "capex": _capex_inputs(),
    }
    if pack == "deal_bridges":
        qoe = _build_case(
            context, pack_id="quality_of_earnings", inputs=inputs["quality_of_earnings"]
        )
        debt = _build_case(context, pack_id="net_debt", inputs=inputs["net_debt"])
        qoe_receipt = build_fdd_metric_receipt(
            qoe, execute_fdd_case(qoe), "adjusted_ebitda"
        )
        debt_receipt = build_fdd_metric_receipt(
            debt, execute_fdd_case(debt), "net_debt"
        )
        chosen = {
            "upstream_metrics": [qoe_receipt, debt_receipt],
            "adjusted_ebitda_ref": qoe_receipt["receipt_id"],
            "enterprise_value": {
                "amount": "5000",
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
            },
            "cash_bridge_items": [],
            "equity_bridge_items": [
                {
                    "bridge_item_id": "bridge.debt",
                    "description": "Reviewed fictional net debt",
                    "category_id": "category.debt",
                    "economic_effect_refs": debt_receipt["economic_effect_refs"],
                    "equity_value_impact": "-450",
                    "included": True,
                    "decision_ref": "decision.synthetic",
                    "evidence_refs": [ARTIFACT_REF],
                    "upstream_metric_ref": debt_receipt["receipt_id"],
                    "upstream_multiplier": "-1",
                }
            ],
        }
    else:
        chosen = inputs[pack]
    case = _build_case(context, pack_id=pack, inputs=chosen)
    path = root / "case.json"
    path.write_text(json.dumps(_bundle(case)))
    return path


@pytest.fixture(
    params=[
        "monthly_pnl",
        "working_capital",
        "customer_concentration",
        "quality_of_earnings",
        "net_debt",
        "normalized_working_capital",
        "capex",
        "deal_bridges",
    ]
)
def financial_workspace(request, tmp_path):
    pack = request.param
    ledger = _load_customer_ledger()
    archive = tmp_path / "Studio"
    client = archive / "Cliente finanziario fittizio"
    client.mkdir(parents=True)
    client_id = "client_" + "c" * 24
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(client, client_id, "Analisi finanziaria")
    intake = tmp_path / "received.txt"
    intake.write_text("Fictional financial-analysis mandate.")
    imported = ledger.import_document(
        client, client_id, engagement["engagement_id"], intake, "source"
    )
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement["engagement_id"],
        "financial-analysis",
        "native-test",
        input_ids=[imported["receipt"]["input_id"]],
    )
    running = ledger.start_run(
        client, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    output = Path(running["output_dir"])
    fixtures = {
        "monthly_pnl": "plugins/clara/evals/preparation/wd40_fy2025/case.json",
        "working_capital": "plugins/clara/evals/preparation/wd40_fy2025_working_capital/case.json",
        "customer_concentration": "plugins/clara/evals/preparation/udc_fy2025_customer_concentration/case.json",
    }
    case = (
        _vera_case(ROOT / fixtures[pack], output / "case", pack_id=pack)
        if pack in fixtures
        else fdd_case(output / "case", pack)
    )
    # Real public CLI enforces this run's context and the exact reviewed sources.
    runner = _load_pack_module()
    assert (
        runner.main(
            [
                "--pack",
                pack,
                "--case",
                str(case),
                "--output-dir",
                str(output / "prepared"),
                "--client-engagement",
                str(running["context_path"]),
            ]
        )
        == 0
    )
    env = process_environment()
    env.update(
        VERA_WORKSPACE_PYTHON=sys.executable,
        VERA_STUDIO_ARCHIVE_SESSION_ID="fictional-financial-native",
        VERA_STUDIO_ARCHIVE_STATE_DIR=str(tmp_path / "private-state"),
    )
    archive_cli(env, "configure", "--archive-root", str(archive))
    binding = {
        "client_id": client_id,
        "engagement_id": engagement["engagement_id"],
        "run_id": prepared["run"]["run_id"],
    }
    return env, binding, output, pack


def test_native_financial_open_preserves_pack_and_nonapproval_boundary(
    financial_workspace,
):
    env, binding, _, pack = financial_workspace
    run = selected_run(env, binding)

    result = native_call(env, "vera_workspace_view", {"work_ref": run["work_ref"]})

    assert run["review_available"] is True
    assert result["kind"] == "financial"
    assert result["data"]["pack_id"] == pack
    assert result["data"]["report_ready"] is False
    assert result["data"]["local_review_read_only"] is True
    assert result["items"]


def test_native_financial_explain_reads_one_prepared_artifact_without_source_population(
    financial_workspace,
):
    env, binding, output, _ = financial_workspace
    reference = selected_run(env, binding)["work_ref"]
    view = native_call(env, "vera_workspace_view", {"work_ref": reference})
    item = next(row for row in view["items"] if row["title"] == "reconciliation.json")
    selected = native_call(
        env, "vera_workspace_view", {"work_ref": reference, "item_id": item["id"]}
    )
    # The model-visible tool returns structured context, unlike UI metadata.
    import subprocess

    from tests.plugins.test_vera_native_workspace import NODE, SERVER

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "vera_workspace_explain",
            "arguments": {
                "work_ref": reference,
                "item_id": item["id"],
                "revision": selected["revision"],
            },
        },
    }

    completed = subprocess.run(
        [NODE, str(SERVER)],
        input=json.dumps(request) + "\n",
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=45,
    )

    result = json.loads(completed.stdout)["result"]
    assert not result.get("isError"), result
    context = result["structuredContent"]["untrusted_evidence"]
    original = json.loads((output / "prepared/reconciliation.json").read_bytes())
    status = next(
        row for row in context["prepared_context"]["entries"] if row["name"] == "status"
    )
    assert status["value"] == original["status"]
    assert context["report_ready"] is False
    assert "source_population" not in context
    assert str(output) not in json.dumps(context)


def test_native_financial_changed_prepared_output_refuses_before_inspection(
    financial_workspace,
):
    env, binding, output, _ = financial_workspace
    reference = selected_run(env, binding)["work_ref"]
    path = output / "prepared/reconciliation.json"
    path.write_bytes(path.read_bytes() + b"\nchanged")

    with pytest.raises(ValueError, match="prepared output changed"):
        native_call(env, "vera_workspace_view", {"work_ref": reference})

    assert selected_run(env, binding)["review_available"] is False


def test_native_financial_changed_compiled_source_refuses_even_with_unchanged_import(
    financial_workspace,
):
    env, binding, output, _ = financial_workspace
    reference = selected_run(env, binding)["work_ref"]
    runner = _load_pack_module()
    source = runner.declared_case_input_bindings(
        output / "case/case.json", financial_workspace[3]
    )[0][1]
    source.write_bytes(source.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="source no longer matches"):
        native_call(env, "vera_workspace_view", {"work_ref": reference})

    assert selected_run(env, binding)["review_available"] is False


@pytest.mark.parametrize(
    "source_ref",
    [
        "/private/tmp/another-case.json",
        'json:{"path":["missing"],"offset":0}',
        'json:{"path":[],"offset":-1}',
        'json:{"path":[],"offset":0,"path_override":"elsewhere"}',
    ],
)
def test_native_financial_refuses_unknown_or_extra_json_selection(
    financial_workspace, source_ref
):
    env, binding, _, _ = financial_workspace
    ref = selected_run(env, binding)["work_ref"]
    view = native_call(env, "vera_workspace_view", {"work_ref": ref})
    selected = next(
        row for row in view["items"] if row["title"] == "reconciliation.json"
    )

    with pytest.raises(ValueError):
        native_call(
            env,
            "vera_workspace_view",
            {"work_ref": ref, "item_id": selected["id"], "source_ref": source_ref},
        )


def test_native_financial_json_child_navigation_preserves_exact_selected_member(
    financial_workspace,
):
    env, binding, output, _ = financial_workspace
    ref = selected_run(env, binding)["work_ref"]
    view = native_call(env, "vera_workspace_view", {"work_ref": ref})
    item = next(row for row in view["items"] if row["title"] == "reconciliation.json")
    root = native_call(
        env, "vera_workspace_view", {"work_ref": ref, "item_id": item["id"]}
    )
    status = next(
        row
        for row in root["selection"]["prepared_context"]["entries"]
        if row["name"] == "status"
    )

    chosen = native_call(
        env,
        "vera_workspace_view",
        {
            "work_ref": ref,
            "item_id": item["id"],
            "revision": root["revision"],
            "source_ref": status["source_ref"],
        },
    )

    assert chosen["selection"]["prepared_context"]["path"] == ["status"]
    assert (
        chosen["selection"]["prepared_context"]["value"]
        == json.loads((output / "prepared/reconciliation.json").read_bytes())["status"]
    )
    assert chosen["data"]["selection"]["source_ref"] == status["source_ref"]


def test_native_financial_save_refuses_without_changing_authoritative_outputs(
    financial_workspace,
):
    import subprocess

    from tests.plugins.test_vera_native_workspace import NODE, SERVER

    env, binding, output, _ = financial_workspace
    ref = selected_run(env, binding)["work_ref"]
    before = {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }
    code = """
const w=require(process.argv[1]);
let id=0;
const call=(name,args)=>w.handle({jsonrpc:'2.0',id:++id,method:'tools/call',params:{name,arguments:args}}).result;
const work_ref=process.argv[2];
const current=call('vera_workspace_view',{work_ref})._meta.workspace;
const saved=call('vera_workspace_save',{work_ref,revision:current.revision,review_ticket:current.review_ticket,
 human_reviewed:true,idempotency_key:'financial-no-new-review',decisions:[]});
process.stdout.write(JSON.stringify(saved));
"""

    completed = subprocess.run(
        [NODE, "-e", code, str(SERVER), ref],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=45,
    )

    result = json.loads(completed.stdout)
    assert result["isError"] is True
    assert "no mutable review service" in result["content"][0]["text"]
    assert {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    } == before
    assert not (output.parent / ".native-workspace").exists()


@pytest.mark.parametrize("financial_workspace", ["monthly_pnl"], indirect=True)
def test_native_financial_csv_pages_cover_exact_prepared_records(financial_workspace):
    import csv

    env, binding, output, _ = financial_workspace
    ref = selected_run(env, binding)["work_ref"]
    view = native_call(env, "vera_workspace_view", {"work_ref": ref})
    item = next(row for row in view["items"] if row["title"] == "monthly_pnl.csv")
    with (output / "prepared/monthly_pnl.csv").open(newline="") as handle:
        actual = list(csv.DictReader(handle))
    assert len(actual) > 30

    first = native_call(
        env, "vera_workspace_view", {"work_ref": ref, "item_id": item["id"]}
    )
    second = native_call(
        env,
        "vera_workspace_view",
        {
            "work_ref": ref,
            "item_id": item["id"],
            "source_ref": "rows-30",
            "revision": first["revision"],
        },
    )

    assert first["selection"]["prepared_context"]["rows"] == actual[:30]
    assert second["selection"]["prepared_context"]["rows"] == actual[30:60]
    assert second["selection"]["prepared_context"]["total"] == len(actual)
    assert first["revision"] == second["revision"]


@pytest.mark.parametrize("surface", ["codex", "cowork"])
@pytest.mark.parametrize("financial_workspace", ["net_debt"], indirect=True)
def test_financial_fresh_extracted_host_package_preserves_engine_receipt_boundary(
    financial_workspace, surface, tmp_path
):
    import importlib.util
    import subprocess

    from tests.plugins.test_vera_native_workspace import NODE

    env, binding, output, _ = financial_workspace
    ref = selected_run(env, binding)["work_ref"]
    builder_path = (
        ROOT
        / "scripts"
        / (
            "build_codex_plugin_zip.py"
            if surface == "codex"
            else "build_claude_plugin_zip.py"
        )
    )
    spec = importlib.util.spec_from_file_location(
        "financial_" + surface + "_builder", builder_path
    )
    builder = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = builder
    spec.loader.exec_module(builder)
    if surface == "codex":
        vera = next(p for p in builder.load_bundles() if p.name == "vera")
        entries = builder.expected_zip_entries(vera)
        prefix = vera.package_root + "/plugins/vera/"
    else:
        _, packages = builder.load_configuration()
        vera = next(p for p in packages if p.plugin == "vera")
        entries = builder.claude_package_entries(vera)
        prefix = ""
    target = tmp_path / "extracted"
    for name, content in entries.items():
        if name.startswith(prefix):
            path = target / name[len(prefix) :]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    assert (target / "scripts/native_financial_analysis.py").is_file()
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "vera_workspace_view", "arguments": {"work_ref": ref}},
    }

    completed = subprocess.run(
        [NODE, str(target / "mcp/workspace.cjs")],
        input=json.dumps(request) + "\n",
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )

    result = json.loads(completed.stdout)["result"]
    if surface == "cowork":
        # Existing packaging changes the assurance execution-location metadata.
        # Its fingerprint must not be accepted as the source/Codex recipe.
        assert result["isError"] is True
        assert "recipe or review boundary changed" in result["content"][0]["text"]
        original = {
            p.name: p.read_bytes()
            for p in (output / "prepared").iterdir()
            if p.is_file()
        }
        fresh = output / "cowork-prepared"
        execution = subprocess.run(
            [
                sys.executable,
                str(target / "modules/financial-analysis/scripts/run_pack.py"),
                "--pack",
                "net_debt",
                "--case",
                str(output / "case/case.json"),
                "--output-dir",
                str(fresh),
                "--client-engagement",
                str(output.parent / "context.json"),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert execution.returncode == 0, execution.stderr
        receipt = json.loads((fresh / "pack_execution_receipt.json").read_bytes())
        assert receipt["report_ready"] is False
        assert receipt["status"] == "passed"
        assert (fresh / "fdd_metrics.json").read_bytes() == original["fdd_metrics.json"]
        assert (fresh / "fdd_line_items.json").read_bytes() == original[
            "fdd_line_items.json"
        ]
        assert {
            p.name: p.read_bytes()
            for p in (output / "prepared").iterdir()
            if p.is_file()
        } == original
        return
    assert not result.get("isError"), result
    snapshot = result["_meta"]["workspace"]
    assert snapshot["data"]["pack_id"] == "net_debt"
    assert snapshot["data"]["report_ready"] is False
    assert snapshot["client_id"] == binding["client_id"]
