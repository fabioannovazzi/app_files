"""Version metadata and cache policy for public plugin ZIPs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile, ZipFile

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

__all__ = ["register_plugin_downloads"]


def register_plugin_downloads(app: FastAPI) -> None:
    """Attach download metadata and HTTP revalidation to the production app."""
    plugin_downloads = {
        f"/static/shared/{product}/downloads/{product}{suffix}-plugin.zip"
        for product in ("vera", "clara", "lucia")
        for suffix in ("", "-cowork")
    }

    @app.middleware("http")
    async def revalidate_plugin_downloads(request: Request, call_next):
        response = await call_next(request)
        if request.url.path in plugin_downloads:
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/plugin-downloads/{product}/{host}", include_in_schema=False)
    def plugin_download_version(
        product: Literal["vera", "clara", "lucia"], host: Literal["codex", "cowork"]
    ) -> JSONResponse:
        """Report the manifest inside the ZIP served by this deployment."""
        if host == "codex":
            filename = f"{product}-plugin.zip"
            manifest_path = (
                f"{product}-codex-plugin/plugins/{product}/.codex-plugin/plugin.json"
            )
        else:
            filename = f"{product}-cowork-plugin.zip"
            manifest_path = ".claude-plugin/plugin.json"
        path = Path("static/shared") / product / "downloads" / filename
        headers = {"Cache-Control": "no-store"}
        try:
            with ZipFile(path) as archive:
                manifest = json.loads(archive.read(manifest_path))
            if manifest["name"] != product or not isinstance(manifest["version"], str):
                raise ValueError("Invalid plugin identity or version")
        except (BadZipFile, KeyError, OSError, TypeError, ValueError):
            return JSONResponse({"detail": "ZIP unavailable"}, 503, headers=headers)
        return JSONResponse(
            {"name": product, "version": manifest["version"]}, headers=headers
        )
