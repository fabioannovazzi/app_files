from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
VERA_ROOT = ROOT / "plugins" / "vera"
VALIDATOR = (
    VERA_ROOT
    / "skills"
    / "privacy-surface-review"
    / "scripts"
    / "validate_privacy_surfaces.py"
)


def _validator_module():
    spec = importlib.util.spec_from_file_location("vera_privacy_validator", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vera_privacy_register_covers_current_workstreams_and_is_fresh() -> None:
    validator = _validator_module()

    errors = validator.validate_privacy_surfaces(VERA_ROOT)

    assert errors == []


def test_vera_privacy_manifests_match_the_published_schema() -> None:
    schema = json.loads(
        (VERA_ROOT / "privacy" / "privacy-surface.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = jsonschema.Draft202012Validator(schema)
    manifests = sorted((VERA_ROOT / "privacy" / "workstreams").glob("*.json"))

    errors = {
        manifest.name: [
            error.message
            for error in validator.iter_errors(
                json.loads(manifest.read_text(encoding="utf-8"))
            )
        ]
        for manifest in manifests
    }

    assert errors
    assert all(not manifest_errors for manifest_errors in errors.values()), errors


def test_vera_privacy_validator_reports_unregistered_manifest_gap(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    vera_root = tmp_path / "plugins" / "vera"
    shutil.copytree(VERA_ROOT, vera_root)
    missing = vera_root / "privacy" / "workstreams" / "check-entries.json"
    missing.unlink()

    errors = validator.validate_privacy_surfaces(vera_root)

    assert "check-entries: registered workstream has no privacy manifest" in errors


def test_vera_privacy_validator_detects_changed_governed_source(
    tmp_path: Path,
) -> None:
    plugins_root = tmp_path / "plugins"
    vera_root = plugins_root / "vera"
    component_root = plugins_root / "prompt-optimizer"
    shutil.copytree(VERA_ROOT, vera_root)
    shutil.copytree(ROOT / "plugins" / "prompt-optimizer", component_root)
    components = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    components["plugins"] = ["prompt-optimizer"]
    components["workflow_roles"] = {}
    (vera_root / "components.json").write_text(
        json.dumps(components, indent=2) + "\n", encoding="utf-8"
    )
    manifest_dir = vera_root / "privacy" / "workstreams"
    for manifest in manifest_dir.glob("*.json"):
        if manifest.stem != "prompt-optimizer":
            manifest.unlink()
    validator_path = (
        vera_root
        / "skills"
        / "privacy-surface-review"
        / "scripts"
        / "validate_privacy_surfaces.py"
    )
    refreshed = subprocess.run(
        [sys.executable, str(validator_path), "--refresh", "prompt-optimizer"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
    governed_skill = component_root / "skills" / "prompt-optimizer" / "SKILL.md"
    governed_skill.write_text(
        governed_skill.read_text(encoding="utf-8") + "\nMaterial workflow change.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(validator_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "prompt-optimizer: privacy review is stale" in result.stdout


def test_vera_privacy_validator_rejects_confirmation_flag_mismatch(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    vera_root = tmp_path / "plugins" / "vera"
    shutil.copytree(VERA_ROOT, vera_root)
    manifest_path = vera_root / "privacy" / "workstreams" / "prompt-optimizer.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["commercialista_notice"]["requires_confirmation"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    errors = validator.validate_privacy_surfaces(vera_root)

    assert "prompt-optimizer: notice confirmation flag disagrees with level" in errors
