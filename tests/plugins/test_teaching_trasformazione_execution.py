"""Execute the packaged synthetic transformation inputs, never learner approvals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.plugins._teaching_release import record_native_check

__all__ = []
ROOT = Path(__file__).resolve().parents[2]
ACTOR = "Synthetic regression operator"
REVIEWER = "Synthetic regression reviewer, not the learner"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_case(module, kit: Path, output: Path, phase: str) -> dict[str, Path]:
    """Use actual course facts with independently authored regression proposals."""
    source = kit / "files" / ("input" if phase == "demo" else "practice")
    facts = read(source / "case.json")
    rights = read(source / "participants.json")
    creditor = read(source / "creditors.json")
    valuation = read(source / "valuation.json")
    update = read(source / "valuation-update.json")
    store = module.CaseStore(output)
    store.initialize(f"COURSE-{phase}", ACTOR, facts["purpose"])
    store.update_case(
        {key: facts[key] for key in ("initial_form", "final_form", "proposed_date")},
        ACTOR,
    )
    for identity, name in (
        ("brief", "case.json"),
        ("rights", "participants.json"),
        ("creditors", "creditors.json"),
    ):
        store.import_evidence(
            identity, source / name, "Invented course evidence", name, ACTOR
        )
    for participant in rights["participants"]:
        store.put(
            "participant",
            {
                **participant,
                "title": "Synthetic proposed rights; no authenticated title",
                "work_share": {
                    "not_applicable": "No work-only participant in this invented case"
                },
                "dependencies": ["evidence:rights"],
            },
            ACTOR,
        )
    store.put(
        "creditor",
        {
            **{
                key: creditor[key]
                for key in (
                    "name",
                    "debt",
                    "receipt",
                    "receipt_date",
                    "consent",
                    "guarantee",
                    "release_assessment",
                    "opposition_assessment",
                )
            },
            "id": "C1",
            "origin_date": None,
            "dependencies": ["evidence:creditors"],
        },
        ACTOR,
    )

    def fact(identity, statement, dependencies):
        return store.put(
            "finding",
            {
                "id": identity,
                "category": "fact",
                "statement": statement,
                "rationale": "Independently authored synthetic regression proposal; inspect referenced input fields",
                "alternatives": [
                    "Seek missing evidence before professional qualification"
                ],
                "confidence": "synthetic_unverified",
                "dependencies": dependencies,
            },
            ACTOR,
        )

    def coverage(values):
        store.put(
            "calculation",
            {
                "id": "coverage",
                "operation": "capital_coverage",
                "args": {
                    "assets": values["assets"],
                    "liabilities": values["liabilities"],
                    "capital": values["proposed_capital"],
                },
                "dependencies": ["evidence:valuation"],
            },
            ACTOR,
        )
        fact(
            "capital",
            f"Synthetic declared liabilities: {values['liabilities']}; arithmetic is not legal capital approval.",
            ["calculation:coverage"],
        )

    # Proposal depends on evidence not yet received; do not substitute an output.
    coverage({"assets": None, "liabilities": None, "proposed_capital": None})
    store.put(
        "calculation",
        {
            "id": "allocation",
            "operation": "allocation",
            "args": {
                "capital": None,
                "shares": [p["capital_share"] for p in rights["participants"]],
            },
            "dependencies": ["evidence:valuation", "evidence:rights"],
        },
        ACTOR,
    )
    fact(
        "collection",
        f"The supplied list declares debt {creditor['debt']}; receipt and consent are unknown.",
        ["creditor:C1"],
    )
    store.put(
        "asset",
        {
            "id": "A1",
            "description": "Synthetic plant",
            "book_value": None,
            "estimated_value": None,
            "tax_value": valuation["tax_value"],
            "business_destination": None,
            "accounting_decision": None,
            "tax_decision": None,
            "dependencies": ["evidence:valuation"],
        },
        ACTOR,
    )
    store.put(
        "issue",
        {
            "id": "tax",
            "question": "Which current applicable sources and documented tax bases are missing?",
            "source_needed": "Professionally reviewed current official sources",
            "owner": REVIEWER,
            "blocks": True,
            "closure_criterion": "Outside this synthetic lesson",
            "resolution": None,
            "dependencies": ["asset:A1#tax_value"],
        },
        ACTOR,
    )
    for identity, dependencies in (
        (
            "capital",
            [
                "finding:capital",
                "calculation:allocation",
                "participant:P1",
                "participant:P2",
            ],
        ),
        ("collection", ["finding:collection"]),
        ("release", ["creditor:C1#receipt", "creditor:C1#release_assessment"]),
        (
            "opposition",
            ["creditor:C1#receipt_date", "creditor:C1#opposition_assessment"],
        ),
        ("tax", ["issue:tax", "asset:A1#tax_value"]),
    ):
        store.branch(
            identity,
            f"Synthetic {identity}",
            REVIEWER,
            "Inspect dependencies and missing evidence",
            dependencies,
            ACTOR,
        )
    missing = store.export()
    state = read(missing / "case.json")
    assert state["branches"]["capital"]["status"] == "blocked"
    assert state["branches"]["collection"]["status"] == "analysis_ready"
    assert "valuation" in " ".join(state["branches"]["capital"]["blockers"])
    store.import_evidence(
        "valuation",
        source / "valuation.json",
        "Invented valuation",
        "assets/liabilities",
        ACTOR,
    )

    coverage(valuation)
    store.put(
        "calculation",
        {
            "id": "allocation",
            "operation": "allocation",
            "args": {
                "capital": valuation["proposed_capital"],
                "shares": [p["capital_share"] for p in rights["participants"]],
            },
            "dependencies": ["evidence:valuation", "evidence:rights"],
        },
        ACTOR,
    )
    asset = store.load()["records"]["asset"]["A1"]
    store.put(
        "asset",
        {
            **{key: value for key, value in asset.items() if key != "version"},
            "book_value": valuation["book_value"],
            "estimated_value": valuation["estimated_value"],
        },
        ACTOR,
    )

    def approve(identity):
        state = store.submit(identity, ACTOR)
        store.review(
            identity,
            state["branches"][identity]["proposal_digest"],
            REVIEWER,
            "approve",
            "SIMULATED approval of synthetic preparation only",
        )

    approve("capital")
    approve("collection")
    approved = store.export()
    store.import_evidence(
        "valuation",
        source / "valuation-update.json",
        "Invented changed valuation",
        "liabilities",
        ACTOR,
    )
    stale = store.export()
    state = read(stale / "case.json")
    assert state["branches"]["capital"]["status"] == "stale"
    assert state["branches"]["collection"]["status"] == "approved_for_preparation"
    assert (
        state["records"]["calculation"]["coverage"]["args"]["liabilities"]
        == valuation["liabilities"]
    )
    with pytest.raises(ValueError, match="digest"):
        store.review(
            "capital",
            read(approved / "case.json")["branches"]["capital"]["proposal_digest"],
            REVIEWER,
            "approve",
            "SIMULATED obsolete approval",
        )
    # Fresh bytes alone do not fix stale interpretation or exact numeric inputs.
    coverage(update)
    approve("capital")
    revised = store.export()
    return {
        "missing": missing,
        "approved": approved,
        "stale": stale,
        "revised": revised,
    }


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize(
    "phase,initial_net,initial_margin,revised_net,revised_margin",
    [
        ("demo", "450000", "350000", "390000", "290000"),
        ("practice", "370000", "270000", "335000", "235000"),
    ],
)
def test_transformation_kit_native_dossier_and_selective_staleness(
    tmp_path,
    monkeypatch,
    language,
    phase,
    initial_net,
    initial_margin,
    revised_net,
    revised_margin,
    record_property,
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    monkeypatch.syspath_prepend(str(ROOT / "plugins/trasformazione/scripts"))
    import transform_case
    from courseware.library import CourseLibrary

    kit = tmp_path / "kit"
    CourseLibrary(ROOT / "plugins/vera", {"trasformazione"}).render(
        "trasformazione", language, kit
    )
    assert (kit / "course.html").is_file()
    stages = run_case(transform_case, kit, tmp_path / "execution", phase)
    approved = read(stages["approved"] / "case.json")
    revised = read(stages["revised"] / "case.json")
    initial_values = approved["branches"]["capital"]["calculations"][
        "calculation:coverage"
    ]["values"]
    revised_values = revised["branches"]["capital"]["calculations"][
        "calculation:coverage"
    ]["values"]
    assert initial_values["net_assets"]["exact"] == initial_net
    assert initial_values["margin"]["exact"] == initial_margin
    assert revised_values["net_assets"]["exact"] == revised_net
    assert revised_values["margin"]["exact"] == revised_margin
    allocation = revised["branches"]["capital"]["calculations"][
        "calculation:allocation"
    ]["values"]
    assert allocation["participant_1"]["exact"] == "60000"
    assert allocation["participant_2"]["exact"] == "40000"
    assert revised["records"]["participant"]["P1"]["vote_share"] == "1/2"
    assert revised["records"]["participant"]["P1"]["profit_share"] == "7/10"
    assert revised["records"]["asset"]["A1"]["tax_value"] is None
    assert revised["branches"]["tax"]["status"] == "blocked"
    assert revised["branches"]["release"]["status"] == "blocked"
    assert revised["branches"]["opposition"]["status"] == "blocked"
    assert revised["branches"]["capital"]["status"] == "approved_for_preparation"
    assert len(revised["decisions"]) == 3
    assert revised["decisions"][0]["reviewer"] == REVIEWER
    for path in stages.values():
        manifest = read(path / "manifest.json")
        assert (
            manifest["files"]["dossier.md"]
            == hashlib.sha256((path / "dossier.md").read_bytes()).hexdigest()
        )
    dossier = (stages["revised"] / "dossier.md").read_text()
    assert "Quali dati arrivano al modello" in dossier
    assert "BOZZA" in dossier
    assert "SIMULATED" in dossier
    history = list((tmp_path / "execution/history").glob("*.json"))
    assert len(history) > 15
    assert read(stages["approved"] / "case.json") == approved
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    from model_data_report import main as report_main

    disclosure = {
        "schema_version": 1,
        "workflow_id": "trasformazione",
        "run_id": f"course-{phase}-{language}",
        "runtime_profile": "openai-codex",
        "language": language,
        "created_at": "2026-10-01T10:00:00+00:00",
        "professional_purpose": "Synthetic native course regression; no learner or professional acceptance",
        "phases": [
            {
                "phase_id": "synthetic-regression",
                "purpose": "Exercise local persistence, calculations and review history",
                "outcome": "not_measurable",
                "evidence_basis": "host_attested",
                "source_extent": [],
                "locally_processed": [],
                "model_visible": [],
                "remained_local": [],
                "reason": "The automated pipeline invokes no model or network service. This fixture does not measure the surrounding native chat context or attest learner exposure. No local-only inference claim is made.",
                "evidence_files": [],
            }
        ],
        "improvement_assessment": {"status": "not_assessed", "candidates": []},
    }
    report_input = tmp_path / "execution/disclosure-input.json"
    report_input.write_text(json.dumps(disclosure), encoding="utf-8")
    assert (
        report_main(
            [
                "build",
                "--input",
                str(report_input),
                "--output-dir",
                str(tmp_path / "execution"),
            ],
            server_attestation=False,
        )
        == 0
    )
    assert (tmp_path / "execution/model_data_report.md").is_file()
    assert (
        read(tmp_path / "execution/model_data_report.json")["workflow_id"]
        == "trasformazione"
    )
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="trasformazione",
        language=language,
        phase=phase,
    )


@pytest.mark.parametrize("archive_name", ["vera-plugin.zip", "vera-chatgpt-upload.zip"])
def test_packaged_transformation_course_renders_and_executes_without_repository_sources(
    tmp_path, archive_name
):
    """Use extracted native packages and their actual own-product entrypoints."""
    import importlib.util
    import subprocess
    import sys
    from zipfile import ZipFile

    with ZipFile(ROOT / "plugin_packages/vera" / archive_name) as archive:
        archive.extractall(tmp_path / "installed")
    manifest = next((tmp_path / "installed").rglob(".codex-plugin/plugin.json"))
    plugin = manifest.parents[1]
    kit = tmp_path / "kit"
    result = subprocess.run(
        [
            sys.executable,
            str(plugin / "scripts/local_courses.py"),
            "render",
            "--workflow",
            "trasformazione",
            "--language",
            "it",
            "--output-dir",
            str(kit),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert (kit / "course.html").is_file()
    component = plugin / "modules/trasformazione/scripts/transform_case.py"
    spec = importlib.util.spec_from_file_location("packaged_transformation", component)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stages = run_case(module, kit, tmp_path / "execution", "practice")
    revised = read(stages["revised"] / "case.json")
    assert (
        revised["branches"]["capital"]["calculations"]["calculation:coverage"][
            "values"
        ]["margin"]["exact"]
        == "235000"
    )
    assert revised["branches"]["tax"]["status"] == "blocked"
