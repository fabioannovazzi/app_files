"""Shared Archive navigation opens exact saved work without composing requests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import VERA_CLIENT_WORKFLOW_IDS

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
PIPELINES = tuple(
    sorted(
        set(VERA_CLIENT_WORKFLOW_IDS)
        | set(
            json.loads((ROOT / "plugins/vera/usage/pipelines.json").read_text())[
                "pipelines"
            ]
        )
        | set(json.loads((ROOT / "plugins/vera/ui/review-routes.json").read_text()))
    )
)
TITLE = "Proiezioni economiche 2027–2029"
OLD_TITLE = "Proiezioni economiche preliminari"
CHAT = "E26-01 · Ipotesi e revisione delle proiezioni"
CHAT_URL = "codex://threads/11111111-1111-4111-8111-111111111111"
SCOPE = {"client_id": "selected-client", "engagement_id": "selected-engagement"}


def fixture(workflow="business-planning"):
    """Use different primary files in successive versions, independent of pipeline."""
    versions = []
    for revision, title, primary in [(1, OLD_TITLE, "pdf"), (2, TITLE, "xlsx")]:
        versions.append(
            {
                "label": title,
                "revision": revision,
                "issued_at": "2026-11-14T10:00:00+00:00",
                "primary_format": primary,
                "formats": [
                    {
                        "format": ext,
                        "name": f"Proiezioni.{ext}",
                        "available": True,
                        "reference": {
                            "entry_key": "projections",
                            "revision": revision,
                            "format": ext,
                        },
                    }
                    for ext in ("md", "pdf", "xlsx")
                ],
            }
        )
    assignment = {
        **SCOPE,
        "workflow_id": workflow,
        "purpose": "Aggiornare le proiezioni economiche",
        "results": [],
        "deliverables": [{"label": TITLE, "versions": versions}],
        "documents": [
            {
                "name": "Dati consuntivi al 31 ottobre.csv",
                "reference": {"input_id": "source"},
            }
        ],
        "document_issues": [],
        "conversations": [{"title": CHAT, "url": CHAT_URL}],
        "work_links": [],
    }
    return {
        "catalogue": {
            **SCOPE,
            "mode": "studio-archive",
            "configured": True,
            "level": "runs",
            "client_label": "Eutekne",
            "engagement_label": "E26-01",
            "can_prepare": True,
            "works": [],
            "incarico": assignment,
        },
        "host_capabilities": {
            "experimental": {"openai/files": {}},
            "message": {"text": {}},
        },
        "document": {
            "name": "Proiezioni.xlsx",
            "path": "/synthetic/saved/Proiezioni.xlsx",
            "preview": None,
        },
    }


def run_ui(data, action=None):
    node = shutil.which("node")
    assert node, "Node is required for the Archive UI regression"
    result = subprocess.run(
        [
            node,
            str(ROOT / "tests/plugins/archive_run_list_ui.cjs"),
            os.environ.get(
                "VERA_TEST_UI_ASSET", str(ROOT / "plugins/vera/ui/workspace.js")
            ),
            "navigation",
        ],
        input=json.dumps({**data, "action": action}),
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("workflow", PIPELINES)
def test_every_pipeline_uses_document_titles_and_existing_chats(workflow):
    result = run_ui(fixture(workflow))
    assert TITLE in result["buttons"] and CHAT in result["buttons"]
    assert result["editableFields"] == 0
    assert result["calls"] == result["hostCalls"] == []
    for unwanted in (
        "Continua con Vera",
        "Usa per un nuovo incarico",
        "Apri MD",
        "Apri PDF",
        "Aggiungi documenti",
        "Aggiungi una nota",
        "Apri chat",
    ):
        assert unwanted not in result["buttons"]


@pytest.mark.parametrize(
    ("title", "revision", "extension"), [(TITLE, 2, "xlsx"), (OLD_TITLE, 1, "pdf")]
)
def test_title_opens_the_exact_declared_document_and_revision(
    title, revision, extension
):
    data = fixture()
    result = run_ui(data, title)
    assert result["calls"] == [
        {
            "name": "vera_incarico_document",
            "arguments": {
                **SCOPE,
                "reference": {
                    "entry_key": "projections",
                    "revision": revision,
                    "format": extension,
                },
            },
        }
    ]
    assert result["hostCalls"] == [
        {"method": "openai/files/open", "params": {"path": data["document"]["path"]}}
    ]
    assert result["editableFields"] == 0
    assert "Chiedi a Vera di questo documento" not in result["buttons"]
    assert "Altri file di questa versione" in result["text"]


def test_chat_title_opens_the_registered_conversation_without_sending_a_request():
    result = run_ui(fixture(), CHAT)
    assert result["calls"] == []
    assert result["hostCalls"] == [
        {"method": "ui/open-link", "params": {"url": CHAT_URL}}
    ]
    assert result["editableFields"] == 0


def test_unavailable_chat_leaves_documents_reachable_without_creating_a_composer():
    data = fixture()
    data["fail_navigation"] = True
    result = run_ui(data, CHAT)
    assert "non è accessibile" in result["status"]
    assert TITLE in result["buttons"]
    assert result["editableFields"] == 0
    assert result["calls"] == []


def test_no_file_open_capability_keeps_the_saved_text_readable():
    data = fixture()
    data["host_capabilities"] = {}
    data["document"]["preview"] = "Actual saved document content"
    result = run_ui(data, TITLE)
    assert "Actual saved document content" in result["text"]
    assert data["document"]["path"] in result["text"]
    assert result["hostCalls"] == []
    assert result["editableFields"] == 0


def test_missing_primary_file_does_not_silently_open_a_different_format():
    data = fixture()
    data["catalogue"]["incarico"]["deliverables"][0]["versions"][-1]["formats"][-1][
        "available"
    ] = False
    result = run_ui(data)
    assert TITLE in result["disabled"]
    assert "Il file non è disponibile" in result["text"]
    assert result["calls"] == result["hostCalls"] == []


@pytest.mark.parametrize("level", ["clients", "engagements"])
def test_archive_directory_has_no_workflow_launchers_or_chat_commands(level):
    data = {
        "catalogue": {
            "mode": "studio-archive",
            "configured": True,
            "level": level,
            "archive_location": "/synthetic/Studio",
            "clients": [],
            "engagements": [],
            "works": [],
        }
    }
    if level == "engagements":
        data["catalogue"].update(
            client_id="selected-client", client_label="Studio Rossi"
        )
    result = run_ui(data)
    assert result["buttons"] == (
        ["Cambia cartella"] if level == "clients" else ["← Clienti"]
    )
    assert result["calls"] == result["hostCalls"] == []
    assert result["editableFields"] == 0
    assert "Altri strumenti" not in result["text"]
    if level == "clients":
        assert "/synthetic/Studio" in result["text"]
        cancelled = run_ui(data, "Cambia cartella")
        assert cancelled["calls"] == [
            {"name": "vera_workspace_archive_setup", "arguments": {"confirmed": True}}
        ]
        assert cancelled["status"] == "Scelta annullata."
        assert "/synthetic/Studio" in cancelled["text"]


@pytest.mark.parametrize(
    ("view", "label", "empty"),
    [
        ("active", "In corso", "Nessuna lavorazione in corso."),
        ("history", "Storico", "Nessuna lavorazione nello storico."),
        ("hidden", "Nascosti", "Nessuna lavorazione nascosta."),
    ],
)
def test_empty_work_filter_keeps_controls_sources_and_results(view, label, empty):
    data = fixture()
    data["catalogue"].update(
        view=view, work_counts={"active": 0, "history": 1, "hidden": 0}
    )
    result = run_ui(data)
    assert all(
        name in result["buttons"] for name in ("In corso", "Storico", "Nascosti")
    )
    assert result["pressed"] == [label]
    assert empty in result["text"]
    assert TITLE in result["buttons"]
    assert "Dati consuntivi al 31 ottobre.csv" in result["buttons"]


def test_work_filters_select_distinct_saved_rows_and_keep_document_scope():
    data = fixture()
    pages = {}
    for view, status, name in [
        ("active", "prepared", "Preparazione attuale"),
        ("history", "completed", "Preparazione precedente"),
        ("hidden", "cancelled", "Tentativo nascosto"),
    ]:
        pages[view] = {
            **data["catalogue"],
            "view": view,
            "work_counts": {"active": 1, "history": 1, "hidden": 1},
            "works": [
                {
                    "work_ref": view,
                    "label": name,
                    "status": status,
                    "workflow": "quesito-legale-fiscale",
                    "created_at": "2026-11-14T12:00:00Z",
                    "inputs_valid": True,
                }
            ],
        }
    data.update(
        catalogue=pages["active"],
        catalogues=pages,
        actions=["Storico", "Nascosti", "In corso"],
    )
    result = run_ui(data)
    assert [call["arguments"]["view"] for call in result["calls"]] == [
        "history",
        "hidden",
        "active",
    ]
    assert result["pressed"] == ["In corso"]
    assert "Preparazione attuale" in result["text"]
    assert "Preparazione precedente" not in result["text"]
    assert "Tentativo nascosto" not in result["text"]
    assert "Preparato" in result["text"]
    assert "Dati consuntivi al 31 ottobre.csv" in result["buttons"]


def test_chat_can_open_another_incarico_in_an_already_loaded_panel():
    data = fixture()
    data["catalogue"]["navigation_id"] = "first-open"
    selected = {
        **data["catalogue"],
        "navigation_id": "second-open",
        "engagement_label": "E26-02",
    }
    data["notifications"] = [selected]
    result = run_ui(data)
    assert "E26-02" in result["text"]
    assert "E26-01" not in result["text"].replace(CHAT, "")
    assert result["calls"] == []


def test_replayed_initial_result_does_not_undo_navigation_but_new_open_does():
    data = fixture()
    initial = {**data["catalogue"], "navigation_id": "first-open"}
    selected = {**initial, "navigation_id": "second-open", "engagement_label": "E26-02"}
    data.update(
        catalogue=initial,
        notifications=[selected, initial, {**initial, "navigation_id": "third-open"}],
    )
    result = run_ui(data)
    assert "E26-02" in result["notificationViews"][0]
    assert "E26-02" in result["notificationViews"][1]
    assert "E26-01" in result["notificationViews"][2]
    assert "E26-02" not in result["notificationViews"][2]


def test_new_directory_result_changes_the_selected_archive_location():
    data = {
        "catalogue": {
            "mode": "studio-archive",
            "configured": True,
            "level": "clients",
            "works": [],
            "clients": [],
            "archive_location": "/original/Studio",
            "navigation_id": "first-open",
        }
    }
    data["notifications"] = [
        {
            **data["catalogue"],
            "archive_location": "/synthetic/Studio",
            "navigation_id": "second-open",
        }
    ]
    result = run_ui(data)
    assert "/synthetic/Studio" in result["text"]
    assert "/original/Studio" not in result["text"]
