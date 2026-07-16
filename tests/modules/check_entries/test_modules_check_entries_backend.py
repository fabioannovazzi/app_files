from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl
import pytest
from polars.testing import assert_frame_equal

import modules.check_entries.backend as backend
from src.check_entries.run import CheckEntriesRunResult


@dataclass
class _Wrapper:
    provider: str | None = None
    model: str | None = None


def _build_session() -> backend.CheckEntriesSession:
    dataframe = pl.DataFrame(
        {
            "movement_number": ["1"],
            "amount": [10.0],
        }
    )
    return backend.CheckEntriesSession(
        session_id="session-test",
        filename="journal.csv",
        raw_content=b"",
        dataframe=dataframe,
        columns=dataframe.columns,
        row_count=dataframe.height,
        mapping={"movement_number": "movement_number", "amount": "amount"},
        pdf_files=[],
    )


def test_run_checks_uses_shared_runner_output(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _build_session()
    wrapper = _Wrapper()
    saved_sessions: list[backend.CheckEntriesSession] = []
    captured: dict[str, Any] = {}

    result_df = pl.DataFrame(
        {
            "movement_number": ["1"],
            "check_status": ["verified"],
            "llm_batch": [True],
        }
    )
    summary_df = pl.DataFrame({"metric": ["rows"], "value": [1]})
    expected = CheckEntriesRunResult(
        result_df=result_df,
        summary_text="ok",
        summary_metrics={"overview": summary_df},
        excel_bytes=b"excel-bytes",
        error_message=None,
        partial=False,
        partial_reason=None,
    )

    def fake_run_check_entries(context, params, **kwargs):
        captured["context"] = context
        captured["params"] = params
        return expected

    monkeypatch.setattr(backend, "_build_llm_wrapper", lambda: wrapper)
    monkeypatch.setattr(
        backend, "select_provider", lambda _step: {"provider": "openai", "model": "gpt-test"}
    )
    monkeypatch.setattr(backend, "run_check_entries", fake_run_check_entries)
    monkeypatch.setattr(backend.store, "save", lambda s: saved_sessions.append(s))

    output = backend.run_checks(
        session,
        {
            "lang": "eng",
            "debug": False,
            "amount_tolerance": 1.0,
            "date_window": 3,
            "timing_difference_window": 5,
            "beneficiary_similarity": 80.0,
            "beneficiary_check_mode": "compare",
        },
    )

    assert wrapper.provider == "openai"
    assert wrapper.model == "gpt-test"
    assert captured["context"].provider == "openai"
    assert captured["context"].model == "gpt-test"
    assert captured["params"].mapping == session.mapping
    assert_frame_equal(output.result_df, result_df)
    assert output.summary_text == "ok"
    assert_frame_equal(output.summary_tables["overview"], summary_df)
    assert output.excel_bytes == b"excel-bytes"
    assert output.error_message is None
    assert output.batch_mode is True
    assert saved_sessions and saved_sessions[-1].output is output


def test_run_checks_preserves_partial_results(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _build_session()
    wrapper = _Wrapper()
    saved_sessions: list[backend.CheckEntriesSession] = []

    partial_df = pl.DataFrame({"movement_number": ["1"], "check_status": ["mismatch"]})
    partial_result = CheckEntriesRunResult(
        result_df=partial_df,
        summary_text="",
        summary_metrics={},
        excel_bytes=b"partial-bytes",
        error_message="network timeout",
        partial=True,
        partial_reason="network timeout",
    )

    monkeypatch.setattr(backend, "_build_llm_wrapper", lambda: wrapper)
    monkeypatch.setattr(
        backend, "select_provider", lambda _step: {"provider": "openai", "model": "gpt-test"}
    )
    monkeypatch.setattr(backend, "run_check_entries", lambda *args, **kwargs: partial_result)
    monkeypatch.setattr(backend.store, "save", lambda s: saved_sessions.append(s))

    output = backend.run_checks(session, {"lang": "eng"})

    assert_frame_equal(output.result_df, partial_df)
    assert output.summary_text == ""
    assert output.summary_tables == {}
    assert output.excel_bytes == b"partial-bytes"
    assert output.error_message == "network timeout"
    assert output.batch_mode is False
    assert saved_sessions and saved_sessions[-1].output is output
