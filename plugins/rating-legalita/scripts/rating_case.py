"""Persist initial-application dossiers; never infer legal facts from documents.

Fixed checks enforce schema, exact evidence quotations, hashes and append-only
history. They cannot establish relevance, authenticity or legal completeness.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import jsonschema
from core_rating import score
from practice_controls import practice_summary

__all__ = ["assess_case", "new_case", "render_dossier", "save_dossier", "main"]

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "references/catalog.json"
# Checklist membership is an explicit review contract, not a legal classifier.
BASE_IDS = {
    *(f"A{i:02}" for i in range(1, 6)),
    *(f"S{i:02}" for i in range(1, 6)),
    *(f"B{i:02}" for i in range(1, 19)),
    *(f"C{i:02}" for i in range(1, 13)),
}
DECIDED = {"verified", "failed", "not_applicable_reviewed"}


def digest(value: Any) -> str:
    """Hash the canonical JSON payload without relying on input key order."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def new_case(case_id: str, as_of: str, *, synthetic: bool = False) -> dict:
    """Start with unknown facts and no invented client or registered archive run."""
    date.fromisoformat(as_of)
    return {
        "schema_version": "0.1",
        "case_id": case_id,
        "synthetic": synthetic,
        "client": None,
        "mode": "guided",
        "operation": "unknown",
        "status": "preintake",
        "as_of": as_of,
        "planned_submission": None,
        "ruleset": {
            "id": "AGCM-31812-2026",
            "checked_at": as_of,
            "catalog_sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
        },
        "practice": {
            "mandate": None,
            "data_governance": None,
            "event_reviews": [],
            "review_sessions": [],
        },
        "subjects": [],
        "events": [],
        "evidence": [],
        "scope": {
            "perimeter_reviewed": False,
            "required_instance_ids": [],
            "coverage_review": None,
            "source_current": False,
        },
        "snapshots": [
            {
                "snapshot_id": "T0",
                "as_of": as_of,
                "kind": "observed",
                "instances": [],
                "base_status": "undetermined",
                "estimated_rating": None,
                "conditions": [],
            }
        ],
        "gaps": [],
        "official_rating": None,
        "approvals": [],
        "external_actions": [],
        "limitations": [
            "Prima attribuzione: nessun invio, rinnovo o mantenimento automatico.",
            "Le decisioni registrate non autenticano l'identità del revisore.",
        ],
    }


def unique(rows: list[dict], key: str) -> dict[str, dict]:
    """Reject duplicate identities instead of silently choosing one record."""
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate {key}")
    return result


def evidence_path(root: Path, uri: str) -> Path:
    """Keep evidence inside the selected input folder, including symlinks."""
    path = (root / uri).resolve()
    if Path(uri).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("Evidence must remain inside the input folder")
    return path


def assess_case(case: dict, source_root: Path, previous: dict | None = None) -> dict:
    """Validate submitted judgments and derive a bounded documentary status."""
    schema = json.loads((ROOT / "schemas/case.schema.json").read_text())
    jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    ).validate(case)
    if not case["snapshots"] or case["snapshots"][0]["snapshot_id"] != "T0":
        raise ValueError("T0 is required")
    unique(case["snapshots"], "snapshot_id")
    if case["snapshots"][0]["kind"] != "observed":
        raise ValueError("T0 must be observed")
    if previous:
        if (
            digest({k: v for k, v in previous.items() if k != "record_sha256"})
            != previous["record_sha256"]
        ):
            raise ValueError("Previous record hash changed")
        old = previous["case"]
        if old["case_id"] != case["case_id"] or old["synthetic"] != case["synthetic"]:
            raise ValueError("Previous case identity differs")
        if old["client"] is not None and old["client"] != case["client"]:
            raise ValueError("Previous client binding differs")
        if case["snapshots"][: len(old["snapshots"])] != old["snapshots"]:
            raise ValueError("Earlier snapshots, including T0, are immutable")
        if case["as_of"] < old["as_of"]:
            raise ValueError("Case date precedes previous record")
        retained = {row["evidence_id"]: row for row in case["evidence"]}
        if any(retained.get(row["evidence_id"]) != row for row in old["evidence"]):
            raise ValueError("Earlier evidence records are immutable")
    practice = practice_summary(
        case, source_root, previous["case"] if previous else None
    )
    catalog = json.loads(CATALOG.read_text())
    source_ids = {row["id"] for row in catalog["sources"]}
    subjects = unique(case["subjects"], "subject_id")
    events = unique(case["events"], "event_id")
    evidence = unique(case["evidence"], "evidence_id")
    unique(case["gaps"], "gap_id")
    for event in events.values():
        if event["subject_id"] is not None and event["subject_id"] not in subjects:
            raise ValueError("Unknown event subject")
    for row in evidence.values():
        if not case["synthetic"] and row["kind"] == "synthetic_fact":
            raise ValueError("Synthetic evidence in a real case")
    observed = [row for row in case["snapshots"] if row["kind"] == "observed"]
    current = observed[-1]
    if current["as_of"] > case["as_of"]:
        raise ValueError("Observed snapshot is in the future")
    texts: dict[str, str] = {}
    blockers = list(practice["blockers"])
    checked_at = case["ruleset"]["checked_at"]
    if checked_at != case["as_of"]:
        blockers.append("Fonti da verificare alla data del caso")
    if (
        case["ruleset"]["catalog_sha256"]
        != hashlib.sha256(CATALOG.read_bytes()).hexdigest()
    ):
        blockers.append("Catalogo modificato: riesaminare le decisioni")
    if not case["scope"]["source_current"]:
        blockers.append("Vigenza delle fonti non confermata")

    def review_valid(review: dict | None) -> bool:
        if review is None:
            return False
        if not set(review["source_ids"]) <= source_ids or not review["source_ids"]:
            raise ValueError("Review must cite known source IDs")
        if review["date"] > case["as_of"]:
            raise ValueError("Review is in the future")
        if not case["synthetic"] and review["kind"] != "professional":
            raise ValueError("Synthetic decision in a real case")
        return True

    # Validate every snapshot, but only the current observed one drives status.
    for snapshot in case["snapshots"]:
        instances = unique(snapshot["instances"], "instance_id")
        for row in instances.values():
            if row["subject_id"] is not None and row["subject_id"] not in subjects:
                raise ValueError("Unknown instance subject")
            if row["event_id"] is not None and row["event_id"] not in events:
                raise ValueError("Unknown instance event")
            if row["status"] in DECIDED:
                review_valid(row["decision"])
                if not row["evidence_links"]:
                    raise ValueError(
                        "A decided requirement needs evidence and a locator"
                    )
            for link in row["evidence_links"]:
                if link["evidence_id"] not in evidence:
                    raise ValueError("Unknown evidence reference")
                item = evidence[link["evidence_id"]]
                if row["status"] not in DECIDED:
                    continue
                if item["read_status"] != "read" or item["sha256"] is None:
                    raise ValueError("Decisions need read, hashed evidence")
                path = evidence_path(source_root, item["uri"])
                if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError("Evidence hash changed")
                # Input is readable text or a reviewed, source-bound extraction.
                text = texts.setdefault(
                    item["evidence_id"], path.read_text(encoding="utf-8")
                )
                if link["excerpt"] not in text:
                    raise ValueError("Quoted evidence is absent from its source")
                if item["as_of"] > snapshot["as_of"]:
                    raise ValueError("Evidence postdates the snapshot")

    instances = unique(current["instances"], "instance_id")
    required = case["scope"]["required_instance_ids"]
    if len(required) != len(set(required)):
        raise ValueError("Duplicate required instance")
    if not set(required) <= instances.keys():
        raise ValueError("Required instance is missing from observed snapshot")
    covered = {instances[key]["rule_id"] for key in required}
    blockers += [
        f"Controllo base mancante: {key}" for key in sorted(BASE_IDS - covered)
    ]
    if any(
        row["rule_id"] in BASE_IDS and key not in required
        for key, row in instances.items()
    ):
        blockers.append("Istanze base escluse dal perimetro dichiarato")
    if not case["scope"]["perimeter_reviewed"] or not review_valid(
        case["scope"]["coverage_review"]
    ):
        blockers.append("Perimetro soggetti/eventi da rivedere")
    if any(row["inclusion"] == "unknown" for row in subjects.values()):
        blockers.append("Inclusione di soggetti non risolta")
    if not any(row["inclusion"] == "included" for row in subjects.values()):
        blockers.append("Nessun soggetto rilevante individuato")
    for subject in subjects.values():
        if subject["inclusion"] == "included" and not any(
            row["subject_id"] == subject["subject_id"] and key in required
            for key, row in instances.items()
        ):
            blockers.append(f"Soggetto non coperto: {subject['subject_id']}")
    base_rows = [row for row in instances.values() if row["rule_id"] in BASE_IDS]
    failed = [row["instance_id"] for row in base_rows if row["status"] == "failed"]
    blockers += [
        f"Requisito aperto: {row['instance_id']}"
        for row in base_rows
        if row["status"] not in {"verified", "not_applicable_reviewed"}
    ]
    if case["client"] is None:
        blockers.append("Identità impresa da definire")
    if case["operation"] != "first_attribution":
        blockers.append("Operazione da confermare: prima attribuzione")
    base = "obstructed" if failed else "undetermined" if blockers else "verified"
    premiums = {}
    for index, letter in enumerate("abcdefgh", 1):
        rows = [row for row in instances.values() if row["rule_id"] == f"P{index:02}"]
        states = {row["status"] for row in rows}
        premiums[letter] = (
            "supported"
            if states == {"verified"}
            else (
                "absent"
                if states and states <= {"failed", "not_applicable_reviewed"}
                else "unknown"
            )
        )
    deductions = [row for row in instances.values() if row["rule_id"] == "P09"]
    deduction = None
    if len(deductions) == 1:
        # P09 outcome is explicit: satisfied means the deduction condition exists.
        deduction = {
            "verified": True,
            "failed": False,
            "not_applicable_reviewed": False,
        }.get(deductions[0]["status"])
    estimate = score(base=base, premiums=premiums, deduction=deduction)
    if (
        current["base_status"] != base
        or current["estimated_rating"] != estimate["estimated_rating"]
    ):
        blockers.append(
            "Campi riassuntivi proposti non coincidono con le decisioni: usare l'esito derivato"
        )
    for gap in case["gaps"]:
        if not set(gap["instance_ids"]) <= instances.keys():
            raise ValueError("Gap references an unknown current instance")
    payload = {
        "case": copy.deepcopy(case),
        "practice_summary": practice,
        "assessment": {
            "base_status": base,
            "score": estimate,
            "blockers": blockers,
            "failed_instances": failed,
            "current_snapshot": current["snapshot_id"],
            "official_rating": None,
            "submission_authorized": False,
            "status": (
                "not_eligible"
                if failed
                else "ready_for_review" if base == "verified" else "incomplete"
            ),
        },
        "previous_record_sha256": previous["record_sha256"] if previous else None,
    }
    payload["record_sha256"] = digest(payload)
    return payload


def render_dossier(record: dict) -> str:
    """Render facts, exact quotations, decisions, gaps and scenarios for review."""
    case, result = record["case"], record["assessment"]
    lines = [
        "# Rating di legalità — dossier di prima attribuzione",
        "",
        (
            "CASO SINTETICO — nessuna pratica reale"
            if case["synthetic"]
            else "BOZZA — revisione professionale richiesta"
        ),
        f"Data: {case['as_of']} · Caso: {case['case_id']}",
        f"Esito documentale: {result['status']}",
        f"Base: {result['base_status']}",
        f"Stima sui requisiti documentati: {result['score']['estimated_rating'] or 'non determinabile'}",
        "Rating ufficiale: non acquisito. Nessuna firma o trasmissione.",
        "",
        "## Cosa impedisce di concludere",
        *[f"- {x}" for x in result["blockers"]],
        *[f"- {x}" for x in result["score"]["warnings"]],
    ]
    for snapshot in case["snapshots"]:
        label = (
            "Scenario obiettivo — non realizzato"
            if snapshot["kind"] == "conditional_scenario"
            else "Situazione documentata"
        )
        lines += ["", f"## {snapshot['snapshot_id']} · {label} al {snapshot['as_of']}"]
        for row in snapshot["instances"]:
            lines += [
                "",
                f"### {row['instance_id']} · {row['rule_id']} · {row['status']}",
                row["fact"],
            ]
            lines += [
                f"> {link['excerpt']}\n\nFonte: {link['evidence_id']} · {link['locator']}"
                for link in row["evidence_links"]
            ]
            if row["decision"]:
                decision = row["decision"]
                lines += [
                    f"Decisione registrata: {decision['actor']} · {decision['date']}",
                    decision["reason"],
                    f"Fonti normative: {', '.join(decision['source_ids'])}",
                ]
        lines += [f"Condizione: {item}" for item in snapshot["conditions"]]
    practice = record["practice_summary"]
    lines += [
        "",
        "## Incarico e presupposti del pilot",
        json.dumps(
            {
                "mandate": case["practice"]["mandate"],
                "data_governance": case["practice"]["data_governance"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        "La registrazione dei presupposti non certifica la liceità del trattamento. Nessuna cancellazione automatica o controllo dei permessi dell'host.",
        "",
        "## Registro eventi e scadenzario",
        json.dumps(practice["events"], ensure_ascii=False, indent=2),
        "Art. 21: 30 giorni dall'evento qualificato, non dalla conoscenza. Nessun invio o promemoria automatico. Distinguere obbligatori (commi 1–3) e premiali (commi 4–5).",
        "Il divieto di nuova domanda del comma 3 decorre dalla cessazione della rilevanza del motivo ostativo: non è calcolato dall'evento o dalla scoperta.",
        "",
        "## Tempo di revisione registrato",
        f"Minuti attivi: {practice['review_minutes'] if practice['review_minutes'] is not None else 'non misurati'} · Sessioni: {practice['measured_sessions']}",
        json.dumps(practice["minutes_by_stage"], ensure_ascii=False),
        "Tempi dichiarati dal professionista, al netto delle pause registrate. Non sono una misura di risparmio o sostenibilità economica.",
        "",
        "## Cosa fare adesso · piano dei gap",
    ]
    for gap in case["gaps"]:
        lines += [
            f"### {gap['gap_id']} · {gap['kind']}",
            f"T0: {gap['t0']}",
            f"Obiettivo: {gap['target']}",
            f"Azione: {gap['action']}",
            f"Responsabile: {gap['owner_role']} · Revisore: {gap['reviewer_role']}",
            f"Data: {gap['due_date'] or 'da concordare'}",
            json.dumps(gap, ensure_ascii=False),
        ]
    lines += [
        "",
        "## Prove e soggetti",
        json.dumps(
            {
                "evidence": case["evidence"],
                "subjects": case["subjects"],
                "events": case["events"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        "",
        "## Limiti e prossima revisione",
        *case["limitations"],
        "Il dossier non è il formulario AGCM. Verificare mappa dei campi, dichiarazioni e allegati sul formulario corrente prima di preparare la domanda da firmare.",
        "Hash e citazioni verificano collegamenti documentali; non provano verità, autenticità, pertinenza o completezza giuridica.",
        f"Impronta del dossier: {record['record_sha256']}",
    ]
    return "\n\n".join(lines) + "\n"


def save_dossier(record: dict, output: Path) -> Path:
    """Save a content-addressed record, preserving and checking earlier output."""
    if (
        digest({k: v for k, v in record.items() if k != "record_sha256"})
        != record["record_sha256"]
    ):
        raise ValueError("Record changed after validation")
    directory = output / record["record_sha256"]
    if output.is_symlink() or directory.is_symlink():
        raise ValueError("Output directory must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, content in (
        ("dossier.json", json.dumps(record, ensure_ascii=False, indent=2) + "\n"),
        ("dossier.md", render_dossier(record)),
    ):
        path = directory / name
        if path.is_symlink():
            raise ValueError("Output must not be a symlink")
        if path.exists():
            if path.read_text() != content:
                raise ValueError("Existing dossier was modified")
        else:
            with path.open("x", encoding="utf-8") as handle:
                path.chmod(0o600)
                handle.write(content)
    return directory


def main() -> int:
    """Allow standalone pre-intake; bind real evidence to Studio Archive v2."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--case-id", required=True)
    init.add_argument("--as-of", required=True)
    init.add_argument("--synthetic", action="store_true")
    init.add_argument("--output", type=Path, required=True)
    render = sub.add_parser("render")
    render.add_argument("--case", type=Path, required=True)
    render.add_argument("--source-root", type=Path)
    render.add_argument("--output", type=Path)
    render.add_argument("--previous", type=Path)
    render.add_argument("--client-engagement", type=Path)
    args = parser.parse_args()
    if args.command == "init":
        case = new_case(args.case_id, args.as_of, synthetic=args.synthetic)
        with args.output.open("x", encoding="utf-8") as handle:
            args.output.chmod(0o600)
            handle.write(json.dumps(case, ensure_ascii=False, indent=2) + "\n")
        return 0
    case = json.loads(args.case.read_text())
    previous = json.loads(args.previous.read_text()) if args.previous else None
    if (
        previous
        and digest(
            {key: value for key, value in previous.items() if key != "record_sha256"}
        )
        != previous["record_sha256"]
    ):
        raise ValueError("Previous record hash changed")
    source_root, output = args.source_root, args.output
    if not case["synthetic"] and (case["client"] is not None or case["evidence"]):
        if args.client_engagement is None:
            raise ValueError("Real cases require a Studio Archive client engagement")
        for vendor in (
            ROOT / "vendor/modules",
            ROOT.parent.parent / "vendor/modules",
            ROOT.parent / "_shared/vendor/modules",
        ):
            if (vendor / "vera_assurance").is_dir():
                sys.path.insert(0, str(vendor))
                break
        from vera_assurance import load_client_engagement_context_file

        context = load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="rating-legalita",
            input_paths=[args.case],
        )
        if context["schema_version"] != "vera.client_workflow_context.v2":
            raise ValueError("Portable v2 archive context required")
        client = case["client"]
        if (
            client is None
            or client["archive_client_id"] != context["client_id"]
            or client["engagement_id"] != context["engagement_id"]
        ):
            raise ValueError("Case and archive client/engagement differ")
        source_root = Path(context["run_root"]) / "inputs"
        paths = [evidence_path(source_root, row["uri"]) for row in case["evidence"]]
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="rating-legalita",
            input_paths=paths,
        )
        output = Path(context["output_dir"])
    if source_root is None or output is None:
        raise ValueError(
            "Standalone pre-intake and synthetic cases need source-root and output"
        )
    record = assess_case(case, source_root, previous)
    path = save_dossier(record, output)
    logging.info("Dossier saved: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
