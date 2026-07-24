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
SCHEMA_PATH = (
    CLARA_ROOT
    / "contracts"
    / "real_data_pilot_mechanical_error_register.v1.schema.json"
)
PILOT_ID = "pilot-0123456789abcdef"
EXECUTION_ID = "execution-fedcba9876543210"
PREPARED_DATA_ROLE = "artifact-0000000000000001"
EXPECTED_ROLES = {
    "mechanical_errors": "mechanical_errors.json",
    PREPARED_DATA_ROLE: f"artifacts/{PREPARED_DATA_ROLE}.bin",
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
VALIDATOR = _load_module(
    "clara_real_data_pilot_mechanical_errors_test",
    SCRIPTS_ROOT / "validate_real_data_pilot_mechanical_errors.py",
)


def _schema_validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _bindings(closure_digest: str) -> dict[str, str]:
    bindings = {field: _digest(field) for field in sorted(VALIDATOR.BINDING_FIELDS)}
    bindings["output_receipt_closure_sha256"] = closure_digest
    return bindings


def _register(*, closure_digest: str = "0" * 64) -> dict[str, Any]:
    class_counts = {
        mechanical_class: 0 for mechanical_class in VALIDATOR.MECHANICAL_CLASSES
    }
    class_counts["reconciliation"] = 2
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
                "artifact_refs": ["mechanical_errors"],
            },
            "check-0000000000000002": {
                "mechanical_class": "reconciliation",
                "error_codes": [
                    "code-0000000000000002",
                    "code-0000000000000003",
                ],
                "status": "failed",
                "artifact_refs": [PREPARED_DATA_ROLE, "mechanical_errors"],
            },
        },
        "error_registry": {
            "error-0000000000000001": {
                "check_id": "check-0000000000000002",
                "error_code": "code-0000000000000002",
                "mechanical_class": "reconciliation",
                "artifact_refs": [PREPARED_DATA_ROLE],
            },
            "error-0000000000000002": {
                "check_id": "check-0000000000000002",
                "error_code": "code-0000000000000003",
                "mechanical_class": "reconciliation",
                "artifact_refs": [PREPARED_DATA_ROLE],
            },
        },
        "summary": {
            "overall_status": "failed",
            "check_counts": {
                "passed": 1,
                "failed": 1,
                "not_run": 0,
            },
            "error_count": 2,
            "class_counts": class_counts,
        },
        "content_policy": {
            "error_messages_in_register": False,
            "row_level_values_in_register": False,
            "semantic_findings_in_register": False,
        },
        "publication_status": "withheld",
        "report_ready": False,
        "limitations": list(VALIDATOR.LIMITATIONS),
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
    prepared_directory = output_directory / "artifacts"
    prepared_directory.mkdir()
    prepared_path = prepared_directory / f"{PREPARED_DATA_ROLE}.bin"
    prepared_path.write_text('{"synthetic":"prepared"}\n', encoding="utf-8")
    register_path = output_directory / "mechanical_errors.json"
    register = _register()
    _write_json(register_path, register)
    case = {
        "local_run_root": tmp_path,
        "output_directory": output_directory,
        "prepared_path": prepared_path,
        "register_path": register_path,
        "register": register,
    }
    provisional_receipts = _seal(case)
    closure_digest = VALIDATOR.output_receipt_closure_sha256(provisional_receipts)
    register["bindings"] = _bindings(closure_digest)
    _write_json(register_path, register)
    case["expected_bindings"] = _bindings(closure_digest)
    case["output_receipts"] = _seal(case)
    return case


def _validate(
    case: dict[str, Any],
    *,
    expected_pilot_id: str = PILOT_ID,
    expected_execution_id: str = EXECUTION_ID,
    output_receipts: Any | None = None,
) -> dict[str, Any]:
    return VALIDATOR.validate_real_data_pilot_mechanical_error_register(
        case["register_path"],
        expected_pilot_id=expected_pilot_id,
        expected_execution_id=expected_execution_id,
        expected_bindings=case["expected_bindings"],
        output_receipts=(
            case["output_receipts"] if output_receipts is None else output_receipts
        ),
        output_directory=case["output_directory"],
        local_run_root=case["local_run_root"],
        repository_root=ROOT,
    )


def _write_mutation_and_reseal(
    case: dict[str, Any],
    register: dict[str, Any],
) -> list[dict[str, Any]]:
    _write_json(case["register_path"], register)
    return _seal(case)


def test_mechanical_error_register_closes_exact_receipts_and_multiple_codes(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)

    result = _validate(case)

    _schema_validator().validate(result)
    assert result["summary"]["overall_status"] == "failed"
    assert result["summary"]["class_counts"]["reconciliation"] == 2
    assert result["check_registry"]["check-0000000000000002"]["error_codes"] == [
        "code-0000000000000002",
        "code-0000000000000003",
    ]
    assert {error["error_code"] for error in result["error_registry"].values()} == {
        "code-0000000000000002",
        "code-0000000000000003",
    }
    assert result["bindings"]["output_receipt_closure_sha256"] == (
        VALIDATOR.output_receipt_closure_sha256(case["output_receipts"])
    )


def test_mechanical_error_register_validation_is_deterministic(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)

    first = json.dumps(
        _validate(case),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    second = json.dumps(
        _validate(case),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert first == second


@pytest.mark.parametrize(
    ("expected_pilot_id", "expected_execution_id", "message"),
    [
        (
            "pilot-ffffffffffffffff",
            EXECUTION_ID,
            "mechanical register.pilot_id must equal",
        ),
        (
            PILOT_ID,
            "execution-ffffffffffffffff",
            "mechanical register.execution_id must equal",
        ),
    ],
)
def test_mechanical_error_register_rejects_cross_run_identity(
    tmp_path: Path,
    expected_pilot_id: str,
    expected_execution_id: str,
    message: str,
) -> None:
    case = _case(tmp_path)

    with pytest.raises(VALIDATOR.ContractValidationError, match=message):
        _validate(
            case,
            expected_pilot_id=expected_pilot_id,
            expected_execution_id=expected_execution_id,
        )


def _binding_drift(register: dict[str, Any]) -> None:
    register["bindings"]["case_contract_sha256"] = "0" * 64


def _closure_binding_drift(register: dict[str, Any]) -> None:
    register["bindings"]["output_receipt_closure_sha256"] = "0" * 64


def _unresolved_artifact(register: dict[str, Any]) -> None:
    register["error_registry"]["error-0000000000000001"]["artifact_refs"] = ["missing"]


def _error_code_drift(register: dict[str, Any]) -> None:
    register["error_registry"]["error-0000000000000001"][
        "error_code"
    ] = "code-ffffffffffffffff"


def _failed_without_error(register: dict[str, Any]) -> None:
    register["error_registry"] = {}
    register["summary"]["error_count"] = 0
    register["summary"]["class_counts"]["reconciliation"] = 0


def _error_on_passed_check(register: dict[str, Any]) -> None:
    register["check_registry"]["check-0000000000000002"]["status"] = "passed"
    register["summary"]["check_counts"] = {
        "passed": 2,
        "failed": 0,
        "not_run": 0,
    }
    register["summary"]["overall_status"] = "passed"


def _summary_contradiction(register: dict[str, Any]) -> None:
    register["summary"]["error_count"] = 3


def _semantic_material(register: dict[str, Any]) -> None:
    register["error_registry"]["error-0000000000000001"][
        "semantic_finding"
    ] = "This account appears misclassified."


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_binding_drift, "case_contract_sha256 does not match"),
        (
            _closure_binding_drift,
            "output_receipt_closure_sha256 does not match",
        ),
        (_unresolved_artifact, "unresolved artifact roles"),
        (_error_code_drift, "is not registered for its check"),
        (_failed_without_error, "must have at least one error"),
        (_error_on_passed_check, "must not have errors"),
        (_summary_contradiction, "summary.error_count must equal"),
        (_semantic_material, "contains unexpected fields"),
    ],
)
def test_mechanical_error_register_rejects_boundary_mutation(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    case = _case(tmp_path)
    register = copy.deepcopy(case["register"])
    mutation(register)
    current_receipts = _write_mutation_and_reseal(case, register)

    with pytest.raises(VALIDATOR.ContractValidationError, match=message):
        _validate(case, output_receipts=current_receipts)


def test_mechanical_error_register_rejects_unsorted_artifact_refs(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    register = copy.deepcopy(case["register"])
    register["check_registry"]["check-0000000000000002"]["artifact_refs"] = [
        "mechanical_errors",
        PREPARED_DATA_ROLE,
    ]
    current_receipts = _write_mutation_and_reseal(case, register)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="must be sorted and unique",
    ):
        _validate(case, output_receipts=current_receipts)


def test_mechanical_error_register_rejects_unsorted_error_codes(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    register = copy.deepcopy(case["register"])
    register["check_registry"]["check-0000000000000002"]["error_codes"].reverse()
    current_receipts = _write_mutation_and_reseal(case, register)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="must be non-empty, sorted, and unique",
    ):
        _validate(case, output_receipts=current_receipts)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda register: register["check_registry"].update(
                {
                    "check-customer-acme": register["check_registry"].pop(
                        "check-0000000000000001"
                    )
                }
            ),
            "check_registry key must be an opaque digest-shaped ID",
        ),
        (
            lambda register: register["error_registry"].update(
                {
                    "error-account-4000": register["error_registry"].pop(
                        "error-0000000000000001"
                    )
                }
            ),
            "error_registry key must be an opaque digest-shaped ID",
        ),
        (
            lambda register: register["check_registry"][
                "check-0000000000000002"
            ].update({"error_codes": ["code-acme-revenue"]}),
            "error_codes\\[\\] must be an opaque digest-shaped ID",
        ),
    ],
)
def test_mechanical_error_register_rejects_pii_like_ids(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    case = _case(tmp_path)
    register = copy.deepcopy(case["register"])
    mutation(register)
    current_receipts = _write_mutation_and_reseal(case, register)

    with pytest.raises(VALIDATOR.ContractValidationError, match=message):
        _validate(case, output_receipts=current_receipts)
    with pytest.raises(jsonschema.ValidationError):
        _schema_validator().validate(register)


def test_mechanical_error_register_rejects_stale_self_receipt_path(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    receipts = copy.deepcopy(case["output_receipts"])
    self_receipt = next(
        receipt for receipt in receipts if receipt["role"] == "mechanical_errors"
    )
    self_receipt["relative_path"] = "moved/mechanical_errors.json"

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="must use its registered generic path",
    ):
        _validate(case, output_receipts=receipts)


def test_mechanical_error_register_rejects_register_byte_drift(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    case["register_path"].write_bytes(case["register_path"].read_bytes() + b"\n")

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="do not match the current output bytes",
    ):
        _validate(case)


def test_value_validator_rejects_value_not_from_register_snapshot(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    forged = copy.deepcopy(case["register"])
    forged["check_registry"]["check-0000000000000003"] = {
        "mechanical_class": "contract",
        "error_codes": ["code-0000000000000004"],
        "status": "passed",
        "artifact_refs": ["mechanical_errors"],
    }
    forged["summary"]["check_counts"]["passed"] = 2
    self_receipt = next(
        receipt
        for receipt in case["output_receipts"]
        if receipt["role"] == "mechanical_errors"
    )

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="snapshot value must equal",
    ):
        VALIDATOR.validate_real_data_pilot_mechanical_error_register_value(
            forged,
            register_path=case["register_path"],
            register_byte_count=self_receipt["byte_count"],
            register_sha256=self_receipt["sha256"],
            expected_pilot_id=PILOT_ID,
            expected_execution_id=EXECUTION_ID,
            expected_bindings=case["expected_bindings"],
            output_receipts=case["output_receipts"],
            output_directory=case["output_directory"],
            local_run_root=case["local_run_root"],
            repository_root=ROOT,
        )


def test_mechanical_wrapper_rejects_output_root_before_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(tmp_path)
    outside_output = tmp_path.parent / f"{tmp_path.name}-outside-output"
    outside_output.mkdir()
    outside_register = outside_output / "mechanical_errors.json"
    outside_register.write_bytes(case["register_path"].read_bytes())
    snapshot_called = False

    def forbidden_snapshot(path: Path, *, root: Path) -> tuple[Any, int, str]:
        nonlocal snapshot_called
        snapshot_called = True
        raise AssertionError(f"unexpected snapshot of {path} below {root}")

    monkeypatch.setattr(
        VALIDATOR,
        "strict_json_snapshot_beneath",
        forbidden_snapshot,
    )

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="must resolve inside the declared local run root",
    ):
        VALIDATOR.validate_real_data_pilot_mechanical_error_register(
            outside_register,
            expected_pilot_id=PILOT_ID,
            expected_execution_id=EXECUTION_ID,
            expected_bindings=case["expected_bindings"],
            output_receipts=case["output_receipts"],
            output_directory=outside_output,
            local_run_root=tmp_path,
            repository_root=ROOT,
        )

    assert snapshot_called is False


def test_mechanical_error_register_rejects_non_self_receipt_drift(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    receipts = copy.deepcopy(case["output_receipts"])
    prepared_receipt = next(
        receipt for receipt in receipts if receipt["role"] == PREPARED_DATA_ROLE
    )
    prepared_receipt["sha256"] = "0" * 64

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="do not match the current output bytes",
    ):
        _validate(case, output_receipts=receipts)


def test_non_self_byte_change_invalidates_receipt_closure(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    case["prepared_path"].write_text(
        '{"synthetic":"changed"}\n',
        encoding="utf-8",
    )
    current_receipts = _seal(case)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="output-receipt closure digest does not match",
    ):
        _validate(case, output_receipts=current_receipts)


def test_mechanical_error_register_rejects_binary_float(tmp_path: Path) -> None:
    case = _case(tmp_path)
    register = copy.deepcopy(case["register"])
    register["summary"]["error_count"] = 2.0
    _write_json(case["register_path"], register)

    with pytest.raises(
        VALIDATOR.ContractValidationError,
        match="JSON fractional or exponent number",
    ):
        _validate(case)


def test_mechanical_error_schema_rejects_semantic_material() -> None:
    register = _register()
    _semantic_material(register)

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator().validate(register)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda register: register.__setitem__(
            "pilot_id",
            f"{PILOT_ID}\n",
        ),
        lambda register: register.__setitem__(
            "execution_id",
            f"{EXECUTION_ID}\n",
        ),
        lambda register: register["bindings"].__setitem__(
            "case_contract_sha256",
            f"{register['bindings']['case_contract_sha256']}\n",
        ),
        lambda register: register["check_registry"].update(
            {
                "check-0000000000000001\n": register["check_registry"].pop(
                    "check-0000000000000001"
                )
            }
        ),
        lambda register: register["error_registry"].update(
            {
                "error-0000000000000001\n": register["error_registry"].pop(
                    "error-0000000000000001"
                )
            }
        ),
        lambda register: register["check_registry"][
            "check-0000000000000002"
        ].__setitem__("error_codes", ["code-0000000000000002\n"]),
        lambda register: register["error_registry"][
            "error-0000000000000001"
        ].__setitem__("check_id", "check-0000000000000002\n"),
    ],
)
def test_mechanical_error_schema_rejects_terminal_newline_ids_and_hashes(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    register = _register()
    mutation(register)

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator().validate(register)


def test_mechanical_error_register_derives_incomplete_status(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    register = copy.deepcopy(case["register"])
    register["check_registry"]["check-0000000000000002"]["status"] = "not_run"
    register["error_registry"] = {}
    register["summary"] = {
        "overall_status": "incomplete",
        "check_counts": {
            "passed": 1,
            "failed": 0,
            "not_run": 1,
        },
        "error_count": 0,
        "class_counts": {
            mechanical_class: 0 for mechanical_class in VALIDATOR.MECHANICAL_CLASSES
        },
    }
    current_receipts = _write_mutation_and_reseal(case, register)

    result = _validate(case, output_receipts=current_receipts)

    assert result["summary"]["overall_status"] == "incomplete"
