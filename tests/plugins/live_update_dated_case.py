"""Packaged regression: saved dated case 1 reopens after reinstall and upgrade."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from openpyxl import load_workbook

archive = Path(sys.argv[1]).resolve()
base = Path(sys.argv[2]).resolve()
base.mkdir(parents=True, exist_ok=True)
os.environ.update(
    MPARANZA_RUNTIME_ROOT=str(base / "runtime"),
    MPARANZA_INCIDENT_STATE_DIR=str(base / "incidents"),
    MPARANZA_INCIDENT_DELIVERY="local-only",
    VERA_REPORTING_INTERNAL="1",
    PYTHONDONTWRITEBYTECODE="1",
    PYTHON=sys.executable,
)
sys.dont_write_bytecode = True
cache = base / "host-cache"
with ZipFile(archive) as z:
    z.extractall(cache)
installed = cache / "vera-codex-plugin/plugins/vera"
sys.path.insert(0, str(installed / "scripts"))
import verified_execution as verification

pinned = verification.prepare_execution_root(installed, None, shared=True)
sys.path.insert(0, str(pinned / "modules/studio-archive/scripts"))
import client_ledger as ledger

client = base / "Synthetic dated case 1"
client.mkdir()
client_id = "client_" + uuid4().hex[:24]
ledger.create_client_manifest(client, client_id)
engagement = ledger.create_engagement(
    client, client_id, "Live plugin update regression"
)
inputs = base / "inputs"
inputs.mkdir()
(inputs / "receivables.csv").write_text(
    "Invoice,Customer,Invoice_Date,Net,VAT,Total,Currency,Paid\nFT-2026-0101,Rossi Costruzioni Srl,2026-07-01,500.00,110.00,610.00,EUR,false\n"
)
(inputs / "bank.csv").write_text(
    "Movement_ID,Date,Amount,Counterparty,Description,Currency,Invoice_Reference\nTX-001,2026-07-10,610.00,Rossi Costruzioni Srl,Saldo FT-2026-0101,EUR,FT-2026-0101\n"
)
receipts = [
    ledger.import_document(
        client, client_id, engagement["engagement_id"], inputs / name, "source"
    )["receipt"]
    for name in ("receivables.csv", "bank.csv")
]
prepared = ledger.prepare_run(
    client,
    client_id,
    engagement["engagement_id"],
    "open-item-reconciliation",
    json.loads((installed / ".codex-plugin/plugin.json").read_text())["version"],
    input_ids=[r["input_id"] for r in receipts],
)
running = ledger.start_run(
    client, engagement["engagement_id"], prepared["run"]["run_id"]
)
context = running["context"]
run = Path(running["run_root"])
output = Path(context["output_dir"])
(output / "model_data_report_options.json").write_text('{"local_only":true}')
assumptions = {
    "scope_year": 2026,
    "cutoff_date": "2026-07-01",
    "post_cutoff_events_excluded": False,
    "report_language": "it",
    "document_language": "it",
    "currency": "EUR",
    "sample_kind": "agent_test",
    "human_confirmation": False,
    "professional_approval": False,
    "assurance_run_date": "2026-10-22",
    "reviewed_source_decisions": {},
}
for item in context["input_bindings"]:
    path = Path(item["path"])
    invoice = path.name == "receivables.csv"
    assumptions["reviewed_source_decisions"][
        path.relative_to(Path(context["input_dir"])).as_posix()
    ] = {
        "role": "open_items" if invoice else "bank_statement",
        "adapter_family": "reviewed_tabular_accounting_v1",
        "reviewer_ref": "codex_agent_test",
        "reviewed_on": "2026-10-22",
        "perimeter": {
            "entity_ref": "synthetic_case_001",
            "party_ref": None,
            "currency": "EUR",
            "unit": "EUR",
            "direction_policy": "customer",
            "allocation_policy": "one_to_one",
        },
        "money": {
            "decimal_separator": ".",
            "thousands_separator": None,
            "reported_unit": "EUR",
            "reported_increment": "0.01",
        },
        "date": {"order": "day_first"},
        "tabular": {
            "sheet": None,
            "header_row": 1,
            "first_data_row": 2,
            "last_data_row": 2,
            "delimiter": ",",
            "columns": (
                {
                    "document_no": "Invoice",
                    "document_date": "Invoice_Date",
                    "amount": "Total",
                    "currency": "Currency",
                    "party_ref": "Customer",
                }
                if invoice
                else {
                    "source_record_id": "Movement_ID",
                    "document_no": "Invoice_Reference",
                    "posting_date": "Date",
                    "amount": "Amount",
                    "party_ref": "Counterparty",
                    "description": "Description",
                    "currency": "Currency",
                }
            ),
            "evidence_type_map": {},
            "default_evidence_type": "open_item" if invoice else "external_bank",
        },
    }
assumptions_path = output / "assumptions.json"
assumptions_path.write_text(json.dumps(assumptions, indent=2))
bound = verification.bind_execution_run(run, pinned)
calculation = subprocess.run(
    [
        sys.executable,
        "-I",
        "-B",
        str(bound / "modules/open-item-reconciliation/scripts/raw_input_runner.py"),
        "--client-engagement",
        str(run / "context.json"),
        "--assumptions-json",
        str(assumptions_path),
        "--output-subdirectory",
        "reconciliation",
        "--language",
        "it",
        "--title",
        "Caso 001: fattura 1 luglio, incasso 10 luglio 2026",
    ],
    cwd=bound,
    capture_output=True,
    text=True,
    timeout=120,
)
(base / "calculation.json").write_text(
    json.dumps(
        {
            "returncode": calculation.returncode,
            "stdout": calculation.stdout,
            "stderr": calculation.stderr,
        },
        indent=2,
    )
)
assert calculation.returncode == 0, calculation.stderr
summary = json.loads(calculation.stdout)
assert summary["semantic_resolution"]["status"] == "not_required", summary
assert summary["semantic_resolution"]["batch_count"] == 0, summary
workbook = load_workbook(
    output / "reconciliation/riconciliazione_audit.xlsx", read_only=True, data_only=True
)
workbook_dates = {}
try:
    for sheet, expected in {
        "Righe normalizzate": {"F2": "2026-07-01", "N3": "2026-07-10"},
        "Dettaglio riconciliazione": {"E2": "2026-07-01", "AD2": "2026-07-10"},
    }.items():
        workbook_dates[sheet] = {
            cell: str(workbook[sheet][cell].value) for cell in expected
        }
        assert workbook_dates[sheet] == expected
finally:
    workbook.close()
(base / "workbook-dates.json").write_text(json.dumps(workbook_dates, indent=2))


class MCP:
    def __init__(self, root):
        configuration = json.loads((root / ".mcp.json").read_text())["mcpServers"][
            "vera"
        ]
        self.process = subprocess.Popen(
            [
                configuration["command"],
                str(root / configuration["args"][0]),
                *configuration["args"][1:],
            ],
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.queue = queue.Queue()
        self.errors = []
        self.counter = 0
        threading.Thread(
            target=lambda: [self.queue.put(line) for line in self.process.stdout],
            daemon=True,
        ).start()
        threading.Thread(
            target=lambda: [self.errors.append(line) for line in self.process.stderr],
            daemon=True,
        ).start()
        self.call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "dated-update-regression", "version": "1"},
            },
        )

    def call(self, method, params):
        self.counter += 1
        self.process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": self.counter,
                    "method": method,
                    "params": params,
                }
            )
            + "\n"
        )
        self.process.stdin.flush()
        try:
            reply = json.loads(self.queue.get(timeout=120))
        except queue.Empty:
            raise RuntimeError("MCP did not reply: " + "".join(self.errors))
        assert reply.get("id") == self.counter, reply
        assert "error" not in reply, reply
        assert not reply["result"].get("isError"), reply
        return reply["result"]

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=30)
        assert self.process.returncode == 0, "".join(self.errors)
        self.process.stdout.close()
        self.process.stderr.close()


reconciliation = output / "reconciliation"
request = {
    "client_engagement": str(run / "context.json"),
    **{
        name + "_path": str(reconciliation / (name + ".json"))
        for name in ("review_payload", "run_intake", "final_artifacts", "ui_decisions")
    },
}
connection = MCP(installed)
responses = {}
try:
    responses["before_update"] = connection.call(
        "tools/call",
        {"name": "validate_open_item_reconciliation_review", "arguments": request},
    )
    connection.close()
    connection = None
    backup = cache.with_name("plugin-backup")
    cache.rename(backup)
    shutil.rmtree(backup)
    with ZipFile(archive) as z:
        z.extractall(cache)
    connection = MCP(installed)
    responses["after_same_version_reinstall_reconnected"] = connection.call(
        "tools/call",
        {"name": "validate_open_item_reconciliation_review", "arguments": request},
    )
    connection.close()
    connection = None
    backup = cache.with_name("plugin-backup")
    cache.rename(backup)
    shutil.rmtree(backup)
    with ZipFile(archive) as z:
        z.extractall(cache)
    metadata = installed / ".codex-plugin/plugin.json"
    value = json.loads(metadata.read_text())
    value["version"] = "0.1.481-fixture"
    metadata.write_text(json.dumps(value))
    index = {
        path.relative_to(installed)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in installed.rglob("*")
        if path.is_file() and path.name != "execution-files.json"
    }
    (installed / "execution-files.json").write_text(
        json.dumps({"schema_version": 1, "files": index})
    )
    connection = MCP(installed)
    responses["after_upgrade_reconnected_review"] = connection.call(
        "tools/call",
        {"name": "validate_open_item_reconciliation_review", "arguments": request},
    )
    assert all(reply["structuredContent"]["ok"] is True for reply in responses.values())
    assert verification.execution_package_id(
        pinned
    ) != verification.execution_package_id(installed)
    assert json.loads((run / "execution-runtime.json").read_text())[
        "package_sha256"
    ] == verification.execution_package_id(pinned)
    (base / "reviews.json").write_text(json.dumps(responses, indent=2))
    (base / "summary.json").write_text(
        json.dumps(
            {
                "package_a": verification.execution_package_id(pinned),
                "package_b": verification.execution_package_id(installed),
                "run_package": json.loads((run / "execution-runtime.json").read_text())[
                    "package_sha256"
                ],
                "calculation": summary,
                "review_stages": list(responses),
                "invoice_date": "2026-07-01",
                "bank_date": "2026-07-10",
                "run_root": str(run),
                "limits": [
                    "Isolated packaged-process regression, not an installed Codex chat or professional approval.",
                    "Upgrade B is a version-labelled package fixture made from candidate A.",
                    "Services are reopened after updates; live installation replacement is not protected.",
                ],
            },
            indent=2,
        )
    )
    print(
        json.dumps(
            {
                "passed": True,
                "run_root": str(run),
                "summary": str(base / "summary.json"),
            }
        )
    )
finally:
    if connection:
        connection.close()
    verification.release_execution_root(bound)
    verification.release_execution_root(pinned)
