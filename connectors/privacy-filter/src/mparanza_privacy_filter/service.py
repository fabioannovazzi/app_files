"""Bound local file access and persist only filtered artifacts and safe counts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .contracts import FORMATS, LABELS, FilteredDocument, FilterError
from .engines import Engine, engine_for
from .rizzo_api import health as rizzo_health
from .rizzo_api import validate_port
from .sessions import SessionStore

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
        "rizzo_unavailable",
        "invalid_rizzo_response",
        "invalid_rizzo_port",
    )
)


@dataclass(frozen=True)
class Settings:
    """User-selected directories and local compute settings."""

    input_root: Path
    output_root: Path
    model_root: Path
    device: str = "cpu"
    engine: str = "openai"
    rizzo_port: int = 5005

    @property
    def spec(self) -> Engine:
        return engine_for(self.engine)

    @property
    def checkpoint(self) -> Path:
        return self.model_root.joinpath(*self.spec.checkpoint_parts)

    @property
    def tokenizer_cache(self) -> Path:
        return self.model_root / "tokenizer"

    def ready(self) -> bool:
        """Require the explicit preparation receipt, weights and tokenizer cache."""
        if self.engine == "lethe":
            try:
                from importlib.metadata import version

                return version("lethe") == "1.3.1"
            except ImportError:
                return False
        if self.engine == "pii-shield":
            from .shield_ready import ready as shield_ready

            return shield_ready(self.model_root)
        if self.engine == "rizzo":
            try:
                return bool(rizzo_health(self.rizzo_port)["model_ready"])
            except FilterError:
                return False
        try:
            receipt = json.loads((self.model_root / "ready.json").read_text())
            if receipt["model_revision"] != self.spec.revision:
                return False
        except (OSError, ValueError, KeyError, TypeError):
            return False
        if not all(
            (self.checkpoint / name).is_file() for name in self.spec.required_files
        ):
            return False
        return self.engine == "gliner2" or (
            self.tokenizer_cache.is_dir()
            and any(p.is_file() for p in self.tokenizer_cache.iterdir())
        )


def _validated_document(
    payload: dict[str, Any], labels: frozenset[str] = LABELS
) -> FilteredDocument:
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
        or not set(counts).issubset(labels)
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
        "rizzo_port": settings.rizzo_port,
    }
    try:
        result = subprocess.run(  # nosec B603
            [sys.executable, "-I", "-m", settings.spec.worker],
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
        return _validated_document(payload, settings.spec.labels)
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
        engine_for(settings.engine)
        validate_port(settings.rizzo_port)
        self.settings = replace(
            settings,
            input_root=settings.input_root.expanduser().resolve(strict=True),
            output_root=settings.output_root.expanduser().resolve(),
            model_root=settings.model_root.expanduser().resolve(),
        )
        if not self.settings.input_root.is_dir():
            raise FilterError("invalid_input_directory")
        if settings.device not in ("cpu", "cuda"):
            raise FilterError("unsupported_device")
        self.settings.output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.backend = backend
        self.lock = threading.Lock()
        self.sessions = (
            SessionStore(self.settings) if self.settings.spec.reversible else None
        )

    def status(self) -> dict[str, Any]:
        """Report readiness without scanning documents or downloading anything."""
        result = {
            "version": __version__,
            "model_ready": (
                False if self.settings.engine == "rizzo" else self.settings.ready()
            ),
            "engine": self.settings.engine,
            "capabilities": {
                "redaction": True,
                "reversible": self.settings.spec.reversible,
                "cross_document": self.settings.spec.cross_document,
                "mapping_authority": "anonymizer",
            },
            "model_revision": self.settings.spec.revision,
            "device": self.settings.device,
            "formats": list(FORMATS),
            "max_batch_files": 5,
            "max_file_bytes": 25 * 1024 * 1024,
            "max_text_characters": 500_000,
        }
        if self.settings.engine == "rizzo":
            result["device"] = "managed-by-local-rizzo-app"
            try:
                result.update(rizzo_health(self.settings.rizzo_port))
            except FilterError as exc:
                result.update(model_ready=False, error=str(exc))
        return result

    def filter_file(self, path: str, session_id: str | None = None) -> dict[str, Any]:
        """Filter one explicit path inside the configured input directory."""
        if not self.settings.ready():
            raise FilterError(
                "rizzo_unavailable"
                if self.settings.engine == "rizzo"
                else "model_not_prepared"
            )
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
                if self.sessions is not None:
                    if session_id is None:
                        raise FilterError("session_required")
                    document = self.sessions.process(session_id, candidate)
                else:
                    if session_id is not None:
                        raise FilterError("sessions_not_supported")
                    document = _validated_document(
                        asdict(self.backend(candidate, self.settings)),
                        self.settings.spec.labels,
                    )
            return self._save(document, session_id)
        except OSError:
            raise FilterError("file_access_failed") from None

    def filter_batch(
        self, paths: list[str], session_id: str | None = None
    ) -> dict[str, Any]:
        """Filter up to five explicit files, reporting failures by input index."""
        if not 1 <= len(paths) <= 5:
            raise FilterError("batch_requires_one_to_five_files")
        results = []
        for index, path in enumerate(paths):
            try:
                results.append(
                    {"index": index, "ok": True, **self.filter_file(path, session_id)}
                )
            except FilterError as exc:
                results.append({"index": index, "ok": False, "error": str(exc)})
        return {"results": results}

    def _save(
        self, document: FilteredDocument, session_id: str | None = None
    ) -> dict[str, Any]:
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
            "engine": self.settings.engine,
            "model_revision": self.settings.spec.revision,
        }
        if session_id is not None:
            receipt["session_id"] = session_id
        for name, content in (
            ("redacted.txt", data),
            ("receipt.json", json.dumps(receipt, ensure_ascii=False).encode("utf-8")),
        ):
            target = folder / name
            with target.open("xb") as handle:
                target.chmod(0o600)
                handle.write(content)
        return {**receipt, "output_path": str(folder / "redacted.txt")}

    def create_session(self, state_path: str | None = None) -> dict[str, Any]:
        """Create a private engine-owned job; Lethe requires a local approved review."""
        if self.sessions is None:
            raise FilterError("sessions_not_supported")
        if not self.settings.ready():
            raise FilterError("model_not_prepared")
        source = None
        if state_path is not None:
            source = (self.settings.input_root / state_path).resolve(strict=True)
            if (
                not source.is_relative_to(self.settings.input_root)
                or not source.is_file()
            ):
                raise FilterError("outside_input_directory")
        return self.sessions.create(source)

    def open_session(self, session_id: str) -> dict[str, Any]:
        """Reopen the exact job after restart; no latest-job substitution."""
        if self.sessions is None:
            raise FilterError("sessions_not_supported")
        return self.sessions.open(session_id)

    def restore_file(self, session_id: str, path: str) -> dict[str, Any]:
        """Save restored identities locally and return only a path and checksum."""
        if self.sessions is None:
            raise FilterError("sessions_not_supported")
        source = (self.settings.input_root / path).resolve(strict=True)
        if not source.is_relative_to(self.settings.input_root) or not source.is_file():
            raise FilterError("outside_input_directory")
        folder = self.settings.output_root / uuid.uuid4().hex
        folder.mkdir(mode=0o700)
        target = folder / "restored.txt"
        self.sessions.restore(session_id, source, target)
        # No artifact ID: read_result cannot read restored files into model context.
        return {
            "session_id": session_id,
            "output_path": str(target),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }

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
