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
SEMANTIC_SCHEMA_PATH = (
    CLARA_ROOT / "contracts" / "real_data_pilot_semantic_review.v1.schema.json"
)
SEMANTIC_RECEIPT_SCHEMA_PATH = (
    CLARA_ROOT / "contracts" / "real_data_pilot_semantic_review_receipt.v1.schema.json"
)
VALIDATION_DATE = "2026-07-23"
SOURCE_BYTES = b"synthetic unit-test bytes; not commercial accounting data\n"


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


INTAKE_VALIDATOR = _load_module(
    "validate_real_data_pilot_intake",
    SCRIPTS_ROOT / "validate_real_data_pilot_intake.py",
)
SEMANTIC_VALIDATOR = _load_module(
    "clara_real_data_pilot_semantic_review_test",
    SCRIPTS_ROOT / "validate_real_data_pilot_semantic_review.py",
)


def _schema_validator(path: Path) -> jsonschema.Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _intake_contract(
    source_sha256: str,
    byte_count: int,
    *,
    schema_version: str = "clara.real_data_pilot_intake.v1",
    data_kind: str = "commercial_trial_balance",
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "pilot_id": "pilot-0123456789abcdef",
        "purpose": "local_due_diligence_preparation_evaluation",
        "source": {
            "source_id": "source-0123456789abcdef",
            "data_kind": data_kind,
            "data_classification": "consented_real",
            "media_type": "text/csv",
            "byte_count": byte_count,
            "sha256": source_sha256,
        },
        "authorization": {
            "status": "reviewed",
            "basis": "explicit_authorized_user_instruction",
            "authority_assertion": "authorizer_has_right_to_permit_this_use",
            "evidence_reference": "Synthetic unit-test declaration.",
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
                "Synthetic unit-test declaration; no real permission is claimed."
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
            "required_reviews": list(INTAKE_VALIDATOR.REQUIRED_SEMANTIC_REVIEWS),
            "automatic_mapping_allowed": False,
            "unresolved_blocking_issues_block_preparation": True,
        },
        "publication_status": "withheld",
        "report_ready": False,
    }


def _evidence_registry(tmp_path: Path) -> dict[str, dict[str, Any]]:
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    registry: dict[str, dict[str, Any]] = {}
    evidence_ids = [
        *(f"evidence-{position:02d}" for position in range(1, 8)),
        "evidence-issue-01",
    ]
    for evidence_id in evidence_ids:
        payload = f"Synthetic unit-test evidence for {evidence_id}.\n".encode()
        relative_path = Path("evidence") / f"{evidence_id}.txt"
        (tmp_path / relative_path).write_bytes(payload)
        registry[evidence_id] = {
            "path": relative_path.as_posix(),
            "media_type": "text/plain",
            "byte_count": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    return registry


def _semantic_review(
    intake_receipt_sha256: str,
    evidence_registry: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    required_reviews = []
    for position, topic in enumerate(
        INTAKE_VALIDATOR.REQUIRED_SEMANTIC_REVIEWS,
        start=1,
    ):
        required_reviews.append(
            {
                "review_id": f"topic-review-{position:02d}",
                "topic": topic,
                "status": "reviewed",
                "decision": f"Unit-test reviewer decision for {topic}.",
                "basis": f"Unit-test evidence for {topic}.",
                "evidence_refs": [f"evidence-{position:02d}"],
            }
        )
    return {
        "schema_version": "clara.real_data_pilot_semantic_review.v1",
        "pilot_id": "pilot-0123456789abcdef",
        "review_version": "review-fedcba9876543210",
        "review_status": "reviewed",
        "reviewed_on": VALIDATION_DATE,
        "reviewer_role": "unit-test reviewer",
        "intake_receipt_sha256": intake_receipt_sha256,
        "evidence_registry": evidence_registry,
        "required_reviews": required_reviews,
        "issues": {},
        "mechanical_error_register_policy": "producer_owned_separate_artifact",
        "publication_status": "withheld",
        "report_ready": False,
    }


def _case(
    tmp_path: Path,
    *,
    intake_contract_version: str = "v1",
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    source_path = tmp_path / "source.csv"
    source_path.write_bytes(SOURCE_BYTES)
    source_sha256 = hashlib.sha256(SOURCE_BYTES).hexdigest()
    intake_path = tmp_path / "intake.json"
    if intake_contract_version == "v2":
        intake = _intake_contract(
            source_sha256,
            len(SOURCE_BYTES),
            schema_version="clara.real_data_pilot_intake.v2",
            data_kind="commercial_general_ledger",
        )
        validate_intake = INTAKE_VALIDATOR.validate_real_data_pilot_intake_v2
    else:
        intake = _intake_contract(source_sha256, len(SOURCE_BYTES))
        validate_intake = INTAKE_VALIDATOR.validate_real_data_pilot_intake
    _write_json(intake_path, intake)
    intake_receipt = validate_intake(
        intake_path,
        source_path,
        as_of_date=VALIDATION_DATE,
        local_run_root=tmp_path,
        repository_root=ROOT,
    )
    intake_receipt_path = tmp_path / "intake_receipt.json"
    _write_json(intake_receipt_path, intake_receipt)
    intake_receipt_sha256 = hashlib.sha256(intake_receipt_path.read_bytes()).hexdigest()
    semantic_review = _semantic_review(
        intake_receipt_sha256,
        _evidence_registry(tmp_path),
    )
    semantic_review_path = tmp_path / "semantic_review.json"
    _write_json(semantic_review_path, semantic_review)
    return (
        semantic_review_path,
        intake_receipt_path,
        semantic_review,
        intake_receipt,
    )


def _run_review(
    review_path: Path,
    intake_receipt_path: Path,
    *,
    as_of_date: str = VALIDATION_DATE,
) -> dict[str, Any]:
    return SEMANTIC_VALIDATOR.validate_real_data_pilot_semantic_review(
        review_path,
        intake_receipt_path,
        as_of_date=as_of_date,
        local_run_root=review_path.parent,
        repository_root=ROOT,
    )


def _issue(
    *,
    topic: str = "account_mapping",
    status: str = "open",
    blocking: bool = True,
    resolution: str | None = None,
) -> dict[str, Any]:
    return {
        "topic": topic,
        "status": status,
        "blocking": blocking,
        "description": "Unit-test semantic issue description.",
        "basis": "Unit-test reviewer basis.",
        "evidence_refs": ["evidence-issue-01"],
        "resolution": resolution,
    }


def test_semantic_review_emits_valid_sanitized_mechanical_readiness_receipt(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)

    receipt = _run_review(review_path, intake_receipt_path)

    _schema_validator(SEMANTIC_RECEIPT_SCHEMA_PATH).validate(receipt)
    assert receipt["readiness"] == {
        "status": "ready_for_mechanical_preparation_only",
        "mechanical_preparation_allowed": True,
        "semantic_status_for_audit_envelope": "not_assessed",
        "publication_status": "withheld",
        "report_ready": False,
        "execution_revalidation_required": True,
        "does_not_establish": list(SEMANTIC_VALIDATOR.DOES_NOT_ESTABLISH),
    }
    assert receipt["review_summary"]["required_review_count"] == 7
    assert receipt["review_summary"]["evidence_count"] == 8
    assert set(receipt["review_summary"]["issue_counts"].values()) == {0}
    assert "Unit-test reviewer decision" not in json.dumps(receipt)
    assert str(tmp_path) not in json.dumps(receipt)


def test_semantic_review_schema_accepts_registered_contract(
    tmp_path: Path,
) -> None:
    _, _, review, _ = _case(tmp_path)

    _schema_validator(SEMANTIC_SCHEMA_PATH).validate(review)


@pytest.mark.parametrize(
    ("schema_path", "payload_kind", "field_path"),
    [
        (SEMANTIC_SCHEMA_PATH, "review", ("pilot_id",)),
        (SEMANTIC_SCHEMA_PATH, "review", ("review_version",)),
        (SEMANTIC_SCHEMA_PATH, "review", ("intake_receipt_sha256",)),
        (SEMANTIC_RECEIPT_SCHEMA_PATH, "receipt", ("pilot_id",)),
        (SEMANTIC_RECEIPT_SCHEMA_PATH, "receipt", ("review_version",)),
        (
            SEMANTIC_RECEIPT_SCHEMA_PATH,
            "receipt",
            ("semantic_review_sha256",),
        ),
    ],
)
def test_semantic_review_schemas_reject_terminal_newline_in_ids_and_sha(
    tmp_path: Path,
    schema_path: Path,
    payload_kind: str,
    field_path: tuple[str, ...],
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    payload = (
        review
        if payload_kind == "review"
        else _run_review(review_path, intake_receipt_path)
    )
    target: dict[str, Any] = payload
    for field in field_path[:-1]:
        target = target[field]
    terminal_field = field_path[-1]
    target[terminal_field] = f"{target[terminal_field]}\n"

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(schema_path).validate(payload)


def test_semantic_review_schema_rejects_terminal_newline_in_registry_id(
    tmp_path: Path,
) -> None:
    _, _, review, _ = _case(tmp_path)
    evidence_record = review["evidence_registry"].pop("evidence-01")
    review["evidence_registry"]["evidence-01\n"] = evidence_record

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(SEMANTIC_SCHEMA_PATH).validate(review)


def test_semantic_review_receipt_is_byte_deterministic(tmp_path: Path) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)
    first = json.dumps(
        _run_review(review_path, intake_receipt_path),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    second = json.dumps(
        _run_review(review_path, intake_receipt_path),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert first == second


def test_semantic_receipt_hash_identifies_the_validated_json_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)
    original_bytes = review_path.read_bytes()
    original_file_sha256 = SEMANTIC_VALIDATOR.file_sha256
    mutated = False

    def _mutate_after_snapshot(path: Path) -> str:
        nonlocal mutated
        if not mutated:
            review_path.write_text('{"review_status":"draft"}\n', encoding="utf-8")
            mutated = True
        return original_file_sha256(path)

    monkeypatch.setattr(SEMANTIC_VALIDATOR, "file_sha256", _mutate_after_snapshot)

    receipt = _run_review(review_path, intake_receipt_path)

    assert (
        receipt["semantic_review_sha256"] == hashlib.sha256(original_bytes).hexdigest()
    )
    assert (
        receipt["semantic_review_sha256"]
        != hashlib.sha256(review_path.read_bytes()).hexdigest()
    )


def test_open_blocking_semantic_issue_blocks_mechanical_preparation(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["issues"] = {"semantic-issue-01": _issue()}
    _write_json(review_path, review)

    receipt = _run_review(review_path, intake_receipt_path)

    assert receipt["readiness"]["status"] == "blocked_by_reviewed_semantic_issues"
    assert receipt["readiness"]["mechanical_preparation_allowed"] is False
    assert receipt["review_summary"]["issue_counts"]["open_blocking"] == 1


def test_v2_general_ledger_dataset_identity_issue_blocks_preparation(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, intake_receipt = _case(
        tmp_path,
        intake_contract_version="v2",
    )
    review["issues"] = {"semantic-issue-01": _issue(topic="dataset_identity_and_grain")}
    _write_json(review_path, review)

    receipt = _run_review(review_path, intake_receipt_path)

    assert intake_receipt["schema_version"] == (
        "clara.real_data_pilot_intake_receipt.v2"
    )
    assert (
        intake_receipt["source_receipt"]["declared_data_kind"]
        == "commercial_general_ledger"
    )
    assert receipt["readiness"]["status"] == "blocked_by_reviewed_semantic_issues"
    assert receipt["readiness"]["mechanical_preparation_allowed"] is False
    assert receipt["review_summary"]["issue_counts"]["open_blocking"] == 1


def test_semantic_review_rejects_unregistered_intake_receipt_version(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, intake_receipt = _case(tmp_path)
    intake_receipt["schema_version"] = "clara.real_data_pilot_intake_receipt.v3"
    _write_json(intake_receipt_path, intake_receipt)
    review["intake_receipt_sha256"] = hashlib.sha256(
        intake_receipt_path.read_bytes()
    ).hexdigest()
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="schema_version is not a supported exact version",
    ):
        _run_review(review_path, intake_receipt_path)


def test_open_nonblocking_semantic_issue_preserves_reviewer_decision(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["issues"] = {"semantic-issue-01": _issue(blocking=False)}
    _write_json(review_path, review)

    receipt = _run_review(review_path, intake_receipt_path)

    assert receipt["readiness"]["status"] == "ready_for_mechanical_preparation_only"
    assert receipt["review_summary"]["issue_counts"]["open_nonblocking"] == 1
    assert receipt["readiness"]["semantic_status_for_audit_envelope"] == "not_assessed"


@pytest.mark.parametrize("status", ["accepted_limitation", "resolved"])
def test_disposed_semantic_issue_is_counted_without_content(
    tmp_path: Path,
    status: str,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["issues"] = {
        "semantic-issue-01": _issue(
            status=status,
            blocking=False,
            resolution="Reviewer-owned disposition.",
        )
    }
    _write_json(review_path, review)

    receipt = _run_review(review_path, intake_receipt_path)

    assert receipt["review_summary"]["issue_counts"][status] == 1
    assert "Reviewer-owned disposition" not in json.dumps(receipt)


def _remove_required_review(review: dict[str, Any]) -> None:
    review["required_reviews"].pop()


def _duplicate_review_id(review: dict[str, Any]) -> None:
    review["required_reviews"][1]["review_id"] = review["required_reviews"][0][
        "review_id"
    ]


def _reverse_review_order(review: dict[str, Any]) -> None:
    review["required_reviews"].reverse()


def _set_automatic_mechanical_register(review: dict[str, Any]) -> None:
    review["mechanical_error_register_policy"] = "combined_with_semantic_errors"


def _set_publication_authorized(review: dict[str, Any]) -> None:
    review["publication_status"] = "authorized"


def _set_report_ready(review: dict[str, Any]) -> None:
    review["report_ready"] = True


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_remove_required_review, "cover each registered topic exactly once"),
        (_duplicate_review_id, "review_id must equal"),
        (
            _set_automatic_mechanical_register,
            "mechanical_error_register_policy must equal",
        ),
        (_set_publication_authorized, "publication_status must equal"),
        (_set_report_ready, "report_ready must equal"),
    ],
)
def test_semantic_review_rejects_boundary_mutation(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    review_path, intake_receipt_path, original, _ = _case(tmp_path)
    review = copy.deepcopy(original)
    mutation(review)
    _write_json(review_path, review)

    with pytest.raises(SEMANTIC_VALIDATOR.ContractValidationError, match=message):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_accepts_required_reviews_in_any_order(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    _reverse_review_order(review)
    _write_json(review_path, review)

    receipt = _run_review(review_path, intake_receipt_path)

    _schema_validator(SEMANTIC_SCHEMA_PATH).validate(review)
    assert receipt["review_summary"]["required_review_count"] == 7


def test_open_semantic_issue_rejects_resolution(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["issues"] = {"semantic-issue-01": _issue(resolution="Premature resolution.")}
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="resolution must be null",
    ):
        _run_review(review_path, intake_receipt_path)


def test_disposed_semantic_issue_rejects_blocking_flag(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["issues"] = {
        "semantic-issue-01": _issue(
            status="resolved",
            blocking=True,
            resolution="Resolved by reviewer.",
        )
    }
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="blocking must be false",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_accepts_issue_registry_in_any_key_order(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["issues"] = {
        "semantic-issue-02": _issue(blocking=False),
        "semantic-issue-01": _issue(blocking=False),
    }
    _write_json(review_path, review)

    receipt = _run_review(review_path, intake_receipt_path)

    assert receipt["review_summary"]["issue_counts"]["open_nonblocking"] == 2


def test_semantic_review_accepts_evidence_refs_in_any_order(tmp_path: Path) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["required_reviews"][0]["evidence_refs"] = [
        "evidence-02",
        "evidence-01",
    ]
    _write_json(review_path, review)

    receipt = _run_review(review_path, intake_receipt_path)

    assert receipt["review_summary"]["required_review_count"] == 7


def test_semantic_review_rejects_duplicate_evidence_refs(tmp_path: Path) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["required_reviews"][0]["evidence_refs"] = [
        "evidence-01",
        "evidence-01",
    ]
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="must contain unique values",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_rejects_unresolved_evidence_ref(tmp_path: Path) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["required_reviews"][0]["evidence_refs"] = ["evidence-missing"]
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="unresolved evidence references",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_rejects_evidence_digest_drift(tmp_path: Path) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    evidence_path = tmp_path / review["evidence_registry"]["evidence-01"]["path"]
    evidence_path.write_bytes(b"x" * evidence_path.stat().st_size)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="sha256 does not match",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_rejects_evidence_in_nested_git_worktree(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    nested_repository = tmp_path / "nested-repository"
    (nested_repository / ".git").mkdir(parents=True)
    original_evidence = tmp_path / review["evidence_registry"]["evidence-01"]["path"]
    nested_evidence = nested_repository / original_evidence.name
    original_evidence.replace(nested_evidence)
    review["evidence_registry"]["evidence-01"]["path"] = nested_evidence.relative_to(
        tmp_path
    ).as_posix()
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="must not be inside an undeclared Git worktree",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_rejects_intake_receipt_digest_drift(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)
    intake_receipt_path.write_bytes(intake_receipt_path.read_bytes() + b"\n")

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="does not match the supplied receipt",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_rejects_forged_minimal_intake_receipt(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    forged_receipt = {
        "schema_version": "clara.real_data_pilot_intake_receipt.v1",
        "pilot_id": review["pilot_id"],
        "validation_date": VALIDATION_DATE,
        "eligibility": {
            "status": "declared_boundary_passed_for_local_pilot_intake",
            "publication_status": "withheld",
            "report_ready": False,
        },
    }
    _write_json(intake_receipt_path, forged_receipt)
    review["intake_receipt_sha256"] = hashlib.sha256(
        intake_receipt_path.read_bytes()
    ).hexdigest()
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="intake receipt is missing fields",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_rejects_pilot_mismatch(tmp_path: Path) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["pilot_id"] = "pilot-fedcba9876543210"
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="does not match the intake receipt",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_requires_same_day_revalidated_intake(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="requires an intake receipt revalidated",
    ):
        _run_review(
            review_path,
            intake_receipt_path,
            as_of_date="2026-07-24",
        )


def test_semantic_review_rejects_future_review_date(tmp_path: Path) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["reviewed_on"] = "2026-07-24"
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="cannot postdate",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_rejects_identifying_receipt_ids(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["review_version"] = "Acme_semantic_review"
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="opaque digest-shaped ID",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_runtime_rejects_padded_text(tmp_path: Path) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["reviewer_role"] = " reviewer "
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="without edge whitespace",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_schema_rejects_padded_text(tmp_path: Path) -> None:
    _, _, review, _ = _case(tmp_path)
    review["reviewer_role"] = " reviewer "

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(SEMANTIC_SCHEMA_PATH).validate(review)


def test_semantic_review_schema_and_runtime_reject_trailing_newline_text(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["reviewer_role"] = "reviewer\n"
    _write_json(review_path, review)

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(SEMANTIC_SCHEMA_PATH).validate(review)
    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="without edge whitespace",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_schema_and_runtime_reject_integer_for_boolean(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["report_ready"] = 0
    _write_json(review_path, review)

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(SEMANTIC_SCHEMA_PATH).validate(review)
    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="report_ready must equal",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_schema_rejects_topic_review_id_mismatch(
    tmp_path: Path,
) -> None:
    _, _, review, _ = _case(tmp_path)
    review["required_reviews"][0]["review_id"] = "topic-review-07"

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(SEMANTIC_SCHEMA_PATH).validate(review)


def test_semantic_review_rejects_duplicate_json_field(tmp_path: Path) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)
    review_path.write_text(
        '{"schema_version":"clara.real_data_pilot_semantic_review.v1",'
        '"schema_version":"duplicate"}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="duplicate JSON field",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_rejects_binary_float(tmp_path: Path) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    review["unexpected_float"] = 0.1
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="JSON fractional or exponent number",
    ):
        _run_review(review_path, intake_receipt_path)


def test_semantic_review_cli_writes_sanitized_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)
    output_path = tmp_path / "semantic_review_receipt.json"
    monkeypatch.setattr(
        SEMANTIC_VALIDATOR,
        "_current_date",
        lambda: SEMANTIC_VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )

    result = SEMANTIC_VALIDATOR.main(
        [
            "--review",
            str(review_path),
            "--intake-receipt",
            str(intake_receipt_path),
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
    _schema_validator(SEMANTIC_RECEIPT_SCHEMA_PATH).validate(receipt)
    assert receipt["readiness"]["report_ready"] is False


def test_semantic_review_cli_requires_fresh_output_and_preserves_prior_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_path, intake_receipt_path, review, _ = _case(tmp_path)
    output_path = tmp_path / "semantic_review_receipt.json"
    monkeypatch.setattr(
        SEMANTIC_VALIDATOR,
        "_current_date",
        lambda: SEMANTIC_VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )
    arguments = [
        "--review",
        str(review_path),
        "--intake-receipt",
        str(intake_receipt_path),
        "--local-run-root",
        str(tmp_path),
        "--repository-root",
        str(ROOT),
        "--output",
        str(output_path),
    ]
    assert SEMANTIC_VALIDATOR.main(arguments) == 0
    prior_receipt = output_path.read_bytes()
    review["review_status"] = "draft"
    _write_json(review_path, review)

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="output path must be absent",
    ):
        SEMANTIC_VALIDATOR.main(arguments)

    assert output_path.read_bytes() == prior_receipt


def test_semantic_review_cli_refuses_unowned_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)
    output_path = tmp_path / "do-not-overwrite.txt"
    original_bytes = b"unrelated local content\n"
    output_path.write_bytes(original_bytes)
    monkeypatch.setattr(
        SEMANTIC_VALIDATOR,
        "_current_date",
        lambda: SEMANTIC_VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="output path must be absent",
    ):
        SEMANTIC_VALIDATOR.main(
            [
                "--review",
                str(review_path),
                "--intake-receipt",
                str(intake_receipt_path),
                "--local-run-root",
                str(tmp_path),
                "--repository-root",
                str(ROOT),
                "--output",
                str(output_path),
            ]
        )

    assert output_path.read_bytes() == original_bytes


def test_semantic_review_cli_refuses_symlink_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)
    target_path = tmp_path / "symlink-target.txt"
    original_bytes = b"target must remain unchanged\n"
    target_path.write_bytes(original_bytes)
    output_path = tmp_path / "semantic-review-output-link.json"
    output_path.symlink_to(target_path)
    monkeypatch.setattr(
        SEMANTIC_VALIDATOR,
        "_current_date",
        lambda: SEMANTIC_VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="must not use a symlink|must not identify a symlink",
    ):
        SEMANTIC_VALIDATOR.main(
            [
                "--review",
                str(review_path),
                "--intake-receipt",
                str(intake_receipt_path),
                "--local-run-root",
                str(tmp_path),
                "--repository-root",
                str(ROOT),
                "--output",
                str(output_path),
            ]
        )

    assert target_path.read_bytes() == original_bytes


def test_semantic_receipt_rejects_dependency_digest_drift(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)
    receipt = _run_review(review_path, intake_receipt_path)
    receipt["validator"]["dependency_sha256"]["semantic_review_schema"] = "0" * 64

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="semantic_review_schema is not current",
    ):
        SEMANTIC_VALIDATOR.validate_real_data_pilot_semantic_review_receipt(receipt)


def test_semantic_receipt_rejects_readiness_count_inconsistency(
    tmp_path: Path,
) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)
    receipt = _run_review(review_path, intake_receipt_path)
    receipt["readiness"]["status"] = "blocked_by_reviewed_semantic_issues"

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="readiness.status must equal",
    ):
        SEMANTIC_VALIDATOR.validate_real_data_pilot_semantic_review_receipt(receipt)


@pytest.mark.parametrize("collision_target", ["review", "intake_receipt"])
def test_semantic_review_cli_rejects_output_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collision_target: str,
) -> None:
    review_path, intake_receipt_path, _, _ = _case(tmp_path)
    target_path = review_path if collision_target == "review" else intake_receipt_path
    original_bytes = target_path.read_bytes()
    monkeypatch.setattr(
        SEMANTIC_VALIDATOR,
        "_current_date",
        lambda: SEMANTIC_VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )

    with pytest.raises(
        SEMANTIC_VALIDATOR.ContractValidationError,
        match="output path must not equal",
    ):
        SEMANTIC_VALIDATOR.main(
            [
                "--review",
                str(review_path),
                "--intake-receipt",
                str(intake_receipt_path),
                "--local-run-root",
                str(tmp_path),
                "--repository-root",
                str(ROOT),
                "--output",
                str(target_path),
            ]
        )

    assert target_path.read_bytes() == original_bytes


def test_semantic_review_cli_parent_symlink_swap_cannot_escape_run_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_path, intake_receipt_path, _, _ = _case(
        tmp_path,
        intake_contract_version="v2",
    )
    receipt_directory = tmp_path / "receipts"
    receipt_directory.mkdir()
    pinned_directory = tmp_path / "receipts-pinned"
    output_path = receipt_directory / "semantic-review-receipt.json"
    monkeypatch.setattr(
        SEMANTIC_VALIDATOR,
        "_current_date",
        lambda: SEMANTIC_VALIDATOR.date.fromisoformat(VALIDATION_DATE),
    )

    with TemporaryDirectory(
        prefix="clara-m6-semantic-output-race-",
        dir=tmp_path.parent,
    ) as raw_outside_directory:
        outside_directory = Path(raw_outside_directory)
        outside_output = outside_directory / output_path.name
        original_open = INTAKE_VALIDATOR.os.open
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
                and flags & INTAKE_VALIDATOR.os.O_CREAT
            ):
                receipt_directory.rename(pinned_directory)
                receipt_directory.symlink_to(
                    outside_directory,
                    target_is_directory=True,
                )
                swapped = True
            return original_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(
            INTAKE_VALIDATOR.os,
            "open",
            _swap_parent_then_open,
        )

        with pytest.raises(
            SEMANTIC_VALIDATOR.ContractValidationError,
            match="output directory path changed during receipt write",
        ):
            SEMANTIC_VALIDATOR.main(
                [
                    "--review",
                    str(review_path),
                    "--intake-receipt",
                    str(intake_receipt_path),
                    "--local-run-root",
                    str(tmp_path),
                    "--repository-root",
                    str(ROOT),
                    "--output",
                    str(output_path),
                ]
            )

        assert swapped is True
        assert not outside_output.exists()
        assert (pinned_directory / output_path.name).is_file()
