"""Small allowlisted response contract; upstream results never cross it."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FilteredDocument", "FilterError", "LABELS", "FORMATS", "MODEL_REVISION"]

MODEL_REVISION = "7ffa9a043d54d1be65afb281eddf0ffbe629385b"
FORMATS = (".txt", ".md", ".markdown", ".docx", ".pdf")
LABELS = frozenset(
    (
        "account_number",
        "private_address",
        "private_email",
        "private_person",
        "private_phone",
        "private_url",
        "private_date",
        "secret",
    )
)


class FilterError(ValueError):
    """A fixed error code safe to return through MCP without source details."""


@dataclass(frozen=True)
class FilteredDocument:
    """Only filtered text and non-identifying aggregate counts leave inference."""

    redacted_text: str
    detection_counts: dict[str, int]
    source_characters: int
