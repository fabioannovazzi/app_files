from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from decimal import Decimal, getcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

import jsonschema
import pytest
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SCRIPTS_ROOT = CLARA_ROOT / "scripts"
CONTRACT_SCHEMA = CLARA_ROOT / "contracts" / "preparation_audit_envelope.v1.schema.json"
CONTRACT_SCHEMA_V2 = (
    CLARA_ROOT / "contracts" / "preparation_audit_envelope.v2.schema.json"
)
FASTENAL_ROOT = CLARA_ROOT / "evals" / "public_truth" / "fastenal_q1_2025"
WD40_ROOT = CLARA_ROOT / "evals" / "preparation" / "wd40_fy2025"
FASTENAL_REPORT = FASTENAL_ROOT / "expected_validation_report.json"
WD40_EXPECTED = WD40_ROOT / "expected"
EXPECTED_ENVELOPE_SHA256 = {
    "fastenal_q1_2025": "791e2f67f140f0f7b3f851981ef514426c5b66afeb82cd463cc2c15b4782e79e",
    "wd40-fy2025-synthetic-monthly-pnl": (
        "319925f9a84510bc4f48cb4b4bd6013ec34662bf757c67e213c798b2f2d85d5c"
    ),
}
EXPECTED_M2_NUMERIC_BOUNDS = {
    "maximum_input_digits": 38,
    "maximum_input_scale": 6,
    "calculation_precision": 128,
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


KERNEL = _load_module(
    "preparation_contract_kernel",
    SCRIPTS_ROOT / "preparation_contract_kernel.py",
)
PUBLIC_ADAPTER = _load_module(
    "clara_public_truth_audit_adapter_test",
    SCRIPTS_ROOT / "build_public_truth_audit_envelope.py",
)
MONTHLY_ADAPTER = _load_module(
    "clara_monthly_pnl_audit_adapter_test",
    SCRIPTS_ROOT / "build_monthly_pnl_audit_envelope.py",
)
MONTHLY_PREPARER = _load_module(
    "clara_monthly_pnl_preparer_for_m3_test",
    SCRIPTS_ROOT / "prepare_monthly_pnl_case.py",
)
PUBLIC_VALIDATOR = _load_module(
    "clara_public_truth_validator_for_m3_test",
    SCRIPTS_ROOT / "validate_public_truth_benchmark.py",
)


def _fastenal_envelope() -> dict[str, Any]:
    return PUBLIC_ADAPTER.build_public_truth_audit_envelope(
        clara_root=CLARA_ROOT,
        benchmark_path=FASTENAL_ROOT / "benchmark.json",
        candidate_path=FASTENAL_ROOT / "expected_prepared_observations.csv",
        validation_report_path=FASTENAL_REPORT,
    )


def _wd40_envelope() -> dict[str, Any]:
    return MONTHLY_ADAPTER.build_monthly_pnl_audit_envelope(
        clara_root=CLARA_ROOT,
        case_path=WD40_ROOT / "case.json",
        prepared_output_dir=WD40_EXPECTED,
    )


def _schema_validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )


def _schema_validator_v2() -> jsonschema.Draft202012Validator:
    v1_schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
    v2_schema = json.loads(CONTRACT_SCHEMA_V2.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(v2_schema)
    registry = Registry().with_resource(
        v1_schema["$id"],
        Resource.from_contents(v1_schema),
    )
    return jsonschema.Draft202012Validator(
        v2_schema,
        registry=registry,
        format_checker=jsonschema.FormatChecker(),
    )


def _write_test_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _v2_local_source_envelope(
    tmp_path: Path,
) -> tuple[dict[str, Any], dict[str, Path]]:
    plugin_root = tmp_path / "plugin"
    plugin_contracts = plugin_root / "contracts"
    plugin_scripts = plugin_root / "scripts"
    plugin_contracts.mkdir(parents=True)
    plugin_scripts.mkdir()
    audit_schema_path = plugin_contracts / CONTRACT_SCHEMA_V2.name
    audit_schema_path.write_bytes(CONTRACT_SCHEMA_V2.read_bytes())
    audit_adapter_path = plugin_scripts / "build_test_audit_envelope.py"
    audit_adapter_path.write_text(
        '"""Synthetic v2 audit adapter fixture."""\n',
        encoding="utf-8",
    )
    producer_path = plugin_scripts / "prepare_test_case.py"
    producer_path.write_text(
        '"""Synthetic v2 preparation fixture."""\n',
        encoding="utf-8",
    )
    pilot_root = tmp_path / "pilot"
    pilot_root.mkdir()
    source_path = pilot_root / "authorized-source.bin"
    source_path.write_bytes(b"synthetic authorized source bytes\n")
    case_path = pilot_root / "case.json"
    _write_test_json(
        case_path,
        {
            "schema_version": "clara.test_local_case.v1",
            "review_status": "reviewed",
        },
    )
    output_path = pilot_root / "prepared.csv"
    output_path.write_text(
        "account,period,value\nsynthetic,2026-01,0\n",
        encoding="utf-8",
    )
    roots = {"plugin": plugin_root, "pilot": pilot_root}
    artifact_specs = [
        (
            "audit_adapter",
            "plugin",
            audit_adapter_path,
            "audit_adapter",
            "text/x-python",
        ),
        (
            "audit_schema",
            "plugin",
            audit_schema_path,
            "audit_schema",
            "application/schema+json",
        ),
        (
            "authorized_source",
            "pilot",
            source_path,
            "authorized_local_source",
            "application/octet-stream",
        ),
        (
            "case_contract",
            "pilot",
            case_path,
            "case_contract",
            "application/json",
        ),
        (
            "prepared_output",
            "pilot",
            output_path,
            "prepared_output",
            "text/csv",
        ),
        (
            "producer",
            "plugin",
            producer_path,
            "producer",
            "text/x-python",
        ),
    ]
    artifacts = [
        KERNEL.named_root_artifact_receipt(
            roots,
            path,
            root_id=root_id,
            artifact_id=artifact_id,
            role=role,
            media_type=media_type,
        )
        for artifact_id, root_id, path, role, media_type in artifact_specs
    ]
    artifacts_by_id = {str(artifact["artifact_id"]): artifact for artifact in artifacts}
    decision_content = {
        "decision": "Synthetic local-source contract reviewed for kernel testing."
    }
    decision = KERNEL.reviewed_decision_receipt(
        decision_id="local_source_review",
        decision_kind="case_owned_local_source_contract",
        status="reviewed",
        reviewed_on="2026-07-24",
        basis="Synthetic test evidence only.",
        content=decision_content,
        evidence_refs=KERNEL.reference_set(
            artifact_refs=("authorized_source", "case_contract"),
        ),
        version="1.0.0",
    )

    def status(
        value: str,
        basis: str,
        *artifact_refs: str,
        decision_refs: tuple[str, ...] = (),
        lineage_refs: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        return {
            "status": value,
            "basis": basis,
            "evidence_refs": KERNEL.reference_set(
                artifact_refs=artifact_refs,
                decision_refs=decision_refs,
                lineage_refs=lineage_refs,
            ),
        }

    numeric_constraints = {
        "arithmetic": "decimal_exact",
        "tolerance_selection": "case_owned",
    }
    envelope = {
        "schema_version": KERNEL.AUDIT_ENVELOPE_SCHEMA_V2,
        "case": {
            "case_id": "synthetic_local_source_case",
            "case_kind": "synthetic_local_source_kernel_test",
            "source_schema_version": "clara.test_local_case.v1",
            "case_artifact_ref": "case_contract",
        },
        "adapter": {
            "adapter_id": "local_source_audit_adapter.v1",
            "adapter_version": "1.0.0",
            "implementation_sha256": artifacts_by_id["audit_adapter"]["sha256"],
            "normalization_scope": "audit_only",
        },
        "local_artifacts": artifacts,
        "remote_sources": [],
        "reviewed_decisions": [decision],
        "execution": {
            "execution_id": "local_source_preparation.v1",
            "producer": "prepare_test_case.py",
            "producer_version": "1.0.0",
            "producer_sha256": artifacts_by_id["producer"]["sha256"],
            "mode": "deterministic_mechanical",
            "input_artifact_refs": ["authorized_source", "case_contract"],
            "output_artifact_refs": ["prepared_output"],
        },
        "numeric_policy": {
            "representation": "decimal_string",
            "finite_only": True,
            "binary_float_allowed": False,
            "exponent_notation_allowed": False,
            "canonical_serialization_required": True,
            "case_constraints": numeric_constraints,
            "case_constraints_sha256": KERNEL.canonical_json_sha256(
                numeric_constraints
            ),
        },
        "reconciliation": {
            "checks": [
                {
                    "check_id": "local_source_bytes",
                    "check_kind": "exact_local_source_receipt",
                    "required": True,
                    "status": "passed",
                    "references": KERNEL.reference_set(
                        artifact_refs=("authorized_source", "prepared_output"),
                        decision_refs=("local_source_review",),
                    ),
                    "numeric_evidence": [],
                    "details": {"scope": "synthetic_test_only"},
                }
            ],
            "errors": [],
        },
        "lineage": {
            "artifact": {
                "declared": True,
                "records": [
                    {
                        "lineage_id": "01_prepared_output",
                        "artifact_ref": "prepared_output",
                        "references": KERNEL.reference_set(
                            artifact_refs=(
                                "authorized_source",
                                "case_contract",
                                "prepared_output",
                            ),
                            decision_refs=("local_source_review",),
                        ),
                        "details": {"scope": "artifact_receipt_closure"},
                    }
                ],
                "limitations": [],
            },
            "aggregate": {
                "declared": False,
                "records": [],
                "limitations": ["No aggregate lineage is claimed by this test."],
            },
            "row": {
                "declared": False,
                "records": [],
                "limitations": ["Row lineage remains unsupported."],
            },
        },
        "statuses": {
            "validation": status(
                "passed",
                "Exact local artifacts and references passed validation.",
                "authorized_source",
                "prepared_output",
            ),
            "preparation": status(
                "passed",
                "The registered synthetic producer result passed.",
                "prepared_output",
                lineage_refs=("01_prepared_output",),
            ),
            "reconciliation": status(
                "passed",
                "The required local-source receipt check passed.",
                "authorized_source",
                "prepared_output",
                decision_refs=("local_source_review",),
            ),
            "semantic": status(
                "not_assessed",
                "Decision presence is bound without judging its correctness.",
                "case_contract",
                decision_refs=("local_source_review",),
            ),
            "source": status(
                "local_receipt_only",
                "Exact local bytes are bound without a fabricated remote receipt.",
                "authorized_source",
                "case_contract",
            ),
            "downstream": status(
                "not_assessed",
                "Downstream compatibility is not assessed.",
                "prepared_output",
            ),
            "publication": status(
                "withheld",
                "The local-source test is not publication authorization.",
                "case_contract",
            ),
        },
        "report_ready": False,
        "limitations": [
            {
                "limitation_id": "01_local_authority",
                "scope": "source",
                "statement": "Exact local bytes do not prove source authority.",
            },
            {
                "limitation_id": "02_semantics",
                "scope": "semantic",
                "statement": "Mechanical validation does not prove semantic correctness.",
            },
        ],
    }
    return envelope, roots


def _declare_v2_aggregate_lineage(
    envelope: dict[str, Any],
    roots: dict[str, Path],
) -> Path:
    prepared_artifact = next(
        artifact
        for artifact in envelope["local_artifacts"]
        if artifact["artifact_id"] == "prepared_output"
    )
    evidence_value = {
        "aggregate_id": "account_month",
        "output_artifact_id": "prepared_output",
        "output_sha256": prepared_artifact["sha256"],
    }
    evidence_path = roots["pilot"] / "aggregate-evidence.json"
    _write_test_json(evidence_path, evidence_value)
    evidence_artifact = KERNEL.named_root_artifact_receipt(
        roots,
        evidence_path,
        root_id="pilot",
        artifact_id="aggregate_evidence",
        role="aggregate_lineage_evidence",
        media_type="application/json",
    )
    envelope["local_artifacts"].append(evidence_artifact)
    envelope["local_artifacts"].sort(key=lambda artifact: artifact["artifact_id"])
    envelope["execution"]["output_artifact_refs"] = [
        "aggregate_evidence",
        "prepared_output",
    ]
    envelope["lineage"]["aggregate"] = {
        "declared": True,
        "records": [
            {
                "lineage_id": "02_account_month",
                "aggregate_id": "account_month",
                "output_artifact_ref": "prepared_output",
                "evidence_artifact_ref": "aggregate_evidence",
                "evidence_json_pointer": "",
                "aggregate_id_json_pointer": "/aggregate_id",
                "output_artifact_id_json_pointer": "/output_artifact_id",
                "output_sha256_json_pointer": "/output_sha256",
                "evidence_sha256": KERNEL.canonical_json_sha256(evidence_value),
                "references": KERNEL.reference_set(
                    artifact_refs=(
                        "aggregate_evidence",
                        "authorized_source",
                        "case_contract",
                        "prepared_output",
                    ),
                    decision_refs=("local_source_review",),
                ),
                "details": {"scope": "synthetic_account_month"},
            }
        ],
        "limitations": [],
    }
    return evidence_path


def _relocate_v2_artifact(
    envelope: dict[str, Any],
    roots: dict[str, Path],
    *,
    artifact_id: str,
    root_id: str,
) -> None:
    artifact = next(
        item
        for item in envelope["local_artifacts"]
        if item["artifact_id"] == artifact_id
    )
    source_path = roots[artifact["root_id"]] / artifact["path"]
    destination_directory = roots[root_id] / "relocated"
    destination_directory.mkdir(exist_ok=True)
    destination_path = destination_directory / source_path.name
    destination_path.write_bytes(source_path.read_bytes())
    relocated = KERNEL.named_root_artifact_receipt(
        roots,
        destination_path,
        root_id=root_id,
        artifact_id=artifact_id,
        role=artifact["role"],
        media_type=artifact.get("media_type"),
    )
    artifact.clear()
    artifact.update(relocated)


def _mutate_monthly_output_bytes(output_dir: Path) -> None:
    path = output_dir / "monthly_pnl.csv"
    path.write_bytes(path.read_bytes() + b"\n")


def _mutate_monthly_manifest_engine(output_dir: Path) -> None:
    path = output_dir / "prepared_evidence_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["recipe"]["engine_sha256"] = "0" * 64
    _write_test_json(path, payload)


def _forge_monthly_reconciliation_and_reseal_manifest(output_dir: Path) -> None:
    reconciliation_path = output_dir / "reconciliation.json"
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    reconciliation["counts"]["monthly_pnl_rows"] += 1
    _write_test_json(reconciliation_path, reconciliation)

    manifest_path = output_dir / "prepared_evidence_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reconciliation_digest = hashlib.sha256(reconciliation_path.read_bytes()).hexdigest()
    manifest["reconciliation"]["sha256"] = reconciliation_digest
    reconciliation_receipt = next(
        item for item in manifest["outputs"] if item["artifact_id"] == "reconciliation"
    )
    reconciliation_receipt["sha256"] = reconciliation_digest
    reconciliation_receipt["size_bytes"] = reconciliation_path.stat().st_size
    manifest["canonical_output_set_sha256"] = KERNEL.canonical_json_sha256(
        manifest["outputs"]
    )
    _write_test_json(manifest_path, manifest)


def _copy_failed_monthly_case(case_root: Path) -> Path:
    shutil.copytree(WD40_ROOT, case_root)
    case_path = case_root / "case.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    trial_balance = case_root / case["files"]["synthetic_monthly_trial_balance"]["path"]
    with trial_balance.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)
    rows.append(dict(rows[0]))
    with trial_balance.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    case["files"]["synthetic_monthly_trial_balance"]["sha256"] = hashlib.sha256(
        trial_balance.read_bytes()
    ).hexdigest()
    _write_test_json(case_path, case)
    return case_path


@pytest.mark.parametrize(
    ("builder", "case_id", "preparation_status", "aggregate_declared"),
    [
        (_fastenal_envelope, "fastenal_q1_2025", "not_assessed", False),
        (
            _wd40_envelope,
            "wd40-fy2025-synthetic-monthly-pnl",
            "passed",
            True,
        ),
    ],
)
def test_preparation_audit_adapter_emits_valid_bounded_envelope(
    builder: Callable[[], dict[str, Any]],
    case_id: str,
    preparation_status: str,
    aggregate_declared: bool,
) -> None:
    envelope = builder()

    _schema_validator().validate(envelope)
    assert envelope["case"]["case_id"] == case_id
    assert envelope["statuses"]["preparation"]["status"] == preparation_status
    assert envelope["statuses"]["semantic"]["status"] == "not_assessed"
    assert envelope["statuses"]["source"]["status"] == "receipt_only"
    assert envelope["statuses"]["downstream"]["status"] == "not_assessed"
    assert envelope["statuses"]["publication"]["status"] == "withheld"
    assert envelope["report_ready"] is False
    assert envelope["lineage"]["aggregate"]["declared"] is aggregate_declared
    assert envelope["lineage"]["row"] == {
        "declared": False,
        "records": [],
        "limitations": envelope["lineage"]["row"]["limitations"],
    }
    assert all(
        source["receipt_scope"] == "declared_remote_receipt"
        for source in envelope["remote_sources"]
    )


def test_preparation_audit_runtime_and_schema_reject_padded_identifier() -> None:
    envelope = _fastenal_envelope()
    envelope["case"]["case_id"] = " padded-case "

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="case.case_id must not contain edge whitespace",
    ):
        KERNEL.validate_audit_envelope(envelope, root=CLARA_ROOT)

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator().validate(envelope)


def test_v2_audit_envelope_binds_exact_local_source_without_remote_receipt(
    tmp_path: Path,
) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)

    validated = KERNEL.validate_audit_envelope_v2(
        envelope,
        artifact_roots=roots,
    )
    _schema_validator_v2().validate(validated)

    assert validated["remote_sources"] == []
    assert validated["statuses"]["source"]["status"] == "local_receipt_only"
    source_artifact = next(
        artifact
        for artifact in validated["local_artifacts"]
        if artifact["role"] == "authorized_local_source"
    )
    assert source_artifact["root_id"] == "pilot"
    assert source_artifact["artifact_id"] in (
        validated["execution"]["input_artifact_refs"]
    )
    assert validated["report_ready"] is False


def test_v2_validation_rejects_audit_schema_replaced_after_receipt_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)
    schema_artifact = next(
        artifact
        for artifact in envelope["local_artifacts"]
        if artifact["role"] == "audit_schema"
    )
    schema_path = roots["plugin"] / schema_artifact["path"]
    original_snapshot = KERNEL.strict_json_snapshot_beneath
    replaced = False

    def replace_before_snapshot(
        path: Path,
        *,
        root: Path,
    ) -> tuple[dict[str, Any], int, str]:
        nonlocal replaced
        if Path(path) == schema_path and not replaced:
            replacement = schema_path.with_name("replacement-schema.json")
            _write_test_json(
                replacement,
                {
                    "properties": {
                        "schema_version": {
                            "const": KERNEL.AUDIT_ENVELOPE_SCHEMA_V2,
                        }
                    },
                    "replacement_marker": True,
                },
            )
            replacement.replace(schema_path)
            replaced = True
        return original_snapshot(path, root=root)

    monkeypatch.setattr(
        KERNEL,
        "strict_json_snapshot_beneath",
        replace_before_snapshot,
    )

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="audit schema artifact bytes changed after artifact receipt validation",
    ):
        KERNEL.validate_audit_envelope_v2(envelope, artifact_roots=roots)


def test_v2_validation_rejects_aggregate_evidence_replaced_after_receipt_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)
    evidence_path = _declare_v2_aggregate_lineage(envelope, roots)
    original_snapshot = KERNEL.strict_json_snapshot_beneath
    replaced = False

    def replace_before_snapshot(
        path: Path,
        *,
        root: Path,
    ) -> tuple[dict[str, Any], int, str]:
        nonlocal replaced
        if Path(path) == evidence_path and not replaced:
            replacement = evidence_path.with_name("replacement-evidence.json")
            evidence_value = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence_value["replacement_marker"] = True
            _write_test_json(replacement, evidence_value)
            replacement.replace(evidence_path)
            replaced = True
        return original_snapshot(path, root=root)

    monkeypatch.setattr(
        KERNEL,
        "strict_json_snapshot_beneath",
        replace_before_snapshot,
    )

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="evidence_artifact bytes changed after artifact receipt validation",
    ):
        KERNEL.validate_audit_envelope_v2(envelope, artifact_roots=roots)


def test_v2_named_root_receipt_rejects_symlink_source(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    pilot_root = tmp_path / "pilot"
    outside_root = tmp_path / "outside"
    plugin_root.mkdir()
    pilot_root.mkdir()
    outside_root.mkdir()
    outside_source = outside_root / "source.bin"
    outside_source.write_bytes(b"synthetic outside bytes\n")
    source_link = pilot_root / "source.bin"
    source_link.symlink_to(outside_source)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="could not safely open",
    ):
        KERNEL.named_root_artifact_receipt(
            {"plugin": plugin_root, "pilot": pilot_root},
            source_link,
            root_id="pilot",
            artifact_id="authorized_source",
            role="authorized_local_source",
        )


def test_v2_named_root_receipt_rejects_pilot_root_nested_below_plugin(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    pilot_root = plugin_root / "pilot"
    pilot_root.mkdir(parents=True)
    source_path = pilot_root / "source.bin"
    source_path.write_bytes(b"synthetic source\n")

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="distinct and non-overlapping",
    ):
        KERNEL.named_root_artifact_receipt(
            {"plugin": plugin_root, "pilot": pilot_root},
            source_path,
            root_id="pilot",
            artifact_id="authorized_source",
            role="authorized_local_source",
        )


def test_v2_named_root_receipt_rejects_plugin_root_nested_below_pilot(
    tmp_path: Path,
) -> None:
    pilot_root = tmp_path / "pilot"
    plugin_root = pilot_root / "plugin"
    plugin_root.mkdir(parents=True)
    source_path = pilot_root / "source.bin"
    source_path.write_bytes(b"synthetic source\n")

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="distinct and non-overlapping",
    ):
        KERNEL.named_root_artifact_receipt(
            {"plugin": plugin_root, "pilot": pilot_root},
            source_path,
            root_id="pilot",
            artifact_id="authorized_source",
            role="authorized_local_source",
        )


def test_v2_named_root_receipt_rejects_symlink_root_alias(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    pilot_alias = tmp_path / "pilot"
    pilot_alias.symlink_to(plugin_root, target_is_directory=True)
    source_path = plugin_root / "source.bin"
    source_path.write_bytes(b"synthetic source\n")

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="non-symlink directory",
    ):
        KERNEL.named_root_artifact_receipt(
            {"plugin": plugin_root, "pilot": pilot_alias},
            source_path,
            root_id="pilot",
            artifact_id="authorized_source",
            role="authorized_local_source",
        )


def test_v2_validation_rejects_source_replaced_by_symlink(tmp_path: Path) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)
    source_artifact = next(
        artifact
        for artifact in envelope["local_artifacts"]
        if artifact["role"] == "authorized_local_source"
    )
    source_path = roots["pilot"] / source_artifact["path"]
    outside = tmp_path / "outside.bin"
    outside.write_bytes(source_path.read_bytes())
    source_path.unlink()
    source_path.symlink_to(outside)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="could not safely open",
    ):
        KERNEL.validate_audit_envelope_v2(envelope, artifact_roots=roots)


def test_v2_validation_rejects_hard_linked_source(tmp_path: Path) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)
    source_artifact = next(
        artifact
        for artifact in envelope["local_artifacts"]
        if artifact["role"] == "authorized_local_source"
    )
    source_path = roots["pilot"] / source_artifact["path"]
    source_path.with_name("source-alias.bin").hardlink_to(source_path)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="must not be hard linked",
    ):
        KERNEL.validate_audit_envelope_v2(envelope, artifact_roots=roots)


def test_v2_validation_and_schema_reject_fabricated_remote_receipt(
    tmp_path: Path,
) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)
    envelope["remote_sources"] = [
        {
            "source_id": "fabricated_source",
            "title": "Fabricated source",
            "document_type": "workbook",
            "url": "https://example.com/fabricated.xlsx",
            "byte_count": 1,
            "sha256": "0" * 64,
            "receipt_scope": "declared_remote_receipt",
        }
    ]

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="remote_sources must be empty",
    ):
        KERNEL.validate_audit_envelope_v2(envelope, artifact_roots=roots)
    with pytest.raises(jsonschema.ValidationError):
        _schema_validator_v2().validate(envelope)


def test_v2_runtime_and_schema_reject_padded_artifact_media_type(
    tmp_path: Path,
) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)
    source_artifact = next(
        artifact
        for artifact in envelope["local_artifacts"]
        if artifact["role"] == "authorized_local_source"
    )
    source_artifact["media_type"] = " application/octet-stream "

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="media_type must not contain edge whitespace",
    ):
        KERNEL.validate_audit_envelope_v2(envelope, artifact_roots=roots)
    with pytest.raises(jsonschema.ValidationError):
        _schema_validator_v2().validate(envelope)


def test_v2_runtime_and_schema_reject_padded_artifact_path(
    tmp_path: Path,
) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)
    source_artifact = next(
        artifact
        for artifact in envelope["local_artifacts"]
        if artifact["role"] == "authorized_local_source"
    )
    source_artifact["path"] = f" {source_artifact['path']}"

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="path must not contain edge whitespace",
    ):
        KERNEL.validate_audit_envelope_v2(envelope, artifact_roots=roots)
    with pytest.raises(jsonschema.ValidationError):
        _schema_validator_v2().validate(envelope)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value["statuses"]["source"].update(
                {"status": "receipt_only"}
            ),
            "statuses.source.status is invalid",
        ),
        (
            lambda value: value["execution"]["input_artifact_refs"].remove(
                "authorized_source"
            ),
            "authorized_local_source artifact must be an execution input",
        ),
        (
            lambda value: value["statuses"]["source"]["evidence_refs"][
                "artifact_refs"
            ].remove("authorized_source"),
            "must reference every authorized_local_source artifact",
        ),
        (
            lambda value: next(
                artifact
                for artifact in value["local_artifacts"]
                if artifact["role"] == "authorized_local_source"
            ).update({"role": "prepared_input"}),
            "requires at least one authorized_local_source artifact",
        ),
    ],
)
def test_v2_runtime_rejects_local_source_boundary_mutation(
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], Any],
    message: str,
) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)
    mutator(envelope)

    with pytest.raises(KERNEL.ContractValidationError, match=message):
        KERNEL.validate_audit_envelope_v2(envelope, artifact_roots=roots)


def test_v2_runtime_and_schema_reject_local_source_on_plugin_root(
    tmp_path: Path,
) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)
    source_artifact = next(
        artifact
        for artifact in envelope["local_artifacts"]
        if artifact["role"] == "authorized_local_source"
    )
    plugin_source = roots["plugin"] / "contracts" / CONTRACT_SCHEMA_V2.name
    source_artifact.update(
        KERNEL.named_root_artifact_receipt(
            roots,
            plugin_source,
            root_id="plugin",
            artifact_id="authorized_source",
            role="authorized_local_source",
            media_type="application/octet-stream",
        )
    )

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="authorized_local_source artifacts must use the pilot root",
    ):
        KERNEL.validate_audit_envelope_v2(envelope, artifact_roots=roots)
    with pytest.raises(jsonschema.ValidationError):
        _schema_validator_v2().validate(envelope)


@pytest.mark.parametrize(
    ("artifact_id", "root_id", "message"),
    [
        ("case_contract", "plugin", "case artifact must use the pilot root"),
        ("audit_adapter", "pilot", "audit_adapter artifact must use the plugin root"),
        ("producer", "pilot", "producer artifact must use the plugin root"),
        ("prepared_output", "plugin", "execution outputs must use the pilot root"),
    ],
)
def test_v2_runtime_enforces_cross_artifact_root_capabilities(
    tmp_path: Path,
    artifact_id: str,
    root_id: str,
    message: str,
) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)
    _relocate_v2_artifact(
        envelope,
        roots,
        artifact_id=artifact_id,
        root_id=root_id,
    )

    _schema_validator_v2().validate(envelope)
    with pytest.raises(KERNEL.ContractValidationError, match=message):
        KERNEL.validate_audit_envelope_v2(envelope, artifact_roots=roots)


def test_v2_requires_exact_named_root_capabilities(tmp_path: Path) -> None:
    envelope, roots = _v2_local_source_envelope(tmp_path)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="exactly the pilot and plugin roots",
    ):
        KERNEL.validate_audit_envelope_v2(
            envelope,
            artifact_roots={"pilot": roots["pilot"]},
        )

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="must be distinct",
    ):
        KERNEL.validate_audit_envelope_v2(
            envelope,
            artifact_roots={"pilot": roots["pilot"], "plugin": roots["pilot"]},
        )


@pytest.mark.parametrize(
    ("builder", "case_id"),
    [
        (_fastenal_envelope, "fastenal_q1_2025"),
        (_wd40_envelope, "wd40-fy2025-synthetic-monthly-pnl"),
    ],
)
def test_preparation_audit_envelope_is_byte_deterministic(
    builder: Callable[[], dict[str, Any]],
    case_id: str,
) -> None:
    first = (
        json.dumps(
            builder(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

    second = (
        json.dumps(
            builder(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

    assert first == second
    assert hashlib.sha256(first).hexdigest() == EXPECTED_ENVELOPE_SHA256[case_id]


def test_public_truth_expected_report_matches_current_validator() -> None:
    report = PUBLIC_VALIDATOR.validate_public_truth_case(
        FASTENAL_ROOT / "benchmark.json",
        FASTENAL_ROOT / "expected_prepared_observations.csv",
    )
    actual = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    assert actual == FASTENAL_REPORT.read_bytes()


@pytest.mark.parametrize(
    "mutator",
    [
        lambda report: report["inputs"]["benchmark"].update({"sha256": "0" * 64}),
        lambda report: report["inputs"]["truth"].update({"sha256": "0" * 64}),
        lambda report: report["inputs"]["expected"].update({"sha256": "0" * 64}),
        lambda report: report["inputs"]["sources"][0].update({"sha256": "0" * 64}),
        lambda report: report["counts"].update(
            {"assertions_passed": report["counts"]["assertions_passed"] + 1}
        ),
    ],
)
def test_public_truth_adapter_rejects_report_not_matching_replay(
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], Any],
) -> None:
    report = json.loads(FASTENAL_REPORT.read_text(encoding="utf-8"))
    mutator(report)
    stale_report = tmp_path / "stale-validation-report.json"
    _write_test_json(stale_report, report)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="does not match deterministic replay",
    ):
        PUBLIC_ADAPTER.build_public_truth_audit_envelope(
            clara_root=CLARA_ROOT,
            benchmark_path=FASTENAL_ROOT / "benchmark.json",
            candidate_path=FASTENAL_ROOT / "expected_prepared_observations.csv",
            validation_report_path=stale_report,
        )


def test_public_truth_adapter_rejects_stale_report_after_boundary_change(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "fastenal"
    shutil.copytree(FASTENAL_ROOT, case_root)
    benchmark_path = case_root / "benchmark.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    benchmark["reviewed_boundary"]["statement"] = "Changed reviewed boundary."
    _write_test_json(benchmark_path, benchmark)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="does not match deterministic replay",
    ):
        PUBLIC_ADAPTER.build_public_truth_audit_envelope(
            clara_root=CLARA_ROOT,
            benchmark_path=benchmark_path,
            candidate_path=case_root / "expected_prepared_observations.csv",
            validation_report_path=case_root / "expected_validation_report.json",
        )


@pytest.mark.parametrize(
    "mutator",
    [
        _mutate_monthly_output_bytes,
        _mutate_monthly_manifest_engine,
        _forge_monthly_reconciliation_and_reseal_manifest,
    ],
)
def test_monthly_adapter_rejects_output_not_matching_replay(
    tmp_path: Path,
    mutator: Callable[[Path], None],
) -> None:
    output_dir = tmp_path / "prepared"
    shutil.copytree(WD40_EXPECTED, output_dir)
    mutator(output_dir)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="does not match deterministic replay",
    ):
        MONTHLY_ADAPTER.build_monthly_pnl_audit_envelope(
            clara_root=CLARA_ROOT,
            case_path=WD40_ROOT / "case.json",
            prepared_output_dir=output_dir,
        )


def test_monthly_adapter_rejects_stale_success_outputs_after_input_change(
    tmp_path: Path,
) -> None:
    case_path = _copy_failed_monthly_case(tmp_path / "case")
    output_dir = tmp_path / "prepared"
    shutil.copytree(WD40_EXPECTED, output_dir)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="output set does not match deterministic replay",
    ):
        MONTHLY_ADAPTER.build_monthly_pnl_audit_envelope(
            clara_root=CLARA_ROOT,
            case_path=case_path,
            prepared_output_dir=output_dir,
        )


def test_monthly_adapter_preserves_failed_run_without_success_artifacts() -> None:
    with TemporaryDirectory(prefix=".m3-failed-", dir=CLARA_ROOT) as raw_dir:
        run_root = Path(raw_dir)
        case_path = _copy_failed_monthly_case(run_root / "case")
        output_dir = run_root / "prepared"
        result = MONTHLY_PREPARER.prepare_monthly_pnl_case(case_path, output_dir)

        envelope = MONTHLY_ADAPTER.build_monthly_pnl_audit_envelope(
            clara_root=CLARA_ROOT,
            case_path=case_path,
            prepared_output_dir=output_dir,
        )

        _schema_validator().validate(envelope)
        assert result["status"] == "failed"
        assert {path.name for path in output_dir.iterdir()} == {
            "reconciliation.json",
            "unmapped_accounts.csv",
        }
        assert envelope["execution"]["output_artifact_refs"] == [
            "reconciliation",
            "unmapped_accounts",
        ]
        assert {item["artifact_id"] for item in envelope["local_artifacts"]}.isdisjoint(
            {"monthly_pnl", "prepared_evidence_manifest"}
        )
        assert envelope["lineage"]["aggregate"]["declared"] is False
        assert envelope["lineage"]["row"]["declared"] is False
        assert envelope["statuses"]["validation"]["status"] == "failed"
        assert envelope["statuses"]["preparation"]["status"] == "failed"
        assert envelope["statuses"]["reconciliation"]["status"] == "failed"
        assert envelope["statuses"]["publication"]["status"] == "withheld"
        assert envelope["report_ready"] is False
        assert {error["code"] for error in envelope["reconciliation"]["errors"]} == {
            error["code"] for error in result["errors"]
        }


def test_monthly_adapter_rejects_success_artifact_left_after_failed_run() -> None:
    with TemporaryDirectory(prefix=".m3-failed-stale-", dir=CLARA_ROOT) as raw_dir:
        run_root = Path(raw_dir)
        case_path = _copy_failed_monthly_case(run_root / "case")
        output_dir = run_root / "prepared"
        result = MONTHLY_PREPARER.prepare_monthly_pnl_case(case_path, output_dir)
        (output_dir / "monthly_pnl.csv").write_text("stale\n", encoding="utf-8")

        with pytest.raises(
            KERNEL.ContractValidationError,
            match="output set does not match deterministic replay",
        ):
            MONTHLY_ADAPTER.build_monthly_pnl_audit_envelope(
                clara_root=CLARA_ROOT,
                case_path=case_path,
                prepared_output_dir=output_dir,
            )

        assert result["status"] == "failed"


def test_public_truth_keeps_distinct_logical_artifacts_with_identical_bytes() -> None:
    artifacts = {
        artifact["artifact_id"]: artifact
        for artifact in _fastenal_envelope()["local_artifacts"]
    }

    assert artifacts["candidate_observations"]["sha256"] == (
        artifacts["expected_observations"]["sha256"]
    )
    assert artifacts["candidate_observations"]["artifact_id"] != (
        artifacts["expected_observations"]["artifact_id"]
    )


def test_monthly_source_receipts_do_not_fabricate_missing_fields() -> None:
    sources = _wd40_envelope()["remote_sources"]

    assert all("publisher" not in source for source in sources)
    assert all("document_date" not in source for source in sources)
    assert all("filed_date" in source["metadata"] for source in sources)


@pytest.mark.parametrize(
    "value",
    [
        "1e3",
        "01",
        "+1",
        "1,000",
        "NaN",
        "Infinity",
    ],
)
def test_parse_decimal_rejects_non_contract_values(value: str) -> None:
    with pytest.raises(KERNEL.ContractValidationError):
        KERNEL.parse_decimal(value, label="value")


@pytest.mark.parametrize("value", ["1.0", "-0", "10.500"])
def test_parse_decimal_rejects_noncanonical_output_text(value: str) -> None:
    with pytest.raises(
        KERNEL.ContractValidationError,
        match="canonical Decimal text",
    ):
        KERNEL.parse_decimal(value, label="value", canonical=True)


@pytest.mark.parametrize(
    "value",
    [
        "0.0000001",
        "123456789012345678901234567890123456789",
    ],
)
def test_parse_decimal_default_does_not_promote_m2_bounds(value: str) -> None:
    assert KERNEL.parse_decimal(value, label="value") == Decimal(value)


@pytest.mark.parametrize(
    "value",
    [
        "0.0000001",
        "123456789012345678901234567890123456789",
    ],
)
def test_parse_decimal_applies_explicit_case_bounds(value: str) -> None:
    policy = KERNEL.ExactDecimalPolicy(
        max_digits=38,
        max_scale=6,
        calculation_precision=128,
    )

    with pytest.raises(KERNEL.ContractValidationError):
        KERNEL.parse_decimal(value, label="value", policy=policy)


def test_m2_numeric_policy_preserves_producer_owned_bounds() -> None:
    constraints = _wd40_envelope()["numeric_policy"]["case_constraints"]

    actual_bounds = {
        "maximum_input_digits": constraints["maximum_input_digits"],
        "maximum_input_scale": constraints["maximum_input_scale"],
        "calculation_precision": constraints["calculation_precision"],
    }

    assert actual_bounds == EXPECTED_M2_NUMERIC_BOUNDS


def test_exact_decimal_helpers_ignore_ambient_context() -> None:
    previous_precision = getcontext().prec
    getcontext().prec = 3
    try:
        on_increment = KERNEL.is_on_increment(
            Decimal("12345678901234567890.12"),
            Decimal("0.01"),
        )
        within_tolerance = KERNEL.difference_within_tolerance(
            Decimal("10000000000000000000.01"),
            Decimal("10000000000000000000"),
            Decimal("0.01"),
        )
    finally:
        getcontext().prec = previous_precision

    assert on_increment is True
    assert within_tolerance is True


def test_exact_decimal_helpers_do_not_impose_a_generic_precision_ceiling() -> None:
    large_value = Decimal("9" * 200 + ".01")

    assert KERNEL.is_on_increment(large_value, Decimal("0.01")) is True
    assert (
        KERNEL.difference_within_tolerance(
            large_value,
            Decimal("9" * 200),
            Decimal("0.01"),
        )
        is True
    )


def test_exact_decimal_context_requires_a_declared_or_derived_precision() -> None:
    with pytest.raises(
        KERNEL.ContractValidationError,
        match="operation-derived precision or an explicit case policy",
    ):
        with KERNEL.exact_decimal_context():
            pass


@pytest.mark.parametrize(
    ("helper", "operands"),
    [
        (KERNEL.is_on_increment, (Decimal("NaN"), Decimal("0.01"))),
        (
            KERNEL.difference_within_tolerance,
            (Decimal("1"), Decimal("Infinity"), Decimal("0")),
        ),
    ],
)
def test_exact_decimal_helpers_reject_nonfinite_operands(
    helper: Callable[..., bool],
    operands: tuple[Decimal, ...],
) -> None:
    with pytest.raises(
        KERNEL.ContractValidationError,
        match="requires finite operands",
    ):
        helper(*operands)


@pytest.mark.parametrize(
    "payload",
    [
        '{"value": 1.5}',
        '{"value": 1e3}',
        '{"value": NaN}',
        '{"value": 1, "value": 2}',
    ],
)
def test_strict_json_load_rejects_ambiguous_json(
    tmp_path: Path,
    payload: str,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(KERNEL.ContractValidationError):
        KERNEL.strict_json_load(path)


def test_strict_json_snapshot_parses_and_hashes_the_same_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "snapshot.json"
    payload = b'{"value":"synthetic"}\n'
    path.write_bytes(payload)

    value, byte_count, digest = KERNEL.strict_json_snapshot(path)

    assert value == {"value": "synthetic"}
    assert byte_count == len(payload)
    assert digest == hashlib.sha256(payload).hexdigest()


def test_file_snapshot_returns_one_stable_byte_count_and_digest(
    tmp_path: Path,
) -> None:
    path = tmp_path / "snapshot.bin"
    payload = b"synthetic snapshot bytes\n"
    path.write_bytes(payload)

    byte_count, digest = KERNEL.file_snapshot(path)

    assert byte_count == len(payload)
    assert digest == hashlib.sha256(payload).hexdigest()


def test_beneath_snapshots_read_exact_regular_file_bytes(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    json_path = root / "snapshot.json"
    payload = b'{"value":"synthetic"}\n'
    json_path.write_bytes(payload)

    value, byte_count, digest = KERNEL.strict_json_snapshot_beneath(
        json_path,
        root=root,
    )
    file_byte_count, file_digest = KERNEL.file_snapshot_beneath(
        json_path,
        root=root,
    )

    assert value == {"value": "synthetic"}
    assert byte_count == file_byte_count == len(payload)
    assert digest == file_digest == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    "relative_escape",
    [
        Path("..") / "outside.json",
        Path("sub") / ".." / ".." / "outside.json",
    ],
)
def test_beneath_snapshot_rejects_lexical_parent_traversal(
    tmp_path: Path,
    relative_escape: Path,
) -> None:
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (tmp_path / "outside.json").write_text('{"outside":true}\n', encoding="utf-8")

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="must not traverse",
    ):
        KERNEL.strict_json_snapshot_beneath(
            root / relative_escape,
            root=root,
        )


def test_beneath_snapshot_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"outside":true}\n', encoding="utf-8")
    (root / "escape.json").symlink_to(outside)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="could not safely open",
    ):
        KERNEL.strict_json_snapshot_beneath(
            root / "escape.json",
            root=root,
        )


def test_beneath_snapshot_rejects_symlink_root(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    path = real_root / "snapshot.json"
    path.write_text('{"inside":true}\n', encoding="utf-8")
    symlink_root = tmp_path / "symlink-root"
    symlink_root.symlink_to(real_root)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="could not safely open",
    ):
        KERNEL.strict_json_snapshot_beneath(
            symlink_root / "snapshot.json",
            root=symlink_root,
        )


def test_beneath_snapshot_rechecks_root_identity_after_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    path = root / "snapshot.json"
    path.write_text('{"inside":true}\n', encoding="utf-8")
    pinned_root = tmp_path / "root-pinned"
    original_read = KERNEL._read_descriptor_bytes
    swapped = False

    def swap_root_during_read(descriptor: int) -> bytes:
        nonlocal swapped
        root.rename(pinned_root)
        root.symlink_to(pinned_root, target_is_directory=True)
        swapped = True
        return original_read(descriptor)

    monkeypatch.setattr(
        KERNEL,
        "_read_descriptor_bytes",
        swap_root_during_read,
    )

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="declared root changed while file was read",
    ):
        KERNEL.strict_json_snapshot_beneath(path, root=root)

    assert swapped is True


def test_beneath_snapshot_rechecks_intermediate_identity_after_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    directory = root / "nested"
    directory.mkdir(parents=True)
    path = directory / "snapshot.json"
    path.write_text('{"inside":true}\n', encoding="utf-8")
    pinned_directory = root / "nested-pinned"
    original_read = KERNEL._read_descriptor_bytes
    swapped = False

    def swap_directory_during_read(descriptor: int) -> bytes:
        nonlocal swapped
        directory.rename(pinned_directory)
        directory.symlink_to(pinned_directory, target_is_directory=True)
        swapped = True
        return original_read(descriptor)

    monkeypatch.setattr(
        KERNEL,
        "_read_descriptor_bytes",
        swap_directory_during_read,
    )

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="directory path changed while file was read",
    ):
        KERNEL.strict_json_snapshot_beneath(path, root=root)

    assert swapped is True


def test_canonical_json_hash_is_order_independent_and_unicode_stable() -> None:
    first = {"z": "é", "a": {"two": 2, "one": 1}}
    second = {"a": {"one": 1, "two": 2}, "z": "é"}

    assert KERNEL.canonical_json_bytes(first) == KERNEL.canonical_json_bytes(second)
    assert KERNEL.canonical_json_sha256(first) == (
        hashlib.sha256(KERNEL.canonical_json_bytes(second)).hexdigest()
    )


def test_reviewed_decision_receipt_rejects_status_promotion() -> None:
    with pytest.raises(
        KERNEL.ContractValidationError,
        match="cannot promote",
    ):
        KERNEL.reviewed_decision_receipt(
            decision_id="decision",
            decision_kind="case_owned",
            status="draft",
            reviewed_on=None,
            basis="Declared draft decision.",
            content={},
            evidence_refs=KERNEL.reference_set(artifact_refs=("artifact",)),
        )


def test_json_schema_rejects_publication_escalation() -> None:
    envelope = _wd40_envelope()
    envelope["statuses"]["publication"]["status"] = "emitted"

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator().validate(envelope)


@pytest.mark.parametrize(
    ("csv_text", "message"),
    [
        ("a,b\n1\n", "truncated"),
        ("a,b\n1,2,3\n", "surplus"),
        ("b,a\n2,1\n", "columns"),
    ],
)
def test_read_exact_csv_rejects_structural_drift(
    tmp_path: Path,
    csv_text: str,
    message: str,
) -> None:
    path = tmp_path / "rows.csv"
    path.write_text(csv_text, encoding="utf-8")

    with pytest.raises(KERNEL.ContractValidationError, match=message):
        KERNEL.read_exact_csv(
            path,
            columns=("a", "b"),
            label="rows",
        )


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value["local_artifacts"].append(
                copy.deepcopy(value["local_artifacts"][0])
            ),
            "duplicate IDs|sorted",
        ),
        (
            lambda value: value["local_artifacts"][0].update({"sha256": "0" * 64}),
            "sha256 does not match",
        ),
        (
            lambda value: value["local_artifacts"][0].update({"path": "../outside"}),
            "stay inside|does not exist",
        ),
        (
            lambda value: value["reviewed_decisions"][0].update({"status": "draft"}),
            "status must be reviewed",
        ),
        (
            lambda value: value["reviewed_decisions"][0].update(
                {"content_sha256": "0" * 64}
            ),
            "does not match content",
        ),
        (
            lambda value: value["reconciliation"]["checks"][0].update(
                {"status": "failed"}
            ),
            "passed reconciliation",
        ),
        (
            lambda value: value.update({"report_ready": True}),
            "cannot claim report readiness",
        ),
        (
            lambda value: value["statuses"]["publication"].update(
                {"status": "emitted"}
            ),
            "cannot establish external publication",
        ),
        (
            lambda value: value["lineage"]["row"].update(
                {
                    "declared": True,
                    "records": [
                        {
                            "lineage_id": "99_false_row_lineage",
                            "row_id": "row_1",
                            "artifact_ref": "monthly_pnl",
                            "references": {
                                "artifact_refs": ["monthly_pnl"],
                                "source_refs": [],
                                "decision_refs": [],
                                "lineage_refs": [],
                            },
                            "details": {},
                        }
                    ],
                    "limitations": [],
                }
            ),
            "row lineage is not supported",
        ),
        (
            lambda value: value["lineage"]["aggregate"]["records"][0].update(
                {"evidence_sha256": "0" * 64}
            ),
            "does not match located evidence",
        ),
        (
            lambda value: value["lineage"]["aggregate"]["records"][0].update(
                {"aggregate_id": "unrelated_aggregate"}
            ),
            "aggregate_id does not match located evidence",
        ),
        (
            lambda value: value["lineage"]["aggregate"]["records"][0].update(
                {"output_artifact_id_json_pointer": "/outputs/1/artifact_id"}
            ),
            "output artifact does not match located evidence",
        ),
        (
            lambda value: value["lineage"]["aggregate"]["records"][0].update(
                {"output_sha256_json_pointer": "/outputs/1/sha256"}
            ),
            "output digest does not match located evidence",
        ),
        (
            lambda value: value["reconciliation"]["checks"][0]["references"][
                "artifact_refs"
            ].append("unknown_artifact"),
            "unknown references|sorted",
        ),
    ],
)
def test_audit_envelope_rejects_isolated_contract_mutation(
    mutator: Callable[[dict[str, Any]], Any],
    message: str,
) -> None:
    envelope = _wd40_envelope()
    mutator(envelope)

    with pytest.raises(KERNEL.ContractValidationError, match=message):
        KERNEL.validate_audit_envelope(envelope, root=CLARA_ROOT)


def test_aggregate_lineage_cannot_be_enabled_by_role_label_alone() -> None:
    envelope = _wd40_envelope()
    aggregate = envelope["lineage"]["aggregate"]["records"][0]
    aggregate["evidence_artifact_ref"] = "monthly_pnl"
    aggregate["evidence_json_pointer"] = ""
    aggregate["evidence_sha256"] = next(
        item["sha256"]
        for item in envelope["local_artifacts"]
        if item["artifact_id"] == "monthly_pnl"
    )
    monthly_artifact = next(
        item
        for item in envelope["local_artifacts"]
        if item["artifact_id"] == "monthly_pnl"
    )
    monthly_artifact["role"] = "aggregate_lineage_evidence"

    with pytest.raises(KERNEL.ContractValidationError, match="invalid JSON"):
        KERNEL.validate_audit_envelope(envelope, root=CLARA_ROOT)


def test_aggregate_lineage_rejects_unrelated_case_json_relabelled_as_evidence() -> None:
    envelope = _wd40_envelope()
    aggregate = envelope["lineage"]["aggregate"]["records"][0]
    aggregate["evidence_artifact_ref"] = "case_contract"
    aggregate["evidence_json_pointer"] = ""
    case_artifact = next(
        item
        for item in envelope["local_artifacts"]
        if item["artifact_id"] == "case_contract"
    )
    aggregate["evidence_sha256"] = case_artifact["sha256"]
    case_artifact["role"] = "aggregate_lineage_evidence"

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="evidence artifact must be an execution output",
    ):
        KERNEL.validate_audit_envelope(envelope, root=CLARA_ROOT)


def test_audit_envelope_rejects_binary_float_in_uninterpreted_details() -> None:
    envelope = _wd40_envelope()
    envelope["reconciliation"]["checks"][0]["details"]["ratio"] = 1.5

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="binary floating-point",
    ):
        KERNEL.validate_audit_envelope(envelope, root=CLARA_ROOT)


def test_audit_envelope_rejects_noncanonical_numeric_evidence() -> None:
    envelope = _fastenal_envelope()
    evidence = next(
        check["numeric_evidence"]
        for check in envelope["reconciliation"]["checks"]
        if check["numeric_evidence"]
    )
    evidence[0]["value"] = "1.0"

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="canonical Decimal text",
    ):
        KERNEL.validate_audit_envelope(envelope, root=CLARA_ROOT)


def test_resolve_local_file_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (root / "escape.txt").symlink_to(outside)

    with pytest.raises(
        KERNEL.ContractValidationError,
        match="stay inside",
    ):
        KERNEL.resolve_local_file(root, "escape.txt", label="artifact")
