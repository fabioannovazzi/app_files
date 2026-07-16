from __future__ import annotations

import logging
import os
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

__all__ = ["load_env_from_secrets_file"]

LOGGER = logging.getLogger(__name__)


def _discover_secrets_file() -> Path | None:
    """Locate the preferred host-local or fallback project secrets file."""
    here = Path(__file__).resolve()
    for parent in list(here.parents):
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            secrets_dir = parent / ".secrets"
            for filename in ("secrets.local.toml", "secrets.toml"):
                candidate = secrets_dir / filename
                if candidate.exists():
                    return candidate
    return None


def _normalize_secret_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def _should_clear_existing_env(key: str) -> bool:
    return key in {"RESEND_API_KEY", "RESEND_FROM_EMAIL"}


def _iter_secret_items(data: Mapping[str, Any]) -> Iterable[tuple[str, Any]]:
    """Yield secret key/value pairs, including nested table entries."""
    for key, value in data.items():
        if isinstance(value, Mapping):
            for nested_key, nested_value in value.items():
                yield nested_key, nested_value
        else:
            yield key, value


def _parse_simple_kv_file(secrets_path: Path) -> dict[str, Any]:
    """Parse a simple KEY=VALUE secrets file when TOML parsing fails."""
    data: dict[str, Any] = {}
    for raw_line in secrets_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = raw_value.strip()
        if value.startswith(('"', "'")) and value.endswith(('"', "'")):
            value = value[1:-1]
        elif "#" in value:
            value = value.split("#", 1)[0].strip()
        if value:
            data[key] = value
    return data


def load_env_from_secrets_file(path: Path | None = None) -> dict[str, str]:
    """Load discovered or explicit project secrets into environment variables."""
    secrets_path = path or _discover_secrets_file()
    if secrets_path is None:
        LOGGER.debug("No secrets.toml file discovered.")
        return {}
    try:
        data = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        LOGGER.debug("Secrets file not found at %s.", secrets_path)
        return {}
    except tomllib.TOMLDecodeError as exc:
        data = _parse_simple_kv_file(secrets_path)
        if data:
            LOGGER.info(
                "Parsed secrets file %s using simple key/value format.", secrets_path
            )
        else:
            LOGGER.warning(
                "Failed to parse secrets file %s as TOML: %s", secrets_path, exc
            )
            return {}

    loaded: dict[str, str] = {}
    secret_items = dict(_iter_secret_items(data))
    for key in list(os.environ):
        if key in secret_items or _should_clear_existing_env(key):
            os.environ.pop(key, None)
    for key, value in secret_items.items():
        normalized = _normalize_secret_value(value)
        if normalized is None:
            continue
        os.environ[key] = normalized
        loaded[key] = normalized

    if loaded:
        LOGGER.info("Loaded %s secrets from %s.", len(loaded), secrets_path)
    return loaded
