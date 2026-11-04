"""Native matter review keeps exact-version decisions pending and app-only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/lucia/scripts"))
sys.path.insert(0, str(ROOT / "plugins/apertura-pratica/scripts"))
from apertura_pratica_core import (
    initialize_workspace,
    load_json,
    prepare_review,
    write_json,
)
from matter_mcp import MatterApp


def prepared(tmp_path):
    root = initialize_workspace(
        tmp_path / "matter",
        opening_mode="new_client_new_matter",
        client_reference="fictional-client",
        matter_reference="fictional-review",
        language="it",
    )
    prepare_review(root)
    return root


def submission(data, request_id="first-save"):
    item = data["review"]["items"][0]
    return {
        "session": data["session"],
        "request_id": request_id,
        "reviewer": "Revisore sintetico",
        "decisions": [
            {
                "item_id": item["id"],
                "action": "return",
                "note": "Richiedere le informazioni mancanti. Non accettare l’incarico.",
            }
        ],
    }


def test_native_matter_save_reopens_without_applying_or_duplicate_writes(tmp_path):
    root = prepared(tmp_path)
    app = MatterApp()
    launch = app.open(str(root))
    assert launch["structuredContent"] == {"status": "ready"}
    assert "fictional-client" not in json.dumps(launch["content"])
    data = launch["_meta"]["matter"]
    request = submission(data)
    saved = app.save(request)
    path = root / "pending_review_decisions.json"
    before = path.read_bytes()
    assert app.save(request) == saved
    assert path.read_bytes() == before
    reopened = MatterApp().open(str(root))["_meta"]["matter"]
    assert reopened["pending_review_status"] == "current"
    assert reopened["pending_review"]["decisions"] == request["decisions"]
    assert not (root / "applied_decisions.json").exists()
    with pytest.raises(ValueError, match="richiesta"):
        app.save({**request, "reviewer": "Another reviewer"})


def test_native_matter_refuses_stale_intake_or_another_panels_pending_save(tmp_path):
    root = prepared(tmp_path)
    app = MatterApp()
    first = app.open(str(root))["_meta"]["matter"]
    second = app.open(str(root))["_meta"]["matter"]
    app.save(submission(first))
    path = root / "pending_review_decisions.json"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="cambiate"):
        app.save(submission(second))
    assert path.read_bytes() == before
    intake = load_json(root / "matter_intake.json")
    intake["matter"]["objective"] = "Changed fictional scope"
    write_json(root / "matter_intake.json", intake)
    with pytest.raises(ValueError, match="corrente"):
        app.save(submission(first, "another-save"))
    assert path.read_bytes() == before


def test_native_matter_rejects_unknown_authority_and_has_no_browser_transport(tmp_path):
    root = prepared(tmp_path)
    app = MatterApp()
    data = app.open(str(root))["_meta"]["matter"]
    with pytest.raises(ValueError, match="Riapri"):
        app.save({**submission(data), "session": "unbound"})
    request = submission(data)
    request["decisions"][0]["item_id"] = "unknown-item"
    with pytest.raises(ValueError, match="unknown"):
        app.save(request)
    html = app.resource()["contents"][0]["text"]
    assert "fetch(" not in html
    assert "data:font/ttf;base64," in html
    assert "ui/initialize" in html
    assert "connect-src 'none'" in html
    assert app.tools[1]["_meta"]["ui"]["visibility"] == ["app"]
