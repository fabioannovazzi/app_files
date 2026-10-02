"""Codex desktop MCP server over local stdio, with no web listener."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from .contracts import FilterError
from .service import FilterService, Settings

__all__ = ["create_server", "main"]


def create_server(service: FilterService) -> FastMCP:
    """Expose only filtered artifacts and non-identifying processing metadata."""
    server = FastMCP(
        "Privacy Filter",
        instructions=(
            "Optional local OpenAI Privacy Filter connector. Use only when requested. "
            "Pass paths to local files; do not read originals into chat first. "
            "filter_file and filter_batch save plain UTF-8 .txt artifacts. "
            "read_result reads only those filtered artifacts. No layout preservation. "
            "Detection can miss data, especially outside English; review the copy "
            "locally before sharing it. A completed run is not an anonymity guarantee."
        ),
        log_level="ERROR",
    )
    read_only = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
    writes = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )

    def status() -> dict[str, Any]:
        """Check local model readiness and supported file formats; no download."""
        return service.status()

    def filter_file(path: str) -> dict[str, Any]:
        """Filter one file in the configured input directory. Return its artifact ID."""
        try:
            return service.filter_file(path)
        except FilterError as exc:
            raise ToolError(str(exc)) from None

    def filter_batch(paths: list[str]) -> dict[str, Any]:
        """Filter 1–5 explicit local paths; return each result by input index."""
        try:
            return service.filter_batch(paths)
        except FilterError as exc:
            raise ToolError(str(exc)) from None

    def read_result(
        artifact_id: str, offset: int = 0, limit: int = 8000
    ) -> dict[str, Any]:
        """Read filtered text only, up to 16,000 characters from a saved artifact."""
        try:
            return service.read_result(artifact_id, offset, limit)
        except FilterError as exc:
            raise ToolError(str(exc)) from None

    server.add_tool(status, name="privacy_filter_status", annotations=read_only)
    server.add_tool(filter_file, name="privacy_filter_file", annotations=writes)
    server.add_tool(filter_batch, name="privacy_filter_batch", annotations=writes)
    server.add_tool(read_result, name="privacy_filter_read", annotations=read_only)
    return server


def main() -> None:
    """Start with explicit input/output/model directories and no automatic setup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    try:
        service = FilterService(
            Settings(args.input_dir, args.output_dir, args.model_dir, args.device)
        )
    except (OSError, FilterError):
        parser.exit(2, "Privacy Filter: invalid local directory configuration.\n")
    create_server(service).run(transport="stdio")


if __name__ == "__main__":
    main()
