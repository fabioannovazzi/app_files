from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_transcription_service_import_does_not_initialize_voice_http_api() -> None:
    repository = Path(__file__).resolve().parents[3]

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from modules.case_notes_voice.transcription_service import create_audio_transcription; assert callable(create_audio_transcription); assert 'modules.case_notes_voice.api' not in sys.modules",
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
