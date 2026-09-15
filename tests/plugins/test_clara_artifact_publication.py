"""Published paths round-trip on every supported operating system."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/clara/scripts"


@pytest.fixture
def publication(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "artifact_publication_test", SCRIPTS / "artifact_publication.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nested_snapshot_is_verifiable_with_portable_manifest_path(
    tmp_path, publication
):
    source = tmp_path / "report.txt"
    source.write_text("reviewed output", encoding="utf-8")
    work = tmp_path / ".generations" / "first"
    work.mkdir(parents=True)
    record = {
        "path": source.name,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }

    pointer = publication.publish_snapshot(
        tmp_path,
        work,
        manifest={"outputs": [record]},
        records=[record],
        manifest_name="manifest.json",
        pointer_name="current.json",
        status="completed",
    )

    assert pointer["manifest"] == ".generations/first/published/manifest.json"
    result = publication.verify_snapshot(
        tmp_path,
        pointer_name="current.json",
        status="completed",
        output_field=("outputs",),
    )
    assert result["identity_verified"] is True


@pytest.mark.parametrize(
    "unsafe", ["../manifest.json", "/manifest.json", "dir\\manifest.json"]
)
def test_snapshot_rejects_nonportable_or_escaping_pointer(
    tmp_path, publication, unsafe
):
    (tmp_path / "current.json").write_text(
        json.dumps({"status": "completed", "manifest": unsafe})
    )

    with pytest.raises(ValueError, match="unsafe output path"):
        publication.verify_snapshot(
            tmp_path,
            pointer_name="current.json",
            status="completed",
            output_field=("outputs",),
        )
