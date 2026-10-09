"""Exact selected-source preparation over the maintained Journal–Bank engine."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["dispatch"]

LANGUAGES = {"it", "en", "fr", "de", "es"}


def draft_fields(
    value: Any, result: dict[str, Any], inputs: dict[str, Any]
) -> dict[str, Any]:
    """Bound unfinished app fields to producer identities without qualifying decisions."""
    if not isinstance(value, dict) or len(json.dumps(value).encode()) > 100_000:
        raise ValueError("Invalid or oversized bank draft")
    if value.get("phase") == "sources":
        if set(value) != {"phase", "choices", "language", "document_language"}:
            raise ValueError("Unexpected source draft fields")
        if result["status"] != "not_inspected":
            raise ValueError("Source draft belongs to another bank preparation phase")
        choices = value["choices"]
        if (
            not isinstance(choices, dict)
            or len(choices) > 1000
            or any(
                key not in inputs
                or not isinstance(side, str)
                or side not in {"bank", "journal", "sample"}
                for key, side in choices.items()
            )
        ):
            raise ValueError("Draft source choice is outside this run")
        if list(choices.values()).count("sample") > 1:
            raise ValueError("A source draft allows at most one sample")
        if (
            not isinstance(value["language"], str)
            or not isinstance(value["document_language"], str)
            or value["language"] not in LANGUAGES
            or value["document_language"] not in LANGUAGES | {"auto"}
        ):
            raise ValueError("Unsupported draft language")
        return value
    if value.get("phase") != "review" or set(value) != {
        "phase",
        "policy",
        "files",
        "selected_item_id",
    }:
        raise ValueError("Unexpected bank review draft fields")
    if result["status"] not in {"inspected", "reviewed"}:
        raise ValueError("Review draft belongs to another bank preparation phase")
    policy, files = value["policy"], value["files"]
    if not isinstance(policy, dict) or not isinstance(files, dict) or len(files) > 1000:
        raise ValueError("Invalid review draft fields")
    readonly = {"allow_evidence_reuse", "require_same_currency", "require_same_unit"}
    if not set(policy) <= set(result["proposal"]["policy"]) - readonly:
        raise ValueError("Draft policy fields are not editable")

    def check_values(record: dict[str, Any]) -> None:
        if any(
            not isinstance(item, (str, bool))
            or isinstance(item, str)
            and len(item) > 4000
            for item in record.values()
        ):
            raise ValueError("Invalid unfinished draft field")

    check_values(policy)
    # The full producer index is local; paginated rows never determine authority.
    index = result.pop("_draft_files")
    by_id = {row["id"]: row for row in index}
    if (
        not isinstance(value["selected_item_id"], str)
        or value["selected_item_id"]
        and value["selected_item_id"] not in by_id
    ):
        raise ValueError("Draft selection is outside this inspection")
    for identity, fields in files.items():
        if (
            identity not in by_id
            or not isinstance(fields, dict)
            or set(fields) != {"mapping", "options"}
        ):
            raise ValueError("Draft mapping is outside this inspection")
        row = by_id[identity]
        recipe = result["proposal"][row["side"]][row["title"]]
        for group, keys in (
            ("mapping", set(recipe["mapping"])),
            ("options", set(recipe) - {"mapping"}),
        ):
            record = fields[group]
            if not isinstance(record, dict) or not set(record) <= keys:
                raise ValueError("Draft mapping fields are not editable")
            check_values(record)
    return value


MAPPING_KEYS = (
    "header_rows",
    "mapping",
    "potential_monetary_columns",
    "excluded_monetary_columns",
    "direction_value_mapping",
    "date_convention",
    "date_locale",
    "non_movement_summary_labels",
    "csv_field_delimiter",
    "decimal_separator",
    "thousands_separator",
)


def file_hash(path: Path) -> str:
    """Hash exact regular single-link bytes without loading full tables into memory."""
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Bank preparation requires regular single-link files")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tree_hash(directory: Path) -> dict[str, str]:
    """Close the exact producer artifact population; hashes are mechanical evidence."""
    result = {}
    if any(parent.is_symlink() for parent in (directory, *directory.parents)):
        raise ValueError("Bank preparation directories cannot be linked")
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Bank preparation artifacts cannot be linked")
        if not path.is_dir():
            result[path.relative_to(directory).as_posix()] = file_hash(path)
    return result


def engine_call(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Use only the isolated maintained implementation and retain timeout uncertainty."""
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_bank_preparation_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if completed.returncode:
        raise ValueError(
            completed.stderr.strip().splitlines()[-1] or "Bank operation refused"
        )
    return json.loads(completed.stdout)


def verify_copies(
    base: Path, selection: dict[str, list[str]], inputs: dict[str, Any]
) -> None:
    """Verify the complete exact selected-source population, without semantic selection."""
    for side, ids in selection.items():
        expected = {
            identity
            + "/"
            + Path(inputs[identity]["execution_relative_path"]).name: inputs[identity][
                "sha256"
            ]
            for identity in ids
        }
        if tree_hash(base / "sources" / side) != expected:
            raise ValueError(
                "Selected bank source copies changed or their population differs"
            )


def dispatch(
    tool: str,
    args: dict[str, Any],
    binding: dict[str, Any],
    loaded: dict[str, Any],
    root: Path,
    api: Any,
) -> dict[str, Any]:
    """Revalidate identities, signatures upstream, source copies and producer receipts."""
    if binding["workflow_id"] != "journal-bank-reconciliation":
        raise PermissionError("Bank preparation belongs to a different workflow")
    if tool not in {
        "vera_workspace_bank_setup",
        "vera_workspace_bank_explain",
        "vera_workspace_bank_inspect",
        "vera_workspace_bank_review",
        "vera_workspace_bank_reconcile",
        "vera_workspace_bank_draft_read",
        "vera_workspace_bank_draft_save",
        "vera_workspace_bank_draft_clear",
    }:
        raise ValueError("Unknown bank preparation action")
    output = Path(loaded["output_dir"])
    private = api.ui_state_directory(output, create=False)
    state_path = private / "bank-preparation.json"
    saved = api.read_json(state_path) if state_path.exists() else None
    base = output / "bank-preparation"
    if any(parent.is_symlink() for parent in (base, *base.parents)):
        raise ValueError("Bank preparation directories cannot be linked")
    inputs = {row["binding_id"]: row for row in loaded["input_manifest"]["inputs"]}
    if any(
        not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", identity) or identity in {".", ".."}
        for identity in inputs
    ):
        raise ValueError("Bank input identity cannot form a portable source path")
    actor = os.environ["VERA_WORKSPACE_ACTOR_ID"]
    tenant = os.environ["VERA_WORKSPACE_TENANT_ID"]
    implementation = engine_call(root, {"operation": "implementation"})["sha256"]
    if saved:
        if saved["implementation_sha256"] != implementation:
            raise ValueError(
                "Bank inspection belongs to a changed maintained implementation"
            )
        verify_copies(base, saved["selection"], inputs)
        generation = base / saved["generation"]
        if tree_hash(generation) != saved["generation_hashes"]:
            raise ValueError("Prepared bank inspection or reviewed recipe changed")
    revision = api.digest(
        [
            loaded["run"],
            loaded["input_manifest"],
            saved,
            implementation,
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_bank_preparation_bridge.py")),
        ]
    )
    offset = args.get("offset", 0)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("Invalid bank preparation page offset")
    result = {
        "work_ref": binding["work_ref"],
        "revision": revision,
        "workflow": binding["workflow_id"],
        "label": loaded["run"]["label"],
        "client_id": binding["client_id"],
        "engagement_id": binding["engagement_id"],
        "status": saved["status"] if saved else "not_inspected",
        "can_write": loaded["run"]["status"] == "running"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","),
        "offset": offset,
        "selection": None,
    }
    rows = [
        {
            "id": identity,
            "title": Path(row["execution_relative_path"]).name,
            "role": row["role"],
        }
        for identity, row in inputs.items()
    ]
    if not saved and any(output.iterdir()):
        result.update(status="recovery_required", can_write=False)
    if any(
        not ({"result", "refusal"} & api.read_json(path).keys())
        for path in private.glob("bank-request-*.json")
    ):
        result.update(status="recovery_required", can_write=False)
    if saved:
        rows = api.read_json(generation / "native-preview/index.json")["files"]
        recipe = api.read_json(
            generation
            / (
                "reviewed_recipe.json"
                if saved["status"] != "inspected"
                else "suggested_recipe.json"
            )
        )
        result["proposal"] = {
            side: {
                name: {
                    key: value for key, value in record.items() if key in MAPPING_KEYS
                }
                for name, record in recipe[side]["files"].items()
            }
            for side in ("bank", "journal")
        }
        result["proposal"]["policy"] = recipe["relationship"]["policy"]
        if saved["status"] == "inspected":
            # The producer's EUR default is a proposal, never inferred currency authority.
            result["proposal"]["policy"]["default_currency"] = None
            result["proposal"]["policy"]["default_entity_ref"] = None
        result["qualification_status"] = saved["qualification_status"]
        result["can_execute"] = (
            saved["status"] == "reviewed"
            and saved["qualification_status"] == "qualified"
        )
    result.update(
        items=rows[offset : offset + 30],
        total=len(rows),
        has_more=offset + 30 < len(rows),
    )
    if args.get("item_id"):
        row = next((row for row in rows if row["id"] == args["item_id"]), None)
        if not saved or row is None:
            raise ValueError("Select an exact inspected source")
        result["selection"] = {
            "id": row["id"],
            **api.read_json(generation / "native-preview" / (row["id"] + ".json")),
        }
    if (
        args.get("revision")
        and args["revision"] != revision
        and tool in {"vera_workspace_bank_setup", "vera_workspace_bank_explain"}
    ):
        raise ValueError("Bank preparation changed; reopen the exact source selection")
    if tool == "vera_workspace_bank_explain":
        if not result["selection"]:
            raise ValueError("Select one inspected bank/journal source")
        if len(json.dumps(result["selection"], ensure_ascii=False).encode()) > 64_000:
            raise ValueError("Selected bank inspection exceeds the model context bound")
        evidence = dict(result["selection"])
        evidence.pop("id")
        evidence["source_file"] = Path(evidence["source_file"]).name
        evidence["preview"] = [
            {
                key: value
                for key, value in row.items()
                if key
                not in {
                    "transaction_id",
                    "source_file",
                    "source_artifact_ref",
                    "source_row",
                    "source_sheet",
                    "reference",
                    "movement_number",
                    "account",
                    "amount_abs",
                }
            }
            for row in evidence.get("preview", [])
        ]
        return {
            "work_ref": binding["work_ref"],
            "revision": revision,
            "purpose": "Review the selected producer inspection metadata and at most 20 normalized preview rows; no approval or full-table access",
            "source": evidence,
        }
    if tool == "vera_workspace_bank_setup":
        if len(json.dumps(result, ensure_ascii=False).encode()) > 2_000_000:
            raise ValueError("Bank preparation exceeds the panel projection bound")
        return result
    if tool.startswith("vera_workspace_bank_draft_"):
        path = private / ("bank-draft-" + api.digest([tenant, actor]) + ".json")

        def read_draft() -> dict[str, Any] | None:
            if not path.exists():
                return None
            if (
                path.is_symlink()
                or not path.is_file()
                or path.stat().st_nlink != 1
                or path.stat().st_size > 110_000
            ):
                raise ValueError("Bank draft must be a regular single-link file")
            document = api.read_json(path)
            if (
                not isinstance(document, dict)
                or document.get("schema_version") != 1
                or document.get("draft_revision")
                != api.digest(
                    {
                        key: item
                        for key, item in document.items()
                        if key != "draft_revision"
                    }
                )
            ):
                raise ValueError("Bank draft integrity changed")
            if any(
                document.get(key) != expected
                for key, expected in {
                    "actor_id": actor,
                    "tenant_id": tenant,
                    "work_ref": binding["work_ref"],
                    **{
                        key: binding[key]
                        for key in ("client_id", "engagement_id", "run_id")
                    },
                }.items()
            ):
                raise PermissionError("Bank draft belongs to a different scope")
            return document

        document = read_draft()
        if tool.endswith("_read"):
            return {
                "draft": document,
                "current_revision": revision,
                "stale": bool(document and document["revision"] != revision),
                "file_bindings": {
                    row["id"]: {"side": row["side"], "source_file": row["title"]}
                    for row in rows
                    if saved
                    and document
                    and row["id"] in document["fields"].get("files", {})
                },
            }
        if not result["can_write"] or result["status"] in {
            "reconciled",
            "recovery_required",
        }:
            raise PermissionError(
                "An editable running bank run and reviewer authority are required"
            )
        if args.get("revision") != revision:
            raise ValueError("Bank draft revision changed; reopen this run")
        expected = args.get("expected_draft_revision")
        if (
            not isinstance(expected, str)
            or expected
            and not re.fullmatch(r"[0-9a-f]{64}", expected)
        ):
            raise ValueError("Invalid bank draft checkpoint")
        with api.write_lock(output):
            if (
                api.load_binding(binding) != loaded
                or (api.read_json(state_path) if state_path.exists() else None) != saved
            ):
                raise ValueError("Bank preparation changed before draft write")
            document = read_draft()
            if (document["draft_revision"] if document else "") != expected:
                raise ValueError(
                    "Bank draft changed in another panel; reopen the saved draft"
                )
            if saved:
                verify_copies(base, saved["selection"], inputs)
                if tree_hash(generation) != saved["generation_hashes"]:
                    raise ValueError("Bank inspection changed before draft write")
            if tool.endswith("_clear"):
                path.unlink(missing_ok=True)
                return {"draft_cleared": True}
            if saved:
                result["_draft_files"] = rows
            fields = draft_fields(args["fields"], result, inputs)
            document = {
                "schema_version": 1,
                "actor_id": actor,
                "tenant_id": tenant,
                "work_ref": binding["work_ref"],
                **{
                    key: binding[key]
                    for key in ("client_id", "engagement_id", "run_id")
                },
                "revision": revision,
                "fields": fields,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            document["draft_revision"] = api.digest(document)
            api.atomic_json(path, document)
            return {"draft_saved": True, "draft_revision": document["draft_revision"]}
    if (
        loaded["run"]["status"] != "running"
        or "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        or args.get("human_reviewed") is not True
    ):
        raise PermissionError("A running run and explicit reviewer action are required")
    with api.write_lock(output):
        live = api.load_binding(binding)
        live_state = api.read_json(state_path) if state_path.exists() else None
        if live_state != saved or api.digest(
            [live["run"], live["input_manifest"]]
        ) != api.digest([loaded["run"], loaded["input_manifest"]]):
            raise ValueError("Bank preparation changed before the write lock")
        if saved:
            verify_copies(base, saved["selection"], inputs)
            if tree_hash(generation) != saved["generation_hashes"]:
                raise ValueError("Prepared bank inspection or reviewed recipe changed")
        receipt = private / (
            "bank-request-"
            + api.digest([actor, tenant, args["idempotency_key"]])
            + ".json"
        )
        request_hash = api.digest([tool, args])
        if receipt.exists():
            previous = api.read_json(receipt)
            if previous["request_hash"] != request_hash:
                raise ValueError("Bank operation key belongs to a different request")
            if "refusal" in previous:
                raise ValueError(previous["refusal"])
            if "result" not in previous:
                raise ValueError(
                    "Bank operation outcome needs verification; do not restart it automatically"
                )
            return previous["result"]
        if not result["can_write"]:
            raise ValueError("Bank operation outcome requires specialist recovery")
        if args["revision"] != revision:
            raise ValueError("Bank preparation changed; reopen it before writing")
        if saved and saved["status"] == "reconciled":
            raise ValueError(
                "This bank run already has results; review its existing outputs"
            )
        if not saved and any(output.iterdir()):
            raise ValueError(
                "Existing output requires the maintained specialist recovery route"
            )
        operation = tool.removeprefix("vera_workspace_bank_")
        if operation == "inspect":
            if saved:
                raise ValueError(
                    "Retain the existing inspection; changing sources requires a new run"
                )
            selection = {
                side: args[side + "_input_ids"] for side in ("bank", "journal")
            }
            selection["sample"] = (
                [args["sample_input_id"]] if args.get("sample_input_id") else []
            )
            chosen = [identity for ids in selection.values() for identity in ids]
            if (
                not selection["bank"]
                or not selection["journal"]
                or len(set(chosen)) != len(chosen)
                or any(identity not in inputs for identity in chosen)
            ):
                raise ValueError(
                    "Select disjoint exact bank, journal and optional sample inputs"
                )
            for identity in chosen:
                path = (
                    Path(loaded["run_root"])
                    / inputs[identity]["execution_relative_path"]
                )
                if path.suffix.lower() not in {
                    ".csv",
                    ".xlsx",
                    ".xls",
                    ".pdf",
                } or path.name.startswith("~$"):
                    raise ValueError(
                        "Selected source is not a supported bank/journal input"
                    )
            language, document_language = args["language"], args["document_language"]
        else:
            if not saved:
                raise ValueError("Inspect the exact selected sources first")
            selection = saved["selection"]
            language, document_language = saved["language"], saved["document_language"]
            if operation == "reconcile" and not result.get("can_execute"):
                raise ValueError(
                    "Current source qualification and reviewed relationship policy are required"
                )
            if operation not in {"review", "reconcile"}:
                raise ValueError("Unknown bank preparation action")
        api.atomic_json(receipt, {"request_hash": request_hash})
        base.mkdir(mode=0o700, exist_ok=True)
        if operation == "inspect":
            for side, ids in selection.items():
                directory = base / "sources" / side
                directory.mkdir(parents=True, mode=0o700)
                for identity in ids:
                    row = inputs[identity]
                    source = Path(loaded["run_root"]) / row["execution_relative_path"]
                    destination = directory / identity / source.name
                    destination.parent.mkdir(mode=0o700)
                    with source.open("rb") as origin, destination.open("xb") as target:
                        destination.chmod(0o600)
                        for chunk in iter(lambda: origin.read(1024 * 1024), b""):
                            target.write(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                    if file_hash(destination) != row["sha256"]:
                        raise ValueError(
                            "Selected source changed while making its exact copy"
                        )
        generation_name = (
            operation + "-" + api.digest([actor, tenant, args["idempotency_key"]])
        )
        operation_output = (
            output / "reconciliation"
            if operation == "reconcile"
            else base / generation_name
        )
        if operation_output.exists():
            raise ValueError(
                "Retain existing bank outputs; do not overwrite a previous operation"
            )
        operation_output.mkdir(mode=0o700)
        recipe_path = (
            None
            if operation == "inspect"
            else generation
            / (
                "suggested_recipe.json"
                if saved["status"] == "inspected"
                else "reviewed_recipe.json"
            )
        )
        request = {
            "operation": operation,
            "bank": str(base / "sources/bank"),
            "journal": str(base / "sources/journal"),
            "sample": str(base / "sources/sample") if selection["sample"] else None,
            "output": str(operation_output),
            "context": loaded["context_path"],
            "recipe": str(recipe_path) if recipe_path else None,
            "language": language,
            "document_language": document_language,
            "actor": actor,
            "reviewed_on": datetime.now(timezone.utc).date().isoformat(),
        }
        if operation == "review":
            request["proposal"] = json.loads(args["proposal_json"])
        engine_result = engine_call(root, request)
        if "review_refused" in engine_result:
            api.atomic_json(
                receipt,
                {
                    "request_hash": request_hash,
                    "refusal": engine_result["review_refused"],
                },
            )
            raise ValueError(engine_result["review_refused"])
        api.load_binding(binding)
        verify_copies(base, selection, inputs)
        if saved and tree_hash(generation) != saved["generation_hashes"]:
            raise ValueError("Prepared bank inspection changed during the operation")
        if (
            engine_call(root, {"operation": "implementation"})["sha256"]
            != implementation
        ):
            raise ValueError("Bank implementation changed during the operation")
        if operation == "reconcile":
            saved["status"] = "reconciled"
        else:
            saved = {
                "selection": selection,
                "language": language,
                "document_language": document_language,
                "generation": generation_name,
                "generation_hashes": tree_hash(operation_output),
                "status": "inspected" if operation == "inspect" else "reviewed",
                "qualification_status": engine_result["qualification_status"],
                "implementation_sha256": implementation,
            }
        api.atomic_json(state_path, saved)
        response = {
            "work_ref": binding["work_ref"],
            "status": saved["status"],
            **engine_result,
            "professional_approval": False,
            "run_completed": False,
        }
        api.atomic_json(receipt, {"request_hash": request_hash, "result": response})
        return response
