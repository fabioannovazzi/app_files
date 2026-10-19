from __future__ import annotations

from pathlib import Path

import pytest

__all__: list[str] = []


@pytest.fixture(autouse=True)
def automatic_archive_reporting_environment(request, tmp_path, monkeypatch):
    """Keep automatic Archive identities, hooks and proof delivery inside each test."""
    monkeypatch.setenv("VERA_REPORTING_STATE_DIR", str(tmp_path / "reporting-state"))
    if {"archive_core", "archive_script_imports", "_load_customer_ledger"} & vars(
        request.module
    ).keys():
        monkeypatch.setenv(
            "MPARANZA_INCIDENT_STATE_DIR", str(tmp_path / "reporting-identity")
        )
        monkeypatch.setenv(
            "MPARANZA_INCIDENT_DEVICE_DIR", str(tmp_path / "reporting-device")
        )
        monkeypatch.setenv("MPARANZA_INCIDENT_DELIVERY", "local-only")


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
