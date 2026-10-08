"""Run the acquisition engine against explicit fictional course inputs, without a browser."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from ade_acquisition.contracts import AcquisitionError, Client, Plan, canonical_hash
from ade_acquisition.engine import Acquisition
from ade_acquisition.reports import write_reports
from ade_acquisition.storage import Store, atomic_json, read_json

__all__ = ["run_demo", "main"]


class _TeachingPortal:
    """A bounded source fixture; deliberately contains no portal or network client."""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self.fixture = fixture
        self.client: Client | None = None

    def select_client(self, plan: Plan, client: Client) -> None:
        self.client = client

    def search_invoices(
        self, client: Client, operation: str, start: Any, end: Any
    ) -> int:
        return len(self.fixture["invoice_numbers"])

    def invoice_rows(self) -> list[dict[str, str]]:
        return [
            {"key": canonical_hash(number), "number": number}
            for number in self.fixture["invoice_numbers"]
        ]

    def download_invoice(self, row: dict[str, str]) -> tuple[str, bytes]:
        if row["number"] in self.fixture["unavailable_originals"]:
            raise AcquisitionError("original-unavailable-in-teaching-fixture")
        if self.client is None:
            raise AcquisitionError("teaching-client-not-selected")
        number, vat = escape(row["number"]), escape(self.client.vat_number)
        xml = f"""<FatturaElettronica><FatturaElettronicaHeader><CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdCodice>09876543210</IdCodice></IdFiscaleIVA></DatiAnagrafici></CedentePrestatore><CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdCodice>{vat}</IdCodice></IdFiscaleIVA></DatiAnagrafici></CessionarioCommittente></FatturaElettronicaHeader><FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Data>2026-01-02</Data><Numero>{number}</Numero></DatiGeneraliDocumento></DatiGenerali></FatturaElettronicaBody></FatturaElettronica>"""
        return f"{row['number']}.xml", xml.encode()

    def restore_invoices(self, *args: Any) -> None:
        """The bounded fixture always retains its two-row source list."""

    def cash_devices(self, *args: Any) -> list[dict[str, Any]]:
        return [
            {
                "name": "Registratore telematico didattico",
                "count": len(self.fixture["cash_rows"]),
            }
        ]

    def cash_rows(self, *args: Any) -> list[dict[str, str]]:
        return self.fixture["cash_rows"]

    def stamp_duty(self, *args: Any) -> dict[str, Any]:
        return {
            "status": "acquired",
            "amount": self.fixture["stamp_amount"],
            "list_a_count": 12,
            "list_b_count": 0,
            "document_count": 12,
            "attestations": "Dati interamente fittizi",
            "payment_status": self.fixture["payment_status"],
            "row_evidence": ["FONTE DIDATTICA LOCALE"],
        }


def run_demo(fixture_path: Path, output: Path) -> dict[str, Any]:
    """Generate actual acquisition outputs while labelling the source as fictional."""
    fixture = read_json(fixture_path)
    if (
        fixture.get("schema_version") != "vera-agenzia-teaching/v1"
        or fixture.get("synthetic") is not True
    ):
        raise AcquisitionError("explicit-teaching-fixture-required")
    plan = Plan.parse(fixture["plan"])
    if (
        len(plan.clients) != 1
        or plan.clients[0].vat_number != "01234567890"
        or plan.operations != ("ricevute", "corrispettivi", "bolli")
        or plan.date_from.isoformat() != "2026-01-01"
        or plan.date_to.isoformat() != "2026-03-31"
        or fixture["invoice_numbers"] != ["DEMO-001", "DEMO-002"]
    ):
        raise AcquisitionError("teaching-fixture-scope-invalid")
    store = Store(output)
    with store.lock():
        run = store.new_run(plan.payload())
        state = Acquisition(store, run, plan, _TeachingPortal(fixture)).execute()
        state["execution_mode"] = "synthetic_local_source_no_portal"
        state.update(write_reports(run, plan, state))
        atomic_json(run / "status.json", state)
        atomic_json(
            run / "teaching-source.json",
            {
                "fixture_sha256": canonical_hash(fixture),
                "phase": fixture["phase"],
                "synthetic": True,
            },
        )
    return {
        "state": state["state"],
        "run_id": run.name,
        "run_directory": str(run),
        "downloaded": state["downloaded"],
        "verified_existing": state["verified_existing"],
        "failed_documents": state["failed_documents"],
        "execution_mode": state["execution_mode"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run_demo(args.fixture, args.output)
    except (AcquisitionError, OSError, KeyError, TypeError, ValueError) as exc:
        code = (
            exc.code if isinstance(exc, AcquisitionError) else "teaching-input-invalid"
        )
        sys.stdout.write(json.dumps({"state": "failed", "error": code}) + "\n")
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
