"""Bound Patent Box preparation; semantic proposals remain operator-reviewed.

Fixed logic is limited to exact paths, schemas, reference closure, review
freshness and Decimal arithmetic. It never decides legal eligibility.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import logging
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "initialize",
    "import_ledger",
    "inspect_ledger",
    "normalize_ledger",
    "verify_formalities",
    "prepare_professional_review",
    "accept_professional_review",
    "propose",
    "review",
    "calculate_draft",
    "main",
]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _vendor in (
    ROOT / "vendor/modules",
    ROOT.parent.parent / "vendor/modules",
    ROOT.parent / "_shared/vendor/modules",
):
    if (_vendor / "vera_assurance").is_dir():
        sys.path.insert(0, str(_vendor))
        break

from patent_box import professional_review
from patent_box.casebook import (
    casebook_markdown,
    check_casebook,
    missing_documents_markdown,
)
from patent_box.contracts import (
    ContractError,
    canonical_hash,
    file_hash,
    indexed,
    read_json,
    validate,
)
from patent_box.coordination import reconcile_declarations
from patent_box.documents import compose_dossier, render_docx, render_pdf
from patent_box.engine import CASE_GATES, IP_GATES, LINE_GATES, calculate
from patent_box.formalities import verify_cms, verify_pdf, verify_timestamp
from patent_box.ledger_import import (
    inspect_table,
    normalization_markdown,
    normalize_population,
)
from patent_box.render import markdown
from vera_assurance import load_client_engagement_context_file

WORKFLOW = "patent-box-review"
STATUSES = ("PASS", "WARNING", "FAIL", "BLOCKED", "NOT_TESTED")
MAX_BYTES = 16 * 1024 * 1024
LOGGER = logging.getLogger(__name__)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must contain text")
    return value.strip()


def _new(path: Path, content: str | bytes) -> None:
    """Exclusive creation preserves every previous proposal, decision and result."""
    if path.is_symlink() or path.parent.is_symlink():
        raise ContractError("Symbolic-link output is forbidden")
    with path.open("xb") as handle:
        handle.write(content.encode("utf-8") if isinstance(content, str) else content)
    path.chmod(0o600)


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ContractError("Expected a bounded regular JSON artifact")
    value = read_json(path)
    if not isinstance(value, dict):
        raise ContractError("Expected a JSON object")
    return value


def _context(context_path: Path) -> tuple[dict[str, Any], Path]:
    context = load_client_engagement_context_file(
        context_path, expected_workflow_id=WORKFLOW
    )
    output = Path(context["output_dir"])
    if output.is_symlink():
        raise ContractError("Symbolic-link output is forbidden")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    return context, output


def _bound(context_path: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    context, output = _context(context_path)
    session = _read(output / "patent_box_session.json")
    if session["run_id"] != context["run_id"]:
        raise ContractError("Session belongs to another run")
    bindings = {
        str(Path(row["path"]).resolve()): row for row in context["input_bindings"]
    }
    for record in session["inputs"]:
        path = Path(record["selected_path"])
        if str(path.resolve()) not in bindings or file_hash(path) != record["sha256"]:
            raise ContractError("Selected input changed; create a new run and review")
        snapshot = output / record["path"]
        if (
            snapshot.is_symlink()
            or not snapshot.resolve().is_relative_to(output.resolve())
            or file_hash(snapshot) != record["sha256"]
        ):
            raise ContractError("Evidence snapshot changed")
    return context, output, session


def initialize(context_path: Path, *, as_of: str, demo: bool = False) -> dict[str, Any]:
    """Snapshot only exact run receipts; do not discover other client documents."""
    context, output = _context(context_path)
    date.fromisoformat(as_of)
    if (output / "patent_box_session.json").exists():
        _, _, session = _bound(context_path)
        if session["as_of"] != as_of or session["demo"] != demo:
            raise ContractError("Initialization differs from existing session")
        return session
    evidence_dir = output / "selected_evidence"
    evidence_dir.mkdir(mode=0o700)
    records = []
    for number, binding in enumerate(context["input_bindings"], 1):
        source = Path(binding["path"])
        if (
            source.is_symlink()
            or not source.is_file()
            or source.stat().st_size > MAX_BYTES
        ):
            raise ContractError("Selected source must be a bounded regular file")
        raw = source.read_bytes()
        target = evidence_dir / f"E{number:04d}{source.suffix.lower()}"
        _new(target, raw)
        records.append(
            {
                "evidence_id": f"E{number:04d}",
                "path": target.relative_to(output).as_posix(),
                "sha256": file_hash(target),
                "description": source.name,
                "selected_path": str(source),
            }
        )
    if not records:
        raise ContractError("Select at least one evidence document")
    session = {
        "schema_version": "1.0",
        "workflow": WORKFLOW,
        "run_id": context["run_id"],
        "as_of": as_of,
        "demo": demo,
        "inputs": records,
        "identity_assurance": "LOCAL_OPERATOR_ASSERTION_NOT_PROFESSIONAL_AUTHENTICATION",
    }
    _new(output / "patent_box_session.json", _dump(session))
    _new(
        output / "intake.md",
        "# Patent Box — apertura della pratica\n\nBOZZA. "
        + ("Pratica sintetica.\n" if demo else "Pratica da istruire.\n")
        + "\nChiarire soggetto e periodo, beni e diritti, attività, costi, opzioni pregresse e incentivi. Leggere solo i documenti selezionati e chiedere ciò che manca.\n\n"
        + "\n".join(f"- {r['evidence_id']}: {r['description']}" for r in records)
        + "\n",
    )
    return session


def _ledger_rows(output: Path, record: dict[str, Any]) -> list[dict[str, str]]:
    """Read exact declared columns, without interpreting accounting meaning."""
    evidence_id = record["evidence_id"]
    fields = [
        "cost_id",
        "ledger_row_key",
        "period_id",
        "account",
        "category",
        "book_amount",
        "income_max",
        "irap_max",
    ]
    reader = csv.DictReader(
        io.StringIO((output / record["path"]).read_text(encoding="utf-8-sig"))
    )
    if reader.fieldnames != fields:
        raise ContractError("CSV needs reviewed column mapping: " + ", ".join(fields))
    costs = []
    for row in reader:
        if set(row) != set(fields) or any(value is None for value in row.values()):
            raise ContractError("Malformed ledger row")
        costs.append({**row, "evidence_id": evidence_id, "currency": "EUR"})
    indexed(costs, "cost_id")
    indexed(costs, "ledger_row_key")
    return costs


def import_ledger(context_path: Path, *, evidence_id: str) -> dict[str, Any]:
    """Parse an explicitly mapped CSV; amounts are proposals, not admitted costs."""
    _, output, session = _bound(context_path)
    record = indexed(session["inputs"], "evidence_id").get(evidence_id)
    if record is None:
        raise ContractError("Ledger is not selected evidence")
    costs = _ledger_rows(output, record)
    result = {
        "status": "PROPOSED_REQUIRES_REVIEW",
        "evidence_id": evidence_id,
        "source_sha256": record["sha256"],
        "costs": costs,
    }
    _new(output / f"ledger_{evidence_id}.json", _dump(result))
    return result


def _ledger_table(
    output: Path, session: dict[str, Any], table_id: str
) -> dict[str, Any]:
    """Replay exact selected bytes so a rehashed cell edit is still rejected."""
    if not re.fullmatch(r"T\.[0-9a-f]{64}", table_id):
        raise ContractError("Invalid table identity")
    table = _read(output / f"ledger_table_{table_id}.json")
    record = indexed(session["inputs"], "evidence_id").get(table["source_evidence_id"])
    if record is None:
        raise ContractError("Table evidence is outside the selected run")
    replayed = inspect_table(output / record["path"], record, table["options"])
    if table["table_id"] != table_id or table != replayed:
        raise ContractError("Table does not replay from the selected original")
    return table


def inspect_ledger(
    context_path: Path, *, evidence_id: str, options: dict[str, Any]
) -> dict[str, Any]:
    """Persist a selected CSV/XLSX/PDF table without deciding its accounting meaning."""
    _, output, session = _bound(context_path)
    record = indexed(session["inputs"], "evidence_id").get(evidence_id)
    if record is None:
        raise ContractError("Ledger is not selected evidence")
    table = inspect_table(output / record["path"], record, options)
    target = output / f"ledger_table_{table['table_id']}.json"
    if target.exists():
        if _ledger_table(output, session, table["table_id"]) != table:
            raise ContractError("Existing table differs from the selected original")
    else:
        _new(target, _dump(table))
    return table


def normalize_ledger(context_path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    """Persist the model's source-bound normalization proposal and readable trace."""
    _, output, session = _bound(context_path)
    validate(plan, "ledger-normalization.schema.json")
    tables = [
        _ledger_table(output, session, row["table_id"]) for row in plan["mappings"]
    ]
    result = normalize_population(
        tables, plan, {r["evidence_id"] for r in session["inputs"]}
    )
    record = {
        "schema_version": "1.0",
        "run_id": session["run_id"],
        "evidence_hash": canonical_hash(session["inputs"]),
        "plan": plan,
        "tables": tables,
        "result": result,
    }
    digest = result["normalization_digest"]
    _new(output / f"normalization_{digest}.json", _dump(record))
    _new(output / f"normalization_{digest}.md", normalization_markdown(result))
    return result


def _normalization(
    output: Path, session: dict[str, Any], digest: str
) -> dict[str, Any]:
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ContractError("Invalid normalization digest")
    record = _read(output / f"normalization_{digest}.json")
    if record["run_id"] != session["run_id"] or record[
        "evidence_hash"
    ] != canonical_hash(session["inputs"]):
        raise ContractError("Normalization belongs to another run or input version")
    plan = record["plan"]
    validate(plan, "ledger-normalization.schema.json")
    tables = [
        _ledger_table(output, session, row["table_id"]) for row in plan["mappings"]
    ]
    result = normalize_population(
        tables, plan, {r["evidence_id"] for r in session["inputs"]}
    )
    if (
        result["normalization_digest"] != digest
        or result != record["result"]
        or record["tables"] != tables
    ):
        raise ContractError("Normalization changed or does not replay")
    return record


def _bind_normalized_costs(proposal: dict[str, Any], record: dict[str, Any]) -> None:
    result = record["result"]
    if (
        indexed(proposal["case"]["costs"], "cost_id")
        != indexed(result["costs"], "cost_id")
        or proposal["case"]["ledger_control_total"] != result["ledger_control_total"]
    ):
        raise ContractError(
            "Cost population or total differs from reviewed normalization"
        )
    controls = indexed(proposal["controls"], "key")
    for allocation in proposal["case"]["allocations"]:
        if allocation["cost_id"] in result["blocked_cost_ids"]:
            key = f"allocation:{allocation['allocation_id']}/PB.COST"
            if controls[key]["status"] not in ("BLOCKED", "NOT_TESTED"):
                raise ContractError(
                    "Unresolved duplicate requires BLOCKED/NOT_TESTED on its affected cost"
                )


def verify_formalities(
    context_path: Path,
    plan: dict[str, Any],
    *,
    openssl: Path,
    trusted_roots: Path | None = None,
    crls: Path | None = None,
    intermediates: Path | None = None,
    trust_basis: str | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Persist actual local verification for exact selected run evidence."""
    _, output, session = _bound(context_path)
    validate(plan, "formalities-plan.schema.json")
    inputs = indexed(session["inputs"], "evidence_id")
    ids = [plan["document_evidence_id"]]
    if plan["signature_evidence_id"] is not None:
        ids.append(plan["signature_evidence_id"])
    if set(ids) - set(inputs):
        raise ContractError("Formalities may read only this run's selected evidence")
    if (plan["format"] == "PDF") != (plan["signature_evidence_id"] is None):
        raise ContractError(
            "PDF uses its embedded signature; other formats need exact signature evidence"
        )
    if trusted_roots is not None:
        _text(trust_basis, "independently configured trust basis")
    elif crls is not None or intermediates is not None:
        raise ContractError(
            "Revocation/intermediate configuration requires explicit trust roots"
        )
    document = output / inputs[plan["document_evidence_id"]]["path"]
    options: dict[str, Any] = {
        "openssl": openssl,
        "at": at or datetime.now(timezone.utc),
        "trusted_roots": trusted_roots,
        "crls": crls,
    }
    if plan["format"] == "PDF":
        verification = verify_pdf(document, **options)
    else:
        signature = output / inputs[plan["signature_evidence_id"]]["path"]
        if plan["format"].startswith("CMS_"):
            verification = verify_cms(
                signature,
                document,
                detached=plan["format"] == "CMS_DETACHED",
                **options,
            )
        else:
            if trusted_roots is None:
                raise ContractError(
                    "Timestamp verification requires independently configured TSA roots"
                )
            verification = verify_timestamp(
                signature,
                document,
                intermediates=intermediates,
                token=plan["format"] == "RFC3161_TOKEN",
                **options,
            )
    snapshots = {}
    for name, path in (
        ("trusted_roots", trusted_roots),
        ("crls", crls),
        ("intermediates", intermediates),
    ):
        if path is not None:
            if (
                path.is_symlink()
                or not path.is_file()
                or path.stat().st_size > MAX_BYTES
            ):
                raise ContractError(
                    "Trust configuration must use bounded regular files"
                )
            raw = path.read_bytes()
            if not raw or len(raw) > MAX_BYTES:
                raise ContractError("Trust configuration is empty or too large")
            # Compare retained bytes, not a second pathname read, with the provider.
            for item in verification.get("signatures", [verification]):
                checked_hashes = item.get("input_sha256", {})
                if (
                    name in checked_hashes
                    and hashlib.sha256(raw).hexdigest() != checked_hashes[name]
                ):
                    raise ContractError(
                        "Trust configuration changed during verification"
                    )
            snapshots[name] = raw
    record = {
        "schema_version": "1.0",
        "run_id": session["run_id"],
        "evidence_hash": canonical_hash(session["inputs"]),
        "plan": plan,
        "trust_basis": trust_basis,
        "verification": verification,
        "trust_snapshot_sha256": {
            name: hashlib.sha256(raw).hexdigest() for name, raw in snapshots.items()
        },
    }
    digest = canonical_hash(record)
    destination = output / f"formalities_{digest}"
    destination.mkdir(mode=0o700)
    _new(destination / "verification.json", _dump(record))
    for name, raw in snapshots.items():
        _new(destination / f"{name}.pem", raw)
    _new(
        destination / "review.md",
        "# Verifica tecnica di firma e marca\n\n"
        + "Esiti tecnici sui documenti selezionati. Poteri, qualifica, scadenze applicabili e conservazione richiedono riesame separato.\n\n"
        + "```json\n"
        + _dump(verification)
        + "```\n",
    )
    return {"formalities_digest": digest, "output_dir": str(destination), **record}


def _scopes(
    case: dict[str, Any],
) -> list[tuple[str, dict[str, Any], list[str], set[str]]]:
    """Expand explicit case structure, not semantic eligibility, into review work."""
    scopes = [
        (
            "case",
            case,
            list(CASE_GATES) + ["COMMUNICATION", "FINAL_REVIEW", "SOURCE_PREFLIGHT"],
            {"ALL", "EXTRAORDINARY"},
        )
    ]
    premial_ips = {a["ip_id"] for a in case["allocations"] if a["mode"] == "PREMIAL"}
    for ip in case["ips"]:
        branches = {"ALL", ip["type"]}
        gates = list(IP_GATES)
        if len(case["ips"]) > 1:
            branches.add("MULTI_IP")
        if ip["outsourced"]:
            branches.add("OUTSOURCED")
            gates.append("OUTSOURCING")
        if ip["ip_id"] in premial_ips:
            branches.add("PREMIAL")
            if ip["type"] == "SOFTWARE":
                branches.add("PREMIAL_SOFTWARE")
            gates.append("PREMIAL")
        scopes.append(("ip:" + ip["ip_id"], ip, gates, branches))
    costs = indexed(case["costs"], "cost_id")
    for allocation in case["allocations"]:
        scopes.append(
            (
                "allocation:" + allocation["allocation_id"],
                allocation,
                list(LINE_GATES),
                {"ALL", "RD_OVERLAP", costs[allocation["cost_id"]]["category"]},
            )
        )
    if case["penalty_protection"]["requested"]:
        scopes.append(
            (
                "penalty",
                case["penalty_protection"],
                [
                    "DOC_A",
                    "DOC_B",
                    "SIGNATURE",
                    "TIMESTAMP",
                    "COMMUNICATION",
                    "RETENTION",
                ],
                {"ALL", "PENALTY_REQUESTED"},
            )
        )
    return scopes


def _requirements(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Require every catalog child within the declared structural branch."""
    catalog = read_json(ROOT / "config/control_catalog.json")["controls"]
    return [
        {"key": scope + "/" + control["control_id"], "scope": scope, **control}
        for scope, _, gates, branches in _scopes(case)
        for control in catalog
        if control["gate"] in gates and control["branch"] in branches
    ]


def _check_proposal(
    proposal: dict[str, Any], session: dict[str, Any]
) -> dict[str, Any]:
    required_fields = {"case", "rules", "controls", "narratives"}
    if not required_fields <= set(proposal) or set(proposal) - required_fields - {
        "casebook",
        "normalization_digest",
    }:
        raise ContractError(
            "Proposal needs case, rules, controls, narratives and optional casebook/normalization_digest"
        )
    result = copy.deepcopy(proposal)
    case, rules = result["case"], result["rules"]
    validate(case, "case.schema.json")
    validate(rules, "ruleset.schema.json")
    if (
        case["case_id"] != session["run_id"]
        or case["demo"] != session["demo"]
        or rules["demo"] != session["demo"]
    ):
        raise ContractError("Proposal identity/demo differs from bound run")
    expected = [
        {key: row[key] for key in ("evidence_id", "path", "sha256", "description")}
        for row in session["inputs"]
    ]
    if case["evidence"] != expected:
        raise ContractError("Proposal must retain the exact selected evidence register")
    indexed(case["ips"], "ip_id")
    indexed(case["costs"], "cost_id")
    indexed(case["costs"], "ledger_row_key")
    indexed(case["allocations"], "allocation_id")
    if any(
        a["cost_id"] not in {c["cost_id"] for c in case["costs"]}
        for a in case["allocations"]
    ):
        raise ContractError("Unknown cost reference")
    requirements = _requirements(case)
    required = {row["key"] for row in requirements}
    if not isinstance(result["controls"], list):
        raise ContractError("Controls must be an array")
    controls = indexed(result["controls"], "key")
    if set(controls) - required:
        raise ContractError("Control outside declared case scope")
    evidence_ids = {r["evidence_id"] for r in expected}
    source_ids = {r["source_id"] for r in rules["sources"]}
    for row in controls.values():
        if (
            set(row) != {"key", "status", "conclusion", "evidence_ids", "source_ids"}
            or row["status"] not in STATUSES
        ):
            raise ContractError("Invalid detailed control contract")
        _text(row["conclusion"], "control rationale")
        for field, allowed in (
            ("evidence_ids", evidence_ids),
            ("source_ids", source_ids),
        ):
            if (
                not isinstance(row[field], list)
                or any(not isinstance(x, str) for x in row[field])
                or not set(row[field]) <= allowed
            ):
                raise ContractError("Unknown control evidence/source reference")
        if row["status"] in ("PASS", "FAIL") and (
            not row["evidence_ids"] or not row["source_ids"]
        ):
            raise ContractError("Substantive decision requires evidence and sources")
    if not isinstance(result["narratives"], list):
        raise ContractError("Narratives must be an array")
    for row in result["narratives"]:
        if set(row) != {"section", "text", "evidence_ids", "locator"} or row[
            "section"
        ] not in ("A", "B"):
            raise ContractError(
                "Narrative needs section A/B, text, evidence_ids and locator"
            )
        _text(row["text"], "narrative")
        _text(row["locator"], "page/row/section locator")
        if (
            not isinstance(row["evidence_ids"], list)
            or not row["evidence_ids"]
            or not set(row["evidence_ids"]) <= evidence_ids
        ):
            raise ContractError("Narrative must cite selected evidence")
    result["controls"] = [
        controls.get(
            row["key"],
            {
                "key": row["key"],
                "status": "NOT_TESTED",
                "conclusion": row["question"],
                "evidence_ids": [],
                "source_ids": [],
            },
        )
        for row in requirements
    ]
    if "casebook" in result:
        checked = check_casebook(result["casebook"], case, rules, required)
        for gap in checked["gaps"]:
            if (
                gap["control_key"] in controls
                and controls[gap["control_key"]]["status"] == "PASS"
            ):
                raise ContractError(
                    "PASS contradicts missing casebook records: " + gap["control_key"]
                )
    # Prefilled global PASS rows must never bypass detailed review.
    case["controls"] = []
    for row in case["ips"] + case["allocations"]:
        row["controls"] = []
    case["penalty_protection"]["controls"] = []
    return result


def _proposal(output: Path, digest: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ContractError("Invalid proposal digest")
    result = _read(output / f"proposal_{digest}.json")
    if canonical_hash(result) != digest:
        raise ContractError("Proposal changed after review")
    return result


def propose(context_path: Path, payload: dict[str, Any]) -> dict[str, str]:
    """Persist the model's proposal and readable review; never approve it."""
    _, output, session = _bound(context_path)
    proposal = _check_proposal(payload, session)
    if "normalization_digest" in proposal:
        record = _normalization(output, session, proposal["normalization_digest"])
        _bind_normalized_costs(proposal, record)
        proposal["normalization_record"] = record
    else:
        # Legacy canonical CSV path still requires exact selected-row equality.
        records = indexed(session["inputs"], "evidence_id")
        cost_evidence = {row["evidence_id"] for row in proposal["case"]["costs"]}
        if not cost_evidence <= set(records):
            raise ContractError("Cost evidence is outside the selected run")
        expected_costs = [
            row
            for evidence_id in sorted(cost_evidence)
            for row in _ledger_rows(output, records[evidence_id])
        ]
        if indexed(expected_costs, "cost_id") != indexed(
            proposal["case"]["costs"], "cost_id"
        ):
            raise ContractError("Cost population differs from selected mapped ledger")
    digest = canonical_hash(proposal)
    _new(output / f"proposal_{digest}.json", _dump(proposal))
    rows = [
        "# Patent Box — proposta da rivedere",
        "",
        "BOZZA. Nessuna decisione professionale registrata.",
        "",
        f"Riferimento: {digest}",
        "",
        "## Perimetro e importi proposti",
        "",
        f"Periodo richiesto: {proposal['case']['claim_period_id']}",
        f"Totale contabile selezionato: EUR {proposal['case']['ledger_control_total']}",
        "",
    ]
    for ip in proposal["case"]["ips"]:
        rows.append(
            f"- Bene {ip['ip_id']}: {ip['name']} ({ip['type']}); {ip['description']}"
        )
    for allocation in proposal["case"]["allocations"]:
        rows.append(
            f"- Quota {allocation['allocation_id']} / {allocation['mode']}: "
            f"costo {allocation['cost_id']}, bene {allocation['ip_id']}, "
            f"progetto {allocation['project_id']}, attività {allocation['activity_id']}; "
            f"redditi EUR {allocation['income_amount']}, IRAP EUR {allocation['irap_amount']}. "
            f"Criterio: {allocation['allocation_method']}"
        )
    if "normalization_record" in proposal:
        rows += ["", normalization_markdown(proposal["normalization_record"]["result"])]
    if "casebook" in proposal:
        rows += [
            "",
            casebook_markdown(proposal["casebook"]),
            missing_documents_markdown(proposal["casebook"]),
        ]
    rows += ["", "## Controlli"]
    for item in proposal["controls"]:
        rows += [
            "",
            f"### {item['key']} — {item['status']}",
            item["conclusion"],
            "Prove: " + ", ".join(item["evidence_ids"]),
            "Fonti: " + ", ".join(item["source_ids"]),
        ]
    rows += ["", "## Testi proposti", ""]
    for paragraph in proposal["narratives"]:
        rows += [
            f"Sezione {paragraph['section']}: {paragraph['text']}",
            "Prove: "
            + ", ".join(paragraph["evidence_ids"])
            + "; "
            + paragraph["locator"],
            "",
        ]
    rules = proposal["rules"]
    rows += [
        "## Regole proposte",
        "",
        f"Versione {rules['ruleset_id']} / {rules['version']}; stato {rules['status']}",
        f"Maggiorazione proposta: {rules['enhancement_rate']}; finestra premiale: {rules['premial_periods']} periodi fiscali.",
        f"Fonti controllate il {rules['sources_checked_on']}; revisione regole del {rules['reviewed_on']}.",
    ]
    for source in rules["sources"]:
        rows.append(
            f"- {source['source_id']}: prova {source['snapshot_evidence_id']}; SHA-256 {source['snapshot_sha256']}"
        )
    rows += [
        "",
        f"Record completo: proposal_{digest}.json",
        "",
        "Confermare esplicitamente la proposta identificata sopra oppure chiedere modifiche. L'identità dichiarata non è autenticata professionalmente. La conferma conserva anche controlli aperti: non li trasforma in PASS.",
    ]
    _new(output / f"review_{digest}.md", "\n".join(rows) + "\n")
    return {
        "proposal_digest": digest,
        "review_path": str(output / f"review_{digest}.md"),
    }


def review(
    context_path: Path,
    *,
    digest: str,
    reviewer: str,
    confirmation_ref: str,
    confirmed: bool,
    synthetic: bool = False,
) -> dict[str, Any]:
    """Record exact explicit host-dialog review, labelled with its real assurance."""
    _, output, session = _bound(context_path)
    _proposal(output, digest)
    if confirmed is not True:
        raise ContractError("Explicit confirmation of this proposal is required")
    if synthetic and not session["demo"]:
        raise ContractError("Synthetic review cannot apply to a real case")
    if session["demo"] and not synthetic:
        raise ContractError("Synthetic acceptance must be labelled synthetic")
    record = {
        "schema_version": "1.0",
        "run_id": session["run_id"],
        "proposal_digest": digest,
        "reviewer": _text(reviewer, "reviewer"),
        "confirmation_ref": _text(confirmation_ref, "host confirmation reference"),
        "confirmed": True,
        "reviewed_on": session["as_of"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "identity_assurance": (
            "SYNTHETIC_ACCEPTANCE" if synthetic else session["identity_assurance"]
        ),
        "evidence_hash": canonical_hash(session["inputs"]),
        "signature": None,
    }
    _new(output / f"decision_{digest}.json", _dump(record))
    return record


def prepare_professional_review(
    context_path: Path,
    *,
    digest: str,
    source_scan: Path,
    action: str = "REVIEW_CONTROLS",
    at: datetime | None = None,
    previous_digest: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Prepare a bounded readable request; signing occurs in the chosen provider."""
    context, output, session = _bound(context_path)
    return professional_review.prepare_review(
        context,
        session,
        output,
        _proposal(output, digest),
        source_scan=source_scan,
        action=action,
        previous_digest=previous_digest,
        reason=reason,
        at=at or datetime.now(timezone.utc),
    )


def accept_professional_review(
    context_path: Path,
    *,
    digest: str,
    request_digest: str,
    signature: Path,
    mandate: Path,
    mandate_signature: Path,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Retain a certificate-authenticated decision for this exact run version."""
    context, output, session = _bound(context_path)
    return professional_review.accept_review(
        context,
        session,
        output,
        _proposal(output, digest),
        request_digest=request_digest,
        signature=signature,
        mandate=mandate,
        mandate_signature=mandate_signature,
        at=at or datetime.now(timezone.utc),
    )


def _aggregate(proposal: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    case = copy.deepcopy(proposal["case"])
    detailed = indexed(proposal["controls"], "key")
    requirements = _requirements(case)
    for scope, target, gates, _ in _scopes(case):
        if scope == "case":
            gates = list(CASE_GATES)
        for gate in gates:
            children = [
                detailed[row["key"]]
                for row in requirements
                if row["scope"] == scope and row["gate"] == gate
            ]
            states = {row["status"] for row in children}
            status = next(
                (
                    state
                    for state in ("FAIL", "BLOCKED", "NOT_TESTED", "WARNING")
                    if state in states
                ),
                "PASS" if children else "NOT_TESTED",
            )
            target["controls"].append(
                {
                    "gate": gate,
                    "status": status,
                    "conclusion": " | ".join(
                        row["key"] + ": " + row["conclusion"] for row in children
                    ),
                    "evidence_ids": sorted(
                        {x for row in children for x in row["evidence_ids"]}
                    ),
                    "source_ids": sorted(
                        {x for row in children for x in row["source_ids"]}
                    ),
                    "reviewer": decision["reviewer"],
                    "reviewed_on": decision["reviewed_on"],
                }
            )
    return case


def _csv(rows: list[dict[str, Any]], fields: list[str]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        # Prevent spreadsheet formula interpretation in evidence-derived text.
        writer.writerow(
            {
                k: (
                    "'" + str(v)
                    if str(v).startswith(("=", "+", "-", "@", "\t", "\r"))
                    else v
                )
                for k, v in row.items()
            }
        )
    return stream.getvalue()


def calculate_draft(
    context_path: Path, *, digest: str, at: datetime | None = None
) -> dict[str, Any]:
    """Calculate one fresh reviewed snapshot and compose traceable draft artifacts."""
    context, output, session = _bound(context_path)
    proposal = _proposal(output, digest)
    if "normalization_digest" in proposal:
        record = _normalization(output, session, proposal["normalization_digest"])
        if record != proposal["normalization_record"]:
            raise ContractError("Normalization differs from the reviewed proposal")
        _bind_normalized_costs(proposal, record)
    professional_review.verify_reopening(
        context, session, output, proposal, at=at or datetime.now(timezone.utc)
    )
    authenticated = output / f"authenticated_decision_{digest}.json"
    decision_path = (
        authenticated if authenticated.exists() else output / f"decision_{digest}.json"
    )
    if authenticated.exists():
        validation_time = at or datetime.now(timezone.utc)
        if (
            not session["demo"]
            and session["as_of"] != validation_time.date().isoformat()
        ):
            raise ContractError(
                "Real calculation needs a current dated archive run and source review"
            )
        decision = professional_review.verify_control_review(
            context, session, output, proposal, at=validation_time
        )
    else:
        decision = _read(decision_path)
    if (
        decision["run_id"] != session["run_id"]
        or decision["proposal_digest"] != digest
        or decision["evidence_hash"] != canonical_hash(session["inputs"])
        or decision["confirmed"] is not True
    ):
        raise ContractError("Review is not bound to this run and these inputs")
    _text(decision["reviewer"], "reviewer")
    if not session["demo"] and not authenticated.exists():
        raise ContractError(
            "Real calculation is blocked without reviewed legal sources and an authenticated professional decision; preparation remains available"
        )
    if (
        session["demo"]
        and not authenticated.exists()
        and decision["identity_assurance"] != "SYNTHETIC_ACCEPTANCE"
    ):
        raise ContractError("Demo requires a labelled synthetic decision")
    case = _aggregate(proposal, decision)
    result = calculate(
        case, proposal["rules"], evidence_root=output, as_of=session["as_of"]
    )
    document = compose_dossier(proposal, result, decision)
    pdf_bytes = render_pdf(document)
    docx_bytes = render_docx(document)
    destination = output / f"calculation_{digest}"
    destination.mkdir(mode=0o700)
    _new(destination / "case.json", _dump(case))
    _new(destination / "rules.json", _dump(proposal["rules"]))
    _new(destination / "result.json", _dump(result))
    _new(destination / "dossier_document.json", _dump(document))
    _new(destination / "fascicolo_A_B.docx", docx_bytes)
    _new(destination / "fascicolo_A_B.pdf", pdf_bytes)
    _new(destination / "workpaper.md", markdown(result))
    if "normalization_record" in proposal:
        record = proposal["normalization_record"]
        _new(destination / "ledger_normalization.json", _dump(record))
        _new(
            destination / "ledger_normalization.md",
            normalization_markdown(record["result"]),
        )
    controls = [
        {
            **row,
            "evidence_ids": ";".join(row["evidence_ids"]),
            "source_ids": ";".join(row["source_ids"]),
            "reviewer": decision["reviewer"],
            "reviewed_on": decision["reviewed_on"],
        }
        for row in proposal["controls"]
    ]
    _new(
        destination / "control_matrix.csv",
        _csv(
            controls,
            [
                "key",
                "status",
                "conclusion",
                "evidence_ids",
                "source_ids",
                "reviewer",
                "reviewed_on",
            ],
        ),
    )
    costs, allocations = indexed(case["costs"], "cost_id"), indexed(
        case["allocations"], "allocation_id"
    )
    trace = []
    for line in result["lines"]:
        cost, allocation = costs[line["cost_id"]], allocations[line["allocation_id"]]
        trace.append(
            {
                **line,
                "reasons": ";".join(line["reasons"]),
                "ledger_row_key": cost["ledger_row_key"],
                "period_id": cost["period_id"],
                "evidence_id": cost["evidence_id"],
                "activity_id": allocation["activity_id"],
                "project_id": allocation["project_id"],
                "allocation_method": allocation["allocation_method"],
            }
        )
    fields = [
        "allocation_id",
        "cost_id",
        "ip_id",
        "mode",
        "status",
        "income_amount",
        "irap_amount",
        "reasons",
        "ledger_row_key",
        "period_id",
        "evidence_id",
        "activity_id",
        "project_id",
        "allocation_method",
    ]
    _new(destination / "cost_reconciliation.csv", _csv(trace, fields))
    open_controls = [row for row in proposal["controls"] if row["status"] != "PASS"]
    missing = (
        "# Documenti mancanti e questioni aperte\n\n"
        + (
            "\n".join(
                f"- {row['key']} ({row['status']}): {row['conclusion']}"
                for row in open_controls
            )
            or "Nessun controllo aperto nella simulazione; la completezza professionale non è certificata."
        )
        + "\n"
    )
    _new(destination / "missing_documents.md", missing)
    dossier = [
        "# Patent Box — fascicolo A/B",
        "",
        "**BOZZA SINTETICA DA RIVEDERE. NON FIRMATA.**",
        "",
        f"Pratica {session['run_id']}; revisione {digest}.",
        "",
        "Questa struttura di lavoro non attesta idoneità documentale o spettanza.",
    ]
    for section in ("A", "B"):
        dossier += ["", f"## Sezione {section}"]
        paragraphs = [r for r in proposal["narratives"] if r["section"] == section]
        for row in paragraphs:
            dossier += [
                "",
                row["text"],
                "Riferimenti: "
                + ", ".join(row["evidence_ids"])
                + "; "
                + row["locator"]
                + ". Testo proposto e riesaminato nella simulazione.",
            ]
        if not paragraphs:
            dossier.append("DA COMPLETARE: testo e prove della sezione non forniti.")
        if section == "B":
            dossier += ["", markdown(result)]
    dossier += [
        "",
        "## Prove selezionate",
        "",
        *[
            f"- {r['evidence_id']}: {r['description']}; SHA-256 {r['sha256']}"
            for r in session["inputs"]
        ],
        "",
        missing,
        "## Adempimenti e limiti",
        "",
        "Fascicolo in bozza. Firma del fascicolo, marca, poteri, modello dichiarativo e conservazione richiedono esiti separati. Nessun invio o monitoraggio attivato.",
    ]
    if "casebook" in proposal:
        book = proposal["casebook"]
        assessment = check_casebook(
            book, case, proposal["rules"], {r["key"] for r in proposal["controls"]}
        )
        declaration = reconcile_declarations(
            book["declarations"], result, assessment["incentives"]
        )
        _new(destination / "casebook.json", _dump(book))
        _new(destination / "casebook.md", casebook_markdown(book))
        _new(destination / "document_requests.md", missing_documents_markdown(book))
        _new(
            destination / "incentive_matrix.json",
            _dump({"rows": assessment["incentives"]}),
        )
        _new(destination / "declaration_bridge.json", _dump(declaration))
        _new(
            destination / "open_casebook_items.json",
            _dump({"gaps": assessment["gaps"]}),
        )
        _new(
            destination / "office_requests.json",
            _dump({"rows": book["office_requests"]}),
        )
        dossier += ["", casebook_markdown(book), missing_documents_markdown(book)]
    _new(destination / "fascicolo_A_B.md", "\n".join(dossier) + "\n")
    _new(
        destination / "case_summary.md",
        markdown(result)
        + "\n"
        + missing
        + (
            "\nPratica sintetica; UAT professionale non eseguita.\n"
            if session["demo"]
            else "\nCalcolo in bozza su proposta riesaminata. Approvazione finale del fascicolo separata.\n"
        ),
    )
    manifest = {
        "run_id": session["run_id"],
        "proposal_digest": digest,
        "decision_sha256": file_hash(decision_path),
        "previous_results": sorted(
            path.name for path in output.glob("calculation_*") if path != destination
        ),
        "artifacts": {
            path.name: file_hash(path) for path in sorted(destination.iterdir())
        },
    }
    _new(destination / "manifest.json", _dump(manifest))
    return {"output_dir": str(destination), "result": result}


def main(argv: list[str] | None = None) -> int:
    """Expose host-operated actions; users do not edit JSON or run Terminal."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-engagement", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("initialize")
    init.add_argument("--as-of", required=True)
    init.add_argument("--demo", action="store_true")
    ledger = commands.add_parser("import-ledger")
    ledger.add_argument("--evidence-id", required=True)
    inspect = commands.add_parser("inspect-ledger")
    inspect.add_argument("--evidence-id", required=True)
    inspect.add_argument("--options", type=Path, required=True)
    normalize = commands.add_parser("normalize-ledger")
    normalize.add_argument("--plan", type=Path, required=True)
    prepare_review = commands.add_parser("prepare-professional-review")
    prepare_review.add_argument("--digest", required=True)
    prepare_review.add_argument("--source-scan", type=Path, required=True)
    prepare_review.add_argument(
        "--action",
        choices=["REVIEW_CONTROLS", "APPROVE_DOSSIER", "REOPEN_CASE"],
        default="REVIEW_CONTROLS",
    )
    prepare_review.add_argument("--previous-digest")
    prepare_review.add_argument("--reason")
    accept_review = commands.add_parser("accept-professional-review")
    accept_review.add_argument("--digest", required=True)
    accept_review.add_argument("--request-digest", required=True)
    accept_review.add_argument("--signature", type=Path, required=True)
    accept_review.add_argument("--mandate", type=Path, required=True)
    accept_review.add_argument("--mandate-signature", type=Path, required=True)
    formal = commands.add_parser("verify-formalities")
    formal.add_argument("--plan", type=Path, required=True)
    formal.add_argument("--openssl", type=Path, required=True)
    formal.add_argument("--trusted-roots", type=Path)
    formal.add_argument("--crls", type=Path)
    formal.add_argument("--intermediates", type=Path)
    formal.add_argument("--trust-basis")
    proposal = commands.add_parser("propose")
    proposal.add_argument("--proposal", type=Path, required=True)
    decision = commands.add_parser("review")
    decision.add_argument("--digest", required=True)
    decision.add_argument("--reviewer", required=True)
    decision.add_argument("--confirmation-ref", required=True)
    decision.add_argument("--confirmed", action="store_true")
    decision.add_argument("--synthetic", action="store_true")
    calc = commands.add_parser("calculate")
    calc.add_argument("--digest", required=True)
    args = parser.parse_args(argv)
    if args.command == "initialize":
        result = initialize(args.client_engagement, as_of=args.as_of, demo=args.demo)
    elif args.command == "import-ledger":
        result = import_ledger(args.client_engagement, evidence_id=args.evidence_id)
    elif args.command in ("inspect-ledger", "normalize-ledger"):
        _, output = _context(args.client_engagement)
        input_path = args.options if args.command == "inspect-ledger" else args.plan
        if not input_path.resolve(strict=True).is_relative_to(output.resolve()):
            raise ContractError(
                "Write the model mapping inside the bound output directory"
            )
        if args.command == "inspect-ledger":
            result = inspect_ledger(
                args.client_engagement,
                evidence_id=args.evidence_id,
                options=_read(input_path),
            )
        else:
            result = normalize_ledger(args.client_engagement, _read(input_path))
    elif args.command == "prepare-professional-review":
        result = prepare_professional_review(
            args.client_engagement,
            digest=args.digest,
            source_scan=args.source_scan,
            action=args.action,
            previous_digest=args.previous_digest,
            reason=args.reason,
        )
    elif args.command == "accept-professional-review":
        result = accept_professional_review(
            args.client_engagement,
            digest=args.digest,
            request_digest=args.request_digest,
            signature=args.signature,
            mandate=args.mandate,
            mandate_signature=args.mandate_signature,
        )
    elif args.command == "verify-formalities":
        _, output = _context(args.client_engagement)
        if not args.plan.resolve(strict=True).is_relative_to(output.resolve()):
            raise ContractError(
                "Write the verification plan inside the bound output directory"
            )
        result = verify_formalities(
            args.client_engagement,
            _read(args.plan),
            openssl=args.openssl,
            trusted_roots=args.trusted_roots,
            crls=args.crls,
            intermediates=args.intermediates,
            trust_basis=args.trust_basis,
        )
    elif args.command == "propose":
        context, output = _context(args.client_engagement)
        proposal_path = args.proposal.resolve(strict=True)
        if not proposal_path.is_relative_to(output.resolve()):
            raise ContractError(
                "Write the model proposal inside the bound output directory"
            )
        result = propose(args.client_engagement, _read(proposal_path))
    elif args.command == "review":
        result = review(
            args.client_engagement,
            digest=args.digest,
            reviewer=args.reviewer,
            confirmation_ref=args.confirmation_ref,
            confirmed=args.confirmed,
            synthetic=args.synthetic,
        )
    else:
        result = calculate_draft(args.client_engagement, digest=args.digest)
    sys.stdout.write(_dump(result))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as error:
        LOGGER.error("Patent Box blocked: %s", error)
        raise SystemExit(2) from error
