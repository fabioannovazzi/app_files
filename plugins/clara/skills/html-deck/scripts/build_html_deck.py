#!/usr/bin/env python3
"""Compile, validate, content-address, and package a Clara HTML stage deck."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from content_ledger import embedded_ledger_markup, validate_content_ledger
from validate_html_deck import default_runtime_path, validate_html_text

SCHEMA_VERSION = "clara.html_deck_build.v1"
WORK_SCHEMA_VERSION = "clara.html_deck_work.v1"
TOKENS = {
    "DECK_TITLE": "title",
    "DECK_SUBTITLE": "subtitle",
    "DECK_AUTHOR": "author",
    "DECK_EYEBROW": "eyebrow",
    "DECK_LANGUAGE": "language",
    "DECK_DESCRIPTION": "description",
    "DECK_ROBOTS": "robots",
    "DECK_THEME_COLOR": "theme_color",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--runtime", type=Path, default=default_runtime_path())
    parser.add_argument("--allow-template-examples", action="store_true")
    parser.add_argument("--max-bytes", type=int, default=1_500_000)
    return parser.parse_args()


def load_runtime(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("clara_html_deck_build_runtime", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load Clara runtime: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_metadata(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != WORK_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported deck work schema: {payload.get('schema_version')!r}"
        )
    required = set(TOKENS.values())
    missing = sorted(field for field in required if field not in payload)
    if missing:
        raise ValueError(f"deck.json is missing fields: {missing}")
    metadata = {field: str(payload.get(field, "")).strip() for field in required}
    if not metadata["title"]:
        raise ValueError("deck.json title cannot be empty")
    return metadata


def replace_metadata(text: str, metadata: dict[str, str]) -> str:
    rendered = text
    for token, field in TOKENS.items():
        rendered = rendered.replace(
            "{{" + token + "}}", html.escape(metadata[field], quote=True)
        )
    return rendered


def render_source(work_dir: Path, runtime_path: Path) -> str:
    metadata = read_metadata(work_dir / "deck.json")
    slides = (work_dir / "slides.html").read_text(encoding="utf-8")
    custom_css = (work_dir / "custom.css").read_text(encoding="utf-8")
    ledger_payload = json.loads(
        (work_dir / "content-ledger.json").read_text(encoding="utf-8")
    )
    ledger = validate_content_ledger(ledger_payload)
    if "</style" in custom_css.lower():
        raise ValueError("custom.css may not contain a closing style tag")
    if "<script" in slides.lower() or "</script" in slides.lower():
        raise ValueError("slides.html may not contain script elements")

    engine_dir = Path(__file__).resolve().parents[1] / "assets" / "deck-engine"
    shell = (engine_dir / "shell.html").read_text(encoding="utf-8")
    deck_css = (engine_dir / "deck.css").read_text(encoding="utf-8")
    deck_js = (engine_dir / "deck.js").read_text(encoding="utf-8")
    rendered_slides = replace_metadata(slides, metadata)
    document = replace_metadata(shell, metadata)
    document = document.replace("{{DECK_CSS}}", deck_css.rstrip())
    document = document.replace("{{CUSTOM_CSS}}", custom_css.rstrip())
    document = document.replace("{{DECK_SLIDES}}", rendered_slides.rstrip())
    document = document.replace("{{DECK_JS}}", deck_js.rstrip())
    document = document.replace("{{CONTENT_LEDGER}}", embedded_ledger_markup(ledger))
    if "{{" in document or "}}" in document:
        raise ValueError("Unresolved template token remains after rendering")

    runtime = load_runtime(runtime_path)
    return runtime.apply_html_deck_runtime(document, profile="stage")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def canonical_zip(path: Path, publication_id: str, html_bytes: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    os.close(descriptor)
    try:
        directory = ZipInfo(f"{publication_id}/", date_time=(1980, 1, 1, 0, 0, 0))
        directory.compress_type = ZIP_STORED
        directory.external_attr = (0o40755 << 16) | 0x10
        file_info = ZipInfo(
            f"{publication_id}/index.html", date_time=(1980, 1, 1, 0, 0, 0)
        )
        file_info.compress_type = ZIP_STORED
        file_info.external_attr = 0o100644 << 16
        with ZipFile(temporary_name, "w", compression=ZIP_STORED) as archive:
            archive.writestr(directory, b"")
            archive.writestr(file_info, html_bytes)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    args = parse_args()
    try:
        work_dir = args.work_dir.expanduser().resolve()
        output_root = args.output_root.expanduser().resolve()
        runtime_path = args.runtime.expanduser().resolve()
        document = render_source(work_dir, runtime_path)
        html_bytes = document.encode("utf-8")
        publication_id = sha256_bytes(html_bytes)
        report = validate_html_text(
            document,
            label=str(work_dir),
            runtime_path=runtime_path,
            publication_id=publication_id,
            allow_template_examples=args.allow_template_examples,
            max_bytes=args.max_bytes,
        )
        if report["result"] != "pass":
            rendered_failure = (
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
            if args.report:
                atomic_write(
                    args.report.expanduser().resolve(), rendered_failure.encode("utf-8")
                )
            print(rendered_failure, end="")
            return 1

        target_dir = output_root / publication_id
        target_path = target_dir / "index.html"
        if target_path.exists():
            existing = target_path.read_bytes()
            if existing != html_bytes:
                raise RuntimeError(f"Content-address collision at {target_path}")
        else:
            atomic_write(target_path, html_bytes)

        package_path = args.package.expanduser().resolve() if args.package else None
        if package_path:
            canonical_zip(package_path, publication_id, html_bytes)

        report["schema_version"] = SCHEMA_VERSION
        report["output"] = {
            "publication_id": publication_id,
            "index_path": str(target_path),
            "bytes": len(html_bytes),
            "sha256": publication_id,
            "package_path": str(package_path) if package_path else None,
            "package_sha256": (
                sha256_bytes(package_path.read_bytes()) if package_path else None
            ),
        }
        rendered_report = (
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        if args.report:
            atomic_write(
                args.report.expanduser().resolve(), rendered_report.encode("utf-8")
            )
        print(rendered_report, end="")
        return 0
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
