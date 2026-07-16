"""CLI helper to generate taxonomy branches via LLM.

Usage example:
  PYTHONPATH=. python scripts/generate_taxonomy_branch.py \n      concealer highlighter --industry "Cosmetics in US" --ground
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, Sequence

from modules.utilities.config import get_naming_params


class HeadlessLLMWrapper:
    """Minimal LLM wrapper to drive the taxonomy generator from CLI."""

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
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s:%(lineno)d | %(message)s",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate taxonomy branches for new categories.",
    )
    parser.add_argument(
        "categories",
        nargs="+",
        help="One or more category names to generate.",
    )
    parser.add_argument(
        "--industry",
        help="Industry context to inject into the prompt.",
    )
    parser.add_argument(
        "--industry-description",
        help="Expanded description for the industry.",
    )
    parser.add_argument(
        "--company",
        help="Company name to include in prompts.",
    )
    parser.add_argument(
        "--ground",
        action="store_true",
        help="Attempt web grounding after generation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display branches without saving to taxonomy storage.",
    )
    return parser.parse_args()


def _build_llm_callable(
    llm_wrapper,
    query_step: str,
    *,
    reasoning: str = "high",
) -> Callable[[str], Dict]:
    from modules.llm.model_router import query_llm_return_json

    system_prompt = "You are an expert in product taxonomies. Return JSON only."

    def _call(prompt: str) -> Dict:
        result = query_llm_return_json(
            llm_wrapper,
            query_step,
            system_prompt,
            prompt,
            reasoning_effort=reasoning,
        )
        return result if isinstance(result, dict) else {}

    return _call


def main() -> int:
    args = _parse_args()
    _configure_logging()
    categories: Sequence[str] = tuple(args.categories or [])
    if not categories:
        logging.error("No categories provided.")
        return 1


    from modules.add_attributes.attribute_taxonomy import (
        get_attribute_taxonomy,
        save_attribute_taxonomy,
    )
    from modules.add_attributes.generate_taxonomy import generate_category_taxonomy
    from modules.add_attributes.grounding import ground_branch_with_web

    taxonomy = get_attribute_taxonomy()
    naming = get_naming_params()

    llm_wrapper = HeadlessLLMWrapper(
        mode="live",
        step_config={
            key: "live"
            for key in naming.keys()
            if key.endswith("Query")
        },
    )

    llm_call = _build_llm_callable(
        llm_wrapper,
        query_step=naming["taxonomyGenerationQuery"],
        reasoning="high",
    )

    updated = False
    logging.info(
        "Generating taxonomy branches. Hold tight—this uses the same LLM flow as the UI,"
        " so you may see multiple prompts per category."
    )

    for raw_category in categories:
        category = str(raw_category).strip()
        if not category:
            continue

        category_norm = category.lower()
        existing = taxonomy.get("categories", []) or []
        if any(
            str(cat.get("id", "")).strip().lower() == category_norm
            or str(cat.get("label", "")).strip().lower() == category_norm
            for cat in existing
        ):
            logging.info("[skip] Category '%s' already exists.", category)
            continue

        logging.info("[generate] Category '%s' ...", category)
        branch = generate_category_taxonomy(
            llm_call=llm_call,
            category_name=category,
            existing_data=taxonomy,
            example_count=2,
            perform_review=True,
            industry=args.industry,
            industry_description=args.industry_description,
            company=args.company,
        )

        if args.ground:
            try:
                branch = ground_branch_with_web(
                    llm_wrapper,
                    branch,
                    category,
                    service_tier=None,
                )
            except Exception as exc:  # pragma: no cover - grounding optional
                logging.warning("[warn] grounding failed for '%s': %s", category, exc)

        attrs = branch.get("attributes") or []
        if not attrs:
            logging.warning("[warn] No attributes generated for '%s'.", category)
            continue

        if args.dry_run:
            logging.info("%s", branch)
            continue

        taxonomy.setdefault("categories", []).append(branch)
        updated = True
        logging.info(
            "[ok] Added '%s' with %s attributes (%s).",
            category,
            len(attrs),
            dt.datetime.now(dt.timezone.utc).isoformat(),
        )

    if updated and not args.dry_run:
        save_attribute_taxonomy(taxonomy)
        logging.info("Saved updated taxonomy storage")

        script_path = Path(__file__).resolve().with_name("update_attribute_activity.py")
        try:
            subprocess.run([sys.executable, str(script_path)], check=True)
            logging.info("Updated attribute_activity.json")
        except Exception as exc:  # pragma: no cover - best effort
            logging.warning("[warn] Failed to update attribute_activity.json: %s", exc)
    elif not updated and not args.dry_run:
        logging.info("No new branches generated; taxonomy unchanged.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
