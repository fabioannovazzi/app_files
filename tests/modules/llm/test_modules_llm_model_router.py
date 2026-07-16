import types

import pytest

import modules.llm.model_router as mr
from modules.llm.model_router import (
    fallback_openai,
    query_llm_return_text,
)
from modules.utilities.config import get_naming_params


class DummyWrapper:
    """Minimal llm_wrapper that records kwargs and invokes the real func."""

    def __init__(self):
        self.calls = []

    def _call_llm(self, real_llm_func, **kwargs):
        self.calls.append(kwargs)
        # Forward kwargs to match the inner function signature (**kwargs)
        return real_llm_func(**kwargs)


def test_fallback_openai_calls_openai_and_extracts(monkeypatch):
    # Arrange
    naming = get_naming_params()
    model_name = naming["gpt5Main"]
    recorded = {}

    def fake_openai(sys_msg, user_msg, model, *args, **kwargs):
        recorded["args"] = (sys_msg, user_msg, model)
        recorded["kwargs"] = kwargs
        return {"raw": "anything"}

    def fake_extract(resp):
        assert resp == {"raw": "anything"}
        return "  hello world  "

    monkeypatch.setattr(mr, "get_completion_chart_message_openai", fake_openai)
    monkeypatch.setattr(mr, "extract_response", fake_extract)

    # Act
    out = fallback_openai("SYS", "USER", model_name)

    # Assert
    assert out == "hello world"
    assert recorded["args"] == ("SYS", "USER", model_name)
    # Only temperature must be passed explicitly
    assert recorded["kwargs"].get("temperature") == 0


def test_query_llm_return_text_openai_happy_path(monkeypatch):
    # Arrange
    naming = get_naming_params()

    def fake_get_naming_params():
        return naming

    def fake_select_provider(step):
        assert step == "step"
        return {"provider": naming["openai"], "model": naming["gpt5Main"]}

    recorded = {}

    def fake_openai(sys_msg, user_msg, model, tools, tool_choice, temperature=0, **_):
        recorded["args"] = (sys_msg, user_msg, model)
        recorded["tools"] = tools
        recorded["tool_choice"] = tool_choice
        recorded["temperature"] = temperature
        return "  TEXT  "

    def fake_extract(resp):
        return resp  # identity; verify .strip() behaviour

    monkeypatch.setattr(mr, "get_naming_params", fake_get_naming_params)
    monkeypatch.setattr(mr, "select_provider", fake_select_provider)
    monkeypatch.setattr(mr, "get_completion_chart_message_openai", fake_openai)
    monkeypatch.setattr(mr, "extract_response", fake_extract)

    wrapper = DummyWrapper()
    tools = [{"type": "function", "function": {"name": "ping"}}]
    tool_choice = {"type": "function", "function": {"name": "ping"}}

    # Act
    out = query_llm_return_text(
        wrapper, "step", "SYS", "USER", tools=tools, tool_choice=tool_choice
    )

    # Assert
    assert out == "TEXT"
    # LLM wrapper receives provider/model for logging/recording
    assert wrapper.calls[0]["provider"] == naming["openai"]
    assert wrapper.calls[0]["model"] == naming["gpt5Main"]
    # OpenAI call receives all key params and temperature=0
    assert recorded["args"] == ("SYS", "USER", naming["gpt5Main"])
    assert recorded["tools"] == tools
    assert recorded["tool_choice"] == tool_choice
    assert recorded["temperature"] == 0


def test_query_llm_return_text_none_wrapper_raises(monkeypatch):
    # Arrange
    # Minimal patch to avoid resolving real config if function validated wrapper first
    # Act / Assert
    with pytest.raises(ValueError) as exc:
        query_llm_return_text(
            None, "any", "SYS", "USER", tools=None, tool_choice="auto"
        )
    assert "llm_wrapper cannot be None" in str(exc.value)


def test_query_llm_return_text_unknown_provider_falls_back(monkeypatch):
    # Arrange
    naming = get_naming_params()

    def fake_get_naming_params():
        return naming

    calls = []
    fallback_query = "llmFallbackQuery"

    def fake_select_provider(step):
        calls.append(step)
        if step == "step":
            return {"provider": "Other", "model": naming["gpt5Main"]}
        if step == fallback_query:
            return {"provider": naming["openai"], "model": naming["gpt5Main"]}
        raise AssertionError(f"Unexpected step: {step}")

    called = {}

    def fake_fallback(sys_msg, user_msg, model):
        called["args"] = (sys_msg, user_msg, model)
        return "fallback-text"

    monkeypatch.setattr(mr, "get_naming_params", fake_get_naming_params)
    monkeypatch.setattr(mr, "select_provider", fake_select_provider)
    monkeypatch.setattr(mr, "fallback_openai", fake_fallback)

    wrapper = DummyWrapper()

    # Act
    out = query_llm_return_text(wrapper, "step", "S", "U")

    # Assert
    assert out == "fallback-text"

    assert called["args"] == ("S", "U", naming["gpt5Main"])
    assert calls == ["step", fallback_query]
