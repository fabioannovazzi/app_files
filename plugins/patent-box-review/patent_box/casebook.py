"""Validate and render the host model's evidence-led case record.

Reference closure and missing-record detection are mechanically verifiable.
No text classifier decides ownership, originality, activity or legal relevance.
"""

from __future__ import annotations

from typing import Any

from .contracts import ContractError, indexed, validate
from .coordination import coordinate_incentives

__all__ = ["check_casebook", "casebook_markdown", "missing_documents_markdown"]

IP_ISSUES = {
    "SOFTWARE": {"AUTHORSHIP", "ORIGINAL_COMPONENT", "THIRD_PARTY_COMPONENTS"},
    "PATENT": {"TITLE_AND_CLAIMS", "TERRITORY", "VALIDITY"},
    "DESIGN": {"PROTECTED_OBJECT", "PROTECTION", "FUNCTIONAL_ACTIVITIES"},
    "OTHER": {"CATEGORY_SCOPE"},
}


def _references(value: Any, registries: dict[str, set[str]]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in registries and not set(item) <= registries[key]:
                raise ContractError(f"Unknown casebook {key} reference")
            _references(item, registries)
    elif isinstance(value, list):
        for item in value:
            _references(item, registries)
    elif isinstance(value, str) and not value.strip():
        raise ContractError("Casebook text cannot be blank")


def check_casebook(
    book: dict[str, Any],
    case: dict[str, Any],
    rules: dict[str, Any],
    control_keys: set[str],
) -> dict[str, Any]:
    """Keep unresolved records visible and reject false reference/completeness claims."""
    validate(book, "casebook.schema.json")
    facts = indexed(book["facts"], "fact_id")
    projects = indexed(book["projects"], "project_id")
    activities = indexed(book["activities"], "activity_id")
    ips = indexed(case["ips"], "ip_id")
    details = indexed(book["ip_details"], "ip_id")
    allocations = indexed(case["allocations"], "allocation_id")
    periods = {p["period_id"] for p in case["periods"]}
    requests = indexed(book["missing_documents"], "request_id")
    evidence_ids = {e["evidence_id"] for e in case["evidence"]}
    source_ids = {s["source_id"] for s in rules["sources"]}
    registries = {
        "evidence_ids": evidence_ids,
        "reported_evidence_ids": evidence_ids,
        "source_ids": source_ids,
        "deadline_source_ids": source_ids,
        "fact_ids": set(facts),
        "use_fact_ids": set(facts),
        "period_ids": periods,
        "control_keys": control_keys,
        "allocation_ids": set(allocations),
        "missing_request_ids": set(requests),
    }
    _references(book, registries)
    if not set(details) <= set(ips):
        raise ContractError("Unknown IP detail")
    gaps: list[dict[str, str]] = []

    def gap(control: str, reason: str) -> None:
        gaps.append({"control_key": control, "reason": reason})

    if not book["taxpayer"]["evidence_ids"]:
        gap("case/PB.SUBJECT", "Identità del contribuente priva di prova selezionata")
    for fact in facts.values():
        if fact["status"] == "EVIDENCED" and not fact["evidence_ids"]:
            raise ContractError("An evidenced fact needs selected evidence")
    for activity in activities.values():
        if activity["project_id"] not in projects or activity["ip_id"] not in ips:
            raise ContractError("Activity has an unknown project or IP")
    for allocation in allocations.values():
        linked_activity = activities.get(allocation["activity_id"])
        if linked_activity is None or not linked_activity["fact_ids"]:
            gap(
                "allocation:" + allocation["allocation_id"] + "/PB.LINKAGE",
                "Attività e prove da documentare",
            )
        elif (linked_activity["project_id"], linked_activity["ip_id"]) != (
            allocation["project_id"],
            allocation["ip_id"],
        ):
            raise ContractError(
                "Allocation disagrees with activity/project/IP register"
            )
        elif not all(
            facts[f]["status"] == "EVIDENCED" for f in linked_activity["fact_ids"]
        ):
            gap(
                "allocation:" + allocation["allocation_id"] + "/PB.LINKAGE",
                "Fatti dell’attività ancora proposti o irrisolti",
            )
    for ip in ips.values():
        scope = "ip:" + ip["ip_id"]
        detail = details.get(ip["ip_id"])
        if detail is None:
            gap(scope + "/PB.RIGHTS", "Scheda del bene e catena dei diritti mancanti")
            continue
        analysis = indexed(detail["analysis"], "issue")
        if not IP_ISSUES[ip["type"]] <= set(analysis):
            gap(
                scope + "/PB.IP." + ip["type"],
                "Istruttoria specifica del bene incompleta",
            )
        for item in analysis.values():
            if item["status"] == "EVIDENCED" and (
                not item["evidence_ids"] or not item["source_ids"]
            ):
                raise ContractError(
                    "IP conclusion needs evidence and applicable sources"
                )
            if item["status"] != "EVIDENCED":
                gap(
                    scope + "/PB.IP." + ip["type"],
                    "Analisi del bene non conclusa: " + item["issue"],
                )
        if not detail["rights_chain"] or any(
            not r["fact_ids"]
            or any(facts[f]["status"] != "EVIDENCED" for f in r["fact_ids"])
            for r in detail["rights_chain"]
        ):
            gap(scope + "/PB.RIGHTS", "Catena dei diritti senza fatti documentati")
        if not detail["use_fact_ids"] or any(
            facts[f]["status"] != "EVIDENCED" for f in detail["use_fact_ids"]
        ):
            gap(scope + "/PB.USE", "Uso del bene da documentare")
        suppliers = indexed(detail["supplier_chain"], "supplier_id")
        if ip["outsourced"] and not suppliers:
            gap(scope + "/PB.OUTSOURCING", "Filiera dei fornitori mancante")
        for supplier in suppliers.values():
            if (
                supplier["parent_supplier_id"] is not None
                and supplier["parent_supplier_id"] not in suppliers
            ):
                raise ContractError("Unknown commissioning supplier")
            visited = {supplier["supplier_id"]}
            parent = supplier["parent_supplier_id"]
            while parent is not None:
                if parent in visited:
                    raise ContractError("Supplier chain contains a cycle")
                visited.add(parent)
                parent = suppliers[parent]["parent_supplier_id"]
            if not supplier["fact_ids"] or any(
                facts[f]["status"] != "EVIDENCED" for f in supplier["fact_ids"]
            ):
                gap(scope + "/PB.OUTSOURCING", "Fatti della filiera da documentare")
    applicability: dict[tuple[str, str], dict[str, Any]] = {}
    for row in book["applicability"]:
        key = (row["branch"], row["scope"])
        if key in applicability:
            raise ContractError("Duplicate branch applicability assessment")
        applicability[key] = row
        if not row["evidence_ids"] or not row["source_ids"]:
            gap(
                "case/PB.TRANSITION",
                "Applicabilità del ramo senza riferimenti: " + row["branch"],
            )
    # A declared structural branch cannot be silently disabled by a contrary flag.
    for ip in ips.values():
        for branch, applies in (
            ("OUTSOURCING", ip["outsourced"]),
            (
                "PREMIAL",
                any(
                    a["ip_id"] == ip["ip_id"] and a["mode"] == "PREMIAL"
                    for a in allocations.values()
                ),
            ),
        ):
            row = applicability.get((branch, "ip:" + ip["ip_id"]))
            if row is None:
                gap(
                    "case/PB.TRANSITION",
                    "Applicabilità da motivare: " + branch + " / " + ip["ip_id"],
                )
            elif row["applicable"] != applies:
                raise ContractError(
                    "Branch applicability contradicts declared case structure"
                )
    for branch in ("EXTRAORDINARY", "PENALTY"):
        row = applicability.get((branch, "case"))
        if row is None:
            gap("case/PB.TRANSITION", "Applicabilità da motivare: " + branch)
        elif (
            branch == "PENALTY"
            and row["applicable"] != case["penalty_protection"]["requested"]
        ):
            raise ContractError("Penalty applicability contradicts the requested scope")
    for row in book["incentives"]:
        if row["period_id"] not in periods or not row["allocation_ids"]:
            raise ContractError(
                "Incentive must reference fiscal period and allocations"
            )
    incentives = coordinate_incentives(book["incentives"])
    for allocation_id in allocations:
        relevant = [r for r in incentives if allocation_id in r["allocation_ids"]]
        if not relevant or any(r["assessment"] == "UNRESOLVED" for r in relevant):
            gap(
                "allocation:" + allocation_id + "/PB.INCENTIVES",
                "Coordinamento o assenza di sovrapposizioni da documentare",
            )
    paragraphs = indexed(book["paragraphs"], "paragraph_id")
    for paragraph in paragraphs.values():
        if paragraph["status"] == "EVIDENCED" and (
            not paragraph["fact_ids"]
            or any(facts[f]["status"] != "EVIDENCED" for f in paragraph["fact_ids"])
        ):
            raise ContractError(
                "An evidenced paragraph cannot assert unsupported facts"
            )
    template = book["template"]
    if template is None:
        if case["penalty_protection"]["requested"]:
            gap("penalty/PB.DOC.A", "Indice vigente e applicabile non acquisito")
            gap("penalty/PB.DOC.B", "Indice vigente e applicabile non acquisito")
    else:
        if (
            template["source_id"] not in source_ids
            or template["evidence_id"] not in evidence_ids
        ):
            raise ContractError(
                "Dossier template must reference a selected versioned source"
            )
        indexed(template["required_paragraphs"], "paragraph_id")
        for required in template["required_paragraphs"]:
            required_paragraph = paragraphs.get(required["paragraph_id"])
            if (
                required_paragraph is None
                or required_paragraph["status"] != "EVIDENCED"
            ):
                gap(
                    "penalty/PB.DOC." + required["section"],
                    "Paragrafo da completare: " + required["title"],
                )
            elif required_paragraph["section"] != required["section"]:
                raise ContractError(
                    "Paragraph assigned to a different template section"
                )
    for model in book["declarations"]:
        if (
            model["model_evidence_id"] not in evidence_ids
            or model["instructions_source_id"] not in source_ids
        ):
            raise ContractError("Return needs selected annual model and instructions")
    if not book["declarations"]:
        gap("case/PB.DECLARATION", "Modello annuale e raccordo dichiarativo mancanti")
    elif case["penalty_protection"]["requested"] and not any(
        r["role"] == "DOCUMENTATION_NOTICE"
        for model in book["declarations"]
        for r in model["rows"]
    ):
        gap(
            "penalty/PB.DECLARATION",
            "Comunicazione documentazione da mappare separatamente",
        )
    indexed(book["adversarial_review"], "issue_id")
    if not book["adversarial_review"]:
        gap("case/PB.ADVERSARIAL", "Riesame critico non documentato")
    for issue in book["adversarial_review"]:
        if not issue["evidence_ids"] or not issue["source_ids"]:
            gap("case/PB.ADVERSARIAL", "Contestazione senza fatti o fonte pertinente")
    office = indexed(book["office_requests"], "request_id")
    for request in office.values():
        if (
            request["evidence_id"] not in evidence_ids
            or request["deadline_source_id"] not in source_ids
        ):
            raise ContractError(
                "Office request needs selected notice and deadline source"
            )
        if request["delivery_due_on"] < request["received_on"]:
            raise ContractError("Delivery deadline precedes receipt")
        if (
            request["integration_of"] is not None
            and request["integration_of"] not in office
        ):
            raise ContractError("Unknown earlier office request")
        receipt = request["delivery_receipt_evidence_id"]
        if receipt is not None and (
            receipt not in evidence_ids or request["delivered_version"] is None
        ):
            raise ContractError("Delivery needs selected receipt and exact version")
    return {"gaps": gaps, "incentives": incentives}


def missing_documents_markdown(book: dict[str, Any]) -> str:
    """Present small, owned requests with their consequences and next action."""
    lines = ["# Documenti e chiarimenti da richiedere", ""]
    for row in book["missing_documents"]:
        lines += [
            f"## {row['request_id']} — {row['priority']}",
            "",
            row["request"],
            "",
            f"Motivo: {row['reason']}",
            f"Referente: {row['owner']}",
            f"Conseguenza: {row['consequence']}",
            f"Prossimo passo: {row['next_step']}",
            "Controlli: " + ", ".join(row["control_keys"]),
            "",
        ]
    if not book["missing_documents"]:
        lines += [
            "Nessuna richiesta registrata; verificare separatamente i controlli aperti.",
            "",
        ]
    return "\n".join(lines)


def casebook_markdown(book: dict[str, Any]) -> str:
    """Render source-backed facts and paragraphs without converting proposals to facts."""
    lines = [
        "# Patent Box — registro della pratica",
        "",
        book["taxpayer"]["name"],
        book["objective"],
        "",
        "## Fatti e prove",
        "",
    ]
    for row in book["facts"]:
        lines += [
            f"- {row['fact_id']} [{row['status']}]: {row['statement']}",
            "  Prove: " + ", ".join(row["evidence_ids"]) + "; " + row["locator"],
        ]
    for section in ("A", "B"):
        lines += ["", "## Sezione " + section, ""]
        for row in book["paragraphs"]:
            if row["section"] == section:
                lines += [
                    f"### {row['title']} — {row['status']}",
                    "",
                    row["text"],
                    "",
                    "Fatti: " + ", ".join(row["fact_ids"]),
                    "Fonti: " + ", ".join(row["source_ids"]),
                    "",
                ]
    lines += ["", "## Riesame critico", ""]
    for row in book["adversarial_review"]:
        lines += [
            f"### {row['issue_id']} — {row['decision']}",
            row["argument"],
            row["response"],
            f"Basi in discussione: redditi EUR {row['income_at_risk']}; IRAP EUR {row['irap_at_risk']}",
            "Prove: " + ", ".join(row["evidence_ids"]),
            "Fonti: " + ", ".join(row["source_ids"]),
            "",
        ]
    return "\n".join(lines) + "\n"
