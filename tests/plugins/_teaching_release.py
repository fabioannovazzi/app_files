"""Bind a completed native regression case to the exact packaged teaching kit."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

__all__ = ["record_native_check"]


def record_native_check(
    record_property: Callable[[str, str], None],
    *,
    root: Path,
    product: str,
    workflow: str,
    language: str,
    phase: str,
) -> None:
    """Call after native output assertions; this never attests learner success."""
    course = root / "plugins" / product / "assets/courses" / workflow / "course.json"
    record_property("teaching_kit", f"{product}/{workflow}/{language}/{phase}")
    record_property(
        "teaching_course_sha256", hashlib.sha256(course.read_bytes()).hexdigest()
    )
