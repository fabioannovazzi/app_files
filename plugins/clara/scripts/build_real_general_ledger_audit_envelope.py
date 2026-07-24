#!/usr/bin/env python3
"""Build an audit-only envelope for one passed real general-ledger pilot.

The adapter is deterministic because byte receipts, producer replay, exact
Decimal controls, reference closure, and output equality are mechanically
verifiable. It preserves reviewer-owned decisions by digest but deliberately
does not interpret them. This first adapter accepts successful producer runs
only; failed runs remain represented by their producer-owned mechanical
register and are not promoted into an audit envelope.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import logging
import os
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from preparation_contract_kernel import (
    AUDIT_ENVELOPE_SCHEMA_V2,
    ContractValidationError,
    canonical_json_sha256,
    file_sha256,
    file_snapshot_beneath,
    named_root_artifact_receipt,
    parse_decimal,
    reference_set,
    reviewed_decision_receipt,
    strict_json_snapshot_beneath,
    validate_audit_envelope_v2,
)
from real_data_pilot_output_boundary import seal_pilot_output_directory
from run_real_general_ledger_pilot import (
    ACCOUNT_MONTH_ROLE,
    CASE_SCHEMA_PATH,
    CASE_SCHEMA_VERSION,
    MECHANICAL_ROLE,
    RECONCILIATION_ROLE,
    SEMANTIC_DECISIONS_SCHEMA_PATH,
    SUCCESS_ROLES,
    MovementParser,
    parse_reviewed_commercial_general_journal,
    producer_contract_sha256,
    run_real_general_ledger_pilot,
)
from validate_real_data_pilot_intake import pinned_pilot_receipt_output
from validate_real_data_pilot_mechanical_errors import (
    output_receipt_closure_sha256,
    validate_real_data_pilot_mechanical_error_register,
)

__all__ = ["build_real_general_ledger_audit_envelope", "main"]

LOGGER = logging.getLogger(__name__)
ADAPTER_ID = "real_general_ledger_audit_adapter.v1"
ADAPTER_VERSION = "1.0.0"
RECONCILIATION_SCHEMA = "clara.real_general_ledger_reconciliation.v1"
AUTHORIZED_SOURCE_RELATIVE_PATH = Path("inputs/authorized-source.bin")
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_DARWIN_ACL_TYPE_EXTENDED = 0x00000100


def _has_extended_acl(path: Path) -> bool:
    """Return whether one existing path has a macOS extended ACL."""

    if sys.platform != "darwin":
        return False
    libc = ctypes.CDLL(None, use_errno=True)
    libc.acl_get_file.argtypes = [ctypes.c_char_p, ctypes.c_int]
    libc.acl_get_file.restype = ctypes.c_void_p
    libc.acl_free.argtypes = [ctypes.c_void_p]
    libc.acl_free.restype = ctypes.c_int
    ctypes.set_errno(0)
    acl = libc.acl_get_file(
        os.fsencode(path),
        _DARWIN_ACL_TYPE_EXTENDED,
    )
    if acl is None:
        error_number = ctypes.get_errno()
        if error_number in {errno.ENOENT, errno.EOPNOTSUPP}:
            return False
        raise OSError(error_number, "extended ACL could not be inspected", path)
    try:
        return True
    finally:
        if libc.acl_free(acl) != 0:
            raise OSError(
                ctypes.get_errno(),
                "extended ACL storage could not be released",
                path,
            )


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ContractValidationError(
            f"{label} must be canonical non-empty text without edge whitespace"
        )
    return value


def _integer(value: Any, *, label: str, positive: bool = False) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < (1 if positive else 0)
    ):
        qualifier = "positive" if positive else "nonnegative"
        raise ContractValidationError(f"{label} must be a {qualifier} integer")
    return value


def _exact_fields(
    value: Mapping[str, Any],
    *,
    required: frozenset[str],
    label: str,
) -> None:
    missing = sorted(required - set(value))
    unexpected = sorted(set(value) - required)
    if missing:
        raise ContractValidationError(f"{label} is missing fields: {missing}")
    if unexpected:
        raise ContractValidationError(
            f"{label} contains unexpected fields: {unexpected}"
        )


def _status(
    status: str,
    basis: str,
    *,
    artifact_refs: Sequence[str] = (),
    decision_refs: Sequence[str] = (),
    lineage_refs: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "status": status,
        "basis": basis,
        "evidence_refs": reference_set(
            artifact_refs=artifact_refs,
            decision_refs=decision_refs,
            lineage_refs=lineage_refs,
        ),
    }


def _root_id_for_path(
    path: Path,
    *,
    artifact_roots: Mapping[str, Path],
    label: str,
) -> str:
    lexical_path = Path(path).absolute()
    matches = [
        root_id
        for root_id, root in artifact_roots.items()
        if lexical_path.is_relative_to(Path(root).absolute())
    ]
    if len(matches) != 1:
        raise ContractValidationError(
            f"{label} must be below exactly one declared artifact root"
        )
    return matches[0]


def _artifact(
    artifact_roots: Mapping[str, Path],
    path: Path,
    *,
    artifact_id: str,
    role: str,
    media_type: str,
    required_root_id: str | None = None,
) -> dict[str, Any]:
    root_id = _root_id_for_path(
        path,
        artifact_roots=artifact_roots,
        label=artifact_id,
    )
    if required_root_id is not None and root_id != required_root_id:
        raise ContractValidationError(
            f"{artifact_id} must use the {required_root_id} artifact root"
        )
    return named_root_artifact_receipt(
        artifact_roots,
        path,
        root_id=root_id,
        artifact_id=artifact_id,
        role=role,
        media_type=media_type,
    )


def _require_private_staged_source(
    source_path: Path,
    *,
    pilot_root: Path,
) -> tuple[tuple[int, ...], ...]:
    """Require the privacy-preserving source locator and owner-only access."""

    expected_path = (pilot_root / AUTHORIZED_SOURCE_RELATIVE_PATH).absolute()
    if source_path != expected_path:
        raise ContractValidationError(
            "authorized source must use the fixed private staging locator "
            f"{AUTHORIZED_SOURCE_RELATIVE_PATH.as_posix()}"
        )
    inputs_directory = expected_path.parent
    identities: list[tuple[int, ...]] = []
    for path, label, expected_kind in (
        (pilot_root, "pilot_root", "directory"),
        (inputs_directory, "authorized source directory", "directory"),
        (expected_path, "authorized source", "file"),
    ):
        try:
            status = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise ContractValidationError(f"{label} could not be inspected") from exc
        if expected_kind == "directory" and not stat.S_ISDIR(status.st_mode):
            raise ContractValidationError(f"{label} must be a non-symlink directory")
        if expected_kind == "file" and not stat.S_ISREG(status.st_mode):
            raise ContractValidationError(f"{label} must be a non-symlink regular file")
        mode = stat.S_IMODE(status.st_mode)
        if mode & 0o077:
            raise ContractValidationError(f"{label} must be owner-only")
        if status.st_uid != os.geteuid():
            raise ContractValidationError(f"{label} must be owned by the current user")
        try:
            has_extended_acl = _has_extended_acl(path)
        except OSError as exc:
            raise ContractValidationError(
                f"{label} extended ACL could not be inspected"
            ) from exc
        if has_extended_acl:
            raise ContractValidationError(f"{label} must not have an extended ACL")
        identities.append(
            (
                status.st_dev,
                status.st_ino,
                stat.S_IFMT(status.st_mode),
                mode,
                status.st_uid,
                status.st_gid,
                status.st_nlink,
            )
        )
    return tuple(identities)


def _receipt_by_id(
    artifacts: Sequence[Mapping[str, Any]],
    artifact_id: str,
) -> Mapping[str, Any]:
    matches = [
        artifact for artifact in artifacts if artifact.get("artifact_id") == artifact_id
    ]
    if len(matches) != 1:
        raise ContractValidationError(
            f"exactly one {artifact_id} artifact receipt is required"
        )
    return matches[0]


def _json_bound_by_receipt(
    path: Path,
    receipt: Mapping[str, Any],
    *,
    artifact_roots: Mapping[str, Path],
    label: str,
) -> dict[str, Any]:
    root_id = _text(receipt["root_id"], label=f"{label}.root_id")
    root = Path(artifact_roots[root_id])
    payload, byte_count, digest = strict_json_snapshot_beneath(path, root=root)
    if byte_count != receipt["byte_count"] or digest != receipt["sha256"]:
        raise ContractValidationError(
            f"{label} bytes changed after artifact receipt creation"
        )
    return payload


def _expected_register_bindings(
    *,
    case_sha256: str,
    intake_receipt_sha256: str,
    semantic_receipt_sha256: str,
    output_receipts: Sequence[Mapping[str, Any]],
    producer_path: Path,
) -> dict[str, str]:
    return {
        "case_contract_sha256": case_sha256,
        "intake_receipt_sha256": intake_receipt_sha256,
        "output_receipt_closure_sha256": output_receipt_closure_sha256(output_receipts),
        "producer_contract_sha256": producer_contract_sha256(),
        "producer_implementation_sha256": file_sha256(producer_path),
        "semantic_review_receipt_sha256": semantic_receipt_sha256,
    }


def _validate_passed_reconciliation(
    reconciliation: Mapping[str, Any],
    *,
    case: Mapping[str, Any],
    case_sha256: str,
    intake_receipt_sha256: str,
    semantic_receipt_sha256: str,
    semantic_decisions_sha256: str,
    parser_layout_sha256: str,
    parser_adapter_sha256: str,
    parser_implementation_sha256: str,
    producer_path: Path,
) -> None:
    """Check only exact producer-owned structure and arithmetic closure."""

    _exact_fields(
        reconciliation,
        required=frozenset(
            {
                "schema_version",
                "pilot_id",
                "execution_id",
                "bindings",
                "counts",
                "controls",
                "sign_convention",
                "output_grain",
                "publication_status",
                "report_ready",
            }
        ),
        label="reconciliation",
    )
    expected_constants = {
        "schema_version": RECONCILIATION_SCHEMA,
        "pilot_id": case["pilot_id"],
        "execution_id": case["execution_id"],
        "sign_convention": "debit_positive_credit_negative",
        "output_grain": "source_account_x_calendar_month",
        "publication_status": "withheld",
        "report_ready": False,
    }
    for field, expected in expected_constants.items():
        if type(reconciliation[field]) is not type(expected) or (
            reconciliation[field] != expected
        ):
            raise ContractValidationError(
                f"reconciliation.{field} does not match the passed case"
            )

    bindings = _mapping(reconciliation["bindings"], label="reconciliation.bindings")
    expected_bindings = {
        "case_contract_sha256": case_sha256,
        "intake_receipt_sha256": intake_receipt_sha256,
        "parser_adapter_implementation_sha256": parser_adapter_sha256,
        "parser_implementation_sha256": parser_implementation_sha256,
        "parser_layout_sha256": parser_layout_sha256,
        "producer_contract_sha256": producer_contract_sha256(),
        "producer_implementation_sha256": file_sha256(producer_path),
        "semantic_decisions_sha256": semantic_decisions_sha256,
        "semantic_review_receipt_sha256": semantic_receipt_sha256,
        "source_sha256": _mapping(
            case["bindings"],
            label="case.bindings",
        )["source_sha256"],
    }
    _exact_fields(
        bindings,
        required=frozenset(expected_bindings),
        label="reconciliation.bindings",
    )
    if dict(bindings) != expected_bindings:
        raise ContractValidationError(
            "reconciliation bindings do not match the exact registered artifacts"
        )

    counts = _mapping(reconciliation["counts"], label="reconciliation.counts")
    _exact_fields(
        counts,
        required=frozenset({"source_movement_count", "account_month_count"}),
        label="reconciliation.counts",
    )
    _integer(
        counts["source_movement_count"],
        label="reconciliation.counts.source_movement_count",
        positive=True,
    )
    _integer(
        counts["account_month_count"],
        label="reconciliation.counts.account_month_count",
        positive=True,
    )

    controls = _mapping(reconciliation["controls"], label="reconciliation.controls")
    _exact_fields(
        controls,
        required=frozenset(
            {
                "basis",
                "reported_debit",
                "source_control_debit",
                "calculated_debit",
                "debit_difference",
                "reported_credit",
                "source_control_credit",
                "calculated_credit",
                "credit_difference",
                "tolerance",
                "status",
                "journal_balance_required",
                "monthly_balance_required",
                "balanced_month_count",
                "emitted_month_count",
                "expected_month_count",
                "expected_calendar_months",
                "emitted_calendar_months",
                "monthly_balance_status",
            }
        ),
        label="reconciliation.controls",
    )
    for field in (
        "reported_debit",
        "source_control_debit",
        "calculated_debit",
        "debit_difference",
        "reported_credit",
        "source_control_credit",
        "calculated_credit",
        "credit_difference",
        "tolerance",
    ):
        parse_decimal(
            controls[field],
            label=f"reconciliation.controls.{field}",
            canonical=True,
        )
    if controls["reported_debit"] != controls["calculated_debit"]:
        raise ContractValidationError("reconciliation debit control did not close")
    if controls["source_control_debit"] != controls["reported_debit"]:
        raise ContractValidationError(
            "reconciliation extracted debit control did not close"
        )
    if controls["reported_credit"] != controls["calculated_credit"]:
        raise ContractValidationError("reconciliation credit control did not close")
    if controls["source_control_credit"] != controls["reported_credit"]:
        raise ContractValidationError(
            "reconciliation extracted credit control did not close"
        )
    expected_control_constants = {
        "basis": "exact_extracted_final_debit_and_credit_controls",
        "debit_difference": "0",
        "credit_difference": "0",
        "tolerance": "0",
        "status": "passed",
        "journal_balance_required": True,
        "monthly_balance_required": True,
        "monthly_balance_status": "passed",
    }
    for field, expected in expected_control_constants.items():
        if type(controls[field]) is not type(expected) or controls[field] != expected:
            raise ContractValidationError(
                f"reconciliation.controls.{field} is not the passed value"
            )
    balanced_months = _integer(
        controls["balanced_month_count"],
        label="reconciliation.controls.balanced_month_count",
        positive=True,
    )
    emitted_months = _integer(
        controls["emitted_month_count"],
        label="reconciliation.controls.emitted_month_count",
        positive=True,
    )
    expected_month_count = _integer(
        controls["expected_month_count"],
        label="reconciliation.controls.expected_month_count",
        positive=True,
    )
    expected_months = controls["expected_calendar_months"]
    emitted_month_values = controls["emitted_calendar_months"]
    if (
        not isinstance(expected_months, list)
        or not isinstance(emitted_month_values, list)
        or expected_months != emitted_month_values
        or len(expected_months) != expected_month_count
    ):
        raise ContractValidationError(
            "reconciliation exact calendar-month membership did not close"
        )
    if not balanced_months == emitted_months == expected_month_count:
        raise ContractValidationError(
            "reconciliation calendar-month controls did not close"
        )


def _replay_and_compare(
    *,
    pilot_root: Path,
    repository_root: Path,
    case_path: Path,
    intake_contract_path: Path,
    intake_receipt_path: Path,
    semantic_review_path: Path,
    semantic_receipt_path: Path,
    semantic_decisions_path: Path,
    source_path: Path,
    parser_layout_path: Path,
    parser_adapter_implementation_path: Path,
    parser_implementation_path: Path,
    prepared_output_dir: Path,
    as_of_date: str,
    parser: MovementParser,
) -> list[dict[str, Any]]:
    """Replay into a fresh private leaf and require exact output receipts."""

    original_receipts = seal_pilot_output_directory(
        prepared_output_dir,
        expected_roles=SUCCESS_ROLES,
        local_run_root=pilot_root,
        repository_root=repository_root,
    )
    with TemporaryDirectory(
        prefix=".clara-m6-general-ledger-audit-replay-",
        dir=pilot_root,
    ) as raw_replay_parent:
        replay_parent = Path(raw_replay_parent)
        replay_parent.chmod(0o700)
        replay = run_real_general_ledger_pilot(
            case_path=case_path,
            intake_contract_path=intake_contract_path,
            intake_receipt_path=intake_receipt_path,
            semantic_review_path=semantic_review_path,
            semantic_receipt_path=semantic_receipt_path,
            semantic_decisions_path=semantic_decisions_path,
            source_path=source_path,
            parser_layout_path=parser_layout_path,
            parser_adapter_implementation_path=parser_adapter_implementation_path,
            parser_implementation_path=parser_implementation_path,
            output_directory=replay_parent / "output",
            local_run_root=pilot_root,
            repository_root=repository_root,
            as_of_date=as_of_date,
            parser=parser,
        )
        if replay.status != "passed":
            raise ContractValidationError(
                "the real general-ledger audit adapter supports passed runs only"
            )
        replay_receipts = [dict(receipt) for receipt in replay.output_receipts]
        if replay_receipts != original_receipts:
            raise ContractValidationError(
                "prepared output receipts do not match deterministic replay"
            )
        for receipt in original_receipts:
            relative_path = str(receipt["relative_path"])
            original_path = prepared_output_dir / relative_path
            replay_path = replay.output_directory / relative_path
            original_snapshot = file_snapshot_beneath(
                original_path,
                root=pilot_root,
            )
            replay_snapshot = file_snapshot_beneath(
                replay_path,
                root=pilot_root,
            )
            expected_snapshot = (
                receipt["byte_count"],
                receipt["sha256"],
            )
            if (
                original_snapshot != expected_snapshot
                or replay_snapshot != expected_snapshot
            ):
                raise ContractValidationError(
                    "prepared output bytes do not match deterministic replay"
                )
    current_receipts = seal_pilot_output_directory(
        prepared_output_dir,
        expected_roles=SUCCESS_ROLES,
        local_run_root=pilot_root,
        repository_root=repository_root,
    )
    if current_receipts != original_receipts:
        raise ContractValidationError(
            "prepared output bytes changed during deterministic replay"
        )
    return original_receipts


def build_real_general_ledger_audit_envelope(
    *,
    plugin_root: Path,
    pilot_root: Path,
    case_path: Path,
    intake_contract_path: Path,
    intake_receipt_path: Path,
    semantic_review_path: Path,
    semantic_receipt_path: Path,
    semantic_decisions_path: Path,
    source_path: Path,
    parser_layout_path: Path,
    parser_adapter_implementation_path: Path,
    parser_implementation_path: Path,
    prepared_output_dir: Path,
    as_of_date: str,
    parser: MovementParser = parse_reviewed_commercial_general_journal,
) -> dict[str, Any]:
    """Return a validated v2 audit envelope for one exactly replayed passed run."""

    plugin_root = Path(plugin_root).absolute()
    pilot_root = Path(pilot_root).absolute()
    artifact_roots = {"pilot": pilot_root, "plugin": plugin_root}
    repository_root = plugin_root.parent.parent
    adapter_path = Path(__file__).absolute()
    expected_adapter_path = (
        plugin_root / "scripts" / "build_real_general_ledger_audit_envelope.py"
    ).absolute()
    if adapter_path != expected_adapter_path:
        raise ContractValidationError(
            "plugin_root does not identify the Clara plugin containing this adapter"
        )
    producer_path = (
        plugin_root / "scripts" / "run_real_general_ledger_pilot.py"
    ).absolute()
    producer_contract_path = (
        plugin_root
        / "contracts"
        / "real_general_ledger_preparation_case.v1.schema.json"
    ).absolute()
    if producer_contract_path != CASE_SCHEMA_PATH.absolute():
        raise ContractValidationError(
            "plugin_root does not identify the registered producer contract"
        )
    semantic_decisions_schema_path = (
        plugin_root
        / "contracts"
        / "real_general_ledger_semantic_decisions.v1.schema.json"
    ).absolute()
    if semantic_decisions_schema_path != SEMANTIC_DECISIONS_SCHEMA_PATH.absolute():
        raise ContractValidationError(
            "plugin_root does not identify the registered semantic-decisions "
            "contract"
        )
    audit_schema_path = (
        plugin_root / "contracts" / "preparation_audit_envelope.v2.schema.json"
    ).absolute()
    kernel_path = (
        plugin_root / "scripts" / "preparation_contract_kernel.py"
    ).absolute()

    pilot_paths = {
        "case_contract": Path(case_path).absolute(),
        "intake_contract": Path(intake_contract_path).absolute(),
        "intake_receipt": Path(intake_receipt_path).absolute(),
        "semantic_review": Path(semantic_review_path).absolute(),
        "semantic_review_receipt": Path(semantic_receipt_path).absolute(),
        "semantic_decisions": Path(semantic_decisions_path).absolute(),
        "authorized_local_source": Path(source_path).absolute(),
        "parser_layout": Path(parser_layout_path).absolute(),
    }
    staged_source_identity = _require_private_staged_source(
        pilot_paths["authorized_local_source"],
        pilot_root=pilot_root,
    )
    prepared_output_dir = Path(prepared_output_dir).absolute()
    output_paths = {
        "account_month_output": (
            prepared_output_dir / SUCCESS_ROLES[ACCOUNT_MONTH_ROLE]
        ).absolute(),
        "mechanical_register": (
            prepared_output_dir / SUCCESS_ROLES[MECHANICAL_ROLE]
        ).absolute(),
        "reconciliation": (
            prepared_output_dir / SUCCESS_ROLES[RECONCILIATION_ROLE]
        ).absolute(),
    }
    if not all(path.exists() for path in output_paths.values()):
        raise ContractValidationError(
            "the real general-ledger audit adapter supports passed runs only"
        )

    artifact_specs = [
        (
            adapter_path,
            "audit_adapter",
            "audit_adapter",
            "text/x-python",
            "plugin",
        ),
        (
            audit_schema_path,
            "audit_schema",
            "audit_schema",
            "application/schema+json",
            "plugin",
        ),
        (
            kernel_path,
            "audit_kernel",
            "audit_kernel",
            "text/x-python",
            "plugin",
        ),
        (
            producer_path,
            "producer",
            "producer",
            "text/x-python",
            "plugin",
        ),
        (
            producer_contract_path,
            "producer_contract",
            "producer_contract",
            "application/schema+json",
            "plugin",
        ),
        (
            semantic_decisions_schema_path,
            "semantic_decisions_schema",
            "producer_contract_dependency",
            "application/schema+json",
            "plugin",
        ),
        (
            pilot_paths["case_contract"],
            "case_contract",
            "case_contract",
            "application/json",
            "pilot",
        ),
        (
            pilot_paths["intake_contract"],
            "intake_contract",
            "reviewed_intake_contract",
            "application/json",
            "pilot",
        ),
        (
            pilot_paths["intake_receipt"],
            "intake_receipt",
            "intake_receipt",
            "application/json",
            "pilot",
        ),
        (
            pilot_paths["semantic_review"],
            "semantic_review",
            "reviewed_semantic_contract",
            "application/json",
            "pilot",
        ),
        (
            pilot_paths["semantic_review_receipt"],
            "semantic_review_receipt",
            "semantic_review_receipt",
            "application/json",
            "pilot",
        ),
        (
            pilot_paths["semantic_decisions"],
            "semantic_decisions",
            "reviewed_semantic_decisions",
            "application/json",
            "pilot",
        ),
        (
            pilot_paths["authorized_local_source"],
            "authorized_local_source",
            "authorized_local_source",
            XLSX_MEDIA_TYPE,
            "pilot",
        ),
        (
            pilot_paths["parser_layout"],
            "parser_layout",
            "reviewed_parser_layout",
            "application/json",
            "pilot",
        ),
        (
            Path(parser_adapter_implementation_path).absolute(),
            "parser_adapter",
            "parser_adapter",
            "text/x-python",
            None,
        ),
        (
            Path(parser_implementation_path).absolute(),
            "parser_implementation",
            "parser_implementation",
            "text/x-python",
            None,
        ),
        (
            output_paths["account_month_output"],
            "account_month_output",
            "prepared_output",
            "text/csv",
            "pilot",
        ),
        (
            output_paths["mechanical_register"],
            "mechanical_register",
            "mechanical_register",
            "application/json",
            "pilot",
        ),
        (
            output_paths["reconciliation"],
            "reconciliation",
            "reconciliation",
            "application/json",
            "pilot",
        ),
    ]
    artifacts = sorted(
        [
            _artifact(
                artifact_roots,
                path,
                artifact_id=artifact_id,
                role=role,
                media_type=media_type,
                required_root_id=required_root_id,
            )
            for path, artifact_id, role, media_type, required_root_id in artifact_specs
        ],
        key=lambda item: str(item["artifact_id"]),
    )

    case = _json_bound_by_receipt(
        pilot_paths["case_contract"],
        _receipt_by_id(artifacts, "case_contract"),
        artifact_roots=artifact_roots,
        label="case contract",
    )
    intake_receipt = _receipt_by_id(artifacts, "intake_receipt")
    semantic_receipt = _receipt_by_id(artifacts, "semantic_review_receipt")
    parser_layout_receipt = _receipt_by_id(artifacts, "parser_layout")
    parser_adapter_receipt = _receipt_by_id(artifacts, "parser_adapter")
    parser_implementation_receipt = _receipt_by_id(
        artifacts,
        "parser_implementation",
    )
    output_receipts = _replay_and_compare(
        pilot_root=pilot_root,
        repository_root=repository_root,
        case_path=pilot_paths["case_contract"],
        intake_contract_path=pilot_paths["intake_contract"],
        intake_receipt_path=pilot_paths["intake_receipt"],
        semantic_review_path=pilot_paths["semantic_review"],
        semantic_receipt_path=pilot_paths["semantic_review_receipt"],
        semantic_decisions_path=pilot_paths["semantic_decisions"],
        source_path=pilot_paths["authorized_local_source"],
        parser_layout_path=pilot_paths["parser_layout"],
        parser_adapter_implementation_path=Path(
            parser_adapter_implementation_path
        ).absolute(),
        parser_implementation_path=Path(parser_implementation_path).absolute(),
        prepared_output_dir=prepared_output_dir,
        as_of_date=as_of_date,
        parser=parser,
    )

    register_bindings = _expected_register_bindings(
        case_sha256=str(_receipt_by_id(artifacts, "case_contract")["sha256"]),
        intake_receipt_sha256=str(intake_receipt["sha256"]),
        semantic_receipt_sha256=str(semantic_receipt["sha256"]),
        output_receipts=output_receipts,
        producer_path=producer_path,
    )
    register = validate_real_data_pilot_mechanical_error_register(
        output_paths["mechanical_register"],
        expected_pilot_id=_text(case["pilot_id"], label="case.pilot_id"),
        expected_execution_id=_text(
            case["execution_id"],
            label="case.execution_id",
        ),
        expected_bindings=register_bindings,
        output_receipts=output_receipts,
        output_directory=prepared_output_dir,
        local_run_root=pilot_root,
        repository_root=repository_root,
    )
    register_summary = _mapping(
        register["summary"],
        label="mechanical register.summary",
    )
    if register_summary.get("overall_status") != "passed":
        raise ContractValidationError(
            "the real general-ledger audit adapter supports passed runs only"
        )

    reconciliation = _json_bound_by_receipt(
        output_paths["reconciliation"],
        _receipt_by_id(artifacts, "reconciliation"),
        artifact_roots=artifact_roots,
        label="reconciliation",
    )
    _validate_passed_reconciliation(
        reconciliation,
        case=case,
        case_sha256=str(_receipt_by_id(artifacts, "case_contract")["sha256"]),
        intake_receipt_sha256=str(intake_receipt["sha256"]),
        semantic_receipt_sha256=str(semantic_receipt["sha256"]),
        semantic_decisions_sha256=str(
            _receipt_by_id(artifacts, "semantic_decisions")["sha256"]
        ),
        parser_layout_sha256=str(parser_layout_receipt["sha256"]),
        parser_adapter_sha256=str(parser_adapter_receipt["sha256"]),
        parser_implementation_sha256=str(parser_implementation_receipt["sha256"]),
        producer_path=producer_path,
    )

    decision_id = "reviewed_general_ledger_case_decisions"
    decision_content = {
        "case_decision_set_sha256": canonical_json_sha256(case["reviewed_decisions"]),
        "semantic_decisions_sha256": str(
            _receipt_by_id(artifacts, "semantic_decisions")["sha256"]
        ),
        "semantic_review_contract_sha256": str(
            _receipt_by_id(artifacts, "semantic_review")["sha256"]
        ),
        "semantic_review_receipt_sha256": str(semantic_receipt["sha256"]),
    }
    decisions = [
        reviewed_decision_receipt(
            decision_id=decision_id,
            decision_kind="case_owned_general_ledger_review",
            status="reviewed",
            reviewed_on=None,
            basis=(
                "Exact reviewer-owned decision artifacts are bound without "
                "semantic interpretation by this adapter."
            ),
            content=decision_content,
            evidence_refs=reference_set(
                artifact_refs=(
                    "case_contract",
                    "semantic_decisions",
                    "semantic_review",
                    "semantic_review_receipt",
                )
            ),
        )
    ]

    register_checks = _mapping(
        register["check_registry"],
        label="mechanical register.check_registry",
    )
    checks = [
        {
            "check_id": "audit_exact_output_replay",
            "check_kind": "exact_output_receipt_and_byte_replay",
            "required": True,
            "status": "passed",
            "references": reference_set(
                artifact_refs=(
                    "account_month_output",
                    "mechanical_register",
                    "producer",
                    "reconciliation",
                )
            ),
            "numeric_evidence": [],
            "details": {"comparison": "exact_portable_output_set"},
        }
    ]
    for check_id, raw_check in register_checks.items():
        check = _mapping(
            raw_check,
            label=f"mechanical register.check_registry.{check_id}",
        )
        if check["status"] != "passed":
            raise ContractValidationError(
                "passed producer register contains a non-passed check"
            )
        mechanical_class = _text(
            check["mechanical_class"],
            label=f"mechanical register.check_registry.{check_id}.mechanical_class",
        )
        checks.append(
            {
                "check_id": str(check_id),
                "check_kind": f"producer_declared_{mechanical_class}",
                "required": True,
                "status": "passed",
                "references": reference_set(
                    artifact_refs=("mechanical_register", "reconciliation"),
                    decision_refs=(decision_id,),
                ),
                "numeric_evidence": [],
                "details": {
                    "registered_error_code_count": len(check["error_codes"]),
                },
            }
        )
    checks.sort(key=lambda item: str(item["check_id"]))

    output_artifact_ids = (
        "account_month_output",
        "mechanical_register",
        "reconciliation",
    )
    lineage_ids = {
        "account_month_output": "01_account_month_output_artifact",
        "mechanical_register": "02_mechanical_register_artifact",
        "reconciliation": "03_reconciliation_artifact",
    }
    derivation_artifacts = (
        "authorized_local_source",
        "case_contract",
        "intake_contract",
        "intake_receipt",
        "parser_adapter",
        "parser_implementation",
        "parser_layout",
        "producer",
        "producer_contract",
        "semantic_decisions",
        "semantic_decisions_schema",
        "semantic_review",
        "semantic_review_receipt",
    )
    artifact_lineage = [
        {
            "lineage_id": lineage_ids[artifact_id],
            "artifact_ref": artifact_id,
            "references": reference_set(
                artifact_refs=derivation_artifacts,
                decision_refs=(decision_id,),
            ),
            "details": {
                "scope": "exact_producer_replay_and_artifact_receipt_closure",
                "semantic_validation": "not_assessed",
            },
        }
        for artifact_id in output_artifact_ids
    ]
    numeric_constraints = {
        "arithmetic": "decimal_exact",
        "control_basis": ("case_owned_exact_extracted_final_debit_and_credit_controls"),
        "comparison": "exact_equality",
        "output_grain": "case_owned_source_account_x_calendar_month",
        "sign_convention": "case_owned_debit_positive_credit_negative",
        "tolerance": "0",
    }
    execution_inputs = sorted(derivation_artifacts)
    envelope: dict[str, Any] = {
        "schema_version": AUDIT_ENVELOPE_SCHEMA_V2,
        "case": {
            "case_id": _text(case["pilot_id"], label="case.pilot_id"),
            "case_kind": "reviewed_private_commercial_general_ledger_pilot",
            "source_schema_version": _text(
                case["schema_version"],
                label="case.schema_version",
            ),
            "case_artifact_ref": "case_contract",
        },
        "adapter": {
            "adapter_id": ADAPTER_ID,
            "adapter_version": ADAPTER_VERSION,
            "implementation_sha256": file_sha256(adapter_path),
            "normalization_scope": "audit_only",
        },
        "local_artifacts": artifacts,
        "remote_sources": [],
        "reviewed_decisions": decisions,
        "execution": {
            "execution_id": _text(
                case["execution_id"],
                label="case.execution_id",
            ),
            "producer": producer_path.name,
            "producer_version": CASE_SCHEMA_VERSION,
            "producer_sha256": file_sha256(producer_path),
            "mode": "deterministic_mechanical",
            "input_artifact_refs": execution_inputs,
            "output_artifact_refs": sorted(output_artifact_ids),
        },
        "numeric_policy": {
            "representation": "decimal_string",
            "finite_only": True,
            "binary_float_allowed": False,
            "exponent_notation_allowed": False,
            "canonical_serialization_required": True,
            "case_constraints": numeric_constraints,
            "case_constraints_sha256": canonical_json_sha256(numeric_constraints),
        },
        "reconciliation": {"checks": checks, "errors": []},
        "lineage": {
            "artifact": {
                "declared": True,
                "records": artifact_lineage,
                "limitations": [],
            },
            "aggregate": {
                "declared": False,
                "records": [],
                "limitations": [
                    "The current producer evidence binds the complete output "
                    "receipt closure but does not expose the prepared-output "
                    "digest through the aggregate-lineage JSON-pointer contract."
                ],
            },
            "row": {
                "declared": False,
                "records": [],
                "limitations": ["No source-row or cell-level lineage is asserted."],
            },
        },
        "statuses": {
            "validation": _status(
                "passed",
                "Exact named-root receipts and complete producer replay passed.",
                artifact_refs=(
                    "audit_adapter",
                    "audit_kernel",
                    "audit_schema",
                    "mechanical_register",
                    "producer",
                ),
            ),
            "preparation": _status(
                "passed",
                "The registered producer reproduced the complete output set.",
                artifact_refs=output_artifact_ids,
                decision_refs=(decision_id,),
                lineage_refs=tuple(lineage_ids.values()),
            ),
            "reconciliation": _status(
                "passed",
                "Producer-owned exact journal and calendar-month controls passed.",
                artifact_refs=("mechanical_register", "reconciliation"),
                decision_refs=(decision_id,),
            ),
            "semantic": _status(
                "not_assessed",
                "Reviewer-owned decisions are bound but are not judged here.",
                artifact_refs=(
                    "case_contract",
                    "semantic_decisions",
                    "semantic_review",
                    "semantic_review_receipt",
                ),
                decision_refs=(decision_id,),
            ),
            "source": _status(
                "local_receipt_only",
                "Exact declared-authorized local bytes are bound without a "
                "remote receipt.",
                artifact_refs=(
                    "authorized_local_source",
                    "intake_contract",
                    "intake_receipt",
                ),
            ),
            "downstream": _status(
                "not_assessed",
                "Interpretation, plotting, reporting, and rendering are unassessed.",
                artifact_refs=("account_month_output", "reconciliation"),
            ),
            "publication": _status(
                "withheld",
                "The private pilot artifacts are not authorized for publication.",
                artifact_refs=("case_contract", "reconciliation"),
                decision_refs=(decision_id,),
            ),
        },
        "report_ready": False,
        "limitations": [
            {
                "limitation_id": "01_local_source_authority",
                "scope": "source",
                "statement": (
                    "Exact local byte receipts do not prove source authority, "
                    "legal permission, or future file immutability."
                ),
            },
            {
                "limitation_id": "02_semantic_authority",
                "scope": "semantic",
                "statement": (
                    "Dataset meaning, accounting decisions, and reviewer "
                    "authority remain reviewed rather than mechanically proven."
                ),
            },
            {
                "limitation_id": "03_success_only_profile",
                "scope": "adapter",
                "statement": (
                    "This adapter accepts passed producer runs only; failure-only "
                    "runs remain represented by their mechanical register."
                ),
            },
            {
                "limitation_id": "04_aggregate_lineage",
                "scope": "lineage",
                "statement": (
                    "Output receipt closure is exact, but aggregate-lineage "
                    "authority is not claimed by this envelope."
                ),
            },
            {
                "limitation_id": "05_row_lineage",
                "scope": "lineage",
                "statement": "No source-row or cell-level lineage is claimed.",
            },
            {
                "limitation_id": "06_downstream_readiness",
                "scope": "downstream",
                "statement": (
                    "Interpretation, plotting, reporting compatibility, report "
                    "readiness, and publication approval remain unassessed."
                ),
            },
        ],
    }
    validated_envelope = validate_audit_envelope_v2(
        envelope,
        artifact_roots=artifact_roots,
    )
    if (
        _require_private_staged_source(
            pilot_paths["authorized_local_source"],
            pilot_root=pilot_root,
        )
        != staged_source_identity
    ):
        raise ContractValidationError(
            "authorized source staging identity changed during audit validation"
        )
    return validated_envelope


def main(argv: Sequence[str] | None = None) -> int:
    """Run the passed real general-ledger audit adapter."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--pilot-root", type=Path, required=True)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--intake-contract", type=Path, required=True)
    parser.add_argument("--intake-receipt", type=Path, required=True)
    parser.add_argument("--semantic-review", type=Path, required=True)
    parser.add_argument("--semantic-receipt", type=Path, required=True)
    parser.add_argument("--semantic-decisions", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--parser-layout", type=Path, required=True)
    parser.add_argument(
        "--parser-adapter-implementation",
        type=Path,
        required=True,
    )
    parser.add_argument("--parser-implementation", type=Path, required=True)
    parser.add_argument("--prepared-output-dir", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        envelope = build_real_general_ledger_audit_envelope(
            plugin_root=args.plugin_root,
            pilot_root=args.pilot_root,
            case_path=args.case,
            intake_contract_path=args.intake_contract,
            intake_receipt_path=args.intake_receipt,
            semantic_review_path=args.semantic_review,
            semantic_receipt_path=args.semantic_receipt,
            semantic_decisions_path=args.semantic_decisions,
            source_path=args.source,
            parser_layout_path=args.parser_layout,
            parser_adapter_implementation_path=(args.parser_adapter_implementation),
            parser_implementation_path=args.parser_implementation,
            prepared_output_dir=args.prepared_output_dir,
            as_of_date=args.as_of_date,
        )
        with pinned_pilot_receipt_output(
            args.output,
            local_run_root=args.pilot_root,
        ) as pinned_output:
            pinned_output.write_json(envelope)
    except (ContractValidationError, OSError, TypeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Real general-ledger audit envelope: %s", envelope["case"]["case_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
