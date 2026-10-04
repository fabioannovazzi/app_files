"""Native dictionary privacy, exact restoration and per-document isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mparanza_privacy_filter import rizzo_api
from mparanza_privacy_filter.contracts import FilterError
from mparanza_privacy_filter.rizzo_mapping import restore
from mparanza_privacy_filter.service import FilterService, Settings

__all__: list[str] = []


@pytest.mark.parametrize(
    "text,expected",
    [
        ("[FULLNAME_10], [FULLNAME_1]", "Bruno, Anna [FULLNAME_10]"),
        ("[FULLNAME_100] / [FULLNAME_1]", "[FULLNAME_100] / Anna [FULLNAME_10]"),
        ("FULLNAME_1 / [ FULLNAME_1 ]", "FULLNAME_1 / [ FULLNAME_1 ]"),
        ("**[FULLNAME_1]**", "**Anna [FULLNAME_10]**"),
    ],
)
def test_restore_exact_tokens_does_not_cascade_or_guess(text, expected):
    mapping = {"[FULLNAME_1]": "Anna [FULLNAME_10]", "[FULLNAME_10]": "Bruno"}
    assert restore(text, mapping) == expected


def test_mapped_api_requests_native_dictionary_without_forwarding_raw_fields(api):
    document, mapping = rizzo_api.analyze_mapped(" Anna writes. ", api.port)
    assert api.requests == [
        (
            "POST",
            "/analyze",
            {"text": "Anna writes.", "include_mapping": True, "exclude_tags": []},
        )
    ]
    assert mapping == {"[FULLNAME_1]": "Anna"}
    assert "Anna" not in str(document)


@pytest.mark.parametrize(
    "field,value",
    [
        ("mapping_enabled", False),
        ("mapping", {}),
        ("mapping", {"[FULLNAME_1]": ""}),
        ("mapping", {"[FULLNAME_1]": "Someone else"}),
        ("mapping", {"FULLNAME_1": "Anna"}),
        ("mapping", {"[SECRET_1]": "Anna"}),
        ("mapping", {"[FULLNAME_2]": "Anna"}),
        ("mapping", {"[FULLNAME_1]": 1}),
        ("n_unique", True),
        ("n_unique", 0),
    ],
)
def test_mapped_api_rejects_invalid_native_contract_without_raw_errors(
    api, field, value
):
    api.mapped_result[field] = value
    with pytest.raises(FilterError, match="^invalid_rizzo_response$"):
        rizzo_api.analyze_mapped("Anna writes.", api.port)


def test_document_session_survives_restart_and_restores_without_running_rizzo(
    tmp_path, api
):
    source = tmp_path / "input"
    source.mkdir()
    (source / "original.txt").write_text("Anna writes.")
    settings = Settings(
        source,
        tmp_path / "out",
        tmp_path / "model",
        engine="rizzo",
        rizzo_port=api.port,
    )
    service = FilterService(settings)
    receipt = service.filter_file("original.txt")
    sid = receipt["session_id"]
    state = settings.model_root / "sessions" / sid / "rizzo.json"
    assert json.loads(state.read_text()) == {"[FULLNAME_1]": "Anna"}
    assert "Anna" not in json.dumps(receipt)
    assert "Anna" not in json.dumps(service.read_result(receipt["artifact_id"]))
    assert service.status()["capabilities"]["reversible"] is True
    assert service.status()["capabilities"]["cross_document"] is False
    (source / "answer.txt").write_text("Approved: [FULLNAME_1]")
    api.status = 500

    reloaded = FilterService(settings)
    assert reloaded.open_session(sid)["documents"] == 1
    restored = reloaded.restore_file(sid, "answer.txt")
    assert Path(restored["output_path"]).read_text() == "Approved: Anna"
    assert "Anna" not in json.dumps(restored)
    with pytest.raises(FilterError, match="artifact_unavailable"):
        reloaded.read_result(Path(restored["output_path"]).parent.name)


def test_second_document_cannot_replace_existing_mapping_and_first_still_restores(
    tmp_path, api
):
    (tmp_path / "A.txt").write_text("Anna writes.")
    (tmp_path / "B.txt").write_text("Maria writes.")
    service = FilterService(
        Settings(
            tmp_path,
            tmp_path / "out",
            tmp_path / "model",
            engine="rizzo",
            rizzo_port=api.port,
        )
    )
    first = service.filter_file("A.txt")
    sid = first["session_id"]
    with pytest.raises(FilterError, match="single_document_session"):
        service.filter_file("B.txt", sid)
    with pytest.raises(FilterError, match="rizzo_batch_requires_separate_sessions"):
        service.filter_batch(["A.txt", "B.txt"], sid)
    api.mapped_result.update(n_chars=13, mapping={"[FULLNAME_1]": "Maria"})
    second = service.filter_file("B.txt")
    assert second["session_id"] != sid
    (tmp_path / "answer.txt").write_text("[FULLNAME_1]")
    assert (
        Path(service.restore_file(sid, "answer.txt")["output_path"]).read_text()
        == "Anna"
    )
    assert (
        Path(
            service.restore_file(second["session_id"], "answer.txt")["output_path"]
        ).read_text()
        == "Maria"
    )


def test_empty_native_mapping_can_be_saved_and_restore_plain_text(tmp_path, api):
    (tmp_path / "A.txt").write_text("Meeting approved.")
    api.mapped_result.update(
        anonymized_text="Meeting approved.",
        mapping={},
        by_label={},
        n_chars=17,
        n_entities=0,
        n_unique=0,
    )
    service = FilterService(
        Settings(
            tmp_path,
            tmp_path / "out",
            tmp_path / "model",
            engine="rizzo",
            rizzo_port=api.port,
        )
    )
    receipt = service.filter_file("A.txt")
    assert receipt["detection_counts"] == {}
    result = service.restore_file(receipt["session_id"], "A.txt")
    assert Path(result["output_path"]).read_text() == "Meeting approved."
