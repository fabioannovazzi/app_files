"""LLM-backed page classifier utilities."""

# isort: skip_file

from __future__ import annotations

import logging
import json
import os
from typing import Tuple

try:  # optional dependency
    from modules.llm.model_router import query_llm_return_json
except Exception as e:  # pragma: no cover - best effort
    logging.exception(e)
    query_llm_return_json = None  # type: ignore

SYSTEM_PROMPT = (
    "You classify pages from bank statements. Output strict JSON with keys: "
    "page_type \u2208 {'transaction','summary','other'}, confidence \u2208 [0,1]. "
    "Consider multilingual tokens. A transaction page contains many entries with booking/value dates and amounts; "
    "a summary page aggregates totals/fees/interests and often lacks per-entry dates. If uncertain, return 'other' with low confidence."
)

USER_TEMPLATE = (
    "LOCALE={{locale}}\n"
    "EXCERPT (top/middle/bottom snippets):\n{{PAGE_EXCERPT}}\nREPLY: JSON only."
)


class LLMPageClassifier:
    """Optional LLM-backed classifier for borderline pages."""

    def classify_excerpt(
        self, page_excerpt: str, locale: str | None = None
    ) -> Tuple[str, float]:
        if os.getenv("BANK_PARSE_LLM") != "1" or query_llm_return_json is None:
            return "other", 0.0
        prompt = USER_TEMPLATE.replace("{{locale}}", locale or "").replace(
            "{{PAGE_EXCERPT}}", page_excerpt
        )
        try:
            data = query_llm_return_json(SYSTEM_PROMPT, prompt)
            if not isinstance(data, dict):
                data = json.loads(str(data))
            label = data.get("page_type", "other")
            conf = float(data.get("confidence", 0.0))
            return label, conf
        except Exception as e:  # pragma: no cover - LLM failure
            logging.exception(e)
            return "other", 0.0
