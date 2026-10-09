"""Fixed grant-dossier adapter over maintained public producers, without a model."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

__all__ = ["main"]

RECORDS = (
    "case_intake",
    "source_register",
    "application_workbench",
    "intelligence_register",
    "review_log",
    "run_state",
)
LIMIT = 2_000_000


def files(output: Path) -> dict:
    """Bind every regular output byte, excluding only the public operating lock."""
    result = {}
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise ValueError("Grant outputs cannot contain links")
        if path.is_dir() or path.name == ".bandi-agevolazioni.lock":
            continue
        if path.stat().st_nlink != 1:
            raise ValueError("Grant outputs must be single-link files")
        result[path.relative_to(output).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def main() -> None:
    """Expose exact public scopes and invoke only four offline dossier operations."""
    root = Path(sys.argv[1]).resolve()
    if root.name != "bandi-agevolazioni":
        raise PermissionError("Unsupported grant producer")
    sys.path.insert(0, str(root / "scripts"))
    from case_core import (
        canonical_json_sha256,
        load_client_engagement_context_file,
        require_run_artifact,
        safe_identifier,
        validate_iso_date,
    )
    from initialize_case import initialize_case
    from package_dossier import package_dossier
    from record_review import SCOPES, current_scope_hash, record_review
    from schema_validation import validate_artifact_schema
    from validate_application import validate_application

    raw = sys.stdin.read(LIMIT + 1)
    if len(raw.encode("utf-8")) > LIMIT:
        raise ValueError("Grant request exceeds the complete-payload boundary")
    request = json.loads(raw)
    action = request["operation"]
    if action == "implementation":
        directories = [root / "scripts", root / "schemas", root / "assets"]
        directories += [
            p / "vera_assurance"
            for p in (
                root / "vendor/modules",
                root.parent.parent / "vendor/modules",
                root.parent / "_shared/vendor/modules",
            )
            if (p / "vera_assurance").is_dir()
        ][:1]
        result = {
            f"{index}/{path.relative_to(directory).as_posix()}": hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for index, directory in enumerate(directories)
            for path in sorted(directory.rglob("*"))
            if path.is_file() and path.suffix in {".py", ".json"}
        }
    elif action == "preflight":
        fields = request["fields"]
        if request["scope"] == "initialization":
            validate_iso_date(fields["reference_date"], field="reference_date")
            safe_identifier(fields["client_reference"], field="client_reference")
            if not re.fullmatch(r"[A-Za-z-]{2,12}", fields["language"]):
                raise ValueError("Invalid language tag")
        else:
            if request["scope"] not in SCOPES:
                raise ValueError("Unsupported public review scope")
            safe_identifier(fields["reviewer_id"], field="reviewer_id")
            if (
                fields["decision"] not in {"accepted", "returned"}
                or not fields["reviewer_role"].strip()
            ):
                raise ValueError("Choose a decision and declare the reviewer role")
        result = {"status": "literal_fields_valid"}
    else:
        context_path = Path(request["context"])
        context = load_client_engagement_context_file(
            context_path,
            expected_workflow_id="bandi-agevolazioni",
            allowed_statuses=("running", "ready_for_review", "completed"),
        )
        output = Path(context["output_dir"])
        before = files(output)
        if action == "read":
            present = [name for name in RECORDS if name + ".json" in before]
            records = {}
            issues = []
            if present:
                if len(present) != len(RECORDS):
                    raise ValueError(
                        "Partial grant initialization needs ordinary recovery"
                    )
                for name in RECORDS:
                    path = output / (name + ".json")
                    if path.stat().st_size > LIMIT:
                        raise ValueError(
                            "Grant record exceeds the whole-record boundary"
                        )
                    records[name] = require_run_artifact(path, run_id=context["run_id"])
                    issues.extend(validate_artifact_schema(name, records[name]))
            hashes = {
                name: canonical_json_sha256(value) for name, value in records.items()
            }
            audit = (
                require_run_artifact(
                    output / "validation_audit.json", run_id=context["run_id"]
                )
                if "validation_audit.json" in before
                else None
            )
            manifest = (
                require_run_artifact(
                    output / "dossier_manifest.json", run_id=context["run_id"]
                )
                if "dossier_manifest.json" in before
                else None
            )
            audit_current = bool(audit and audit["artifact_hashes"] == hashes)
            package_current = bool(
                manifest
                and manifest["artifact_hashes"] == hashes
                and audit_current
                and manifest["validation_audit_sha256"] == canonical_json_sha256(audit)
                and all(
                    before.get(item["path"]) == item["sha256"]
                    for item in manifest["artifacts"]
                )
            )
            result = {
                "initialized": bool(records),
                "records": records,
                "schema_issues": issues,
                "record_hashes": hashes,
                "scope_hashes": (
                    {
                        scope: current_scope_hash(
                            output, run_id=context["run_id"], scope=scope
                        )
                        for scope in sorted(SCOPES)
                    }
                    if records
                    else {}
                ),
                "audit": audit,
                "audit_current": audit_current,
                "manifest": manifest,
                "package_current": package_current,
            }
            if files(output) != before:
                raise ValueError("Grant outputs changed while reading the whole scope")
        else:
            if before != request["expected_files"]:
                raise ValueError("Grant outputs changed before the public operation")
            if action == "initialize":
                if before:
                    raise ValueError(
                        "Existing grant outputs require ordinary continuation"
                    )
                initialize_case(
                    output,
                    client_engagement=context_path,
                    **request["fields"],
                )
                result = {"status": "empty_drafts_created", "ready_to_file": False}
            elif action == "review":
                result = record_review(
                    output_dir=output,
                    client_engagement=context_path,
                    scope=request["scope"],
                    confirmed_by_user=True,
                    **request["fields"],
                )
                if result["scope_sha256"] != request["scope_sha256"]:
                    raise ValueError(
                        "Public review scope changed; inspect the recorded event"
                    )
            elif action == "validate":
                result = validate_application(
                    output_dir=output, client_engagement=context_path
                )
            elif action == "package":
                result = package_dossier(
                    output_dir=output, client_engagement=context_path
                )
            else:
                raise ValueError("Unsupported grant dossier operation")
        result["files"] = files(output)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
