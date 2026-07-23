"""Hosted WhatsApp Business ingestion and read-only MCP connector."""

from __future__ import annotations

from .api import router, well_known_router

__all__ = ["router", "well_known_router"]
