from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "bilancio-xbrl-it"
SCRIPTS = PLUGIN_ROOT / "scripts"
RULE_PACK = PLUGIN_ROOT / "rulepacks" / "it" / "statutory-forms-2026.1.json"


def _load_module(name: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"bilancio_pdf_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pdf_trial_balance = _load_module("pdf_trial_balance")
managed_ocr_runtime = _load_module("managed_ocr_runtime")
xbrl_case = _load_module("xbrl_case")
case_service = _load_module("case_service")
http_api = _load_module("http_api")
intelligence_contract = _load_module("intelligence_contract")
review_views = _load_module("review_views")


def _payload() -> dict[str, object]:
    return {
        "case_id": "case_pdf_2025",
        "tenant_id": "tenant_pdf",
        "entity": {
            "legal_name": "PDF S.r.l.",
            "tax_identifier": "IT00000000000",
            "registered_office": "Milano (MI), Italia",
            "legal_form": "SRL",
            "accounting_framework": "OIC",
            "listed": False,
            "regulated_sector": False,
            "consolidated": False,
            "final_liquidation": False,
            "first_financial_year": False,
            "prior_year_form": "ABBREVIATED",
            "prior_period_start": "2024-01-01",
            "prior_period_end": "2024-12-31",
            "micro_exclusion_flags": [],
        },
        "period": {"start": "2025-01-01", "end": "2025-12-31"},
        "oic_rule_pack": "OIC_2024_2025.1",
        "filing_campaign_year": 2026,
        "taxonomy_checksum": "a" * 64,
    }


def _rule_pack() -> dict[str, object]:
    return json.loads(RULE_PACK.read_text(encoding="utf-8"))


def _write_pdf(path: Path, *, text: bool = True) -> None:
    pdf = canvas.Canvas(str(path), pagesize=landscape(A4))
    if text:
        x_positions = (20, 100, 280, 390, 480, 570, 670)
        rows = (
            (
                "account_code",
                "account_description",
                "opening_signed",
                "period_debit",
                "period_credit",
                "closing_signed",
                "prior_closing_signed",
            ),
            ("100", "Cassa", "100", "50", "10", "139", "90"),
            ("200", "Patrimonio netto", "-100", "10", "50", "-140", "-90"),
            ("TOTALE", "Totale generale", "0", "60", "60", "0", "0"),
        )
        for row_index, row in enumerate(rows):
            y = 560 - row_index * 24
            for x, value in zip(x_positions, row, strict=True):
                pdf.drawString(x, y, value)
    pdf.showPage()
    pdf.save()


def _accepted_review(candidate: dict[str, object]) -> dict[str, object]:
    account_row = candidate["rows"][0]
    total_row = candidate["rows"][2]
    return {
        "decision": "ACCEPTED",
        "reason": "Verified every header, account row, amount, and the summary exclusion.",
        "declarations": {
            "headers_and_columns_reviewed": True,
            "account_rows_reviewed": True,
            "monetary_values_reviewed": True,
            "excluded_rows_reviewed": True,
        },
        "corrections": [
            {
                "row_id": account_row["row_id"],
                "column_index": 6,
                "value": "140",
                "reason": "Confirmed against the printed closing balance.",
            }
        ],
        "excluded_rows": [
            {
                "row_id": total_row["row_id"],
                "reason": "Summary total, not an account.",
            }
        ],
    }


def _created_case(tmp_path: Path) -> dict[str, object]:
    return xbrl_case.create_case(
        tmp_path / "case", _payload(), _rule_pack(), "preparer_pdf"
    )


def test_readable_pdf_requires_review_before_installing_trial_balance(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trial-balance.pdf"
    _write_pdf(source)
    case = _created_case(tmp_path)

    result = xbrl_case.ingest_pdf_trial_balance(
        case, source, "preparer_pdf", case["revision_id"]
    )

    candidate = result["pdf_trial_balance_candidate"]
    assert result["trial_balance"] is None
    assert candidate["status"] == "PENDING_REVIEW"
    assert candidate["row_count"] == 3
    assert candidate["proposed_mapping_complete"] is True
    assert candidate["ocr_used"] is False
    assert result["source_documents"][0]["sha256"]
    assert review_views.build_review_view(result, "CASE_DASHBOARD")["next_action"] == (
        "REVIEW_PDF_EXTRACTION"
    )
    packet = intelligence_contract.build_next_intelligence_packet(result)
    assert packet["untrusted_evidence"]["pdf_trial_balance_candidate"]["row_count"] == 3
    assert packet["policy"]["professional_review_required"] is True


def test_reviewed_pdf_corrections_and_exclusions_retain_cell_provenance(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trial-balance.pdf"
    _write_pdf(source)
    case = _created_case(tmp_path)
    case = xbrl_case.ingest_pdf_trial_balance(
        case, source, "preparer_pdf", case["revision_id"]
    )
    review = _accepted_review(case["pdf_trial_balance_candidate"])

    result = xbrl_case.record_pdf_trial_balance_review(
        case, review, "reviewer_pdf", case["revision_id"]
    )

    trial_balance = result["trial_balance"]
    assert [item["account_code"] for item in trial_balance["entries"]] == ["100", "200"]
    assert trial_balance["entries"][0]["closing_signed"] == "140.00"
    assert trial_balance["calibration"]["closing_difference"] == "0.00"
    assert trial_balance["confirmed_convention"] is None
    anchor = next(
        item
        for item in trial_balance["source_anchors"]
        if item["account_id"] == "acc_000001"
        and item["normalized_column"] == "closing_signed"
    )
    assert anchor["raw_value"] == "139"
    assert anchor["normalized_value"] == "140.00"
    assert anchor["page"] == 1
    assert anchor["bbox"]
    assert anchor["candidate_source_ref"].endswith("_c006")
    assert anchor["evidence_status"] == "USER_CONFIRMED"
    assert anchor["correction"]["reviewed_by"] == "reviewer_pdf"
    assert result["pdf_trial_balance_candidate"]["status"] == "ACCEPTED"
    assert result["source_documents"][0]["purpose"] == "TRIAL_BALANCE"


def test_pdf_acceptance_without_all_declarations_is_atomic(tmp_path: Path) -> None:
    source = tmp_path / "trial-balance.pdf"
    _write_pdf(source)
    case = _created_case(tmp_path)
    case = xbrl_case.ingest_pdf_trial_balance(
        case, source, "preparer_pdf", case["revision_id"]
    )
    revision = case["revision_id"]
    review = _accepted_review(case["pdf_trial_balance_candidate"])
    review["declarations"]["monetary_values_reviewed"] = False

    with pytest.raises(ValueError, match="not confirmed"):
        xbrl_case.record_pdf_trial_balance_review(
            case, review, "reviewer_pdf", revision
        )

    assert case["revision_id"] == revision
    assert case["trial_balance"] is None
    assert case["pdf_trial_balance_candidate"]["status"] == "PENDING_REVIEW"


def test_scanned_pdf_uses_ocr_geometry_and_surfaces_low_confidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scan.pdf"
    _write_pdf(source, text=False)
    values = (
        (
            "account_code",
            "account_description",
            "opening_signed",
            "period_debit",
            "period_credit",
            "closing_signed",
            "prior_closing_signed",
        ),
        ("100", "Cassa", "100", "50", "10", "140", "90"),
    )

    def provider(_path: Path, _page_index: int, *, language: str) -> list[object]:
        assert language == "it"
        words = []
        for row_index, row in enumerate(values):
            for column_index, value in enumerate(row):
                x = 20 + column_index * 105
                y = 20 + row_index * 25
                confidence = 0.80 if value == "140" else 0.99
                words.append(
                    pdf_trial_balance.OcrWord(value, (x, y, x + 80, y + 10), confidence)
                )
        return words

    extraction = pdf_trial_balance.extract_pdf_tables(
        source,
        max_bytes=1024 * 1024,
        ocr_word_provider=provider,
    )

    assert extraction["ocr_used"] is True
    assert extraction["methods"] == ["PADDLE_OCR_LAYOUT"]
    assert extraction["tables"][0]["rows"][1]["cells"][5]["confidence"] == 0.80


def test_image_only_pdf_with_ocr_disabled_requests_setup(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    _write_pdf(source, text=False)

    with pytest.raises(pdf_trial_balance.OcrSetupRequired, match="OCR_SETUP_REQUIRED"):
        pdf_trial_balance.extract_pdf_tables(
            source,
            ocr_enabled=False,
            max_bytes=1024 * 1024,
        )


def test_managed_ocr_install_prepares_declared_packages_and_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requirements = tmp_path / "requirements-ocr.txt"
    requirements.write_text("paddleocr==3.5.0\npaddlepaddle==3.3.1\n", encoding="utf-8")
    monkeypatch.setattr(
        managed_ocr_runtime, "_runtime_root", lambda: tmp_path / "runtime"
    )

    def package_runner(arguments: list[str], **_kwargs: object):
        target = Path(arguments[arguments.index("--target") + 1])
        for module in managed_ocr_runtime.REQUIRED_MODULES:
            package = target / module
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(arguments, 0, "", "")

    def model_runner(arguments: list[str], **kwargs: object):
        environment = kwargs["env"]
        cache = Path(environment["PADDLE_PDX_CACHE_HOME"]) / "official_models"
        for model in managed_ocr_runtime.OCR_MODEL_NAMES:
            directory = cache / model
            directory.mkdir(parents=True)
            (directory / "inference.json").write_text("{}", encoding="utf-8")
            (directory / "inference.pdiparams").write_bytes(b"model")
        return subprocess.CompletedProcess(arguments, 0, "", "")

    result = managed_ocr_runtime.install_ocr_runtime(
        requirements,
        runner=package_runner,
        model_runner=model_runner,
    )

    assert result.status == "ready"
    assert result.reused is False
    assert managed_ocr_runtime.activate_ocr_runtime(requirements) == Path(
        result.runtime_path
    )
    receipt = json.loads(
        (Path(result.runtime_path) / managed_ocr_runtime.READY_MARKER).read_text(
            encoding="utf-8"
        )
    )
    assert receipt["models"] == list(managed_ocr_runtime.OCR_MODEL_NAMES)


def test_pdf_ingest_rejects_symlink_source(tmp_path: Path) -> None:
    source = tmp_path / "trial-balance.pdf"
    link = tmp_path / "linked.pdf"
    _write_pdf(source)
    link.symlink_to(source)
    case = _created_case(tmp_path)

    with pytest.raises(ValueError, match="symbolic-link components"):
        xbrl_case.ingest_pdf_trial_balance(
            case, link, "preparer_pdf", case["revision_id"]
        )


def test_pdf_ingest_rejects_symbolic_link_in_source_ancestor(tmp_path: Path) -> None:
    real_directory = tmp_path / "real-input"
    linked_directory = tmp_path / "linked-input"
    real_directory.mkdir()
    source = real_directory / "trial-balance.pdf"
    _write_pdf(source)
    linked_directory.symlink_to(real_directory, target_is_directory=True)
    case = _created_case(tmp_path)

    with pytest.raises(ValueError, match="symbolic-link components"):
        xbrl_case.ingest_pdf_trial_balance(
            case,
            linked_directory / source.name,
            "preparer_pdf",
            case["revision_id"],
        )


def test_http_pdf_ingest_and_review_promote_only_reviewed_rows(tmp_path: Path) -> None:
    source = tmp_path / "trial-balance.pdf"
    _write_pdf(source)
    service = case_service.CaseService(tmp_path / "store", input_root=tmp_path)
    context = case_service.RequestContext(
        tenant_id="tenant_pdf",
        actor_id="reviewer_pdf",
        roles=("PREPARER",),
        originating_interface="pytest-http",
    )
    app = http_api.create_app(service, _rule_pack(), lambda _request: context)
    client = TestClient(app)
    created = client.post(
        "/v1/xbrl-cases",
        json=_payload(),
        headers={"Idempotency-Key": "create_pdf"},
    )
    ingested = client.post(
        "/v1/xbrl-cases/case_pdf_2025/documents",
        json={
            "document_kind": "PDF_TRIAL_BALANCE",
            "source_path": str(source),
            "ocr_language": "it",
        },
        headers={
            "If-Match": f'"{created.json()["revision_id"]}"',
            "Idempotency-Key": "ingest_pdf",
        },
    )
    case = xbrl_case.load_case(tmp_path / "store/tenant_pdf/case_pdf_2025")
    review = _accepted_review(case["pdf_trial_balance_candidate"])
    reviewed = client.post(
        "/v1/xbrl-cases/case_pdf_2025/review-pdf-extraction",
        json=review,
        headers={
            "If-Match": f'"{ingested.json()["revision_id"]}"',
            "Idempotency-Key": "review_pdf",
        },
    )

    assert created.status_code == 201
    assert ingested.status_code == 200
    assert reviewed.status_code == 200
    stored = xbrl_case.load_case(tmp_path / "store/tenant_pdf/case_pdf_2025")
    assert len(stored["trial_balance"]["entries"]) == 2
    assert stored["pdf_trial_balance_candidate"]["status"] == "ACCEPTED"


def test_queued_pdf_ingest_retries_without_mutating_case_on_ocr_setup_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scan.pdf"
    _write_pdf(source, text=False)
    service = case_service.CaseService(tmp_path / "store", input_root=tmp_path)
    preparer = case_service.RequestContext(
        tenant_id="tenant_pdf",
        actor_id="preparer_pdf",
        roles=("PREPARER",),
        originating_interface="pytest-queue",
    )
    worker = case_service.RequestContext(
        tenant_id="tenant_pdf",
        actor_id="worker_pdf",
        roles=("SERVICE_WORKER",),
        originating_interface="background-worker",
    )
    service.create(preparer, _payload(), _rule_pack(), "create_pdf")
    service.enqueue_job(
        preparer,
        "case_pdf_2025",
        "pdf_ocr_setup",
        "ingest_pdf",
        {"source_path": str(source), "ocr_enabled": False},
        "rev_1",
        max_attempts=2,
    )

    first = service.run_job(worker, "case_pdf_2025", "pdf_ocr_setup")
    second = service.run_job(worker, "case_pdf_2025", "pdf_ocr_setup")
    exhausted = service.run_job(worker, "case_pdf_2025", "pdf_ocr_setup")

    assert first["status"] == "FAILED"
    assert first["attempts"] == 1
    assert first["last_error"]["code"] == "OcrSetupRequired"
    assert "OCR_SETUP_REQUIRED" in first["last_error"]["message"]
    assert second["status"] == "FAILED"
    assert second["attempts"] == 2
    assert exhausted == second
    stored = xbrl_case.load_case(tmp_path / "store/tenant_pdf/case_pdf_2025")
    assert stored["revision_id"] == "rev_1"
    assert stored["pdf_trial_balance_candidate"] is None
