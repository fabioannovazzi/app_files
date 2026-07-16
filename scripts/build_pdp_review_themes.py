from __future__ import annotations

"""Build stratified-sample review themes and tag the full raw-review corpus."""

import argparse
import logging
import random
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
ROOT_PATH = str(ROOT_DIR)
if ROOT_PATH in sys.path:
    sys.path.remove(ROOT_PATH)
sys.path.insert(0, ROOT_PATH)

from modules.llm.llm_call_wrapper import init_llm_wrapper
from modules.pdp.postgres_compat import connect_pdp_database
from modules.pdp.review_constants import DEFAULT_PDP_STORE_PATH, enforce_default_pdp_store_path
from modules.pdp.review_theme_codebook import (
    REVIEW_THEME_PIPELINE_VERSION,
    ProductReviewContext,
    build_review_records_from_contexts,
    discover_review_theme_codebook,
    ensure_review_theme_schema,
    fetch_parent_review_context_rows,
    persist_review_theme_run,
    sample_reviews_by_stratum,
    tag_reviews_with_codebook,
)
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.utilities.session_context import SessionContext

LOGGER = logging.getLogger(__name__)

_TOP_SELLER_SORT_MODES = ("best_selling", "best_sellers", "top_sellers", "bestsellers")
_NEW_LAUNCH_SORT_MODES = ("new_arrivals", "newest", "most_recent")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a frozen review-theme codebook from stratified samples, then "
            "tag all raw reviews against that codebook."
        )
    )
    parser.add_argument("--retailer", required=True, help="Retailer key, e.g. chewy.")
    parser.add_argument(
        "--category",
        action="append",
        default=None,
        help="Category key to process. Repeat for multiple categories.",
    )
    parser.add_argument(
        "--brand",
        action="append",
        default=None,
        help=(
            "Optional brand used only to add a neutral target-brand discovery batch. "
            "The model does not see the brand stratum label."
        ),
    )
    parser.add_argument(
        "--parent-id",
        action="append",
        default=None,
        help="Optional debug scope: process only these parent_product_id values.",
    )
    parser.add_argument(
        "--limit-products",
        type=int,
        default=None,
        help="Optional canary cap on products with raw reviews.",
    )
    parser.add_argument(
        "--reviews-per-stratum",
        type=int,
        default=50,
        help="Review sample budget for each stratum used to discover the codebook.",
    )
    parser.add_argument(
        "--sample-stratum",
        action="append",
        choices=(
            "top_sellers",
            "non_top_sellers",
            "new_products",
            "successful_new_products",
            "target_brand",
            "weak_low_rated",
            "general_random",
        ),
        default=None,
        help=(
            "Optional discovery stratum. Repeat to restrict the codebook sample. "
            "Strata are used only to write the codebook."
        ),
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=42,
        help="Random seed for deterministic stratified sampling.",
    )
    parser.add_argument(
        "--max-themes",
        type=int,
        default=25,
        help="Hard maximum number of frozen codebook subthemes.",
    )
    parser.add_argument(
        "--max-parent-themes",
        type=int,
        default=10,
        help="Hard maximum number of parent themes in the frozen codebook.",
    )
    parser.add_argument(
        "--service-tier",
        default=None,
        help="Optional OpenAI service tier for review theme discovery/tagging.",
    )
    parser.add_argument(
        "--retry-missing",
        type=int,
        default=1,
        help="Retry count for missing batch tag responses.",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Stop after codebook discovery and print the frozen themes.",
    )
    parser.add_argument(
        "--force-sequential-tagging",
        action="store_true",
        help="Avoid Batch API for small interactive canaries.",
    )
    parser.add_argument(
        "--tag-batch-size",
        type=int,
        default=25,
        help="Reviews per LLM request during fixed-codebook tagging.",
    )
    parser.add_argument(
        "--tag-limit-reviews",
        type=int,
        default=None,
        help="Optional canary cap on reviews to tag after codebook discovery.",
    )
    return parser.parse_args()


def _normalize_text(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def _sort_mode_clause(sort_modes: Sequence[str]) -> str:
    return ",".join("?" for _ in sort_modes)


def _ranked_parent_ids(
    conn,
    *,
    retailer: str,
    category_key: str,
    contexts: Sequence[ProductReviewContext],
    sort_modes: Sequence[str],
    share: float = 0.20,
) -> set[str]:
    url_to_parent = {
        context.pdp_url: context.parent_product_id
        for context in contexts
        if context.pdp_url
    }
    if not url_to_parent:
        return set()
    placeholders = _sort_mode_clause(sort_modes)
    latest = conn.execute(
        f"""
        SELECT MAX(crawl_ts)
        FROM retailer_listing_observations
        WHERE retailer = ?
          AND category_key = ?
          AND lower(sort_mode) IN ({placeholders})
        """,
        (retailer, category_key, *[mode.lower() for mode in sort_modes]),
    ).fetchone()
    crawl_ts = latest[0] if latest else None
    if not crawl_ts:
        return set()
    rows = conn.execute(
        f"""
        SELECT pdp_url, page, position
        FROM retailer_listing_observations
        WHERE retailer = ?
          AND category_key = ?
          AND crawl_ts = ?
          AND lower(sort_mode) IN ({placeholders})
        ORDER BY page, position, pdp_url
        """,
        (retailer, category_key, crawl_ts, *[mode.lower() for mode in sort_modes]),
    ).fetchall()
    ranked: list[str] = []
    seen: set[str] = set()
    for pdp_url, _page, _position in rows:
        parent_id = url_to_parent.get(_normalize_text(pdp_url))
        if not parent_id or parent_id in seen:
            continue
        seen.add(parent_id)
        ranked.append(parent_id)
    limit = max(1, min(len(ranked), int(len(contexts) * share + 0.999)))
    return set(ranked[:limit])


def _with_rank_cohorts(
    conn,
    *,
    retailer: str,
    category_key: str,
    contexts: Sequence[ProductReviewContext],
) -> tuple[ProductReviewContext, ...]:
    top_ids = _ranked_parent_ids(
        conn,
        retailer=retailer,
        category_key=category_key,
        contexts=contexts,
        sort_modes=_TOP_SELLER_SORT_MODES,
    )
    new_ids = _ranked_parent_ids(
        conn,
        retailer=retailer,
        category_key=category_key,
        contexts=contexts,
        sort_modes=_NEW_LAUNCH_SORT_MODES,
    )
    return tuple(
        replace(
            context,
            is_top_seller=context.parent_product_id in top_ids,
            is_new_launch=context.parent_product_id in new_ids,
        )
        for context in contexts
    )


def _group_contexts_by_category(
    contexts: Sequence[ProductReviewContext],
) -> dict[str, tuple[ProductReviewContext, ...]]:
    grouped: dict[str, list[ProductReviewContext]] = {}
    for context in contexts:
        grouped.setdefault(context.category_key, []).append(context)
    return {key: tuple(value) for key, value in grouped.items()}


def _limit_contexts_for_canary(
    contexts: Sequence[ProductReviewContext],
    *,
    limit: int,
    seed: int,
) -> tuple[ProductReviewContext, ...]:
    if limit <= 0 or len(contexts) <= limit:
        return tuple(contexts)
    rng = random.Random(seed)
    top = [context for context in contexts if context.is_top_seller]
    other = [context for context in contexts if not context.is_top_seller]
    rng.shuffle(top)
    rng.shuffle(other)
    top_limit = min(len(top), max(1, limit // 2))
    picked = [*top[:top_limit]]
    remaining = limit - len(picked)
    picked.extend(other[:remaining])
    if len(picked) < limit:
        used = {context.parent_product_id for context in picked}
        leftovers = [
            context for context in contexts if context.parent_product_id not in used
        ]
        rng.shuffle(leftovers)
        picked.extend(leftovers[: limit - len(picked)])
    rng.shuffle(picked)
    return tuple(picked[:limit])


def _build_llm_wrapper() -> object:
    session = SessionContext.from_state({})
    init_llm_wrapper("", session=session)
    return session.state["llm_wrapper"]


def _run_scope(args: argparse.Namespace) -> str:
    if args.parent_id:
        return "canary"
    if args.limit_products is not None:
        return "canary"
    if args.tag_limit_reviews is not None:
        return "canary"
    if args.sample_stratum:
        return "canary"
    return "full"


def _run_category(
    conn,
    *,
    retailer: str,
    category_key: str,
    contexts: Sequence[ProductReviewContext],
    args: argparse.Namespace,
) -> None:
    scoped_contexts = _with_rank_cohorts(
        conn,
        retailer=retailer,
        category_key=category_key,
        contexts=contexts,
    )
    if args.limit_products is not None:
        scoped_contexts = _limit_contexts_for_canary(
            scoped_contexts,
            limit=args.limit_products,
            seed=args.sample_seed,
        )
    records = build_review_records_from_contexts(scoped_contexts)
    sampled = sample_reviews_by_stratum(
        records,
        reviews_per_stratum=args.reviews_per_stratum,
        seed=args.sample_seed,
        stratum_names=args.sample_stratum,
        focus_brands=args.brand,
    )
    LOGGER.info(
        "Review theme samples: retailer=%s category=%s products=%d reviews=%d %s",
        retailer,
        category_key,
        len(scoped_contexts),
        len(records),
        " ".join(f"{key}={len(value)}" for key, value in sampled.items()),
    )
    llm_wrapper = _build_llm_wrapper()
    themes = discover_review_theme_codebook(
        llm_wrapper,
        retailer=retailer,
        category_key=category_key,
        sampled_records_by_stratum=sampled,
        max_themes=args.max_themes,
        max_parent_themes=args.max_parent_themes,
        service_tier=args.service_tier,
    )
    for theme in themes:
        LOGGER.info(
            "Theme: parent=%s subtheme=%s id=%s",
            theme.theme_family,
            theme.theme_label,
            theme.theme_id,
        )
    if args.discover_only:
        LOGGER.info(
            "Review theme discovery-only complete: retailer=%s category=%s themes=%d",
            retailer,
            category_key,
            len(themes),
        )
        return
    tag_records = (
        records[: args.tag_limit_reviews]
        if args.tag_limit_reviews is not None
        else records
    )
    tags = tag_reviews_with_codebook(
        llm_wrapper,
        records=tag_records,
        themes=themes,
        service_tier=args.service_tier,
        retry_missing=args.retry_missing,
        force_sequential=args.force_sequential_tagging,
        tag_batch_size=args.tag_batch_size,
    )
    run_id = persist_review_theme_run(
        conn,
        retailer=retailer,
        category_key=category_key,
        records=tag_records,
        sampled_records_by_stratum=sampled,
        themes=themes,
        tags=tags,
        sample_seed=args.sample_seed,
        reviews_per_stratum=args.reviews_per_stratum,
        max_themes=args.max_themes,
        run_scope=_run_scope(args),
    )
    LOGGER.info(
        "Review theme run complete: run_id=%s retailer=%s category=%s reviews=%d themes=%d tags=%d pipeline=%s",
        run_id,
        retailer,
        category_key,
        len(tag_records),
        len(themes),
        len(tags),
        REVIEW_THEME_PIPELINE_VERSION,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s:%(lineno)d | %(message)s",
    )
    args = _parse_args()
    load_env_from_secrets_file()
    pdp_store_path = enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH)
    with connect_pdp_database(pdp_store_path) as conn:
        ensure_review_theme_schema(conn)
        contexts = fetch_parent_review_context_rows(
            conn,
            retailer=args.retailer,
            category_keys=args.category,
            parent_ids=args.parent_id,
        )
        grouped = _group_contexts_by_category(contexts)
        if not grouped:
            LOGGER.warning(
                "No raw review products found for retailer=%s categories=%s",
                args.retailer,
                ",".join(args.category or ()) or "all",
            )
            return
        for category_key, category_contexts in grouped.items():
            _run_category(
                conn,
                retailer=args.retailer,
                category_key=category_key,
                contexts=category_contexts,
                args=args,
            )
            conn.commit()


if __name__ == "__main__":
    main()
