"""Owned fictional originals through public preparation; no real model/host claim."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from tests._plugin_cli import workflow_cli
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_aml_authoring import REQUEST, STAGE, program
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import registry_workspace
from tests.plugins.test_vera_native_workspace import ROOT

__all__ = []


@pytest.fixture
def initial_invoice(registry_workspace, tmp_path, monkeypatch, request):
    env, studio, _, _, client, engagement = registry_workspace
    env.update(
        VERA_WORKSPACE_ACTOR_ID="fictional-reviewer",
        VERA_WORKSPACE_TENANT_ID="fictional-studio",
        VERA_WORKSPACE_ROLES="REVIEWER",
    )
    monkeypatch.syspath_prepend(str(ROOT / "plugins/invoice-xml/scripts"))
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    spec = importlib.util.spec_from_file_location(
        "fictional_author_invoice",
        ROOT / "plugins/invoice-xml/tests/test_invoice_xml.py",
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    variant = getattr(request, "param", "TD01")
    proposal, original = fixture._proposal(
        tmp_path, variant if variant.startswith("TD") else "TD01"
    )
    if variant == "partial":
        proposal["invoice"]["FatturaElettronicaBody"][0]["DatiGenerali"][
            "DatiGeneraliDocumento"
        ]["Numero"] = None
        proposal["questions"] = ["Fictional numbering remains unknown."]
        fixture._refresh_evidence(proposal)
    if variant == "body-object":
        proposal["invoice"]["FatturaElettronicaBody"] = proposal["invoice"][
            "FatturaElettronicaBody"
        ][0]
        fixture._refresh_evidence(proposal)
    folder, ledger = studio / "Cliente Beta", _load_customer_ledger()
    source_paths = [original / "synthetic-invoice.txt"]
    if variant == "all-pages":
        import fitz

        document = fitz.open()
        document.new_page().insert_text((72, 72), "Fictional PDF page one")
        document.new_page().insert_text((72, 72), "Fictional PDF page two")
        document.save(original / "fictional.pdf")
        pixmap = document[0].get_pixmap()
        pixmap.save(original / "fictional.png")
        document.close()
        (original / "fictional.json").write_text('{"context":"fictional"}')
        source_paths.extend(
            original / name
            for name in ("fictional.pdf", "fictional.png", "fictional.json")
        )
    imported = [
        ledger.import_document(folder, client, engagement, path, "source")["receipt"]
        for path in source_paths
    ]
    prepared = ledger.prepare_run(
        folder,
        client,
        engagement,
        "invoice-xml",
        "test-version",
        input_ids=[r["input_id"] for r in imported],
    )
    ledger.start_run(folder, engagement, prepared["run"]["run_id"])
    loaded = ledger.load_run(folder, engagement, prepared["run"]["run_id"])
    originals = {r["sha256"]: r for r in loaded["input_manifest"]["inputs"]}
    first = originals[proposal["sources"][0]["sha256"]]
    proposal["sources"][0]["path"] = (
        Path(first["execution_relative_path"]).relative_to("inputs").as_posix()
    )
    for index, receipt in enumerate(imported[1:], 2):
        row = originals[receipt["sha256"]]
        proposal["sources"].append(
            {
                "id": f"source-{index}",
                "path": Path(row["execution_relative_path"])
                .relative_to("inputs")
                .as_posix(),
                "sha256": row["sha256"],
                "title": "Fictional supplementary original",
                "role": "context",
                "evidence_group": "invoice-1",
            }
        )
    ref = "studio-" + "_".join(
        v.split("_", 1)[1] for v in (client, engagement, prepared["run"]["run_id"])
    )
    return env, folder, loaded, proposal, ref, fixture


def invoice_program(ref: str, proposal: dict, body: str) -> str:
    return (
        program(ref, {"proposal": proposal}, body)
        .replace("vera_workspace_aml_author_", "vera_workspace_invoice_author_")
        .replace(
            "Fictional review of the documented loan: preserve unresolved explanations.",
            "Fictional invoice from complete originals; unknown values remain unknown.",
        )
    )


EVIDENCE = """
const selection=review.proposal.sources.map(({sha256,...source})=>source);
const evidenceArgs={...exact,expected_stage_revision:context.stage_revision,selection,idempotency_key:'fictional-evidence'};
const evidence=model(call('vera_workspace_invoice_author_evidence',evidenceArgs));
review.evidence_ref=evidence.evidence_ref;
context=model(call('vera_workspace_invoice_author_context',exact));
"""
# Source preparation changes the private CAS stamp; reread it before proposal authoring.
REQUEST_INVOICE = REQUEST.replace("const context=", "let context=")
ALL = REQUEST_INVOICE + EVIDENCE + STAGE


@pytest.mark.parametrize(
    "initial_invoice",
    ["TD01", "TD04", "TD17", "TD18", "TD19", "partial", "body-object"],
    indirect=True,
)
def test_complete_originals_conserve_public_proposal_without_export_or_approval(
    initial_invoice,
):
    env, _, loaded, proposal, ref, _ = initial_invoice
    result = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            ALL
            + "const saved=payload(call('vera_workspace_invoice_author_publish',publishArgs));"
            + "const retry=payload(call('vera_workspace_invoice_author_publish',publishArgs));"
            + "const evidenceRetry=model(call('vera_workspace_invoice_author_evidence',evidenceArgs));"
            + "const after=payload(call('vera_workspace_view',{work_ref,source_ref:saved.source_ref}));"
            + "const result={saved,retry,evidence,evidenceRetry,context,read,after};",
        ),
    )
    output = Path(loaded["output_dir"])
    draft = output / ("draft-" + result["saved"]["source_ref"])
    assert json.loads((draft / "proposal.json").read_text()) == proposal
    assert (draft / "preview.html").read_text() == result["read"]["memo"]
    assert json.loads((draft / "review_request.json").read_text())["reviewer"] is None
    assert result["read"]["record"]["export"] is None
    assert result["read"]["record"]["review"] is None
    assert result["saved"]["professional_approval"] is False
    assert result["after"]["kind"] == "invoice"
    assert result["saved"] == result["retry"]
    assert result["evidence"] == result["evidenceRetry"]
    assert result["evidence"]["model_exposure_verified"] is False
    assert (
        result["context"]["prepared_evidence"][0]["manifest"]["sources"]
        == proposal["sources"]
    )
    assert not list(output.rglob("*.xml"))
    assert (
        output / ("invoice-native-proposal-" + result["saved"]["source_ref"] + ".json")
    ).is_file()
    assert loaded["run"]["status"] == "running"


@pytest.mark.parametrize("initial_invoice", ["all-pages"], indirect=True)
def test_source_preparation_retains_all_pages_images_text_and_original_hashes(
    initial_invoice,
):
    env, _, _, proposal, ref, _ = initial_invoice
    result = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            REQUEST_INVOICE + EVIDENCE + "const result={evidence,context};",
        ),
    )
    manifest, path = result["evidence"]["manifest"], Path(
        result["evidence"]["views_directory"]
    )
    assert manifest["sources"] == proposal["sources"]
    assert len(manifest["material"]) == 4
    pdf = next(row for row in manifest["material"] if len(row["views"]) == 2)
    assert [v["page"] for v in pdf["views"]] == [1, 2]
    assert "page one" in (path / pdf["views"][0]["text"]).read_text()
    assert "page two" in (path / pdf["views"][1]["text"]).read_text()
    assert (path / pdf["views"][1]["image"]).is_file()
    assert result["evidence"]["model_exposure_verified"] is False
    assert result["context"]["stage_revision"]


@pytest.mark.parametrize(
    "change",
    [
        "approval",
        "foreign_source",
        "hash",
        "lost_source",
        "foreign_evidence",
        "metadata",
    ],
)
def test_proposal_rejects_ungranted_originals_and_extra_authority(
    initial_invoice, change
):
    env, _, loaded, proposal, ref, _ = initial_invoice
    mutate = {
        "approval": "review.review={status:'approved_for_export'};",
        "foreign_source": "review.proposal.sources[0].path='../foreign.txt';",
        "hash": "review.proposal.sources[0].sha256='0'.repeat(64);",
        "lost_source": "review.proposal.sources=[];",
        "foreign_evidence": "review.evidence_ref='evidence-'+'0'.repeat(64);",
        "metadata": "review.proposal.sources[0].role='professional_confirmation';",
    }[change]
    result = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            REQUEST_INVOICE
            + EVIDENCE
            + mutate
            + "const result=call('vera_workspace_invoice_author_stage',{...exact,expected_stage_revision:context.stage_revision,review,idempotency_key:'refused'});",
        ),
    )
    assert result["isError"] is True
    assert not list(Path(loaded["output_dir"]).glob("draft-*"))


@pytest.mark.parametrize("change", ["missing", "foreign", "role", "duplicate", "stale"])
def test_evidence_preparation_requires_every_chosen_original_and_fresh_cas(
    initial_invoice, change
):
    env, _, loaded, proposal, ref, _ = initial_invoice
    mutate = {
        "missing": "selection=[];",
        "foreign": "selection[0].path='../foreign.txt';",
        "role": "selection[0].role='filename-inferred';",
        "duplicate": "selection.push(selection[0]);",
        "stale": "context.stage_revision='0'.repeat(64);",
    }[change]
    result = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            REQUEST_INVOICE
            + "let selection=review.proposal.sources.map(({sha256,...source})=>source);"
            + mutate
            + "const result=call('vera_workspace_invoice_author_evidence',{...exact,selection,expected_stage_revision:context.stage_revision,idempotency_key:'refused'});",
        ),
    )
    assert result["isError"] is True
    assert not list(
        Path(loaded["output_dir"]).parent.glob(
            ".native-workspace/invoice-authoring-*/mandate-*/evidence-*/source_evidence.json"
        )
    )


@pytest.mark.parametrize(
    "damage", ["missing_receipt", "orphan", "pending", "changed_view"]
)
def test_uncertain_prepared_evidence_blocks_new_proposals_and_archive_closure(
    initial_invoice, damage
):
    env, _, loaded, proposal, ref, _ = initial_invoice
    prepared = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            REQUEST_INVOICE + EVIDENCE + "const result={requested,evidence};",
        ),
    )
    view = Path(prepared["evidence"]["views_directory"])
    base = view.parent
    if damage == "missing_receipt":
        next(base.glob("evidence-request-*.json")).unlink()
    elif damage == "orphan":
        (base / ("evidence-" + "0" * 64)).mkdir()
    elif damage == "pending":
        (base / ("evidence-request-" + "0" * 64 + ".json")).write_text("{}")
    else:
        next(p for p in view.iterdir() if p.suffix == ".txt").write_text(
            "Altered actual prepared text"
        )
    result = rpc_program(
        env,
        f"""
const setupNow=call('vera_workspace_invoice_author_setup',{{work_ref:{json.dumps(ref)}}});
const closure=call('vera_workspace_archive_closure',{{client_id:{json.dumps(loaded['run']['client_id'])},engagement_id:{json.dumps(loaded['run']['engagement_id'])},run_id:{json.dumps(loaded['run']['run_id'])}}});
const result={{setupNow,closure}};
""",
    )
    assert result["closure"]["isError"] is True
    if damage == "changed_view":
        assert result["setupNow"]["isError"] is True
    else:
        assert result["setupNow"]["_meta"]["workspace"]["can_write"] is False


def test_authoring_conservation_requires_separate_actual_professional_export(
    initial_invoice,
):
    env, _, loaded, proposal, ref, fixture = initial_invoice
    result = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            ALL
            + """
const saved=payload(call('vera_workspace_invoice_author_publish',publishArgs));
const chosen=payload(call('vera_workspace_invoice_setup',{work_ref,source_ref:saved.source_ref}));
const reviewFields={reviewer:'Fictional actual reviewer',reviewed_at:'2026-10-07T12:00:00+02:00',approval_basis:'Fictional actual approval; not tax certification'};
const exportScope={work_ref,revision:chosen.revision,review_ticket:chosen.review_ticket,source_ref:saved.source_ref,expected_draft_revision:''};
const drafted=payload(call('vera_workspace_invoice_draft_save',{...exportScope,fields:reviewFields}));
const args={...exportScope,expected_draft_revision:drafted.draft_revision,review:reviewFields,human_reviewed:false,idempotency_key:'refused-export'};
const refused=call('vera_workspace_invoice_export',args);
const accepted=payload(call('vera_workspace_invoice_export',{...args,human_reviewed:true,idempotency_key:'actual-export'}));
const result={saved,refused,accepted};
""",
        ),
    )
    output = Path(loaded["output_dir"])
    actual = next(output.rglob("*.xml")).read_bytes()
    assert result["refused"]["isError"] is True
    assert result["accepted"]["status"] == "exported_for_operator"
    assert fixture.InvoiceSchema().errors(actual) == []
    assert result["saved"]["professional_approval"] is False


@pytest.mark.parametrize("change", ["actor", "tenant", "source"])
def test_prepared_sources_remain_bound_to_actual_actor_tenant_and_original_bytes(
    initial_invoice, change
):
    env, _, _, proposal, ref, _ = initial_invoice
    saved = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            REQUEST_INVOICE + EVIDENCE + "const result={requested,context};",
        ),
    )
    if change == "source":
        Path(saved["context"]["sources"][0]["path"]).write_text("Changed original")
    else:
        env = {
            **env,
            "VERA_WORKSPACE_" + change.upper() + "_ID": "another-fictional-owner",
        }
    result = rpc_program(
        env,
        "const result=call('vera_workspace_invoice_author_context',"
        + json.dumps({"work_ref": ref, "grant_ref": saved["requested"]["grant_ref"]})
        + ");",
    )
    assert result["isError"] is True


def test_same_original_correction_retains_old_xml_and_does_not_carry_approval(
    initial_invoice,
):
    env, _, loaded, proposal, ref, fixture = initial_invoice
    first = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            ALL
            + "const result=payload(call('vera_workspace_invoice_author_publish',publishArgs));",
        ),
    )
    output = Path(loaded["output_dir"])
    original = output / ("draft-" + first["source_ref"])
    fixture.export_invoice(
        original,
        fixture._review(proposal),
        input_root=Path(loaded["run_root"]) / "inputs",
    )
    old_bytes = {
        p.relative_to(output).as_posix(): p.read_bytes()
        for p in output.rglob("*")
        if p.is_file()
    }
    proposal["draft_id"] = "fictional-corrected"
    proposal["invoice"]["FatturaElettronicaBody"][0]["DatiGenerali"][
        "DatiGeneraliDocumento"
    ]["Numero"] = "FICTIONAL-CORRECTION"
    fixture._refresh_evidence(proposal)
    second = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            ALL
            + "const result=payload(call('vera_workspace_invoice_author_publish',publishArgs));",
        ).replace("fictional-mandate", "correction-mandate"),
    )
    assert second["source_ref"] != first["source_ref"]
    assert {name: (output / name).read_bytes() for name in old_bytes} == old_bytes
    assert not (output / ("draft-" + second["source_ref"]) / "export").exists()
    assert len(list(output.glob("intake-*"))) == 1


def test_public_html_replay_preserves_literal_carriage_returns(initial_invoice):
    env, _, loaded, proposal, ref, _ = initial_invoice
    proposal["decisions"]["source_completeness"][
        "assessment"
    ] = "Fictional first line\r\nFictional second line"
    result = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            ALL
            + "const result=payload(call('vera_workspace_invoice_author_publish',publishArgs));",
        ),
    )
    preview = (
        Path(loaded["output_dir"]) / ("draft-" + result["source_ref"]) / "preview.html"
    ).read_bytes()
    assert b"Fictional first line\r\nFictional second line" in preview


@pytest.mark.parametrize("committed", [False, True])
def test_interrupted_public_draft_conservation_never_repeats_or_adopts(
    initial_invoice, monkeypatch, committed
):
    import native_aml_authoring

    from tests.plugins.test_vera_native_workspace import workspace_module

    env, _, loaded, proposal, ref, _ = initial_invoice
    staged = rpc_program(
        env, invoice_program(ref, proposal, ALL + "const result={publishArgs,staged};")
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    actual = native_aml_authoring.inspect

    def interrupted(*args, **kwargs):
        if kwargs.get("save"):
            if committed:
                actual(*args, **kwargs)
            raise TimeoutError("Fictional interrupted invoice conservation")
        return actual(*args, **kwargs)

    monkeypatch.setattr(native_aml_authoring, "inspect", interrupted)
    api, output = workspace_module(), Path(loaded["output_dir"])
    with pytest.raises(TimeoutError, match="interrupted"):
        api.dispatch("vera_workspace_invoice_author_publish", staged["publishArgs"])
    before = {
        p.relative_to(output).as_posix(): p.read_bytes()
        for p in output.rglob("*")
        if p.is_file()
    }
    with pytest.raises(PermissionError, match="uncertain writes"):
        api.dispatch("vera_workspace_invoice_author_publish", staged["publishArgs"])
    setup = api.dispatch("vera_workspace_invoice_author_setup", {"work_ref": ref})
    assert setup["can_write"] is False
    assert setup["recovery_required"] is True
    assert {name: (output / name).read_bytes() for name in before} == before
    assert bool(list(output.glob("draft-*"))) is committed
    assert not list(output.rglob("*.xml"))


def test_interrupted_material_retention_blocks_retry_and_keeps_actual_views(
    initial_invoice, monkeypatch
):
    from tests.plugins.test_vera_native_workspace import workspace_module

    env, _, loaded, proposal, ref, _ = initial_invoice
    grant = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            REQUEST_INVOICE
            + "const selection=review.proposal.sources.map(({sha256,...source})=>source);const result={exact,context,selection};",
        ),
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    api = workspace_module()
    actual = api.atomic_json

    def interrupted(path, value):
        if path.name == "state.json":
            raise TimeoutError("Fictional interrupted material retention")
        return actual(path, value)

    monkeypatch.setattr(api, "atomic_json", interrupted)
    args = {
        **grant["exact"],
        "expected_stage_revision": grant["context"]["stage_revision"],
        "selection": grant["selection"],
        "idempotency_key": "interrupted-material",
    }
    with pytest.raises(TimeoutError, match="interrupted"):
        api.dispatch("vera_workspace_invoice_author_evidence", args)
    with pytest.raises(PermissionError, match="uncertain writes"):
        api.dispatch("vera_workspace_invoice_author_evidence", args)
    setup = api.dispatch("vera_workspace_invoice_author_setup", {"work_ref": ref})
    assert setup["can_write"] is False
    assert setup["recovery_required"] is True
    assert list(
        Path(loaded["output_dir"]).parent.glob(
            ".native-workspace/invoice-authoring-*/mandate-*/evidence-*/source_evidence.json"
        )
    )


@pytest.mark.parametrize("host", ["codex", "cowork"])
def test_extracted_maintained_packages_prepare_and_public_cli_corrects(
    initial_invoice, tmp_path, host
):
    env, _, loaded, proposal, ref, fixture = initial_invoice
    if host == "codex":
        from scripts import build_codex_plugin_zip as builder

        bundle = next(b for b in builder.load_bundles() if b.target_name == "vera")
        entries = builder.expected_zip_entries(bundle)
        prefix = "vera-codex-plugin/plugins/vera/"
    else:
        from scripts import build_claude_plugin_zip as builder

        _, packages = builder.load_configuration()
        bundle = next(b for b in packages if b.plugin == "vera")
        entries = builder.claude_package_entries(bundle)
        prefix = ""
    target = tmp_path / "extracted"
    for name, content in entries.items():
        if name.startswith(prefix):
            path = target / name[len(prefix) :]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    result = rpc_program(
        env,
        invoice_program(
            ref,
            proposal,
            ALL
            + "const result=payload(call('vera_workspace_invoice_author_publish',publishArgs));",
        ),
        server=target / "mcp/workspace.cjs",
    )
    output = Path(loaded["output_dir"])
    first = output / ("draft-" + result["source_ref"]) / "proposal.json"
    previous = first.read_bytes()
    proposal["draft_id"] = "fictional-independent-public-correction"
    request = output / "independent-correction.json"
    request.write_text(json.dumps(proposal))
    completed = subprocess.run(
        [
            *workflow_cli(target / "modules/invoice-xml/scripts/invoice_workflow.py"),
            "prepare",
            "--client-engagement",
            loaded["context_path"],
            "--proposal",
            str(request),
            "--output",
            str(output),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr
    assert (output / ("draft-" + fixture.digest(proposal)) / "proposal.json").is_file()
    assert first.read_bytes() == previous
    assert not list(output.rglob("*.xml"))
    assert (target / "scripts/native_invoice_authoring.py").read_bytes() == (
        ROOT / "plugins/vera/scripts/native_invoice_authoring.py"
    ).read_bytes()
    assert (
        target / "modules/invoice-xml/scripts/invoice_workflow.py"
    ).read_bytes() == entries[
        prefix + "modules/invoice-xml/scripts/invoice_workflow.py"
    ]
