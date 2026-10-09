"""Fictional actual producer jobs; no worker/provider or installed-host acceptance."""

from __future__ import annotations

import copy
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def audit_workspace(tmp_path, monkeypatch, request, vera_workflow_workspace):
    scripts = ROOT / "plugins/passive-invoice-audit/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    spec = importlib.util.spec_from_file_location(
        "fictional_passive_audit_fixture",
        ROOT / "plugins/passive-invoice-audit/tests/test_passive_invoice_audit.py",
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    import native_passive_audit as native

    xml = tmp_path / "invoice.xml"
    fixture._write_invoice(xml)
    variant = getattr(request, "param", "ordinary")
    if variant == "fresh":
        fixture._write_invoice(xml, number="INV-FRESH", supplier_vat="01234511111")
    ledger = fixture._write_ledger(
        tmp_path / "ledger.csv",
        fixture._ledger_rows(
            number="FOREIGN" if variant in {"missing", "fresh"} else "INV-1",
            supplier_vat="01234522222" if variant == "fresh" else "01234567890",
            gross="777.00" if variant == "fresh" else "122.00",
        ),
    )
    mapping = fixture._write_mapping(tmp_path / "mapping.json")
    source_files = {"invoice.xml": xml.read_text()}
    if variant in {"many", "ambiguous"}:
        source_files = {}
        ledger_rows = []
        for index in range(61 if variant == "many" else 3):
            number = f"INV-{index + 1:03d}"
            supplier = f"0123456{index:04d}" if variant == "many" else "01234567890"
            fixture._write_invoice(xml, number=number, supplier_vat=supplier)
            source_files[f"invoice-{index + 1:03d}.xml"] = xml.read_text()
            ledger_rows.extend(
                fixture._ledger_rows(
                    number=number,
                    supplier_vat=supplier,
                    movement_id=f"M-{index + 1:03d}",
                )
            )
        fixture._write_ledger(ledger, ledger_rows)
    work = vera_workflow_workspace(
        "passive-invoice-audit",
        input_files={
            **source_files,
            "ledger.csv": ledger.read_text(),
            "mapping.json": mapping.read_text(),
        },
    )
    identities = {
        Path(row["path"]).name: row["binding_id"]
        for row in work["context"]["input_bindings"]
    }
    recipe = {
        "inputs": {
            "invoices": [identities[name] for name in source_files],
            "ledger": identities["ledger.csv"],
            "ledger_mapping": identities["mapping.json"],
        },
        "controls": {
            "ledger_sheet": None,
            "chunk_size": 25 if variant == "many" else 1,
            "concurrency": 1,
            "max_retries": 0,
            "reasoning_effort": "low",
            "amount_tolerance": "0.01",
        },
    }
    workers = SimpleNamespace(
        configured_runtime=lambda: "codex-luna",
        load_worker_selection=lambda path, **kwargs: (
            "gpt-5.6-luna",
            kwargs["reasoning_effort"],
            None,
        ),
    )
    plan = native.build_plan(fixture.audit_core, work["context"], recipe, workers)
    runner = fixture.FixtureRunner({}, fail=variant == "failed")
    if variant == "cowork":
        import cowork_worker

        workers.configured_runtime = lambda: "cowork-haiku"
        plan = native.build_plan(fixture.audit_core, work["context"], recipe, workers)
        runner = cowork_worker.run_cowork_chunk
    elif variant == "exception":

        class ExceptionRunner(fixture.FixtureRunner):
            def __call__(self, *args, **kwargs):
                result = super().__call__(*args, **kwargs)
                for row in result["response_payload"]["results"]:
                    row.update(
                        status="review_required",
                        suspected_issue_type="economic_substance_account_mismatch",
                        invoice_evidence=["Fictional telecom line"],
                        booked_account_evidence=["Fictional booked expense account"],
                        professional_should_inspect="Compare the fictional classification with the invoice line.",
                    )
                return result

        runner = ExceptionRunner({})
    if variant == "failed":
        with pytest.raises(fixture.audit_core.AuditError, match="Luna chunks failed"):
            native.run_job(fixture.audit_core, plan, runner)
    elif variant != "fresh":
        native.run_job(fixture.audit_core, plan, runner)
    return SimpleNamespace(
        native=native,
        producer=fixture.audit_core,
        fixture=fixture,
        work=work,
        recipe=recipe,
        plan=plan,
        workers=workers,
        runner=runner,
        output=work["output_dir"],
    )


def bridge(work, operation="inspect", args=None, package=None):
    base = package or ROOT / "plugins/vera"
    producer = (
        package / "modules/passive-invoice-audit"
        if package
        else ROOT / "plugins/passive-invoice-audit"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(base / "scripts/native_passive_audit_bridge.py"),
            str(producer),
        ],
        input=json.dumps(
            {
                "operation": operation,
                "context": str(work.work["context_path"]),
                "recipe": work.recipe,
                "args": args or {},
            }
        ),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip().splitlines()[-1])
    return json.loads(result.stdout)


def inspect(work, **args):
    return work.native.inspect_job(work.producer, work.plan, args)


def change_json(path, callback):
    value = json.loads(path.read_text())
    callback(value)
    path.write_text(json.dumps(value))


def test_passive_job_inspection_is_exact_read_only_and_never_approval(audit_workspace):
    work = audit_workspace
    before = work.native.tree_hash(work.output)

    result = bridge(work)

    assert result["status"] == "completed"
    assert result["total"] == 0
    assert result["summary"]["luna_no_issue_detected"] == 1
    assert result["professional_approval"] is False
    assert result["provider_attestation"] is False
    assert result["archive_completed"] is False
    assert work.native.tree_hash(work.output) == before
    assert (
        json.loads(Path(work.work["context"]["run_manifest_path"]).read_text())[
            "status"
        ]
        == "running"
    )


def test_passive_population_selected_json_contains_only_explicit_member(
    audit_workspace,
):
    work = audit_workspace
    page = inspect(work, view="population")
    selected = inspect(work, view="population", item_id=page["items"][0]["id"])
    pointer = next(
        row["source_ref"]
        for row in selected["selection"]["entries"]
        if row["name"] == "invoice"
    )

    member = inspect(
        work,
        view="population",
        item_id=page["items"][0]["id"],
        source_ref=pointer,
        revision=page["revision"],
    )

    assert member["selection"]["path"] == ["invoice"]
    assert "entries" in member["selection"]
    assert member["selection"]["coverage"].startswith("This exact member page only")
    assert member["selection"]["total"] > 10


def test_passive_resume_reuses_completed_actual_producer_chunks(audit_workspace):
    work = audit_workspace
    calls = work.runner.calls
    chunks = work.native.tree_hash(work.output / "luna_chunks")

    summary = work.native.run_job(work.producer, work.plan, work.runner)

    assert work.runner.calls == calls
    assert work.native.tree_hash(work.output / "luna_chunks") == chunks
    assert summary["status"] == "completed"
    assert inspect(work)["summary"]["population"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("chunk_size", True),
        ("concurrency", 5),
        ("max_retries", -1),
        ("amount_tolerance", "NaN"),
        ("amount_tolerance", "not-money"),
        ("amount_tolerance", "-0.01"),
        ("reasoning_effort", "cheap"),
        ("ledger_sheet", ""),
    ],
)
def test_passive_plan_rejects_unsupported_explicit_controls(
    audit_workspace, field, value
):
    work = audit_workspace
    recipe = copy.deepcopy(work.recipe)
    recipe["controls"][field] = value

    with pytest.raises(ValueError):
        work.native.build_plan(
            work.producer, work.work["context"], recipe, work.workers
        )


@pytest.mark.parametrize("role", ["ledger", "ledger_mapping", "invoices"])
def test_passive_plan_rejects_foreign_receipt_id(audit_workspace, role):
    work = audit_workspace
    recipe = copy.deepcopy(work.recipe)
    recipe["inputs"][role] = ["foreign"] if role == "invoices" else "foreign"

    with pytest.raises(PermissionError, match="exact run receipt"):
        work.native.build_plan(
            work.producer, work.work["context"], recipe, work.workers
        )


@pytest.mark.parametrize("view", ["population", "chunks", "orphans", "exceptions"])
def test_passive_inspection_rejects_foreign_selected_item(audit_workspace, view):
    with pytest.raises(ValueError, match="another view or population"):
        inspect(audit_workspace, view=view, item_id="invoice:foreign")


def test_passive_changed_controls_refuse_existing_database(audit_workspace):
    work = audit_workspace
    recipe = copy.deepcopy(work.recipe)
    recipe["controls"]["amount_tolerance"] = "0.02"
    plan = work.native.build_plan(
        work.producer, work.work["context"], recipe, work.workers
    )

    with pytest.raises(ValueError, match="different inputs or controls"):
        work.native.inspect_job(work.producer, plan, {})


def test_passive_changed_registered_source_refuses_before_read(audit_workspace):
    work = audit_workspace
    work.work["input_by_name"]["ledger.csv"].write_text("changed source")

    with pytest.raises(ValueError, match="source receipt changed"):
        work.native.build_plan(
            work.producer, work.work["context"], work.recipe, work.workers
        )


@pytest.mark.parametrize(
    "artifact",
    [
        "full_population.jsonl",
        "exception_workpaper.xlsx",
        "run_summary.json",
        "audit.sqlite3",
    ],
)
def test_passive_linked_artifact_is_rejected(audit_workspace, artifact):
    work = audit_workspace
    path = work.output / artifact
    moved = path.with_name("moved-" + path.name)
    path.rename(moved)
    path.symlink_to(moved)

    with pytest.raises(ValueError, match="linked"):
        inspect(work)


@pytest.mark.parametrize(
    "artifact", ["audit_packets.json", "luna_output_schema.json", "chunk_result.json"]
)
def test_passive_altered_chunk_contract_is_rejected(audit_workspace, artifact):
    work = audit_workspace
    directory = next((work.output / "luna_chunks").iterdir())
    # Discover the maintained public checkpoint name instead of assuming it.
    path = directory / (
        work.producer.CHUNK_RESULT_NAME if artifact == "chunk_result.json" else artifact
    )
    value = json.loads(path.read_text())
    if artifact == "audit_packets.json":
        value[0]["invoice_id"] = "foreign"
    elif artifact == "luna_output_schema.json":
        value["title"] = "foreign schema"
    else:
        value["model"] = "unreviewed-model"
    path.write_text(json.dumps(value))

    with pytest.raises(ValueError):
        inspect(work)


def test_passive_altered_published_screening_state_is_rejected(audit_workspace):
    work = audit_workspace
    path = work.output / "full_population.jsonl"
    row = json.loads(path.read_text())
    row["final_state"] = "approved"
    path.write_text(json.dumps(row) + "\n")

    with pytest.raises(ValueError, match="screening state changed"):
        inspect(work)


def test_passive_exception_workpaper_values_are_public_producer_values(audit_workspace):
    from openpyxl import load_workbook

    work = audit_workspace
    path = work.output / "exception_workpaper.xlsx"
    workbook = load_workbook(path)
    workbook.worksheets[0]["A1"] = "Certified correct"
    workbook.save(path)
    workbook.close()

    with pytest.raises(ValueError, match="workbook differs"):
        inspect(work)


def test_passive_summary_counter_change_is_rejected(audit_workspace):
    work = audit_workspace
    change_json(
        work.output / "run_summary.json", lambda row: row.update(population=999)
    )

    with pytest.raises(ValueError, match="summary counters"):
        inspect(work)


def test_passive_live_chunk_hides_stale_completed_summary(audit_workspace):
    work = audit_workspace
    with sqlite3.connect(work.output / "audit.sqlite3") as connection:
        connection.execute("UPDATE chunks SET status='running'")

    result = inspect(work)

    assert result["status"] == "in_progress"
    assert result["published_summary_current"] is False
    assert "summary" not in result
    assert result["chunk_counts"] == {"running": 1}


def test_passive_bridge_has_no_unqualified_worker_execution_route(audit_workspace):
    with pytest.raises(
        ValueError, match="Unsupported passive-invoice foundation action"
    ):
        bridge(audit_workspace, "run")


def test_passive_job_revision_rejects_new_output_population(audit_workspace):
    work = audit_workspace
    revision = inspect(work)["revision"]
    (work.output / "extra.txt").write_text("new evidence")

    with pytest.raises(ValueError, match="job changed"):
        inspect(work, revision=revision)


@pytest.mark.parametrize(
    "audit_workspace,expected",
    [
        ("missing", "completed"),
        ("exception", "completed"),
        ("failed", "failed"),
        ("cowork", "awaiting_semantic_review"),
    ],
    indirect=["audit_workspace"],
)
def test_passive_partial_and_exception_states_preserve_review_requirement(
    audit_workspace, expected
):
    result = inspect(audit_workspace)

    assert result["status"] == expected
    assert result["total"] == 1
    assert result["summary"]["invoices_requiring_professional_attention"] == 1
    assert result["professional_approval"] is False
    assert result["archive_completed"] is False


@pytest.mark.parametrize("audit_workspace", ["failed"], indirect=True)
def test_passive_failed_job_resumes_same_database_without_discarding_attempts(
    audit_workspace,
):
    work = audit_workspace
    runner = work.fixture.FixtureRunner({})

    summary = work.native.run_job(work.producer, work.plan, runner)

    assert summary["status"] == "completed"
    assert runner.calls == 1
    assert inspect(work)["summary"]["luna_chunks_completed"] == 1
    with sqlite3.connect(work.output / "audit.sqlite3") as connection:
        assert connection.execute("SELECT attempt_count FROM chunks").fetchone()[0] == 2


@pytest.mark.parametrize("audit_workspace", ["cowork"], indirect=True)
def test_passive_cowork_pending_keeps_host_request_and_never_reports_screening_success(
    audit_workspace,
):
    work = audit_workspace
    result = inspect(work)
    directory = next((work.output / "luna_chunks").iterdir())
    host_request = json.loads((directory / "cowork_request.json").read_text())

    assert result["summary"]["luna_no_issue_detected"] == 0
    assert result["summary"]["luna_not_run_or_failed"] == 1
    assert host_request["requested_model"] == "haiku"
    assert host_request["agent"] == "vera:passive-invoice-reviewer"
    assert not (directory / "cowork_response.json").exists()


@pytest.mark.parametrize(
    "control,value", [("worker_selection", "foreign"), ("reasoning_effort", "high")]
)
def test_passive_cowork_does_not_adopt_codex_override(audit_workspace, control, value):
    work = audit_workspace
    recipe = copy.deepcopy(work.recipe)
    workers = SimpleNamespace(
        configured_runtime=lambda: "cowork-haiku",
        load_worker_selection=work.workers.load_worker_selection,
    )
    if control == "worker_selection":
        recipe["inputs"][control] = value
        expected = PermissionError
    else:
        recipe["controls"][control] = value
        expected = ValueError

    with pytest.raises(expected):
        work.native.build_plan(work.producer, work.work["context"], recipe, workers)


@pytest.mark.parametrize(
    "args",
    [
        {"offset": True},
        {"offset": -1},
        {"view": "approved"},
        {"source_ref": 'json:{"path":[],"offset":0}'},
    ],
)
def test_passive_invalid_page_and_unselected_json_are_rejected(audit_workspace, args):
    with pytest.raises(ValueError):
        inspect(audit_workspace, **args)


def test_passive_summary_text_change_is_rejected(audit_workspace):
    work = audit_workspace
    path = work.output / "run_summary.md"
    path.write_text(path.read_text() + "Certified correct\n")

    with pytest.raises(ValueError, match="summary text structure"):
        inspect(work)


def test_passive_changed_population_while_reading_public_workpaper_is_rejected(
    audit_workspace, monkeypatch
):
    work = audit_workspace
    write = work.producer._write_exception_workpaper

    def concurrent_write(*args):
        write(*args)
        (work.output / "concurrent.txt").write_text("Concurrent actual output")

    monkeypatch.setattr(work.producer, "_write_exception_workpaper", concurrent_write)

    with pytest.raises(ValueError, match="changed during inspection"):
        inspect(work)


@pytest.mark.parametrize(
    "surface,audit_workspace",
    [("codex", "ordinary"), ("cowork", "cowork")],
    indirect=["audit_workspace"],
)
def test_passive_fresh_extracted_package_preserves_actual_job_and_runtime(
    audit_workspace, tmp_path, surface
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    builder = load_builder(
        "build_codex_plugin_zip" if surface == "codex" else "build_claude_plugin_zip"
    )
    if surface == "codex":
        vera = next(p for p in builder.load_bundles() if p.name == "vera")
        entries = builder.expected_zip_entries(vera)
        prefix = vera.package_root + "/plugins/vera/"
    else:
        _, packages = builder.load_configuration()
        vera = next(p for p in packages if p.plugin == "vera")
        entries = builder.claude_package_entries(vera)
        prefix = ""
    target = tmp_path / "extracted"
    for name, content in entries.items():
        if name.startswith(prefix):
            path = target / name[len(prefix) :]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    before = audit_workspace.native.tree_hash(audit_workspace.output)

    result = bridge(audit_workspace, package=target)

    assert result["status"] == (
        "completed" if surface == "codex" else "awaiting_semantic_review"
    )
    assert result["summary"]["semantic_worker_requested"] == (
        "gpt-5.6-luna" if surface == "codex" else "haiku"
    )
    assert result["professional_approval"] is False
    assert audit_workspace.native.tree_hash(audit_workspace.output) == before


def test_passive_plan_and_job_reject_late_source_change_before_execution(
    audit_workspace,
):
    work = audit_workspace
    before = work.native.tree_hash(work.output)
    work.work["input_by_name"]["ledger.csv"].write_text("Changed after plan")

    with pytest.raises(ValueError, match="source changed"):
        work.native.run_job(work.producer, work.plan, work.runner)

    assert work.native.tree_hash(work.output) == before


def test_passive_inspection_detects_source_race_and_keeps_actual_outputs(
    audit_workspace, monkeypatch
):
    work = audit_workspace
    before = work.native.tree_hash(work.output)
    write = work.producer._write_exception_workpaper

    def concurrent_source(*args):
        write(*args)
        work.work["input_by_name"]["ledger.csv"].write_text("Changed while reading")

    monkeypatch.setattr(work.producer, "_write_exception_workpaper", concurrent_source)

    with pytest.raises(ValueError, match="source changed"):
        inspect(work)

    assert work.native.tree_hash(work.output) == before


@pytest.mark.parametrize("audit_workspace", ["many"], indirect=True)
def test_passive_large_population_and_json_member_pages_remain_complete(
    audit_workspace,
):
    work = audit_workspace
    first = inspect(work, view="population")
    second = inspect(work, view="population", offset=30, revision=first["revision"])
    last = inspect(work, view="population", offset=60, revision=first["revision"])

    assert first["total"] == 61
    assert len(first["items"]) == len(second["items"]) == 30
    assert len(last["items"]) == 1
    assert set(row["id"] for row in first["items"]).isdisjoint(
        row["id"] for row in second["items"]
    )
    assert last["summary"]["luna_chunks_completed"] == 3
    assert last["summary"]["luna_no_issue_detected"] == 61


@pytest.mark.parametrize("audit_workspace", ["many"], indirect=True)
def test_passive_directory_population_cannot_silently_add_unselected_xml(
    audit_workspace,
):
    work = audit_workspace
    extra = work.work["input_dir"] / "unregistered.xml"
    extra.write_text(work.work["input_by_name"]["invoice-001.xml"].read_text())

    with pytest.raises(ValueError, match="differs from explicit receipts"):
        work.native.build_plan(
            work.producer, work.work["context"], work.recipe, work.workers
        )


@pytest.mark.parametrize("audit_workspace", ["ambiguous"], indirect=True)
def test_passive_does_not_force_same_supplier_date_amount_candidates(audit_workspace):
    work = audit_workspace
    result = inspect(work)

    assert result["total"] == 3
    assert result["summary"]["ambiguous_match"] == 3
    assert result["summary"]["luna_chunks_completed"] == 0
    assert work.runner.calls == 0
    assert result["professional_approval"] is False
