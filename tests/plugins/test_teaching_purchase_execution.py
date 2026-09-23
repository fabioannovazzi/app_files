"""Run invoice teaching workflows with reviewed native-output replay.

The real Codex executions are separately retained in the release review. These
portable regressions replay their exact semantic content, never a fake native
launch receipt or model attestation, through the current workflow and workbook.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

from tests.plugins._teaching_release import prepared_kit, record_native_check
from tests.plugins.test_teaching_kit_execution import ROOT, _bound_case, _read, _write

__all__: list[str] = []


def _load(name, filename, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, filename)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase,count", [("demo", 3), ("practice", 4)])
@prepared_kit("vera/purchase-invoice-review")
def test_purchase_kit_runs_reviewed_native_results_through_current_workflow(
    tmp_path, monkeypatch, record_property, language, phase, count
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "purchase-invoice-review",
        "passive-invoice-audit",
        phase,
        language=language,
    )
    context = run["context"]
    output = Path(run["output_dir"])
    ledger = next(
        Path(i["path"]) for i in context["input_bindings"] if i["path"].endswith(".csv")
    )
    with ledger.open(encoding="utf-8", newline="") as stream:
        headers = csv.DictReader(stream).fieldnames
    mapping = output / "reviewed-ledger-mapping.json"
    _write(mapping, {**{key: key for key in headers}, "number_format": "canonical"})
    scripts = ROOT / "plugins/passive-invoice-audit/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    _load("audit_core", scripts / "audit_core.py", monkeypatch)
    _load("luna_worker", scripts / "luna_worker.py", monkeypatch)
    cli = _load("purchase_teaching_cli", scripts / "run_audit.py", monkeypatch)
    fixture = _read(ROOT / "tests/fixtures/teaching_reviews/purchase_invoice.json")[
        "cases"
    ][f"{language}-{phase}"]
    calls = []

    def replay(prompt, schema, chunk, workflow, packet_sha, effort, **kwargs):
        packets = json.loads(prompt.partition("PACKETS_JSON:\n")[2])
        results = []
        for packet in packets:
            expected = fixture["results"][packet["invoice_number"]]
            stable = dict(packet)
            stable.pop("invoice_id")
            stable.pop("source_reference")
            assert stable == expected["packet"]
            results.append({**expected["response"], "invoice_id": packet["invoice_id"]})
        calls.append(packet_sha)
        return {
            "response_payload": {
                "schema_version": "vera.passive_invoice_luna.v1",
                "results": results,
            },
            "usage": {},
            "duration_ms": 0,
            "model": "gpt-5.6-luna",
            "reasoning_effort": effort,
        }

    monkeypatch.setattr(cli, "run_luna_chunk", replay)
    monkeypatch.setattr(cli, "configured_runtime", lambda: "codex-native")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_audit",
            "--invoices",
            str(context["input_dir"]),
            "--ledger",
            str(ledger),
            "--ledger-mapping",
            str(mapping),
            "--output",
            str(output / "audit"),
            "--client-engagement",
            str(run["context_path"]),
            "--reasoning-effort",
            "low",
        ],
    )
    assert cli.main() == 0
    audit = output / "audit"
    summary = _read(audit / "run_summary.json")
    assert summary["status"] == "completed"
    assert summary["population"] == count
    assert summary["matched"] == count
    assert summary["invoices_requiring_professional_attention"] == 1
    assert summary["luna_chunks_failed"] == 0
    assert summary["ledger_entry_without_invoice"] == 0
    rows = [
        json.loads(line)
        for line in (audit / "full_population.jsonl").read_text().splitlines()
    ]
    assert {
        r["invoice"]["invoice_number"]
        for r in rows
        if r["final_state"] == "professional_review_required"
    } == {"DEMO-003"}
    for row in rows:
        assert (
            row["invoice"]["source_sha256"]
            == fixture["results"][row["invoice"]["invoice_number"]]["source_sha256"]
        )
    workbook = load_workbook(audit / "exception_workpaper.xlsx", data_only=True)
    sheet = workbook["Exceptions"]
    assert sheet.max_row == 2
    assert sheet["D2"].value == "DEMO-003"
    assert "Carburante" in sheet["G2"].value
    assert sheet["L2"].value
    assert sheet["M2"].value and sheet["N2"].value and sheet["O2"].value
    assert sheet.auto_filter.ref == "A1:Q2"
    assert sheet.freeze_panes == "A2"
    assert sheet["A1"].fill.fgColor.rgb == "FF173F67"
    workbook.close()
    assert len(calls) == 1
    assert cli.main() == 0
    assert len(calls) == 1  # Completed semantic chunks are resumed, not rerun.
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="purchase-invoice-review",
        language=language,
        phase=phase,
    )
