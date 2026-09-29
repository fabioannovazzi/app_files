"""Bound Patent Box preparation; semantic proposals remain operator-reviewed.

Fixed logic is limited to exact paths, schemas, reference closure, review
freshness and Decimal arithmetic. It never decides legal eligibility.
"""

from __future__ import annotations

import argparse
import copy
import csv
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

from patent_box.contracts import (
    ContractError,
    canonical_hash,
    file_hash,
    indexed,
    read_json,
    validate,
)
from patent_box.engine import CASE_GATES, IP_GATES, LINE_GATES, calculate
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
        + "\nChiarire soggetto e periodo, software e diritti, attività, costi, opzioni pregresse e incentivi. Leggere solo i documenti selezionati e chiedere ciò che manca.\n\n"
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


def _requirements(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand declared structural scope; legal applicability remains in review."""
    catalog = read_json(ROOT / "config/control_catalog.json")["controls"]
    scopes = [
        (
            "case",
            case,
            list(CASE_GATES) + ["COMMUNICATION", "FINAL_REVIEW", "SOURCE_PREFLIGHT"],
            {"ALL"},
        )
    ]
    for ip in case["ips"]:
        branches = {"ALL", "SOFTWARE"}
        if len(case["ips"]) > 1:
            branches.add("MULTI_IP")
        if ip["outsourced"]:
            branches.add("OUTSOURCED")
        scopes.append(
            (
                "ip:" + ip["ip_id"],
                ip,
                list(IP_GATES) + (["OUTSOURCING"] if ip["outsourced"] else []),
                branches,
            )
        )
    costs = indexed(case["costs"], "cost_id")
    for allocation in case["allocations"]:
        branches = {"ALL", "RD_OVERLAP", costs[allocation["cost_id"]]["category"]}
        scopes.append(
            (
                "allocation:" + allocation["allocation_id"],
                allocation,
                list(LINE_GATES),
                branches,
            )
        )
    requirements = []
    for scope, _, gates, branches in scopes:
        for control in catalog:
            if control["gate"] in gates and control["branch"] in branches:
                requirements.append(
                    {
                        "key": scope + "/" + control["control_id"],
                        "scope": scope,
                        **control,
                    }
                )
    return requirements


def _check_proposal(
    proposal: dict[str, Any], session: dict[str, Any]
) -> dict[str, Any]:
    if set(proposal) != {"case", "rules", "controls", "narratives"}:
        raise ContractError("Proposal needs exactly case, rules, controls, narratives")
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
    if (
        any(
            ip["type"] != "SOFTWARE" or ip["premial_event"] is not None
            for ip in case["ips"]
        )
        or any(row["mode"] != "ORDINARY" for row in case["allocations"])
        or case["prior_claims"]
    ):
        raise ContractError(
            "First integration supports ordinary software only; specialist history/premial requires a dedicated workflow"
        )
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
        raise ContractError("Control outside declared ordinary-software scope")
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
    # Exact equality proves the normalized cost population still comes from
    # the selected, explicitly mapped CSV; a matching ID alone is insufficient.
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
        "## Dati, importi e narrazione",
        "",
        "```json",
        _dump(proposal["case"]),
        "```",
        "",
        "## Controlli",
    ]
    for item in proposal["controls"]:
        rows += [
            "",
            f"### {item['key']} — {item['status']}",
            item["conclusion"],
            "Prove: " + ", ".join(item["evidence_ids"]),
            "Fonti: " + ", ".join(item["source_ids"]),
        ]
    rows += [
        "",
        "## Testi proposti",
        _dump(proposal["narratives"]),
        "",
        "## Regole proposte",
        "```json",
        _dump(proposal["rules"]),
        "```",
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


def _aggregate(proposal: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    case = copy.deepcopy(proposal["case"])
    detailed = indexed(proposal["controls"], "key")
    requirements = _requirements(case)
    scopes = (
        [("case", case, CASE_GATES)]
        + [
            (
                "ip:" + row["ip_id"],
                row,
                (*IP_GATES, *(("OUTSOURCING",) if row["outsourced"] else ())),
            )
            for row in case["ips"]
        ]
        + [
            ("allocation:" + row["allocation_id"], row, LINE_GATES)
            for row in case["allocations"]
        ]
    )
    for scope, target, gates in scopes:
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


def calculate_draft(context_path: Path, *, digest: str) -> dict[str, Any]:
    """Calculate one fresh reviewed snapshot and compose traceable draft artifacts."""
    _, output, session = _bound(context_path)
    proposal = _proposal(output, digest)
    decision = _read(output / f"decision_{digest}.json")
    if (
        decision["run_id"] != session["run_id"]
        or decision["proposal_digest"] != digest
        or decision["evidence_hash"] != canonical_hash(session["inputs"])
        or decision["confirmed"] is not True
    ):
        raise ContractError("Review is not bound to this run and these inputs")
    _text(decision["reviewer"], "reviewer")
    if not session["demo"]:
        raise ContractError(
            "Real calculation is blocked pending reviewed legal sources and an authenticated professional review adapter; preparation remains available"
        )
    if decision["identity_assurance"] != "SYNTHETIC_ACCEPTANCE":
        raise ContractError("Demo requires a labelled synthetic decision")
    case = _aggregate(proposal, decision)
    result = calculate(
        case, proposal["rules"], evidence_root=output, as_of=session["as_of"]
    )
    destination = output / f"calculation_{digest}"
    destination.mkdir(mode=0o700)
    _new(destination / "case.json", _dump(case))
    _new(destination / "rules.json", _dump(proposal["rules"]))
    _new(destination / "result.json", _dump(result))
    _new(destination / "workpaper.md", markdown(result))
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
        "Firma, marca, modello dichiarativo, coordinamento quantitativo incentivi e autenticazione professionale: NON VERIFICATI. Regole reali DRAFT. Nessun invio o monitoraggio attivato.",
    ]
    _new(destination / "fascicolo_A_B.md", "\n".join(dossier) + "\n")
    _new(
        destination / "case_summary.md",
        markdown(result)
        + "\n"
        + missing
        + "\nRevisione sintetica; UAT professionale non eseguita.\n",
    )
    manifest = {
        "run_id": session["run_id"],
        "proposal_digest": digest,
        "decision_sha256": file_hash(output / f"decision_{digest}.json"),
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
