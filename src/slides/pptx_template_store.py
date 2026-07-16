from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from src.slides.pptx_template_manifest import (
    DECK_PPTX_TEMPLATE_FILENAME,
    DECK_PPTX_TEMPLATE_MANIFEST_FILENAME,
    build_pptx_template_manifest,
    write_deck_pptx_template_manifest,
)

__all__ = [
    "PptxTemplateRecord",
    "apply_saved_pptx_template_to_deck",
    "clear_deck_pptx_template",
    "list_saved_pptx_templates",
    "load_default_pptx_template_id",
    "save_uploaded_pptx_template",
    "set_default_pptx_template",
]

_TEMPLATE_LIBRARY_DIRNAME = "_pptx_templates"
_DEFAULT_TEMPLATE_FILENAME = "default_template_id.txt"
_METADATA_FILENAME = "metadata.json"
_VALID_TEMPLATE_SUFFIXES = {".pptx", ".potx"}
_TEMPLATE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml"
)
_PRESENTATION_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
)


@dataclass(frozen=True, slots=True)
class PptxTemplateRecord:
    """Persisted PPTX template metadata for a single owner."""

    template_id: str
    name: str
    original_filename: str
    uploaded_at: str
    is_default: bool


def list_saved_pptx_templates(
    storage_root: Path,
    owner_email: str | None,
) -> list[PptxTemplateRecord]:
    """List saved PPTX templates for ``owner_email`` under ``storage_root``."""

    owner_dir = _owner_template_dir(storage_root, owner_email)
    if not owner_dir.exists():
        return []
    default_template_id = load_default_pptx_template_id(storage_root, owner_email)
    records: list[PptxTemplateRecord] = []
    for template_dir in sorted(
        (entry for entry in owner_dir.iterdir() if entry.is_dir()),
        key=lambda entry: entry.name.lower(),
    ):
        metadata_path = template_dir / _METADATA_FILENAME
        if not metadata_path.exists():
            continue
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        template_id = str(payload.get("templateId") or template_dir.name).strip()
        records.append(
            PptxTemplateRecord(
                template_id=template_id,
                name=str(payload.get("name") or template_id).strip(),
                original_filename=str(payload.get("originalFilename") or "").strip(),
                uploaded_at=str(payload.get("uploadedAt") or "").strip(),
                is_default=template_id == default_template_id,
            )
        )
    return records


def load_default_pptx_template_id(
    storage_root: Path,
    owner_email: str | None,
) -> str | None:
    """Return the default saved template id for ``owner_email`` when configured."""

    path = _owner_template_dir(storage_root, owner_email) / _DEFAULT_TEMPLATE_FILENAME
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def set_default_pptx_template(
    storage_root: Path,
    owner_email: str | None,
    template_id: str,
) -> None:
    """Persist ``template_id`` as the default template for ``owner_email``."""

    template_dir = _template_dir(storage_root, owner_email, template_id)
    if not template_dir.exists():
        raise FileNotFoundError(f"PPTX template '{template_id}' does not exist.")
    default_path = (
        _owner_template_dir(storage_root, owner_email) / _DEFAULT_TEMPLATE_FILENAME
    )
    default_path.parent.mkdir(parents=True, exist_ok=True)
    default_path.write_text(str(template_id).strip(), encoding="utf-8")


def save_uploaded_pptx_template(
    storage_root: Path,
    owner_email: str | None,
    *,
    filename: str,
    file_bytes: bytes,
    set_default: bool = True,
) -> PptxTemplateRecord:
    """Persist an uploaded PPTX/POTX template and return its metadata record."""

    suffix = Path(filename or "").suffix.lower()
    if suffix not in _VALID_TEMPLATE_SUFFIXES:
        raise ValueError("Upload a .pptx or .potx template.")
    normalized_bytes = _normalize_template_file_bytes(file_bytes, suffix=suffix)
    template_id = _generate_template_id(filename)
    template_dir = _template_dir(storage_root, owner_email, template_id)
    template_dir.mkdir(parents=True, exist_ok=False)
    template_path = template_dir / DECK_PPTX_TEMPLATE_FILENAME
    template_path.write_bytes(normalized_bytes)
    manifest = build_pptx_template_manifest(template_path)
    write_deck_pptx_template_manifest(template_dir, manifest)
    uploaded_at = datetime.now(UTC).isoformat()
    display_name = _template_display_name(filename)
    metadata = {
        "templateId": template_id,
        "name": display_name,
        "originalFilename": str(filename or "").strip(),
        "uploadedAt": uploaded_at,
    }
    (template_dir / _METADATA_FILENAME).write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if set_default:
        set_default_pptx_template(storage_root, owner_email, template_id)
    return PptxTemplateRecord(
        template_id=template_id,
        name=display_name,
        original_filename=str(filename or "").strip(),
        uploaded_at=uploaded_at,
        is_default=bool(set_default),
    )


def apply_saved_pptx_template_to_deck(
    storage_root: Path,
    owner_email: str | None,
    *,
    deck_path: Path,
    template_id: str | None,
    use_uniform_template: bool = False,
) -> str | None:
    """Materialize the selected/default saved template into ``deck_path``."""

    if use_uniform_template:
        clear_deck_pptx_template(deck_path)
        return None
    resolved_template_id = (
        str(template_id).strip()
        if str(template_id or "").strip()
        else load_default_pptx_template_id(storage_root, owner_email)
    )
    if not resolved_template_id:
        clear_deck_pptx_template(deck_path)
        return None
    template_dir = _template_dir(storage_root, owner_email, resolved_template_id)
    template_path = template_dir / DECK_PPTX_TEMPLATE_FILENAME
    manifest_path = template_dir / DECK_PPTX_TEMPLATE_MANIFEST_FILENAME
    if not template_path.exists() or not manifest_path.exists():
        raise FileNotFoundError(
            f"PPTX template '{resolved_template_id}' is unavailable."
        )
    deck_path.mkdir(parents=True, exist_ok=True)
    clear_deck_pptx_template(deck_path)
    (deck_path / DECK_PPTX_TEMPLATE_FILENAME).write_bytes(template_path.read_bytes())
    (deck_path / DECK_PPTX_TEMPLATE_MANIFEST_FILENAME).write_text(
        manifest_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return resolved_template_id


def clear_deck_pptx_template(deck_path: Path) -> None:
    """Remove any deck-local custom PPTX template and manifest."""

    (deck_path / DECK_PPTX_TEMPLATE_FILENAME).unlink(missing_ok=True)
    (deck_path / DECK_PPTX_TEMPLATE_MANIFEST_FILENAME).unlink(missing_ok=True)


def _template_library_root(storage_root: Path) -> Path:
    return Path(storage_root) / _TEMPLATE_LIBRARY_DIRNAME


def _owner_template_dir(storage_root: Path, owner_email: str | None) -> Path:
    return _template_library_root(storage_root) / _owner_key(owner_email)


def _template_dir(
    storage_root: Path, owner_email: str | None, template_id: str
) -> Path:
    return _owner_template_dir(storage_root, owner_email) / str(template_id).strip()


def _owner_key(owner_email: str | None) -> str:
    normalized = str(owner_email or "").strip().lower()
    if not normalized:
        return "anonymous"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"user-{digest}"


def _generate_template_id(filename: str) -> str:
    stem = _template_display_name(filename)
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    slug = slug or "template"
    return f"{slug}-{uuid.uuid4().hex[:8]}"


def _template_display_name(filename: str) -> str:
    stem = Path(filename or "").stem.strip()
    return stem or "Template"


def _normalize_template_file_bytes(file_bytes: bytes, *, suffix: str) -> bytes:
    if suffix != ".potx":
        return file_bytes
    source = io.BytesIO(file_bytes)
    output = io.BytesIO()
    with ZipFile(source) as src_zip, ZipFile(output, "w", ZIP_DEFLATED) as out_zip:
        for info in src_zip.infolist():
            data = src_zip.read(info.filename)
            if info.filename == "[Content_Types].xml":
                data = data.replace(
                    _TEMPLATE_CONTENT_TYPE.encode("utf-8"),
                    _PRESENTATION_CONTENT_TYPE.encode("utf-8"),
                )
            out_zip.writestr(info, data)
    return output.getvalue()
