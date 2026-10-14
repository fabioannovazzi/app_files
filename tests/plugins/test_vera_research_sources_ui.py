"""Native subscription UI interactions over a fictional host and actual register."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.plugins.test_bilancio_native_workspace import NODE

__all__ = []
ROOT = Path(__file__).resolve().parents[2]


def ui(tmp_path, program, options=None):
    code = (
        "const {fixture}=require(process.argv[1]);const ui=fixture(process.argv[2],JSON.parse(process.argv[3]));(async()=>{"
        + program
        + "})().catch(e=>{process.stderr.write(e.message);process.exitCode=1;});"
    )
    completed = subprocess.run(
        [
            NODE,
            "-e",
            code,
            str(Path(__file__).with_name("research_sources_ui_fixture.cjs")),
            str(ROOT / "plugins/vera"),
            json.dumps(options or {}),
        ],
        env={**os.environ, "MPARANZA_RESEARCH_HOME": str(tmp_path / "profile")},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_connect_saves_choice_and_requests_real_host_check_without_claiming_success(
    tmp_path,
):
    result = ui(
        tmp_path,
        "await ui.panel.open();await ui.button('Collega').action();process.stdout.write(JSON.stringify({text:ui.text(),calls:ui.calls,messages:ui.messages}));",
    )
    assert "Verifica richiesta alla chat" in result["text"]
    assert "Documento consultato" not in result["text"]
    assert [c["name"] for c in result["calls"]] == [
        "vera_research_sources_state",
        "vera_research_sources_configure",
        "vera_research_sources_request",
    ]
    assert "Eutekne" in result["messages"][0]


def test_disconnect_removes_saved_permission_and_pending_access_check(tmp_path):
    result = ui(
        tmp_path,
        "await ui.panel.open();await ui.button('Collega').action();await ui.button('Scollega').action();process.stdout.write(JSON.stringify({text:ui.text(),state:ui.server.call('vera_research_sources_state').structuredContent}));",
    )
    assert result["state"]["providers"][0]["enabled"] is False
    assert result["state"]["providers"][0]["pending"] is None
    assert "Non collegato" in result["text"]


def test_unavailable_message_capability_keeps_authorisation_and_explains_chat_fallback(
    tmp_path,
):
    result = ui(
        tmp_path,
        "await ui.panel.open();await ui.button('Collega').action();process.stdout.write(JSON.stringify({text:ui.text(),status:ui.status()}));",
        {"message": False},
    )
    assert "Chiedi a Vera" in result["status"]
    assert "Verifica richiesta" in result["text"]


@pytest.mark.parametrize(
    ("language", "title", "data_title"),
    [
        ("it", "Fonti di ricerca", "Quali dati arrivano al modello"),
        ("en", "Research sources", "What data reaches the model"),
        ("fr", "Sources de recherche", "Quelles données parviennent au modèle"),
        ("de", "Recherchequellen", "Welche Daten das Modell erreichen"),
        ("es", "Fuentes de investigación", "Qué datos llegan al modelo"),
    ],
)
def test_localized_panel_ends_with_its_actual_model_data_boundary(
    tmp_path, language, title, data_title
):
    result = ui(
        tmp_path,
        "await ui.panel.open();process.stdout.write(JSON.stringify({text:ui.text(),tail:ui.elements().at(-2).textContent}));",
        {"language": language},
    )
    assert title in result["text"]
    assert data_title in result["text"]
    assert result["tail"] == data_title


def test_untrusted_source_title_remains_literal_text_and_old_payload_cannot_restore_permission(
    tmp_path,
):
    result = ui(
        tmp_path,
        "await ui.panel.open();await ui.button('Collega').action();const old=ui.server.call('vera_research_sources_state').structuredContent;old.providers[0].last_check={result:'document_read',observed_at:'fictional date',source_title:'<img src=x onerror=attack()>',basis:'host_observation_reported'};old.providers[0].pending=null;ui.panel.render(old);const safe=ui.text(),tags=ui.elements().map(e=>e.tagName);await ui.button('Scollega').action();ui.panel.render(old);process.stdout.write(JSON.stringify({safe,tags,text:ui.text()}));",
    )
    assert "<img src=x onerror=attack()>" in result["safe"]
    assert "IMG" not in result["tags"]
    assert "Documento consultato" not in result["text"]
