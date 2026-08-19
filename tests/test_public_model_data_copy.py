from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "validate_public_model_data_copy.py"


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "public_model_data_copy_validator", VALIDATOR_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_public_page(root: Path, source: str) -> None:
    page = root / "static" / "shared" / "journal-sampling" / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(source, encoding="utf-8")


def test_validator_flags_internal_filename_and_implementation_terms(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    _write_public_page(
        tmp_path,
        """
        <section data-model-data-workflow="example">
          <p>The MCP widget loads review_payload.json.</p>
        </section>
        """,
    )

    findings = validator.validate_public_model_data_copy(tmp_path)

    assert [(finding.rule, finding.token) for finding in findings] == [
        ("internal-filename", "review_payload.json"),
        ("internal-interface", "MCP"),
        ("implementation-jargon", "widget"),
    ]


def test_validator_allows_professional_terms_and_technical_details_outside_block(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    _write_public_page(
        tmp_path,
        """
        <p>Developer note: MCP reads review_payload.json.</p>
        <section data-model-data-workflow="example">
          <p>Codex and Cowork may receive selected CSV, XML and PDF evidence.</p>
        </section>
        """,
    )

    findings = validator.validate_public_model_data_copy(tmp_path)

    assert findings == []


def test_validator_checks_localized_model_copy_in_shared_javascript(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    script = tmp_path / "static" / "shared" / "journal-sampling" / "index.html"
    script.parent.mkdir(parents=True)
    script.write_text(
        'const page = {modelData: "The fallback uses a file-based payload."};',
        encoding="utf-8",
    )

    findings = validator.validate_public_model_data_copy(tmp_path)

    assert [(finding.rule, finding.token) for finding in findings] == [
        ("implementation-jargon", "fallback"),
        ("implementation-jargon", "file-based"),
        ("implementation-jargon", "payload"),
    ]


def test_validator_can_audit_all_public_pages_and_format_a_finding(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    page = tmp_path / "static" / "shared" / "another-process" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text(
        '<section data-model-data-workflow="other">MCP</section>',
        encoding="utf-8",
    )

    findings = validator.validate_public_model_data_copy(
        tmp_path, all_public_pages=True
    )

    assert len(findings) == 1
    assert (
        findings[0]
        .format(tmp_path)
        .startswith(
            "static/shared/another-process/index.html:1: internal-interface: 'MCP'."
        )
    )


def test_validator_main_returns_success_and_failure_for_governed_copy(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    _write_public_page(
        tmp_path,
        '<section data-model-data-workflow="example">Plain copy.</section>',
    )
    success = validator.main(["--root", str(tmp_path)])
    _write_public_page(
        tmp_path,
        '<section data-model-data-workflow="example">MCP</section>',
    )

    failure = validator.main(["--root", str(tmp_path)])

    assert success == 0
    assert failure == 1


def test_journal_audit_public_copy_has_no_internal_editorial_language() -> None:
    validator = _load_validator()

    findings = validator.validate_public_model_data_copy(ROOT)

    assert findings == [], "\n".join(finding.format(ROOT) for finding in findings)


def test_plain_language_revision_preserves_journal_audit_disclosure_bounds() -> None:
    journal = (ROOT / "static/shared/journal-sampling/index.html").read_text(
        encoding="utf-8"
    )
    entries = (ROOT / "static/shared/check-entries/index.html").read_text(
        encoding="utf-8"
    )
    journal_block = journal.split('data-model-data-status="relevant"', 1)[1].split(
        "</section>", 1
    )[0]
    entries_block = entries.split('data-model-data-status="relevant"', 1)[1].split(
        "</section>", 1
    )[0]

    for required in (
        "prime 20 righe canoniche",
        "campiona l'intero giornale",
        "fino a 750 righe selezionate",
        "tutti i 17 campi contabili e di origine",
        "non pseudonimizza i dati professionali",
        "Non c'è anonimizzazione automatica",
        "né garanzia di elaborazione solo locale",
    ):
        assert required in journal_block

    for required in (
        "l'intera popolazione qualificata",
        "1.500 risultati e 500 PDF",
        "2.500 elementi o 2.000.000 byte",
        "al massimo 25 per chiamata",
        "500.000 byte",
        "senza inviarlo al modello",
        "Una fonte completa può essere aperta",
        "non vengono anonimizzati né pseudonimizzati automaticamente",
    ):
        assert required in entries_block

    assert journal.count('"model.runtime.copy":') == 5
    assert entries.count('"model.runtime.copy":') == 5
