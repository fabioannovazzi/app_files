"""Execute actual Scissione kit inputs; reviews are explicit test-only fixtures.

No learner participation, professional acceptance, voice or window visibility is
simulated. Case interpretation below is synthetic host work, never kit content.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from tests.plugins._teaching_release import record_native_check
from tests.plugins.test_scissione_guidata import case, review_request, row
from tests.plugins.test_teaching_kit_execution import (
    _bound_case,
    _complete_teaching_case,
    _write,
)

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
LANGUAGES = ["it", "en", "fr", "de", "es"]
sys.path.insert(0, str(ROOT / "plugins/scissione-guidata/scripts"))
from run_scissione import execute, read_revision  # noqa: E402
from scissione_core import ScissioneError  # noqa: E402


def _interpret(run: dict, language: str, *, updated: bool = False) -> dict:
    """Bind the fixture interpretation to the exact imported, authored inputs."""
    data = case()
    data["operation_id"] = "fictional-arco-demerging"
    data["purpose"] = (
        "Fictional Arco division; missing lease and unexamined contingent liabilities"
    )
    data["entities"][0]["name"] = "Arco Meccanica S.r.l. — fictional"
    data["entities"][1]["name"] = "Arco Servizi S.r.l. — fictional"
    inputs = Path(run["context"]["run_root"]) / "inputs"
    selected = sorted(p for p in inputs.rglob("*") if p.suffix in {".md", ".csv"})
    data["evidence"] = [
        {
            "id": path.stem,
            "entity_ids": ["scissa", "beneficiary"],
            "path": path.relative_to(inputs).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "locator": (
                "Whole fictional mandate"
                if path.suffix == ".md"
                else "Header and two allocation rows"
            ),
            "as_of": "2026-09-29",
        }
        for index, path in enumerate(selected)
    ]
    mandate = next(p for p in selected if p.name == f"mandate-{language}.md")
    assert "800000" in mandate.read_text()
    csv_name = "allocations-update.csv" if updated else "allocations.csv"
    source = next(p for p in selected if p.name == csv_name)
    with source.open() as stream:
        allocations = list(csv.DictReader(stream))
    original = row(data, "inventory")
    data["records"].remove(original)
    ids = []
    net = {field: Decimal(0) for field in ("before", "transferred", "remaining")}
    for entry in allocations:
        item = copy.deepcopy(original)
        item["id"] = entry["item_id"]
        item["data"]["item_id"] = entry["item_id"]
        item["data"]["side"] = entry["side"]
        item["evidence_ids"] = [
            evidence["id"]
            for evidence in data["evidence"]
            if evidence["path"].endswith(csv_name)
        ]
        for basis in ("book", "tax", "economic"):
            item["data"][basis] = {field: entry[f"{basis}_{field}"] for field in net}
        for field in net:
            net[field] += Decimal(entry[f"economic_{field}"]) * (
                1 if entry["side"] == "asset" else -1
            )
        ids.append(item["id"])
        data["records"].append(item)
    evidence_ids = [f"mandate-{language}"]
    for item in data["records"]:
        if item["evidence_ids"] == ["source"]:
            item["evidence_ids"] = evidence_ids
        item["depends_on"] = [
            value for value in item["depends_on"] if value != "inventory"
        ]
    row(data, "valuation")["evidence_ids"] = [Path(csv_name).stem]
    row(data, "valuation")["data"].update(
        {field: str(value) for field, value in net.items()}
    )
    row(data, "calculation")["depends_on"].extend(ids)
    row(data, "calculation")["data"]["allocation_ids"] = ids
    row(data, "perimeter")["depends_on"].extend(ids)
    row(data, "perimeter")["data"]["required_records"].remove("inventory")
    row(data, "perimeter")["data"]["required_records"].extend(ids)
    row(data, "contracts").update(status="unknown")
    row(data, "contracts")["data"] = {"value": None, "basis": "Lease not supplied"}
    row(data, "liabilities").update(status="unknown")
    row(data, "liabilities")["data"] = {
        "amount": None,
        "basis": "Contingent liabilities not examined",
    }
    return data


def _request(run: dict, name: str, payload: dict, action: str) -> dict:
    path = Path(run["output_dir"]) / name
    _write(path, payload)
    return execute(Path(run["context_path"]), action, path)


def _review(run: dict, draft: dict) -> dict:
    return _request(
        run,
        "synthetic-test-review.json",
        review_request(
            draft, ["route", "ownership", "valuation", "machine", "loan", "calculation"]
        ),
        "review",
    )


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_scissione_kit_runs_missing_evidence_and_selective_reopening(
    tmp_path, monkeypatch, record_property, language, phase
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "scissione-guidata",
        "scissione-guidata",
        "demo",
        language=language,
    )
    draft = _request(
        run, "proposal.json", {"case": _interpret(run, language)}, "prepare"
    )
    assert draft["schedule"] == {}
    assert draft["approvals"] == {}
    with pytest.raises(ScissioneError, match="unknown|Unknown"):
        _request(
            run,
            "rejected-perimeter.json",
            review_request(draft, ["perimeter"]),
            "review",
        )
    result = _review(run, draft)
    assert result["schedule"]["owners"][0]["economic_transferred"] == "144000.00"
    assert result["schedule"]["owners"][1]["economic_transferred"] == "96000.00"
    assert result["schedule"]["owners"][0]["units_rounded"] == "6000"
    assert result["schedule"]["owners"][0]["shareholder_tax_cost"] is None
    assert result["status"] == "partial"
    assert row(result["case"], "contracts")["status"] == "unknown"
    assert (
        read_revision(Path(run["output_dir"]), draft["revision_sha256"])["approvals"]
        == {}
    )
    revision_path = f"scissione_versions/{result['revision_sha256']}/revision.json"
    ledger = _complete_teaching_case(
        run, tmp_path / "case", artifact_ids={revision_path: "prior_revision"}
    )
    if phase == "practice":
        from courseware.library import CourseLibrary

        old_files = {
            p: p.read_bytes()
            for p in Path(run["context"]["run_root"]).rglob("*")
            if p.is_file()
        }
        kit = CourseLibrary(ROOT / "plugins/vera", {"scissione-guidata"}).render(
            "scissione-guidata", language, tmp_path / "updated-kit"
        )
        context = run["context"]
        imported = [
            ledger.import_document(
                tmp_path / "case",
                context["client_id"],
                context["engagement_id"],
                Path(p),
                "source",
            )
            for p in kit["practice_files"]
        ]
        prepared = ledger.prepare_run(
            tmp_path / "case",
            context["client_id"],
            context["engagement_id"],
            "scissione-guidata",
            "0.1.0",
            input_ids=[item["receipt"]["input_id"] for item in imported],
            upstream_artifacts=[
                {
                    "run_id": context["run_id"],
                    "artifact_id": "prior_revision",
                    "role": "case",
                }
            ],
            new_run=True,
        )
        run = ledger.start_run(
            tmp_path / "case", context["engagement_id"], prepared["run"]["run_id"]
        )
        binding = next(
            item
            for item in run["context"]["input_bindings"]
            if item["kind"] == "upstream_artifact"
        )
        upstream = (
            Path(binding["path"])
            .relative_to(Path(run["context"]["run_root"]) / "inputs")
            .as_posix()
        )
        changed = _request(
            run,
            "continuation.json",
            {
                "case": _interpret(run, language, updated=True),
                "previous_revision_path": upstream,
            },
            "prepare",
        )
        # Changed physical evidence and its dependent values must reopen reviews.
        assert {"machine", "valuation", "calculation"}.issubset(
            changed["change_impact"]["invalidated_approval_ids"]
        )
        assert changed["approvals"]["ownership"] == result["approvals"]["ownership"]
        assert changed["approvals"]["route"] == result["approvals"]["route"]
        assert changed["previous_sha256"] == result["revision_sha256"]
        result = _review(run, changed)
        assert result["schedule"]["owners"][0]["economic_transferred"] == "162000.00"
        assert result["schedule"]["owners"][1]["economic_transferred"] == "108000.00"
        assert result["schedule"]["allocations"][0]["book"]["transferred"] == "150000"
        assert result["schedule"]["allocations"][0]["tax"]["transferred"] == "120000"
        assert all(path.read_bytes() == content for path, content in old_files.items())
        _complete_teaching_case(run, tmp_path / "case")
    assert result["legal_validation"] == "not_certified"
    assert result["filing_status"] == "not_performed"
    version = Path(run["output_dir"]) / "scissione_versions" / result["revision_sha256"]
    assert "Firma e deposito non eseguiti" in (version / "review.md").read_text()
    assert read_revision(Path(run["output_dir"])) == result
    _write(
        tmp_path / "reviewed-artifacts.json",
        {
            name: hashlib.sha256((version / name).read_bytes()).hexdigest()
            for name in (
                "review.html",
                "ownership_before_after.json",
                "allocations.json",
                "change_impact.json",
            )
        },
    )
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="scissione-guidata",
        language=language,
        phase=phase,
    )
