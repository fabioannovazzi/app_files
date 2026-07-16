import json
import types

import pytest

from modules.utilities.ui_notifier import FastAPINotifier

def test_normalize_research_result_prefers_raw_response():
    from src.deep_research_utils import normalize_research_result

    res = {"raw_response": {"val": 123}, "other": 42}
    out = normalize_research_result(res)
    assert out == {"val": 123}


def test_normalize_research_result_invalid_json_returns_input_and_calls_st_error():
    import src.deep_research_utils as dru

    notifier = FastAPINotifier()
    bad = "not json"
    out = dru.normalize_research_result(bad, notifier=notifier)

    assert out == bad
    assert any(
        event["level"] == "error"
        and event["message"] == "Error normalizing the research result"
        for event in notifier.events
    )


def test_normalize_research_result_parses_json_string():
    from src.deep_research_utils import normalize_research_result

    s = json.dumps({"a": 1})
    out = normalize_research_result(s)
    assert out == {"a": 1}


def test_extract_trace_info_with_attribute_objects():
    from src.deep_research_utils import extract_trace_info

    NS = types.SimpleNamespace
    res = {
        "raw_response": {
            "output": [
                NS(type="reasoning", summary=[NS(text="one"), NS(text="two")]),
                NS(type="web_search_call", action=NS(query="pizza"), status="ok"),
            ]
        }
    }

    out = extract_trace_info(res)
    assert out == {"reasoning": ["one", "two"], "search": {"query": "pizza", "status": "ok"}}


def test_extract_trace_info_defaults_when_missing():
    from src.deep_research_utils import extract_trace_info

    out = extract_trace_info({})
    assert out == {"reasoning": [], "search": {"query": "", "status": ""}}


def test_dump_response_logs_json_when_notifier_missing(caplog):
    import logging
    from src.deep_research_utils import dump_response

    data = {"x": 1}
    expected = json.dumps(data, indent=2, ensure_ascii=False)

    caplog.set_level(logging.INFO)
    dump_response(data)

    messages = [rec.getMessage() for rec in caplog.records]
    assert any(expected == msg for msg in messages)


def test_dump_response_writes_to_notifier_when_provided():
    from src.deep_research_utils import dump_response

    notifier = FastAPINotifier()
    data = {"y": 2}
    expected = json.dumps(data, indent=2, ensure_ascii=False)
    dump_response(data, notifier=notifier)

    assert any(
        event["level"] == "write" and event["message"] == expected
        for event in notifier.events
    )
