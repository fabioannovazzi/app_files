"""Mechanical safety and serialization helpers for grant-application runs."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import sys
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

__all__ = [
    "PLUGIN_NAME",
    "case_lock",
    "canonical_json_sha256",
    "iso_now",
    "load_json_object",
    "load_running_context",
    "relative_run_path",
    "require_run_artifact",
    "safe_identifier",
    "sha256_file",
    "validate_iso_date",
    "write_private_json",
    "write_private_text",
]

PLUGIN_NAME = "bandi-agevolazioni"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MAX_JSON_BYTES = 10_000_000
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")

for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from vera_assurance import (  # noqa: E402
    load_client_engagement_context_file,
    validate_client_workflow_run,
)


def iso_now() -> str:
    """Return a stable UTC timestamp."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_identifier(value: object, *, field: str) -> str:
    """Validate a stable identifier using a mechanically auditable alphabet."""

    text = str(value or "").strip()
    if not SAFE_IDENTIFIER_RE.fullmatch(text):
        raise ValueError(
            f"{field} must be 1-80 characters using letters, digits, '.', '_' or '-'"
        )
    return text


def validate_iso_date(value: object, *, field: str) -> str:
    """Validate one ISO calendar date without interpreting its legal effect."""

    text = str(value or "").strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one regular file."""

    if path.is_symlink() or not path.is_file():
        raise ValueError(f"source must be a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(*payloads: object) -> str:
    """Hash JSON values canonically for review and stale-input detection."""

    raw = json.dumps(
        payloads,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    """Read a bounded JSON object from a regular file."""

    if path.is_symlink() or not path.is_file():
        raise ValueError(f"JSON input must be a regular file: {path}")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON input must contain an object: {path}")
    return payload


def _mark_private(path: Path) -> Path:
    path.chmod(0o600)
    return path


def write_private_text(path: Path, text: str) -> Path:
    """Atomically write owner-only text below an existing private output root."""

    if path.parent.is_symlink():
        raise PermissionError(f"output parent cannot be a symbolic link: {path.parent}")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    _mark_private(temporary)
    temporary.replace(path)
    return _mark_private(path)


def write_private_json(path: Path, payload: dict[str, Any]) -> Path:
    """Atomically write stable owner-only JSON."""

    return write_private_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def load_running_context(
    client_engagement: Path,
    *,
    output_dir: Path,
    input_paths: Sequence[Path] = (),
    additional_output_paths: Sequence[Path] = (),
) -> dict[str, Any]:
    """Load one exact running Studio Archive workflow context."""

    context = load_client_engagement_context_file(
        client_engagement,
        expected_workflow_id=PLUGIN_NAME,
        input_paths=input_paths,
        output_dir=output_dir,
    )
    for path in additional_output_paths:
        validate_client_workflow_run(
            context,
            expected_workflow_id=PLUGIN_NAME,
            output_dir=path,
        )
    safe_output = output_dir.expanduser().resolve()
    if safe_output.is_symlink():
        raise PermissionError("run output directory cannot be a symbolic link")
    safe_output.mkdir(parents=True, mode=0o700, exist_ok=True)
    safe_output.chmod(0o700)
    return context


def relative_run_path(path: Path, context: dict[str, Any]) -> str:
    """Return a portable path below the exact Studio Archive run root."""

    resolved = path.resolve()
    run_root = Path(str(context["run_root"])).resolve()
    try:
        return resolved.relative_to(run_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"path is outside the selected workflow run: {path}") from exc


def require_run_artifact(path: Path, *, run_id: str) -> dict[str, Any]:
    """Require a JSON artifact to belong to this plugin and run."""

    payload = load_json_object(path)
    if payload.get("plugin") != PLUGIN_NAME or payload.get("run_id") != run_id:
        raise ValueError(f"artifact belongs to another plugin run: {path}")
    return payload


@contextmanager
def case_lock(output_dir: Path) -> Iterator[None]:
    """Enforce one mechanical writer for a short case mutation."""

    lock_path = output_dir / ".bandi-agevolazioni.lock"
    try:
        with lock_path.open("x", encoding="utf-8") as handle:
            handle.write(iso_now())
        lock_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except FileExistsError as exc:
        raise RuntimeError(
            "another bandi-agevolazioni mutation is in progress"
        ) from exc
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)
