from __future__ import annotations

"""FastAPI entrypoint that wires the full application factory."""

from modules.pdp.api import create_app
from modules.utilities.secrets_loader import load_env_from_secrets_file

__all__ = ["app", "create_app"]

load_env_from_secrets_file()
app = create_app()
