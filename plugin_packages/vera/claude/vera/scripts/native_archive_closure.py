"""Recoverable app declarations and exact maintained Archive run finalization."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_archive_navigation import (
    archive_module,
    engagement_scope,
    fingerprint,
    page,
    reviewer,
)
from native_bank_preparation import file_hash

__all__ = ["dispatch"]

FIELDS = {"artifact_id", "purpose", "audience", "media_type"}


def bridge(root: Path, request: dict) -> dict:
    """Use one fixed local helper; no model worker, provider or server request."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_archive_closure_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1]
            or "Archive disclosure validation refused"
        )
    return json.loads(result.stdout)


def snapshot(root: Path, args: dict, api: Any) -> dict:
    """Close exact receipts/bytes for auditability, without selecting deliverables semantically."""
    core = archive_module(root)
    folder, engagement = engagement_scope(
        core, args["client_id"], args["engagement_id"]
    )
    loaded = core.ledger.load_run(folder, args["engagement_id"], args["run_id"])
    run = loaded["run"]
    if run["workflow_id"] not in core.VERA_CLIENT_WORKFLOW_IDS:
        raise PermissionError("Workflow is outside the maintained Vera engagement gate")
    output = Path(loaded["output_dir"])
    authoring = None
    if run["workflow_id"] == "patent-box-review":
        from native_patent_box import audit_run as audit_patent_box
        from native_patent_box_authoring import audit_run as audit_patent_box_author

        patent_box = audit_patent_box(output, api)
        if patent_box["recovery_required"]:
            raise ValueError(
                "Patent Box operation requires ordinary recovery before closure"
            )
        authoring = {"patent_box_operations": patent_box["state"]}
        proposals = audit_patent_box_author(output, api)
        if proposals["unfinished"] or proposals["recovery_required"]:
            raise ValueError(
                "Patent Box model mandate requires disposition or recovery before closure"
            )
        authoring["patent_box_model_mandates"] = proposals["states"]
    if run["workflow_id"] == "bandi-agevolazioni":
        from native_bandi import audit_run as audit_bandi
        from native_bandi_authoring import audit_run as audit_bandi_authoring

        bandi = audit_bandi(output, api)
        if bandi["recovery_required"]:
            raise ValueError("Grant operation needs ordinary recovery before closure")
        proposals = audit_bandi_authoring(output, api)
        if proposals["pending"] or proposals["recovery_required"]:
            raise ValueError(
                "Grant contributions require explicit cancellation, disposition or ordinary recovery before closure"
            )
        authoring = {
            "bandi_operations": bandi["state"],
            "bandi_contributions": proposals["states"],
        }
    if run["workflow_id"] == "registro-imprese-sari":
        from native_sari_followup import closure_audit

        followup = closure_audit(core, folder, loaded, api)
        if followup["recovery_required"]:
            raise ValueError(
                "Registry follow-up requires ordinary recovery before closure"
            )
        from native_sari_intake import audit_run as audit_sari

        sari = audit_sari(output, api)
        if sari["recovery_required"]:
            raise ValueError(
                "Registry intake requires ordinary recovery before output closure"
            )
        from native_sari_authoring import audit_run as audit_sari_authoring

        proposals = audit_sari_authoring(output, api)
        if proposals["recovery_required"] or proposals["unfinished"]:
            raise ValueError(
                "Registry proposal requires recovery, registration or explicit cancellation before output closure"
            )
        from native_sari_review import audit_run as audit_sari_review

        review = audit_sari_review(output, api)
        if review["recovery_required"]:
            raise ValueError(
                "Registry public review requires ordinary recovery before output closure"
            )
        authoring = {
            "intake": sari["state"],
            "proposals": proposals["states"],
            "review": review["state"],
            "followup": followup["state"],
        }
    if run["workflow_id"] == "previdenza-inps":
        from native_inps import audit_run as audit_inps

        inps = audit_inps(output, api)
        if inps["recovery_required"]:
            raise ValueError(
                "INPS public review requires ordinary recovery before output closure"
            )
        authoring = inps["state"]
    if run["workflow_id"] == "esg-reporting-assurance":
        from native_esg_authoring import audit_run as audit_esg

        esg = audit_esg(output, api)
        if esg["pending"] or esg["recovery_required"]:
            raise ValueError(
                "ESG source preparation requires conservation/cancellation or recovery before closure"
            )
        authoring = esg["state"]
    if run["workflow_id"] == "composizione-negoziata":
        from native_cnc import audit_run as audit_cnc

        cnc = audit_cnc(output, api)
        if cnc["pending"] or cnc["recovery_required"]:
            raise ValueError(
                "CNC source preparation requires cancellation/conservation or recovery before output closure"
            )
        authoring = cnc["state"]
    if run["workflow_id"] == "variance-analysis":
        from native_variance import audit_run as audit_variance
        from native_variance_authoring import (
            audit_authoring as audit_variance_authoring,
        )
        from native_variance_review import audit_review as audit_variance_review

        variance_authoring = audit_variance_authoring(output, api)
        if variance_authoring["recovery_required"] or variance_authoring["pending"]:
            raise ValueError(
                "Variance comparison preparation requires recovery or a separately conserved/cancelled mandate before output closure"
            )
        authoring = variance_authoring["state"]
        professional = audit_variance_review(output, api)
        if professional["recovery_required"]:
            raise ValueError(
                "Variance professional conservation requires recovery before output closure"
            )
        from native_variance_narrative import audit_narrative

        narrative = audit_narrative(output, api)
        if narrative["recovery_required"] or narrative["pending"]:
            raise ValueError(
                "Variance notes require recovery or explicit named readback before output closure"
            )
        authoring = {
            "authoring": authoring,
            "professional": professional["requests"],
            "narrative": narrative["state"],
        }

        private = api.ui_state_directory(output, create=False)
        native_execution = (
            (private / "variance-state.json").exists()
            or any(private.glob("variance-request-*.json"))
            or any(
                re.fullmatch(r"variance-[a-f0-9]{64}", child.name)
                for child in output.iterdir()
            )
        )
        if native_execution and audit_variance(output, api)["recovery_required"]:
            raise ValueError(
                "Variance execution requires recovery before output closure"
            )
    if run["workflow_id"] == "management-control-pack":
        from native_management_authoring import (
            audit_authoring as audit_management_authoring,
        )
        from native_management_execution import audit_run as audit_management

        management_authoring = audit_management_authoring(output, api)
        if management_authoring["recovery_required"] or management_authoring["pending"]:
            raise ValueError(
                "Management case preparation requires recovery or a separately registered/cancelled mandate before output closure"
            )
        management = audit_management(output, api)
        if management["recovery_required"]:
            raise ValueError(
                "Management execution requires recovery before output closure"
            )
        from native_management_commentary import audit_commentary

        commentary = audit_commentary(output, api)
        if commentary["recovery_required"] or commentary["pending"]:
            raise ValueError(
                "Management commentary requires recovery or explicit complete named readback before output closure"
            )
        authoring = {
            "management_authoring": management_authoring["state"],
            "management_calculation": management["saved"],
            "management_commentary": commentary["state"],
        }
    if run["workflow_id"] == "business-valuation":
        from native_valuation import audit_run as audit_valuation
        from native_valuation_authoring import (
            audit_authoring as audit_valuation_authoring,
        )
        from native_valuation_review import audit_review as audit_valuation_review

        valuation_authoring = audit_valuation_authoring(output, api)

        if (
            audit_valuation(output, api)["recovery_required"]
            or audit_valuation_review(output, api)["recovery_required"]
            or valuation_authoring["recovery_required"]
        ):
            raise ValueError(
                "Valuation execution requires recovery before output closure"
            )
        if valuation_authoring["pending"]:
            raise ValueError(
                "Valuation authoring mandates require named case readback or explicit cancellation before output closure"
            )
    if run["workflow_id"] == "financial-analysis":
        from native_financial_execution import audit_run as audit_financial

        authoring = audit_financial(output, api)
        if authoring["recovery_required"]:
            raise ValueError(
                "Financial Analysis execution requires recovery before output closure"
            )
        if authoring["pending_authoring"]:
            raise ValueError(
                "Financial authoring mandates require exact case review or explicit cancellation before output closure"
            )
    if run["workflow_id"] == "centrale-rischi-review":
        from native_centrale_rischi import audit_run as audit_cr

        authoring = audit_cr(output, api)
        if authoring["recovery_required"]:
            raise ValueError("CR execution requires recovery before output closure")
    if run["workflow_id"] in {
        "aml-review",
        "adeguati-assetti",
        "scissione-guidata",
        "invoice-xml",
    }:
        from native_aml_authoring import audit_run

        authoring = audit_run(output, api, run["workflow_id"])
        if authoring["recovery_required"]:
            raise ValueError(
                "Assessment authoring requires recovery before output closure"
            )
    rows = []
    for p in core.ledger._output_files(output):
        name = p.relative_to(output).as_posix()
        size, sha = core.ledger._stable_file_identity(
            p, label="native closure artifact"
        )
        rows.append(
            {
                "id": "file:" + fingerprint([name, size, sha])[:32],
                "name": name,
                "byte_count": size,
                "sha256": sha,
                "path": str(p),
            }
        )
    if len(rows) > 10_000:
        raise ValueError("Output population exceeds native limit; use Studio Archive")
    report = bridge(
        root,
        {
            "operation": "report",
            "output": str(output),
            "run_id": run["run_id"],
            "workflow_id": run["workflow_id"],
        },
    )
    manifest_path = Path(loaded["run_root"]) / "artifact_manifest.json"
    manifest = None
    if run["status"] in {"ready_for_review", "completed"}:
        manifest = core.ledger.validate_run_artifacts(
            folder, args["engagement_id"], args["run_id"]
        )
    implementation = fingerprint(
        [
            bridge(root, {"operation": "implementation"}),
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_archive_closure_bridge.py")),
            file_hash(Path(__file__).with_name("native_archive_navigation.py")),
        ]
    )
    scope = fingerprint(
        [
            engagement,
            run,
            loaded["input_manifest"],
            rows,
            file_hash(manifest_path) if manifest_path.exists() else None,
            implementation,
            authoring,
        ]
    )
    return {
        "core": core,
        "folder": folder,
        "loaded": loaded,
        "output": output,
        "rows": rows,
        "report": report,
        "manifest": manifest,
        "implementation": implementation,
        "scope_revision": scope,
        "scope": [
            os.environ["VERA_WORKSPACE_ACTOR_ID"],
            os.environ["VERA_WORKSPACE_TENANT_ID"],
            run["client_id"],
            run["engagement_id"],
            run["run_id"],
        ],
        "engagement": engagement,
    }


def draft_path(current: dict, api: Any) -> Path:
    """Retain unfinished metadata outside the physical domain output population."""
    return api.ui_state_directory(current["output"], create=False) / (
        "closure-draft-" + fingerprint(current["scope"]) + ".json"
    )


def draft_read(current: dict, api: Any) -> tuple[dict, str]:
    path = draft_path(current, api)
    if path.is_symlink():
        raise ValueError("Archive declaration draft cannot use symbolic links")
    if not path.exists():
        return {"declarations": {}}, ""
    value = api.read_json(path)
    stamp = value["draft_sha256"]
    if value["scope"] != current["scope"] or stamp != fingerprint(
        {k: v for k, v in value.items() if k != "draft_sha256"}
    ):
        raise ValueError(
            "Archive declaration draft changed or belongs to another owner"
        )
    return value, stamp


def receipts(current: dict, api: Any) -> list[dict]:
    """An uncertain request remains explicit; the app does not adopt ledger writes."""
    return [
        api.read_json(p)
        for p in api.ui_state_directory(current["output"], create=False).glob(
            "closure-request-*.json"
        )
    ]


def projection(current: dict, args: dict, api: Any) -> dict:
    draft, stamp = draft_read(current, api)
    stale = bool(stamp and draft["scope_revision"] != current["scope_revision"])
    declarations = draft["declarations"] if not stale else {}
    sealed = (
        {r["path"]: {k: r[k] for k in FIELDS} for r in current["manifest"]["artifacts"]}
        if current["manifest"]
        else {}
    )
    shown = [
        {
            **{k: r[k] for k in ("id", "name", "byte_count", "path")},
            "declaration": sealed.get(r["name"], declarations.get(r["id"], {})),
        }
        for r in current["rows"]
    ]
    result = page(shown, args)
    run = current["loaded"]["run"]
    uncertain = any("result" not in r for r in receipts(current, api))
    return {
        **result,
        **{
            k: run[k]
            for k in (
                "client_id",
                "engagement_id",
                "run_id",
                "workflow_id",
                "label",
                "status",
            )
        },
        "scope_revision": current["scope_revision"],
        "draft_revision": stamp,
        "draft_stale": stale,
        "interrupted": uncertain,
        "report": current["report"],
        "can_declare": reviewer()
        and run["status"] == "running"
        and current["engagement"]["status"] == "open"
        and not uncertain,
        "can_complete": reviewer()
        and run["status"] == "ready_for_review"
        and current["engagement"]["status"] == "open"
        and current["report"]["valid"]
        and not uncertain,
        "declaration_count": len(declarations),
        "archive_completion_is_professional_approval": False,
    }


def dispatch(root: Path, tool: str, args: dict, api: Any) -> dict:
    """Keep recoverable proposals separate from both seal and explicit archival completion."""
    current = snapshot(root, args, api)
    if tool == "vera_workspace_archive_closure":
        return projection(current, args, api)
    if not reviewer() or args.get("confirmed") is not True:
        raise PermissionError("Explicit reviewer action required for Archive closure")
    with api.write_lock(current["output"]):
        current = snapshot(root, args, api)
        draft, stamp = draft_read(current, api)
        if tool in {
            "vera_workspace_archive_finalize",
            "vera_workspace_archive_complete",
        }:
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid archive closure request key")
            path = api.ui_state_directory(current["output"]) / (
                "closure-request-" + fingerprint([current["scope"][:2], key]) + ".json"
            )
            request_sha = fingerprint([tool, current["scope"], args])
            if path.exists():
                saved = api.read_json(path)
                if saved["request_sha256"] != request_sha:
                    raise ValueError("Archive closure key belongs to another request")
                if "result" not in saved:
                    raise ValueError(
                        "Interrupted archive closure requires specialist verification"
                    )
                if fingerprint(current["manifest"]) != saved[
                    "manifest_sha256"
                ] or current["loaded"]["run"]["status"] not in {
                    saved["result"]["status"],
                    "completed",
                }:
                    raise ValueError("Archive closure outcome changed; reopen the run")
                return saved["result"]
        if (
            args["scope_revision"] != current["scope_revision"]
            or args["expected_draft_revision"] != stamp
        ):
            raise ValueError(
                "Archive run, output population or private draft changed; reopen closure"
            )
        if tool == "vera_workspace_archive_discard":
            draft_path(current, api).unlink(missing_ok=True)
            return {"discarded": True, "draft_revision": ""}
        run = current["loaded"]["run"]
        if current["engagement"]["status"] != "open" or any(
            "result" not in r for r in receipts(current, api)
        ):
            raise ValueError(
                "Closed engagement or interrupted closure requires specialist verification"
            )
        if stamp and draft["scope_revision"] != current["scope_revision"]:
            raise ValueError(
                "Declaration draft is stale; explicitly discard before renewed review"
            )
        if tool == "vera_workspace_archive_declare":
            if run["status"] != "running":
                raise ValueError("Declarations require a running run")
            patches = args["declarations"]
            ids = {r["id"] for r in current["rows"]}
            if (
                not isinstance(patches, dict)
                or len(patches) > 30
                or not patches.keys() <= ids
            ):
                raise ValueError("Choose at most 30 exact output identities")
            merged = dict(draft["declarations"])
            for identity, fields in patches.items():
                if (
                    not isinstance(fields, dict)
                    or not fields.keys() <= FIELDS
                    or any(
                        not isinstance(v, str) or len(v) > 500 for v in fields.values()
                    )
                ):
                    raise ValueError("Invalid unfinished output declaration")
                merged[identity] = {**merged.get(identity, {}), **fields}
            value = {
                "scope": current["scope"],
                "scope_revision": current["scope_revision"],
                "declarations": merged,
            }
            value["draft_sha256"] = fingerprint(value)
            if len(json.dumps(value).encode()) > 2_000_000:
                raise ValueError(
                    "Declaration draft exceeds native limit; retain it and use Studio Archive"
                )
            api.ui_state_directory(current["output"])
            api.atomic_json(draft_path(current, api), value)
            return {"draft_saved": True, "draft_revision": value["draft_sha256"]}
        if (
            tool
            not in {
                "vera_workspace_archive_finalize",
                "vera_workspace_archive_complete",
            }
            or args.get("human_reviewed") is not True
        ):
            raise ValueError("Confirm the exact complete artifact population")
        if not current["report"]["valid"]:
            raise ValueError(
                "Prepare and validate this run's real model-data disclosure first"
            )
        core = current["core"]
        if tool == "vera_workspace_archive_finalize":
            if (
                run["status"] != "running"
                or not current["rows"]
                or set(draft["declarations"]) != {r["id"] for r in current["rows"]}
            ):
                raise ValueError("Declare every output of the running run")
            declarations = []
            for row in current["rows"]:
                data = {
                    **draft["declarations"][row["id"]],
                    "path": row["name"],
                    "byte_count": row["byte_count"],
                    "sha256": row["sha256"],
                }
                core.ledger._validate_artifact_record(data)
                declarations.append(
                    {k: v for k, v in data.items() if k not in {"byte_count", "sha256"}}
                )
            if len({r["artifact_id"] for r in declarations}) != len(declarations):
                raise ValueError("Output identities must be unique")
        elif run["status"] != "ready_for_review":
            raise ValueError("Review the sealed outputs before completing this run")
        if snapshot(root, args, api)["scope_revision"] != current["scope_revision"]:
            raise ValueError("Output population changed during closure validation")
        api.atomic_json(path, {"request_sha256": request_sha})
        ids = [run[k] for k in ("client_id", "engagement_id", "run_id")]
        if tool == "vera_workspace_archive_finalize":
            core.finalize_studio_client_workflow(*ids, declarations)
        else:
            core.complete_studio_client_workflow(*ids)
        after = snapshot(root, args, api)
        actual = {
            r["path"]: (r["byte_count"], r["sha256"])
            for r in after["manifest"]["artifacts"]
        }
        expected = {r["name"]: (r["byte_count"], r["sha256"]) for r in current["rows"]}
        status = (
            "ready_for_review"
            if tool == "vera_workspace_archive_finalize"
            else "completed"
        )
        if (
            actual != expected
            or after["implementation"] != current["implementation"]
            or after["loaded"]["input_manifest"] != current["loaded"]["input_manifest"]
            or after["loaded"]["run"]["status"] != status
            or not after["report"]["valid"]
        ):
            raise ValueError(
                "Sealed artifacts differ from reviewed bytes; specialist verification required"
            )
        result = {
            **{k: run[k] for k in ("client_id", "engagement_id", "run_id")},
            "status": after["loaded"]["run"]["status"],
            "professional_approval": False,
            "sent_or_published": False,
        }
        api.atomic_json(
            path,
            {
                "request_sha256": request_sha,
                "result": result,
                "manifest_sha256": fingerprint(after["manifest"]),
            },
        )
        draft_path(current, api).unlink(missing_ok=True)
        return result
