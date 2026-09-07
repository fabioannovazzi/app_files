from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.generate_non_plotting_review_widgets import TARGETS, render_target

ROOT = Path(__file__).resolve().parents[2]
ASSET = (
    ROOT
    / "plugins/open-item-reconciliation/assets/open-item-reconciliation-review-widget.html"
)


def test_accounting_widget_generation_preserves_server_bridge_and_matches_source() -> (
    None
):
    target = next(
        item for item in TARGETS if item["plugin"] == "open-item-reconciliation"
    )
    html = render_target(target)

    assert html == ASSET.read_text(encoding="utf-8")
    assert "  <script>\n    const CONFIG = " in html
    assert html.index('class="content"') < html.index('class="review-actions"')
    assert html.index('class="desk-diagnostics"') < html.index(
        'id="execution-provenance"'
    )


def test_accounting_copy_covers_every_supported_locale() -> None:
    translations = json.loads(
        (ROOT / "scripts/review_widgets/open_item_i18n.json").read_text()
    )

    assert set(translations) == {"it", "en", "fr", "de", "es"}
    assert {tuple(sorted(values)) for values in translations.values()} == {
        tuple(sorted(translations["en"]))
    }


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_accounting_desk_separates_documents_and_withholds_unproven_settlement(
    tmp_path: Path, language: str
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to execute the generated widget")
    html = ASSET.read_text(encoding="utf-8")
    javascript = re.search(r"<script>(.*?)</script>", html, re.DOTALL)[1]
    javascript = re.split(
        r'^    document\.getElementById\("[^\"]+"\)\.addEventListener',
        javascript,
        maxsplit=1,
        flags=re.MULTILINE,
    )[0]
    exercise = r"""
    const assert = require("node:assert/strict");
    const base = {id:"one",item_type:"missing_evidence_review",allowed_actions:["accept"],data:{document_no:"INV-1",amount:"1000.00",currency:"EUR",reconciliation_status:"needs_evidence",allocated_amount:"1000.00",residual_amount:"0",relationship_control_status:"failed"}};
    state.payload={review_payload:{language:LANG,items:[base,{id:"doc",item_type:"workpaper_artifact"},{id:"check",item_type:"check_exception"}]}};
    assert.equal(filteredItems().length,1);
    assert.equal(filteredItems()[0].id,"one");
    const unsupported=detailsHtml(base);
    assert.ok(unsupported.includes(esc(deskText("unsupportedNote"))));
    assert.ok(unsupported.includes(`<strong>${esc(deskText("unavailable"))}</strong>`));
    assert.ok(!unsupported.includes('<strong>0,00 EUR</strong>'));
    const partial={...base,data:{...base.data,reconciliation_status:"partially_paid",allocated_amount:"400.00",residual_amount:"600.00",relationship_control_status:"passed"}};
    const supported=detailsHtml(partial);
    assert.ok(supported.includes(esc(deskMoney("400.00","EUR"))));
    assert.ok(supported.includes(esc(deskMoney("600.00","EUR"))));
    assert.ok(decisionImpactHtml(base,"accept").includes(esc(deskText("acceptEffect"))));
    state.selectedType="documents";
    assert.deepEqual(filteredItems().map(item=>item.id),["doc"]);
    state.selectedType="exceptions";
    assert.deepEqual(filteredItems().map(item=>item.id),["check"]);
    assert.ok(detailsHtml({...base,data:{...base.data,document_no:"<img src=x onerror=alert(1)>"}}).includes("&lt;img"));
    const elements={"save-status":{},"review-checkpoint":{value:"",focus(){}},"checkpoint-details":{open:false}};
    const document={getElementById(id){return elements[id];}};
    assert.throws(()=>applyToolArgs(),new RegExp(deskText("checkpointRequired").replace(/[.*+?^${}()|[\]\\]/g,"\\$&")));
    assert.equal(elements["checkpoint-details"].open,true);
    elements["review-checkpoint"].value="a".repeat(64);
    assert.equal(applyToolArgs().expected_predecessor_checkpoint,"a".repeat(64));
    const window={openai:{}};
    copyDecisionJson=async()=>{};
    setRecoveryIssue=()=>{};
    renderProgress=()=>{};
    state.decisions={one:{item_id:"one",action:"accept"}};
    handleSaveDecisions().then(()=>{
      assert.equal(elements["save-status"].textContent,deskText("notPersisted"));
      assert.equal(savedDecisionInputs().length,0);
    }).catch(error=>{console.error(error);process.exitCode=1;});
    """.replace("LANG", json.dumps(language))
    script = tmp_path / "widget-test.cjs"
    script.write_text(javascript + exercise, encoding="utf-8")
    result = subprocess.run(
        [node, str(script)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
