from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

import polars as pl

from modules.pdp.attribute_mapping_paths import get_attribute_mapping_dir

ATTRIBUTE_MAPPING_DIR = get_attribute_mapping_dir()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute web-search attribute fill uplift from attribute_web_fill_audit.csv "
            "(N/A before vs N/A after web step), split by category and attribute."
        )
    )
    parser.add_argument(
        "--audit-csv",
        type=Path,
        default=ATTRIBUTE_MAPPING_DIR / "attribute_web_fill_audit.csv",
        help="Path to web fill audit CSV.",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=ATTRIBUTE_MAPPING_DIR / "attribute_web_fill_uplift_summary.csv",
        help="Output CSV path for per-attribute/category summary.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=40,
        help="How many top rows to print by filled count.",
    )
    return parser.parse_args()


def _safe_json_obj(raw: object) -> dict[str, Any]:
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if not text or text == "{}":
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_requested_parent(raw: object) -> list[str]:
    if not isinstance(raw, str):
        return []
    parts = [item.strip() for item in raw.split(",")]
    return [item for item in parts if item]


def _parse_requested_variant(raw: object) -> dict[str, list[str]]:
    parsed = _safe_json_obj(raw)
    result: dict[str, list[str]] = {}
    for key, value in parsed.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, list):
            attrs = [str(item).strip() for item in value if str(item).strip()]
        else:
            attrs = []
        if attrs:
            result[key] = attrs
    return result


def _parse_filled_parent(raw: object) -> set[str]:
    parsed = _safe_json_obj(raw)
    return {str(attr_id).strip() for attr_id in parsed.keys() if str(attr_id).strip()}


def _parse_filled_variant(raw: object) -> dict[str, set[str]]:
    parsed = _safe_json_obj(raw)
    result: dict[str, set[str]] = {}
    for variant_key, payload in parsed.items():
        if not isinstance(variant_key, str):
            continue
        if not isinstance(payload, dict):
            continue
        attrs = {
            str(attr_id).strip() for attr_id in payload.keys() if str(attr_id).strip()
        }
        if attrs:
            result[variant_key] = attrs
    return result


def _counter_key(
    scope: str, category_key: str, attribute_id: str
) -> tuple[str, str, str]:
    return (scope, category_key.strip(), attribute_id.strip())


def build_uplift_summary(audit_df: pl.DataFrame) -> pl.DataFrame:
    counter: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {"before_missing": 0, "filled": 0, "after_missing": 0}
    )

    for row in audit_df.iter_rows(named=True):
        category_key = str(row.get("category_key") or "").strip()
        if not category_key:
            category_key = "(unknown)"

        requested_parent = _parse_requested_parent(
            row.get("requested_parent_attributes")
        )
        filled_parent = _parse_filled_parent(row.get("filled_parent_attributes"))
        for attribute_id in requested_parent:
            key = _counter_key("parent", category_key, attribute_id)
            stats = counter[key]
            stats["before_missing"] += 1
            if attribute_id in filled_parent:
                stats["filled"] += 1
            else:
                stats["after_missing"] += 1

        requested_variant = _parse_requested_variant(
            row.get("requested_variant_attributes")
        )
        filled_variant = _parse_filled_variant(row.get("filled_variant_attributes"))
        for variant_key, attrs in requested_variant.items():
            filled_attrs = filled_variant.get(variant_key, set())
            for attribute_id in attrs:
                key = _counter_key("variant", category_key, attribute_id)
                stats = counter[key]
                stats["before_missing"] += 1
                if attribute_id in filled_attrs:
                    stats["filled"] += 1
                else:
                    stats["after_missing"] += 1

    rows: list[dict[str, Any]] = []
    for (scope, category_key, attribute_id), stats in counter.items():
        before_missing = stats["before_missing"]
        filled = stats["filled"]
        after_missing = stats["after_missing"]
        fill_rate = (filled / before_missing) if before_missing > 0 else 0.0
        rows.append(
            {
                "scope": scope,
                "category_key": category_key,
                "attribute_id": attribute_id,
                "before_missing_count": before_missing,
                "filled_count": filled,
                "after_missing_count": after_missing,
                "fill_rate": fill_rate,
                "fill_rate_pct": fill_rate * 100.0,
            }
        )

    if not rows:
        return pl.DataFrame(
            schema={
                "scope": pl.Utf8,
                "category_key": pl.Utf8,
                "attribute_id": pl.Utf8,
                "before_missing_count": pl.Int64,
                "filled_count": pl.Int64,
                "after_missing_count": pl.Int64,
                "fill_rate": pl.Float64,
                "fill_rate_pct": pl.Float64,
            }
        )

    return pl.DataFrame(rows).sort(
        [
            "filled_count",
            "before_missing_count",
            "scope",
            "category_key",
            "attribute_id",
        ],
        descending=[True, True, False, False, False],
    )


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if not args.audit_csv.exists():
        raise SystemExit(f"Audit file not found: {args.audit_csv}")

    audit_df = pl.read_csv(args.audit_csv)
    if audit_df.is_empty():
        raise SystemExit(f"Audit file is empty: {args.audit_csv}")

    summary_df = build_uplift_summary(audit_df)
    if summary_df.is_empty():
        raise SystemExit("No requested attributes found in audit file.")

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    summary_df.write_csv(args.out_csv)

    total_before = int(
        summary_df.select(pl.col("before_missing_count").sum()).item() or 0
    )
    total_filled = int(summary_df.select(pl.col("filled_count").sum()).item() or 0)
    total_after = int(
        summary_df.select(pl.col("after_missing_count").sum()).item() or 0
    )
    total_fill_rate = (total_filled / total_before) if total_before > 0 else 0.0

    print(f"audit_csv: {args.audit_csv}")
    print(f"summary_csv: {args.out_csv}")
    print(f"total_before_missing: {total_before}")
    print(f"total_filled: {total_filled}")
    print(f"total_after_missing: {total_after}")
    print(f"total_fill_rate_pct: {total_fill_rate * 100:.2f}")
    print()
    print(f"top_{args.top}_by_filled_count:")
    print(summary_df.head(args.top))


if __name__ == "__main__":
    main()
