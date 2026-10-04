"""Make the contributed engine importable when tests run from the repository."""

from __future__ import annotations

import sys
from pathlib import Path

__all__: list[str] = []

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
