import types

import httpx
import pytest
from openai import APITimeoutError

import modules.llm.llm_api as la

NAMING = {
    "o3": "o3",
    "deepResearchO3": "deepResearchO3",
    "deepResearchO4Mini": "deepResearchO4Mini",
    "gpt5Thinking": "gpt5Thinking",
    "gpt5ThinkingMini": "gpt5ThinkingMini",
    "gpt5ThinkingNano": "gpt5ThinkingNano",
    "gpt54Mini": "gpt54Mini",
    "gpt5Main": "test-model",
}


class DummyResponse:
    def __init__(self, content: str):
        self._content = content

    def model_dump(self):
        return {"choices": [{"message": {"content": self._content}}]}


def test_get_completion_chart_message_openai_retries_on_api_timeout(monkeypatch):
    monkeypatch.setattr(la, "get_naming_params", lambda: NAMING)

    class DummyClient:
        def __init__(self):
            self.calls = 0

            def create(*args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise APITimeoutError("timeout")
                return DummyResponse("OK")

            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=create)
            )

    client = DummyClient()
    monkeypatch.setattr(la, "get_openai_client", lambda: client)

    sleep_calls: list[int] = []

    def fake_sleep(duration: int):
        sleep_calls.append(duration)

    monkeypatch.setattr(la.time, "sleep", fake_sleep)

    model_name = "chat-completions-model"
    out = la.get_completion_chart_message_openai(
        "SYS", "USER", model_name, max_retries=2, service_tier="auto"
    )

    assert out == "OK"
    assert sleep_calls == [1]


def test_get_completion_chart_message_openai_propagates_last_error(monkeypatch):
    monkeypatch.setattr(la, "get_naming_params", lambda: NAMING)

    def always_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("boom")

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=always_timeout)
        )
    )
    monkeypatch.setattr(la, "get_openai_client", lambda: client)

    sleep_calls: list[int] = []
    monkeypatch.setattr(la.time, "sleep", lambda s: sleep_calls.append(s))

    model_name = "chat-completions-model"
    with pytest.raises(httpx.ReadTimeout):
        la.get_completion_chart_message_openai(
            "SYS", "USER", model_name, max_retries=2, service_tier="auto"
        )

    assert sleep_calls == [1]
