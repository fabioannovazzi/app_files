from __future__ import annotations

import json
import socket
import subprocess
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
)
from method_mcp import MethodApp


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/lucia/scripts"))

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


def test_native_method_only_returns_selected_text_to_the_app(tmp_path):
    path, value = instructions(tmp_path)
    value["firm_positions"] = '</script><script>alert("injected")</script>'
    path.write_text(json.dumps(value))
    app = MethodApp()
    result = app.open({"directory": str(tmp_path), "filename": path.name})
    assert value["firm_positions"] not in json.dumps(result["content"])
    assert result["structuredContent"] == {"status": "ready"}
    assert result["_meta"]["method"]["value"] == value
    html = app.resource()["contents"][0]["text"]
    assert value["firm_positions"] not in html
    assert "connect-src 'none'" in html
    assert "data:font/ttf;base64," in html
    assert "URL.createObjectURL" not in html


def test_oversized_configuration_is_not_loaded(tmp_path):
    path = tmp_path / "oversize.json"
    path.write_bytes(b" " * 1_000_001)
    with pytest.raises(ValueError, match="1 MB"):
        MethodApp().open({"directory": str(tmp_path), "filename": path.name})


def test_standalone_editor_cli_is_retired(tmp_path):
    with pytest.raises(SystemExit):
        playbook_main(["editor", "--out", str(tmp_path / "studio.html")])
    assert not (tmp_path / "studio.html").exists()


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


def save_request(data, value, request_id="save-one"):
    return {
        "session": data["session"],
        "revision": data["revision"],
        "request_id": request_id,
        "value": value,
    }


def test_native_save_preserves_old_version_reopens_and_retries_once(tmp_path):
    path, value = instructions(tmp_path)
    before = path.read_bytes()
    app = MethodApp()
    data = app.open({"directory": str(tmp_path), "filename": path.name})["_meta"][
        "method"
    ]
    changed = {**value, "purpose": "Review the confidentiality period"}
    request = save_request(data, changed)
    saved = app.save(request)
    assert saved == app.save(request)
    assert path.read_bytes() == before
    assert saved["_meta"]["method"]["value"]["version"] == 5
    reopened = MethodApp().open(
        {"directory": str(tmp_path), "filename": saved["_meta"]["method"]["filename"]}
    )
    assert reopened["_meta"]["method"]["value"]["purpose"] == changed["purpose"]
    with pytest.raises(ValueError, match="richiesta"):
        app.save({**request, "value": value})
    with pytest.raises(ValueError, match="versione"):
        app.save({**request, "request_id": "different-request"})
    assert len(list(tmp_path.glob("studio-bianchi-v*.json"))) == 1


def test_native_save_refuses_external_changes_and_file_collisions(tmp_path):
    path, value = instructions(tmp_path)
    app = MethodApp()
    data = app.open({"directory": str(tmp_path), "filename": path.name})["_meta"][
        "method"
    ]
    changed = {**value, "purpose": "new purpose"}
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="cambiato"):
        app.save(save_request(data, changed))
    data = app.open({"directory": str(tmp_path), "filename": path.name})["_meta"][
        "method"
    ]
    collision = tmp_path / "studio-bianchi-v5.json"
    collision.write_text("another version")
    with pytest.raises(FileExistsError):
        app.save(save_request(data, {**changed, "purpose": "another purpose"}))
    assert collision.read_text() == "another version"


def test_native_method_folder_scope_is_not_supplied_by_form_values(tmp_path):
    path, value = instructions(tmp_path)
    app = MethodApp()
    with pytest.raises(ValueError, match="cartella"):
        app.open({"directory": str(tmp_path), "filename": "../elsewhere.json"})
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="cartella"):
        app.open({"directory": str(tmp_path), "filename": link.name})
    data = app.open({"directory": str(tmp_path), "filename": path.name})["_meta"][
        "method"
    ]
    with pytest.raises(ValueError, match="Riapri"):
        app.save(save_request({**data, "session": "unbound"}, value))
    bad = {**value, "id": "../escape"}
    with pytest.raises(ValueError):
        app.save(save_request(data, bad))
    source = app.import_value(
        {"session": data["session"], "value": {**value, "id": "imported-method"}}
    )["_meta"]["method"]
    saved = app.save(save_request(source, source["value"]))
    assert saved["_meta"]["method"]["filename"] == "imported-method-v4.json"
    copy = {
        **source["value"],
        "id": "copy-method",
        "version": 1,
        "derived_from": {"id": "imported-method", "version": 4},
    }
    copied = app.save(save_request(saved["_meta"]["method"], copy, "copy"))
    assert copied["_meta"]["method"]["value"]["derived_from"] == copy["derived_from"]
    assert (tmp_path / "imported-method-v4.json").exists()


def test_native_app_tools_use_bound_app_only_save_and_import():
    app = MethodApp()
    assert (
        app.tools[0]["_meta"]["ui"]["resourceUri"] == "ui://lucia/firm-method-v1.html"
    )
    assert all(tool["_meta"]["ui"]["visibility"] == ["app"] for tool in app.tools[1:])
    assert not any(
        "directory" in tool["inputSchema"]["properties"] for tool in app.tools[1:]
    )


def test_method_editor_does_not_load_document_processing_dependencies():
    """Opening a saved method needs only its schema, not Word/PDF processors."""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); import method_mcp; assert 'legal_documents' not in sys.modules; assert 'legal_matter' not in sys.modules",
            str(ROOT / "plugins/lucia/scripts"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
