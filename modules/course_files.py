"""Serve historical course URLs from the build's single-copy download store."""

from __future__ import annotations

import json
from pathlib import Path

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

__all__ = ["CourseFiles"]


class CourseFiles(StaticFiles):
    """Rewrite exact published aliases while retaining StaticFiles HTTP behavior."""

    def __init__(self, directory: Path) -> None:
        super().__init__(directory=directory)
        mapping = directory / "file-aliases.json"
        self.aliases = json.loads(mapping.read_bytes())["aliases"]

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Keep old URLs and new cross-product hash URLs on the same stored bytes."""
        return await super().get_response(self.aliases.get(path, path), scope)
