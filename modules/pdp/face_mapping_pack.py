from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import polars as pl

from modules.utilities.utils import get_row_count, get_schema_and_column_names

__all__ = [
    "DEFAULT_FACE_CATEGORIES",
    "DEFAULT_OUTPUT_ROOT",
    "build_face_mapping_review_pack",
    "find_latest_face_export",
    "find_latest_face_report_dir",
    "zip_face_mapping_review_pack",
]


DEFAULT_FACE_CATEGORIES = (
    "bb_cc_creams",
    "color_correct",
    "contour",
    "tinted_moisturizer",
)
DEFAULT_CLI_ROOT = Path("data/pdp/cli")
DEFAULT_OUTPUT_ROOT = Path("data/pdp/reports/face_mapping_packs")
DEFAULT_EXPORT_ROOT = Path("data/pdp/exports")
DEFAULT_REPORT_ROOT = Path("data/pdp/reports")
OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
VERDICT_PRIORITY = {
    "mismatch": 0,
    "our_missing": 1,
    "partial_match": 2,
    "ulta_missing": 3,
    "both_missing": 4,
    "exact_match": 5,
}


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_url_text(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    return text.replace("\\u002F", "/")


def _safe_stem(value: str | None) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return safe.strip("._") or None


def _package_slug(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        raise ValueError(f"{field_name} must contain at least one path-safe character.")
    return normalized


def _package_output_dir(output_root: Path, *, retailer: str, package_key: str) -> Path:
    return (
        output_root
        / _package_slug(retailer, field_name="retailer")
        / _package_slug(package_key, field_name="package")
    )


def _package_zip_path(output_dir: Path) -> Path:
    return output_dir.with_suffix(".zip")


def _prepare_package_output_dir(
    output_root: Path, *, retailer: str, package_key: str
) -> Path:
    output_dir = _package_output_dir(
        output_root,
        retailer=retailer,
        package_key=package_key,
    )
    zip_path = _package_zip_path(output_dir)
    if zip_path.exists():
        zip_path.unlink()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _infer_image_suffix(image_url: str | None) -> str:
    url = _normalize_url_text(image_url)
    if not url:
        return ".jpg"
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in {".png", ".jpg", ".jpeg", ".webp"} else ".jpg"


def _find_local_cli_image(
    parent_product_id: str | None,
    *,
    cli_root: Path = DEFAULT_CLI_ROOT,
) -> Path | None:
    safe_parent = _safe_stem(parent_product_id)
    if not safe_parent or not cli_root.exists():
        return None

    matches: list[Path] = []
    for pattern in (
        f"*/images/{safe_parent}_*_hero.*",
        f"*/images/{safe_parent}_hero.*",
    ):
        matches.extend(path for path in cli_root.glob(pattern) if path.is_file())
    if not matches:
        return None
    return sorted(matches)[0]


def _copy_local_image(source: Path, destination: Path) -> str | None:
    if not source.exists():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return str(destination.resolve())


def _download_image(image_url: str | None, destination: Path) -> str | None:
    url = _normalize_url_text(image_url)
    if not url:
        return None
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
            )
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read()
    except (OSError, URLError):
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return str(destination.resolve())


def _fetch_og_image_url(pdp_url: str | None) -> str | None:
    url = _normalize_url_text(pdp_url)
    if not url:
        return None
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
            )
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            html = response.read(800_000).decode("utf-8", errors="replace")
    except (OSError, URLError):
        return None
    match = OG_IMAGE_RE.search(html)
    if not match:
        return None
    return _normalize_url_text(match.group(1))


def _relative_output_path(output_dir: Path, file_path: str | None) -> str | None:
    text = _normalize_text(file_path)
    if not text:
        return None
    try:
        return str(Path(text).resolve().relative_to(output_dir.resolve()))
    except Exception:
        return None


def _materialize_pack_image(
    *,
    output_dir: Path,
    parent_product_id: str | None,
    hero_image_url: str | None,
    pdp_url: str | None,
    cli_root: Path = DEFAULT_CLI_ROOT,
) -> dict[str, str | None]:
    safe_parent = _safe_stem(parent_product_id)
    if not safe_parent:
        return {
            "pack_image_path": None,
            "pack_image_source": None,
            "og_image_url": None,
        }

    images_dir = output_dir / "images"
    local_cli_image = _find_local_cli_image(parent_product_id, cli_root=cli_root)
    if local_cli_image is not None:
        destination = images_dir / f"{safe_parent}{local_cli_image.suffix.lower()}"
        image_path = _copy_local_image(local_cli_image, destination)
        if image_path:
            return {
                "pack_image_path": image_path,
                "pack_image_source": "local_cli_image",
                "og_image_url": None,
            }

    normalized_hero = _normalize_url_text(hero_image_url)
    if normalized_hero:
        destination = (
            images_dir / f"{safe_parent}{_infer_image_suffix(normalized_hero)}"
        )
        image_path = _download_image(normalized_hero, destination)
        if image_path:
            return {
                "pack_image_path": image_path,
                "pack_image_source": "hero_image_url",
                "og_image_url": None,
            }

    og_image_url = _fetch_og_image_url(pdp_url)
    if og_image_url:
        destination = images_dir / f"{safe_parent}{_infer_image_suffix(og_image_url)}"
        image_path = _download_image(og_image_url, destination)
        if image_path:
            return {
                "pack_image_path": image_path,
                "pack_image_source": "og_image_url",
                "og_image_url": og_image_url,
            }

    return {
        "pack_image_path": None,
        "pack_image_source": None,
        "og_image_url": og_image_url,
    }


def _build_image_index(face_products: pl.DataFrame) -> pl.DataFrame:
    if get_row_count(face_products) == 0:
        return pl.DataFrame(
            schema={
                "parent_product_id": pl.Utf8,
                "product_name": pl.Utf8,
                "image_file": pl.Utf8,
                "image_available": pl.Boolean,
                "image_source": pl.Utf8,
                "inspect_rule": pl.Utf8,
            }
        )
    return (
        face_products.select(
            [
                "parent_product_id",
                "product_name",
                pl.col("pack_image_file").alias("image_file"),
                pl.col("pack_image_file").is_not_null().alias("image_available"),
                pl.col("pack_image_source").alias("image_source"),
            ]
        )
        .with_columns(
            pl.lit(
                "Inspect images only when the product materially affects the verdict."
            ).alias("inspect_rule")
        )
        .sort(["product_name", "parent_product_id"])
    )


def _build_category_overview(verdict_summary: pl.DataFrame) -> pl.DataFrame:
    if get_row_count(verdict_summary) == 0:
        return pl.DataFrame(
            schema={
                "mapped_category_key": pl.Utf8,
                "total_rows": pl.Int64,
                "exact_match_rows": pl.Int64,
                "mismatch_rows": pl.Int64,
                "our_missing_rows": pl.Int64,
                "partial_match_rows": pl.Int64,
                "ulta_missing_rows": pl.Int64,
                "both_missing_rows": pl.Int64,
            }
        )
    return (
        verdict_summary.group_by("mapped_category_key")
        .agg(
            [
                pl.col("len").sum().alias("total_rows"),
                pl.when(pl.col("verdict") == "exact_match")
                .then(pl.col("len"))
                .otherwise(0)
                .sum()
                .alias("exact_match_rows"),
                pl.when(pl.col("verdict") == "mismatch")
                .then(pl.col("len"))
                .otherwise(0)
                .sum()
                .alias("mismatch_rows"),
                pl.when(pl.col("verdict") == "our_missing")
                .then(pl.col("len"))
                .otherwise(0)
                .sum()
                .alias("our_missing_rows"),
                pl.when(pl.col("verdict") == "partial_match")
                .then(pl.col("len"))
                .otherwise(0)
                .sum()
                .alias("partial_match_rows"),
                pl.when(pl.col("verdict") == "ulta_missing")
                .then(pl.col("len"))
                .otherwise(0)
                .sum()
                .alias("ulta_missing_rows"),
                pl.when(pl.col("verdict") == "both_missing")
                .then(pl.col("len"))
                .otherwise(0)
                .sum()
                .alias("both_missing_rows"),
            ]
        )
        .with_columns(
            [
                (pl.col("exact_match_rows") / pl.col("total_rows")).alias(
                    "exact_match_share"
                ),
                (
                    (pl.col("mismatch_rows") + pl.col("our_missing_rows"))
                    / pl.col("total_rows")
                ).alias("problem_share"),
            ]
        )
        .sort("mapped_category_key")
    )


def _build_priority_issue_matrix(verdict_summary: pl.DataFrame) -> pl.DataFrame:
    if get_row_count(verdict_summary) == 0:
        return pl.DataFrame(
            schema={
                "mapped_category_key": pl.Utf8,
                "filter_family": pl.Utf8,
                "mismatch_rows": pl.Int64,
                "our_missing_rows": pl.Int64,
                "partial_match_rows": pl.Int64,
                "problem_rows": pl.Int64,
            }
        )
    return (
        verdict_summary.group_by(["mapped_category_key", "filter_family"])
        .agg(
            [
                pl.when(pl.col("verdict") == "mismatch")
                .then(pl.col("len"))
                .otherwise(0)
                .sum()
                .alias("mismatch_rows"),
                pl.when(pl.col("verdict") == "our_missing")
                .then(pl.col("len"))
                .otherwise(0)
                .sum()
                .alias("our_missing_rows"),
                pl.when(pl.col("verdict") == "partial_match")
                .then(pl.col("len"))
                .otherwise(0)
                .sum()
                .alias("partial_match_rows"),
            ]
        )
        .with_columns(
            (
                pl.col("mismatch_rows")
                + pl.col("our_missing_rows")
                + pl.col("partial_match_rows")
            ).alias("problem_rows")
        )
        .filter(pl.col("problem_rows") > 0)
        .sort(
            by=["problem_rows", "mapped_category_key", "filter_family"],
            descending=[True, False, False],
        )
    )


def _build_issue_examples(
    product_filter_matrix: pl.DataFrame,
    *,
    per_issue_limit: int = 4,
) -> pl.DataFrame:
    if get_row_count(product_filter_matrix) == 0:
        return product_filter_matrix
    examples = (
        product_filter_matrix.filter(
            pl.col("verdict").is_in(
                ["mismatch", "our_missing", "partial_match", "ulta_missing"]
            )
        )
        .with_columns(
            [
                pl.col("verdict")
                .replace_strict(VERDICT_PRIORITY, default=99)
                .alias("verdict_priority"),
                pl.col("product_name").fill_null("").alias("_product_name_sort"),
            ]
        )
        .sort(
            by=[
                "mapped_category_key",
                "filter_family",
                "verdict_priority",
                "_product_name_sort",
                "parent_product_id",
            ]
        )
        .group_by(
            ["mapped_category_key", "filter_family", "verdict"], maintain_order=True
        )
        .head(per_issue_limit)
        .drop(["verdict_priority", "_product_name_sort"])
    )
    return examples


def _build_prompt(
    *,
    categories: tuple[str, ...],
    source_report_dir: Path,
    source_export_path: Path,
) -> str:
    category_list = ", ".join(categories)
    return f"""You are a skeptical data-quality analyst reviewing an Ulta face-mapping evidence pack.

Your job is to judge whether the current mapping for the new Ulta face categories is trustworthy enough to use, and to explain where the remaining failures come from.

Scope:
- Categories in scope: {category_list}
- Source comparison pack: {source_report_dir.name}
- Source mapped export: {source_export_path.name}

Core logic:
- Start with category_overview.csv to see which categories are healthy versus fragile.
- Use priority_issue_matrix.csv, mismatch_summary.csv, and our_missing_summary.csv to identify the biggest problem families.
- Use bridge_family_alignment.csv to separate bridge coverage issues from extraction or taxonomy issues.
- Use product_filter_matrix.csv and issue_examples.csv for concrete product-level evidence.
- Use face_products.csv and images/ only to validate whether the mapped values look plausible in product reality.
- Use retailer_filter_observations.csv only when you need to understand what Ulta actually exposed for a specific family.

Important rules:
- Treat exact_match as positive evidence.
- Treat our_missing as a coverage failure on our side unless Ulta itself is missing the family.
- Treat mismatch as a possible extraction problem, taxonomy problem, or retailer ambiguity; do not assume all mismatches are equally bad.
- Treat ulta_missing as mostly a retailer-gap signal, not an immediate failure on our side.
- Distinguish these failure modes clearly:
  1. extraction / parsing problem
  2. taxonomy gap or bad synonym coverage
  3. bridge design problem
  4. retailer ambiguity / noisy Ulta evidence
- Be skeptical. Do not overstate confidence from small counts.
- Use examples. Totals without concrete product evidence are not enough.
- Keep the output practical and evidence-led.

Files:
- summary.json: pack metadata and source paths.
- category_overview.csv: high-level quality by category.
- priority_issue_matrix.csv: category/family issues ranked by size.
- category_filter_verdict_summary.csv: full verdict counts by category and family.
- mismatch_summary.csv: mismatch counts by category and family.
- our_missing_summary.csv: missing-value counts by category and family.
- bridge_family_alignment.csv: whether expected bridge families were actually observed in the latest crawl.
- double_matching_summary.csv: where Ulta multi-value filters may make one-value mapping lossy.
- product_filter_matrix.csv: product-level comparison rows with verdicts.
- issue_examples.csv: small set of representative problem rows.
- face_products.csv: mapped parent products in scope with key attributes, URLs, and image paths.
- retailer_filter_observations.csv: raw Ulta filter observations in scope.
- image_index.csv: which product images are available.
- images/: product packshots for visual spot checks.

Output:
1. Overall verdict: is the current mapping good enough to trust, partly trust, or not trust yet?
2. Category-by-category read: what is the quality level of each category in scope?
3. Main failure modes: what is mostly extraction, what is mostly taxonomy, what is mostly bridge design, and what is mostly retailer ambiguity?
4. Strongest evidence of correctness: which families and products show that the mapping is working?
5. Biggest unresolved problems: which category/family combinations still look weak or misleading?
6. Product examples: which specific products best illustrate the strongest successes and the worst failures?
7. Promotion readiness: what is safe to ship now, and what should stay local until fixed?
8. Priority fix list: the shortest sensible sequence of fixes before broader rollout.
9. Recap block with exactly these fields:
   - Overall status
   - Strongest categories
   - Weakest categories
   - Primary failure modes
   - Best example products
   - Worst example products
   - Safe to promote now: yes / partly / no
"""


def _select_existing_columns(df: pl.DataFrame, desired: list[str]) -> list[str]:
    columns, _ = get_schema_and_column_names(df)
    return [column for column in desired if column in columns]


def _load_csv(path: Path) -> pl.DataFrame:
    return pl.read_csv(path, infer_schema_length=10000)


def _find_latest_path(paths: list[Path]) -> Path:
    if not paths:
        raise FileNotFoundError("No matching artifact found.")
    return sorted(paths)[-1]


def find_latest_face_export(export_root: Path = DEFAULT_EXPORT_ROOT) -> Path:
    candidates = list(export_root.glob("pdp_attributes_*face_patch*_parents.csv"))
    if not candidates:
        candidates = list(export_root.glob("pdp_attributes_*new_face_parents.csv"))
    return _find_latest_path(candidates)


def find_latest_face_report_dir(report_root: Path = DEFAULT_REPORT_ROOT) -> Path:
    candidates = [
        path for path in report_root.glob("ulta_face_bridge_*") if path.is_dir()
    ]
    return _find_latest_path(candidates)


def zip_face_mapping_review_pack(output_dir: Path) -> Path:
    zip_path = _package_zip_path(output_dir)
    include_files = [
        "summary.json",
        "pack_manifest.json",
        "prompt_for_pro.txt",
        "category_overview.csv",
        "priority_issue_matrix.csv",
        "bridge_family_alignment.csv",
        "category_filter_verdict_summary.csv",
        "mismatch_summary.csv",
        "our_missing_summary.csv",
        "double_matching_summary.csv",
        "product_filter_matrix.csv",
        "issue_examples.csv",
        "face_products.csv",
        "retailer_filter_observations.csv",
        "image_index.csv",
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in include_files:
            candidate = output_dir / name
            if candidate.exists():
                zf.write(candidate, arcname=str(Path(output_dir.name) / name))
        images_dir = output_dir / "images"
        if images_dir.exists():
            for image_path in sorted(images_dir.rglob("*")):
                if image_path.is_file():
                    zf.write(
                        image_path,
                        arcname=str(
                            Path(output_dir.name) / image_path.relative_to(output_dir)
                        ),
                    )
    return zip_path


def build_face_mapping_review_pack(
    *,
    export_path: Path | None = None,
    report_dir: Path | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    categories: tuple[str, ...] = DEFAULT_FACE_CATEGORIES,
) -> Path:
    resolved_export = export_path or find_latest_face_export()
    resolved_report_dir = report_dir or find_latest_face_report_dir()
    output_dir = _prepare_package_output_dir(
        output_root,
        retailer="ulta",
        package_key="face_mapping_review",
    )

    face_products = _load_csv(resolved_export).filter(
        pl.col("category_key").is_in(categories)
    )
    product_matrix = _load_csv(
        resolved_report_dir / "brand_filter_comparison.csv"
    ).filter(pl.col("mapped_category_key").is_in(categories))
    verdict_summary = _load_csv(
        resolved_report_dir / "category_filter_verdict_summary.csv"
    ).filter(pl.col("mapped_category_key").is_in(categories))
    mismatch_summary = _load_csv(resolved_report_dir / "mismatch_summary.csv").filter(
        pl.col("mapped_category_key").is_in(categories)
    )
    our_missing_summary = _load_csv(
        resolved_report_dir / "our_missing_summary.csv"
    ).filter(pl.col("mapped_category_key").is_in(categories))
    bridge_alignment = _load_csv(
        resolved_report_dir / "bridge_family_alignment.csv"
    ).filter(pl.col("category_key").is_in(categories))
    double_matching = _load_csv(
        resolved_report_dir / "double_matching_summary.csv"
    ).filter(pl.col("category_key").is_in(categories))
    filter_observations = _load_csv(
        resolved_report_dir / "retailer_filter_observations.csv"
    ).filter(pl.col("category_key").is_in(categories))
    source_summary = json.loads(
        (resolved_report_dir / "summary.json").read_text(encoding="utf-8")
    )

    desired_face_columns = [
        "retailer",
        "parent_product_id",
        "category_key",
        "brand",
        "product_name",
        "pdp_url",
        "hero_image_url",
        "form",
        "finish",
        "coverage",
        "color family",
        "spf",
        "skin type",
        "color-corrector shade",
        "shade depth",
        "sales_share",
        "cumulative_sales_share",
        "pareto_rank",
        "pareto_bucket",
        "price_band",
        "description",
    ]
    face_products = face_products.select(
        _select_existing_columns(face_products, desired_face_columns)
    )

    image_rows: list[dict[str, str | None]] = []
    for row in face_products.iter_rows(named=True):
        image_meta = _materialize_pack_image(
            output_dir=output_dir,
            parent_product_id=_normalize_text(row.get("parent_product_id")),
            hero_image_url=_normalize_url_text(row.get("hero_image_url")),
            pdp_url=_normalize_url_text(row.get("pdp_url")),
        )
        image_rows.append(
            {
                "parent_product_id": _normalize_text(row.get("parent_product_id")),
                "pack_image_path": image_meta["pack_image_path"],
                "pack_image_source": image_meta["pack_image_source"],
                "og_image_url": image_meta["og_image_url"],
            }
        )
    image_df = (
        pl.DataFrame(image_rows)
        if image_rows
        else pl.DataFrame(
            schema={
                "parent_product_id": pl.Utf8,
                "pack_image_path": pl.Utf8,
                "pack_image_source": pl.Utf8,
                "og_image_url": pl.Utf8,
            }
        )
    )
    if get_row_count(image_df) > 0:
        face_products = face_products.join(image_df, on="parent_product_id", how="left")
    else:
        face_products = face_products.with_columns(
            [
                pl.lit(None, dtype=pl.Utf8).alias("pack_image_path"),
                pl.lit(None, dtype=pl.Utf8).alias("pack_image_source"),
                pl.lit(None, dtype=pl.Utf8).alias("og_image_url"),
            ]
        )
    face_products = face_products.with_columns(
        [
            pl.col("pack_image_path")
            .map_elements(
                lambda value: _relative_output_path(output_dir, value),
                return_dtype=pl.Utf8,
            )
            .alias("pack_image_file"),
            pl.col("description")
            .map_elements(
                lambda value: " ".join(str(value).split())[:400] if value else None,
                return_dtype=pl.Utf8,
            )
            .alias("description_excerpt"),
        ]
    )

    image_meta_small = face_products.select(
        ["parent_product_id", "pack_image_file", "pack_image_source"]
    )
    product_matrix = product_matrix.join(
        image_meta_small, on="parent_product_id", how="left"
    )
    issue_examples = _build_issue_examples(product_matrix)
    category_overview = _build_category_overview(verdict_summary)
    priority_issue_matrix = _build_priority_issue_matrix(verdict_summary)
    image_index = _build_image_index(face_products)

    prompt_text = _build_prompt(
        categories=categories,
        source_report_dir=resolved_report_dir,
        source_export_path=resolved_export,
    )
    summary = {
        "pack_type": "ulta_face_mapping_review",
        "retailer": "ulta",
        "categories": list(categories),
        "source_export_path": str(resolved_export.resolve()),
        "source_report_dir": str(resolved_report_dir.resolve()),
        "source_report_summary": source_summary,
        "face_product_rows": int(get_row_count(face_products)),
        "product_filter_rows": int(get_row_count(product_matrix)),
        "issue_example_rows": int(get_row_count(issue_examples)),
        "image_count": int(
            get_row_count(image_index.filter(pl.col("image_available") == True))
        ),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest = {
        "pack_type": "ulta_face_mapping_review",
        "files": {
            "summary": "summary.json",
            "prompt": "prompt_for_pro.txt",
            "category_overview": "category_overview.csv",
            "priority_issue_matrix": "priority_issue_matrix.csv",
            "bridge_family_alignment": "bridge_family_alignment.csv",
            "category_filter_verdict_summary": "category_filter_verdict_summary.csv",
            "mismatch_summary": "mismatch_summary.csv",
            "our_missing_summary": "our_missing_summary.csv",
            "double_matching_summary": "double_matching_summary.csv",
            "product_filter_matrix": "product_filter_matrix.csv",
            "issue_examples": "issue_examples.csv",
            "face_products": "face_products.csv",
            "retailer_filter_observations": "retailer_filter_observations.csv",
            "image_index": "image_index.csv",
            "images_dir": "images",
        },
        "definitions": {
            "exact_match": "Our mapped value matches at least one observed Ulta filter value.",
            "mismatch": "Ulta exposed a value for the family, but our mapped value disagrees.",
            "our_missing": "Ulta exposed a value for the family, but our mapping produced no usable value.",
            "partial_match": "Our mapped value overlaps with Ulta evidence but does not resolve cleanly.",
            "ulta_missing": "Our mapped value exists, but Ulta did not expose a comparable filter value.",
            "both_missing": "Neither side exposed a usable value for that product/family row.",
        },
    }

    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "pack_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "prompt_for_pro.txt").write_text(prompt_text, encoding="utf-8")
    category_overview.write_csv(output_dir / "category_overview.csv")
    priority_issue_matrix.write_csv(output_dir / "priority_issue_matrix.csv")
    bridge_alignment.write_csv(output_dir / "bridge_family_alignment.csv")
    verdict_summary.write_csv(output_dir / "category_filter_verdict_summary.csv")
    mismatch_summary.write_csv(output_dir / "mismatch_summary.csv")
    our_missing_summary.write_csv(output_dir / "our_missing_summary.csv")
    double_matching.write_csv(output_dir / "double_matching_summary.csv")
    product_matrix.write_csv(output_dir / "product_filter_matrix.csv")
    issue_examples.write_csv(output_dir / "issue_examples.csv")
    face_products.write_csv(output_dir / "face_products.csv")
    filter_observations.write_csv(output_dir / "retailer_filter_observations.csv")
    image_index.write_csv(output_dir / "image_index.csv")
    zip_face_mapping_review_pack(output_dir)
    return output_dir
