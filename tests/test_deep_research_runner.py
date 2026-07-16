import logging

import pytest

from modules.utilities.session_context import SessionContext

def test_runs_must_be_positive_raises_value_error():
    from src.deep_research_runner import run_parallel_deep_research

    with pytest.raises(ValueError):
        run_parallel_deep_research("hello", runs=0, llm_wrapper=object())


def test_sequential_path_calls_run_step_json_with_web_search_and_throttle(monkeypatch):
    from src.deep_research_runner import run_parallel_deep_research

    calls = []
    sleep_calls = []

    def fake_sleep(seconds):
        sleep_calls.append(seconds)

    def fake_run_step_json(
        llm_wrapper,
        step,
        system_prompt,
        prompt_user,
        *,
        tools=None,
        tool_choice="auto",
        **kwargs,
    ):
        calls.append(
            {
                "llm_wrapper": llm_wrapper,
                "step": step,
                "system_prompt": system_prompt,
                "prompt_user": prompt_user,
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        return [{"ok": True, "idx": len(calls) - 1}]

    monkeypatch.setattr("modules.llm.batch_runner.run_step_json", fake_run_step_json)
    monkeypatch.setattr("time.sleep", fake_sleep)

    prompt = "What is deep research?"
    wrapper = object()
    runs = 3
    out = run_parallel_deep_research(
        prompt, runs=runs, throttle=0.1, llm_wrapper=wrapper
    )

    # Assert: returned one result per run in order
    assert isinstance(out, list) and len(out) == runs
    assert [r["idx"] for r in out] == list(range(runs))

    # Assert: throttle slept between runs (runs - 1 times)
    assert len(sleep_calls) == runs - 1

    # Assert: each call used the expected step, prompts and tools
    assert all(c["step"] == "deepResearchRun" for c in calls)
    assert all(c["system_prompt"] == "" for c in calls)
    assert all(c["prompt_user"] == prompt for c in calls)
    # Only the configured web search tool when code_interpreter is False
    assert all(c["tools"] == [{"type": "web_search_preview"}] for c in calls)
    assert all(c["tool_choice"] == "auto" for c in calls)
    assert all(c["llm_wrapper"] is wrapper for c in calls)


def test_uses_session_state_wrapper_and_adds_code_interpreter_tool(monkeypatch):
    sentinel_wrapper = object()
    session = SessionContext.from_state({"llm_wrapper": sentinel_wrapper})

    captured = {}

    def fake_run_step_json(
        llm_wrapper,
        step,
        system_prompt,
        prompt_user,
        *,
        tools=None,
        tool_choice="auto",
        **kwargs,
    ):
        captured.update(
            {
                "llm_wrapper": llm_wrapper,
                "step": step,
                "system_prompt": system_prompt,
                "prompt_user": prompt_user,
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        return [{"ok": True}]

    monkeypatch.setattr("modules.llm.batch_runner.run_step_json", fake_run_step_json)

    from src.deep_research_runner import run_parallel_deep_research

    out = run_parallel_deep_research(
        "q",
        runs=1,
        throttle=0,
        code_interpreter=True,
        session=session,
        llm_wrapper=None,
    )

    assert isinstance(out, list) and len(out) == 1 and out[0]["ok"] is True

    # Ensures wrapper is taken from the session context and tools include code_interpreter
    assert captured["llm_wrapper"] is sentinel_wrapper
    assert captured["step"] == "deepResearchRun"
    assert captured["system_prompt"] == ""
    assert captured["prompt_user"] == "q"
    assert captured["tool_choice"] == "auto"
    assert captured["tools"] == [
        {"type": "web_search_preview"},
        {"type": "code_interpreter", "container": {"type": "auto"}},
    ]


def test_missing_web_search_tool_configuration_skips_tool(monkeypatch, caplog):
    import src.deep_research_runner as drr
    from modules.utilities import config as cfg

    naming = dict(cfg.get_naming_params())
    del naming["webSearchTool"]
    monkeypatch.setattr(drr, "get_naming_params", lambda: naming)

    captured = {}

    def fake_run_step_json(
        llm_wrapper,
        step,
        system_prompt,
        prompt_user,
        *,
        tools=None,
        tool_choice="auto",
        **kwargs,
    ):
        captured.update(tools=tools)
        return [{"ok": True}]

    monkeypatch.setattr("modules.llm.batch_runner.run_step_json", fake_run_step_json)

    with caplog.at_level(logging.WARNING):
        out = drr.run_parallel_deep_research(
            "q", runs=1, throttle=0, llm_wrapper=object()
        )

    assert out and out[0]["ok"] is True
    assert captured["tools"] == []
    assert "not configured" in caplog.text


def test_invalid_web_search_tool_configuration_skips_tool(monkeypatch, caplog):
    import src.deep_research_runner as drr
    from modules.utilities import config as cfg

    naming = dict(cfg.get_naming_params())
    naming["webSearchTool"] = "unsupported_tool"
    monkeypatch.setattr(drr, "get_naming_params", lambda: naming)

    captured = {}

    def fake_run_step_json(
        llm_wrapper,
        step,
        system_prompt,
        prompt_user,
        *,
        tools=None,
        tool_choice="auto",
        **kwargs,
    ):
        captured.update(tools=tools)
        return [{"ok": True}]

    monkeypatch.setattr("modules.llm.batch_runner.run_step_json", fake_run_step_json)

    with caplog.at_level(logging.WARNING):
        out = drr.run_parallel_deep_research(
            "q", runs=1, throttle=0, llm_wrapper=object()
        )

    assert out and out[0]["ok"] is True
    assert captured["tools"] == []
    assert "not supported" in caplog.text
