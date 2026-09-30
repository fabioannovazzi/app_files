"""Verify the dependency-checker command contract without environment changes."""

from __future__ import annotations

import importlib.metadata
import runpy
from pathlib import Path

import pytest

CHECKER = (
    Path(__file__).resolve().parents[2]
    / "plugins/business-valuation/scripts/check_dependencies.py"
)


@pytest.fixture
def checker(monkeypatch):
    versions = {
        "jsonschema": "4.23.0",
        "openpyxl": "3.1.0",
        "python-docx": "1.1.0",
        "reportlab": "4.0.0",
    }
    monkeypatch.setattr(importlib.metadata, "version", versions.__getitem__)
    return runpy.run_path(str(CHECKER))["main"], versions


@pytest.mark.parametrize("args", [[], ["--requirements", "requirements.txt"]])
def test_checker_accepts_declared_set_and_minimum_versions(checker, args):
    main, _ = checker
    assert main(args) == 0


@pytest.mark.parametrize(
    ("package", "version"),
    [
        ("jsonschema", "4.22.0"),
        ("jsonschema", "5.0.0"),
        ("openpyxl", "3.0.9"),
        ("openpyxl", "4.0.0"),
        ("python-docx", "1.0.0"),
        ("reportlab", "3.6.0"),
        ("reportlab", "5.0.0"),
    ],
)
def test_checker_rejects_unsupported_dependency_version(checker, package, version):
    main, versions = checker
    versions[package] = version
    with pytest.raises(SystemExit, match=package):
        main([])


def test_checker_rejects_unrecognized_version(checker):
    main, versions = checker
    versions["jsonschema"] = "unknown"
    with pytest.raises(
        SystemExit, match="Unsupported installed version for jsonschema"
    ):
        main([])


def test_checker_rejects_missing_package(checker, monkeypatch):
    main, _ = checker

    def missing(package):
        raise importlib.metadata.PackageNotFoundError(package)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    with pytest.raises(SystemExit, match="jsonschema"):
        main([])


def test_checker_rejects_unregistered_requirement_set(checker):
    main, _ = checker
    with pytest.raises(SystemExit) as result:
        main(["--requirements", "other.txt"])
    assert result.value.code == 2
