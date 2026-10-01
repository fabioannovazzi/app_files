"""Prepare and adopt document preferences in the existing studio profile store."""

from __future__ import annotations

import argparse
import copy
import json
import logging
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from promote_studio_profile import persist_studio_profile
from workflow_core import (
    PLUGIN_ROOT,
    atomic_write_json,
    canonical_digest,
    copy_input_snapshot,
    file_digest,
    load_json,
    load_workspace,
    run_dir_from_workspace,
    utc_now,
    workflow_lock,
)

__all__ = ["prepare_format_review", "approve_format_review", "main"]
LOGGER = logging.getLogger(__name__)


def _validate_profile(profile: dict[str, Any]) -> None:
    schema = load_json(PLUGIN_ROOT / "schemas/model_contribution.schema.json")
    Draft202012Validator(
        {"$defs": schema["$defs"], **schema["properties"]["studio_profile_proposal"]}
    ).validate(profile)
    if profile is None:
        raise ValueError("A complete studio profile is required")


def _leaf_paths(value: Any, prefix: str) -> list[str]:
    if isinstance(value, dict):
        return [
            path
            for key, child in value.items()
            for path in _leaf_paths(child, f"{prefix}.{key}")
        ]
    return [prefix]


def prepare_format_review(
    workspace: Path,
    *,
    review_id: str,
    settings_path: Path,
    samples: list[Path],
    base_profile_path: Path | None = None,
) -> Path:
    """Snapshot selected examples and a model-prepared proposal for user review."""
    root = workspace.expanduser().resolve()
    manifest = load_workspace(root)
    review_dir = run_dir_from_workspace(root, review_id)
    with workflow_lock(root):
        if review_dir.exists():
            raise ValueError("Format review ID already exists; use a fresh ID")
        stored_path = root / "studio_profile.json"
        stored = load_json(stored_path) if stored_path.is_file() else None
        if stored:
            if stored["workspace_id"] != manifest["workspace_id"]:
                raise ValueError("Existing profile belongs to another studio workspace")
            if base_profile_path is not None:
                raise ValueError(
                    "An existing studio profile is authoritative; revise only DOCX preferences here"
                )
            base = stored
        elif base_profile_path is not None:
            base = load_json(base_profile_path)
        else:
            raise ValueError(
                "First setup requires a complete proposed communications profile and brand_profile"
            )
        profile = copy.deepcopy(base["profile"])
        settings = load_json(settings_path)
        profile["document"]["docx"] = settings
        _validate_profile(profile)
        brand = dict(base["brand_profile"])
        intake_schema = load_json(
            PLUGIN_ROOT / "schemas/communication_intake.schema.json"
        )
        Draft202012Validator(
            {"$defs": intake_schema["$defs"], "$ref": "#/$defs/brandProfile"}
        ).validate(brand)
        logo = brand.pop("logo_path", None)
        if stored:
            asset = stored["brand_assets"].get("logo")
            if asset:
                candidate = (root / asset["workspace_relative_path"]).resolve()
                if (
                    not candidate.is_relative_to(root / "studio_assets")
                    or file_digest(candidate) != asset["sha256"]
                ):
                    raise ValueError("Stored logo path or hash is invalid")
                logo = str(candidate)
        if settings.get("use_logo") and not logo:
            raise ValueError(
                "The proposed DOCX format requests a logo but none was supplied"
            )
        old_records = []
        for record in profile["field_provenance"]:
            remaining = [
                p for p in record["field_paths"] if not p.startswith("document.docx.")
            ]
            if remaining:
                old_records.append({**record, "field_paths": remaining})
        profile["field_provenance"] = old_records + [
            {
                "field_paths": _leaf_paths(settings, "document.docx"),
                "basis": "user_supplied",
                "history_ids": [],
                "analysis": "Proposed DOCX presentation settings are supplied for explicit studio review; selected examples are style evidence only.",
            }
        ]
        if not settings:
            raise ValueError("Supply at least one document preference")
        review_dir.mkdir(mode=0o700)
        records = [
            copy_input_snapshot(
                path, destination_dir=review_dir / "inputs", identity=f"sample-{i:03d}"
            )
            for i, path in enumerate(samples)
        ]
        logo_record = (
            copy_input_snapshot(
                Path(logo), destination_dir=review_dir / "inputs", identity="logo"
            )
            if logo
            else None
        )
        payload = {
            "schema_version": 1,
            "kind": "document_format_review",
            "workspace_id": manifest["workspace_id"],
            "studio_name": brand["studio_name"],
            "brand_profile": brand,
            "profile": profile,
            "previous_profile_sha256": file_digest(stored_path) if stored else None,
            "samples": records,
            "logo": logo_record,
            "prepared_at": utc_now(),
        }
        payload["review_digest"] = canonical_digest(payload)
        atomic_write_json(review_dir / "format_review.json", payload)
        review_text = (
            f"# Document format: {brand['studio_name']}\n\nReview digest: {payload['review_digest']}\n\n"
            "These are proposed presentation settings. Fonts are requested, not embedded or downloaded; availability must be checked in the renderer. "
            "Signature lines are plain text, not a digital signature. Samples are not copied into client reports.\n\n"
            "Inspect a synthetic preview, including a long table and page break, before confirming. "
            "The complete proposal below also shows the preserved communications settings.\n\n```json\n"
            + json.dumps(
                {"brand_profile": brand, "profile": profile},
                ensure_ascii=False,
                indent=2,
            )
            + "\n```\n"
        )
        (review_dir / "format_review.md").write_text(review_text, encoding="utf-8")
        return review_dir


def approve_format_review(
    review_dir: Path, *, review_digest: str, reviewer: str, confirmed_by_user: bool
) -> Path:
    """Persist the exact reviewed proposal using the common profile writer."""
    if not confirmed_by_user or not reviewer.strip():
        raise ValueError(
            "Studio format adoption requires explicit user confirmation and a reviewer"
        )
    root = review_dir.resolve().parent.parent
    manifest = load_workspace(root)
    if review_dir.resolve().parent != root / "runs":
        raise ValueError("Format review is outside the studio workspace")
    with workflow_lock(root):
        payload = load_json(review_dir / "format_review.json")
        declared_digest = payload.pop("review_digest")
        if (
            canonical_digest(payload) != declared_digest
            or declared_digest != review_digest
        ):
            raise ValueError(
                "Format proposal changed or supplied review digest differs"
            )
        if payload["workspace_id"] != manifest["workspace_id"]:
            raise ValueError("Format review belongs to another studio")
        stored_path = root / "studio_profile.json"
        stored = load_json(stored_path) if stored_path.is_file() else None
        if (
            stored
            and stored.get("approved_from", {}).get("contribution_digest")
            == review_digest
        ):
            return stored_path
        current_hash = file_digest(stored_path) if stored else None
        if current_hash != payload["previous_profile_sha256"]:
            raise ValueError("Studio profile changed; prepare a new format review")
        for record in payload["samples"] + (
            [payload["logo"]] if payload["logo"] else []
        ):
            snapshot = Path(record["snapshot_path"]).resolve()
            if (
                not snapshot.is_relative_to(review_dir.resolve() / "inputs")
                or file_digest(snapshot) != record["sha256"]
            ):
                raise ValueError(
                    "Selected format evidence changed or escapes its review"
                )
        _validate_profile(payload["profile"])
        return persist_studio_profile(
            root,
            profile=payload["profile"],
            brand_profile=payload["brand_profile"],
            workspace_id=manifest["workspace_id"],
            logo=Path(payload["logo"]["snapshot_path"]) if payload["logo"] else None,
            approved_from={
                "run_id": review_dir.name,
                "contribution_digest": review_digest,
                "review_event": {
                    "decision": "accepted",
                    "reviewer": reviewer,
                    "confirmed_by_user": True,
                    "asserted_not_authenticated": True,
                },
            },
        )


def main(argv: list[str] | None = None) -> int:
    """Expose the two internal workflow steps for Vera."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--workspace", type=Path, required=True)
    prepare.add_argument("--review-id", required=True)
    prepare.add_argument("--settings", type=Path, required=True)
    prepare.add_argument("--sample", type=Path, action="append", default=[])
    prepare.add_argument("--base-profile", type=Path)
    adopt = sub.add_parser("approve")
    adopt.add_argument("--review-dir", type=Path, required=True)
    adopt.add_argument("--review-digest", required=True)
    adopt.add_argument("--reviewer", required=True)
    adopt.add_argument("--confirmed-by-user", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "prepare":
        path = prepare_format_review(
            args.workspace,
            review_id=args.review_id,
            settings_path=args.settings,
            samples=args.sample,
            base_profile_path=args.base_profile,
        )
    else:
        path = approve_format_review(
            args.review_dir,
            review_digest=args.review_digest,
            reviewer=args.reviewer,
            confirmed_by_user=args.confirmed_by_user,
        )
    LOGGER.info("Studio format: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
