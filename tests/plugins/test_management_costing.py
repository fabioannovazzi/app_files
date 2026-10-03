from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from openpyxl import load_workbook

from tests.model_data_helpers import write_no_model_report

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/management-control-pack/scripts"
FIXTURES = ROOT / "tests/fixtures/costing"
sys.path.insert(0, str(SCRIPTS))

from costing_core import (  # noqa: E402
    METHODS,
    CostingContractError,
    allocate_cents,
    calculate_costing,
    calculate_decisions,
)
from costing_pack import build_costing_pack  # noqa: E402
from management_control_core import (  # noqa: E402
    PackContractError,
    build_model_context,
    build_model_context_receipt,
    finalize_commentary,
    render_html,
    render_markdown,
    write_excel,
    write_json,
)
from run_costing import main as costing_main  # noqa: E402


def reference(name="jobs"):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def payload(name="jobs", methods=METHODS):
    return {
        "schema_version": "vera.costing_case.v1",
        "entity": "Officina dimostrativa",
        "language": "it",
        "audience": "internal",
        "decision_question": "Quali commesse contribuiscono al risultato operativo?",
        "methods": list(methods),
        "case": reference(name)["case"],
        "decisions": [],
        "accounting_bridge": None,
    }


@pytest.mark.parametrize(
    "name", ["production", "trade", "services", "jobs", "pizzeria", "capacity"]
)
@pytest.mark.parametrize("method", METHODS)
def test_costing_matches_independently_checked_contributor_case(name, method):
    fixture = reference(name)
    expected = fixture["expected"][method]

    result = calculate_costing(fixture["case"], [method])["methods"][0]

    assert result["entityProfitCents"] == expected["entityProfitCents"]
    assert [
        {key: row[key] for key in expected_row}
        for row, expected_row in zip(
            result["objects"], expected["objects"], strict=True
        )
    ] == expected["objects"]


@pytest.mark.parametrize(
    "amount,weights,capacity,expected",
    [
        (
            1,
            {"B": "1", "A": "1"},
            None,
            {"byObject": {"A": 1, "B": 0}, "unusedCents": 0},
        ),
        (
            -100,
            {"A": "1", "B": "1", "C": "1"},
            None,
            {"byObject": {"A": -34, "B": -33, "C": -33}, "unusedCents": 0},
        ),
        (
            10000,
            {"A": "2", "B": "3"},
            "10",
            {"byObject": {"A": 2000, "B": 3000}, "unusedCents": 5000},
        ),
        (
            300,
            {"A": "0.1", "B": "0.2"},
            None,
            {"byObject": {"A": 100, "B": 200}, "unusedCents": 0},
        ),
        (0, {"A": "0"}, None, {"byObject": {"A": 0}, "unusedCents": 0}),
        (
            1,
            {"A": "10000000000000000000000", "B": "10000000000000000000000.000001"},
            None,
            {"byObject": {"A": 0, "B": 1}, "unusedCents": 0},
        ),
    ],
)
def test_allocation_preserves_signed_cents_and_unused_capacity(
    amount, weights, capacity, expected
):
    assert allocate_cents(amount, weights, capacity) == expected


@pytest.mark.parametrize(
    "amount,weights,capacity",
    [
        (1.2, {"A": "1"}, None),
        (True, {"A": "1"}, None),
        (2**53, {"A": "1"}, None),
        (100, {"A": "0"}, None),
        (100, {"A": "-1"}, None),
        (100, {"A": "1,2"}, None),
        (100, {"A": "11"}, "10"),
        (100, {}, None),
        (100, {"~UNUSED": "1"}, None),
    ],
)
def test_allocation_rejects_invalid_money_or_driver(amount, weights, capacity):
    with pytest.raises(CostingContractError):
        allocate_cents(amount, weights, capacity)


@pytest.mark.parametrize(
    "path,value",
    [
        (("meta", "schemaVersion"), "99"),
        (("meta", "currency"), "USD"),
        (("meta", "basis"), "cash"),
        (("meta", "demonstration"), "yes"),
        (("meta", "periodStart"), "2026-10-01"),
        (("meta", "periodEnd"), "2026-02-30"),
        (("meta", "clientId"), "../other"),
        (("sourceTotals", "revenueCents"), 1),
        (("sourceTotals", "costsCents"), 1),
        (("sourceTotals", "evidenceIds"), ["missing"]),
        (("objects", 0, "dimension"), "unknown"),
        (("objects", 0, "dimension"), "client"),
        (("objects", 0, "units"), "-1"),
        (("costs", 0, "behavior"), "mixed"),
        (("costs", 0, "traceability"), "unknown"),
        (("costs", 0, "objectId"), "unknown"),
        (("costs", 0, "evidenceIds"), []),
        (("costs", 1, "id"), "C001"),
        (("pools", 0, "driver", "weights"), {"A": "1"}),
        (("pools", 0, "driver", "capacityPolicy"), "guessed"),
        (("pools", 0, "driver", "capacity"), "10"),
        (("commonPolicy",), "automatic"),
        (("review", "status"), "draft"),
    ],
)
def test_costing_rejects_unreviewed_or_inconsistent_case(path, value):
    case = reference()["case"]
    node = case
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value

    with pytest.raises(CostingContractError):
        calculate_costing(case, METHODS)


@pytest.mark.parametrize("methods", [[], ["unknown"], ["abc", "abc"], "abc"])
def test_costing_requires_explicit_valid_method_scope(methods):
    with pytest.raises(CostingContractError):
        calculate_costing(reference()["case"], methods)


@pytest.mark.parametrize("omitted", [False, True])
def test_direct_scope_is_complete_without_unused_full_or_abc_drivers(omitted):
    case = reference()["case"]
    case["traditionalDriver"] = None
    case["pools"][0]["driver"] = None
    case["pools"][1]["driver"] = None
    if omitted:
        del case["traditionalDriver"]
        del case["pools"][0]["driver"]
        del case["pools"][1]["driver"]

    result = calculate_costing(case, ["direct_costing", "direct_costing_evoluto"])

    assert result["status"] == "ready_for_review"
    assert result["unavailableMethods"] == []


@pytest.mark.parametrize(
    "methods,status", [(["direct_costing", "abc"], "partial"), (["abc"], "blocked")]
)
def test_missing_requested_driver_preserves_supported_results(methods, status):
    case = reference()["case"]
    case["pools"][0]["driver"] = None

    result = calculate_costing(case, methods)

    assert result["status"] == status
    assert result["unavailableMethods"][0]["method"] == "abc"


def test_unresolved_variable_driver_blocks_object_contributions():
    case = reference("production")["case"]
    case["pools"][0]["driver"] = None

    result = calculate_costing(case, ["direct_costing"])

    assert result["status"] == "blocked"


def test_retained_common_costs_reconcile_at_entity_level():
    case = reference()["case"]
    case["commonPolicy"] = "retain_entity"
    case["commonDriver"] = None

    result = calculate_costing(case, ["abc"])["methods"][0]

    assert result["retainedCommonCents"] == 250000
    assert result["entityProfitCents"] == 2650000


@pytest.mark.parametrize(
    "kind,amounts,expected",
    [
        (
            "incremental_order",
            {
                "revenueCents": 100000,
                "variableCents": 60000,
                "additionalFixedCents": 10000,
                "opportunityCents": 5000,
                "oneOffCents": 2000,
            },
            23000,
        ),
        (
            "make_or_buy",
            {
                "avoidableMakeCents": 100000,
                "releasedCapacityContributionCents": 10000,
                "purchaseCents": 75000,
                "transitionCents": 5000,
                "strandedFixedCents": 80000,
            },
            30000,
        ),
        (
            "discontinue",
            {
                "lostRevenueCents": 100000,
                "avoidedVariableCents": 60000,
                "avoidableFixedCents": 20000,
                "exitCents": 5000,
                "replacementContributionCents": 0,
                "strandedFixedCents": 90000,
            },
            -25000,
        ),
    ],
)
def test_decisions_use_incremental_inputs_without_saving_stranded_costs(
    kind, amounts, expected
):
    rows = [
        {
            "id": "D1",
            "type": kind,
            "label": "Synthetic option",
            "basis": "Reviewed synthetic assumptions",
            "evidenceIds": ["E"],
            "amounts": amounts,
        }
    ]

    result = calculate_decisions(rows, {"E"})

    assert result[0]["deltaProfitCents"] == expected
    assert result[0]["decision"] == "professional_review_required"


def test_unbalanced_accounting_bridge_blocks_delivery():
    case = payload()
    case["accounting_bridge"] = {
        "sourceProfitCents": 2000000,
        "basis": "Synthetic accounts",
        "reviewer": "Test",
        "sourceEvidenceId": "SYN-01",
        "entries": [],
    }

    pack = build_costing_pack(case)

    assert pack["status"] == "blocked"
    assert pack["controls"][-1]["difference"] == "6500.00"


def test_bounded_context_excludes_cost_rows_and_evidence_locators():
    case = payload()
    case["case"]["evidence"][0]["locator"] = "PRIVATE_SOURCE_LOCATOR"
    case["case"]["costs"][0]["label"] = "PRIVATE_COST_LABEL"
    pack = build_costing_pack(case)

    context = build_model_context(pack)
    receipt = build_model_context_receipt(pack, context)

    assert "PRIVATE_SOURCE_LOCATOR" not in json.dumps(context)
    assert "PRIVATE_COST_LABEL" not in json.dumps(context)
    assert context["sections"]["costing"]["question"] == case["decision_question"]
    assert receipt["status"] == "ready_for_review"


@pytest.mark.parametrize("language", ["it", "en"])
def test_reports_render_selected_scope_and_preserve_untrusted_labels(
    tmp_path, language
):
    case = payload(methods=["direct_costing_evoluto"])
    case["language"] = language
    case["entity"] = "=1+1"
    case["case"]["objects"][0]["label"] = "<script>alert(1)</script>"
    pack = build_costing_pack(case)
    path = tmp_path / "costing.xlsx"

    rendered = render_html(pack)
    markdown = render_markdown(pack)
    write_excel(path, pack)

    assert "<script>alert" not in rendered
    assert "&lt;script&gt;alert" in rendered
    assert "21,000.00" in rendered if language == "en" else "21.000,00" in rendered
    assert "full_costing" not in markdown
    workbook = load_workbook(path)
    assert workbook.worksheets[0]["B2"].value == "'=1+1"
    assert workbook["direct_costing_evoluto"]["E2"].value == 21000
    workbook.close()


def archive_case(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "test_costing_ledger", ROOT / "plugins/studio-archive/scripts/client_ledger.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source = tmp_path / "synthetic-source.json"
    source.write_text(json.dumps(reference()["case"]))
    client_root = tmp_path / "Client"
    client_root.mkdir()
    client_id = "client_111111111111111111111111"
    module.create_client_manifest(client_root, client_id)
    engagement = module.create_engagement(
        client_root, client_id, "Synthetic costing test"
    )
    engagement_id = engagement["engagement_id"]
    imported = module.import_document(
        client_root, client_id, engagement_id, source, "source"
    )
    prepared = module.prepare_run(
        client_root,
        client_id,
        engagement_id,
        "management-control-pack",
        "0.1.6",
        input_ids=[imported["receipt"]["input_id"]],
    )
    running = module.start_run(client_root, engagement_id, prepared["run"]["run_id"])
    output = Path(running["output_dir"])
    source = Path(running["context"]["input_bindings"][0]["path"])
    case = payload(methods=["direct_costing_evoluto"])
    case["case"]["meta"].update(clientId=client_id, engagementId=engagement_id)
    case["case"]["evidence"][0]["source_sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    case_path = output / "reviewed_costing_case.json"
    write_json(case_path, case)
    return module, client_root, engagement_id, running, source, case_path


def execute_costing(running, source, case_path):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "run_costing.py"),
            "--input",
            str(source),
            "--case",
            str(case_path),
            "--client-engagement",
            running["context_path"],
            "--output-dir",
            str(Path(running["output_dir"]) / "pack"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_costing_cli_completes_real_archive_lifecycle_without_general_ledger(tmp_path):
    ledger, client, engagement, running, source, case_path = archive_case(tmp_path)

    result = execute_costing(running, source, case_path)

    assert result.returncode == 0, result.stderr
    output = Path(running["output_dir"])
    pack_dir = output / "pack"
    pack = json.loads((pack_dir / "management_control_pack.json").read_text())
    assert pack["status"] == "ready_for_review"
    assert (
        pack["metrics"]["costing.direct_costing_evoluto.A.margin"]["value"]
        == "21000.00"
    )
    commentary = json.loads((pack_dir / "commentary_template.json").read_text())
    commentary["observations"] = [
        {
            "text": "Alfa contributes 21,000 EUR after specific fixed costs.",
            "metric_ids": ["costing.direct_costing_evoluto.A.margin"],
        }
    ]
    commentary_path = pack_dir / "management_commentary.json"
    write_json(commentary_path, commentary)
    finalized = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "finalize_pack.py"),
            "--pack",
            str(pack_dir / "management_control_pack.json"),
            "--commentary",
            str(commentary_path),
            "--client-engagement",
            running["context_path"],
            "--output-dir",
            str(pack_dir / "final"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert finalized.returncode == 0, finalized.stderr
    assert (
        "Alfa contributes"
        in (pack_dir / "final/management_control_dashboard_reviewed.html").read_text()
    )
    write_no_model_report(output, "management-control-pack", running["run"]["run_id"])
    declarations = [
        {
            "artifact_id": f"costing_{i}",
            "path": str(path.relative_to(output)),
            "purpose": "Synthetic costing lifecycle evidence",
            "audience": "review",
            "media_type": "application/octet-stream",
        }
        for i, path in enumerate(sorted(output.rglob("*")))
        if path.is_file()
    ]
    ledger.finalize_run(client, engagement, running["run"]["run_id"], declarations)
    completed = ledger.complete_run(client, engagement, running["run"]["run_id"])
    assert completed["run"]["status"] == "completed"


@pytest.mark.parametrize("failure", ["client", "evidence", "outside", "overwrite"])
def test_costing_cli_rejects_wrong_binding_and_preserves_previous_outputs(
    tmp_path, failure
):
    _, _, _, running, source, case_path = archive_case(tmp_path)
    case = json.loads(case_path.read_text())
    if failure == "client":
        case["case"]["meta"]["clientId"] = "OTHER"
    elif failure == "evidence":
        case["case"]["evidence"][0]["source_sha256"] = "0" * 64
    elif failure == "outside":
        source = tmp_path / "outside.json"
        source.write_text("{}")
    else:
        pack_dir = Path(running["output_dir"]) / "pack"
        pack_dir.mkdir()
        (pack_dir / "prior.txt").write_text("Preserve")
    write_json(case_path, case)

    result = execute_costing(running, source, case_path)

    assert result.returncode != 0
    assert not (
        Path(running["output_dir"]) / "pack/management_control_pack.json"
    ).exists()


def test_changed_costing_input_invalidates_previous_commentary(tmp_path):
    case = payload()
    original = build_costing_pack(case)
    path = tmp_path / "pack.json"
    write_json(path, original)
    commentary = {
        "schema_version": "vera.management_control_commentary.v1",
        "workflow_id": "management-control-pack",
        "pack_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    changed = deepcopy(case)
    changed["case"]["review"]["note"] += " Revised assumption."

    with pytest.raises(PackContractError, match="different pack"):
        finalize_commentary(build_costing_pack(changed), commentary)


@pytest.mark.parametrize("missing_driver,expected_exit", [(False, 0), (True, 2)])
def test_costing_main_persists_requested_scope_status(
    tmp_path, missing_driver, expected_exit
):
    _, _, _, running, source, case_path = archive_case(tmp_path)
    case = json.loads(case_path.read_text())
    case["methods"] = ["abc"]
    if missing_driver:
        case["case"]["pools"][0]["driver"] = None
    write_json(case_path, case)

    result = costing_main(
        [
            "--input",
            str(source),
            "--case",
            str(case_path),
            "--client-engagement",
            running["context_path"],
            "--output-dir",
            str(Path(running["output_dir"]) / "direct-main"),
        ]
    )

    assert result == expected_exit
    assert (
        Path(running["output_dir"]) / "direct-main/execution_receipt.json"
    ).is_file()


def test_costing_main_rejects_unbound_source_without_outputs(tmp_path):
    _, _, _, running, source, case_path = archive_case(tmp_path)
    source.write_text("Changed source")

    with pytest.raises(SystemExit) as error:
        costing_main(
            [
                "--input",
                str(source),
                "--case",
                str(case_path),
                "--client-engagement",
                running["context_path"],
                "--output-dir",
                str(Path(running["output_dir"]) / "rejected"),
            ]
        )

    assert error.value.code == 2
    assert not (Path(running["output_dir"]) / "rejected").exists()


def test_decision_outputs_and_reviewed_commentary_are_present_in_both_reports(tmp_path):
    case = payload()
    case["decisions"] = [
        {
            "id": "ORDER",
            "type": "incremental_order",
            "label": "Ordine aggiuntivo",
            "basis": "Ipotesi sintetiche",
            "evidenceIds": ["SYN-01"],
            "amounts": {
                "revenueCents": 100000,
                "variableCents": 60000,
                "additionalFixedCents": 10000,
                "opportunityCents": 5000,
                "oneOffCents": 2000,
            },
        }
    ]
    pack = build_costing_pack(case)
    commentary = {
        "observations": [{"text": "Il risultato incrementale è 230 EUR."}],
        "hypotheses": [],
        "questions": [],
        "limitations": [],
    }

    html = render_html(pack, commentary)
    markdown = render_markdown(pack, commentary)

    assert "230,00" in html
    assert "Ordine aggiuntivo" in markdown
    assert "Il risultato incrementale è 230 EUR." in html
    assert "Il risultato incrementale è 230 EUR." in markdown


def test_reviewed_non_synthetic_mapping_requires_named_reviewer_and_date():
    case = reference()["case"]
    case["meta"]["demonstration"] = False
    case["evidence"][0].update(kind="document", status="documented")
    case["review"].update(
        status="reviewed",
        reviewer="Synthetic review test",
        reviewedAt="2026-10-03T12:00:00+02:00",
    )

    result = calculate_costing(case, ["direct_costing"])

    assert result["status"] == "ready_for_review"
