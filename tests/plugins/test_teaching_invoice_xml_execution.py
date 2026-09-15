"""Run fictional first-use invoice inputs through current preparation and export."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from lxml import etree

from tests.plugins._invoice_teaching import proposal
from tests.plugins._teaching_release import record_native_check
from tests.plugins.test_teaching_kit_execution import (
    ROOT,
    _bound_case,
    _complete_teaching_case,
    _read,
    _run,
    _write,
)


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize(
    "phase,number,total",
    [("demo", "DID-001", "122.00"), ("practice", "DID-002", "244.00")],
)
def test_invoice_kit_prepares_reviews_and_exports_current_native_xml(
    tmp_path, monkeypatch, language, phase, number, total, record_property
):
    run = _bound_case(
        tmp_path, monkeypatch, "invoice-xml", "invoice-xml", phase, language=language
    )
    scripts = ROOT / "plugins/invoice-xml/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    from invoice_schema import InvoiceSchema
    from invoice_workflow import digest, export_invoice

    output = Path(run["output_dir"])
    bindings = run["context"]["input_bindings"]
    assert len(bindings) == 1
    source_path = Path(bindings[0]["path"])
    original_bytes = source_path.read_bytes()
    selection = [
        {
            "id": "teaching-invoice",
            "path": source_path.relative_to(run["context"]["input_dir"]).as_posix(),
            "title": "Fictional invoice data sheet; no real invoice or approval",
            "role": "invoice",
            "evidence_group": "one-fictional-invoice",
        }
    ]
    _write(output / "source_selection.json", selection)
    _run(
        scripts / "source_evidence.py",
        "--selection",
        output / "source_selection.json",
        "--client-engagement",
        run["context_path"],
        "--output",
        output,
    )
    intake = _read(next(output.glob("intake-*/source_evidence.json")))
    assert intake["interpretation_status"] == "awaiting_model_extraction"
    assert intake["sources"][0]["sha256"] == hashlib.sha256(original_bytes).hexdigest()
    fixture_interpretation = proposal(intake["sources"][0], phase, language)
    _write(output / "proposal.json", fixture_interpretation)
    _run(
        scripts / "invoice_workflow.py",
        "prepare",
        "--proposal",
        output / "proposal.json",
        "--client-engagement",
        run["context_path"],
        "--output",
        output,
    )
    revision = next(output.glob("draft-*"))
    preview_bytes = (revision / "preview.html").read_bytes()
    assert number in preview_bytes.decode()
    assert (
        _read(revision / "validation.json")["status"] == "awaiting_professional_review"
    )
    assert list(output.rglob("*.xml")) == []
    # Native review_request is deliberately not an approval.
    with pytest.raises(ValueError):
        export_invoice(
            revision,
            _read(revision / "review_request.json"),
            input_root=Path(run["context"]["input_dir"]),
        )
    # This event exists only in the regression test. It must never be loaded by
    # a live teacher or reported as an actual professional/learner approval.
    fixture_review = {
        "schema_version": 1,
        "proposal_sha256": digest(fixture_interpretation),
        "status": "approved_for_export",
        "reviewer": "Synthetic teaching regression reviewer",
        "reviewed_at": "2026-09-14T12:00:00+02:00",
        "approval_basis": "Synthetic regression-test event; not a professional or learner approval",
    }
    _write(output / "synthetic-review-fixture.json", fixture_review)
    _run(
        scripts / "invoice_workflow.py",
        "export",
        "--revision",
        revision,
        "--review",
        output / "synthetic-review-fixture.json",
        "--client-engagement",
        run["context_path"],
        "--output",
        output,
    )
    xml_path = next((revision / "export").glob("*.xml"))
    xml = xml_path.read_bytes()
    assert InvoiceSchema().errors(xml) == []
    tree = etree.fromstring(xml)
    assert tree.findtext(".//Numero") == number
    assert tree.findtext(".//ImportoTotaleDocumento") == total
    assert tree.findtext(".//TipoDocumento") == "TD01"
    export_report = _read(revision / "export/export_report.json")
    assert export_report["status"] == "exported_for_operator"
    assert export_report["sdi_acceptance"] == "not_tested"
    assert source_path.read_bytes() == original_bytes
    assert (revision / "preview.html").read_bytes() == preview_bytes
    assert not list((tmp_path / "kit").rglob("*review*.json"))
    _complete_teaching_case(run, tmp_path / "case")
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="invoice-xml",
        language=language,
        phase=phase,
    )
