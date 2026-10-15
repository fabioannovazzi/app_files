from __future__ import annotations

from pathlib import Path

import pytest

__all__: list[str] = []


@pytest.fixture(autouse=True)
def bilancio_script_imports(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Restore Bilancio imports after the repository clears plugin modules."""
    if "bilancio" in request.path.name:
        scripts = (
            Path(__file__).resolve().parents[2] / "plugins/bilancio-xbrl-it/scripts"
        )
        monkeypatch.syspath_prepend(str(scripts))
