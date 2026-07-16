from __future__ import annotations

import json

import polars as pl
import pytest

from modules.check_entries.audit_note import generate_audit_note


def _capture_run_step_text(monkeypatch):
    """Monkeypatch run_step_text to capture inputs and return a stubbed note."""

    calls: dict[str, str] = {}

    def _fake(llm_wrapper, step, system_prompt, prompts, *, tools=None, tool_choice="auto"):
        # Store the last call for assertions
        calls["step"] = step
        calls["system_prompt"] = system_prompt
        calls["prompt_user"] = prompts
        return ["STUB_AUDIT_NOTE"]

    monkeypatch.setattr("modules.check_entries.audit_note.run_step_text", _fake)
    return calls


def _extract_payload(prompt_user: str) -> dict:
    """Extract the JSON payload following the 'Data: ' marker in the prompt."""
    marker = "Data: "
    assert marker in prompt_user, "Expected 'Data: ' marker in prompt"
    data = prompt_user[prompt_user.index(marker) + len(marker) :]
    return json.loads(data)


def test_generate_audit_note_simple_patterns_english(monkeypatch):
    # Arrange: three checks (two mismatches, one 'other', one ok)
    amount_msg = "Amount mismatch: expected 10±0, found 12"
    fraud_msg = "Fraud: suspicious transfer"
    other_msg = "Some other issue"
    df = pl.DataFrame(
        {
            "check_status": ["mismatch", "mismatch", "ok", "mismatch"],
            "explanation": [amount_msg, fraud_msg, "ignored", other_msg],
        }
    )
    calls = _capture_run_step_text(monkeypatch)

    # Act
    out = generate_audit_note(object(), df, lang="eng")

    # Assert: returns stubbed note and calls LLM with correct step/language
    assert out == "STUB_AUDIT_NOTE"
    assert calls["step"] == "quickRewriteQuery"
    assert calls["system_prompt"] == "Respond in English."

    payload = _extract_payload(calls["prompt_user"])
    # Totals reflect inferred categories from explanation prefixes
    assert payload["totals"]["amount"] == 1
    assert payload["totals"]["fraud"] == 1
    # Details contain the full explanations; uncategorized collects the 'other'
    assert payload["details"]["amount"] == [amount_msg]
    assert payload["details"]["fraud"] == [fraud_msg]
    assert other_msg in payload["uncategorized"]


def test_generate_audit_note_flattens_mismatches_and_italian(monkeypatch):
    # Arrange: mismatch info provided via list[struct] column; includes unknown type
    date_msg = (
        "Date mismatch: expected 2024-01-01±2 days, found 2024-01-05"
    )
    unknown_msg = "Unmapped discrepancy entry"
    df = pl.DataFrame(
        [
            {
                "check_status": "mismatch",
                # Top-level fields intentionally conflict with struct fields
                "explanation": "top-level ignored",
                "mismatch_type": "top-level",
                "mismatches": [
                    {"explanation": date_msg, "mismatch_type": "date_mismatch"}
                ],
            },
            {
                "check_status": "mismatch",
                "explanation": "top-level ignored 2",
                "mismatch_type": "top-level 2",
                "mismatches": [
                    {"explanation": unknown_msg, "mismatch_type": "weird_mismatch"}
                ],
            },
            {
                "check_status": "ok",
                "explanation": "irrelevant",
                "mismatch_type": "unused",
                "mismatches": [],
            },
        ]
    )
    calls = _capture_run_step_text(monkeypatch)

    # Act
    out = generate_audit_note(object(), df, lang="ita")

    # Assert: returns stub and uses Italian in system prompt
    assert out == "STUB_AUDIT_NOTE"
    assert calls["system_prompt"] == "Respond in Italian."

    payload = _extract_payload(calls["prompt_user"])
    # The struct-provided mismatch_type drives categorization
    assert payload["totals"]["date"] == 1
    assert payload["details"]["date"] == [date_msg]
    # Unknown mismatch_type is not in known categories -> goes to uncategorized
    assert unknown_msg in payload["uncategorized"]


def test_generate_audit_note_no_mismatches_yields_empty_payload(monkeypatch):
    # Arrange: only 'ok' rows
    df = pl.DataFrame({"check_status": ["ok", "ok"], "explanation": ["a", "b"]})
    calls = _capture_run_step_text(monkeypatch)

    # Act
    out = generate_audit_note(object(), df)

    # Assert: totals all zero, details empty, no uncategorized
    assert out == "STUB_AUDIT_NOTE"
    payload = _extract_payload(calls["prompt_user"])
    assert sum(payload["totals"].values()) == 0
    assert all(len(v) == 0 for v in payload["details"].values())
    assert payload["uncategorized"] == []
