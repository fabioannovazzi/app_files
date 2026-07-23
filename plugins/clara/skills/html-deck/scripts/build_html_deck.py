#!/usr/bin/env python3
"""Compile, validate, content-address, and package a Clara HTML stage deck."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from content_ledger import embedded_ledger_markup, validate_content_ledger
from evidence_bindings import (
    SOURCE_BOUND_PLAN_SCHEMA_VERSION,
    assert_no_unbound_quantitative_content,
    canonical_json_bytes,
    embedded_evidence_ledger_markup,
    resolve_source_bound_documents,
)
from evidence_bindings import sha256_bytes as evidence_sha256_bytes
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
LEGACY_QUANTITATIVE_TEXT_RE = re.compile(r"\d")
UNRESOLVED_TEMPLATE_TOKEN_RE = re.compile(r"\{\{[A-Z][A-Z0-9_]*\}\}")


@dataclass(frozen=True)
class PreparedWork:
    """Build inputs after source-bound recompilation or legacy classification."""

    ledger: dict[str, Any]
    evidence_ledger: dict[str, Any] | None
    evidence_status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--runtime", type=Path, default=default_runtime_path())
    parser.add_argument("--allow-template-examples", action="store_true")
    parser.add_argument(
        "--allow-unverified-quantitative-content",
        action="store_true",
        help=(
            "Explicit legacy/illustrative escape hatch. The build remains marked "
            "not_verified and is unsuitable for source-backed reporting."
        ),
    )
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


def _load_composer() -> Any:
    path = Path(__file__).with_name("compose_html_deck.py")
    spec = importlib.util.spec_from_file_location(
        "clara_html_deck_build_composer",
        path,
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load Clara deck composer: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _pretty_json(payload: dict[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _visible_text(markup: str) -> str:
    without_comments = re.sub(r"<!--.*?-->", " ", markup, flags=re.DOTALL)
    without_tags = re.sub(r"<[^>]*>", " ", without_comments)
    return html.unescape(without_tags)


def _assert_source_bound_visible_metadata_has_no_quantitative_content(
    *,
    metadata: dict[str, str],
    shell_markup: str,
    slides: str,
) -> None:
    """Block untraceable digits in metadata that the publication renders visibly.

    This is mechanically verifiable: ``deck.json`` has no evidence-binding
    contract, while the shell and slide templates identify exactly which
    metadata tokens can become visible publication text.
    """

    visible_template = _visible_text(f"{shell_markup}\n{slides}")
    found = [
        f"deck.json.{field}"
        for token, field in TOKENS.items()
        if f"{{{{{token}}}}}" in visible_template
        and LEGACY_QUANTITATIVE_TEXT_RE.search(metadata[field])
    ]
    if found:
        raise ValueError(
            "source-bound deck metadata cannot contain visible quantitative "
            "content because deck.json has no evidence-binding route; unbound "
            f"values at {', '.join(found)}"
        )


def _css_identifier(value: str) -> str | None:
    """Decode a narrow CSS property identifier, including escaped characters."""

    compact = "".join(value.split())
    decoded: list[str] = []
    index = 0
    while index < len(compact):
        character = compact[index]
        if character == "\\":
            index += 1
            if index >= len(compact):
                return None
            hex_start = index
            while (
                index < len(compact)
                and index - hex_start < 6
                and compact[index] in "0123456789abcdefABCDEF"
            ):
                index += 1
            if index > hex_start:
                codepoint = int(compact[hex_start:index], 16)
                if codepoint == 0 or codepoint > 0x10FFFF:
                    return None
                decoded.append(chr(codepoint))
                continue
            if compact[index] in "\r\n\f":
                return None
            decoded.append(compact[index])
            index += 1
            continue
        if not (character.isalnum() or character in "_-"):
            return None
        decoded.append(character)
        index += 1
    return "".join(decoded)


def _mask_css_comments_and_strings(value: str) -> str:
    """Preserve CSS structure while hiding comments and quoted values."""

    masked = list(value)
    index = 0
    while index < len(value):
        if value.startswith("/*", index):
            end = value.find("*/", index + 2)
            end = len(value) if end < 0 else end + 2
            for offset in range(index, end):
                masked[offset] = ""
            index = end
            continue
        quote = value[index]
        if quote not in {'"', "'"}:
            index += 1
            continue
        masked[index] = " "
        index += 1
        while index < len(value):
            character = value[index]
            if character not in "\r\n":
                masked[index] = " "
            if character == "\\" and index + 1 < len(value):
                index += 1
                if value[index] not in "\r\n":
                    masked[index] = " "
            elif character == quote:
                index += 1
                break
            index += 1
    return "".join(masked)


def _decode_css_escapes(value: str) -> str:
    """Decode CSS identifier escapes for conservative property/function checks."""

    decoded: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "\\":
            decoded.append(value[index])
            index += 1
            continue
        index += 1
        if index >= len(value):
            break
        hex_start = index
        while (
            index < len(value)
            and index - hex_start < 6
            and value[index] in "0123456789abcdefABCDEF"
        ):
            index += 1
        if index > hex_start:
            codepoint = int(value[hex_start:index], 16)
            decoded.append(chr(codepoint) if 0 < codepoint <= 0x10FFFF else "\ufffd")
            if index < len(value) and value[index].isspace():
                index += 1
            continue
        if value[index] not in "\r\n\f":
            decoded.append(value[index])
        index += 1
    return "".join(decoded)


def _css_calls_url_function(value: str) -> bool:
    """Return whether authored CSS can introduce an unbound image/resource."""

    normalized = _decode_css_escapes(_mask_css_comments_and_strings(value))
    return bool(
        re.search(
            r"(?<![A-Za-z0-9_-])url\s*\(",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _css_declares_generated_content(value: str) -> bool:
    """Return whether CSS declares the generated-text ``content`` property."""

    masked = _mask_css_comments_and_strings(value)
    delimiter_index = -1
    for index, character in enumerate(masked):
        if character in "{};":
            delimiter_index = index
            continue
        if character != ":":
            continue
        candidate = _css_identifier(masked[delimiter_index + 1 : index].strip())
        if candidate is not None and candidate.casefold() == "content":
            return True
    return False


def _assert_source_bound_custom_css_has_no_generated_content(
    custom_css: str,
    *,
    generated_css_end: str,
) -> None:
    """Reject authored CSS text generation that bypasses evidence bindings."""

    authored_css = (
        custom_css.split(generated_css_end, 1)[1]
        if generated_css_end in custom_css
        else custom_css
    )
    if _css_declares_generated_content(authored_css):
        raise ValueError(
            "source-bound custom.css cannot declare the CSS content property "
            "because generated visible text bypasses evidence bindings"
        )
    if _css_calls_url_function(authored_css):
        raise ValueError(
            "source-bound custom.css cannot call url() because an authored "
            "image or resource can contain unbound quantitative content"
        )


def _assert_legacy_deck_has_no_quantitative_content(
    *,
    plan: dict[str, Any],
    ledger: dict[str, Any],
    slides: str,
) -> None:
    try:
        assert_no_unbound_quantitative_content(plan, ledger)
    except ValueError as exc:
        raise ValueError(
            "legacy deck plans cannot publish quantitative content. Migrate to "
            f"{SOURCE_BOUND_PLAN_SCHEMA_VERSION}: {exc}"
        ) from exc
    visible = _visible_text(slides)
    if LEGACY_QUANTITATIVE_TEXT_RE.search(visible):
        raise ValueError(
            "legacy slides.html contains visible quantitative content. Migrate "
            f"the deck to {SOURCE_BOUND_PLAN_SCHEMA_VERSION} so every value is "
            "evidence-bound."
        )


def _contains_template_examples(value: Any) -> bool:
    if isinstance(value, str):
        return "REPLACE THIS" in value
    if isinstance(value, dict):
        return any(_contains_template_examples(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_template_examples(item) for item in value)
    return False


def _require_exact_text(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"source-bound deck is missing {label}: {path.name}")
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        raise ValueError(
            f"source-bound {label} drifted from deterministic recompilation: "
            f"{path.name}"
        )


def prepare_work(
    work_dir: Path,
    *,
    allow_template_examples: bool = False,
    allow_unverified_quantitative_content: bool = False,
) -> PreparedWork:
    """Re-resolve verified work or classify a non-quantitative legacy deck."""

    plan_path = work_dir / "deck-plan.json"
    ledger_path = work_dir / "content-ledger.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or not isinstance(ledger, dict):
        raise ValueError("deck-plan.json and content-ledger.json must be objects")
    slides_path = work_dir / "slides.html"
    css_path = work_dir / "custom.css"
    slides = slides_path.read_text(encoding="utf-8")
    custom_css = css_path.read_text(encoding="utf-8")

    if plan.get("schema_version") != SOURCE_BOUND_PLAN_SCHEMA_VERSION:
        unresolved_template = _contains_template_examples(plan)
        if not allow_unverified_quantitative_content and (
            allow_template_examples or not unresolved_template
        ):
            _assert_legacy_deck_has_no_quantitative_content(
                plan=plan,
                ledger=ledger,
                slides=slides,
            )
        return PreparedWork(
            ledger=ledger,
            evidence_ledger=None,
            evidence_status="not_verified",
        )

    metadata = read_metadata(work_dir / "deck.json")
    engine_dir = Path(__file__).resolve().parents[1] / "assets" / "deck-engine"
    shell = (engine_dir / "shell.html").read_text(encoding="utf-8")
    _assert_source_bound_visible_metadata_has_no_quantitative_content(
        metadata=metadata,
        shell_markup=shell,
        slides=slides,
    )
    composer = _load_composer()
    _assert_source_bound_custom_css_has_no_generated_content(
        custom_css,
        generated_css_end=composer.GENERATED_CSS_END,
    )
    resolution = resolve_source_bound_documents(
        plan=plan,
        ledger=ledger,
        base_dir=work_dir,
    )
    composition = composer.compose_deck(
        resolution.resolved_plan,
        registry_path=composer.default_registry_path(),
        existing_custom_css=custom_css,
    )
    _require_exact_text(slides_path, composition.slides_html, "slides")
    _require_exact_text(css_path, composition.custom_css, "custom CSS")
    _require_exact_text(
        work_dir / "resolved-deck-plan.json",
        _pretty_json(resolution.resolved_plan),
        "resolved deck plan",
    )
    _require_exact_text(
        work_dir / "resolved-content-ledger.json",
        _pretty_json(resolution.resolved_ledger),
        "resolved content ledger",
    )
    _require_exact_text(
        work_dir / "evidence-ledger.json",
        _pretty_json(resolution.evidence_ledger),
        "evidence ledger",
    )
    return PreparedWork(
        ledger=resolution.resolved_ledger,
        evidence_ledger=resolution.evidence_ledger,
        evidence_status="verified",
    )


def render_source(
    work_dir: Path,
    runtime_path: Path,
    *,
    ledger_payload: dict[str, Any] | None = None,
    evidence_ledger: dict[str, Any] | None = None,
) -> str:
    metadata = read_metadata(work_dir / "deck.json")
    slides = (work_dir / "slides.html").read_text(encoding="utf-8")
    custom_css = (work_dir / "custom.css").read_text(encoding="utf-8")
    if ledger_payload is None:
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
    document = document.replace(
        "{{EVIDENCE_LEDGER}}",
        embedded_evidence_ledger_markup(evidence_ledger),
    )
    if UNRESOLVED_TEMPLATE_TOKEN_RE.search(document):
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
        prepared = prepare_work(
            work_dir,
            allow_template_examples=args.allow_template_examples,
            allow_unverified_quantitative_content=(
                args.allow_unverified_quantitative_content
            ),
        )
        document = render_source(
            work_dir,
            runtime_path,
            ledger_payload=prepared.ledger,
            evidence_ledger=prepared.evidence_ledger,
        )
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
        report["evidence"] = {
            "status": prepared.evidence_status,
            "ledger_sha256": (
                evidence_sha256_bytes(canonical_json_bytes(prepared.evidence_ledger))
                if prepared.evidence_ledger is not None
                else None
            ),
        }
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
