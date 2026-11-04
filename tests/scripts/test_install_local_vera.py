"""Local update transactions select verified sources and recover failed switches."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from tests.plugins.test_live_plugin_runtime import package, write_index

ROOT = Path(__file__).resolve().parents[2]


def installer():
    spec = importlib.util.spec_from_file_location(
        "install_local_vera_test", ROOT / "scripts/install_local_vera.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def distribution(tmp_path, version="1", product="vera"):
    root = tmp_path / f"distribution-{version}"
    (root / "plugins").mkdir(parents=True)
    original = package(tmp_path, version)
    manifest = original / ".codex-plugin/plugin.json"
    manifest.write_text(json.dumps({"name": product, "version": version}))
    write_index(original)
    original.rename(root / f"plugins/{product}")
    catalog = root / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps(
            {
                "name": f"mp-{product}",
                "plugins": [
                    {
                        "name": product,
                        "source": {"source": "local", "path": f"./plugins/{product}"},
                    }
                ],
            }
        )
    )
    return root


class Host:
    def __init__(self, source=None, fail=False, stale=False, product="vera"):
        self.product = product
        self.source = source
        self.previous = source
        self.fail = fail
        self.stale = stale
        self.calls = []
        self.version = None

    def __call__(self, args):
        self.calls.append(args)
        if args == ["marketplace", "list"]:
            return {
                "marketplaces": (
                    []
                    if self.source is None
                    else [
                        {
                            "name": f"mp-{self.product}",
                            "marketplaceSource": {
                                "sourceType": "local",
                                "source": str(self.source),
                            },
                        }
                    ]
                )
            }
        if args[:2] == ["marketplace", "remove"]:
            self.source = None
        elif args[:2] == ["marketplace", "add"]:
            self.source = self.previous if self.stale else Path(args[2])
        elif args[0] == "add":
            if self.fail and self.source != self.previous:
                raise subprocess.CalledProcessError(1, "fixture install failure")
            self.version = json.loads(
                (
                    self.source / f"plugins/{self.product}/.codex-plugin/plugin.json"
                ).read_text()
            )["version"]
        elif args == ["list"]:
            return {
                "installed": [
                    {
                        "name": self.product,
                        "pluginId": f"{self.product}@mp-{self.product}",
                        "enabled": True,
                        "installed": True,
                        "version": self.version,
                    }
                ]
            }
        return {"ok": True}


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_install_stages_verified_source_before_switching_and_confirms_version(
    tmp_path, monkeypatch, product
):
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    module = installer()
    source = distribution(tmp_path, product=product)
    host = Host(product=product)
    result = module.install(
        source, tmp_path / "sources", "1", command=host, product=product
    )
    assert host.source == Path(result["source"])
    assert host.source != source
    assert host.version == "1"
    assert (host.source / f"plugins/{product}/execution-files.json").is_file()
    assert result["active_chat_acceptance"] == "requires a fresh chat"


def test_stale_catalog_is_detected_before_replacing_installed_plugin(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    previous = distribution(tmp_path, "1")
    selected = distribution(tmp_path, "2")
    host = Host(previous, stale=True)
    with pytest.raises(ValueError, match="selected another local source"):
        installer().install(selected, tmp_path / "sources", "2", command=host)
    assert not any(args[0] == "add" for args in host.calls)
    assert host.source == previous


def test_failed_install_restores_previous_source_and_version(tmp_path, monkeypatch):
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    previous = distribution(tmp_path, "1")
    selected = distribution(tmp_path, "2")
    host = Host(previous, fail=True)
    with pytest.raises(subprocess.CalledProcessError):
        installer().install(selected, tmp_path / "sources", "2", command=host)
    assert host.source == previous
    assert host.version == "1"


def test_corrupt_source_does_not_modify_host_registration(tmp_path, monkeypatch):
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    source = distribution(tmp_path)
    (source / "plugins/vera/scripts/helper.py").write_text("broken")
    host = Host()
    with pytest.raises(ValueError, match="content mismatch"):
        installer().install(source, tmp_path / "sources", "1", command=host)
    assert host.calls == []


def test_concurrent_updates_are_serial_and_keep_only_two_managed_sources(
    tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    module = installer()
    sources = [distribution(tmp_path, str(version)) for version in range(1, 5)]
    host = Host()
    gate = Barrier(2)

    def update(index):
        gate.wait(timeout=5)
        return module.install(
            sources[index], tmp_path / "sources", str(index + 1), command=host
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update, (0, 1)))
    assert {row["version"] for row in results} == {"1", "2"}
    for index in (2, 3):
        module.install(
            sources[index], tmp_path / "sources", str(index + 1), command=host
        )
    assert host.version == "4"
    assert len(list((tmp_path / "sources").glob("*/.managed-source.json"))) == 2


def test_next_install_recovers_owned_interrupted_staging_and_preserves_unknown(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    destination = tmp_path / "sources"
    interrupted = destination / ".staging-interrupted"
    interrupted.mkdir(parents=True)
    info = interrupted.stat()
    (interrupted / ".managed-source.json").write_text(
        json.dumps({"package_sha256": "a" * 64, "identity": [info.st_dev, info.st_ino]})
    )
    (interrupted / "partial-code").write_text("incomplete")
    unknown = destination / ".staging-unknown"
    unknown.mkdir()
    (unknown / "keep").write_text("unowned")
    installer().install(distribution(tmp_path), destination, "1", command=Host())
    assert not interrupted.exists()
    assert (unknown / "keep").read_text() == "unowned"
