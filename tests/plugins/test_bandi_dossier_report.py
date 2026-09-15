"""Check the native report's evidence, localization and safe local presentation."""

from __future__ import annotations

import copy
import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from tests.plugins.test_bandi_agevolazioni_plugin import (
    _initialized_case,
    _read,
    _reviewable_workbench,
)


class ReportStructure(HTMLParser):
    """Collect rendered markup without executing any report content."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.links: list[str] = []
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str | None]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)
        values = dict(attrs)
        if "id" in values:
            self.ids.append(values["id"])
        if "href" in values:
            self.links.append(values["href"])

    def handle_data(self, data):
        self.text.append(data)


def report_structure(content: str) -> ReportStructure:
    structure = ReportStructure()
    structure.feed(content)
    return structure


def assert_local_report_links(content: str) -> None:
    structure = report_structure(content)
    assert len(structure.ids) == len(set(structure.ids))
    assert {link[1:] for link in structure.links if link.startswith("#")} <= set(
        structure.ids
    )
    assert not {"script", "iframe", "img", "form", "object", "embed"} & set(
        structure.tags
    )
    assert not any(name.startswith("on") for name, _ in structure.attrs)
    assert not any("://" in link or link.startswith("//") for link in structure.links)
    assert "Content-Security-Policy" in content


def _records(tmp_path):
    scripts, workspace = _initialized_case(tmp_path)
    output = workspace["output_dir"]
    _reviewable_workbench(output)
    return scripts["report"], {
        "intake": _read(output / "case_intake.json"),
        "sources": _read(output / "source_register.json"),
        "workbench": _read(output / "application_workbench.json"),
        "run_state": _read(output / "run_state.json"),
        "audit": {"limitations": []},
    }


@pytest.mark.parametrize(
    ("language", "title", "amount"),
    [
        ("it", "Dossier per un bando", "1.000,00 EUR"),
        ("en", "Grant-application dossier", "1,000.00 EUR"),
        ("fr", "Dossier de demande d’aide", "1\u202f000,00 EUR"),
        ("de", "Förderantragsdossier", "1.000,00 EUR"),
        ("es", "Expediente de solicitud de ayuda", "1.000,00 EUR"),
    ],
)
def test_report_localizes_labels_and_keeps_every_evidence_link(
    tmp_path, language, title, amount
):
    renderer, records = _records(tmp_path)
    records["run_state"]["language"] = language
    original = copy.deepcopy(records)

    report = renderer.render_dossier_html(**records)

    assert f'<html lang="{language}">' in report
    assert title in report
    assert amount in report
    assert "Bozza narrativa sintetica." in report
    assert "Giudizio professionale sintetico per il test." in report
    assert_local_report_links(report)
    assert records == original


def test_report_escapes_untrusted_content_and_keeps_multiple_assessments(tmp_path):
    renderer, records = _records(tmp_path)
    payload = '<script>alert("x")</script><img src="https://example.invalid/track">'
    records["workbench"]["case_summary"] = payload
    records["intake"]["application"]["title"] = payload
    records["workbench"]["requirements"][0]["source_refs"][0]["excerpt"] = payload
    records["workbench"]["narratives"][0]["draft"] = payload
    records["workbench"]["facts"][0]["value"] = {"untrusted": payload}
    second = copy.deepcopy(records["workbench"]["assessments"][0])
    second.update(assessment_id="ASM-SECOND", rationale="Second independent assessment")
    records["workbench"]["assessments"].append(second)

    report = renderer.render_dossier_html(**records)

    assert payload in "".join(report_structure(report).text)
    assert "Second independent assessment" in report
    assert "Giudizio professionale sintetico per il test." in report
    assert "&lt;script&gt;" in report
    assert_local_report_links(report)


@pytest.mark.parametrize("submitted", [True, False])
def test_report_describes_actual_action_flags_without_claiming_authorization(
    tmp_path, submitted
):
    renderer, records = _records(tmp_path)
    records["run_state"].update(language="en", submission_actions_performed=submitted)

    report = renderer.render_dossier_html(**records)

    status = "Recorded" if submitted else "Not recorded"
    assert f"<dt>Submission</dt><dd>{status}</dd>" in report
    assert "It does not authorize signing or submission." in report
    assert records["workbench"]["dossier"]["ready_to_file"] is False


def test_empty_report_preserves_unknown_language_content_and_missing_values(tmp_path):
    renderer, records = _records(tmp_path)
    records["run_state"]["language"] = "nl"
    records["workbench"]["case_summary"] = "Eigen samenvatting"
    for key in (
        "requirements",
        "assessments",
        "facts",
        "document_checklist",
        "expenses",
        "form_fields",
        "narratives",
        "consistency_checks",
        "issues",
    ):
        records["workbench"][key] = []
    records["workbench"]["authority_simulation"] = {
        "overall_outcome": "not_run",
        "reviewer_perspective": "",
        "checks": [],
    }
    records["sources"]["sources"] = []
    records["intake"]["project"]["requested_amount"] = None

    report = renderer.render_dossier_html(**records)

    assert '<html lang="en">' in report
    assert "Eigen samenvatting" in report
    assert "No entries recorded." in report
    assert "<dt>Proposed requested amount</dt><dd>—</dd>" in report
    assert "No issues recorded. Outstanding reviews are still required." in report
    assert_local_report_links(report)


def test_report_retains_open_issues_and_unassessed_requirements(tmp_path):
    renderer, records = _records(tmp_path)
    records["workbench"]["assessments"] = []
    records["workbench"]["authority_simulation"]["checks"][0]["related_ids"].remove(
        "ASM-001"
    )
    records["workbench"]["issues"] = [
        {
            "issue_id": "ISSUE-1",
            "detail": "Evidence must be clarified",
            "related_ids": ["REQ-001"],
            "status": "open",
            "review_status": "proposed",
        }
    ]
    records["workbench"]["requirements"][0]["review_status"] = "future_status"

    report = renderer.render_dossier_html(**records)

    assert "Evidence must be clarified" in report
    assert "Valutazione non ancora registrata." in report
    assert "future_status" in report
    assert_local_report_links(report)


@pytest.mark.parametrize("amount", ["not an amount", "NaN"])
def test_report_does_not_silently_turn_invalid_recorded_amount_into_zero(
    tmp_path, amount
):
    renderer, records = _records(tmp_path)
    records["intake"]["project"]["requested_amount"] = amount

    report = renderer.render_dossier_html(**records)

    assert f"<dt>Importo richiesto proposto</dt><dd>{amount}</dd>" in report


def test_report_translation_sets_have_identical_keys():
    path = (
        Path(__file__).resolve().parents[2]
        / "plugins/bandi-agevolazioni/assets/dossier-labels.json"
    )
    labels = json.loads(path.read_text())

    assert set(labels) == {"it", "en", "fr", "de", "es"}
    assert all(set(values) == set(labels["en"]) for values in labels.values())
    assert all(value.strip() for values in labels.values() for value in values.values())
