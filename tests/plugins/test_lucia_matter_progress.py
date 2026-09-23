from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/lucia/scripts"))
from legal_documents import prepare
from legal_matter import initialize, render, save, status


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Local matter state must not connect to a server")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def matter(tmp_path):
    source = tmp_path / "fattura.txt"
    source.write_text("Fattura 7: EUR 1000.\n", encoding="utf-8")
    run = tmp_path / "pratica"
    prepare(run, [source], "revisione-documentale", ["Credito"])
    initialize(run, "recupero-crediti", "Preparare la pratica di recupero del credito")
    state = json.loads((run / "matter.json").read_text(encoding="utf-8"))
    state["stages"] = [
        {
            "id": "evidence",
            "label": "Prove",
            "status": "pending",
            "note": "",
            "outputs": [],
        },
        {
            "id": "interest",
            "label": "Interessi",
            "status": "pending",
            "note": "",
            "outputs": [],
        },
    ]
    state["questions"] = [
        {
            "id": "Q1",
            "question": "Quando è scaduto il pagamento?",
            "reason": "Serve il termine iniziale per il calcolo richiesto.",
            "blocks": ["interest"],
            "status": "open",
            "answer": "",
            "citations": [],
        }
    ]
    return run, state


def proposal(run, state):
    path = run / "proposed-state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def test_unanswered_question_only_blocks_its_dependent_stage(tmp_path):
    run, state = matter(tmp_path)
    save(run, proposal(run, state), 0)
    result = status(run)
    assert result["blocked_stages"] == {"interest": ["Q1"]}
    assert result["ready_stages"] == ["evidence"]
    assert result["work_products_recorded"] is False


def test_answered_question_resumes_saved_work_and_retains_history(tmp_path):
    run, state = matter(tmp_path)
    save(run, proposal(run, state), 0)
    reopened = json.loads((run / "matter.json").read_text(encoding="utf-8"))
    reopened["questions"][0].update(
        status="answered",
        answer="Il cliente conferma il 20 settembre 2026; fonte contrattuale da verificare.",
    )
    save(run, proposal(run, reopened), 1)
    assert status(run)["ready_stages"] == ["evidence", "interest"]
    assert (
        json.loads(
            (run / "matter-history/revision-0001.json").read_text(encoding="utf-8")
        )["questions"][0]["status"]
        == "open"
    )


def test_blocked_stage_cannot_be_marked_done_even_if_file_exists(tmp_path):
    run, state = matter(tmp_path)
    (run / "interessi.md").write_text("Risultato proposto senza decorrenza")
    state["stages"][1].update(
        status="done", outputs=["interessi.md"], note="Calcolo eseguito"
    )
    with pytest.raises(ValueError, match="unanswered"):
        save(run, proposal(run, state), 0)
    assert status(run)["revision"] == 0


@pytest.mark.parametrize("change", ["edit", "delete"])
def test_saved_output_drift_is_visible_on_reopen(tmp_path, change):
    run, state = matter(tmp_path)
    output = run / "prove.md"
    output.write_text("Fattura 7 presente; consegna non documentata.")
    state["stages"][0].update(
        status="done", note="Matrice prove salvata", outputs=["prove.md"]
    )
    save(run, proposal(run, state), 0)
    if change == "edit":
        output.write_text("Alterato")
    else:
        output.unlink()
    result = status(run)
    assert result["changed_outputs"] == ["prove.md"]
    assert result["work_products_recorded"] is False


def test_stale_update_is_rejected_without_overwriting_answers(tmp_path):
    run, state = matter(tmp_path)
    update = proposal(run, state)
    save(run, update, 0)
    with pytest.raises(ValueError, match="changed since"):
        save(run, update, 0)
    assert status(run)["revision"] == 1


def test_matter_review_html_shows_questions_and_results(tmp_path):
    run, state = matter(tmp_path)
    save(run, proposal(run, state), 0)
    output = render(run).read_text(encoding="utf-8")
    assert "Quando è scaduto il pagamento?" in output
    assert "Serve il termine iniziale" in output
    assert "Passaggi interessati" in output


def test_output_path_cannot_escape_selected_matter(tmp_path):
    run, state = matter(tmp_path)
    state["stages"][0].update(
        status="done", note="Registrato", outputs=["../fattura.txt"]
    )
    with pytest.raises(ValueError, match="selected run"):
        save(run, proposal(run, state), 0)


def test_a_question_answer_does_not_fabricate_evidence(tmp_path):
    run, state = matter(tmp_path)
    state["questions"][0].update(
        status="answered",
        answer="Scadenza 20 settembre",
        citations=[
            {"source_id": "D001", "anchor": "line:1", "quote": "Scadenza 20 settembre"}
        ],
    )
    with pytest.raises(ValueError, match="does not match"):
        save(run, proposal(run, state), 0)


def test_whitespace_does_not_count_as_evidence(tmp_path):
    run, state = matter(tmp_path)
    state["questions"][0]["citations"] = [
        {"source_id": "D001", "anchor": "unknown", "quote": " \t "}
    ]
    with pytest.raises(ValueError, match="does not match"):
        save(run, proposal(run, state), 0)


def test_retry_after_interrupted_commit_reuses_identical_history(tmp_path):
    run, state = matter(tmp_path)
    history = run / "matter-history"
    history.mkdir()
    (history / "revision-0000.json").write_bytes((run / "matter.json").read_bytes())

    save(run, proposal(run, state), 0)

    assert status(run)["revision"] == 1
    assert not (run / "matter-save.lock").exists()


def test_conflicting_history_cannot_be_overwritten(tmp_path):
    run, state = matter(tmp_path)
    history = run / "matter-history"
    history.mkdir()
    snapshot = history / "revision-0000.json"
    snapshot.write_text('{"revision":999}')
    with pytest.raises(ValueError, match="history differs"):
        save(run, proposal(run, state), 0)
    assert snapshot.read_text(encoding="utf-8") == '{"revision":999}'
    assert status(run)["revision"] == 0


def test_parallel_save_lock_preserves_existing_work(tmp_path):
    run, state = matter(tmp_path)
    lock = run / "matter-save.lock"
    lock.write_text("another save")
    with pytest.raises(ValueError, match="Another save"):
        save(run, proposal(run, state), 0)
    assert lock.read_text(encoding="utf-8") == "another save"
    assert status(run)["revision"] == 0


def test_failed_atomic_commit_leaves_current_state_and_allows_retry(
    tmp_path, monkeypatch
):
    run, state = matter(tmp_path)
    update = proposal(run, state)

    def unavailable(*args, **kwargs):
        raise OSError("Simulated interrupted commit")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", unavailable)
        with pytest.raises(OSError, match="interrupted"):
            save(run, update, 0)
    assert status(run)["revision"] == 0
    assert not (run / "matter-save.lock").exists()
    assert not list(run.glob("matter-next-*"))
    save(run, update, 0)
    assert status(run)["revision"] == 1
