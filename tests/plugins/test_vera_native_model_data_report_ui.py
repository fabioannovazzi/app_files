"""Saved report text stays readable and inert in its standalone DOM renderer."""

from __future__ import annotations

import copy
import json
import subprocess

import pytest

from tests.plugins.test_vera_model_data_report import (
    _full_document_request,
    _load_module,
    _reduced_request,
)
from tests.plugins.test_vera_native_workspace import NODE, ROOT

__all__ = []


def report_view(report: dict, markdown: str) -> dict:
    """Exercise the renderer directly; Fusione is outside selective reporting."""
    source = ROOT / "plugins/vera/ui/model-data-report.js"
    code = """
const fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag,text) { this.tagName=tag.toUpperCase();this.text=text||'';this.children=[]; }
  append(...items) { this.children.push(...items); }
}
const sandbox={globalThis:{}};
vm.runInNewContext(fs.readFileSync(SOURCE,'utf8'),sandbox);
const parent=new Element('main');
sandbox.globalThis.VeraModelDataReport.render(parent,MARKDOWN,{node:(tag,text)=>new Element(tag,text)});
const collect=e=>[e,...e.children.flatMap(collect)],nodes=collect(parent);
process.stdout.write(JSON.stringify({
  text:nodes.map(x=>x.text).join(' '),calls:[],tags:nodes.map(x=>x.tagName),
  report:parent.children.map(x=>x.children.map(c=>({tag:c.tagName,text:c.text,items:c.children.map(y=>y.text)})))
}));
""".replace(
        "SOURCE", json.dumps(str(source))
    ).replace(
        "MARKDOWN", json.dumps(markdown, ensure_ascii=False)
    )
    result = subprocess.run(
        [NODE, "-e", code], capture_output=True, text=True, check=True, timeout=20
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_native_report_displays_canonical_localized_full_context_text(
    tmp_path, language
):
    report, markdown = _load_module().build_model_data_report(
        _full_document_request(language), evidence_root=tmp_path
    )

    result = report_view(report, markdown)

    assert "84 pages" in result["text"]
    assert "1 files" in result["text"]
    assert "Section relationships could not be reviewed" in result["text"]
    assert "semantic-review" in result["text"]
    assert result["calls"] == []
    assert len(result["report"]) == 1
    assert "IFRAME" not in result["tags"]


def test_native_report_keeps_all_phases_and_separate_units(tmp_path):
    (tmp_path / "mapping_payload.json").write_text('{"fictional":true}')
    request = _reduced_request()
    full = _full_document_request()["phases"][0]
    unknown = copy.deepcopy(full)
    unknown.update(
        phase_id="unknown-exposure",
        outcome="not_measurable",
        evidence_basis="not_measurable",
        model_visible=[],
        reason="Host exposure is unknown; no reduction is inferred.",
    )
    request["phases"].extend([full, unknown])
    for number in range(71):
        phase = copy.deepcopy(full)
        phase["phase_id"] = f"complete-phase-{number}"
        request["phases"].append(phase)
    report, markdown = _load_module().build_model_data_report(
        request, evidence_root=tmp_path
    )

    result = report_view(report, markdown)

    headings = [row for row in result["report"][0] if row["tag"] == "H4"]
    assert len(headings) == 75  # 74 phases plus the retained improvement candidate.
    assert "complete-phase-70" in result["text"]
    assert "Host exposure is unknown; no reduction is inferred." in result["text"]
    assert "10,000 rows" in result["text"]
    assert "14 columns" in result["text"]
    assert "84 pages" in result["text"]
    assert (
        "Confrontare casi rappresentativi e mantenere il drill-down esatto."
        in result["text"]
    )
    assert result["calls"] == []


def test_native_report_treats_html_links_and_scripts_as_literal_text():
    markdown = '# Saved report\n\n<script>alert("fictional")</script>\n- [external](https://example.invalid/)\n\n### Retained phase\n\n<img src=x onerror=alert(1)>\n'

    result = report_view({}, markdown)

    assert '<script>alert("fictional")</script>' in result["text"]
    assert "[external](https://example.invalid/)" in result["text"]
    assert "<img src=x onerror=alert(1)>" in result["text"]
    assert not {"SCRIPT", "IMG", "IFRAME", "A"}.intersection(result["tags"])
    assert result["calls"] == []
