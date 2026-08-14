from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

__all__ = [
    "CLIENT_REFERENCE",
    "MAX_HANDOFF_ITEMS",
    "MAX_HANDOFF_PAGE_BYTES",
    "ModelHandoffResult",
    "write_model_handoff",
]

SCHEMA_VERSION = "1.0"
CLIENT_REFERENCE = "CLIENT-001"
MAX_HANDOFF_ITEMS = 2_500
MAX_HANDOFF_PAGE_BYTES = 1_500_000
MAX_EXCERPT_CHARS = 600
ROOT_FILE_NAME = "model_handoff.json"
PAGES_DIRECTORY_NAME = "model_handoff_pages"
KIND_PRIORITY = {
    "file_metadata": 10,
    "evidence_excerpt": 20,
    "fiscal_field": 30,
    "missing_request_candidate": 40,
    "email_request": 50,
    "duplicate_group": 60,
    "xml_anomaly": 70,
    "xml_duplicate_group": 80,
}


@dataclass(frozen=True)
class ModelHandoffResult:
    """Paths and counts for one purpose-shaped model handoff."""

    root_path: Path
    page_paths: tuple[Path, ...]
    item_count: int


def _json_bytes(payload: Any, *, pretty: bool) -> bytes:
    if pretty:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return f"{text}\n".encode("utf-8")


def _write_bytes(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o600)
    return path


def _read_json_object(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _bounded_text(value: Any, limit: int = MAX_EXCERPT_CHARS) -> str:
    return _clean_text(value)[:limit]


def _opaque_reference(namespace: str, value: str) -> str:
    digest = hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()
    return f"{namespace}-{digest[:20]}"


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _review_items(review_payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = review_payload.get("items")
    if not isinstance(items, list):
        raise ValueError("review_payload.items must be an array")
    if review_payload.get("item_count") != len(items):
        raise ValueError(
            "review_payload.item_count must equal review_payload.items length"
        )
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("review_payload.items must contain only objects")
    return items


def _document_lookup(items: Sequence[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for item in items:
        if item.get("item_type") != "document_inventory":
            continue
        source_path = _clean_text(item.get("source_path"))
        item_id = _clean_text(item.get("id"))
        if source_path and item_id:
            lookup[source_path] = item_id
    return lookup


def _document_reference(source_path: Any, lookup: dict[str, str]) -> str:
    path = _clean_text(source_path)
    return lookup.get(path) or _opaque_reference("document", path or "unmapped")


def _file_metadata_items(
    review_items: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in review_items:
        if item.get("item_type") != "document_inventory":
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        item_id = _clean_text(item.get("id"))
        records.append(
            {
                "id": f"file-metadata:{item_id}",
                "kind": "file_metadata",
                "document_ref": item_id,
                "relative_path": _clean_text(data.get("relative_path")),
                "file_name": _clean_text(data.get("file_name")),
                "extension": _clean_text(data.get("extension")),
                "size_bytes": data.get("size_bytes"),
                "modified_iso": _clean_text(data.get("modified_iso")),
                "sha256": _clean_text(data.get("sha256")),
                "category": _clean_text(data.get("category")),
                "confidence": _clean_text(data.get("confidence")),
                "years": (
                    data.get("years") if isinstance(data.get("years"), list) else []
                ),
                "notes": _clean_text(data.get("notes")),
                "readable": data.get("readable"),
                "extraction_method": _clean_text(data.get("extraction_method")),
                "text_locator": _clean_text(data.get("text_path")),
                "structured_field_count": data.get("structured_field_count", 0),
            }
        )
    return records


def _evidence_excerpt_items(
    review_items: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in review_items:
        if item.get("item_type") != "document_inventory":
            continue
        item_id = _clean_text(item.get("id"))
        evidence_records = item.get("evidence")
        if not isinstance(evidence_records, list):
            continue
        for evidence_index, evidence in enumerate(evidence_records, start=1):
            if (
                not isinstance(evidence, dict)
                or evidence.get("kind") != "extracted_text"
            ):
                continue
            preview = _bounded_text(evidence.get("preview"))
            if not preview:
                continue
            records.append(
                {
                    "id": f"evidence-excerpt:{item_id}:{evidence_index}",
                    "kind": "evidence_excerpt",
                    "document_ref": item_id,
                    "text_locator": _clean_text(evidence.get("path")),
                    "text": preview,
                    "character_limit": MAX_EXCERPT_CHARS,
                    "selection_basis": "flagged_by_local_review_payload",
                }
            )
    return records


def _fiscal_field_items(
    review_items: Sequence[dict[str, Any]],
    document_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    retained_fields = (
        "document_kind",
        "section",
        "field_code",
        "label",
        "value",
        "normalized_value",
        "value_type",
        "confidence",
        "warnings",
    )
    for item in review_items:
        if item.get("item_type") != "extracted_fiscal_field":
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        citation_text = ""
        evidence_records = item.get("evidence")
        if isinstance(evidence_records, list):
            for evidence in evidence_records:
                if isinstance(evidence, dict) and evidence.get("kind") == "snippet":
                    citation_text = _bounded_text(evidence.get("text"))
                    break
        item_id = _clean_text(item.get("id"))
        source_ref = _document_reference(item.get("source_path"), document_lookup)
        record = {
            "id": f"fiscal-field:{item_id}",
            "kind": "fiscal_field",
            "source_document_ref": source_ref,
            "citation": {
                "source_document_ref": source_ref,
                "text": citation_text,
                "character_limit": MAX_EXCERPT_CHARS,
            },
        }
        for field in retained_fields:
            value = data.get(field)
            record[field] = _clean_text(value) if not isinstance(value, list) else value
        records.append(record)
    return records


def _missing_request_candidate_items(
    review_items: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in review_items:
        if item.get("item_type") != "missing_document_request":
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        item_id = _clean_text(item.get("id"))
        records.append(
            {
                "id": f"missing-request-candidate:{item_id}",
                "kind": "missing_request_candidate",
                "review_item_ref": item_id,
                "request_text": _clean_text(data.get("request_text")),
                "purpose": "professional_review",
                "email_drafting_eligible": False,
            }
        )
    return records


def _email_request_items(
    review_items: Sequence[dict[str, Any]],
    ui_decisions: dict[str, Any],
) -> list[dict[str, Any]]:
    item_by_id = {
        _clean_text(item.get("id")): item
        for item in review_items
        if item.get("item_type") == "missing_document_request"
    }
    decisions = ui_decisions.get("decisions")
    if not isinstance(decisions, list):
        return []
    records: list[dict[str, Any]] = []
    for decision_index, decision in enumerate(decisions, start=1):
        if not isinstance(decision, dict):
            continue
        item_id = _clean_text(decision.get("item_id"))
        item = item_by_id.get(item_id)
        if item is None:
            continue
        action = _clean_text(decision.get("action"))
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        reviewed_texts: list[str] = []
        if action == "accept":
            reviewed_texts = [_clean_text(data.get("request_text"))]
        elif action == "edit":
            reviewed_texts = [_clean_text(decision.get("edit_value"))]
        elif action == "request_more_documents":
            requested = decision.get("requested_documents")
            if isinstance(requested, list):
                reviewed_texts = [_clean_text(value) for value in requested]
            if not any(reviewed_texts):
                reviewed_texts = [_clean_text(data.get("request_text"))]
        for request_index, request_text in enumerate(reviewed_texts, start=1):
            if not request_text:
                continue
            records.append(
                {
                    "id": f"email-request:{decision_index}:{request_index}:{item_id}",
                    "kind": "email_request",
                    "review_item_ref": item_id,
                    "client_reference": CLIENT_REFERENCE,
                    "request_text": request_text,
                    "review_action": action,
                    "purpose": "client_email_drafting",
                }
            )
    return records


def _duplicate_group_items(
    review_items: Sequence[dict[str, Any]],
    document_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[str]] = {}
    for item in review_items:
        if item.get("item_type") != "duplicate_warning":
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        duplicate_type = _clean_text(data.get("duplicate_type"))
        group_key = _clean_text(data.get("group_key"))
        group = (duplicate_type, group_key)
        groups.setdefault(group, []).append(
            _document_reference(item.get("source_path"), document_lookup)
        )
    records: list[dict[str, Any]] = []
    for duplicate_type, group_key in sorted(
        groups, key=lambda value: (value[0].encode("utf-8"), value[1].encode("utf-8"))
    ):
        group_ref = _opaque_reference(
            "duplicate-group", f"{duplicate_type}:{group_key}"
        )
        member_refs = sorted(set(groups[(duplicate_type, group_key)]))
        records.append(
            {
                "id": group_ref,
                "kind": "duplicate_group",
                "group_ref": group_ref,
                "duplicate_type": duplicate_type,
                "member_document_refs": member_refs,
                "member_count": len(member_refs),
            }
        )
    return records


def _xml_anomaly_items(
    review_items: Sequence[dict[str, Any]],
    document_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in review_items:
        if item.get("item_type") != "formal_xml_anomaly":
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        anomalies = data.get("anomalies")
        if not isinstance(anomalies, list):
            anomalies = []
        item_id = _clean_text(item.get("id"))
        records.append(
            {
                "id": f"xml-anomaly:{item_id}",
                "kind": "xml_anomaly",
                "source_document_ref": _document_reference(
                    item.get("source_path"), document_lookup
                ),
                "malformed": bool(data.get("malformed")),
                "anomalies": [
                    _clean_text(value) for value in anomalies if _clean_text(value)
                ],
            }
        )
    return records


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_number} must contain a JSON object")
        records.append(value)
    return records


def _xml_duplicate_group_items(
    output_dir: Path,
    document_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    groups: dict[str, list[str]] = {}
    source_path = output_dir / "extracted" / "fatture_xml.jsonl"
    for record in _read_jsonl(source_path):
        duplicate_key = _clean_text(record.get("duplicate_key"))
        if bool(record.get("malformed")) or not duplicate_key.strip("|"):
            continue
        groups.setdefault(duplicate_key, []).append(
            _document_reference(record.get("relative_path"), document_lookup)
        )
    results: list[dict[str, Any]] = []
    for duplicate_key in sorted(groups, key=lambda value: value.encode("utf-8")):
        member_refs = sorted(set(groups[duplicate_key]))
        if len(member_refs) < 2:
            continue
        group_ref = _opaque_reference("xml-duplicate-group", duplicate_key)
        results.append(
            {
                "id": group_ref,
                "kind": "xml_duplicate_group",
                "group_ref": group_ref,
                "member_document_refs": member_refs,
                "member_count": len(member_refs),
            }
        )
    return results


def _build_items(
    output_dir: Path,
    review_payload: dict[str, Any],
    ui_decisions: dict[str, Any],
) -> list[dict[str, Any]]:
    review_items = _review_items(review_payload)
    document_lookup = _document_lookup(review_items)
    records = [
        *_file_metadata_items(review_items),
        *_evidence_excerpt_items(review_items),
        *_fiscal_field_items(review_items, document_lookup),
        *_missing_request_candidate_items(review_items),
        *_email_request_items(review_items, ui_decisions),
        *_duplicate_group_items(review_items, document_lookup),
        *_xml_anomaly_items(review_items, document_lookup),
        *_xml_duplicate_group_items(output_dir, document_lookup),
    ]
    return sorted(
        records,
        key=lambda item: (
            KIND_PRIORITY.get(str(item.get("kind")), 999),
            str(item.get("id", "")).encode("utf-8"),
        ),
    )


def _page_payload(
    run_id: str, page_number: int, items: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "page_number": page_number,
        "items": list(items),
    }


def _page_parts(run_id: str, page_number: int) -> tuple[bytes, bytes]:
    empty_page = _json_bytes(
        _page_payload(run_id, page_number, []),
        pretty=False,
    )
    prefix, suffix = empty_page.split(b"[]", maxsplit=1)
    return prefix + b"[", b"]" + suffix


def _paginate(run_id: str, items: Sequence[dict[str, Any]]) -> list[bytes]:
    pages: list[bytes] = []
    current: list[bytes] = []
    current_content_size = 0
    page_number = 1
    for item in items:
        item_bytes = _json_bytes(item, pretty=False).rstrip(b"\n")
        prefix, suffix = _page_parts(run_id, page_number)
        candidate_size = (
            len(prefix)
            + current_content_size
            + (1 if current else 0)
            + len(item_bytes)
            + len(suffix)
        )
        if (
            len(current) < MAX_HANDOFF_ITEMS
            and candidate_size <= MAX_HANDOFF_PAGE_BYTES
        ):
            current.append(item_bytes)
            current_content_size += (1 if current_content_size else 0) + len(item_bytes)
            continue
        if not current:
            raise ValueError(
                f"model handoff item {item.get('id')} cannot fit within "
                f"{MAX_HANDOFF_PAGE_BYTES} bytes"
            )
        pages.append(prefix + b",".join(current) + suffix)
        page_number += 1
        current = [item_bytes]
        current_content_size = len(item_bytes)
        next_prefix, next_suffix = _page_parts(run_id, page_number)
        if (
            len(next_prefix) + len(item_bytes) + len(next_suffix)
            > MAX_HANDOFF_PAGE_BYTES
        ):
            raise ValueError(
                f"model handoff item {item.get('id')} cannot fit within "
                f"{MAX_HANDOFF_PAGE_BYTES} bytes"
            )
    if current or not pages:
        prefix, suffix = _page_parts(run_id, page_number)
        pages.append(prefix + b",".join(current) + suffix)
    return pages


def _count_by_kind(items: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        kind = str(item.get("kind", "unknown"))
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items(), key=lambda value: value[0].encode("utf-8")))


def _clear_page_directory(page_dir: Path) -> None:
    page_dir.mkdir(parents=True, exist_ok=True)
    page_dir.chmod(0o700)
    for path in page_dir.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"unsafe model handoff page entry: {path}")
        path.unlink()


def _output_record(path: Path, output_dir: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": path.relative_to(output_dir).as_posix(),
        "kind": "json",
        "status": "written",
        "size_bytes": len(content),
        "sha256": _sha256_bytes(content),
    }


def write_model_handoff(output_dir: Path | str) -> ModelHandoffResult:
    """Write the bounded model-default artifact from exact local review state."""

    root = Path(output_dir).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    review_payload = _read_json_object(root / "review_payload.json")
    ui_decisions = _read_json_object(root / "ui_decisions.json", required=False)
    run_id = _clean_text(review_payload.get("run_id"))
    if not run_id:
        raise ValueError("review_payload.run_id is required")
    if ui_decisions and _clean_text(ui_decisions.get("run_id")) != run_id:
        raise ValueError("ui_decisions.run_id must match review_payload.run_id")

    items = _build_items(root, review_payload, ui_decisions)
    page_contents = _paginate(run_id, items)
    page_dir = root / PAGES_DIRECTORY_NAME
    _clear_page_directory(page_dir)
    page_paths: list[Path] = []
    page_manifest: list[dict[str, Any]] = []
    offset = 0
    for page_number, content in enumerate(page_contents, start=1):
        page_path = _write_bytes(page_dir / f"page-{page_number:04d}.json", content)
        page_payload = json.loads(content)
        page_items = page_payload["items"]
        page_paths.append(page_path)
        page_manifest.append(
            {
                "page_number": page_number,
                "path": page_path.relative_to(root).as_posix(),
                "item_offset": offset,
                "item_count": len(page_items),
                "size_bytes": len(content),
                "sha256": _sha256_bytes(content),
                "kinds": _count_by_kind(page_items),
            }
        )
        offset += len(page_items)

    counts = _count_by_kind(items)
    decision_status = _clean_text(ui_decisions.get("status")) or "pending_review"
    root_payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact": "client_file_preparation_model_handoff",
        "run_id": run_id,
        "created_at": review_payload.get("created_at"),
        "language": review_payload.get("language"),
        "jurisdiction": review_payload.get("jurisdiction"),
        "runtime_profiles": ["openai-codex", "anthropic-cowork"],
        "default_model_context": True,
        "client_reference": CLIENT_REFERENCE,
        "review_status": decision_status,
        "source_population": {
            "review_item_count": len(_review_items(review_payload)),
            "file_count": counts.get("file_metadata", 0),
            "mapped_fiscal_field_count": counts.get("fiscal_field", 0),
            "reviewed_email_request_count": counts.get("email_request", 0),
        },
        "content_policy": {
            "file_population": "one_metadata_item_per_inventory_file",
            "document_excerpts": "flagged_review_evidence_only_max_600_characters",
            "fiscal_fields": "all_mapped_fields_with_max_600_character_citation",
            "email_drafting": "reviewed_missing_requests_only_with_generic_client_reference",
            "xml_synthesis": "anomaly_and_opaque_duplicate_group_references_without_party_fields",
            "anonymization": "not_applied",
            "pseudonymization": "generic_client_reference_only_for_email_drafting",
            "exact_local_artifacts": "retained_outside_this_default_model_handoff",
        },
        "phase_access": {
            "file_preparation_review": [
                "file_metadata",
                "evidence_excerpt",
                "fiscal_field",
                "missing_request_candidate",
                "duplicate_group",
                "xml_anomaly",
                "xml_duplicate_group",
            ],
            "email_drafting": ["email_request"],
            "xml_synthesis": ["xml_anomaly", "xml_duplicate_group"],
        },
        "pagination": {
            "ordering": "kind_priority_then_utf8_id",
            "sampling": False,
            "max_items_per_page": MAX_HANDOFF_ITEMS,
            "max_bytes_per_page": MAX_HANDOFF_PAGE_BYTES,
            "item_count": len(items),
            "page_count": len(page_paths),
            "pages": page_manifest,
        },
        "item_counts_by_kind": counts,
    }
    root_path = _write_bytes(
        root / ROOT_FILE_NAME, _json_bytes(root_payload, pretty=True)
    )
    return ModelHandoffResult(
        root_path=root_path,
        page_paths=tuple(page_paths),
        item_count=len(items),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write the purpose-shaped Client File Preparation model handoff."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = write_model_handoff(args.output_dir)
    output_dir = args.output_dir.expanduser().resolve()
    outputs = [
        _output_record(result.root_path, output_dir),
        *(_output_record(path, output_dir) for path in result.page_paths),
    ]
    print(  # noqa: T201 - command output is the machine-readable MCP handoff.
        json.dumps(
            {
                "ok": True,
                "item_count": result.item_count,
                "page_count": len(result.page_paths),
                "outputs": outputs,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
