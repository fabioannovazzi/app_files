from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "plugins" / "browser-automation"
SCRIPT = COMPONENT / "scripts" / "acceptance_fixture.py"


def test_acceptance_fixture_cli_binds_probes_and_closes() -> None:
    completed = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), "--self-check"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["schema_version"] == "browser-automation-acceptance-fixture/v2"
    assert result["status"] == "ready"
    assert result["origin"].startswith("http://127.0.0.1:")
    assert result["page_url"] == f'{result["origin"]}/'
    assert result["health_url"] == f'{result["origin"]}/healthz'
    assert result["process"] == {
        "heading": "Vera browser acceptance fixture",
        "client_code_label": "Client code",
        "client_code_submit_key": "Enter",
        "client_ready_text": "Client code accepted",
        "document_type_label": "Document type",
        "document_type_value": "Invoice",
        "reviewed_label": "Reviewed",
        "action_name": "Prepare package",
        "result_role": "status",
        "terminal_text": "Package ready: Invoice; reviewed yes",
        "download_name": "Download synthetic ZIP",
        "download_path": "/synthetic-package.zip",
        "download_entry_name": "vera-browser-acceptance.txt",
        "download_byte_length": 196,
        "download_sha256": (
            "da88429c87585cbfebd605aceb25a3d0fc06b08675dfe9abc7a9d229643313b5"
        ),
        "operation_contract": [
            "goto",
            "wait_for",
            "fill",
            "press",
            "select",
            "set_checked",
            "click",
            "extract",
            "download",
        ],
    }


def test_acceptance_instructions_use_shipped_fixture_and_bounded_timeout_check() -> (
    None
):
    module_skill = (COMPONENT / "skills" / "browser-automation" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    wrapper_skill = (
        ROOT / "plugins" / "vera" / "skills" / "browser-automation" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "scripts/acceptance_fixture.py --port 0" in module_skill
    assert "exactly equals `page_url`" in module_skill
    assert "local_fixture_navigation_failed" in module_skill
    assert "do not improvise a local server" in wrapper_skill
