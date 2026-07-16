import json

import pytest

from modules.llm.batch_runner import _build_lines, run_step_json, run_step_text
from modules.utilities.config import get_naming_params


def test_run_step_json_single_string_autoflex(monkeypatch):
    # Arrange: force Flex eligibility and capture the service_tier passed to query
    monkeypatch.setattr("modules.llm.batch_runner.should_use_flex", lambda step: True)
    monkeypatch.setattr("modules.llm.batch_runner.should_use_batch", lambda step: False)
    calls = []

    def fake_query(
        llm_wrapper,
        step,
        system_prompt,
        prompt_user,
        *,
        tools=None,
        tool_choice="auto",
        service_tier=None,
        reasoning_effort=None,
        extra_body=None,
    ):
        calls.append(
            {
                "step": step,
                "system": system_prompt,
                "user": prompt_user,
                "service_tier": service_tier,
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        return {"ok": True, "tier": service_tier}

    monkeypatch.setattr("modules.llm.batch_runner.query_llm_return_json", fake_query)

    # Act
    res = run_step_json(object(), "any_step", "SYS", "USER")

    # Assert
    assert res == [{"ok": True, "tier": "flex"}]
    assert len(calls) == 1
    assert calls[0]["service_tier"] == "flex"


def test_run_step_json_batch_parsing_and_order(monkeypatch):
    # Arrange: enable batch, disable flex; capture created batch lines
    monkeypatch.setattr("modules.llm.batch_runner.should_use_batch", lambda step: True)
    monkeypatch.setattr("modules.llm.batch_runner.should_use_flex", lambda step: False)
    naming = get_naming_params()
    model_key = naming["modelName"]
    provider_key = naming["providerName"]
    monkeypatch.setattr(
        "modules.llm.batch_runner.select_provider",
        lambda step: {model_key: "m-test", provider_key: "p-test"},
    )

    naming = get_naming_params()
    model_key = naming["modelName"]
    provider_key = naming["providerName"]
    batch_key = naming["batchMode"]
    provider_info = {provider_key: "openai", model_key: "gpt-test", batch_key: True}
    monkeypatch.setattr(
        "modules.llm.batch_runner.select_provider", lambda step: provider_info
    )

    received_lines = {}

    def fake_create_batch_file(lines):
        # Capture what _build_lines produced
        received_lines["lines"] = lines
        return "fid_1"

    def fake_submit_batch(fid):
        assert fid == "fid_1"
        return "bid_1"

    # Simulate provider-style raw outputs with custom_id out of order
    raw_map = {
        "1": json.dumps(
            {"response": {"output": [{"content": [{"text": "not json"}]}]}}
        ),
        "0": json.dumps(
            {"response": {"output": [{"content": [{"text": '{"alpha": 1}'}]}]}}
        ),
    }

    def fake_wait_for_batch(llm_wrapper, bid):
        assert bid == "bid_1"
        return raw_map

    monkeypatch.setattr(
        "modules.llm.batch_runner.create_batch_file", fake_create_batch_file
    )
    monkeypatch.setattr("modules.llm.batch_runner.submit_batch", fake_submit_batch)
    monkeypatch.setattr("modules.llm.batch_runner.wait_for_batch", fake_wait_for_batch)

    prompts = ["P0", "P1"]

    # Act
    out = run_step_json(object(), "step_x", "SYS", prompts)

    # Assert: order preserved and JSON loaded when valid, else raw captured
    assert out == [{"alpha": 1}, {"raw": "not json"}]

    # Check that lines were built correctly for each prompt
    lines = received_lines["lines"]
    assert [ln["custom_id"] for ln in lines] == ["0", "1"]
    assert lines[0]["body"]["input"][0]["role"] == "system"
    assert lines[0]["body"]["input"][0]["content"] == "SYS"
    assert lines[0]["body"]["input"][1]["role"] == "user"
    assert lines[0]["body"]["input"][1]["content"] == "P0"
    assert lines[1]["body"]["input"][1]["content"] == "P1"
    assert all(ln["body"]["model"] == "gpt-test" for ln in lines)


def test_run_step_json_single_item_uses_live_when_batch_enabled(monkeypatch):
    monkeypatch.setattr("modules.llm.batch_runner.should_use_batch", lambda step: True)
    monkeypatch.setattr("modules.llm.batch_runner.should_use_flex", lambda step: False)
    monkeypatch.setattr(
        "modules.llm.batch_runner.create_batch_file",
        lambda lines: (_ for _ in ()).throw(
            AssertionError("single prompt should not use provider batch")
        ),
    )
    calls = []

    def fake_query(
        llm_wrapper,
        step,
        system_prompt,
        prompt_user,
        *,
        tools=None,
        tool_choice="auto",
        service_tier=None,
        reasoning_effort=None,
        extra_body=None,
    ):
        calls.append((step, system_prompt, prompt_user, service_tier))
        return {"ok": True}

    monkeypatch.setattr("modules.llm.batch_runner.query_llm_return_json", fake_query)

    out = run_step_json(object(), "step_x", "SYS", ["P0"])

    assert out == [{"ok": True}]
    assert calls == [("step_x", "SYS", "P0", None)]


def test_build_lines_accepts_image_content():
    naming = get_naming_params()
    step = naming["pdpVisionAttributeQuery"]
    lines = _build_lines(
        step,
        "Respond in json with attributes.",
        [
            {
                "user_content": [
                    {"type": "input_text", "text": "find format"},
                    {"type": "input_image", "image_url": "https://example.com/x.jpg"},
                ]
            }
        ],
    )
    assert len(lines) == 1
    body = lines[0]["body"]
    assert body["input"][0]["role"] == "system"
    assert "json" in body["input"][0]["content"].lower()
    assert body["input"][1]["role"] == "user"
    assert isinstance(body["input"][1]["content"], list)


def test_run_step_json_clamps_explicit_flex_when_not_eligible(monkeypatch):
    # Arrange: make step not Flex-eligible and capture service_tier value
    monkeypatch.setattr("modules.llm.batch_runner.should_use_flex", lambda step: False)
    monkeypatch.setattr("modules.llm.batch_runner.should_use_batch", lambda step: False)
    seen = {}

    def fake_query(
        llm_wrapper,
        step,
        system_prompt,
        prompt_user,
        *,
        tools=None,
        tool_choice="auto",
        service_tier=None,
        reasoning_effort=None,
        extra_body=None,
    ):
        seen["service_tier"] = service_tier
        return {"tier": service_tier}

    monkeypatch.setattr("modules.llm.batch_runner.query_llm_return_json", fake_query)

    # Act
    res = run_step_json(object(), "s", "SYS", "USER", service_tier="flex")

    # Assert: service_tier is clamped to None
    assert res == [{"tier": None}]
    assert seen["service_tier"] is None


def test_run_step_text_sequential_when_tools_present(monkeypatch):
    # Arrange: Batch would be allowed, but tools must force sequential
    monkeypatch.setattr("modules.llm.batch_runner.should_use_batch", lambda step: True)
    # Fail fast if batch path is attempted
    monkeypatch.setattr(
        "modules.llm.batch_runner.create_batch_file",
        lambda lines: (_ for _ in ()).throw(
            AssertionError("batch should not run when tools are provided")
        ),
    )

    calls = []

    def fake_query(
        llm_wrapper, step, system_prompt, prompt_user, *, tools=None, tool_choice="auto"
    ):
        calls.append((prompt_user, tools))
        return f"resp:{prompt_user}"

    monkeypatch.setattr("modules.llm.batch_runner.query_llm_return_text", fake_query)

    prompts = ["a", "b"]

    # Act
    out = run_step_text(object(), "s", "SYS", prompts, tools=[{"type": "dummy"}])

    # Assert
    assert out == ["resp:a", "resp:b"]
    assert calls == [("a", [{"type": "dummy"}]), ("b", [{"type": "dummy"}])]


def test_build_lines_adds_lowercase_json_when_only_uppercase():
    naming = get_naming_params()
    model_key = naming["modelName"]
    provider_key = naming["providerName"]

    def fake_select(step):
        return {model_key: "model-x", provider_key: "p-test"}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("modules.llm.batch_runner.select_provider", fake_select)
    try:
        lines = _build_lines("step", "Reply in JSON", ["prompt"])
    finally:
        monkeypatch.undo()
    inputs = lines[0]["body"]["input"]
    assert inputs[-1]["content"] == "Respond in json."
    assert any("json" in msg["content"] for msg in inputs)
    assert lines[0]["body"][model_key] == "model-x"


def test_run_step_text_batch_uses_provider_model(monkeypatch):
    monkeypatch.setattr("modules.llm.batch_runner.should_use_batch", lambda step: True)

    naming = get_naming_params()
    model_key = naming["modelName"]
    provider_key = naming["providerName"]
    batch_key = naming["batchMode"]
    provider_info = {provider_key: "openai", model_key: "text-model", batch_key: True}
    monkeypatch.setattr(
        "modules.llm.batch_runner.select_provider", lambda step: provider_info
    )

    received_lines = {}

    def fake_create_batch_file(lines):
        received_lines["lines"] = lines
        return "fid_1"

    def fake_submit_batch(fid):
        assert fid == "fid_1"
        return "bid_1"

    raw_map = {
        "0": json.dumps({"response": {"output": [{"content": [{"text": "A"}]}]}}),
        "1": json.dumps({"response": {"output": [{"content": [{"text": "B"}]}]}}),
    }

    def fake_wait_for_batch(llm_wrapper, bid):
        assert bid == "bid_1"
        return raw_map

    monkeypatch.setattr(
        "modules.llm.batch_runner.create_batch_file", fake_create_batch_file
    )
    monkeypatch.setattr("modules.llm.batch_runner.submit_batch", fake_submit_batch)
    monkeypatch.setattr("modules.llm.batch_runner.wait_for_batch", fake_wait_for_batch)

    out = run_step_text(object(), "step_text", "SYS", ["P0", "P1"])
    assert out == ["A", "B"]

    lines = received_lines["lines"]
    assert all(ln["body"][model_key] == "text-model" for ln in lines)
    assert all(ln["body"][model_key] != "o3" for ln in lines)


def test_run_step_text_single_item_uses_live_when_batch_enabled(monkeypatch):
    monkeypatch.setattr("modules.llm.batch_runner.should_use_batch", lambda step: True)
    monkeypatch.setattr(
        "modules.llm.batch_runner.create_batch_file",
        lambda lines: (_ for _ in ()).throw(
            AssertionError("single prompt should not use provider batch")
        ),
    )
    calls = []

    def fake_query(
        llm_wrapper,
        step,
        system_prompt,
        prompt_user,
        *,
        tools=None,
        tool_choice="auto",
    ):
        calls.append((step, system_prompt, prompt_user))
        return "ok"

    monkeypatch.setattr("modules.llm.batch_runner.query_llm_return_text", fake_query)

    out = run_step_text(object(), "step_text", "SYS", ["P0"])

    assert out == ["ok"]
    assert calls == [("step_text", "SYS", "P0")]


def test_run_step_json_batch_prefers_message_content(monkeypatch):
    monkeypatch.setattr("modules.llm.batch_runner.should_use_batch", lambda step: True)
    monkeypatch.setattr("modules.llm.batch_runner.should_use_flex", lambda step: False)

    naming = get_naming_params()
    model_key = naming["modelName"]
    provider_key = naming["providerName"]
    batch_key = naming["batchMode"]
    provider_info = {provider_key: "openai", model_key: "gpt-test", batch_key: True}
    monkeypatch.setattr(
        "modules.llm.batch_runner.select_provider", lambda step: provider_info
    )

    def fake_create_batch_file(lines):
        return "fid_msg"

    def fake_submit_batch(fid):
        assert fid == "fid_msg"
        return "bid_msg"

    raw_map = {
        "0": json.dumps(
            {
                "response": {
                    "status_code": 200,
                    "body": {
                        "output": [
                            {"id": "rs1", "type": "reasoning", "summary": []},
                            {
                                "id": "msg1",
                                "type": "message",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": '{"parent": {"coverage": {"value": "full"}}, "variants": {}}',
                                    }
                                ],
                            },
                        ]
                    },
                }
            }
        ),
        "1": json.dumps(
            {
                "response": {
                    "status_code": 200,
                    "body": {
                        "output": [
                            {
                                "id": "msg2",
                                "type": "message",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": '{"parent": {"coverage": {"value": "partial"}}, "variants": {}}',
                                    }
                                ],
                            },
                        ]
                    },
                }
            }
        ),
    }

    def fake_wait_for_batch(llm_wrapper, bid):
        assert bid == "bid_msg"
        return raw_map

    monkeypatch.setattr(
        "modules.llm.batch_runner.create_batch_file", fake_create_batch_file
    )
    monkeypatch.setattr("modules.llm.batch_runner.submit_batch", fake_submit_batch)
    monkeypatch.setattr("modules.llm.batch_runner.wait_for_batch", fake_wait_for_batch)

    out = run_step_json(
        object(),
        "pdpClassificationQuery",
        "SYS",
        ["prompt one", "prompt two"],
    )
    assert out == [
        {"parent": {"coverage": {"value": "full"}}, "variants": {}},
        {"parent": {"coverage": {"value": "partial"}}, "variants": {}},
    ]


def test_run_step_json_batch_retries_missing(monkeypatch):
    monkeypatch.setattr("modules.llm.batch_runner.should_use_batch", lambda step: True)
    monkeypatch.setattr("modules.llm.batch_runner.should_use_flex", lambda step: False)

    naming = get_naming_params()
    model_key = naming["modelName"]
    provider_key = naming["providerName"]
    batch_key = naming["batchMode"]
    provider_info = {provider_key: "openai", model_key: "gpt-test", batch_key: True}
    monkeypatch.setattr(
        "modules.llm.batch_runner.select_provider", lambda step: provider_info
    )

    prompts = ["p0", "p1", "p2"]
    lines_seen = []

    def fake_create_batch_file(lines):
        lines_seen.append(lines)
        return f"fid_{len(lines_seen)}"

    def fake_submit_batch(fid):
        return f"bid_{fid}"

    raw_first = {
        "0": json.dumps(
            {"response": {"output": [{"content": [{"text": '{"ok": 0}'}]}]}}
        ),
        "2": json.dumps(
            {"response": {"output": [{"content": [{"text": '{"ok": 2}'}]}]}}
        ),
    }
    raw_retry = {
        "0": json.dumps(
            {"response": {"output": [{"content": [{"text": '{"ok": 1}'}]}]}}
        ),
    }
    wait_calls = {"count": 0}

    def fake_wait_for_batch(_llm, _bid):
        wait_calls["count"] += 1
        if wait_calls["count"] == 1:
            return raw_first
        return raw_retry

    monkeypatch.setattr(
        "modules.llm.batch_runner.create_batch_file", fake_create_batch_file
    )
    monkeypatch.setattr("modules.llm.batch_runner.submit_batch", fake_submit_batch)
    monkeypatch.setattr("modules.llm.batch_runner.wait_for_batch", fake_wait_for_batch)

    out = run_step_json(
        object(),
        "step_x",
        "SYS",
        prompts,
        retry_missing=True,
    )
    assert out == [{"ok": 0}, {"ok": 1}, {"ok": 2}]
    assert len(lines_seen) == 2
    assert len(lines_seen[1]) == 1
    assert lines_seen[1][0]["body"]["input"][1]["content"] == "p1"
