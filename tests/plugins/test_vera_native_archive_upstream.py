"""Native selection of sealed fictional artifacts and its exact scope boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_closure import (  # noqa: F401
    closure_workspace,
    declare_all,
    setup,
)
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import (  # noqa: F401
    registry_workspace,
)

__all__ = []


@pytest.fixture
def sealed_upstream(closure_workspace):
    """Seal actual fixture files through the maintained native closure route."""
    env, folder, output, selected = closure_workspace
    rpc_program(
        env,
        setup(selected)
        + declare_all()
        + "const result=payload(call('vera_workspace_archive_finalize',seal));",
    )
    return env, folder, output, selected


def upstream_setup(selected: dict) -> str:
    """Use a displayed exact artifact and explicitly authored role."""
    return f"""
const selected={json.dumps({k: selected[k] for k in ('client_id', 'engagement_id')})};
const inputs=payload(call('vera_workspace_archive_inputs',selected));
const artifact=inputs.upstream_rows.find(r=>r.path==='working-000.txt');
const reference={{run_id:artifact.run_id,artifact_id:artifact.artifact_id,role:'explicitly_selected_source'}};
const args={{...scope(inputs),workflow_id:'client-file-preparation',input_ids:[],upstream_artifacts:[reference],label:'Fictional upstream selection',purpose:'Inspect the selected sealed file',idempotency_key:'fictional-upstream-selection'}};
"""


@pytest.mark.parametrize("closure_workspace", [35], indirect=True)
def test_upstream_catalogue_paginates_exact_sealed_artifacts_with_stable_scope(
    sealed_upstream,
):
    env, _, output, selected = sealed_upstream

    result = rpc_program(
        env,
        upstream_setup(selected)
        + """
const next=payload(call('vera_workspace_archive_inputs',{...selected,artifact_offset:30}));
const result={inputs,next};
""",
    )

    first, second = result["inputs"], result["next"]
    expected = sorted(
        p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
    )
    assert (
        sorted(r["path"] for r in first["upstream_rows"] + second["upstream_rows"])
        == expected
    )
    assert len(first["upstream_rows"]) == 30
    assert first["upstream_has_more"] is True
    assert second["upstream_has_more"] is False
    assert first["scope_revision"] == second["scope_revision"]
    assert str(output) not in json.dumps(result)


@pytest.mark.parametrize(
    "change",
    [
        "run_id:'run_ffffffffffffffffffffffff'",
        "artifact_id:'nonexistent-artifact'",
        "role:' '",
        "path:'/unregistered/path'",
    ],
)
def test_upstream_prepare_rejects_forged_reference_without_creating_run(
    sealed_upstream,
    change,
):
    env, folder, _, selected = sealed_upstream
    ledger = _load_customer_ledger()
    before = ledger.list_runs(folder, selected["engagement_id"])

    result = rpc_program(
        env,
        upstream_setup(selected)
        + f"const result=call('vera_workspace_archive_prepare',{{...args,upstream_artifacts:[{{...reference,{change}}}]}});",
    )

    assert result["isError"] is True
    assert ledger.list_runs(folder, selected["engagement_id"]) == before


def test_upstream_tamper_invalidates_ticket_and_removes_selectable_source(
    sealed_upstream,
):
    env, folder, output, selected = sealed_upstream
    ledger = _load_customer_ledger()
    run_ids = [
        r["run"]["run_id"] for r in ledger.list_runs(folder, selected["engagement_id"])
    ]

    result = rpc_program(
        env,
        upstream_setup(selected)
        + f"require('node:fs').writeFileSync({json.dumps(str(output / 'working-000.txt'))},'Changed fictional sealed bytes');"
        + """
const refused=call('vera_workspace_archive_prepare',args);
const fresh=payload(call('vera_workspace_archive_inputs',selected));
const result={refused,fresh};
""",
    )

    assert result["refused"]["isError"] is True
    assert result["fresh"]["upstream_rows"] == []
    assert result["fresh"]["upstream_unavailable"][0]["run_id"] == selected["run_id"]
    assert [
        r["run"]["run_id"] for r in ledger.list_runs(folder, selected["engagement_id"])
    ] == run_ids
