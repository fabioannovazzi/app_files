from __future__ import annotations

import argparse
import html
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

__all__ = [
    "GalleryReadinessViolation",
    "HtmlGalleryItem",
    "find_html_gallery_items",
    "find_artifact_readiness_violations",
    "find_title_contract_violations",
    "main",
    "validate_png_gallery_manifest",
]

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class HtmlGalleryItem:
    label: str
    source: str
    output: str
    artifact_type: str


@dataclass(frozen=True)
class GalleryReadinessViolation:
    label: str
    code: str
    detail: str


REQUIRED_ARTIFACT_SIDECARS = {
    "source",
    "context",
    "data",
    "manifest",
    "recipe",
}


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that the curated PNG examples gallery is backed by PNG "
            "source artifacts rather than HTML screenshot fallbacks."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("runs/png_examples/png-gallery/manifest.json"),
        help="Curated gallery manifest to validate.",
    )
    parser.add_argument(
        "--allow-html",
        action="store_true",
        help=(
            "Allow HTML-backed gallery cards. Use only for explicit debugging "
            "or known temporary browser-export failures."
        ),
    )
    parser.add_argument(
        "--require-artifact-ready",
        action="store_true",
        help=(
            "Require every gallery card to expose resolvable source/context/data/"
            "manifest/recipe sidecars and an artifact capability contract."
        ),
    )
    parser.add_argument(
        "--require-title-contract",
        action="store_true",
        help=(
            "Require every gallery card to expose at least three visible title "
            "rows: who/scope, what/measure/grain, and when/comparison/window."
        ),
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    return parser.parse_args(argv)


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("gallery manifest must be a JSON object")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("gallery manifest must contain an items list")
    return payload


def find_html_gallery_items(manifest: dict[str, Any]) -> list[HtmlGalleryItem]:
    """Return exact HTML-backed cards; this is a mechanical manifest invariant."""

    items = manifest.get("items")
    if not isinstance(items, list):
        raise ValueError("gallery manifest must contain an items list")

    html_items: list[HtmlGalleryItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        artifact_type = str(item.get("artifact_type") or "")
        if artifact_type != "html":
            continue
        html_items.append(
            HtmlGalleryItem(
                label=str(item.get("label") or ""),
                source=str(item.get("source") or ""),
                output=str(item.get("output") or ""),
                artifact_type=artifact_type,
            )
        )
    return html_items


def validate_png_gallery_manifest(
    manifest_path: Path,
    *,
    allow_html: bool = False,
) -> list[HtmlGalleryItem]:
    """Return HTML-backed cards that violate the curated gallery PNG-only rule."""

    manifest = _load_manifest(manifest_path)
    html_items = find_html_gallery_items(manifest)
    return [] if allow_html else html_items


def find_artifact_readiness_violations(
    manifest_path: Path,
) -> list[GalleryReadinessViolation]:
    """Return cards that do not expose the required source artifact metadata."""

    manifest = _load_manifest(manifest_path)
    gallery_dir = manifest_path.parent
    violations: list[GalleryReadinessViolation] = []
    for item in manifest["items"]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "")
        sidecars = item.get("sidecars")
        if not isinstance(sidecars, list):
            violations.append(
                GalleryReadinessViolation(label, "missing_sidecars", "no sidecars list")
            )
            sidecars = []
        sidecar_map: dict[str, str] = {}
        for sidecar in sidecars:
            if not isinstance(sidecar, dict):
                continue
            sidecar_label = sidecar.get("label")
            href = sidecar.get("href")
            if isinstance(sidecar_label, str) and isinstance(href, str):
                sidecar_map[sidecar_label] = href
        for required_label in sorted(REQUIRED_ARTIFACT_SIDECARS):
            href = sidecar_map.get(required_label)
            if not href:
                violations.append(
                    GalleryReadinessViolation(
                        label,
                        f"missing_{required_label}",
                        f"missing {required_label} sidecar",
                    )
                )
                continue
            if "://" not in href and not (gallery_dir / href).resolve().exists():
                violations.append(
                    GalleryReadinessViolation(
                        label,
                        f"broken_{required_label}",
                        href,
                    )
                )
        contract = item.get("artifact_contract")
        if not isinstance(contract, dict):
            violations.append(
                GalleryReadinessViolation(
                    label,
                    "missing_artifact_contract",
                    "missing artifact_contract object",
                )
            )
        else:
            for key in (
                "capability_id",
                "when_to_use",
                "required_parameters",
                "outputs",
            ):
                if contract.get(key) in (None, "", [], {}):
                    violations.append(
                        GalleryReadinessViolation(
                            label,
                            f"incomplete_artifact_contract_{key}",
                            f"missing artifact_contract.{key}",
                        )
                    )
        readiness = item.get("artifact_readiness")
        if isinstance(readiness, dict) and readiness.get("ready") is not True:
            issues = readiness.get("issues")
            violations.append(
                GalleryReadinessViolation(
                    label,
                    "artifact_readiness_not_ready",
                    ", ".join(str(issue) for issue in issues or []),
                )
            )
    return violations


def find_title_contract_violations(
    manifest_path: Path,
) -> list[GalleryReadinessViolation]:
    """Return cards that do not expose the three-row reporting title contract."""

    manifest = _load_manifest(manifest_path)
    gallery_dir = manifest_path.parent
    violations: list[GalleryReadinessViolation] = []
    for item in manifest["items"]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "")
        title_lines = _title_lines_for_item(item, gallery_dir)
        if len(title_lines) < 3:
            violations.append(
                GalleryReadinessViolation(
                    label,
                    "missing_title_contract",
                    f"found {len(title_lines)} title row(s)",
                )
            )
    return violations


def _title_lines_for_item(item: dict[str, Any], gallery_dir: Path) -> list[str]:
    manifest_lines = _title_lines_from_context_payload(item.get("title_context"))
    if len(manifest_lines) >= 3:
        return manifest_lines
    context_lines = _title_lines_from_context_sidecars(item, gallery_dir)
    if len(context_lines) >= 3:
        return context_lines
    source_path = _local_path_from_href(str(item.get("source") or ""), gallery_dir)
    if source_path is not None and source_path.exists():
        source_lines = _title_lines_from_source(source_path)
        if len(source_lines) >= 3:
            return source_lines
    return context_lines


def _title_lines_from_context_sidecars(
    item: dict[str, Any],
    gallery_dir: Path,
) -> list[str]:
    sidecars = item.get("sidecars")
    if not isinstance(sidecars, list):
        return []
    for sidecar in sidecars:
        if not isinstance(sidecar, dict) or sidecar.get("label") != "context":
            continue
        href = sidecar.get("href")
        if not isinstance(href, str):
            continue
        path = _local_path_from_href(href, gallery_dir)
        if path is None or not path.exists() or path.suffix.lower() != ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        lines = _title_lines_from_context_payload(payload)
        if len(lines) >= 3:
            return lines
    return []


def _title_lines_from_context_payload(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    lines = _clean_title_lines(payload.get("lines"))
    if len(lines) >= 3:
        return lines
    lines = _clean_title_lines(
        [payload.get("who"), payload.get("what"), payload.get("when")]
    )
    if len(lines) >= 3:
        return lines
    lines = _clean_title_lines(payload.get("chart_title_lines"))
    if len(lines) >= 3:
        return lines
    contract = payload.get("title_contract")
    if isinstance(contract, dict):
        lines = _clean_title_lines(
            [contract.get("who"), contract.get("what"), contract.get("when")]
        )
        if len(lines) >= 3:
            return lines
    lines = _clean_title_lines(payload.get("chart_title"))
    if len(lines) >= 3:
        return lines
    exports = payload.get("exports")
    if isinstance(exports, list):
        for export in exports:
            lines = _title_lines_from_context_payload(export)
            if len(lines) >= 3:
                return lines
    return []


def _title_lines_from_source(path: Path) -> list[str]:
    if path.suffix.lower() not in {".html", ".htm"}:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    plotly_title = _extract_plotly_title_text(text)
    if plotly_title:
        lines = _split_title_rows(plotly_title)
        if len(lines) >= 3:
            return lines
    html_title = _extract_semantic_html_title(text)
    return _split_title_rows(html_title)


def _extract_plotly_title_text(text: str) -> str:
    patterns = (
        r'"title"\s*:\s*\{[^{}]*"text"\s*:\s*"((?:\\.|[^"])*)"',
        r'"text"\s*:\s*"((?:\\.|[^"])*)"\s*,\s*"title"',
    )
    fallback = ""
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            try:
                candidate = html.unescape(
                    match.group(1).encode().decode("unicode_escape")
                )
            except UnicodeDecodeError:
                candidate = html.unescape(match.group(1))
            if not fallback:
                fallback = candidate
            if len(_split_title_rows(candidate)) >= 3:
                return candidate
    return fallback


def _extract_semantic_html_title(text: str) -> str:
    title_block = re.search(
        r'<(?:header|div|section)[^>]+class="[^"]*(?:title|headline)[^"]*"[^>]*>'
        r"(.*?)</(?:header|div|section)>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if title_block:
        return title_block.group(1)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.IGNORECASE | re.DOTALL)
    return h1.group(1) if h1 else ""


def _split_title_rows(value: Any) -> list[str]:
    text = str(value or "")
    text = re.sub(r"</(?:h1|h2|p|div|span)>", "<br>", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return _clean_title_lines(text.splitlines())


def _clean_title_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_lines = re.split(r"\s*/\s*|<br\s*/?>|\n", value, flags=re.IGNORECASE)
    elif isinstance(value, list):
        raw_lines = [str(item) for item in value if item not in (None, "")]
    else:
        return []
    return [
        cleaned
        for cleaned in (
            re.sub(r"\s+", " ", html.unescape(line)).strip() for line in raw_lines
        )
        if cleaned
    ]


def _local_path_from_href(href: str, gallery_dir: Path) -> Path | None:
    if not href:
        return None
    parsed = urlparse(href)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    if parsed.scheme:
        return None
    return (gallery_dir / href).resolve()


def _log_html_items(items: Sequence[HtmlGalleryItem]) -> None:
    for item in items:
        LOGGER.error(
            "HTML-backed gallery card: label=%s source=%s output=%s",
            item.label,
            item.source,
            item.output,
        )


def _log_readiness_violations(
    violations: Sequence[GalleryReadinessViolation],
) -> None:
    for violation in violations:
        LOGGER.error(
            "Artifact-readiness violation: label=%s code=%s detail=%s",
            violation.label,
            violation.code,
            violation.detail,
        )


def _log_title_violations(
    violations: Sequence[GalleryReadinessViolation],
) -> None:
    for violation in violations:
        LOGGER.error(
            "Title-contract violation: label=%s code=%s detail=%s",
            violation.label,
            violation.code,
            violation.detail,
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(message)s",
    )

    try:
        manifest = _load_manifest(args.manifest)
        html_items = find_html_gallery_items(manifest)
        readiness_violations = (
            find_artifact_readiness_violations(args.manifest)
            if bool(args.require_artifact_ready)
            else []
        )
        title_violations = (
            find_title_contract_violations(args.manifest)
            if bool(args.require_title_contract)
            else []
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        LOGGER.error("Could not validate %s: %s", args.manifest, exc)
        return 2

    if readiness_violations:
        LOGGER.error(
            "Gallery has %s artifact-readiness violation(s): %s",
            len(readiness_violations),
            args.manifest,
        )
        _log_readiness_violations(readiness_violations)
        return 1

    if title_violations:
        LOGGER.error(
            "Gallery has %s title-contract violation(s): %s",
            len(title_violations),
            args.manifest,
        )
        _log_title_violations(title_violations)
        return 1

    if html_items and not bool(args.allow_html):
        LOGGER.error(
            "Curated PNG gallery has %s HTML-backed card(s); regenerate "
            "plugin examples with Chrome/Kaleido access before publishing.",
            len(html_items),
        )
        _log_html_items(html_items)
        return 1

    if html_items:
        LOGGER.warning(
            "Curated PNG gallery has %s HTML-backed card(s), allowed by flag.",
            len(html_items),
        )
    else:
        LOGGER.info("Curated PNG gallery is PNG-only: %s", args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
