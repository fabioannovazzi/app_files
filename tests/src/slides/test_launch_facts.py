from __future__ import annotations

import pytest

from src.slides.launch_facts import validate_launch_facts_payload


def test_validate_launch_facts_payload_accepts_supported_shape() -> None:
    payload = {
        "version": "launch_facts/1",
        "retailer": "Ulta",
        "category": "Lipstick",
        "question": "Which launch signals survive basic audit?",
        "summaryMetrics": [
            {"label": "Observed launches", "value": "29"},
            {"label": "Audited launches", "value": "21"},
        ],
        "attributeSignals": [
            {
                "attribute": "Hydrating",
                "finding": "Over-indexes in launches versus the older base.",
            }
        ],
        "launchExamples": [
            {"brand": "Example Brand", "product": "Hydrating Lip Stick"},
        ],
    }

    validated = validate_launch_facts_payload(payload)

    assert validated["retailer"] == "Ulta"


def test_validate_launch_facts_payload_rejects_missing_question() -> None:
    payload = {
        "retailer": "Ulta",
        "category": "Lipstick",
        "summaryMetrics": [{"label": "Observed launches", "value": "29"}],
    }

    with pytest.raises(ValueError, match="non-empty 'question'"):
        validate_launch_facts_payload(payload)
