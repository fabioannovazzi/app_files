from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
CASE_ROOT = CLARA_ROOT / "evals" / "preparation" / "wd40_fy2025"
CASE_PATH = CASE_ROOT / "case.json"
EXPECTED_ROOT = CASE_ROOT / "expected"
SEMANTIC_LAYER_PATH = CASE_ROOT / "monthly_pnl.semantic.json"
REPORTING_REQUEST_PATH = CASE_ROOT / "reporting_handoff_request.json"
STATEMENT_RECIPE_PATH = CASE_ROOT / "statement_render_recipe.json"
HANDOFF_SCRIPT = CLARA_ROOT / "scripts" / "build_monthly_pnl_reporting_handoff.py"
EVIDENCE_SCRIPT = (
    CLARA_ROOT / "skills" / "html-deck" / "scripts" / "evidence_bindings.py"
)
HANDOFF_SCHEMA = (
    CLARA_ROOT / "contracts" / "reporting_evidence_handoff_receipt.v1.schema.json"
)


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def handoff_module() -> Any:
    return _load_module(
        "clara_monthly_pnl_reporting_handoff_test",
        HANDOFF_SCRIPT,
    )


@pytest.fixture(scope="module")
def evidence_module() -> Any:
    return _load_module(
        "clara_monthly_pnl_reporting_handoff_evidence_test",
        EVIDENCE_SCRIPT,
    )


def _build_handoff(module: Any, output_dir: Path) -> dict[str, Any]:
    return module.build_monthly_pnl_reporting_handoff(
        clara_root=CLARA_ROOT,
        case_path=CASE_PATH,
        prepared_output_dir=EXPECTED_ROOT,
        semantic_layer_path=SEMANTIC_LAYER_PATH,
        reporting_request_path=REPORTING_REQUEST_PATH,
        statement_recipe_path=STATEMENT_RECIPE_PATH,
        output_dir=output_dir,
    )


def _validate_handoff(
    module: Any,
    handoff_dir: Path,
    *,
    verify_fresh_render: bool = False,
) -> dict[str, Any]:
    return module.validate_monthly_pnl_reporting_handoff(
        clara_root=CLARA_ROOT,
        case_path=CASE_PATH,
        prepared_output_dir=EXPECTED_ROOT,
        semantic_layer_path=SEMANTIC_LAYER_PATH,
        reporting_request_path=REPORTING_REQUEST_PATH,
        statement_recipe_path=STATEMENT_RECIPE_PATH,
        handoff_dir=handoff_dir,
        verify_fresh_render=verify_fresh_render,
    )


@pytest.fixture(scope="module")
def canonical_handoff(
    tmp_path_factory: pytest.TempPathFactory,
    handoff_module: Any,
) -> tuple[Path, dict[str, Any]]:
    output_dir = tmp_path_factory.mktemp("clara-m4-canonical") / "handoff"
    receipt = _build_handoff(handoff_module, output_dir)
    return output_dir, receipt


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    assert rows
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _copy_handoff(source: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "handoff"
    shutil.copytree(source, destination)
    render_dir = destination / "render"
    input_path = destination / "evidence" / "monthly_pnl.csv"
    generated_recipe_path = render_dir / "render_request_recipe.json"
    for name in ("render_request_recipe.json", "used_recipe.json"):
        path = render_dir / name
        recipe = _load_json(path)
        recipe["source_file"] = str(input_path.resolve())
        _write_json(path, recipe)
    manifest_path = render_dir / "render_manifest.json"
    manifest = _load_json(manifest_path)
    manifest["input_file"] = str(input_path.resolve())
    manifest["output_dir"] = str(render_dir.resolve())
    relocated_run_dir = destination / ".clara-reporting-run-relocated"
    manifest["command"][2] = str(input_path.resolve())
    manifest["command"][4] = str(relocated_run_dir.resolve())
    manifest["command"][8] = str(
        (relocated_run_dir / "render_request_recipe.json").resolve()
    )
    manifest["evidence"]["input"]["path"] = str(input_path.resolve())
    manifest["evidence"]["recipe"]["path"] = str(generated_recipe_path.resolve())
    manifest["evidence"]["recipe"]["sha256"] = _sha256(generated_recipe_path)
    manifest["evidence"]["recipe"]["size_bytes"] = generated_recipe_path.stat().st_size
    for output in manifest["evidence"]["outputs"]:
        output_path = render_dir / output["path"]
        output["sha256"] = _sha256(output_path)
        output["size_bytes"] = output_path.stat().st_size
    manifest["evidence"]["output_set_sha256"] = _canonical_json_sha256(
        manifest["evidence"]["outputs"]
    )
    _write_json(manifest_path, manifest)
    return destination


def _refresh_render_manifest_output_receipts(
    module: Any,
    handoff_dir: Path,
) -> None:
    render_dir = handoff_dir / "render"
    manifest_path = render_dir / "render_manifest.json"
    manifest = _load_json(manifest_path)
    for output in manifest["evidence"]["outputs"]:
        output_path = render_dir / output["path"]
        output["sha256"] = _sha256(output_path)
        output["size_bytes"] = output_path.stat().st_size
    manifest["evidence"]["output_set_sha256"] = module.canonical_json_sha256(
        manifest["evidence"]["outputs"]
    )
    _write_json(manifest_path, manifest)


def _patch_loaded_json(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    predicate: Callable[[Path], bool],
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    real_load = module._load_json

    def load_with_mutation(path: Path) -> dict[str, Any]:
        payload = real_load(path)
        if predicate(Path(path).resolve()):
            payload = copy.deepcopy(payload)
            mutate(payload)
        return payload

    monkeypatch.setattr(module, "_load_json", load_with_mutation)


def _render_never_called(**_kwargs: Any) -> dict[str, Any]:
    raise AssertionError("render must not run after a failed pre-render gate")


def test_reporting_handoff_closes_all_reviewed_transport_gates(
    canonical_handoff: tuple[Path, dict[str, Any]],
    handoff_module: Any,
) -> None:
    handoff_dir, receipt = canonical_handoff
    schema = _load_json(HANDOFF_SCHEMA)
    validator = Draft202012Validator(schema)
    serialized_rows = _read_csv(
        handoff_dir / "evidence" / "serialized_html_numeric_cells.csv"
    )
    bundle = _load_json(handoff_dir / "evidence" / "evidence-bundle.json")
    bundle_by_id = {artifact["id"]: artifact for artifact in bundle["artifacts"]}
    render_by_path = {
        artifact["path"]: artifact for artifact in receipt["render"]["portable_outputs"]
    }
    publication_receipt = _load_json(
        handoff_dir / "evidence" / "publication_receipt.json"
    )

    assert list(validator.iter_errors(receipt)) == []
    assert receipt["classification"] == "synthetic_benchmark_only"
    assert receipt["semantic"] == {
        "semantic_layer_id": ("wd40_fy2025_synthetic_monthly_pnl.reporting_semantics"),
        "semantic_version": 1,
        "review_status": "model_reviewed",
        "validation": receipt["semantic"]["validation"],
        "snapshot_attachment": receipt["semantic"]["snapshot_attachment"],
        "validation_status": "contract_valid",
        "readiness": "ready_as_scoped_semantic_input",
        "compatibility_status": "compatible",
        "origin_snapshot_matches": True,
        "analysis_id": "analysis.prepared_monthly_pnl_statement",
        "policy_validity": "conditional",
        "capability_id": "statement.pnl_table",
    }
    assert receipt["handoff_ready_for_review"] is True
    assert receipt["report_ready"] is False
    assert receipt["publication_status"] == "withheld"
    assert receipt["gates"] == {
        "preparation": "passed",
        "reconciliation": "passed",
        "semantic_wiring": "verified",
        "render_transport": "verified",
        "serialized_html_cell_coverage": "verified",
        "evidence_bundle": "verified",
        "publication": "withheld",
    }
    assert receipt["evidence"] == {
        **receipt["evidence"],
        "bundle_schema_version": "clara.evidence_bundle.v1",
        "verified_artifact_count": 4,
        "expected_cell_count": 168,
        "verified_cell_count": 168,
        "coverage_status": "exact",
        "missing_cell_count": 0,
        "extra_cell_count": 0,
        "duplicate_cell_count": 0,
    }
    assert len(serialized_rows) == 168
    assert (
        len(
            {
                (row["row_key"], row["period"], row["scenario"])
                for row in serialized_rows
            }
        )
        == 168
    )
    assert len(bundle["artifacts"]) == 4

    prepared_sha256 = receipt["prepared_snapshot"]["prepared_artifact"]["sha256"]
    rendered_sha256 = render_by_path["render/pnl_statement_table_chart_data.csv"][
        "sha256"
    ]
    assert receipt["render"]["input_sha256"] == prepared_sha256
    assert bundle_by_id["prepared-monthly-pnl"]["sha256"] == prepared_sha256
    assert bundle_by_id["prepared-monthly-pnl"]["sha256"] == _sha256(
        handoff_dir / "evidence" / "monthly_pnl.csv"
    )
    assert bundle_by_id["rendered-statement-values"]["sha256"] == rendered_sha256
    assert rendered_sha256 == _sha256(
        handoff_dir / "evidence" / "rendered_statement_values.csv"
    )
    assert rendered_sha256 == _sha256(
        handoff_dir / "render" / "pnl_statement_table_chart_data.csv"
    )
    assert (
        bundle_by_id["serialized-html-numeric-cells"]["sha256"]
        == receipt["evidence"]["serialized_html_cells"]["sha256"]
    )
    assert (
        bundle_by_id["publication-receipt"]["sha256"]
        == receipt["evidence"]["publication_receipt"]["sha256"]
    )
    assert receipt["evidence"]["bundle"]["sha256"] == _sha256(
        handoff_dir / "evidence" / "evidence-bundle.json"
    )
    assert publication_receipt["prepared_input"]["sha256"] == prepared_sha256
    assert publication_receipt["render"] == receipt["render"]
    assert set(receipt["contracts"]["implementations"]) == {
        "adapter_registry",
        "check_compatibility",
        "clara_manifest",
        "evidence_bindings",
        "handoff_builder",
        "monthly_pnl_audit_adapter",
        "preparation_contract_kernel",
        "profile_dataset",
        "render_capability",
        "render_contract_registry",
        "reporting_adapters",
        "semantic_layer",
        "statement_core",
        "statement_manifest",
        "statement_runner",
    }
    assert publication_receipt["contracts"][
        "implementation_set_sha256"
    ] == handoff_module.canonical_json_sha256(receipt["contracts"]["implementations"])
    assert (
        publication_receipt["serialized_html_numeric_domain"]["serialized_cells_sha256"]
        == receipt["evidence"]["serialized_html_cells"]["sha256"]
    )
    assert (
        receipt["prepared_snapshot"]["address_set_sha256"]
        == receipt["evidence"]["address_set_sha256"]
    )
    assert (
        receipt["prepared_snapshot"]["value_set_sha256"]
        == receipt["evidence"]["value_set_sha256"]
    )


def test_reporting_handoff_canonical_receipts_are_byte_deterministic(
    tmp_path: Path,
    handoff_module: Any,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_receipt = _build_handoff(handoff_module, first)
    second_receipt = _build_handoff(handoff_module, second)

    assert first_receipt == second_receipt
    assert (first / "reporting_handoff.json").read_bytes() == (
        second / "reporting_handoff.json"
    ).read_bytes()
    assert (first / "evidence" / "evidence-bundle.json").read_bytes() == (
        second / "evidence" / "evidence-bundle.json"
    ).read_bytes()


def test_reporting_handoff_rejects_draft_semantics_before_render(
    tmp_path: Path,
    handoff_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_loaded_json(
        monkeypatch,
        handoff_module,
        lambda path: path == SEMANTIC_LAYER_PATH.resolve(),
        lambda payload: payload["review"].update({"status": "draft"}),
    )
    monkeypatch.setattr(handoff_module, "_render_once", _render_never_called)

    with pytest.raises(
        handoff_module.ContractValidationError,
        match="semantic layer must remain model-reviewed",
    ):
        _build_handoff(handoff_module, tmp_path / "handoff")


def test_reporting_handoff_rejects_wrong_render_role_before_render(
    tmp_path: Path,
    handoff_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_loaded_json(
        monkeypatch,
        handoff_module,
        lambda path: path == REPORTING_REQUEST_PATH.resolve(),
        lambda payload: payload["render"]["role_bindings"].update(
            {"statement_value": "display_order"}
        ),
    )
    monkeypatch.setattr(handoff_module, "_render_once", _render_never_called)

    with pytest.raises(
        handoff_module.ContractValidationError,
        match="request render role bindings drifted",
    ):
        _build_handoff(handoff_module, tmp_path / "handoff")


def test_reporting_handoff_exact_replay_catches_value_swap_hidden_by_profile(
    tmp_path: Path,
    handoff_module: Any,
) -> None:
    prepared_dir = tmp_path / "prepared"
    shutil.copytree(EXPECTED_ROOT, prepared_dir)
    monthly_pnl = prepared_dir / "monthly_pnl.csv"
    rows = _read_csv(monthly_pnl)
    rows[8]["value"], rows[9]["value"] = rows[9]["value"], rows[8]["value"]
    _write_csv(monthly_pnl, rows)
    profiler, semantics, _renderer, _evidence = handoff_module._component_modules(
        CLARA_ROOT
    )
    original_profile = handoff_module._normalized_profile(
        profiler=profiler,
        monthly_pnl_path=EXPECTED_ROOT / "monthly_pnl.csv",
    )
    changed_profile = handoff_module._normalized_profile(
        profiler=profiler,
        monthly_pnl_path=monthly_pnl,
    )

    assert _sha256(monthly_pnl) != _sha256(EXPECTED_ROOT / "monthly_pnl.csv")
    assert semantics.canonical_snapshot_fingerprint(
        changed_profile
    ) == semantics.canonical_snapshot_fingerprint(original_profile)
    with pytest.raises(
        handoff_module.ContractValidationError,
        match="does not match deterministic replay",
    ):
        handoff_module.build_monthly_pnl_reporting_handoff(
            clara_root=CLARA_ROOT,
            case_path=CASE_PATH,
            prepared_output_dir=prepared_dir,
            semantic_layer_path=SEMANTIC_LAYER_PATH,
            reporting_request_path=REPORTING_REQUEST_PATH,
            statement_recipe_path=STATEMENT_RECIPE_PATH,
            output_dir=tmp_path / "handoff",
        )


@pytest.mark.parametrize(
    ("mutate", "expected_message"),
    [
        (
            lambda payload: payload["render"]["statement_structure"].update(
                {"relative_path": "../statement_render_recipe.json"}
            ),
            "escapes",
        ),
        (
            lambda payload: payload["render"]["statement_structure"].update(
                {"sha256": "0" * 64}
            ),
            "request statement recipe digest drifted",
        ),
    ],
)
def test_reporting_handoff_rejects_recipe_path_or_digest_drift(
    tmp_path: Path,
    handoff_module: Any,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[dict[str, Any]], None],
    expected_message: str,
) -> None:
    _patch_loaded_json(
        monkeypatch,
        handoff_module,
        lambda path: path == REPORTING_REQUEST_PATH.resolve(),
        mutate,
    )
    monkeypatch.setattr(handoff_module, "_render_once", _render_never_called)

    with pytest.raises(
        handoff_module.ContractValidationError,
        match=expected_message,
    ):
        _build_handoff(handoff_module, tmp_path / "handoff")


def test_reporting_handoff_rejects_renderer_formula_before_render(
    tmp_path: Path,
    handoff_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def add_formula(payload: dict[str, Any]) -> None:
        row = payload["statement_rows"][0]
        row.pop("source_key")
        row["formula"] = {"operation": "sum", "terms": ["net_sales"]}

    _patch_loaded_json(
        monkeypatch,
        handoff_module,
        lambda path: path.name == "statement_render_recipe.json",
        add_formula,
    )
    monkeypatch.setattr(handoff_module, "_render_once", _render_never_called)

    with pytest.raises(
        handoff_module.ContractValidationError,
        match="statement recipe must use source-key-only transport",
    ):
        _build_handoff(handoff_module, tmp_path / "handoff")


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "changed"])
def test_reporting_handoff_rejects_resealed_serialized_cell_ledger_drift(
    tmp_path: Path,
    canonical_handoff: tuple[Path, dict[str, Any]],
    handoff_module: Any,
    evidence_module: Any,
    mutation: str,
) -> None:
    canonical_dir, _receipt = canonical_handoff
    handoff_dir = _copy_handoff(canonical_dir, tmp_path)
    ledger_path = handoff_dir / "evidence" / "serialized_html_numeric_cells.csv"
    rows = _read_csv(ledger_path)
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = dict(rows[0])
    else:
        rows[0]["prepared_value"] = "51001"
        rows[0]["rendered_value"] = "51001"
        rows[0]["serialized_text"] = "51 001"
        rows[0]["value_sha256"] = handoff_module.canonical_json_sha256("51001")
    _write_csv(ledger_path, rows)
    evidence_module.seal_evidence_bundle(
        handoff_dir / "evidence" / "evidence-bundle.json"
    )

    with pytest.raises(
        handoff_module.ContractValidationError,
        match="serialized-cell",
    ):
        _validate_handoff(handoff_module, handoff_dir)


def test_reporting_handoff_rejects_resealed_render_and_html_value_drift(
    tmp_path: Path,
    canonical_handoff: tuple[Path, dict[str, Any]],
    handoff_module: Any,
    evidence_module: Any,
) -> None:
    canonical_dir, _receipt = canonical_handoff
    handoff_dir = _copy_handoff(canonical_dir, tmp_path)
    chart_path = handoff_dir / "render" / "pnl_statement_table_chart_data.csv"
    chart_rows = _read_csv(chart_path)
    chart_rows[0]["2024-09_SYN"] = "51001.0"
    _write_csv(chart_path, chart_rows)
    html_path = handoff_dir / "render" / "pnl_statement_table.html"
    html = html_path.read_text(encoding="utf-8")
    assert html.count('<td class="num">51 000</td>') == 1
    html_path.write_text(
        html.replace(
            '<td class="num">51 000</td>',
            '<td class="num">51 001</td>',
            1,
        ),
        encoding="utf-8",
    )
    shutil.copyfile(
        chart_path,
        handoff_dir / "evidence" / "rendered_statement_values.csv",
    )
    _refresh_render_manifest_output_receipts(handoff_module, handoff_dir)
    evidence_module.seal_evidence_bundle(
        handoff_dir / "evidence" / "evidence-bundle.json"
    )

    with pytest.raises(
        handoff_module.ContractValidationError,
        match="rendered value does not equal prepared value",
    ):
        _validate_handoff(handoff_module, handoff_dir)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("report_ready", True),
        ("publication_status", "published"),
    ],
)
def test_reporting_handoff_schema_rejects_publication_escalation(
    canonical_handoff: tuple[Path, dict[str, Any]],
    field: str,
    value: object,
) -> None:
    _handoff_dir, receipt = canonical_handoff
    escalated = copy.deepcopy(receipt)
    escalated[field] = value
    validator = Draft202012Validator(_load_json(HANDOFF_SCHEMA))

    errors = list(validator.iter_errors(escalated))

    assert any(list(error.absolute_path) == [field] for error in errors)


@pytest.mark.parametrize("mutation", ["stale", "extra"])
def test_reporting_handoff_rejects_stale_or_extra_render_artifact(
    tmp_path: Path,
    canonical_handoff: tuple[Path, dict[str, Any]],
    handoff_module: Any,
    mutation: str,
) -> None:
    canonical_dir, _receipt = canonical_handoff
    handoff_dir = _copy_handoff(canonical_dir, tmp_path)
    if mutation == "stale":
        html_path = handoff_dir / "render" / "pnl_statement_table.html"
        html_path.write_text(
            html_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        expected_message = "render output receipt drifted"
    else:
        (handoff_dir / "render" / "unexpected.txt").write_text(
            "not declared\n",
            encoding="utf-8",
        )
        expected_message = "handoff output inventory drifted"

    with pytest.raises(
        handoff_module.ContractValidationError,
        match=expected_message,
    ):
        _validate_handoff(handoff_module, handoff_dir)


def test_reporting_handoff_withholds_ready_receipt_until_fresh_validation(
    tmp_path: Path,
    handoff_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "handoff"

    def reject_fresh_render(**_kwargs: Any) -> None:
        raise handoff_module.ContractValidationError("forced fresh-render failure")

    monkeypatch.setattr(
        handoff_module,
        "_assert_fresh_render",
        reject_fresh_render,
    )

    with pytest.raises(
        handoff_module.ContractValidationError,
        match="forced fresh-render failure",
    ):
        _build_handoff(handoff_module, output_dir)

    assert output_dir.is_dir()
    assert not (output_dir / "reporting_handoff.json").exists()


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    [
        ("extra-header", "header-cell structure drifted"),
        ("body-span", "body cell spans are not permitted"),
        ("presentation", "presentation boundary drifted"),
    ],
)
def test_reporting_handoff_rejects_serialized_html_address_or_copy_drift(
    tmp_path: Path,
    canonical_handoff: tuple[Path, dict[str, Any]],
    handoff_module: Any,
    mutation: str,
    expected_message: str,
) -> None:
    canonical_dir, _receipt = canonical_handoff
    handoff_dir = _copy_handoff(canonical_dir, tmp_path)
    html_path = handoff_dir / "render" / "pnl_statement_table.html"
    html = html_path.read_text(encoding="utf-8")
    if mutation == "extra-header":
        html = html.replace(
            '<th class="period" colspan="1">2024-09</th>',
            ('<th class="blank"></th>' '<th class="period" colspan="1">2024-09</th>'),
            1,
        )
    elif mutation == "body-span":
        html = html.replace(
            '<td class="num">51 000</td>',
            '<td class="num" colspan="2">51 000</td>',
            1,
        )
    else:
        html = html.replace(
            "<p>WD-40 Company — synthetic monthly preparation fixture</p>",
            "<p>WD-40 Company — issuer actual monthly results</p>",
            1,
        )
    html_path.write_text(html, encoding="utf-8")
    _refresh_render_manifest_output_receipts(handoff_module, handoff_dir)

    with pytest.raises(
        handoff_module.ContractValidationError,
        match=expected_message,
    ):
        _validate_handoff(handoff_module, handoff_dir)


def test_reporting_handoff_rejects_context_numeric_drift(
    tmp_path: Path,
    canonical_handoff: tuple[Path, dict[str, Any]],
    handoff_module: Any,
) -> None:
    canonical_dir, _receipt = canonical_handoff
    handoff_dir = _copy_handoff(canonical_dir, tmp_path)
    context_path = handoff_dir / "render" / "pnl_statement_table_chart_context.json"
    context = _load_json(context_path)
    context["table_rows"][0]["values"]["2024-09_SYN"] = 51001.0
    _write_json(context_path, context)
    _refresh_render_manifest_output_receipts(handoff_module, handoff_dir)

    with pytest.raises(
        handoff_module.ContractValidationError,
        match="statement chart context value drifted",
    ):
        _validate_handoff(handoff_module, handoff_dir)


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        ("label", "Issuer actual net sales", "rendered statement label drifted"),
        ("prefix", "=", "rendered statement prefix drifted"),
    ],
)
def test_reporting_handoff_rejects_rendered_csv_metadata_drift(
    tmp_path: Path,
    canonical_handoff: tuple[Path, dict[str, Any]],
    handoff_module: Any,
    field: str,
    value: str,
    expected_message: str,
) -> None:
    canonical_dir, _receipt = canonical_handoff
    handoff_dir = _copy_handoff(canonical_dir, tmp_path)
    chart_path = handoff_dir / "render" / "pnl_statement_table_chart_data.csv"
    rows = _read_csv(chart_path)
    rows[0][field] = value
    _write_csv(chart_path, rows)
    _refresh_render_manifest_output_receipts(handoff_module, handoff_dir)

    with pytest.raises(
        handoff_module.ContractValidationError,
        match=expected_message,
    ):
        _validate_handoff(handoff_module, handoff_dir)


@pytest.mark.parametrize("control_file", ["artifact_manifest", "final_artifacts"])
def test_reporting_handoff_rejects_control_manifest_wiring_drift(
    tmp_path: Path,
    canonical_handoff: tuple[Path, dict[str, Any]],
    handoff_module: Any,
    control_file: str,
) -> None:
    canonical_dir, _receipt = canonical_handoff
    handoff_dir = _copy_handoff(canonical_dir, tmp_path)
    render_dir = handoff_dir / "render"
    if control_file == "artifact_manifest":
        path = render_dir / "artifact_manifest.json"
        payload = _load_json(path)
        payload["artifacts"][0]["data_path"] = "unreviewed_values.csv"
        expected_message = "component table artifact wiring drifted"
    else:
        path = render_dir / "final_artifacts.json"
        payload = _load_json(path)
        payload["outputs"][1]["path"] = "unreviewed_values.csv"
        expected_message = "component final-artifact wiring drifted"
    _write_json(path, payload)
    _refresh_render_manifest_output_receipts(handoff_module, handoff_dir)

    with pytest.raises(
        handoff_module.ContractValidationError,
        match=expected_message,
    ):
        _validate_handoff(handoff_module, handoff_dir)


@pytest.mark.parametrize("mutation", ["description", "provenance"])
def test_reporting_handoff_rejects_resealed_bundle_metadata_drift(
    tmp_path: Path,
    canonical_handoff: tuple[Path, dict[str, Any]],
    handoff_module: Any,
    mutation: str,
) -> None:
    canonical_dir, _receipt = canonical_handoff
    handoff_dir = _copy_handoff(canonical_dir, tmp_path)
    bundle_path = handoff_dir / "evidence" / "evidence-bundle.json"
    bundle = _load_json(bundle_path)
    if mutation == "description":
        bundle["description"] = "Issuer actuals independently verified."
        expected_message = "reviewed metadata drifted"
    else:
        bundle["artifacts"][0]["provenance"] = "Issuer verified."
        expected_message = "unexpected fields"
    _write_json(bundle_path, bundle)

    with pytest.raises(
        handoff_module.ContractValidationError,
        match=expected_message,
    ):
        _validate_handoff(handoff_module, handoff_dir)


def test_reporting_handoff_rejects_request_identity_drift_before_render(
    tmp_path: Path,
    handoff_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_loaded_json(
        monkeypatch,
        handoff_module,
        lambda path: path == REPORTING_REQUEST_PATH.resolve(),
        lambda payload: payload.update({"request_id": "approved-production-report"}),
    )
    monkeypatch.setattr(handoff_module, "_render_once", _render_never_called)

    with pytest.raises(
        handoff_module.ContractValidationError,
        match="request_id is not the frozen case request",
    ):
        _build_handoff(handoff_module, tmp_path / "handoff")


def test_reporting_handoff_rejects_semantic_review_basis_drift_before_render(
    tmp_path: Path,
    handoff_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied_case = tmp_path / "case"
    shutil.copytree(CASE_ROOT, copied_case)
    notes_path = copied_case / "SOURCE_NOTES.md"
    notes_path.write_text(
        notes_path.read_text(encoding="utf-8")
        + "\nIssuer actual monthly disclosure.\n",
        encoding="utf-8",
    )
    frozen_envelope = handoff_module.build_monthly_pnl_audit_envelope(
        clara_root=CLARA_ROOT,
        case_path=CASE_PATH,
        prepared_output_dir=EXPECTED_ROOT,
    )
    monkeypatch.setattr(
        handoff_module,
        "build_monthly_pnl_audit_envelope",
        lambda **_kwargs: frozen_envelope,
    )
    monkeypatch.setattr(handoff_module, "_render_once", _render_never_called)

    with pytest.raises(
        handoff_module.ContractValidationError,
        match="semantic review basis drifted",
    ):
        handoff_module.build_monthly_pnl_reporting_handoff(
            clara_root=CLARA_ROOT,
            case_path=copied_case / "case.json",
            prepared_output_dir=copied_case / "expected",
            semantic_layer_path=copied_case / "monthly_pnl.semantic.json",
            reporting_request_path=copied_case / "reporting_handoff_request.json",
            statement_recipe_path=copied_case / "statement_render_recipe.json",
            output_dir=tmp_path / "handoff",
        )


def test_reporting_handoff_rejects_existing_output_directory(
    tmp_path: Path,
    handoff_module: Any,
) -> None:
    output_dir = tmp_path / "already-exists"
    output_dir.mkdir()

    with pytest.raises(
        handoff_module.ContractValidationError,
        match="output directory must not already exist",
    ):
        _build_handoff(handoff_module, output_dir)
