"""Fresh checkouts obtain generated product archives before running consumers."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("host", ["codex", "cowork"])
def test_cold_start_reports_missing_builds_before_changing_environment(
    tmp_path, monkeypatch, capsys, host
):
    script = ROOT / "scripts/check_shared_runtime_cold_start.py"
    spec = importlib.util.spec_from_file_location("cold_start", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "scripts/cold_start.py"))
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["cold_start", "--output", "report.json", "--host-package", host],
    )
    monkeypatch.setenv("PATH", "unchanged")

    with pytest.raises(SystemExit) as error:
        module.main()

    assert error.value.code == 2
    assert "product-archives CI artifact" in capsys.readouterr().err
    assert module.os.environ["PATH"] == "unchanged"
    assert not (tmp_path / "report.json").exists()


def test_product_archives_are_ignored_and_not_tracked():
    tracked = subprocess.check_output(
        ["git", "ls-files", "plugin_packages/*/*.zip"], cwd=ROOT, text=True
    )
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "plugin_packages/vera/vera-plugin.zip"],
        cwd=ROOT,
        check=False,
    )

    assert tracked == ""
    assert ignored.returncode == 0


@pytest.mark.parametrize(
    ("workflow", "job"),
    [
        ("clara-cowork.yml", "packaged-reporting"),
        ("plugin-runtime.yml", "workflow-regressions"),
        ("plugin-runtime.yml", "vera-packaged-mcp"),
        ("shared-runtime-cold-start.yml", "cold-start"),
        ("teaching-kits.yml", "teaching-kits"),
        ("product-release-alignment.yml", "alignment"),
    ],
)
def test_direct_archive_consumers_wait_for_and_download_their_build(workflow, job):
    jobs = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text())["jobs"]
    consumer = jobs[job]

    assert consumer["needs"] == "product-archives"
    assert (
        jobs["product-archives"]["uses"]
        == "./.github/workflows/build-product-archives.yml"
    )
    assert any(
        step.get("uses") == "actions/download-artifact@v4"
        and step["with"] == {"name": "product-archives", "path": "plugin_packages"}
        for step in consumer["steps"]
    )
