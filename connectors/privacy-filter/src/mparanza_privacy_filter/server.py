"""Desktop MCP server over local stdio, with no web listener."""

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
    spec = service.settings.spec
    server = FastMCP(
        spec.title,
        instructions=(
            f"Optional local {spec.title} connector. Use only when requested. "
            "Pass paths to local files; do not read originals into chat first. "
            "filter_file and filter_batch save plain UTF-8 .txt artifacts. "
            "read_result reads only those filtered artifacts. No layout preservation. "
            "Check capabilities.cross_document before reusing a session across files. "
            "Lethe and PII-Shield reuse one job session. Rizzo creates a separate session automatically "
            "for every document; retain the returned session_id for restoration. "
            "Mappings remain local and authoritative to the anonymizer. Restore returns only a path; "
            "never open restored identities in model context. "
            "Detection can miss data; review the copy "
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

    def filter_file(path: str, session_id: str | None = None) -> dict[str, Any]:
        """Filter one file in the configured input directory. Return its artifact ID."""
        try:
            return service.filter_file(path, session_id)
        except FilterError as exc:
            raise ToolError(str(exc)) from None

    def filter_batch(paths: list[str], session_id: str | None = None) -> dict[str, Any]:
        """Filter 1–5 explicit local paths; return each result by input index."""
        try:
            return service.filter_batch(paths, session_id)
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

    def create_session(state_path: str | None = None) -> dict[str, Any]:
        """Create a local pseudonymization job. Lethe needs an approved review file path."""
        try:
            return service.create_session(state_path)
        except (FilterError, OSError):
            raise ToolError("session_creation_failed") from None

    def open_session(session_id: str) -> dict[str, Any]:
        """Reopen the exact session; return metadata only, never identity mappings."""
        try:
            return service.open_session(session_id)
        except FilterError as exc:
            raise ToolError(str(exc)) from None

    def restore_file(session_id: str, path: str) -> dict[str, Any]:
        """Restore a local AI-output file using this session; return path only. Do not read the restored file into chat."""
        try:
            return service.restore_file(session_id, path)
        except (FilterError, OSError):
            raise ToolError("restoration_failed") from None

    if spec.reversible:
        server.add_tool(
            create_session, name=f"{spec.prefix}_session_create", annotations=writes
        )
        server.add_tool(
            open_session, name=f"{spec.prefix}_session_open", annotations=read_only
        )
        server.add_tool(restore_file, name=f"{spec.prefix}_restore", annotations=writes)
    server.add_tool(status, name=f"{spec.prefix}_status", annotations=read_only)
    server.add_tool(filter_file, name=f"{spec.prefix}_file", annotations=writes)
    server.add_tool(filter_batch, name=f"{spec.prefix}_batch", annotations=writes)
    server.add_tool(read_result, name=f"{spec.prefix}_read", annotations=read_only)
    return server


def main() -> None:
    """Start with explicit input/output/model directories and no automatic setup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--engine",
        choices=("openai", "gliner2", "rizzo", "lethe", "pii-shield"),
        default="openai",
    )
    parser.add_argument("--rizzo-port", type=int, default=5005)
    args = parser.parse_args()
    if args.engine != "rizzo" and args.model_dir is None:
        parser.error("--model-dir is required for this engine")
    try:
        service = FilterService(
            Settings(
                args.input_dir,
                args.output_dir,
                args.model_dir or args.output_dir / ".rizzo-state",
                args.device,
                args.engine,
                args.rizzo_port,
            )
        )
    except (OSError, FilterError):
        parser.exit(2, "Privacy Filter: invalid local directory configuration.\n")
    create_server(service).run(transport="stdio")


if __name__ == "__main__":
    main()
