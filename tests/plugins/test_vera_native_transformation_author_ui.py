"""Fictional authoring events only; no installed host or real model execution."""

from __future__ import annotations

from tests.plugins.test_vera_native_transformation_ui import events

__all__ = []

CONFIRM = "Autorizzo la chat a leggere il caso corrente completo e gli originali sintetici scelti, soltanto per una proposta da riesaminare"
FIXTURE = """
const consent='Autorizzo la chat a leggere il caso corrente completo e gli originali sintetici scelti, soltanto per una proposta da riesaminare';
const authorFixture=(extra={})=>fixture(source,{fields:{question:'',operation:'',source_refs:[]},pending_requests:[],pending_public_operations:[],mandates:[],stages:[],stage_revision:'fictional-stage',public_draft_revision:'fictional-public-draft',public_draft_empty:true,can_prepare_request:true,can_adopt:false,can_cancel:true,request_prepared:false,reply(name,args,page){if(name.endsWith('_author_request')){page.question=args.fields.question;page.selected_sources=[];page.status='open';page.grant_ref='fictional-grant';page.pending_operations=false;return {grant_ref:'fictional-grant',model_executed:false};}if(name.endsWith('_author_message_prepare')){page.request_prepared=true;page.can_prepare_request=false;return {saved:true,model_executed:false,message_received:false};}if(name.endsWith('_author_read'))return page;},...extra});
"""


def test_author_ui_partial_question_recovers_without_grant_or_consent():
    result = events(
        FIXTURE
        + "const ui=authorFixture();await ui.panel.openAuthor('fictional-transform');const question=ui.field('Domanda sulla dimostrazione sintetica');question.value='  Literal incomplete question  ';question.dispatch('input');await ui.panel.flush();await ui.panel.refresh();process.stdout.write(JSON.stringify({fields:ui.page.fields,confirmed:ui.field(consent).checked,calls:ui.calls}));"
    )
    assert result["fields"]["question"] == "  Literal incomplete question  "
    assert result["confirmed"] is False
    assert not any(call["name"].endswith("_request") for call in result["calls"])


def test_author_ui_explicit_question_authorization_is_not_model_execution():
    result = events(
        FIXTURE
        + "const ui=authorFixture();await ui.panel.openAuthor('fictional-transform');const question=ui.field('Domanda sulla dimostrazione sintetica');question.value='FICTIONAL requested proposal';question.dispatch('input');const operation=ui.field('Proposta richiesta alla chat');operation.value='put';operation.dispatch('change');let refused=false;try{await ui.button('Autorizza questa domanda e le fonti scelte').action();}catch(error){refused=true;}ui.field(consent).checked=true;await ui.button('Autorizza questa domanda e le fonti scelte').action();process.stdout.write(JSON.stringify({refused,calls:ui.calls,text:ui.text()}));"
    )
    assert result["refused"] is True
    request = next(
        call for call in result["calls"] if call["name"].endswith("_author_request")
    )
    assert request["args"]["confirmed"] is True
    assert request["args"]["fields"]["source_refs"] == []
    assert not any(
        call["name"].endswith("_message_prepare") for call in result["calls"]
    )
    assert "Nessuna proposta è stata conservata" in result["text"]


def test_author_ui_changed_selected_source_withdraws_model_confirmation():
    result = events(
        FIXTURE
        + "const ui=authorFixture();ui.page.data.sources=[{source_ref:'fictional-source',name:'Synthetic.txt',sha256:'a'.repeat(64)}];await ui.panel.openAuthor('fictional-transform');ui.field(consent).checked=true;const selected=ui.field('Synthetic.txt · fictional-source');selected.checked=true;selected.dispatch('change');await ui.panel.flush();process.stdout.write(JSON.stringify({fields:ui.page.fields,confirmed:ui.field(consent).checked,calls:ui.calls}));"
    )
    assert result["fields"]["source_refs"] == ["fictional-source"]
    assert result["confirmed"] is False
    assert not any(call["name"].endswith("_request") for call in result["calls"])


def test_author_ui_no_message_capability_shows_copyable_request_before_final_footer():
    result = events(
        FIXTURE
        + "const ui=authorFixture({question:'Fictional retained question',selected_sources:[],pending_operations:false});await ui.panel.openMandate('fictional-transform','fictional-grant');await ui.button('Chiedi alla chat di preparare la proposta').action();const request=ui.field('Richiesta da copiare nella chat corrente');process.stdout.write(JSON.stringify({request:request.value,readonly:request.readOnly,calls:ui.calls,last:ui.tree().children.at(-1).text}));"
    )
    assert result["readonly"] is True
    assert "vera_workspace_transformation_author_context" in result["request"]
    assert "vera_workspace_transformation_author_stage" in result["request"]
    assert "non invocare submit/review/export" in result["request"]
    assert "review_ticket" not in result["request"]
    assert "ricevute del contesto effettivo del provider" in result["last"]
    assert any(call["name"].endswith("_message_prepare") for call in result["calls"])


def test_author_ui_message_acknowledgment_is_separate_from_private_preparation():
    result = events(
        FIXTURE
        + "const sent=[];const ui=authorFixture({question:'Fictional question',selected_sources:[],pending_operations:false,sendToChat:async text=>{sent.push(text);return true;}});await ui.panel.openMandate('fictional-transform','fictional-grant');await ui.button('Chiedi alla chat di preparare la proposta').action();process.stdout.write(JSON.stringify({sent,calls:ui.calls,disabled:ui.button('Chiedi alla chat di preparare la proposta').disabled}));"
    )
    assert len(result["sent"]) == 1
    assert result["disabled"] is True
    assert not any(call["name"].endswith("_execute") for call in result["calls"])


def test_author_ui_transport_failure_does_not_retry_automatically():
    result = events(
        FIXTURE
        + "let attempts=0;const ui=authorFixture({question:'Fictional question',selected_sources:[],pending_operations:false,sendToChat:async()=>{attempts++;throw new Error('FICTIONAL lost receipt');}});await ui.panel.openMandate('fictional-transform','fictional-grant');let failed=false;try{await ui.button('Chiedi alla chat di preparare la proposta').action();}catch(error){failed=true;}process.stdout.write(JSON.stringify({attempts,failed,prepared:ui.page.request_prepared,disabled:ui.button('Chiedi alla chat di preparare la proposta').disabled,calls:ui.calls}));"
    )
    assert result["attempts"] == 1
    assert result["failed"] is True
    assert result["prepared"] is True
    assert result["disabled"] is True


def test_author_ui_viewer_and_pending_public_write_disable_new_model_request():
    result = events(
        FIXTURE
        + "const viewer=authorFixture({can_write:false});await viewer.panel.openAuthor('fictional-transform');const pending=authorFixture({pending_public_operations:['uncertain']});await pending.panel.openAuthor('fictional-transform');process.stdout.write(JSON.stringify({viewerDisabled:viewer.button('Autorizza questa domanda e le fonti scelte').disabled,pendingDisabled:pending.button('Autorizza questa domanda e le fonti scelte').disabled,text:pending.text()}));"
    )
    assert result["viewerDisabled"] is True
    assert result["pendingDisabled"] is True
    assert "Nessuna nuova preparazione del modello" in result["text"]
