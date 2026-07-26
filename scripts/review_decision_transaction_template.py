from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

__all__ = [
    "APPLY_HELPERS_END",
    "APPLY_HELPERS_START",
    "REVIEW_OUTPUT_TRANSACTION_HELPER",
    "SAVE_HELPERS_END",
    "SAVE_HELPERS_START",
    "TRANSACTION_HELPER_END",
    "TRANSACTION_HELPER_START",
    "marked_javascript_block",
    "upsert_review_output_transaction",
    "upsert_marked_javascript_block",
]

TRANSACTION_HELPER_START = "// BEGIN GENERATED REVIEW OUTPUT TRANSACTION"
TRANSACTION_HELPER_END = "// END GENERATED REVIEW OUTPUT TRANSACTION"
SAVE_HELPERS_START = "// BEGIN GENERATED REVIEW SAVE HELPERS"
SAVE_HELPERS_END = "// END GENERATED REVIEW SAVE HELPERS"
APPLY_HELPERS_START = "// BEGIN GENERATED REVIEW APPLY HELPERS"
APPLY_HELPERS_END = "// END GENERATED REVIEW APPLY HELPERS"

_EMBEDDED_START = "// BEGIN EMBEDDABLE REVIEW OUTPUT TRANSACTION"
_EMBEDDED_END = "// END EMBEDDABLE REVIEW OUTPUT TRANSACTION"
_RUNTIME_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "vera_assurance"
    / "review_output_transaction.cjs"
)


def _embedded_runtime_source() -> str:
    """Load the canonical deterministic transaction runtime for generators."""

    source = _RUNTIME_PATH.read_text(encoding="utf-8")
    if source.count(_EMBEDDED_START) != 1 or source.count(_EMBEDDED_END) != 1:
        raise RuntimeError("Review output transaction runtime markers are invalid")
    _, remainder = source.split(_EMBEDDED_START, 1)
    body, _ = remainder.split(_EMBEDDED_END, 1)
    return body.strip()


# Byte-exact rollback, containment, and mode restoration are mechanical
# assurance requirements. Semantic review judgment remains outside this code.
REVIEW_OUTPUT_TRANSACTION_HELPER = _embedded_runtime_source()


def upsert_review_output_transaction(
    text: str,
    *,
    insert_before: Sequence[str],
) -> str:
    """Refresh embedded runtimes without duplicating imported/custom ones."""

    has_marker = TRANSACTION_HELPER_START in text or TRANSACTION_HELPER_END in text
    # Runtime ownership is mechanically explicit. Importing the canonical
    # module or defining the bounded Journal-Bank transaction must not also
    # create a second set of transaction functions in the same server.
    owns_runtime_elsewhere = (
        "require(REVIEW_TRANSACTION_RUNTIME)" in text
        or "function withOutputDirectoryTransaction(" in text
    )
    if not has_marker and owns_runtime_elsewhere:
        return text
    return upsert_marked_javascript_block(
        text,
        start=TRANSACTION_HELPER_START,
        body=REVIEW_OUTPUT_TRANSACTION_HELPER,
        end=TRANSACTION_HELPER_END,
        insert_before=insert_before,
    )


def marked_javascript_block(start: str, body: str, end: str) -> str:
    """Render one generator-owned JavaScript block."""

    return f"{start}\n{body.rstrip()}\n{end}\n"


def upsert_marked_javascript_block(
    text: str,
    *,
    start: str,
    body: str,
    end: str,
    insert_before: Sequence[str],
) -> str:
    """Replace only a marked block, or insert it before a stable anchor."""

    has_start = start in text
    has_end = end in text
    if has_start != has_end:
        raise RuntimeError(f"Incomplete generated block: {start}")
    if text.count(start) > 1 or text.count(end) > 1:
        raise RuntimeError(f"Duplicate generated block: {start}")
    rendered = marked_javascript_block(start, body, end)
    if has_start:
        start_index = text.index(start)
        end_index = text.index(end, start_index) + len(end)
        if text.find(start, start_index + len(start), end_index) != -1:
            raise RuntimeError(f"Nested generated block: {start}")
        suffix_index = end_index
        if suffix_index < len(text) and text[suffix_index] == "\n":
            suffix_index += 1
        return f"{text[:start_index]}{rendered}{text[suffix_index:]}"
    for anchor in insert_before:
        index = text.find(anchor)
        if index != -1:
            return f"{text[:index]}{rendered}\n{text[index:]}"
    raise RuntimeError(f"Could not insert generated block: {start}")
