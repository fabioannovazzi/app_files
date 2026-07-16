"""Prompt templates for beneficiary extraction and comparison.

These helpers build structured JSON prompts for LLM calls.  They mention
common ISO 20022 labels (e.g. "Beneficiary", "Ultimate Creditor",
"Receiver", "IBAN holder") so that the model can parse bank statements
reliably.  Optional *amount* and *date* fields are only included when the
pre-check could not confirm them.
"""

from __future__ import annotations

from typing import Any

_LABEL_HINT = (
    "Labels such as 'Beneficiary', 'Ultimate Creditor', 'Receiver', or "
    "'IBAN holder' often precede the payee name."
)


def _build_user_prompt(text: str, *, amount: str | None, date: str | None) -> str:
    """Return the user prompt including optional amount and date hints."""

    parts = [
        "Read the following bank statement text and extract the payee/beneficiary name.",
        _LABEL_HINT,
    ]
    if amount is not None:
        parts.append(f"The relevant transaction amount is {amount}.")
    if date is not None:
        parts.append(f"The transaction date is {date}.")
    parts.append("PDF text:\n" + text)
    return " \n".join(parts)


def extract_beneficiary_prompt(
    text: str, *, amount: str | None = None, date: str | None = None
) -> dict[str, Any]:
    """Return a prompt for extracting a beneficiary name from *text*.

    Parameters
    ----------
    text:
        PDF text to analyse.
    amount, date:
        Optional hints added only if the pre-check failed to confirm them.
    """

    schema = {
        "name": "extract_beneficiary",
        "schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["ok", "not_found"]},
                "explanation": {"type": "string"},
                "beneficiary_extracted": {"type": "string"},
                "candidate_names": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["status", "explanation", "beneficiary_extracted"],
        },
    }
    user_prompt = _build_user_prompt(text, amount=amount, date=date)
    return {
        "input": [
            {
                "role": "system",
                "content": "You are a helpful assistant. Reply in JSON only.",
            },
            {"role": "user", "content": user_prompt},
        ],
        "text": {"format": {"type": "json_schema"}, "schema": schema},
    }


def compare_beneficiary_prompt(
    text: str,
    expected_name: str,
    *,
    amount: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """Return a prompt to compare an extracted beneficiary to *expected_name*.

    Parameters
    ----------
    text:
        PDF text to analyse.
    expected_name:
        The beneficiary name to compare against.
    amount, date:
        Optional hints added only if the pre-check failed to confirm them.
    """

    schema = {
        "name": "compare_beneficiary",
        "schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["ok", "mismatch"]},
                "beneficiary_extracted": {"type": "string"},
                "name_similarity": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                },
                "explanation": {"type": "string"},
            },
            "required": [
                "status",
                "beneficiary_extracted",
                "name_similarity",
                "explanation",
            ],
        },
    }
    intro = (
        "Extract the payee/beneficiary name and compare it to " f"'{expected_name}'."
    )
    user_prompt = intro + " " + _build_user_prompt(text, amount=amount, date=date)
    return {
        "input": [
            {
                "role": "system",
                "content": "You are a helpful assistant. Reply in JSON only.",
            },
            {"role": "user", "content": user_prompt},
        ],
        "text": {"format": {"type": "json_schema"}, "schema": schema},
    }
