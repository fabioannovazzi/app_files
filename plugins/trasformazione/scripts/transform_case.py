"""Persist and review synthetic transformation cases; never execute legal actions.

Fixed rules here are justified by exact arithmetic, referential integrity and
approval auditability. They do not select law, classify entities or interpret
documents. The calling model authors proposals; the operator records review.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import logging
import re
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any

__all__ = ["CaseStore", "calculate", "create_case", "main"]

LOG = logging.getLogger(__name__)
KINDS = {
    "finding": ("statement", "category", "rationale", "alternatives", "confidence"),
    "participant": (
        "name",
        "capital_share",
        "vote_share",
        "profit_share",
        "title",
        "work_share",
        "consent",
    ),
    "creditor": (
        "name",
        "debt",
        "origin_date",
        "guarantee",
        "consent",
        "receipt",
        "receipt_date",
        "release_assessment",
        "opposition_assessment",
    ),
    "reserve": (
        "amount",
        "origin",
        "year",
        "regime",
        "restrictions",
        "balance_sheet",
        "uses",
        "prior_taxation",
    ),
    "asset": (
        "description",
        "book_value",
        "estimated_value",
        "tax_value",
        "business_destination",
        "accounting_decision",
        "tax_decision",
    ),
    "deadline": (
        "source_version",
        "trigger",
        "method",
        "extensions",
        "territory",
        "proposed_date",
        "approved_date",
        "receipt",
    ),
    "issue": (
        "question",
        "source_needed",
        "owner",
        "blocks",
        "closure_criterion",
        "resolution",
    ),
    "source": (
        "title",
        "url",
        "article",
        "publication_date",
        "effective_from",
        "applicability_from",
        "applicability_until",
        "transitional_conditions",
        "retrieved_at",
        "verification_status",
        "reviewer",
        "snapshot",
    ),
    "calculation": ("operation", "args"),
}
MONEY = {"debt", "amount", "book_value", "estimated_value", "tax_value"}
SHARES = {"capital_share", "vote_share", "profit_share", "work_share"}
ID = re.compile(r"[a-zA-Z0-9_-]{1,80}\Z")
REF = re.compile(r"([a-z]+):([a-zA-Z0-9_-]{1,80})(?:#([a-z_]+))?\Z")
STATES = {
    "draft",
    "evidence_pending",
    "analysis_ready",
    "professional_review",
    "approved_for_preparation",
    "blocked",
    "stale",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: nonempty text required")
    return value


def _cell(value: Any) -> str:
    """Render inert data without allowing Markdown links or embedded HTML."""
    if value is None:
        return "Da acquisire"
    if isinstance(value, dict):
        value = "; ".join(f"{key}: {item}" for key, item in value.items())
    if isinstance(value, list):
        value = "; ".join(str(item) for item in value) or "Nessuna indicata"
    text = html.escape(str(value), quote=False).replace("\n", " ").replace("\r", " ")
    for token in ("\\", "|", "[", "]", "`", "*", "_", "#"):
        text = text.replace(token, "\\" + token)
    return text


def _table(rows: list[dict[str, Any]], columns: dict[str, str]) -> str:
    if not rows:
        return "Non compilato in questo caso sintetico; nessuna verifica conclusa."
    lines = [
        "| " + " | ".join(columns.values()) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_cell(row.get(key)) for key in columns) + " |" for row in rows
    )
    return "\n".join(lines)


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid record identifier")
    return value


def _number(value: Any) -> Fraction:
    if not isinstance(value, str) or len(value) > 100 or "e" in value.lower():
        raise ValueError("Exact numeric string required; null is unknown, never zero")
    try:
        number = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Invalid finite decimal or rational") from exc
    if number < 0:
        raise ValueError("Negative value outside this arithmetic prototype")
    return number


def _format(value: Fraction) -> dict[str, str]:
    with localcontext() as context:
        context.prec = 220
        rounded = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return {"exact": str(value), "display": str(rounded)}


def calculate(operation: str, args: dict[str, Any]) -> dict[str, Any]:
    """Compute explicit inputs; return exact values and a disclosed display residue."""
    if operation == "capital_coverage":
        assets, liabilities, capital = (
            _number(args[key]) for key in ("assets", "liabilities", "capital")
        )
        if capital <= 0 or assets - liabilities < capital:
            raise ValueError("Insufficient arithmetic capital coverage")
        values = {
            "net_assets": assets - liabilities,
            "margin": assets - liabilities - capital,
        }
    elif operation in {"allocation", "work_allocation"}:
        capital = _number(args["capital"])
        shares = [_number(value) for value in args["shares"]]
        if capital <= 0 or not shares or sum(shares) != 1:
            raise ValueError(
                "Capital must be positive and shares must reconcile exactly to one"
            )
        if operation == "work_allocation":
            work = _number(args["work_share"])
            if not 0 < work < 1:
                raise ValueError(
                    "An explicitly determined work share between zero and one is required"
                )
            shares = [share * (1 - work) for share in shares] + [work]
        values = {
            f"participant_{i + 1}": capital * share for i, share in enumerate(shares)
        }
    elif operation == "reserve_balance":
        opening, distribution = _number(args["opening"]), _number(args["distribution"])
        if distribution > opening:
            raise ValueError("Distribution exceeds the selected reserve")
        values = {"balance": opening - distribution}
    elif operation == "qualified_gain":
        if args["qualification"] != "synthetic_assumption":
            raise ValueError(
                "Explicit synthetic qualification required; no tax treatment is inferred"
            )
        gain = _number(args["normal_value"]) - _number(args["tax_basis"])
        if gain < 0:
            raise ValueError(
                "Negative difference requires a separate professional assessment"
            )
        values = {"positive_difference": gain}
    else:
        raise ValueError("Unsupported arithmetic operation")
    result: dict[str, Any] = {
        "values": {key: _format(value) for key, value in values.items()},
        "policy": "Exact rational storage; display cents ROUND_HALF_UP; no residual allocation inferred",
        "legal_or_tax_approval": False,
    }
    if operation in {"allocation", "work_allocation"}:
        displayed = sum(Fraction(row["display"]) for row in result["values"].values())
        result["display_residue"] = _format(capital - displayed)
    return result


def _reference(value: str) -> tuple[str, str, str | None]:
    match = REF.fullmatch(value) if isinstance(value, str) else None
    if not match or match[1] not in {*KINDS, "evidence"}:
        raise ValueError(f"Invalid dependency reference: {value!r}")
    return match[1], match[2], match[3]


def _references(values: Any) -> list[str]:
    if not isinstance(values, list) or len(values) != len(set(values)):
        raise ValueError("Dependencies must be a list of unique references")
    for value in values:
        _reference(value)
    return values


def create_case(case_id: str, owner: str, purpose: str) -> dict[str, Any]:
    """Create an explicitly synthetic case with unknown attributes preserved."""
    return {
        "schema_version": 1,
        "workflow": "vera:trasformazione",
        "synthetic_only": True,
        "case": {
            "id": _identifier(case_id),
            "owner": _text(owner, "owner"),
            "purpose": _text(purpose, "purpose"),
            "jurisdiction": "IT",
            "initial_form": None,
            "final_form": None,
            "initial_tax_regime": None,
            "final_tax_regime": None,
            "initial_commerciality": None,
            "final_commerciality": None,
            "proposed_date": None,
            "actual_date": None,
        },
        "revision": 0,
        "records": {kind: {} for kind in (*KINDS, "evidence")},
        "branches": {},
        "decisions": [],
        "events": [],
    }


class CaseStore:
    """An append-only local case ledger; reviewer names are not authenticated signatures."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def initialize(self, case_id: str, owner: str, purpose: str) -> dict[str, Any]:
        if self.root.exists() and any(self.root.iterdir()):
            raise ValueError("Case directory must be new or empty")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.root / "history").mkdir(mode=0o700)
        (self.root / "evidence").mkdir(mode=0o700)
        return self._save(
            create_case(case_id, owner, purpose), "create_case", owner, None
        )

    def load(self) -> dict[str, Any]:
        files = sorted((self.root / "history").glob("*.json"))
        if not files:
            raise ValueError("No case history found")
        previous = None
        for revision, path in enumerate(files, 1):
            envelope = json.loads(path.read_text(encoding="utf-8"))
            state = envelope["state"]
            expected = _digest({"state": state, "previous": previous})
            if (
                envelope["digest"] != expected
                or envelope["previous"] != previous
                or state["revision"] != revision
            ):
                raise ValueError("Case history integrity mismatch")
            previous = expected
        if (
            state["synthetic_only"] is not True
            or state["workflow"] != "vera:trasformazione"
        ):
            raise ValueError("Only synthetic transformation cases are supported")
        self._verify_evidence(state)
        self._refresh(state)
        return state

    def _verify_evidence(self, state: dict[str, Any]) -> None:
        for record in state["records"]["evidence"].values():
            path = self.root / record["local_path"]
            if (
                not path.resolve().is_relative_to(self.root / "evidence")
                or path.is_symlink()
                or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]
            ):
                raise ValueError("Evidence integrity mismatch")

    def _save(
        self, state: dict[str, Any], action: str, actor: str, previous: str | None
    ) -> dict[str, Any]:
        _text(actor, "actor")
        self._refresh(state)
        state["revision"] += 1
        state["events"].append(
            {
                "at": _now(),
                "actor": actor,
                "action": action,
                "revision": state["revision"],
            }
        )
        envelope = {"state": state, "previous": previous}
        envelope["digest"] = _digest(envelope)
        path = self.root / "history" / f"{state['revision']:08d}.json"
        # Exclusive creation prevents a concurrent writer from silently losing work.
        with path.open("xb") as handle:
            handle.write(_bytes(envelope))
        path.chmod(0o600)
        return state

    def _current(self) -> tuple[dict[str, Any], str]:
        state = self.load()
        path = self.root / "history" / f"{state['revision']:08d}.json"
        return state, json.loads(path.read_text())["digest"]

    def _bindings(
        self, state: dict[str, Any], refs: list[str]
    ) -> tuple[dict[str, Any], list[str]]:
        bound: dict[str, Any] = {}
        missing: list[str] = []
        visiting: set[str] = set()

        def visit(ref: str) -> None:
            if ref in visiting:
                raise ValueError("Dependency cycle")
            if ref in bound:
                return
            kind, record_id, field = _reference(ref)
            record = state["records"][kind].get(record_id)
            value = record.get(field) if record is not None and field else record
            bound[ref] = value
            if value is None or value == "":
                missing.append(ref)
            if record:
                visiting.add(ref)
                for dependency in record["dependencies"]:
                    visit(dependency)
                visiting.remove(ref)

        for ref in refs:
            visit(ref)
        return bound, missing

    def _refresh(self, state: dict[str, Any]) -> None:
        for branch_id, branch in state["branches"].items():
            bound, missing = self._bindings(state, branch["dependencies"])
            blockers = [f"Missing evidence or value: {ref}" for ref in missing]
            calculations = {}
            for ref, record in bound.items():
                kind, _, field = _reference(ref)
                if kind == "calculation" and record and field is None:
                    try:
                        calculations[ref] = calculate(
                            record["operation"], record["args"]
                        )
                    except (ValueError, KeyError, TypeError) as exc:
                        blockers.append(f"{ref}: {exc}")
                if (
                    kind == "issue"
                    and record
                    and field is None
                    and record["blocks"]
                    and not record["resolution"]
                ):
                    blockers.append(f"Open research issue: {ref}: {record['question']}")
            digest = _digest(
                {
                    "case": state["case"],
                    "branch": {
                        key: branch[key]
                        for key in ("title", "owner", "next_step", "dependencies")
                    },
                    "bindings": bound,
                }
            )
            decisions = [
                item for item in state["decisions"] if item["branch_id"] == branch_id
            ]
            latest = decisions[-1] if decisions else None
            if latest and latest["proposal_digest"] != digest:
                status = "stale"
            elif blockers:
                status = "blocked"
            elif latest:
                status = (
                    "approved_for_preparation"
                    if latest["outcome"] == "approve"
                    else "professional_review"
                )
            elif branch["submitted_digest"] == digest:
                status = "professional_review"
            elif not any(
                ref.startswith("finding:") and value for ref, value in bound.items()
            ):
                status = "evidence_pending"
            else:
                status = "analysis_ready"
            branch.update(
                status=status,
                proposal_digest=digest,
                blockers=blockers,
                calculations=calculations,
            )

    def update_case(self, fields: dict[str, Any], actor: str) -> dict[str, Any]:
        state, previous = self._current()
        if set(fields) - (set(state["case"]) - {"id", "owner", "jurisdiction"}):
            raise ValueError("Unsupported or immutable case fields")
        state["case"].update(fields)
        return self._save(state, "update_case", actor, previous)

    def import_evidence(
        self, record_id: str, path: Path, origin: str, locator: str, actor: str
    ) -> dict[str, Any]:
        state, previous = self._current()
        _identifier(record_id)
        _text(origin, "origin")
        _text(locator, "locator")
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000_000:
            raise ValueError(
                "Select a regular synthetic evidence file of at most 20 MB"
            )
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        destination = self.root / "evidence" / sha
        if not destination.exists():
            with destination.open("xb") as handle:
                handle.write(data)
            destination.chmod(0o600)
        records = state["records"]["evidence"]
        records[record_id] = {
            "id": record_id,
            "version": records.get(record_id, {}).get("version", 0) + 1,
            "origin": origin,
            "original_name": path.name,
            "locator": locator,
            "acquired_at": _now(),
            "sha256": sha,
            "local_path": destination.relative_to(self.root).as_posix(),
            "quality": "synthetic_unverified",
            "permissions": "local_operator_supplied",
            "personal_data": "declared_synthetic_not_detected",
            "dependencies": [],
            "content_is_untrusted": True,
        }
        return self._save(state, f"import_evidence:{record_id}", actor, previous)

    def put(self, kind: str, record: dict[str, Any], actor: str) -> dict[str, Any]:
        """Store a proposal, preserving unknown values and exact dependency versions."""
        state, previous = self._current()
        if kind not in KINDS:
            raise ValueError("Unsupported record kind")
        record = copy.deepcopy(record)
        record_id = _identifier(record["id"])
        required = {*KINDS[kind], "id", "dependencies"}
        if set(record) != required:
            raise ValueError(f"{kind}: expected fields {sorted(required)}")
        _references(record["dependencies"])
        for key in MONEY | SHARES:
            value = record.get(key)
            if value is not None:
                if isinstance(value, dict) and set(value) == {"not_applicable"}:
                    _text(value["not_applicable"], "non-applicability reason")
                else:
                    number = _number(value)
                    if key in SHARES and number > 1:
                        raise ValueError("A share must be between zero and one")
        if kind == "finding":
            if record["category"] not in {"fact", "norm", "interpretation"}:
                raise ValueError("Separate fact, norm and interpretation")
            for key in ("statement", "rationale", "confidence"):
                _text(record[key], key)
            if (
                not isinstance(record["alternatives"], list)
                or not record["dependencies"]
            ):
                raise ValueError(
                    "A finding requires alternatives and dependency references"
                )
            if record["category"] != "fact" and not any(
                ref.startswith("source:") for ref in record["dependencies"]
            ):
                raise ValueError("Norms and interpretations require a source version")
        if kind == "source":
            _text(record["title"], "title")
            if not isinstance(record["snapshot"], str) or not record[
                "snapshot"
            ].startswith("evidence:"):
                raise ValueError("A source must bind a local evidence snapshot")
            if record["snapshot"] not in record["dependencies"]:
                raise ValueError("Source snapshot must be an explicit dependency")
            if record["verification_status"] not in {"unverified", "synthetic_review"}:
                raise ValueError(
                    "Professional source validation is outside the prototype"
                )
        if kind == "deadline" and (
            record["approved_date"] is not None or record["receipt"] is not None
        ):
            raise ValueError(
                "Deadlines remain proposals; no approved deadline or external receipt"
            )
        records = state["records"][kind]
        record["version"] = records.get(record_id, {}).get("version", 0) + 1
        records[record_id] = record
        self._bindings(state, [f"{kind}:{record_id}"])
        return self._save(state, f"put:{kind}:{record_id}", actor, previous)

    def branch(
        self,
        branch_id: str,
        title: str,
        owner: str,
        next_step: str,
        dependencies: list[str],
        actor: str,
    ) -> dict[str, Any]:
        state, previous = self._current()
        _identifier(branch_id)
        for key, value in (
            ("title", title),
            ("owner", owner),
            ("next_step", next_step),
        ):
            _text(value, key)
        if not dependencies:
            raise ValueError("A branch must declare its evidence requirements")
        state["branches"][branch_id] = {
            "title": title,
            "owner": owner,
            "next_step": next_step,
            "dependencies": _references(dependencies),
            "submitted_digest": None,
        }
        return self._save(state, f"branch:{branch_id}", actor, previous)

    def submit(self, branch_id: str, actor: str) -> dict[str, Any]:
        state, previous = self._current()
        branch = state["branches"][branch_id]
        if branch["blockers"] or branch["status"] == "evidence_pending":
            raise ValueError(
                "Resolve this branch's blockers and prepare its findings first"
            )
        branch["submitted_digest"] = branch["proposal_digest"]
        return self._save(state, f"submit:{branch_id}", actor, previous)

    def review(
        self,
        branch_id: str,
        proposal_digest: str,
        reviewer: str,
        outcome: str,
        reason: str,
    ) -> dict[str, Any]:
        state, previous = self._current()
        _text(reviewer, "reviewer")
        _text(reason, "review reason")
        if outcome not in {"approve", "request_changes"}:
            raise ValueError("Invalid review outcome")
        branch = state["branches"][branch_id]
        if (
            branch["blockers"]
            or branch["submitted_digest"] != proposal_digest
            or branch["proposal_digest"] != proposal_digest
        ):
            raise ValueError(
                "Review requires the exact submitted, unblocked proposal digest"
            )
        state["decisions"].append(
            {
                "id": f"D{len(state['decisions']) + 1:04d}",
                "branch_id": branch_id,
                "proposal_digest": proposal_digest,
                "case_revision": state["revision"],
                "reviewer": reviewer,
                "outcome": outcome,
                "reason": reason,
                "at": _now(),
                "scope": "synthetic_preparation_only",
                "authenticated_signature": False,
            }
        )
        return self._save(state, f"review:{branch_id}", reviewer, previous)

    def export(self) -> Path:
        """Write a version-bound dossier; export is delivery, never execution."""
        state = self.load()
        directory = self.root / "exports" / f"revision-{state['revision']:08d}"
        if directory.exists():
            expected = _bytes(state)
            if (directory / "case.json").read_bytes() != expected:
                raise ValueError("Existing export integrity mismatch")
            manifest = json.loads((directory / "manifest.json").read_text())
            if set(manifest["files"]) != {"case.json", "dossier.md"}:
                raise ValueError("Existing export integrity mismatch")
            for name, digest in manifest["files"].items():
                if (
                    hashlib.sha256((directory / name).read_bytes()).hexdigest()
                    != digest
                ):
                    raise ValueError("Existing export integrity mismatch")
            return directory
        directory.mkdir(parents=True, mode=0o700)
        (directory / "case.json").write_bytes(_bytes(state))
        sections = [
            "# Trasformazione societaria — dossier sintetico",
            "BOZZA. Prototipo su dati sintetici; nessuna validazione professionale, efficacia giuridica o azione esterna.",
            f"Pratica: {state['case']['id']} · Revisione: {state['revision']}",
            "## Perimetro",
            _table(
                [state["case"]],
                {
                    "owner": "Responsabile",
                    "purpose": "Finalità",
                    "initial_form": "Forma iniziale",
                    "final_form": "Forma finale",
                    "proposed_date": "Data proposta",
                },
            ),
        ]
        status_labels = {
            "draft": "Bozza",
            "evidence_pending": "Evidenze da integrare",
            "analysis_ready": "Analisi proposta",
            "professional_review": "In revisione",
            "approved_for_preparation": "Approvazione sintetica per preparazione",
            "blocked": "Bloccato",
            "stale": "Revisione da riaprire",
        }
        for branch_id, branch in state["branches"].items():
            sections.extend(
                [
                    f"## {_cell(branch['title'])}",
                    f"Stato: **{status_labels[branch['status']]}**. Responsabile: {_cell(branch['owner'])}. Prossimo passo: {_cell(branch['next_step'])}",
                ]
            )
            if branch["status"] == "stale":
                sections.append(
                    "I documenti o dati sono cambiati: le conclusioni e i calcoli seguenti sono proposte precedenti da riesaminare. L'approvazione storica non vale per la versione corrente."
                )
            sections.extend(f"- {_cell(blocker)}" for blocker in branch["blockers"])
            bound, _ = self._bindings(state, branch["dependencies"])
            for ref, value in bound.items():
                if ref.startswith("finding:") and value:
                    if "#" in ref:
                        sections.extend([f"### {_cell(ref)}", _cell(value)])
                        continue
                    sections.extend(
                        [
                            f"### {_cell(ref)} · {_cell(value['category'])}",
                            _cell(value["statement"]),
                            f"Motivazione: {_cell(value['rationale'])}",
                            f"Confidenza proposta: {_cell(value['confidence'])}; alternative: {_cell(value['alternatives'])}",
                            f"Evidenze e fonti: {_cell(value['dependencies'])}",
                        ]
                    )
            if branch["calculations"]:
                rows = [
                    {"calculation": ref, "measure": key, **value}
                    for ref, result in branch["calculations"].items()
                    for key, value in result["values"].items()
                ]
                rows.extend(
                    {
                        "calculation": ref,
                        "measure": "Residuo di arrotondamento non assegnato",
                        **result["display_residue"],
                    }
                    for ref, result in branch["calculations"].items()
                    if "display_residue" in result
                )
                sections.extend(
                    [
                        "### Prospetti aritmetici",
                        _table(
                            rows,
                            {
                                "calculation": "Prospetto",
                                "measure": "Misura",
                                "exact": "Valore esatto",
                                "display": "Visualizzazione",
                            },
                        ),
                        "Valori esatti conservati come razionali; visualizzazione al centesimo con ROUND_HALF_UP. Il residuo non viene assegnato automaticamente. Nessuna approvazione giuridica o fiscale.",
                    ]
                )
        for title, kind, columns in (
            (
                "Checklist documentale",
                "evidence",
                {
                    "id": "ID",
                    "original_name": "Documento",
                    "origin": "Origine",
                    "locator": "Riferimento",
                    "version": "Versione",
                },
            ),
            (
                "Capitale, utili e voto distinti",
                "participant",
                {
                    "name": "Socio",
                    "capital_share": "Capitale",
                    "vote_share": "Voto",
                    "profit_share": "Utili",
                    "work_share": "Opera",
                    "title": "Titolo",
                },
            ),
            (
                "Creditori: liberazione e opposizione",
                "creditor",
                {
                    "name": "Creditore",
                    "debt": "Debito",
                    "guarantee": "Garanzia",
                    "receipt": "Ricevuta",
                    "release_assessment": "Liberazione",
                    "opposition_assessment": "Opposizione",
                },
            ),
            (
                "Strati delle riserve",
                "reserve",
                {
                    "id": "ID",
                    "amount": "Importo",
                    "origin": "Origine",
                    "year": "Anno",
                    "regime": "Regime",
                    "restrictions": "Vincoli",
                    "uses": "Utilizzi",
                },
            ),
            (
                "Ponte valori e scritture proposte",
                "asset",
                {
                    "description": "Posta",
                    "book_value": "Contabile",
                    "estimated_value": "Stimato",
                    "tax_value": "Fiscale",
                    "accounting_decision": "Scrittura proposta",
                    "tax_decision": "Trattamento fiscale",
                },
            ),
            (
                "Scadenze proposte da verificare",
                "deadline",
                {
                    "id": "ID",
                    "source_version": "Fonte/versione",
                    "trigger": "Evento",
                    "method": "Metodo",
                    "proposed_date": "Data proposta",
                },
            ),
            (
                "Questioni aperte",
                "issue",
                {
                    "question": "Questione",
                    "source_needed": "Fonte da acquisire",
                    "owner": "Responsabile",
                    "closure_criterion": "Criterio di chiusura",
                    "resolution": "Esito",
                },
            ),
            (
                "Versioni delle fonti",
                "source",
                {
                    "id": "ID",
                    "title": "Fonte",
                    "version": "Versione",
                    "applicability_from": "Applicabilità da",
                    "verification_status": "Verifica",
                    "snapshot": "Documento",
                },
            ),
        ):
            rows = state["records"][kind]
            sections.extend([f"## {title}", _table(list(rows.values()), columns)])
        decisions = [
            {
                **decision,
                "current": (
                    "Corrente"
                    if decision["proposal_digest"]
                    == state["branches"][decision["branch_id"]]["proposal_digest"]
                    else "Superata: da riesaminare"
                ),
            }
            for decision in state["decisions"]
        ]
        sections.extend(
            [
                "## Decisioni del revisore",
                "Le identità sono dichiarate dall'operatore locale, non firme autenticate.",
                _table(
                    decisions,
                    {
                        "branch_id": "Ramo",
                        "reviewer": "Revisore",
                        "outcome": "Esito dichiarato",
                        "reason": "Motivo",
                        "current": "Validità",
                    },
                ),
                "Versioni, impronte, dati completi e cronologia sono conservati nei record JSON associati.",
                "## Quali dati arrivano al modello",
                "Il modello della sessione può leggere documenti sintetici selezionati, fatti, ipotesi, fonti, analisi, decisioni e dossier. Il helper locale conserva file, hash, versioni e calcoli; non chiama modelli né servizi esterni e non misura il contesto del provider. Non anonimizza automaticamente. Questo dossier non certifica quali dati il provider abbia ricevuto. Nel prototipo non sono ammessi casi reali.",
            ]
        )
        (directory / "dossier.md").write_text(
            "\n\n".join(sections) + "\n", encoding="utf-8"
        )
        (directory / "manifest.json").write_bytes(
            _bytes(
                {
                    "revision": state["revision"],
                    "synthetic_only": True,
                    "external_actions": [],
                    "files": {
                        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in sorted(directory.iterdir())
                        if path.is_file()
                    },
                }
            )
        )
        return directory


def main(argv: list[str] | None = None) -> int:
    """Apply one explicit local case operation and print machine-readable output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--id", required=True)
    init.add_argument("--owner", required=True)
    init.add_argument("--purpose", required=True)
    init.add_argument("--synthetic-only", action="store_true", required=True)
    put = commands.add_parser("put")
    put.add_argument("kind", choices=KINDS)
    put.add_argument("--json", type=Path, required=True)
    put.add_argument("--actor", required=True)
    update = commands.add_parser("update-case")
    update.add_argument("--json", type=Path, required=True)
    update.add_argument("--actor", required=True)
    evidence = commands.add_parser("import-evidence")
    evidence.add_argument("--id", required=True)
    evidence.add_argument("--file", type=Path, required=True)
    evidence.add_argument("--origin", required=True)
    evidence.add_argument("--locator", required=True)
    evidence.add_argument("--actor", required=True)
    branch = commands.add_parser("branch")
    branch.add_argument("--id", required=True)
    branch.add_argument("--title", required=True)
    branch.add_argument("--owner", required=True)
    branch.add_argument("--next-step", required=True)
    branch.add_argument("--dependency", action="append", required=True)
    branch.add_argument("--actor", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--branch", required=True)
    submit.add_argument("--actor", required=True)
    review = commands.add_parser("review")
    review.add_argument("--branch", required=True)
    review.add_argument("--digest", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument(
        "--outcome", choices=("approve", "request_changes"), required=True
    )
    review.add_argument("--reason", required=True)
    commands.add_parser("status")
    commands.add_parser("export")
    args = parser.parse_args(argv)
    store = CaseStore(args.case_dir)
    logging.basicConfig(level=logging.INFO)
    try:
        if args.command == "init":
            result = store.initialize(args.id, args.owner, args.purpose)
        elif args.command == "put":
            result = store.put(args.kind, json.loads(args.json.read_text()), args.actor)
        elif args.command == "update-case":
            result = store.update_case(json.loads(args.json.read_text()), args.actor)
        elif args.command == "import-evidence":
            result = store.import_evidence(
                args.id, args.file, args.origin, args.locator, args.actor
            )
        elif args.command == "branch":
            result = store.branch(
                args.id,
                args.title,
                args.owner,
                args.next_step,
                args.dependency,
                args.actor,
            )
        elif args.command == "submit":
            result = store.submit(args.branch, args.actor)
        elif args.command == "review":
            result = store.review(
                args.branch, args.digest, args.reviewer, args.outcome, args.reason
            )
        elif args.command == "export":
            result = {"dossier_dir": str(store.export())}
        else:
            result = store.load()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        LOG.error("Transformation operation failed: %s", exc)
        return 1
    LOG.info("%s", _bytes(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
