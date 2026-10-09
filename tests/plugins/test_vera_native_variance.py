"""Real public rich variance output and owned optional native boundaries."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import ROOT, configure

__all__ = []


@pytest.fixture
def variance_run(tmp_path, monkeypatch, request):
    """Register actual source and complete explicitly authored recipe receipts."""
    variant = getattr(request, "param", "ready")
    ledger = _load_customer_ledger()
    client = tmp_path / "Synthetic variance client"
    client.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client, client_id)
    engagement_id = ledger.create_engagement(
        client, client_id, "Fictional management variance"
    )["engagement_id"]
    source = tmp_path / "variance-original.csv"
    source.write_bytes(
        (
            ROOT / "scripts/course_materials/inputs/variance/january-february.csv"
        ).read_bytes()
    )
    if variant == "many":
        source.write_text(
            "Scenario,Month,Category,Amount\n"
            + "".join(
                f"PL,2026-01,Category {i},100\nAC,2026-01,Category {i},{110+i}\n"
                for i in range(61)
            )
        )
    if variant == "pvm":
        source.write_text(
            "Scenario,Month,Category,Amount,Units\n"
            "PL,2026-01,A,1000,100\nPL,2026-01,B,2000,100\n"
            "AC,2026-01,A,1320,120\nAC,2026-01,B,1980,90\n"
        )
    recipe = {
        "language": "it",
        "mappings": {
            "period_column": "Scenario",
            "baseline_period": "PL",
            "comparison_period": "AC",
            "amount_column": "Amount",
            "units_column": None,
            "discount_column": None,
            "cogs_column": None,
            "dimensions": ["Month", "Category"],
            "calculation_grain": ["Month", "Category"],
        },
        "options": {
            "comparison_basis": "scenario",
            "period_comparison_mode": "not_applicable",
        },
        "accounting_review": {
            "perimeter": {
                "status": "established",
                "description": "One fictional entity, same two months.",
            },
            "source_tie_out": {
                "status": "established",
                "baseline_source_total": 47000,
                "comparison_source_total": 53000,
                "source_basis": "Complete fictional originals",
                "tolerance": 0.01,
            },
            "favorable_adverse_convention": {
                "status": "established",
                "description": "Revenue positive, costs negative; higher operating result favorable.",
            },
            "materiality": {
                "status": "not_applied",
                "reason": "Retain every supplied fictional line.",
            },
        },
    }
    if variant == "blocked":
        recipe["accounting_review"]["source_tie_out"]["comparison_source_total"] = 53001
    if variant == "pvm":
        recipe["mappings"]["units_column"] = "Units"
        recipe["accounting_review"]["source_tie_out"].update(
            baseline_source_total=3000, comparison_source_total=3300
        )
    if variant == "prior-reviewed":
        recipe["accounting_review"].update(
            professional_review={
                "status": "approved",
                "reviewed_by": "Prior fictional professional",
                "reviewed_at": "2026-10-07T12:00:00+02:00",
            },
            root_cause_review={
                "status": "approved",
                "selected_alternative": 2,
                "rationale": "Literal prior fictional decision",
            },
        )
    if variant in {"partial", "many"}:
        recipe["accounting_review"] = {}
    recipe_path = tmp_path / "explicit-comparison.json"
    recipe_path.write_text(json.dumps(recipe))
    ids = [
        ledger.import_document(client, client_id, engagement_id, p, "source")[
            "receipt"
        ]["input_id"]
        for p in (source, recipe_path)
    ]
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement_id,
        "variance-analysis",
        "development",
        input_ids=ids,
    )
    started = ledger.start_run(client, engagement_id, prepared["run"]["run_id"])
    binding = {
        "work_ref": "fictional-variance",
        "client_root": str(client),
        "client_id": client_id,
        "engagement_id": engagement_id,
        "run_id": started["run"]["run_id"],
        "workflow_id": "variance-analysis",
    }
    return (
        configure(monkeypatch, tmp_path, [binding]),
        Path(started["output_dir"]),
        binding,
        {
            "source_input_id": ids[0],
            "recipe_input_id": ids[1],
            "currency": "EUR",
            "language": "it",
        },
    )


BEGIN = """
const work={work_ref:'fictional-variance'};
const setup=payload(call('vera_workspace_variance_setup',work));
"""


def prepare(fixture):
    return (
        BEGIN
        + f"const fields={json.dumps(fixture[3])};"
        + """
payload(call('vera_workspace_variance_draft_save',{...work,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields}));
const current=payload(call('vera_workspace_variance_setup',work));
const args={...work,revision:current.revision,review_ticket:current.review_ticket,expected_draft_revision:current.draft_revision,fields,confirmed:true,idempotency_key:'fictional-rich-variance'};
const prepared=payload(call('vera_workspace_variance_prepare',args));
const reopened=payload(call('vera_workspace_variance_setup',work));
const exact={...work,revision:reopened.revision,source_ref:prepared.source_ref};
"""
    )


@pytest.mark.parametrize(
    "variance_run,expected",
    [
        ("ready", "written_pending_review"),
        ("partial", "written_pending_review"),
        ("blocked", "blocked"),
    ],
    indirect=["variance_run"],
)
def test_native_variance_preserves_rich_public_outputs_and_accounting_state(
    variance_run, expected
):
    env, output, binding, _ = variance_run

    result = rpc_program(
        env,
        prepare(variance_run)
        + "const result={prepared,retry:payload(call('vera_workspace_variance_prepare',args)),files:payload(call('vera_workspace_variance_outputs',exact)),context:payload(call('vera_workspace_variance_read',{...exact,artifact_name:'standard_variance_context.json'}))};",
    )

    folder = output / result["prepared"]["source_ref"]
    context = json.loads((folder / "standard_variance_context.json").read_bytes())
    manifest = json.loads((folder / "model_use_manifest.json").read_bytes())
    assert result["prepared"] == result["retry"]
    assert result["prepared"]["status"] == expected
    assert context["totals"]["amount_baseline"] == 47000
    assert context["totals"]["amount_comparison"] == 53000
    assert context["totals"]["total_delta"] == 6000
    assert manifest["default_model_use"]["raw_source_rows_included"] is False
    assert (folder / "root_cause_client_report.docx").is_file()
    assert (folder / "waterfall.png").is_file()
    assert (folder / "exploded_variance_bridge.png").is_file()
    assert (folder / "waterfall_small_multiples.png").is_file()
    assert (folder / "inspection/inspection.json").is_file()
    assert (folder / "inspection/suggested_recipe.json").is_file()
    assert result["prepared"]["review_payload_validated"] is True
    expected_alternatives = {f"root_cause_bridge_alt_{i}.csv" for i in range(1, 11)}
    assert expected_alternatives <= {p.name for p in folder.iterdir()}
    assert len(result["files"]["outputs"]) == len(
        [p for p in folder.rglob("*") if p.is_file()]
    )
    assert result["prepared"]["professional_approval"] is False
    assert (
        _load_customer_ledger().load_run(
            Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
        )["run"]["status"]
        == "running"
    )


def test_native_variance_draft_recovers_empty_cas_without_calculation(variance_run):
    env, output, _, values = variance_run

    result = rpc_program(
        env,
        BEGIN
        + f"const fields={json.dumps(values)};"
        + """
const save=v=>({...work,revision:v.revision,review_ticket:v.review_ticket,expected_draft_revision:v.draft_revision});
payload(call('vera_workspace_variance_draft_save',{...save(setup),fields}));
const recovered=payload(call('vera_workspace_variance_setup',work));
const cleared=payload(call('vera_workspace_variance_draft_save',{...save(recovered),fields:{source_input_id:'',recipe_input_id:'',currency:'',language:''}}));
const stale=call('vera_workspace_variance_draft_save',{...save(setup),fields});
const result={recovered,cleared,stale,current:payload(call('vera_workspace_variance_setup',work))};
""",
    )

    assert result["recovered"]["draft"] == values
    assert result["recovered"]["draft_revision"] != result["cleared"]["draft_revision"]
    assert result["stale"]["isError"] is True
    assert result["current"]["draft"] == dict.fromkeys(values, "")
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "change",
    [
        "fields.source_input_id='input_foreign';",
        "fields.recipe_input_id=fields.source_input_id;",
        "fields.currency='';",
        "fields.language='xx';",
    ],
)
def test_native_variance_refuses_foreign_or_incomplete_setup_without_intent(
    variance_run, change
):
    env, output, _, values = variance_run

    result = rpc_program(
        env,
        BEGIN
        + f"const fields={json.dumps(values)};"
        + change
        + "const result=call('vera_workspace_variance_prepare',{...work,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields,confirmed:true,idempotency_key:'invalid-source'});",
    )

    assert result["isError"] is True
    assert list(output.iterdir()) == []
    assert not list(output.parent.glob(".native-workspace/variance-request-*"))


def test_native_variance_unsigned_execution_creates_no_output(variance_run):
    env, output, _, fields = variance_run

    result = rpc_program(
        env,
        BEGIN
        + f"const fields={json.dumps(fields)};"
        + "const result=call('vera_workspace_variance_prepare',{...work,revision:setup.revision,review_ticket:'forged',expected_draft_revision:setup.draft_revision,fields,confirmed:true,idempotency_key:'unsigned'});",
    )

    assert result["isError"] is True
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("variance_run", ["many"], indirect=True)
def test_native_variance_pages_full_results_beyond_public_widget_preview(variance_run):
    env, output, _, _ = variance_run

    result = rpc_program(
        env,
        prepare(variance_run)
        + """
let offset=0,rows=[],page;
do {page=payload(call('vera_workspace_variance_read',{...exact,artifact_name:'variance_results.csv',offset}));rows.push(...page.rows);offset+=20;}while(page.has_more);
const model=call('vera_workspace_variance_explain',{...exact,artifact_name:'variance_results.csv',offset:60});
const result={prepared,rows,total:page.total,model};
""",
    )

    with (
        output / result["prepared"]["source_ref"] / "variance_results.csv"
    ).open() as stream:
        complete = list(csv.DictReader(stream))
    assert len(complete) == 61
    assert result["rows"] == complete
    assert result["total"] == 61
    assert result["model"]["structuredContent"]["rows"] == complete[60:]
    assert "_meta" not in result["model"]
    assert "variance-original.csv" not in json.dumps(result["model"])


def test_native_variance_viewer_cannot_save_or_calculate(variance_run):
    env, output, _, values = variance_run
    env = {**env, "VERA_WORKSPACE_ROLES": "VIEWER"}

    result = rpc_program(
        env,
        BEGIN
        + f"const fields={json.dumps(values)};"
        + "const result={setup,saved:call('vera_workspace_variance_draft_save',{...work,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields})};",
    )

    assert result["setup"]["can_prepare"] is False
    assert result["saved"]["isError"] is True
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "artifact_name", ["../context.json", "/private/foreign.json", "not-present.json"]
)
def test_native_variance_refuses_arbitrary_or_missing_output_member(
    variance_run, artifact_name
):
    env, _, _, _ = variance_run

    result = rpc_program(
        env,
        prepare(variance_run)
        + f"const result=call('vera_workspace_variance_read',{{...exact,artifact_name:{json.dumps(artifact_name)}}});",
    )

    assert result["isError"] is True


def test_native_variance_corrupt_output_blocks_read_and_repeat(variance_run):
    env, output, _, _ = variance_run
    prepared = rpc_program(env, prepare(variance_run) + "const result=prepared;")
    path = output / prepared["source_ref"] / "variance_results.csv"
    path.write_text(path.read_text() + "altered bytes")

    result = rpc_program(
        env,
        "const result=call('vera_workspace_variance_setup',{work_ref:'fictional-variance'});",
    )

    assert result["isError"] is True
    assert "artifact bytes or population changed" in result["content"][0]["text"]


@pytest.mark.parametrize("interruption", ["intent", "orphan"])
def test_native_variance_uncertain_execution_refuses_writes(variance_run, interruption):
    env, output, _, values = variance_run
    if interruption == "intent":
        private = output.parent / ".native-workspace"
        private.mkdir()
        (private / "variance-request-orphan.json").write_text(
            json.dumps({"request_sha256": "0" * 64})
        )
    else:
        (output / ("variance-" + "0" * 64)).mkdir()

    result = rpc_program(
        env,
        BEGIN
        + f"const fields={json.dumps(values)};"
        + "const result={setup,write:call('vera_workspace_variance_prepare',{...work,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields,confirmed:true,idempotency_key:'uncertain-repeat'})};",
    )

    assert result["setup"]["status"] == "recovery_required"
    assert result["setup"]["can_prepare"] is False
    assert result["write"]["isError"] is True


def test_native_variance_exact_png_preview_has_private_app_boundary(variance_run):
    env, _, _, _ = variance_run

    result = rpc_program(
        env,
        prepare(variance_run)
        + "const result=call('vera_workspace_variance_asset',{...exact,artifact_name:'waterfall.png'});",
    )

    assert result["_meta"]["workspace"]["image_url"].startswith(
        "data:image/png;base64,iVBOR"
    )
    assert "image_url" not in json.dumps(result["structuredContent"])
    assert "image_url" not in json.dumps(result["content"])


@pytest.mark.parametrize("interruption", ["intent", "orphan"])
def test_native_variance_uncertain_execution_blocks_owned_archive_closure(
    variance_run, tmp_path, interruption
):
    from tests.plugins.test_vera_native_archive_navigation import archive_cli

    env, output, binding, _ = variance_run
    env = {
        **env,
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-variance-closure",
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(
            tmp_path.parent / f"private-archive-{tmp_path.name}"
        ),
    }
    archive_cli(
        env, "configure", "--archive-root", str(Path(binding["client_root"]).parent)
    )
    env.pop("VERA_WORKSPACE_BINDINGS")
    if interruption == "intent":
        private = output.parent / ".native-workspace"
        private.mkdir()
        (private / "variance-request-incomplete.json").write_text(
            json.dumps({"request_sha256": "0" * 64})
        )
    else:
        (output / ("variance-" + "0" * 64)).mkdir()
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}

    result = rpc_program(
        env,
        f"const result=call('vera_workspace_archive_closure',{json.dumps(selected)});",
    )

    assert result["isError"] is True
    assert (
        "Variance execution requires recovery before output closure"
        in result["content"][0]["text"]
    )
