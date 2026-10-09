"""Public named-source receipts preserve complete sealed parents and explicit scope."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_financial_execution import (
    archive_environment,
    execute_script,
    financial_intake,
)
from tests.plugins.test_vera_native_workspace import workspace_module

__all__ = []


@pytest.fixture
def custom_source(request, tmp_path, monkeypatch):
    """Write controlled source bytes before the public fixture seals its contracts."""
    original = Path.write_text
    source = tmp_path / "originals/source.txt"

    def write_text(path, value, *args, **kwargs):
        if path == source:
            path.write_bytes(request.param)
            return len(request.param)
        return original(path, value, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write_text)
    return financial_intake.__wrapped__(
        SimpleNamespace(param="net_debt"), tmp_path, monkeypatch
    )


def source_script(fixture) -> str:
    return (
        execute_script(fixture)
        + """
const execution=payload(call('vera_workspace_financial_execute',executeArgs));
const inventory=payload(call('vera_workspace_financial_source_setup',{work_ref:exact.work_ref,source_ref:execution.source_ref}));
const item=inventory.items[0];
const chosen={work_ref:exact.work_ref,source_ref:execution.source_ref,item_id:item.artifact_id};
const page=payload(call('vera_workspace_financial_source_setup',chosen));
const fields={question:'Verify the origin of this one fictional sealed source.',selectors_text:'record alpha\nperiod 2025'};
const grantArgs={...chosen,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision,fields,confirmed:true,human_reviewed:true,idempotency_key:'fictional-financial-source'};
""".replace(
            "record alpha\nperiod", "record alpha\\nperiod"
        )
    )


def test_native_financial_named_source_uses_public_receipt_and_preserves_parent(
    financial_intake,
):
    env, output, *_ = financial_intake
    result = rpc_program(
        env,
        source_script(financial_intake)
        + """
const beforeView=payload(call('vera_workspace_financial_view',{work_ref:exact.work_ref,source_ref:execution.source_ref}));
const grant=payload(call('vera_workspace_financial_source_grant',grantArgs));
const retry=payload(call('vera_workspace_financial_source_grant',grantArgs));
const view=payload(call('vera_workspace_financial_source_view',{work_ref:exact.work_ref,grant_ref:grant.grant_ref}));
const context=call('vera_workspace_financial_source_context',{work_ref:exact.work_ref,grant_ref:grant.grant_ref,revision:view.revision}).structuredContent;
const after=payload(call('vera_workspace_financial_setup',{work_ref:exact.work_ref}));
const result={execution,grant,retry,view,context,after,source:item};
""",
    )
    assert result["grant"] == result["retry"]
    assert result["grant"]["professional_approval"] is False
    assert result["grant"]["run_completed"] is False
    assert result["context"]["report_ready"] is False
    assert result["context"]["source_artifact_id"] == result["source"]["artifact_id"]
    with Path(result["context"]["authorized_source_path"]).open(
        encoding="utf-8", newline=""
    ) as handle:
        expected = handle.read()
    assert result["context"]["page"]["text"] == expected[:24000]
    assert (
        result["context"]["public_receipt"]["authorization"]
        == "open_only_this_named_source_for_the_recorded_question"
    )
    assert result["context"]["public_receipt"]["selectors"] == [
        "period 2025",
        "record alpha",
    ]
    assert len(result["after"]["versions"]) == 1
    assert result["after"]["recovery_required"] is False
    parent = output / result["execution"]["source_ref"]
    derivative = output / result["grant"]["grant_ref"]
    assert not (parent / "prepared/model_drilldowns").exists()
    for path in parent.rglob("*"):
        if path.is_file():
            assert (
                path.read_bytes()
                == (derivative / path.relative_to(parent)).read_bytes()
            )
    receipts = list(
        derivative.glob("prepared/model_drilldowns/evidence_request_*.json")
    )
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_bytes()) == result["context"]["public_receipt"]


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_unsent_question_draft_recovers_and_refuses_concurrent_empty_replay(
    financial_intake,
):
    env, output, *_ = financial_intake
    result = rpc_program(
        env,
        source_script(financial_intake)
        + """
const save={...chosen,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision,fields};
const saved=payload(call('vera_workspace_financial_source_draft_save',save));
const stale=call('vera_workspace_financial_source_draft_save',{...save,fields:{question:'',selectors_text:''}});
const reopened=payload(call('vera_workspace_financial_source_setup',chosen));
const cleared=payload(call('vera_workspace_financial_source_draft_save',{...save,expected_draft_revision:reopened.draft_revision,fields:{question:'',selectors_text:''}}));
const replay=call('vera_workspace_financial_source_draft_save',{...save,expected_draft_revision:reopened.draft_revision});
const result={saved,stale,reopened,cleared,replay,after:payload(call('vera_workspace_financial_source_setup',chosen))};
""",
    )
    assert (
        result["reopened"]["draft"]["question"]
        == "Verify the origin of this one fictional sealed source."
    )
    assert result["stale"]["isError"] is True
    assert result["replay"]["isError"] is True
    assert result["after"]["draft"] == {"question": "", "selectors_text": ""}
    assert result["after"]["grants"] == []
    assert list(output.glob("financial-evidence-*")) == []


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
@pytest.mark.parametrize(
    "change",
    [
        "item_id:'foreign'",
        "source_ref:'foreign'",
        "revision:'stale'",
        "confirmed:false",
        "fields:{question:'',selectors_text:''}",
        "expected_draft_revision:'stale'",
    ],
)
def test_native_financial_invalid_source_request_does_not_authorize_or_copy(
    financial_intake, change
):
    env, output, *_ = financial_intake
    result = rpc_program(
        env,
        source_script(financial_intake)
        + f"const result=call('vera_workspace_financial_source_grant',{{...grantArgs,{change}}});",
    )
    assert result["isError"] is True
    assert list(output.glob("financial-evidence-*")) == []


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_changed_request_source_refuses_context_and_closure(
    financial_intake,
):
    env, output, binding, *_ = financial_intake
    stored = rpc_program(
        env,
        source_script(financial_intake)
        + "const result=payload(call('vera_workspace_financial_source_grant',grantArgs));",
    )
    source = next((output / stored["grant_ref"] / "case").glob("source.txt"))
    source.write_bytes(source.read_bytes() + b"\n")
    result = rpc_program(
        env,
        f"const result=call('vera_workspace_financial_source_view',{{work_ref:'fictional-financial',grant_ref:{json.dumps(stored['grant_ref'])}}});",
    )
    assert result["isError"] is True
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    closure = rpc_program(
        archive_environment(env, binding, output),
        f"const result=call('vera_workspace_archive_closure',{json.dumps(selected)});",
    )
    assert closure["isError"] is True
    assert "source request artifacts changed" in closure["content"][0]["text"]


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_interrupted_public_source_authorization_blocks_retry_and_closure(
    financial_intake, monkeypatch
):
    env, output, binding, *_ = financial_intake
    prepared = rpc_program(
        env, source_script(financial_intake) + "const result={args:grantArgs};"
    )
    module = workspace_module()
    import native_financial_sources as sources

    original = sources.bridge

    def interrupted(root, request):
        if request["operation"] == "authorize":
            raise OSError("Fictional source authorization interrupted")
        return original(root, request)

    monkeypatch.setattr(sources, "bridge", interrupted)
    args = prepared["args"]
    args.pop("review_ticket")
    with pytest.raises(OSError, match="Fictional source authorization interrupted"):
        module.dispatch("vera_workspace_financial_source_grant", args)
    monkeypatch.setattr(sources, "bridge", original)
    result = rpc_program(
        env,
        "const result=payload(call('vera_workspace_financial_setup',{work_ref:'fictional-financial'}));",
    )
    assert result["recovery_required"] is True
    assert len(list(output.glob("financial-evidence-*"))) == 1
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    closure = rpc_program(
        archive_environment(env, binding, output),
        f"const result=call('vera_workspace_archive_closure',{json.dumps(selected)});",
    )
    assert closure["isError"] is True
    assert "requires recovery before output closure" in closure["content"][0]["text"]


@pytest.mark.parametrize(
    "custom_source",
    [("αβ🙂\r\n" * 14000).encode()],
    indirect=True,
    ids=["complete-unicode-pages"],
)
def test_native_financial_source_pages_cover_complete_utf8_with_multibyte_boundaries(
    custom_source,
):
    env, *_ = custom_source
    result = rpc_program(
        env,
        source_script(custom_source)
        + """
const grant=payload(call('vera_workspace_financial_source_grant',grantArgs));
const first=payload(call('vera_workspace_financial_source_view',{work_ref:exact.work_ref,grant_ref:grant.grant_ref}));
const pages=[first];
while(pages.at(-1).page.has_more){pages.push(payload(call('vera_workspace_financial_source_view',{work_ref:exact.work_ref,grant_ref:grant.grant_ref,offset:pages.length*24000})));}
const textPage=pages[1];
const context=call('vera_workspace_financial_source_context',{work_ref:exact.work_ref,grant_ref:grant.grant_ref,revision:textPage.revision,offset:24000}).structuredContent;
const outside=call('vera_workspace_financial_source_view',{work_ref:exact.work_ref,grant_ref:grant.grant_ref,offset:2400000});
const invalid=call('vera_workspace_financial_source_view',{work_ref:exact.work_ref,grant_ref:grant.grant_ref,offset:1});
const result={pages,context,outside,invalid};
""",
    )
    assert "".join(row["page"]["text"] for row in result["pages"]) == "αβ🙂\r\n" * 14000
    assert result["context"]["page"] == result["pages"][1]["page"]
    assert result["context"]["page"]["complete_file"] is False
    assert result["outside"]["isError"] is True
    assert result["invalid"]["isError"] is True


@pytest.mark.parametrize(
    "custom_source",
    [b"\x89PNG\x00\xffFictional binary evidence"],
    indirect=True,
    ids=["binary-source"],
)
def test_native_financial_binary_source_keeps_exact_file_authority_without_fabricated_text(
    custom_source,
):
    env, *_ = custom_source
    result = rpc_program(
        env,
        source_script(custom_source)
        + """
const grant=payload(call('vera_workspace_financial_source_grant',grantArgs));
const view=payload(call('vera_workspace_financial_source_view',{work_ref:exact.work_ref,grant_ref:grant.grant_ref}));
const context=call('vera_workspace_financial_source_context',{work_ref:exact.work_ref,grant_ref:grant.grant_ref,revision:view.revision}).structuredContent;
const result={view,context};
""",
    )
    assert result["context"]["page"]["available"] is False
    assert "text" not in result["context"]["page"]
    assert (
        Path(result["context"]["authorized_source_path"]).read_bytes()
        == b"\x89PNG\x00\xffFictional binary evidence"
    )
    assert "no OCR or conversion" in result["context"]["page"]["limitation"]


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
@pytest.mark.parametrize("change", ["revision:'stale'", "grant_ref:'foreign'"])
def test_native_financial_source_context_refuses_foreign_or_stale_question(
    financial_intake, change
):
    env, *_ = financial_intake
    result = rpc_program(
        env,
        source_script(financial_intake)
        + f"""
const grant=payload(call('vera_workspace_financial_source_grant',grantArgs));
const view=payload(call('vera_workspace_financial_source_view',{{work_ref:exact.work_ref,grant_ref:grant.grant_ref}}));
const result=call('vera_workspace_financial_source_context',{{work_ref:exact.work_ref,grant_ref:grant.grant_ref,revision:view.revision,{change}}});
""",
    )
    assert result["isError"] is True


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
@pytest.mark.parametrize("action", ["grant", "draft_save"])
def test_native_financial_viewer_reads_sealed_identity_but_cannot_save_or_authorize(
    financial_intake, action
):
    env, output, *_ = financial_intake
    stored = rpc_program(
        env,
        source_script(financial_intake)
        + "const result={source_ref:execution.source_ref,item_id:item.artifact_id};",
    )
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": "VIEWER"},
        f"""
const chosen={{work_ref:'fictional-financial',...{json.dumps(stored)}}};
const page=payload(call('vera_workspace_financial_source_setup',chosen));
const result=call('vera_workspace_financial_source_{action}',{{...chosen,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision,fields:{{question:'Fictional viewer request.',selectors_text:''}},{"confirmed:true,human_reviewed:true,idempotency_key:'viewer-source'" if action=="grant" else ""}}});
""",
    )
    assert result["isError"] is True
    assert list(output.glob("financial-evidence-*")) == []
