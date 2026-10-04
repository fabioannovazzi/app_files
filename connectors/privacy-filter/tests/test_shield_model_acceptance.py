"""Opt-in real PII-Shield session acceptance; no client data or model downloads."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from mparanza_privacy_filter.service import FilterService, Settings

__all__: list[str] = []

MODEL_ROOT = os.environ.get("SHIELD_TEST_ROOT")
pytestmark = pytest.mark.skipif(
    not MODEL_ROOT,
    reason="Set SHIELD_TEST_ROOT to an explicitly prepared local PII-Shield runtime",
)


def test_real_shield_three_documents_five_people_consistent_and_restored(
    tmp_path: Path,
) -> None:
    people = (
        "John Smith",
        "Mary Johnson",
        "Robert Brown",
        "Patricia Williams",
        "Michael Davis",
    )
    source = tmp_path / "inputs"
    source.mkdir()
    for filename, ordered in (
        ("A.txt", people),
        ("B.txt", tuple(reversed(people))),
        ("C.txt", people[2:] + people[:2]),
    ):
        (source / filename).write_text(
            "\n".join(f"Full legal name: {person}." for person in ordered)
        )
    service = FilterService(
        Settings(source, tmp_path / "output", Path(MODEL_ROOT), engine="pii-shield")
    )
    assert service.status()["model_ready"] is True
    sid = service.create_session()["session_id"]

    first = service.filter_file("A.txt", sid)
    second = service.filter_file("B.txt", sid)
    reloaded = FilterService(service.settings)
    third = reloaded.filter_file("C.txt", sid)
    filtered = [
        reloaded.read_result(item["artifact_id"])["redacted_text"]
        for item in (first, second, third)
    ]
    tokens = re.findall(r"<PERSON_\d+[a-z]?>", filtered[0])
    assert len(tokens) == len(set(tokens)) == 5, filtered
    assert re.findall(r"<PERSON_\d+[a-z]?>", filtered[1]) == list(reversed(tokens))
    assert re.findall(r"<PERSON_\d+[a-z]?>", filtered[2]) == tokens[2:] + tokens[:2]
    assert not any(
        person in json.dumps((first, second, third, filtered)) for person in people
    )
    assert reloaded.open_session(sid)["documents"] == 3

    (source / "answer.txt").write_text("Approved: " + "; ".join(reversed(tokens)))
    result = reloaded.restore_file(sid, "answer.txt")
    assert Path(result["output_path"]).read_text() == "Approved: " + "; ".join(
        reversed(people)
    )
    assert not any(person in json.dumps(result) for person in people)
