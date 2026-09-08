from __future__ import annotations

import copy
import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins/browser-automation/scripts"


@pytest.fixture
def review(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "batch_review", SCRIPTS / "batch_review.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(status="completed", identity="invoice-1"):
    return {
        "id": identity,
        "document": f"Demo {identity}",
        "action": "Registrare fattura",
        "reason": "Trattamento confermato per questa descrizione e cliente",
        "status": status,
        "proposed": [
            {
                "label": "Conto",
                "value": "Servizi",
                "source": "Proposta del modello basata sulla regola del cliente",
            }
        ],
        "actual": (
            [
                {
                    "label": "Conto",
                    "value": "Servizi",
                    "source": "Registrazione osservata",
                }
            ]
            if status == "completed"
            else []
        ),
        "evidence": [
            {
                "label": "Conferma",
                "value": "Registrazione salvata",
                "source": "Prima nota DEMO-1",
            }
        ],
        "outcome": "Registrata" if status == "completed" else "Non completata",
        "question": (
            ""
            if status in {"completed", "pending"}
            else "Verificare il risultato prima di riprovare"
        ),
        "posting_reference": "DEMO-1" if status == "completed" else "",
        "correction_of": "",
    }


def payload():
    return {
        "schema_version": "browser-batch-review/v1",
        "batch_id": "demo",
        "title": "Revisione dimostrativa",
        "scope": "Dati sintetici: nessun collegamento a TeamSystem",
        "status": "finished",
        "expected_items": 2,
        "entries": [entry(), entry("unverified", "invoice-2")],
        "reviews": [],
    }


def test_saved_report_reopens_after_run_with_exceptions_first(review, tmp_path):
    directory = tmp_path / "batch"
    path = review.save_review(directory, payload(), expected_revision=0)

    reopened = review.render_review(directory)

    assert reopened == path
    text = path.read_text()
    assert text.index("Demo invoice-2") < text.index("Demo invoice-1")
    assert "Esito da verificare: 1" in text
    assert "Trattamento proposto" in text
    assert "Prima nota DEMO-1" in text


def test_later_human_check_is_saved_without_changing_posting(review, tmp_path):
    directory = tmp_path / "batch"
    review.save_review(directory, payload(), expected_revision=0)

    path = review.record_review(
        directory,
        entry_id="invoice-1",
        decision="checked",
        note="Francesco conferma conto e IVA",
        expected_revision=1,
    )

    result = review.read_review(directory)
    assert result["revision"] == 2
    assert result["payload"]["entries"][0] == entry()
    assert result["payload"]["reviews"][0]["note"] == "Francesco conferma conto e IVA"
    assert "Controllata" in path.read_text()


def test_correction_request_does_not_claim_correction_was_executed(review, tmp_path):
    directory = tmp_path / "batch"
    review.save_review(directory, payload(), expected_revision=0)

    path = review.record_review(
        directory,
        entry_id="invoice-1",
        decision="correction_requested",
        note="Rivedere il conto",
        expected_revision=1,
    )

    result = review.read_review(directory)["payload"]
    assert result["entries"][0]["actual"] == entry()["actual"]
    assert len(result["entries"]) == 2
    assert "Correzione richiesta" in path.read_text()
    assert path.read_text().index("Demo invoice-1") < path.read_text().index(
        "Demo invoice-2"
    )


def test_completed_posting_can_only_be_corrected_with_separate_linked_entry(
    review, tmp_path
):
    directory = tmp_path / "batch"
    review.save_review(directory, payload(), expected_revision=0)
    data = payload()
    correction = entry("set_aside", "correction-1")
    correction["correction_of"] = "invoice-1"
    data["entries"].append(correction)

    review.save_review(directory, data, expected_revision=1)

    latest = review.read_review(directory)["payload"]
    assert latest["entries"][0] == entry()
    assert latest["entries"][2]["correction_of"] == "invoice-1"
    assert latest["expected_items"] == 2


@pytest.mark.parametrize(
    "change",
    [
        "rewrite_completed",
        "remove_item",
        "replace_identity",
        "replace_scope",
        "delete_review",
    ],
)
def test_updates_preserve_existing_history(review, tmp_path, change):
    directory = tmp_path / "batch"
    data = payload()
    data["reviews"] = [
        {
            "entry_id": "invoice-1",
            "decision": "checked",
            "note": "Checked",
            "at": "2026-09-08T12:00:00Z",
        }
    ]
    review.save_review(directory, data, expected_revision=0)
    update = copy.deepcopy(data)
    if change == "rewrite_completed":
        update["entries"][0]["reason"] = "A different explanation"
    elif change == "remove_item":
        update["entries"].pop()
        update["status"] = "paused"
    elif change == "replace_identity":
        update["entries"][0]["document"] = "Another invoice"
    elif change == "replace_scope":
        update["scope"] = "Another client"
    else:
        update["reviews"] = []

    with pytest.raises(ValueError):
        review.save_review(directory, update, expected_revision=1)


def test_interrupted_batch_preserves_pending_items_then_resumes(review, tmp_path):
    directory = tmp_path / "batch"
    data = payload()
    data["status"] = "paused"
    data["entries"][1] = entry("pending", "invoice-2")
    review.save_review(directory, data, expected_revision=0)
    data["entries"][1] = entry("set_aside", "invoice-2")
    data["status"] = "finished"

    path = review.save_review(directory, data, expected_revision=1)

    assert "Elaborazione terminata" in path.read_text()
    assert "Da decidere: 1" in path.read_text()
    assert (directory / "review-0001.html").exists()


@pytest.mark.parametrize(
    "change",
    [
        "missing_actual",
        "missing_evidence",
        "open_completed_question",
        "no_exception_question",
        "unknown_population",
        "pending_finish",
        "missing_item",
        "duplicate",
        "bad_correction",
        "bad_detail",
        "bad_schema",
        "bad_total",
        "bad_status",
        "bad_reviews",
        "bad_id",
        "bad_optional",
        "too_many_items",
        "bad_entry",
        "bad_array",
    ],
)
def test_invalid_or_incomplete_claims_are_rejected(review, change):
    data = payload()
    if change == "missing_actual":
        data["entries"][0]["actual"] = []
    elif change == "missing_evidence":
        data["entries"][0]["evidence"] = []
    elif change == "open_completed_question":
        data["entries"][0]["question"] = "Unknown account"
    elif change == "no_exception_question":
        data["entries"][1]["question"] = ""
    elif change == "unknown_population":
        data["expected_items"] = None
    elif change == "pending_finish":
        data["entries"][1]["status"] = "pending"
    elif change == "missing_item":
        data["expected_items"] = 3
    elif change == "duplicate":
        data["entries"][1]["id"] = "invoice-1"
    elif change == "bad_correction":
        data["entries"][1]["correction_of"] = "missing"
    elif change == "bad_detail":
        data["entries"][0]["actual"][0]["source"] = ""
    elif change == "bad_schema":
        data["schema_version"] = "other"
    elif change == "bad_total":
        data["expected_items"] = True
    elif change == "bad_status":
        data["status"] = "successful"
    elif change == "bad_reviews":
        data["reviews"] = [{}]
    elif change == "bad_id":
        data["entries"][0]["id"] = ""
    elif change == "bad_optional":
        data["entries"][0]["posting_reference"] = None
    elif change == "too_many_items":
        data["expected_items"] = 1
    elif change == "bad_entry":
        data["entries"][0]["extra"] = "unexpected"
    else:
        data["entries"][0]["actual"] = {}

    with pytest.raises(ValueError):
        review.validate_review(data)


def test_report_escapes_source_content_and_never_embeds_it_as_script(review, tmp_path):
    data = payload()
    data["entries"][0]["reason"] = '<script>alert("secret")</script>'
    data["entries"][0]["evidence"][0][
        "value"
    ] = '<img src="https://example.com/secret">'

    path = review.save_review(tmp_path / "batch", data, expected_revision=0)

    text = path.read_text()
    assert "<script>alert(" not in text
    assert "<img src=" not in text
    assert "&lt;script&gt;" in text
    assert "default-src 'none'" in text


@pytest.mark.parametrize("revision", [-1, True, 10000, 0])
def test_bad_or_stale_writer_cannot_overwrite_review(review, tmp_path, revision):
    directory = tmp_path / "batch"
    review.save_review(directory, payload(), expected_revision=0)

    with pytest.raises((ValueError, FileExistsError)):
        review.save_review(directory, payload(), expected_revision=revision)


def test_stale_human_review_is_rejected(review, tmp_path):
    directory = tmp_path / "batch"
    review.save_review(directory, payload(), expected_revision=0)
    review.save_review(directory, payload(), expected_revision=1)

    with pytest.raises(ValueError, match="stale"):
        review.record_review(
            directory,
            entry_id="invoice-1",
            decision="checked",
            note="Checked",
            expected_revision=1,
        )


@pytest.mark.parametrize(
    "damage",
    [
        "hash",
        "sequence",
        pytest.param(
            "symlink",
            marks=pytest.mark.skipif(
                os.name == "nt",
                reason="Windows symlink creation requires host privileges",
            ),
        ),
        "html",
        "record",
    ],
)
def test_reopen_detects_tampered_or_unsafe_artifacts(review, tmp_path, damage):
    directory = tmp_path / "batch"
    path = review.save_review(directory, payload(), expected_revision=0)
    source = directory / "review-0001.json"
    if damage == "hash":
        data = json.loads(source.read_text())
        data["payload"]["title"] = "Changed"
        source.write_text(json.dumps(data))
    elif damage == "sequence":
        source.rename(directory / "review-0002.json")
    elif damage == "symlink":
        moved = tmp_path / "moved.json"
        source.rename(moved)
        source.symlink_to(moved)
    elif damage == "html":
        path.write_text("tampered")
    else:
        source.write_text("{}")

    with pytest.raises(ValueError):
        review.render_review(directory)


def test_html_can_be_regenerated_from_saved_json(review, tmp_path):
    directory = tmp_path / "batch"
    path = review.save_review(directory, payload(), expected_revision=0)
    original = path.read_bytes()
    path.unlink()

    rebuilt = review.render_review(directory)

    assert rebuilt.read_bytes() == original


def test_cli_save_resume_and_human_review(review, tmp_path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(payload()))
    directory = tmp_path / "batch"
    assert review.main(["save", str(directory), "--input", str(source)]) == 0
    assert review.main(["resume", str(directory)]) == 0
    assert (
        review.main(
            [
                "review",
                str(directory),
                "--entry",
                "invoice-1",
                "--decision",
                "checked",
                "--note",
                "Checked by Francesco",
                "--expected-revision",
                "1",
            ]
        )
        == 0
    )
    assert review.read_review(directory)["revision"] == 2


@pytest.mark.parametrize("command", ["save", "review"])
def test_cli_requires_explicit_input(review, tmp_path, command):
    with pytest.raises(SystemExit):
        review.main([command, str(tmp_path / "batch")])


def test_cli_reports_missing_batch(review, tmp_path):
    assert review.main(["resume", str(tmp_path / "missing")]) == 1


def test_empty_paused_batch_does_not_claim_acquisition(review, tmp_path):
    data = payload()
    data.update(status="paused", expected_items=None, entries=[])

    path = review.save_review(tmp_path / "empty", data, expected_revision=0)

    assert "Nessuna fattura acquisita" in path.read_text()
    assert "Interrotto" in path.read_text()


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX permission bits are not Windows ACLs"
)
def test_private_files_use_owner_only_posix_modes(review, tmp_path):
    directory = tmp_path / "batch"
    path = review.save_review(directory, payload(), expected_revision=0)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
