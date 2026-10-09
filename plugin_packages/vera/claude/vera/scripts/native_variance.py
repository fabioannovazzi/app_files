"""Optional owned variance intake and complete immutable public output inspection."""

from __future__ import annotations

import base64
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_sales_plan_authoring import owner_scope

__all__ = ["audit_run", "dispatch"]

FIELDS = {"source_input_id", "recipe_input_id", "currency", "language"}
LANGUAGES = {"it", "en", "fr", "de", "es"}


def engine_call(root: Path, request: dict) -> dict:
    """Isolate vendored runtime imports; timeout leaves a durable unresolved intent."""
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_variance_bridge.py")),
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
            completed.stderr.strip().splitlines()[-1] or "Variance refused"
        )
    return json.loads(completed.stdout)


def fields(value: dict, *, final: bool = False) -> dict:
    """Validate literal setup shape and ISO currency; no semantic mapping inference."""
    if set(value) != FIELDS or any(
        not isinstance(v, str) or len(v) > 200 for v in value.values()
    ):
        raise ValueError("Use complete literal variance setup fields")
    if final and (
        not all(value.values())
        or not re.fullmatch(r"[A-Z]{3}", value["currency"])
        or value["language"] not in LANGUAGES
    ):
        raise ValueError(
            "Select exact originals, recipe, reviewed currency and language"
        )
    return dict(value)


def selected(identity: str, loaded: dict) -> tuple[Path, dict]:
    """Permit only exact registered same-run receipts, never arbitrary file paths."""
    row = next(
        (r for r in loaded["input_manifest"]["inputs"] if r["binding_id"] == identity),
        None,
    )
    if row is None:
        raise PermissionError("Variance input is outside this run")
    path = Path(loaded["run_root"]) / row["execution_relative_path"]
    if file_hash(path) != row["sha256"]:
        raise ValueError("Variance input differs from its registered receipt")
    return path, row


def selection(value: dict, loaded: dict, api: Any) -> tuple[Path, Path, dict]:
    value = fields(value, final=True)
    source, _ = selected(value["source_input_id"], loaded)
    recipe, _ = selected(value["recipe_input_id"], loaded)
    if (
        source.suffix.lower() not in {".csv", ".tsv", ".psv", ".xlsx", ".xlsm"}
        or recipe.suffix.lower() != ".json"
    ):
        raise ValueError(
            "Select a supported variance original and registered JSON recipe"
        )
    payload = api.read_json(recipe)
    if not isinstance(payload.get("mappings"), dict):
        raise ValueError("Select the public variance recipe with explicit mappings")
    return source, recipe, payload


def audit_run(output: Path, api: Any) -> dict:
    """Uncertain exports and altered generations cannot be adopted or closed."""
    private = api.ui_state_directory(output, create=False)
    from native_variance_authoring import audit_authoring

    authoring = audit_authoring(output, api)
    from native_variance_review import audit_review

    professional = audit_review(output, api)
    from native_variance_narrative import audit_narrative

    narrative = audit_narrative(output, api)
    saved_path = private / "variance-state.json"
    saved = api.read_json(saved_path) if saved_path.exists() else None
    requests = [api.read_json(p) for p in private.glob("variance-request-*.json")]
    recovery = any("result" not in row for row in requests)
    known = saved["generation"] if saved else None
    if saved:
        if (
            not re.fullmatch(r"variance-[a-f0-9]{64}", known)
            or tree_hash(output / known) != saved["artifacts"]
        ):
            raise ValueError("Variance artifact bytes or population changed")
        recovery |= not any(
            row.get("result", {}).get("source_ref") == known for row in requests
        )
    recovery |= any(
        p.name != known and p.name not in authoring["intakes"]
        for p in output.glob("variance-*")
    )
    if not saved:
        recovery |= any(
            p.name not in authoring["intakes"] for p in output.iterdir()
        ) or bool(requests)
    return {
        "saved": saved,
        "private": private,
        "recovery_required": recovery
        or authoring["recovery_required"]
        or professional["recovery_required"]
        or narrative["recovery_required"],
        "authoring_present": bool(authoring["state"]["grants"]),
    }


def context(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    if binding["workflow_id"] != "variance-analysis":
        raise PermissionError("Variance belongs to another workflow")
    output = Path(loaded["output_dir"])
    current = audit_run(output, api)
    implementation = engine_call(root, {"operation": "contract"})
    implementation["native"] = {
        p.name: file_hash(p)
        for p in (Path(__file__), Path(__file__).with_name("native_variance_bridge.py"))
    }
    scope = {
        "owner": owner_scope(binding),
        "run": loaded["run"],
        "inputs": loaded["input_manifest"],
        "implementation": implementation,
    }
    if current["saved"]:
        if current["saved"]["implementation"] != implementation:
            raise ValueError("Variance public or native implementation changed")
        selection(current["saved"]["fields"], loaded, api)
    current.update(
        output=output,
        implementation=implementation,
        scope=scope,
        revision=api.digest([scope, current["saved"]]),
    )
    draft_path = current["private"] / (
        "variance-draft-" + api.digest(scope["owner"]) + ".json"
    )
    draft = api.read_json(draft_path) if draft_path.exists() else None
    if draft and draft["scope"] != scope:
        # Terminal lifecycle metadata may change after a sealed calculation.
        # Read-only consultation still requires the exact owner, inputs,
        # implementation and already-calculated choices; no draft is adopted.
        read_only_calculation = (
            loaded["run"]["status"] in {"ready_for_review", "completed"}
            and current["saved"] is not None
            and not current["recovery_required"]
            and draft["fields"] == current["saved"]["fields"]
            and {k: v for k, v in draft["scope"].items() if k != "run"}
            == {k: v for k, v in scope.items() if k != "run"}
        )
        if not read_only_calculation:
            raise ValueError("Variance unfinished draft belongs to a changed scope")
    current.update(
        draft_path=draft_path,
        draft=draft["fields"] if draft else dict.fromkeys(FIELDS, ""),
        draft_revision=api.digest(draft) if draft else "",
    )
    return current


def bounded(value: dict, maximum: int = 64000) -> dict:
    """Complete pages are refused when oversized; never silently truncate records."""
    if len(json.dumps(value, ensure_ascii=False).encode()) > maximum:
        raise ValueError(
            "Variance evidence exceeds the page limit; use retained specialist files"
        )
    return value


def offset(args: dict) -> int:
    value = args.get("offset", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Invalid variance page offset")
    return value


def directory(current: dict, args: dict) -> Path:
    if (
        current["recovery_required"]
        or not current["saved"]
        or args.get("source_ref") != current["saved"]["generation"]
    ):
        raise ValueError(
            "Choose the exact conserved variance generation or recover the interrupted execution"
        )
    return current["output"] / current["saved"]["generation"]


def artifact(folder: Path, name: str) -> Path:
    """Names must identify exact members of the verified sealed output tree."""
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Invalid variance artifact name")
    path = folder / name
    if (
        Path(name).is_absolute()
        or ".." in Path(name).parts
        or Path(name).as_posix() != name
        or not path.resolve().is_relative_to(folder.resolve())
        or not path.is_file()
    ):
        raise ValueError("Select an existing exact variance artifact")
    return path


def read_page(folder: Path, name: str, start: int, api: Any) -> dict:
    path = artifact(folder, name)
    if path.suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    elif path.suffix == ".json":
        value = api.read_json(path)
        rows = (
            value
            if isinstance(value, list)
            else [{"field": key, "value": item} for key, item in value.items()]
        )
    elif path.suffix == ".md":
        text = path.read_text(encoding="utf-8")
        if len(text.encode()) > 60000:
            raise ValueError(
                "Complete variance document exceeds the view limit; open the retained file"
            )
        rows = [{"document": text}]
    else:
        raise ValueError("Use exact CSV, JSON or Markdown evidence for discussion")
    return bounded(
        {
            "rows": rows[start : start + 20],
            "total": len(rows),
            "has_more": start + 20 < len(rows),
        }
    )


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Execute a confirmed registered recipe once, preserving normal rich outputs."""
    current = context(binding, loaded, root, api)
    writable = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    if tool == "vera_workspace_variance_setup":
        choices = [
            {
                "id": r["binding_id"],
                "name": Path(r["execution_relative_path"]).name,
                "suffix": Path(r["execution_relative_path"]).suffix.lower(),
            }
            for r in loaded["input_manifest"]["inputs"]
        ]
        start = offset(args)
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "label": loaded["run"]["label"],
                "status": (
                    "recovery_required"
                    if current["recovery_required"]
                    else (
                        "prepared"
                        if current["saved"]
                        else "authoring" if current["authoring_present"] else "ready"
                    )
                ),
                "can_prepare": writable
                and not current["saved"]
                and not current["authoring_present"]
                and not current["recovery_required"],
                "draft": current["draft"],
                "draft_revision": current["draft_revision"],
                "items": choices[start : start + 30],
                "total": len(choices),
                "has_more": start + 30 < len(choices),
                "source_ref": (
                    current["saved"]["generation"] if current["saved"] else None
                ),
                "professional_approval": False,
                "accounting_readiness": (
                    api.read_json(
                        current["output"]
                        / current["saved"]["generation"]
                        / "final_artifacts.json"
                    )["accounting_readiness"]
                    if current["saved"]
                    else None
                ),
                "run_completed": False,
            }
        )
    if tool == "vera_workspace_variance_prepare":
        if (
            not writable
            or args.get("confirmed") is not True
            or current["recovery_required"]
            or current["authoring_present"]
        ):
            raise PermissionError(
                "Confirmed owned running reviewer and unambiguous variance state are required"
            )
        value = fields(args["fields"], final=True)
        source, recipe, _ = selection(value, loaded, api)
        key = args["idempotency_key"]
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", key):
            raise ValueError("Invalid variance request identity")
        with api.write_lock(current["output"]):
            current = context(binding, api.load_binding(binding), root, api)
            fingerprint = api.digest([current["scope"], value])
            intent = current["private"] / (
                "variance-request-"
                + api.digest([current["scope"]["owner"], key])
                + ".json"
            )
            if intent.exists():
                previous = api.read_json(intent)
                if (
                    previous["request_sha256"] != fingerprint
                    or "result" not in previous
                ):
                    raise ValueError(
                        "Changed variance retry or uncertain export requires recovery"
                    )
                return previous["result"]
            if (
                current["saved"]
                or args["revision"] != current["revision"]
                or args["expected_draft_revision"] != current["draft_revision"]
                or value != current["draft"]
            ):
                raise ValueError(
                    "Variance choice or private draft changed; reopen the exact setup"
                )
            generation = "variance-" + fingerprint
            api.atomic_json(intent, {"request_sha256": fingerprint})
            output = current["output"] / generation
            generated = engine_call(
                root,
                {
                    "operation": "prepare",
                    "source": str(source),
                    "recipe": str(recipe),
                    "output": str(output),
                    "context": loaded["context_path"],
                    "currency": value["currency"],
                    "language": value["language"],
                    "node": api.node_executable(),
                },
            )
            result = {
                "work_ref": args["work_ref"],
                "saved": True,
                "status": generated["final_artifacts"]["status"],
                "source_ref": generation,
                "accounting_readiness": generated["final_artifacts"][
                    "accounting_readiness"
                ],
                "professional_approval": False,
                "run_completed": False,
                "review_payload_validated": generated["review_payload_validated"],
            }
            if (
                current["scope"]
                != context(binding, api.load_binding(binding), root, api)["scope"]
            ):
                raise ValueError(
                    "Variance scope changed during export; specialist recovery is required"
                )
            api.atomic_json(
                current["private"] / "variance-state.json",
                {
                    "fields": value,
                    "generation": generation,
                    "implementation": current["implementation"],
                    "artifacts": tree_hash(output),
                },
            )
            api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
            return result
    if args.get("revision") != current["revision"]:
        raise ValueError("Stale variance selection")
    if tool == "vera_workspace_variance_draft_save":
        if not writable or current["saved"] or current["recovery_required"]:
            raise PermissionError(
                "Variance draft requires an owned uncalculated running reviewer"
            )
        with api.write_lock(current["output"]):
            latest = context(binding, api.load_binding(binding), root, api)
            if (
                latest["revision"] != args["revision"]
                or latest["draft_revision"] != args["expected_draft_revision"]
            ):
                raise ValueError("Variance private draft changed concurrently")
            draft = {"scope": latest["scope"], "fields": fields(args["fields"])}
            api.atomic_json(latest["draft_path"], draft)
            return {
                "saved": True,
                "status": "draft_saved",
                "draft_revision": api.digest(draft),
            }
    if tool == "vera_workspace_variance_case":
        source, recipe, payload = selection(args["fields"], loaded, api)
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "draft_revision": current["draft_revision"],
                "fields": args["fields"],
                "recipe": payload,
                "original": {"name": source.name, "sha256": file_hash(source)},
                "recipe_identity": {"name": recipe.name, "sha256": file_hash(recipe)},
                "professional_approval": False,
            },
            2000000,
        )
    folder = directory(current, args)
    exact = {
        "work_ref": args["work_ref"],
        "revision": current["revision"],
        "source_ref": args["source_ref"],
        "professional_approval": False,
        "run_completed": False,
    }
    if tool == "vera_workspace_variance_outputs":
        return bounded(
            {
                **exact,
                "outputs": [
                    {"name": p.relative_to(folder).as_posix(), "path": str(p)}
                    for p in sorted(folder.rglob("*"))
                    if p.is_file()
                ],
            },
            2000000,
        )
    if tool == "vera_workspace_variance_asset":
        path = artifact(folder, args["artifact_name"])
        if path.suffix != ".png" or path.stat().st_size > 4000000:
            raise ValueError(
                "Open this exact retained file outside the bounded chart preview"
            )
        return {
            **exact,
            "image_url": "data:image/png;base64,"
            + base64.b64encode(path.read_bytes()).decode(),
            "artifact_name": args["artifact_name"],
        }
    if tool in {"vera_workspace_variance_read", "vera_workspace_variance_explain"}:
        page = read_page(folder, args["artifact_name"], offset(args), api)
        return {
            **exact,
            "artifact_name": args["artifact_name"],
            **page,
            "evidence_status": "untrusted_generated_evidence",
        }
    raise ValueError("Unknown native variance operation")
