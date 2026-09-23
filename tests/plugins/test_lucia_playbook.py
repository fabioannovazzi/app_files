from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/lucia/scripts"))
from legal_documents import read_pack
from legal_playbook import main as playbook_main
from legal_playbook import (
    prepare_playbook,
    read_playbook_run,
    validate_playbook,
    write_editor,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("The firm editor must not connect to a server")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def instructions(tmp_path):
    value = json.loads(
        (ROOT / "plugins/lucia/assets/playbook-nda.json").read_text(encoding="utf-8")
    )
    value.update(id="studio-bianchi", name="NDA — Studio Bianchi", version=4)
    value["columns"] = ["Responsabilità", "Legge applicabile", "Non sollecitazione"]
    value["firm_positions"] = (
        "Segnalare una non sollecitazione superiore a 12 mesi come scostamento dalle istruzioni, non come invalidità legale."
    )
    path = tmp_path / "studio.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path, value


def evidence(tmp_path):
    source = tmp_path / "NDA.txt"
    source.write_text("Non sollecitazione: 24 mesi. Legge italiana.", encoding="utf-8")
    return source


def test_selected_firm_version_changes_the_prepared_review_and_survives_resume(
    tmp_path,
):
    path, value = instructions(tmp_path)
    source = evidence(tmp_path)
    run = tmp_path / "run"

    handoff = prepare_playbook(run, path, [source])

    pack = read_pack(run)
    review = json.loads((run / "review.json").read_text(encoding="utf-8"))
    assert pack["topics"] == value["columns"]
    assert [item["topic"] for item in review["items"]] == value["columns"]
    assert review["context"]["firm_instructions"] == value["firm_positions"]
    assert read_playbook_run(run)["playbook"]["version"] == 4
    assert (
        json.loads(handoff.read_text(encoding="utf-8"))["playbook"]["questions"]
        == value["questions"]
    )
    path.write_text("The external configuration is no longer this version.")
    assert read_playbook_run(run)["playbook"]["id"] == "studio-bianchi"


def test_a_changed_selected_snapshot_invalidates_existing_review(tmp_path):
    path, value = instructions(tmp_path)
    run = tmp_path / "run"
    prepare_playbook(run, path, [evidence(tmp_path)])
    value["firm_positions"] = "Changed after the run began"
    (run / "playbook.json").write_text(json.dumps(value))

    with pytest.raises(ValueError, match="firm workflow changed"):
        read_pack(run)


def test_template_label_does_not_silently_open_a_local_path(tmp_path):
    path, value = instructions(tmp_path)
    value["template_name"] = "/etc/passwd"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="actual file explicitly"):
        prepare_playbook(tmp_path / "run", path, [evidence(tmp_path)])
    assert not (tmp_path / "run").exists()


def test_explicit_template_is_snapshotted_once_and_identified_for_drafting(tmp_path):
    path, value = instructions(tmp_path)
    value["workflow"] = "redazione-da-modello"
    value["template_name"] = "Modello NDA del cliente"
    path.write_text(json.dumps(value))
    template = tmp_path / "modello.md"
    template.write_text("Accordo con {{cliente}}")
    run = tmp_path / "run"

    prepare_playbook(run, path, [evidence(tmp_path), template], template)

    assert len(read_pack(run)["sources"]) == 2
    assert read_playbook_run(run)["template_source_id"] == "D002"


@pytest.mark.parametrize(
    "patch",
    [
        {"name": " "},
        {"columns": ["Foro", " foro "]},
        {"columns": []},
        {"tracked_changes": True},
        {"execute": "shell command"},
        {"questions": [" "]},
    ],
)
def test_invalid_or_executable_configuration_is_rejected(tmp_path, patch):
    _, value = instructions(tmp_path)
    value.update(patch)
    with pytest.raises(ValueError):
        validate_playbook(value)


def test_editor_embeds_instruction_text_as_data_and_never_overwrites_an_existing_file(
    tmp_path,
):
    path, value = instructions(tmp_path)
    value["firm_positions"] = '</script><script>alert("injected")</script>'
    path.write_text(json.dumps(value))
    output = tmp_path / "editor.html"

    write_editor(output, path)

    html = output.read_text(encoding="utf-8")
    assert '</script><script>alert("injected")' not in html
    assert "\\u003c/script>" in html
    assert "connect-src 'none'" in html
    assert "data:font/ttf;base64," in html
    with pytest.raises(FileExistsError):
        write_editor(output, path)


def test_oversized_configuration_is_not_loaded(tmp_path):
    path = tmp_path / "oversize.json"
    path.write_bytes(b" " * 1_000_001)
    with pytest.raises(ValueError, match="1 MB"):
        write_editor(tmp_path / "editor.html", path)


def test_editor_cli_creates_a_working_standalone_file(tmp_path):
    target = tmp_path / "studio.html"
    assert playbook_main(["editor", "--out", str(target)]) == 0
    assert "__PLAYBOOK_DATA__" not in target.read_text(encoding="utf-8")


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_editor_labels_cover_every_language_and_workflow(language):
    labels = json.loads(
        (ROOT / "plugins/lucia/scripts/legal_playbook_labels.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(labels[language]) == set(labels["it"])
    assert len(labels[language]["workflows"]) == 5
    assert set(labels[language]["formats"]) == {"html", "xlsx", "docx"}
