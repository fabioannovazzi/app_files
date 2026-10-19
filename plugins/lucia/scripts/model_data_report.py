#!/usr/bin/env python3
"""Build a small, evidence-bounded model-data report for one Vera run."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = [
    "ModelDataReportError",
    "build_model_data_report",
    "main",
    "render_model_data_report",
    "show_model_data_report",
    "validate_model_data_report",
]


class ModelDataReportError(ValueError):
    """Raised when model-data evidence is incomplete or contradictory."""


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUNTIME_PROFILES = {
    "openai-chatgpt",
    "openai-codex",
    "anthropic-cowork",
    "google-antigravity",
    "other-host",
}
_LANGUAGES = {"it", "en", "fr", "de", "es"}
_OUTCOMES = {
    "reduced_projection",
    "full_context_required",
    "no_case_data",
    "not_measurable",
}
_EVIDENCE_BASES = {
    "exact_payload_receipt",
    "workflow_receipt",
    "host_attested",
    "not_measurable",
}
_UNITS = {
    "rows",
    "columns",
    "cells",
    "files",
    "pages",
    "sections",
    "chunks",
    "messages",
    "threads",
    "attachments",
    "images",
    "ocr_blocks",
    "characters",
    "bytes",
    "metrics",
    "exceptions",
    "claims",
    "evidence_excerpts",
    "items",
}
_MEASUREMENT_BASES = {"measured", "derived", "attested", "not_measurable"}
_ASSESSMENT_STATUSES = {"candidate", "none_supported", "not_assessed"}
_CANDIDATE_STATUSES = {"candidate_needs_validation", "validated"}
_INPUT_FIELDS = {
    "schema_version",
    "workflow_id",
    "run_id",
    "runtime_profile",
    "language",
    "created_at",
    "professional_purpose",
    "phases",
    "improvement_assessment",
}
_BOUND_REPORT_FIELDS = {"privacy_contract", "contract_review"}
_REPORT_LIMITATIONS = [
    "The report records workflow evidence and exact payload files when available; it is not provider-signed network telemetry.",
    "The report does not decide semantic necessity, provide legal advice, perform a DPIA, or certify GDPR compliance.",
]
_PHASE_FIELDS = {
    "phase_id",
    "purpose",
    "outcome",
    "evidence_basis",
    "source_extent",
    "locally_processed",
    "model_visible",
    "remained_local",
    "reason",
    "evidence_files",
}
_MEASUREMENT_FIELDS = {"unit", "quantity", "label", "basis"}
_ASSESSMENT_FIELDS = {"status", "candidates"}
_CANDIDATE_FIELDS = {
    "candidate_id",
    "phase_ids",
    "change",
    "evidence",
    "estimated_reduction",
    "quality_safeguard",
    "status",
    "validation_evidence",
}

_COPY = {
    "en": {
        "title": "Model data report",
        "workflow": "Workflow",
        "run": "Run",
        "runtime": "Runtime",
        "purpose": "Professional purpose",
        "summary": "Summary",
        "summary_text": "{count} model phase(s): {outcomes}.",
        "phase_title": "What reached the model",
        "measurement_note": (
            '"Processed locally" is the total handled by code; "Never visible to '
            'the model" is the part of the source that did not enter model context. '
            "The measures overlap and must not be added together."
        ),
        "phase": "Phase",
        "outcome": "Outcome",
        "source": "Available source",
        "local": "Processed locally",
        "visible": "Model-visible",
        "excluded": "Never visible to the model",
        "reason": "Reason",
        "basis": "Evidence",
        "none": "None recorded",
        "improvement": "Potential improvement",
        "estimated": "Estimated reduction",
        "safeguard": "Quality safeguard",
        "status": "Status",
        "limitation": "Evidence boundary",
        "limitation_text": (
            "This report is bound to workflow evidence and exact payload files when "
            "available. It is not provider-signed network telemetry, a DPIA, or proof "
            "of GDPR compliance."
        ),
    },
    "it": {
        "title": "Report sui dati arrivati al modello",
        "workflow": "Processo",
        "run": "Esecuzione",
        "runtime": "Ambiente",
        "purpose": "Finalità professionale",
        "summary": "Sintesi",
        "summary_text": "{count} fase/i del modello: {outcomes}.",
        "phase_title": "Che cosa è arrivato al modello",
        "measurement_note": (
            '"Elaborato localmente" indica il totale trattato dal codice; "Mai '
            'visibile al modello" indica la parte della fonte che non è entrata nel '
            "contesto del modello. Le due misure si sovrappongono e non vanno sommate."
        ),
        "phase": "Fase",
        "outcome": "Esito",
        "source": "Fonte disponibile",
        "local": "Elaborato localmente",
        "visible": "Visibile al modello",
        "excluded": "Mai visibile al modello",
        "reason": "Motivo",
        "basis": "Evidenza",
        "none": "Nessun elemento registrato",
        "improvement": "Possibile miglioramento",
        "estimated": "Riduzione stimata",
        "safeguard": "Salvaguardia della qualità",
        "status": "Stato",
        "limitation": "Limite dell'evidenza",
        "limitation_text": (
            "Il report è legato alle evidenze del processo e, quando disponibili, "
            "agli esatti file inviati al modello. Non è telemetria di rete firmata "
            "dal provider, una DPIA o una prova di conformità GDPR."
        ),
    },
    "fr": {
        "title": "Rapport sur les données transmises au modèle",
        "workflow": "Processus",
        "run": "Exécution",
        "runtime": "Environnement",
        "purpose": "Finalité professionnelle",
        "summary": "Synthèse",
        "summary_text": "{count} phase(s) du modèle : {outcomes}.",
        "phase_title": "Ce qui est parvenu au modèle",
        "measurement_note": (
            "« Traité localement » indique le total traité par le code ; « Jamais "
            "visible par le modèle » indique la partie de la source qui n’est pas "
            "entrée dans le contexte du modèle. Les mesures se chevauchent et ne "
            "doivent pas être additionnées."
        ),
        "phase": "Phase",
        "outcome": "Résultat",
        "source": "Source disponible",
        "local": "Traité localement",
        "visible": "Visible par le modèle",
        "excluded": "Jamais visible par le modèle",
        "reason": "Raison",
        "basis": "Évidence",
        "none": "Aucun élément enregistré",
        "improvement": "Amélioration possible",
        "estimated": "Réduction estimée",
        "safeguard": "Protection de la qualité",
        "status": "Statut",
        "limitation": "Limite de l'évidence",
        "limitation_text": (
            "Ce rapport est lié aux éléments du processus et aux fichiers exacts "
            "lorsqu'ils sont disponibles. Il ne constitue ni une télémétrie réseau "
            "signée par le fournisseur, ni une AIPD, ni une preuve de conformité RGPD."
        ),
    },
    "de": {
        "title": "Bericht zu den Modelldaten",
        "workflow": "Prozess",
        "run": "Ausführung",
        "runtime": "Umgebung",
        "purpose": "Beruflicher Zweck",
        "summary": "Zusammenfassung",
        "summary_text": "{count} Modellphase(n): {outcomes}.",
        "phase_title": "Was das Modell erhalten hat",
        "measurement_note": (
            "„Lokal verarbeitet“ bezeichnet den gesamten vom Code verarbeiteten "
            "Umfang; „Nie für das Modell sichtbar“ bezeichnet den Teil der Quelle, "
            "der nicht in den Modellkontext gelangte. Die Messwerte überlappen und "
            "dürfen nicht addiert werden."
        ),
        "phase": "Phase",
        "outcome": "Ergebnis",
        "source": "Verfügbare Quelle",
        "local": "Lokal verarbeitet",
        "visible": "Für das Modell sichtbar",
        "excluded": "Nie für das Modell sichtbar",
        "reason": "Grund",
        "basis": "Nachweis",
        "none": "Keine Elemente erfasst",
        "improvement": "Mögliche Verbesserung",
        "estimated": "Geschätzte Reduzierung",
        "safeguard": "Qualitätssicherung",
        "status": "Status",
        "limitation": "Nachweisgrenze",
        "limitation_text": (
            "Dieser Bericht ist an Prozessnachweise und, soweit vorhanden, an exakte "
            "Modelldateien gebunden. Er ist keine vom Anbieter signierte "
            "Netzwerktelemetrie, keine DSFA und kein Nachweis der DSGVO-Konformität."
        ),
    },
    "es": {
        "title": "Informe de datos enviados al modelo",
        "workflow": "Proceso",
        "run": "Ejecución",
        "runtime": "Entorno",
        "purpose": "Finalidad profesional",
        "summary": "Resumen",
        "summary_text": "{count} fase(s) del modelo: {outcomes}.",
        "phase_title": "Qué llegó al modelo",
        "measurement_note": (
            "«Procesado localmente» indica el total tratado por el código; «Nunca "
            "visible para el modelo» indica la parte de la fuente que no entró en el "
            "contexto del modelo. Las medidas se solapan y no deben sumarse."
        ),
        "phase": "Fase",
        "outcome": "Resultado",
        "source": "Fuente disponible",
        "local": "Procesado localmente",
        "visible": "Visible para el modelo",
        "excluded": "Nunca visible para el modelo",
        "reason": "Motivo",
        "basis": "Evidencia",
        "none": "Ningún elemento registrado",
        "improvement": "Posible mejora",
        "estimated": "Reducción estimada",
        "safeguard": "Protección de la calidad",
        "status": "Estado",
        "limitation": "Límite de la evidencia",
        "limitation_text": (
            "Este informe está vinculado a la evidencia del proceso y, cuando existen, "
            "a los archivos exactos enviados al modelo. No es telemetría de red firmada "
            "por el proveedor, una EIPD ni prueba de cumplimiento del RGPD."
        ),
    },
}

_OUTCOME_COPY = {
    "en": {
        "reduced_projection": "Reduced projection",
        "full_context_required": "Full context required",
        "no_case_data": "No case data",
        "not_measurable": "Not measurable",
    },
    "it": {
        "reduced_projection": "Proiezione ridotta",
        "full_context_required": "Contesto completo necessario",
        "no_case_data": "Nessun dato del caso",
        "not_measurable": "Non misurabile",
    },
    "fr": {
        "reduced_projection": "Projection réduite",
        "full_context_required": "Contexte complet nécessaire",
        "no_case_data": "Aucune donnée du dossier",
        "not_measurable": "Non mesurable",
    },
    "de": {
        "reduced_projection": "Reduzierte Projektion",
        "full_context_required": "Vollständiger Kontext erforderlich",
        "no_case_data": "Keine Falldaten",
        "not_measurable": "Nicht messbar",
    },
    "es": {
        "reduced_projection": "Proyección reducida",
        "full_context_required": "Contexto completo necesario",
        "no_case_data": "Sin datos del caso",
        "not_measurable": "No medible",
    },
}


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelDataReportError(f"{label} must be an object")
    return value


def _sequence(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ModelDataReportError(f"{label} must be a list")
    return list(value)


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ModelDataReportError(f"{label} must be non-empty trimmed text")
    if "\n" in value or "\r" in value:
        raise ModelDataReportError(f"{label} must be single-line text")
    return value


def _identifier(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise ModelDataReportError(f"{label} must be a canonical identifier")
    return text


def _timestamp(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ModelDataReportError(f"{label} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or "T" not in text:
        raise ModelDataReportError(f"{label} must include a timezone")
    return text


def _exact_fields(value: Mapping[str, Any], expected: set[str], *, label: str) -> None:
    missing = expected - set(value)
    unexpected = set(value) - expected
    if missing or unexpected:
        raise ModelDataReportError(
            f"{label} fields invalid; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )


def _measurement(value: object, *, label: str) -> dict[str, Any]:
    payload = _mapping(value, label=label)
    _exact_fields(payload, _MEASUREMENT_FIELDS, label=label)
    unit = _text(payload["unit"], label=f"{label}.unit")
    if unit not in _UNITS:
        raise ModelDataReportError(f"{label}.unit is unsupported")
    quantity = payload["quantity"]
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
        raise ModelDataReportError(f"{label}.quantity must be a non-negative integer")
    basis = _text(payload["basis"], label=f"{label}.basis")
    if basis not in _MEASUREMENT_BASES:
        raise ModelDataReportError(f"{label}.basis is unsupported")
    return {
        "unit": unit,
        "quantity": quantity,
        "label": _text(payload["label"], label=f"{label}.label"),
        "basis": basis,
    }


def _measurements(value: object, *, label: str) -> list[dict[str, Any]]:
    return [
        _measurement(item, label=f"{label}[{index}]")
        for index, item in enumerate(_sequence(value, label=label))
    ]


def _resolve_evidence_file(root: Path, relative_value: object, *, label: str) -> Path:
    relative = Path(_text(relative_value, label=label))
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ModelDataReportError(f"{label} must be a normalized relative path")
    candidate = root / relative
    if candidate.is_symlink() or not candidate.is_file():
        raise ModelDataReportError(f"{label} must identify a regular evidence file")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ModelDataReportError(f"{label} escapes the evidence root") from exc
    return resolved


def _file_receipt(path: Path, *, root: Path, phase_id: str) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "phase_id": phase_id,
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _validate_phase(
    value: object,
    *,
    index: int,
    evidence_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    label = f"phases[{index}]"
    payload = _mapping(value, label=label)
    _exact_fields(payload, _PHASE_FIELDS, label=label)
    phase_id = _identifier(payload["phase_id"], label=f"{label}.phase_id")
    outcome = _text(payload["outcome"], label=f"{label}.outcome")
    if outcome not in _OUTCOMES:
        raise ModelDataReportError(f"{label}.outcome is unsupported")
    evidence_basis = _text(payload["evidence_basis"], label=f"{label}.evidence_basis")
    if evidence_basis not in _EVIDENCE_BASES:
        raise ModelDataReportError(f"{label}.evidence_basis is unsupported")

    evidence_values = _sequence(
        payload["evidence_files"], label=f"{label}.evidence_files"
    )
    if evidence_basis == "exact_payload_receipt" and not evidence_values:
        raise ModelDataReportError(
            f"{label} requires an evidence file for exact_payload_receipt"
        )
    if outcome == "not_measurable" and evidence_basis not in {
        "host_attested",
        "not_measurable",
    }:
        raise ModelDataReportError(
            f"{label} not_measurable outcome has contradictory evidence basis"
        )

    source_extent = _measurements(
        payload["source_extent"], label=f"{label}.source_extent"
    )
    locally_processed = _measurements(
        payload["locally_processed"], label=f"{label}.locally_processed"
    )
    model_visible = _measurements(
        payload["model_visible"], label=f"{label}.model_visible"
    )
    remained_local = _measurements(
        payload["remained_local"], label=f"{label}.remained_local"
    )
    if outcome == "reduced_projection" and (not model_visible or not remained_local):
        raise ModelDataReportError(
            f"{label} reduced_projection requires model_visible and remained_local measurements"
        )
    if outcome == "no_case_data" and model_visible:
        raise ModelDataReportError(
            f"{label} no_case_data cannot declare model-visible case measurements"
        )
    if outcome == "full_context_required" and not model_visible:
        raise ModelDataReportError(
            f"{label} full_context_required needs model-visible measurements"
        )

    receipts: list[dict[str, Any]] = []
    normalized_evidence: list[str] = []
    for evidence_index, relative_value in enumerate(evidence_values):
        path = _resolve_evidence_file(
            evidence_root,
            relative_value,
            label=f"{label}.evidence_files[{evidence_index}]",
        )
        normalized_evidence.append(path.relative_to(evidence_root).as_posix())
        receipts.append(_file_receipt(path, root=evidence_root, phase_id=phase_id))

    return (
        {
            "phase_id": phase_id,
            "purpose": _text(payload["purpose"], label=f"{label}.purpose"),
            "outcome": outcome,
            "evidence_basis": evidence_basis,
            "source_extent": source_extent,
            "locally_processed": locally_processed,
            "model_visible": model_visible,
            "remained_local": remained_local,
            "reason": _text(payload["reason"], label=f"{label}.reason"),
            "evidence_files": normalized_evidence,
        },
        receipts,
    )


def _validate_assessment(value: object, *, phase_ids: set[str]) -> dict[str, Any]:
    payload = _mapping(value, label="improvement_assessment")
    _exact_fields(payload, _ASSESSMENT_FIELDS, label="improvement_assessment")
    status = _text(payload["status"], label="improvement_assessment.status")
    if status not in _ASSESSMENT_STATUSES:
        raise ModelDataReportError("improvement_assessment.status is unsupported")
    candidate_values = _sequence(
        payload["candidates"], label="improvement_assessment.candidates"
    )
    if status == "candidate" and not candidate_values:
        raise ModelDataReportError(
            "candidate assessment requires at least one candidate"
        )
    if status != "candidate" and candidate_values:
        raise ModelDataReportError(
            "only a candidate assessment may contain improvement candidates"
        )

    candidates: list[dict[str, Any]] = []
    candidate_ids: set[str] = set()
    for index, value_item in enumerate(candidate_values):
        label = f"improvement_assessment.candidates[{index}]"
        candidate = _mapping(value_item, label=label)
        _exact_fields(candidate, _CANDIDATE_FIELDS, label=label)
        candidate_id = _identifier(
            candidate["candidate_id"], label=f"{label}.candidate_id"
        )
        if candidate_id in candidate_ids:
            raise ModelDataReportError("improvement candidate IDs must be unique")
        candidate_ids.add(candidate_id)
        candidate_phase_ids = [
            _identifier(item, label=f"{label}.phase_ids[{phase_index}]")
            for phase_index, item in enumerate(
                _sequence(candidate["phase_ids"], label=f"{label}.phase_ids")
            )
        ]
        if not candidate_phase_ids or not set(candidate_phase_ids) <= phase_ids:
            raise ModelDataReportError(
                f"{label}.phase_ids must reference report phases"
            )
        evidence = [
            _text(item, label=f"{label}.evidence[{evidence_index}]")
            for evidence_index, item in enumerate(
                _sequence(candidate["evidence"], label=f"{label}.evidence")
            )
        ]
        if not evidence:
            raise ModelDataReportError(f"{label}.evidence must not be empty")
        candidate_status = _text(candidate["status"], label=f"{label}.status")
        if candidate_status not in _CANDIDATE_STATUSES:
            raise ModelDataReportError(f"{label}.status is unsupported")
        validation_evidence = [
            _text(item, label=f"{label}.validation_evidence[{evidence_index}]")
            for evidence_index, item in enumerate(
                _sequence(
                    candidate["validation_evidence"],
                    label=f"{label}.validation_evidence",
                )
            )
        ]
        if candidate_status == "validated" and not validation_evidence:
            raise ModelDataReportError(
                f"{label}.validated status requires validation evidence"
            )
        estimated_reduction = _measurements(
            candidate["estimated_reduction"],
            label=f"{label}.estimated_reduction",
        )
        if not estimated_reduction:
            raise ModelDataReportError(f"{label}.estimated_reduction must not be empty")
        candidates.append(
            {
                "candidate_id": candidate_id,
                "phase_ids": candidate_phase_ids,
                "change": _text(candidate["change"], label=f"{label}.change"),
                "evidence": evidence,
                "estimated_reduction": estimated_reduction,
                "quality_safeguard": _text(
                    candidate["quality_safeguard"],
                    label=f"{label}.quality_safeguard",
                ),
                "status": candidate_status,
                "validation_evidence": validation_evidence,
            }
        )
    return {"status": status, "candidates": candidates}


def _canonical_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _validate_request(
    request: object, *, evidence_root: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = _mapping(request, label="request")
    _exact_fields(payload, _INPUT_FIELDS, label="request")
    if payload["schema_version"] != 1:
        raise ModelDataReportError("request.schema_version must be 1")
    runtime_profile = _text(payload["runtime_profile"], label="request.runtime_profile")
    if runtime_profile not in _RUNTIME_PROFILES:
        raise ModelDataReportError("request.runtime_profile is unsupported")
    language = _text(payload["language"], label="request.language")
    if language not in _LANGUAGES:
        raise ModelDataReportError("request.language is unsupported")

    phase_values = _sequence(payload["phases"], label="request.phases")
    if not phase_values:
        raise ModelDataReportError("request.phases must not be empty")
    phases: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    phase_ids: set[str] = set()
    for index, value in enumerate(phase_values):
        phase, phase_receipts = _validate_phase(
            value, index=index, evidence_root=evidence_root
        )
        if phase["phase_id"] in phase_ids:
            raise ModelDataReportError("phase IDs must be unique")
        phase_ids.add(phase["phase_id"])
        phases.append(phase)
        receipts.extend(phase_receipts)

    return (
        {
            "schema_version": 1,
            "workflow_id": _identifier(
                payload["workflow_id"], label="request.workflow_id"
            ),
            "run_id": _identifier(payload["run_id"], label="request.run_id"),
            "runtime_profile": runtime_profile,
            "language": language,
            "created_at": _timestamp(payload["created_at"], label="request.created_at"),
            "professional_purpose": _text(
                payload["professional_purpose"], label="request.professional_purpose"
            ),
            "phases": phases,
            "improvement_assessment": _validate_assessment(
                payload["improvement_assessment"], phase_ids=phase_ids
            ),
        },
        receipts,
    )


def _format_measurements(values: Sequence[Mapping[str, Any]], *, none: str) -> str:
    if not values:
        return none
    return "; ".join(
        f"{value['quantity']:,} {value['unit']} — {value['label']} ({value['basis']})"
        for value in values
    )


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _installed_product_root() -> Path | None:
    """Find the invoking product, including a helper vendored inside its component."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "privacy/registry.json").is_file() and any(
            (parent / name).is_file()
            for name in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json")
        ):
            return parent
    return None


def _privacy_contract_module(product_root: Path | None):
    """Load bundled code only; reopening a historical report needs no network."""
    candidates = [Path(__file__).with_name("privacy_contract.py")]
    if product_root is not None:
        candidates.append(product_root / "scripts/privacy_contract.py")
    # Editable canonical reporting source has its governance sibling here.
    candidates.append(
        Path(__file__).resolve().parents[1]
        / "privacy-runtime/scripts/privacy_contract.py"
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise ModelDataReportError("Bundled privacy contract implementation is missing")
    spec = importlib.util.spec_from_file_location("_report_privacy_contract", path)
    if spec is None or spec.loader is None:
        raise ModelDataReportError(
            "Cannot load bundled privacy contract implementation"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_contract_review(
    value: Any, *, phase_ids: set[str], bound: bool
) -> dict[str, Any]:
    """Validate an agent's declared comparison, without substituting a code verdict."""
    review = _mapping(value, label="contract_review")
    _exact_fields(review, {"status", "phase_ids", "reason"}, label="contract_review")
    status = review["status"]
    if status not in {"consistent", "divergence", "not_assessed"}:
        raise ModelDataReportError("Unknown contract comparison status")
    selected = _sequence(review["phase_ids"], label="contract_review.phase_ids")
    if (
        not all(isinstance(phase, str) for phase in selected)
        or len(selected) != len(set(selected))
        or not set(selected) <= phase_ids
    ):
        raise ModelDataReportError(
            "Contract comparison must reference actual unique phase IDs"
        )
    if status == "consistent" and (set(selected) != phase_ids or not bound):
        raise ModelDataReportError(
            "A consistent comparison requires the reviewed runtime and all actual phases"
        )
    if status == "divergence" and not selected:
        raise ModelDataReportError("A divergence must identify its actual phases")
    if status == "not_assessed" and selected:
        raise ModelDataReportError(
            "Unassessed comparisons cannot claim reviewed phases"
        )
    return {
        "status": status,
        "phase_ids": list(selected),
        "reason": _text(review["reason"], label="contract_review.reason"),
    }


def _render_markdown(report: Mapping[str, Any]) -> str:
    language = str(report["language"])
    copy = _COPY[language]
    outcome_copy = _OUTCOME_COPY[language]
    phases = list(report["phases"])
    outcome_counts = Counter(str(phase["outcome"]) for phase in phases)
    outcomes = ", ".join(
        f"{outcome_copy[outcome]}: {count}"
        for outcome, count in sorted(outcome_counts.items())
    )
    lines = [
        f"# {copy['title']}",
        "",
        f"- {copy['workflow']}: `{report['workflow_id']}`",
        f"- {copy['run']}: `{report['run_id']}`",
        f"- {copy['runtime']}: `{report['runtime_profile']}`",
        f"- {copy['purpose']}: {report['professional_purpose']}",
        "",
        f"## {copy['summary']}",
        "",
        copy["summary_text"].format(count=len(phases), outcomes=outcomes),
        "",
        f"## {copy['phase_title']}",
        "",
        copy["measurement_note"],
    ]
    for phase in phases:
        lines.extend(
            [
                "",
                f"### `{_markdown_cell(phase['phase_id'])}` — "
                f"{outcome_copy[str(phase['outcome'])]}",
                "",
                f"- {copy['source']}: "
                + _format_measurements(phase["source_extent"], none=copy["none"]),
                f"- {copy['local']}: "
                + _format_measurements(phase["locally_processed"], none=copy["none"]),
                f"- {copy['visible']}: "
                + _format_measurements(phase["model_visible"], none=copy["none"]),
                f"- {copy['excluded']}: "
                + _format_measurements(phase["remained_local"], none=copy["none"]),
                f"- {copy['reason']}: {phase['reason']}",
                f"- {copy['basis']}: `{phase['evidence_basis']}`",
            ]
        )

    assessment = _mapping(
        report["improvement_assessment"], label="report.improvement_assessment"
    )
    candidates = list(assessment["candidates"])
    if assessment["status"] == "candidate":
        lines.extend(["", f"## {copy['improvement']}", ""])
        for candidate in candidates:
            lines.extend(
                [
                    f"### `{candidate['candidate_id']}`",
                    "",
                    str(candidate["change"]),
                    "",
                    f"- {copy['estimated']}: "
                    + _format_measurements(
                        candidate["estimated_reduction"], none=copy["none"]
                    ),
                    f"- {copy['safeguard']}: {candidate['quality_safeguard']}",
                    f"- {copy['status']}: `{candidate['status']}`",
                ]
            )
    if report.get("schema_version") == 2:
        binding = report["privacy_contract"]
        review = report["contract_review"]
        labels = {
            "it": (
                "Contratto privacy della funzione",
                "Confronto con la lavorazione",
                "Riferimento alla descrizione revisionata; non prova i dati effettivamente trasmessi al fornitore del modello.",
            ),
            "en": (
                "Function privacy contract",
                "Comparison with this run",
                "Reference to the reviewed description; it does not prove what was transmitted to the model provider.",
            ),
            "fr": (
                "Contrat de confidentialité de la fonction",
                "Comparaison avec ce traitement",
                "Référence à la description révisée ; elle ne prouve pas les données transmises au fournisseur du modèle.",
            ),
            "de": (
                "Datenschutzbeschreibung der Funktion",
                "Abgleich mit diesem Lauf",
                "Verweis auf die geprüfte Beschreibung; kein Nachweis der tatsächlich an den Modellanbieter übermittelten Daten.",
            ),
            "es": (
                "Contrato de privacidad de la función",
                "Comparación con esta ejecución",
                "Referencia a la descripción revisada; no demuestra los datos transmitidos al proveedor del modelo.",
            ),
        }
        title, comparison, limitation = labels[language]
        statuses = {
            "it": {
                "consistent": "coerente",
                "divergence": "differenze rilevate",
                "not_assessed": "non verificato",
            },
            "en": {
                "consistent": "consistent",
                "divergence": "differences found",
                "not_assessed": "not reviewed",
            },
            "fr": {
                "consistent": "cohérent",
                "divergence": "différences constatées",
                "not_assessed": "non vérifié",
            },
            "de": {
                "consistent": "übereinstimmend",
                "divergence": "Abweichungen festgestellt",
                "not_assessed": "nicht geprüft",
            },
            "es": {
                "consistent": "coherente",
                "divergence": "diferencias detectadas",
                "not_assessed": "no verificado",
            },
        }
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                f"{binding['product'].title()} · `{binding['workstream']}` · `{binding['product_version']}`",
                f"`SHA-256: {binding['contract_sha256']}`",
                "",
                f"{comparison}: **{statuses[language][review['status']]}** — {review['reason']}",
                "",
                limitation,
            ]
        )
    lines.extend(
        [
            "",
            f"## {copy['limitation']}",
            "",
            copy["limitation_text"],
            "",
        ]
    )
    return "\n".join(lines)


def build_model_data_report(
    request: object,
    *,
    evidence_root: str | Path,
    product_root: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Validate one run request and return its durable JSON and Markdown reports."""

    root = Path(evidence_root).expanduser().resolve()
    if not root.is_dir():
        raise ModelDataReportError("evidence_root must be an existing directory")
    request_data = dict(_mapping(request, label="request"))
    contract_review = request_data.pop("contract_review", None)
    normalized, file_receipts = _validate_request(request_data, evidence_root=root)
    installed = (
        Path(product_root).resolve()
        if product_root is not None
        else _installed_product_root()
    )
    if installed is not None:
        contract = _privacy_contract_module(installed)
        try:
            normalized["privacy_contract"] = contract.bind_run(
                installed, normalized["workflow_id"], normalized["runtime_profile"]
            )
        except contract.PrivacyContractError as exc:
            raise ModelDataReportError(str(exc)) from exc
        normalized["contract_review"] = _validate_contract_review(
            (
                contract_review
                if contract_review is not None
                else {
                    "status": "not_assessed",
                    "phase_ids": [],
                    "reason": "The host agent has not recorded a comparison of this run with the reviewed contract.",
                }
            ),
            phase_ids={phase["phase_id"] for phase in normalized["phases"]},
            bound=normalized["privacy_contract"]["status"] == "bound",
        )
        normalized["schema_version"] = 2
    elif contract_review is not None:
        raise ModelDataReportError(
            "A contract comparison requires a registered product installation"
        )
    input_sha256 = hashlib.sha256(_canonical_bytes(normalized)).hexdigest()
    receipt_content = {
        "input_sha256": input_sha256,
        "files": file_receipts,
    }
    receipt_sha256 = hashlib.sha256(_canonical_bytes(receipt_content)).hexdigest()
    report = {
        **normalized,
        "report_id": f"model_data_{receipt_sha256[:24]}",
        "evidence": {
            **receipt_content,
            "receipt_sha256": receipt_sha256,
        },
        "limitations": list(_REPORT_LIMITATIONS),
    }
    return report, _render_markdown(report)


def validate_model_data_report(
    report: object,
    *,
    evidence_root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate stable hashes and report structure without reinterpreting necessity."""

    payload = _mapping(report, label="report")
    version = payload.get("schema_version")
    if version == 3:
        from archive_reporting import validate_report

        try:
            return validate_report(payload)
        except (ValueError, KeyError, TypeError) as exc:
            raise ModelDataReportError(str(exc)) from exc
    if type(version) is not int or version not in {1, 2}:
        raise ModelDataReportError("report.schema_version must be 1 or 2")
    input_fields = _INPUT_FIELDS | (_BOUND_REPORT_FIELDS if version == 2 else set())
    required = input_fields | {"report_id", "evidence", "limitations"}
    _exact_fields(payload, required, label="report")
    normalized = {key: payload[key] for key in input_fields}
    if version == 2:
        contract = _privacy_contract_module(_installed_product_root())
        try:
            contract.validate_binding(
                payload["privacy_contract"],
                workflow_id=payload["workflow_id"],
                runtime_profile=payload["runtime_profile"],
            )
        except contract.PrivacyContractError as exc:
            raise ModelDataReportError(str(exc)) from exc
        _validate_contract_review(
            payload["contract_review"],
            phase_ids={phase["phase_id"] for phase in payload["phases"]},
            bound=payload["privacy_contract"]["status"] == "bound",
        )
    expected_hash = hashlib.sha256(_canonical_bytes(normalized)).hexdigest()
    evidence = _mapping(payload["evidence"], label="report.evidence")
    _exact_fields(
        evidence,
        {"input_sha256", "files", "receipt_sha256"},
        label="report.evidence",
    )
    if evidence["input_sha256"] != expected_hash:
        raise ModelDataReportError("report input hash does not match report content")
    if not _SHA256_RE.fullmatch(str(evidence["input_sha256"])):
        raise ModelDataReportError("report input hash is invalid")
    files = _sequence(evidence["files"], label="report.evidence.files")
    phase_ids = {str(phase["phase_id"]) for phase in normalized["phases"]}
    normalized_files: list[dict[str, Any]] = []
    for index, value in enumerate(files):
        label = f"report.evidence.files[{index}]"
        receipt = _mapping(value, label=label)
        _exact_fields(receipt, {"phase_id", "path", "sha256", "bytes"}, label=label)
        if receipt["phase_id"] not in phase_ids:
            raise ModelDataReportError(
                f"{label}.phase_id does not reference a report phase"
            )
        if not _SHA256_RE.fullmatch(str(receipt["sha256"])):
            raise ModelDataReportError(f"{label}.sha256 is invalid")
        byte_count = receipt["bytes"]
        if (
            not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count < 0
        ):
            raise ModelDataReportError(f"{label}.bytes must be a non-negative integer")
        normalized_files.append(dict(receipt))
    receipt_content = {
        "input_sha256": expected_hash,
        "files": normalized_files,
    }
    expected_receipt_hash = hashlib.sha256(
        _canonical_bytes(receipt_content)
    ).hexdigest()
    if evidence["receipt_sha256"] != expected_receipt_hash:
        raise ModelDataReportError("report receipt hash does not match evidence")
    if payload["report_id"] != f"model_data_{expected_receipt_hash[:24]}":
        raise ModelDataReportError("report_id does not match report evidence")
    if evidence_root is not None:
        root = Path(evidence_root).expanduser().resolve()
        if not root.is_dir():
            raise ModelDataReportError("evidence_root must be an existing directory")
        # Revalidate the recorded execution, not a newly bound installation.
        request = {key: payload[key] for key in _INPUT_FIELDS}
        request["schema_version"] = 1
        checked, current_files = _validate_request(request, evidence_root=root)
        if checked != request:
            raise ModelDataReportError("Report execution fields are not canonical")
        if current_files != normalized_files:
            raise ModelDataReportError(
                "report evidence file changed or receipts differ"
            )
    if payload["limitations"] != _REPORT_LIMITATIONS:
        raise ModelDataReportError(
            "report limitations differ from the maintained disclosure"
        )
    return dict(payload)


def render_model_data_report(
    report: object, *, evidence_root: str | Path | None = None
) -> str:
    """Validate and render saved facts without rebinding to the current installation."""

    validated = validate_model_data_report(report, evidence_root=evidence_root)
    if validated["schema_version"] == 3:
        from archive_reporting import render_report

        return render_report(validated)
    return _render_markdown(validated)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def show_model_data_report(report_path: str | Path) -> str:
    """Render the recorded report without changing files or contacting a service.

    Hash checks preserve the recorded facts. Viewing a historical report does
    not re-read source documents or claim that its evidence is still available.
    """

    path = Path(report_path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ModelDataReportError("report must be an existing regular JSON file")
    return render_model_data_report(json.loads(path.read_text(encoding="utf-8")))


def _write_once_or_identical(path: Path, data: bytes) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise ModelDataReportError(
                f"refusing to replace non-regular output: {path.name}"
            )
        if path.read_bytes() != data:
            raise ModelDataReportError(
                f"refusing to replace a different existing report: {path.name}"
            )
        return
    _atomic_write(path, data)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--input", type=Path, required=True)
    build.add_argument("--evidence-root", type=Path)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument(
        "--local-only",
        action="store_true",
        help="Build the local report without sending its digest for server stamping.",
    )
    validate = subparsers.add_parser("validate")
    validate.add_argument("--report", type=Path, required=True)
    show = subparsers.add_parser(
        "show", help="Display a saved report without rerunning it"
    )
    show.add_argument("--report", type=Path, required=True)
    return parser


def _selective_report_policy():
    """Apply Vera's fixed policy without changing Clara or Lucia reporting."""
    root = _installed_product_root()
    if (
        root is None
        or json.loads((root / "privacy/registry.json").read_text())["product"] != "vera"
    ):
        return None
    for candidate in (root / "vendor/modules", root.parent / "_shared/vendor/modules"):
        if (candidate / "vera_assurance").is_dir():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            break
    if str(root / "scripts") not in sys.path:
        sys.path.insert(0, str(root / "scripts"))
    import selective_reporting

    return selective_reporting


def main(argv: list[str] | None = None, *, server_attestation: bool = True) -> int:
    """Build, validate, or display a Vera model-data report."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "show":
            sys.stdout.write(show_model_data_report(args.report))
            return 0
        if args.command == "validate":
            report_path = args.report.expanduser()
            if report_path.is_symlink() or not report_path.is_file():
                raise ModelDataReportError("report must be a regular JSON file")
            report_path = report_path.resolve()
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            report = validate_model_data_report(
                payload,
                evidence_root=report_path.parent,
            )
            sys.stdout.write(
                json.dumps(
                    {"status": "valid", "report_id": report["report_id"]},
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
            return 0

        requested_input = args.input.expanduser()
        if requested_input.is_symlink() or not requested_input.is_file():
            raise ModelDataReportError("input must be a regular JSON file")
        input_path = requested_input.resolve()
        requested_evidence_root = (
            args.evidence_root.expanduser()
            if args.evidence_root is not None
            else input_path.parent
        )
        if requested_evidence_root.is_symlink():
            raise ModelDataReportError("evidence-root must not be a symbolic link")
        evidence_root = requested_evidence_root.resolve()
        requested_output_dir = args.output_dir.expanduser()
        if requested_output_dir.is_symlink() or not requested_output_dir.is_dir():
            raise ModelDataReportError(
                "output-dir must be an existing regular directory"
            )
        output_dir = requested_output_dir.resolve()
        request = json.loads(input_path.read_text(encoding="utf-8"))
        policy = _selective_report_policy()
        if policy is not None:
            if not isinstance(request, dict):
                raise ModelDataReportError("Report input must be an object")
            if policy.report_pipeline(request.get("workflow_id", "")) is None:
                sys.stdout.write(
                    json.dumps(
                        {
                            "status": "not_applicable",
                            "reason": "pipeline_not_selected",
                            "server_receipt": {"status": "not_requested"},
                        }
                    )
                    + "\n"
                )
                return 0
            raise ModelDataReportError(
                "Vera reports are generated by Studio Archive start/end writes, not from an agent-authored input file; use show --report to read the automatic report"
            )
        report, markdown = build_model_data_report(
            request,
            evidence_root=evidence_root,
        )
        json_path = output_dir / "model_data_report.json"
        markdown_path = output_dir / "model_data_report.md"
        if report["schema_version"] == 2:
            product_root = _installed_product_root()
            if product_root is None:
                raise ModelDataReportError(
                    "Cannot retain the governing product contract"
                )
            binding = report["privacy_contract"]
            contract_path = (
                product_root / f"privacy/contracts/{binding['workstream']}.json"
            )
            retained_contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract_module = _privacy_contract_module(product_root)
            contract_bytes = contract_module.canonical_bytes(retained_contract)
            if hashlib.sha256(contract_bytes).hexdigest() != binding["contract_sha256"]:
                raise ModelDataReportError(
                    "Governing contract changed while saving the report"
                )
            _write_once_or_identical(
                output_dir / "privacy_contract.json", contract_bytes
            )
        _write_once_or_identical(json_path, _canonical_bytes(report))
        _write_once_or_identical(markdown_path, markdown.encode("utf-8"))
        if not server_attestation or args.local_only:
            server_receipt = {"status": "not_requested", "reason": "local_only"}
        else:
            from notarized_run_receipt import (
                NotarizedRunReceiptError,
                stamp_model_data_report,
            )

            try:
                server_receipt = stamp_model_data_report(
                    json_path,
                    output_dir=output_dir,
                    plugin_root=Path(__file__).resolve().parents[1],
                )
            except NotarizedRunReceiptError as exc:
                # Auxiliary delivery cannot invalidate completed local artifacts.
                server_receipt = {"status": "pending", "reason": str(exc)}
                request_path = output_dir / "model_data_receipt_request.json"
                if request_path.is_file() and not request_path.is_symlink():
                    server_receipt["request_path"] = str(request_path)
        sys.stdout.write(
            json.dumps(
                {
                    "status": "written",
                    "report_id": report["report_id"],
                    "json_path": str(json_path),
                    "markdown_path": str(markdown_path),
                    **(
                        {
                            "privacy_contract_path": str(
                                output_dir / "privacy_contract.json"
                            )
                        }
                        if report["schema_version"] == 2
                        else {}
                    ),
                    "display_markdown": markdown,
                    "server_receipt": server_receipt,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        return 0
    except (ModelDataReportError, json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(f"model-data-report: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
