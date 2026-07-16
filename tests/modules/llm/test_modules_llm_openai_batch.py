import json

import pytest

import modules.llm.openai_batch as ob
from modules.llm.openai_batch import (
    _ensure_line,
    _lines_to_jsonl,
    create_batch_file,
    submit_batch,
    wait_for_batch,
)
from modules.utilities.config import get_naming_params


def _make_prompt(cid: str, sys_text: str, user_text: str) -> dict:
    model = get_naming_params()["gpt5Main"]
    return {
        "custom_id": cid,
        "body": {
            "model": model,
            "input": [
                {"role": "system", "content": sys_text},
                {"role": "user", "content": user_text},
            ],
        },
    }


def test_ensure_line_defaults_model_and_schema(monkeypatch):
    naming = get_naming_params()
    calls: list[str] = []

    def fake_select(step):
        calls.append(step)
        if step == naming["llmFallbackQuery"]:
            return {"model": "m", "provider": naming["openai"]}
        raise AssertionError(f"unexpected step: {step}")

    monkeypatch.setattr(ob, "select_provider", fake_select)
    prompt = {"custom_id": "1", "schema": {"type": "object"}, "body": {"input": []}}
    line = _ensure_line(prompt)
    assert line["body"]["model"] == "m"
    assert line["body"]["text"]["format"]["type"] == "json_schema"
    assert calls == [naming["llmFallbackQuery"]]


def test_ensure_line_rejects_non_openai_default(monkeypatch):
    naming = get_naming_params()

    def fake_select(step):
        if step == naming["llmFallbackQuery"]:
            return {"model": "other-model", "provider": "Other"}
        raise AssertionError(f"unexpected step: {step}")

    monkeypatch.setattr(ob, "select_provider", fake_select)
    prompt = {"custom_id": "1", "body": {"input": []}}
    with pytest.raises(RuntimeError, match="must resolve to OpenAI"):
        _ensure_line(prompt)


def test_ensure_line_respects_model_override(monkeypatch):
    monkeypatch.setattr(ob, "select_provider", lambda step: {"model": "x"})
    prompt = {"custom_id": "1", "body": {"model": "y", "input": []}}
    line = _ensure_line(prompt)
    assert line["body"]["model"] == "y"


def test_lines_to_jsonl_roundtrip():
    lines = [{"a": 1}, {"b": 2}]
    data = _lines_to_jsonl(lines)
    decoded = data.decode().splitlines()
    assert decoded == [json.dumps(l, ensure_ascii=False) for l in lines]


def test_create_batch_file_requires_provider_batch_mode(monkeypatch):
    monkeypatch.setattr(ob, "_provider_enabled", lambda: False)

    with pytest.raises(RuntimeError, match="Provider batch mode is disabled"):
        create_batch_file([_make_prompt("c1", "S1", "U1")])


def test_submit_batch_requires_provider_batch_mode(monkeypatch):
    monkeypatch.setattr(ob, "_provider_enabled", lambda: False)

    with pytest.raises(RuntimeError, match="Provider batch mode is disabled"):
        submit_batch("file_nonexistent")


def test_wait_for_batch_timeout(monkeypatch):
    monkeypatch.setattr(ob, "_provider_enabled", lambda: False)

    class DummyJob:
        status = "in_progress"

    class DummyClient:
        def __init__(self):
            self.batches = self

        def retrieve(self, batch_id):  # type: ignore[override]
            assert batch_id == "batch_timeout"
            return DummyJob()

    monkeypatch.setattr(ob.llm_client, "get_openai_client", lambda: DummyClient())
    monkeypatch.setattr(ob.time, "sleep", lambda _seconds: None)

    # Act / Assert
    with pytest.raises(RuntimeError, match="Batch polling timed out"):
        wait_for_batch(object(), "batch_timeout", timeout=0)


def test_wait_for_batch_provider_id_ignores_disabled_batch_mode(monkeypatch):
    # Arrange: clear fallback registries and simulate provider response
    ob._BATCH_JOBS.clear()
    monkeypatch.setattr(ob, "_provider_enabled", lambda: False)

    class DummyJob:
        status = "completed"
        output_file_id = "out123"

    class DummyClient:
        def __init__(self):
            self.batches = self
            self.files = self

        def retrieve(self, batch_id):  # type: ignore[override]
            assert batch_id == "batch_abc"
            return DummyJob()

        def retrieve_content(self, file_id):  # type: ignore[override]
            assert file_id == "out123"
            line = {
                "custom_id": "0",
                "response": {"output": [{"content": [{"type": "text", "text": "ok"}]}]},
            }
            return json.dumps(line)

    monkeypatch.setattr(ob.llm_client, "get_openai_client", lambda: DummyClient())

    # Act
    result = wait_for_batch(object(), "batch_abc")

    # Assert
    assert set(result.keys()) == {"0"}
    raw = json.loads(result["0"])
    assert raw["custom_id"] == "0"


def test_wait_for_batch_registered_provider_job(monkeypatch):
    # Arrange: ensure the job is registered (typical OpenAI path)
    original_jobs = ob._BATCH_JOBS.copy()
    ob._BATCH_JOBS.clear()

    batch_id = "batch_registered"
    ob._BATCH_JOBS[batch_id] = "file-abc"
    monkeypatch.setattr(ob, "_provider_enabled", lambda: True)

    class DummyJob:
        status = "completed"
        output_file_id = "out456"

    class DummyClient:
        def __init__(self):
            self.calls = 0
            self.batches = self
            self.files = self

        def retrieve(self, bid):  # type: ignore[override]
            assert bid == batch_id
            self.calls += 1
            return DummyJob()

        def retrieve_content(self, file_id):  # type: ignore[override]
            assert file_id == "out456"
            line = {
                "custom_id": "7",
                "response": {
                    "output": [
                        {
                            "content": [
                                {"type": "text", "text": json.dumps({"ok": True})}
                            ]
                        }
                    ]
                },
            }
            return json.dumps(line)

    dummy_client = DummyClient()
    monkeypatch.setattr(ob.llm_client, "get_openai_client", lambda: dummy_client)

    try:
        result = wait_for_batch(object(), batch_id)
    finally:
        ob._BATCH_JOBS.clear()
        ob._BATCH_JOBS.update(original_jobs)

    # Assert: provider was queried.
    assert dummy_client.calls == 1
    assert set(result.keys()) == {"7"}
    raw = json.loads(result["7"])
    assert raw["custom_id"] == "7"


def test_wait_for_batch_completed_includes_request_level_errors(monkeypatch):
    class DummyJob:
        status = "completed"
        output_file_id = "out456"
        error_file_id = "err456"

    class DummyClient:
        def __init__(self):
            self.batches = self
            self.files = self

        def retrieve(self, bid):  # type: ignore[override]
            assert bid == "batch_with_errors"
            return DummyJob()

        def retrieve_content(self, file_id):  # type: ignore[override]
            if file_id == "out456":
                return json.dumps(
                    {
                        "custom_id": "0",
                        "response": {
                            "output": [
                                {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": json.dumps({"ok": True}),
                                        }
                                    ]
                                }
                            ]
                        },
                    }
                )
            assert file_id == "err456"
            return json.dumps(
                {
                    "custom_id": "1",
                    "response": {
                        "status_code": 400,
                        "body": {
                            "error": {
                                "message": "bad image",
                                "type": "invalid_request_error",
                            }
                        },
                    },
                }
            )

    monkeypatch.setattr(ob.llm_client, "get_openai_client", lambda: DummyClient())

    result = wait_for_batch(object(), "batch_with_errors")

    assert set(result.keys()) == {"0", "1"}
    assert (
        json.loads(result["1"])["response"]["body"]["error"]["message"] == "bad image"
    )


def test_create_batch_file_provider(monkeypatch):
    naming = get_naming_params()
    model = naming["gpt5Main"]
    monkeypatch.setattr(ob, "_provider_enabled", lambda: True)

    class DummyClient:
        def __init__(self):
            self.created_file = None

            class Files:
                def __init__(self, outer):
                    self._outer = outer

                def create(self, file, purpose):
                    self._outer.created_file = file
                    assert purpose == "batch"

                    class Obj:
                        id = "fid"

                    return Obj()

            self.files = Files(self)

    dummy_client = DummyClient()
    monkeypatch.setattr(ob.llm_client, "get_openai_client", lambda: dummy_client)

    prompts = [
        {
            "custom_id": "1",
            "body": {
                "model": model,
                "input": [],
                "text": {"format": {"type": "json_object"}},
            },
        }
    ]
    fid = create_batch_file(prompts)
    assert fid == "fid"
    filename, file_obj, content_type = dummy_client.created_file
    assert filename == "batch.jsonl"
    assert content_type == "application/jsonl"
    decoded = file_obj.getvalue().decode().splitlines()
    assert json.loads(decoded[0])["body"]["model"] == model


def test_submit_batch_provider(monkeypatch):
    monkeypatch.setattr(ob, "_provider_enabled", lambda: True)

    class DummyClient:
        def __init__(self):
            class Batches:
                @staticmethod
                def create(input_file_id, completion_window, endpoint):
                    class Job:
                        id = "bid"

                    return Job()

            self.batches = Batches()

    monkeypatch.setattr(ob.llm_client, "get_openai_client", lambda: DummyClient())
    bid = submit_batch("fid")
    assert bid == "bid"
