"""Local opaque engine sessions; schema and isolation rules are mechanical contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from .contracts import FilteredDocument, FilterError

__all__ = ["SessionStore", "run_session_worker"]


def run_session_worker(request: dict[str, Any]) -> dict[str, Any]:
    """Suppress upstream diagnostics and return only the fixed worker contract."""
    try:
        result = subprocess.run(  # nosec B603
            [sys.executable, "-I", "-m", "mparanza_privacy_filter.session_worker"],
            input=json.dumps(request),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            raise FilterError("session_processing_failed")
        body = json.loads(result.stdout)
        if not isinstance(body, dict) or "error" in body:
            raise FilterError("session_processing_failed")
        return body
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise FilterError("session_processing_failed") from None


class SessionStore:
    """Persist anonymizer state outside artifacts and never return it through MCP."""

    def __init__(self, settings: Any, backend: Any = run_session_worker) -> None:
        self.settings = settings
        self.root: Path = settings.model_root / "sessions"
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise FilterError("invalid_session_directory")
        self.backend = backend

    def _folder(self, session_id: str) -> Path:
        try:
            if uuid.UUID(session_id).hex != session_id:
                raise ValueError
        except ValueError:
            raise FilterError("invalid_session_id") from None
        folder = self.root / session_id
        if folder.is_symlink() or not folder.is_dir():
            raise FilterError("session_unavailable")
        return folder

    def _inventory(self, folder: Path) -> dict[str, str]:
        result = {}
        for path in folder.rglob("*"):
            if path.is_symlink():
                raise FilterError("invalid_session_state")
            if path.is_file() and path.name != "receipt.json":
                result[path.relative_to(folder).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        return result

    def _write(self, folder: Path, receipt: dict[str, Any]) -> None:
        receipt["state_sha256"] = self._inventory(folder)
        for path in folder.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)
        target = folder / "receipt.json"
        target.write_text(json.dumps(receipt), encoding="utf-8")
        target.chmod(0o600)

    def _load(self, folder: Path) -> dict[str, Any]:
        try:
            if (folder / "receipt.json").is_symlink():
                raise FilterError("invalid_session_state")
            body = json.loads((folder / "receipt.json").read_text())
            if body["engine"] != self.settings.engine:
                raise FilterError("session_engine_mismatch")
            if body["state_sha256"] != self._inventory(folder):
                raise FilterError("session_integrity_failed")
            if body.get("failed"):
                raise FilterError("session_requires_recovery")
            return dict(body)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, FilterError):
                raise
            raise FilterError("session_unavailable") from None

    def _request(self, operation: str, folder: Path, **extra: Any) -> dict[str, Any]:
        return {
            "operation": operation,
            "engine": self.settings.engine,
            "folder": str(folder),
            "model_root": str(self.settings.model_root),
            **extra,
        }

    def create(self, state_path: Path | None = None) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        folder = self.root / session_id
        folder.mkdir(mode=0o700)
        receipt = {
            "session_id": session_id,
            "engine": self.settings.engine,
            "documents": 0,
        }
        try:
            body = self.backend(
                self._request(
                    "create", folder, state_path=str(state_path) if state_path else None
                )
            )
            if body != {"created": True}:
                raise FilterError("invalid_session_response")
            self._write(folder, receipt)
        except (OSError, FilterError):
            receipt["failed"] = True
            self._write(folder, receipt)
            raise FilterError("session_creation_failed") from None
        return {
            "session_id": session_id,
            "engine": self.settings.engine,
            "documents": 0,
        }

    def open(self, session_id: str) -> dict[str, Any]:
        folder = self._folder(session_id)
        receipt = self._load(folder)
        return {key: receipt[key] for key in ("session_id", "engine", "documents")}

    def process(self, session_id: str, path: Path) -> FilteredDocument:
        folder = self._folder(session_id)
        lock = folder.with_name(folder.name + ".lock")
        try:
            lock.mkdir(mode=0o700)
        except FileExistsError:
            raise FilterError("session_busy") from None
        try:
            receipt = self._load(folder)
            try:
                body = self.backend(self._request("filter", folder, path=str(path)))
                if set(body) != {
                    "redacted_text",
                    "detection_counts",
                    "source_characters",
                }:
                    raise FilterError("invalid_session_response")
                text, counts, chars = (
                    body["redacted_text"],
                    body["detection_counts"],
                    body["source_characters"],
                )
                if (
                    not isinstance(text, str)
                    or not isinstance(counts, dict)
                    or set(counts) != {"entities"}
                    or type(counts["entities"]) is not int
                    or counts["entities"] < 0
                    or type(chars) is not int
                    or chars < 0
                ):
                    raise FilterError("invalid_session_response")
                receipt["documents"] += 1
                self._write(folder, receipt)
                return FilteredDocument(text, counts, chars)
            except (OSError, FilterError):
                # Never reuse uncertain state after a partial engine write.
                receipt["failed"] = True
                self._write(folder, receipt)
                raise FilterError("session_processing_failed") from None
        finally:
            lock.rmdir()

    def restore(self, session_id: str, path: Path, target: Path) -> None:
        folder = self._folder(session_id)
        lock = folder.with_name(folder.name + ".lock")
        try:
            lock.mkdir(mode=0o700)
        except FileExistsError:
            raise FilterError("session_busy") from None
        try:
            self._load(folder)
            body = self.backend(
                self._request("restore", folder, path=str(path), target=str(target))
            )
            if (
                body != {"restored": True}
                or not target.is_file()
                or target.is_symlink()
            ):
                raise FilterError("invalid_session_response")
            target.chmod(0o600)
        finally:
            lock.rmdir()
