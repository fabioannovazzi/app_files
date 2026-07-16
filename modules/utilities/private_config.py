"""Resolve deployment-private configuration without coupling it to Git."""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["resolve_private_config_path"]

_ENV_PRIVATE_CONFIG_DIR = "APP_PRIVATE_CONFIG_DIR"


def resolve_private_config_path(
    default_path: Path,
    *,
    filename: str,
    specific_env_var: str | None = None,
) -> Path:
    """Return a runtime config path, preferring explicit environment settings.

    Path selection is deterministic because deployment configuration must be
    mechanically auditable and must never depend on model interpretation.
    """

    if Path(filename).name != filename:
        raise ValueError("Private configuration filename must not contain a path.")

    if specific_env_var:
        specific_path = (os.environ.get(specific_env_var) or "").strip()
        if specific_path:
            return Path(specific_path).expanduser()

    private_config_dir = (os.environ.get(_ENV_PRIVATE_CONFIG_DIR) or "").strip()
    if private_config_dir:
        return Path(private_config_dir).expanduser() / filename

    return default_path
