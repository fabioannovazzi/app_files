"""Both hosts must receive the same product release, including public downloads."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/build_product_release.py"
SPEC = importlib.util.spec_from_file_location("product_release", SCRIPT)
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


@pytest.mark.skipif(shutil.which("make") is None, reason="Deployment requires make")
@pytest.mark.parametrize("product", release.PRODUCTS)
def test_public_codex_download_link_resolves_to_staged_release(
    tmp_path: Path, product: str
) -> None:
    for name in release.PRODUCTS:
        release_case(tmp_path, name)
    repo = SCRIPT.parents[1]
    page = repo / "static/shared/plugin-downloads/index.html"
    link = re.search(
        rf'href="([^"]+)" download="{product}-plugin.zip"', page.read_text()
    )
    assert link is not None
    expected = tmp_path / f"plugin_packages/{product}/{product}-plugin.zip"
    public = tmp_path / "static/shared/plugin-downloads" / link.group(1)

    subprocess.run(
        ["make", "-f", str(repo / "Makefile"), "stage-product-downloads"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    assert public.resolve().read_bytes() == expected.read_bytes()


@pytest.mark.skipif(shutil.which("make") is None, reason="Deployment requires make")
def test_missing_codex_build_preserves_existing_public_download(tmp_path: Path) -> None:
    for product in release.PRODUCTS:
        release_case(tmp_path, product)
    public = tmp_path / "static/shared/vera/downloads/vera-plugin.zip"
    public.write_bytes(b"previous deployed archive")
    (tmp_path / "plugin_packages/lucia/lucia-plugin.zip").unlink()

    result = subprocess.run(
        ["make", "-f", str(SCRIPT.parents[1] / "Makefile"), "stage-product-downloads"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
    )

    assert result.returncode != 0
    assert public.read_bytes() == b"previous deployed archive"


def write_archive(
    path: Path, product: str, version: str, content: str = "source"
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = (
        ".claude-plugin/plugin.json"
        if "cowork" in path.name or "claude" in path.name
        else ".codex-plugin/plugin.json"
    )
    with ZipFile(path, "w") as archive:
        archive.writestr(manifest, json.dumps({"name": product, "version": version}))
        archive.writestr("skill.md", content)


def release_case(root: Path, product: str) -> list[Path]:
    source = root / "plugins" / product / ".codex-plugin/plugin.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"version": "0.1.188"}))
    directory = root / "plugin_packages" / product
    paths = [
        directory / f"{product}-{suffix}.zip"
        for suffix in ("plugin", "chatgpt-upload", "claude-plugin")
    ]
    public = (
        root / "static/shared" / product / "downloads" / f"{product}-cowork-plugin.zip"
    )
    for path in paths:
        write_archive(path, product, "0.1.188")
    public.parent.mkdir(parents=True)
    public.write_bytes(paths[-1].read_bytes())
    return [*paths, public]


@pytest.mark.parametrize("product", release.PRODUCTS)
def test_accepts_matching_release_for_each_product(
    tmp_path: Path, product: str
) -> None:
    release_case(tmp_path, product)

    assert release.verify_versions(tmp_path, (product,)) == {product: "0.1.188"}


@pytest.mark.parametrize("artifact", [0, 1, 2, 3])
def test_rejects_stale_version_in_any_distribution(
    tmp_path: Path, artifact: int
) -> None:
    paths = release_case(tmp_path, "clara")
    write_archive(paths[artifact], "clara", "0.1.180")

    with pytest.raises(ValueError, match="canonical version is 0.1.188"):
        release.verify_versions(tmp_path, ("clara",))


def test_rejects_changed_public_content_even_with_matching_version(
    tmp_path: Path,
) -> None:
    paths = release_case(tmp_path, "clara")
    write_archive(paths[-1], "clara", "0.1.188", "outdated code")

    with pytest.raises(ValueError, match="public Cowork ZIP differs"):
        release.verify_versions(tmp_path, ("clara",))


def test_rejects_missing_distribution(tmp_path: Path) -> None:
    paths = release_case(tmp_path, "clara")
    paths[1].unlink()

    with pytest.raises(FileNotFoundError):
        release.verify_versions(tmp_path, ("clara",))


def test_check_explains_how_to_obtain_untracked_archives(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(release, "ROOT", tmp_path)

    result = release.main(["clara", "--check"])

    assert result == 1
    assert "python scripts/build_product_release.py clara" in caplog.text
    assert "product-archives CI artifact" in caplog.text


def test_default_command_checks_both_hosts_for_all_products(
    tmp_path, monkeypatch
) -> None:
    for product in release.PRODUCTS:
        release_case(tmp_path, product)
    commands = []
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(
        release.subprocess, "run", lambda command, **kwargs: commands.append(command)
    )

    assert release.main(["--check"]) == 0

    assert commands[0] == [
        release.sys.executable,
        "scripts/sync_reporting_runtime.py",
        "--check",
    ]
    assert commands[1:3] == [
        [release.sys.executable, "scripts/sync_privacy_runtime.py", "--check"],
        [release.sys.executable, "scripts/build_privacy_contracts.py", "--check"],
    ]
    assert commands[3] == [
        release.sys.executable,
        "scripts/check_shared_runtime_revision.py",
    ]
    assert all("--check" in command for command in commands[4:])
    assert any(
        "scripts/build_claude_plugin_zip.py" in command
        and all(product in command for product in release.PRODUCTS)
        for command in commands
    )
    assert sum("--chatgpt-upload" in command for command in commands) == 3
    assert [
        release.sys.executable,
        "scripts/build_antigravity_plugin.py",
        *release.PRODUCTS,
        "--check",
    ] in commands


def test_failed_builder_stops_release_before_other_distributions(
    tmp_path, monkeypatch
) -> None:
    calls = []

    def fail(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(release.subprocess, "run", fail)

    assert release.main(["clara"]) == 1
    assert len(calls) == 1


def test_command_fails_when_builders_leave_a_stale_public_zip(
    tmp_path, monkeypatch
) -> None:
    paths = release_case(tmp_path, "clara")
    write_archive(paths[-1], "clara", "0.1.180")
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release.subprocess, "run", lambda *args, **kwargs: None)

    assert release.main(["clara", "--check"]) == 1


def test_rejects_archive_without_product_manifest(tmp_path) -> None:
    paths = release_case(tmp_path, "clara")
    write_archive(paths[0], "another-plugin", "0.1.188")

    with pytest.raises(ValueError, match="expected one clara manifest"):
        release.verify_versions(tmp_path, ("clara",))
