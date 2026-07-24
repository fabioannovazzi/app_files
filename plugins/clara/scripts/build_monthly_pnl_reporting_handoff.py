#!/usr/bin/env python3
"""Build and validate the bounded WD-40 monthly-P&L reporting handoff.

The handoff is deterministic because it performs mechanically verifiable work:
it replays preparation, checks exact bytes and reviewed contract wiring, invokes
an explicitly selected renderer, compares every prepared/rendered/serialized
HTML numeric cell, and seals the resulting evidence. It does not select a chart,
interpret the statement, approve the semantic judgment, or authorize
publication.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import logging
import re
import shutil
import sys
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_monthly_pnl_audit_envelope import (  # noqa: E402
    build_monthly_pnl_audit_envelope,
)
from preparation_contract_kernel import (  # noqa: E402
    ContractValidationError,
    canonical_json_sha256,
    file_sha256,
)

__all__ = [
    "HANDOFF_SCHEMA_VERSION",
    "build_monthly_pnl_reporting_handoff",
    "validate_monthly_pnl_reporting_handoff",
    "main",
]

LOGGER = logging.getLogger(__name__)

HANDOFF_SCHEMA_VERSION = "clara.reporting_evidence_handoff_receipt.v1"
REQUEST_SCHEMA_VERSION = "clara.monthly_pnl_reporting_handoff_request.v1"
PUBLICATION_RECEIPT_SCHEMA_VERSION = "clara.monthly_pnl_publication_evidence_receipt.v1"
DATASET_CONTRACT_ID = "wd40_fy2025_synthetic_monthly_pnl"
M3_CASE_ID = "wd40-fy2025-synthetic-monthly-pnl"
REQUEST_ID = "wd40_fy2025_synthetic_monthly_pnl.statement_table"
SEMANTIC_LAYER_ID = f"{DATASET_CONTRACT_ID}.reporting_semantics"
ANALYSIS_ID = "analysis.prepared_monthly_pnl_statement"
ANALYSIS_TASK_ID = "evidence_and_reporting_tables"
SELECTION_EMPHASIS = "structured_statement_values"
CAPABILITY_ID = "statement.pnl_table"
PERIOD_RULE_ID = "period_rule.all_available"
CLASSIFICATION = "synthetic_benchmark_only"
SCENARIO = "SYN"
ARTIFACT_MODE = "data_and_render"
EXPECTED_CELL_COUNT = 168
SERIALIZED_HTML_NUMERIC_DOMAIN = (
    "Every serialized tbody td.num statement value cell, addressed by row_key, "
    "period, and scenario."
)
EXPECTED_SEMANTIC_SHA256 = (
    "a0759a793eef04596ae9305cce4df40fb3f4611cedc70a44aa315d21abd32afe"
)
EXPECTED_RECIPE_SHA256 = (
    "493727b2874f005d1d338725fd5c461953397f079c133413b3eab9a4653cd5e8"
)
EXPECTED_SOURCE_NOTES_SHA256 = (
    "7ea069095ffff82bfed4d1643ce3fb53fd8afa0b38f28d570ad91b1f59b23d3a"
)
EXPECTED_RECIPE_PRESENTATION = {
    "schema_version": "1.0",
    "title": "WD-40 Company — synthetic monthly preparation fixture",
    "statement_label": "Prepared monthly profit and loss statement",
    "unit": "USD thousands",
    "scope_label": (
        "Synthetic monthly phasing; public quarter and fiscal-year tie-outs"
    ),
}
EXPECTED_PUBLICATION_LIMITATIONS = [
    (
        "The monthly phasing is synthetic and must not be presented as issuer "
        "actual monthly disclosure."
    ),
    "Model review is not human accounting review.",
    "The request does not authorize chart selection, interpretation, or publication.",
]
EXPECTED_BUNDLE_DESCRIPTION = (
    "Synthetic benchmark evidence sealing the prepared values, rendered "
    "statement values, all serialized HTML numeric cells, and the portable "
    "publication receipt."
)
EXPECTED_RENDER_FILES = frozenset(
    {
        "artifact_manifest.json",
        "final_artifacts.json",
        "pnl_statement_table.html",
        "pnl_statement_table_chart_context.json",
        "pnl_statement_table_chart_data.csv",
        "render_manifest.json",
        "render_request_recipe.json",
        "used_recipe.json",
    }
)
EXPECTED_CURRENT_RUN_OUTPUTS = EXPECTED_RENDER_FILES - {
    "render_manifest.json",
    "render_request_recipe.json",
}
PORTABLE_RENDER_FILES = (
    "final_artifacts.json",
    "pnl_statement_table.html",
    "pnl_statement_table_chart_context.json",
    "pnl_statement_table_chart_data.csv",
)
PREPARED_COLUMNS = (
    "row_key",
    "period",
    "scenario",
    "value",
    "unit",
    "period_start",
    "period_end",
    "line_type",
    "display_order",
)
SERIALIZED_CELL_COLUMNS = (
    "cell_id",
    "row_key",
    "period",
    "scenario",
    "display_order",
    "render_row_position",
    "render_column_position",
    "prepared_value",
    "rendered_value",
    "serialized_text",
    "value_sha256",
)
EXPECTED_ROLE_BINDINGS = {
    "period_axis": "period",
    "statement_value": "value",
    "statement_line_item": "row_key",
    "statement_scenario": "scenario",
}
EXPECTED_SEMANTIC_ROLE_BINDINGS = {
    "period_axis": {
        "binding_type": "concept",
        "concept_id": "period.period",
    },
    "statement_value": {
        "binding_type": "concept",
        "concept_id": "metric.value",
    },
    "statement_line_item": {
        "binding_type": "concept",
        "concept_id": "dimension.row_key",
    },
    "statement_scenario": {
        "binding_type": "concept",
        "concept_id": "dimension.scenario",
    },
    "statement_structure": {
        "binding_type": "package",
        "source_id": "source.statement_render_recipe",
    },
}
DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_MODULE_CACHE: dict[str, Any] = {}


class _StatementTableParser(HTMLParser):
    """Collect serialized statement address axes and numeric cells."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._thead_depth = 0
        self._tbody_depth = 0
        self._capture_kind: str | None = None
        self._capture_tag: str | None = None
        self._capture_colspan: int | None = None
        self._parts: list[str] = []
        self._header_row: list[tuple[str, str, int]] | None = None
        self._row_label: str | None = None
        self._row_values: list[str] | None = None
        self._in_title_header = False
        self.header_rows: list[list[tuple[str, str, int]]] = []
        self.title_lines: list[tuple[str, str]] = []
        self.source_lines: list[str] = []
        self.body_rows: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        classes = {
            token
            for key, value in attrs
            if key.casefold() == "class" and value
            for token in value.split()
        }
        if lowered == "header" and "title" in classes:
            if self._in_title_header:
                raise ContractValidationError("nested statement HTML title header")
            self._in_title_header = True
            return
        if lowered == "thead":
            self._thead_depth += 1
            return
        if lowered == "tbody":
            self._tbody_depth += 1
            return
        if lowered == "tr" and self._thead_depth:
            if self._header_row is not None:
                raise ContractValidationError("nested statement HTML header row")
            self._header_row = []
            return
        if lowered == "tr" and self._tbody_depth:
            if self._row_values is not None:
                raise ContractValidationError("nested statement HTML body row")
            self._row_label = None
            self._row_values = []
            return
        if lowered == "p" and self._in_title_header:
            line_kind = "metric" if "metric" in classes else "plain"
            self._start_capture(f"title:{line_kind}", lowered)
            return
        if lowered == "p" and "source" in classes:
            self._start_capture("source", lowered)
            return
        if lowered == "th" and self._thead_depth:
            if self._header_row is None:
                raise ContractValidationError(
                    "statement HTML header cell is outside a header row"
                )
            if any(key.casefold() == "rowspan" for key, _value in attrs):
                raise ContractValidationError(
                    "statement HTML header rowspan is not permitted"
                )
            header_kinds = [
                kind for kind in ("blank", "period", "scenario") if kind in classes
            ]
            if len(header_kinds) != 1:
                raise ContractValidationError(
                    "statement HTML contains an unaddressed header cell"
                )
            colspan_values = [
                value
                for key, value in attrs
                if key.casefold() == "colspan" and value is not None
            ]
            if len(colspan_values) > 1:
                raise ContractValidationError("duplicate statement HTML header colspan")
            raw_colspan = colspan_values[0] if colspan_values else "1"
            try:
                colspan = int(raw_colspan)
            except ValueError as exc:
                raise ContractValidationError(
                    "statement HTML header colspan is not an integer"
                ) from exc
            if colspan <= 0:
                raise ContractValidationError(
                    "statement HTML header colspan must be positive"
                )
            self._start_capture(
                f"header:{header_kinds[0]}",
                lowered,
                colspan=colspan,
            )
            return
        if lowered != "td" or not self._tbody_depth:
            return
        if self._row_values is None:
            raise ContractValidationError("statement HTML cell is outside a body row")
        if any(key.casefold() in {"colspan", "rowspan"} for key, _value in attrs):
            raise ContractValidationError(
                "statement HTML body cell spans are not permitted"
            )
        if "label" in classes:
            self._start_capture("label", lowered)
        elif "num" in classes:
            self._start_capture("numeric", lowered)
        else:
            raise ContractValidationError(
                "statement HTML body contains an unaddressed table cell"
            )

    def _start_capture(
        self,
        kind: str,
        tag: str,
        *,
        colspan: int | None = None,
    ) -> None:
        if self._capture_kind is not None:
            raise ContractValidationError("nested statement HTML value capture")
        self._capture_kind = kind
        self._capture_tag = tag
        self._capture_colspan = colspan
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_kind is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == self._capture_tag:
            value = "".join(self._parts).strip()
            if self._capture_kind and self._capture_kind.startswith("header:"):
                if self._header_row is None or self._capture_colspan is None:
                    raise ContractValidationError(
                        "statement HTML header capture is incomplete"
                    )
                header_kind = self._capture_kind.partition(":")[2]
                self._header_row.append((header_kind, value, self._capture_colspan))
            elif self._capture_kind == "label":
                if self._row_label is not None:
                    raise ContractValidationError(
                        "statement HTML row has duplicate labels"
                    )
                self._row_label = value
            elif self._capture_kind == "numeric":
                if self._row_values is None:
                    raise ContractValidationError(
                        "statement HTML numeric cell is outside a body row"
                    )
                self._row_values.append(value)
            elif self._capture_kind and self._capture_kind.startswith("title:"):
                self.title_lines.append((self._capture_kind.partition(":")[2], value))
            elif self._capture_kind == "source":
                self.source_lines.append(value)
            self._capture_kind = None
            self._capture_tag = None
            self._capture_colspan = None
            self._parts = []
        if lowered == "tr" and self._thead_depth:
            if self._header_row is None:
                raise ContractValidationError(
                    "statement HTML header row is structurally incomplete"
                )
            self.header_rows.append(self._header_row)
            self._header_row = None
        elif lowered == "tr" and self._tbody_depth:
            if self._row_values is None or self._row_label is None:
                raise ContractValidationError(
                    "statement HTML body row is missing its label"
                )
            self.body_rows.append((self._row_label, self._row_values))
            self._row_label = None
            self._row_values = None
        elif lowered == "header" and self._in_title_header:
            self._in_title_header = False
        elif lowered == "thead" and self._thead_depth:
            self._thead_depth -= 1
        elif lowered == "tbody" and self._tbody_depth:
            self._tbody_depth -= 1


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractValidationError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractValidationError(f"non-standard JSON constant {value!r}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ContractValidationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractValidationError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _write_csv(
    path: Path,
    *,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fieldnames),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    label: str,
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required)
    if missing:
        raise ContractValidationError(f"{label} is missing fields: {missing}")
    if unexpected:
        raise ContractValidationError(f"{label} has unexpected fields: {unexpected}")


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{label} must be non-empty text")
    return value.strip()


def _sha256(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if SHA256_RE.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be a lowercase SHA-256 digest")
    return result


def _contained_file(root: Path, relative: Any, *, label: str) -> Path:
    relative_text = _text(relative, label=label)
    relative_path = Path(relative_text)
    if relative_path.is_absolute():
        raise ContractValidationError(f"{label} must be relative")
    lexical = root / relative_path
    if lexical.is_symlink():
        raise ContractValidationError(f"{label} may not be a symbolic link")
    resolved_root = root.resolve()
    resolved = lexical.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ContractValidationError(f"{label} escapes {resolved_root}") from exc
    if not resolved.is_file():
        raise ContractValidationError(f"{label} does not exist: {relative_text}")
    return resolved


def _require_case_owned(path: Path, case_root: Path, *, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(case_root.resolve())
    except ValueError as exc:
        raise ContractValidationError(f"{label} must be inside {case_root}") from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise ContractValidationError(f"{label} must be a regular case-owned file")
    return resolved


def _load_module(name: str, path: Path) -> Any:
    key = f"{name}:{path.resolve()}"
    if key in _MODULE_CACHE:
        return _MODULE_CACHE[key]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _MODULE_CACHE[key] = module
    return module


def _component_modules(clara_root: Path) -> tuple[Any, Any, Any, Any]:
    reporting_scripts = clara_root / "modules" / "reporting-engine" / "scripts"
    profiler = _load_module(
        "clara_m4_reporting_profile_dataset",
        reporting_scripts / "profile_dataset.py",
    )
    semantics = _load_module(
        "clara_m4_reporting_semantic_layer",
        reporting_scripts / "semantic_layer.py",
    )
    renderer = _load_module(
        "clara_m4_reporting_render_capability",
        reporting_scripts / "render_capability.py",
    )
    evidence = _load_module(
        "clara_m4_html_deck_evidence_bindings",
        clara_root / "skills" / "html-deck" / "scripts" / "evidence_bindings.py",
    )
    return profiler, semantics, renderer, evidence


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ContractValidationError("numeric values must be finite")
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _parse_decimal(value: Any, *, label: str) -> Decimal:
    text = _text(value, label=label)
    if DECIMAL_RE.fullmatch(text) is None:
        raise ContractValidationError(f"{label} must be a canonical decimal")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ContractValidationError(f"{label} must be a finite decimal") from exc
    if not result.is_finite():
        raise ContractValidationError(f"{label} must be a finite decimal")
    return result


def _parse_serialized_decimal(value: str, *, label: str) -> Decimal:
    compact = value.replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    return _parse_decimal(compact, label=label)


def _artifact_receipt(root: Path, path: Path) -> dict[str, Any]:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ContractValidationError(
            f"handoff artifact escapes output root: {resolved_path}"
        ) from exc
    if not resolved_path.is_file():
        raise ContractValidationError(f"handoff artifact is missing: {relative}")
    return {
        "path": relative,
        "sha256": file_sha256(resolved_path),
        "size_bytes": resolved_path.stat().st_size,
    }


def _plugin_contract_receipt(clara_root: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(clara_root.resolve()).as_posix()
    except ValueError as exc:
        raise ContractValidationError(
            f"plugin contract escapes Clara root: {resolved}"
        ) from exc
    return {
        "path": relative,
        "sha256": file_sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _portable_implementation_receipt(
    path: Path,
    *,
    portable_path: str,
) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ContractValidationError(
            f"reporting implementation is missing: {portable_path}"
        )
    return {
        "path": portable_path,
        "sha256": file_sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _implementation_receipts(clara_root: Path) -> dict[str, dict[str, Any]]:
    reporting_root = clara_root / "modules" / "reporting-engine"
    embedded_statement_root = clara_root / "modules" / "statement-analysis"
    repository_statement_root = clara_root.parent / "statement-analysis"
    statement_root = (
        embedded_statement_root
        if embedded_statement_root.is_dir()
        else repository_statement_root
    )
    receipts = {
        "clara_manifest": _plugin_contract_receipt(
            clara_root,
            clara_root / ".codex-plugin" / "plugin.json",
        ),
        "handoff_builder": _plugin_contract_receipt(
            clara_root,
            clara_root / "scripts" / "build_monthly_pnl_reporting_handoff.py",
        ),
        "monthly_pnl_audit_adapter": _plugin_contract_receipt(
            clara_root,
            clara_root / "scripts" / "build_monthly_pnl_audit_envelope.py",
        ),
        "preparation_contract_kernel": _plugin_contract_receipt(
            clara_root,
            clara_root / "scripts" / "preparation_contract_kernel.py",
        ),
        "profile_dataset": _plugin_contract_receipt(
            clara_root,
            reporting_root / "scripts" / "profile_dataset.py",
        ),
        "semantic_layer": _plugin_contract_receipt(
            clara_root,
            reporting_root / "scripts" / "semantic_layer.py",
        ),
        "reporting_adapters": _plugin_contract_receipt(
            clara_root,
            reporting_root / "scripts" / "reporting_adapters.py",
        ),
        "render_capability": _plugin_contract_receipt(
            clara_root,
            reporting_root / "scripts" / "render_capability.py",
        ),
        "adapter_registry": _plugin_contract_receipt(
            clara_root,
            reporting_root / "catalog" / "adapter_registry.json",
        ),
        "evidence_bindings": _plugin_contract_receipt(
            clara_root,
            clara_root / "skills" / "html-deck" / "scripts" / "evidence_bindings.py",
        ),
        "check_compatibility": _plugin_contract_receipt(
            clara_root,
            reporting_root / "scripts" / "check_compatibility.py",
        ),
        "render_contract_registry": _plugin_contract_receipt(
            clara_root,
            reporting_root / "scripts" / "render_contract_registry.py",
        ),
        "statement_manifest": _portable_implementation_receipt(
            statement_root / ".codex-plugin" / "plugin.json",
            portable_path="component/statement-analysis/.codex-plugin/plugin.json",
        ),
        "statement_runner": _portable_implementation_receipt(
            statement_root / "scripts" / "run_statement_analysis.py",
            portable_path=(
                "component/statement-analysis/scripts/run_statement_analysis.py"
            ),
        ),
        "statement_core": _portable_implementation_receipt(
            statement_root / "scripts" / "statement_core.py",
            portable_path="component/statement-analysis/scripts/statement_core.py",
        ),
    }
    return dict(sorted(receipts.items()))


def _find_artifact(envelope: Mapping[str, Any], artifact_id: str) -> Mapping[str, Any]:
    matches = [
        artifact
        for artifact in envelope.get("local_artifacts", [])
        if artifact.get("artifact_id") == artifact_id
    ]
    if len(matches) != 1:
        raise ContractValidationError(
            f"M3 envelope must contain exactly one {artifact_id!r} artifact"
        )
    return matches[0]


def _validate_m3_envelope(
    *,
    clara_root: Path,
    case_path: Path,
    prepared_output_dir: Path,
) -> dict[str, Any]:
    envelope = build_monthly_pnl_audit_envelope(
        clara_root=clara_root,
        case_path=case_path,
        prepared_output_dir=prepared_output_dir,
    )
    if envelope["case"]["case_id"] != M3_CASE_ID:
        raise ContractValidationError("unexpected M3 case identity")
    for gate in ("validation", "preparation", "reconciliation"):
        if envelope["statuses"][gate]["status"] != "passed":
            raise ContractValidationError(f"M3 {gate} gate did not pass")
    if envelope["statuses"]["publication"]["status"] != "withheld":
        raise ContractValidationError("M3 publication status must remain withheld")
    if envelope["report_ready"] is not False:
        raise ContractValidationError("M3 report_ready must remain false")
    monthly_receipt = _find_artifact(envelope, "monthly_pnl")
    monthly_path = prepared_output_dir / "monthly_pnl.csv"
    if monthly_receipt["sha256"] != file_sha256(monthly_path):
        raise ContractValidationError(
            "M3 monthly_pnl digest does not match current prepared bytes"
        )
    return envelope


def _validate_request(
    *,
    request: Mapping[str, Any],
    case_root: Path,
    prepared_monthly_pnl: Path,
    semantic_layer_path: Path,
    statement_recipe_path: Path,
) -> None:
    _exact_keys(
        request,
        required={
            "schema_version",
            "request_id",
            "case_id",
            "dataset",
            "semantic_layer",
            "selected_analysis",
            "render",
            "evidence_boundary",
            "publication_boundary",
        },
        label="reporting handoff request",
    )
    if request["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise ContractValidationError(
            f"request schema_version must be {REQUEST_SCHEMA_VERSION}"
        )
    if request["case_id"] != M3_CASE_ID:
        raise ContractValidationError("request case_id does not match M3")
    if request["request_id"] != REQUEST_ID:
        raise ContractValidationError("request_id is not the frozen case request")

    dataset = request["dataset"]
    if not isinstance(dataset, Mapping):
        raise ContractValidationError("request.dataset must be an object")
    _exact_keys(
        dataset,
        required={
            "dataset_contract_id",
            "prepared_artifact",
            "classification",
            "disclosure_boundary",
        },
        label="request.dataset",
    )
    if dataset["dataset_contract_id"] != DATASET_CONTRACT_ID:
        raise ContractValidationError("request dataset identity is not the frozen case")
    if dataset["classification"] != CLASSIFICATION:
        raise ContractValidationError("request classification must remain synthetic")
    if (
        dataset["disclosure_boundary"]
        != "synthetic_monthly_phasing_not_issuer_actual_monthly_disclosure"
    ):
        raise ContractValidationError("request disclosure boundary was weakened")
    prepared = dataset["prepared_artifact"]
    if not isinstance(prepared, Mapping):
        raise ContractValidationError("request prepared_artifact must be an object")
    _exact_keys(
        prepared,
        required={"relative_path", "sha256"},
        label="request.dataset.prepared_artifact",
    )
    resolved_prepared = _contained_file(
        case_root,
        prepared["relative_path"],
        label="request.dataset.prepared_artifact.relative_path",
    )
    if resolved_prepared != prepared_monthly_pnl.resolve():
        raise ContractValidationError("request prepared artifact path drifted")
    if _sha256(prepared["sha256"], label="request prepared SHA-256") != file_sha256(
        prepared_monthly_pnl
    ):
        raise ContractValidationError("request prepared artifact digest drifted")

    semantic = request["semantic_layer"]
    if not isinstance(semantic, Mapping):
        raise ContractValidationError("request.semantic_layer must be an object")
    _exact_keys(
        semantic,
        required={
            "relative_path",
            "sha256",
            "semantic_layer_id",
            "semantic_version",
            "origin_profile_fingerprint",
            "review_basis",
            "review",
        },
        label="request.semantic_layer",
    )
    resolved_semantic = _contained_file(
        case_root,
        semantic["relative_path"],
        label="request.semantic_layer.relative_path",
    )
    if resolved_semantic != semantic_layer_path.resolve():
        raise ContractValidationError("request semantic layer path drifted")
    semantic_sha256 = _sha256(
        semantic["sha256"],
        label="request semantic SHA-256",
    )
    if semantic_sha256 != EXPECTED_SEMANTIC_SHA256 or semantic_sha256 != file_sha256(
        semantic_layer_path
    ):
        raise ContractValidationError("request semantic layer digest drifted")
    if (
        semantic["semantic_layer_id"] != SEMANTIC_LAYER_ID
        or semantic["semantic_version"] != 1
    ):
        raise ContractValidationError("request semantic layer identity drifted")
    review_basis = semantic["review_basis"]
    if not isinstance(review_basis, Mapping):
        raise ContractValidationError("request semantic review_basis must be an object")
    _exact_keys(
        review_basis,
        required={"relative_path", "sha256"},
        label="request.semantic_layer.review_basis",
    )
    source_notes_path = _contained_file(
        case_root,
        review_basis["relative_path"],
        label="request.semantic_layer.review_basis.relative_path",
    )
    expected_source_notes_path = (case_root / "SOURCE_NOTES.md").resolve()
    source_notes_sha256 = _sha256(
        review_basis["sha256"],
        label="request semantic review-basis SHA-256",
    )
    if (
        source_notes_path != expected_source_notes_path
        or source_notes_sha256 != EXPECTED_SOURCE_NOTES_SHA256
        or source_notes_sha256 != file_sha256(source_notes_path)
    ):
        raise ContractValidationError("request semantic review basis drifted")
    review = semantic["review"]
    if not isinstance(review, Mapping):
        raise ContractValidationError("request semantic review must be an object")
    _exact_keys(
        review,
        required={"status", "reviewed_at", "human_reviewed"},
        label="request.semantic_layer.review",
    )
    if review != {
        "status": "model_reviewed",
        "reviewed_at": "2026-07-23",
        "human_reviewed": False,
    }:
        raise ContractValidationError(
            "request must preserve model-reviewed, not human-reviewed, status"
        )

    selected = request["selected_analysis"]
    if not isinstance(selected, Mapping):
        raise ContractValidationError("request.selected_analysis must be an object")
    _exact_keys(
        selected,
        required={
            "analysis_id",
            "analysis_task_id",
            "selection_emphasis",
            "selection_owner",
            "automatic_chart_selection",
        },
        label="request.selected_analysis",
    )
    if selected != {
        "analysis_id": ANALYSIS_ID,
        "analysis_task_id": ANALYSIS_TASK_ID,
        "selection_emphasis": SELECTION_EMPHASIS,
        "selection_owner": "reviewed_case_request",
        "automatic_chart_selection": False,
    }:
        raise ContractValidationError(
            "request must explicitly preserve the reviewed analysis selection"
        )

    render = request["render"]
    if not isinstance(render, Mapping):
        raise ContractValidationError("request.render must be an object")
    _exact_keys(
        render,
        required={
            "capability_id",
            "artifact_mode",
            "render_columns",
            "role_bindings",
            "statement_structure",
            "periods",
            "scenarios",
        },
        label="request.render",
    )
    if render["capability_id"] != CAPABILITY_ID:
        raise ContractValidationError("request capability drifted")
    if render["artifact_mode"] != ARTIFACT_MODE:
        raise ContractValidationError("request artifact mode drifted")
    if render["role_bindings"] != EXPECTED_ROLE_BINDINGS:
        raise ContractValidationError("request render role bindings drifted")
    if render["render_columns"] != {
        "period": "period",
        "value": "value",
        "row_key": "row_key",
        "scenario": "scenario",
    }:
        raise ContractValidationError("request render columns drifted")
    structure = render["statement_structure"]
    if not isinstance(structure, Mapping):
        raise ContractValidationError("request statement_structure must be an object")
    _exact_keys(
        structure,
        required={"relative_path", "sha256"},
        label="request.render.statement_structure",
    )
    resolved_recipe = _contained_file(
        case_root,
        structure["relative_path"],
        label="request.render.statement_structure.relative_path",
    )
    if resolved_recipe != statement_recipe_path.resolve():
        raise ContractValidationError("request statement recipe path drifted")
    recipe_sha256 = _sha256(
        structure["sha256"],
        label="request recipe SHA-256",
    )
    if recipe_sha256 != EXPECTED_RECIPE_SHA256 or recipe_sha256 != file_sha256(
        statement_recipe_path
    ):
        raise ContractValidationError("request statement recipe digest drifted")
    periods = render["periods"]
    if (
        not isinstance(periods, list)
        or len(periods) != 12
        or len(set(periods)) != 12
        or periods != sorted(periods)
    ):
        raise ContractValidationError(
            "request periods must be 12 unique ordered fiscal months"
        )
    if render["scenarios"] != [SCENARIO]:
        raise ContractValidationError("request scenario must be SYN only")

    evidence_boundary = request["evidence_boundary"]
    if not isinstance(evidence_boundary, Mapping):
        raise ContractValidationError("request.evidence_boundary must be an object")
    _exact_keys(
        evidence_boundary,
        required={
            "serialized_html_numeric_domain",
            "expected_numeric_cell_count",
            "require_exact_prepared_render_serialized_html_closure",
            "require_complete_render_and_evidence_coverage",
        },
        label="request.evidence_boundary",
    )
    if (
        evidence_boundary["serialized_html_numeric_domain"]
        != SERIALIZED_HTML_NUMERIC_DOMAIN
        or evidence_boundary["expected_numeric_cell_count"] != EXPECTED_CELL_COUNT
        or evidence_boundary["require_exact_prepared_render_serialized_html_closure"]
        is not True
        or evidence_boundary["require_complete_render_and_evidence_coverage"]
        is not True
    ):
        raise ContractValidationError("request evidence coverage boundary was weakened")

    publication = request["publication_boundary"]
    if not isinstance(publication, Mapping):
        raise ContractValidationError("request.publication_boundary must be an object")
    _exact_keys(
        publication,
        required={
            "handoff_purpose",
            "report_ready",
            "publication_status",
            "limitations",
        },
        label="request.publication_boundary",
    )
    if (
        publication["handoff_purpose"] != "deterministic_reporting_transport"
        or publication["report_ready"] is not False
        or publication["publication_status"] != "withheld"
        or publication["limitations"] != EXPECTED_PUBLICATION_LIMITATIONS
    ):
        raise ContractValidationError("request publication boundary was weakened")


def _normalized_profile(
    *,
    profiler: Any,
    monthly_pnl_path: Path,
) -> dict[str, Any]:
    profile = profiler.profile_dataset(
        monthly_pnl_path,
        dataset_id=DATASET_CONTRACT_ID,
    )
    source = profile.get("source")
    if not isinstance(source, dict):
        raise ContractValidationError("dataset profile source is missing")
    source["path"] = "evidence/monthly_pnl.csv"
    return profile


def _record_index(
    records: Any, identifier: str, value: str, *, label: str
) -> Mapping[str, Any]:
    if not isinstance(records, list):
        raise ContractValidationError(f"{label} must be a list")
    matches = [
        record
        for record in records
        if isinstance(record, Mapping) and record.get(identifier) == value
    ]
    if len(matches) != 1:
        raise ContractValidationError(
            f"{label} must contain exactly one {identifier}={value!r}"
        )
    return matches[0]


def _validate_semantic_gate(
    *,
    layer: Mapping[str, Any],
    request: Mapping[str, Any],
    profile: Mapping[str, Any],
    validation: Mapping[str, Any],
    attachment: Mapping[str, Any],
) -> None:
    if (
        layer.get("semantic_layer_id") != SEMANTIC_LAYER_ID
        or layer.get("semantic_version") != 1
    ):
        raise ContractValidationError("semantic layer identity drifted")
    if (layer.get("dataset_contract") or {}).get(
        "dataset_contract_id"
    ) != DATASET_CONTRACT_ID:
        raise ContractValidationError("semantic dataset identity drifted")
    semantic_review = layer.get("review") or {}
    if semantic_review.get("status") != "model_reviewed":
        raise ContractValidationError("semantic layer must remain model-reviewed")
    if (
        semantic_review.get("reviewed_by") != "Codex semantic fixture review"
        or semantic_review.get("reviewed_at") != "2026-07-23"
        or not any(
            "not human-reviewed" in str(note).casefold()
            for note in semantic_review.get("notes", [])
        )
    ):
        raise ContractValidationError("semantic review provenance drifted")
    if any(
        record.get("status") == "unknown"
        for collection in ("metrics", "dimensions", "periods")
        for record in layer.get(collection, [])
        if isinstance(record, Mapping)
    ):
        raise ContractValidationError("semantic layer contains unresolved concepts")

    metric_value = _record_index(
        layer.get("metrics"),
        "metric_id",
        "metric.value",
        label="semantic metrics",
    )
    if (
        metric_value.get("status") != "conditional"
        or metric_value.get("metric_class") != "additive_value"
        or (metric_value.get("binding") or {}).get("column") != "value"
        or "sum_across_statement_lines"
        not in (metric_value.get("aggregation") or {}).get("forbidden", [])
    ):
        raise ContractValidationError("semantic statement-value boundary drifted")
    display_order = _record_index(
        layer.get("metrics"),
        "metric_id",
        "metric.display_order",
        label="semantic metrics",
    )
    if display_order.get("status") != "excluded":
        raise ContractValidationError("display_order must remain excluded as a metric")
    expected_dimensions = {
        "dimension.row_key": ("row_key", "defined"),
        "dimension.scenario": ("scenario", "defined"),
        "dimension.line_type": ("line_type", "excluded"),
        "dimension.unit": ("unit", "excluded"),
    }
    for dimension_id, (column, status) in expected_dimensions.items():
        record = _record_index(
            layer.get("dimensions"),
            "dimension_id",
            dimension_id,
            label="semantic dimensions",
        )
        if record.get("column") != column or record.get("status") != status:
            raise ContractValidationError(f"semantic dimension {dimension_id} drifted")
    expected_periods = {
        "period.period": ("period", "defined"),
        "period.period_start": ("period_start", "excluded"),
        "period.period_end": ("period_end", "excluded"),
    }
    for period_id, (column, status) in expected_periods.items():
        record = _record_index(
            layer.get("periods"),
            "period_id",
            period_id,
            label="semantic periods",
        )
        if record.get("column") != column or record.get("status") != status:
            raise ContractValidationError(f"semantic period {period_id} drifted")

    policy = _record_index(
        layer.get("analysis_policies"),
        "analysis_id",
        ANALYSIS_ID,
        label="semantic analysis policies",
    )
    if (
        policy.get("validity") != "conditional"
        or policy.get("analysis_task_ids") != [ANALYSIS_TASK_ID]
        or policy.get("selection_emphases") != [SELECTION_EMPHASIS]
        or policy.get("period_rule_id") != PERIOD_RULE_ID
        or policy.get("role_bindings") != EXPECTED_SEMANTIC_ROLE_BINDINGS
        or not policy.get("conditions")
    ):
        raise ContractValidationError("selected semantic policy drifted")
    package_source = _record_index(
        layer.get("sources"),
        "source_id",
        "source.statement_render_recipe",
        label="semantic sources",
    )
    if (
        package_source.get("locator")
        != request["render"]["statement_structure"]["relative_path"]
        or package_source.get("authority") != "canonical"
    ):
        raise ContractValidationError("semantic statement package source drifted")

    if validation.get("status") != "contract_valid":
        raise ContractValidationError("semantic layer contract is invalid")
    if validation.get("semantic_readiness") != "ready_as_scoped_semantic_input":
        raise ContractValidationError("semantic layer is not ready as scoped input")
    snapshot = validation.get("snapshot") or {}
    compatibility = snapshot.get("compatibility") or {}
    if (
        snapshot.get("dataset_id") != DATASET_CONTRACT_ID
        or snapshot.get("is_origin_snapshot") is not True
        or compatibility.get("status")
        not in {"compatible", "compatible_with_extensions"}
        or compatibility.get("identity_matches") is not True
        or compatibility.get("origin_snapshot_matches") is not True
    ):
        raise ContractValidationError("semantic snapshot compatibility failed")
    expected_fingerprint = request["semantic_layer"]["origin_profile_fingerprint"]
    if (
        snapshot.get("snapshot_fingerprint") != expected_fingerprint
        or compatibility.get("snapshot_fingerprint") != expected_fingerprint
    ):
        raise ContractValidationError("semantic snapshot fingerprint drifted")
    policy_result = _record_index(
        validation.get("policy_results"),
        "analysis_id",
        ANALYSIS_ID,
        label="semantic policy results",
    )
    if (
        policy_result.get("usable_as_semantic_input") is not True
        or policy_result.get("has_complete_manifest_role_set") is not True
        or CAPABILITY_ID not in policy_result.get("candidate_capability_ids", [])
    ):
        raise ContractValidationError("selected semantic policy is not usable")
    role_result = _record_index(
        policy_result.get("role_set_results"),
        "capability_id",
        CAPABILITY_ID,
        label="semantic role-set results",
    )
    if role_result.get("complete") is not True:
        raise ContractValidationError("semantic capability roles are incomplete")
    if attachment.get("attachment_status") != "attached":
        raise ContractValidationError("semantic snapshot attachment was rejected")
    if (attachment.get("compatibility") or {}).get("status") not in {
        "compatible",
        "compatible_with_extensions",
    }:
        raise ContractValidationError("semantic attachment is not compatible")
    if profile.get("dataset_id") != DATASET_CONTRACT_ID:
        raise ContractValidationError("dataset profile identity drifted")


def _evaluate_semantics(
    *,
    clara_root: Path,
    semantic_layer_path: Path,
    request: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _profiler, semantics, _renderer, _evidence = _component_modules(clara_root)
    layer = _load_json(semantic_layer_path)
    manifest = _load_json(
        clara_root
        / "modules"
        / "reporting-engine"
        / "catalog"
        / "selection_manifest.json"
    )
    validation = semantics.validate_semantic_layer(
        layer,
        dict(profile),
        manifest,
    )
    attachment = semantics.build_snapshot_attachment(layer, dict(profile))
    _validate_semantic_gate(
        layer=layer,
        request=request,
        profile=profile,
        validation=validation,
        attachment=attachment,
    )
    return layer, validation, attachment


def _read_prepared_cells(
    path: Path,
    *,
    request: Mapping[str, Any],
) -> tuple[
    dict[tuple[str, str, str], Decimal],
    dict[str, dict[str, str]],
]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != PREPARED_COLUMNS:
            raise ContractValidationError("prepared monthly P&L columns drifted")
        rows = list(reader)
    periods = request["render"]["periods"]
    allowed_periods = set(periods)
    cells: dict[tuple[str, str, str], Decimal] = {}
    row_metadata: dict[str, dict[str, str]] = {}
    for position, row in enumerate(rows, start=2):
        address = (row["row_key"], row["period"], row["scenario"])
        if address in cells:
            raise ContractValidationError(f"duplicate prepared cell: {address}")
        if row["period"] not in allowed_periods or row["scenario"] != SCENARIO:
            raise ContractValidationError(
                f"prepared cell is outside reviewed scope: {address}"
            )
        if row["unit"] != "USD_thousands":
            raise ContractValidationError("prepared statement unit drifted")
        if re.fullmatch(r"[0-9]{3}", row["display_order"]) is None:
            raise ContractValidationError("prepared display_order must be zero-padded")
        cells[address] = _parse_decimal(
            row["value"],
            label=f"prepared monthly P&L row {position} value",
        )
        metadata = {
            "display_order": row["display_order"],
            "line_type": row["line_type"],
        }
        previous = row_metadata.setdefault(row["row_key"], metadata)
        if previous != metadata:
            raise ContractValidationError(
                f"prepared row metadata varies for {row['row_key']}"
            )
    expected_addresses = {
        (row_key, period, SCENARIO) for row_key in row_metadata for period in periods
    }
    if cells.keys() != expected_addresses:
        raise ContractValidationError(
            "prepared monthly P&L does not contain a complete rectangular scope"
        )
    if len(row_metadata) != 14 or len(cells) != EXPECTED_CELL_COUNT:
        raise ContractValidationError("prepared numeric cell count drifted")
    return cells, row_metadata


def _validate_recipe(
    *,
    recipe: Mapping[str, Any],
    request: Mapping[str, Any],
    row_metadata: Mapping[str, Mapping[str, str]],
) -> tuple[list[str], list[tuple[str, str]]]:
    presentation = {field: recipe.get(field) for field in EXPECTED_RECIPE_PRESENTATION}
    if presentation != EXPECTED_RECIPE_PRESENTATION:
        raise ContractValidationError(
            "statement recipe reviewed presentation boundary drifted"
        )
    mappings = recipe.get("mappings")
    if mappings != {
        "row_key_column": "row_key",
        "period_column": "period",
        "scenario_column": "scenario",
        "value_column": "value",
    }:
        raise ContractValidationError("statement recipe mappings drifted")
    periods = request["render"]["periods"]
    if recipe.get("periods") != periods:
        raise ContractValidationError("statement recipe periods drifted")
    scenarios_by_period = recipe.get("scenarios_by_period")
    if scenarios_by_period != {period: [SCENARIO] for period in periods}:
        raise ContractValidationError("statement recipe scenarios drifted")
    rows = recipe.get("statement_rows")
    if not isinstance(rows, list) or len(rows) != 14:
        raise ContractValidationError("statement recipe must contain 14 rows")
    row_keys: list[str] = []
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ContractValidationError("statement recipe rows must be objects")
        key = _text(row.get("key"), label="statement recipe row key")
        if key in row_keys:
            raise ContractValidationError(f"duplicate statement recipe row: {key}")
        if row.get("source_key") != key or "formula" in row:
            raise ContractValidationError(
                "statement recipe must use source-key-only transport"
            )
        metadata = row_metadata.get(key)
        if metadata is None:
            raise ContractValidationError(
                f"statement recipe row has no prepared values: {key}"
            )
        if metadata["display_order"] != f"{position:03d}":
            raise ContractValidationError(
                f"statement recipe order does not match prepared row {key}"
            )
        if row.get("line_type", "detail") != metadata["line_type"]:
            raise ContractValidationError(
                f"statement recipe line_type does not match prepared row {key}"
            )
        row_keys.append(key)
    if set(row_keys) != set(row_metadata):
        raise ContractValidationError("statement recipe row inventory drifted")
    pairs = [(period, SCENARIO) for period in periods]
    return row_keys, pairs


def _read_rendered_cells(
    chart_data_path: Path,
    *,
    recipe: Mapping[str, Any],
    row_keys: Sequence[str],
    pairs: Sequence[tuple[str, str]],
    row_metadata: Mapping[str, Mapping[str, str]],
) -> dict[tuple[str, str, str], Decimal]:
    expected_value_columns = [f"{period}_{scenario}" for period, scenario in pairs]
    expected_columns = (
        "key",
        "label",
        "position",
        "level",
        "line_type",
        "prefix",
        *expected_value_columns,
    )
    with chart_data_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected_columns:
            raise ContractValidationError("rendered chart-data columns drifted")
        rows = list(reader)
    if [row["key"] for row in rows] != list(row_keys):
        raise ContractValidationError("rendered statement row order drifted")
    recipe_rows = {row["key"]: row for row in recipe["statement_rows"]}
    cells: dict[tuple[str, str, str], Decimal] = {}
    for row_position, row in enumerate(rows, start=1):
        row_key = row["key"]
        if row["position"] != str(row_position):
            raise ContractValidationError("rendered statement position drifted")
        recipe_row = recipe_rows[row_key]
        if row["label"] != recipe_row["label"]:
            raise ContractValidationError("rendered statement label drifted")
        if row["level"] != str(recipe_row.get("level", 0)):
            raise ContractValidationError("rendered statement level drifted")
        if row["line_type"] != row_metadata[row_key]["line_type"]:
            raise ContractValidationError("rendered statement line_type drifted")
        if row["prefix"] != recipe_row.get("prefix", ""):
            raise ContractValidationError("rendered statement prefix drifted")
        for period, scenario in pairs:
            address = (row_key, period, scenario)
            if address in cells:
                raise ContractValidationError(f"duplicate rendered cell: {address}")
            cells[address] = _parse_decimal(
                row[f"{period}_{scenario}"],
                label=f"rendered value {address}",
            )
    if len(cells) != EXPECTED_CELL_COUNT:
        raise ContractValidationError("rendered numeric cell count drifted")
    return cells


def _validate_context_cells(
    path: Path,
    *,
    recipe: Mapping[str, Any],
    row_keys: Sequence[str],
    pairs: Sequence[tuple[str, str]],
    prepared_cells: Mapping[tuple[str, str, str], Decimal],
) -> None:
    context = _load_json(path)
    _exact_keys(
        context,
        required={
            "schema_version",
            "analysis_type",
            "object_type",
            "capability_id",
            "table_key",
            "table_spec_name",
            "statement_label",
            "unit",
            "title",
            "scope_label",
            "source_file",
            "periods",
            "scenarios_by_period",
            "chart_title_lines",
            "chart_title",
            "title_contract",
            "row_grain",
            "statement_rows",
            "table_rows",
        },
        label="statement chart context",
    )
    title_lines = [
        recipe["title"],
        f"{recipe['statement_label']} in {recipe['unit']}",
        recipe["scope_label"],
    ]
    expected_metadata = {
        "schema_version": "1.0",
        "analysis_type": "pnl_statement_table",
        "object_type": "table",
        "capability_id": CAPABILITY_ID,
        "table_key": "pnl_statement_table",
        "table_spec_name": "pnl_statement_table",
        "statement_label": recipe["statement_label"],
        "unit": recipe["unit"],
        "title": recipe["title"],
        "scope_label": recipe["scope_label"],
        "source_file": "monthly_pnl.csv",
        "periods": recipe["periods"],
        "scenarios_by_period": recipe["scenarios_by_period"],
        "chart_title_lines": title_lines,
        "chart_title": " / ".join(title_lines),
        "title_contract": {
            "who": title_lines[0],
            "what": title_lines[1],
            "when": title_lines[2],
        },
        "row_grain": (
            "One row per ordered P&L statement line; values are transported "
            "from source keys without renderer formulas."
        ),
        "statement_rows": recipe["statement_rows"],
    }
    for field, expected in expected_metadata.items():
        if context[field] != expected:
            raise ContractValidationError(
                f"statement chart context metadata drifted: {field}"
            )
    table_rows = context["table_rows"]
    if not isinstance(table_rows, list) or len(table_rows) != len(row_keys):
        raise ContractValidationError("statement chart context row inventory drifted")
    recipe_rows = {row["key"]: row for row in recipe["statement_rows"]}
    expected_value_fields = {f"{period}_{scenario}" for period, scenario in pairs}
    seen_addresses: set[tuple[str, str, str]] = set()
    for position, (row_key, row) in enumerate(
        zip(row_keys, table_rows),
        start=1,
    ):
        if not isinstance(row, Mapping):
            raise ContractValidationError(
                "statement chart context row must be an object"
            )
        _exact_keys(
            row,
            required={
                "key",
                "label",
                "position",
                "level",
                "line_type",
                "prefix",
                "values",
            },
            label=f"statement chart context row {position}",
        )
        recipe_row = recipe_rows[row_key]
        expected_row_metadata = {
            "key": row_key,
            "label": recipe_row["label"],
            "position": position,
            "level": recipe_row.get("level", 0),
            "line_type": recipe_row.get("line_type", "detail"),
            "prefix": recipe_row.get("prefix", ""),
        }
        if {
            field: row[field] for field in expected_row_metadata
        } != expected_row_metadata:
            raise ContractValidationError(
                f"statement chart context row metadata drifted: {row_key}"
            )
        values = row["values"]
        if not isinstance(values, Mapping) or set(values) != expected_value_fields:
            raise ContractValidationError(
                f"statement chart context value fields drifted: {row_key}"
            )
        for period, scenario in pairs:
            address = (row_key, period, scenario)
            raw_value = values[f"{period}_{scenario}"]
            if isinstance(raw_value, bool) or not isinstance(
                raw_value,
                (int, float),
            ):
                raise ContractValidationError(
                    f"statement chart context value is not numeric: {address}"
                )
            context_value = Decimal(str(raw_value))
            if not context_value.is_finite():
                raise ContractValidationError(
                    f"statement chart context value is not finite: {address}"
                )
            if context_value != prepared_cells[address]:
                raise ContractValidationError(
                    f"statement chart context value drifted: {address}"
                )
            if address in seen_addresses:
                raise ContractValidationError(
                    f"duplicate statement chart context address: {address}"
                )
            seen_addresses.add(address)
    if seen_addresses != set(prepared_cells):
        raise ContractValidationError(
            "statement chart context address coverage drifted"
        )


def _read_serialized_html_cells(
    path: Path,
    *,
    recipe: Mapping[str, Any],
    row_keys: Sequence[str],
    pairs: Sequence[tuple[str, str]],
) -> list[str]:
    parser = _StatementTableParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    if (
        parser._capture_kind is not None
        or parser._capture_tag is not None
        or parser._thead_depth
        or parser._tbody_depth
        or parser._header_row is not None
        or parser._row_values is not None
        or parser._in_title_header
    ):
        raise ContractValidationError(
            "rendered statement HTML is structurally incomplete"
        )
    expected_header_rows = [
        [
            ("blank", "", 1),
            *[
                (
                    "period",
                    period,
                    len(recipe["scenarios_by_period"][period]),
                )
                for period in recipe["periods"]
            ],
        ],
        [
            ("blank", "", 1),
            *[("scenario", scenario, 1) for _period, scenario in pairs],
        ],
    ]
    if parser.header_rows != expected_header_rows:
        raise ContractValidationError(
            "rendered statement HTML header-cell structure drifted"
        )
    expected_title_lines = [
        ("plain", recipe["title"]),
        (
            "metric",
            f"{recipe['statement_label']} in {recipe['unit']}",
        ),
        ("plain", recipe["scope_label"]),
    ]
    if parser.title_lines != expected_title_lines:
        raise ContractValidationError(
            "rendered statement HTML presentation boundary drifted"
        )
    if parser.source_lines != ["Source: monthly_pnl.csv"]:
        raise ContractValidationError("rendered statement HTML source footnote drifted")
    recipe_rows = recipe["statement_rows"]
    if [row["key"] for row in recipe_rows] != list(row_keys):
        raise ContractValidationError(
            "statement recipe row keys drifted before HTML validation"
        )
    expected_labels = [f"{row['prefix']} {row['label']}".strip() for row in recipe_rows]
    if len(set(expected_labels)) != len(expected_labels):
        raise ContractValidationError(
            "statement recipe produces ambiguous serialized row labels"
        )
    serialized_labels = [label for label, _values in parser.body_rows]
    if serialized_labels != expected_labels:
        raise ContractValidationError("rendered statement HTML row labels drifted")
    values_per_row = len(pairs)
    if any(len(values) != values_per_row for _label, values in parser.body_rows):
        raise ContractValidationError("rendered statement HTML row width drifted")
    return [value for _label, values in parser.body_rows for value in values]


def _address_payload(
    *,
    row_keys: Sequence[str],
    pairs: Sequence[tuple[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            "row_key": row_key,
            "period": period,
            "scenario": scenario,
        }
        for row_key in row_keys
        for period, scenario in pairs
    ]


def _build_serialized_cell_rows(
    *,
    prepared_cells: Mapping[tuple[str, str, str], Decimal],
    rendered_cells: Mapping[tuple[str, str, str], Decimal],
    serialized_cells: Sequence[str],
    row_keys: Sequence[str],
    pairs: Sequence[tuple[str, str]],
    row_metadata: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    if set(prepared_cells) != set(rendered_cells):
        missing = sorted(set(prepared_cells) - set(rendered_cells))
        extra = sorted(set(rendered_cells) - set(prepared_cells))
        raise ContractValidationError(
            f"rendered address coverage mismatch; missing={missing}, extra={extra}"
        )
    if len(serialized_cells) != EXPECTED_CELL_COUNT:
        raise ContractValidationError(
            f"serialized HTML numeric cell count must be {EXPECTED_CELL_COUNT}"
        )
    rows: list[dict[str, str]] = []
    serialized_position = 0
    for row_position, row_key in enumerate(row_keys, start=1):
        for column_position, (period, scenario) in enumerate(pairs, start=1):
            address = (row_key, period, scenario)
            prepared = prepared_cells[address]
            rendered = rendered_cells[address]
            if rendered != prepared:
                raise ContractValidationError(
                    f"rendered value does not equal prepared value at {address}"
                )
            serialized_text = serialized_cells[serialized_position]
            serialized_position += 1
            serialized = _parse_serialized_decimal(
                serialized_text,
                label=f"serialized HTML value {address}",
            )
            if serialized != prepared:
                raise ContractValidationError(
                    f"serialized HTML value does not equal prepared value at {address}"
                )
            canonical_value = _canonical_decimal(prepared)
            rows.append(
                {
                    "cell_id": f"cell-{row_position:03d}-{column_position:03d}",
                    "row_key": row_key,
                    "period": period,
                    "scenario": scenario,
                    "display_order": row_metadata[row_key]["display_order"],
                    "render_row_position": f"{row_position:03d}",
                    "render_column_position": f"{column_position:03d}",
                    "prepared_value": canonical_value,
                    "rendered_value": _canonical_decimal(rendered),
                    "serialized_text": serialized_text,
                    "value_sha256": canonical_json_sha256(canonical_value),
                }
            )
    return rows


def _read_serialized_cell_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SERIALIZED_CELL_COLUMNS:
            raise ContractValidationError("serialized-cell ledger columns drifted")
        rows = list(reader)
    if len(rows) != EXPECTED_CELL_COUNT:
        raise ContractValidationError("serialized-cell ledger count drifted")
    if len({row["cell_id"] for row in rows}) != len(rows):
        raise ContractValidationError("serialized-cell ledger has duplicate cell IDs")
    addresses = [(row["row_key"], row["period"], row["scenario"]) for row in rows]
    if len(set(addresses)) != len(addresses):
        raise ContractValidationError("serialized-cell ledger has duplicate addresses")
    for row in rows:
        value = _parse_decimal(
            row["prepared_value"],
            label=f"serialized-cell ledger {row['cell_id']} prepared value",
        )
        if _canonical_decimal(value) != row["prepared_value"]:
            raise ContractValidationError(
                "serialized-cell prepared values must be canonical"
            )
        if row["rendered_value"] != row["prepared_value"]:
            raise ContractValidationError(
                "serialized-cell rendered value does not equal prepared value"
            )
        if row["value_sha256"] != canonical_json_sha256(row["prepared_value"]):
            raise ContractValidationError("serialized-cell value digest drifted")
    return rows


def _normalized_component_manifest(
    path: Path,
    *,
    recipe: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _load_json(path)
    _exact_keys(
        payload,
        required={"schema_version", "producer", "artifacts", "output_dir"},
        label="component artifact manifest",
    )
    if payload["schema_version"] != "1.0" or payload["producer"] != {
        "plugin": "statement-analysis",
        "capability_id": CAPABILITY_ID,
    }:
        raise ContractValidationError("component artifact manifest identity drifted")
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise ContractValidationError("component artifact manifest inventory drifted")
    table_artifact = artifacts[0]
    if not isinstance(table_artifact, Mapping):
        raise ContractValidationError("component table artifact is malformed")
    _exact_keys(
        table_artifact,
        required={
            "artifact_id",
            "kind",
            "artifact_type",
            "capability_id",
            "table_key",
            "table_spec_name",
            "path",
            "source_path",
            "data_path",
            "context_path",
            "resolved_parameters",
        },
        label="component table artifact",
    )
    expected_parameters = {
        "source_file": "monthly_pnl.csv",
        "statement_rows": recipe["statement_rows"],
        "periods": recipe["periods"],
        "scenarios_by_period": recipe["scenarios_by_period"],
        "statement_label": recipe["statement_label"],
        "unit": recipe["unit"],
        "scope_label": recipe["scope_label"],
    }
    expected_table_artifact = {
        "artifact_id": "pnl_statement_table",
        "kind": "tables",
        "artifact_type": "table",
        "capability_id": CAPABILITY_ID,
        "table_key": "pnl_statement_table",
        "table_spec_name": "pnl_statement_table",
        "path": "pnl_statement_table.html",
        "source_path": "pnl_statement_table.html",
        "data_path": "pnl_statement_table_chart_data.csv",
        "context_path": "pnl_statement_table_chart_context.json",
        "resolved_parameters": expected_parameters,
    }
    if dict(table_artifact) != expected_table_artifact:
        raise ContractValidationError("component table artifact wiring drifted")
    context_artifact = artifacts[1]
    if context_artifact != {
        "artifact_id": "context",
        "kind": "contexts",
        "artifact_type": "context",
        "path": "pnl_statement_table_chart_context.json",
    }:
        raise ContractValidationError("component context artifact wiring drifted")
    if not isinstance(payload["output_dir"], str) or not payload["output_dir"]:
        raise ContractValidationError("component artifact manifest lacks output_dir")
    payload["output_dir"] = "<isolated-run-dir>"
    return payload


def _validate_final_artifacts(path: Path) -> None:
    payload = _load_json(path)
    expected = {
        "schema_version": "1.0",
        "plugin": "statement-analysis",
        "outputs": [
            {
                "path": "pnl_statement_table.html",
                "kind": "html",
                "status": "written",
            },
            {
                "path": "pnl_statement_table_chart_data.csv",
                "kind": "csv",
                "status": "written",
            },
            {
                "path": "pnl_statement_table_chart_context.json",
                "kind": "json",
                "status": "written",
            },
            {
                "path": "artifact_manifest.json",
                "kind": "json",
                "status": "written",
            },
        ],
    }
    if payload != expected:
        raise ContractValidationError("component final-artifact wiring drifted")


def _normalized_effective_recipe(
    path: Path,
    *,
    expected_source_file: Path,
) -> dict[str, Any]:
    payload = _load_json(path)
    source_file = payload.get("source_file")
    if not isinstance(source_file, str) or not Path(source_file).is_absolute():
        raise ContractValidationError(
            "effective render recipe must record the exact absolute input path"
        )
    if Path(source_file).resolve() != expected_source_file.resolve():
        raise ContractValidationError(
            "effective render recipe source_file does not match render input"
        )
    payload["source_file"] = "evidence/monthly_pnl.csv"
    return payload


def _portable_render_summary(
    *,
    clara_root: Path,
    handoff_dir: Path,
    render_dir: Path,
    render_manifest: Mapping[str, Any],
    expected_input_sha256: str,
    expected_role_bindings: Mapping[str, Any],
) -> dict[str, Any]:
    actual_files = {
        path.relative_to(render_dir).as_posix()
        for path in render_dir.rglob("*")
        if path.is_file()
    }
    if actual_files != EXPECTED_RENDER_FILES:
        raise ContractValidationError(
            "render output set drifted; "
            f"missing={sorted(EXPECTED_RENDER_FILES - actual_files)}, "
            f"extra={sorted(actual_files - EXPECTED_RENDER_FILES)}"
        )
    _exact_keys(
        render_manifest,
        required={
            "schema_version",
            "capability_id",
            "owner",
            "adapter_id",
            "component_name",
            "legacy_plugin_source",
            "input_file",
            "output_dir",
            "artifact_mode",
            "include_variants",
            "invocation_plan",
            "recipe",
            "command",
            "runner",
            "artifacts",
            "render_proof",
            "evidence",
            "boundary",
        },
        label="render manifest",
    )
    if (
        render_manifest.get("schema_version") != "0.2"
        or render_manifest.get("capability_id") != CAPABILITY_ID
        or render_manifest.get("owner") != "clara.reporting-engine"
        or render_manifest.get("adapter_id") != "reporting-engine.statement"
        or render_manifest.get("component_name") != "statement-analysis"
        or render_manifest.get("legacy_plugin_source") != "statement-analysis"
        or render_manifest.get("artifact_mode") != ARTIFACT_MODE
        or render_manifest.get("include_variants") is not False
        or render_manifest.get("artifacts") != sorted(EXPECTED_RENDER_FILES)
        or render_manifest.get("boundary")
        != (
            "Unified Clara reporting-engine render call with exact input, "
            "request, recipe, and current-run output byte evidence. Semantic "
            "chart selection and interpretation are outside this layer."
        )
        or (render_manifest.get("runner") or {}).get("status") != "ok"
        or (render_manifest.get("render_proof") or {}).get("status") != "rendered"
        or (render_manifest.get("recipe") or {}).get("required_roles", {}).get("status")
        != "satisfied"
        or (render_manifest.get("recipe") or {})
        .get("required_roles", {})
        .get("missing_roles")
        != []
    ):
        raise ContractValidationError("render manifest success boundary failed")
    command = render_manifest["command"]
    expected_input_path = render_dir.parent / "evidence" / "monthly_pnl.csv"
    if not isinstance(command, list) or len(command) != 9:
        raise ContractValidationError("render command contract drifted")
    runner_path = Path(str(command[1]))
    implementation_receipts = _implementation_receipts(clara_root)
    if (
        not runner_path.is_file()
        or file_sha256(runner_path)
        != implementation_receipts["statement_runner"]["sha256"]
        or Path(str(command[2])).resolve() != expected_input_path.resolve()
        or command[3] != "--output-dir"
        or Path(str(command[4])).parent.resolve() != handoff_dir.resolve()
        or not Path(str(command[4])).name.startswith(".clara-reporting-run-")
        or command[5:8] != ["--language", "en", "--recipe"]
        or Path(str(command[8])).parent != Path(str(command[4]))
        or Path(str(command[8])).name != "render_request_recipe.json"
    ):
        raise ContractValidationError("render command implementation drifted")
    statement_core_path = runner_path.parent / "statement_core.py"
    if (
        not statement_core_path.is_file()
        or file_sha256(statement_core_path)
        != implementation_receipts["statement_core"]["sha256"]
    ):
        raise ContractValidationError("statement core implementation drifted")
    runner = render_manifest["runner"]
    if not isinstance(runner, Mapping):
        raise ContractValidationError("render runner receipt is malformed")
    _exact_keys(
        runner,
        required={
            "status",
            "runner_type",
            "returncode",
            "stdout",
            "stderr",
        },
        label="render runner receipt",
    )
    if (
        runner["status"] != "ok"
        or runner["runner_type"] != "component_cli"
        or runner["returncode"] != 0
        or runner["stderr"] != ""
    ):
        raise ContractValidationError("render runner receipt drifted")
    try:
        runner_stdout = json.loads(
            runner["stdout"],
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise ContractValidationError("render runner stdout is invalid") from exc
    if not isinstance(runner_stdout, Mapping):
        raise ContractValidationError("render runner stdout is malformed")
    _exact_keys(
        runner_stdout,
        required={
            "status",
            "html_path",
            "csv_path",
            "context_path",
            "manifest_path",
            "row_count",
        },
        label="render runner stdout",
    )
    expected_runner_files = {
        "html_path": "pnl_statement_table.html",
        "csv_path": "pnl_statement_table_chart_data.csv",
        "context_path": "pnl_statement_table_chart_context.json",
        "manifest_path": "artifact_manifest.json",
    }
    if (
        runner_stdout["status"] != "ok"
        or runner_stdout["row_count"] != 14
        or any(
            Path(str(runner_stdout[field])).name != filename
            for field, filename in expected_runner_files.items()
        )
    ):
        raise ContractValidationError("render runner stdout drifted")
    invocation_plan = render_manifest.get("invocation_plan") or {}
    mechanical_compatibility = invocation_plan.get("compatibility") or {}
    if mechanical_compatibility.get(
        "status"
    ) != "mechanically_incomplete" or mechanical_compatibility.get("issues") != [
        "requires_semantic_or_package_role"
    ]:
        raise ContractValidationError(
            "unexpected mechanical compatibility boundary for reviewed handoff"
        )
    mechanical_roles = {
        record.get("role"): record
        for record in invocation_plan.get("required_roles", [])
        if isinstance(record, Mapping)
    }
    expected_mechanical_roles = {
        "period_axis": (
            "candidate_ambiguous",
            ["period", "period_start", "period_end"],
        ),
        "statement_value": ("candidate_available", ["value"]),
        "statement_line_item": (
            "candidate_ambiguous",
            ["line_type", "row_key"],
        ),
        "statement_scenario": ("candidate_available", ["scenario"]),
        "statement_structure": ("semantic_or_package_gap", []),
    }
    if set(mechanical_roles) != set(expected_mechanical_roles):
        raise ContractValidationError("mechanical required-role inventory drifted")
    for role, (status, candidates) in expected_mechanical_roles.items():
        record = mechanical_roles[role]
        if (
            record.get("dataset_match_status") != status
            or record.get("dataset_candidates") != candidates
        ):
            raise ContractValidationError(
                f"mechanical role evidence drifted for {role}"
            )
    if (
        Path(str(render_manifest.get("input_file"))).resolve()
        != expected_input_path.resolve()
        or Path(str(render_manifest.get("output_dir"))).resolve()
        != render_dir.resolve()
    ):
        raise ContractValidationError("render manifest path boundary drifted")
    input_evidence = (render_manifest.get("evidence") or {}).get("input") or {}
    if (
        Path(str(input_evidence.get("path"))).resolve() != expected_input_path.resolve()
        or input_evidence.get("sha256") != expected_input_sha256
        or input_evidence.get("size_bytes") != expected_input_path.stat().st_size
    ):
        raise ContractValidationError("render input evidence drifted")
    request_contract = {
        "capability_id": CAPABILITY_ID,
        "role_bindings": dict(expected_role_bindings),
        "options": {},
        "language": "en",
        "currency": None,
        "artifact_mode": ARTIFACT_MODE,
        "include_variants": False,
    }
    request_evidence = (render_manifest.get("evidence") or {}).get("request") or {}
    expected_request_sha256 = canonical_json_sha256(request_contract)
    if (
        request_evidence.get("contract") != request_contract
        or request_evidence.get("sha256") != expected_request_sha256
    ):
        raise ContractValidationError("render request evidence drifted")

    output_records = (render_manifest.get("evidence") or {}).get("outputs")
    if not isinstance(output_records, list):
        raise ContractValidationError("render output evidence is missing")
    if {
        record.get("path") for record in output_records
    } != EXPECTED_CURRENT_RUN_OUTPUTS:
        raise ContractValidationError("render current-run output inventory drifted")
    for record in output_records:
        relative = _text(record.get("path"), label="render output path")
        output_path = render_dir / relative
        if (
            record.get("sha256") != file_sha256(output_path)
            or record.get("size_bytes") != output_path.stat().st_size
        ):
            raise ContractValidationError(f"render output receipt drifted: {relative}")
    if (render_manifest.get("evidence") or {}).get(
        "output_set_sha256"
    ) != canonical_json_sha256(output_records):
        raise ContractValidationError("render raw output-set digest drifted")
    recipe_evidence = (render_manifest.get("evidence") or {}).get("recipe") or {}
    generated_recipe_path = render_dir / "render_request_recipe.json"
    if (
        Path(str(recipe_evidence.get("path"))).resolve()
        != generated_recipe_path.resolve()
        or recipe_evidence.get("sha256") != file_sha256(generated_recipe_path)
        or recipe_evidence.get("size_bytes") != generated_recipe_path.stat().st_size
    ):
        raise ContractValidationError("render recipe evidence drifted")
    if (render_dir / "render_request_recipe.json").read_bytes() != (
        render_dir / "used_recipe.json"
    ).read_bytes():
        raise ContractValidationError(
            "generated render request recipe and used recipe differ"
        )

    normalized_recipe = _normalized_effective_recipe(
        render_dir / "used_recipe.json",
        expected_source_file=expected_input_path,
    )
    expected_normalized_recipe = _load_json(
        render_dir.parent / "contracts" / "statement_render_recipe.json"
    )
    expected_normalized_recipe.update(
        {
            "source_file": "evidence/monthly_pnl.csv",
            "language": "en",
            "options": {},
        }
    )
    if normalized_recipe != expected_normalized_recipe:
        raise ContractValidationError(
            "effective render recipe does not match reviewed statement recipe"
        )
    reviewed_recipe = _load_json(
        render_dir.parent / "contracts" / "statement_render_recipe.json"
    )
    normalized_component = _normalized_component_manifest(
        render_dir / "artifact_manifest.json",
        recipe=reviewed_recipe,
    )
    _validate_final_artifacts(render_dir / "final_artifacts.json")
    portable_outputs = [
        _artifact_receipt(handoff_dir, render_dir / relative)
        for relative in PORTABLE_RENDER_FILES
    ]
    return {
        "capability_id": CAPABILITY_ID,
        "adapter_id": "reporting-engine.statement",
        "component_name": "statement-analysis",
        "request_sha256": expected_request_sha256,
        "input_sha256": expected_input_sha256,
        "normalized_effective_recipe_sha256": canonical_json_sha256(normalized_recipe),
        "portable_outputs": portable_outputs,
        "portable_output_set_sha256": canonical_json_sha256(portable_outputs),
        "normalized_component_manifest_sha256": canonical_json_sha256(
            normalized_component
        ),
        "mechanical_compatibility_status": "mechanically_incomplete",
        "mechanical_compatibility_issues": ["requires_semantic_or_package_role"],
        "reviewed_semantic_override_status": "verified",
        "raw_manifest_validated": True,
        "raw_manifest_portable": False,
    }


def _render_once(
    *,
    clara_root: Path,
    input_file: Path,
    output_dir: Path,
    recipe_path: Path,
    profile: Mapping[str, Any],
    role_bindings: Mapping[str, Any],
) -> dict[str, Any]:
    _profiler, _semantics, renderer, _evidence = _component_modules(clara_root)
    request = renderer.RenderRequest(
        capability_id=CAPABILITY_ID,
        input_file=input_file.resolve(),
        output_dir=output_dir.resolve(),
        recipe_path=recipe_path.resolve(),
        dataset_profile=dict(profile),
        role_bindings=dict(role_bindings),
        artifact_mode=ARTIFACT_MODE,
    )
    return renderer.render_capability(
        request,
        root=clara_root / "modules" / "reporting-engine",
    )


def _assert_fresh_render(
    *,
    clara_root: Path,
    handoff_dir: Path,
    profile: Mapping[str, Any],
    role_bindings: Mapping[str, Any],
    expected_render_summary: Mapping[str, Any],
) -> None:
    input_file = handoff_dir / "evidence" / "monthly_pnl.csv"
    recipe_path = handoff_dir / "contracts" / "statement_render_recipe.json"
    reviewed_recipe = _load_json(recipe_path)
    with TemporaryDirectory(prefix="clara-m4-fresh-render-") as raw_dir:
        fresh_root = Path(raw_dir)
        fresh_render = fresh_root / "render"
        manifest = _render_once(
            clara_root=clara_root,
            input_file=input_file,
            output_dir=fresh_render,
            recipe_path=recipe_path,
            profile=profile,
            role_bindings=role_bindings,
        )
        for relative in PORTABLE_RENDER_FILES:
            if (fresh_render / relative).read_bytes() != (
                handoff_dir / "render" / relative
            ).read_bytes():
                raise ContractValidationError(
                    f"fresh render does not reproduce {relative}"
                )
        if canonical_json_sha256(
            _normalized_effective_recipe(
                fresh_render / "used_recipe.json",
                expected_source_file=handoff_dir / "evidence" / "monthly_pnl.csv",
            )
        ) != expected_render_summary.get("normalized_effective_recipe_sha256"):
            raise ContractValidationError(
                "fresh render does not reproduce the normalized effective recipe"
            )
        fresh_component = _normalized_component_manifest(
            fresh_render / "artifact_manifest.json",
            recipe=reviewed_recipe,
        )
        _validate_final_artifacts(fresh_render / "final_artifacts.json")
        if canonical_json_sha256(fresh_component) != expected_render_summary.get(
            "normalized_component_manifest_sha256"
        ):
            raise ContractValidationError(
                "fresh render does not reproduce normalized component manifest"
            )
        output_records = (manifest.get("evidence") or {}).get("outputs") or []
        for record in output_records:
            relative = record.get("path")
            if relative in {"artifact_manifest.json", "used_recipe.json"}:
                continue
            if relative not in PORTABLE_RENDER_FILES:
                raise ContractValidationError(
                    f"fresh render produced unexpected stable artifact {relative}"
                )


def _coverage_digests(
    *,
    row_keys: Sequence[str],
    pairs: Sequence[tuple[str, str]],
    prepared_cells: Mapping[tuple[str, str, str], Decimal],
) -> tuple[str, str]:
    addresses = _address_payload(row_keys=row_keys, pairs=pairs)
    values = [
        {
            **address,
            "value": _canonical_decimal(
                prepared_cells[
                    (
                        address["row_key"],
                        address["period"],
                        address["scenario"],
                    )
                ]
            ),
        }
        for address in addresses
    ]
    return canonical_json_sha256(addresses), canonical_json_sha256(values)


def _build_publication_receipt(
    *,
    case_id: str,
    prepared_receipt: Mapping[str, Any],
    semantic_review_basis_receipt: Mapping[str, Any],
    semantic_receipt: Mapping[str, Any],
    request_receipt: Mapping[str, Any],
    recipe_receipt: Mapping[str, Any],
    implementation_receipts: Mapping[str, Any],
    render_summary: Mapping[str, Any],
    serialized_cells_receipt: Mapping[str, Any],
    address_set_sha256: str,
    value_set_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": PUBLICATION_RECEIPT_SCHEMA_VERSION,
        "case_id": case_id,
        "classification": CLASSIFICATION,
        "contracts": {
            "semantic_review_basis_sha256": semantic_review_basis_receipt["sha256"],
            "semantic_layer_sha256": semantic_receipt["sha256"],
            "reporting_request_sha256": request_receipt["sha256"],
            "statement_recipe_sha256": recipe_receipt["sha256"],
            "implementation_set_sha256": canonical_json_sha256(implementation_receipts),
        },
        "prepared_input": {
            "sha256": prepared_receipt["sha256"],
            "size_bytes": prepared_receipt["size_bytes"],
        },
        "render": dict(render_summary),
        "serialized_html_numeric_domain": {
            "definition": SERIALIZED_HTML_NUMERIC_DOMAIN,
            "expected_cell_count": EXPECTED_CELL_COUNT,
            "verified_cell_count": EXPECTED_CELL_COUNT,
            "address_set_sha256": address_set_sha256,
            "value_set_sha256": value_set_sha256,
            "serialized_cells_sha256": serialized_cells_receipt["sha256"],
            "coverage_status": "exact",
        },
        "boundaries": {
            "semantic_correctness_proven": False,
            "source_authority_proven": False,
            "human_review_proven": False,
            "publication_approved": False,
            "report_ready": False,
        },
    }


def _draft_evidence_bundle(evidence_dir: Path) -> Path:
    bundle_path = evidence_dir / "evidence-bundle.json"
    _write_json(
        bundle_path,
        {
            "schema_version": "clara.evidence_bundle.v1",
            "bundle_id": "wd40-fy2025-monthly-pnl-reporting-handoff",
            "description": EXPECTED_BUNDLE_DESCRIPTION,
            "artifacts": [
                {
                    "id": "prepared-monthly-pnl",
                    "source_id": "source-prepared-monthly-pnl",
                    "path": "monthly_pnl.csv",
                    "media_type": "text/csv",
                    "sha256": "",
                    "size_bytes": 0,
                    "snapshot_id": "wd40-fy2025-synthetic-monthly-pnl-v1",
                    "table": {
                        "key_fields": ["row_key", "period", "scenario"],
                        "order_by": ["display_order", "period"],
                    },
                },
                {
                    "id": "rendered-statement-values",
                    "source_id": "source-rendered-statement-values",
                    "path": "rendered_statement_values.csv",
                    "media_type": "text/csv",
                    "sha256": "",
                    "size_bytes": 0,
                    "snapshot_id": "wd40-fy2025-rendered-statement-values-v1",
                    "table": {
                        "key_fields": ["key"],
                        "order_by": ["position"],
                    },
                },
                {
                    "id": "serialized-html-numeric-cells",
                    "source_id": "source-serialized-html-numeric-cells",
                    "path": "serialized_html_numeric_cells.csv",
                    "media_type": "text/csv",
                    "sha256": "",
                    "size_bytes": 0,
                    "snapshot_id": "wd40-fy2025-serialized-html-numeric-cells-v1",
                    "table": {
                        "key_fields": ["cell_id"],
                        "order_by": [
                            "render_row_position",
                            "render_column_position",
                        ],
                    },
                },
                {
                    "id": "publication-receipt",
                    "source_id": "source-publication-receipt",
                    "path": "publication_receipt.json",
                    "media_type": "application/json",
                    "sha256": "",
                    "size_bytes": 0,
                    "snapshot_id": "wd40-fy2025-publication-receipt-v1",
                },
            ],
        },
    )
    return bundle_path


def _validate_bundle(
    *,
    clara_root: Path,
    bundle_path: Path,
) -> dict[str, Any]:
    _profiler, _semantics, _renderer, evidence = _component_modules(clara_root)
    validation = evidence.validate_evidence_bundle(bundle_path)
    if (
        validation.get("schema_version") != "clara.evidence_bundle.v1"
        or validation.get("bundle_id") != "wd40-fy2025-monthly-pnl-reporting-handoff"
        or validation.get("artifact_count") != 4
    ):
        raise ContractValidationError("evidence bundle validation drifted")
    expected_contracts = {
        "prepared-monthly-pnl": {
            "source_id": "source-prepared-monthly-pnl",
            "path": "monthly_pnl.csv",
            "media_type": "text/csv",
            "snapshot_id": "wd40-fy2025-synthetic-monthly-pnl-v1",
            "table": {
                "key_fields": ["row_key", "period", "scenario"],
                "order_by": ["display_order", "period"],
                "records_pointer": "",
            },
        },
        "rendered-statement-values": {
            "source_id": "source-rendered-statement-values",
            "path": "rendered_statement_values.csv",
            "media_type": "text/csv",
            "snapshot_id": "wd40-fy2025-rendered-statement-values-v1",
            "table": {
                "key_fields": ["key"],
                "order_by": ["position"],
                "records_pointer": "",
            },
        },
        "serialized-html-numeric-cells": {
            "source_id": "source-serialized-html-numeric-cells",
            "path": "serialized_html_numeric_cells.csv",
            "media_type": "text/csv",
            "snapshot_id": "wd40-fy2025-serialized-html-numeric-cells-v1",
            "table": {
                "key_fields": ["cell_id"],
                "order_by": [
                    "render_row_position",
                    "render_column_position",
                ],
                "records_pointer": "",
            },
        },
        "publication-receipt": {
            "source_id": "source-publication-receipt",
            "path": "publication_receipt.json",
            "media_type": "application/json",
            "snapshot_id": "wd40-fy2025-publication-receipt-v1",
            "table": None,
        },
    }
    raw_bundle = _load_json(bundle_path)
    _exact_keys(
        raw_bundle,
        required={"schema_version", "bundle_id", "description", "artifacts"},
        label="evidence bundle",
    )
    if (
        raw_bundle["schema_version"] != "clara.evidence_bundle.v1"
        or raw_bundle["bundle_id"] != "wd40-fy2025-monthly-pnl-reporting-handoff"
        or raw_bundle["description"] != EXPECTED_BUNDLE_DESCRIPTION
    ):
        raise ContractValidationError("evidence bundle reviewed metadata drifted")
    raw_artifacts = raw_bundle["artifacts"]
    if not isinstance(raw_artifacts, list):
        raise ContractValidationError("evidence bundle artifacts must be a list")
    expected_order = list(expected_contracts)
    if [artifact.get("id") for artifact in raw_artifacts] != expected_order:
        raise ContractValidationError("evidence bundle artifact order drifted")
    for raw_artifact in raw_artifacts:
        if not isinstance(raw_artifact, Mapping):
            raise ContractValidationError("evidence bundle artifact must be an object")
        artifact_id = raw_artifact["id"]
        expected_contract = expected_contracts[artifact_id]
        required_fields = {
            "id",
            "source_id",
            "path",
            "media_type",
            "sha256",
            "size_bytes",
            "snapshot_id",
        }
        if expected_contract["table"] is not None:
            required_fields.add("table")
        _exact_keys(
            raw_artifact,
            required=required_fields,
            label=f"evidence bundle artifact {artifact_id}",
        )
        expected_raw_contract = dict(expected_contract)
        expected_table = expected_raw_contract.get("table")
        if isinstance(expected_table, dict):
            expected_raw_contract["table"] = {
                key: value
                for key, value in expected_table.items()
                if key != "records_pointer"
            }
        actual_raw_contract = {
            field: raw_artifact.get(field)
            for field in (
                "source_id",
                "path",
                "media_type",
                "snapshot_id",
                "table",
            )
        }
        if actual_raw_contract != expected_raw_contract:
            raise ContractValidationError(
                f"evidence bundle raw contract drifted for {artifact_id}"
            )
    artifacts = validation.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise ContractValidationError("evidence bundle artifacts are malformed")
    artifacts_by_id = {artifact.get("id"): artifact for artifact in artifacts}
    if set(artifacts_by_id) != set(expected_contracts):
        raise ContractValidationError("evidence bundle artifact inventory drifted")
    for artifact_id, expected_contract in expected_contracts.items():
        artifact = artifacts_by_id[artifact_id]
        actual_contract = {
            field: artifact.get(field)
            for field in (
                "source_id",
                "path",
                "media_type",
                "snapshot_id",
                "table",
            )
        }
        if actual_contract != expected_contract:
            raise ContractValidationError(
                f"evidence bundle contract drifted for {artifact_id}"
            )
    return validation


def _assemble_handoff_receipt(
    *,
    clara_root: Path,
    handoff_dir: Path,
    request: Mapping[str, Any],
    profile: Mapping[str, Any],
    validation: Mapping[str, Any],
    render_summary: Mapping[str, Any],
    address_set_sha256: str,
    value_set_sha256: str,
    bundle_validation: Mapping[str, Any],
) -> dict[str, Any]:
    contracts_dir = handoff_dir / "contracts"
    audit_dir = handoff_dir / "audit"
    evidence_dir = handoff_dir / "evidence"
    semantic_snapshot = validation["snapshot"]
    compatibility = semantic_snapshot["compatibility"]
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "handoff_id": request["request_id"],
        "case_id": M3_CASE_ID,
        "classification": CLASSIFICATION,
        "contracts": {
            "preparation_audit_envelope": _artifact_receipt(
                handoff_dir,
                audit_dir / "preparation_audit_envelope.json",
            ),
            "semantic_review_basis": _artifact_receipt(
                handoff_dir,
                contracts_dir / "SOURCE_NOTES.md",
            ),
            "semantic_layer": _artifact_receipt(
                handoff_dir,
                contracts_dir / "monthly_pnl.semantic.json",
            ),
            "reporting_request": _artifact_receipt(
                handoff_dir,
                contracts_dir / "reporting_handoff_request.json",
            ),
            "statement_recipe": _artifact_receipt(
                handoff_dir,
                contracts_dir / "statement_render_recipe.json",
            ),
            "handoff_schema": _plugin_contract_receipt(
                clara_root,
                clara_root
                / "contracts"
                / "reporting_evidence_handoff_receipt.v1.schema.json",
            ),
            "semantic_schema": _plugin_contract_receipt(
                clara_root,
                clara_root
                / "modules"
                / "reporting-engine"
                / "catalog"
                / "semantic_layer.schema.json",
            ),
            "selection_manifest": _plugin_contract_receipt(
                clara_root,
                clara_root
                / "modules"
                / "reporting-engine"
                / "catalog"
                / "selection_manifest.json",
            ),
            "implementations": _implementation_receipts(clara_root),
        },
        "prepared_snapshot": {
            "dataset_contract_id": DATASET_CONTRACT_ID,
            "prepared_artifact": _artifact_receipt(
                handoff_dir,
                evidence_dir / "monthly_pnl.csv",
            ),
            "dataset_profile": _artifact_receipt(
                handoff_dir,
                handoff_dir / "dataset_profile.json",
            ),
            "profile_schema_version": profile["schema_version"],
            "snapshot_fingerprint": request["semantic_layer"][
                "origin_profile_fingerprint"
            ],
            "row_count": profile["row_count"],
            "numeric_cell_count": EXPECTED_CELL_COUNT,
            "address_set_sha256": address_set_sha256,
            "value_set_sha256": value_set_sha256,
        },
        "semantic": {
            "semantic_layer_id": SEMANTIC_LAYER_ID,
            "semantic_version": 1,
            "review_status": "model_reviewed",
            "validation": _artifact_receipt(
                handoff_dir,
                handoff_dir / "semantic_validation.json",
            ),
            "snapshot_attachment": _artifact_receipt(
                handoff_dir,
                handoff_dir / "snapshot_attachment.json",
            ),
            "validation_status": "contract_valid",
            "readiness": "ready_as_scoped_semantic_input",
            "compatibility_status": compatibility["status"],
            "origin_snapshot_matches": semantic_snapshot["is_origin_snapshot"],
            "analysis_id": ANALYSIS_ID,
            "policy_validity": "conditional",
            "capability_id": CAPABILITY_ID,
        },
        "render": dict(render_summary),
        "evidence": {
            "bundle": _artifact_receipt(
                handoff_dir,
                evidence_dir / "evidence-bundle.json",
            ),
            "bundle_schema_version": bundle_validation["schema_version"],
            "verified_artifact_count": bundle_validation["artifact_count"],
            "serialized_html_numeric_domain": SERIALIZED_HTML_NUMERIC_DOMAIN,
            "expected_cell_count": EXPECTED_CELL_COUNT,
            "verified_cell_count": EXPECTED_CELL_COUNT,
            "coverage_status": "exact",
            "missing_cell_count": 0,
            "extra_cell_count": 0,
            "duplicate_cell_count": 0,
            "address_set_sha256": address_set_sha256,
            "value_set_sha256": value_set_sha256,
            "serialized_html_cells": _artifact_receipt(
                handoff_dir,
                evidence_dir / "serialized_html_numeric_cells.csv",
            ),
            "publication_receipt": _artifact_receipt(
                handoff_dir,
                evidence_dir / "publication_receipt.json",
            ),
        },
        "gates": {
            "preparation": "passed",
            "reconciliation": "passed",
            "semantic_wiring": "verified",
            "render_transport": "verified",
            "serialized_html_cell_coverage": "verified",
            "evidence_bundle": "verified",
            "publication": "withheld",
        },
        "handoff_ready_for_review": True,
        "report_ready": False,
        "publication_status": "withheld",
        "limitations": [
            "The monthly phasing is synthetic and is not issuer actual monthly disclosure.",
            "Semantic review is model review, not human accounting review.",
            "Exact generic Decimal rendering is not proven because the current statement renderer uses binary float internally.",
            "The serialized HTML check does not prove computed browser visibility, and the Reporting Engine HTML is not an HTML-deck evidence ledger.",
            "Source authority, row lineage, interpretation, visual approval, and publication authorization remain unproven.",
            "The raw render manifest is validated for the current run but excluded from the portable determinism oracle because it records run-local paths.",
        ],
    }


def _validate_receipt_schema(
    *,
    clara_root: Path,
    receipt: Mapping[str, Any],
) -> None:
    schema_path = (
        clara_root / "contracts" / "reporting_evidence_handoff_receipt.v1.schema.json"
    )
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(receipt),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.absolute_path) or "<root>"
        raise ContractValidationError(
            f"handoff receipt schema error at {location}: {error.message}"
        )


def _validate_handoff_artifacts(
    *,
    clara_root: Path,
    case_path: Path,
    prepared_output_dir: Path,
    semantic_layer_path: Path,
    reporting_request_path: Path,
    statement_recipe_path: Path,
    handoff_dir: Path,
    verify_fresh_render: bool,
    require_stored_receipt: bool = True,
) -> dict[str, Any]:
    case_path = case_path.resolve()
    case_root = case_path.parent
    prepared_output_dir = prepared_output_dir.resolve()
    semantic_layer_path = _require_case_owned(
        semantic_layer_path,
        case_root,
        label="semantic layer",
    )
    reporting_request_path = _require_case_owned(
        reporting_request_path,
        case_root,
        label="reporting request",
    )
    statement_recipe_path = _require_case_owned(
        statement_recipe_path,
        case_root,
        label="statement recipe",
    )
    prepared_monthly_pnl = prepared_output_dir / "monthly_pnl.csv"
    envelope = _validate_m3_envelope(
        clara_root=clara_root,
        case_path=case_path,
        prepared_output_dir=prepared_output_dir,
    )
    request = _load_json(reporting_request_path)
    _validate_request(
        request=request,
        case_root=case_root,
        prepared_monthly_pnl=prepared_monthly_pnl,
        semantic_layer_path=semantic_layer_path,
        statement_recipe_path=statement_recipe_path,
    )
    source_notes_path = (
        case_root / request["semantic_layer"]["review_basis"]["relative_path"]
    ).resolve()

    required_files = {
        "audit/preparation_audit_envelope.json",
        "contracts/SOURCE_NOTES.md",
        "contracts/monthly_pnl.semantic.json",
        "contracts/reporting_handoff_request.json",
        "contracts/statement_render_recipe.json",
        "dataset_profile.json",
        "semantic_validation.json",
        "snapshot_attachment.json",
        "evidence/monthly_pnl.csv",
        "evidence/rendered_statement_values.csv",
        "evidence/serialized_html_numeric_cells.csv",
        "evidence/publication_receipt.json",
        "evidence/evidence-bundle.json",
        *(f"render/{relative}" for relative in EXPECTED_RENDER_FILES),
    }
    if require_stored_receipt:
        required_files.add("reporting_handoff.json")
    actual_files = {
        path.relative_to(handoff_dir).as_posix()
        for path in handoff_dir.rglob("*")
        if path.is_file()
    }
    if actual_files != required_files:
        raise ContractValidationError(
            "handoff output inventory drifted; "
            f"missing={sorted(required_files - actual_files)}, "
            f"extra={sorted(actual_files - required_files)}"
        )
    exact_copies = {
        source_notes_path: handoff_dir / "contracts" / "SOURCE_NOTES.md",
        semantic_layer_path: handoff_dir / "contracts" / "monthly_pnl.semantic.json",
        reporting_request_path: handoff_dir
        / "contracts"
        / "reporting_handoff_request.json",
        statement_recipe_path: handoff_dir
        / "contracts"
        / "statement_render_recipe.json",
        prepared_monthly_pnl: handoff_dir / "evidence" / "monthly_pnl.csv",
    }
    for source, copied in exact_copies.items():
        if source.read_bytes() != copied.read_bytes():
            raise ContractValidationError(
                f"handoff copy does not match source bytes: {copied.name}"
            )
    expected_envelope_bytes = (
        json.dumps(
            envelope,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if (
        handoff_dir / "audit" / "preparation_audit_envelope.json"
    ).read_bytes() != expected_envelope_bytes:
        raise ContractValidationError("handoff M3 envelope does not match fresh replay")
    if _find_artifact(envelope, "monthly_pnl")["sha256"] != file_sha256(
        handoff_dir / "evidence" / "monthly_pnl.csv"
    ):
        raise ContractValidationError("handoff prepared input is not the M3 artifact")

    profiler, semantics, _renderer, _evidence = _component_modules(clara_root)
    profile = _normalized_profile(
        profiler=profiler,
        monthly_pnl_path=handoff_dir / "evidence" / "monthly_pnl.csv",
    )
    stored_profile = _load_json(handoff_dir / "dataset_profile.json")
    if stored_profile != profile:
        raise ContractValidationError(
            "stored dataset profile does not match complete fresh profile"
        )
    layer, validation, attachment = _evaluate_semantics(
        clara_root=clara_root,
        semantic_layer_path=semantic_layer_path,
        request=request,
        profile=profile,
    )
    if _load_json(handoff_dir / "semantic_validation.json") != validation:
        raise ContractValidationError("stored semantic validation is stale")
    if _load_json(handoff_dir / "snapshot_attachment.json") != attachment:
        raise ContractValidationError("stored snapshot attachment is stale")
    if file_sha256(semantic_layer_path) != request["semantic_layer"]["sha256"]:
        raise ContractValidationError("semantic layer exact digest drifted")
    if (
        semantics.canonical_snapshot_fingerprint(profile)
        != request["semantic_layer"]["origin_profile_fingerprint"]
    ):
        raise ContractValidationError("profile fingerprint drifted")

    prepared_cells, row_metadata = _read_prepared_cells(
        handoff_dir / "evidence" / "monthly_pnl.csv",
        request=request,
    )
    recipe = _load_json(handoff_dir / "contracts" / "statement_render_recipe.json")
    row_keys, pairs = _validate_recipe(
        recipe=recipe,
        request=request,
        row_metadata=row_metadata,
    )
    render_manifest = _load_json(handoff_dir / "render" / "render_manifest.json")
    render_summary = _portable_render_summary(
        clara_root=clara_root,
        handoff_dir=handoff_dir,
        render_dir=handoff_dir / "render",
        render_manifest=render_manifest,
        expected_input_sha256=file_sha256(handoff_dir / "evidence" / "monthly_pnl.csv"),
        expected_role_bindings=request["render"]["role_bindings"],
    )
    rendered_cells = _read_rendered_cells(
        handoff_dir / "render" / "pnl_statement_table_chart_data.csv",
        recipe=recipe,
        row_keys=row_keys,
        pairs=pairs,
        row_metadata=row_metadata,
    )
    _validate_context_cells(
        handoff_dir / "render" / "pnl_statement_table_chart_context.json",
        recipe=recipe,
        row_keys=row_keys,
        pairs=pairs,
        prepared_cells=prepared_cells,
    )
    serialized_cells = _read_serialized_html_cells(
        handoff_dir / "render" / "pnl_statement_table.html",
        recipe=recipe,
        row_keys=row_keys,
        pairs=pairs,
    )
    expected_serialized_rows = _build_serialized_cell_rows(
        prepared_cells=prepared_cells,
        rendered_cells=rendered_cells,
        serialized_cells=serialized_cells,
        row_keys=row_keys,
        pairs=pairs,
        row_metadata=row_metadata,
    )
    stored_serialized_rows = _read_serialized_cell_rows(
        handoff_dir / "evidence" / "serialized_html_numeric_cells.csv"
    )
    if stored_serialized_rows != expected_serialized_rows:
        raise ContractValidationError(
            "serialized-cell ledger does not match current prepared/rendered/HTML cells"
        )
    if (handoff_dir / "evidence" / "rendered_statement_values.csv").read_bytes() != (
        handoff_dir / "render" / "pnl_statement_table_chart_data.csv"
    ).read_bytes():
        raise ContractValidationError(
            "sealed rendered values do not match Reporting Engine output"
        )
    address_set_sha256, value_set_sha256 = _coverage_digests(
        row_keys=row_keys,
        pairs=pairs,
        prepared_cells=prepared_cells,
    )

    expected_publication_receipt = _build_publication_receipt(
        case_id=M3_CASE_ID,
        prepared_receipt=_artifact_receipt(
            handoff_dir,
            handoff_dir / "evidence" / "monthly_pnl.csv",
        ),
        semantic_review_basis_receipt=_artifact_receipt(
            handoff_dir,
            handoff_dir / "contracts" / "SOURCE_NOTES.md",
        ),
        semantic_receipt=_artifact_receipt(
            handoff_dir,
            handoff_dir / "contracts" / "monthly_pnl.semantic.json",
        ),
        request_receipt=_artifact_receipt(
            handoff_dir,
            handoff_dir / "contracts" / "reporting_handoff_request.json",
        ),
        recipe_receipt=_artifact_receipt(
            handoff_dir,
            handoff_dir / "contracts" / "statement_render_recipe.json",
        ),
        implementation_receipts=_implementation_receipts(clara_root),
        render_summary=render_summary,
        serialized_cells_receipt=_artifact_receipt(
            handoff_dir,
            handoff_dir / "evidence" / "serialized_html_numeric_cells.csv",
        ),
        address_set_sha256=address_set_sha256,
        value_set_sha256=value_set_sha256,
    )
    if (
        _load_json(handoff_dir / "evidence" / "publication_receipt.json")
        != expected_publication_receipt
    ):
        raise ContractValidationError("portable publication receipt is stale")
    bundle_validation = _validate_bundle(
        clara_root=clara_root,
        bundle_path=handoff_dir / "evidence" / "evidence-bundle.json",
    )
    bundle_by_id = {
        artifact["id"]: artifact for artifact in bundle_validation["artifacts"]
    }
    expected_bundle_links = {
        "prepared-monthly-pnl": handoff_dir / "evidence" / "monthly_pnl.csv",
        "rendered-statement-values": handoff_dir
        / "evidence"
        / "rendered_statement_values.csv",
        "serialized-html-numeric-cells": handoff_dir
        / "evidence"
        / "serialized_html_numeric_cells.csv",
        "publication-receipt": handoff_dir / "evidence" / "publication_receipt.json",
    }
    for artifact_id, artifact_path in expected_bundle_links.items():
        if bundle_by_id[artifact_id]["sha256"] != file_sha256(artifact_path):
            raise ContractValidationError(
                f"evidence bundle does not seal {artifact_id}"
            )

    expected_receipt = _assemble_handoff_receipt(
        clara_root=clara_root,
        handoff_dir=handoff_dir,
        request=request,
        profile=profile,
        validation=validation,
        render_summary=render_summary,
        address_set_sha256=address_set_sha256,
        value_set_sha256=value_set_sha256,
        bundle_validation=bundle_validation,
    )
    _validate_receipt_schema(clara_root=clara_root, receipt=expected_receipt)
    if verify_fresh_render:
        _assert_fresh_render(
            clara_root=clara_root,
            handoff_dir=handoff_dir,
            profile=profile,
            role_bindings=request["render"]["role_bindings"],
            expected_render_summary=render_summary,
        )
    if layer["review"]["status"] != expected_receipt["semantic"]["review_status"]:
        raise ContractValidationError("semantic review status was promoted")
    if not require_stored_receipt:
        return expected_receipt
    stored_receipt = _load_json(handoff_dir / "reporting_handoff.json")
    _validate_receipt_schema(clara_root=clara_root, receipt=stored_receipt)
    if stored_receipt != expected_receipt:
        raise ContractValidationError("reporting handoff receipt is stale")
    return stored_receipt


def build_monthly_pnl_reporting_handoff(
    *,
    clara_root: Path,
    case_path: Path,
    prepared_output_dir: Path,
    semantic_layer_path: Path,
    statement_recipe_path: Path,
    output_dir: Path,
    reporting_request_path: Path | None = None,
) -> dict[str, Any]:
    """Build and independently validate one successful M4 handoff."""

    clara_root = clara_root.resolve()
    case_path = case_path.resolve()
    case_root = case_path.parent
    prepared_output_dir = prepared_output_dir.resolve()
    semantic_layer_path = _require_case_owned(
        semantic_layer_path,
        case_root,
        label="semantic layer",
    )
    statement_recipe_path = _require_case_owned(
        statement_recipe_path,
        case_root,
        label="statement recipe",
    )
    reporting_request_path = _require_case_owned(
        reporting_request_path or case_root / "reporting_handoff_request.json",
        case_root,
        label="reporting request",
    )
    prepared_monthly_pnl = prepared_output_dir / "monthly_pnl.csv"
    envelope = _validate_m3_envelope(
        clara_root=clara_root,
        case_path=case_path,
        prepared_output_dir=prepared_output_dir,
    )
    request = _load_json(reporting_request_path)
    _validate_request(
        request=request,
        case_root=case_root,
        prepared_monthly_pnl=prepared_monthly_pnl,
        semantic_layer_path=semantic_layer_path,
        statement_recipe_path=statement_recipe_path,
    )
    source_notes_path = (
        case_root / request["semantic_layer"]["review_basis"]["relative_path"]
    ).resolve()

    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ContractValidationError("handoff output directory must not already exist")
    audit_dir = output_dir / "audit"
    contracts_dir = output_dir / "contracts"
    evidence_dir = output_dir / "evidence"
    render_dir = output_dir / "render"
    for directory in (audit_dir, contracts_dir, evidence_dir):
        directory.mkdir(parents=True, exist_ok=False)

    _write_json(audit_dir / "preparation_audit_envelope.json", envelope)
    shutil.copyfile(
        source_notes_path,
        contracts_dir / "SOURCE_NOTES.md",
    )
    shutil.copyfile(
        semantic_layer_path,
        contracts_dir / "monthly_pnl.semantic.json",
    )
    shutil.copyfile(
        reporting_request_path,
        contracts_dir / "reporting_handoff_request.json",
    )
    shutil.copyfile(
        statement_recipe_path,
        contracts_dir / "statement_render_recipe.json",
    )
    shutil.copyfile(prepared_monthly_pnl, evidence_dir / "monthly_pnl.csv")

    profiler, semantics, _renderer, evidence = _component_modules(clara_root)
    profile = _normalized_profile(
        profiler=profiler,
        monthly_pnl_path=evidence_dir / "monthly_pnl.csv",
    )
    _write_json(output_dir / "dataset_profile.json", profile)
    _layer, validation, attachment = _evaluate_semantics(
        clara_root=clara_root,
        semantic_layer_path=semantic_layer_path,
        request=request,
        profile=profile,
    )
    if (
        semantics.canonical_snapshot_fingerprint(profile)
        != request["semantic_layer"]["origin_profile_fingerprint"]
    ):
        raise ContractValidationError("fresh profile fingerprint drifted")
    _write_json(output_dir / "semantic_validation.json", validation)
    _write_json(output_dir / "snapshot_attachment.json", attachment)

    prepared_cells, row_metadata = _read_prepared_cells(
        evidence_dir / "monthly_pnl.csv",
        request=request,
    )
    recipe = _load_json(contracts_dir / "statement_render_recipe.json")
    row_keys, pairs = _validate_recipe(
        recipe=recipe,
        request=request,
        row_metadata=row_metadata,
    )
    render_manifest = _render_once(
        clara_root=clara_root,
        input_file=evidence_dir / "monthly_pnl.csv",
        output_dir=render_dir,
        recipe_path=contracts_dir / "statement_render_recipe.json",
        profile=profile,
        role_bindings=request["render"]["role_bindings"],
    )
    render_summary = _portable_render_summary(
        clara_root=clara_root,
        handoff_dir=output_dir,
        render_dir=render_dir,
        render_manifest=render_manifest,
        expected_input_sha256=file_sha256(evidence_dir / "monthly_pnl.csv"),
        expected_role_bindings=request["render"]["role_bindings"],
    )
    rendered_cells = _read_rendered_cells(
        render_dir / "pnl_statement_table_chart_data.csv",
        recipe=recipe,
        row_keys=row_keys,
        pairs=pairs,
        row_metadata=row_metadata,
    )
    _validate_context_cells(
        render_dir / "pnl_statement_table_chart_context.json",
        recipe=recipe,
        row_keys=row_keys,
        pairs=pairs,
        prepared_cells=prepared_cells,
    )
    serialized_cells = _read_serialized_html_cells(
        render_dir / "pnl_statement_table.html",
        recipe=recipe,
        row_keys=row_keys,
        pairs=pairs,
    )
    serialized_rows = _build_serialized_cell_rows(
        prepared_cells=prepared_cells,
        rendered_cells=rendered_cells,
        serialized_cells=serialized_cells,
        row_keys=row_keys,
        pairs=pairs,
        row_metadata=row_metadata,
    )
    _write_csv(
        evidence_dir / "serialized_html_numeric_cells.csv",
        fieldnames=SERIALIZED_CELL_COLUMNS,
        rows=serialized_rows,
    )
    shutil.copyfile(
        render_dir / "pnl_statement_table_chart_data.csv",
        evidence_dir / "rendered_statement_values.csv",
    )
    address_set_sha256, value_set_sha256 = _coverage_digests(
        row_keys=row_keys,
        pairs=pairs,
        prepared_cells=prepared_cells,
    )
    publication_receipt = _build_publication_receipt(
        case_id=M3_CASE_ID,
        prepared_receipt=_artifact_receipt(
            output_dir,
            evidence_dir / "monthly_pnl.csv",
        ),
        semantic_review_basis_receipt=_artifact_receipt(
            output_dir,
            contracts_dir / "SOURCE_NOTES.md",
        ),
        semantic_receipt=_artifact_receipt(
            output_dir,
            contracts_dir / "monthly_pnl.semantic.json",
        ),
        request_receipt=_artifact_receipt(
            output_dir,
            contracts_dir / "reporting_handoff_request.json",
        ),
        recipe_receipt=_artifact_receipt(
            output_dir,
            contracts_dir / "statement_render_recipe.json",
        ),
        implementation_receipts=_implementation_receipts(clara_root),
        render_summary=render_summary,
        serialized_cells_receipt=_artifact_receipt(
            output_dir,
            evidence_dir / "serialized_html_numeric_cells.csv",
        ),
        address_set_sha256=address_set_sha256,
        value_set_sha256=value_set_sha256,
    )
    _write_json(evidence_dir / "publication_receipt.json", publication_receipt)
    bundle_path = _draft_evidence_bundle(evidence_dir)
    evidence.seal_evidence_bundle(bundle_path)
    _validate_bundle(
        clara_root=clara_root,
        bundle_path=bundle_path,
    )
    receipt = _validate_handoff_artifacts(
        clara_root=clara_root,
        case_path=case_path,
        prepared_output_dir=prepared_output_dir,
        semantic_layer_path=semantic_layer_path,
        reporting_request_path=reporting_request_path,
        statement_recipe_path=statement_recipe_path,
        handoff_dir=output_dir,
        verify_fresh_render=True,
        require_stored_receipt=False,
    )
    _write_json(output_dir / "reporting_handoff.json", receipt)
    return receipt


def validate_monthly_pnl_reporting_handoff(
    *,
    clara_root: Path,
    case_path: Path,
    prepared_output_dir: Path,
    semantic_layer_path: Path,
    statement_recipe_path: Path,
    handoff_dir: Path,
    reporting_request_path: Path | None = None,
    verify_fresh_render: bool = True,
) -> dict[str, Any]:
    """Recompute every M4 gate from current bytes and a fresh render."""

    case_path = case_path.resolve()
    return _validate_handoff_artifacts(
        clara_root=clara_root.resolve(),
        case_path=case_path,
        prepared_output_dir=prepared_output_dir.resolve(),
        semantic_layer_path=semantic_layer_path.resolve(),
        reporting_request_path=(
            reporting_request_path
            or case_path.parent / "reporting_handoff_request.json"
        ).resolve(),
        statement_recipe_path=statement_recipe_path.resolve(),
        handoff_dir=handoff_dir.resolve(),
        verify_fresh_render=verify_fresh_render,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Build or validate one frozen M4 reporting handoff."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "validate"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("case", type=Path)
        command_parser.add_argument("prepared_output_dir", type=Path)
        command_parser.add_argument("output_dir", type=Path)
        command_parser.add_argument("--semantic-layer", type=Path, required=True)
        command_parser.add_argument("--statement-recipe", type=Path, required=True)
        command_parser.add_argument("--reporting-request", type=Path)
        command_parser.add_argument(
            "--clara-root",
            type=Path,
            default=Path(__file__).resolve().parents[1],
        )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        kwargs = {
            "clara_root": args.clara_root,
            "case_path": args.case,
            "prepared_output_dir": args.prepared_output_dir,
            "semantic_layer_path": args.semantic_layer,
            "reporting_request_path": args.reporting_request,
            "statement_recipe_path": args.statement_recipe,
        }
        if args.command == "build":
            receipt = build_monthly_pnl_reporting_handoff(
                **kwargs,
                output_dir=args.output_dir,
            )
        else:
            receipt = validate_monthly_pnl_reporting_handoff(
                **kwargs,
                handoff_dir=args.output_dir,
            )
    except (
        ContractValidationError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info(
        "M4 reporting handoff: %s (%s)",
        receipt["handoff_id"],
        "ready for review" if receipt["handoff_ready_for_review"] else "blocked",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
