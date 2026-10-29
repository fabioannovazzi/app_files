"""Exercise the shipped matter review renderer without fabricating browser acceptance."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "asset",
    [
        "apertura-pratica/assets/apertura-pratica-review-widget.html",
        "apertura-pratica/assets/apertura-pratica-review.html",
        "archive-organization/assets/archive-organization-review-widget.html",
        "new-client/assets/new-client-review-widget.html",
        "open-item-reconciliation/assets/open-item-reconciliation-review-widget.html",
    ],
)
def test_review_assets_are_readable_without_embedded_or_remote_fonts(asset):
    html = (ROOT / "plugins" / asset).read_text()

    assert max(map(len, html.splitlines())) <= 2000
    assert "@font-face" not in html
    assert "data:font/" not in html
    assert "@import" not in html
    assert re.search(
        r"(?:font-family|--font-ui)\s*:[^;{}]*(?:system-ui|-apple-system)[^;{}]*sans-serif",
        html,
    )


def test_matter_assets_match_their_builder():
    from scripts.build_matter_review_assets import build

    generated = build()

    assert {path: path.read_text() for path in generated} == generated


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_matter_widget_shows_request_sources_and_escapes_case_text(language):
    html = (
        ROOT / "plugins/apertura-pratica/assets/apertura-pratica-review-widget.html"
    ).read_text()
    script = re.search(r"<script>([\s\S]*)</script>", html).group(1)
    labels = json.loads(
        (ROOT / "plugins/apertura-pratica/references/display-labels.json").read_text()
    )[language]
    payload = {
        "language": language,
        "evidence_sources": [{"evidence_id": "evidence-request", "name": "request.md"}],
        "items": [
            {
                "id": "request",
                "item_type": "matter_request",
                "title": labels["summary"],
                "status": "proposed",
                "recommended_action": "return",
                "allowed_actions": ["accept", "return", "reject"],
                "evidence_ids": ["evidence-request"],
                "data": {
                    "client": {
                        "display_name": "Beta <script>alert(1)</script>",
                        "identity_status": "reported",
                    },
                    "matter": {
                        "objective": "Review the missing 20 components",
                        "summary": "100 ordered; 80 received",
                        "custom_note": "retain this field",
                    },
                },
            }
        ],
    }
    program = r"""
const vm=require('node:vm'),fs=require('node:fs');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const nodes={};
const document={documentElement:{},querySelector:key=>(nodes[key]??={addEventListener(){}})};
const context={document,location:{pathname:'/review'},window:{openai:{toolOutput:{review_payload:input.payload}},addEventListener(){}}};
vm.createContext(context);vm.runInContext(input.script,context);
process.stdout.write(JSON.stringify({body:nodes['#items'].innerHTML,title:nodes['#title'].textContent,language:document.documentElement.lang,toolbarHidden:nodes['#toolbar'].hidden}));
"""
    node = shutil.which("node")
    assert node, "The supported Node runtime is required to exercise the real widget."
    result = subprocess.run(
        [node, "-e", program],
        input=json.dumps({"script": script, "payload": payload}),
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    actual = json.loads(result.stdout)
    assert actual["language"] == language
    assert actual["title"] == labels["page_title"]
    assert actual["toolbarHidden"] is True
    assert "100 ordered; 80 received" in actual["body"]
    assert "Review the missing 20 components" in actual["body"]
    assert "retain this field" in actual["body"]
    assert "request.md" in actual["body"]
    assert labels["reported"] in actual["body"]
    assert "<script>alert(1)</script>" not in actual["body"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in actual["body"]
    assert "<pre>" not in actual["body"]
    assert "[object Object]" not in actual["body"]
    assert "<select" not in actual["body"]
