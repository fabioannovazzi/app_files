from __future__ import annotations

import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_setup_script_is_executable() -> None:
    mode = (ROOT / "scripts" / "setup.sh").stat().st_mode

    assert mode & stat.S_IXUSR


def test_dataframe_check_script_is_executable() -> None:
    mode = (ROOT / "scripts" / "check_len_df.sh").stat().st_mode

    assert mode & stat.S_IXUSR
