from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUPPORT_PATH = ROOT / "tests" / "plugins" / "test_clara_html_evidence_bindings.py"


def load_test_support() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_html_evidence_integrity_support",
        SUPPORT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def verified_index(tmp_path: Path) -> tuple[Any, Any, Path]:
    support = load_test_support()
    evidence = support.load_module()
    work = support.write_source_bound_work(tmp_path, evidence)
    built = support.run_script(
        support.SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(tmp_path / "dist"),
    )
    assert built.returncode == 0, built.stderr or built.stdout
    index_path = Path(json.loads(built.stdout)["output"]["index_path"])
    return support, evidence, index_path


def replace_evidence_ledger(
    html_text: str,
    evidence: Any,
    ledger: dict[str, Any],
) -> str:
    markup = evidence.embedded_evidence_ledger_markup(ledger)
    return evidence.EVIDENCE_LEDGER_RE.sub(lambda _: markup, html_text, count=1)


def check_status(report: dict[str, Any], code: str) -> str:
    return next(check["status"] for check in report["checks"] if check["code"] == code)


def test_validator_rejects_tampered_binding_raw_value(
    tmp_path: Path,
    verified_index: tuple[Any, Any, Path],
) -> None:
    support, evidence, index_path = verified_index
    html_text = index_path.read_text(encoding="utf-8")
    ledger = evidence.extract_embedded_evidence_ledger(html_text)
    assert ledger is not None
    ledger["bindings"][0]["raw_value"] = "999"
    tampered_path = tmp_path / "tampered-raw-value.html"
    tampered_path.write_text(
        replace_evidence_ledger(html_text, evidence, ledger),
        encoding="utf-8",
    )

    validated = support.run_script(
        support.SKILL_ROOT / "scripts" / "validate_html_deck.py",
        str(tampered_path),
        "--allow-readable-path",
    )

    assert validated.returncode == 1
    report = json.loads(validated.stdout)
    assert check_status(report, "provenance.evidence_ledger") == "fail"


def test_validator_rejects_tampered_binding_resolved_value(
    tmp_path: Path,
    verified_index: tuple[Any, Any, Path],
) -> None:
    support, evidence, index_path = verified_index
    html_text = index_path.read_text(encoding="utf-8")
    ledger = evidence.extract_embedded_evidence_ledger(html_text)
    assert ledger is not None
    ledger["bindings"][0]["resolved_value"] = "999"
    tampered_path = tmp_path / "tampered-resolved-value.html"
    tampered_path.write_text(
        replace_evidence_ledger(html_text, evidence, ledger),
        encoding="utf-8",
    )

    validated = support.run_script(
        support.SKILL_ROOT / "scripts" / "validate_html_deck.py",
        str(tampered_path),
        "--allow-readable-path",
    )

    assert validated.returncode == 1
    report = json.loads(validated.stdout)
    assert check_status(report, "provenance.evidence_ledger") == "fail"


def test_validator_rejects_tampered_resolved_content_ledger_digest(
    tmp_path: Path,
    verified_index: tuple[Any, Any, Path],
) -> None:
    support, evidence, index_path = verified_index
    html_text = index_path.read_text(encoding="utf-8")
    ledger = evidence.extract_embedded_evidence_ledger(html_text)
    assert ledger is not None
    ledger["resolved"]["content_ledger_sha256"] = "0" * 64
    tampered_path = tmp_path / "tampered-resolved-ledger.html"
    tampered_path.write_text(
        replace_evidence_ledger(html_text, evidence, ledger),
        encoding="utf-8",
    )

    validated = support.run_script(
        support.SKILL_ROOT / "scripts" / "validate_html_deck.py",
        str(tampered_path),
        "--allow-readable-path",
    )

    assert validated.returncode == 1
    report = json.loads(validated.stdout)
    assert check_status(report, "provenance.evidence_ledger") == "pass"
    assert check_status(report, "provenance.evidence_content_ledger") == "fail"


def test_validator_rejects_wrong_content_address_directory(
    tmp_path: Path,
    verified_index: tuple[Any, Any, Path],
) -> None:
    support, _, index_path = verified_index
    wrong_dir = tmp_path / ("0" * 64)
    wrong_dir.mkdir()
    wrong_index = wrong_dir / "index.html"
    shutil.copyfile(index_path, wrong_index)

    validated = support.run_script(
        support.SKILL_ROOT / "scripts" / "validate_html_deck.py",
        str(wrong_index),
    )

    assert validated.returncode == 1
    report = json.loads(validated.stdout)
    assert check_status(report, "publication.id") == "fail"
