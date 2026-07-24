from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SCRIPTS_ROOT = CLARA_ROOT / "scripts"
INTAKE_SCHEMA_PATH = CLARA_ROOT / "contracts" / "real_data_pilot_intake.v1.schema.json"
RECEIPT_SCHEMA_PATH = (
    CLARA_ROOT / "contracts" / "real_data_pilot_intake_receipt.v1.schema.json"
)
INTAKE_SCHEMA_V2_PATH = (
    CLARA_ROOT / "contracts" / "real_data_pilot_intake.v2.schema.json"
)
RECEIPT_SCHEMA_V2_PATH = (
    CLARA_ROOT / "contracts" / "real_data_pilot_intake_receipt.v2.schema.json"
)
VALIDATION_DATE = "2026-07-23"
SOURCE_BYTES = b"synthetic unit-test bytes; not a commercial trial balance\n"


def _load_module(name: str, path: Path) -> Any:
    scripts_path = str(SCRIPTS_ROOT)
    inserted = scripts_path not in sys.path
    if inserted:
        sys.path.insert(0, scripts_path)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_path)


VALIDATOR = _load_module(
    "clara_real_data_pilot_intake_test",
    SCRIPTS_ROOT / "validate_real_data_pilot_intake.py",
)


def _schema_validator(path: Path) -> jsonschema.Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )


def test_v2_receipt_schema_names_the_v2_authoritative_validator() -> None:
    schema = json.loads(RECEIPT_SCHEMA_V2_PATH.read_text(encoding="utf-8"))

    assert "validate_real_data_pilot_intake_receipt_v2" in schema["$comment"]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _case(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    source_path = tmp_path / "source.xlsx"
    source_path.write_bytes(SOURCE_BYTES)
    source_sha256 = hashlib.sha256(SOURCE_BYTES).hexdigest()
    intake = {
        "schema_version": "clara.real_data_pilot_intake.v1",
        "pilot_id": "pilot-0123456789abcdef",
        "purpose": "local_due_diligence_preparation_evaluation",
        "source": {
            "source_id": "source-0123456789abcdef",
            "data_kind": "commercial_trial_balance",
            "data_classification": "consented_real",
            "media_type": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            "byte_count": len(SOURCE_BYTES),
            "sha256": source_sha256,
        },
        "authorization": {
            "status": "reviewed",
            "basis": "explicit_authorized_user_instruction",
            "authority_assertion": "authorizer_has_right_to_permit_this_use",
            "evidence_reference": "unit-test-only authorization declaration",
            "authorizing_role": "unit-test fixture",
            "authorized_on": VALIDATION_DATE,
            "valid_from": VALIDATION_DATE,
            "valid_until": None,
            "purpose": "local_due_diligence_preparation_evaluation",
            "authorized_source_sha256": source_sha256,
            "permitted_actions": [
                "codex_model_processing",
                "local_deterministic_processing",
            ],
            "prohibited_actions": [
                "commit_raw_or_row_level_data",
                "package_raw_or_row_level_data",
                "publish_raw_or_row_level_data",
            ],
            "terms_summary": (
                "Synthetic unit-test declaration; no real-data permission is claimed."
            ),
        },
        "privacy": {
            "codex_context_acknowledged": True,
            "automatic_anonymization_claimed": False,
            "clara_external_recipient_added": False,
            "raw_and_row_level_storage": "local_run_root_only",
            "repository_recording_policy": "sanitized_summary_and_receipts_only",
        },
        "deidentification_review": {
            "status": "not_applicable",
            "basis": "Unit-test contract uses no real data.",
            "reidentification_risk_review_status": "not_applicable",
        },
        "semantic_review_plan": {
            "status": "pending",
            "required_reviews": [
                "account_mapping",
                "control_equivalence_and_tolerance",
                "currency_unit_and_fx",
                "dataset_identity_and_grain",
                "period_calendar_and_value_basis",
                "scope_entity_and_eliminations",
                "sign_convention",
            ],
            "automatic_mapping_allowed": False,
            "unresolved_blocking_issues_block_preparation": True,
        },
        "publication_status": "withheld",
        "report_ready": False,
    }
    intake_path = tmp_path / "intake.json"
    _write_json(intake_path, intake)
    return intake_path, source_path, intake


def _validate(tmp_path: Path) -> dict[str, Any]:
    intake_path, source_path, _ = _case(tmp_path)
    return _run_intake(intake_path, source_path)


def _run_intake(
    intake_path: Path,
    source_path: Path,
    *,
    as_of_date: str = VALIDATION_DATE,
) -> dict[str, Any]:
    return VALIDATOR.validate_real_data_pilot_intake(
        intake_path,
        source_path,
        as_of_date=as_of_date,
        local_run_root=intake_path.parent,
        repository_root=ROOT,
    )


def _general_ledger_case(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    intake_path, source_path, intake = _case(tmp_path)
    intake["schema_version"] = "clara.real_data_pilot_intake.v2"
    intake["source"]["data_kind"] = "commercial_general_ledger"
    _write_json(intake_path, intake)
    return intake_path, source_path, intake


def _run_intake_v2(
    intake_path: Path,
    source_path: Path,
    *,
    as_of_date: str = VALIDATION_DATE,
) -> dict[str, Any]:
    return VALIDATOR.validate_real_data_pilot_intake_v2(
        intake_path,
        source_path,
        as_of_date=as_of_date,
        local_run_root=intake_path.parent,
        repository_root=ROOT,
    )


def test_real_data_pilot_intake_emits_valid_sanitized_receipt(
    tmp_path: Path,
) -> None:
    receipt = _validate(tmp_path)

    _schema_validator(RECEIPT_SCHEMA_PATH).validate(receipt)
    assert receipt["eligibility"] == {
        "status": "declared_boundary_passed_for_local_pilot_intake",
        "purpose": "local_due_diligence_preparation_evaluation",
        "publication_status": "withheld",
        "report_ready": False,
        "execution_revalidation_required": True,
        "does_not_establish": list(VALIDATOR.DOES_NOT_ESTABLISH),
    }
    assert receipt["semantic_review"]["status"] == "not_assessed"
    assert receipt["authorization_receipt"]["assurance"] == (
        "declaration_bound_to_exact_source_not_independently_verified"
    )
    assert (
        receipt["authorization_receipt"]["authorized_source_sha256"]
        == receipt["source_receipt"]["sha256"]
    )
    assert "evidence_reference" not in receipt["authorization_receipt"]
    assert receipt["privacy_boundary"]["storage_location_check"] == {
        "status": "passed_at_validation",
        "source_relation": "outside_repository_within_run_root",
        "intake_relation": "outside_repository_within_run_root",
        "resolved_path_containment_enforced": True,
        "git_ignore_required_inside_repository": True,
    }
    assert str(tmp_path) not in json.dumps(receipt)
    assert SOURCE_BYTES.decode("utf-8").strip() not in json.dumps(receipt)


def test_frozen_v1_schema_and_runtime_reject_general_ledger(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["source"]["data_kind"] = "commercial_general_ledger"
    _write_json(intake_path, intake)

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(INTAKE_SCHEMA_PATH).validate(intake)
    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="source.data_kind is not registered",
    ):
        _run_intake(intake_path, source_path)


def test_v2_schema_and_runtime_preserve_general_ledger_declaration(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _general_ledger_case(tmp_path)

    _schema_validator(INTAKE_SCHEMA_V2_PATH).validate(intake)
    receipt = _run_intake_v2(intake_path, source_path)
    _schema_validator(RECEIPT_SCHEMA_V2_PATH).validate(receipt)

    assert receipt["schema_version"] == VALIDATOR.INTAKE_RECEIPT_SCHEMA_V2
    assert (
        receipt["source_receipt"]["declared_data_kind"] == "commercial_general_ledger"
    )
    assert receipt["semantic_review"]["status"] == "not_assessed"
    assert receipt["eligibility"]["publication_status"] == "withheld"
    assert receipt["eligibility"]["report_ready"] is False
    assert receipt["eligibility"]["does_not_establish"] == list(
        VALIDATOR.DOES_NOT_ESTABLISH_V2
    )


def test_v2_schema_and_runtime_reject_unregistered_generic_source_kind(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _general_ledger_case(tmp_path)
    intake["source"]["data_kind"] = "general_ledger"
    _write_json(intake_path, intake)

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(INTAKE_SCHEMA_V2_PATH).validate(intake)
    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="source.data_kind is not registered",
    ):
        _run_intake_v2(intake_path, source_path)


def test_real_data_pilot_intake_schema_accepts_registered_contract(
    tmp_path: Path,
) -> None:
    _, _, intake = _case(tmp_path)

    _schema_validator(INTAKE_SCHEMA_PATH).validate(intake)


@pytest.mark.parametrize(
    ("schema_path", "payload_kind", "field_path"),
    [
        (INTAKE_SCHEMA_PATH, "intake", ("pilot_id",)),
        (INTAKE_SCHEMA_PATH, "intake", ("source", "source_id")),
        (INTAKE_SCHEMA_PATH, "intake", ("source", "sha256")),
        (RECEIPT_SCHEMA_PATH, "receipt", ("pilot_id",)),
        (RECEIPT_SCHEMA_PATH, "receipt", ("source_receipt", "source_id")),
        (RECEIPT_SCHEMA_PATH, "receipt", ("source_receipt", "sha256")),
    ],
)
def test_real_data_pilot_intake_schemas_reject_terminal_newline_in_ids_and_sha(
    tmp_path: Path,
    schema_path: Path,
    payload_kind: str,
    field_path: tuple[str, ...],
) -> None:
    if payload_kind == "intake":
        _, _, payload = _case(tmp_path)
    else:
        payload = _validate(tmp_path)
    target: dict[str, Any] = payload
    for field in field_path[:-1]:
        target = target[field]
    terminal_field = field_path[-1]
    target[terminal_field] = f"{target[terminal_field]}\n"

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(schema_path).validate(payload)


def test_real_data_pilot_intake_receipt_is_byte_deterministic(
    tmp_path: Path,
) -> None:
    first = json.dumps(
        _validate(tmp_path),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    second = json.dumps(
        _validate(tmp_path),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert first == second


def test_intake_receipt_schema_rejects_anonymized_without_review(
    tmp_path: Path,
) -> None:
    receipt = _validate(tmp_path)
    receipt["source_receipt"]["declared_data_classification"] = "anonymized_real"

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(RECEIPT_SCHEMA_PATH).validate(receipt)


def test_intake_receipt_hash_identifies_the_validated_json_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_path, source_path, _ = _case(tmp_path)
    original_bytes = intake_path.read_bytes()
    original_file_sha256 = VALIDATOR.file_sha256
    mutated = False

    def _mutate_after_snapshot(path: Path) -> str:
        nonlocal mutated
        if not mutated:
            intake_path.write_text('{"authorization":"draft"}\n', encoding="utf-8")
            mutated = True
        return original_file_sha256(path)

    monkeypatch.setattr(VALIDATOR, "file_sha256", _mutate_after_snapshot)

    receipt = _run_intake(intake_path, source_path)

    assert (
        receipt["intake_contract_sha256"] == hashlib.sha256(original_bytes).hexdigest()
    )
    assert (
        receipt["intake_contract_sha256"]
        != hashlib.sha256(intake_path.read_bytes()).hexdigest()
    )


def test_anonymized_real_requires_reviewed_deidentification_record(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["source"]["data_classification"] = "anonymized_real"
    _write_json(intake_path, intake)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="anonymized_real requires reviewed",
    ):
        _run_intake(intake_path, source_path)


def test_anonymized_real_accepts_reviewed_deidentification_record(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["source"]["data_classification"] = "anonymized_real"
    intake["deidentification_review"] = {
        "status": "reviewed",
        "basis": "Reviewed de-identification method and retained-field inventory.",
        "reidentification_risk_review_status": "reviewed",
    }
    _write_json(intake_path, intake)

    receipt = _run_intake(intake_path, source_path)

    assert (
        receipt["source_receipt"]["declared_data_classification"] == "anonymized_real"
    )
    assert receipt["deidentification_review"]["status"] == "reviewed"


def test_consented_real_rejects_mixed_deidentification_statuses(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["deidentification_review"]["status"] = "reviewed"
    _write_json(intake_path, intake)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="review statuses must match",
    ):
        _run_intake(intake_path, source_path)


def _set_missing_authorization_status(intake: dict[str, Any]) -> None:
    intake["authorization"].pop("status")


def _set_draft_authorization(intake: dict[str, Any]) -> None:
    intake["authorization"]["status"] = "draft"


def _set_wrong_authorized_digest(intake: dict[str, Any]) -> None:
    intake["authorization"]["authorized_source_sha256"] = "0" * 64


def _set_wrong_purpose(intake: dict[str, Any]) -> None:
    intake["authorization"]["purpose"] = "general_product_development"


def _set_missing_permitted_action(intake: dict[str, Any]) -> None:
    intake["authorization"]["permitted_actions"] = ["local_deterministic_processing"]


def _set_missing_prohibition(intake: dict[str, Any]) -> None:
    intake["authorization"]["prohibited_actions"] = [
        "commit_raw_or_row_level_data",
        "package_raw_or_row_level_data",
    ]


def _set_codex_context_unacknowledged(intake: dict[str, Any]) -> None:
    intake["privacy"]["codex_context_acknowledged"] = False


def _set_automatic_anonymization_claim(intake: dict[str, Any]) -> None:
    intake["privacy"]["automatic_anonymization_claimed"] = True


def _set_external_recipient(intake: dict[str, Any]) -> None:
    intake["privacy"]["clara_external_recipient_added"] = True


def _set_raw_storage_in_repository(intake: dict[str, Any]) -> None:
    intake["privacy"]["raw_and_row_level_storage"] = "repository"


def _set_automatic_mapping_allowed(intake: dict[str, Any]) -> None:
    intake["semantic_review_plan"]["automatic_mapping_allowed"] = True


def _set_blocking_issues_ignored(intake: dict[str, Any]) -> None:
    intake["semantic_review_plan"][
        "unresolved_blocking_issues_block_preparation"
    ] = False


def _set_publication_ready(intake: dict[str, Any]) -> None:
    intake["publication_status"] = "authorized"


def _set_report_ready(intake: dict[str, Any]) -> None:
    intake["report_ready"] = True


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_set_missing_authorization_status, "authorization is missing fields"),
        (_set_draft_authorization, "authorization.status must equal"),
        (_set_wrong_authorized_digest, "authorized_source_sha256 must equal"),
        (_set_wrong_purpose, "authorization.purpose must equal"),
        (_set_missing_permitted_action, "permitted_actions must equal"),
        (_set_missing_prohibition, "prohibited_actions must equal"),
        (_set_codex_context_unacknowledged, "codex_context_acknowledged must equal"),
        (
            _set_automatic_anonymization_claim,
            "automatic_anonymization_claimed must equal",
        ),
        (_set_external_recipient, "clara_external_recipient_added must equal"),
        (_set_raw_storage_in_repository, "raw_and_row_level_storage must equal"),
        (_set_automatic_mapping_allowed, "automatic_mapping_allowed must equal"),
        (
            _set_blocking_issues_ignored,
            "unresolved_blocking_issues_block_preparation must equal",
        ),
        (_set_publication_ready, "publication_status must equal"),
        (_set_report_ready, "report_ready must equal"),
    ],
)
def test_real_data_pilot_intake_rejects_boundary_mutation(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    intake_path, source_path, original = _case(tmp_path)
    intake = copy.deepcopy(original)
    mutation(intake)
    _write_json(intake_path, intake)

    with pytest.raises(VALIDATOR.ContractValidationError, match=message):
        _run_intake(intake_path, source_path)


def test_real_data_pilot_intake_rejects_source_digest_drift(
    tmp_path: Path,
) -> None:
    intake_path, source_path, _ = _case(tmp_path)
    source_path.write_bytes(SOURCE_BYTES + b"changed")

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="byte_count does not match",
    ):
        _run_intake(intake_path, source_path)


def test_real_data_pilot_intake_rejects_source_digest_mismatch_at_same_size(
    tmp_path: Path,
) -> None:
    intake_path, source_path, _ = _case(tmp_path)
    source_path.write_bytes(b"x" * len(SOURCE_BYTES))

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="sha256 does not match",
    ):
        _run_intake(intake_path, source_path)


def test_real_data_pilot_intake_rejects_expired_authorization(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["authorization"]["valid_from"] = "2026-07-01"
    intake["authorization"]["valid_until"] = "2026-07-22"
    _write_json(intake_path, intake)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="authorization has expired",
    ):
        _run_intake(intake_path, source_path)


def test_real_data_pilot_intake_rejects_future_authorization(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["authorization"]["authorized_on"] = "2026-07-24"
    _write_json(intake_path, intake)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="cannot follow the validation date",
    ):
        _run_intake(intake_path, source_path)


def test_real_data_pilot_intake_rejects_duplicate_json_field(
    tmp_path: Path,
) -> None:
    intake_path, source_path, _ = _case(tmp_path)
    intake_path.write_text(
        '{"schema_version":"clara.real_data_pilot_intake.v1",'
        '"schema_version":"duplicate"}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="duplicate JSON field",
    ):
        _run_intake(intake_path, source_path)


def test_real_data_pilot_intake_rejects_binary_float(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["unexpected_float"] = 0.1
    _write_json(intake_path, intake)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="JSON fractional or exponent number",
    ):
        _run_intake(intake_path, source_path)


def test_invalid_authorization_is_rejected_before_source_bytes_are_hashed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["authorization"]["status"] = "draft"
    _write_json(intake_path, intake)

    def _unexpected_hash(_: Path) -> str:
        raise AssertionError("source bytes must not be hashed before authorization")

    monkeypatch.setattr(VALIDATOR, "file_sha256", _unexpected_hash)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="authorization.status must equal",
    ):
        _run_intake(intake_path, source_path)


@pytest.mark.parametrize(
    ("field_path", "sensitive_value"),
    [
        (("pilot_id",), "Acme_Corp_DD"),
        (("source", "source_id"), "Acme_Trial_Balance"),
    ],
)
def test_real_data_pilot_intake_rejects_identifying_receipt_ids(
    tmp_path: Path,
    field_path: tuple[str, ...],
    sensitive_value: str,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    if len(field_path) == 1:
        intake[field_path[0]] = sensitive_value
    else:
        intake[field_path[0]][field_path[1]] = sensitive_value
    _write_json(intake_path, intake)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="opaque digest-shaped ID",
    ):
        _run_intake(intake_path, source_path)


def test_real_data_pilot_intake_runtime_rejects_padded_identifier(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["pilot_id"] = f" {intake['pilot_id']} "
    _write_json(intake_path, intake)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="without edge whitespace",
    ):
        _run_intake(intake_path, source_path)


def test_real_data_pilot_intake_schema_rejects_padded_identifier(
    tmp_path: Path,
) -> None:
    _, _, intake = _case(tmp_path)
    intake["pilot_id"] = f" {intake['pilot_id']} "

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(INTAKE_SCHEMA_PATH).validate(intake)


def test_real_data_pilot_intake_schema_and_runtime_reject_trailing_newline_text(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["authorization"]["evidence_reference"] = "review record\n"
    _write_json(intake_path, intake)

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(INTAKE_SCHEMA_PATH).validate(intake)
    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="without edge whitespace",
    ):
        _run_intake(intake_path, source_path)


def test_real_data_pilot_intake_schema_and_runtime_reject_integer_for_boolean(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["report_ready"] = 0
    _write_json(intake_path, intake)

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(INTAKE_SCHEMA_PATH).validate(intake)
    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="report_ready must equal",
    ):
        _run_intake(intake_path, source_path)


def test_real_data_pilot_intake_rejects_arbitrary_media_type(
    tmp_path: Path,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    intake["source"]["media_type"] = "Acme confidential trial balance"
    _write_json(intake_path, intake)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="media_type is not registered",
    ):
        _run_intake(intake_path, source_path)


def test_real_data_pilot_intake_rejects_source_outside_run_root(
    tmp_path: Path,
) -> None:
    intake_path, source_path, _ = _case(tmp_path)
    narrower_run_root = tmp_path / "run"
    narrower_run_root.mkdir()
    moved_intake_path = narrower_run_root / intake_path.name
    intake_path.replace(moved_intake_path)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="source path must resolve inside",
    ):
        VALIDATOR.validate_real_data_pilot_intake(
            moved_intake_path,
            source_path,
            as_of_date=VALIDATION_DATE,
            local_run_root=narrower_run_root,
            repository_root=ROOT,
        )


def test_real_data_pilot_intake_rejects_tracked_repository_source(
    tmp_path: Path,
) -> None:
    ignored_parent = ROOT / "out"
    assert ignored_parent.is_dir()
    with TemporaryDirectory(
        prefix="clara-m6-intake-location-test-",
        dir=ignored_parent,
    ) as raw_dir:
        intake_path, _, _ = _case(Path(raw_dir))
        tracked_source = CLARA_ROOT / "scripts" / "validate_real_data_pilot_intake.py"

        with pytest.raises(
            VALIDATOR.ContractValidationError,
            match="source path is inside the repository but is not Git-ignored",
        ):
            VALIDATOR.validate_real_data_pilot_intake(
                intake_path,
                tracked_source,
                as_of_date=VALIDATION_DATE,
                local_run_root=ROOT,
                repository_root=ROOT,
            )


def test_real_data_pilot_intake_rejects_unrelated_repository_root(
    tmp_path: Path,
) -> None:
    ignored_parent = ROOT / "out"
    assert ignored_parent.is_dir()
    unrelated_repository = tmp_path / "unrelated-repository"
    (unrelated_repository / ".git").mkdir(parents=True)
    with TemporaryDirectory(
        prefix="clara-m6-repository-substitution-test-",
        dir=ignored_parent,
    ) as raw_dir:
        intake_path, source_path, _ = _case(Path(raw_dir))

        with pytest.raises(
            VALIDATOR.ContractValidationError,
            match="must match the Git worktree enclosing local_run_root",
        ):
            VALIDATOR.validate_real_data_pilot_intake(
                intake_path,
                source_path,
                as_of_date=VALIDATION_DATE,
                local_run_root=Path(raw_dir),
                repository_root=unrelated_repository,
            )


def test_real_data_pilot_intake_rejects_source_in_nested_git_worktree(
    tmp_path: Path,
) -> None:
    intake_path, source_path, _ = _case(tmp_path)
    nested_repository = tmp_path / "nested-repository"
    (nested_repository / ".git").mkdir(parents=True)
    nested_source = nested_repository / source_path.name
    source_path.replace(nested_source)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="must not be inside an undeclared Git worktree",
    ):
        _run_intake(intake_path, nested_source)


def test_real_data_pilot_intake_rejects_ignored_hardlink_alias(
    tmp_path: Path,
) -> None:
    ignored_parent = ROOT / "out"
    assert ignored_parent.is_dir()
    tracked_source = CLARA_ROOT / "scripts" / "validate_real_data_pilot_intake.py"
    with TemporaryDirectory(
        prefix="clara-m6-hardlink-test-",
        dir=ignored_parent,
    ) as raw_dir:
        run_root = Path(raw_dir)
        intake_path, _, _ = _case(run_root)
        alias_path = run_root / "tracked-source-alias.py"
        try:
            alias_path.hardlink_to(tracked_source)

            with pytest.raises(
                VALIDATOR.ContractValidationError,
                match="must not be a hard-linked file",
            ):
                VALIDATOR.validate_real_data_pilot_intake(
                    intake_path,
                    alias_path,
                    as_of_date=VALIDATION_DATE,
                    local_run_root=run_root,
                    repository_root=ROOT,
                )
        finally:
            alias_path.unlink(missing_ok=True)


@pytest.mark.parametrize("collision_target", ["source", "intake"])
def test_real_data_pilot_intake_cli_rejects_output_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collision_target: str,
) -> None:
    intake_path, source_path, _ = _case(tmp_path)
    target_path = source_path if collision_target == "source" else intake_path
    original_bytes = target_path.read_bytes()
    monkeypatch.setattr(
        VALIDATOR,
        "_current_date",
        lambda: VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="output path must not equal",
    ):
        VALIDATOR.main(
            [
                "--intake",
                str(intake_path),
                "--source",
                str(source_path),
                "--local-run-root",
                str(tmp_path),
                "--repository-root",
                str(ROOT),
                "--output",
                str(target_path),
            ]
        )

    assert target_path.read_bytes() == original_bytes


def test_real_data_pilot_intake_cli_requires_fresh_output_and_preserves_prior_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_path, source_path, intake = _case(tmp_path)
    output_path = tmp_path / "receipt.json"
    monkeypatch.setattr(
        VALIDATOR,
        "_current_date",
        lambda: VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )
    arguments = [
        "--intake",
        str(intake_path),
        "--source",
        str(source_path),
        "--local-run-root",
        str(tmp_path),
        "--repository-root",
        str(ROOT),
        "--output",
        str(output_path),
    ]
    assert VALIDATOR.main(arguments) == 0
    prior_receipt = output_path.read_bytes()
    intake["authorization"]["status"] = "draft"
    _write_json(intake_path, intake)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="output path must be absent",
    ):
        VALIDATOR.main(arguments)

    assert output_path.read_bytes() == prior_receipt


def test_real_data_pilot_intake_cli_refuses_unowned_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_path, source_path, _ = _case(tmp_path)
    output_path = tmp_path / "do-not-overwrite.txt"
    original_bytes = b"unrelated local content\n"
    output_path.write_bytes(original_bytes)
    monkeypatch.setattr(
        VALIDATOR,
        "_current_date",
        lambda: VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="output path must be absent",
    ):
        VALIDATOR.main(
            [
                "--intake",
                str(intake_path),
                "--source",
                str(source_path),
                "--local-run-root",
                str(tmp_path),
                "--repository-root",
                str(ROOT),
                "--output",
                str(output_path),
            ]
        )

    assert output_path.read_bytes() == original_bytes


def test_real_data_pilot_intake_cli_refuses_symlink_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_path, source_path, _ = _case(tmp_path)
    target_path = tmp_path / "symlink-target.txt"
    original_bytes = b"target must remain unchanged\n"
    target_path.write_bytes(original_bytes)
    output_path = tmp_path / "intake-output-link.json"
    output_path.symlink_to(target_path)
    monkeypatch.setattr(
        VALIDATOR,
        "_current_date",
        lambda: VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="must not use a symlink|must not identify a symlink",
    ):
        VALIDATOR.main(
            [
                "--intake",
                str(intake_path),
                "--source",
                str(source_path),
                "--local-run-root",
                str(tmp_path),
                "--repository-root",
                str(ROOT),
                "--output",
                str(output_path),
            ]
        )

    assert target_path.read_bytes() == original_bytes


def test_real_data_pilot_intake_receipt_rejects_dependency_digest_drift(
    tmp_path: Path,
) -> None:
    receipt = _validate(tmp_path)
    receipt["validator"]["dependency_sha256"]["intake_schema"] = "0" * 64

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="intake_schema is not current",
    ):
        VALIDATOR.validate_real_data_pilot_intake_receipt(receipt)


def test_real_data_pilot_intake_receipt_rejects_authorized_source_drift(
    tmp_path: Path,
) -> None:
    receipt = _validate(tmp_path)
    receipt["authorization_receipt"]["authorized_source_sha256"] = "0" * 64

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="authorization is not bound to the source digest",
    ):
        VALIDATOR.validate_real_data_pilot_intake_receipt(receipt)


def test_real_data_pilot_intake_cli_writes_only_sanitized_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_path, source_path, _ = _case(tmp_path)
    output_path = tmp_path / "receipt.json"
    monkeypatch.setattr(
        VALIDATOR,
        "_current_date",
        lambda: VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )

    result = VALIDATOR.main(
        [
            "--intake",
            str(intake_path),
            "--source",
            str(source_path),
            "--local-run-root",
            str(tmp_path),
            "--repository-root",
            str(ROOT),
            "--output",
            str(output_path),
        ]
    )

    assert result == 0
    receipt = json.loads(output_path.read_text(encoding="utf-8"))
    _schema_validator(RECEIPT_SCHEMA_PATH).validate(receipt)
    assert receipt["eligibility"]["report_ready"] is False


def test_real_data_pilot_intake_cli_v2_writes_general_ledger_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_path, source_path, _ = _general_ledger_case(tmp_path)
    output_path = tmp_path / "receipt-v2.json"
    monkeypatch.setattr(
        VALIDATOR,
        "_current_date",
        lambda: VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )

    result = VALIDATOR.main(
        [
            "--contract-version",
            "v2",
            "--intake",
            str(intake_path),
            "--source",
            str(source_path),
            "--local-run-root",
            str(tmp_path),
            "--repository-root",
            str(ROOT),
            "--output",
            str(output_path),
        ]
    )

    assert result == 0
    receipt = json.loads(output_path.read_text(encoding="utf-8"))
    _schema_validator(RECEIPT_SCHEMA_V2_PATH).validate(receipt)
    assert (
        receipt["source_receipt"]["declared_data_kind"] == "commercial_general_ledger"
    )
    assert receipt["eligibility"]["report_ready"] is False


def test_pinned_receipt_writer_rejects_same_length_in_place_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "mutated-receipt.json"
    original_read = VALIDATOR._read_descriptor_bytes
    tampered = False

    def mutate_before_read(descriptor: int) -> bytes:
        nonlocal tampered
        current = VALIDATOR.os.pread(descriptor, 4096, 0)
        replacement = current.replace(b"123456", b"654321")
        assert replacement != current
        VALIDATOR.os.pwrite(descriptor, replacement, 0)
        VALIDATOR.os.fsync(descriptor)
        tampered = True
        return original_read(descriptor)

    monkeypatch.setattr(
        VALIDATOR,
        "_read_descriptor_bytes",
        mutate_before_read,
    )

    with VALIDATOR.pinned_pilot_receipt_output(
        output_path,
        local_run_root=tmp_path,
    ) as pinned_output:
        with pytest.raises(
            VALIDATOR.ContractValidationError,
            match="output bytes changed during the write",
        ):
            pinned_output.write_json({"marker": 123456})

    assert tampered is True
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"marker": 654321}


def test_pinned_receipt_writer_rereads_bytes_after_parent_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "late-mutated-receipt.json"
    original_fsync = VALIDATOR.os.fsync
    tampered = False

    with VALIDATOR.pinned_pilot_receipt_output(
        output_path,
        local_run_root=tmp_path,
    ) as pinned_output:

        def mutate_on_parent_fsync(descriptor: int) -> None:
            nonlocal tampered
            original_fsync(descriptor)
            if descriptor != pinned_output._parent_descriptor or tampered:
                return
            output_descriptor = VALIDATOR.os.open(
                output_path.name,
                VALIDATOR.os.O_RDWR | VALIDATOR.os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            try:
                current = VALIDATOR.os.pread(output_descriptor, 4096, 0)
                replacement = current.replace(b"123456", b"654321")
                assert replacement != current
                VALIDATOR.os.pwrite(output_descriptor, replacement, 0)
                original_fsync(output_descriptor)
            finally:
                VALIDATOR.os.close(output_descriptor)
            tampered = True

        monkeypatch.setattr(VALIDATOR.os, "fsync", mutate_on_parent_fsync)

        with pytest.raises(
            VALIDATOR.ContractValidationError,
            match="output changed before write completion",
        ):
            pinned_output.write_json({"marker": 123456})

    assert tampered is True


def test_pinned_receipt_writer_rechecks_parent_after_final_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt_directory = tmp_path / "receipts"
    receipt_directory.mkdir()
    pinned_directory = tmp_path / "receipts-pinned"
    output_path = receipt_directory / "late-parent-swap.json"
    original_read = VALIDATOR._read_descriptor_bytes
    read_count = 0

    with TemporaryDirectory(
        prefix="clara-m6-late-output-race-",
        dir=tmp_path.parent,
    ) as raw_outside_directory:
        outside_directory = Path(raw_outside_directory)

        def swap_parent_on_final_read(descriptor: int) -> bytes:
            nonlocal read_count
            read_count += 1
            if read_count == 2:
                receipt_directory.rename(pinned_directory)
                receipt_directory.symlink_to(
                    outside_directory,
                    target_is_directory=True,
                )
            return original_read(descriptor)

        monkeypatch.setattr(
            VALIDATOR,
            "_read_descriptor_bytes",
            swap_parent_on_final_read,
        )

        with VALIDATOR.pinned_pilot_receipt_output(
            output_path,
            local_run_root=tmp_path,
        ) as pinned_output:
            with pytest.raises(
                VALIDATOR.ContractValidationError,
                match="output directory path changed during receipt write",
            ):
                pinned_output.write_json({"marker": 123456})

        assert read_count == 2
        assert not (outside_directory / output_path.name).exists()
        assert (pinned_directory / output_path.name).is_file()


@pytest.mark.parametrize("contract_version", ["v1", "v2"])
def test_real_data_pilot_intake_cli_parent_symlink_swap_cannot_escape_run_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contract_version: str,
) -> None:
    if contract_version == "v2":
        intake_path, source_path, _ = _general_ledger_case(tmp_path)
    else:
        intake_path, source_path, _ = _case(tmp_path)
    receipt_directory = tmp_path / "receipts"
    receipt_directory.mkdir()
    pinned_directory = tmp_path / "receipts-pinned"
    output_path = receipt_directory / "intake-receipt.json"
    monkeypatch.setattr(
        VALIDATOR,
        "_current_date",
        lambda: VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )

    with TemporaryDirectory(
        prefix="clara-m6-intake-output-race-",
        dir=tmp_path.parent,
    ) as raw_outside_directory:
        outside_directory = Path(raw_outside_directory)
        outside_output = outside_directory / output_path.name
        original_open = VALIDATOR.os.open
        swapped = False

        def _swap_parent_then_open(
            path: str | Path,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            nonlocal swapped
            if (
                not swapped
                and path == output_path.name
                and flags & VALIDATOR.os.O_CREAT
            ):
                receipt_directory.rename(pinned_directory)
                receipt_directory.symlink_to(
                    outside_directory,
                    target_is_directory=True,
                )
                swapped = True
            return original_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(VALIDATOR.os, "open", _swap_parent_then_open)
        arguments = [
            "--contract-version",
            contract_version,
            "--intake",
            str(intake_path),
            "--source",
            str(source_path),
            "--local-run-root",
            str(tmp_path),
            "--repository-root",
            str(ROOT),
            "--output",
            str(output_path),
        ]

        with pytest.raises(
            VALIDATOR.ContractValidationError,
            match="output directory path changed during receipt write",
        ):
            VALIDATOR.main(arguments)

        assert swapped is True
        assert not outside_output.exists()
        assert (pinned_directory / output_path.name).is_file()
