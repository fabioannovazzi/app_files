"""LLM helper functions."""

from __future__ import annotations

import json
import os
from typing import List

from .locale_utils import parse_date, parse_number
from .schema import Transaction


def extract_transactions_llm(block_text: str, locale_hint: str) -> List[Transaction]:
    """Attempt to parse transactions using an LLM.

    If the necessary environment variables are not set, this function returns
    an empty list.  The actual LLM call is intentionally left as a TODO.
    """

    if not os.getenv("LLM_API_KEY"):
        return []

    # TODO: Implement real LLM call; placeholder returns no transactions
    _ = (block_text, locale_hint)  # satisfy linters
    return []
