"""Native exact-version invoice preparation, inspection and confirmed local export."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash

__all__ = ["dispatch", "read_prepared"]

REVIEW_FIELDS = {"reviewer", "reviewed_at", "approval_basis"}
DECISION_LABELS = {
    "source_grouping": "Documenti della fattura",
    "source_completeness": "Completezza e leggibilità delle fonti",
    "parties": "Fornitore e cliente",
    "document_type": "Tipo di documento",
    "tax_treatment": "Trattamento fiscale",
    "numbering_and_date": "Numero e data",
    "routing": "Recapito del file",
    "duplicate_and_issue_status": "Precedente emissione o esportazione",
    "operation_facts": "Operazione documentata",
    "date_basis": "Criterio della data",
    "original_invoice_reference": "Fattura originaria",
    "currency_conversion": "Conversione della valuta",
}


def engine(root: Path, request: dict) -> dict:
    """Use only the fixed isolated producer, offline validation and public persistence."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_invoice_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "Invoice producer refused"
        )
    return json.loads(result.stdout)


def bounded(value: dict, limit: int = 2_000_000) -> dict:
    if len(json.dumps(value).encode()) > limit:
        raise ValueError(
            "Invoice selection exceeds native limit; use the specialist route"
        )
    return value


def catalogue(root: Path, binding: dict, loaded: dict, api: Any) -> dict:
    """Hash exact physical populations for auditability; never select a latest invoice semantically."""
    if binding["workflow_id"] != "invoice-xml" or root.name != "invoice-xml":
        raise PermissionError("Invoice belongs to another workflow")
    output = Path(loaded["output_dir"])
    population = tree_hash(output)
    if len(population) > 10_000:
        raise ValueError("Invoice output population exceeds native limit")
    rows = []
    for path in sorted(output.glob("draft-*")):
        match = re.fullmatch(r"draft-([0-9a-f]{64})", path.name)
        if match is None or not path.is_dir() or path.is_symlink():
            raise ValueError("Unknown invoice revision requires specialist recovery")
        rows.append({"id": match[1], "title": path.name, "prepared": True})
    candidate = None
    if (output / "proposal.json").exists():
        value = engine(
            root, {"operation": "candidate", "context": str(loaded["context_path"])}
        )
        candidate = {
            "id": value["proposal_sha256"],
            "status": value["validation"]["status"],
            "field_count": value["validation"]["field_count"],
            "issue_count": len(value["validation"]["issues"]),
            "prepared": value["proposal_sha256"] in {r["id"] for r in rows},
        }
    implementation = api.digest(
        [
            engine(root, {"operation": "implementation"}),
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_invoice_bridge.py")),
        ]
    )
    from native_aml_authoring import audit_run

    authoring = audit_run(output, api, "invoice-xml")
    checkpoint = api.digest(
        [loaded["run"], loaded["input_manifest"], population, implementation, authoring]
    )
    return {
        "rows": rows,
        "candidate": candidate,
        "population": population,
        "implementation": implementation,
        "checkpoint": checkpoint,
        "authoring": authoring,
    }


def record(root: Path, loaded: dict, identity: str) -> dict:
    return engine(
        root,
        {
            "operation": "read",
            "context": str(loaded["context_path"]),
            "proposal_sha256": identity,
        },
    )


def items(value: dict, api: Any) -> list[dict]:
    """Follow exact public JSON pointers and authored references, without interpreting support."""
    proposal = value["proposal"]
    sources = {r["id"]: r for r in proposal["sources"]}

    def references(rows: list) -> list:
        return [
            {
                "locator": r["locator"],
                **{
                    k: sources[r["source_id"]][k]
                    for k in ("id", "title", "path", "role", "evidence_group")
                },
            }
            for r in rows
        ]

    rows = []
    for pointer, text in value["fields"].items():
        evidence = proposal["field_evidence"].get(pointer, {})
        rows.append(
            {
                "group": "fields",
                "key": pointer,
                "title": pointer,
                "data": {
                    "value": text,
                    "basis": evidence.get("basis"),
                    "kind": evidence.get("kind"),
                    "uncertain": evidence.get("uncertain"),
                    "operands": evidence.get("operands", []),
                },
                "evidence": references(evidence.get("references", [])),
            }
        )
    for key, decision in proposal["decisions"].items():
        rows.append(
            {
                "group": "decisions",
                "key": key,
                "title": DECISION_LABELS.get(key, key),
                "data": {"assessment": decision["assessment"]},
                "evidence": references(decision["references"]),
            }
        )
    for index, issue in enumerate(value["validation"]["issues"]):
        rows.append(
            {
                "group": "issues",
                "key": str(index),
                "title": issue,
                "data": {"issue": issue},
                "evidence": [],
            }
        )
    for row in rows:
        row["id"] = (
            "invoice:"
            + api.digest([value["proposal_sha256"], row["group"], row["key"]])[:32]
        )
    return rows


def read_prepared(
    root: Path, binding: dict, loaded: dict, args: dict, api: Any
) -> dict:
    current = catalogue(root, binding, loaded, api)
    if args.get("revision") and args["revision"] != current["checkpoint"]:
        raise ValueError("Invoice sources or artifacts changed; reopen exact revision")
    identity = args.get("source_ref")
    if identity not in {r["id"] for r in current["rows"]}:
        raise ValueError("Choose an exact prepared invoice revision")
    value = record(root, loaded, identity)
    rows = items(value, api)
    offset = args.get("offset", 0)
    if type(offset) is not int or offset < 0:
        raise ValueError("Invalid invoice page offset")
    selected = next((r for r in rows if r["id"] == args.get("item_id")), None)
    if args.get("item_id") and selected is None:
        raise ValueError("Invoice selection belongs to another exact revision")
    return bounded(
        {
            "revision": current["checkpoint"],
            "items": [
                {k: r[k] for k in ("id", "group", "title")}
                for r in rows[offset : offset + 30]
            ],
            "total": len(rows),
            "selection": selected,
            "data": {
                "selection": {"source_ref": identity},
                "validation": value["validation"],
                "export": value["export"],
                "review": value["review"],
                "artifacts": [
                    name
                    for name in current["population"]
                    if name.startswith("draft-" + identity + "/")
                ],
                "route": value["proposal"]["route"],
                "transmission_mode": value["proposal"]["transmission_mode"],
                "source_count": len(value["proposal"]["sources"]),
            },
        }
    )


def private_scope(binding: dict) -> list:
    return [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        *[binding[k] for k in ("client_id", "engagement_id", "run_id")],
    ]


def draft_path(output: Path, binding: dict, identity: str, api: Any) -> Path:
    return api.ui_state_directory(output, create=False) / (
        "invoice-draft-" + api.digest([private_scope(binding), identity]) + ".json"
    )


def read_draft(
    output: Path, binding: dict, identity: str, current: dict, api: Any
) -> dict:
    path = draft_path(output, binding, identity, api)
    if path.is_symlink():
        raise ValueError("Invoice draft cannot use symbolic links")
    if not path.exists():
        return {"fields": {}, "draft_revision": "", "stale": False}
    saved = api.read_json(path)
    if saved["scope"] != [private_scope(binding), identity] or saved[
        "draft_revision"
    ] != api.digest({k: v for k, v in saved.items() if k != "draft_revision"}):
        raise ValueError("Invoice draft changed or belongs to another owner")
    stale = saved["revision"] != current["checkpoint"]
    return {
        "fields": {} if stale else saved["fields"],
        "draft_revision": saved["draft_revision"],
        "stale": stale,
    }


def uncertain(output: Path, api: Any) -> bool:
    return any(
        "result" not in api.read_json(p)
        for p in api.ui_state_directory(output, create=False).glob(
            "invoice-request-*.json"
        )
    )


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Keep draft attribution, exact local export and run completion distinct."""
    if tool.startswith("vera_workspace_invoice_author_"):
        if tool == "vera_workspace_invoice_author_evidence":
            from native_invoice_authoring import dispatch_evidence

            return dispatch_evidence(args, binding, loaded, root, api)
        from native_aml_authoring import dispatch as author_dispatch

        try:
            return author_dispatch(tool, args, binding, loaded, root, api)
        except (ValueError, PermissionError) as error:
            raise type(error)(str(error).replace("AML", "Invoice")) from error
    output = Path(loaded["output_dir"])
    current = catalogue(root, binding, loaded, api)
    identity = args.get("source_ref")
    if tool == "vera_workspace_invoice_setup":
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid invoice page offset")
        shown = []
        for row in current["rows"][offset : offset + 30]:
            value = record(root, loaded, row["id"])
            bodies = value["proposal"]["invoice"].get("FatturaElettronicaBody", [])
            bodies = bodies if isinstance(bodies, list) else [bodies]
            title = ", ".join(
                str(
                    b.get("DatiGenerali", {})
                    .get("DatiGeneraliDocumento", {})
                    .get("Numero")
                    or "Numero da completare"
                )
                for b in bodies
            )
            shown.append(
                {
                    **row,
                    "title": title,
                    "status": value["validation"]["status"],
                    "exported": bool(value["export"]),
                }
            )
        chosen = (
            record(root, loaded, identity)
            if identity in {r["id"] for r in current["rows"]}
            else None
        )
        if identity and chosen is None:
            raise ValueError("Choose an exact prepared invoice")
        result = {
            "work_ref": binding["work_ref"],
            "workflow": "invoice-xml",
            "kind": "invoice",
            "revision": current["checkpoint"],
            "candidate": current["candidate"],
            "items": shown,
            "total": len(current["rows"]),
            "offset": offset,
            "has_more": offset + 30 < len(current["rows"]),
            "run_status": loaded["run"]["status"],
            "interrupted": uncertain(output, api)
            or current["authoring"]["recovery_required"],
            "data": {
                "selection": {"source_ref": identity},
                "validation": chosen["validation"] if chosen else None,
                "export": chosen["export"] if chosen else None,
                "review": chosen["review"] if chosen else None,
            },
        }
        if identity:
            result["draft"] = read_draft(output, binding, identity, current, api)
        writable = (
            loaded["run"]["status"] == "running"
            and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
            and not result["interrupted"]
        )
        result["can_prepare"] = writable and bool(current["candidate"])
        result["can_export"] = writable and bool(chosen) and not chosen["export"]
        return bounded(result)
    if tool == "vera_workspace_invoice_explain":
        result = read_prepared(root, binding, loaded, args, api)
        if result["selection"] is None:
            raise ValueError("Choose one exact invoice field or decision")
        return bounded(
            {
                "selection": result["selection"],
                "route": result["data"]["route"],
                "sdi_acceptance": "not_tested",
                "reviewer_authentication": "not_authenticated",
            },
            64_000,
        )
    if "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","):
        raise PermissionError("Configured reviewer action required for invoice writes")
    with api.write_lock(output):
        loaded = api.load_binding(binding)
        current = catalogue(root, binding, loaded, api)
        if loaded["run"]["status"] != "running":
            raise ValueError("Invoice writes require a running run")
        action = tool in {
            "vera_workspace_invoice_prepare",
            "vera_workspace_invoice_export",
        }
        if action:
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid invoice request key")
            path = api.ui_state_directory(output) / (
                "invoice-request-" + api.digest([private_scope(binding), key]) + ".json"
            )
            request_sha = api.digest([tool, private_scope(binding), args])
            if path.exists():
                saved = api.read_json(path)
                if saved["request_sha256"] != request_sha:
                    raise ValueError("Invoice key belongs to another request")
                if "result" not in saved:
                    raise ValueError(
                        "Interrupted invoice write requires specialist verification"
                    )
                if (
                    saved["population"] != api.digest(current["population"])
                    or saved["implementation"] != current["implementation"]
                ):
                    raise ValueError("Invoice outcome changed; reopen the run")
                return saved["result"]
        if args["revision"] != current["checkpoint"]:
            raise ValueError("Invoice source or output population changed; reopen")
        if uncertain(output, api) or current["authoring"]["recovery_required"]:
            raise ValueError(
                "Interrupted invoice write requires specialist verification"
            )
        draft = (
            read_draft(output, binding, identity, current, api) if identity else None
        )
        if (
            draft is not None
            and args["expected_draft_revision"] != draft["draft_revision"]
        ):
            raise ValueError("Invoice review draft changed concurrently")
        if (
            identity not in {r["id"] for r in current["rows"]}
            and tool != "vera_workspace_invoice_prepare"
        ):
            raise ValueError("Invoice revision does not belong to this run")
        if tool == "vera_workspace_invoice_draft_clear":
            draft_path(output, binding, identity, api).unlink(missing_ok=True)
            return {"discarded": True, "draft_revision": ""}
        if draft and draft["stale"]:
            raise ValueError(
                "Invoice review draft is stale; discard explicitly or use specialist recovery"
            )
        if tool == "vera_workspace_invoice_draft_save":
            if record(root, loaded, identity)["export"]:
                raise ValueError(
                    "Invoice already exported; inspect the existing review"
                )
            fields = args["fields"]
            if (
                not isinstance(fields, dict)
                or not fields.keys() <= REVIEW_FIELDS
                or any(not isinstance(v, str) or len(v) > 4000 for v in fields.values())
            ):
                raise ValueError("Invalid unfinished invoice attribution")
            value = {
                "scope": [private_scope(binding), identity],
                "revision": current["checkpoint"],
                "fields": {**draft["fields"], **fields},
            }
            value["draft_revision"] = api.digest(value)
            api.ui_state_directory(output)
            api.atomic_json(draft_path(output, binding, identity, api), value)
            return {"draft_saved": True, "draft_revision": value["draft_revision"]}
        if not action or args.get("human_reviewed") is not True:
            raise ValueError("Confirm the exact invoice action")
        request = {"context": str(loaded["context_path"])}
        if tool == "vera_workspace_invoice_prepare":
            identity = args["candidate_ref"]
            if not current["candidate"] or current["candidate"]["id"] != identity:
                raise ValueError("Invoice candidate changed or is missing")
            engine(
                root, {**request, "operation": "candidate", "proposal_sha256": identity}
            )
            operation = "prepare"
        else:
            fields = args["review"]
            if (
                not isinstance(fields, dict)
                or set(fields) != REVIEW_FIELDS
                or any(
                    not isinstance(v, str) or not v.strip() or len(v) > 4000
                    for v in fields.values()
                )
            ):
                raise ValueError(
                    "Provide complete actual professional attribution and approval reference"
                )
            if record(root, loaded, identity)["export"]:
                raise ValueError(
                    "Invoice already exported; inspect the existing exact review"
                )
            request["review"] = {
                "schema_version": 1,
                "proposal_sha256": identity,
                "status": "approved_for_export",
                **fields,
            }
            engine(
                root,
                {**request, "operation": "check_export", "proposal_sha256": identity},
            )
            operation = "export"
        if (
            catalogue(root, binding, api.load_binding(binding), api)["checkpoint"]
            != current["checkpoint"]
        ):
            raise ValueError("Invoice changed during action validation")
        api.atomic_json(path, {"request_sha256": request_sha})
        result = engine(
            root, {**request, "operation": operation, "proposal_sha256": identity}
        )
        after_loaded = api.load_binding(binding)
        after = catalogue(root, binding, after_loaded, api)
        verified = record(root, loaded, identity)
        prefix = "draft-" + identity + ("/export/" if operation == "export" else "/")
        expected_added = (
            {
                prefix + name
                for name in (
                    "review.json",
                    "export_report.json",
                    verified["export"]["xml_path"],
                )
            }
            if operation == "export"
            else {
                prefix + name
                for name in (
                    "proposal.json",
                    "validation.json",
                    "preview.html",
                    "review_request.json",
                )
            }
        )
        if (
            any(
                after["population"].get(name) != sha
                for name, sha in current["population"].items()
            )
            or not set(after["population"]) - set(current["population"])
            <= expected_added
            or after["implementation"] != current["implementation"]
            or after_loaded["run"] != loaded["run"]
            or after_loaded["input_manifest"] != loaded["input_manifest"]
            or result["proposal_sha256"] != identity
        ):
            raise ValueError(
                "Invoice artifacts differ from reviewed state; specialist verification required"
            )
        outcome = {
            "status": (
                "exported_for_operator"
                if operation == "export"
                else verified["validation"]["status"]
            ),
            "source_ref": identity,
            "sdi_acceptance": "not_tested",
            "signed": False,
            "sent_or_published": False,
            "run_completed": False,
        }
        api.atomic_json(
            path,
            {
                "request_sha256": request_sha,
                "result": outcome,
                "population": api.digest(after["population"]),
                "implementation": after["implementation"],
            },
        )
        if operation == "export":
            draft_path(output, binding, identity, api).unlink(missing_ok=True)
        return outcome
