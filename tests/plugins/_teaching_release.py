"""Bind a completed native regression case to the exact packaged teaching kit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import pytest

__all__ = ["record_native_check", "prepared_kit"]


def prepared_kit(*keys: str):
    """Run replacement exercises only when those exact kits are shipped as v2."""
    root = Path(__file__).resolve().parents[2]
    plan = json.loads((root / "scripts/course_materials/release_plan.json").read_text())
    return pytest.mark.skipif(
        not set(keys).issubset(plan["prepared"]),
        reason="Replacement lesson deferred; retained published material has separate coverage",
    )


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
