"""Exact native Scissione version reads and recoverable record-specific reviews."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash

__all__ = ["dispatch", "read_prepared"]

FIELDS = {"reviewer", "role", "reviewed_at", "rationale"}
FILES = {
    "revision.json",
    "review.md",
    "review.html",
    "ownership_before_after.json",
    "allocations.json",
    "change_impact.json",
    "artifact_manifest.json",
}
KINDS = {
    "fact": "Fatto",
    "allocation": "Assegnazione",
    "liability": "Passività",
    "ownership": "Partecipazioni",
    "valuation": "Valutazione",
    "tax_position": "Posizione fiscale",
    "rule": "Fonte normativa",
    "decision": "Decisione",
    "deadline": "Scadenza",
    "document": "Documento",
}


def engine_call(root: Path, request: dict) -> dict:
    """Run only the fixed isolated maintained service; retain uncertain append outcomes."""
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_scissione_bridge.py")),
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
            completed.stderr.strip().splitlines()[-1] or "Scissione service refused"
        )
    return json.loads(completed.stdout)


def offset(args: dict) -> int:
    """Paginate exact records mechanically, without semantic selection."""
    value = args.get("offset", 0)
    if type(value) is not int or value < 0:
        raise ValueError("Invalid Scissione page offset")
    return value


def bounded(value: dict) -> dict:
    """Refuse oversized private pages rather than silently substituting a summary."""
    if len(json.dumps(value).encode()) > 2_000_000:
        raise ValueError("Scissione page exceeds native limit; use specialist workflow")
    return value


def catalogue(root: Path, binding: dict, loaded: dict, api: Any) -> dict:
    """Close the exact artifact population and public current pointer; infer no latest approval."""
    if (
        binding["workflow_id"] != "scissione-guidata"
        or root.name != "scissione-guidata"
    ):
        raise PermissionError("Scissione belongs to another workflow")
    output = Path(loaded["output_dir"])
    versions = output / "scissione_versions"
    pointer = output / "scissione_current.json"
    rows, population = [], {}
    if versions.exists() != pointer.exists():
        raise ValueError("Incomplete Scissione pointer/version population")
    if versions.exists():
        if versions.is_symlink() or not versions.is_dir():
            raise ValueError("Linked or invalid Scissione version directory")
        population[pointer.name] = file_hash(pointer)
        current = api.read_json(pointer)["revision_sha256"]
        for folder in sorted(versions.iterdir()):
            if (
                not re.fullmatch(r"[0-9a-f]{64}", folder.name)
                or folder.is_symlink()
                or not folder.is_dir()
                or {p.name for p in folder.iterdir()} != FILES
            ):
                raise ValueError(
                    "Unknown Scissione artifacts require specialist recovery"
                )
            hashes = {p.name: file_hash(p) for p in folder.iterdir()}
            manifest = api.read_json(folder / "artifact_manifest.json")
            if manifest != {
                "files": {
                    k: v for k, v in hashes.items() if k != "artifact_manifest.json"
                },
                "revision_sha256": folder.name,
            }:
                raise ValueError("Scissione artifact manifest changed")
            record = api.read_json(folder / "revision.json")
            if record["revision_sha256"] != folder.name:
                raise ValueError("Scissione version identity changed")
            population.update(
                {
                    "scissione_versions/" + folder.name + "/" + name: sha
                    for name, sha in hashes.items()
                }
            )
            rows.append(
                {
                    "id": folder.name,
                    "title": record["case"]["as_of"] + " · " + record["status"],
                    "status": record["status"],
                    "as_of": record["case"]["as_of"],
                    "current": folder.name == current,
                }
            )
        if current not in {row["id"] for row in rows} or api.read_json(pointer) != {
            "revision_sha256": current,
            "report": "scissione_versions/" + current + "/review.html",
        }:
            raise ValueError(
                "Scissione current pointer does not identify a verified version"
            )
    else:
        current = None
    implementation = engine_call(root, {"operation": "implementation"})
    from native_aml_authoring import audit_run

    authoring = audit_run(output, api, "scissione-guidata")
    checkpoint = api.digest(
        [
            loaded["run"],
            loaded["input_manifest"],
            population,
            implementation,
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_scissione_bridge.py")),
            authoring,
        ]
    )
    return {
        "rows": rows,
        "current": current,
        "population": population,
        "implementation": implementation,
        "checkpoint": checkpoint,
        "authoring": authoring,
    }


def read_record(root: Path, binding: dict, loaded: dict, ref: str, api: Any) -> dict:
    """Replay lineage, reports and exact evidence receipts inside this authorised run."""
    if not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{64}", ref):
        raise ValueError("Choose an exact Scissione revision")
    record = engine_call(
        root,
        {"operation": "read", "context": str(loaded["context_path"]), "revision": ref},
    )
    inputs = {
        Path(loaded["run_root"]) / row["execution_relative_path"]: row["sha256"]
        for row in loaded["input_manifest"]["inputs"]
    }
    for row in record["case"]["evidence"]:
        relative = Path(row["path"])
        path = Path(loaded["run_root"]) / "inputs" / relative
        if relative.is_absolute() or ".." in relative.parts or path not in inputs:
            raise PermissionError("Scissione evidence is outside registered inputs")
        if row["sha256"] != inputs[path] or file_hash(path) != row["sha256"]:
            raise ValueError("Scissione source receipt changed")
    return record


def record_item(row: dict, api: Any, case: dict) -> dict:
    """Name an existing authored record and retain its precise opaque identity."""
    roles = {
        case["route_record"]: "Percorso dell’operazione",
        case["perimeter_record"]: "Perimetro da verificare",
        case["calculation_record"]: "Ipotesi e basi del calcolo",
    }
    return {
        "id": "record:" + api.digest(row["id"])[:32],
        "title": roles.get(
            row["id"],
            KINDS[row["kind"]] + " · " + str(row["data"].get("choice", row["id"])),
        ),
        "group": "record",
        "data": row,
    }


def read_prepared(
    root: Path, binding: dict, loaded: dict, args: dict, api: Any
) -> dict:
    """Return at most 30 labels and one linked section from an exact immutable version."""
    before = catalogue(root, binding, loaded, api)
    ref = args.get("source_ref")
    if ref is None and len(before["rows"]) == 1:
        ref = before["rows"][0]["id"]
    if ref not in {row["id"] for row in before["rows"]}:
        raise ValueError("Choose an exact persisted Scissione revision")
    record = read_record(root, binding, loaded, ref, api)
    case = record["case"]
    rows = [
        {
            "id": "perimeter",
            "title": "Perimetro dell’operazione",
            "group": "perimeter",
            "data": {
                "purpose": case["purpose"],
                "as_of": case["as_of"],
                "currency": case["currency"],
                "entities": case["entities"],
            },
        }
    ]
    rows += [record_item(row, api, case) for row in case["records"]]
    rows += [
        {
            "id": "issue:" + str(i),
            "title": issue,
            "group": "issue",
            "data": {"message": issue},
        }
        for i, issue in enumerate(record["issues"])
    ]
    rows.append(
        {
            "id": "impact",
            "title": "Modifiche e decisioni riaperte",
            "group": "impact",
            "data": record["change_impact"],
        }
    )
    for section in ("owners", "allocations"):
        rows += [
            {
                "id": section + ":" + str(i),
                "title": ("Partecipazioni" if section == "owners" else "Assegnazioni")
                + " · "
                + str(i + 1),
                "group": section,
                "data": row,
            }
            for i, row in enumerate(record["schedule"].get(section, []))
        ]
    totals = {
        k: v
        for k, v in record["schedule"].items()
        if k not in {"owners", "allocations"}
    }
    if totals:
        rows.append(
            {
                "id": "totals",
                "title": "Totali e residui del prospetto",
                "group": "totals",
                "data": totals,
            }
        )
    selected = next((row for row in rows if row["id"] == args.get("item_id")), None)
    if selected and selected["group"] == "record":
        records = {row["id"]: row for row in case["records"]}
        linked, pending = set(), list(selected["data"]["depends_on"])
        while pending:
            key = pending.pop()
            if key not in linked:
                linked.add(key)
                pending.extend(records[key]["depends_on"])
        dependencies = [row for row in case["records"] if row["id"] in linked]
        evidence_ids = {
            key
            for row in [selected["data"], *dependencies]
            for key in row["evidence_ids"]
        }
        selected = {
            **selected,
            "approval": record["approvals"].get(selected["data"]["id"]),
            "dependencies": dependencies,
            "evidence": [row for row in case["evidence"] if row["id"] in evidence_ids],
        }
    prefix = "scissione_versions/" + ref + "/"
    artifacts = {k: v for k, v in before["population"].items() if k.startswith(prefix)}
    revision = api.digest(
        [
            loaded["run"],
            loaded["input_manifest"],
            ref,
            artifacts,
            before["implementation"],
        ]
    )
    after = catalogue(root, binding, loaded, api)
    if after != before:
        raise ValueError("Scissione state changed during read; reopen exact version")
    start = offset(args)
    return bounded(
        {
            "revision": revision,
            "items": [
                {k: row[k] for k in ("id", "title", "group")}
                for row in rows[start : start + 30]
            ],
            "selection": selected,
            "total": len(rows),
            "data": {
                "status": record["status"],
                "as_of": case["as_of"],
                "purpose": case["purpose"],
                "currency": case["currency"],
                "filing_status": record["filing_status"],
                "legal_validation": record["legal_validation"],
                "selection": {"source_ref": ref},
                "current": ref == before["current"],
                "decision_checkpoint": before["checkpoint"],
                "artifacts": list(artifacts),
                "can_review": ref == before["current"]
                and not before["authoring"]["recovery_required"]
                and loaded["run"]["status"] == "running"
                and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","),
                "verification": "Exact authored record and dependencies with maintained-engine lineage/report replay. Attribution and recorded entity authority are not authenticated identity or access credentials. Calculations do not certify legal validity, completeness, due diligence, tax applicability, company acts, signing, filing or Archive completion. Initial case preparation and same-evidence correction require a separate explicit source mandate and full case proposal. Material new sources, source qualification, professional applicability, model-data reporting and Archive finalization remain specialist-led.",
            },
        }
    )


def draft_path(output: Path, binding: dict, ref: str, item: str, api: Any) -> Path:
    """Keep unfinished attribution outside official files, scoped to actor/run/version/record."""
    return api.ui_state_directory(output, create=False) / (
        "scissione-draft-"
        + api.digest(
            [
                os.environ["VERA_WORKSPACE_ACTOR_ID"],
                os.environ["VERA_WORKSPACE_TENANT_ID"],
                binding,
                ref,
                item,
            ]
        )
        + ".json"
    )


def draft_read(path: Path, api: Any) -> tuple[dict, str]:
    """Validate exact private draft integrity; confirmation is never retained."""
    if not path.exists():
        return {"fields": {}}, ""
    value = api.read_json(path)
    stamp = value["draft_sha256"]
    if stamp != api.digest({k: v for k, v in value.items() if k != "draft_sha256"}):
        raise ValueError("Scissione draft changed")
    return value, stamp


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Save private proposals or append an explicit record review through the unchanged engine."""
    if tool.startswith("vera_workspace_scissione_author_"):
        from native_aml_authoring import dispatch as author_dispatch

        try:
            return author_dispatch(tool, args, binding, loaded, root, api)
        except (ValueError, PermissionError) as error:
            raise type(error)(str(error).replace("AML", "Scissione")) from error
    if tool == "vera_workspace_scissione_setup":
        current = catalogue(root, binding, loaded, api)
        start = offset(args)
        return {
            "work_ref": binding["work_ref"],
            "label": loaded["run"]["label"],
            "items": current["rows"][start : start + 30],
            "total": len(current["rows"]),
            "offset": start,
            "has_more": start + 30 < len(current["rows"]),
        }
    current = read_prepared(root, binding, loaded, args, api)
    if args.get("revision") and current["revision"] != args["revision"]:
        raise ValueError("Stale Scissione version")
    selected = current["selection"]
    if not selected or selected["group"] != "record":
        raise ValueError("Choose one exact Scissione professional record")
    output = Path(loaded["output_dir"])
    ref = current["data"]["selection"]["source_ref"]
    scope = [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        binding,
        ref,
        args["item_id"],
        current["revision"],
    ]
    path = draft_path(output, binding, ref, args["item_id"], api)
    draft, stamp = draft_read(path, api)
    if stamp and draft["scope"] != scope:
        raise ValueError("Scissione draft belongs to another version or owner")
    if tool == "vera_workspace_scissione_draft_read":
        return {
            "fields": draft["fields"],
            "draft_revision": stamp,
            "interrupted": any(
                "result" not in api.read_json(p)
                for p in api.ui_state_directory(output, create=False).glob(
                    "scissione-request-*.json"
                )
            ),
        }
    if tool not in {
        "vera_workspace_scissione_draft_save",
        "vera_workspace_scissione_draft_clear",
        "vera_workspace_scissione_review",
    }:
        raise ValueError("Unknown Scissione action")
    with api.write_lock(output):
        loaded = api.load_binding(binding)
        current = read_prepared(root, binding, loaded, args, api)
        if args.get("revision") != current["revision"]:
            raise ValueError("Scissione run or exact revision changed before write")
        draft, stamp = draft_read(path, api)
        if stamp and draft["scope"] != scope:
            raise ValueError("Scissione draft owner changed")
        if tool == "vera_workspace_scissione_review":
            if args.get("human_reviewed") is not True:
                raise ValueError(
                    "Confirm the selected record and its exact dependencies"
                )
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid Scissione request key")
            receipt = api.ui_state_directory(output) / (
                "scissione-request-" + api.digest([scope[:2], key]) + ".json"
            )
            fingerprint = api.digest([tool, binding, scope[:2], args])
            if receipt.exists():
                saved = api.read_json(receipt)
                if saved["request_sha256"] != fingerprint:
                    raise ValueError("Scissione request key belongs to another review")
                if "result" not in saved:
                    raise ValueError(
                        "Interrupted Scissione review requires specialist recovery"
                    )
                outcome = read_record(
                    root, binding, loaded, saved["result"]["source_ref"], api
                )
                if outcome["previous_sha256"] != ref:
                    raise ValueError(
                        "Scissione retry outcome differs from the selected revision"
                    )
                return saved["result"]
        if (
            not current["data"]["can_review"]
            and tool != "vera_workspace_scissione_draft_clear"
        ):
            raise PermissionError(
                "Review requires the current Scissione version, running run and reviewer"
            )
        if tool == "vera_workspace_scissione_draft_clear" and (
            loaded["run"]["status"] != "running"
            or "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        ):
            raise PermissionError("Running run and reviewer required for draft discard")
        if (
            args["expected_checkpoint"] != current["data"]["decision_checkpoint"]
            or args["expected_draft_revision"] != stamp
        ):
            raise ValueError(
                "Scissione population or private draft changed; reload before writing"
            )
        if tool == "vera_workspace_scissione_draft_clear":
            path.unlink(missing_ok=True)
            return {"discarded": True, "draft_revision": ""}
        if tool == "vera_workspace_scissione_draft_save":
            fields = args["fields"]
            if (
                not isinstance(fields, dict)
                or not fields.keys() <= FIELDS
                or any(not isinstance(v, str) or len(v) > 4000 for v in fields.values())
            ):
                raise ValueError("Invalid Scissione review fields")
            saved = {"scope": scope, "fields": {**draft["fields"], **fields}}
            saved["draft_sha256"] = api.digest(saved)
            api.ui_state_directory(output)
            api.atomic_json(path, saved)
            return {"draft_saved": True, "draft_revision": saved["draft_sha256"]}
        if any(
            "result" not in api.read_json(p)
            for p in api.ui_state_directory(output, create=False).glob(
                "scissione-request-*.json"
            )
        ):
            raise ValueError(
                "Interrupted Scissione review requires specialist recovery; do not repeat"
            )
        if not FIELDS <= draft["fields"].keys() or any(
            not v.strip() for v in draft["fields"].values()
        ):
            raise ValueError("Complete all professional review fields")
        review = {
            "revision_sha256": ref,
            "record_ids": [selected["data"]["id"]],
            **draft["fields"],
        }
        staged = api.ui_state_directory(output) / (
            "scissione-review-" + api.digest(review) + ".json"
        )
        api.atomic_json(staged, review)
        request = {
            "context": str(loaded["context_path"]),
            "revision": ref,
            "request": str(staged),
        }
        expected = engine_call(root, {**request, "operation": "validate"})
        before = catalogue(root, binding, api.load_binding(binding), api)
        if before["checkpoint"] != current["data"]["decision_checkpoint"]:
            raise ValueError(
                "Scissione implementation, inputs or versions changed during validation"
            )
        official = output / ("native-scissione-review-" + fingerprint + ".json")
        if official.exists():
            raise ValueError(
                "Existing native Scissione request requires specialist recovery"
            )
        api.atomic_json(receipt, {"request_sha256": fingerprint})
        with official.open("x", encoding="utf-8") as stream:
            official.chmod(0o600)
            json.dump(review, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        response = engine_call(
            root, {**request, "request": str(official), "operation": "review"}
        )
        loaded = api.load_binding(binding)
        after = catalogue(root, binding, loaded, api)
        result_ref = response["revision_sha256"]
        produced = read_record(root, binding, loaded, result_ref, api)
        new_prefix = "scissione_versions/" + result_ref + "/"
        changed = {
            k: v
            for k, v in after["population"].items()
            if k.startswith(new_prefix) or k == "scissione_current.json"
        }
        if (
            after["implementation"] != before["implementation"]
            or after["population"] != {**before["population"], **changed}
            or after["current"] != result_ref
            or result_ref != expected["revision_sha256"]
            or produced["previous_sha256"] != ref
            or api.read_json(official) != review
        ):
            raise ValueError(
                "Scissione append differs from the reviewed version; specialist recovery required"
            )
        result = {
            "saved": True,
            "source_ref": result_ref,
            "status": produced["status"],
            "authenticated_signature": False,
            "run_completed": False,
        }
        api.atomic_json(receipt, {"request_sha256": fingerprint, "result": result})
        path.unlink(missing_ok=True)
        return result
