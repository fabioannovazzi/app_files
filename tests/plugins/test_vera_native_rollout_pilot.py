"""Private packaged MCP mechanisms; no installed native-host acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import ROOT


def build_private_pilot(
    destination: Path,
    *,
    owned: bool,
    passive_review_case: bool = False,
    reviewed_source_group_case: bool = False,
    retain_private_pilot: Path | None = None,
) -> Path:
    """Use the public harness with separate fictional persistence for each test."""
    command = [
        sys.executable,
        str(ROOT / "scripts/build_vera_native_rollout_pilot.py"),
        str(destination),
        "--version",
        "0.0.11",
    ]
    if owned:
        command.append("--owned-archive")
    if passive_review_case:
        command.append("--passive-review-case")
    if reviewed_source_group_case:
        command.append("--reviewed-source-group-case")
    if retain_private_pilot is not None:
        command.extend(["--retain-private-pilot", str(retain_private_pilot)])
    subprocess.run(command, capture_output=True, text=True, check=True, timeout=90)
    plugin = destination / "plugins/vera-workspace-pilot"
    assert (plugin / "scripts/native_inps_rpc.cjs").read_bytes() == (
        ROOT / "plugins/vera/scripts/native_inps_rpc.cjs"
    ).read_bytes()
    assert (plugin / "scripts/native_sari_review_rpc.cjs").read_bytes() == (
        ROOT / "plugins/vera/scripts/native_sari_review_rpc.cjs"
    ).read_bytes()
    return plugin


def test_private_pilot_owned_import_conserves_selected_bytes_without_starting_run(
    tmp_path,
):
    """The generated pilot must execute its declared new adapter dependencies."""
    plugin = build_private_pilot(tmp_path / "import-pilot", owned=True)
    environment = profile_environment(plugin, "veraOwnedWorkspace")
    data = "Fictional selected source for the private pilot."

    result = rpc_program(
        environment,
        """
const clients=payload(call('vera_workspace_open',{})).clients;
const client=clients.find(row=>row.client_id);
const engagement=payload(call('vera_workspace_open',{client_id:client.client_id})).engagements[0];
const selected={client_id:client.client_id,engagement_id:engagement.engagement_id};
const before=payload(call('vera_workspace_open',selected));
const setup=payload(call('vera_workspace_archive_import_setup',selected));
const bytes=Buffer.from('Fictional selected source for the private pilot.');
const file={name:'fictional-pilot-source.txt',byte_count:bytes.length,sha256:require('node:crypto').createHash('sha256').update(bytes).digest('hex'),role:'source'};
const authority={...selected,scope_revision:setup.scope_revision,archive_ticket:setup.archive_ticket,confirmed:true};
const begun=payload(call('vera_workspace_archive_import_begin',{...authority,file,idempotency_key:'fictional-pilot-import'}));
payload(call('vera_workspace_archive_import_chunk',{...authority,upload_ref:begun.upload_ref,offset:0,data:bytes.toString('base64')}));
const finished=payload(call('vera_workspace_archive_import_finish',{...authority,upload_ref:begun.upload_ref}));
const retry=payload(call('vera_workspace_archive_import_finish',{...authority,upload_ref:begun.upload_ref}));
const after=payload(call('vera_workspace_open',selected));
const runs=rows=>rows.map(({run_id,status,workflow})=>({run_id,status,workflow}));
const result={finished,retry,before:runs(before.works),after:runs(after.works)};
""",
        server=plugin / "mcp/workspace.cjs",
    )

    assert result["finished"]["sha256"] == hashlib.sha256(data.encode()).hexdigest()
    assert result["finished"]["role"] == "source"
    assert result["finished"]["run_started"] is False
    assert result["retry"] == result["finished"]
    assert result["after"] == result["before"]
    conserved = next(
        (tmp_path / "import-pilot/fictional-archive").glob(
            "*/Vera/engagements/*/inputs/*/fictional-pilot-source.txt"
        )
    )
    assert conserved.read_bytes() == data.encode()


def test_private_rollout_upgrade_retains_prior_scopes_and_prepares_fictional_group(
    tmp_path,
):
    prior = build_private_pilot(
        tmp_path / "prior", owned=True, passive_review_case=True
    )
    prior_mcp = json.loads((prior / ".mcp.json").read_bytes())
    prior_env = prior_mcp["mcpServers"]["veraNativeWorkspace"]["env"]
    prior_bindings = json.loads(Path(prior_env["VERA_WORKSPACE_BINDINGS"]).read_bytes())
    retained_bytes = {
        path: path.read_bytes()
        for path in (tmp_path / "prior").rglob("*")
        if path.is_file()
    }
    destination = tmp_path / "updated"

    plugin = build_private_pilot(
        destination,
        owned=False,
        reviewed_source_group_case=True,
        retain_private_pilot=prior,
    )
    env = profile_environment(plugin, "veraNativeWorkspace")
    current = json.loads(Path(env["VERA_WORKSPACE_BINDINGS"]).read_bytes())
    mcp = json.loads((plugin / ".mcp.json").read_bytes())
    case = json.loads(
        (destination / "source-group-native-acceptance-case.json").read_bytes()
    )
    identities = {row["name"]: row["id"] for row in case["inputs"]}
    fields = {
        "canonical_id": identities["reviewed.json"],
        "originals": {"invoice.txt": identities["invoice.txt"]},
        "operator_ref": "Fictional private pilot technical reviewer",
        "decision_basis": "Explicit synthetic mapping; fictional extraction review is preserved, never certified.",
    }
    result = rpc_program(
        env,
        "const fields="
        + json.dumps(fields)
        + ";\n"
        + """
const directory=payload(call('vera_workspace_open',{}));
const setup=payload(call('vera_workspace_source_group_setup',{work_ref:'source-group-fictional',canonical_id:fields.canonical_id}));
const prepared=payload(call('vera_workspace_source_group_prepare',{work_ref:setup.work_ref,revision:setup.revision,source_ref:fields.canonical_id,review_ticket:setup.review_ticket,expected_draft_revision:'',fields,human_reviewed:true,idempotency_key:'private-pilot-source-group'}));
const outputs=payload(call('vera_workspace_source_group_outputs',{work_ref:setup.work_ref,revision:prepared.revision,source_ref:fields.canonical_id,group_ref:prepared.group_ref}));
const result={directory,prepared,outputs};
""",
        server=plugin / "mcp/workspace.cjs",
    )

    assert current["bindings"][:-1] == prior_bindings["bindings"]
    assert current["actor_id"] == prior_bindings["actor_id"]
    assert current["tenant_id"] == prior_bindings["tenant_id"]
    assert (
        mcp["mcpServers"]["veraOwnedWorkspace"]["env"]
        == prior_mcp["mcpServers"]["veraOwnedWorkspace"]["env"]
    )
    assert {path: path.read_bytes() for path in retained_bytes} == retained_bytes
    assert len(result["directory"]["works"]) == 7
    assert result["prepared"]["status"] == "prepared"
    assert result["prepared"]["professional_approval"] is False
    assert len(result["outputs"]["outputs"]) == 3
    assert "Fictional sources and extraction review" in case["scope"]
    assert "Absent" in case["grouping_attribution"]
    assert not list(Path(case["binding"]["client_root"]).rglob("audit.sqlite3"))


def test_private_rollout_archive_disclosure_validates_through_packaged_producer(
    tmp_path,
):
    from tests.model_data_helpers import write_no_model_report

    plugin = build_private_pilot(tmp_path / "pilot", owned=False)
    output = tmp_path / "fictional-disclosure"
    output.mkdir()
    run_id = "run_" + "b" * 24
    write_no_model_report(
        output,
        "client-file-preparation",
        run_id,
        report_script=plugin
        / "modules/studio-archive/scripts/build_model_data_report.py",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(plugin / "scripts/native_archive_closure_bridge.py"),
            str(plugin / "modules/studio-archive"),
        ],
        input=json.dumps(
            {
                "operation": "report",
                "output": str(output),
                "run_id": run_id,
                "workflow_id": "client-file-preparation",
            }
        ),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert json.loads(completed.stdout)["valid"] is True
    assert (output / "model_data_report.md").is_file()


def test_private_rollout_passive_case_retains_explicit_fictional_review_boundary(
    tmp_path,
):
    from tests.plugins.test_vera_native_passive_review import label_program

    destination = tmp_path / "passive-review"
    plugin = build_private_pilot(destination, owned=True, passive_review_case=True)
    environment = profile_environment(plugin, "veraNativeWorkspace")
    case = json.loads(
        (destination / "passive-native-acceptance-case.json").read_bytes()
    )
    recipe = case["recipe"]
    choices = {
        identity: role
        for role, identity in recipe["inputs"].items()
        if role != "invoices"
    }
    choices.update({identity: "invoices" for identity in recipe["inputs"]["invoices"]})
    fields = {
        "choices": choices,
        "controls": {
            key: str(value) if value is not None else ""
            for key, value in recipe["controls"].items()
        },
        "operator_ref": "Fictional pilot mechanism reviewer",
        "decision_basis": "Fictional retained semantic checkpoint; no model execution or ledger approval.",
    }

    result = rpc_program(
        environment,
        label_program(fields).replace(
            "fictional-passive", "passive-fictional-checkpoint"
        )
        + """
const published=payload(call('vera_workspace_passive_review_publish',{...reviewAuthority(recovered),human_reviewed:true,idempotency_key:'private-pilot-labels'}));
const current=payload(call('vera_workspace_passive_review_setup',{work_ref:initial.work_ref}));
const directory=payload(call('vera_workspace_open',{}));
const result={published,current,directory};
""",
        server=plugin / "mcp/workspace.cjs",
    )

    assert len(result["directory"]["works"]) == 6
    assert result["published"]["status"] == "completed"
    assert result["current"]["selected_review"]["metrics"]["exception_recall"] == 0.0
    assert result["current"]["professional_approval"] is False
    assert "no model/provider" in case["scope"]
    assert "Absent" in case["human_labels"]
    binding = case["binding"]
    run = (
        Path(binding["client_root"])
        / "Vera/engagements"
        / binding["engagement_id"]
        / "runs"
        / binding["run_id"]
    )
    manifest = json.loads((run / "run.json").read_bytes())
    assert "fittizio" in manifest["label"]
    assert "nessuna esecuzione del modello" in manifest["purpose"]


def profile_environment(plugin: Path, profile: str) -> dict[str, str]:
    """Run the packaged configuration without account credentials or inherited scope."""
    environment = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR")
        if key in os.environ
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.update(
        json.loads((plugin / ".mcp.json").read_bytes())["mcpServers"][profile]["env"]
    )
    return environment


def test_private_rollout_default_retains_five_operator_cases(tmp_path):
    plugin = build_private_pilot(tmp_path / "operator", owned=False)
    environment = profile_environment(plugin, "veraNativeWorkspace")

    result = rpc_program(
        environment,
        """
const initial=payload(call('vera_workspace_open', {}));
const projections=initial.works.map(row=>payload(call('vera_workspace_view', {work_ref:row.work_ref})));
const result={initial, projections};
""",
        server=plugin / "mcp/workspace.cjs",
    )

    assert (
        "veraOwnedWorkspace"
        not in json.loads((plugin / ".mcp.json").read_bytes())["mcpServers"]
    )
    assert [row["work_ref"] for row in result["initial"]["works"]] == [
        "aurora_2025",
        "boreale_2025",
        "bank-fictional",
        "treasury-fictional",
        "archive-fictional",
    ]
    assert [row["workflow"] for row in result["projections"]] == [
        "bilancio-xbrl-it",
        "bilancio-xbrl-it",
        "journal-bank-reconciliation",
        "treasury-forecast",
        "archive-organization",
    ]


def test_private_rollout_owned_profile_executes_reviewed_bank_and_treasury(tmp_path):
    plugin = build_private_pilot(tmp_path / "owned", owned=True)
    environment = profile_environment(plugin, "veraOwnedWorkspace")

    result = rpc_program(
        environment,
        """
const directory=payload(call('vera_workspace_open',{}));
const works=[];
for(const client of directory.clients.filter(row=>row.client_id)) {
 const engagements=payload(call('vera_workspace_open',{client_id:client.client_id}));
 for(const engagement of engagements.engagements)
  works.push(...payload(call('vera_workspace_open',{client_id:client.client_id,engagement_id:engagement.engagement_id})).works);
}
const foreign=call('vera_workspace_open',{client_id:'client_bbbbbbbbbbbbbbbbbbbbbbbb'});
const bilancio=payload(call('vera_workspace_view',{work_ref:works.find(row=>row.workflow==='bilancio-xbrl-it').work_ref}));
const bank=works.find(row=>row.workflow==='journal-bank-reconciliation');
const bankScope=state=>({work_ref:state.work_ref,revision:state.revision,review_ticket:state.review_ticket,human_reviewed:true});
const initial=payload(call('vera_workspace_bank_setup',{work_ref:bank.work_ref}));
const inspection=payload(call('vera_workspace_bank_inspect',{...bankScope(initial),bank_input_ids:initial.items.filter(row=>row.title==='bank.csv').map(row=>row.id),journal_input_ids:initial.items.filter(row=>row.title==='journal.csv').map(row=>row.id),language:'it',document_language:'auto',idempotency_key:'pilot-inspect'}));
const page=payload(call('vera_workspace_bank_setup',{work_ref:bank.work_ref}));
const proposal=structuredClone(page.proposal);
proposal.policy.default_currency='CHF';
proposal.policy.default_entity_ref='entity.owned.demo';
const reviewed=payload(call('vera_workspace_bank_review',{...bankScope(page),proposal_json:JSON.stringify(proposal),idempotency_key:'pilot-review'}));
const ready=payload(call('vera_workspace_bank_setup',{work_ref:bank.work_ref}));
const execution=payload(call('vera_workspace_bank_reconcile',{...bankScope(ready),idempotency_key:'pilot-reconcile'}));
const bankView=payload(call('vera_workspace_view',{work_ref:bank.work_ref}));
const treasury=works.find(row=>row.workflow==='treasury-forecast');
const treasuryView=payload(call('vera_workspace_view',{work_ref:treasury.work_ref}));
const event=treasuryView.items[0].event_id;
const treasurySelected=payload(call('vera_workspace_view',{work_ref:treasury.work_ref,item_id:event}));
const saved=payload(call('vera_workspace_save',{work_ref:treasury.work_ref,revision:treasurySelected.revision,review_ticket:treasurySelected.review_ticket,item_id:event,human_reviewed:true,idempotency_key:'pilot-date',decisions:{[event]:{expected_date:'2026-10-01',basis:'Data fittizia verificata nella prova del pacchetto privato'}}}));
const treasuryReopened=payload(call('vera_workspace_view',{work_ref:treasury.work_ref}));
const result={directory,works,foreign,bilancio,initial,inspection,page,reviewed,ready,execution,bankView,treasuryView,saved,treasuryReopened};
""",
        server=plugin / "mcp/workspace.cjs",
    )

    assert "VERA_WORKSPACE_BINDINGS" not in environment
    assert len([row for row in result["directory"]["clients"] if row["client_id"]]) == 3
    assert result["foreign"]["isError"] is True
    assert len(result["works"]) == 3
    assert result["bilancio"]["kind"] == "bilancio"
    assert result["initial"]["status"] == "not_inspected"
    assert result["page"]["proposal"]["policy"]["default_currency"] is None
    assert result["ready"]["can_execute"] is True
    assert result["execution"]["matched"] == 2
    assert result["execution"]["professional_approval"] is False
    assert result["execution"]["run_completed"] is False
    assert result["bankView"]["workflow"] == "journal-bank-reconciliation"
    assert result["treasuryReopened"]["revision"] == result["saved"]["revision"]
    assert result["treasuryReopened"]["revision"] != result["treasuryView"]["revision"]

    bank_outputs = next(
        (tmp_path / "owned/fictional-archive/Banca iniziale - dati fittizi").glob(
            "Vera/engagements/*/runs/*/outputs"
        )
    )
    assert (bank_outputs / "reconciliation/journal_bank_reconciliation.xlsx").is_file()
    assert (bank_outputs / "reconciliation/review_payload.json").is_file()
    treasury_outputs = next(
        (tmp_path / "owned/fictional-archive/Studio client").glob(
            "Vera/engagements/*/runs/*/outputs"
        )
    )
    assert (
        treasury_outputs
        / "versions"
        / result["treasuryView"]["revision"]
        / "forecast.json"
    ).is_file()
    assert (
        treasury_outputs / "versions" / result["saved"]["revision"] / "tesoreria.xlsx"
    ).is_file()
