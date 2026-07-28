"""Entrypoint for Mparanza's narrow hosted-service application."""

from __future__ import annotations

from modules.hosted_services.api import app, create_app

__all__ = ["app", "create_app"]
