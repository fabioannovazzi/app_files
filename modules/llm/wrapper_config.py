from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from modules.utilities.cache import get_cache_dir

__all__ = ["get_llm_step_config", "get_llm_wrapper_template"]


def _get_wrapper_cache_dir() -> Path:
    try:
        return get_cache_dir("llm")
    except PermissionError:  # pragma: no cover - fallback when cache unwritable
        return Path.cwd()


def get_llm_step_config() -> dict[str, str]:
    """Return the default per-step LLM mode configuration."""
    return {
        "attributeClassificationQuery": "live",
        "attributeDiscoveryQuery": "live",
        "attributeScoringQuery": "live",
        "categoryWebsiteLookup": "live",
        "checkEntriesQuery": "live",
        "deepResearchRun": "live",
        "inferColumnQuery": "live",
        "launchValidationReviewQuery": "live",
        "llmFallbackQuery": "live",
        "merchantBrandWebsiteLookup": "live",
        "pdpVisionAttributeQuery": "live",
        "pdpWebAttributeQuery": "live",
        "quickRewriteQuery": "live",
        "randomMovementsQuery": "live",
        "readImageTableQuery": "live",
        "reasonedJudgementQuery": "live",
        "slideOcrSemanticQuery": "live",
        "slideOcrResidualAuditQuery": "live",
        "slideOcrVisualCorrectionQuery": "live",
    }


def get_llm_wrapper_template() -> dict[str, Any]:
    """Return the canonical wrapper defaults used across runtimes."""
    cache_dir = _get_wrapper_cache_dir()
    return {
        "mode": "replay",
        "record_file": str(cache_dir / "record.json"),
        "step_config": copy.deepcopy(get_llm_step_config()),
    }
