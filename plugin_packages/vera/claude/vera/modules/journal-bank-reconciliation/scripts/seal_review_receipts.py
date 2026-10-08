"""Seal explicit mapping and relationship decisions for journal-bank reconciliation."""

from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__journal_bank_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/journal-bank-reconciliation"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Journal–Bank implementation bootstrap is not a real file.")
with open(_BOOTSTRAP_PATH, "rb") as _bootstrap_handle:
    _BOOTSTRAP_BEFORE = _bootstrap_os.fstat(_bootstrap_handle.fileno())
    _BOOTSTRAP_BYTES = _bootstrap_handle.read()
    _BOOTSTRAP_AFTER = _bootstrap_os.fstat(_bootstrap_handle.fileno())
_BOOTSTRAP_IDENTITY = (
    _BOOTSTRAP_ENTRY.st_dev,
    _BOOTSTRAP_ENTRY.st_ino,
    _BOOTSTRAP_ENTRY.st_size,
    _BOOTSTRAP_ENTRY.st_mtime_ns,
)
if (
    _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_BEFORE.st_dev,
        _BOOTSTRAP_BEFORE.st_ino,
        _BOOTSTRAP_BEFORE.st_size,
        _BOOTSTRAP_BEFORE.st_mtime_ns,
    )
    or _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_AFTER.st_dev,
        _BOOTSTRAP_AFTER.st_ino,
        _BOOTSTRAP_AFTER.st_size,
        _BOOTSTRAP_AFTER.st_mtime_ns,
    )
    or len(_BOOTSTRAP_BYTES) != _BOOTSTRAP_AFTER.st_size
):
    raise RuntimeError("Journal–Bank implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_journal_bank_implementation_bootstrap",
}
# The exact stable single-link bootstrap source is verified above.
exec(  # nosec B102
    compile(_BOOTSTRAP_BYTES, _BOOTSTRAP_PATH, "exec"), _BOOTSTRAP_NAMESPACE
)
_BOOTSTRAP_NAMESPACE["activate_implementation_boundary"]()
_SCRIPTS_DIR = _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__))
if _SCRIPTS_DIR not in _bootstrap_sys.path:
    _bootstrap_sys.path.insert(0, _SCRIPTS_DIR)

import argparse
import copy
import json
import logging
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from journal_bank_core import (
    build_mapping_review_receipt,
    build_relationship_review_receipt,
    canonical_json_sha256,
    configure_logging,
    inspect_mapping_review_source,
    read_json,
)
from vera_assurance import (
    AssuranceContractError,
    load_client_engagement_context_file,
    validate_artifact_receipt,
)

__all__ = ["main", "seal_review_receipts"]
LOGGER = logging.getLogger(__name__)
_MAPPING_FIELDS = {
    "header_rows",
    "mapping",
    "excluded_monetary_columns",
    "date_convention",
    "date_locale",
    "non_movement_summary_labels",
    "csv_field_delimiter",
    "decimal_separator",
    "thousands_separator",
    "direction_value_mapping",
}
_REQUIRED_MAPPING_FIELDS = {
    "header_rows",
    "mapping",
    "excluded_monetary_columns",
    "date_convention",
}


def seal_review_receipts(
    recipe: dict[str, Any],
    decisions: dict[str, Any],
    receipts: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Bind explicit decisions to current bytes; mechanical checks never approve policy."""
    if set(decisions) != {
        "reviewer_ref",
        "reviewed_on",
        "bank",
        "journal",
        "relationship",
    }:
        raise ValueError(
            "decisions must contain reviewer_ref, reviewed_on, bank, journal, relationship"
        )
    reviewer = decisions["reviewer_ref"]
    reviewed_on = decisions["reviewed_on"]
    if not isinstance(reviewer, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*", reviewer
    ):
        raise ValueError(
            "reviewer_ref must be an explicit identifier matching ^[A-Za-z0-9][A-Za-z0-9._-]*$"
        )
    if not isinstance(reviewed_on, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", reviewed_on
    ):
        raise ValueError("reviewed_on must be an explicit ISO date (YYYY-MM-DD)")
    date.fromisoformat(reviewed_on)
    result = copy.deepcopy(recipe)
    source_refs = []
    validated_sources = []
    for side in ("bank", "journal"):
        files = result[side]["files"]
        reviewed = decisions[side]
        if (
            not isinstance(reviewed, dict)
            or set(reviewed) != {"files"}
            or set(reviewed["files"]) != set(files)
            or not files
        ):
            raise ValueError(
                f"{side}.files must review every inspected source exactly once"
            )
        side_receipts = [
            item for item in receipts if item["root_id"] == f"source_{side}"
        ]
        if len(side_receipts) != len(files) or {
            item["path"] for item in side_receipts
        } != set(files):
            raise ValueError(
                f"{side}: input receipts must match every recipe source exactly once"
            )
        for index, (source_file, file_recipe) in enumerate(files.items(), start=1):
            choice = reviewed["files"][source_file]
            if (
                not isinstance(choice, dict)
                or not _REQUIRED_MAPPING_FIELDS <= set(choice)
                or set(choice) - _MAPPING_FIELDS
            ):
                raise ValueError(
                    f"{side}/{source_file}: mapping decisions are incomplete or contain unknown fields"
                )
            headers = choice["header_rows"]
            if (
                not isinstance(headers, list)
                or not headers
                or any(type(value) is not int or value < 1 for value in headers)
                or len(headers) != len(set(headers))
            ):
                raise ValueError(
                    f"{side}/{source_file}: header_rows must be explicit unique positive integers"
                )
            mapping = choice["mapping"]
            if (
                not isinstance(mapping, dict)
                or not mapping.get("date")
                or not any(mapping.get(key) for key in ("amount", "debit", "credit"))
            ):
                raise ValueError(
                    f"{side}/{source_file}: mapping requires date and amount or debit/credit"
                )
            receipt = next(
                item for item in side_receipts if item["path"] == source_file
            )
            relative = Path(source_file)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError("source paths must be canonical relative paths")
            candidates = [
                Path(item["path"])
                for item in context["input_bindings"]
                if Path(item["path"]).parts[-len(relative.parts) :] == relative.parts
            ]
            if len(candidates) != 1:
                raise ValueError(
                    f"{side}/{source_file}: source must resolve to one client engagement input"
                )
            source = candidates[0]
            root = source.parents[len(relative.parts) - 1]
            validate_artifact_receipt(root, receipt)
            if not receipt["artifact_id"].endswith("." + receipt["sha256"]):
                raise ValueError(
                    "source artifact reference must bind the current source digest"
                )
            validated_sources.append((root, receipt))
            source_refs.append(receipt["artifact_id"])
            # Never inherit unreviewed proposal values or a previously sealed receipt.
            for field in _MAPPING_FIELDS | {
                "mapping_decision",
                "potential_monetary_columns",
            }:
                file_recipe.pop(field, None)
            file_recipe.update(choice)
            diagnostic = inspect_mapping_review_source(
                source,
                side=side,
                source_file=source_file,
                recipe=result,
                source_artifact_ref=receipt["artifact_id"],
            )
            if diagnostic["qualification_status"] == "unsupported_source_layout":
                raise ValueError(
                    f"{side}/{source_file}: source layout or mapping cannot be reviewed"
                )
            potential = diagnostic["potential_monetary_columns"]
            sealed = build_mapping_review_receipt(
                decision_id=f"decision.mapping.{side}.{index}",
                reviewer_ref=reviewer,
                reviewed_on=reviewed_on,
                source_artifact_ref=receipt["artifact_id"],
                side=side,
                source_file=source_file,
                potential_monetary_columns=potential,
                **choice,
            )
            file_recipe["potential_monetary_columns"] = potential
            file_recipe["mapping_decision"] = sealed
            diagnostic = inspect_mapping_review_source(
                source,
                side=side,
                source_file=source_file,
                recipe=result,
                source_artifact_ref=receipt["artifact_id"],
            )
            if diagnostic["qualification_status"] != "qualified":
                raise ValueError(
                    f"{side}/{source_file}: reviewed mapping does not qualify source: {diagnostic.get('failure_kind')}"
                )
    relationship = build_relationship_review_receipt(
        decision_id="decision.relationship",
        reviewer_ref=reviewer,
        reviewed_on=reviewed_on,
        source_artifact_refs=source_refs,
        policy=decisions["relationship"],
    )
    policy = relationship["content"]["policy"]
    result["relationship"] = {
        "policy": policy,
        "decision": relationship,
        "review_content_sha256": canonical_json_sha256({"policy": policy}),
    }
    result.setdefault("matching", {}).update(
        {
            "amount_tolerance": policy["amount_tolerance"],
            "date_window_days": policy["date_window_days"],
        }
    )
    for root, receipt in validated_sources:
        validate_artifact_receipt(root, receipt)
    return result


def main() -> int:
    """Seal a complete reviewed recipe through the packaged managed entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    args = parser.parse_args()
    configure_logging()
    receipts_path = args.output_dir / "input_receipts.json"
    try:
        context = load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="journal-bank-reconciliation",
            input_paths=[args.recipe, args.decisions, receipts_path],
            output_dir=args.output_dir,
        )
        if not args.recipe.resolve().is_relative_to(Path(context["output_dir"])):
            raise AssuranceContractError(
                "recipe must be inside the client engagement output directory"
            )
    except AssuranceContractError as exc:
        LOGGER.error("CLIENT_ENGAGEMENT_BLOCKED: %s", exc)
        return 2
    try:
        result = seal_review_receipts(
            read_json(args.recipe),
            read_json(args.decisions),
            read_json(receipts_path)["receipts"],
            context,
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=args.recipe.parent,
            prefix=".review-receipts-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            try:
                json.dump(result, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            except (OSError, TypeError, ValueError):
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(args.recipe)
        finally:
            temporary.unlink(missing_ok=True)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        LOGGER.error("REVIEW_RECEIPTS_BLOCKED: %s", exc)
        return 2
    LOGGER.info("Sealed reviewed mapping and relationship receipts: %s", args.recipe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
