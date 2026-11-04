"""Fresh checkouts obtain generated product archives before running consumers."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from zipfile import ZipFile

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


def test_alignment_restores_new_and_hidden_files_without_stale_checkout_files(tmp_path):
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/product-release-alignment.yml").read_text()
    )
    steps = workflow["jobs"]["alignment"]["steps"]
    restoration = next(
        step
        for step in steps
        if step.get("name")
        == "Restore generated Cowork directories from this commit's archives"
    )
    for product in ("vera", "clara", "lucia"):
        package = tmp_path / "plugin_packages" / product
        directory = package / "claude" / product
        directory.mkdir(parents=True)
        (directory / "removed-skill.md").write_text("stale checkout")
        with ZipFile(package / f"{product}-claude-plugin.zip", "w") as archive:
            archive.writestr(".claude-plugin/plugin.json", '{"version":"new"}')
            archive.writestr("skills/new/SKILL.md", "new skill from built artifact")

    subprocess.run(["bash", "-e", "-c", restoration["run"]], cwd=tmp_path, check=True)

    for product in ("vera", "clara", "lucia"):
        directory = tmp_path / "plugin_packages" / product / "claude" / product
        assert not (directory / "removed-skill.md").exists()
        assert (
            directory / ".claude-plugin/plugin.json"
        ).read_text() == '{"version":"new"}'
        assert (directory / "skills/new/SKILL.md").read_text() == (
            "new skill from built artifact"
        )


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
