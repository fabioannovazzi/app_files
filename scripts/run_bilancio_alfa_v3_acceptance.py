#!/usr/bin/env python3
"""Exercise Alfa v3 through Vera's persistent, authenticated case service.

The entirely synthetic P1/C1 decisions are test inputs, not real professional
approvals. Expected results are an independent oracle and never drive product
state. This does not test an enabled conversation, UI, filing, or real clients.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import os
import subprocess  # nosec B404
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

__all__ = ["AlfaAcceptance", "main"]

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
COLUMN_MAPPING = {
    "dare_2025": "closing_debit",
    "avere_2025": "closing_credit",
    "dare_2024": "prior_closing_debit",
    "avere_2024": "prior_closing_credit",
}
AREA_NAMES = [
    "Immobilizzazioni materiali",
    "Crediti e ricavi",
    "Cassa e banche",
    "Debiti e finanziamenti",
    "Personale e TFR",
    "Imposte",
    "Ratei e risconti",
    "Patrimonio netto",
    "Fondi per rischi e oneri",
    "Altre componenti economiche",
    "Rimanenze",
    "Rendiconto finanziario",
    "Cambiamenti, errori e fatti successivi",
    "Immobilizzazioni immateriali",
    "Partecipazioni e gruppo",
    "Leasing",
    "Patrimoni e finanziamenti destinati",
    "Fusioni e scissioni",
    "Quote di emissione",
    "Titoli di debito",
    "Lavori in corso su ordinazione",
    "Operazioni in valuta estera",
    "Bilanci intermedi",
    "Strumenti finanziari derivati",
    "Passaggio ai principi contabili nazionali",
]
AREA_IDS = {name: f"area_{i:02d}" for i, name in enumerate(AREA_NAMES, 1)}
SCOPES = [
    "area:area_07",
    "area:area_04",
    "area:area_13",
    "mapping:4210",
    "mapping:2410",
    "validation",
]


class McpAcceptanceService:
    """Send the same scenario through the packaged stdio server and bridge."""

    def __init__(self, plugin: Path, fixtures: Path, output: Path) -> None:
        self.plugin, self.fixtures, self.output = plugin, fixtures, output
        self.scanner = output / "synthetic_fixture_checksum_scanner.py"
        manifest = {
            str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (fixtures / "dati").iterdir()
            if p.is_file()
        }
        self.scanner.write_text(
            "from pathlib import Path\nimport hashlib, json, sys\n"
            + "known = json.loads("
            + repr(json.dumps(manifest))
            + ")\n"
            + "p = Path(sys.argv[1]).resolve()\n"
            + "if str(p) not in known: raise SystemExit(1)\n"
            + "raise SystemExit(0 if known.get(str(p)) == hashlib.sha256(p.read_bytes()).hexdigest() else 1)\n",
            encoding="utf-8",
        )

    def call(
        self, context: Any, tool: str, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        environment = dict(os.environ)
        environment.update(
            {
                "VERA_XBRL_STORAGE_ROOT": str(self.output / "cases"),
                "VERA_XBRL_INPUT_ROOT": str(self.fixtures),
                "VERA_XBRL_TENANT_ID": context.tenant_id,
                "VERA_XBRL_ACTOR_ID": context.actor_id,
                "VERA_XBRL_ROLES": ",".join(context.roles),
                "VERA_XBRL_PYTHON": sys.executable,
                "VERA_XBRL_NATIVE_UI": "0",
                "VERA_XBRL_UI_ONLY": "0",
                "VERA_XBRL_STATUTORY_RULE_PACK": str(
                    self.plugin / "rulepacks/it/statutory-forms-2026.1.json"
                ),
                "VERA_XBRL_DISCLOSURE_RULE_PACK": str(
                    self.plugin / "rulepacks/it/disclosures-2026.1.json"
                ),
                "VERA_XBRL_SCANNER_COMMAND_JSON": json.dumps(
                    [sys.executable, str(self.scanner)]
                ),
                "VERA_XBRL_SCANNER_ENGINE": "synthetic-fixture-checksum-only",
                "VERA_XBRL_SCANNER_SIGNATURE_VERSION": "not-a-production-malware-verdict",
            }
        )
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
        initialization = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        }
        # Fixed local MCP entrypoint and a separately passed JSON request; no shell.
        result = subprocess.run(  # nosec B603,B607
            ["node", str(self.plugin / "mcp/server.cjs")],
            input=json.dumps(initialization) + "\n" + json.dumps(request) + "\n",
            text=True,
            capture_output=True,
            env=environment,
            timeout=120,
            check=True,
        )
        response = json.loads(result.stdout.splitlines()[-1])
        if response.get("error"):
            raise ValueError(response["error"]["message"])
        return response["result"]["structuredContent"]

    def create(
        self,
        context: Any,
        payload: Mapping[str, Any],
        rule_pack: Mapping[str, Any],
        key: str,
    ) -> dict[str, Any]:
        return self.call(
            context, "xbrl_case_create", {"payload": payload, "idempotency_key": key}
        )

    def mutate(
        self,
        context: Any,
        case_id: str,
        operation: str,
        payload: Mapping[str, Any],
        revision: str,
        key: str,
    ) -> dict[str, Any]:
        common = {"case_id": case_id, "revision_id": revision, "idempotency_key": key}
        if operation == "ingest":
            return self.call(
                context,
                "xbrl_document_ingest",
                {**common, "document_kind": "TRIAL_BALANCE", **payload},
            )
        if operation == "validate":
            return self.call(context, "xbrl_case_validate", common)
        trusted_payload = {k: v for k, v in payload.items() if k != "rule_pack"}
        return self.call(
            context,
            "xbrl_case_analyze",
            {**common, "operation": operation, "payload": trusted_payload},
        )


class AlfaAcceptance:
    """Execute reviewed synthetic decisions and retain point-by-point evidence."""

    def __init__(
        self, plugin: Path, fixtures: Path, output: Path, transport: str = "service"
    ) -> None:
        if output.exists():
            raise ValueError("Acceptance output must be a new directory")
        if str(plugin / "scripts") not in sys.path:
            sys.path.insert(0, str(plugin / "scripts"))
        from access_control import RequestContext
        from case_service import CaseService
        from closing_workflow import closing_status
        from xbrl_case import load_case

        self.plugin, self.fixtures, self.output = plugin, fixtures, output
        output.mkdir(parents=True)
        self.oracle = json.loads((fixtures / "risultati_attesi.json").read_bytes())
        self.status_function, self.load_case = closing_status, load_case
        self.transport = transport
        self.service: Any = (
            McpAcceptanceService(plugin, fixtures, output)
            if transport == "mcp"
            else CaseService(output / "cases", input_root=fixtures)
        )
        self.preparer = RequestContext(
            "alfa_synthetic", "C1", ("PREPARER",), "alfa-v3-acceptance"
        )
        self.reviewer = RequestContext(
            "alfa_synthetic", "P1", ("REVIEWER",), "alfa-v3-acceptance"
        )
        self.documents: dict[str, str] = {}
        self.counter = 0
        self.trace: list[dict[str, Any]] = []
        self.checks: list[dict[str, Any]] = []
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.rule_pack = json.loads(
            (plugin / "rulepacks/it/statutory-forms-2026.1.json").read_bytes()
        )

    def case(self) -> dict[str, Any]:
        return self.load_case(self.output / "cases/alfa_synthetic/alfa_2025")

    def status(self) -> dict[str, Any]:
        return self.status_function(self.case())

    def mutate(
        self, operation: str, payload: Mapping[str, Any], *, reviewer: bool = False
    ) -> dict[str, Any]:
        self.counter += 1
        context = self.reviewer if reviewer else self.preparer
        result = self.service.mutate(
            context,
            "alfa_2025",
            operation,
            payload,
            self.case()["revision_id"],
            f"alfa_{self.counter:04d}",
        )
        self.trace.append(
            {
                "step": self.counter,
                "operation": operation,
                "actor": context.actor_id,
                "result": result,
            }
        )
        return result

    def attach(self, number: str) -> str:
        path = next((self.fixtures / "dati").glob(number + "_*"))
        if number == "01":
            self.mutate(
                "ingest",
                {
                    "source_path": str(path),
                    "column_mapping": COLUMN_MAPPING,
                    "blank_balance_cells_are_zero": True,
                },
            )
        else:
            self.mutate(
                "attach_supporting_document",
                {
                    "source_path": str(path),
                    "purpose": "SUPPORTING_EVIDENCE",
                    "description": path.stem,
                },
            )
        document_id = self.case()["source_documents"][-1]["document_id"]
        self.documents[number] = document_id
        return document_id

    def replacement(self, number: str) -> None:
        path = next((self.fixtures / "dati").glob(number + "_*"))
        self.mutate(
            "ingest_closing_trial_balance",
            {
                "source_path": str(path),
                "version_id": "doc" + number,
                "column_mapping": COLUMN_MAPPING,
                "blank_balance_cells_are_zero": True,
            },
        )
        self.documents[number] = self.case()["source_documents"][-1]["document_id"]

    def decision(
        self,
        record: str,
        kind: str,
        decision: Mapping[str, Any],
        evidence: list[str],
        reason: str,
        date: str,
    ) -> None:
        if kind == "AREAS":
            before = self.status()["areas"]
            self.mutate(
                "propose_closing_review",
                {
                    "proposal_id": "proposal-" + record,
                    "kind": "AREAS",
                    "content": decision,
                    "evidence_refs": [self.documents[n] for n in evidence],
                    "reason": reason,
                },
            )
            self.check(
                "areas.proposal_has_no_authority." + record,
                before,
                self.status()["areas"],
            )
            decision = {**decision, "proposal_id": "proposal-" + record}
        self.mutate(
            "record_closing_decision",
            {
                "record_id": record,
                "kind": kind,
                "decision": decision,
                "evidence_refs": [self.documents[n] for n in evidence],
                "reason": reason,
                "effective_date": date,
            },
            reviewer=True,
        )

    def check(
        self, name: str, expected: Any, observed: Any, *oracle_paths: str
    ) -> None:
        self.checks.append(
            {
                "id": name,
                "expected": expected,
                "observed": observed,
                "conformant": expected == observed,
                "oracle_paths": list(oracle_paths),
            }
        )

    def checkpoint(self, name: str) -> None:
        case = self.case()
        self.snapshots[name] = deepcopy(case)
        (self.output / (name + ".json")).write_text(
            json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def rejected(
        self,
        name: str,
        operation: str,
        payload: Mapping[str, Any],
        *,
        reviewer: bool = False,
        contains: str = "",
    ) -> None:
        before = self.case()
        try:
            self.mutate(operation, payload, reviewer=reviewer)
        except (ValueError, PermissionError) as error:
            observed = not contains or contains in str(error)
            self.trace.append(
                {
                    "operation": operation,
                    "expected_rejection": name,
                    "error": str(error),
                }
            )
        else:
            observed = False
        self.check(name, True, observed)
        digest = lambda value: hashlib.sha256(
            json.dumps(value, sort_keys=True).encode()
        ).hexdigest()
        self.check(name + ".atomic", digest(before), digest(self.case()))

    def screening(
        self, record: str, version: str, included: bool, evidence: list[str], date: str
    ) -> None:
        self.decision(
            record,
            "SCREENING",
            {
                "version_id": version,
                "convention": "SIGNED_BALANCE_ONLY",
                "closing_entries_included": included,
                "checks": dict.fromkeys(
                    ["period", "comparative", "debit_credit", "closing_entries"], True
                ),
            },
            evidence,
            "Controlli rivisti e riconciliazione esatta delle scritture approvate.",
            date,
        )

    def propose(
        self,
        proposal: str,
        subject: str,
        debit: str,
        credit: str,
        amount: str,
        evidence: list[str],
    ) -> None:
        self.mutate(
            "propose_closing_adjustment",
            {
                "proposal_id": proposal,
                "subject_key": subject,
                "lines": [
                    {"account_code": debit, "debit": amount, "credit": "0"},
                    {"account_code": credit, "debit": "0", "credit": amount},
                ],
                "evidence_refs": [self.documents[n] for n in evidence],
                "reason": "Rettifica proposta sulla base delle fonti sintetiche selezionate.",
            },
        )

    def run(self) -> dict[str, Any]:
        payload = {
            "case_id": "alfa_2025",
            "entity": {
                "legal_name": "Alfa Servizi S.r.l. (SINTETICA)",
                "tax_identifier": "SYNTHETIC-ALFA",
                "registered_office": "Sede fittizia, Italia",
                "legal_form": "SRL",
                "accounting_framework": "OIC",
                "listed": False,
                "regulated_sector": False,
                "consolidated": False,
                "final_liquidation": False,
                "first_financial_year": False,
                "prior_year_form": "ABBREVIATED",
                "prior_period_start": "2024-01-01",
                "prior_period_end": "2024-12-31",
                "micro_exclusion_flags": [],
            },
            "period": {"start": "2025-01-01", "end": "2025-12-31"},
            "oic_rule_pack": "OIC_2024_2025.1",
            "filing_campaign_year": 2026,
            "taxonomy_checksum": "a" * 64,
        }
        self.service.create(self.reviewer, payload, self.rule_pack, "alfa_create")
        self.mutate(
            "start_closing_workflow",
            {
                "accounting_origin": "CONTABILITA_ESTERNA",
                "effective_date": "2026-01-08",
            },
            reviewer=True,
        )
        for number in ["01", "02", "03", "04", "05"]:
            self.attach(number)
        self.check(
            "origin.explicit",
            self.oracle["origine_contabilita"],
            self.status()["accounting_origin"],
            "/origine_contabilita",
            "/origine_contabilita_indicata",
        )
        self.check(
            "origin.effective_date",
            self.oracle["origine_contabilita_indicata"]["data"],
            self.case()["closing_workflow"]["opening"]["effective_date"],
        )
        initial = [
            (
                "R1",
                "Bilancio corrente e comparativo",
                "AVAILABLE_SUFFICIENT",
                ["01"],
                False,
            ),
            ("R2", "Registro cespiti", "AVAILABLE_SUFFICIENT", ["02"], False),
            ("R3", "Contratto di finanziamento", "AVAILABLE_SUFFICIENT", ["03"], False),
            (
                "R4",
                "Estratto conto di dicembre al 31/12",
                "AVAILABLE_STALE",
                ["04"],
                True,
            ),
            ("R5", "Prospetto TFR al 31/12", "MISSING", [], True),
            ("R6", "Inventario di magazzino", "NOT_APPLICABLE", ["01"], False),
            ("R7", "Contenziosi e rischi", "REVIEW_REQUIRED", ["05"], False),
        ]
        requirements = [
            {
                "requirement_id": rid,
                "description": description,
                "status": state,
                "evidence_refs": [self.documents[n] for n in refs],
                "request_from_client": request,
                "reason": "Valutazione professionale delle fonti e dei requisiti del caso sintetico.",
            }
            for rid, description, state, refs, request in initial
        ]
        self.decision(
            "D-FASC1",
            "FASCICOLO",
            {"requirements": requirements, "sufficient_to_start": False},
            ["01", "04"],
            "Estratto conto fermo al 30/11; TFR assente; nessun magazzino nel caso di servizi.",
            "2026-01-09",
        )
        status = self.status()
        self.check(
            "fascicolo.requirements",
            self.oracle["fascicolo_iniziale"]["requisiti"],
            {r["requirement_id"]: r["status"] for r in status["requirements"]},
            "/fascicolo_iniziale/requisiti",
        )
        self.check(
            "fascicolo.insufficient",
            False,
            status["fascicolo_sufficient"],
            "/fascicolo_iniziale/esito",
        )
        self.check(
            "request.two_items",
            self.oracle["fascicolo_iniziale"]["voci_in_bozza"],
            [r["requirement_id"] for r in status["request_draft"]["items"]],
            "/fascicolo_iniziale/voci_in_bozza",
        )
        self.check(
            "request.single_draft",
            "DRAFT",
            status["request_draft"]["status"],
            "/fascicolo_iniziale/bozze_richiesta_cliente",
        )
        self.check(
            "request.no_R7",
            False,
            any(r["requirement_id"] == "R7" for r in status["request_draft"]["items"]),
            "/fascicolo_iniziale/R7_in_bozza",
        )
        self.check(
            "request.never_sent",
            False,
            status["request_draft"]["sent"],
            "/fascicolo_iniziale/invio_automatico",
            "/fascicolo_iniziale/invio",
        )
        self.rejected(
            "form.blocked_before_fascicolo",
            "determine_forms",
            {"metrics": [], "rule_pack": self.rule_pack},
            contains="Closing fascicolo",
        )
        self.checkpoint("01_fascicolo_initial")
        self.attach("06")
        self.attach("07")
        self.decision(
            "D-R7",
            "ISSUE",
            {
                "issue_id": "vertenza",
                "requirement_id": "R7",
                "area_id": AREA_IDS["Fondi per rischi e oneri"],
                "description": "Valutazione della vertenza: accantonamento ancora da decidere",
                "status": "ROUTED",
            },
            ["05"],
            "La vertenza da 8.000 euro va valutata nei fondi, senza decidere automaticamente un accantonamento.",
            "2026-01-12",
        )
        updates = [
            {
                "requirement_id": rid,
                "description": desc,
                "status": "AVAILABLE_SUFFICIENT",
                "evidence_refs": [self.documents[num]],
                "request_from_client": False,
                "reason": "Fonte aggiornata e saldo raccordato al conto selezionato.",
            }
            for rid, desc, num in [
                ("R4", "Saldo banca al 31/12", "06"),
                ("R5", "Fondo TFR al 31/12", "07"),
            ]
        ]
        self.decision(
            "D-FASC2",
            "FASCICOLO",
            {"requirements": updates, "sufficient_to_start": True},
            ["06", "07"],
            "Saldo banca e fondo TFR raccordati; R7 instradata con D-R7.",
            "2026-01-12",
        )
        self.check(
            "fascicolo.sufficient",
            True,
            self.status()["fascicolo_sufficient"],
            "/fascicolo_dopo_integrazione",
        )
        self.check(
            "screening.not_skipped",
            False,
            self.status()["form_and_mapping_allowed"],
            "/fascicolo_dopo_integrazione/forma_e_mapping",
        )
        self.screening("D-SCR1", "baseline", False, ["01", "02", "03"], "2026-01-13")
        self.check(
            "screening.explicit_closing",
            False,
            self.case()["trial_balance"]["closing_entries_review"]["appears_included"],
            "/screening_doc01/chiusure_incluse",
        )
        self.money_checks("01", "screening_doc01")
        self.propose("A1", "ammortamento2025", "4140", "1015", "12000", ["02"])
        self.propose("A2", "rateo2025", "4210", "2410", "1000", ["03"])
        self.check("adjustments.only_proposed", {}, self.status()["active_adjustments"])
        for proposal, source in [("A1", "02"), ("A2", "03")]:
            self.decision(
                "D-" + proposal,
                "ADJUSTMENT",
                {"proposal_id": proposal, "outcome": "APPROVED"},
                [source],
                "Scrittura di chiusura rivista dal professionista.",
                "2026-01-15",
            )
        self.check(
            "adjustments.two_active",
            ["D-A1", "D-A2"],
            list(self.status()["active_adjustments"]),
            "/rettifiche",
        )
        self.check(
            "adjustments.original_not_posted",
            self.snapshots["01_fascicolo_initial"]["trial_balance"]["entries"],
            self.case()["trial_balance"]["entries"],
        )
        self.replacement("13")
        self.check_mismatch(
            "13",
            self.oracle["prove_errore"]["E1"]["differenze_non_autorizzate"],
            "/prove_errore/E1",
        )
        self.failed_screening("E1", "doc13", "D-SCR2-E1")
        self.check(
            "E1.form_mapping_blocked",
            False,
            self.status()["form_and_mapping_allowed"],
            "/prove_errore/E1/atteso",
        )
        self.checkpoint("02_E1_rejected")
        self.replacement("10")
        self.screening("D-SCR2", "doc10", True, ["01", "10"], "2026-01-16")
        self.check(
            "doc10.form_mapping_open",
            True,
            self.status()["form_and_mapping_allowed"],
            "/doc10/si_aprono",
        )
        self.money_checks("10", "doc10")
        self.check(
            "register.phase5",
            7,
            self.status()["register_count"],
            "/registro_decisioni_dopo_fase5",
        )
        self.checkpoint("03_doc10_screened")
        self.mutate(
            "determine_forms",
            {
                "metrics": [
                    {
                        "year": 2025,
                        "assets": "279400",
                        "revenue": "560000",
                        "employees": "6",
                    },
                    {
                        "year": 2024,
                        "assets": "227200",
                        "revenue": "500000",
                        "employees": "6",
                    },
                ],
                "rule_pack": self.rule_pack,
            },
        )
        self.check(
            "form.micro_not_eligible",
            False,
            "MICRO" in self.case()["form_analysis"]["eligible_forms"],
            "/forma/micro_ammissibile",
        )
        self.check(
            "form.abbreviated_eligible",
            True,
            "ABBREVIATED" in self.case()["form_analysis"]["eligible_forms"],
            "/forma/abbreviato_ammissibile",
        )
        self.decision(
            "D-FORMA",
            "FORM",
            {"form": "ABBREVIATED"},
            ["10"],
            "Abbreviato ammissibile; micro non ammissibile sui due esercizi.",
            "2026-01-16",
        )
        self.check(
            "form.explicit_choice",
            "ABBREVIATED",
            self.case()["selected_form"],
            "/forma/scelta",
            "/forma/decisione",
        )
        areas = [
            {
                "area_id": AREA_IDS[name],
                "label": name,
                "status": "ACTIVE" if i < 10 else "EXCLUDED",
                "reason": (
                    "Segnali presenti nei conti e documenti rivisti."
                    if i < 10
                    else (
                        "Abbreviato: rendiconto non obbligatorio."
                        if name == "Rendiconto finanziario"
                        else "Nessuna fattispecie emersa nelle fonti riviste; l'assenza di segnali da sola non prova l'assenza."
                    )
                ),
            }
            for i, name in enumerate(AREA_NAMES)
        ]
        self.decision(
            "D-ESCL",
            "AREAS",
            {
                "areas": areas,
                "open_issues": [
                    {
                        "issue_id": "imposte2025",
                        "area_id": AREA_IDS["Imposte"],
                        "description": "Imposte 2025 ancora da determinare",
                        "status": "OPEN",
                    }
                ],
            },
            ["01", "02", "03", "04", "05", "06", "07"],
            "Applicabilità rivista e confermata dal professionista, comprese le quindici esclusioni.",
            "2026-01-16",
        )
        self.check(
            "areas.active",
            self.oracle["aree"]["attive"],
            [a["label"] for a in self.status()["areas"] if a["status"] == "ACTIVE"],
            "/aree/attive",
        )
        self.check(
            "areas.confirmed_exclusions",
            15,
            sum(a["status"] == "EXCLUDED" for a in self.status()["areas"]),
            "/aree/esclusioni",
            "/aree/escluse_con_motivo_specifico",
            "/aree/escluse_senza_segnali",
        )
        self.check(
            "areas.total",
            self.oracle["aree"]["totale"],
            len(self.status()["areas"]),
            "/aree/totale",
        )
        self.check(
            "doc10.not_complete",
            False,
            self.status()["closure_allowed"],
            "/doc10/non_attesta_completamento",
            "/doc10/questioni_aperte",
            "/fondi_rischi",
        )
        self.check(
            "register.phase7",
            9,
            self.status()["register_count"],
            "/registro_decisioni_dopo_fase7",
        )
        self.checkpoint("04_areas_reviewed")
        self.attach("11")
        self.check(
            "new_evidence.unreviewed_block",
            False,
            self.status()["form_and_mapping_allowed"],
        )
        self.mutate(
            "open_closing_reconsideration",
            {
                "record_id": "R-A2",
                "reason": "Nuova comunicazione della banca: tasso al 4,5% dal 01/10/2025; riesame del rateo e dell'area esclusa.",
                "evidence_refs": [self.documents["11"]],
                "effective_date": "2026-01-20",
                "decision": {
                    "decision_ids": ["D-A2"],
                    "area_ids": [AREA_IDS["Cambiamenti, errori e fatti successivi"]],
                    "scopes": SCOPES,
                },
            },
        )
        self.suspension_checks("between_20_22", before_replacement=True)
        self.checkpoint("05_suspended_20_22")
        self.decision(
            "D-FS",
            "AREAS",
            {
                "areas": [
                    {
                        "area_id": AREA_IDS["Cambiamenti, errori e fatti successivi"],
                        "label": "Cambiamenti, errori e fatti successivi",
                        "status": "ACTIVE",
                        "reason": "Documento 11 riguarda una condizione già esistente al 31/12/2025.",
                    }
                ]
            },
            ["11"],
            "Qualificazione professionale del documento 11 e attivazione dell'area.",
            "2026-01-22",
        )
        self.propose("A2-bis", "rateo2025", "4210", "2410", "1125", ["03", "11"])
        self.rejected(
            "A2bis.requires_explicit_replacement",
            "record_closing_decision",
            {
                "record_id": "invalid-A2bis",
                "kind": "ADJUSTMENT",
                "reason": "Prova di duplicazione vietata.",
                "evidence_refs": [self.documents["11"]],
                "decision": {"proposal_id": "A2-bis", "outcome": "APPROVED"},
            },
            reviewer=True,
            contains="supersede",
        )
        self.decision(
            "D-A2-bis",
            "ADJUSTMENT",
            {
                "proposal_id": "A2-bis",
                "outcome": "APPROVED",
                "supersedes": "D-A2",
                "resolves_reconsiderations": ["R-A2"],
            },
            ["03", "11"],
            "Rateo ricalcolato al 4,50%; sostituisce integralmente A2.",
            "2026-01-22",
        )
        self.suspension_checks("after_A2bis_before_doc12", before_replacement=False)
        self.check(
            "register.complete_22",
            12,
            self.status()["register_count"],
            "/modifica_doc11/registro_decisioni",
        )
        self.checkpoint("06_suspended_after_A2bis")
        self.replacement("14")
        self.check_mismatch(
            "14",
            self.oracle["prove_errore"]["E2"]["differenza_pari_ad_A2"],
            "/prove_errore/E2",
        )
        self.failed_screening("E2", "doc14", "D-SCR3")
        self.suspension_checks("E2_still_suspended", before_replacement=False)
        self.check(
            "E2.no_DSCR3",
            False,
            "D-SCR3" in self.status()["decision_states"],
            "/prove_errore/E2/atteso",
        )
        self.checkpoint("07_E2_rejected")
        self.replacement("12")
        self.check(
            "doc12.intake_alone_not_enough",
            False,
            self.status()["form_and_mapping_allowed"],
        )
        self.screening("D-SCR3", "doc12", True, ["01", "12"], "2026-01-23")
        self.money_checks("12", "modifica_doc11/doc12")
        self.check(
            "doc12.resumes_only_after_review",
            True,
            self.status()["form_and_mapping_allowed"],
            "/modifica_doc11/stato_dopo_A2bis_prima_del_doc12/condizioni_per_riprendere_le_validazioni",
        )
        self.check(
            "doc12.controls_must_repeat",
            dict.fromkeys(SCOPES, "REVIEW_REQUIRED"),
            self.status()["dependencies"],
            "/modifica_doc11/si_riaprono",
            "/modifica_doc11/stato_dopo_A2bis_prima_del_doc12/condizioni_per_chiudere_le_validazioni",
        )
        self.check(
            "doc12.A1_still_valid",
            "VALID",
            self.status()["decision_states"]["D-A1"],
            "/modifica_doc11/A1",
        )
        unchanged = ["D-FASC1", "D-R7", "D-FASC2", "D-SCR1", "D-FORMA"]
        self.check(
            "doc12.unaffected_decisions_valid",
            dict.fromkeys(unchanged, "VALID"),
            {r: self.status()["decision_states"][r] for r in unchanged},
            "/modifica_doc11/non_si_riaprono",
        )
        self.check("doc12.form_retained", "ABBREVIATED", self.case()["selected_form"])
        self.check(
            "doc12.taxes_and_litigation_open",
            ["imposte2025", "vertenza"],
            sorted(i["issue_id"] for i in self.status()["open_issues"]),
            "/modifica_doc11/questioni_aperte_dopo_doc12",
        )
        self.check(
            "doc12.no_complete_accounts", False, self.status()["closure_allowed"]
        )
        self.check(
            "register.complete_23",
            13,
            self.status()["register_count"],
            "/modifica_doc11/registro_dopo_doc12",
        )
        for label, snapshot in self.snapshots.items():
            previous = snapshot["closing_workflow"]["events"]
            self.check(
                "register.preserved." + label,
                previous,
                self.case()["closing_workflow"]["events"][: len(previous)],
            )
        self.checkpoint("08_doc12_screened_controls_pending")
        self.mutate("validate", {})
        validation = self.case()["validation"]
        self.check(
            "validation.closing_blockers",
            True,
            any(
                i["rule_id"].startswith("CLOSING.") and i["severity"] == "BLOCKER"
                for i in validation["issues"]
            ),
        )
        self.check("validation.cannot_pass", "FAIL", validation["status"])
        self.checkpoint("09_validation_still_blocked")
        self.finish_boundary_checks()
        return self.report()

    def money_checks(self, number: str, oracle_key: str) -> None:
        oracle = self.oracle
        for key in oracle_key.split("/"):
            oracle = oracle[key]
        table = self.case()["trial_balance"]
        totals = table["calibration"]
        expected = oracle["quadratura_2025"] if number == "01" else oracle["totale"]
        self.check(
            "doc" + number + ".debit_total",
            expected,
            int(Decimal(totals["closing_debit_total"])),
            "/" + oracle_key,
        )
        self.check(
            "doc" + number + ".credit_total",
            expected,
            int(Decimal(totals["closing_credit_total"])),
        )
        self.check(
            "doc" + number + ".comparative_unchanged",
            727200,
            int(sum(Decimal(r["prior_closing_debit"]) for r in table["entries"])),
        )
        if number != "01":
            # The fixture's account-role selection is explicit test input, not
            # a classifier for arbitrary charts of accounts.
            income_codes = {
                "3010",
                "4010",
                "4020",
                "4110",
                "4120",
                "4130",
                "4140",
                "4210",
                "4310",
                "4910",
            }
            pretax = -sum(
                Decimal(r["closing_signed"])
                for r in table["entries"]
                if r["account_code"] in income_codes
            )
            self.check(
                "doc" + number + ".pretax",
                oracle["risultato_ante_imposte"],
                int(pretax),
            )

    def check_mismatch(
        self, number: str, expected: Mapping[str, Any], pointer: str
    ) -> None:
        version = next(
            v
            for v in self.case()["closing_workflow"]["versions"]
            if v["version_id"] == "doc" + number
        )
        self.check(
            "doc" + number + ".mismatch",
            "MISMATCH",
            version["reconciliation"]["status"],
            pointer,
        )
        observed = {
            d["account_code"]: int(Decimal(d["difference"]))
            for d in version["reconciliation"]["differences"]
        }
        self.check(
            "doc" + number + ".exact_unauthorized_deltas", expected, observed, pointer
        )

    def failed_screening(self, name: str, version: str, record: str) -> None:
        self.rejected(
            name + ".screening_rejected",
            "record_closing_decision",
            {
                "record_id": record,
                "kind": "SCREENING",
                "reason": "Prova negativa: quadratura senza riconciliazione esatta.",
                "evidence_refs": [self.documents[version[3:]]],
                "decision": {
                    "version_id": version,
                    "convention": "SIGNED_BALANCE_ONLY",
                    "closing_entries_included": True,
                    "checks": dict.fromkeys(
                        ["period", "comparative", "debit_credit", "closing_entries"],
                        True,
                    ),
                },
            },
            reviewer=True,
            contains="exactly",
        )

    def suspension_checks(self, label: str, *, before_replacement: bool) -> None:
        status = self.status()
        pointer = "/modifica_doc11/" + (
            "stato_intermedio_20_22_gennaio"
            if before_replacement
            else "stato_dopo_A2bis_prima_del_doc12"
        )
        self.check(
            label + ".A2",
            "REVIEW_REQUIRED" if before_replacement else "SUPERSEDED",
            status["decision_states"]["D-A2"],
            pointer,
        )
        self.check(label + ".A1", "VALID", status["decision_states"]["D-A1"])
        self.check(
            label + ".suspended",
            dict.fromkeys(SCOPES, "SUSPENDED"),
            status["dependencies"],
            pointer + "/validazione_sospesa",
        )
        self.check(
            label + ".no_closure",
            False,
            status["closure_allowed"],
            pointer + "/chiusura_consentita",
        )
        self.check(
            label + ".no_form_mapping", False, status["form_and_mapping_allowed"]
        )
        self.check(
            label + ".review",
            "OPEN" if before_replacement else "CLOSED",
            status["reconsiderations"]["R-A2"]["state"],
        )
        self.check(
            label + ".latest_accounts_doc10", "doc10", status["selected_version_id"]
        )
        self.check(
            label + ".form_preserved", "ABBREVIATED", self.case()["selected_form"]
        )

    def finish_boundary_checks(self) -> None:
        from closing_workflow import verify_closing_register
        from intelligence_contract import build_intelligence_packet
        from review_views import build_review_view
        from xbrl_case import normalize_decimal

        case = self.case()
        self.check(
            "register.no_origin_decision",
            False,
            any(e["kind"] == "ORIGIN" for e in case["closing_workflow"]["events"]),
        )
        self.rejected(
            "role.preparer_cannot_decide",
            "record_closing_decision",
            {"record_id": "not-authorized"},
            contains="OVERRIDE",
        )
        self.rejected(
            "replacement.direct_ingest_cannot_bypass",
            "ingest",
            {
                "source_path": str(next((self.fixtures / "dati").glob("14_*"))),
                "column_mapping": COLUMN_MAPPING,
            },
            contains="replacement",
        )
        modified = deepcopy(case)
        modified["closing_workflow"]["events"][0]["reason"] = "Changed old decision"
        try:
            verify_closing_register(modified)
        except ValueError:
            rejected = True
        else:
            rejected = False
        self.check("register.tamper_rejected", True, rejected)
        page = build_review_view(case, "CLOSING_DECISIONS", limit=2)
        self.check(
            "review.paginated",
            {"returned": 2, "total": 13, "has_more": True},
            {key: page["page"][key] for key in ["returned", "total", "has_more"]},
        )
        packet = build_intelligence_packet(case, "WORKFLOW_GUIDANCE", [])
        self.check(
            "model.closing_context_present",
            True,
            "closing" in packet["reviewed_context"],
        )
        self.check(
            "model.no_entity_identity", False, "SYNTHETIC-ALFA" in json.dumps(packet)
        )
        evidence = build_review_view(case, "CLOSING_EVIDENCE")["items"]
        by_doc = {r["document_id"]: r for r in evidence}
        for number in ["02", "03", "04", "05", "06", "07", "11"]:
            source = next((self.fixtures / "dati").glob(number + "_*"))
            self.check(
                "source.exact_extract." + number,
                source.read_bytes().decode("utf-8-sig"),
                by_doc[self.documents[number]]["text"],
            )
        assets = list(
            csv.DictReader(
                io.StringIO(by_doc[self.documents["02"]]["text"]), delimiter=";"
            )
        )[0]
        depreciation = (
            normalize_decimal(assets["costo_storico"])
            * Decimal(assets["aliquota"].rstrip("%"))
            / 100
        )
        self.check("source.depreciation_12000", 12000, int(depreciation))
        bank = list(
            csv.DictReader(
                io.StringIO(by_doc[self.documents["06"]]["text"]), delimiter=";"
            )
        )
        bank_end = normalize_decimal(bank[-1]["saldo"])
        accounts = {r["account_code"]: r for r in case["trial_balance"]["entries"]}
        self.check(
            "source.bank_reconciles",
            bank_end,
            Decimal(accounts["1410"]["closing_signed"]),
        )
        tfr = list(
            csv.DictReader(
                io.StringIO(by_doc[self.documents["07"]]["text"]), delimiter=";"
            )
        )
        tfr_end = sum(normalize_decimal(r["importo"]) for r in tfr[:-1])
        self.check(
            "source.TFR_movement", normalize_decimal(tfr[-1]["importo"]), tfr_end
        )
        self.check(
            "source.TFR_reconciles",
            tfr_end,
            -Decimal(accounts["2110"]["closing_signed"]),
        )
        adjustment = self.status()["active_adjustments"]["D-A2-bis"]
        expected = self.oracle["modifica_doc11"]["A2-bis"]
        self.check(
            "A2bis.reviewed_debit_account",
            expected["dare"],
            adjustment["lines"][0]["account_code"],
            "/modifica_doc11/A2-bis/dare",
        )
        self.check(
            "A2bis.reviewed_credit_account",
            expected["avere"],
            adjustment["lines"][1]["account_code"],
            "/modifica_doc11/A2-bis/avere",
        )
        self.check(
            "A2bis.full_replacement_amount",
            expected["importo"],
            int(Decimal(adjustment["lines"][0]["debit"])),
            "/modifica_doc11/A2-bis/importo",
        )
        self.check(
            "A2bis.source11_bound",
            True,
            self.documents["11"] in [r["document_id"] for r in adjustment["evidence"]],
            "/modifica_doc11/A2-bis/fonte",
        )
        status = self.status()
        self.check(
            "A2.superseded",
            "SUPERSEDED",
            status["decision_states"]["D-A2"],
            "/modifica_doc11/A2",
        )
        self.check(
            "new_area.professionally_activated",
            "ACTIVE",
            next(a["status"] for a in status["areas"] if a["area_id"] == "area_13"),
            "/modifica_doc11/area_attivata",
            "/modifica_doc11/qualificazione",
        )
        expected_ids = [
            e["record"]
            for e in self.oracle["modifica_doc11"]["registro_dopo_doc12"]["eventi"]
        ]
        self.check(
            "register.exact_order",
            expected_ids,
            [e["record_id"] for e in case["closing_workflow"]["events"]],
        )
        self.check(
            "register.professional_accountability",
            True,
            all(
                e["actor"] == "P1"
                and e["role"] == "REVIEWER"
                and e["reason"]
                and e["evidence"]
                for e in case["closing_workflow"]["events"]
                if e["kind"] != "RECONSIDERATION"
            ),
        )
        self.check(
            "register.screening_links",
            ["D-A1", "D-A2-bis"],
            case["closing_workflow"]["events"][-1]["decision"]["approved_decision_ids"],
        )
        for snapshot, oracle_key in [
            ("03_doc10_screened", "registro_decisioni_dopo_fase5"),
            ("04_areas_reviewed", "registro_decisioni_dopo_fase7"),
        ]:
            expected_states = dict.fromkeys(
                self.oracle[oracle_key]["vista_stato"], "VALID"
            )
            self.check(
                "register.states." + snapshot,
                expected_states,
                self.status_function(self.snapshots[snapshot])["decision_states"],
                "/" + oracle_key + "/vista_stato",
            )
        before = self.status_function(self.snapshots["05_suspended_20_22"])[
            "decision_states"
        ]
        expected_before = dict.fromkeys(
            self.oracle["modifica_doc11"]["registro_decisioni"]["vista_stato"][
                "dal_2026-01-20_al_2026-01-22"
            ],
            "VALID",
        )
        expected_before.update(
            {
                "D-A2": "REVIEW_REQUIRED",
                "D-ESCL": "PARTIAL_REVIEW_REQUIRED",
                "R-A2": "OPEN",
            }
        )
        self.check(
            "register.states.20_22",
            expected_before,
            before,
            "/modifica_doc11/registro_decisioni/vista_stato/dal_2026-01-20_al_2026-01-22",
        )
        expected_final = dict.fromkeys(
            self.oracle["modifica_doc11"]["registro_dopo_doc12"]["vista_stato"], "VALID"
        )
        expected_final.update(
            {
                "D-A2": "SUPERSEDED",
                "D-SCR2": "SUPERSEDED",
                "D-ESCL": "PARTIALLY_SUPERSEDED",
                "R-A2": "CLOSED",
            }
        )
        self.check(
            "register.states.final",
            expected_final,
            self.status()["decision_states"],
            "/modifica_doc11/registro_dopo_doc12/vista_stato",
        )
        expected_events = self.oracle["modifica_doc11"]["registro_dopo_doc12"]["eventi"]
        expected_dates = {e["record"]: e["data"] for e in expected_events}
        observed_dates = {
            e["record_id"]: e["effective_date"]
            for e in case["closing_workflow"]["events"]
        }
        self.check("register.effective_dates", expected_dates, observed_dates)
        self.check(
            "scope.no_final_approval_export",
            {"approval": None, "artifacts": []},
            {"approval": case["approval"], "artifacts": case["artifacts"]},
            "/fuori_perimetro",
        )
        self.check(
            "fascicolo.first_decision_recorded",
            self.oracle["fascicolo_iniziale"]["decisione"],
            case["closing_workflow"]["events"][0]["record_id"],
            "/fascicolo_iniziale/decisione",
        )

    def report(self) -> dict[str, Any]:
        manifest = {
            str(p.relative_to(self.fixtures)): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in sorted(self.fixtures.rglob("*"))
            if p.is_file()
        }
        failures = [c["id"] for c in self.checks if not c["conformant"]]
        # Repeated expected event payloads are scenario inputs. Runtime behavior
        # is proved by role enforcement, append integrity and state projections,
        # not by echoing those supplied strings back as inferred accounting facts.
        coverage = {}

        def visit(value: Any, pointer: str) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    visit(child, pointer + "/" + key)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, pointer + "/" + str(index))
            else:
                applicable = [
                    c["id"]
                    for c in self.checks
                    if any(
                        pointer.startswith(p) or p.startswith(pointer)
                        for p in c["oracle_paths"]
                    )
                ]
                coverage[pointer] = {
                    "expected": value,
                    "behavior_checks": applicable,
                    "classification": (
                        "BEHAVIOR_CHECK"
                        if applicable
                        else "SCENARIO_INPUT_OR_SCOPE_REVIEW"
                    ),
                }

        visit(self.oracle, "")
        report = {
            "case": "Alfa v3",
            "status": "PASS" if not failures else "FAIL",
            "check_count": len(self.checks),
            "failures": failures,
            "checks": self.checks,
            "oracle_coverage": coverage,
            "source_sha256": manifest,
            "plugin_root": str(self.plugin),
            "execution_boundary": f"Vera {self.transport}; persistent synthetic case; simulated authenticated P1/C1; no enabled-host or UI claim",
            "limits": [
                "The oracle includes professional input decisions and scope descriptions; those are not model-inference benchmarks.",
                "No real client, final accounts approval, XBRL export, filing, email or production malware verdict.",
                "Tax computation, litigation provision, prior-XBRL reconciliation and notes remain outside Alfa v3 scope.",
            ],
        }
        (self.output / "acceptance.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        (self.output / "execution_trace.json").write_text(
            json.dumps(self.trace, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        rows = [
            "# Collaudo Alfa v3",
            "",
            f"Esito: **{report['status']}**. Controlli: {len(self.checks)}. Scostamenti: {len(failures)}.",
            "",
            "Eseguito sul servizio persistente di Vera con identità P1/C1 simulate e dati interamente sintetici. Gli esiti non qualificano una conversazione già aperta o un'interfaccia nativa.",
            "",
            "| Punto | Atteso | Osservato | Esito |",
            "| --- | --- | --- | --- |",
        ]
        for check in self.checks:

            def compact(value: Any) -> str:
                text = json.dumps(value, ensure_ascii=False, default=str)
                if len(text) > 240:
                    return "SHA-256 " + hashlib.sha256(text.encode()).hexdigest()
                return text.replace("|", "\\|").replace("\n", " ")

            rows.append(
                f"| {check['id']} | {compact(check['expected'])} | {compact(check['observed'])} | {'Conforme' if check['conformant'] else 'Scostamento'} |"
            )
        rows += [
            "",
            "Il JSON allegato conserva tutti gli esiti, i riferimenti ai risultati attesi, le impronte delle fonti e la distinzione tra comportamento verificato e dati/decisioni forniti dallo scenario.",
            "",
            "Imposte e valutazione della vertenza rimangono aperte: il bilancio completo non è approvato né esportato.",
        ]
        (self.output / "confronto_alfa_v3.md").write_text(
            "\n".join(rows) + "\n", encoding="utf-8"
        )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugin-root", type=Path, default=ROOT / "plugins/bilancio-xbrl-it"
    )
    parser.add_argument(
        "--fixtures", type=Path, default=ROOT / "tests/fixtures/bilancio_alfa_v3"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transport", choices=["service", "mcp"], default="service")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    report = AlfaAcceptance(
        args.plugin_root.resolve(),
        args.fixtures.resolve(),
        args.output.resolve(),
        args.transport,
    ).run()
    LOGGER.info(
        "Alfa v3: %s; %s checks; failures: %s",
        report["status"],
        report["check_count"],
        report["failures"],
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
