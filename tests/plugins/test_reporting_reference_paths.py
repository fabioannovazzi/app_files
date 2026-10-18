"""Reporting guidance must resolve inside the actual installed host package."""

from __future__ import annotations

import importlib
import json
import re
import runpy
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("directories", [[], ["vera", "mparanza-vera"]])
def test_reference_resolution_rejects_missing_or_ambiguous_installation(
    tmp_path, directories
):
    manifest = tmp_path / ".codex-plugin/plugin.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"name": "vera"}), encoding="utf-8")
    for directory in directories:
        reference = tmp_path / "skills" / directory / "references/workflow-usage.md"
        reference.parent.mkdir(parents=True)
        reference.write_text("Synthetic reference", encoding="utf-8")
    resolve = runpy.run_path(
        str(ROOT / "plugins/_shared/reporting-runtime/reporting_product.py")
    )["installed_reference_path"]

    with pytest.raises(ValueError, match="missing or ambiguous"):
        resolve("workflow-usage.md", tmp_path)


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("host", ["codex", "chatgpt", "cowork", "antigravity"])
def test_packaged_startup_guidance_points_to_installed_references(
    product, host, tmp_path, monkeypatch
):
    archives = {
        "codex": f"plugin_packages/{product}/{product}-plugin.zip",
        "chatgpt": f"plugin_packages/{product}/{product}-chatgpt-upload.zip",
        "cowork": f"plugin_packages/{product}/{product}-claude-plugin.zip",
        "antigravity": f"static/shared/{product}/downloads/{product}-antigravity-plugin.zip",
    }
    installation = tmp_path / "installation"
    with ZipFile(ROOT / archives[host]) as archive:
        archive.extractall(installation)
    (usage_path,) = installation.rglob("scripts/workflow_usage.py")
    product_root = usage_path.parent.parent
    monkeypatch.syspath_prepend(str(usage_path.parent))
    for name in ("operational_incidents", "workflow_usage", "reporting_product"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    incidents = importlib.import_module("operational_incidents")
    # The package's actual guidance runs with isolated, synthetic pending state.
    # Never access a real installation identity or send a report from this test.
    monkeypatch.setenv("MPARANZA_INCIDENT_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(
        incidents,
        "local_context",
        lambda: {
            "credentials": {},
            "client_status": {},
            "pending_diagnostics": [],
            "outbox_path": str(tmp_path / "outbox"),
        },
    )

    guidance = incidents.startup_context()

    references = re.findall(r"skills/[^\s]+/references/[\w-]+\.md", guidance)
    assert len(references) == 2, guidance
    assert {Path(path).name for path in references} == {
        "workflow-usage.md",
        "incident-recovery.md",
    }
    assert all((product_root / path).is_file() for path in references), references
    assert all("//" not in path for path in references), references
    assert f"{product}_incident_register" in guidance
