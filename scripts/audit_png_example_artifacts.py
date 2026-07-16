from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "ArtifactAuditRow",
    "audit_png_example_artifacts",
    "classify_current_export",
    "classify_png_residue",
    "main",
]

CHART_AUDIT_NAMES = {
    "distribution_audit.json",
    "mix_contribution_audit.json",
    "period_comparison_audit.json",
    "scatter_bubble_audit.json",
    "set_overlap_audit.json",
    "variance_audit.json",
}


@dataclass(frozen=True)
class ArtifactAuditRow:
    plugin_run: str
    chart: str
    artifact: str
    current_export_class: str
    png_residue: str
    renderer: str
    status: str
    capability_id: str
    source_reference: str
    audit_path: str
    source_artifact_exists: bool
    source_artifact_mtime: str
    sibling_png_exists: bool
    sibling_png_mtime: str
    gallery_png_exists: bool
    gallery_png_mtime: str
    plotly_export_error: str
    screenshot_error: str


@dataclass(frozen=True)
class _RawArtifactRecord:
    plugin_run: str
    chart: str
    artifact: str
    renderer: str
    status: str
    plotly_export_error: str
    screenshot_error: str
    audit_path: Path


@dataclass(frozen=True)
class _ManifestRecord:
    capability_id: str = ""
    source_reference: str = ""


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Classify plugin example artifacts as current PNG exports, stale "
            "PNGs, or HTML-only failures."
        )
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("runs/png_examples"),
        help="Root containing plugin example run folders.",
    )
    parser.add_argument(
        "--gallery-dir",
        type=Path,
        default=Path("runs/png_examples/png-gallery"),
        help="Existing review gallery directory to compare against.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("runs/png_examples/png_artifact_audit.json"),
        help="JSON report path.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("runs/png_examples/png_artifact_audit.csv"),
        help="CSV report path.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("runs/png_examples/png_artifact_audit.md"),
        help="Markdown summary path.",
    )
    return parser.parse_args(argv)


def classify_current_export(artifact: str, renderer: str, status: str) -> str:
    """Classify the current audited export using mechanical file metadata."""

    suffix = Path(artifact).suffix.lower()
    normalized_renderer = renderer.lower()
    normalized_status = status.lower()
    if suffix == ".png":
        if normalized_renderer.startswith("legacy_plotly"):
            return "legacy_plotly_png"
        return "native_plugin_png"
    if suffix == ".html" and (
        normalized_renderer.endswith("html_only")
        or normalized_renderer == "plotly_html"
        or normalized_status == "written_html_only"
    ):
        return "failed_html_only_output"
    if suffix == ".html":
        return "html_artifact"
    return "unknown_artifact"


def classify_png_residue(
    current_artifact: str,
    *,
    sibling_png_exists: bool,
    gallery_png_exists: bool,
) -> str:
    """Report PNGs that exist but are not the current audited artifact."""

    if Path(current_artifact).suffix.lower() == ".png":
        return "current_source_png"
    if sibling_png_exists and gallery_png_exists:
        return "stale_source_png_and_gallery_png"
    if sibling_png_exists:
        return "stale_source_png"
    if gallery_png_exists:
        return "gallery_png_without_current_source_png"
    return "no_png"


def audit_png_example_artifacts(
    source_root: Path,
    gallery_dir: Path,
) -> list[ArtifactAuditRow]:
    source_root = source_root.resolve()
    gallery_dir = gallery_dir.resolve()
    rows: list[ArtifactAuditRow] = []
    for audit_path in sorted(_iter_chart_audits(source_root)):
        run_dir = audit_path.parent
        manifest_records = _manifest_records(run_dir)
        for record in _raw_artifact_records(audit_path):
            artifact_path = run_dir / record.artifact
            sibling_png = artifact_path.with_suffix(".png")
            gallery_png = gallery_dir / _gallery_output_name(source_root, artifact_path)
            manifest_record = manifest_records.get(
                record.artifact
            ) or manifest_records.get(sibling_png.name)
            current_export_class = classify_current_export(
                record.artifact,
                record.renderer,
                record.status,
            )
            png_residue = classify_png_residue(
                record.artifact,
                sibling_png_exists=sibling_png.exists(),
                gallery_png_exists=gallery_png.exists(),
            )
            rows.append(
                ArtifactAuditRow(
                    plugin_run=record.plugin_run,
                    chart=record.chart,
                    artifact=record.artifact,
                    current_export_class=current_export_class,
                    png_residue=png_residue,
                    renderer=record.renderer,
                    status=record.status,
                    capability_id=(
                        manifest_record.capability_id if manifest_record else ""
                    ),
                    source_reference=(
                        manifest_record.source_reference if manifest_record else ""
                    ),
                    audit_path=str(audit_path.relative_to(source_root.parent)),
                    source_artifact_exists=artifact_path.exists(),
                    source_artifact_mtime=_mtime(artifact_path),
                    sibling_png_exists=sibling_png.exists(),
                    sibling_png_mtime=_mtime(sibling_png),
                    gallery_png_exists=gallery_png.exists(),
                    gallery_png_mtime=_mtime(gallery_png),
                    plotly_export_error=record.plotly_export_error,
                    screenshot_error=record.screenshot_error,
                )
            )
    return rows


def _iter_chart_audits(source_root: Path) -> Iterable[Path]:
    for audit_path in source_root.rglob("*_audit.json"):
        if (
            audit_path.name in CHART_AUDIT_NAMES
            and "source_pack" not in audit_path.parts
        ):
            yield audit_path


def _raw_artifact_records(audit_path: Path) -> list[_RawArtifactRecord]:
    payload = _load_json(audit_path)
    plugin_run = audit_path.parent.name
    records: list[_RawArtifactRecord] = []
    seen: set[tuple[str, str]] = set()

    def add(
        *,
        chart: str,
        artifact: str,
        renderer: str = "",
        status: str = "",
        plotly_export_error: str = "",
        screenshot_error: str = "",
    ) -> None:
        if not artifact or Path(artifact).suffix.lower() not in {".png", ".html"}:
            return
        key = (artifact, renderer)
        if key in seen:
            return
        seen.add(key)
        records.append(
            _RawArtifactRecord(
                plugin_run=plugin_run,
                chart=chart or Path(artifact).stem,
                artifact=artifact,
                renderer=renderer,
                status=status,
                plotly_export_error=plotly_export_error,
                screenshot_error=screenshot_error,
                audit_path=audit_path,
            )
        )

    chart_audits = payload.get("legacy_runtime", {}).get("chart_audits")
    if isinstance(chart_audits, dict):
        for chart_name, chart_payload in chart_audits.items():
            if isinstance(chart_payload, dict):
                _add_exports_from_chart_payload(add, chart_name, chart_payload)
    elif isinstance(chart_audits, list):
        for chart_payload in chart_audits:
            if isinstance(chart_payload, dict):
                chart_name = _str_value(chart_payload.get("chart"))
                _add_exports_from_chart_payload(add, chart_name, chart_payload)

    charts = payload.get("charts")
    if isinstance(charts, dict):
        for chart_name, chart_payload in charts.items():
            if not isinstance(chart_payload, dict):
                continue
            _add_exports_from_chart_payload(add, str(chart_name), chart_payload)
            for artifact in chart_payload.get("artifacts", []):
                add(
                    chart=str(chart_name),
                    artifact=_str_value(artifact),
                    renderer=_str_value(chart_payload.get("renderer")),
                    status=_str_value(chart_payload.get("status")),
                    plotly_export_error=_str_value(chart_payload.get("error")),
                )
    elif isinstance(charts, list):
        for chart_payload in charts:
            if isinstance(chart_payload, dict):
                chart_name = _str_value(chart_payload.get("chart"))
                _add_exports_from_chart_payload(add, chart_name, chart_payload)

    # Some audit schemas, notably variance, store renderer rows deeper in the tree.
    for item in _walk_dicts(payload):
        artifact = _str_value(item.get("artifact"))
        renderer = _str_value(item.get("renderer"))
        if artifact and renderer:
            add(
                chart=_str_value(item.get("chart")) or Path(artifact).stem,
                artifact=artifact,
                renderer=renderer,
                status=_str_value(item.get("status")),
                plotly_export_error=_str_value(item.get("plotly_export_error")),
                screenshot_error=_str_value(item.get("screenshot_error")),
            )

    return records


def _add_exports_from_chart_payload(
    add: Any,
    chart_name: str,
    chart_payload: dict[str, Any],
) -> None:
    for export in chart_payload.get("exports", []):
        if not isinstance(export, dict):
            continue
        add(
            chart=chart_name or _str_value(chart_payload.get("chart")),
            artifact=_str_value(export.get("artifact")),
            renderer=_str_value(export.get("renderer")),
            status=_str_value(chart_payload.get("status")),
            plotly_export_error=_str_value(export.get("plotly_export_error")),
            screenshot_error=_str_value(export.get("screenshot_error")),
        )


def _manifest_records(run_dir: Path) -> dict[str, _ManifestRecord]:
    records: dict[str, _ManifestRecord] = {}
    for manifest_path in (run_dir / "source_pack" / "manifest.json",):
        if not manifest_path.exists():
            continue
        payload = _load_json(manifest_path)
        for item in payload.get("artifacts", []):
            if not isinstance(item, dict):
                continue
            path = _str_value(
                item.get("path") or item.get("source_path") or item.get("pack_path")
            )
            if not path or Path(path).suffix.lower() not in {".png", ".html"}:
                continue
            source_reference = _str_value(item.get("artifact_id"))
            if not source_reference:
                source_reference = Path(path).stem
            records[Path(path).name] = _ManifestRecord(
                capability_id=_str_value(item.get("capability_id")),
                source_reference=source_reference,
            )
    return records


def _gallery_output_name(source_root: Path, source_path: Path) -> str:
    relative = source_path.resolve().relative_to(source_root.resolve())
    parent = "__".join(relative.parent.parts)
    return f"{parent}__{source_path.stem}.png" if parent else f"{source_path.stem}.png"


def _mtime(path: Path) -> str:
    if not path.exists():
        return ""
    return str(int(path.stat().st_mtime))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _str_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _write_json(rows: Sequence[ArtifactAuditRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": _summary(rows),
        "rows": [asdict(row) for row in rows],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(rows: Sequence[ArtifactAuditRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(ArtifactAuditRow.__dataclass_fields__)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _write_markdown(rows: Sequence[ArtifactAuditRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = _summary(rows)
    lines = [
        "# PNG Artifact Audit",
        "",
        "This is a mechanical comparison of current run audit records, source "
        "artifacts, sibling PNGs, and review-gallery PNGs.",
        "",
        "## Current Export Class",
        "",
    ]
    for key, value in summary["current_export_class"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## PNG Residue", ""])
    for key, value in summary["png_residue"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## HTML-Only Failures With Existing PNGs",
            "",
            "| plugin_run | chart | current artifact | png residue | renderer |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        if row.current_export_class != "failed_html_only_output":
            continue
        if row.png_residue == "no_png":
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    row.plugin_run,
                    row.chart,
                    row.artifact,
                    row.png_residue,
                    row.renderer,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Failed HTML-Only Outputs Without Any PNG",
            "",
            "| plugin_run | chart | current artifact | renderer |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        if (
            row.current_export_class == "failed_html_only_output"
            and row.png_residue == "no_png"
        ):
            lines.append(
                "| "
                + " | ".join([row.plugin_run, row.chart, row.artifact, row.renderer])
                + " |"
            )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _summary(rows: Sequence[ArtifactAuditRow]) -> dict[str, dict[str, int]]:
    return {
        "current_export_class": dict(
            sorted(Counter(row.current_export_class for row in rows).items())
        ),
        "png_residue": dict(sorted(Counter(row.png_residue for row in rows).items())),
        "renderer": dict(sorted(Counter(row.renderer for row in rows).items())),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = audit_png_example_artifacts(args.source_root, args.gallery_dir)
    _write_json(rows, args.output_json)
    _write_csv(rows, args.output_csv)
    _write_markdown(rows, args.output_md)
    summary = _summary(rows)
    print(json.dumps(summary, indent=2))
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_csv}")
    print(f"Wrote {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
