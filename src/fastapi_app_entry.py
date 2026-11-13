"""Entrypoint for Mparanza's narrow hosted-service application."""

from __future__ import annotations

from modules.hosted_services.api import app, create_app

from modules.hosted_services.plugin_downloads import register_plugin_downloads

register_plugin_downloads(app)

__all__ = ["app", "create_app"]
