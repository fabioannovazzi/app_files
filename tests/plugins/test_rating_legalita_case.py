from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/rating-legalita/scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "rating_case_test", SCRIPTS / "rating_case.py"
)
assert SPEC and SPEC.loader
CASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CASE)
sys.path.remove(str(SCRIPTS))


def prepared_case(tmp_path: Path) -> dict:
    """Qualified synthetic decisions test plumbing, not model legal accuracy."""
    case = CASE.new_case("SYN-001", "2026-10-02", synthetic=True)
    case.update(
        client={
            "legal_name": "Impresa sintetica",
            "archive_client_id": None,
            "engagement_id": None,
        },
        operation="first_attribution",
        status="evidence_in_progress",
    )
    case["subjects"] = [
        {
            "subject_id": "PERSON-1",
            "name_or_alias": "Persona sintetica",
            "role": "Amministratore",
            "start_date": "2020-01-01",
            "end_date": None,
            "inclusion": "included",
            "reason": "Ruolo assunto nel solo test sintetico",
        }
    ]
    review = {
        "actor": "Revisore sintetico",
        "date": "2026-10-02",
        "kind": "synthetic_assumption",
        "reason": "Esito convenzionale di prova; non costituisce verifica professionale",
        "source_ids": ["S01"],
    }
    source = "SYNTHETIC FIXTURE: base requirements reviewed as satisfied; ANAC deduction absent."
    (tmp_path / "evidence.txt").write_text(source)
    case["evidence"] = [
        {
            "evidence_id": "E1",
            "kind": "synthetic_fact",
            "title": "Assunzioni di test",
            "uri": "evidence.txt",
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
            "as_of": "2026-10-02",
            "read_status": "read",
            "limitations": ["Synthetic decisions, not model extraction"],
        }
    ]
    current = copy.deepcopy(case["snapshots"][0])
    current["snapshot_id"] = "OBS-1"
    current.update(base_status="verified", estimated_rating="★")
    for rule in sorted(CASE.BASE_IDS | {"P09"}):
        current["instances"].append(
            {
                "instance_id": rule + ":PERSON-1",
                "rule_id": rule,
                "subject_id": "PERSON-1",
                "event_id": None,
                "status": "failed" if rule == "P09" else "verified",
                "outcome": "not_satisfied" if rule == "P09" else "satisfied",
                "fact": "Synthetic qualified fact for " + rule,
                "evidence_links": [
                    {"evidence_id": "E1", "locator": "line 1", "excerpt": source}
                ],
                "decision": copy.deepcopy(review),
            }
        )
    case["snapshots"].append(current)
    case["scope"].update(
        source_current=True,
        perimeter_reviewed=True,
        coverage_review=review,
        required_instance_ids=[
            row["instance_id"]
            for row in current["instances"]
            if row["rule_id"] in CASE.BASE_IDS
        ],
    )
    return case


def test_start_without_documents_produces_incomplete_dossier(tmp_path):
    case = CASE.new_case("INTAKE-1", "2026-10-02")

    record = CASE.assess_case(case, tmp_path)

    assert record["assessment"]["status"] == "incomplete"
    assert record["assessment"]["score"]["estimated_rating"] is None
    assert record["case"]["client"] is None


def test_positive_case_saves_review_dossier_and_never_official_rating(tmp_path):
    case = prepared_case(tmp_path)

    record = CASE.assess_case(case, tmp_path)
    output = CASE.save_dossier(record, tmp_path / "output")

    assert record["assessment"]["status"] == "ready_for_review"
    assert record["assessment"]["score"]["estimated_rating"] == "★"
    assert record["assessment"]["official_rating"] is None
    assert record["assessment"]["submission_authorized"] is False
    assert "CASO SINTETICO" in (output / "dossier.md").read_text()
    assert "SYNTHETIC FIXTURE" in (output / "dossier.md").read_text()


@pytest.mark.parametrize(
    "state,outcome,expected",
    [
        ("claimed", "unknown", "incomplete"),
        ("disputed", "unknown", "incomplete"),
        ("stale", "unknown", "incomplete"),
        ("failed", "not_satisfied", "not_eligible"),
    ],
)
def test_open_or_failed_base_prevents_rating(tmp_path, state, outcome, expected):
    case = prepared_case(tmp_path)
    case["snapshots"][-1]["instances"][0].update(status=state, outcome=outcome)

    result = CASE.assess_case(case, tmp_path)["assessment"]

    assert result["status"] == expected
    assert result["score"]["estimated_rating"] is None


def test_conditional_target_does_not_replace_observed_gap(tmp_path):
    case = prepared_case(tmp_path)
    target = copy.deepcopy(case["snapshots"][-1])
    target.update(
        kind="conditional_scenario",
        snapshot_id="TARGET",
        conditions=["Only after new evidence"],
    )
    case["snapshots"][-1]["instances"][0].update(status="claimed", outcome="unknown")
    case["snapshots"].append(target)

    record = CASE.assess_case(case, tmp_path)

    assert record["assessment"]["base_status"] == "undetermined"
    assert "Scenario obiettivo — non realizzato" in CASE.render_dossier(record)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("excerpt", "Invented passage", "Quoted evidence"),
        ("evidence_id", "MISSING", "Unknown evidence"),
    ],
)
def test_missing_or_fabricated_citation_is_rejected(tmp_path, field, value, error):
    case = prepared_case(tmp_path)
    case["snapshots"][-1]["instances"][0]["evidence_links"][0][field] = value

    with pytest.raises(ValueError, match=error):
        CASE.assess_case(case, tmp_path)


def test_changed_source_is_rejected(tmp_path):
    case = prepared_case(tmp_path)
    (tmp_path / "evidence.txt").write_text("changed")

    with pytest.raises(ValueError, match="hash changed"):
        CASE.assess_case(case, tmp_path)


def test_omitted_control_prevents_positive_summary(tmp_path):
    case = prepared_case(tmp_path)
    case["snapshots"][-1]["instances"].pop(0)
    case["scope"]["required_instance_ids"].pop(0)

    result = CASE.assess_case(case, tmp_path)["assessment"]

    assert result["base_status"] == "undetermined"


def test_uncovered_subject_prevents_positive_summary(tmp_path):
    case = prepared_case(tmp_path)
    subject = copy.deepcopy(case["subjects"][0])
    subject["subject_id"] = "PERSON-2"
    case["subjects"].append(subject)

    result = CASE.assess_case(case, tmp_path)["assessment"]

    assert "Soggetto non coperto: PERSON-2" in result["blockers"]


def test_preserves_t0_and_rejects_rewritten_history(tmp_path):
    case = prepared_case(tmp_path)
    previous = CASE.assess_case(case, tmp_path)
    case["snapshots"][0]["conditions"] = ["rewritten"]

    with pytest.raises(ValueError, match="immutable"):
        CASE.assess_case(case, tmp_path, previous)


def test_real_case_rejects_synthetic_evidence(tmp_path):
    from tests.plugins.test_rating_legalita_practice import pilot_records

    case = prepared_case(tmp_path)
    pilot_records(case)
    case["synthetic"] = False

    with pytest.raises(ValueError, match="Synthetic evidence"):
        CASE.assess_case(case, tmp_path)


def test_evidence_cannot_escape_input_folder(tmp_path):
    case = prepared_case(tmp_path)
    case["evidence"][0]["uri"] = "../outside.txt"

    with pytest.raises(ValueError, match="inside the input folder"):
        CASE.assess_case(case, tmp_path)


def test_changed_record_cannot_be_saved(tmp_path):
    record = CASE.assess_case(CASE.new_case("INTAKE", "2026-10-02"), tmp_path)
    record["assessment"]["status"] = "ready_for_review"

    with pytest.raises(ValueError, match="changed after validation"):
        CASE.save_dossier(record, tmp_path)


def test_real_case_cli_requires_archive_binding(tmp_path):
    case = prepared_case(tmp_path)
    case["synthetic"] = False
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "rating_case.py"),
            "render",
            "--case",
            str(path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "require a Studio Archive" in result.stderr


def test_synthetic_cli_delivers_inspectable_dossier(tmp_path):
    case = prepared_case(tmp_path)
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "rating_case.py"),
            "render",
            "--case",
            str(path),
            "--source-root",
            str(tmp_path),
            "--output",
            str(tmp_path / "output"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert len(list((tmp_path / "output").glob("*/dossier.md"))) == 1


def test_cli_init_and_render_without_documents(tmp_path, monkeypatch):
    path = tmp_path / "case.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rating_case",
            "init",
            "--case-id",
            "INTAKE",
            "--as-of",
            "2026-10-02",
            "--output",
            str(path),
        ],
    )
    CASE.main()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rating_case",
            "render",
            "--case",
            str(path),
            "--source-root",
            str(tmp_path),
            "--output",
            str(tmp_path / "output"),
        ],
    )

    result = CASE.main()

    assert result == 0
    record = json.loads(next((tmp_path / "output").glob("*/dossier.json")).read_text())
    assert record["assessment"]["status"] == "incomplete"


def test_cli_real_archive_receipts_produce_a_dossier(tmp_path, monkeypatch):
    case = prepared_case(tmp_path)
    from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger

    ledger = _load_customer_ledger()
    client_root = tmp_path / "Client"
    client_root.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client_root, client_id)
    engagement_id = ledger.create_engagement(
        client_root, client_id, "Synthetic rating test"
    )["engagement_id"]
    receipt = ledger.import_document(
        client_root, client_id, engagement_id, tmp_path / "evidence.txt", "source"
    )["receipt"]
    prepared = ledger.prepare_run(
        client_root,
        client_id,
        engagement_id,
        "rating-legalita",
        "0.1.0",
        input_ids=[receipt["input_id"]],
    )
    running = ledger.start_run(client_root, engagement_id, prepared["run"]["run_id"])
    workspace = {
        "context": running["context"],
        "context_path": Path(running["context_path"]),
        "output_dir": Path(running["output_dir"]),
        "input_paths": [
            Path(row["path"]) for row in running["context"]["input_bindings"]
        ],
    }
    from tests.plugins.test_rating_legalita_practice import pilot_records

    pilot_records(case)
    case["synthetic"] = False
    case["client"].update(
        archive_client_id=workspace["context"]["client_id"],
        engagement_id=workspace["context"]["engagement_id"],
    )
    case["evidence"][0].update(
        kind="document",
        uri=workspace["input_paths"][0]
        .relative_to(Path(workspace["context"]["run_root"]) / "inputs")
        .as_posix(),
    )
    case["scope"]["coverage_review"]["kind"] = "professional"
    for row in case["snapshots"][-1]["instances"]:
        row["decision"]["kind"] = "professional"
    path = workspace["output_dir"] / "review_input.json"
    path.write_text(json.dumps(case))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rating_case",
            "render",
            "--case",
            str(path),
            "--client-engagement",
            str(workspace["context_path"]),
        ],
    )

    result = CASE.main()

    assert result == 0
    assert len(list(workspace["output_dir"].glob("*/dossier.md"))) == 1


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("duplicate_evidence", "Duplicate evidence_id"),
        ("unknown_subject", "Unknown instance subject"),
        ("unknown_event", "Unknown instance event"),
        ("unread", "read, hashed evidence"),
        ("no_evidence", "needs evidence"),
        ("source_id", "known source IDs"),
        ("future_review", "Review is in the future"),
    ],
)
def test_broken_decision_lineage_rejected(tmp_path, mutation, error):
    case = prepared_case(tmp_path)
    row = case["snapshots"][-1]["instances"][0]
    if mutation == "duplicate_evidence":
        case["evidence"].append(copy.deepcopy(case["evidence"][0]))
    elif mutation == "unknown_subject":
        row["subject_id"] = "missing"
    elif mutation == "unknown_event":
        row["event_id"] = "missing"
    elif mutation == "unread":
        case["evidence"][0]["read_status"] = "unread"
    elif mutation == "no_evidence":
        row["evidence_links"] = []
    elif mutation == "source_id":
        row["decision"]["source_ids"] = ["missing"]
    else:
        row["decision"]["date"] = "2027-01-01"

    with pytest.raises(ValueError, match=error):
        CASE.assess_case(case, tmp_path)
