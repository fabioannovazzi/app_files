from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

import polars as pl

ROOT_DIR = Path(__file__).resolve().parents[1]
ROOT_PATH = str(ROOT_DIR)
if ROOT_PATH in sys.path:
    sys.path.remove(ROOT_PATH)
sys.path.insert(0, ROOT_PATH)

from modules.pdp.postgres_compat import is_postgres_enabled
from modules.pdp.review_constants import DEFAULT_PDP_STORE_PATH, enforce_default_pdp_store_path
from modules.pdp.run_status_notifications import (
    resolve_notification_recipients,
    send_run_notification,
)
from modules.utilities.config import get_naming_params
from modules.utilities.secrets_loader import load_env_from_secrets_file


class HeadlessLLMWrapper:
    """Lightweight LLM wrapper for headless CLI execution."""

    def __init__(self, *, mode: str = "live", step_config: dict | None = None) -> None:
        self.mode = mode
        self.step_config = step_config or {}

    def _call_llm(
        self,
        *,
        real_llm_func,
        query_step: str,
        prompt_system: str,
        prompt_user: str,
        **kwargs,
    ):
        return real_llm_func(**kwargs)


def _configure_logging() -> None:
    level_name = os.environ.get("EXPORT_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_dir = Path("logs")
    log_path = log_dir / "export_pdp_attributes.log"

    formatter = logging.Formatter("%(levelname)s %(name)s:%(lineno)d | %(message)s")

    handlers: list[logging.Handler] = []
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except Exception:
        # Fall back to console-only if we cannot write the log file.
        pass

    console_handler = logging.StreamHandler()
    # Surface the same level to the console so progress is visible when running the CLI.
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)

    logging.getLogger("modules.add_attributes.pdp_attribute_export").setLevel(level)


def _log_duplicate_keys(df: pl.DataFrame, *, subset: Sequence[str], label: str) -> None:
    if df.is_empty():
        logging.info("%s: no rows to check for duplicates.", label)
        return
    missing = [col for col in subset if col not in df.columns]
    if missing:
        logging.warning(
            "%s: cannot check duplicates; missing columns=%s", label, missing
        )
        return
    duplicate_rows = df.height - df.unique(subset=list(subset)).height
    if duplicate_rows <= 0:
        logging.info("%s: no duplicate keys on %s", label, list(subset))
        return
    top_groups = (
        df.group_by(list(subset))
        .len()
        .filter(pl.col("len") > 1)
        .sort("len", descending=True)
        .head(10)
        .to_dicts()
    )
    logging.warning(
        "%s: duplicate keys detected on %s (duplicate_rows=%s top=%s)",
        label,
        list(subset),
        duplicate_rows,
        top_groups,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persist deterministic attributes derived from parsed PDPs.",
    )
    parser.add_argument(
        "--retailer",
        action="append",
        help="Restrict export to one or more retailers (case-insensitive).",
    )
    parser.add_argument(
        "--category",
        action="append",
        help="Process only these normalized category keys (use multiple times).",
    )
    parser.add_argument(
        "--categories",
        action="append",
        dest="category",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--deterministic-only",
        action="store_true",
        help="Skip the LLM pass and run deterministic extraction only.",
    )
    parser.add_argument(
        "--run-vlm",
        action="store_true",
        help=(
            "After persisting deterministic/LLM results, run the PDP image/VLM "
            "mapping step for the same retailer/category scope without the "
            "web-search pass."
        ),
    )
    parser.add_argument(
        "--parent-id",
        action="append",
        dest="parent_id",
        help="Limit processing to one or more parent_product_id values (debug only).",
    )
    parser.add_argument(
        "--dump-llm-json",
        type=Path,
        help="When set, append every raw LLM response to this JSONL file (debug only).",
    )
    parser.add_argument(
        "--clear-retailer",
        action="store_true",
        help="When set, drop cached/store rows for the specified retailers before writing results (even if zero rows).",
    )
    parser.add_argument(
        "--skip-amazon-family-aggregation",
        action="store_true",
        help=(
            "Skip automatic Amazon variant->parent family aggregation that runs "
            "after export for Amazon-scoped runs."
        ),
    )
    parser.add_argument(
        "--notify-email",
        action="append",
        default=None,
        help=(
            "Optional run-notification recipient (repeatable). "
            "Can also be set via PDP_RUN_NOTIFY_EMAILS."
        ),
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Disable run-notification emails for this invocation.",
    )
    parser.add_argument(
        "--no-llm-batch",
        action="store_true",
        help="Disable OpenAI Batch mode for this invocation.",
    )
    return parser.parse_args()


def _normalized_retailer_scope(retailers: Sequence[str] | None) -> set[str]:
    if not retailers:
        return set()
    return {
        str(retailer).strip().lower() for retailer in retailers if str(retailer).strip()
    }


def _should_auto_aggregate_amazon(retailers: Sequence[str] | None) -> bool:
    if retailers is None:
        # "all retailers" includes Amazon.
        return True
    scope = _normalized_retailer_scope(retailers)
    return scope == {"amazon"}


def _run_amazon_family_aggregation(
    *,
    pdp_store_path: Path,
    categories: Sequence[str] | None,
) -> None:
    from scripts.aggregate_product_families import (
        main as aggregate_product_families_main,
    )

    argv: list[str] = [
        "--retailer",
        "amazon",
        "--pdp-store-path",
        str(pdp_store_path),
    ]
    if categories:
        for category in categories:
            value = str(category).strip()
            if value:
                argv.extend(["--category", value])

    logging.info(
        "Running Amazon product-family aggregation after attribute export (args=%s).",
        argv,
    )
    exit_code = aggregate_product_families_main(argv)
    if exit_code != 0:
        raise RuntimeError(
            f"Amazon product-family aggregation failed with exit code {exit_code}"
        )


def _build_llm_wrapper(*, deterministic_only: bool) -> HeadlessLLMWrapper | None:
    if deterministic_only:
        return None
    naming = get_naming_params()
    step_keys = [key for key in naming.keys() if key.endswith("Query")]
    step_config = {key: "live" for key in step_keys}
    return HeadlessLLMWrapper(mode="live", step_config=step_config)


def _disable_llm_batch_mode() -> None:
    from modules.llm import model_router

    original_get_run_params = model_router.get_run_params

    def _get_run_params_without_batch() -> dict:
        params = dict(original_get_run_params())
        params["llmBatchMode"] = False
        return params

    model_router.get_run_params = _get_run_params_without_batch


def _export_attribute_frames(
    *,
    pdp_store_path: Path,
    retailers: Sequence[str] | None,
    categories: Sequence[str] | None,
    deterministic_only: bool,
    parent_filter: Sequence[str] | None,
    llm_dump_path: Path | None,
    clear_retailer: bool,
):
    from modules.add_attributes.pdp_attribute_export import export_pdp_attributes

    return export_pdp_attributes(
        pdp_store_path=pdp_store_path,
        retailers=retailers,
        categories=categories,
        llm_wrapper=_build_llm_wrapper(deterministic_only=deterministic_only),
        parent_filter=parent_filter,
        llm_dump_path=llm_dump_path,
        clear_retailer=clear_retailer,
    )


def _run_vlm_attribute_mapping(
    *,
    retailers: Sequence[str] | None,
    categories: Sequence[str] | None,
) -> None:
    from modules.pdp.attribute_mapping_runner import run_attribute_mapping_vlm

    logging.info(
        "Running VLM mapping after export_pdp_attributes (retailers=%s, categories=%s).",
        retailers or "(all)",
        categories or "(all)",
    )
    run_attribute_mapping_vlm(retailers=retailers, categories=categories)


def main() -> int:
    args = _parse_args()
    pdp_store_path = enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH)
    retailers: Sequence[str] | None = tuple(args.retailer) if args.retailer else None
    categories = tuple(args.category) if args.category else None
    notify_recipients = (
        ()
        if args.no_notify
        else resolve_notification_recipients(args.notify_email)
    )
    started_at = dt.datetime.now(dt.timezone.utc)

    _configure_logging()
    load_env_from_secrets_file()
    logging.info(
        "Starting export_pdp_attributes (retailers=%s, categories=%s, deterministic_only=%s, run_vlm=%s)",
        retailers,
        categories,
        args.deterministic_only,
        args.run_vlm,
    )
    if args.no_llm_batch:
        _disable_llm_batch_mode()
        logging.info("OpenAI Batch mode disabled for this invocation.")
    send_run_notification(
        run_name="export_pdp_attributes",
        status="started",
        recipients=notify_recipients,
        started_at=started_at,
        details={
            "retailers": ",".join(retailers) if retailers else "(all)",
            "categories": ",".join(categories) if categories else "(all)",
            "deterministic_only": args.deterministic_only,
            "run_vlm": args.run_vlm,
            "clear_retailer": args.clear_retailer,
            "pdp_store_path": str(pdp_store_path),
        },
    )

    parent_count = 0
    variant_count = 0
    combined_count = 0
    parent_filter = tuple(args.parent_id) if args.parent_id else None
    postgres_enabled = is_postgres_enabled()
    if not postgres_enabled:
        detail = (
            "PDP Postgres is not configured. Set PDP_DATABASE_URL or set "
            "PDP_STORE_BACKEND=postgres with DATABASE_URL, and make sure the SSH "
            "tunnel is active. export_pdp_attributes.py no longer uses a local "
            "local PDP database fallback."
        )
        logging.error("%s", detail)
        send_run_notification(
            run_name="export_pdp_attributes",
            status="failed",
            recipients=notify_recipients,
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc),
            details={
                "retailers": ",".join(retailers) if retailers else "(all)",
                "categories": ",".join(categories) if categories else "(all)",
                "deterministic_only": args.deterministic_only,
                "run_vlm": args.run_vlm,
                "error": detail,
            },
            logger=logging.getLogger(__name__),
        )
        return 1

    try:
        parents_df, variants_df, combined_df, unmatched, unmatched_examples = (
            _export_attribute_frames(
                pdp_store_path=pdp_store_path,
                retailers=retailers,
                categories=categories,
                deterministic_only=args.deterministic_only,
                parent_filter=parent_filter,
                llm_dump_path=args.dump_llm_json,
                clear_retailer=args.clear_retailer,
            )
        )

        if args.run_vlm:
            _run_vlm_attribute_mapping(retailers=retailers, categories=categories)
            (
                parents_df,
                variants_df,
                combined_df,
                unmatched,
                unmatched_examples,
            ) = _export_attribute_frames(
                pdp_store_path=pdp_store_path,
                retailers=retailers,
                categories=categories,
                deterministic_only=True,
                parent_filter=parent_filter,
                llm_dump_path=None,
                clear_retailer=False,
            )

        _log_duplicate_keys(
            variants_df,
            subset=("retailer", "variant_id"),
            label="Catalog variants",
        )
        _log_duplicate_keys(
            parents_df,
            subset=("retailer", "parent_product_id"),
            label="Catalog parents",
        )

        parent_count = (
            parents_df.height if hasattr(parents_df, "height") else len(parents_df)
        )
        variant_count = (
            variants_df.height if hasattr(variants_df, "height") else len(variants_df)
        )
        combined_count = (
            combined_df.height if hasattr(combined_df, "height") else len(combined_df)
        )
        logging.info(
            "Persisted PDP attributes to the database "
            "(parents=%s variants=%s combined=%s).",
            parent_count,
            variant_count,
            combined_count,
        )
        if unmatched:
            logging.warning("Unmatched categories (check taxonomy mapping):")
            for normalized in sorted(unmatched):
                examples = ", ".join(
                    sorted(unmatched_examples.get(normalized, {"(missing category)"}))
                )
                label = normalized or "(missing category)"
                logging.warning("  - %s: %s", label, examples)

        should_aggregate_amazon = (
            not args.skip_amazon_family_aggregation
            and not parent_filter
            and _should_auto_aggregate_amazon(retailers)
        )
        if should_aggregate_amazon:
            _run_amazon_family_aggregation(
                pdp_store_path=pdp_store_path,
                categories=categories,
            )
        elif args.skip_amazon_family_aggregation:
            logging.info(
                "Skipped Amazon family aggregation because skip flag is enabled."
            )
        elif parent_filter:
            logging.info(
                "Skipped Amazon family aggregation because --parent-id filter is active."
            )
        else:
            logging.info(
                "Skipped Amazon family aggregation because retailer scope is not Amazon-only."
            )
    except Exception as exc:
        detail = str(exc)
        send_run_notification(
            run_name="export_pdp_attributes",
            status="failed",
            recipients=notify_recipients,
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc),
            details={
                "retailers": ",".join(retailers) if retailers else "(all)",
                "categories": ",".join(categories) if categories else "(all)",
                "deterministic_only": args.deterministic_only,
                "run_vlm": args.run_vlm,
                "error": detail,
            },
            logger=logging.getLogger(__name__),
        )
        raise

    else:
        success_details: dict[str, object] = {
            "retailers": ",".join(retailers) if retailers else "(all)",
            "categories": ",".join(categories) if categories else "(all)",
            "deterministic_only": args.deterministic_only,
            "run_vlm": args.run_vlm,
            "parent_rows": parent_count,
            "variant_rows": variant_count,
            "combined_rows": combined_count,
        }
        send_run_notification(
            run_name="export_pdp_attributes",
            status="success",
            recipients=notify_recipients,
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc),
            details=success_details,
            logger=logging.getLogger(__name__),
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
