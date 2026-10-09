"""Explicit new registry runs from immutable prior workpapers and selected receipts.

Byte identities, receipt linkage and ownership are mechanical audit contracts.
Interpreting or rewriting requested changes remains model-led specialist work.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from native_archive_navigation import archive_module, engagement_scope, work_ref
from native_bank_preparation import file_hash, tree_hash
from native_sari_authoring import dispatch as author_dispatch
from native_sari_authoring import stamp
from native_sari_intake import bounded
from native_sari_intake import dispatch as intake_dispatch
from native_sari_intake import fields as intake_fields
from native_sari_review import snapshot as review_snapshot

__all__ = ["dispatch", "audit_run", "ensure_run_ready", "closure_audit"]


def closure_audit(core: Any, folder: Path, loaded: dict, api: Any) -> dict:
    """Use the closure's actual owned ledger without depending on dispatch capabilities."""

    def load_owned(binding: dict) -> dict:
        owned_folder, _ = engagement_scope(
            core, binding["client_id"], binding["engagement_id"]
        )
        if (
            owned_folder.resolve() != folder.resolve()
            or owned_folder.resolve() != Path(binding["client_root"]).resolve()
        ):
            raise PermissionError("Registry follow-up closure leaves its owned client")
        value = core.ledger.load_run(
            owned_folder, binding["engagement_id"], binding["run_id"]
        )
        if value["run"]["workflow_id"] != binding["workflow_id"]:
            raise PermissionError("Registry follow-up closure changes workflow")
        return value

    scoped = SimpleNamespace(
        read_json=api.read_json,
        ui_state_directory=api.ui_state_directory,
        load_binding=load_owned,
    )
    output = Path(loaded["output_dir"])
    marker_path = (
        api.ui_state_directory(output, create=False) / "sari-followup-origin.json"
    )
    if marker_path.exists():
        target = api.read_json(marker_path)["target"]
        if any(
            target[k] != loaded["run"][k]
            for k in ("client_id", "engagement_id", "run_id", "workflow_id")
        ) or target["work_ref"] != work_ref(
            target["client_id"], target["engagement_id"], target["run_id"]
        ):
            raise PermissionError("Registry follow-up closure names another run")
        load_owned(target)
        ensure_run_ready(target, loaded, scoped)
    return audit_run(output, scoped)


def audit_run(output: Path, api: Any) -> dict:
    """Incomplete successor creation is never silently retried or treated as conserved."""
    home = api.ui_state_directory(output, create=False)
    path = home / "sari-followup-operations.json"
    state = api.read_json(path) if path.exists() else {"operations": []}
    keys, known = set(), set()
    recovery = False
    for row in state["operations"]:
        reference = row["snapshot_ref"]
        if (
            row["key"] in keys
            or row["fingerprint"] != stamp(row["request"])
            or reference != "followup-" + stamp([row["request"], row["key"]])
            or reference in known
            or row["status"] not in {"pending", "complete"}
        ):
            raise ValueError("Registry follow-up operation identity changed")
        keys.add(row["key"])
        known.add(reference)
        recovery |= row["status"] == "pending"
        if row["status"] != "complete":
            continue
        receipt = row["receipt"]
        if (
            row["receipt_sha256"] != stamp(receipt)
            or tree_hash(home / "sari-followups" / reference) != receipt["preserved"]
        ):
            raise ValueError(
                "Registry follow-up receipt or preserved predecessor changed"
            )
        source, target = row["request"]["binding"], receipt["binding"]
        if target["run_id"] == source["run_id"] or any(
            source[k] != target[k]
            for k in ("client_id", "engagement_id", "workflow_id", "client_root")
        ):
            raise PermissionError(
                "Registry follow-up leaves its predecessor engagement"
            )
        loaded = api.load_binding(target)
        indexed = {r["binding_id"]: r for r in loaded["input_manifest"]["inputs"]}
        for identifier, expected in receipt["selected_input_hashes"].items():
            if identifier not in indexed or indexed[identifier]["sha256"] != expected:
                raise ValueError("Registry follow-up registered input receipt changed")
        marker = api.read_json(
            api.ui_state_directory(Path(loaded["output_dir"]), create=False)
            / "sari-followup-origin.json"
        )
        if marker != {
            "binding": source,
            "operation_key": row["key"],
            "target": target,
            "owner": row["request"]["owner"],
        }:
            raise ValueError("Registry follow-up origin differs from its receipt")
    recovery |= any(p.name not in known for p in (home / "sari-followups").glob("*"))
    return {"state": state, "recovery_required": recovery}


def ensure_run_ready(binding: dict, loaded: dict, api: Any) -> None:
    """A partially initialized child cannot escape its unresolved parent intent."""
    marker_path = (
        api.ui_state_directory(Path(loaded["output_dir"]), create=False)
        / "sari-followup-origin.json"
    )
    if not marker_path.exists():
        return
    marker = api.read_json(marker_path)
    if (
        marker["target"] != binding
        or marker["owner"][0] != os.environ["VERA_WORKSPACE_TENANT_ID"]
    ):
        raise PermissionError("Registry follow-up origin belongs to another scope")
    source = marker["binding"]
    if (
        any(
            source[k] != binding[k]
            for k in ("client_id", "engagement_id", "workflow_id", "client_root")
        )
        or source["run_id"] == binding["run_id"]
    ):
        raise PermissionError("Invalid registry follow-up predecessor")
    prior = api.load_binding(source)
    audited = audit_run(Path(prior["output_dir"]), api)
    row = next(
        (
            r
            for r in audited["state"]["operations"]
            if r["key"] == marker["operation_key"]
        ),
        None,
    )
    if (
        row is None
        or row["status"] != "complete"
        or row["receipt"]["binding"] != binding
    ):
        raise ValueError(
            "Registry follow-up creation is uncertain; ordinary recovery required"
        )


def snapshot(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    """Scope includes the whole displayed predecessor and engagement import population."""
    prior = review_snapshot(binding, loaded, root, api)
    own = audit_run(prior["output"], api)
    if api.configuration()["mode"] == "studio-archive":
        core = archive_module(api.module_root("studio-archive"))
        folder, engagement = engagement_scope(
            core, binding["client_id"], binding["engagement_id"]
        )
    else:
        # load_binding already selected the maintained ledger for this explicit pilot.
        import client_ledger

        core = SimpleNamespace(ledger=client_ledger)
        folder = Path(binding["client_root"])
        engagement = client_ledger.load_engagement_manifest(
            folder, binding["engagement_id"]
        )
    if folder.resolve() != Path(binding["client_root"]).resolve():
        raise PermissionError("Registry follow-up belongs to another client folder")
    imports = list(core.ledger.list_inputs(folder, binding["engagement_id"]))
    from native_archive_imports import audit_engagement

    import_audit = audit_engagement(core, folder, binding["engagement_id"])
    scope = {
        "prior": prior["scope"],
        "engagement": engagement,
        "imports": imports,
        "implementation": file_hash(Path(__file__)),
    }
    home = api.ui_state_directory(prior["output"], create=False)
    path = home / ("sari-followup-draft-" + stamp(prior["scope"]["owner"]) + ".json")
    draft = (
        api.read_json(path)
        if path.exists()
        else {
            "scope": scope,
            "generation": 0,
            "fields": {
                "question": "",
                "input_ids": [],
                "include_previous_outputs": False,
                "reference_date": "",
                "client_reference": "",
                "language": "it",
                "jurisdiction": "IT",
            },
        }
    )
    applied = (
        api.read_json(prior["output"] / "applied_decisions.json")
        if "applied_decisions.json" in prior["files"]
        else None
    )
    if applied and (
        applied["plugin"] != root.name
        or applied["run_id"] != binding["run_id"]
        or applied["review_payload_sha256"] != prior["public"]["review_sha256"]
    ):
        raise ValueError("Registry applied review belongs to another predecessor")
    recovery = (
        prior["recovery_required"]
        or own["recovery_required"]
        or import_audit["recovery_required"]
    )
    can_create = (
        api.configuration()["mode"] == "studio-archive"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and engagement["status"] == "open"
        and bool(applied)
        and not recovery
        and not prior["authoring_unfinished"]
        and loaded["run"]["status"] in {"running", "ready_for_review", "completed"}
    )
    return {
        **prior,
        "scope": scope,
        "revision": stamp(scope),
        "draft": draft,
        "draft_path": path,
        "draft_revision": stamp(draft),
        "draft_stale": draft["scope"] != scope,
        "state": own["state"],
        "imports": imports,
        "applied": applied,
        "recovery_required": recovery,
        "can_create": can_create,
    }


def fields(value: Any, current: dict, *, complete: bool = False) -> dict:
    """Literal source choices and public initial parameters; no inherited acceptance."""
    required = {
        "question",
        "input_ids",
        "include_previous_outputs",
        "reference_date",
        "client_reference",
        "language",
        "jurisdiction",
    }
    if (
        not isinstance(value, dict)
        or set(value) != required
        or not isinstance(value["question"], str)
        or len(value["question"]) > 4000
        or type(value["include_previous_outputs"]) is not bool
    ):
        raise ValueError("Invalid literal registry follow-up fields")
    intake_fields(
        {
            k: value[k]
            for k in ("reference_date", "client_reference", "language", "jurisdiction")
        },
        complete=complete,
    )
    chosen = value["input_ids"]
    if (
        not isinstance(chosen, list)
        or any(not isinstance(v, str) for v in chosen)
        or len(chosen) != len(set(chosen))
        or set(chosen) - {r["input_id"] for r in current["imports"]}
    ):
        raise PermissionError("Choose exact imported evidence from this engagement")
    if len(chosen) + len(current["files"]) + 1 > 1000:
        raise ValueError("Complete follow-up input population exceeds the Archive gate")
    if complete and (
        not value["question"].strip() or value["include_previous_outputs"] is not True
    ):
        raise PermissionError(
            "Confirm the actual question and the whole predecessor output snapshot"
        )
    return bounded(value, 100_000)


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Create, initialize and authorize a separate draft; never edit its predecessor."""
    if binding["workflow_id"] != root.name or root.name != "registro-imprese-sari":
        raise PermissionError("Registry follow-up belongs to another workflow")
    current = snapshot(binding, loaded, root, api)
    action = tool.removeprefix("vera_workspace_sari_followup_")
    base = {
        "work_ref": binding["work_ref"],
        "revision": current["revision"],
        "source_ref": current["public"]["review_sha256"] if current["public"] else "",
        "data": {
            "selection": {
                "source_ref": (
                    current["public"]["review_sha256"] if current["public"] else None
                )
            }
        },
        "run_status": loaded["run"]["status"],
        "can_create": current["can_create"],
        "recovery_required": current["recovery_required"],
        "fields": current["draft"]["fields"],
        "draft_revision": current["draft_revision"],
        "draft_stale": current["draft_stale"],
        "actual_model_reads_verified": False,
    }
    if action == "setup":
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid registry follow-up evidence page")
        return bounded(
            {
                **base,
                "rows": [
                    {
                        k: r[k]
                        for k in (
                            "input_id",
                            "original_name",
                            "role",
                            "byte_count",
                            "sha256",
                        )
                    }
                    for r in current["imports"][offset : offset + 30]
                ],
                "total": len(current["imports"]),
                "offset": offset,
                "has_more": offset + 30 < len(current["imports"]),
                "previous_files": [
                    {"name": name, "sha256": value}
                    for name, value in current["files"].items()
                ],
                "applied_review": current["applied"],
                "successors": [
                    r["receipt"]["result"]
                    for r in current["state"]["operations"]
                    if r["status"] == "complete"
                ],
            }
        )
    if action not in {"draft_save", "draft_clear", "create"}:
        raise ValueError("Unsupported registry follow-up action")
    if not current["can_create"]:
        raise PermissionError(
            "Registry follow-up requires owned open engagement, applied review and no uncertain writes"
        )
    request = {
        "owner": current["scope"]["prior"]["owner"],
        "binding": binding,
        "action": action,
        "args": args,
    }
    key = args.get("idempotency_key")
    if action == "create":
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", key):
            raise ValueError("Invalid registry follow-up operation key")
        old = next((r for r in current["state"]["operations"] if r["key"] == key), None)
        if old:
            if old["request"] != request or old["status"] != "complete":
                raise ValueError(
                    "Registry follow-up retry changed or has uncertain outcome"
                )
            return old["receipt"]["result"]
    if (
        args["revision"] != current["revision"]
        or args["source_ref"] != base["source_ref"]
        or args["expected_draft_revision"] != current["draft_revision"]
    ):
        raise ValueError("Registry predecessor, imports or draft changed; reopen")
    if action in {"draft_clear", "create"} and args.get("confirmed") is not True:
        raise PermissionError("Renew the explicit separate-run registry confirmation")
    selected = None
    if action in {"draft_save", "create"}:
        if current["draft_stale"]:
            raise ValueError(
                "Inspect and explicitly discard the stale follow-up fields"
            )
        selected = fields(args["fields"], current, complete=action == "create")
    if action == "create" and selected != current["draft"]["fields"]:
        raise ValueError("Authorize only the exact privately saved registry follow-up")
    with api.write_lock(current["output"]):
        fresh = snapshot(binding, api.load_binding(binding), root, api)
        if any(fresh[k] != current[k] for k in ("revision", "draft_revision", "state")):
            raise ValueError("Registry follow-up changed before conservation")
        if action in {"draft_save", "draft_clear"}:
            value = (
                selected
                if action == "draft_save"
                else {
                    "question": "",
                    "input_ids": [],
                    "include_previous_outputs": False,
                    "reference_date": "",
                    "client_reference": "",
                    "language": "it",
                    "jurisdiction": "IT",
                }
            )
            draft = {
                "scope": current["scope"],
                "generation": current["draft"]["generation"] + 1,
                "fields": value,
            }
            api.atomic_json(current["draft_path"], draft)
            return {
                "saved": True,
                "work_ref": binding["work_ref"],
                "draft_revision": stamp(draft),
                "fields": value,
                "status": "private_followup_saved",
            }
        reference = "followup-" + stamp([request, key])
        home = api.ui_state_directory(current["output"]) / "sari-followups"
        state = current["state"]
        row = {
            "key": key,
            "request": request,
            "fingerprint": stamp(request),
            "snapshot_ref": reference,
            "status": "pending",
        }
        state["operations"].append(row)
        bounded(state)
        ledger = (
            api.ui_state_directory(current["output"]) / "sari-followup-operations.json"
        )
        api.atomic_json(ledger, state)
        home.mkdir(mode=0o700, exist_ok=True)
        home.chmod(0o700)
        saved = home / reference
        saved.mkdir(mode=0o700)
        prior_dir = saved / "prior-outputs"
        shutil.copytree(current["output"], prior_dir)
        prior_dir.chmod(0o700)
        if tree_hash(prior_dir) != current["files"]:
            raise ValueError(
                "Registry predecessor changed during preservation; ordinary recovery required"
            )
        lineage = {
            "schema_version": "vera.native_sari_followup.v1",
            "owner": request["owner"],
            "predecessor": binding,
            "predecessor_run_status": loaded["run"]["status"],
            "predecessor_outputs": current["files"],
            "applied_review_sha256": current["files"]["applied_decisions.json"],
            "question": selected["question"],
            "professional_approvals_carried": False,
            "saved_choices_may_postdate_application": True,
            "actual_model_reads_verified": False,
        }
        core = archive_module(api.module_root("studio-archive"))
        folder, _ = engagement_scope(
            core, binding["client_id"], binding["engagement_id"]
        )
        imported = []
        history_inputs = []
        for path in sorted(p for p in prior_dir.rglob("*") if p.is_file()):
            receipt = core.ledger.import_document(
                folder,
                binding["client_id"],
                binding["engagement_id"],
                path.resolve(),
                "source",
            )["receipt"]
            imported.append((receipt["input_id"], file_hash(path)))
            history_inputs.append(
                {
                    "predecessor_relative_path": path.relative_to(prior_dir).as_posix(),
                    "input_id": receipt["input_id"],
                    "sha256": file_hash(path),
                }
            )
        lineage["history_inputs"] = history_inputs
        api.atomic_json(saved / "followup-lineage.json", lineage)
        receipt = core.ledger.import_document(
            folder,
            binding["client_id"],
            binding["engagement_id"],
            (saved / "followup-lineage.json").resolve(),
            "source",
        )["receipt"]
        imported.append(
            (receipt["input_id"], file_hash(saved / "followup-lineage.json"))
        )
        ids = list(dict.fromkeys([*selected["input_ids"], *[r[0] for r in imported]]))
        prepared = core.prepare_studio_client_workflow(
            binding["engagement_id"],
            root.name,
            input_ids=ids,
            label="Registro Imprese: seguito del riesame",
            purpose=selected["question"],
            idempotency_key="native-sari-followup-" + stamp([request["owner"], key]),
            new_run=True,
        )
        run_id = prepared["run"]["run_id"]
        target = {
            **binding,
            "run_id": run_id,
            "work_ref": work_ref(
                binding["client_id"], binding["engagement_id"], run_id
            ),
        }
        target_loaded = api.load_binding(target)
        api.atomic_json(
            api.ui_state_directory(Path(target_loaded["output_dir"]))
            / "sari-followup-origin.json",
            {
                "binding": binding,
                "operation_key": key,
                "target": target,
                "owner": request["owner"],
            },
        )
        core.start_studio_client_workflow(
            binding["client_id"], binding["engagement_id"], run_id
        )
        target_loaded = api.load_binding(target)
        initial = intake_dispatch(
            "vera_workspace_sari_setup", {}, target, target_loaded, root, api
        )
        initial_fields = {
            k: selected[k]
            for k in ("reference_date", "client_reference", "language", "jurisdiction")
        }
        private = intake_dispatch(
            "vera_workspace_sari_draft_save",
            {
                "revision": initial["revision"],
                "expected_draft_revision": initial["draft_revision"],
                "fields": initial_fields,
            },
            target,
            target_loaded,
            root,
            api,
        )
        intake_dispatch(
            "vera_workspace_sari_prepare",
            {
                "revision": initial["revision"],
                "expected_draft_revision": private["draft_revision"],
                "fields": initial_fields,
                "confirmed": True,
                "idempotency_key": "followup-initialize-"
                + stamp([request["owner"], key]),
            },
            target,
            target_loaded,
            root,
            api,
        )
        target_loaded = api.load_binding(target)
        author = author_dispatch(
            "vera_workspace_sari_author_setup", {}, target, target_loaded, root, api
        )
        question = {"question": selected["question"], "input_ids": ids}
        private = author_dispatch(
            "vera_workspace_sari_author_draft_save",
            {
                "revision": author["revision"],
                "expected_draft_revision": author["draft_revision"],
                "fields": question,
            },
            target,
            target_loaded,
            root,
            api,
        )
        grant = author_dispatch(
            "vera_workspace_sari_author_request",
            {
                "revision": author["revision"],
                "expected_draft_revision": private["draft_revision"],
                "fields": question,
                "confirmed": True,
                "idempotency_key": "followup-mandate-" + stamp([request["owner"], key]),
            },
            target,
            target_loaded,
            root,
            api,
        )
        hydrated = api.load_binding(target)
        indexed = {
            r["binding_id"]: r["sha256"] for r in hydrated["input_manifest"]["inputs"]
        }
        expected = {
            r["input_id"]: r["sha256"]
            for r in current["imports"]
            if r["input_id"] in selected["input_ids"]
        }
        expected.update(imported)
        if (
            indexed != expected
            or tree_hash(current["output"]) != current["files"]
            or api.load_binding(binding)["run"] != loaded["run"]
        ):
            raise ValueError(
                "Registry follow-up or predecessor differs from the confirmed conservation"
            )
        result = {
            "saved": True,
            "status": "registry_followup_mandate_registered",
            "work_ref": target["work_ref"],
            "run_id": run_id,
            "grant_ref": grant["grant_ref"],
            "previous_work_ref": binding["work_ref"],
            "professional_approvals_carried": False,
            "actual_model_reads_verified": False,
            "ready_to_file": False,
        }
        receipt = {
            "binding": target,
            "selected_input_hashes": expected,
            "preserved": tree_hash(saved),
            "result": result,
        }
        row.update(status="complete", receipt=receipt, receipt_sha256=stamp(receipt))
        api.atomic_json(ledger, state)
        return bounded(result)
