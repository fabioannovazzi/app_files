"""Product-owner choices about which workflows can run as local lessons."""

from __future__ import annotations

__all__ = ["unavailable_local_workflows", "local_unavailability"]


def unavailable_local_workflows(product: str) -> frozenset[str]:
    """Return explicit local teaching exclusions, not professional routing rules."""
    if product == "clara":
        return frozenset({"brand-fit", "hosted-interview", "research-video"})
    return frozenset()


def local_unavailability(product: str, workflow: object) -> str | None:
    """Explain an unavailable lesson without claiming its workflow is absent."""
    if isinstance(workflow, str) and workflow in unavailable_local_workflows(product):
        return (
            "This Clara workflow requires hosted services and is unavailable in "
            "local lessons. Choose another local lesson; the normal professional "
            "workflow remains separate."
        )
    return None
