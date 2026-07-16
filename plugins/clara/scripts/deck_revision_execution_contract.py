"""Shared execution contract for Clara deck-revision plans."""

from __future__ import annotations

__all__ = [
    "CHANGE_SCOPES",
    "EXECUTION_STRATEGIES",
    "MODEL_OR_HUMAN_EXECUTION_STRATEGIES",
    "PATCH_EXECUTION_STRATEGY",
    "SUCCESS_CRITERION_TYPES",
    "SUPPORTED_PATCH_OPERATIONS",
    "execution_strategy_requirement",
]

CHANGE_SCOPES = {
    "text",
    "layout",
    "visual",
    "storyline",
    "structure",
    "content",
    "unknown",
}

PATCH_EXECUTION_STRATEGY = "deterministic_patch"
EXECUTION_STRATEGIES = {
    PATCH_EXECUTION_STRATEGY,
    "model_assisted_edit",
    "slide_rebuild",
    "deck_restructure",
    "needs_human_decision",
}
MODEL_OR_HUMAN_EXECUTION_STRATEGIES = EXECUTION_STRATEGIES - {PATCH_EXECUTION_STRATEGY}

SUCCESS_CRITERION_TYPES = {
    "title_equals",
    "text_present",
    "text_absent",
    "slide_count_equals",
    "shape_position",
    "manual_review",
    "semantic_review",
}

SUPPORTED_PATCH_OPERATIONS = {
    "set_title_text",
    "set_shape_text",
    "replace_text",
    "add_textbox",
    "delete_shape",
    "move_shape",
}


def execution_strategy_requirement(strategy: str) -> str:
    """Return the next execution requirement for a validated strategy."""

    if strategy == PATCH_EXECUTION_STRATEGY:
        return (
            "requires supported target-bound application_patches and mechanical "
            "verification criteria"
        )
    if strategy == "model_assisted_edit":
        return (
            "requires Codex/model slide editing against the approved understanding "
            "and then verification"
        )
    if strategy == "slide_rebuild":
        return (
            "requires rebuilding the affected slide from the deck style, source "
            "materials, and approved change"
        )
    if strategy == "deck_restructure":
        return (
            "requires changing deck sequence or section structure before slide-level "
            "patches can be complete"
        )
    if strategy == "needs_human_decision":
        return "requires consultant/user decision before execution"
    return "requires a supported execution strategy"
