"""Project model-authored research into a revision-bound professional review UI."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["write_pipeline_review"]

ACTIONS = ["accept", "reject", "mark_unclear", "request_more_documents", "skip"]
PREVIEW_CHARACTERS = 12000
PREVIEW_COPY = {
    "it": (
        "Estratto: apri il documento originale per il testo completo.",
        "Testo salvato completo.",
    ),
    "en": (
        "Excerpt only; open the original artifact for the complete text.",
        "Complete saved text.",
    ),
    "fr": (
        "Extrait : ouvrez le document original pour le texte complet.",
        "Texte enregistré complet.",
    ),
    "de": (
        "Auszug: Öffnen Sie das Original für den vollständigen Text.",
        "Vollständiger gespeicherter Text.",
    ),
    "es": (
        "Extracto: abra el documento original para ver el texto completo.",
        "Texto guardado completo.",
    ),
}
ENCODING_LIMIT_COPY = {
    "it": "Anteprima non disponibile: la codifica della fonte non è supportata. Apri il file originale.",
    "en": "Text preview unavailable: the source encoding is unsupported. Open the original file.",
    "fr": "Aperçu indisponible : l'encodage de la source n'est pas pris en charge. Ouvrez le fichier original.",
    "de": "Textvorschau nicht verfügbar: Die Zeichenkodierung der Quelle wird nicht unterstützt. Öffnen Sie die Originaldatei.",
    "es": "Vista previa no disponible: la codificación de la fuente no es compatible. Abra el archivo original.",
}


def write_pipeline_review(root: Path, context: dict[str, Any]) -> dict[str, Any]:
    """Write faithful views and exact source bindings; never decide legal quality."""
    root = root.resolve(strict=True)
    run_root = Path(context["run_root"]).resolve(strict=True)
    if not root.is_relative_to(run_root):
        raise ValueError("Research review output must remain inside the current run")
    for name in (
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
        "review_history",
    ):
        if not (root / name).resolve().is_relative_to(root):
            raise ValueError(f"Review output escapes the current run: {name}")
    bindings: list[dict[str, str]] = []

    def read_bytes(relative: str) -> bytes:
        path = (root / relative).resolve(strict=True)
        if not path.is_file() or not path.is_relative_to(root):
            raise ValueError(f"Research review source escapes output: {relative}")
        raw = path.read_bytes()
        bindings.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest()})
        return raw

    def read(relative: str, *, text: bool = True) -> str:
        raw = read_bytes(relative)
        return raw.decode("utf-8") if text else ""

    record = json.loads(read("research_review.json"))
    if not isinstance(record, dict):
        raise ValueError("Research record must be an object")
    if record.get("method") != "shared_agentic_legal_tax_research":
        raise ValueError("Research review requires the shared research record")
    items: list[dict[str, Any]] = []
    locale = str(context.get("language", "it")).lower().replace("_", "-").split("-")[0]
    preview_copy = PREVIEW_COPY.get(locale, PREVIEW_COPY["en"])

    def preview(text: str) -> dict[str, Any]:
        # Bound the display only; hash complete bytes and retain the original artifact.
        return {
            "text": text[:PREVIEW_CHARACTERS],
            "preview_is_excerpt": len(text) > PREVIEW_CHARACTERS,
            "character_count": len(text),
            "preview_notice": (
                preview_copy[0] if len(text) > PREVIEW_CHARACTERS else preview_copy[1]
            ),
        }

    def source_preview(relative: str, *, textual: bool) -> dict[str, Any]:
        # Preview decoding is mechanical; never guess an encoding or alter evidence.
        raw = read_bytes(relative)
        if textual:
            try:
                return preview(raw.decode("utf-8-sig"))
            except UnicodeDecodeError:
                return {
                    "path": relative,
                    "preview": ENCODING_LIMIT_COPY.get(
                        locale, ENCODING_LIMIT_COPY["en"]
                    ),
                    "preview_status": "unsupported_encoding",
                }
        return {
            "path": relative,
            "preview": "Binary source capture; inspect the original artifact.",
        }

    def item(
        identifier: str, kind: str, title: str, data: dict[str, Any], source: str
    ) -> None:
        items.append(
            {
                "id": identifier,
                "item_type": kind,
                "title": title,
                "source_path": source,
                "output_path": source,
                "allowed_actions": ACTIONS,
                "recommended_action": (
                    data.get("reviewer_action")
                    if data.get("reviewer_action") in ACTIONS
                    else None
                ),
                "status": "needs_review",
                "data": data,
                "evidence": [],
            }
        )

    for key, kind in (("issues", "research_issue"), ("cycles", "research_cycle")):
        entries = record.get(key)
        if not isinstance(entries, list):
            raise ValueError(f"Research {key} must be a list")
        identifiers: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                raise ValueError(f"Research {key} entry requires an ID")
            if not entry["id"] or entry["id"] in identifiers:
                raise ValueError(f"Research {key} IDs must be distinct and nonempty")
            identifiers.add(entry["id"])
            item(
                f"{key}-{entry['id']}",
                kind,
                str(entry.get("question") or entry.get("purpose") or entry["id"]),
                entry,
                "research_review.json",
            )
    completion = record.get("completion")
    if not isinstance(completion, dict):
        raise ValueError("Research completion assessment must be an object")
    item(
        "research-completion",
        "research_completion",
        "Research scope and limits",
        completion,
        "research_review.json",
    )
    for relative in (
        "research_record.md",
        "validated_document.md",
        "answer_contract.json",
        "claims_review.json",
        "position/validated_document.md",
        "position/answer_contract.json",
        "position/claims_review.json",
        "adversarial/validated_document.md",
        "adversarial/answer_contract.json",
        "adversarial/claims_review.json",
        "opinion_comparison.md",
        "adversarial_assessment.json",
        "opinion_delivery.json",
    ):
        if (root / relative).exists():
            text = read(relative)
            data = preview(text)
            if relative == "adversarial_assessment.json":
                assessment = json.loads(text)
                if not isinstance(assessment, dict):
                    raise ValueError("Opposing assessment must be an object")
                data.update(
                    {
                        key: assessment[key]
                        for key in (
                            "outcome",
                            "rationale",
                            "comparison",
                            "comparison_review",
                            "search_record",
                        )
                        if key in assessment
                    }
                )
            item(
                f"document-{relative}",
                "opinion_review",
                relative,
                data,
                relative,
            )
    sources = root / "research/sources"
    if sources.exists():
        for path in sorted(sources.rglob("*")):
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                item(
                    f"source-{relative}",
                    "source_capture",
                    relative,
                    source_preview(
                        relative,
                        textual=path.suffix.lower()
                        in {".txt", ".md", ".json", ".html"},
                    ),
                    relative,
                )
    # Bind every explicitly declared artifact too, including phase sources outside
    # research/sources. The role is copied from the binding, never inferred from law.
    binding = record.get("binding", {})
    declared = binding.get("artifacts", []) if isinstance(binding, dict) else []
    if not isinstance(declared, list):
        raise ValueError("Declared research artifacts must be a list")
    seen = {entry["path"] for entry in bindings}
    for artifact in declared:
        if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
            raise ValueError("Declared research artifact requires a path")
        relative = artifact["path"]
        if relative in seen:
            continue
        textual = Path(relative).suffix.lower() in {".md", ".txt", ".json", ".html"}
        source = artifact.get("role") == "source"
        if source:
            data = source_preview(relative, textual=textual)
        else:
            text = read(relative, text=textual)
            data = (
                preview(text)
                if textual
                else {
                    "path": relative,
                    "preview": "Binary artifact; inspect the original.",
                }
            )
        item(
            f"bound-{relative}",
            "source_capture" if source else "validation_artifact",
            relative,
            data,
            relative,
        )
        seen.add(relative)
    now = datetime.now(timezone.utc).isoformat()
    run_id = context["run_id"]
    language = context.get("language", "it")
    common = {
        "schema_version": "1.0",
        "plugin": "deep-research-validator",
        "workflow": "deep-research-validator",
        "run_id": run_id,
    }
    previous_payload_path = root / "review_payload.json"
    if previous_payload_path.exists():
        previous_payload = json.loads(previous_payload_path.read_text(encoding="utf-8"))
        if (
            previous_payload.get("run_id") == run_id
            and previous_payload.get("source_bindings") == bindings
            and previous_payload.get("items") == items
            and previous_payload.get("language") == language
        ):
            now = previous_payload.get("created_at", now)
    payload = {
        **common,
        "created_at": now,
        "language": language,
        "review_type": "legal_tax_pipeline_review",
        "items": items,
        "item_count": len(items),
        "source_bindings": bindings,
        "summary": {
            "declared_research_status": completion.get("status"),
            "issue_count": len(record["issues"]),
            "cycle_count": len(record["cycles"]),
        },
        "status": "ready_for_review",
    }
    # Mechanical identity checks protect decisions against a different evidence revision.
    digest = hashlib.sha256(
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
    ).hexdigest()
    intake = {
        **common,
        "created_at": now,
        "inferred_task": "legal_tax_research_review",
        "assumptions": {"declared_research_status": completion.get("status")},
        "unresolved_questions": [
            entry["question"]
            for entry in record["issues"]
            if entry.get("status") == "open" and isinstance(entry.get("question"), str)
        ],
        "dependency_check": {
            "status": "not_run_by_ui_projection",
            "note": "The invoking workflow performs its dependency check before helper execution.",
        },
        "language": language,
        "path_reference": "run_root_relative",
        "output_dir": root.relative_to(run_root).as_posix(),
        "input_paths": [
            (root / binding["path"]).relative_to(run_root).as_posix()
            for binding in bindings
        ],
        "data_posture": {
            "local_files_read": [binding["path"] for binding in bindings],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "notes": [
                "Review displays existing research artifacts. No legal judgment is inferred from record shape or reviewer acceptance."
            ],
        },
        "status": "ready_for_review",
    }
    decisions = {
        **common,
        "review_payload_path": "review_payload.json",
        "review_payload_sha256": digest,
        "decisions": [],
        "decision_count": 0,
        "status": "pending_review",
    }
    previous_path = root / "ui_decisions.json"
    unchanged = False
    if previous_path.exists():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        if previous.get("review_payload_sha256") == digest:
            decisions = previous
            unchanged = True
        else:
            previous_hash = hashlib.sha256(previous_path.read_bytes()).hexdigest()
            history = root / "review_history" / previous_hash
            if not history.resolve().is_relative_to(root):
                raise ValueError("Review history escapes the current run")
            history.mkdir(parents=True, exist_ok=True)
            for name in (
                "run_intake.json",
                "review_payload.json",
                "ui_decisions.json",
                "applied_decisions.json",
                "final_artifacts.json",
            ):
                if (root / name).is_file():
                    shutil.copy2(root / name, history / name)
            # A previous application belongs to the saved revision, not this new review.
            (root / "applied_decisions.json").unlink(missing_ok=True)
    final = {
        **common,
        "review_payload_sha256": digest,
        "outputs": [
            {
                "path": path.relative_to(root).as_posix(),
                "kind": path.suffix.lstrip("."),
                "status": "written",
            }
            for path in sorted(root.rglob("*"))
            if path.is_file()
            and not (
                path.parent == root
                and path.name
                in {
                    "run_intake.json",
                    "review_payload.json",
                    "ui_decisions.json",
                    "final_artifacts.json",
                }
            )
        ],
        "caveats": [
            "Review acceptance does not certify legal correctness. Reopened issues require actual investigation and refreshed substantive reviews."
        ],
        "next_actions": [
            "Save and apply reviewer decisions, consume follow-up requests, and verify research/opinion bindings before Archive completion."
        ],
        "status": "written_pending_review",
    }
    if unchanged:
        previous_final_path = root / "final_artifacts.json"
        if previous_final_path.exists():
            previous_final = json.loads(previous_final_path.read_text(encoding="utf-8"))
            if previous_final.get("review_payload_sha256") == digest:
                final.update(previous_final)
    for name, value in (
        ("run_intake.json", intake),
        ("review_payload.json", payload),
        ("ui_decisions.json", decisions),
        ("final_artifacts.json", final),
    ):
        if not (root / name).resolve().is_relative_to(root):
            raise ValueError(f"Review output escapes the current run: {name}")
        (root / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return {
        "review_payload_sha256": digest,
        "item_count": len(items),
        "declared_research_status": completion.get("status"),
    }
