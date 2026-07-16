from modules.utilities.config import get_naming_params


def test_query_llm_return_json_disables_json_mode_for_web_search(monkeypatch):
    import modules.llm.model_router as mr

    naming = get_naming_params()
    monkeypatch.setattr(mr, "get_naming_params", lambda: naming)
    monkeypatch.setattr(
        mr,
        "select_provider",
        lambda step: {
            "provider": naming["openai"],
            "model": naming["gpt5Main"],
        },
    )
    captured = {}

    def fake_get_completion_chart_message_openai(*args, **kwargs):
        captured["json_mode"] = kwargs.get("json_mode")
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(
        mr,
        "get_completion_chart_message_openai",
        fake_get_completion_chart_message_openai,
    )

    class DummyWrapper:
        def _call_llm(self, real_llm_func, **kwargs):
            return real_llm_func(service_tier=kwargs.get("service_tier"))

    wrapper = DummyWrapper()

    result = mr.query_llm_return_json(
        wrapper,
        query_step="step",
        prompt_system="sys",
        prompt_user="user",
        tools=[{"type": "web_search_preview"}],
    )

    assert captured["json_mode"] is False
    assert result == {}


def test_query_llm_return_json_appends_json_keyword(monkeypatch):
    import modules.llm.model_router as mr

    naming = get_naming_params()
    monkeypatch.setattr(mr, "get_naming_params", lambda: naming)
    monkeypatch.setattr(
        mr,
        "select_provider",
        lambda step: {
            "provider": naming["openai"],
            "model": naming["gpt5Main"],
        },
    )
    captured = {}

    def fake_get_completion_chart_message_openai(*args, **kwargs):
        captured["prompt_user"] = args[1]
        captured["json_mode"] = kwargs.get("json_mode")
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(
        mr,
        "get_completion_chart_message_openai",
        fake_get_completion_chart_message_openai,
    )

    class DummyWrapper:
        def _call_llm(self, real_llm_func, **kwargs):
            return real_llm_func(service_tier=kwargs.get("service_tier"))

    wrapper = DummyWrapper()

    mr.query_llm_return_json(
        wrapper, query_step="step", prompt_system="sys", prompt_user="user"
    )

    assert captured["json_mode"] is True
    assert "json" in captured["prompt_user"].lower()


def test_query_llm_return_json_appends_when_only_uppercase(monkeypatch):
    import modules.llm.model_router as mr

    naming = get_naming_params()
    monkeypatch.setattr(mr, "get_naming_params", lambda: naming)
    monkeypatch.setattr(
        mr,
        "select_provider",
        lambda step: {
            "provider": naming["openai"],
            "model": naming["gpt5Main"],
        },
    )
    captured = {}

    def fake_get_completion_chart_message_openai(*args, **kwargs):
        captured["prompt_user"] = args[1]
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(
        mr,
        "get_completion_chart_message_openai",
        fake_get_completion_chart_message_openai,
    )

    class DummyWrapper:
        def _call_llm(self, real_llm_func, **kwargs):
            return real_llm_func(service_tier=kwargs.get("service_tier"))

    wrapper = DummyWrapper()

    mr.query_llm_return_json(
        wrapper,
        query_step="step",
        prompt_system="Reply in JSON only",
        prompt_user="Some prompt",
    )

    assert "json" in captured["prompt_user"]


def test_query_llm_return_json_appends_when_json_in_system_only(monkeypatch):
    import modules.llm.model_router as mr

    naming = get_naming_params()
    monkeypatch.setattr(mr, "get_naming_params", lambda: naming)
    monkeypatch.setattr(
        mr,
        "select_provider",
        lambda step: {
            "provider": naming["openai"],
            "model": naming["gpt5Main"],
        },
    )
    captured = {}

    def fake_get_completion_chart_message_openai(*args, **kwargs):
        captured["prompt_user"] = args[1]
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(
        mr,
        "get_completion_chart_message_openai",
        fake_get_completion_chart_message_openai,
    )

    class DummyWrapper:
        def _call_llm(self, real_llm_func, **kwargs):
            return real_llm_func(service_tier=kwargs.get("service_tier"))

    wrapper = DummyWrapper()

    system_prompt = "Return result as a json object"
    mr.query_llm_return_json(
        wrapper, query_step="step", prompt_system=system_prompt, prompt_user="data"
    )

    assert "json" in captured["prompt_user"].lower()
