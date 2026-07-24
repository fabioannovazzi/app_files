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

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SCRIPTS_ROOT = CLARA_ROOT / "scripts"
CONTRACT_SCHEMA = CLARA_ROOT / "contracts" / "preparation_audit_envelope.v1.schema.json"
FASTENAL_ROOT = CLARA_ROOT / "evals" / "public_truth" / "fastenal_q1_2025"
WD40_ROOT = CLARA_ROOT / "evals" / "preparation" / "wd40_fy2025"
FASTENAL_REPORT = FASTENAL_ROOT / "expected_validation_report.json"
WD40_EXPECTED = WD40_ROOT / "expected"
EXPECTED_ENVELOPE_SHA256 = {
    "fastenal_q1_2025": "62a745acec4f7ae6849077f3bec813595ed4fc7ca7dbad3acfac581595b419c5",
    "wd40-fy2025-synthetic-monthly-pnl": (
        "adc9a63cb02d9ab906e52f0636bc613c04c4074010b0596ee73cb01bca34e238"
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


def _write_test_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
        match="case.case_id must be a canonical identifier",
    ):
        KERNEL.validate_audit_envelope(envelope, root=CLARA_ROOT)

    with pytest.raises(jsonschema.ValidationError):
        _schema_validator().validate(envelope)


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
