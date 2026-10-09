"""Private CAS behaviour against an injected already-authorized mandate snapshot."""

from __future__ import annotations

import json
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest

from tests.plugins import test_vera_native_workspace as factory

__all__ = []


@pytest.fixture
def disposition(tmp_path, monkeypatch):
    factory.workspace_module()
    import native_bandi_decision_drafts as module

    output = tmp_path / "outputs"
    output.mkdir()
    public = output / "intelligence_register.json"
    public.write_text('{"runs":[]}\n')
    private = tmp_path / "private-actor"
    private.mkdir()
    reference = "mandate-" + "a" * 64
    current = {
        "identity": {"owner": ["tenant", "actor"], "binding": {"work_ref": "work"}},
        "state": {
            "grants": [
                {
                    "grant_ref": reference,
                    "status": "recorded",
                    "public_record_sha256": "d" * 64,
                }
            ]
        },
        "revision": "r" * 64,
        "source_ref": "s" * 64,
        "can_write": True,
        "home": private,
        "public": {"output": output},
    }
    monkeypatch.setattr(
        module, "contribution_snapshot", lambda *args: deepcopy(current)
    )

    def save(path, value):
        path.write_text(json.dumps(value))

    api = SimpleNamespace(
        read_json=lambda path: json.loads(path.read_text()),
        atomic_json=save,
        write_lock=lambda path: nullcontext(),
        load_binding=lambda binding: {},
    )
    binding = {
        "workflow_id": "bandi-agevolazioni",
        "component": "bandi-agevolazioni",
        "work_ref": "work",
    }
    args = {
        "work_ref": "work",
        "grant_ref": reference,
        "revision": current["revision"],
        "source_ref": current["source_ref"],
    }

    def call(action, **extra):
        return module.dispatch(
            "vera_workspace_bandi_author_decision_draft_" + action,
            {**args, **extra},
            binding,
            {},
            tmp_path,
            api,
        )

    return call, current, api, public


def test_disposition_save_restores_literal_fields_without_consent_or_public_mutation(
    disposition,
):
    call, _, _, public = disposition
    before = public.read_bytes()
    page = call("read")
    literal = {
        "decision": "",
        "reviewer_id": "  reviewer to complete  ",
        "reviewer_role": "",
        "notes": "Incomplete literal note; no decision.",
    }
    saved = call("save", expected_draft_revision=page["draft_revision"], fields=literal)
    reopened = call("read")
    assert reopened["fields"] == literal
    assert reopened["draft_revision"] == saved["draft_revision"]
    assert reopened["confirmation_restored"] is False
    assert reopened["draft_stale"] is False
    assert public.read_bytes() == before


def test_disposition_stale_cas_refuses_another_panel_without_overwriting_fields(
    disposition,
):
    call, _, _, _ = disposition
    page = call("read")
    fields = {**page["fields"], "notes": "First panel"}
    call("save", expected_draft_revision=page["draft_revision"], fields=fields)
    with pytest.raises(ValueError, match="Another panel"):
        call(
            "save",
            expected_draft_revision=page["draft_revision"],
            fields={**fields, "notes": "Second panel"},
        )
    assert call("read")["fields"] == fields


def test_disposition_scope_change_labels_retained_fields_stale_and_clear_requires_confirmation(
    disposition,
):
    call, current, _, public = disposition
    before = public.read_bytes()
    page = call("read")
    call(
        "save",
        expected_draft_revision=page["draft_revision"],
        fields={**page["fields"], "notes": "Older case fields"},
    )
    current["identity"]["case_version"] = "next"
    stale = call("read")
    with pytest.raises(ValueError, match="Explicitly confirm"):
        call("clear", expected_draft_revision=stale["draft_revision"])
    assert stale["draft_stale"] is True
    assert stale["fields"]["notes"] == "Older case fields"
    call("clear", expected_draft_revision=stale["draft_revision"], confirmed=True)
    reopened = call("read")
    assert reopened["fields"] == {
        "decision": "",
        "reviewer_id": "",
        "reviewer_role": "",
        "notes": "",
    }
    assert reopened["draft_stale"] is False
    assert reopened["confirmation_restored"] is False
    assert public.read_bytes() == before


@pytest.mark.parametrize(
    "condition", ["viewer", "decided", "other_mandate", "source_changed"]
)
def test_disposition_writes_refuse_wrong_role_closed_grant_or_scope(
    disposition, condition
):
    call, current, _, public = disposition
    before = public.read_bytes()
    page = call("read")
    if condition == "viewer":
        current["can_write"] = False
    elif condition == "decided":
        current["state"]["grants"][0]["status"] = "decided"
    elif condition == "other_mandate":
        current["state"]["grants"] = []
    else:
        current["source_ref"] = "changed"
    with pytest.raises((ValueError, PermissionError)):
        call(
            "save",
            expected_draft_revision=page["draft_revision"],
            fields=page["fields"],
        )
    assert public.read_bytes() == before


def test_disposition_rechecks_scope_under_lock_before_writing(disposition):
    call, current, api, _ = disposition
    page = call("read")

    @contextmanager
    def changed_lock(path):
        current["revision"] = "new-revision"
        yield

    api.write_lock = changed_lock
    with pytest.raises(ValueError, match="changed before saving"):
        call(
            "save",
            expected_draft_revision=page["draft_revision"],
            fields=page["fields"],
        )
    assert list(current["home"].iterdir()) == []
