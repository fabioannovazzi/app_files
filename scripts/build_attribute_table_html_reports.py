from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

import polars as pl
from polars.exceptions import PolarsError

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.attribute_table_templates import (  # noqa: E402
    ATTRIBUTE_TABLE_DIRNAME,
    build_attribute_tables_from_package,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)

MOJIBAKE_MARKERS = ("\u00c3", "\u00c2", "\u00e2")
TABLE_LINKS = (
    ("attribute_bundle_comparison_table.html", "Attribute bundle comparison"),
    ("attribute_bridge_table.html", "Winner/emerging bridge"),
    ("rank_weighted_visibility_table.html", "Rank-weighted visibility"),
    ("product_signal_evidence_table.html", "Product signal evidence"),
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        df = pl.read_csv(path, infer_schema_length=0)
    except PolarsError:
        with path.open(encoding="utf-8", newline="") as handle:
            return [
                {key: _safe_text(value) for key, value in row.items()}
                for row in csv.DictReader(handle)
            ]
    return [
        {key: _safe_text(value) for key, value in row.items()}
        for row in df.iter_rows(named=True)
    ]


def _safe_text(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"none", "null", "nan"}:
        return ""
    return _repair_display_text(text)


def _repair_display_text(text: str) -> str:
    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text
    return unicodedata.normalize("NFC", repaired)


def _display_label(value: object) -> str:
    return _safe_text(value).replace("_", " ").title()


def _slug_for_package(package_dir: Path, summary: Mapping[str, Any]) -> str:
    category = _safe_text(summary.get("category_key")) or package_dir.parent.name
    retailer = _safe_text(summary.get("retailer")) or package_dir.name
    return f"{category}_{retailer}".replace("/", "_")


def _copy_attribute_tables(package_dir: Path, output_dir: Path) -> None:
    table_dir = package_dir / ATTRIBUTE_TABLE_DIRNAME
    build_attribute_tables_from_package(package_dir)
    target = output_dir / ATTRIBUTE_TABLE_DIRNAME
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(table_dir, target)


def _normalize_key(value: object | None) -> str:
    return " ".join(_safe_text(value).casefold().split())


def _cli_image_dir(package_dir: Path, summary: Mapping[str, Any]) -> Path:
    retailer = _safe_text(summary.get("retailer")) or package_dir.name
    category = _safe_text(summary.get("category_key")) or package_dir.parent.name
    return Path("data/pdp/cli") / f"{retailer}_{category}" / "images"


def _product_image_lookup(
    package_dir: Path,
    summary: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    cli_images = _cli_image_dir(package_dir, summary)
    for file_name in ("top_seller_products.csv", "recent_products.csv"):
        for row in _read_rows(package_dir / file_name):
            product_key = _normalize_key(row.get("product_name"))
            if not product_key:
                continue
            entry = lookup.setdefault(product_key, {})
            for key in (
                "parent_product_id",
                "pack_image_file",
                "pack_image_path",
                "local_image_path",
                "hero_image_url",
            ):
                if not entry.get(key) and _safe_text(row.get(key)):
                    entry[key] = _safe_text(row.get(key))
            parent_id = entry.get("parent_product_id")
            if parent_id and not entry.get("cli_image_path") and cli_images.exists():
                for candidate in sorted(cli_images.glob(f"{parent_id}*")):
                    if candidate.is_file():
                        entry["cli_image_path"] = str(candidate)
                        break
    return lookup


def _product_image_source(
    package_dir: Path,
    row: Mapping[str, str],
    product_lookup: Mapping[str, Mapping[str, str]],
) -> Path | None:
    image_file = _safe_text(row.get("image_file"))
    if image_file:
        source = package_dir / image_file
        if source.exists() and source.is_file():
            return source
    product_key = _normalize_key(row.get("product"))
    entry = product_lookup.get(product_key, {})
    for key in (
        "pack_image_file",
        "pack_image_path",
        "local_image_path",
        "cli_image_path",
    ):
        value = _safe_text(entry.get(key))
        if not value:
            continue
        source = package_dir / value if key == "pack_image_file" else Path(value)
        if source.exists() and source.is_file():
            return source
    return None


def _copy_product_images(
    package_dir: Path,
    output_dir: Path,
    product_rows: Sequence[Mapping[str, str]],
    product_lookup: Mapping[str, Mapping[str, str]],
) -> dict[str, str]:
    image_map: dict[str, str] = {}
    image_dir = output_dir / "images"
    for row in product_rows:
        source = _product_image_source(package_dir, row, product_lookup)
        if source is None:
            continue
        image_dir.mkdir(parents=True, exist_ok=True)
        target = image_dir / source.name
        shutil.copy2(source, target)
        image_ref = f"images/{target.name}"
        image_file = _safe_text(row.get("image_file"))
        if image_file:
            image_map[image_file] = image_ref
        product_key = _normalize_key(row.get("product"))
        if product_key:
            image_map[f"product:{product_key}"] = image_ref
    return image_map


def _number(value: object) -> float | None:
    text = _safe_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_rate(value: object) -> str:
    numeric = _number(value)
    if numeric is None:
        return ""
    return f"{numeric * 100:.1f}%"


def _format_delta_pp(value: object) -> str:
    numeric = _number(value)
    if numeric is None:
        return ""
    sign = "+" if numeric > 0 else ""
    return f"{sign}{numeric * 100:.1f} pp"


def _sort_review_rows(rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    def score(row: Mapping[str, str]) -> float:
        return _number(row.get("experience_signal_score")) or 0.0

    return sorted((dict(row) for row in rows), key=score, reverse=True)


def _review_display_rows(rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    display_rows: list[dict[str, str]] = []
    for row in _sort_review_rows(rows)[:8]:
        display_rows.append(
            {
                "Theme": _safe_text(row.get("theme_label")),
                "Comparison": _safe_text(row.get("comparison_type")).replace("_", " "),
                "Signal": _safe_text(row.get("experience_signal_class")).replace(
                    "_", " "
                ),
                "Focus mention": _format_rate(row.get("focus_product_mention_rate")),
                "Baseline mention": _format_rate(
                    row.get("baseline_product_mention_rate")
                ),
                "Positive delta": _format_delta_pp(
                    row.get("positive_review_rate_delta")
                ),
                "Negative delta": _format_delta_pp(
                    row.get("negative_review_rate_delta")
                ),
                "Read": _safe_text(row.get("experience_signal_summary")),
            }
        )
    return display_rows


def _escape(value: object) -> str:
    return html.escape(_safe_text(value), quote=True)


def _render_table(
    rows: Sequence[Mapping[str, str]],
    columns: Sequence[str],
    *,
    max_rows: int,
    labels: Mapping[str, str] | None = None,
    numeric_columns: set[str] | None = None,
    strong_columns: set[str] | None = None,
) -> str:
    visible = [row for row in rows[:max_rows]]
    if not visible:
        return '<p class="empty">No rows surfaced for this table.</p>'
    labels = labels or {}
    numeric_columns = numeric_columns or set()
    strong_columns = strong_columns or set()
    header_parts = []
    for column in columns:
        header_class = "num" if column in numeric_columns else ""
        label = _escape(labels.get(column) or _display_label(column))
        header_parts.append(f'<th class="{header_class}">{label}</th>')
    header = "".join(header_parts)
    body_rows = []
    for row in visible:
        cell_parts = []
        for column in columns:
            cell_class = " ".join(
                _cell_classes(column, numeric_columns, strong_columns)
            )
            value = _escape(row.get(column))
            cell_parts.append(f'<td class="{cell_class}">{value}</td>')
        cells = "".join(cell_parts)
        body_rows.append(f"<tr>{cells}</tr>")
    if len(rows) > max_rows:
        body_rows.append(
            f'<tr class="more"><td colspan="{len(columns)}">'
            f"Compact view: {max_rows} of {len(rows)} rows. "
            "Full generated table linked below.</td></tr>"
        )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _cell_classes(
    column: str,
    numeric_columns: set[str],
    strong_columns: set[str],
) -> list[str]:
    classes: list[str] = []
    if column in numeric_columns:
        classes.append("num")
    if column in strong_columns:
        classes.append("strong")
    return classes


def _filter_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    column: str,
    value: str,
) -> list[dict[str, str]]:
    return [dict(row) for row in rows if _safe_text(row.get(column)) == value]


def _first(rows: Sequence[Mapping[str, str]]) -> Mapping[str, str] | None:
    return rows[0] if rows else None


def _bundle_sentence(row: Mapping[str, str] | None, *, fallback: str) -> str:
    if not row:
        return fallback
    ratio = _safe_text(row.get("index"))
    ratio_clause = f" and {ratio}" if ratio else ""
    focus = _safe_text(row.get("focus_share"))
    baseline = _safe_text(row.get("baseline_share"))
    prevalence = f"{focus} vs {baseline}" if focus or baseline else ""
    return (
        f"The leading row is <strong>{_escape(row.get('signal_bundle'))}</strong>: "
        f"{_escape(prevalence)}, {_escape(row.get('delta'))}{ratio_clause}, "
        f"across {_escape(row.get('focus_n'))} products and "
        f"{_escape(row.get('brands'))} brands."
    )


def _render_product_cards(
    rows: Sequence[Mapping[str, str]],
    image_map: Mapping[str, str],
    *,
    max_cards: int = 6,
) -> str:
    def image_src(row: Mapping[str, str]) -> str | None:
        image_file = _safe_text(row.get("image_file"))
        product_key = _normalize_key(row.get("product"))
        return image_map.get(image_file) or image_map.get(f"product:{product_key}")

    sorted_rows = sorted(
        enumerate(rows),
        key=lambda item: (image_src(item[1]) is None, item[0]),
    )
    image_rows = [item for item in sorted_rows if image_src(item[1]) is not None]
    card_rows = image_rows or sorted_rows
    cards: list[str] = []
    for _index, row in card_rows[:max_cards]:
        current_image_src = image_src(row)
        image_html = (
            f'<img src="{_escape(current_image_src)}" alt="{_escape(row.get("product"))}">'
            if current_image_src
            else '<div class="image-placeholder"></div>'
        )
        cards.append(
            '<figure class="product-card">'
            f"{image_html}"
            "<figcaption>"
            f"<strong>{_escape(row.get('brand'))}</strong><br>"
            f"{_escape(row.get('product'))}"
            f"<span>{_escape(row.get('rank'))} - {_escape(row.get('matched_signal'))}</span>"
            "</figcaption>"
            "</figure>"
        )
    if not cards:
        return '<p class="empty">No product examples surfaced for this package.</p>'
    return f"<div class=\"products\">{''.join(cards)}</div>"


def _render_links() -> str:
    links = [
        f'<a href="{ATTRIBUTE_TABLE_DIRNAME}/{_escape(filename)}">{_escape(label)}</a>'
        for filename, label in TABLE_LINKS
    ]
    return '<p class="links">' + "".join(links) + "</p>"


def _bridge_summary(rows: Sequence[Mapping[str, str]]) -> str:
    if not rows:
        return "No bridge rows surfaced between current winners and emerging signals."
    bridge_count = sum(
        1 for row in rows if _safe_text(row.get("alignment")) == "Bridge"
    )
    winning_only = sum(
        1 for row in rows if _safe_text(row.get("alignment")) == "Winning-now only"
    )
    emerging_only = sum(
        1 for row in rows if _safe_text(row.get("alignment")) == "Emerging only"
    )
    return (
        f"The bridge table surfaces {bridge_count} shared bundle rows, "
        f"{winning_only} winner-only rows, and {emerging_only} emerging-only rows."
    )


def _review_summary(rows: Sequence[Mapping[str, str]]) -> str:
    top = _first(_sort_review_rows(rows))
    if not top:
        return "No review-theme rows surfaced for this package."
    signal_class = _safe_text(top.get("experience_signal_class")).replace("_", " ")
    return (
        f"The strongest review-visible row is {_escape(top.get('theme_label'))}: "
        f"{signal_class}, with {_format_delta_pp(top.get('positive_review_rate_delta'))} "
        "positive-review delta and "
        f"{_format_delta_pp(top.get('negative_review_rate_delta'))} negative-review delta."
    )


def _visibility_summary(rows: Sequence[Mapping[str, str]]) -> str:
    top = _first(rows)
    if not top:
        return "No rank-weighted visibility rows surfaced for this package."
    return (
        f"The first shelf lane is <strong>{_escape(top.get('lane'))}</strong>, "
        f"with {_escape(top.get('gross_weight'))} gross visibility and "
        f"{_escape(top.get('incremental'))} incremental visibility."
    )


def _visual_summary(
    product_rows: Sequence[Mapping[str, str]], image_map: Mapping[str, str]
) -> str:
    image_count = 0
    for row in product_rows:
        product_key = _normalize_key(row.get("product"))
        if image_map.get(_safe_text(row.get("image_file"))) or image_map.get(
            f"product:{product_key}"
        ):
            image_count += 1
    return (
        f"{image_count} of {len(product_rows)} surfaced product-evidence rows have "
        "a copied image in this HTML report."
    )


def _markdown_report(
    *,
    title: str,
    summary: Mapping[str, Any],
    winning: Sequence[Mapping[str, str]],
    emerging: Sequence[Mapping[str, str]],
    review_rows: Sequence[Mapping[str, str]],
) -> str:
    winner = _first(winning)
    emerging_row = _first(emerging)
    review_row = _first(_sort_review_rows(review_rows))
    lines = [
        f"# {title}",
        "",
        f"- Products: {_safe_text(summary.get('listing_products'))}",
        f"- Top sellers: {_safe_text(summary.get('top_seller_products'))}",
        f"- Recent products: {_safe_text(summary.get('recent_products'))}",
        f"- Review-theme rows: {_safe_text(summary.get('review_theme_cohort_comparison_rows'))}",
        "",
        "## Winning now",
        _safe_text(winner.get("signal_bundle")) if winner else "No rows surfaced.",
        "",
        "## Emerging signal",
        (
            _safe_text(emerging_row.get("signal_bundle"))
            if emerging_row
            else "No rows surfaced."
        ),
        "",
        "## Review-visible layer",
        (
            _safe_text(review_row.get("experience_signal_summary"))
            if review_row
            else "No review-theme rows surfaced."
        ),
    ]
    return "\n".join(lines) + "\n"


def _render_html_report(package_dir: Path, output_dir: Path) -> dict[str, Any]:
    summary = _read_json(package_dir / "summary.json")
    package_integrity = _read_json(package_dir / "package_integrity.json")
    package_warnings = _read_json(package_dir / "package_warnings.json")
    _copy_attribute_tables(package_dir, output_dir)

    table_dir = package_dir / ATTRIBUTE_TABLE_DIRNAME
    bundle_rows = _read_rows(table_dir / "attribute_bundle_comparison_table.csv")
    bridge_rows = _read_rows(table_dir / "attribute_bridge_table.csv")
    visibility_rows = _read_rows(table_dir / "rank_weighted_visibility_table.csv")
    product_rows = _read_rows(table_dir / "product_signal_evidence_table.csv")
    review_rows = _read_rows(package_dir / "review_theme_cohort_comparison.csv")
    product_lookup = _product_image_lookup(package_dir, summary)
    image_map = _copy_product_images(
        package_dir, output_dir, product_rows, product_lookup
    )

    winning = _filter_rows(bundle_rows, column="layer", value="Winning now")
    emerging = _filter_rows(bundle_rows, column="layer", value="Emerging signal")
    review_display = _review_display_rows(review_rows)

    retailer_label = _safe_text(summary.get("retailer_label")) or _display_label(
        package_dir.name
    )
    category_label = _safe_text(summary.get("category_label")) or _display_label(
        package_dir.parent.name
    )
    category_display = _display_label(category_label)
    title = f"{retailer_label} {category_display} Attribute Report"
    integrity_status = _safe_text(package_integrity.get("status")) or _safe_text(
        summary.get("package_integrity", {}).get("status")
    )
    warning_status = _safe_text(package_warnings.get("status")) or _safe_text(
        summary.get("package_warning_status")
    )

    bundle_columns = [
        "signal_bundle",
        "focus_n",
        "baseline_n",
        "focus_share",
        "baseline_share",
        "delta",
        "index",
        "brands",
    ]
    bridge_columns = [
        "signal_bundle",
        "alignment",
        "current_share",
        "current_delta",
        "current_index",
        "emerging_share",
        "emerging_delta",
        "emerging_index",
        "current_brands",
        "recent_brands",
    ]
    visibility_columns = [
        "rank",
        "lane",
        "gross_weight",
        "incremental",
        "cumulative",
        "skus",
        "brands",
        "robustness",
    ]
    product_columns = [
        "cohort",
        "rank",
        "brand",
        "product",
        "matched_signal",
        "rating",
        "reviews",
        "caveat",
    ]
    review_columns = [
        "Theme",
        "Comparison",
        "Signal",
        "Focus mention",
        "Baseline mention",
        "Positive delta",
        "Negative delta",
        "Read",
    ]
    numeric_columns = {
        "focus_n",
        "baseline_n",
        "focus_share",
        "baseline_share",
        "delta",
        "index",
        "brands",
        "current_share",
        "current_delta",
        "current_index",
        "emerging_share",
        "emerging_delta",
        "emerging_index",
        "current_brands",
        "recent_brands",
        "rank",
        "gross_weight",
        "incremental",
        "cumulative",
        "skus",
        "rating",
        "reviews",
        "Focus mention",
        "Baseline mention",
        "Positive delta",
        "Negative delta",
    }
    strong_columns = {
        "focus_share",
        "delta",
        "current_delta",
        "emerging_delta",
        "incremental",
        "Positive delta",
        "Negative delta",
    }
    column_labels = {
        "signal_bundle": "Signal bundle",
        "focus_n": "Focus n",
        "baseline_n": "Baseline n",
        "focus_share": "Focus",
        "baseline_share": "Baseline",
        "current_share": "Current",
        "current_delta": "Current delta",
        "current_index": "Current index",
        "emerging_share": "Emerging",
        "emerging_delta": "Emerging delta",
        "emerging_index": "Emerging index",
        "current_brands": "Current brands",
        "recent_brands": "Recent brands",
        "gross_weight": "Gross",
        "incremental": "Incremental",
        "cumulative": "Cumulative",
        "skus": "SKUs",
    }

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)}</title>
  <style>
    :root {{ --ink:#202124; --muted:#5f6368; --rule:#d7dbe0; --soft:#fff; --accent:#1e6f68; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:#fff; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    main {{ width:min(1180px,calc(100vw - 40px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ border-bottom:2px solid var(--ink); padding-bottom:18px; margin-bottom:22px; }}
    h1 {{ font-size:30px; line-height:1.12; margin:0 0 8px; letter-spacing:0; }}
    h2 {{ font-size:19px; line-height:1.2; margin:28px 0 10px; letter-spacing:0; }}
    h3 {{ font-size:15px; line-height:1.25; margin:18px 0 8px; letter-spacing:0; }}
    p {{ margin:0 0 10px; }}
    .lede {{ max-width:900px; font-size:16px; }}
    .meta {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; margin-top:16px; }}
    .meta div {{ border-top:1px solid var(--rule); padding-top:8px; min-width:0; }}
    .meta span {{ display:block; color:var(--muted); font-size:11px; text-transform:uppercase; font-weight:650; }}
    .note {{ background:#fff; border-top:1px solid var(--rule); border-bottom:1px solid var(--rule); padding:12px 0; margin:16px 0; }}
    .readout {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px 24px; margin:18px 0 8px; }}
    .readout div {{ border-top:1px solid var(--rule); padding-top:9px; }}
    .readout .label {{ display:block; margin-bottom:3px; }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:20px; }}
    table {{ width:100%; border-collapse:collapse; margin:8px 0 16px; table-layout:fixed; border-top:2px solid var(--ink); border-bottom:1px solid var(--ink); }}
    th {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--ink); color:var(--muted); font-size:11px; text-transform:uppercase; }}
    td {{ vertical-align:top; padding:7px 8px; border-bottom:1px solid var(--rule); overflow-wrap:anywhere; }}
    .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
    .strong {{ font-weight:700; }}
    .more td, .empty {{ color:var(--muted); font-style:italic; background:#fff; }}
    .products {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:12px 0 16px; }}
    .product-card {{ margin:0; border:1px solid var(--rule); padding:8px; }}
    .product-card img, .image-placeholder {{ width:100%; aspect-ratio:1/1; object-fit:contain; background:var(--soft); display:block; }}
    .image-placeholder::after {{ content:"No image"; display:grid; place-items:center; height:100%; color:var(--muted); font-size:12px; }}
    .product-card figcaption {{ font-size:12px; margin-top:8px; }}
    .product-card span {{ display:block; color:var(--muted); margin-top:3px; }}
    .links a {{ display:inline-block; margin:0 14px 8px 0; color:var(--accent); text-decoration:none; font-weight:650; }}
    @media (max-width:820px) {{ .meta,.grid,.readout,.products {{ grid-template-columns:1fr; }} main {{ width:min(100vw - 24px,1180px); }} }}
  </style>
</head>
<body><main>
<header>
  <h1>{_escape(title)}</h1>
  <p class="lede">Evidence-led HTML report generated from the retailer package. Compact reporting table excerpts ground the narrative; full table artifacts are linked at the end.</p>
  <div class="meta">
    <div><span>Package</span>{_escape(retailer_label)} - {_escape(category_display)}</div>
    <div><span>Universe</span>{_escape(summary.get("listing_products"))} products</div>
    <div><span>Cohorts</span>{_escape(summary.get("top_seller_products"))} top sellers / {_escape(summary.get("recent_products"))} recent</div>
    <div><span>Review themes</span>{_escape(summary.get("review_theme_cohort_comparison_rows"))} surfaced rows</div>
    <div><span>Integrity</span>{_escape(integrity_status)} / {_escape(warning_status)}</div>
  </div>
</header>
<section class="note"><strong>How to read this report.</strong> The tables are deterministic package artifacts. They do not replace the interpretation; they keep the evidence, units, and examples stable while the narrative stays concise.</section>
<section>
  <h2>Evidence Read</h2>
  <div class="readout">
    <div><strong class="label">Current winners</strong>{_bundle_sentence(_first(winning), fallback="No current winning bundle cleared the table template thresholds.")}</div>
    <div><strong class="label">Emerging layer</strong>{_bundle_sentence(_first(emerging), fallback="No emerging bundle cleared the table template thresholds.")}</div>
    <div><strong class="label">Winner/emerging bridge</strong>{_escape(_bridge_summary(bridge_rows))}</div>
    <div><strong class="label">Review-visible layer</strong>{_review_summary(review_rows)}</div>
    <div><strong class="label">Ranked shelf visibility</strong>{_visibility_summary(visibility_rows)}</div>
    <div><strong class="label">Visual product evidence</strong>{_escape(_visual_summary(product_rows, image_map))}</div>
  </div>
</section>
<section>
  <h2>Visual Product Evidence</h2>
  <p>These examples are the image-backed products surfaced by the deterministic product-evidence table, using package images or the existing downloaded image store.</p>
  {_render_product_cards(product_rows, image_map)}
</section>
<section>
  <h2>1. Winning Now</h2>
  <p>{_bundle_sentence(_first(winning), fallback="No current winning bundle cleared the table template thresholds.")}</p>
  {_render_table(winning, bundle_columns, max_rows=8, labels=column_labels, numeric_columns=numeric_columns, strong_columns=strong_columns)}
</section>
<section>
  <h2>2. Emerging Signals And Bridge</h2>
  <p>{_bundle_sentence(_first(emerging), fallback="No emerging bundle cleared the table template thresholds.")}</p>
  {_render_table(bridge_rows, bridge_columns, max_rows=10, labels=column_labels, numeric_columns=numeric_columns, strong_columns=strong_columns)}
</section>
<section>
  <h2>3. Rank-Weighted Visibility</h2>
  <p>The shelf table reads ranked visibility as gross, incremental, and cumulative coverage, so large but overlapping lanes do not crowd out smaller incremental signals.</p>
  {_render_table(visibility_rows, visibility_columns, max_rows=8, labels=column_labels, numeric_columns=numeric_columns, strong_columns=strong_columns)}
</section>
<section>
  <h2>4. Review-Visible Experience Layer</h2>
  <p>Review themes are a secondary evidence layer: they show where consumer language over- or under-indexes across the package cohorts, not causal drivers.</p>
  {_render_table(review_display, review_columns, max_rows=8, labels=column_labels, numeric_columns=numeric_columns, strong_columns=strong_columns)}
</section>
<section>
  <h2>5. Product Evidence</h2>
  <p>Product examples connect the selected bundle rows back to ranked SKUs, ratings, review counts, attributes, and package images when available.</p>
  {_render_table(product_rows, product_columns, max_rows=10, labels=column_labels, numeric_columns=numeric_columns, strong_columns=strong_columns)}
</section>
<section>
  <h2>Generated Table Artifacts</h2>
  {_render_links()}
</section>
</main></body></html>
"""
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "report.html"
    html_path.write_text(html_text, encoding="utf-8")
    markdown_path = output_dir / "report.md"
    markdown_path.write_text(
        _markdown_report(
            title=title,
            summary=summary,
            winning=winning,
            emerging=emerging,
            review_rows=review_rows,
        ),
        encoding="utf-8",
    )
    index_payload = {
        "title": title,
        "package_dir": str(package_dir),
        "report_html": "report.html",
        "report_markdown": "report.md",
        "attribute_tables": f"{ATTRIBUTE_TABLE_DIRNAME}/manifest.json",
        "review_theme_rows": len(review_rows),
        "bundle_rows": len(bundle_rows),
        "bridge_rows": len(bridge_rows),
        "visibility_rows": len(visibility_rows),
        "product_rows": len(product_rows),
    }
    (output_dir / "report_index.json").write_text(
        json.dumps(index_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return index_payload


def _write_batch_index(output_root: Path, reports: Sequence[Mapping[str, Any]]) -> None:
    items = []
    for report in reports:
        report_dir = _safe_text(report.get("output_dir"))
        title = _safe_text(report.get("title"))
        items.append(
            f'<li><a href="{_escape(report_dir)}/report.html">{_escape(title)}</a></li>'
        )
    html_text = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Attribute Table Report Batch</title>"
        "<style>body{font:14px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "margin:32px auto;max-width:860px;color:#202124}h1{font-size:28px}"
        "li{margin:8px 0}a{color:#1e6f68;font-weight:650;text-decoration:none}</style>"
        "</head><body><h1>Attribute Table Report Batch</h1><ul>"
        + "".join(items)
        + "</ul></body></html>"
    )
    (output_root / "index.html").write_text(html_text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build compact HTML reports from retailer package table artifacts."
    )
    parser.add_argument(
        "package_dir",
        nargs="+",
        type=Path,
        help="Retailer evidence package directory. May be repeated.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runs/attribute_table_report_batch"),
        help="Directory where per-package report folders are written.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    reports: list[dict[str, Any]] = []
    args.output_root.mkdir(parents=True, exist_ok=True)
    for package_dir in args.package_dir:
        summary = _read_json(package_dir / "summary.json")
        slug = _slug_for_package(package_dir, summary)
        output_dir = args.output_root / slug
        report = dict(_render_html_report(package_dir, output_dir))
        report["output_dir"] = output_dir.name
        reports.append(report)
        LOGGER.info("Wrote report: %s", output_dir / "report.html")
    _write_batch_index(args.output_root, reports)
    (args.output_root / "batch_index.json").write_text(
        json.dumps({"reports": reports}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    sys.stdout.write(
        json.dumps({"output_root": str(args.output_root), "reports": reports}, indent=2)
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
