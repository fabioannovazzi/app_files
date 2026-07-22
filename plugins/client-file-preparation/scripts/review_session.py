from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from detect_duplicates import DuplicateCandidate
from extract_documents import DocumentEvidence
from parse_fatturapa_xml import InvoiceXmlRecord, localize_formal_anomaly
from parse_fiscal_forms import (
    SUMMARY_COPY,
    FiscalField,
    localize_field_label,
    localize_warning,
)
from scan_folder import (
    CATEGORY_CH_BANK_TAX,
    CATEGORY_CH_GE_TAX,
    CATEGORY_CH_SALARY_CERTIFICATE,
    CATEGORY_CH_TAX_ASSESSMENT,
    CATEGORY_CH_TAX_RETURN,
    CATEGORY_CH_ZH_TAX,
    CATEGORY_NON_CLASSIFICATI,
    CATEGORY_UK_BANK_TAX,
    CATEGORY_UK_HMRC_NOTICE,
    CATEGORY_UK_PAYSLIP,
    CATEGORY_UK_SELF_ASSESSMENT,
    CATEGORY_UK_YEAR_END_PAYROLL,
    MAX_SOURCE_ENTRIES,
    MAX_SOURCE_FILE_BYTES,
    MAX_SOURCE_FILES,
    MAX_SOURCE_TOTAL_BYTES,
    FileRecord,
)

__all__ = [
    "ReviewSessionResult",
    "RunIntakeResult",
    "write_review_session_artifacts",
    "write_run_intake",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "client-file-preparation"
WORKFLOW_NAME = "client-file-preparation"
MAX_PREVIEW_CHARS = 2000
PACKAGE_HASH_BASIS = "sorted_outputs_path_size_sha256_canonical_json_v1"
INVENTORY_REQUIRED_COLUMNS = [
    "relative_path",
    "file_name",
    "extension",
    "size_bytes",
    "modified_iso",
    "sha256",
    "category",
    "confidence",
    "years",
    "notes",
]
STRUCTURED_FIELDS_REQUIRED_COLUMNS = [
    "relative_path",
    "file_name",
    "document_kind",
    "field_code",
    "label",
    "value",
    "confidence",
]
XML_SUMMARY_REQUIRED_COLUMNS = [
    "relative_path",
    "file_name",
    "supplier_vat",
    "invoice_date",
    "invoice_number",
    "total_amount",
    "malformed",
]

CONFIDENCE_COPY = {
    "it": {"alta": "alta", "media": "media", "bassa": "bassa"},
    "en": {"alta": "high", "media": "medium", "bassa": "low"},
    "fr": {"alta": "élevée", "media": "moyenne", "bassa": "faible"},
    "de": {"alta": "hoch", "media": "mittel", "bassa": "niedrig"},
}

CATEGORY_COPY = {
    "en": {
        "730 / precompilata": "Italian 730 / pre-filled return",
        "fatture elettroniche XML": "electronic invoices (XML)",
        "ricevute sanitarie": "medical receipts",
        "mutuo": "mortgage",
        "affitto / locazione": "rent / lease",
        "assicurazioni": "insurance",
        "previdenza": "social security",
        "avvisi / comunicazioni": "notices / communications",
        "contratti": "contracts",
        "documenti non classificati": "unclassified documents",
    },
    "fr": {
        "730 / precompilata": "déclaration italienne 730 / préremplie",
        "fatture elettroniche XML": "factures électroniques XML",
        "ricevute sanitarie": "reçus médicaux",
        "mutuo": "prêt hypothécaire",
        "affitto / locazione": "loyer / bail",
        "assicurazioni": "assurances",
        "previdenza": "prévoyance sociale",
        "avvisi / comunicazioni": "avis / communications",
        "contratti": "contrats",
        "documenti non classificati": "documents non classés",
        CATEGORY_CH_GE_TAX: "documents fiscaux genevois",
        CATEGORY_CH_ZH_TAX: "documents fiscaux zurichois",
        CATEGORY_CH_TAX_RETURN: "déclaration fiscale suisse",
        CATEGORY_CH_TAX_ASSESSMENT: "taxation suisse",
        CATEGORY_CH_SALARY_CERTIFICATE: "certificat de salaire suisse",
        CATEGORY_CH_BANK_TAX: "attestations fiscales bancaires et d’impôt anticipé suisses",
        CATEGORY_UK_YEAR_END_PAYROLL: "documents britanniques P60 / P45 / P11D",
        CATEGORY_UK_PAYSLIP: "bulletin de salaire britannique",
        CATEGORY_UK_SELF_ASSESSMENT: "déclaration britannique Self Assessment",
        CATEGORY_UK_HMRC_NOTICE: "avis HMRC britanniques",
        CATEGORY_UK_BANK_TAX: "attestations fiscales bancaires et d’investissement britanniques",
    },
    "de": {
        "730 / precompilata": "italienische Erklärung 730 / vorausgefüllt",
        "fatture elettroniche XML": "elektronische Rechnungen (XML)",
        "ricevute sanitarie": "Gesundheitsbelege",
        "mutuo": "Hypothek",
        "affitto / locazione": "Miete / Pacht",
        "assicurazioni": "Versicherungen",
        "previdenza": "Sozialversicherung",
        "avvisi / comunicazioni": "Bescheide / Mitteilungen",
        "contratti": "Verträge",
        "documenti non classificati": "nicht klassifizierte Dokumente",
        CATEGORY_CH_GE_TAX: "Genfer Steuerunterlagen",
        CATEGORY_CH_ZH_TAX: "Zürcher Steuerunterlagen",
        CATEGORY_CH_TAX_RETURN: "Schweizer Steuererklärung",
        CATEGORY_CH_TAX_ASSESSMENT: "Schweizer Steuerveranlagung",
        CATEGORY_CH_SALARY_CERTIFICATE: "Schweizer Lohnausweis",
        CATEGORY_CH_BANK_TAX: "Schweizer Bank- und Verrechnungssteuerbescheinigungen",
        CATEGORY_UK_YEAR_END_PAYROLL: "britische P60-/P45-/P11D-Unterlagen",
        CATEGORY_UK_PAYSLIP: "britische Lohnabrechnung",
        CATEGORY_UK_SELF_ASSESSMENT: "britische Self-Assessment-Steuererklärung",
        CATEGORY_UK_HMRC_NOTICE: "britische HMRC-Mitteilungen",
        CATEGORY_UK_BANK_TAX: "britische Bank- und Kapitalertragsteuerbescheinigungen",
    },
}


def _localized_confidence(value: str, language: str) -> str:
    return CONFIDENCE_COPY[language].get(value, value)


def _localized_category(value: str, language: str) -> str:
    return CATEGORY_COPY.get(language, {}).get(value, value)


def _localized_note(value: str, language: str, target_year: int | None = None) -> str:
    if language == "it":
        return value
    if value == "classificazione non certa":
        return {
            "en": "classification uncertain",
            "fr": "classification incertaine",
            "de": "Klassifizierung unklar",
        }[language]
    if value.startswith("anno non coerente"):
        return {
            "en": f"year differs from target {target_year}",
            "fr": f"année différente de la cible {target_year}",
            "de": f"Jahr weicht vom Zieljahr {target_year} ab",
        }[language]
    if value.startswith("immagine"):
        return {
            "en": "image: possible receipt or scanned document",
            "fr": "image : reçu possible ou document numérisé",
            "de": "Bild: möglicher Beleg oder gescanntes Dokument",
        }[language]
    if value.startswith("XML generico"):
        return {
            "en": "generic XML: FatturaPA structure not identified",
            "fr": "XML générique : structure FatturaPA non identifiée",
            "de": "Generisches XML: FatturaPA-Struktur nicht erkannt",
        }[language]
    if value == "collegamento simbolico non seguito":
        return {
            "en": "symbolic link not followed",
            "fr": "lien symbolique non suivi",
            "de": "symbolischer Link wurde nicht verfolgt",
        }[language]
    return value


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before the heavier extraction steps."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for a client-file-preparation run."""

    run_intake_path: Path
    review_payload_path: Path
    ui_decisions_path: Path
    final_artifacts_path: Path
    review_item_count: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_id() -> str:
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    return f"{PLUGIN_NAME}-{timestamp}-{secrets.token_hex(8)}"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _harden_owner_only_tree(output_dir: Path) -> None:
    """Make the completed local review package private before returning it."""

    output_dir.chmod(0o700)
    for path in output_dir.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"L'output non può contenere link simbolici: {path}")
        path.chmod(0o700 if path.is_dir() else 0o600)


def _write_review_handoff_card(
    output_dir: Path,
    *,
    run_id: str,
    validate_tool: str,
    render_tool: str,
    save_tool: str,
    apply_tool: str,
    language: str = "it",
) -> Path:
    path = output_dir / "review_handoff.md"
    copy = {
        "it": {
            "product": "Preparazione del fascicolo cliente",
            "title": "Passaggio alla revisione",
            "run": "ID esecuzione",
            "payload": "Payload di revisione",
            "intake": "Dati di esecuzione",
            "pending": "Decisioni in attesa",
            "applied": "Decisioni applicate",
            "artifacts": "Artefatti finali",
            "heading": "Revisione in Codex",
            "validate": "Validare il payload con",
            "render": "Aprire l’area di revisione con",
            "save": "Salvare le decisioni con",
            "apply": "Applicare le decisioni con",
            "notice": "Il salvataggio e l’applicazione persistenti richiedono la superficie MCP o il server locale. Il fallback HTML statico può soltanto copiare o scaricare il JSON delle decisioni.",
        },
        "en": {
            "product": "Client file preparation",
            "title": "Review handoff",
            "run": "Run ID",
            "payload": "Review payload",
            "intake": "Run intake",
            "pending": "Pending decisions",
            "applied": "Applied decisions",
            "artifacts": "Final artifacts",
            "heading": "Review in Codex",
            "validate": "Validate the payload with",
            "render": "Open the review workbench with",
            "save": "Save reviewer actions with",
            "apply": "Apply reviewer actions with",
            "notice": "Persistent save and apply require the MCP or local-server review surface. The static HTML fallback can only copy or download decision JSON.",
        },
        "fr": {
            "product": "Préparation du dossier client",
            "title": "Passage à la revue",
            "run": "ID d’exécution",
            "payload": "Données de revue",
            "intake": "Paramètres d’exécution",
            "pending": "Décisions en attente",
            "applied": "Décisions appliquées",
            "artifacts": "Livrables finaux",
            "heading": "Revue dans Codex",
            "validate": "Valider les données avec",
            "render": "Ouvrir l’espace de revue avec",
            "save": "Enregistrer les décisions avec",
            "apply": "Appliquer les décisions avec",
            "notice": "L’enregistrement et l’application persistants exigent la surface MCP ou le serveur local. Le mode HTML statique peut uniquement copier ou télécharger le JSON des décisions.",
        },
        "de": {
            "product": "Vorbereitung der Mandantenakte",
            "title": "Übergabe zur Prüfung",
            "run": "Lauf-ID",
            "payload": "Prüfdaten",
            "intake": "Laufdaten",
            "pending": "Ausstehende Entscheidungen",
            "applied": "Angewandte Entscheidungen",
            "artifacts": "Endartefakte",
            "heading": "Prüfung in Codex",
            "validate": "Prüfdaten validieren mit",
            "render": "Prüfansicht öffnen mit",
            "save": "Entscheidungen speichern mit",
            "apply": "Entscheidungen anwenden mit",
            "notice": "Dauerhaftes Speichern und Anwenden erfordern die MCP- oder lokale Server-Prüfansicht. Der statische HTML-Fallback kann Entscheidungs-JSON nur kopieren oder herunterladen.",
        },
    }[language]
    lines = [
        f"# {copy['product']} · {copy['title']}",
        "<!-- review-contract: Review Handoff -->",
        "",
        f"- {copy['run']}: `{run_id}`",
        f"- {copy['payload']}: `review_payload.json`",
        f"- {copy['intake']}: `run_intake.json`",
        f"- {copy['pending']}: `ui_decisions.json`",
        f"- {copy['applied']}: `applied_decisions.json`",
        f"- {copy['artifacts']}: `final_artifacts.json`",
        "",
        f"## {copy['heading']}",
        f"1. {copy['validate']} `{validate_tool}`.",
        f"2. {copy['render']} `{render_tool}`.",
        f"3. {copy['save']} `{save_tool}`.",
        f"4. {copy['apply']} `{apply_tool}`.",
        "",
        copy["notice"],
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _review_handoff_output_record(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "kind": "md",
        "status": "written",
        "required_text": [
            "Review Handoff",
            "review_payload.json",
            "ui_decisions.json",
            "applied_decisions.json",
            "final_artifacts.json",
        ],
        "qa_checks": ["nonempty_text", "required_text"],
    }


def _local_output_refs(final_artifacts_path: Path) -> list[str]:
    refs = [
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    ]
    payload = json.loads(final_artifacts_path.read_text(encoding="utf-8"))
    outputs = payload.get("outputs")
    if isinstance(outputs, list):
        for output in outputs:
            if not isinstance(output, dict):
                continue
            path_value = output.get("path")
            if (
                isinstance(path_value, str)
                and path_value.strip()
                and "://" not in path_value
            ):
                refs.append(path_value.strip())
    return list(dict.fromkeys(refs))


def _append_execution_trace(
    run_intake_path: Path,
    final_artifacts_path: Path,
    *,
    command: Sequence[str],
) -> None:
    payload = json.loads(run_intake_path.read_text(encoding="utf-8"))
    data_posture = payload.get("data_posture")
    local_files = (
        data_posture.get("local_files_read") if isinstance(data_posture, dict) else None
    )
    inputs = (
        local_files if isinstance(local_files, list) else payload.get("input_paths", [])
    )
    payload["execution_trace"] = [
        {
            "step_id": f"{WORKFLOW_NAME}_review_session",
            "kind": "deterministic_review_session",
            "status": "passed",
            "execution_location": "local_codex_workspace",
            "command": list(command),
            "inputs": [str(entry) for entry in inputs if entry],
            "outputs": _local_output_refs(final_artifacts_path),
        }
    ]
    _write_json(run_intake_path, payload)


def _category_counts(records: Sequence[FileRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.category] = counts.get(record.category, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _as_output_ref(path: Path, output_dir: Path) -> str:
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _read_preview(path: Path, limit: int = MAX_PREVIEW_CHARS) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit].strip()
    except OSError:
        return ""


def _evidence_by_path(
    document_evidence: Sequence[DocumentEvidence],
) -> dict[str, DocumentEvidence]:
    return {item.relative_path: item for item in document_evidence}


def _fiscal_field_counts(fields: Sequence[FiscalField]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field in fields:
        counts[field.relative_path] = counts.get(field.relative_path, 0) + 1
    return counts


def _base_item(
    item_id: str,
    item_type: str,
    title: str,
    *,
    allowed_actions: Sequence[str],
    recommended_action: str,
    source_path: str | None = None,
    output_path: str | None = None,
    evidence: Sequence[dict[str, Any]] = (),
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "item_type": item_type,
        "title": title,
        "source_path": source_path,
        "output_path": output_path,
        "allowed_actions": list(allowed_actions),
        "recommended_action": recommended_action,
        "evidence": list(evidence),
        "data": data or {},
        "status": "needs_review",
    }


def _document_item(
    index: int,
    record: FileRecord,
    output_dir: Path,
    evidence: DocumentEvidence | None,
    fiscal_field_count: int,
    *,
    include_preview: bool,
    language: str,
) -> dict[str, Any]:
    evidence_refs: list[dict[str, Any]] = []
    if include_preview and evidence and evidence.text_path:
        text_path = output_dir / "extracted" / evidence.text_path
        evidence_refs.append(
            {
                "kind": "extracted_text",
                "path": _as_output_ref(text_path, output_dir),
                "preview": _read_preview(text_path, limit=600),
            }
        )
    if evidence:
        evidence_refs.append(
            {
                "kind": "extraction_result",
                "readable": evidence.readable,
                "method": evidence.extraction_method,
                "confidence": _localized_confidence(evidence.confidence, language),
                "notes": [_localized_note(note, language) for note in evidence.notes],
            }
        )
    needs_attention = (
        record.category == CATEGORY_NON_CLASSIFICATI
        or record.confidence != "alta"
        or bool(record.notes)
        or evidence is None
        or not evidence.readable
        or bool(evidence.notes)
        or evidence.extraction_method.startswith("unsupported")
    )
    return _base_item(
        f"document-{index}",
        "document_inventory",
        record.relative_path,
        source_path=record.relative_path,
        allowed_actions=("accept", "mark_unclear", "skip"),
        recommended_action="mark_unclear" if needs_attention else "accept",
        evidence=evidence_refs,
        data=(
            record.as_row()
            | {
                "category": _localized_category(record.category, language),
                "confidence": _localized_confidence(record.confidence, language),
                "notes": " | ".join(
                    _localized_note(note, language) for note in record.notes
                ),
            }
        )
        | {
            "readable": evidence.readable if evidence else None,
            "extraction_method": evidence.extraction_method if evidence else None,
            "text_path": evidence.text_path if evidence else "",
            "structured_field_count": fiscal_field_count,
        },
    )


def _uncertain_document_items(
    records: Sequence[FileRecord],
    evidence_lookup: dict[str, DocumentEvidence],
    target_year: int | None,
    language: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        evidence = evidence_lookup.get(record.relative_path)
        reason_codes: list[str] = []
        if record.category == CATEGORY_NON_CLASSIFICATI:
            reason_codes.append("unclassified_document")
        if record.confidence != "alta":
            reason_codes.append("classification_below_high")
        if record.notes:
            reason_codes.extend(record.notes)
        if target_year is not None and record.years and target_year not in record.years:
            reason_codes.append("year_outside_target")
        if evidence is not None and not evidence.readable:
            reason_codes.append("text_unreadable")
        if not reason_codes:
            continue
        reason_copy = {
            "unclassified_document": {
                "it": "documento non classificato",
                "en": "unclassified document",
                "fr": "document non classé",
                "de": "nicht klassifiziertes Dokument",
            },
            "classification_below_high": {
                "it": "classificazione non alta",
                "en": "classification confidence below high",
                "fr": "niveau de confiance inférieur à élevé",
                "de": "Klassifizierungsvertrauen unter hoch",
            },
            "year_outside_target": {
                "it": "anno fuori target",
                "en": "year outside target",
                "fr": "année hors cible",
                "de": "Jahr außerhalb des Zieljahres",
            },
            "text_unreadable": {
                "it": "testo non leggibile",
                "en": "text unreadable",
                "fr": "texte illisible",
                "de": "Text nicht lesbar",
            },
        }
        reasons = [
            reason_copy.get(code, {}).get(
                language,
                _localized_note(code, language, target_year),
            )
            for code in reason_codes
        ]
        items.append(
            _base_item(
                f"uncertain-file-{index}",
                "uncertain_file",
                record.relative_path,
                source_path=record.relative_path,
                allowed_actions=("accept", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                data={
                    "category": _localized_category(record.category, language),
                    "confidence": _localized_confidence(record.confidence, language),
                    "reasons": reasons,
                    "years": list(record.years),
                },
            )
        )
    return items


def _missing_document_items(
    missing_items: Sequence[str],
    language: str,
) -> list[dict[str, Any]]:
    title = {
        "it": "Richiesta mancante/incerta",
        "en": "Missing/uncertain request",
        "fr": "Demande manquante/incertaine",
        "de": "Fehlende/unklare Anforderung",
    }[language]
    return [
        _base_item(
            f"missing-document-{index}",
            "missing_document_request",
            f"{title} {index}",
            allowed_actions=("accept", "reject", "request_more_documents"),
            recommended_action="accept",
            output_path="02_documenti_mancanti_o_incerti.md",
            data={"request_text": item},
        )
        for index, item in enumerate(missing_items, start=1)
    ]


def _fiscal_field_items(
    fields: Sequence[FiscalField],
    *,
    include_preview: bool,
    language: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, field in enumerate(fields, start=1):
        data = field.as_row()
        evidence_text = data.pop("evidence", "")
        data["label"] = localize_field_label(field.label, language)
        data["confidence"] = _localized_confidence(field.confidence, language)
        evidence = [
            {
                "kind": "structured_field_extraction",
                "warnings": [
                    localize_warning(warning, language) for warning in field.warnings
                ],
            }
        ]
        if include_preview and evidence_text:
            evidence.append({"kind": "snippet", "text": evidence_text})
        items.append(
            _base_item(
                f"fiscal-field-{index}",
                "extracted_fiscal_field",
                f"{field.document_kind}: {localize_field_label(field.label, language)}",
                source_path=field.relative_path,
                output_path="extracted/structured_fiscal_fields.csv",
                allowed_actions=("accept", "mark_unclear", "skip"),
                recommended_action=(
                    "accept"
                    if field.confidence in {"alta", "media"}
                    else "mark_unclear"
                ),
                evidence=evidence,
                data=data,
            )
        )
    return items


def _draft_item(
    item_id: str,
    item_type: str,
    title: str,
    output_dir: Path,
    relative_path: str,
    *,
    include_preview: bool,
) -> dict[str, Any]:
    path = output_dir / relative_path
    return _base_item(
        item_id,
        item_type,
        title,
        output_path=relative_path,
        allowed_actions=("accept", "edit", "mark_unclear", "skip"),
        recommended_action="accept" if path.exists() else "mark_unclear",
        data={
            "path": relative_path,
            "exists": path.exists(),
        }
        | ({"preview": _read_preview(path)} if include_preview else {}),
    )


def _duplicate_items(
    candidates: Sequence[DuplicateCandidate],
    language: str,
) -> list[dict[str, Any]]:
    return [
        _base_item(
            f"duplicate-{index}",
            "duplicate_warning",
            candidate.relative_path,
            source_path=candidate.relative_path,
            output_path="duplicate_candidates.csv",
            allowed_actions=("accept", "reject", "mark_unclear", "skip"),
            recommended_action="mark_unclear",
            data=candidate.as_row()
            | {
                "duplicate_type": {
                    "hash-identico": {
                        "it": "hash identico",
                        "en": "identical hash",
                        "fr": "empreinte identique",
                        "de": "identischer Hash",
                    },
                    "nome-dimensione-simile": {
                        "it": "nome e dimensione simili",
                        "en": "similar name and size",
                        "fr": "nom et taille similaires",
                        "de": "ähnlicher Name und ähnliche Größe",
                    },
                }
                .get(candidate.duplicate_type, {})
                .get(
                    language,
                    candidate.duplicate_type,
                )
            },
        )
        for index, candidate in enumerate(candidates, start=1)
    ]


def _xml_anomaly_items(
    records: Sequence[InvoiceXmlRecord],
    language: str,
) -> list[dict[str, Any]]:
    return [
        _base_item(
            f"xml-anomaly-{index}",
            "formal_xml_anomaly",
            record.relative_path,
            source_path=record.relative_path,
            output_path="fatture/formal_anomalies.md",
            allowed_actions=("accept", "mark_unclear", "skip"),
            recommended_action="mark_unclear",
            data=record.as_json()
            | {
                "anomalies": [
                    localize_formal_anomaly(value, language)
                    for value in record.anomalies
                ]
            },
        )
        for index, record in enumerate(records, start=1)
        if record.malformed or record.anomalies
    ]


def _review_columns(language: str) -> list[dict[str, str]]:
    labels = {
        "it": ("Tipo", "Elemento", "Azione suggerita", "Fonte", "Output", "Stato"),
        "en": ("Type", "Item", "Suggested action", "Source", "Output", "Status"),
        "fr": ("Type", "Élément", "Action suggérée", "Source", "Sortie", "Statut"),
        "de": ("Typ", "Element", "Empfohlene Aktion", "Quelle", "Ausgabe", "Status"),
    }[language]
    return [
        {"field": field, "label": label}
        for field, label in zip(
            (
                "item_type",
                "title",
                "recommended_action",
                "source_path",
                "output_path",
                "status",
            ),
            labels,
            strict=True,
        )
    ]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _first_clean(values: Sequence[Any]) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _first_record_path(records: Sequence[FileRecord]) -> str:
    return _first_clean([record.relative_path for record in records])


def _first_field_text(fields: Sequence[FiscalField]) -> str:
    for field in fields:
        text = _clean_text(field.field_code or field.label or field.document_kind)
        if text:
            return text
    return ""


def _append_if_text(target: list[str], value: Any) -> None:
    text = _clean_text(value)
    if text and text not in target:
        target.append(text)


def _required_text_by_path(
    *,
    client_name: str,
    target_year: int | None,
    records: Sequence[FileRecord],
    missing_items: Sequence[str],
    professional_questions: Sequence[str],
    client_questions: Sequence[str],
    structured_fields: Sequence[FiscalField],
    language: str,
) -> dict[str, list[str]]:
    copy = {
        "it": {
            "year_missing": "non indicato",
            "environment": "# Controllo ambiente",
            "index": "# Indice fascicolo",
            "year": "Anno target",
            "files": "File analizzati",
            "missing": "# Documenti mancanti o incerti",
            "questions": "# Domande interne dello studio",
            "memo": "# Memo di istruttoria clienti",
            "client": "Cliente",
            "memo_year": "Anno",
            "documents": "## Documenti ricevuti",
            "memo_missing": "## Elementi mancanti o incerti",
            "studio": "# Scheda per lo studio",
            "summary": "## Sintesi del fascicolo",
            "fields": "Campi fiscali strutturati estratti",
            "studio_missing": "## Punti mancanti o incerti",
            "email_subject": "Oggetto: Documenti e chiarimenti per completare l'istruttoria",
            "email_draft": "# Bozza email cliente",
            "email_empty": "Nessuna richiesta cliente generata automaticamente",
            "handoff": "Passaggio alla revisione",
        },
        "en": {
            "year_missing": "not specified",
            "environment": "# Environment check",
            "index": "# Client file index",
            "year": "Target year",
            "files": "Files reviewed",
            "missing": "# Missing or uncertain documents",
            "questions": "# Questions for the firm",
            "memo": "# Client file-preparation memo",
            "client": "Client",
            "memo_year": "Year",
            "documents": "## Documents received",
            "memo_missing": "## Missing or uncertain items",
            "studio": "# File-preparation brief for the firm",
            "summary": "## File summary",
            "fields": "Structured fiscal fields extracted",
            "studio_missing": "## Missing or uncertain items",
            "email_subject": "Subject: Documents and clarifications needed to complete file preparation",
            "email_draft": "# Draft client email",
            "email_empty": "The formal checks did not generate a client request",
            "handoff": "Review handoff",
        },
        "fr": {
            "year_missing": "non indiquée",
            "environment": "# Contrôle de l’environnement",
            "index": "# Index du dossier client",
            "year": "Année cible",
            "files": "Fichiers examinés",
            "missing": "# Documents manquants ou incertains",
            "questions": "# Questions internes du cabinet",
            "memo": "# Note de préparation du dossier client",
            "client": "Client",
            "memo_year": "Année",
            "documents": "## Documents reçus",
            "memo_missing": "## Éléments manquants ou incertains",
            "studio": "# Fiche de préparation pour le cabinet",
            "summary": "## Synthèse du dossier",
            "fields": "Champs fiscaux structurés extraits",
            "studio_missing": "## Éléments manquants ou incertains",
            "email_subject": "Objet : Documents et précisions nécessaires pour compléter le dossier",
            "email_draft": "# Projet d’e-mail au client",
            "email_empty": "Les contrôles formels n’ont généré aucune demande au client",
            "handoff": "Passage à la revue",
        },
        "de": {
            "year_missing": "nicht angegeben",
            "environment": "# Umgebungsprüfung",
            "index": "# Index der Mandantenakte",
            "year": "Zieljahr",
            "files": "Geprüfte Dateien",
            "missing": "# Fehlende oder unklare Unterlagen",
            "questions": "# Interne Fragen der Kanzlei",
            "memo": "# Arbeitsvermerk zur Mandantenakte",
            "client": "Mandant",
            "memo_year": "Jahr",
            "documents": "## Erhaltene Unterlagen",
            "memo_missing": "## Fehlende oder unklare Punkte",
            "studio": "# Arbeitsübersicht für die Kanzlei",
            "summary": "## Zusammenfassung der Akte",
            "fields": "Extrahierte strukturierte Steuerfelder",
            "studio_missing": "## Fehlende oder unklare Punkte",
            "email_subject": "Betreff: Unterlagen und Angaben zur Vervollständigung der Akte",
            "email_draft": "# Entwurf der Mandanten-E-Mail",
            "email_empty": "Aus den formalen Prüfungen ergab sich keine Anfrage an den Mandanten",
            "handoff": "Übergabe zur Prüfung",
        },
    }[language]
    fiscal_copy = SUMMARY_COPY[language]
    year_text = str(target_year) if target_year is not None else copy["year_missing"]
    first_record = _first_record_path(records)
    first_missing = _first_clean(missing_items)
    first_professional_question = _first_clean(professional_questions)
    first_client_question = _first_clean(client_questions)
    first_field = _first_field_text(structured_fields)

    required = {
        "00_environment_check.md": [copy["environment"]],
        "00_fascicolo_index.md": [
            copy["index"],
            f"{copy['year']}: {year_text}",
            f"{copy['files']}: {len(records)}",
        ],
        "02_documenti_mancanti_o_incerti.md": [copy["missing"]],
        "03_domande_interne_studio.md": [copy["questions"]],
        "04_bozza_email_cliente.md": [],
        "06_memo_istruttoria.md": [
            copy["memo"],
            f"{copy['client']} {client_name}",
            f"{copy['memo_year']} {year_text}",
            f"{copy['files']}: {len(records)}.",
            copy["documents"],
            copy["memo_missing"],
        ],
        "07_scheda_codex_per_studio.md": [
            copy["studio"],
            client_name,
            year_text,
            copy["summary"],
            f"{copy['files']}: {len(records)}",
            f"{copy['fields']}: {len(structured_fields)}",
            copy["studio_missing"],
        ],
        "08_dati_fiscali_strutturati.md": [
            f"# {fiscal_copy['title']}",
            f"{fiscal_copy['field_count']}: {len(structured_fields)}",
        ],
        "review_handoff.md": [
            "Review Handoff",
            copy["handoff"],
            "review_payload.json",
            "ui_decisions.json",
            "applied_decisions.json",
            "final_artifacts.json",
        ],
    }

    _append_if_text(required["00_fascicolo_index.md"], first_record)
    _append_if_text(required["02_documenti_mancanti_o_incerti.md"], first_missing)
    _append_if_text(
        required["03_domande_interne_studio.md"], first_professional_question
    )
    if first_client_question:
        required["04_bozza_email_cliente.md"] = [
            copy["email_subject"],
            client_name,
            first_client_question,
        ]
    else:
        required["04_bozza_email_cliente.md"] = [
            copy["email_draft"],
            copy["email_empty"],
        ]
    _append_if_text(required["06_memo_istruttoria.md"], first_missing)
    _append_if_text(required["06_memo_istruttoria.md"], first_professional_question)
    _append_if_text(required["06_memo_istruttoria.md"], first_client_question)
    _append_if_text(required["07_scheda_codex_per_studio.md"], first_missing)
    _append_if_text(
        required["07_scheda_codex_per_studio.md"], first_professional_question
    )
    _append_if_text(required["07_scheda_codex_per_studio.md"], first_client_question)
    _append_if_text(required["08_dati_fiscali_strutturati.md"], first_field)
    return required


def _output_records(
    output_dir: Path,
    *,
    client_name: str,
    target_year: int | None,
    records: Sequence[FileRecord],
    missing_items: Sequence[str],
    professional_questions: Sequence[str],
    client_questions: Sequence[str],
    structured_fields: Sequence[FiscalField],
    xml_records: Sequence[InvoiceXmlRecord],
    language: str,
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    review_files = {"final_artifacts.json"}
    required_text_by_path = _required_text_by_path(
        client_name=client_name,
        target_year=target_year,
        records=records,
        missing_items=missing_items,
        professional_questions=professional_questions,
        client_questions=client_questions,
        structured_fields=structured_fields,
        language=language,
    )
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name in review_files:
            continue
        relative = path.relative_to(output_dir).as_posix()
        output = {
            "path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
            "kind": path.suffix.lower().lstrip(".") or "file",
            "status": "written",
        }
        required_text = required_text_by_path.get(relative)
        if required_text:
            output["required_text"] = required_text
            output["qa_checks"] = ["nonempty_text", "required_text"]
        if relative == "01_document_inventory.csv":
            output["row_count"] = len(records)
            output["required_columns"] = INVENTORY_REQUIRED_COLUMNS
        elif relative == "extracted/structured_fiscal_fields.csv":
            output["row_count"] = len(structured_fields)
            output["required_columns"] = STRUCTURED_FIELDS_REQUIRED_COLUMNS
        elif relative == "extracted/structured_fiscal_fields.jsonl":
            output["row_count"] = len(structured_fields)
            output["required_columns"] = STRUCTURED_FIELDS_REQUIRED_COLUMNS
        elif relative == "fatture/fatture_summary.csv":
            output["row_count"] = len(xml_records)
            output["required_columns"] = XML_SUMMARY_REQUIRED_COLUMNS
        outputs.append(output)
    return outputs


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_integrity(outputs: Sequence[dict[str, Any]]) -> dict[str, str]:
    """Hash the exact output inventory for reproducible cross-phase verification."""

    canonical_outputs = sorted(
        (
            {
                "path": str(output["path"]),
                "sha256": str(output["sha256"]),
                "size_bytes": int(output["size_bytes"]),
            }
            for output in outputs
        ),
        key=lambda output: output["path"].encode("utf-8"),
    )
    canonical = json.dumps(
        canonical_outputs,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "algorithm": "sha256",
        "package_hash_basis": PACKAGE_HASH_BASIS,
        "package_hash": hashlib.sha256(canonical).hexdigest(),
    }


def write_run_intake(
    output_dir: Path,
    root: Path,
    *,
    target_year: int | None,
    client_name: str,
    records: Sequence[FileRecord],
    missing_dependency_count: int,
    require_ocr: bool,
    enable_ocr: bool,
    ocr_lang: str,
    jurisdiction: str,
    language: str,
) -> RunIntakeResult:
    """Write the intake contract as soon as folder scope is known."""

    run_id = _run_id()
    data_posture_notes = {
        "it": [
            "Gli script esaminano localmente i file della cartella cliente e producono artefatti limitati per la review nell’interfaccia.",
            "Per impostazione predefinita non vengono usati connettori esterni, percorsi di upload, SQL remoto o notebook ospitati.",
        ],
        "en": [
            "Scripts inspect local customer-folder files and write bounded review artifacts for UI review.",
            "No external connector, upload path, remote SQL, or hosted notebook execution is used by default.",
        ],
        "fr": [
            "Les scripts examinent localement les fichiers du dossier client et produisent des artefacts limités pour la revue dans l’interface.",
            "Par défaut, aucun connecteur externe, chemin de téléversement, SQL distant ou notebook hébergé n’est utilisé.",
        ],
        "de": [
            "Die Skripte prüfen die Dateien des Mandantenordners lokal und erzeugen begrenzte Artefakte für die Prüfung in der Oberfläche.",
            "Standardmäßig werden keine externen Konnektoren, Upload-Pfade, Remote-SQL-Abfragen oder gehosteten Notebooks verwendet.",
        ],
    }[language]
    if enable_ocr or require_ocr:
        data_posture_notes.append(
            {
                "it": "Quando è abilitato o necessario, l’OCR legge i documenti locali prima della produzione degli artefatti limitati di review.",
                "en": "OCR, when enabled or required, reads local document files before bounded review artifacts are written.",
                "fr": "Lorsqu’il est activé ou requis, l’OCR lit les documents locaux avant la production des artefacts de revue limités.",
                "de": "Wenn OCR aktiviert oder erforderlich ist, liest es lokale Dokumente, bevor begrenzte Prüfartefakte erzeugt werden.",
            }[language]
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "jurisdiction": jurisdiction,
        "input_paths": [root.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "first_customer_folder_intake",
        "assumptions": {
            "client_name": client_name,
            "target_year": target_year,
            "ocr_requested": enable_ocr,
            "ocr_language": ocr_lang,
            "working_language": language,
            "jurisdiction": jurisdiction,
            "ocr_required_by_file_types": require_ocr,
            "category_counts": _category_counts(records),
            "file_count": len(records),
        },
        "source_snapshot": {
            "algorithm": "sha256",
            "limits": {
                "max_entry_count": MAX_SOURCE_ENTRIES,
                "max_file_count": MAX_SOURCE_FILES,
                "max_file_bytes": MAX_SOURCE_FILE_BYTES,
                "max_total_bytes": MAX_SOURCE_TOTAL_BYTES,
            },
            "observed": {
                "file_count": len(records),
                "regular_file_count": sum(bool(record.sha256) for record in records),
                "symlink_count": sum(not bool(record.sha256) for record in records),
                "total_regular_bytes": sum(
                    record.size_bytes for record in records if record.sha256
                ),
            },
            "files": [
                {
                    "relative_path": record.relative_path,
                    "size_bytes": record.size_bytes,
                    "modified_iso": record.modified_iso,
                    "sha256": record.sha256,
                    "entry_type": (
                        "regular_file" if record.sha256 else "symlink_not_followed"
                    ),
                }
                for record in records
            ],
        },
        "unresolved_questions": [],
        "dependency_check": {
            "missing_dependency_count": missing_dependency_count,
            "status": (
                "ok" if missing_dependency_count == 0 else "missing_optional_or_core"
            ),
        },
        "data_posture": {
            "local_files_read": [root.as_posix()],
            "model_excerpts_sent": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": data_posture_notes,
        },
        "status": "ready_for_extraction",
    }
    return RunIntakeResult(
        run_id=run_id,
        path=_write_json(output_dir / "run_intake.json", payload),
    )


def write_review_session_artifacts(
    output_dir: Path,
    root: Path,
    *,
    run_id: str,
    run_intake_path: Path,
    target_year: int | None,
    client_name: str,
    records: Sequence[FileRecord],
    document_evidence: Sequence[DocumentEvidence],
    structured_fields: Sequence[FiscalField],
    missing_items: Sequence[str],
    professional_questions: Sequence[str],
    client_questions: Sequence[str],
    duplicate_candidates: Sequence[DuplicateCandidate],
    xml_records: Sequence[InvoiceXmlRecord],
    jurisdiction: str,
    language: str,
    include_previews: bool = False,
) -> ReviewSessionResult:
    """Write review payload, pending decisions, and final artifact index."""

    evidence_lookup = _evidence_by_path(document_evidence)
    field_counts = _fiscal_field_counts(structured_fields)
    items: list[dict[str, Any]] = []
    items.extend(
        _document_item(
            index,
            record,
            output_dir,
            evidence_lookup.get(record.relative_path),
            field_counts.get(record.relative_path, 0),
            include_preview=include_previews,
            language=language,
        )
        for index, record in enumerate(records, start=1)
    )
    items.extend(
        _uncertain_document_items(
            records,
            evidence_lookup,
            target_year,
            language,
        )
    )
    items.extend(_missing_document_items(missing_items, language))
    items.extend(
        _fiscal_field_items(
            structured_fields,
            include_preview=include_previews,
            language=language,
        )
    )
    items.extend(_duplicate_items(duplicate_candidates, language))
    items.extend(_xml_anomaly_items(xml_records, language))
    items.append(
        _draft_item(
            "draft-studio-brief",
            "draft_memo_section",
            {
                "it": "Scheda operativa per lo studio",
                "en": "Operational brief for the firm",
                "fr": "Fiche opérationnelle pour le cabinet",
                "de": "Arbeitsübersicht für die Kanzlei",
            }[language],
            output_dir,
            "07_scheda_codex_per_studio.md",
            include_preview=include_previews,
        )
    )
    items.append(
        _draft_item(
            "draft-memo",
            "draft_memo_section",
            {
                "it": "Memo istruttoria per lo studio",
                "en": "File-preparation memo for the firm",
                "fr": "Note de préparation pour le cabinet",
                "de": "Arbeitsvermerk für die Kanzlei",
            }[language],
            output_dir,
            "06_memo_istruttoria.md",
            include_preview=include_previews,
        )
    )
    items.append(
        _draft_item(
            "draft-client-email",
            "draft_client_email",
            {
                "it": "Bozza email cliente",
                "en": "Draft client email",
                "fr": "Projet d’e-mail au client",
                "de": "Entwurf der Mandanten-E-Mail",
            }[language],
            output_dir,
            "04_bozza_email_cliente.md",
            include_preview=include_previews,
        )
    )

    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "jurisdiction": jurisdiction,
        "source_paths": [],
        "source_scope": {
            "kind": "local_customer_folder",
            "local_reference": "run_intake.json",
        },
        "preview_policy": {
            "mode": "explicit_opt_in",
            "previews_included": include_previews,
        },
        "review_type": "client_file_preparation_folder_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(language),
        "notices": [
            {
                "it": "Verificare gli elementi proposti rispetto ai file locali prima di applicare le decisioni.",
                "en": "Check proposed items against the local files before applying decisions.",
                "fr": "Vérifier les éléments proposés par rapport aux fichiers locaux avant d’appliquer les décisions.",
                "de": "Vorgeschlagene Punkte vor der Anwendung von Entscheidungen anhand der lokalen Dateien prüfen.",
            }[language],
            {
                "it": "I percorsi assoluti e le anteprime testuali restano locali salvo inclusione esplicita.",
                "en": "Absolute paths and text previews remain local unless explicitly included.",
                "fr": "Les chemins absolus et les aperçus textuels restent locaux sauf inclusion explicite.",
                "de": "Absolute Pfade und Textvorschauen bleiben lokal, sofern sie nicht ausdrücklich einbezogen werden.",
            }[language],
        ],
        "source_artifacts": {},
        "evidence": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "document_inventory": "01_document_inventory.csv",
            "missing_documents": "02_documenti_mancanti_o_incerti.md",
            "structured_fiscal_fields": "extracted/structured_fiscal_fields.csv",
            "memo": "06_memo_istruttoria.md",
            "client_email": "04_bozza_email_cliente.md",
        },
        "allowed_actions": [
            "accept",
            "reject",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "status": "ready_for_review",
        "summary": {
            "file_count": len(records),
            "uncertain_file_count": sum(
                1 for item in items if item["item_type"] == "uncertain_file"
            ),
            "missing_document_count": len(missing_items),
            "structured_field_count": len(structured_fields),
            "duplicate_count": len(duplicate_candidates),
            "xml_anomaly_count": sum(1 for record in xml_records if record.anomalies),
            "professional_questions": list(professional_questions),
        },
    }
    review_payload_path = _write_json(
        output_dir / "review_payload.json", review_payload
    )

    ui_decisions_path = _write_json(
        output_dir / "ui_decisions.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": run_id,
            "decided_at": None,
            "decision_source": "not_collected",
            "review_payload_path": review_payload_path.name,
            "decisions": [],
            "decision_count": 0,
            "status": "pending_review",
        },
    )

    review_handoff_path = _write_review_handoff_card(
        output_dir,
        run_id=run_id,
        validate_tool="validate_client_file_preparation_review",
        render_tool="render_client_file_preparation_review",
        save_tool="save_client_file_preparation_decisions",
        apply_tool="apply_client_file_preparation_decisions",
        language=language,
    )
    outputs = _output_records(
        output_dir,
        client_name=client_name,
        target_year=target_year,
        records=records,
        missing_items=missing_items,
        professional_questions=professional_questions,
        client_questions=client_questions,
        structured_fields=structured_fields,
        xml_records=xml_records,
        language=language,
    )
    manifest_copy = {
        "it": {
            "caveat": "ui_decisions.json resta in attesa finché una revisione Codex, l’interfaccia locale o il fallback non registra le decisioni.",
            "review": "Rivedere review_payload.json prima di modificare il memo dello studio o l’e-mail al cliente.",
            "persist": "Registrare le decisioni di accettazione, modifica o rifiuto in ui_decisions.json quando viene eseguita la revisione.",
        },
        "en": {
            "caveat": "ui_decisions.json remains pending until a Codex review, local interface, or fallback records reviewer decisions.",
            "review": "Review review_payload.json before revising the firm memo or client email.",
            "persist": "Record accept, edit, or reject decisions in ui_decisions.json when the review is performed.",
        },
        "fr": {
            "caveat": "ui_decisions.json reste en attente jusqu’à ce qu’une revue Codex, l’interface locale ou le mode de secours enregistre les décisions.",
            "review": "Examiner review_payload.json avant de modifier la note du cabinet ou l’e-mail au client.",
            "persist": "Enregistrer les décisions d’acceptation, de modification ou de rejet dans ui_decisions.json lors de la revue.",
        },
        "de": {
            "caveat": "ui_decisions.json bleibt ausstehend, bis eine Codex-Prüfung, die lokale Oberfläche oder der Fallback Entscheidungen erfasst.",
            "review": "review_payload.json vor der Überarbeitung des Kanzleivermerks oder der Mandanten-E-Mail prüfen.",
            "persist": "Annahme-, Änderungs- oder Ablehnungsentscheidungen bei der Prüfung in ui_decisions.json erfassen.",
        },
    }[language]
    final_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "completed_at": _utc_now(),
        "outputs": outputs,
        "integrity": _package_integrity(outputs),
        "caveats": [manifest_copy["caveat"]],
        "next_actions": [manifest_copy["review"], manifest_copy["persist"]],
        "status": "written_pending_review",
    }
    final_artifacts_path = _write_json(
        output_dir / "final_artifacts.json",
        final_payload,
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=[
            "python",
            "plugins/client-file-preparation/scripts/build_file_preparation_outputs.py",
        ],
    )
    # The trace update changes run_intake.json, so seal the package only after it.
    sealed_outputs = _output_records(
        output_dir,
        client_name=client_name,
        target_year=target_year,
        records=records,
        missing_items=missing_items,
        professional_questions=professional_questions,
        client_questions=client_questions,
        structured_fields=structured_fields,
        xml_records=xml_records,
        language=language,
    )
    final_payload["outputs"] = sealed_outputs
    final_payload["integrity"] = _package_integrity(sealed_outputs)
    _write_json(final_artifacts_path, final_payload)
    _harden_owner_only_tree(output_dir)

    return ReviewSessionResult(
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
