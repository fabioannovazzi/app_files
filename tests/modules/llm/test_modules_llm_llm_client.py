import importlib
import sys
import types
from pathlib import Path

import pytest

from modules.utilities.session_context import SessionContext, use_session_context


@pytest.fixture()
def llm_client_module(monkeypatch):
    """Provide a freshly imported OpenAI-only LLM client module."""
    # Stub openai
    openai_mod = types.ModuleType("openai")

    class DummyOpenAI:
        def __init__(self, api_key=None, timeout=None, base_url=None, **_):
            self.api_key = api_key
            self.timeout = timeout
            self.base_url = base_url

    openai_mod.OpenAI = DummyOpenAI
    monkeypatch.setitem(sys.modules, "openai", openai_mod)

    # Preload a lightweight 'modules.llm' package to avoid executing its __init__
    llm_pkg = types.ModuleType("modules.llm")
    llm_pkg.__path__ = [str(Path("modules/llm").resolve())]
    monkeypatch.setitem(sys.modules, "modules.llm", llm_pkg)

    # Reimport target module fresh each time
    if "modules.llm.llm_client" in sys.modules:
        monkeypatch.delitem(sys.modules, "modules.llm.llm_client", raising=False)
    mod = importlib.import_module("modules.llm.llm_client")
    return mod


def test_initialize_openai_client_creates_and_caches(llm_client_module):
    # Arrange
    mod = llm_client_module
    session = SessionContext.from_state({"secrets": {"openAiKey": "sk-open"}})

    # Act
    with use_session_context(session):
        client = mod.initialize_openai_client()

    # Assert
    assert client is session.state["openaiClient"]
    assert client.api_key == "sk-open"
    assert client.timeout == 900.0


def test_initialize_openai_client_returns_false_when_cached(llm_client_module):
    # Arrange: simulate already-initialized client in session_state
    mod = llm_client_module
    existing = object()
    session = SessionContext.from_state({"openaiClient": existing})

    # Act
    with use_session_context(session):
        result = mod.initialize_openai_client()

    # Assert
    assert result is False
    assert session.state["openaiClient"] is existing


def test_initialize_client_rejects_unsupported_provider(llm_client_module):
    mod = llm_client_module

    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        mod.initialize_client("unsupported")
