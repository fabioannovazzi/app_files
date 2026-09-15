"""Synthetic local-flow checks; these do not constitute a DATEV Windows run."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]
VERA = ROOT / "plugins/vera"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def helper():
    return load(VERA / "scripts/datev_starter.py", "datev_starter")


def event(source: str = "host_tool") -> dict:
    return {
        "id": "environment",
        "intent": "Verificare controllo nativo",
        "action": "Interrogati gli strumenti disponibili nell'host di prova",
        "decision_reason": "DATEV è un'applicazione nativa",
        "outcome": "Controllo nativo non disponibile nella fixture",
        "postcondition": "Nessuna azione DATEV eseguita",
        "source_type": source,
        "source_ref": "test-tool-result-1 (simulato)",
        "uncertainties": ["Collegamento alla finestra ancora da verificare"],
        "next_step": "Identificare la versione DATEV e il supporto Computer Use",
    }


def request() -> dict:
    return {
        "schema_version": "browser-development-request/v1",
        "request_id": "datev-native-adaptation",
        "title": "Adattare la procedura fatture passive a DATEV Windows",
        "process": "DATEV desktop; prodotto e versione da acquisire",
        "objective": "Un esempio con report per cliente e progressi riprendibili",
        "source_version": "Fixture sintetica; nessuna prova live",
        "findings": [
            {
                "summary": "Resoconto strumento host simulato: controllo nativo indisponibile",
                "basis": "operator_report",
                "step_ids": ["environment"],
            }
        ],
        "requested_work": [
            "Verificare il supporto host e collegare la finestra nativa"
        ],
        "acceptance_checks": [
            "Una fattura reale conserva descrizioni complete e associazioni nel report"
        ],
        "gaps": ["Non disponibili prodotto, versione e schermata DATEV reali"],
        "known_limits": [
            "Nessun replay DATEV live; nessun esecutore browser applicabile"
        ],
    }


def review() -> dict:
    return {
        "schema_version": "browser-batch-review/v1",
        "batch_id": "local-client-a",
        "title": "Esempio sintetico DATEV",
        "scope": "Cliente fittizio A; una fattura; resto non verificato",
        "status": "paused",
        "expected_items": 1,
        "entries": [
            {
                "id": "invoice-1",
                "document": "Fattura fittizia 1",
                "action": "Rivedere il trattamento",
                "reason": "Associazione da verificare",
                "status": "set_aside",
                "proposed": [],
                "actual": [],
                "evidence": [
                    {
                        "label": "Descrizione completa",
                        "value": "Riga sintetica privata",
                        "source": "Fixture, non DATEV",
                    }
                ],
                "outcome": "Nessuna registrazione",
                "question": "Verificare trattamento del cliente",
                "posting_reference": "",
                "correction_of": "",
            }
        ],
        "reviews": [],
    }


def test_start_ships_known_procedure_and_saves_empty_truthful_progress(
    helper, tmp_path
):
    result = helper.start(tmp_path / "run")
    assert result["revision"] == 1
    assert result["steps"] == []
    assert result["execution_verified"] is False
    assert result["client_reviews"] == []
    assert "Nessun profilo" in result["start_state"]
    assert (tmp_path / "run/PROCEDURA.md").read_bytes() == helper.PROCEDURE.read_bytes()
    assert Path(result["report_path"]).is_file()


@pytest.mark.parametrize("source", ["host_tool", "operator_report", "unknown"])
def test_unsupported_or_reported_step_resumes_without_fabricated_observation(
    helper, tmp_path, source
):
    run = tmp_path / "run"
    helper.start(run)
    helper.record(run, event(source), expected_revision=1)
    result = helper.resume(run)
    assert result["revision"] == 2
    assert result["execution_verified"] is False
    assert result["native_replay_validated"] is False
    assert result["resume_instruction"] == event()["next_step"]
    assert source in result["steps"][0]["outcome"]
    assert result["steps"][0]["evidence_basis"] != "observed"
    assert (
        helper.checkpoint.read_checkpoint(run)["payload"]["steps"][0]["capture"] is None
    )


def test_stale_writer_does_not_overwrite_saved_progress(helper, tmp_path):
    run = tmp_path / "run"
    helper.start(run)
    helper.record(run, event(), expected_revision=1)
    before = (run / "checkpoint-0002.json").read_bytes()
    with pytest.raises(ValueError, match="Stale"):
        helper.record(run, event(), expected_revision=1)
    assert (run / "checkpoint-0002.json").read_bytes() == before


def test_native_event_rejects_browser_capture_claim(helper, tmp_path):
    run = tmp_path / "run"
    helper.start(run)
    payload = event()
    payload["capture"] = {"before_sha256": "a" * 64}
    with pytest.raises(ValueError, match="not browser capture"):
        helper.record(run, payload, expected_revision=1)
    assert helper.resume(run)["revision"] == 1


def test_partial_client_report_and_later_correction_survive_resume(helper, tmp_path):
    run = tmp_path / "run"
    helper.start(run)
    helper.save_client_review(run, "a", review(), expected_revision=0)
    helper.batch.record_review(
        run / "client-a",
        entry_id="invoice-1",
        decision="correction_requested",
        note="Rivedere conto della fattura sintetica",
        expected_revision=1,
    )
    result = helper.resume(run)
    assert len(result["client_reviews"]) == 1
    assert "Correzione richiesta" in Path(result["client_reviews"][0]).read_text()
    assert "Riga sintetica privata" in Path(result["client_reviews"][0]).read_text()
    assert (
        helper.batch.read_review(run / "client-a")["payload"]["entries"][0]["status"]
        == "set_aside"
    )


def test_client_scope_cannot_be_changed_during_resume(helper, tmp_path):
    run = tmp_path / "run"
    helper.start(run)
    helper.save_client_review(run, "a", review(), expected_revision=0)
    different_client = review()
    different_client["scope"] = "Cliente diverso"
    with pytest.raises(ValueError, match="identity or scope"):
        helper.save_client_review(run, "a", different_client, expected_revision=1)


def test_partial_native_request_exports_only_reviewed_text_not_private_case(
    helper, tmp_path
):
    run = tmp_path / "run"
    helper.start(run)
    helper.record(run, event(), expected_revision=1)
    helper.save_client_review(run, "a", review(), expected_revision=0)
    output = tmp_path / "technical-review"
    prepared = helper.prepare(run, request(), output)
    archive = helper.development.export_request(
        output,
        tmp_path / "approved.zip",
        expected_sha256=prepared["review_sha256"],
        approval_id="synthetic-user-approval",
    )
    assert helper.development.verify_archive(archive)["cr_id"] is None
    assert helper.development.verify_archive(archive)["sent"] is False
    with ZipFile(archive) as zipped:
        assert set(zipped.namelist()) == {
            "RICHIESTA.md",
            "request.json",
            "sources.json",
            "review-manifest.json",
            "transfer-approval.json",
        }
        assert b"Riga sintetica privata" not in b"".join(
            zipped.read(name) for name in zipped.namelist()
        )
    assert helper.resume(run)["revision"] == 2


def test_native_request_cannot_promote_report_to_observed(helper, tmp_path):
    run = tmp_path / "run"
    helper.start(run)
    helper.record(run, event(), expected_revision=1)
    payload = request()
    payload["findings"][0]["basis"] = "observed"
    with pytest.raises(ValueError, match="cannot be promoted"):
        helper.prepare(run, payload, tmp_path / "request")


def test_another_testers_checkpoint_is_not_relabelled_datev(helper, tmp_path):
    run = tmp_path / "run"
    helper.start(run)
    payload = helper.checkpoint.read_checkpoint(run)["payload"]
    payload["objective"] = "Procedura ECONS di un altro operatore"
    foreign = tmp_path / "foreign"
    helper.checkpoint.save_checkpoint(foreign, payload, expected_revision=0)
    with pytest.raises(ValueError, match="not a DATEV"):
        helper.resume(foreign)


def test_cli_record_resume_review_and_prepare_partial_request(helper, tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO)
    run = tmp_path / "run"
    assert helper.main(["start", str(run)]) == 0
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(event()))
    assert (
        helper.main(
            ["record", str(run), "--input", str(input_path), "--expected-revision", "1"]
        )
        == 0
    )
    input_path.write_text(json.dumps(review()))
    assert (
        helper.main(
            [
                "save-review",
                str(run),
                "--input",
                str(input_path),
                "--expected-revision",
                "0",
                "--client-key",
                "a",
            ]
        )
        == 0
    )
    input_path.write_text(json.dumps(request()))
    output = tmp_path / "review"
    assert (
        helper.main(
            [
                "prepare-request",
                str(run),
                "--input",
                str(input_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert helper.main(["resume", str(run)]) == 0
    assert (output / "request.json").is_file()
    assert "native_replay_validated" in caplog.text


def test_cli_reports_save_failure_without_claiming_progress(helper, tmp_path, caplog):
    assert helper.main(["start", str(tmp_path / "absent-parent/run")]) == 1
    assert not (tmp_path / "absent-parent/run").exists()
    assert "report_path" not in caplog.text


def test_prepared_request_uses_existing_capability_text_api_with_receipt(
    helper, tmp_path, monkeypatch
):
    run = tmp_path / "run"
    helper.start(run)
    helper.record(run, event(), expected_revision=1)
    output = tmp_path / "technical-review"
    helper.prepare(run, request(), output)
    client = load(VERA / "scripts/change_requests.py", "datev_change_requests")
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(tmp_path / "state"))
    sent = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _amount):
            return json.dumps(
                {
                    "change_request_id": "CR-999",
                    "status_token": "synthetic-token",
                    "status": "open",
                    "fixed": False,
                    "fixed_version": None,
                    "install_url": None,
                }
            ).encode()

    def opener(req, **_kwargs):
        sent.append(json.loads(req.data))
        return Response()

    receipt = client.submit_suggestion(
        VERA, output / "request.json", opener=opener, now=100.0
    )
    assert receipt["change_request_id"] == "CR-999"  # Simulated server receipt only.
    assert sent[0]["kind"] == "capability"
    assert sent[0]["request"] == request()
    assert "attachments" not in sent[0]


def test_installed_cli_resolves_bundled_procedure_and_helpers(tmp_path):
    # A minimal installation layout proves resolution without a source checkout.
    import shutil

    installed = tmp_path / "installed"
    for relative in ["scripts/datev_starter.py", ".codex-plugin/plugin.json"]:
        target = installed / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(VERA / relative, target)
    shutil.copytree(
        ROOT / "plugins/browser-automation", installed / "modules/browser-automation"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(installed / "scripts/datev_starter.py"),
            "start",
            str(tmp_path / "run"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stderr)["route"] == "datev-native-guided"
    assert (tmp_path / "run/PROCEDURA.md").is_file()


@pytest.mark.parametrize("unsafe", ["git", "symlink", "relative"])
def test_private_output_boundary(helper, tmp_path, unsafe):
    parent = tmp_path / "parent"
    parent.mkdir()
    if unsafe == "git":
        (parent / ".git").mkdir()
        target = parent / "run"
    elif unsafe == "symlink":
        target = tmp_path / "link/run"
        target.parent.symlink_to(parent, target_is_directory=True)
    else:
        target = Path("relative-run")
    with pytest.raises(ValueError, match="private path"):
        helper.start(target)
