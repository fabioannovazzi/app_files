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
    assert result["schema_version"] == "browser-automation-acceptance-fixture/v1"
    assert result["status"] == "ready"
    assert result["origin"].startswith("http://127.0.0.1:")
    assert result["page_url"] == f'{result["origin"]}/'
    assert result["health_url"] == f'{result["origin"]}/healthz'
    assert result["process"] == {
        "heading": "Vera browser acceptance fixture",
        "reference_label": "Reference",
        "archive_label": "Include archive",
        "action_name": "Prepare",
        "result_role": "status",
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
