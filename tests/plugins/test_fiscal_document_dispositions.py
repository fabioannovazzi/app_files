from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "plugins/client-file-preparation/scripts/parse_fiscal_forms.py"
)
COVER_LETTER = "Lettera: il modello F24 sara fornito successivamente."


@pytest.fixture
def parser(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Load the public parser without keeping its script search path."""
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("fiscal_disposition_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def evidence(parser: Any, name: str, text_path: str, readable: bool = True) -> Any:
    """Make one synthetic extracted-source record."""
    return parser.DocumentEvidence(
        relative_path=name,
        file_name=name,
        extension=".pdf",
        category="unknown",
        extraction_method="synthetic",
        readable=readable,
        needs_ocr=False,
        ocr_available=False,
        page_count=1,
        char_count=len(COVER_LETTER),
        text_path=text_path,
        confidence="low",
        detected_fields_json="{}",
        notes=(),
    )


def reviewed_cover_letter() -> dict[str, dict[str, str]]:
    """Bind the reviewed unsupported decision to the exact cover text."""
    return {
        "F24.pdf": {
            "kind": "unsupported",
            "basis": "model_review",
            "text_sha256": hashlib.sha256(COVER_LETTER.encode()).hexdigest(),
        }
    }


def test_reviewed_cover_letter_overrides_misleading_filename(
    parser: Any, tmp_path: Path
) -> None:
    (tmp_path / "cover.txt").write_text(COVER_LETTER, encoding="utf-8")
    source = evidence(parser, "F24.pdf", "cover.txt")

    fields = parser.parse_structured_fiscal_fields(
        [source], tmp_path, kind_decisions=reviewed_cover_letter()
    )

    disposition = json.loads((tmp_path / "document_dispositions.json").read_text())[
        "documents"
    ][0]
    assert fields == []
    assert disposition["candidate_kind"] == "F24"
    assert disposition["selected_kind"] == "unsupported"
    assert disposition["status"] == "reviewed_unsupported"


@pytest.mark.parametrize("readable,text_path", [(False, ""), (True, "missing.txt")])
def test_unreadable_source_keeps_explicit_disposition(
    parser: Any, tmp_path: Path, readable: bool, text_path: str
) -> None:
    source = evidence(parser, "source.pdf", text_path, readable)

    fields = parser.parse_structured_fiscal_fields([source], tmp_path)

    documents = json.loads((tmp_path / "document_dispositions.json").read_text())[
        "documents"
    ]
    assert fields == []
    assert len(documents) == 1
    assert documents[0]["relative_path"] == "source.pdf"
    assert documents[0]["status"] == "unreadable"
    assert documents[0]["field_count"] == 0


def test_changed_text_rejects_previous_document_kind_review(
    parser: Any, tmp_path: Path
) -> None:
    (tmp_path / "cover.txt").write_text(COVER_LETTER + " Revised.", encoding="utf-8")
    source = evidence(parser, "F24.pdf", "cover.txt")

    with pytest.raises(ValueError, match="stale document-kind decision"):
        parser.parse_structured_fiscal_fields(
            [source], tmp_path, kind_decisions=reviewed_cover_letter()
        )
