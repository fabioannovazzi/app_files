from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT
    / "plugins"
    / "clara"
    / "skills"
    / "html-deck"
    / "scripts"
    / "content_ledger.py"
)


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_html_content_ledger", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def ledger() -> dict[str, Any]:
    return {
        "schema_version": "clara.html_deck_ledger.v1",
        "sources": [
            {
                "id": "source-a",
                "label": "Approved workpaper",
                "kind": "workpaper",
                "locator": "/private/case/advisory_workpaper.md",
                "sha256": "a" * 64,
            }
        ],
        "slides": [
            {
                "slide_id": "opening",
                "basis_status": "speaker-judgement",
                "basis_note": "Opening framing approved by the advisor.",
                "claims": [],
            },
            {
                "slide_id": "evidence",
                "basis_status": "source-backed",
                "basis_note": "",
                "claims": [
                    {
                        "id": "claim-revenue",
                        "statement": "Revenue increased by 12%.",
                        "classification": "fact",
                        "basis_status": "source-backed",
                        "basis_note": "",
                        "source_ids": ["source-a"],
                    }
                ],
            },
        ],
    }


def test_validate_content_ledger_ties_every_deck_slide_to_basis() -> None:
    module = load_module()

    normalized = module.validate_content_ledger(
        ledger(),
        slide_ids=["opening", "evidence"],
    )

    assert [slide["slide_id"] for slide in normalized["slides"]] == [
        "opening",
        "evidence",
    ]
    assert normalized["slides"][1]["claims"][0]["source_ids"] == ["source-a"]


def test_embedded_ledger_omits_private_locator_and_round_trips() -> None:
    module = load_module()

    markup = module.embedded_ledger_markup(ledger())
    extracted = module.extract_embedded_ledger(f"<html><body>{markup}</body></html>")

    assert "/private/case" not in markup
    assert extracted is not None
    assert extracted["sources"][0]["id"] == "source-a"


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value["slides"][1]["claims"][0].update(
                {"source_ids": ["missing"]}
            ),
            "unknown sources",
        ),
        (
            lambda value: value["slides"][1]["claims"][0].update(
                {"classification": "truth"}
            ),
            "unsupported classification",
        ),
        (
            lambda value: value["slides"][1]["claims"][0].update(
                {"basis_status": "speaker-judgement", "source_ids": []}
            ),
            "fact claim.*source-backed",
        ),
        (lambda value: value["slides"].pop(), "slide mismatch"),
    ],
)
def test_validate_content_ledger_rejects_broken_mechanical_links(
    mutator: Any,
    message: str,
) -> None:
    module = load_module()
    payload = ledger()
    mutator(payload)

    with pytest.raises(ValueError, match=message):
        module.validate_content_ledger(
            payload,
            slide_ids=["opening", "evidence"],
        )


def test_validate_content_ledger_does_not_claim_semantic_truth() -> None:
    module = load_module()
    payload = ledger()
    payload["slides"][1]["claims"][0]["statement"] = "A contested interpretation."

    normalized = module.validate_content_ledger(
        payload,
        slide_ids=["opening", "evidence"],
    )

    assert (
        normalized["slides"][1]["claims"][0]["statement"]
        == "A contested interpretation."
    )


def test_validate_content_ledger_allows_explicit_unsourced_judgement() -> None:
    module = load_module()
    payload = ledger()
    payload["slides"][0]["claims"] = [
        {
            "id": "claim-advisor-view",
            "statement": "The team is not ready to decide.",
            "classification": "judgement",
            "basis_status": "speaker-judgement",
            "basis_note": "Advisor judgement from the review meeting.",
            "source_ids": [],
        }
    ]

    normalized = module.validate_content_ledger(
        payload,
        slide_ids=["opening", "evidence"],
    )

    assert normalized["slides"][0]["claims"][0]["source_ids"] == []


@pytest.mark.parametrize("value", ["false", 0, 1, None])
def test_validate_content_ledger_rejects_non_boolean_publish_locator(
    value: Any,
) -> None:
    module = load_module()
    payload = ledger()
    payload["sources"][0]["publish_locator"] = value

    with pytest.raises(ValueError, match="publish_locator must be a boolean"):
        module.validate_content_ledger(payload)


def test_embedded_ledger_publishes_locator_only_after_explicit_true() -> None:
    module = load_module()
    payload = ledger()
    payload["sources"][0]["publish_locator"] = True

    markup = module.embedded_ledger_markup(payload)

    assert "/private/case/advisory_workpaper.md" in markup
