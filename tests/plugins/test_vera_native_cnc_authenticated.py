"""Real local preparation and chosen receipt import on fictional Archive cases."""

from __future__ import annotations

import json
import os
import sys
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path

import pytest

from tests.plugins.test_vera_native_cnc import (  # noqa: F401
    case,
    cnc,
    cnc_run,
    initial,
    ledger,
    rpc_program,
    workspace_module,
)

__all__ = []


@pytest.fixture
def authenticated_run(cnc_run):
    case, binding, _ = cnc_run
    record = cnc.apply_request(case.context, initial(case))
    output = Path(case.run["output_dir"])
    (output / "cnc-revision-000001.md").write_text(cnc.render_record(record))
    return case, binding, record


def prepared_program(fixture):
    return f"""
const work={{work_ref:{json.dumps(fixture[1]['work_ref'])}}};
const identity={{...work,source_ref:{json.dumps(fixture[2]['content_sha256'])},item_id:'proposal'}};
const page=payload(call('vera_workspace_cnc_authenticated_setup',identity));
const prepareArgs={{...identity,revision:page.revision,review_ticket:page.review_ticket,confirmed:true,idempotency_key:'fictional-auth-prepare'}};
const prepared=payload(call('vera_workspace_cnc_authenticated_prepare',prepareArgs));
const exact={{...identity,target_ref:prepared.files[0].sha256}};
const read=payload(call('vera_workspace_cnc_authenticated_read',exact));
const authority=p=>({{...exact,revision:p.revision,review_ticket:p.review_ticket,expected_draft_revision:p.draft_revision}});
"""


def test_cnc_authenticated_prepares_exact_public_file_and_recovers_private_draft_without_network(
    authenticated_run,
):
    result = rpc_program(
        os.environ.copy(),
        prepared_program(authenticated_run)
        + """
const fields={receipt:{actor:'PRIVATE UNSENT RECEIPT NAME'},reason:'Literal incomplete draft'};
const saved=payload(call('vera_workspace_cnc_authenticated_draft_save',{...authority(read),fields}));
const stale=call('vera_workspace_cnc_authenticated_draft_save',{...authority(read),fields:{receipt:null,reason:'stale'}});
const recovered=payload(call('vera_workspace_cnc_authenticated_read',exact));
const node=payload(call('vera_workspace_cnc_read',identity));
const context=call('vera_workspace_cnc_context',{...identity,revision:node.revision}).structuredContent;
const result={page,prepared,read,saved,stale,recovered,context,retry:payload(call('vera_workspace_cnc_authenticated_prepare',prepareArgs))};
""",
    )
    assert result["page"]["total"] == 0
    assert result["prepared"] == result["retry"]
    assert result["prepared"]["receipt_verified"] is False
    assert (
        result["read"]["prepared"]["target"]["node"]
        == authenticated_run[2]["payload"]["nodes"]["proposal"]
    )
    path = Path(result["prepared"]["files"][0]["path"])
    assert json.loads(path.read_text()) == result["prepared"]["target"]
    assert result["recovered"]["draft"] == {
        "receipt": {"actor": "PRIVATE UNSENT RECEIPT NAME"},
        "reason": "Literal incomplete draft",
    }
    assert result["recovered"]["receipt_verified"] is False
    assert result["stale"]["isError"] is True
    assert "PRIVATE UNSENT RECEIPT NAME" not in json.dumps(result["context"])
    assert (
        len(
            ledger.load_workflow_history(
                authenticated_run[0].root,
                authenticated_run[0].engagement_id,
                "composizione-negoziata",
            )
        )
        == 1
    )


@pytest.mark.parametrize(
    "change", ["no_confirmation", "forged_ticket", "wrong_node", "viewer"]
)
def test_cnc_authenticated_preparation_requires_exact_renewed_editable_selection(
    authenticated_run,
    change,
):
    identity = {
        "work_ref": authenticated_run[1]["work_ref"],
        "source_ref": authenticated_run[2]["content_sha256"],
        "item_id": "proposal",
    }
    modifications = {
        "no_confirmation": "confirmed:false",
        "forged_ticket": "review_ticket:'forged'",
        "wrong_node": "item_id:'funding'",
        "viewer": "",
    }
    env = {
        **os.environ,
        **({"VERA_WORKSPACE_ROLES": "VIEWER"} if change == "viewer" else {}),
    }
    result = rpc_program(
        env,
        f"""
const identity={json.dumps(identity)};
const page=payload(call('vera_workspace_cnc_authenticated_setup',identity));
const result=call('vera_workspace_cnc_authenticated_prepare',{{...identity,revision:page.revision,review_ticket:page.review_ticket,confirmed:true,idempotency_key:'fictional-refused',{modifications[change]}}});
""",
    )
    assert result["isError"] is True
    assert (
        list(Path(authenticated_run[0].run["output_dir"]).glob("cnc-review-*.json"))
        == []
    )


@pytest.fixture
def authenticated_service(authenticated_run, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from modules.auth import dependencies
    from modules.auth.google_identity import GoogleUserInfo
    from modules.auth.session import create_session_cookie
    from modules.cnc_review import api
    from tests.modules.auth.test_dependencies import _config

    service = workspace_module()
    monkeypatch.syspath_prepend(str(Path(cnc.__file__).parent))
    import cnc_review_client
    import native_cnc_authenticated as adapter
    import native_cnc_authenticated_bridge as bridge

    monkeypatch.setitem(sys.modules, "cnc_case", cnc)
    config = _config(session_secret="fictional-native-cnc-review-test-only")
    monkeypatch.setattr(dependencies, "get_auth_config", lambda: config)
    store = api.ReviewStore(tmp_path / "reviews.sqlite3")
    app = FastAPI()
    app.include_router(api.api_router)
    app.dependency_overrides[api.get_store] = lambda: store
    client = TestClient(app)
    cookie, _ = create_session_cookie(
        GoogleUserInfo(email="native-test-reviewer@example.test"), config
    )
    client.cookies.set(config.session_cookie_name, cookie)
    outgoing = []

    class Transport:
        def open(self, request, timeout):
            assert request.full_url == cnc_review_client.ENDPOINT
            assert timeout == 15
            value = json.loads(request.data)
            assert set(value) == {"receipt_id", "receipt_sha256"}
            outgoing.append(value)
            response = client.post("/api/vera/cnc-reviews/verify", json=value)
            if response.status_code != 200:
                raise ValueError("Retained test service refused receipt")
            return BytesIO(response.content)

    monkeypatch.setattr(
        cnc_review_client.urllib.request, "build_opener", lambda *args: Transport()
    )

    def execute(root, args):
        captured = StringIO()
        with monkeypatch.context() as isolated:
            isolated.setattr(sys, "argv", [str(bridge.__file__), str(root)])
            isolated.setattr(sys, "stdin", StringIO(json.dumps(args)))
            with redirect_stdout(captured):
                bridge.main()
        return json.loads(captured.getvalue())

    monkeypatch.setattr(adapter, "engine", execute)
    case, binding, record = authenticated_run
    identity = {
        "work_ref": binding["work_ref"],
        "source_ref": record["content_sha256"],
        "item_id": "proposal",
    }

    def call(action, args):
        return service.dispatch("vera_workspace_cnc_authenticated_" + action, args)

    page = call("setup", identity)
    prepared = call(
        "prepare",
        {
            **identity,
            "revision": page["revision"],
            "confirmed": True,
            "idempotency_key": "fictional-direct-prepare",
        },
    )
    exact = {**identity, "target_ref": prepared["files"][0]["sha256"]}
    return case, call, client, outgoing, prepared, exact, cnc_review_client


def chosen_receipt(fixture, decision="accepted"):
    _, call, client, _, prepared, exact, _ = fixture
    response = client.post(
        "/api/vera/cnc-reviews",
        json={**prepared["target"]["request"], "decision": decision},
        headers={"Origin": "http://testserver", "X-CNC-Review": "1"},
    )
    assert response.status_code == 200
    fields = {
        "receipt": response.json(),
        "reason": "Fictional test account decision; no real professional acceptance.",
    }
    page = call("read", exact)
    call(
        "draft_save",
        {
            **exact,
            "revision": page["revision"],
            "expected_draft_revision": page["draft_revision"],
            "fields": fields,
        },
    )
    fresh = call("read", exact)
    args = {
        **exact,
        "revision": fresh["revision"],
        "expected_draft_revision": fresh["draft_revision"],
        "fields": fields,
        "confirmed": True,
        "idempotency_key": "fictional-auth-import",
    }
    return fields, args


@pytest.mark.parametrize("decision", ["accepted", "changes_requested", "rejected"])
def test_cnc_authenticated_import_uses_real_retained_signed_account_and_public_writer(
    authenticated_service, decision
):
    case, call, _, outgoing, _, _, _ = authenticated_service
    fields, args = chosen_receipt(authenticated_service, decision)
    assert outgoing == []
    imported = call("import", args)
    repeated = call("import", args)
    history = ledger.load_workflow_history(
        case.root, case.engagement_id, "composizione-negoziata"
    )
    review = history[-1]["payload"]["reviews"][-1]
    assert imported == repeated
    assert imported["receipt_verified"] is True
    assert imported["professional_approval"] is False
    assert imported["run_completed"] is False
    assert imported["case_revision"] == 2
    assert review["authority"] == "mparanza_authenticated_account"
    assert review["decision"] == decision
    assert review["reviewer_ref"] == "native-test-reviewer@example.test"
    assert review["server_receipt"] == fields["receipt"]
    assert len(outgoing) == 2
    assert all(row["receipt_id"] == fields["receipt"]["request_id"] for row in outgoing)
    assert (
        json.loads(Path(imported["files"][1]["path"]).read_text()) == fields["receipt"]
    )
    assert Path(imported["files"][2]["path"]).read_text() == cnc.render_record(
        history[-1]
    )


def test_cnc_authenticated_unavailable_verifier_keeps_decision_pending_and_drafting_available(
    authenticated_service, monkeypatch
):
    import urllib.error

    case, call, _, outgoing, _, exact, client = authenticated_service
    _, args = chosen_receipt(authenticated_service)
    before = {
        p.name: p.read_bytes()
        for p in Path(case.run["output_dir"]).iterdir()
        if p.is_file()
    }

    class Unavailable:
        def open(self, *args, **kwargs):
            raise urllib.error.URLError("fictional unavailable verification")

    monkeypatch.setattr(
        client.urllib.request, "build_opener", lambda *args: Unavailable()
    )
    result = call("import", args)
    after = call("read", exact)
    assert result["saved"] is False
    assert result["verification_pending"] is True
    assert after["can_write"] is True
    assert after["recovery_required"] is False
    assert {
        p.name: p.read_bytes()
        for p in Path(case.run["output_dir"]).iterdir()
        if p.is_file()
    } == before
    assert outgoing == []


@pytest.mark.parametrize("change", ["uuid", "actor", "not_confirmed", "unsaved_reason"])
def test_cnc_authenticated_import_refuses_scope_forgery_and_unsaved_choice(
    authenticated_service, change
):
    case, call, _, outgoing, _, exact, _ = authenticated_service
    fields, args = chosen_receipt(authenticated_service)
    if change in {"uuid", "actor"}:
        from uuid import uuid4

        fields = {
            **fields,
            "receipt": {
                **fields["receipt"],
                **(
                    {"request_id": str(uuid4())}
                    if change == "uuid"
                    else {"actor": "forged@example.test"}
                ),
            },
        }
        page = call("read", exact)
        call(
            "draft_save",
            {
                **exact,
                "revision": page["revision"],
                "expected_draft_revision": page["draft_revision"],
                "fields": fields,
            },
        )
        page = call("read", exact)
        args.update(
            revision=page["revision"],
            expected_draft_revision=page["draft_revision"],
            fields=fields,
        )
    if change == "not_confirmed":
        args["confirmed"] = False
    if change == "unsaved_reason":
        args["fields"] = {**fields, "reason": "Not the retained reason"}
    if change == "actor":
        assert call("import", args)["verification_pending"] is True
        assert len(outgoing) == 1
    else:
        with pytest.raises((ValueError, PermissionError)):
            call("import", args)
        assert outgoing == []
    assert (
        len(
            ledger.load_workflow_history(
                case.root, case.engagement_id, "composizione-negoziata"
            )
        )
        == 1
    )


@pytest.mark.parametrize("operation", ["prepare", "import"])
def test_cnc_authenticated_interruption_after_actual_public_write_retains_evidence_and_refuses_retry(
    authenticated_service,
    monkeypatch,
    operation,
):
    import native_cnc_authenticated as adapter

    case, call, _, _, _, exact, _ = authenticated_service
    if operation == "import":
        _, args = chosen_receipt(authenticated_service)
    else:
        identity = {k: v for k, v in exact.items() if k != "target_ref"}
        page = call("setup", identity)
        args = {
            **identity,
            "revision": page["revision"],
            "confirmed": True,
            "idempotency_key": "fictional-interrupted-preparation",
        }
    original = adapter.engine

    def interrupted(root, posted):
        original(root, posted)
        raise ValueError("Fictional interruption after actual public side effect")

    monkeypatch.setattr(adapter, "engine", interrupted)
    with pytest.raises(ValueError, match="after actual public"):
        call(operation, args)
    history = ledger.load_workflow_history(
        case.root, case.engagement_id, "composizione-negoziata"
    )
    latest_identity = {
        "work_ref": exact["work_ref"],
        "source_ref": history[-1]["content_sha256"],
        "item_id": "proposal",
    }
    page = call("setup", latest_identity)
    assert page["recovery_required"] is True
    assert page["can_write"] is False
    assert len(history) == (2 if operation == "import" else 1)
    assert len(list(Path(case.run["output_dir"]).glob("cnc-review-*.json"))) == (
        1 if operation == "import" else 2
    )
    with pytest.raises(ValueError, match="uncertain authenticated CNC retry"):
        call(operation, args)


def test_cnc_authenticated_outputs_seal_and_closed_viewer_does_not_reverify(
    authenticated_service, monkeypatch
):
    from tests.model_data_helpers import write_no_model_report

    case, call, _, outgoing, _, exact, _ = authenticated_service
    _, args = chosen_receipt(authenticated_service)
    imported = call("import", args)
    output = Path(case.run["output_dir"])
    write_no_model_report(output, "composizione-negoziata", case.run["run"]["run_id"])
    declarations = [
        {
            "artifact_id": p.name.replace(".", "-"),
            "path": p.name,
            "purpose": "Retain fictional authenticated-review test outputs.",
            "audience": "review",
            "media_type": (
                "application/json" if p.suffix == ".json" else "text/markdown"
            ),
        }
        for p in output.iterdir()
        if p.is_file()
    ]
    ledger.finalize_run(
        case.root, case.engagement_id, case.run["run"]["run_id"], declarations
    )
    ledger.complete_run(case.root, case.engagement_id, case.run["run"]["run_id"])
    history = ledger.load_workflow_history(
        case.root, case.engagement_id, "composizione-negoziata"
    )
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "VIEWER")
    read = call("read", {**exact, "source_ref": history[-1]["content_sha256"]})
    assert read["can_write"] is False
    assert read["receipt_verified"] is False
    assert len(outgoing) == 2
    assert len(imported["files"]) == 4
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    assert ledger.validate_run_artifacts(
        case.root, case.engagement_id, case.run["run"]["run_id"]
    )["artifacts"]
