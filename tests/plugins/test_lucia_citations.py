from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/lucia/scripts"))
from legal_citations import main as citations_main
from legal_citations import render_citations, scaffold, validate_citations
from legal_documents import prepare


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError(
            "Citation helpers must not research or transmit client data"
        )

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def case(tmp_path):
    document = tmp_path / "draft.txt"
    document.write_text("La fonte di prova richiede una comunicazione scritta.")
    source = tmp_path / "authority.txt"
    source.write_text(
        "Fonte fittizia per test software, versione 2.\nLa comunicazione deve essere scritta.\n"
    )
    run = tmp_path / "citations"
    prepare(run, [document, source], "revisione-documentale", ["Citazioni"])
    path = scaffold(run, ["D001"], "Controllo del documento di prova")
    value = json.loads(path.read_text())
    value["inventory"]["D001"].update(reviewed_anchors=["line:1"], limitations=[])
    value["authorities"] = [
        {
            "id": "A1",
            "citation": "Fonte fittizia, versione 2",
            "kind": "other",
            "url": "https://example.invalid/authority",
            "source_id": "D002",
            "access": "full-text",
            "checked_at": "2026-09-23",
            "version": "Versione 2; fonte fittizia",
            "reviewed_anchors": ["line:1", "line:2"],
            "limitations": [],
        }
    ]
    value["claims"] = [
        {
            "id": "C1",
            "document_passage": {
                "source_id": "D001",
                "anchor": "line:1",
                "quote": "La fonte di prova richiede una comunicazione scritta.",
            },
            "proposition": "Forma scritta prevista dalla fonte fittizia",
            "relevant_date": "Versione 2 del caso software fittizio",
            "correction": "Conservare il testo per questo solo controllo software.",
            "checks": [
                {
                    "authority_id": "A1",
                    "identity": "matched",
                    "version": "applicable",
                    "support": "supports",
                    "passages": [
                        {
                            "source_id": "D002",
                            "anchor": "line:2",
                            "quote": "La comunicazione deve essere scritta.",
                        }
                    ],
                    "reasoning": "La proposizione del documento corrisponde al testo della fonte di prova, nella versione selezionata.",
                }
            ],
        }
    ]
    return run, value


def test_complete_source_and_separate_document_quotes_support_recorded_judgment(
    tmp_path,
):
    run, value = case(tmp_path)
    result = validate_citations(run, value)
    assert result["valid"] is True
    assert result["inventory_complete"] is True
    assert result["checks"] == [
        {"claim_id": "C1", "authority_id": "A1", "result": "supported"}
    ]


@pytest.mark.parametrize(
    "field,status,expected",
    [
        ("identity", "mismatch", "wrong-identity"),
        ("version", "wrong-version", "wrong-version"),
        ("support", "contradicts", "not-supported"),
        ("support", "does-not-address", "not-supported"),
        ("support", "partial", "partial"),
        ("identity", "unresolved", "unverified"),
    ],
)
def test_recorded_source_failures_remain_distinct(tmp_path, field, status, expected):
    run, value = case(tmp_path)
    value["claims"][0]["checks"][0][field] = status
    result = validate_citations(run, value)
    assert result["valid"] is True
    assert result["checks"][0]["result"] == expected


def test_excerpt_cannot_be_promoted_to_fully_verified_authority(tmp_path):
    run, value = case(tmp_path)
    value["authorities"][0]["access"] = "excerpt"
    result = validate_citations(run, value)
    assert result["valid"] is True
    assert result["checks"][0]["result"] == "unverified"


def test_unavailable_source_stays_unverified_without_preventing_other_work(tmp_path):
    run, value = case(tmp_path)
    value["authorities"][0].update(
        source_id=None,
        access="unavailable",
        reviewed_anchors=[],
        limitations=["Il testo non è stato raggiunto."],
    )
    value["claims"][0]["checks"][0].update(
        identity="unresolved", version="unresolved", support="unresolved", passages=[]
    )
    result = validate_citations(run, value)
    assert result["valid"] is True
    assert result["checks"][0]["result"] == "unverified"


def test_inaccessible_text_cannot_carry_a_claim_of_verification(tmp_path):
    run, value = case(tmp_path)
    value["authorities"][0].update(
        source_id=None,
        access="unavailable",
        reviewed_anchors=[],
        limitations=["Non accessibile"],
    )
    result = validate_citations(run, value)
    assert result["valid"] is False
    assert any("inaccessible source" in e for e in result["errors"])


def test_a_draft_cannot_be_used_as_its_own_legal_authority(tmp_path):
    run, value = case(tmp_path)
    value["authorities"][0].update(source_id="D001", reviewed_anchors=["line:1"])
    result = validate_citations(run, value)
    assert result["valid"] is False
    assert any("own citation" in e for e in result["errors"])


@pytest.mark.parametrize("quote", [" ", "This text was never in the source."])
def test_unsupported_or_blank_quotes_cannot_pass(tmp_path, quote):
    run, value = case(tmp_path)
    value["claims"][0]["checks"][0]["passages"][0]["quote"] = quote
    assert validate_citations(run, value)["valid"] is False


def test_reviewing_only_part_of_authority_cannot_yield_verified_support(tmp_path):
    run, value = case(tmp_path)
    value["authorities"][0]["reviewed_anchors"] = ["line:2"]
    result = validate_citations(run, value)
    assert result["valid"] is True
    assert result["checks"][0]["result"] == "unverified"


def test_unreviewed_document_inventory_is_visible_even_when_one_claim_is_supported(
    tmp_path,
):
    run, value = case(tmp_path)
    value["inventory"]["D001"]["reviewed_anchors"] = []
    result = validate_citations(run, value)
    assert result["valid"] is True
    assert result["inventory_complete"] is False
    assert result["limitations"]


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://secret:token@example.invalid/source",
    ],
)
def test_authority_urls_cannot_execute_code_or_expose_credentials(tmp_path, url):
    run, value = case(tmp_path)
    value["authorities"][0]["url"] = url
    assert validate_citations(run, value)["valid"] is False


@pytest.mark.parametrize(
    "language,title",
    [
        ("it", "Verifica delle citazioni"),
        ("en", "Citation and authority"),
        ("fr", "Vérification des citations"),
        ("de", "Prüfung von Zitaten"),
        ("es", "Verificación de citas"),
    ],
)
def test_render_includes_proposition_source_support_and_data_path(
    tmp_path, language, title
):
    run, value = case(tmp_path)
    value["language"] = language
    value["claims"][0]["correction"] = '<script>alert("not executed")</script>'
    path = run / "citations.json"
    path.write_text(json.dumps(value))
    page = render_citations(run, path).read_text()
    assert title in page
    assert "2026-09-23" in page
    assert "La comunicazione deve essere scritta." in page
    assert "<script>alert(" not in page
    assert "&lt;script&gt;" in page


def test_failed_rerender_does_not_leave_old_report_as_current(tmp_path):
    run, value = case(tmp_path)
    path = run / "citations.json"
    path.write_text(json.dumps(value))
    render_citations(run, path)
    value["claims"][0]["checks"][0]["passages"][0]["quote"] = "Fabricated"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="quotation not found"):
        render_citations(run, path)
    assert not (run / "citations.html").exists()
    assert (run / "previous-1-citations.html").exists()


def test_cli_render_reports_actual_validation_failure(tmp_path):
    run, value = case(tmp_path)
    value["authorities"][0]["checked_at"] = "2026-02-31"
    (run / "citations.json").write_text(json.dumps(value))
    assert citations_main(["render", "--run-dir", str(run)]) == 2
