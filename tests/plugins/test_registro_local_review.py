"""Real local transport, native persistence and cross-origin/lifecycle guards."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from tests.plugins.test_registro_imprese_sari_plugin import (
    PLUGIN_ROOT,
    _load_archive_core,
    _node_or_skip,
    _prepare_case,
)


def test_local_review_native_save_apply_reload_and_archived_guard(tmp_path: Path):
    output, _ = _prepare_case(tmp_path)
    process = subprocess.Popen(
        [
            _node_or_skip(),
            str(PLUGIN_ROOT / "mcp/server.cjs"),
            "--http",
            "--client-engagement",
            str(output.parent / "context.json"),
        ],
        env={**os.environ, "VERA_CLIENT_WORKFLOW_PYTHON": sys.executable},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout
    try:
        url = json.loads(process.stdout.readline())["url"]
        origin = url.rsplit("/", 2)[0]

        def get_payload():
            with urllib.request.urlopen(url, timeout=10) as response:
                assert response.headers["X-Content-Type-Options"] == "nosniff"
                html = response.read().decode()
            matched = re.search(
                r"window.openai=\{toolOutput:(.*?),callTool:async", html
            )
            assert matched
            return json.loads(matched[1])

        payload = get_payload()
        assert payload["local_read_only"] is False
        item = next(
            row
            for row in payload["review_payload"]["items"]
            if "request_more_documents" in row["allowed_actions"]
        )
        arguments = {
            "persistence_token": payload["persistence_token"],
            "decisions": [
                {
                    "item_id": item["id"],
                    "action": "request_more_documents",
                    "requested_documents": ["Synthetic fixture document request"],
                    "reviewer_note": "Automated transport regression, not human approval",
                }
            ],
        }

        def post(name, *, request_origin=origin):
            request = urllib.request.Request(
                url + "call",
                data=json.dumps({"name": name, "arguments": arguments}).encode(),
                headers={"Content-Type": "application/json", "Origin": request_origin},
            )
            try:
                response = urllib.request.urlopen(request, timeout=10)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.status, json.loads(response.read())

        save = "save_registro_imprese_sari_decisions"
        apply = "apply_registro_imprese_sari_decisions"
        assert post(save, request_origin="https://unrelated.example")[0] == 403
        assert post("unrelated_tool")[0] == 409
        assert post(save)[1]["persisted"] is True
        assert post(apply)[1]["ready_to_file"] is False
        refreshed = get_payload()
        assert (
            refreshed["ui_decisions"]["decisions"][0]["action"]
            == "request_more_documents"
        )
        assert post(save)[0] == 409  # The old tab token cannot silently overwrite.
        arguments["persistence_token"] = refreshed["persistence_token"]
        assert post(save)[0] == 200

        # Seal the real fixture through the archive lifecycle before reopening.
        context_path = output.parent / "context.json"
        context = json.loads(context_path.read_text())
        ledger = _load_archive_core().ledger
        from tests.model_data_helpers import write_no_model_report

        write_no_model_report(output, context["workflow_id"], context["run_id"])
        ledger.finalize_run(
            context_path.parents[5],
            context["engagement_id"],
            context["run_id"],
            [
                {
                    "artifact_id": f"artifact_{i}",
                    "path": p.name,
                    "purpose": "Native review regression evidence",
                    "audience": "review",
                    "media_type": "application/octet-stream",
                }
                for i, p in enumerate(sorted(output.iterdir()))
                if p.is_file()
            ],
        )
        ledger.complete_run(
            context_path.parents[5], context["engagement_id"], context["run_id"]
        )
        before = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
        archived = get_payload()
        assert archived["local_read_only"] is True
        arguments["persistence_token"] = archived["persistence_token"]
        assert post(save)[0] == 409
        assert post(apply)[0] == 409
        assert before == {
            p.name: p.read_bytes() for p in output.iterdir() if p.is_file()
        }
    finally:
        process.terminate()
        process.wait(timeout=10)
