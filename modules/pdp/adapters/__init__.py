from __future__ import annotations

from typing import Iterable, Protocol, Sequence

from ..models import EvidenceBlob, ParentProduct, Variant


class RetailerAdapter(Protocol):
    """Adapter hooks for retailer-specific quirks."""

    retailer: str

    def primary_id_from_url(self, url: str) -> str | None:
        ...

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        ...

    def retailer_specific_fixes(
        self,
        parent: ParentProduct | None,
        variants: list[Variant],
        profile_name: str | None = None,
    ) -> None:
        ...


class NullAdapter:
    """Default no-op adapter."""

    retailer = "generic"

    def primary_id_from_url(self, url: str) -> str | None:  # noqa: D401 - protocol compatibility
        return None

    def extra_blobs(self, html: str) -> tuple[EvidenceBlob, ...]:
        return ()

    def retailer_specific_fixes(
        self,
        parent: ParentProduct | None,
        variants: list[Variant],
        profile_name: str | None = None,
    ) -> None:
        return None


__all__ = ["NullAdapter", "RetailerAdapter"]
