"""Bind and package a model-written position and opposing opinion.

Fixed checks enforce file provenance and declared review states. They never
select authorities, invent objections, or decide which legal position wins.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

__all__ = ["prepare_adversarial", "package_opinion", "verify_opinion", "main"]

MODULE_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "shared_adversarial_validation", MODULE_ROOT / "scripts" / "package_validation.py"
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Shared answer validator could not be loaded")
_VALIDATOR = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _VALIDATOR
_SPEC.loader.exec_module(_VALIDATOR)

REQUIRED_FILES = (
    "answer_contract.json",
    "document_inventory.json",
    "source_inventory.json",
    "claims_review.json",
    "validated_document.md",
)
OUTCOMES = {
    "credible_counterposition",
    "no_substantial_counterposition",
    "evidence_limited",
}
STATUS_KEYS = (
    "complete",
    "professional_review_required",
    "evidence_limited",
    "revision_required",
    "blocked",
)
STATUS_LABELS = {
    "it": (
        "Esame completato",
        "Revisione professionale necessaria",
        "Evidenze limitate",
        "Correzione necessaria",
        "Questioni bloccanti",
    ),
    "en": (
        "Examination completed",
        "Professional review required",
        "Limited evidence",
        "Revision required",
        "Blocking issues",
    ),
    "fr": (
        "Examen terminé",
        "Revue professionnelle nécessaire",
        "Éléments limités",
        "Révision nécessaire",
        "Points bloquants",
    ),
    "de": (
        "Prüfung abgeschlossen",
        "Fachliche Prüfung erforderlich",
        "Begrenzte Nachweise",
        "Überarbeitung erforderlich",
        "Blockierende Fragen",
    ),
    "es": (
        "Examen completado",
        "Revisión profesional necesaria",
        "Pruebas limitadas",
        "Corrección necesaria",
        "Cuestiones bloqueantes",
    ),
}
DELIVERY_OUTPUTS = (
    "adversarial_brief.json",
    "adversarial_assessment.json",
    "opinion_comparison.md",
    "opinion_package.md",
    "position_audit.json",
    "adversarial_audit.json",
)
COPY = {
    "it": (
        "Parere e posizione contraria",
        "Parere esaminato",
        "Posizione contraria",
        "Confronto per il professionista",
        "Conclusione del parere",
        "Conclusione contraria",
        "Questioni decisive",
        "Evidenze mancanti",
        "Scelte professionali",
        "Effetto sul parere",
        "La completezza dei documenti non certifica la correttezza giuridica.",
    ),
    "en": (
        "Opinion and opposing position",
        "Reviewed opinion",
        "Opposing position",
        "Comparison for the professional",
        "Original conclusion",
        "Opposing conclusion",
        "Decisive issues",
        "Evidence gaps",
        "Professional choices",
        "Effect on the opinion",
        "Document completeness does not certify legal correctness.",
    ),
    "fr": (
        "Avis et position contraire",
        "Avis examiné",
        "Position contraire",
        "Comparaison pour le professionnel",
        "Conclusion initiale",
        "Conclusion contraire",
        "Questions décisives",
        "Éléments manquants",
        "Choix professionnels",
        "Effet sur l’avis",
        "La complétude des documents ne certifie pas leur exactitude juridique.",
    ),
    "de": (
        "Gutachten und Gegenposition",
        "Geprüftes Gutachten",
        "Gegenposition",
        "Vergleich für die Fachperson",
        "Ursprüngliche Schlussfolgerung",
        "Gegenläufige Schlussfolgerung",
        "Entscheidende Fragen",
        "Fehlende Nachweise",
        "Fachliche Entscheidungen",
        "Auswirkung auf das Gutachten",
        "Vollständige Dokumente bestätigen keine rechtliche Richtigkeit.",
    ),
    "es": (
        "Dictamen y posición contraria",
        "Dictamen revisado",
        "Posición contraria",
        "Comparación para el profesional",
        "Conclusión inicial",
        "Conclusión contraria",
        "Cuestiones decisivas",
        "Pruebas pendientes",
        "Decisiones profesionales",
        "Efecto sobre el dictamen",
        "La integridad documental no certifica la corrección jurídica.",
    ),
}


def _file(root: Path, relative: str) -> Path:
    """Reject traversal and symlinks before touching a managed artifact."""
    name = Path(relative)
    if name.is_absolute() or not name.parts or ".." in name.parts:
        raise ValueError(f"Invalid artifact path: {relative}")
    current = root
    for part in name.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlink artifact rejected: {relative}")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Artifact outside run: {relative}")
    return current


def _read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return data


def _write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(root: Path, phase: str) -> dict[str, str]:
    directory = _file(root, phase)
    if not directory.is_dir():
        raise ValueError(f"Missing opinion phase: {phase}")
    result = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(root).as_posix()
        checked = _file(root, relative)
        if checked.is_file():
            result[relative] = _digest(checked)
    return result


def _audit(root: Path, phase: str) -> dict[str, Any]:
    paths = {name: _file(root, f"{phase}/{name}") for name in REQUIRED_FILES}
    for name, path in paths.items():
        if not path.is_file():
            raise ValueError(f"Missing {phase}/{name}")
    review = _read(paths["claims_review.json"])
    document = paths["validated_document.md"].read_text(encoding="utf-8").strip()
    if not document or document != str(review.get("validated_document", "")).strip():
        raise ValueError(f"{phase}: reviewed text differs from the delivered document")
    sources = _read(paths["source_inventory.json"])
    for source in sources.get("sources", []):
        capture = source.get("captured_text_path")
        if capture and not _file(root, f"{phase}/{capture}").is_file():
            raise ValueError(f"{phase}: missing captured source")
    audit = _VALIDATOR.build_audit(
        _read(paths["document_inventory.json"]),
        sources,
        review,
        _read(paths["answer_contract.json"]),
        source_base_dir=paths["source_inventory.json"].parent,
    )
    if audit["record_integrity_status"] != "record_complete":
        raise ValueError(
            f"{phase}: incomplete validation record: {audit['failed_checks']}"
        )
    # Exact source membership is a provenance check, not a support judgment.
    for claim in review["claims"]:
        for check in claim["source_checks"]:
            reference = check["source_ref"]
            matches = [
                source
                for source in sources["sources"]
                if reference
                in {
                    source.get(key)
                    for key in (
                        "source_id",
                        "url",
                        "requested_url",
                        "final_url",
                        "path",
                        "origin_path",
                        "name",
                    )
                }
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"{phase}: unresolved or ambiguous source reference: {reference}"
                )
    return audit


def _counter_contract(original: dict[str, Any]) -> dict[str, Any]:
    result = dict(original)
    result.pop("adversarial_policy", None)
    result.update(
        # The optional research choice belongs to original-answer generation only.
        generation_route="codex_direct",
        document_type="adversarial opinion or reasoned search result",
        purpose="Develop and assess the strongest evidence-bound opposing case to the bound original position.",
        audience="Professional reviewing the original position",
        validation_scope="all_material_claims",
    )
    return result


def prepare_adversarial(root: Path) -> dict[str, Any]:
    """Freeze the reviewed position regardless of its substantive outcome."""
    audit = _audit(root, "position")
    contract = _read(_file(root, "position/answer_contract.json"))
    if contract.get("adversarial_policy") != "required":
        raise ValueError(
            "Vera opinion contract must declare adversarial_policy=required"
        )
    brief = {
        "schema_version": "1.0",
        "position_files": _snapshot(root, "position"),
        "original_validation_readiness": audit["delivery_readiness"],
        "counter_contract": _counter_contract(contract),
    }
    _file(root, "adversarial").mkdir(exist_ok=True)
    _write(_file(root, "adversarial_brief.json"), brief)
    _write(_file(root, "adversarial/answer_contract.json"), brief["counter_contract"])
    _write(_file(root, "opinion_progress.json"), {"status": "adversarial_pending"})
    return brief


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _texts(value: Any) -> bool:
    return isinstance(value, list) and all(_text(item) for item in value)


def _assessment(root: Path) -> dict[str, Any]:
    assessment = _read(_file(root, "adversarial_assessment.json"))
    if (
        assessment.get("schema_version") != "1.0"
        or assessment.get("outcome") not in OUTCOMES
    ):
        raise ValueError("Invalid adversarial assessment schema or outcome")
    if assessment.get("brief_sha256") != _digest(_file(root, "adversarial_brief.json")):
        raise ValueError(
            "Adversarial assessment targets a different or stale position brief"
        )
    if not _text(assessment.get("rationale")):
        raise ValueError("Adversarial outcome requires model-written reasons")
    search = assessment.get("search_record")
    source_ids = {
        source["source_id"]
        for source in _read(_file(root, "adversarial/source_inventory.json"))["sources"]
    }
    if not isinstance(search, list) or not search:
        raise ValueError("Adversarial examination requires a search record")
    for item in search:
        if not isinstance(item, dict) or not all(
            _text(item.get(key)) for key in ("question", "search_or_source", "finding")
        ):
            raise ValueError("Incomplete adversarial search record")
        if (
            not _texts(item.get("source_refs"))
            or not set(item["source_refs"]) <= source_ids
        ):
            raise ValueError("Search record references uncaptured sources")
    comparison = assessment.get("comparison")
    if not isinstance(comparison, dict) or not all(
        _text(comparison.get(key))
        for key in ("original_conclusion", "opposing_conclusion", "effect_analysis")
    ):
        raise ValueError("Missing opinion comparison")
    if not all(
        _texts(comparison.get(key))
        for key in ("decisive_issues", "evidence_gaps", "professional_choices")
    ):
        raise ValueError("Incomplete opinion comparison")
    if comparison.get("original_position_effect") not in {
        "unchanged",
        "professional_review_required",
        "revision_required",
    }:
        raise ValueError("Invalid original-position effect")
    review = assessment.get("comparison_review")
    if (
        not isinstance(review, dict)
        or review.get("status") not in {"reviewed", "revision_required"}
        or not _text(review.get("analysis"))
    ):
        raise ValueError("Comparison requires a separate semantic review")
    if assessment.get("language") not in COPY:
        raise ValueError("Choose an explicit supported output language")
    return assessment


def _evaluate(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    brief = _read(_file(root, "adversarial_brief.json"))
    if brief.get("position_files") != _snapshot(root, "position"):
        raise ValueError(
            "Original position changed; repeat preparation and adversarial examination"
        )
    original_contract = _read(_file(root, "position/answer_contract.json"))
    counter_contract = _read(_file(root, "adversarial/answer_contract.json"))
    if counter_contract != _counter_contract(
        original_contract
    ) or counter_contract != brief.get("counter_contract"):
        raise ValueError(
            "Opposing opinion changed the bound jurisdiction, facts contract, or review policy"
        )
    original = _audit(root, "position")
    opposing = _audit(root, "adversarial")
    assessment = _assessment(root)
    states = {original["delivery_readiness"], opposing["delivery_readiness"]}
    comparison = assessment["comparison"]
    if states & {"blocked", "not_reliable"}:
        status = "blocked"
    elif (
        "revision_required" in states
        or comparison["original_position_effect"] == "revision_required"
        or assessment["comparison_review"]["status"] == "revision_required"
    ):
        status = "revision_required"
    elif (
        "professional_review_required" in states
        or comparison["original_position_effect"] == "professional_review_required"
    ):
        status = "professional_review_required"
    elif "evidence_limited" in states or assessment["outcome"] == "evidence_limited":
        status = "evidence_limited"
    else:
        status = "complete"
    return original, opposing, assessment, status


def _render_comparison(assessment: dict[str, Any]) -> str:
    copy = COPY[assessment["language"]]
    comparison = assessment["comparison"]
    lines = [f"# {copy[3]}", "", assessment["rationale"]]
    for index, key in (
        (4, "original_conclusion"),
        (5, "opposing_conclusion"),
        (6, "decisive_issues"),
        (7, "evidence_gaps"),
        (8, "professional_choices"),
        (9, "effect_analysis"),
    ):
        value = comparison[key]
        if isinstance(value, list) and not value:
            continue
        lines.extend(["", f"## {copy[index]}", ""])
        lines.extend(
            [f"- {item}" for item in value] if isinstance(value, list) else [value]
        )
    return "\n".join([*lines, "", copy[10], ""])


def package_opinion(root: Path, *, docx: bool = False) -> dict[str, Any]:
    """Deliver both separately reviewed positions without picking a winner."""
    original, opposing, assessment, status = _evaluate(root)
    copy = COPY[assessment["language"]]
    status_label = dict(zip(STATUS_KEYS, STATUS_LABELS[assessment["language"]]))[status]
    comparison = _render_comparison(assessment)
    _file(root, "opinion_comparison.md").write_text(comparison, encoding="utf-8")
    _write(_file(root, "position_audit.json"), original)
    _write(_file(root, "adversarial_audit.json"), opposing)
    index = f"# {copy[0]}\n\n{status_label}\n\n- [{copy[1]}](position/validated_document.md)\n- [{copy[2]}](adversarial/validated_document.md)\n- [{copy[3]}](opinion_comparison.md)\n\n{assessment['rationale']}\n\n{copy[10]}\n"
    _file(root, "opinion_package.md").write_text(index, encoding="utf-8")
    outputs = list(DELIVERY_OUTPUTS)
    if docx:
        path = _file(root, "opinion_comparison.docx")
        if not _VALIDATOR.try_write_docx(comparison, path):
            raise ValueError("DOCX export requested but unavailable")
        outputs.append("opinion_comparison.docx")
    files = {**_snapshot(root, "position"), **_snapshot(root, "adversarial")}
    files.update({name: _digest(_file(root, name)) for name in outputs})
    delivery = {
        "schema_version": "1.0",
        "status": status,
        "original_validation_readiness": original["delivery_readiness"],
        "adversarial_validation_readiness": opposing["delivery_readiness"],
        "adversarial_outcome": assessment["outcome"],
        "files": files,
        "integrity_meaning": "Exact artifacts and explicit review states only; no legal-correctness certification or professional approval.",
    }
    _write(_file(root, "opinion_delivery.json"), delivery)
    _write(
        _file(root, "opinion_progress.json"),
        {
            "status": "packaged",
            "delivery_sha256": _digest(_file(root, "opinion_delivery.json")),
        },
    )
    return verify_opinion(root)


def verify_opinion(root: Path) -> dict[str, Any]:
    """Recompute reviews and reject missing, changed or newly prepared work."""
    delivery = _read(_file(root, "opinion_delivery.json"))
    if (
        delivery.get("schema_version") != "1.0"
        or not isinstance(delivery.get("files"), dict)
        or not set(DELIVERY_OUTPUTS) <= set(delivery["files"])
    ):
        raise ValueError("Incomplete opinion delivery manifest")
    progress = _read(_file(root, "opinion_progress.json"))
    if progress != {
        "status": "packaged",
        "delivery_sha256": _digest(_file(root, "opinion_delivery.json")),
    }:
        raise ValueError(
            "Opinion journey has not been packaged after its last preparation"
        )
    for name, digest in delivery["files"].items():
        path = _file(root, name)
        if not path.is_file() or _digest(path) != digest:
            raise ValueError(f"Missing or changed opinion artifact: {name}")
    for phase in ("position", "adversarial"):
        if _snapshot(root, phase) != {
            name: digest
            for name, digest in delivery["files"].items()
            if name.startswith(f"{phase}/")
        }:
            raise ValueError(f"Opinion phase changed: {phase}")
    original, opposing, assessment, status = _evaluate(root)
    expected = {
        "status": status,
        "original_validation_readiness": original["delivery_readiness"],
        "adversarial_validation_readiness": opposing["delivery_readiness"],
        "adversarial_outcome": assessment["outcome"],
    }
    if any(delivery.get(key) != value for key, value in expected.items()):
        raise ValueError("Delivery status conflicts with current review records")
    return delivery


def main() -> int:
    """Run within the existing Studio Archive validation engagement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "package", "verify"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--docx", action="store_true")
    args = parser.parse_args()
    root = args.output_dir.expanduser().resolve(strict=True)
    try:
        _VALIDATOR.load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="deep-research-validator",
            input_paths=[_file(root, f"position/{name}") for name in REQUIRED_FILES],
            output_dir=root,
            allowed_statuses=(
                ("running", "ready_for_review", "completed")
                if args.action == "verify"
                else ("running",)
            ),
        )
        if args.action == "prepare":
            result = prepare_adversarial(root)
        elif args.action == "package":
            result = package_opinion(root, docx=args.docx)
        else:
            result = verify_opinion(root)
    except (OSError, ValueError, _VALIDATOR.AssuranceContractError) as exc:
        parser.error(str(exc))
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("%s", json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
