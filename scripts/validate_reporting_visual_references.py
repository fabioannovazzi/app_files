from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

__all__ = [
    "ReferenceValidationIssue",
    "main",
    "validate_reporting_visual_references",
]

LOGGER = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_PATH = Path("docs/visual_reporting_references.json")
REQUIRED_FAMILY_FIELDS = (
    "family_id",
    "label",
    "match_terms",
    "default_variants",
    "review_focus",
    "reference_example_ids",
)
REQUIRED_EXAMPLE_FIELDS = (
    "example_id",
    "source",
    "title",
    "family_id",
    "variant_ids",
    "source_url",
    "asset_url",
    "asset_type",
    "primary_use",
    "look_at",
    "avoid_using_for",
    "selection_tags",
    "license_note",
)


@dataclass(frozen=True)
class ReferenceValidationIssue:
    location: str
    message: str


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the classified reporting visual reference corpus."
    )
    parser.add_argument(
        "--references",
        type=Path,
        default=DEFAULT_REFERENCE_PATH,
        help="Reference manifest to validate.",
    )
    parser.add_argument(
        "--allow-missing-assets",
        action="store_true",
        help="Allow missing local assets. Use only while drafting new examples.",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    return parser.parse_args(argv)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _list_of_dicts(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"reference manifest must contain a {key} list")
    return [item for item in value if isinstance(item, dict)]


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _validate_required_fields(
    record: dict[str, Any],
    *,
    required_fields: Sequence[str],
    location: str,
) -> list[ReferenceValidationIssue]:
    issues: list[ReferenceValidationIssue] = []
    for field in required_fields:
        value = record.get(field)
        if field not in record or value is None or value == "":
            issues.append(ReferenceValidationIssue(location, f"missing {field}"))
    return issues


def _duplicate_issues(
    records: Sequence[dict[str, Any]],
    *,
    key: str,
    location: str,
) -> list[ReferenceValidationIssue]:
    seen: set[str] = set()
    issues: list[ReferenceValidationIssue] = []
    for record in records:
        value = record.get(key)
        if not isinstance(value, str) or not value:
            continue
        if value in seen:
            issues.append(
                ReferenceValidationIssue(location, f"duplicate {key}: {value}")
            )
        seen.add(value)
    return issues


def _resolve_repo_path(path_value: Any) -> Path | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def _validate_asset(
    example: dict[str, Any],
    *,
    assets_root: Path | None,
    require_assets: bool,
) -> list[ReferenceValidationIssue]:
    example_id = str(example.get("example_id") or "<missing>")
    location = f"examples.{example_id}"
    asset_path = _resolve_repo_path(example.get("local_asset"))
    if asset_path is None:
        if require_assets:
            return [ReferenceValidationIssue(location, "missing local_asset")]
        return []

    issues: list[ReferenceValidationIssue] = []
    if assets_root is not None:
        try:
            asset_path.resolve().relative_to(assets_root.resolve())
        except ValueError:
            issues.append(
                ReferenceValidationIssue(
                    location,
                    f"local_asset is outside assets_root: {asset_path}",
                )
            )

    if not asset_path.exists():
        if require_assets:
            issues.append(
                ReferenceValidationIssue(location, f"local_asset missing: {asset_path}")
            )
        return issues

    try:
        with Image.open(asset_path) as image:
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        issues.append(
            ReferenceValidationIssue(
                location,
                f"local_asset is not a readable image: {asset_path} ({exc})",
            )
        )
    return issues


def validate_reporting_visual_references(
    reference_path: Path = DEFAULT_REFERENCE_PATH,
    *,
    require_assets: bool = True,
) -> list[ReferenceValidationIssue]:
    """Validate the reference corpus structure and local image assets."""

    payload = _load_json_object(reference_path)
    families = _list_of_dicts(payload, "families")
    examples = _list_of_dicts(payload, "examples")
    issues: list[ReferenceValidationIssue] = []

    if payload.get("schema_version") != "2.0":
        issues.append(
            ReferenceValidationIssue(
                "schema_version",
                "expected schema_version 2.0 for classified reference corpus",
            )
        )

    assets_root = _resolve_repo_path(payload.get("assets_root"))
    if assets_root is None:
        issues.append(ReferenceValidationIssue("assets_root", "missing assets_root"))

    family_ids = {
        family.get("family_id")
        for family in families
        if isinstance(family.get("family_id"), str)
    }
    example_ids = {
        example.get("example_id")
        for example in examples
        if isinstance(example.get("example_id"), str)
    }

    issues.extend(_duplicate_issues(families, key="family_id", location="families"))
    issues.extend(_duplicate_issues(examples, key="example_id", location="examples"))

    for family in families:
        family_id = str(family.get("family_id") or "<missing>")
        location = f"families.{family_id}"
        issues.extend(
            _validate_required_fields(
                family,
                required_fields=REQUIRED_FAMILY_FIELDS,
                location=location,
            )
        )
        for field in ("match_terms", "review_focus", "default_variants"):
            if field in family and not _is_string_list(family.get(field)):
                issues.append(
                    ReferenceValidationIssue(
                        location, f"{field} must be a list of strings"
                    )
                )
        reference_ids = family.get("reference_example_ids")
        if reference_ids is not None and not _is_string_list(reference_ids):
            issues.append(
                ReferenceValidationIssue(
                    location,
                    "reference_example_ids must be a list of strings",
                )
            )
        elif isinstance(reference_ids, list):
            for example_id in reference_ids:
                if example_id not in example_ids:
                    issues.append(
                        ReferenceValidationIssue(
                            location,
                            f"unknown reference_example_id: {example_id}",
                        )
                    )

    for example in examples:
        example_id = str(example.get("example_id") or "<missing>")
        location = f"examples.{example_id}"
        issues.extend(
            _validate_required_fields(
                example,
                required_fields=REQUIRED_EXAMPLE_FIELDS,
                location=location,
            )
        )
        family_id = example.get("family_id")
        if family_id not in family_ids:
            issues.append(
                ReferenceValidationIssue(location, f"unknown family_id: {family_id}")
            )
        for field in ("variant_ids", "look_at", "avoid_using_for", "selection_tags"):
            if not _is_string_list(example.get(field)):
                issues.append(
                    ReferenceValidationIssue(
                        location,
                        f"{field} must be a list of strings",
                    )
                )
        issues.extend(
            _validate_asset(
                example,
                assets_root=assets_root,
                require_assets=require_assets,
            )
        )

    return issues


def _log_issues(issues: Sequence[ReferenceValidationIssue]) -> None:
    for issue in issues:
        LOGGER.error("%s: %s", issue.location, issue.message)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(message)s",
    )
    try:
        issues = validate_reporting_visual_references(
            args.references,
            require_assets=not args.allow_missing_assets,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        LOGGER.error("Could not validate reporting visual references: %s", exc)
        return 2
    if issues:
        LOGGER.error(
            "Reporting visual reference validation failed: %s issue(s)", len(issues)
        )
        _log_issues(issues)
        return 1
    LOGGER.info("Reporting visual references are valid: %s", args.references)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
