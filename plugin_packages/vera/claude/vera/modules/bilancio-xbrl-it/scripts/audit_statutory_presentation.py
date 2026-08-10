#!/usr/bin/env python3
"""Audit selected-form primary-statement coverage against a built catalogue.

The controlled zero-coverage scenario is structural test evidence only. Every
zero is an explicit simulated professional confirmation; it is never inferred
from an absent accounting fact and it does not represent a real entity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from statutory_presentation import build_statutory_presentation_coverage
from validate_xbrl import validate_instance
from xbrl_case import render_xbrl

__all__ = ["audit_statutory_presentation", "validate_complete_form_instances"]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular local JSON file")
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload, raw


def audit_statutory_presentation(
    catalogue: Mapping[str, Any], rule_pack: Mapping[str, Any]
) -> dict[str, Any]:
    """Verify each configured form inventory and an explicit-zero closure."""

    raw_forms = rule_pack.get("forms")
    if not isinstance(raw_forms, Mapping) or not raw_forms:
        raise ValueError("Statutory presentation rule pack defines no forms")
    forms: list[dict[str, Any]] = []
    for form in sorted(str(item) for item in raw_forms):
        coverage = _complete_form_coverage(form, catalogue, rule_pack)
        inventory = coverage["inventory"]
        forms.append(
            {
                "form": form,
                "inventory_sha256": inventory["inventory_sha256"],
                "roles": inventory["roles"],
                "unique_required_leaf_concepts": len(inventory["requirements"]),
                "unique_total_concepts": len(inventory["totals"]),
                "formula_count": len(inventory["formulas"]),
                "controlled_closure": {
                    "status": coverage["status"],
                    "explicit_decisions": coverage["summary"]["explicit_decisions"],
                    "output_fact_count": len(coverage["output_facts"]),
                    "missing_period_decisions": coverage["summary"][
                        "missing_period_decisions"
                    ],
                    "issues": coverage["summary"]["issues"],
                },
            }
        )
    report = {
        "schema_version": 1,
        "test_nature": "CONTROLLED_STRUCTURAL_ZERO_COVERAGE_ONLY",
        "limitation": (
            "This verifies inventory closure and official calculation mechanics; "
            "it is not evidence for a real entity's accounting judgments."
        ),
        "taxonomy_id": catalogue["taxonomy_id"],
        "taxonomy_package_sha256": catalogue["taxonomy_package_sha256"],
        "rule_pack_id": rule_pack["id"],
        "forms": forms,
    }
    report["report_sha256"] = hashlib.sha256(_canonical_json(report)).hexdigest()
    return report


def _complete_form_coverage(
    form: str,
    catalogue: Mapping[str, Any],
    rule_pack: Mapping[str, Any],
) -> dict[str, Any]:
    probe = build_statutory_presentation_coverage(
        {
            "selected_form": form,
            "period": {"start": "2025-01-01", "end": "2025-12-31"},
            "statements": {"facts": []},
            "canonical_facts": [],
            "taxonomy_facts": [],
        },
        catalogue,
        rule_pack,
        [],
        "controlled_structural_audit",
    )
    decisions = [
        {
            "xbrl_concept": item["xbrl_concept"],
            "current_status": "ZERO_CONFIRMED",
            "prior_status": "ZERO_CONFIRMED",
            "reason": "Controlled structural coverage test; not a real entity decision.",
            "source_refs": ["controlled-test:explicit-zero-coverage"],
        }
        for item in probe["inventory"]["requirements"]
    ]
    coverage = build_statutory_presentation_coverage(
        {
            "selected_form": form,
            "period": {"start": "2025-01-01", "end": "2025-12-31"},
            "statements": {"facts": []},
            "canonical_facts": [],
            "taxonomy_facts": [],
        },
        catalogue,
        rule_pack,
        decisions,
        "controlled_structural_audit",
    )
    if coverage["status"] != "COMPLETE":
        raise RuntimeError(f"Structural presentation closure failed for {form}")
    return coverage


def validate_complete_form_instances(
    catalogue: Mapping[str, Any],
    rule_pack: Mapping[str, Any],
    catalogue_path: Path,
    taxonomy_package: Path,
    output_dir: Path,
) -> list[dict[str, Any]]:
    """Render and validate one controlled complete-form instance per form."""

    if output_dir.is_symlink():
        raise ValueError("Complete-form validation output must not be a symbolic link")
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError("Complete-form validation output directory must be empty")
    results: list[dict[str, Any]] = []
    for form in sorted(str(item) for item in rule_pack["forms"]):
        coverage = _complete_form_coverage(form, catalogue, rule_pack)
        snapshot = {
            "case_id": f"controlled_complete_{form.lower()}",
            "entity": {
                "legal_name": f"Controlled Complete {form.title()} S.r.l.",
                "tax_identifier": "IT00000000000",
                "prior_period_start": "2024-01-01",
                "prior_period_end": "2024-12-31",
            },
            "period": {"start": "2025-01-01", "end": "2025-12-31"},
            "selected_form": form,
            "reporting_precision": 0,
            "output_language": "it",
            "rule_pack_versions": {"taxonomy_id": catalogue["taxonomy_id"]},
            "taxonomy_checksum": catalogue["taxonomy_package_sha256"],
            "statutory_presentation_required": True,
            "statutory_presentation": coverage,
            "canonical_facts": [],
            "taxonomy_facts": [],
            "narrative_blocks": [],
        }
        snapshot_hash = hashlib.sha256(_canonical_json(snapshot)).hexdigest()
        case = {
            "state": "APPROVED",
            "approval": {"snapshot": snapshot, "snapshot_hash": snapshot_hash},
        }
        instance = output_dir / f"controlled-complete-{form.lower()}.xbrl"
        instance.write_bytes(render_xbrl(case, catalogue_path))
        validation_report = output_dir / f"controlled-complete-{form.lower()}.json"
        validation = validate_instance(
            instance,
            validation_report,
            taxonomy_package,
            str(catalogue["taxonomy_package_sha256"]),
        )
        results.append(
            {
                "form": form,
                "status": validation["status"],
                "instance_file": instance.name,
                "instance_sha256": hashlib.sha256(instance.read_bytes()).hexdigest(),
                "validation_report_file": validation_report.name,
                "validation_report_sha256": hashlib.sha256(
                    validation_report.read_bytes()
                ).hexdigest(),
                "processor": validation["processor"],
                "message_count": len(validation["messages"]),
                "error_messages": [
                    item
                    for item in validation["messages"]
                    if item.get("level")
                    in {"error", "error-semantic", "assertion-not-satisfied"}
                ],
            }
        )
    if any(item["status"] != "PASS" for item in results):
        raise RuntimeError("At least one complete-form XBRL instance failed validation")
    return results


def main() -> int:
    """Run the controlled catalogue audit and optionally persist its report."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--rule-pack", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--taxonomy-package", type=Path)
    parser.add_argument("--instance-output-dir", type=Path)
    args = parser.parse_args()
    catalogue, catalogue_raw = _read_json(args.catalogue, "Taxonomy catalogue")
    rule_pack, rule_pack_raw = _read_json(args.rule_pack, "Presentation rule pack")
    report = audit_statutory_presentation(catalogue, rule_pack)
    if (args.taxonomy_package is None) != (args.instance_output_dir is None):
        raise ValueError(
            "Taxonomy package and instance output directory must be supplied together"
        )
    if args.taxonomy_package is not None and args.instance_output_dir is not None:
        validations = validate_complete_form_instances(
            catalogue,
            rule_pack,
            args.catalogue,
            args.taxonomy_package,
            args.instance_output_dir,
        )
        by_form = {item["form"]: item for item in validations}
        for form_result in report["forms"]:
            form_result["xbrl_validation"] = by_form[form_result["form"]]
        report.pop("report_sha256", None)
        report["report_sha256"] = hashlib.sha256(_canonical_json(report)).hexdigest()
    report["catalogue_file_sha256"] = hashlib.sha256(catalogue_raw).hexdigest()
    report["rule_pack_file_sha256"] = hashlib.sha256(rule_pack_raw).hexdigest()
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.is_symlink() or args.output.parent.is_symlink():
            raise ValueError("Audit output path must not use symbolic links")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
