from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import polars as pl

from modules.utilities.utils import get_schema_and_column_names

__all__ = [
    "BLONZER_PRIMARY_CATEGORY_KEY",
    "BLONZER_SECONDARY_CATEGORY_KEY",
    "annotate_market_hybrid_claims",
    "annotate_bronzer_blush_hybrid",
]


BLONZER_PRIMARY_CATEGORY_KEY = "bronzer"
BLONZER_SECONDARY_CATEGORY_KEY = "blush"

_BLUSH_BRONZER_CLAIM_REGEX = (
    r"(\bblonzer(?:s)?\b"
    r"|\bblush(?:es)?\s*(?:/|&|\+|and)\s*bronzer(?:s)?\b"
    r"|\bbronzer(?:s)?\s*(?:/|&|\+|and)\s*blush(?:es)?\b"
    r"|\bblush\s*bronzer\b"
    r"|\bbronzer\s*blush\b"
    r"|\b2\s*in\s*1\b[^\n]{0,60}\bblush\b[^\n]{0,60}\bbronzer\b"
    r"|\b2\s*in\s*1\b[^\n]{0,60}\bbronzer\b[^\n]{0,60}\bblush\b)"
)
_BLUSH_HIGHLIGHTER_CLAIM_REGEX = (
    r"(\bblush(?:es)?\s*(?:/|&|\+|and)\s*highlighter(?:s)?\b"
    r"|\bhighlighter(?:s)?\s*(?:/|&|\+|and)\s*blush(?:es)?\b"
    r"|\bblushlighter(?:s)?\b"
    r"|\bhighlighting\s+blush(?:es)?\b"
    r"|\bblush\s*highlighter\b"
    r"|\bhighlighter\s*blush\b)"
)
_BRONZER_HIGHLIGHTER_CLAIM_REGEX = (
    r"(\bbronzer(?:s)?\s*(?:/|&|\+|and)\s*highlighter(?:s)?\b"
    r"|\bhighlighter(?:s)?\s*(?:/|&|\+|and)\s*bronzer(?:s)?\b"
    r"|\bbronzer\s*highlighter\b"
    r"|\bhighlighter\s*bronzer\b)"
)
_LIP_CHEEK_CLAIM_REGEX = (
    r"(\blip(?:s)?\s*(?:/|&|\+|and)\s*cheek(?:s)?\b"
    r"|\bcheek(?:s)?\s*(?:/|&|\+|and)\s*lip(?:s)?\b"
    r"|\blips?\s+for\s+cheeks?\b"
    r"|\bfor\s+lips?\s+and\s+cheeks?\b)"
)
_EYESHADOW_EYELINER_CLAIM_REGEX = (
    r"(\beyeshadow(?:s)?\s*(?:/|&|\+|and)\s*eyeliner(?:s)?\b"
    r"|\beyeliner(?:s)?\s*(?:/|&|\+|and)\s*eyeshadow(?:s)?\b"
    r"|\bshadow(?:s)?\s*(?:/|&|\+|and)\s*liner(?:s)?\b"
    r"|\bcan\s+be\s+used\s+as\s+(?:an?\s+)?eyeliner\b)"
)


@dataclass(frozen=True)
class _HybridRule:
    primary_categories: tuple[str, ...]
    secondary_category: str
    claim_regex: str


_HYBRID_RULES: tuple[_HybridRule, ...] = (
    _HybridRule(
        primary_categories=(BLONZER_PRIMARY_CATEGORY_KEY,),
        secondary_category=BLONZER_SECONDARY_CATEGORY_KEY,
        claim_regex=_BLUSH_BRONZER_CLAIM_REGEX,
    ),
    _HybridRule(
        primary_categories=("blush",),
        secondary_category="highlighter",
        claim_regex=_BLUSH_HIGHLIGHTER_CLAIM_REGEX,
    ),
    _HybridRule(
        primary_categories=(BLONZER_PRIMARY_CATEGORY_KEY,),
        secondary_category="highlighter",
        claim_regex=_BRONZER_HIGHLIGHTER_CLAIM_REGEX,
    ),
    _HybridRule(
        primary_categories=(
            "lipstick",
            "liquid lipstick",
            "lip gloss",
            "lip oil",
            "lip stain",
            "lip tint",
        ),
        secondary_category="cheek",
        claim_regex=_LIP_CHEEK_CLAIM_REGEX,
    ),
    _HybridRule(
        primary_categories=("eyeshadow",),
        secondary_category="eyeliner",
        claim_regex=_EYESHADOW_EYELINER_CLAIM_REGEX,
    ),
)

_SECONDARY_CATEGORY_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys(rule.secondary_category for rule in _HYBRID_RULES)
)

_PARENT_TEXT_COLUMNS: tuple[str, ...] = (
    "product_name",
    "description",
    "description_markdown",
    "short_description",
    "long_description",
    "details",
    "benefits",
    "product_description",
    "title_raw",
)

_VARIANT_TEXT_COLUMNS: tuple[str, ...] = (
    "variant_description",
    "shade_name_raw",
    "shade_name_normalized",
    "product_name",
    "title_raw",
)


def _hybrid_secondary_key(secondary_category: str) -> str:
    return secondary_category.strip().lower().replace(" ", "_")


def _category_norm_expr(columns: set[str]) -> pl.Expr:
    candidate_columns = ("category_key", "category_label", "category")
    for column_name in candidate_columns:
        if column_name in columns:
            return (
                pl.col(column_name)
                .cast(pl.Utf8)
                .fill_null("")
                .str.to_lowercase()
                .str.replace_all(r"[_-]+", " ")
                .str.replace_all(r"\s+", " ")
                .str.strip_chars()
            )
    return pl.lit("")


def _composed_text_expr(columns: set[str], *, record_type: str | None) -> pl.Expr:
    if record_type == "variant":
        candidates: Sequence[str] = _VARIANT_TEXT_COLUMNS
    else:
        candidates = _PARENT_TEXT_COLUMNS
    available = [column for column in candidates if column in columns]
    if not available:
        return pl.lit("")
    return pl.concat_str(
        [
            pl.col(column_name)
            .cast(pl.Utf8)
            .fill_null("")
            .str.to_lowercase()
            .str.replace_all(r"\s+", " ")
            .str.strip_chars()
            for column_name in available
        ],
        separator=" | ",
    )


def _ensure_overlay_columns(frame: pl.DataFrame) -> pl.DataFrame:
    columns, _ = get_schema_and_column_names(frame)
    column_set = set(columns)
    additions: list[pl.Expr] = []
    for secondary_category in _SECONDARY_CATEGORY_KEYS:
        secondary_key = _hybrid_secondary_key(secondary_category)
        if f"brand_claims_{secondary_key}_hybrid" not in column_set:
            additions.append(
                pl.lit(False)
                .cast(pl.Boolean)
                .alias(f"brand_claims_{secondary_key}_hybrid")
            )
        if f"inferred_{secondary_key}_hybrid" not in column_set:
            additions.append(
                pl.lit(False).cast(pl.Boolean).alias(f"inferred_{secondary_key}_hybrid")
            )
        if f"also_{secondary_key}" not in column_set:
            additions.append(
                pl.lit(False).cast(pl.Boolean).alias(f"also_{secondary_key}")
            )
        if f"also_{secondary_key}_secondary_category" not in column_set:
            additions.append(
                pl.lit(None)
                .cast(pl.Utf8)
                .alias(f"also_{secondary_key}_secondary_category")
            )
        if f"also_{secondary_key}_source" not in column_set:
            additions.append(
                pl.lit(None).cast(pl.Utf8).alias(f"also_{secondary_key}_source")
            )
        if f"also_{secondary_key}_evidence" not in column_set:
            additions.append(
                pl.lit(None).cast(pl.Utf8).alias(f"also_{secondary_key}_evidence")
            )
    if not additions:
        return frame
    return frame.with_columns(additions)


def annotate_market_hybrid_claims(
    frame: pl.DataFrame,
    *,
    record_type: str | None = None,
) -> pl.DataFrame:
    """Annotate explicit market hybrid claims on the provided records."""
    if frame.is_empty():
        return _ensure_overlay_columns(frame)

    columns, _ = get_schema_and_column_names(frame)
    column_set = set(columns)
    text_expr = _composed_text_expr(column_set, record_type=record_type)
    category_expr = _category_norm_expr(column_set)

    result = frame.with_columns(
        text_expr.alias("_hybrid_claim_text"),
        category_expr.alias("_hybrid_category"),
    )

    per_secondary_claim_cols: dict[str, list[str]] = {}
    per_secondary_match_cols: dict[str, list[str]] = {}

    for rule_index, rule in enumerate(_HYBRID_RULES):
        secondary_key = _hybrid_secondary_key(rule.secondary_category)
        match_col = f"_hybrid_claim_match_{rule_index}"
        claim_col = f"_hybrid_claim_detected_{rule_index}"
        primary_values = list(rule.primary_categories)
        in_primary_category_expr = pl.col("_hybrid_category").is_in(primary_values)
        result = result.with_columns(
            pl.when(in_primary_category_expr)
            .then(pl.col("_hybrid_claim_text").str.extract(rule.claim_regex, 1))
            .otherwise(pl.lit(None))
            .cast(pl.Utf8)
            .alias(match_col)
        )
        result = result.with_columns(
            (
                in_primary_category_expr
                & pl.col(match_col).is_not_null()
                & (pl.col(match_col) != "")
            ).alias(claim_col)
        )
        per_secondary_claim_cols.setdefault(secondary_key, []).append(claim_col)
        per_secondary_match_cols.setdefault(secondary_key, []).append(match_col)

    overlay_exprs: list[pl.Expr] = []
    for secondary_category in _SECONDARY_CATEGORY_KEYS:
        secondary_key = _hybrid_secondary_key(secondary_category)
        claim_cols = per_secondary_claim_cols.get(secondary_key, [])
        match_cols = per_secondary_match_cols.get(secondary_key, [])
        if claim_cols:
            claim_expr = pl.any_horizontal(
                [pl.col(col) for col in claim_cols]
            ).fill_null(False)
        else:
            claim_expr = pl.lit(False)
        evidence_expr = (
            pl.coalesce([pl.col(col) for col in match_cols])
            if match_cols
            else pl.lit(None)
        )
        overlay_exprs.extend(
            [
                claim_expr.cast(pl.Boolean).alias(
                    f"brand_claims_{secondary_key}_hybrid"
                ),
                pl.lit(False)
                .cast(pl.Boolean)
                .alias(f"inferred_{secondary_key}_hybrid"),
                claim_expr.cast(pl.Boolean).alias(f"also_{secondary_key}"),
                pl.when(claim_expr)
                .then(pl.lit(secondary_category))
                .otherwise(pl.lit(None))
                .cast(pl.Utf8)
                .alias(f"also_{secondary_key}_secondary_category"),
                pl.when(claim_expr)
                .then(pl.lit("brand_claim"))
                .otherwise(pl.lit(None))
                .cast(pl.Utf8)
                .alias(f"also_{secondary_key}_source"),
                pl.when(claim_expr)
                .then(evidence_expr)
                .otherwise(pl.lit(None))
                .cast(pl.Utf8)
                .alias(f"also_{secondary_key}_evidence"),
            ]
        )
    result = result.with_columns(overlay_exprs)

    helper_columns = ["_hybrid_claim_text", "_hybrid_category"]
    for claim_cols in per_secondary_claim_cols.values():
        helper_columns.extend(claim_cols)
    for match_cols in per_secondary_match_cols.values():
        helper_columns.extend(match_cols)
    result = result.drop(
        [column for column in helper_columns if column in result.columns]
    )
    return _ensure_overlay_columns(result)


def annotate_bronzer_blush_hybrid(
    frame: pl.DataFrame,
    *,
    record_type: str | None = None,
) -> pl.DataFrame:
    """Backwards-compatible wrapper for market hybrid overlay annotation."""
    return annotate_market_hybrid_claims(frame, record_type=record_type)
