"""Two persisted P1 acceptance demonstrations; every identity and approval is synthetic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fusione_archive import ledger
from fusione_case import CaseStore, reference
from fusione_model import CaseError
from fusione_p1 import ASSUMPTIONS, SECTIONS
from fusione_report import export_report

__all__ = ["prepare_case", "run_p1_demo"]


class Demo:
    """Keep synthetic source values, archive receipts and exact case references together."""

    def __init__(self, root: Path, branch_name: str):
        root.mkdir(parents=True, exist_ok=False)
        self.root = root
        self.branch_name = branch_name
        self.api = ledger()
        self.store = CaseStore.create(
            root / "case",
            "synthetic_reviewer",
            {
                "operation_type": "fusione",
                "objectives": "SYNTHETIC P1 acceptance case",
                "jurisdictions": ["IT"],
                "planned_date": "2026-12-01",
                "actual_date": None,
            },
            synthetic=True,
        )
        self.entities: dict[str, dict[str, Any]] = {}
        self.bindings: dict[str, dict[str, Any]] = {}
        self.clients: dict[str, tuple[Path, str, str]] = {}
        self.facts: dict[str, dict[str, Any]] = {}
        for number, name in enumerate(("alpha", "beta"), start=1):
            client_root = root / name
            client_root.mkdir()
            client_id = "client_" + f"{number:024x}"
            self.api.create_client_manifest(client_root, client_id)
            engagement = self.api.create_engagement(
                client_root, client_id, "SYNTHETIC merger"
            )
            entity = self.store.put(
                name,
                "Entity",
                {
                    "name": "SYNTHETIC " + name,
                    "legal_form": "Spa",
                    "role": "acquirer" if number == 1 else "target",
                    "residence": "IT",
                    "accounting_framework": "OIC",
                    "source_roots": [str(client_root)],
                },
                scope=[name],
                dependencies=[],
                expected_version=0,
            )
            self.entities[name] = reference(entity)
            self.clients[name] = client_root, client_id, engagement["engagement_id"]
            bound = self.store.bind_archive(
                "archive_" + name,
                name,
                client_root,
                client_id,
                engagement["engagement_id"],
            )
            self.bindings[name] = reference(bound)

    def fact(
        self, name: str, value: Any, kind: str = "text", company: str = "alpha"
    ) -> dict[str, Any]:
        client_root, client_id, engagement_id = self.clients[company]
        source = client_root / (name + ".json")
        source.write_text(
            json.dumps(
                {"synthetic": True, "fact": name, "value": value, "value_kind": kind},
                indent=2,
            ),
            encoding="utf-8",
        )
        receipt = self.api.import_document(
            client_root, client_id, engagement_id, source, "source"
        )["receipt"]
        proof = self.store.import_archive(
            "evidence_" + name,
            self.bindings[company],
            receipt["input_id"],
            locator="JSON value",
            description="SYNTHETIC " + name,
        )
        record = self.store.put(
            name,
            "Fact",
            {
                "description": "SYNTHETIC " + name,
                "fact_status": "known",
                "value_kind": kind,
                "value": value,
                "unit": kind,
                "as_of": "2026-09-30",
            },
            scope=[company],
            dependencies=[reference(proof)],
            expected_version=0,
        )
        self.facts[name] = reference(record)
        return reference(record)

    def approve(self, row: dict[str, Any], suffix: str = "") -> None:
        self.store.approve(
            "approval_" + row["id"] + suffix,
            reference(row),
            professional_role="SYNTHETIC reviewer",
            scope_text="Synthetic software acceptance only",
            confirmation="SYNTHETIC fixture approval; no person or real case is represented.",
        )

    def paper(self, name: str, kind: str, request: dict[str, Any]) -> dict[str, Any]:
        row = self.store.workpaper(name, kind, request, expected_version=0)
        if row["data"]["issues"]:
            raise CaseError(
                "Synthetic fixture has unresolved workpaper issues: "
                + str(row["data"]["issues"])
            )
        self.approve(row)
        (self.root / (name + "-request.json")).write_text(
            json.dumps(
                {
                    "action": "workpaper",
                    "object_id": name,
                    "kind": kind,
                    "request": request,
                    "expected_version": 0,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return reference(row)


def prepare_case(root: Path, branch_name: str) -> Demo:
    """Execute both actual archive and case APIs, without network or client data."""
    demo = Demo(root.resolve(), branch_name)
    fact = demo.fact
    store = demo.store
    # A synthetic source exercises the approval mechanics; legal research is separately documented.
    fact(
        "source_note",
        "SYNTHETIC rule text for software testing; not a legal authority.",
    )
    source = store.put(
        "source",
        "SourceVersion",
        {
            "title": "SYNTHETIC source",
            "url": "https://example.invalid/fusione-p1",
            "checked_on": "2026-09-30",
            "access_status": "retrieved",
            "error": None,
            "source_version": "synthetic-v1",
        },
        scope=["alpha"],
        dependencies=[reference(store.read("evidence_source_note"))],
        expected_version=0,
    )
    rule = store.put(
        "rule",
        "RuleVersion",
        {
            "statement": "SYNTHETIC reviewed assumptions and calendar only",
            "citation": "synthetic-1",
            "review_status": "professional_review_pending",
            "published_on": "2026-01-01",
            "effective_from": "2026-01-01",
            "effective_to": None,
            "applicable_from": "2026-01-01",
            "applicable_to": "2026-12-31",
            "transitional_notes": "Synthetic validity interval",
            "scope": "Synthetic fixtures only",
            "preconditions": ["Synthetic case"],
            "exceptions": [],
            "test_refs": ["P1-DEMO"],
        },
        scope=["alpha"],
        dependencies=[reference(source)],
        expected_version=0,
    )
    demo.approve(rule)
    wholly = branch_name == "wholly_owned_domestic_oic"
    edge = None
    if wholly:
        edge = reference(
            store.put(
                "ownership_edge",
                "OwnershipEdge",
                {
                    "holder": "alpha",
                    "company": "beta",
                    "ratio": "1/1",
                    "rights": "SYNTHETIC ordinary ownership",
                    "as_of": "2026-09-30",
                },
                scope=["alpha", "beta"],
                dependencies=list(demo.entities.values()),
                expected_version=0,
            )
        )
    plan = demo.paper(
        "plan",
        "BranchDecision",
        {
            "branch": branch_name,
            "acquirer": demo.entities["alpha"],
            "target": demo.entities["beta"],
            "assumptions": {
                key: fact(key, True, "boolean") for key in sorted(ASSUMPTIONS)
            },
            "ownership": fact("ownership", "1/1" if wholly else "0/1", "fraction"),
            "ownership_edge": edge,
            "rationale": fact(
                "branch_rationale",
                "SYNTHETIC manual branch selection and reviewed scope",
            ),
            "rules": [reference(rule)],
        },
    )
    va = vb = None
    if not wholly:
        for name, company, amount in (
            ("valuation_a", "alpha", "600000.00"),
            ("valuation_b", "beta", "400000.00"),
        ):
            result = demo.paper(
                name,
                "Valuation",
                {
                    "plan": plan,
                    "company": demo.entities[company],
                    "basis": "equity",
                    "value": fact("equity_" + company, amount, "decimal", company),
                    "debt": None,
                    "cash": None,
                    "adjustments": None,
                    "method": fact(
                        "method_" + company,
                        "SYNTHETIC professionally supplied equity; no automated valuation",
                        company=company,
                    ),
                    "valuation_date": fact(
                        "valuation_date_" + company, "2026-09-30", "date", company
                    ),
                },
            )
            if company == "alpha":
                va = result
            else:
                vb = result
    owner_a = {
        "id": "owner_a",
        "name": fact("owner_a", "SYNTHETIC Alice"),
        "units": fact("owner_a_units", "60000", "decimal"),
    }
    owners_b = (
        []
        if wholly
        else [
            {
                "id": "owner_b",
                "name": fact("owner_b", "SYNTHETIC Bruno", company="beta"),
                "units": fact("owner_b_units", "20000", "decimal", "beta"),
            }
        ]
    )
    ex = demo.paper(
        "exchange",
        "ExchangeModel",
        {
            "plan": plan,
            "valuation_a": va,
            "valuation_b": vb,
            "units_a": fact("units_a", "60000", "decimal"),
            "units_b": None if wholly else fact("units_b", "20000", "decimal", "beta"),
            "nominal": fact("nominal", "1.00", "decimal"),
            "unit_type": "shares",
            "shareholders_a": [owner_a],
            "shareholders_b": owners_b,
            "allocation_policy": fact(
                "allocation_policy",
                "SYNTHETIC exact whole shares; no cash adjustment or hidden rounding",
            ),
        },
    )

    def account(key: str, amount: str, category: str, company: str) -> dict[str, Any]:
        return {
            "id": key,
            "label": "SYNTHETIC " + key,
            "category": category,
            "balance": fact(company + "_" + key, amount, "decimal", company),
        }

    a = [
        account("cash", "500000", "asset", "alpha"),
        account("capital", "-60000", "equity", "alpha"),
        account("reserves", "-440000", "equity", "alpha"),
    ]
    b = [
        account("assets", "500000" if wholly else "350000", "asset", "beta"),
        account("liabilities", "-200000", "liability", "beta"),
        account("equity", "-300000" if wholly else "-150000", "equity", "beta"),
    ]
    if wholly:
        a += [
            account("investment", "480000", "asset", "alpha"),
            account("investment_funding", "-480000", "liability", "alpha"),
        ]
    allocation = [
        account(
            "reviewed_asset_uplift" if wholly else "reviewed_merger_reserve",
            "180000" if wholly else "-110000",
            "asset" if wholly else "equity",
            "beta",
        )
    ]
    book = demo.paper(
        "bridge",
        "BookBridge",
        {
            "plan": plan,
            "exchange": ex,
            "balances_a": a,
            "balances_b": b,
            "date_a": fact("balance_date_a", "2026-09-30", "date"),
            "date_b": fact("balance_date_b", "2026-09-30", "date", "beta"),
            "investment_account": "investment" if wholly else None,
            "eliminations": [],
            "difference_allocations": allocation,
            "accounting_policy": fact(
                "accounting_policy",
                "SYNTHETIC selected accounting allocation, with separately reviewed tax effects; not a real goodwill or tax determination",
            ),
            "tax_register": [
                {
                    "id": "basis_b",
                    "owner": fact("tax_owner", "SYNTHETIC beta", company="beta"),
                    "category": "asset",
                    "book": fact(
                        "tax_book", "680000" if wholly else "350000", "decimal", "beta"
                    ),
                    "tax": fact(
                        "tax_basis", "500000" if wholly else "350000", "decimal", "beta"
                    ),
                    "assessment": fact(
                        "tax_assessment",
                        "SYNTHETIC tax bases kept distinct; tax treatment and deferred taxes require case-specific professional review",
                        company="beta",
                    ),
                }
            ],
        },
    )
    events = []
    owner = fact("calendar_owner", "SYNTHETIC responsible professional")
    for key, anchors, count, unit, constraint, actual in (
        (
            "project_notice",
            ["2026-09-01", "2026-09-02"],
            30,
            "days",
            "not_before",
            "2026-10-02",
        ),
        ("documents_available", ["2026-09-02"], 30, "days", "not_before", "2026-10-02"),
        ("creditor_wait", ["2026-10-02", "2026-10-03"], 60, "days", "not_before", None),
        ("annual_accounts", ["2026-03-31"], 6, "months", "not_after", "2026-09-30"),
        ("statement_age", ["2026-06-02"], 120, "days", "not_after", "2026-09-30"),
    ):
        events.append(
            {
                "id": key,
                "label": "SYNTHETIC " + key,
                "anchors": [
                    fact(f"{key}_anchor_{i}", day, "date")
                    for i, day in enumerate(anchors)
                ],
                "count": count,
                "unit": unit,
                "rule": reference(rule),
                "owner": owner,
                "actual": (
                    None if actual is None else fact(key + "_actual", actual, "date")
                ),
                "constraint": constraint,
                "adjusted_boundary": None,
                "adjustment_reason": None,
            }
        )
    cal = demo.paper(
        "calendar",
        "Deadline",
        {
            "plan": plan,
            "events": events,
            "computation_policy": fact(
                "calendar_policy",
                "SYNTHETIC declared ordinary terms; no inferred waivers or holiday adjustments",
            ),
        },
    )
    demo.paper(
        "dossier",
        "LegalDocument",
        {
            "plan": plan,
            "exchange": ex,
            "bridge": book,
            "calendar": cal,
            "title": "SYNTHETIC P1 review dossier",
            "sections": {
                key: fact(
                    "section_" + key,
                    "SYNTHETIC reviewed section: "
                    + key
                    + ". Human execution and real receipts are not demonstrated.",
                )
                for key in sorted(SECTIONS)
            },
        },
    )
    return demo


def run_p1_demo(destination: Path) -> dict[str, Any]:
    """Persist two complete cases and a changed-input review, with honest test boundaries."""
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=False)
    checks: dict[str, bool] = {}
    reports = {}
    for branch_name in sorted(("ordinary_domestic_oic", "wholly_owned_domestic_oic")):
        demo = prepare_case(destination / branch_name, branch_name)
        store = demo.store
        exchange = store.read("exchange")["data"]["result"]
        book = store.read("bridge")["data"]["result"]
        checks[branch_name + ":dossier_review_recorded"] = (
            store.status("dossier")["review_state"] == "approved_for_defined_scope"
        )
        checks[branch_name + ":balanced_opening"] = book["opening_residual"] == "0.00"
        checks[branch_name + ":archive_receipts"] = (
            "archive_receipt" in store.read("evidence_units_a")["data"]
        )
        checks[branch_name + ":no_signature_or_filing"] = (
            store.read("dossier")["data"]["result"]["filing"] == "not_performed"
        )
        if branch_name == "ordinary_domestic_oic":
            checks["ordinary:ratio_and_allocation"] = (
                exchange["exchange_ratio"] == "2/1"
                and exchange["new_units"] == "40000/1"
                and exchange["allocations"][1]["resulting_fraction"] == "2/5"
            )
            checks["ordinary:concambio"] = (
                book["difference_signed_debit"] == "-110000.00"
            )
        else:
            checks["wholly:no_new_units"] = (
                exchange["new_units"] == "0/1" and exchange["exchange_ratio"] is None
            )
            checks["wholly:annullamento"] = (
                book["difference_signed_debit"] == "180000.00"
            )
        reports[branch_name] = export_report(store, demo.root / "before")
        updated = demo.fact("beta_liabilities_updated", "-200100", "decimal", "beta")
        revised_evidence = store.read(updated["id"])["dependencies"]
        previous = store.read("beta_liabilities")
        changed = {**previous["data"], "value": "-200100"}
        store.put(
            previous["id"],
            "Fact",
            changed,
            scope=previous["scope"],
            dependencies=revised_evidence,
            expected_version=previous["version"],
        )
        checks[branch_name + ":selective_reopening"] = (
            store.status("dossier")["review_state"] == "needs_review"
            and store.status("calendar")["review_state"] == "approved_for_defined_scope"
        )
        checks[branch_name + ":approval_history_preserved"] = (
            store.read("approval_dossier")["data"]["target"]["version"] == 1
        )
        export_report(store, demo.root / "after")
    result = {
        "synthetic": True,
        "passed": all(checks.values()),
        "checks": checks,
        "reports": reports,
        "not_run": [
            "Real-client acceptance",
            "Independent professional validation",
            "Signature",
            "Filing",
            "P2/P3 branches",
        ],
    }
    (destination / "p1-demo-results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result
