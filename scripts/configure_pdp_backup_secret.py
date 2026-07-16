from __future__ import annotations

import argparse
import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add a server-local PDP_BACKUP_DATABASE_URL without printing secrets.",
    )
    parser.add_argument(
        "--secrets-path",
        type=Path,
        default=Path(".secrets/secrets.toml"),
        help="Path to the secrets file to update.",
    )
    parser.add_argument(
        "--source-key",
        default="PDP_DATABASE_URL",
        help="Existing key to copy from.",
    )
    parser.add_argument(
        "--target-key",
        default="PDP_BACKUP_DATABASE_URL",
        help="Backup URL key to write.",
    )
    parser.add_argument(
        "--from-port",
        default="5433",
        help="Port in the source URL/DSN to replace.",
    )
    parser.add_argument(
        "--to-port",
        default="5432",
        help="Server-local Postgres port for backups.",
    )
    return parser.parse_args()


def _extract_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _quote_value(value: str) -> str:
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


def _find_key_value(lines: list[str], key: str) -> str | None:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        found_key, raw_value = stripped.split("=", 1)
        if found_key.strip() == key:
            return _extract_value(raw_value)
    return None


def _has_key(lines: list[str], key: str) -> bool:
    return _find_key_value(lines, key) is not None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    secrets_path = args.secrets_path
    if not secrets_path.exists():
        LOGGER.error("Secrets file is missing: %s", secrets_path)
        return 1

    lines = secrets_path.read_text(encoding="utf-8").splitlines()
    if _has_key(lines, str(args.target_key)):
        LOGGER.info("%s already exists.", args.target_key)
        return 0

    source_value = _find_key_value(lines, str(args.source_key))
    if not source_value:
        LOGGER.error("%s is missing.", args.source_key)
        return 1

    backup_value = source_value.replace(
        f"port={args.from_port}",
        f"port={args.to_port}",
    ).replace(
        f":{args.from_port}/",
        f":{args.to_port}/",
    )
    lines.append(f"{args.target_key} = {_quote_value(backup_value)}")
    secrets_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    LOGGER.info("%s added.", args.target_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
