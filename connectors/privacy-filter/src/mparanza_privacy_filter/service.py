"""Bound local file access and persist only filtered artifacts and safe counts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .contracts import FORMATS, LABELS, MODEL_REVISION, FilteredDocument, FilterError

__all__ = ["Settings", "FilterService", "run_worker"]

_WORKER_ERRORS = frozenset(
    (
        "unsupported_format",
        "file_too_large",
        "encrypted_pdf",
        "pdf_page_without_text_requires_review_or_ocr",
        "invalid_docx",
        "docx_expansion_too_large",
        "empty_document",
        "text_too_large",
        "tokenizer_roundtrip_mismatch",
        "invalid_model_spans",
        "outside_input_directory",
        "processing_failed",
    )
)


@dataclass(frozen=True)
class Settings:
    """User-selected directories and local compute settings."""

    input_root: Path
    output_root: Path
    model_root: Path
    device: str = "cpu"

    @property
    def checkpoint(self) -> Path:
        return self.model_root / "checkpoint" / "original"

    @property
    def tokenizer_cache(self) -> Path:
        return self.model_root / "tokenizer"

    def ready(self) -> bool:
        """Require the explicit preparation receipt, weights and tokenizer cache."""
        try:
            receipt = json.loads((self.model_root / "ready.json").read_text())
            if receipt["model_revision"] != MODEL_REVISION:
                return False
        except (OSError, ValueError, KeyError, TypeError):
            return False
        return (
            (self.checkpoint / "config.json").is_file()
            and (self.checkpoint / "model.safetensors").is_file()
            and self.tokenizer_cache.is_dir()
            and any(p.is_file() for p in self.tokenizer_cache.iterdir())
        )


def _validated_document(payload: dict[str, Any]) -> FilteredDocument:
    """Reject unexpected fields rather than forward an upstream JSON result."""
    if set(payload) != {"redacted_text", "detection_counts", "source_characters"}:
        raise FilterError("invalid_worker_response")
    text, counts, characters = (
        payload["redacted_text"],
        payload["detection_counts"],
        payload["source_characters"],
    )
    if (
        not isinstance(text, str)
        or not isinstance(counts, dict)
        or not set(counts).issubset(LABELS)
        or any(type(value) is not int or value < 0 for value in counts.values())
        or type(characters) is not int
        or characters < 0
    ):
        raise FilterError("invalid_worker_response")
    return FilteredDocument(text, counts, characters)


def run_worker(path: Path, settings: Settings) -> FilteredDocument:
    """Run inference with an explicit timeout; suppress every raw diagnostic."""
    request = {
        "path": str(path),
        "input_root": str(settings.input_root),
        "checkpoint": str(settings.checkpoint),
        "tokenizer_cache": str(settings.tokenizer_cache),
        "device": settings.device,
    }
    try:
        result = subprocess.run(  # nosec B603
            [sys.executable, "-I", "-m", "mparanza_privacy_filter.worker"],
            input=json.dumps(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            raise FilterError("processing_failed")
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise FilterError("invalid_worker_response")
        if "error" in payload:
            code = payload["error"]
            raise FilterError(
                code
                if isinstance(code, str) and code in _WORKER_ERRORS
                else "processing_failed"
            )
        return _validated_document(payload)
    except subprocess.TimeoutExpired:
        raise FilterError("processing_timeout") from None
    except (OSError, json.JSONDecodeError):
        raise FilterError("processing_failed") from None


class FilterService:
    """Four operations; original documents are never returned or overwritten."""

    def __init__(
        self,
        settings: Settings,
        backend: Callable[[Path, Settings], FilteredDocument] = run_worker,
    ) -> None:
        self.settings = Settings(
            settings.input_root.expanduser().resolve(strict=True),
            settings.output_root.expanduser().resolve(),
            settings.model_root.expanduser().resolve(),
            settings.device,
        )
        if not self.settings.input_root.is_dir():
            raise FilterError("invalid_input_directory")
        if settings.device not in ("cpu", "cuda"):
            raise FilterError("unsupported_device")
        self.settings.output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.backend = backend
        self.lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        """Report readiness without scanning documents or downloading anything."""
        return {
            "version": __version__,
            "model_ready": self.settings.ready(),
            "model_revision": MODEL_REVISION,
            "device": self.settings.device,
            "formats": list(FORMATS),
            "max_batch_files": 5,
            "max_file_bytes": 25 * 1024 * 1024,
            "max_text_characters": 500_000,
        }

    def filter_file(self, path: str) -> dict[str, Any]:
        """Filter one explicit path inside the configured input directory."""
        if not self.settings.ready():
            raise FilterError("model_not_prepared")
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.settings.input_root / candidate
        try:
            candidate = candidate.resolve(strict=True)
            if not candidate.is_relative_to(self.settings.input_root):
                raise FilterError("outside_input_directory")
            if not candidate.is_file():
                raise FilterError("not_a_file")
            if candidate.suffix.lower() not in FORMATS:
                raise FilterError("unsupported_format")
            with self.lock:
                document = _validated_document(
                    asdict(self.backend(candidate, self.settings))
                )
            return self._save(document)
        except OSError:
            raise FilterError("file_access_failed") from None

    def filter_batch(self, paths: list[str]) -> dict[str, Any]:
        """Filter up to five explicit files, reporting failures by input index."""
        if not 1 <= len(paths) <= 5:
            raise FilterError("batch_requires_one_to_five_files")
        results = []
        for index, path in enumerate(paths):
            try:
                results.append({"index": index, "ok": True, **self.filter_file(path)})
            except FilterError as exc:
                results.append({"index": index, "ok": False, "error": str(exc)})
        return {"results": results}

    def _save(self, document: FilteredDocument) -> dict[str, Any]:
        artifact_id = uuid.uuid4().hex
        folder = self.settings.output_root / artifact_id
        folder.mkdir(mode=0o700)
        data = document.redacted_text.encode("utf-8")
        receipt = {
            "artifact_id": artifact_id,
            "source_characters": document.source_characters,
            "redacted_characters": len(document.redacted_text),
            "detection_counts": document.detection_counts,
            "sha256": hashlib.sha256(data).hexdigest(),
            "model_revision": MODEL_REVISION,
        }
        for name, content in (
            ("redacted.txt", data),
            ("receipt.json", json.dumps(receipt, ensure_ascii=False).encode("utf-8")),
        ):
            target = folder / name
            with target.open("xb") as handle:
                target.chmod(0o600)
                handle.write(content)
        return {**receipt, "output_path": str(folder / "redacted.txt")}

    def read_result(
        self, artifact_id: str, offset: int = 0, limit: int = 8000
    ) -> dict[str, Any]:
        """Read a bounded portion of a persisted filtered artifact after restart."""
        try:
            if uuid.UUID(artifact_id).hex != artifact_id:
                raise ValueError
        except ValueError:
            raise FilterError("invalid_artifact_id") from None
        if offset < 0 or not 1 <= limit <= 16000:
            raise FilterError("invalid_read_range")
        folder = self.settings.output_root / artifact_id
        try:
            text_path, receipt_path = folder / "redacted.txt", folder / "receipt.json"
            if (
                folder.is_symlink()
                or text_path.is_symlink()
                or receipt_path.is_symlink()
            ):
                raise FilterError("invalid_artifact")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            data = text_path.read_bytes()
            if hashlib.sha256(data).hexdigest() != receipt["sha256"]:
                raise FilterError("artifact_integrity_failed")
            text = data.decode("utf-8")
            end = min(offset + limit, len(text))
            return {
                "artifact_id": artifact_id,
                "redacted_text": text[offset:end],
                "total_characters": len(text),
                "next_offset": end if end < len(text) else None,
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, FilterError):
                raise
            raise FilterError("artifact_unavailable") from None
