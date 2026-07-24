from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SCRIPTS_ROOT = CLARA_ROOT / "scripts"
MECHANICAL_SCHEMA_PATH = (
    CLARA_ROOT
    / "contracts"
    / "real_data_pilot_mechanical_error_register.v1.schema.json"
)
CANDIDATE_SCHEMA_PATH = (
    CLARA_ROOT
    / "contracts"
    / "real_data_pilot_sanitized_error_class_summary_candidate.v1.schema.json"
)
RETENTION_SCHEMA_PATH = (
    CLARA_ROOT / "contracts" / "real_data_pilot_retention_approval.v1.schema.json"
)
SUMMARY_SCHEMA_PATH = (
    CLARA_ROOT
    / "contracts"
    / "real_data_pilot_sanitized_error_class_summary.v1.schema.json"
)
VALIDATION_DATE = "2026-07-23"
PILOT_ID = "pilot-0123456789abcdef"
EXECUTION_ID = "execution-fedcba9876543210"
ARTIFACT_ROLE = "artifact-0000000000000001"
EXPECTED_ROLES = {
    ARTIFACT_ROLE: f"artifacts/{ARTIFACT_ROLE}.bin",
    "mechanical_errors": "mechanical_errors.json",
}


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


BOUNDARY = _load_module(
    "real_data_pilot_output_boundary",
    SCRIPTS_ROOT / "real_data_pilot_output_boundary.py",
)
MECHANICAL = _load_module(
    "validate_real_data_pilot_mechanical_errors",
    SCRIPTS_ROOT / "validate_real_data_pilot_mechanical_errors.py",
)
BUILDER = _load_module(
    "clara_real_data_pilot_error_summary_test",
    SCRIPTS_ROOT / "build_real_data_pilot_error_summary.py",
)


def _schema_validator(path: Path) -> jsonschema.Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _bindings(closure_digest: str) -> dict[str, str]:
    bindings = {field: _digest(field) for field in sorted(MECHANICAL.BINDING_FIELDS)}
    bindings["output_receipt_closure_sha256"] = closure_digest
    return bindings


def _mechanical_register(*, closure_digest: str = "0" * 64) -> dict[str, Any]:
    return {
        "schema_version": "clara.real_data_pilot_mechanical_error_register.v1",
        "pilot_id": PILOT_ID,
        "execution_id": EXECUTION_ID,
        "bindings": _bindings(closure_digest),
        "check_registry": {
            "check-0000000000000001": {
                "mechanical_class": "contract",
                "error_codes": ["code-0000000000000001"],
                "status": "passed",
                "artifact_refs": [ARTIFACT_ROLE],
            }
        },
        "error_registry": {},
        "summary": {
            "overall_status": "passed",
            "check_counts": {
                "passed": 1,
                "failed": 0,
                "not_run": 0,
            },
            "error_count": 0,
            "class_counts": {
                mechanical_class: 0
                for mechanical_class in MECHANICAL.MECHANICAL_CLASSES
            },
        },
        "content_policy": {
            "error_messages_in_register": False,
            "row_level_values_in_register": False,
            "semantic_findings_in_register": False,
        },
        "publication_status": "withheld",
        "report_ready": False,
        "limitations": list(MECHANICAL.LIMITATIONS),
    }


def _retention_approval(
    *,
    mechanical_register_sha256: str,
    candidate_summary_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": "clara.real_data_pilot_retention_approval.v1",
        "pilot_id": PILOT_ID,
        "execution_id": EXECUTION_ID,
        "review_version": "retention-review-0011223344556677",
        "reviewed_on": VALIDATION_DATE,
        "reviewer_role": "unit-test reviewer",
        "basis": (
            "Synthetic test confirms the exact candidate contains no local detail."
        ),
        "mechanical_register_sha256": mechanical_register_sha256,
        "candidate_summary_sha256": candidate_summary_sha256,
        "status": "reviewed",
        "decision": "approved",
        "scope": "sanitized_error_class_summary_only",
        "prohibited_content": list(BUILDER.PROHIBITED_CONTENT),
        "publication_status": "withheld",
        "report_ready": False,
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _seal(case: dict[str, Any]) -> list[dict[str, Any]]:
    return BOUNDARY.seal_pilot_output_directory(
        case["output_directory"],
        expected_roles=EXPECTED_ROLES,
        local_run_root=case["local_run_root"],
        repository_root=ROOT,
    )


def _case(tmp_path: Path) -> dict[str, Any]:
    input_path = tmp_path / "input.json"
    input_path.write_text('{"synthetic":true}\n', encoding="utf-8")
    output_directory = BOUNDARY.create_fresh_pilot_output_directory(
        tmp_path / "output",
        local_run_root=tmp_path,
        repository_root=ROOT,
        input_paths=[input_path],
    )
    artifact_directory = output_directory / "artifacts"
    artifact_directory.mkdir()
    (artifact_directory / f"{ARTIFACT_ROLE}.bin").write_bytes(b"synthetic artifact")
    mechanical_path = output_directory / "mechanical_errors.json"
    mechanical_register = _mechanical_register()
    _write_json(mechanical_path, mechanical_register)
    case = {
        "local_run_root": tmp_path,
        "output_directory": output_directory,
        "mechanical_path": mechanical_path,
        "mechanical_register": mechanical_register,
    }
    provisional_receipts = _seal(case)
    closure_digest = MECHANICAL.output_receipt_closure_sha256(provisional_receipts)
    mechanical_register["bindings"] = _bindings(closure_digest)
    _write_json(mechanical_path, mechanical_register)
    output_receipts = _seal(case)
    expected_bindings = _bindings(closure_digest)
    candidate = BUILDER.build_real_data_pilot_sanitized_error_summary_candidate(
        mechanical_path,
        expected_pilot_id=PILOT_ID,
        expected_execution_id=EXECUTION_ID,
        expected_bindings=expected_bindings,
        output_receipts=output_receipts,
        output_directory=output_directory,
        local_run_root=tmp_path,
        repository_root=ROOT,
    )
    approval = _retention_approval(
        mechanical_register_sha256=candidate["mechanical_register_sha256"],
        candidate_summary_sha256=BUILDER.canonical_json_sha256(candidate),
    )
    approval_path = tmp_path / "retention_approval.json"
    _write_json(approval_path, approval)
    case.update(
        {
            "output_receipts": output_receipts,
            "expected_bindings": expected_bindings,
            "candidate": candidate,
            "approval": approval,
            "approval_path": approval_path,
        }
    )
    return case


def _build(case: dict[str, Any]) -> dict[str, Any]:
    return BUILDER.build_real_data_pilot_sanitized_error_summary(
        case["mechanical_path"],
        case["approval_path"],
        expected_pilot_id=PILOT_ID,
        expected_execution_id=EXECUTION_ID,
        expected_bindings=case["expected_bindings"],
        output_receipts=case["output_receipts"],
        output_directory=case["output_directory"],
        as_of_date=VALIDATION_DATE,
        local_run_root=case["local_run_root"],
        repository_root=ROOT,
    )


def _validate_summary(
    case: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    return BUILDER.validate_real_data_pilot_sanitized_error_summary(
        summary,
        case["mechanical_path"],
        case["approval_path"],
        expected_pilot_id=PILOT_ID,
        expected_execution_id=EXECUTION_ID,
        expected_bindings=case["expected_bindings"],
        output_receipts=case["output_receipts"],
        output_directory=case["output_directory"],
        as_of_date=VALIDATION_DATE,
        local_run_root=case["local_run_root"],
        repository_root=ROOT,
    )


def test_sanitized_error_summary_binds_exact_reviewed_candidate(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)

    summary = _build(case)

    _schema_validator(MECHANICAL_SCHEMA_PATH).validate(case["mechanical_register"])
    _schema_validator(CANDIDATE_SCHEMA_PATH).validate(case["candidate"])
    _schema_validator(RETENTION_SCHEMA_PATH).validate(case["approval"])
    _schema_validator(SUMMARY_SCHEMA_PATH).validate(summary)
    assert summary["candidate"] == case["candidate"]
    assert summary["candidate_summary_sha256"] == BUILDER.canonical_json_sha256(
        case["candidate"]
    )
    assert _validate_summary(case, summary) == summary


def test_sanitized_error_summary_omits_local_review_prose_and_paths(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)

    serialized = json.dumps(_build(case))

    assert case["approval"]["reviewer_role"] not in serialized
    assert case["approval"]["basis"] not in serialized
    assert str(tmp_path) not in serialized


def test_sanitized_error_candidate_and_summary_are_byte_deterministic(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)

    first = json.dumps(
        _build(case),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    second = json.dumps(
        _build(case),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert first == second


def test_sanitized_error_summary_requires_retention_approval(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)

    with pytest.raises(
        BUILDER.ContractValidationError,
        match="retention approval path must identify",
    ):
        BUILDER.build_real_data_pilot_sanitized_error_summary(
            case["mechanical_path"],
            tmp_path / "missing.json",
            expected_pilot_id=PILOT_ID,
            expected_execution_id=EXECUTION_ID,
            expected_bindings=case["expected_bindings"],
            output_receipts=case["output_receipts"],
            output_directory=case["output_directory"],
            as_of_date=VALIDATION_DATE,
            local_run_root=tmp_path,
            repository_root=ROOT,
        )


def test_sanitized_error_summary_rejects_approval_for_other_candidate(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    case["approval"]["candidate_summary_sha256"] = "0" * 64
    _write_json(case["approval_path"], case["approval"])

    with pytest.raises(
        BUILDER.ContractValidationError,
        match="candidate_summary_sha256 must equal",
    ):
        _build(case)


def test_sanitized_error_summary_rejects_register_digest_mismatch(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    case["approval"]["mechanical_register_sha256"] = "0" * 64
    _write_json(case["approval_path"], case["approval"])

    with pytest.raises(
        BUILDER.ContractValidationError,
        match="mechanical_register_sha256 must equal",
    ):
        _build(case)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("status", "draft", "retention approval.status must equal"),
        ("decision", "rejected", "retention approval.decision must equal"),
        ("scope", "full_error_register", "retention approval.scope must equal"),
        ("report_ready", True, "retention approval.report_ready must equal"),
    ],
)
def test_sanitized_error_summary_rejects_retention_boundary_mutation(
    tmp_path: Path,
    field: str,
    value: Any,
    message: str,
) -> None:
    case = _case(tmp_path)
    case["approval"][field] = value
    _write_json(case["approval_path"], case["approval"])

    with pytest.raises(BUILDER.ContractValidationError, match=message):
        _build(case)


def test_sanitized_error_summary_rejects_future_retention_review(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    case["approval"]["reviewed_on"] = "2026-07-24"
    _write_json(case["approval_path"], case["approval"])

    with pytest.raises(BUILDER.ContractValidationError, match="cannot postdate"):
        _build(case)


def test_full_replay_validator_rejects_coordinated_detached_count_mutation(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    summary = _build(case)
    summary["candidate"]["check_counts"]["passed"] = 999
    summary["candidate_summary_sha256"] = BUILDER.canonical_json_sha256(
        summary["candidate"]
    )
    summary["retention_approval_sha256"] = "f" * 64

    with pytest.raises(
        BUILDER.ContractValidationError,
        match="candidate must equal",
    ):
        _validate_summary(case, summary)


def test_full_replay_validator_rejects_validation_date_mutation(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    summary = _build(case)
    summary["validation_date"] = "2026-07-24"

    with pytest.raises(
        BUILDER.ContractValidationError,
        match="validation_date must equal",
    ):
        _validate_summary(case, summary)


def test_candidate_validator_rejects_error_class_count_mismatch(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    candidate = copy.deepcopy(case["candidate"])
    candidate["class_counts"]["reconciliation"] = 999

    with pytest.raises(
        BUILDER.ContractValidationError,
        match="class_counts must sum",
    ):
        BUILDER.validate_real_data_pilot_sanitized_error_summary_candidate(
            candidate,
            expected_pilot_id=PILOT_ID,
            expected_execution_id=EXECUTION_ID,
            expected_register_sha256=candidate["mechanical_register_sha256"],
            expected_bindings=case["expected_bindings"],
        )


def test_candidate_and_summary_schemas_reject_zero_check_coverage(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    candidate = copy.deepcopy(case["candidate"])
    candidate["check_counts"] = {"passed": 0, "failed": 0, "not_run": 0}
    summary = _build(case)
    summary["candidate"] = candidate

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(CANDIDATE_SCHEMA_PATH).validate(candidate)
    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(SUMMARY_SCHEMA_PATH).validate(summary)


def test_final_summary_schema_rejects_candidate_status_contradiction(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    summary = _build(case)
    summary["candidate"]["check_counts"] = {
        "passed": 0,
        "failed": 1,
        "not_run": 0,
    }
    summary["candidate"]["mechanical_status"] = "passed"
    summary["candidate"]["error_count"] = 0

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(SUMMARY_SCHEMA_PATH).validate(summary)


def test_summary_validator_rejects_dependency_drift(tmp_path: Path) -> None:
    case = _case(tmp_path)
    summary = _build(case)
    summary["validator"]["dependency_sha256"]["intake_validator"] = "0" * 64

    with pytest.raises(
        BUILDER.ContractValidationError,
        match="intake_validator must equal",
    ):
        _validate_summary(case, summary)


@pytest.mark.parametrize(
    ("schema_path", "payload_factory", "mutation"),
    [
        (
            CANDIDATE_SCHEMA_PATH,
            lambda case: copy.deepcopy(case["candidate"]),
            lambda payload: payload.__setitem__("pilot_id", f"{PILOT_ID}\n"),
        ),
        (
            RETENTION_SCHEMA_PATH,
            lambda case: copy.deepcopy(case["approval"]),
            lambda payload: payload.__setitem__(
                "candidate_summary_sha256",
                f"{payload['candidate_summary_sha256']}\n",
            ),
        ),
        (
            SUMMARY_SCHEMA_PATH,
            lambda case: _build(case),
            lambda payload: payload.__setitem__(
                "candidate_summary_sha256",
                f"{payload['candidate_summary_sha256']}\n",
            ),
        ),
    ],
)
def test_summary_schemas_reject_terminal_newline_identifiers_and_hashes(
    tmp_path: Path,
    schema_path: Path,
    payload_factory: Callable[[dict[str, Any]], dict[str, Any]],
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    case = _case(tmp_path)
    payload = payload_factory(case)
    mutation(payload)

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator(schema_path).validate(payload)


def test_candidate_builder_rejects_post_snapshot_path_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(tmp_path)
    outside_path = tmp_path.parent / f"{tmp_path.name}-outside-register.json"
    outside_path.write_bytes(case["mechanical_path"].read_bytes())
    original_snapshot = BUILDER.strict_json_snapshot_beneath
    calls = 0

    def swapping_snapshot(
        path: Path,
        *,
        root: Path,
    ) -> tuple[dict[str, Any], int, str]:
        nonlocal calls
        result = original_snapshot(path, root=root)
        calls += 1
        if calls == 1:
            case["mechanical_path"].unlink()
            case["mechanical_path"].symlink_to(outside_path)
        return result

    monkeypatch.setattr(
        BUILDER,
        "strict_json_snapshot_beneath",
        swapping_snapshot,
    )

    with pytest.raises(
        BUILDER.ContractValidationError,
        match="must resolve inside the declared local run root",
    ):
        BUILDER.build_real_data_pilot_sanitized_error_summary_candidate(
            case["mechanical_path"],
            expected_pilot_id=PILOT_ID,
            expected_execution_id=EXECUTION_ID,
            expected_bindings=case["expected_bindings"],
            output_receipts=case["output_receipts"],
            output_directory=case["output_directory"],
            local_run_root=tmp_path,
            repository_root=ROOT,
        )


def test_summary_builder_rejects_approval_check_open_symlink_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(tmp_path)
    outside_path = tmp_path.parent / f"{tmp_path.name}-outside-approval.json"
    outside_path.write_bytes(case["approval_path"].read_bytes())
    original_validate = BUILDER._validate_local_json_path
    swapped = False

    def swapping_validate(
        path: Path,
        *,
        local_run_root: Path,
        repository_root: Path,
        label: str,
    ) -> Path:
        nonlocal swapped
        result = original_validate(
            path,
            local_run_root=local_run_root,
            repository_root=repository_root,
            label=label,
        )
        if label == "retention approval path" and not swapped:
            case["approval_path"].unlink()
            case["approval_path"].symlink_to(outside_path)
            swapped = True
        return result

    monkeypatch.setattr(BUILDER, "_validate_local_json_path", swapping_validate)

    with pytest.raises(
        BUILDER.ContractValidationError,
        match="could not safely open file below the declared root",
    ):
        _build(case)
