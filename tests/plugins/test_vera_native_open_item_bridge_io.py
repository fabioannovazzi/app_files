"""Native Open-item bridges keep dependency diagnostics out of JSON responses."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

__all__ = []
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "bridge, arguments, expected",
    [
        (
            "native_open_items_intake_bridge.py",
            {"operation": "contract"},
            {"roles": ["open_items"], "adapters": ["csv"], "implementation": []},
        ),
        (
            "native_open_item_bridge.py",
            {"operation": "read", "output_dir": "fictional-output"},
            {"status": "ready"},
        ),
    ],
)
def test_native_bridge_keeps_import_and_execution_diagnostics_on_stderr(
    tmp_path, bridge, arguments, expected
):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "raw_input_runner.py").write_text(
        "import sys\nsys.stdout.write('dependency import warning\\n')\n"
        "SUPPORTED_SOURCE_ROLES = ['open_items']\n"
        "SUPPORTED_ADAPTER_FAMILIES = ['csv']\n"
    )
    (scripts / "audit_assurance.py").write_text(
        "import sys\ndef build_implementation_receipts(root):\n"
        "    sys.stdout.write('execution diagnostic\\n')\n"
        "    return []\n"
        "def validate_assurance_run(output):\n    return {}\n"
    )
    (scripts / "review_server.py").write_text(
        "import sys\nsys.stdout.write('dependency import warning\\n')\n"
        "def build_session_payload(output, *, for_display):\n"
        "    sys.stdout.write('execution diagnostic\\n')\n"
        "    return {'status': 'ready'}\n"
    )

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(ROOT / "plugins/vera/scripts" / bridge),
            str(tmp_path),
        ],
        input=json.dumps(arguments),
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )

    assert json.loads(result.stdout) == expected
    assert result.stderr == "dependency import warning\nexecution diagnostic\n"
