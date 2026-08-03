from __future__ import annotations

import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED_MODULES = ROOT / "plugins" / "_shared" / "vendor" / "modules"
if str(SHARED_MODULES) not in sys.path:
    sys.path.insert(0, str(SHARED_MODULES))

from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    AssuranceEnvelopeError,
    DecisionReceiptError,
    MoneyValidationError,
    RelationshipContractError,
    SerializationValidationError,
    artifact_receipt,
    build_allocation_ledger,
    build_assurance_envelope,
    build_client_engagement_context,
    build_gate_register,
    build_numeric_evidence_ledger,
    build_reviewed_decision_receipt,
    build_source_qualification,
    build_studio_client_folder_binding,
    canonical_json_bytes,
    canonical_json_sha256,
    decimal_text,
    difference_within_tolerance,
    load_client_engagement_context_file,
    parse_canonical_decimal,
    parse_localized_decimal,
    validate_artifact_receipt,
    validate_assurance_envelope,
    validate_client_engagement_context,
    validate_client_workflow_run,
    validate_numeric_evidence_ledger,
    validate_reviewed_decision_receipt,
    validate_source_qualification,
    validate_studio_client_folder_binding,
)


def _control(
    control_id: str,
    *,
    status: str,
    required: bool = True,
) -> dict[str, object]:
    return {
        "control_id": control_id,
        "required": required,
        "status": status,
        "evidence_refs": ["evidence.input"],
        "detail": "",
    }


def _gate(status: str, evidence_ref: str) -> dict[str, object]:
    return {
        "status": status,
        "evidence_refs": [evidence_ref] if status == "passed" else [],
        "limitations": [],
    }


def _ready_gates() -> dict[str, dict[str, object]]:
    return {
        "source": _gate("passed", "source.qualification"),
        "preparation": _gate("passed", "prepared.batch"),
        "reconciliation": _gate("passed", "reconciliation.result"),
        "semantic_review": _gate("passed", "review.decision"),
        "reporting": _gate("passed", "report.receipt"),
        "publication": _gate("withheld", ""),
    }


def _numeric_entry() -> dict[str, object]:
    return {
        "evidence_id": "revenue.total",
        "value": "1234.56",
        "unit": "currency",
        "currency": "EUR",
        "source": {
            "artifact_ref": "source.workbook",
            "locator": "Trial balance!C8",
            "value": "1234.56",
        },
        "prepared": {
            "artifact_ref": "prepared.table",
            "locator": "revenue.total",
            "value": "1234.56",
        },
        "outputs": [
            {
                "artifact_ref": "report.workbook",
                "locator": "Income statement!D12",
                "value": "1234.56",
            }
        ],
        "calculation_ref": "calculation.revenue_total",
        "decision_ref": "decision.coa_mapping",
        "limitations": [],
    }


def _client_folder(tmp_path: Path) -> dict[str, object]:
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    return build_studio_client_folder_binding(
        studio_client_id="client_" + hashlib.sha256(b"rossi").hexdigest()[:24],
        scope_id="scope_" + hashlib.sha256(b"rossi").hexdigest()[:24],
        archive_root=archive_root,
        scope_relative_dir="Rossi",
        client_root=client_root,
        display_name="Rossi",
    )


def test_client_engagement_accepts_only_selected_client_input(tmp_path: Path) -> None:
    folder = _client_folder(tmp_path)
    input_dir = Path(str(folder["client_root"])) / "audit-input"
    input_dir.mkdir()
    workspace_root = tmp_path / "Vera Work"

    context = build_client_engagement_context(
        studio_client_folder=folder,
        engagement_id="audit-2026",
        workflow_id="audit-reconciliation",
        run_id="run-001",
        input_dir=input_dir,
        workspace_root=workspace_root,
    )

    assert context["output_dir"] == str(
        workspace_root
        / "clients"
        / folder["studio_client_id"]
        / "engagements"
        / "audit-2026"
        / "runs"
        / "audit-reconciliation"
        / "run-001"
    )
    assert validate_client_engagement_context(context) == context


def test_client_engagement_rejects_other_client_input(tmp_path: Path) -> None:
    folder = _client_folder(tmp_path)
    other_client_input = tmp_path / "Studio" / "Bianchi" / "audit-input"
    other_client_input.mkdir(parents=True)

    with pytest.raises(AssuranceContractError, match="selected studio client"):
        build_client_engagement_context(
            studio_client_folder=folder,
            engagement_id="audit-2026",
            workflow_id="audit-reconciliation",
            run_id="run-001",
            input_dir=other_client_input,
            workspace_root=tmp_path / "Vera Work",
        )


def test_client_workflow_context_file_rejects_legacy_pointer_context(
    tmp_path: Path,
) -> None:
    folder = _client_folder(tmp_path)
    input_dir = (
        Path(str(folder["client_root"])) / "Vera engagements" / "eng_1" / "inputs"
    )
    input_dir.mkdir(parents=True)
    source = input_dir / "monthly-pnl.xlsx"
    source.write_bytes(b"source")
    context = build_client_engagement_context(
        studio_client_folder=folder,
        engagement_id="eng_1",
        workflow_id="financial-analysis",
        run_id="run_1",
        input_dir=input_dir,
        workspace_root=tmp_path / "Vera Work",
    )
    context_path = tmp_path / "client-engagement.json"
    context_path.write_text(json.dumps(context), encoding="utf-8")

    with pytest.raises(AssuranceContractError, match="portable customer-folder"):
        load_client_engagement_context_file(
            context_path,
            expected_workflow_id="financial-analysis",
            input_paths=[source],
            output_dir=context["output_dir"],
        )


def test_client_workflow_context_rejects_another_workflow(tmp_path: Path) -> None:
    folder = _client_folder(tmp_path)
    input_dir = Path(str(folder["client_root"])) / "inputs"
    input_dir.mkdir()
    context = build_client_engagement_context(
        studio_client_folder=folder,
        engagement_id="eng_1",
        workflow_id="sales-plan",
        run_id="run_1",
        input_dir=input_dir,
        workspace_root=tmp_path / "Vera Work",
    )

    with pytest.raises(AssuranceContractError, match="different Vera workflow"):
        validate_client_workflow_run(
            context,
            expected_workflow_id="financial-analysis",
        )


def test_client_workflow_context_rejects_input_outside_engagement(
    tmp_path: Path,
) -> None:
    folder = _client_folder(tmp_path)
    input_dir = Path(str(folder["client_root"])) / "inputs"
    input_dir.mkdir()
    outside = tmp_path / "other-client.xlsx"
    outside.write_bytes(b"outside")
    context = build_client_engagement_context(
        studio_client_folder=folder,
        engagement_id="eng_1",
        workflow_id="financial-analysis",
        run_id="run_1",
        input_dir=input_dir,
        workspace_root=tmp_path / "Vera Work",
    )

    with pytest.raises(AssuranceContractError, match="outside"):
        validate_client_workflow_run(
            context,
            expected_workflow_id="financial-analysis",
            input_paths=[outside],
        )


def test_client_folder_rejects_tampered_folder_scope_identity(tmp_path: Path) -> None:
    folder = _client_folder(tmp_path)
    folder["scope_id"] = "scope_000000000000000000000000"
    content = {key: value for key, value in folder.items() if key != "content_sha256"}
    folder["content_sha256"] = canonical_json_sha256(content)

    with pytest.raises(AssuranceContractError, match="scope_relative_dir"):
        validate_studio_client_folder_binding(folder)


@pytest.mark.parametrize(
    ("raw", "decimal_separator", "thousands_separator", "expected"),
    [
        ("EUR 1.234,56", ",", ".", Decimal("1234.56")),
        ("1,234.56", ".", ",", Decimal("1234.56")),
        ("(20,50)", ",", ".", Decimal("-20.50")),
        (42, None, None, Decimal("42")),
    ],
)
def test_parse_localized_decimal_explicit_syntax_is_exact(
    raw: object,
    decimal_separator: str | None,
    thousands_separator: str | None,
    expected: Decimal,
) -> None:
    result = parse_localized_decimal(
        raw,
        decimal_separator=decimal_separator,
        thousands_separator=thousands_separator,
    )

    assert result == expected


def test_parse_localized_decimal_ambiguous_separator_requires_reviewed_locale() -> None:
    with pytest.raises(MoneyValidationError, match="ambiguous"):
        parse_localized_decimal("1.234")


@pytest.mark.parametrize(
    ("raw", "thousands_separator", "expected"),
    [
        ("1,234", ",", Decimal("1234")),
        ("1,234.56", ",", Decimal("1234.56")),
        ("1.234", ",", Decimal("1.234")),
        ("1.234", ".", Decimal("1234")),
        ("1.234,56", ".", Decimal("1234.56")),
        ("1,234", ".", Decimal("1.234")),
    ],
)
def test_parse_localized_decimal_preserves_explicit_thousands_role(
    raw: str,
    thousands_separator: str,
    expected: Decimal,
) -> None:
    result = parse_localized_decimal(
        raw,
        decimal_separator=None,
        thousands_separator=thousands_separator,
    )

    assert result == expected


@pytest.mark.parametrize(
    ("raw", "thousands_separator"),
    [
        ("1,23", ","),
        ("1.23", "."),
    ],
)
def test_parse_localized_decimal_rejects_malformed_explicit_thousands_grouping(
    raw: str,
    thousands_separator: str,
) -> None:
    with pytest.raises(MoneyValidationError, match="thousands grouping"):
        parse_localized_decimal(
            raw,
            decimal_separator=None,
            thousands_separator=thousands_separator,
        )


@pytest.mark.parametrize(
    (
        "raw",
        "decimal_separator",
        "thousands_separator",
        "allow_float",
        "expected",
    ),
    [
        ("USD 1,234.50", ".", None, False, Decimal("1234.50")),
        ("1.234,50 EUR", None, None, False, Decimal("1234.50")),
        ("1,234,567", None, None, False, Decimal("1234567")),
        ("1 234 567", None, None, False, Decimal("1234567")),
        ("1'234'567,50", ",", None, False, Decimal("1234567.50")),
        ("+ 12.50", ".", None, False, Decimal("12.50")),
        (Decimal("12.50"), None, None, False, Decimal("12.50")),
        (0.1, None, None, True, Decimal("0.1")),
    ],
)
def test_parse_localized_decimal_accepts_supported_boundary_syntax(
    raw: object,
    decimal_separator: str | None,
    thousands_separator: str | None,
    allow_float: bool,
    expected: Decimal,
) -> None:
    result = parse_localized_decimal(
        raw,
        decimal_separator=decimal_separator,
        thousands_separator=thousands_separator,
        allow_float=allow_float,
    )

    assert result == expected


@pytest.mark.parametrize(
    ("raw", "decimal_separator", "thousands_separator", "message"),
    [
        ("1", ";", None, "decimal_separator"),
        ("1", None, ";", "thousands_separator"),
        ("1", ",", ",", "must differ"),
        ("1,,2", None, None, "separator grouping"),
        ("1,23,456", None, None, "multiple decimal separators"),
        ("1 234'567", None, None, "multiple thousands-separator"),
        ("1 234.56.78", ".", None, "multiple decimal separators"),
        ("1.23 456", ".", None, "after the decimal separator"),
        (None, None, None, "monetary value"),
        (True, None, None, "monetary value"),
        (object(), None, None, "text, int, or Decimal"),
        ("EUR", None, None, "non-empty"),
        ("++1", None, None, "invalid sign"),
        ("(+1)", None, None, "two sign conventions"),
        ("12A", None, None, "unsupported characters"),
    ],
)
def test_parse_localized_decimal_rejects_unsupported_boundary_syntax(
    raw: object,
    decimal_separator: str | None,
    thousands_separator: str | None,
    message: str,
) -> None:
    with pytest.raises(MoneyValidationError, match=message):
        parse_localized_decimal(
            raw,
            decimal_separator=decimal_separator,
            thousands_separator=thousands_separator,
        )


@pytest.mark.parametrize(
    ("raw", "allow_float", "message"),
    [
        (Decimal("NaN"), False, "finite"),
        (float("inf"), True, "finite"),
        (float("-inf"), True, "finite"),
    ],
)
def test_parse_localized_decimal_rejects_non_finite_numbers(
    raw: Decimal | float,
    allow_float: bool,
    message: str,
) -> None:
    with pytest.raises(MoneyValidationError, match=message):
        parse_localized_decimal(raw, allow_float=allow_float)


def test_parse_localized_decimal_rejects_binary_float_by_default() -> None:
    with pytest.raises(MoneyValidationError, match="binary float"):
        parse_localized_decimal(0.1)


@pytest.mark.parametrize("raw", ("12,34.56", "12 34,56", "1'23.45"))
def test_parse_localized_decimal_rejects_malformed_thousands_grouping(
    raw: str,
) -> None:
    with pytest.raises(MoneyValidationError, match="thousands grouping"):
        parse_localized_decimal(
            raw,
            decimal_separator=".",
            thousands_separator=",",
        )


def test_canonical_decimal_rejects_redundant_scale_and_negative_zero() -> None:
    with pytest.raises(MoneyValidationError, match="canonical"):
        parse_canonical_decimal("1.00")

    assert decimal_text(Decimal("-0.00")) == "0"


def test_difference_within_tolerance_is_exact_at_cent_boundary() -> None:
    difference, within = difference_within_tolerance(
        Decimal("100.01"),
        Decimal("100"),
        Decimal("0.01"),
    )

    assert difference == Decimal("0.01")
    assert within is True


def test_difference_within_tolerance_rejects_negative_tolerance() -> None:
    with pytest.raises(MoneyValidationError, match="must not be negative"):
        difference_within_tolerance(
            Decimal("100"),
            Decimal("100"),
            Decimal("-0.01"),
        )


def test_canonical_json_is_order_invariant_and_rejects_floats() -> None:
    assert canonical_json_bytes({"b": 2, "a": 1}) == canonical_json_bytes(
        {"a": 1, "b": 2}
    )

    with pytest.raises(SerializationValidationError, match="binary floating"):
        canonical_json_bytes({"amount": 1.25})


def test_artifact_receipt_detects_changed_bytes(tmp_path: Path) -> None:
    artifact = tmp_path / "source.csv"
    artifact.write_text("amount\n1.00\n", encoding="utf-8")
    receipt = artifact_receipt(
        tmp_path,
        artifact,
        artifact_id="source.csv",
        role="source",
        media_type="text/csv",
    )

    artifact.write_text("amount\n2.00\n", encoding="utf-8")

    with pytest.raises(SerializationValidationError, match="does not match"):
        validate_artifact_receipt(tmp_path, receipt)


def test_artifact_receipt_rejects_path_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("value\n1\n", encoding="utf-8")

    with pytest.raises(SerializationValidationError, match="inside its root"):
        artifact_receipt(
            root,
            outside,
            artifact_id="outside",
            role="source",
        )


def test_artifact_receipt_replay_rejects_symlinked_parent_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    contained = root / "contained"
    contained.mkdir(parents=True)
    artifact = contained / "source.csv"
    artifact.write_text("value\n1\n", encoding="utf-8")
    receipt = artifact_receipt(
        root,
        artifact,
        artifact_id="source.csv",
        role="source",
    )
    artifact.unlink()
    contained.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "source.csv").write_text("value\n1\n", encoding="utf-8")
    contained.symlink_to(outside, target_is_directory=True)

    with pytest.raises(SerializationValidationError, match="escapes its root"):
        validate_artifact_receipt(root, receipt)


def test_qualified_source_requires_all_required_controls_to_pass() -> None:
    with pytest.raises(AssuranceContractError, match="requires every required"):
        build_source_qualification(
            qualification_id="journal.native",
            adapter_id="native_journal",
            adapter_version="v1",
            source_family="native_rowwise_journal",
            status="qualified",
            source_artifact_refs=["source.journal"],
            controls=[_control("amount_ownership", status="not_assessed")],
        )


def test_unsupported_source_layout_cannot_emit_prepared_rows() -> None:
    with pytest.raises(AssuranceContractError, match="cannot emit prepared rows"):
        build_source_qualification(
            qualification_id="journal.pdf",
            adapter_id="generic_text_pdf",
            adapter_version="v1",
            source_family="unbounded_text_pdf",
            status="unsupported_source_layout",
            source_artifact_refs=["source.journal"],
            candidate_row_count=2,
            emitted_row_count=1,
            controls=[_control("amount_ownership", status="failed")],
        )


def test_needs_review_requires_unassessed_required_control() -> None:
    qualification = build_source_qualification(
        qualification_id="journal.mapping",
        adapter_id="native_journal",
        adapter_version="v1",
        source_family="native_rowwise_journal",
        status="needs_review",
        source_artifact_refs=["source.journal"],
        controls=[_control("reviewed_mapping", status="not_assessed")],
    )

    assert qualification["status"] == "needs_review"
    assert qualification["emitted_row_count"] == 0


def test_source_qualification_rejects_more_emitted_than_candidate_rows() -> None:
    with pytest.raises(AssuranceContractError, match="cannot exceed"):
        build_source_qualification(
            qualification_id="journal.native",
            adapter_id="native_journal",
            adapter_version="v1",
            source_family="native_rowwise_journal",
            status="qualified",
            source_artifact_refs=["source.journal"],
            candidate_row_count=1,
            emitted_row_count=2,
            controls=[_control("required_fields", status="passed")],
        )


def test_source_qualification_rejects_duplicate_control_ids() -> None:
    payload = {
        "schema_version": "vera.source_qualification.v1",
        "qualification_id": "journal.native",
        "adapter_id": "native_journal",
        "adapter_version": "v1",
        "source_family": "native_rowwise_journal",
        "status": "qualified",
        "source_artifact_refs": ["source.journal"],
        "reviewed_mapping_ref": "decision.mapping",
        "candidate_row_count": 1,
        "emitted_row_count": 1,
        "controls": [
            _control("required_fields", status="passed"),
            _control("required_fields", status="passed"),
        ],
        "limitations": [],
    }

    with pytest.raises(AssuranceContractError, match="unique"):
        validate_source_qualification(payload)


def test_failed_upstream_gate_cannot_be_promoted_to_reporting_passed() -> None:
    gates = _ready_gates()
    gates["source"] = _gate("failed", "")

    with pytest.raises(AssuranceContractError, match="requires source"):
        build_gate_register(gates)


def test_gate_register_derives_report_ready_independently_from_publication() -> None:
    register = build_gate_register(_ready_gates())

    assert register["report_ready"] is True
    assert register["gates"]["publication"]["status"] == "withheld"


def test_numeric_evidence_ledger_closes_exact_values() -> None:
    ledger = build_numeric_evidence_ledger([_numeric_entry()])

    assert ledger["entries"][0]["value"] == "1234.56"
    assert len(ledger["content_sha256"]) == 64


def test_numeric_evidence_ledger_rejects_changed_rendered_value() -> None:
    entry = _numeric_entry()
    outputs = entry["outputs"]
    assert isinstance(outputs, list)
    output = outputs[0]
    assert isinstance(output, dict)
    output["value"] = "1234.55"

    with pytest.raises(AssuranceContractError, match="does not equal"):
        build_numeric_evidence_ledger([entry])


def test_numeric_evidence_ledger_rejects_changed_source_value() -> None:
    entry = _numeric_entry()
    source = entry["source"]
    assert isinstance(source, dict)
    source["value"] = "1234.55"

    with pytest.raises(AssuranceContractError, match="source.value does not equal"):
        build_numeric_evidence_ledger([entry])


def test_numeric_evidence_ledger_rejects_stale_content_digest() -> None:
    ledger = build_numeric_evidence_ledger([_numeric_entry()])
    ledger["entries"][0]["limitations"] = ["changed after sealing"]

    with pytest.raises(AssuranceContractError, match="stale"):
        validate_numeric_evidence_ledger(ledger)


def test_reviewed_decision_is_bound_to_source_and_adapter_version() -> None:
    decision = build_reviewed_decision_receipt(
        decision_id="decision.journal_mapping",
        decision_type="source_mapping",
        status="reviewed",
        reviewer_ref="reviewer.partner",
        reviewed_on="2026-07-24",
        adapter_id="native_journal",
        adapter_version="v1",
        source_artifact_refs=["source.journal"],
        content={"date": "Data", "debit": "Dare", "credit": "Avere"},
    )

    with pytest.raises(DecisionReceiptError, match="adapter version is stale"):
        validate_reviewed_decision_receipt(
            decision,
            expected_source_artifact_refs=["source.journal"],
            expected_adapter_id="native_journal",
            expected_adapter_version="v2",
            require_reviewed=True,
        )


def test_reviewed_decision_rejects_changed_content() -> None:
    decision = build_reviewed_decision_receipt(
        decision_id="decision.journal_mapping",
        decision_type="source_mapping",
        status="reviewed",
        reviewer_ref="reviewer.partner",
        reviewed_on="2026-07-24",
        adapter_id="native_journal",
        adapter_version="v1",
        source_artifact_refs=["source.journal"],
        content={"date": "Data"},
    )
    decision["content"]["date"] = "Posting date"

    with pytest.raises(DecisionReceiptError, match="digest is stale"):
        validate_reviewed_decision_receipt(decision)


@pytest.mark.parametrize(
    ("expected_decision_id", "expected_decision_type", "message"),
    [
        ("decision.other", None, "identity is stale"),
        (None, "publication_authority", "type is stale"),
    ],
)
def test_reviewed_decision_rejects_wrong_expected_identity_or_type(
    expected_decision_id: str | None,
    expected_decision_type: str | None,
    message: str,
) -> None:
    decision = build_reviewed_decision_receipt(
        decision_id="decision.mapping",
        decision_type="source_mapping",
        status="reviewed",
        reviewer_ref="reviewer.partner",
        reviewed_on="2026-07-24",
        adapter_id="native_journal",
        adapter_version="v1",
        source_artifact_refs=["source.workbook"],
        content={"amount": "amount"},
    )

    with pytest.raises(DecisionReceiptError, match=message):
        validate_reviewed_decision_receipt(
            decision,
            expected_decision_id=expected_decision_id,
            expected_decision_type=expected_decision_type,
        )


def _record(
    record_id: str,
    amount: str,
    *,
    currency: str = "EUR",
    party_ref: str = "party.acme",
) -> dict[str, object]:
    return {
        "record_id": record_id,
        "amount": amount,
        "currency": currency,
        "unit": "currency",
        "entity_ref": "entity.client",
        "party_ref": party_ref,
    }


def _allocation(
    allocation_id: str,
    source_ref: str,
    target_ref: str,
    amount: str,
    *,
    currency: str = "EUR",
    evidence_ref: str | None = None,
) -> dict[str, object]:
    return {
        "allocation_id": allocation_id,
        "source_record_ref": source_ref,
        "target_record_ref": target_ref,
        "amount": amount,
        "currency": currency,
        "unit": "currency",
        "evidence_refs": [evidence_ref or f"evidence.{allocation_id}"],
    }


def _relationship_policy(shape: str = "one_to_one") -> dict[str, object]:
    return {
        "relationship_shape": shape,
        "require_same_currency": True,
        "require_same_unit": True,
        "require_same_entity": True,
        "require_same_party": True,
        "allow_evidence_reuse": False,
        "tolerance": "0",
    }


def test_allocation_ledger_balances_exact_one_to_one_relationship() -> None:
    ledger = build_allocation_ledger(
        ledger_id="bank_to_open_items",
        policy=_relationship_policy(),
        source_records=[_record("bank.1", "100")],
        target_records=[_record("open.1", "100")],
        allocations=[_allocation("allocation.1", "bank.1", "open.1", "100")],
    )

    assert ledger["balanced"] is True
    assert ledger["source_residuals"] == [{"record_ref": "bank.1", "residual": "0"}]


def test_allocation_ledger_rejects_one_bank_row_closing_duplicate_open_rows() -> None:
    with pytest.raises(
        RelationshipContractError,
        match="reuses a source record|exceeds a population record",
    ):
        build_allocation_ledger(
            ledger_id="bank_to_open_items",
            policy=_relationship_policy("one_to_many"),
            source_records=[_record("bank.1", "100")],
            target_records=[
                _record("open.1", "100"),
                _record("open.2", "100"),
            ],
            allocations=[
                _allocation("allocation.1", "bank.1", "open.1", "100"),
                _allocation("allocation.2", "bank.1", "open.2", "100"),
            ],
        )


def test_allocation_ledger_rejects_cross_currency_match() -> None:
    with pytest.raises(RelationshipContractError, match="currency mismatch"):
        build_allocation_ledger(
            ledger_id="bank_to_open_items",
            policy=_relationship_policy(),
            source_records=[_record("bank.1", "100", currency="EUR")],
            target_records=[_record("open.1", "100", currency="USD")],
            allocations=[
                _allocation(
                    "allocation.1",
                    "bank.1",
                    "open.1",
                    "100",
                    currency="EUR",
                )
            ],
        )


def test_allocation_ledger_rejects_evidence_reuse() -> None:
    policy = _relationship_policy("many_to_many")
    with pytest.raises(RelationshipContractError, match="evidence was reused"):
        build_allocation_ledger(
            ledger_id="grouped",
            policy=policy,
            source_records=[
                _record("bank.1", "50"),
                _record("bank.2", "50"),
            ],
            target_records=[
                _record("open.1", "50"),
                _record("open.2", "50"),
            ],
            allocations=[
                _allocation(
                    "allocation.1",
                    "bank.1",
                    "open.1",
                    "50",
                    evidence_ref="evidence.shared",
                ),
                _allocation(
                    "allocation.2",
                    "bank.2",
                    "open.2",
                    "50",
                    evidence_ref="evidence.shared",
                ),
            ],
        )


@pytest.mark.parametrize("policy_field", ("require_same_currency", "require_same_unit"))
def test_allocation_ledger_v1_rejects_unsupported_conversion_policy(
    policy_field: str,
) -> None:
    policy = _relationship_policy()
    policy[policy_field] = False

    with pytest.raises(RelationshipContractError, match="conversion is unsupported"):
        build_allocation_ledger(
            ledger_id="converted",
            policy=policy,
            source_records=[_record("bank.1", "100")],
            target_records=[_record("open.1", "100")],
            allocations=[_allocation("allocation.1", "bank.1", "open.1", "100")],
        )


def _build_ready_envelope(tmp_path: Path) -> dict[str, object]:
    source = tmp_path / "source.csv"
    prepared = tmp_path / "prepared.csv"
    report = tmp_path / "report.md"
    implementation = tmp_path / "adapter.py"
    source.write_text("amount\n1234.56\n", encoding="utf-8")
    prepared.write_text("value\n1234.56\n", encoding="utf-8")
    report.write_text("Revenue: 1234.56\n", encoding="utf-8")
    implementation.write_text("ADAPTER_VERSION = 'v1'\n", encoding="utf-8")
    receipts = [
        artifact_receipt(
            tmp_path,
            source,
            artifact_id="source.workbook",
            role="source",
        ),
        artifact_receipt(
            tmp_path,
            prepared,
            artifact_id="prepared.table",
            role="prepared",
        ),
        artifact_receipt(
            tmp_path,
            report,
            artifact_id="report.workbook",
            role="report",
        ),
        artifact_receipt(
            tmp_path,
            implementation,
            artifact_id="implementation.adapter",
            role="implementation",
        ),
    ]
    decision = build_reviewed_decision_receipt(
        decision_id="decision.coa_mapping",
        decision_type="source_mapping",
        status="reviewed",
        reviewer_ref="reviewer.partner",
        reviewed_on="2026-07-24",
        adapter_id="native_journal",
        adapter_version="v1",
        source_artifact_refs=["source.workbook"],
        content={"amount": "amount"},
    )
    professional_decision = build_reviewed_decision_receipt(
        decision_id="decision.professional_review",
        decision_type="professional_review",
        status="reviewed",
        reviewer_ref="reviewer.partner",
        reviewed_on="2026-07-24",
        adapter_id="report_builder",
        adapter_version="v1",
        source_artifact_refs=["source.workbook"],
        content={"conclusion": "reviewed for reporting"},
    )
    qualification = build_source_qualification(
        qualification_id="source.qualification",
        adapter_id="native_journal",
        adapter_version="v1",
        source_family="native_rowwise_journal",
        status="qualified",
        source_artifact_refs=["source.workbook"],
        reviewed_mapping_ref="decision.coa_mapping",
        candidate_row_count=1,
        emitted_row_count=1,
        controls=[_control("required_fields", status="passed")],
    )
    numeric_entry = _numeric_entry()
    numeric_ledger = build_numeric_evidence_ledger(
        [numeric_entry],
        ledger_id="ledger.report_values",
    )
    gates = {
        "source": _gate("passed", "source.qualification"),
        "preparation": _gate("passed", "prepared.table"),
        "reconciliation": _gate("not_applicable", ""),
        "semantic_review": _gate("passed", "decision.professional_review"),
        "reporting": _gate("passed", "ledger.report_values"),
        "publication": _gate("withheld", ""),
    }
    return build_assurance_envelope(
        run_id="run.report",
        workflow_id="report_builder",
        workflow_version="v1",
        artifact_receipts=receipts,
        implementation_artifact_refs=["implementation.adapter"],
        reviewed_decisions=[decision, professional_decision],
        source_qualifications=[qualification],
        allocation_ledgers=[],
        numeric_evidence_ledgers=[numeric_ledger],
        gate_register=build_gate_register(gates),
        limitations=[],
        artifact_roots=tmp_path,
    )


def test_assurance_envelope_replays_exact_artifacts_and_reference_closure(
    tmp_path: Path,
) -> None:
    envelope = _build_ready_envelope(tmp_path)

    replayed = validate_assurance_envelope(envelope, artifact_roots=tmp_path)

    assert replayed["gate_register"]["report_ready"] is True
    assert len(replayed["content_sha256"]) == 64


def test_assurance_envelope_rejects_changed_source_bytes(tmp_path: Path) -> None:
    envelope = _build_ready_envelope(tmp_path)
    (tmp_path / "source.csv").write_text("amount\n9999.99\n", encoding="utf-8")

    with pytest.raises(AssuranceEnvelopeError, match="does not match"):
        validate_assurance_envelope(envelope, artifact_roots=tmp_path)


def test_assurance_envelope_rejects_non_text_limitation(tmp_path: Path) -> None:
    envelope = _build_ready_envelope(tmp_path)
    envelope["limitations"] = [1]
    content = dict(envelope)
    content.pop("content_sha256")
    envelope["content_sha256"] = canonical_json_sha256(content)

    with pytest.raises(AssuranceEnvelopeError, match="must be non-empty trimmed text"):
        validate_assurance_envelope(envelope, artifact_roots=tmp_path)


def test_assurance_envelope_rejects_allocation_with_unknown_evidence(
    tmp_path: Path,
) -> None:
    envelope = _build_ready_envelope(tmp_path)
    allocation_ledger = build_allocation_ledger(
        ledger_id="bank_to_open_items",
        policy=_relationship_policy(),
        source_records=[_record("bank.1", "100")],
        target_records=[_record("open.1", "100")],
        allocations=[
            _allocation(
                "allocation.1",
                "bank.1",
                "open.1",
                "100",
                evidence_ref="evidence.unregistered",
            )
        ],
    )
    envelope["allocation_ledgers"] = [allocation_ledger]
    content = dict(envelope)
    content.pop("content_sha256")
    envelope["content_sha256"] = canonical_json_sha256(content)

    with pytest.raises(AssuranceEnvelopeError, match="unknown evidence"):
        validate_assurance_envelope(envelope, artifact_roots=tmp_path)


def test_assurance_envelope_rejects_multiple_ids_for_one_artifact_path(
    tmp_path: Path,
) -> None:
    envelope = _build_ready_envelope(tmp_path)
    source_receipt = dict(envelope["artifact_receipts"][0])
    source_receipt["artifact_id"] = "source.alias"
    envelope["artifact_receipts"].append(source_receipt)
    content = dict(envelope)
    content.pop("content_sha256")
    envelope["content_sha256"] = canonical_json_sha256(content)

    with pytest.raises(AssuranceEnvelopeError, match="multiple identities"):
        validate_assurance_envelope(envelope, artifact_roots=tmp_path)


def test_assurance_envelope_passed_source_gate_covers_every_qualification(
    tmp_path: Path,
) -> None:
    envelope = _build_ready_envelope(tmp_path)
    envelope["source_qualifications"].append(
        build_source_qualification(
            qualification_id="source.pending",
            adapter_id="native_journal",
            adapter_version="v1",
            source_family="native_rowwise_journal",
            status="needs_review",
            source_artifact_refs=["source.workbook"],
            candidate_row_count=1,
            emitted_row_count=0,
            controls=[_control("reviewed_mapping", status="not_assessed")],
        )
    )
    content = dict(envelope)
    content.pop("content_sha256")
    envelope["content_sha256"] = canonical_json_sha256(content)

    with pytest.raises(
        AssuranceEnvelopeError,
        match="every source qualification",
    ):
        validate_assurance_envelope(envelope, artifact_roots=tmp_path)


def test_assurance_envelope_passed_semantic_gate_requires_reviewed_decision(
    tmp_path: Path,
) -> None:
    envelope = _build_ready_envelope(tmp_path)
    pending_decision = build_reviewed_decision_receipt(
        decision_id="decision.pending_review",
        decision_type="professional_review",
        status="draft",
        reviewer_ref="reviewer.partner",
        reviewed_on="2026-07-24",
        adapter_id="report_builder",
        adapter_version="v1",
        source_artifact_refs=["source.workbook"],
        content={"conclusion": "pending"},
    )
    envelope["reviewed_decisions"].append(pending_decision)
    envelope["gate_register"]["gates"]["semantic_review"]["evidence_refs"] = [
        "decision.pending_review"
    ]
    content = dict(envelope)
    content.pop("content_sha256")
    envelope["content_sha256"] = canonical_json_sha256(content)

    with pytest.raises(AssuranceEnvelopeError, match="reviewed professional"):
        validate_assurance_envelope(envelope, artifact_roots=tmp_path)


def test_assurance_envelope_mapping_decision_cannot_pass_semantic_gate(
    tmp_path: Path,
) -> None:
    envelope = _build_ready_envelope(tmp_path)
    envelope["gate_register"]["gates"]["semantic_review"]["evidence_refs"] = [
        "decision.coa_mapping"
    ]
    content = dict(envelope)
    content.pop("content_sha256")
    envelope["content_sha256"] = canonical_json_sha256(content)

    with pytest.raises(AssuranceEnvelopeError, match="reviewed professional"):
        validate_assurance_envelope(envelope, artifact_roots=tmp_path)


@pytest.mark.parametrize(
    ("gate_name", "wrong_ref", "message"),
    [
        (
            "preparation",
            "source.workbook",
            "prepared or work-product evidence",
        ),
        (
            "reconciliation",
            "source.qualification",
            "relationship ledger, numeric evidence ledger",
        ),
        (
            "reporting",
            "source.workbook",
            "report or numeric-ledger evidence",
        ),
        (
            "publication",
            "source.qualification",
            "publication evidence or reviewed publication authority",
        ),
    ],
)
def test_assurance_envelope_passed_gate_rejects_wrong_evidence_class(
    tmp_path: Path,
    gate_name: str,
    wrong_ref: str,
    message: str,
) -> None:
    envelope = _build_ready_envelope(tmp_path)
    envelope["gate_register"]["gates"][gate_name]["status"] = "passed"
    envelope["gate_register"]["gates"][gate_name]["evidence_refs"] = [wrong_ref]
    content = dict(envelope)
    content.pop("content_sha256")
    envelope["content_sha256"] = canonical_json_sha256(content)

    with pytest.raises(AssuranceEnvelopeError, match=message):
        validate_assurance_envelope(envelope, artifact_roots=tmp_path)
