from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_png_examples_gallery as gallery

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
DEFAULT_STATIC_GALLERY_DIR = Path("static/shared/png-gallery")
DEFAULT_SOURCE_ROOTS = (
    Path("runs/png_examples"),
    Path("runs/source_inventory_gallery"),
)
GROUP_SOURCE_ALIASES = {
    "attributes": ("attributes",),
    "distribution": ("distribution",),
    "mix_cohort": ("mix_cohort",),
    "mix_comparison": (
        "mix_comparison",
        "mix_comparison_column_total",
        "mix_regular",
    ),
    "mix_current": ("mix_current", "mix_regular"),
    "mix_like_for_like": ("mix_like_for_like",),
    "period": ("period", "period_comparison"),
    "scatter": ("scatter", "scatter_bubble"),
    "set_overlap": ("set_overlap",),
    "variance": ("variance",),
}
SOURCE_EXTENSIONS = (".html", ".png")
FULL_DATA_SIDECAR_FILENAMES = {
    "distribution_canonical.csv",
    "mix_contribution_canonical.csv",
    "period_comparison_canonical.csv",
    "scatter_bubble_canonical.csv",
    "set_overlap_canonical.csv",
    "variance_results.csv",
}


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild the published static PNG gallery inventory from real run "
            "artifacts without rerendering the current static PNGs."
        )
    )
    parser.add_argument(
        "--gallery-dir",
        type=Path,
        default=DEFAULT_STATIC_GALLERY_DIR,
        help="Static png-gallery directory containing index.html and manifest.json.",
    )
    parser.add_argument(
        "--source-root",
        action="append",
        type=Path,
        default=[],
        help="Run artifact root to search; can be passed more than once.",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    return parser.parse_args(argv)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _label_parts(label: str) -> tuple[str, str]:
    if " / " not in label:
        raise ValueError(f"Gallery label must contain ' / ': {label}")
    group, stem = label.split(" / ", 1)
    if not group or not stem:
        raise ValueError(f"Gallery label must contain group and stem: {label}")
    return group, stem


def _source_aliases(group: str) -> tuple[str, ...]:
    return GROUP_SOURCE_ALIASES.get(group, (group,))


def _locate_source_artifact(
    label: str,
    source_roots: Sequence[Path],
) -> Path:
    group, stem = _label_parts(gallery._source_gallery_label(label))
    candidates: list[Path] = []
    for source_root in source_roots:
        for source_group in _source_aliases(group):
            for suffix in SOURCE_EXTENSIONS:
                path = source_root / source_group / f"{stem}{suffix}"
                if path.exists():
                    candidates.append(path.resolve())
    if not candidates:
        raise FileNotFoundError(f"No source artifact found for gallery label: {label}")
    return candidates[0]


def _copy_file(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def _is_full_data_sidecar(path: Path) -> bool:
    return path.name in FULL_DATA_SIDECAR_FILENAMES


def _find_json_value_after(text: str, marker: str, open_char: str) -> Any | None:
    marker_index = text.find(marker)
    if marker_index < 0:
        return None
    value_index = text.find(open_char, marker_index)
    if value_index < 0:
        return None
    try:
        value, _end = json.JSONDecoder().raw_decode(text[value_index:])
    except json.JSONDecodeError:
        return None
    return value


def _extract_plotly_chart_data(source: Path) -> dict[str, Any] | None:
    if source.suffix.lower() != ".html":
        return None
    text = source.read_text(encoding="utf-8", errors="replace")
    traces = _find_json_value_after(text, "Plotly.newPlot", "[")
    if not isinstance(traces, list):
        return None
    return {
        "data_kind": "plotly_traces",
        "trace_count": len(traces),
        "traces": traces,
    }


def _compact_context_chart_data(context_path: Path | None) -> dict[str, Any] | None:
    if context_path is None or not context_path.exists():
        return None
    try:
        context = _load_json(context_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return {
        "data_kind": "chart_context",
        "context_source": context_path.name,
        "context": context,
    }


def _write_compact_data_sidecar(
    *,
    source: Path,
    target: Path,
    label: str,
    skipped_source_data: Path,
    context_path: Path | None,
) -> Path:
    payload = _extract_plotly_chart_data(source)
    if payload is None:
        payload = _compact_context_chart_data(context_path)
    if payload is None:
        payload = {"data_kind": "source_artifact_only"}
    payload = {
        "schema_version": "1.0",
        "label": label,
        "source_artifact": source.name,
        "replaces_full_data_sidecar": skipped_source_data.name,
        **payload,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return target


def _sidecar_target_path(
    source_dir: Path,
    target_dir: Path,
    sidecar_path: Path,
) -> Path:
    resolved_sidecar = sidecar_path.resolve()
    try:
        relative = resolved_sidecar.relative_to(source_dir.resolve())
    except ValueError:
        relative = Path(resolved_sidecar.name)
    return target_dir / relative


def _published_item(
    original_source: Path,
    output_path: Path,
    label: str,
    static_root: Path,
) -> gallery.GalleryItem:
    group, _stem = _label_parts(label)
    source_dir = original_source.parent
    target_dir = static_root / group / source_dir.name
    temporary_item = gallery.GalleryItem(
        source_path=original_source,
        output_path=output_path,
        label=label,
        dimensions=None,
    )
    copied_source = _copy_file(original_source, target_dir / original_source.name)
    skipped_full_data_sidecar: Path | None = None
    copied_context_path: Path | None = None
    for sidecar in gallery._sidecar_links(temporary_item):
        if sidecar.label == "source":
            continue
        if sidecar.label == "data" and _is_full_data_sidecar(sidecar.path):
            skipped_full_data_sidecar = sidecar.path
            continue
        sidecar_target = _sidecar_target_path(source_dir, target_dir, sidecar.path)
        copied_sidecar = _copy_file(sidecar.path, sidecar_target)
        if sidecar.label == "context":
            copied_context_path = copied_sidecar
    if skipped_full_data_sidecar is not None:
        compact_data_path = copied_source.with_name(
            f"{copied_source.stem}_chart_data.json"
        )
        _write_compact_data_sidecar(
            source=original_source,
            target=compact_data_path,
            label=label,
            skipped_source_data=skipped_full_data_sidecar,
            context_path=copied_context_path,
        )
    return gallery.GalleryItem(
        source_path=copied_source,
        output_path=output_path,
        label=label,
        dimensions=None,
    )


def _clear_static_source_dirs(static_root: Path) -> None:
    for group in GROUP_SOURCE_ALIASES:
        path = static_root / group
        if path.exists():
            shutil.rmtree(path)


def _build_static_inventory(args: argparse.Namespace) -> int:
    gallery_dir = args.gallery_dir.resolve()
    static_root = gallery_dir.parent
    manifest_path = gallery_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    source_roots = [
        path.resolve() for path in (args.source_root or list(DEFAULT_SOURCE_ROOTS))
    ]

    _clear_static_source_dirs(static_root)
    items: list[gallery.GalleryItem] = []
    for payload in manifest.get("items") or []:
        if not isinstance(payload, dict):
            continue
        label = str(payload.get("label") or "")
        output = str(payload.get("output") or "")
        output_path = gallery_dir / output
        if not output_path.exists():
            raise FileNotFoundError(f"Missing static gallery PNG: {output_path}")
        original_source = _locate_source_artifact(label, source_roots)
        items.append(_published_item(original_source, output_path, label, static_root))

    items = gallery._sort_gallery_items(items)
    stats = {item.output_path: gallery._image_stats(item.output_path) for item in items}
    (gallery_dir / "index.html").write_text(
        gallery._build_index(items, stats, gallery_dir),
        encoding="utf-8",
    )
    (gallery_dir / "manifest.json").write_text(
        json.dumps(gallery._build_manifest(items, stats, gallery_dir), indent=2),
        encoding="utf-8",
    )
    LOGGER.info("Wrote artifact-ready static gallery inventory: %s", gallery_dir)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(message)s",
    )
    return _build_static_inventory(args)


if __name__ == "__main__":
    raise SystemExit(main())
