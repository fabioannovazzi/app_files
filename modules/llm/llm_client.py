import logging
import os
from typing import Mapping

from openai import OpenAI

from modules.utilities.config import get_naming_params
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.utilities.session_context import session_state
from modules.utilities.ui_notifier import ui

LOGGER = logging.getLogger(__name__)
_SECRETS_LOADED = False


def _ensure_secrets_loaded() -> None:
    """Ensure secrets from `.secrets/secrets.toml` are loaded into env."""
    global _SECRETS_LOADED
    if _SECRETS_LOADED:
        return
    try:
        load_env_from_secrets_file()
    except Exception as exc:  # pragma: no cover - best effort
        LOGGER.warning("Failed to load secrets file: %s", exc)
    _SECRETS_LOADED = True


def _get_secret(name: str) -> str:
    """Return a secret value from session or environment."""
    _ensure_secrets_loaded()
    secrets = session_state.get("secrets")
    if isinstance(secrets, Mapping) and name in secrets:
        return secrets[name]
    env_value = os.environ.get(name)
    if env_value:
        return env_value
    fallback_env_keys = {
        "openAiKey": ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_APIKEY"),
    }
    for env_key in fallback_env_keys.get(name, ()):
        env_value = os.environ.get(env_key)
        if env_value:
            return env_value
    raise KeyError(
        "Missing secret for "
        f"{name}. Set it in session_state['secrets'] "
        f"or via environment variables ({', '.join(fallback_env_keys.get(name, (name,)))})."
    )


def initialize_openai_client():
    namingParams = get_naming_params()
    openAiKey = namingParams["openAiKey"]
    openaiClient = namingParams["openaiClient"]
    if openaiClient not in session_state or not session_state[openaiClient]:
        client = OpenAI(api_key=_get_secret(openAiKey), timeout=900.0)
        session_state[openaiClient] = client
        ui.caption("OpenAi client initialized.")
        return client
    else:
        return False


def initialize_client(modelChoice):
    namingParams = get_naming_params()
    openai = namingParams["openai"]

    if modelChoice == openai:
        return initialize_openai_client()
    raise ValueError(f"Unsupported LLM provider: {modelChoice!r}")


def get_openai_client():
    namingParams = get_naming_params()
    openaiClient = namingParams["openaiClient"]
    openai = namingParams["openai"]
    if openaiClient in session_state and session_state[openaiClient]:
        client = session_state[openaiClient]
    else:
        initialize_client(openai)
        client = session_state[openaiClient]
    return client
