"""A declared local review must name real source files and persistent state."""

from __future__ import annotations

import json

from tests.scripts.test_audit_plugin_interaction_patterns import (
    load_audit_module,
    write_plugin,
)


def test_existing_treasury_server_is_recognized_without_inventing_mcp_widget():
    audit = load_audit_module()
    report = audit.audit_plugin(audit.ROOT / "plugins/treasury-forecast")
    assert report.has_local_browser_writeback
    assert report.stateful_decision_review
    assert not report.mcp_review_widget
    assert "static_review_without_mcp_widget" not in {
        issue.code for issue in report.issues
    }


def test_declaration_without_server_cannot_mask_a_static_review(tmp_path):
    audit = load_audit_module()
    plugin = write_plugin(
        tmp_path,
        "native-review",
        "local deterministic external destructive approval-sensitive material scripts/run.py treasury_session.json final_artifacts.json",
        asset_text="<p>Review</p>",
    )
    contract = {
        "schema_version": 1,
        "transport": "loopback_http",
        "entrypoint": "scripts/run.py",
        "server": "scripts/missing.py",
        "persistence": "scripts/session.py",
        "review_asset": "assets/review.html",
        "state_artifact": "treasury_session.json",
    }
    (plugin / "assets/local-review-contract.json").write_text(json.dumps(contract))
    report = audit.audit_plugin(plugin)
    assert not report.has_local_browser_writeback
