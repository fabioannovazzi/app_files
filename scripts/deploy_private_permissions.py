"""Validate and securely publish ignored permission maps to a server."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import secrets
import shlex

# This CLI intentionally invokes validated ssh/scp commands.
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

__all__ = [
    "PermissionConfigError",
    "PermissionFileSummary",
    "deploy_permission_files",
    "discover_permission_files",
    "main",
    "validate_permission_file",
]

LOGGER = logging.getLogger(__name__)

_DEFAULT_CONFIG_DIR = Path("config")
_DEFAULT_REMOTE_DIR = PurePosixPath("/var/lib/mparanza/config")
_DEPLOY_HOST_ENV = "APP_FILES_DEPLOY_HOST"
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]+$")
_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+_permissions\.json$")


class PermissionConfigError(ValueError):
    """Raised when a permission map does not satisfy the public contract."""


@dataclass(frozen=True, slots=True)
class PermissionFileSummary:
    """Non-sensitive validation metadata for one permission map."""

    path: Path
    group_count: int
    entry_count: int


def _validate_permission_entry(entry: object, *, group_index: int) -> None:
    """Validate one allow-list entry without including its value in errors."""

    if isinstance(entry, str):
        if entry.strip():
            return
        raise PermissionConfigError(
            f"Permission entry in group {group_index} must not be empty."
        )

    if not isinstance(entry, dict):
        raise PermissionConfigError(
            f"Permission entry in group {group_index} must be a string or object."
        )

    email = entry.get("email")
    if not isinstance(email, str) or not email.strip():
        raise PermissionConfigError(
            f"Permission object in group {group_index} requires a non-empty email."
        )
    for expiry_key in ("expires_at", "expires"):
        expiry = entry.get(expiry_key)
        if expiry is not None and not isinstance(expiry, str):
            raise PermissionConfigError(
                f"Permission object in group {group_index} has an invalid expiry."
            )


def validate_permission_file(path: Path) -> PermissionFileSummary:
    """Validate a permission JSON file and return non-sensitive counts."""

    if not _FILENAME_PATTERN.fullmatch(path.name):
        raise PermissionConfigError(
            "Permission filename must use only letters, numbers, underscores, or "
            "hyphens and end with '_permissions.json'."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PermissionConfigError(f"Permission file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PermissionConfigError(
            f"Permission file is not valid JSON: {path}"
        ) from exc

    if not isinstance(raw, dict):
        raise PermissionConfigError("Permission file must contain a JSON object.")

    entry_count = 0
    for group_index, (group_name, entries) in enumerate(raw.items(), start=1):
        if not isinstance(group_name, str) or not group_name.strip():
            raise PermissionConfigError(
                f"Permission group {group_index} requires a non-empty name."
            )
        if not isinstance(entries, list):
            raise PermissionConfigError(
                f"Permission group {group_index} must contain a list."
            )
        for entry in entries:
            _validate_permission_entry(entry, group_index=group_index)
            entry_count += 1

    return PermissionFileSummary(
        path=path,
        group_count=len(raw),
        entry_count=entry_count,
    )


def discover_permission_files(config_dir: Path) -> list[Path]:
    """Return the ignored runtime permission maps in stable filename order."""

    return sorted(config_dir.glob("*_permissions.json"), key=lambda path: path.name)


def _validate_host(host: str) -> str:
    candidate = host.strip()
    if not candidate or not _HOST_PATTERN.fullmatch(candidate):
        raise PermissionConfigError("SSH host contains unsupported characters.")
    return candidate


def _validate_remote_dir(remote_dir: PurePosixPath) -> PurePosixPath:
    if not remote_dir.is_absolute():
        raise PermissionConfigError("Remote configuration directory must be absolute.")
    if any(character.isspace() for character in str(remote_dir)):
        raise PermissionConfigError(
            "Remote configuration directory must not contain whitespace."
        )
    return remote_dir


def _run(command: Sequence[str], *, check: bool = True) -> None:
    # Commands are argument arrays; no local shell is involved.
    subprocess.run(list(command), check=check)  # nosec B603


def deploy_permission_files(
    files: Sequence[Path],
    *,
    host: str,
    remote_dir: PurePosixPath,
) -> list[PermissionFileSummary]:
    """Validate locally, upload to temporary paths, then publish atomically."""

    if not files:
        raise PermissionConfigError("No private permission files were found.")

    summaries = [validate_permission_file(path) for path in files]
    validated_host = _validate_host(host)
    validated_remote_dir = _validate_remote_dir(remote_dir)
    token = secrets.token_hex(8)
    staged: list[tuple[PurePosixPath, PurePosixPath]] = []

    prepare_command = shlex.join(
        ["install", "-d", "-m", "700", str(validated_remote_dir)]
    )
    _run(["ssh", validated_host, prepare_command])

    try:
        for summary in summaries:
            final_path = validated_remote_dir / summary.path.name
            temporary_path = validated_remote_dir / f".{summary.path.name}.{token}.tmp"
            staged.append((temporary_path, final_path))
            _run(
                [
                    "scp",
                    str(summary.path),
                    f"{validated_host}:{temporary_path}",
                ]
            )

        publish_commands: list[str] = []
        for temporary_path, final_path in staged:
            publish_commands.append(shlex.join(["chmod", "600", str(temporary_path)]))
            publish_commands.append(
                shlex.join(["mv", "-f", str(temporary_path), str(final_path)])
            )
        _run(["ssh", validated_host, " && ".join(publish_commands)])
    except subprocess.CalledProcessError:
        cleanup_paths = [str(temporary_path) for temporary_path, _final in staged]
        if cleanup_paths:
            cleanup_command = shlex.join(["rm", "-f", *cleanup_paths])
            _run(["ssh", validated_host, cleanup_command], check=False)
        raise

    return summaries


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate ignored permission maps and securely publish them without Git."
        )
    )
    parser.add_argument(
        "--host",
        default=os.environ.get(_DEPLOY_HOST_ENV),
        help=f"SSH host or alias (defaults to ${_DEPLOY_HOST_ENV}).",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=_DEFAULT_CONFIG_DIR,
        help="Directory containing local *_permissions.json files.",
    )
    parser.add_argument(
        "--remote-dir",
        type=PurePosixPath,
        default=_DEFAULT_REMOTE_DIR,
        help="Private configuration directory on the server.",
    )
    parser.add_argument(
        "--file",
        action="append",
        dest="files",
        type=Path,
        help="Specific permission file to deploy; repeat to deploy several.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate files without contacting the server.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the private permission deployment command."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    files = args.files or discover_permission_files(args.config_dir)
    summaries = [validate_permission_file(path) for path in files]

    if args.dry_run:
        LOGGER.info(
            "Validated %s private permission files containing %s groups.",
            len(summaries),
            sum(summary.group_count for summary in summaries),
        )
        return 0

    if not args.host:
        parser.error(f"--host or ${_DEPLOY_HOST_ENV} is required.")

    deploy_permission_files(files, host=args.host, remote_dir=args.remote_dir)
    LOGGER.info(
        "Published %s private permission files to %s:%s.",
        len(summaries),
        args.host,
        args.remote_dir,
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
