from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "ReviewPacket",
    "build_review_packet",
    "infer_family_id",
    "infer_variant_ids",
    "main",
]

LOGGER = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = Path("runs/png_examples/png-gallery/manifest.json")
DEFAULT_REFERENCE_PATH = Path("docs/visual_reporting_references.json")
FALLBACK_FAMILY_ID = "general_chart"
WORKFLOW_RULES = (
    "Start from the exact generated chart or table artifact, not from a best "
    "existing example.",
    "Use IBCS and UniformChart examples as directional references, not as "
    "gallery content or automatic templates.",
    "For improvement requests, diagnose and propose a scoped edit plan before "
    "changing code unless the user already asked to implement.",
    "Separate the requested change from adjacent reporting/IBCS suggestions.",
    "After approved edits, regenerate the relevant artifact and inspect the "
    "before/after output visually.",
)
VARIANT_MATCH_TERMS = (
    ("small_multiples", ("small multiples", "small_multiples")),
    ("stacked_column", ("stacked column",)),
    ("stacked_bar", ("stacked bar",)),
    ("stacked", ("stacked", "cohort")),
    ("waterfall", ("waterfall", "bridge")),
    ("scatter", ("scatter", "scattergram")),
    ("bubble", ("bubble",)),
    ("mekko", ("mekko", "marimekko")),
    ("mosaic", ("mosaic",)),
    ("table", ("table",)),
    ("bar", ("bar", "ranked")),
    ("column", ("column",)),
    ("variance", ("variance", "pvm", "year over year")),
    ("line", ("line", "slope")),
    ("distribution", ("distribution", "boxplot", "histogram", "ecdf", "stripplot")),
)
SOURCE_ORDER = ("IBCS", "UniformChart")


@dataclass(frozen=True)
class ReviewPacket:
    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(self.payload, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        return _packet_to_markdown(self.payload)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a chart/table visual review packet from the generated PNG "
            "gallery manifest and fixed reporting reference manifest."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Generated gallery manifest to inspect.",
    )
    parser.add_argument(
        "--references",
        type=Path,
        default=DEFAULT_REFERENCE_PATH,
        help="Fixed reporting visual reference manifest.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help=(
            "Case-insensitive substring filter across label, source, output, "
            "plugin source, capability, and grammar. May be repeated."
        ),
    )
    parser.add_argument(
        "--plugin-source",
        default="",
        help="Optional exact plugin_source filter from the gallery manifest.",
    )
    parser.add_argument(
        "--family",
        default="",
        help="Optional exact inferred family filter, such as column_bar.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of matched items to include.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path. Defaults to stdout.",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    return parser.parse_args(argv)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    items = manifest.get("items")
    if not isinstance(items, list):
        raise ValueError("gallery manifest must contain an items list")
    return [item for item in items if isinstance(item, dict)]


def _reference_families(reference_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    families = reference_manifest.get("families")
    if not isinstance(families, list):
        raise ValueError("reference manifest must contain a families list")
    return [family for family in families if isinstance(family, dict)]


def _reference_examples(reference_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    examples = reference_manifest.get("examples")
    if not isinstance(examples, list):
        return []
    return [example for example in examples if isinstance(example, dict)]


def _context_summary(item: dict[str, Any]) -> dict[str, Any]:
    context = item.get("context_summary")
    return context if isinstance(context, dict) else {}


def _search_text(item: dict[str, Any]) -> str:
    context = _context_summary(item)
    parts = [
        item.get("label"),
        item.get("plugin_source"),
        item.get("plugin_source_label"),
        item.get("source"),
        item.get("output"),
        context.get("capability"),
        context.get("grammar"),
        context.get("metrics"),
        context.get("dimensions"),
        context.get("periods"),
    ]
    return _normalize_text(" ".join(str(part) for part in parts if part))


def _normalize_text(value: str) -> str:
    value = value.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", value.lower()).strip()


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value))


def _matches_term(term: str, search_text: str, search_tokens: set[str]) -> bool:
    normalized_term = _normalize_text(term)
    if not normalized_term:
        return False
    if " " in normalized_term:
        return normalized_term in search_text
    return normalized_term in search_tokens


def infer_family_id(
    item: dict[str, Any],
    reference_manifest: dict[str, Any],
) -> str:
    """Infer a reporting visual family from stable gallery metadata."""

    known_family_ids = {
        family_id
        for family in _reference_families(reference_manifest)
        if isinstance((family_id := family.get("family_id")), str) and family_id
    }
    contract = item.get("artifact_contract")
    if isinstance(contract, dict):
        visual_family = contract.get("visual_family")
        if isinstance(visual_family, str) and visual_family in known_family_ids:
            return visual_family
        object_type = contract.get("object_type")
        if object_type == "table" and "reporting_table" in known_family_ids:
            return "reporting_table"
    if item.get("artifact_type") == "table" and "reporting_table" in known_family_ids:
        return "reporting_table"

    text = _search_text(item)
    tokens = _tokens(text)
    fallback = FALLBACK_FAMILY_ID
    best_family_id = fallback
    best_score = 0
    for family in _reference_families(reference_manifest):
        family_id = family.get("family_id")
        if not isinstance(family_id, str) or not family_id:
            continue
        if family_id == fallback:
            continue
        raw_terms = family.get("match_terms")
        terms = raw_terms if isinstance(raw_terms, list) else []
        score = sum(
            1
            for term in terms
            if isinstance(term, str) and _matches_term(term, text, tokens)
        )
        if score > best_score:
            best_family_id = family_id
            best_score = score
    return best_family_id


def infer_variant_ids(
    item: dict[str, Any],
    family: dict[str, Any] | None = None,
) -> list[str]:
    """Infer stable structural variants from gallery metadata for reference routing."""

    text = _search_text(item)
    tokens = _tokens(text)
    variants: list[str] = []
    seen: set[str] = set()
    for variant_id, terms in VARIANT_MATCH_TERMS:
        if any(_matches_term(term, text, tokens) for term in terms):
            variants.append(variant_id)
            seen.add(variant_id)
    if not variants and family is not None:
        defaults = family.get("default_variants")
        if isinstance(defaults, list):
            for default in defaults:
                if isinstance(default, str) and default and default not in seen:
                    variants.append(default)
                    seen.add(default)
    return variants


def _family_by_id(reference_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for family in _reference_families(reference_manifest):
        family_id = family.get("family_id")
        if isinstance(family_id, str) and family_id:
            by_id[family_id] = family
    return by_id


def _examples_by_id(reference_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for example in _reference_examples(reference_manifest):
        example_id = example.get("example_id")
        if isinstance(example_id, str) and example_id:
            by_id[example_id] = example
    return by_id


def _item_matches_filters(
    item: dict[str, Any],
    *,
    only_filters: Sequence[str],
    plugin_source: str,
) -> bool:
    if plugin_source and str(item.get("plugin_source") or "") != plugin_source:
        return False
    text = _search_text(item)
    return all(_normalize_text(needle) in text for needle in only_filters)


def _resolve_gallery_path(gallery_dir: Path, raw_path: Any) -> str:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return ""
    path = Path(raw_path)
    if path.is_absolute():
        return str(path)
    return str((gallery_dir / path).resolve())


def _sidecar_records(gallery_dir: Path, item: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sidecars = item.get("sidecars")
    if not isinstance(raw_sidecars, list):
        return []
    sidecars: list[dict[str, Any]] = []
    for sidecar in raw_sidecars:
        if not isinstance(sidecar, dict):
            continue
        label = str(sidecar.get("label") or "")
        path = _resolve_gallery_path(gallery_dir, sidecar.get("href"))
        sidecars.append(
            {
                "label": label,
                "path": path,
                "exists": bool(path and Path(path).exists()),
            }
        )
    return sidecars


def _quality_flag_labels(item: dict[str, Any]) -> list[str]:
    raw_flags = item.get("quality_flags")
    if not isinstance(raw_flags, list):
        return []
    labels: list[str] = []
    for flag in raw_flags:
        if isinstance(flag, dict):
            label = flag.get("label")
            detail = flag.get("detail")
            if label and detail:
                labels.append(f"{label}: {detail}")
            elif label:
                labels.append(str(label))
        elif flag:
            labels.append(str(flag))
    return labels


def _source_sort_index(source: str) -> int:
    try:
        return SOURCE_ORDER.index(source)
    except ValueError:
        return len(SOURCE_ORDER)


def _list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _classified_reference_records(
    family: dict[str, Any],
    reference_manifest: dict[str, Any],
    variant_ids: Sequence[str],
) -> list[dict[str, Any]]:
    examples_by_id = _examples_by_id(reference_manifest)
    raw_reference_ids = family.get("reference_example_ids")
    reference_ids = _list_of_strings(raw_reference_ids)
    if reference_ids:
        examples = [
            examples_by_id[example_id]
            for example_id in reference_ids
            if example_id in examples_by_id
        ]
    else:
        family_id = family.get("family_id")
        examples = [
            example
            for example in _reference_examples(reference_manifest)
            if example.get("family_id") == family_id
        ]

    variant_set = set(variant_ids)
    records: list[dict[str, Any]] = []
    for example in examples:
        local_asset = str(example.get("local_asset") or "")
        resolved_asset = str((REPO_ROOT / local_asset).resolve()) if local_asset else ""
        example_variants = _list_of_strings(example.get("variant_ids"))
        matched_variants = sorted(variant_set.intersection(example_variants))
        records.append(
            {
                "example_id": str(example.get("example_id") or ""),
                "source": str(example.get("source") or ""),
                "title": str(example.get("title") or ""),
                "family_id": str(example.get("family_id") or ""),
                "variant_ids": example_variants,
                "matched_variant_ids": matched_variants,
                "source_url": str(example.get("source_url") or ""),
                "asset_url": str(example.get("asset_url") or ""),
                "local_asset": resolved_asset,
                "local_asset_exists": bool(
                    resolved_asset and Path(resolved_asset).exists()
                ),
                "asset_type": str(example.get("asset_type") or ""),
                "primary_use": str(example.get("primary_use") or ""),
                "look_at": _list_of_strings(example.get("look_at")),
                "avoid_using_for": _list_of_strings(example.get("avoid_using_for")),
                "selection_tags": _list_of_strings(example.get("selection_tags")),
                "license_note": str(example.get("license_note") or ""),
            }
        )
    return sorted(
        records,
        key=lambda record: (
            -len(record["matched_variant_ids"]),
            _source_sort_index(record["source"]),
            record["example_id"],
        ),
    )


def _legacy_reference_records(family: dict[str, Any]) -> list[dict[str, Any]]:
    raw_examples = family.get("reference_examples")
    if not isinstance(raw_examples, list):
        return []
    records: list[dict[str, Any]] = []
    for example in raw_examples:
        if not isinstance(example, dict):
            continue
        local_asset = str(example.get("local_asset") or "")
        resolved_asset = str((REPO_ROOT / local_asset).resolve()) if local_asset else ""
        records.append(
            {
                "example_id": "",
                "source": str(example.get("source") or ""),
                "title": str(example.get("title") or ""),
                "family_id": str(family.get("family_id") or ""),
                "variant_ids": [],
                "matched_variant_ids": [],
                "source_url": str(example.get("url") or ""),
                "asset_url": "",
                "local_asset": resolved_asset,
                "local_asset_exists": bool(
                    resolved_asset and Path(resolved_asset).exists()
                ),
                "asset_type": "",
                "primary_use": str(example.get("notes") or ""),
                "look_at": [],
                "avoid_using_for": [],
                "selection_tags": [],
                "license_note": "",
            }
        )
    return records


def _reference_records(
    family: dict[str, Any],
    reference_manifest: dict[str, Any],
    variant_ids: Sequence[str],
) -> list[dict[str, Any]]:
    if _reference_examples(reference_manifest):
        return _classified_reference_records(family, reference_manifest, variant_ids)
    return _legacy_reference_records(family)


def _review_item(
    item: dict[str, Any],
    *,
    gallery_dir: Path,
    reference_manifest: dict[str, Any],
) -> dict[str, Any]:
    families = _family_by_id(reference_manifest)
    family_id = infer_family_id(item, reference_manifest)
    family = families.get(family_id) or families.get(FALLBACK_FAMILY_ID) or {}
    variant_ids = infer_variant_ids(item, family)
    return {
        "label": str(item.get("label") or ""),
        "plugin_source": str(item.get("plugin_source") or ""),
        "plugin_source_label": str(item.get("plugin_source_label") or ""),
        "family_id": family_id,
        "family_label": str(family.get("label") or family_id),
        "variant_ids": variant_ids,
        "artifact_type": str(item.get("artifact_type") or ""),
        "source_path": _resolve_gallery_path(gallery_dir, item.get("source")),
        "output_path": _resolve_gallery_path(gallery_dir, item.get("output")),
        "context_summary": _context_summary(item),
        "quality_flags": _quality_flag_labels(item),
        "sidecars": _sidecar_records(gallery_dir, item),
        "review_focus": (
            family.get("review_focus")
            if isinstance(family.get("review_focus"), list)
            else []
        ),
        "reference_examples": _reference_records(
            family,
            reference_manifest,
            variant_ids,
        ),
    }


def build_review_packet(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    reference_path: Path = DEFAULT_REFERENCE_PATH,
    *,
    only_filters: Sequence[str] = (),
    plugin_source: str = "",
    family_filter: str = "",
    limit: int = 0,
) -> ReviewPacket:
    manifest_path = manifest_path.resolve()
    reference_path = reference_path.resolve()
    manifest = _load_json_object(manifest_path)
    reference_manifest = _load_json_object(reference_path)
    gallery_dir = manifest_path.parent

    selected_items: list[dict[str, Any]] = []
    for item in _manifest_items(manifest):
        if not _item_matches_filters(
            item,
            only_filters=only_filters,
            plugin_source=plugin_source,
        ):
            continue
        inferred_family = infer_family_id(item, reference_manifest)
        if family_filter and inferred_family != family_filter:
            continue
        selected_items.append(item)

    if limit > 0:
        selected_items = selected_items[:limit]

    review_items = [
        _review_item(
            item,
            gallery_dir=gallery_dir,
            reference_manifest=reference_manifest,
        )
        for item in selected_items
    ]
    payload = {
        "schema_version": "1.0",
        "manifest_path": str(manifest_path),
        "reference_manifest_path": str(reference_path),
        "gallery_url_hint": "static/shared/png-gallery/index.html",
        "item_count": len(review_items),
        "mode": "single" if len(review_items) == 1 else "queue",
        "workflow_rules": list(WORKFLOW_RULES),
        "source_notes": reference_manifest.get("source_notes", []),
        "items": review_items,
    }
    return ReviewPacket(payload)


def _markdown_list(values: Sequence[Any], *, indent: str = "- ") -> list[str]:
    return [f"{indent}{value}" for value in values if str(value)]


def _packet_to_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Reporting Visual Review Packet",
        "",
        f"- Manifest: `{payload.get('manifest_path')}`",
        f"- References: `{payload.get('reference_manifest_path')}`",
        f"- Items: {payload.get('item_count')}",
        f"- Mode: {payload.get('mode')}",
        f"- Gallery: {payload.get('gallery_url_hint')}",
        "",
        "## Workflow Rules",
    ]
    lines.extend(_markdown_list(payload.get("workflow_rules") or []))
    lines.append("")
    for index, item in enumerate(payload.get("items") or [], start=1):
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                f"## {index}. {item.get('label')}",
                "",
                f"- Plugin: `{item.get('plugin_source')}`",
                f"- Family: `{item.get('family_id')}` ({item.get('family_label')})",
                f"- Variants: `{', '.join(item.get('variant_ids') or [])}`",
                f"- Artifact type: `{item.get('artifact_type')}`",
                f"- Output: `{item.get('output_path')}`",
                f"- Source: `{item.get('source_path')}`",
            ]
        )
        context = item.get("context_summary")
        if isinstance(context, dict) and context:
            compact_context = {
                key: context.get(key)
                for key in ("capability", "grammar", "metrics", "dimensions", "periods")
                if context.get(key)
            }
            if compact_context:
                lines.append(
                    f"- Context: `{json.dumps(compact_context, sort_keys=True)}`"
                )
        flags = item.get("quality_flags") or []
        lines.append(f"- Quality flags: {', '.join(flags) if flags else 'none'}")
        sidecars = item.get("sidecars") or []
        if sidecars:
            sidecar_bits = [
                f"{sidecar.get('label')}=`{sidecar.get('path')}`"
                for sidecar in sidecars
                if isinstance(sidecar, dict)
            ]
            lines.append(f"- Sidecars: {'; '.join(sidecar_bits)}")
        focus = item.get("review_focus") or []
        if focus:
            lines.append("- Review focus:")
            lines.extend(_markdown_list(focus, indent="  - "))
        references = item.get("reference_examples") or []
        if references:
            lines.append("- Reference examples:")
            for reference in references:
                if not isinstance(reference, dict):
                    continue
                asset = reference.get("local_asset")
                asset_state = (
                    "cached" if reference.get("local_asset_exists") else "not cached"
                )
                asset_note = (
                    f", asset {asset_state}: `{asset}`" if asset else ", no local asset"
                )
                matched = reference.get("matched_variant_ids") or []
                variant_note = f", variants: {', '.join(matched)}" if matched else ""
                lines.append(
                    "  - "
                    f"{reference.get('source')}: {reference.get('title')} "
                    f"({reference.get('source_url')}{asset_note}{variant_note})"
                )
                primary_use = reference.get("primary_use")
                if primary_use:
                    lines.append(f"    - Use for: {primary_use}")
                look_at = reference.get("look_at") or []
                if look_at:
                    lines.append(f"    - Look at: {', '.join(look_at[:4])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(message)s",
    )
    try:
        packet = build_review_packet(
            args.manifest,
            args.references,
            only_filters=args.only,
            plugin_source=args.plugin_source,
            family_filter=args.family,
            limit=args.limit,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        LOGGER.error("Could not prepare reporting visual review: %s", exc)
        return 2

    if packet.payload["item_count"] == 0:
        LOGGER.error("No gallery items matched the requested filters.")
        return 1

    output = packet.to_json() if args.format == "json" else packet.to_markdown()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        LOGGER.info("Wrote reporting visual review packet to %s", args.output)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
