"""Authorised native projections over existing Studio Archive workflow stores."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

__all__ = ["dispatch", "module_root"]

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2_000_000
MAX_RECORD_BYTES = 8_000_000  # Archive's existing bounded 5,000-file contract.
REVIEW_FILES = (
    "run_intake.json",
    "review_payload.json",
    "ui_decisions.json",
    "applied_decisions.json",
    "final_artifacts.json",
    "treasury_session.json",
    "model_review_context.json",
    "archive_plan.json",
    "approved_plan.json",
    "apply_journal.json",
    "model_handoff.json",
    "review_integrity.json",
    "assurance_envelope.json",
    "workflow_output_closure.json",
)
REVIEW_SUBDIRECTORIES = {
    "journal-bank-reconciliation": "reconciliation",
    "journal-sampling": "sample",
    "check-entries": "checks",
    "open-item-reconciliation": "reconciliation",
    "client-file-preparation": "intake",
    "report-builder": "report",
    "concordato-plan-review": "reviewed-output",
}


def module_root(component: str) -> Path:
    """Use the same sibling/module layout as Vera's component launcher."""
    registered = read_json(ROOT / "components.json")["plugins"]
    if component not in registered:
        raise ValueError("Unregistered workflow")
    packaged = ROOT / "modules" / component
    return packaged if packaged.is_dir() else ROOT.parent / component


def read_json(path: Path) -> dict[str, Any]:
    """Reject linked, oversized or non-object records before inspecting them."""
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_nlink != 1
        or path.stat().st_size > MAX_RECORD_BYTES
    ):
        raise ValueError(f"Unavailable or oversized record: {path.name}")
    result = json.loads(path.read_bytes())
    if not isinstance(result, dict):
        raise ValueError(f"Expected an object: {path.name}")
    return result


def digest(value: Any) -> str:
    """Exact content binding is mechanical, not a professional judgment."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def configuration() -> dict[str, Any]:
    """Use operator bindings or the maintained archive's owned local session."""
    configured = os.environ.get("VERA_WORKSPACE_BINDINGS", "")
    if not configured:
        identity = {
            field: os.environ.get("VERA_WORKSPACE_" + field.upper(), "")
            for field in ("tenant_id", "actor_id")
        }
        if not all(identity.values()):
            raise ValueError("Open the workspace through its local MCP service")
        return {**identity, "mode": "studio-archive", "bindings": []}
    value = read_json(Path(configured))
    value["mode"] = "operator-bindings"
    for field in ("tenant_id", "actor_id"):
        expected = os.environ.get("VERA_WORKSPACE_" + field.upper(), "")
        if not expected or value[field] != expected:
            raise PermissionError(
                "Workspace configuration does not belong to this configured host actor"
            )
    bindings = value["bindings"]
    if not isinstance(bindings, list) or len(bindings) > 200:
        raise ValueError("Workspace contains at most 200 run references")
    refs = [item["work_ref"] for item in bindings]
    if len(set(refs)) != len(refs) or any(
        not re.fullmatch(r"[a-zA-Z0-9_-]{1,120}", ref) for ref in refs
    ):
        raise ValueError("Workspace references must be unique bounded identifiers")
    return value


def load_binding(binding: dict[str, Any]) -> dict[str, Any]:
    """Replay the existing ledger, including all source receipts, every time."""
    scripts = module_root("studio-archive") / "scripts"
    sys.path.insert(0, str(scripts))
    from client_ledger import load_run

    loaded = load_run(
        Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
    )
    run = loaded["run"]
    if (
        run["client_id"] != binding["client_id"]
        or run["workflow_id"] != binding["workflow_id"]
    ):
        raise PermissionError("Run belongs to a different client or workflow")
    component = binding.get("component", binding["workflow_id"])
    expected = component
    if expected != binding["workflow_id"]:
        raise PermissionError("Component does not own this workflow")
    if component == "bilancio-xbrl-it":
        legacy = read_json(Path(os.environ["VERA_XBRL_WORKSPACE_BINDINGS"]))
        old = next(
            (row for row in legacy["bindings"] if row["case_id"] == binding["case_id"]),
            None,
        )
        if old is None or any(
            old[key] != binding[key]
            for key in ("client_id", "client_root", "engagement_id", "run_id")
        ):
            raise PermissionError("Bilancio case is bound to another archive run")
    return loaded


def connect_bilancio_binding(binding: dict[str, Any]) -> dict[str, Any]:
    """Join an owned archive run to its independently authorized case reference."""
    configured = os.environ.get("VERA_XBRL_WORKSPACE_BINDINGS", "")
    if not configured:
        raise PermissionError("Bilancio requires its canonical case connection")
    path = Path(configured)
    cases = read_json(path)
    if path.stat().st_size > 128_000:
        raise ValueError("Bilancio connection exceeds its bounded host contract")
    for field in ("tenant_id", "actor_id"):
        owner = os.environ.get("VERA_WORKSPACE_" + field.upper(), "")
        canonical = os.environ.get("VERA_XBRL_" + field.upper(), "")
        if not owner or canonical != owner or cases[field] != owner:
            raise PermissionError("Bilancio connection belongs to another actor")
    rows = cases["bindings"]
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError("Bilancio connection contains at most 200 references")
    matches = [
        row
        for row in rows
        if all(
            row[key] == binding[key]
            for key in ("client_root", "client_id", "engagement_id", "run_id")
        )
    ]
    if len(matches) != 1:
        raise PermissionError("Bilancio needs one exact authorized case connection")
    connected = {**binding, "case_id": matches[0]["case_id"]}
    load_binding(connected)
    # The case service still authorizes the actual case, not just its directory.
    bilancio_call(
        "xbrl_workspace_view",
        {"case_id": connected["case_id"], "view": "CASE_DASHBOARD"},
    )
    return connected


def workbench_module() -> Any:
    """Reuse the maintained local review adapter in source and generated packages."""
    path = ROOT / "scripts" / "serve_review_workbench.py"
    if not path.exists():
        path = ROOT.parents[1] / "scripts" / "serve_review_workbench.py"
    spec = importlib.util.spec_from_file_location("vera_native_workbench", path)
    if spec is None or spec.loader is None:
        raise ValueError("Shared review adapter is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def review_directory(output: Path, component: str) -> Path:
    """Resolve only the workflow's fixed review location, never a UI path."""
    candidates = [output]
    if component in REVIEW_SUBDIRECTORIES:
        candidates.append(output / REVIEW_SUBDIRECTORIES[component])
    for directory in candidates:
        if any(parent.is_symlink() for parent in (directory, *directory.parents)):
            raise ValueError("Review directories cannot use symbolic links")
    available = [p for p in candidates if (p / "review_payload.json").exists()]
    if len(available) > 1:
        raise ValueError("Ambiguous review location; resolve the workflow run first")
    return available[0] if available else candidates[-1]


def output_revision(output: Path, component: str = "") -> str:
    """Detect changes to review state without introducing a second review store."""
    values = {}
    review = review_directory(output, component)
    for directory in dict.fromkeys((output, review)):
        for name in REVIEW_FILES:
            path = directory / name
            if path.exists():
                read_json(path)
                values[path.relative_to(output).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    if component == "client-file-preparation":
        _, _, pages = file_preparation_handoff(review)
        values.update(pages)
    if component == "report-builder":
        path = review / "report_analysis.json"
        read_json(path)
        values[path.relative_to(output).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    if component == "open-item-reconciliation":
        for name in (
            "run_manifest.json",
            "assurance_receipts.json",
            "professional_review.json",
        ):
            path = review / name
            if path.exists():
                read_json(path)
                values[path.relative_to(output).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    return digest(values)


def file_preparation_handoff(
    directory: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    """Verify every maintained model page, without substituting raw UI previews."""
    context = read_json(directory / "model_handoff.json")
    review = read_json(directory / "review_payload.json")
    if (
        context["artifact"] != "client_file_preparation_model_handoff"
        or context["schema_version"] != "1.0"
        or context["run_id"] != review["run_id"]
    ):
        raise ValueError("Model handoff does not belong to this review")
    pagination = context["pagination"]
    records, fingerprints = [], {}
    if pagination["page_count"] != len(pagination["pages"]):
        raise ValueError("Incomplete model handoff page manifest")
    for index, entry in enumerate(pagination["pages"], start=1):
        relative = entry["path"]
        if not re.fullmatch(r"model_handoff_pages/page-\d{4,8}\.json", relative):
            raise ValueError("Unregistered model handoff page path")
        path = directory / relative
        if path.parent.is_symlink():
            raise ValueError("Model handoff pages cannot use symbolic links")
        page = read_json(path)
        content = path.read_bytes()
        fingerprint = hashlib.sha256(content).hexdigest()
        if (
            len(content) > 1_500_000
            or len(content) != entry["size_bytes"]
            or fingerprint != entry["sha256"]
            or page["run_id"] != context["run_id"]
            or page["schema_version"] != context["schema_version"]
            or page["page_number"] != index
            or entry["page_number"] != index
            or entry["item_offset"] != len(records)
            or entry["item_count"] != len(page["items"])
            or len(page["items"]) > 2_500
            or relative in fingerprints
        ):
            raise ValueError("Model handoff page identity or content changed")
        fingerprints[relative] = fingerprint
        records.extend(page["items"])
    if len(records) != pagination["item_count"]:
        raise ValueError("Incomplete model handoff population")
    return context, records, fingerprints


def file_preparation_selection(
    current: dict[str, Any],
    directory: Path,
) -> dict[str, Any]:
    """Map exact UI identities through the existing handoff producer's helpers."""
    context, records, _ = file_preparation_handoff(directory)
    selected = current["selection"]
    if selected["item_type"] in {"draft_memo_section", "draft_client_email"}:
        return {
            "selection_mode": "explicitly_selected_draft",
            "item": selected,
            "instruction": "This exact draft was selected for discussion; it is not default synthesis context or approval to send.",
        }
    path = module_root("client-file-preparation") / "scripts/model_handoff.py"
    spec = importlib.util.spec_from_file_location(
        "native_file_preparation_handoff", path
    )
    if spec is None or spec.loader is None:
        raise ValueError("Maintained model handoff producer is unavailable")
    domain = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = domain
    spec.loader.exec_module(domain)
    review = read_json(directory / "review_payload.json")
    lookup = domain._document_lookup(review["items"])
    # These helpers already own context fields and opaque identity formulas.
    # Only exact IDs are mapped here; document meaning is never reclassified.
    projected = [
        *domain._file_metadata_items([selected]),
        *domain._evidence_excerpt_items([selected]),
        *domain._fiscal_field_items([selected], lookup),
        *domain._missing_request_candidate_items([selected]),
        *domain._duplicate_group_items([selected], lookup),
        *domain._xml_anomaly_items([selected], lookup),
    ]
    references = {item["id"] for item in projected}
    if selected["item_type"] == "uncertain_file":
        document_ref = domain._document_reference(selected["source_path"], lookup)
        references.update(
            item["id"] for item in records if item.get("document_ref") == document_ref
        )
    allowed = context["phase_access"]["file_preparation_review"]
    matching = [
        item for item in records if item["id"] in references and item["kind"] in allowed
    ]
    if not matching:
        raise ValueError("Selected item has no maintained file-preparation context")
    return {
        "selection_mode": "maintained_model_handoff",
        "items": matching,
        "content_policy": context["content_policy"],
        "phase": "file_preparation_review",
    }


def outputs(binding: dict[str, Any], loaded: dict[str, Any]) -> list[dict[str, str]]:
    """Expose only declared regular artifacts inside the authoritative run."""
    output = Path(loaded["output_dir"])
    review = review_directory(output, binding.get("component", binding["workflow_id"]))
    manifest_path = review / "final_artifacts.json"
    if not manifest_path.exists():
        return []
    manifest = read_json(manifest_path)
    candidates = [
        row.get("path") for row in manifest.get("outputs", []) if isinstance(row, dict)
    ]
    candidates += [manifest.get(key) for key in ("report", "workbook", "forecast")]
    result = []
    for raw in dict.fromkeys(raw for raw in candidates if isinstance(raw, str) and raw):
        path = Path(raw)
        path = path if path.is_absolute() else review / path
        if (
            not path.is_relative_to(output)
            or ".." in path.parts
            or any(p.is_symlink() for p in (path, *path.parents))
        ):
            raise ValueError("Declared output leaves the authorised run")
        if path.is_file():
            result.append(
                {"name": path.name, "path": str(path), "work_ref": binding["work_ref"]}
            )
    return result


def bilancio_call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(module_root("bilancio-xbrl-it") / "scripts/service_bridge.py"),
        ],
        input=json.dumps({"tool": tool, "arguments": args}),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "Bilancio service failed")
    return json.loads(completed.stdout)


def treasury_record(loaded: dict[str, Any]) -> dict[str, Any]:
    from types import SimpleNamespace

    from native_treasury_preparation import audit_preparation

    audit_preparation(
        Path(loaded["output_dir"]),
        module_root("treasury-forecast"),
        SimpleNamespace(read_json=read_json, ui_state_directory=ui_state_directory),
    )
    sys.path.insert(0, str(module_root("treasury-forecast") / "scripts"))
    import run_treasury  # Registers the maintained assurance module path.
    from treasury_session import current_record
    from vera_assurance import load_client_engagement_context_file

    output = Path(loaded["output_dir"])
    state, record = current_record(output)
    context = load_client_engagement_context_file(
        Path(loaded["context_path"]),
        expected_workflow_id="treasury-forecast",
        input_paths=[Path(s["path"]) for s in state["sources"]],
        allowed_statuses=("running", "ready_for_review", "completed"),
    )
    if context["schema_version"] != "vera.client_workflow_context.v2":
        raise run_treasury.TreasuryError(
            "Treasury requires a portable v2 client workflow"
        )
    return record


def archive_execution_projection(output: Path, offset: int) -> dict[str, Any]:
    """Keep raw executable hashes and Drive identities in the existing engine."""
    plan_path, journal_path = (
        output / "approved_plan.json",
        output / "apply_journal.json",
    )
    approved = read_json(plan_path) if plan_path.exists() else None
    journal = read_json(journal_path) if journal_path.exists() else None
    projection = None
    if approved:
        domain_path = (
            module_root("archive-organization") / "scripts/archive_organization.py"
        )
        spec = importlib.util.spec_from_file_location(
            "native_archive_projection", domain_path
        )
        if spec is None or spec.loader is None:
            raise ValueError("Archive projection service is unavailable")
        domain = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(domain)
        plan = read_json(output / "archive_plan.json")

        def project_path(value: str) -> str:
            if approved["storage_kind"] == "local_filesystem":
                return value
            return domain._project_drive_relative_path(plan["snapshot_sha256"], value)

        changes = [
            row
            for row in approved["items"]
            if row["approved_action"] in domain.CHANGE_ACTIONS
        ]
        projection = {
            "storage_kind": approved["storage_kind"],
            "approved_by": approved["approved_by"],
            "change_count": len(changes),
            "offset": offset,
            "has_more": offset + 30 < len(changes),
            "items": [
                {
                    "source": project_path(row["source_relative_path"]),
                    "destination": project_path(row["approved_target_relative_path"]),
                    "action": row["approved_action"],
                }
                for row in changes[offset : offset + 30]
            ],
        }
    return {
        "approved_plan": projection,
        "journal": (
            {"status": journal["status"], "operation_count": len(journal["operations"])}
            if journal
            else None
        ),
        "execution_requires_separate_explicit_approval": True,
    }


def report_checkpoint(output: Path, run_id: str) -> dict[str, Any] | None:
    """Read only a prior engine acknowledgement retained outside report outputs."""
    path = ui_state_directory(output, create=False) / "report-checkpoint.json"
    if not path.exists():
        return None
    stored = read_json(path)
    if stored["run_id"] != run_id:
        raise ValueError("Report checkpoint belongs to another run")
    for key in ("current_checkpoint", "predecessor_checkpoint"):
        value = stored[key]
        if value is None and key == "predecessor_checkpoint":
            continue
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Invalid retained report checkpoint")
    return stored


def report_review(
    output: Path,
    directory: Path,
    run_id: str,
    operation: str,
    posted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Forward retained checkpoints to the existing report service and replay."""
    helper = workbench_module()
    workbench = helper.LocalReviewWorkbench(module_root("report-builder"), directory)
    stored = report_checkpoint(output, run_id)
    raw = helper._raw_session_payload(workbench)
    if operation == "save" and raw["applied_decisions"]:
        raise ValueError(
            "After report application, retain a native draft or apply the reviewed successor"
        )
    arguments = helper._with_vera_customer_context(
        workbench,
        helper._server_tool_args(workbench, posted or {}),
        read_only=operation == "read",
    )
    if stored:
        expected = (
            stored["current_checkpoint"]
            if operation == "apply" and raw["applied_decisions"]
            else stored["predecessor_checkpoint"]
        )
        if expected:
            arguments["expected_predecessor_checkpoint"] = expected
    supplied = (posted or {}).get("expected_predecessor_checkpoint")
    if (
        operation == "apply"
        and raw["applied_decisions"]
        and not stored
        and not supplied
    ):
        raise ValueError("Retained report checkpoint is required for successor apply")
    if supplied:
        if stored and supplied != arguments.get("expected_predecessor_checkpoint"):
            raise ValueError(
                "Supplied report checkpoint differs from retained authority"
            )
        arguments["expected_predecessor_checkpoint"] = supplied
    name = {
        "read": "render_report_builder_review",
        "save": "save_report_builder_decisions",
        "apply": "apply_report_builder_decisions",
    }[operation]
    result = helper._mcp_tool_result(
        workbench, name, arguments, browser_payload=operation == "read"
    )
    if result.get("ok") is False:
        raise ValueError(str(result.get("error") or "Report review was refused"))
    if operation == "read":
        if result["review_payload"]["run_id"] != run_id:
            raise ValueError("Report service returned another run")
        result["applied_decisions"] = raw["applied_decisions"]
        # Narrative edits intentionally preserve the original review packet.
        # Show the engine's replay-validated current narrative in the projection.
        analysis = read_json(directory / "report_analysis.json")
        sections = {row["section"]: row for row in analysis["sections"]}
        if len(sections) != len(analysis["sections"]):
            raise ValueError("Ambiguous report section identity")
        for item in result["review_payload"]["items"]:
            if item["item_type"] == "report_section":
                item["data"]["codex_comment"] = sections[item["data"]["section"]].get(
                    "codex_comment", ""
                )
    else:
        checkpoint = result.get("integrity_checkpoint")
        predecessor = (
            result["applied_decisions"].get("predecessor_checkpoint")
            if operation == "apply"
            else result.get("predecessor_checkpoint")
        )
        if (
            result.get("persisted") is not True
            or result.get("run_id") != run_id
            or not isinstance(checkpoint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", checkpoint)
            or (
                predecessor is not None
                and (
                    not isinstance(predecessor, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", predecessor)
                )
            )
        ):
            raise ValueError("Report service returned no valid retained authority")
        atomic_json(
            ui_state_directory(output) / "report-checkpoint.json",
            {
                "run_id": run_id,
                "current_checkpoint": checkpoint,
                "predecessor_checkpoint": predecessor,
            },
        )
    redactions = helper._known_absolute_paths(
        {"session": raw, "tool_args": arguments, "output": str(directory.resolve())}
    )
    return helper._sanitize_browser_payload(result, redactions=redactions)


def concordato_review(
    output: Path,
    directory: Path,
    loaded: dict[str, Any],
    operation: str,
    posted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hydrate the maintained case through its public persisted-reference contract."""
    helper = workbench_module()
    arguments = {
        "client_engagement": str(loaded["context_path"]),
        "review_reference": read_json(directory / "final_artifacts.json")[
            "review_reference"
        ],
    }
    if operation != "read":
        if posted is None:
            raise ValueError("Explicit Concordato review decisions are required")
        if operation == "apply":
            memo_ids = {
                item["id"]
                for item in read_json(directory / "review_payload.json")["items"]
                if item["item_type"] == "codex_review_memo"
            }
            if any(
                row["item_id"] in memo_ids and row["action"] == "edit"
                for row in posted["decisions"]
            ):
                raise ValueError(
                    "L'applicazione del memo Concordato resta sospesa: il riepilogo "
                    "Word aggiornato non supera il replay del motore. Conserva la "
                    "proposta con Salva decisione; i file ufficiali restano invariati."
                )
        arguments.update(
            decisions=posted["decisions"],
            reviewer=posted["reviewer"],
            decision_source="native_workspace",
        )
    result = engine_context("concordato-plan-review", arguments, operation=operation)
    if result.get("ok") is False:
        raise ValueError(str(result.get("error") or "Concordato review was refused"))
    if operation == "read":
        if result["review_payload"]["run_id"] != loaded["run"]["run_id"]:
            raise ValueError("Concordato service returned another run")
        result["local_review_read_only"] = loaded["run"]["status"] != "running"
    elif (
        result.get("persisted") is not True
        or result.get("run_id") != loaded["run"]["run_id"]
    ):
        raise ValueError("Concordato decisions were not persisted")
    redactions = helper._known_absolute_paths(
        {"tool_args": arguments, "output": str(output.resolve())}
    )
    return helper._sanitize_browser_payload(result, redactions=redactions)


def snapshot(
    binding: dict[str, Any], loaded: dict[str, Any], args: dict[str, Any]
) -> dict[str, Any]:
    component = binding.get("component", binding["workflow_id"])
    root = module_root(component)
    output = Path(loaded["output_dir"])
    start_revision = output_revision(output, component)
    offset = args.get("offset", 0)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("Invalid page offset")
    if component == "bilancio-xbrl-it":
        data = bilancio_call(
            "xbrl_workspace_view",
            {
                "case_id": binding["case_id"],
                "view": args.get("view", "ISSUES_PANEL"),
                "offset": offset,
                **({"issue_id": args["item_id"]} if args.get("item_id") else {}),
                **({"revision_id": args["revision"]} if args.get("revision") else {}),
                **(
                    {"source_ref": args["source_ref"]} if args.get("source_ref") else {}
                ),
            },
        )
        revision = data["revision_id"]
        items = data["review"].get("issues", {}).get("items", [])
        total = (
            data["review"].get("issues", {}).get("page", {}).get("total", len(items))
        )
        selected = data["selection"]
        kind = "bilancio"
    elif component == "treasury-forecast":
        data = treasury_record(loaded)
        revision = data["record_sha256"]
        all_items = data["events"]
        items, total = all_items[offset : offset + 30], len(all_items)
        selected = next(
            (row for row in all_items if row["event_id"] == args.get("item_id")), None
        )
        # Keep the engine record authoritative; send a bounded projection to UI.
        data = {
            key: data[key]
            for key in (
                "company_name",
                "currency",
                "as_of",
                "horizon_end",
                "status",
                "opening_cash",
                "minimum_daily_cash",
                "first_negative_day",
                "calculation_complete",
                "coverage",
                "proposal_sha256",
                "review",
            )
        }
        kind = "treasury"
    elif component == "financial-analysis":
        from native_financial_analysis import read_prepared

        prepared = read_prepared(root, loaded, args, read_json)
        revision = prepared["revision"]
        data = prepared["data"]
        items, total = prepared["items"], prepared["total"]
        selected = prepared["selection"]
        kind = "financial"
    elif component == "centrale-rischi-review":
        from types import SimpleNamespace

        from native_centrale_rischi import read_prepared

        prepared = read_prepared(
            root,
            binding,
            loaded,
            args,
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
            ),
        )
        revision, data = prepared["revision"], prepared["data"]
        items, total, selected = (
            prepared["items"],
            prepared["total"],
            prepared["selection"],
        )
        kind = "cr"
    elif component == "sales-plan":
        from types import SimpleNamespace

        from native_sales_plan import read_prepared

        prepared = read_prepared(
            root,
            binding,
            loaded,
            args,
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
            ),
        )
        revision = prepared["revision"]
        data = prepared["data"]
        items, total = prepared["items"], prepared["total"]
        selected = prepared["selection"]
        kind = "sales"
    elif component == "lipe":
        from types import SimpleNamespace

        from native_lipe import read_prepared

        prepared = read_prepared(
            root,
            binding,
            loaded,
            args,
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
            ),
        )
        revision = prepared["revision"]
        data = prepared["data"]
        items, total = prepared["items"], prepared["total"]
        selected = prepared["selection"]
        kind = "lipe"
    elif component in {"aml-review", "adeguati-assetti"}:
        from types import SimpleNamespace

        from native_aml import read_prepared

        prepared = read_prepared(
            root,
            binding,
            loaded,
            args,
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
            ),
        )
        revision = prepared["revision"]
        data = prepared["data"]
        items, total = prepared["items"], prepared["total"]
        selected = prepared["selection"]
        kind = "aml" if component == "aml-review" else "assetti"
    elif component == "invoice-xml":
        from types import SimpleNamespace

        from native_invoice import read_prepared

        prepared = read_prepared(
            root,
            binding,
            loaded,
            args,
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
            ),
        )
        revision, data = prepared["revision"], prepared["data"]
        items, total, selected = (
            prepared["items"],
            prepared["total"],
            prepared["selection"],
        )
        kind = "invoice"
    elif component == "scissione-guidata":
        from types import SimpleNamespace

        from native_scissione import read_prepared

        prepared = read_prepared(
            root,
            binding,
            loaded,
            args,
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
            ),
        )
        revision, data = prepared["revision"], prepared["data"]
        items, total, selected = (
            prepared["items"],
            prepared["total"],
            prepared["selection"],
        )
        kind = "scissione"
    elif (root / "assets/review-workbench-adapter.json").is_file():
        helper = workbench_module()
        directory = review_directory(output, component)
        if component == "report-builder":
            data = report_review(output, directory, loaded["run"]["run_id"], "read")
        elif component == "concordato-plan-review":
            data = concordato_review(output, directory, loaded, "read")
        elif component == "open-item-reconciliation":
            data = open_item_review(directory, "read", {})
        else:
            data = helper.build_session_payload(
                helper.LocalReviewWorkbench(root, directory)
            )
        if component == "report-builder":
            data["local_review_read_only"] = loaded["run"]["status"] != "running"
        revision = start_revision
        all_items = data["review_payload"]["items"]
        items, total = all_items[offset : offset + 30], len(all_items)
        selected = next(
            (row for row in all_items if row["id"] == args.get("item_id")), None
        )
        data = {
            key: data.get(key)
            for key in (
                "ui_decisions",
                "applied_decisions",
                "final_artifacts",
                "local_review_read_only",
            )
        }
        data["adapter"] = read_json(root / "assets/review-workbench-adapter.json")
        data["adapter"].pop("demo", None)
        if component == "concordato-plan-review":
            data["memo_application_available"] = False
        if component == "open-item-reconciliation":
            manifest = directory / "run_manifest.json"
            data["regeneration_available"] = bool(
                manifest.is_file()
                and "report_options" in read_json(manifest)
                and data["applied_decisions"]
            )
        if component == "archive-organization":
            data["archive_execution"] = archive_execution_projection(output, offset)
        kind = "workbench"
    else:
        raise ValueError(
            "This workflow's native adapter is not implemented yet; use its existing workflow"
        )
    if args.get("item_id") and selected is None:
        raise ValueError("Unknown selection in this authorised run")
    if args.get("revision") and revision != args["revision"]:
        raise ValueError("Stale state: reopen this run before continuing")
    if output_revision(output, component) != start_revision:
        raise ValueError("State changed during reading: reopen this run")
    result = {
        "work_ref": binding["work_ref"],
        "client_id": binding["client_id"],
        "client_label": Path(binding["client_root"]).name,
        "engagement_id": binding["engagement_id"],
        "workflow": component,
        "label": loaded["run"]["label"],
        "run_status": loaded["run"]["status"],
        "kind": kind,
        "view": args.get("view", "REVIEW"),
        "revision": revision,
        "data": data,
        "items": items,
        "selection": selected,
        "offset": offset,
        "total": total,
        "has_more": offset + 30 < total,
    }
    if len(json.dumps(result).encode()) > MAX_BYTES:
        raise ValueError(
            "Native projection is oversized; use the existing paginated workflow"
        )
    return result


def ui_state_directory(output: Path, *, create: bool = True) -> Path:
    """Keep unapplied UI state outside the ledger's declared output tree."""
    directory = output.parent / ".native-workspace"
    if any(parent.is_symlink() for parent in (directory, *directory.parents)):
        raise ValueError("Native state cannot use symbolic links")
    if create:
        directory.mkdir(mode=0o700, exist_ok=True)
    if directory.exists() and not directory.is_dir():
        raise ValueError("Native state must be a directory")
    return directory


@contextmanager
def write_lock(output: Path) -> Iterator[None]:
    """Serialize shared UI writes; domain engines retain their own transactions."""
    path = ui_state_directory(output) / "write.lock"
    with path.open("x"):
        try:
            yield
        finally:
            path.unlink(missing_ok=True)


def draft_path(output: Path, actor: str, *, create: bool = True) -> Path:
    return ui_state_directory(output, create=create) / (
        "draft-" + digest(actor) + ".json"
    )


def atomic_json(path: Path, value: Any) -> None:
    """Persist recoverable UI drafts and submission receipts, never case state."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def selected_decisions(current: dict[str, Any], args: dict[str, Any]) -> Any:
    """Reject writes outside the exact item opened for human review."""
    selected = args.get("item_id")
    if not selected or not current["selection"]:
        raise ValueError("Select one exact item before saving a decision")
    decisions = args["decisions"]
    if current["kind"] == "treasury":
        if not isinstance(decisions, dict) or set(decisions) != {selected}:
            raise ValueError("Decision must belong to the selected event")
    else:
        if (
            not isinstance(decisions, list)
            or len(decisions) != 1
            or not isinstance(decisions[0], dict)
            or decisions[0].get("item_id") != selected
        ):
            raise ValueError("Decision must belong to the selected item")
    return decisions


def selected_model_context(
    current: dict[str, Any], output: Path, loaded: dict[str, Any]
) -> dict[str, Any]:
    """Use the engine's existing model projection for exactly the UI selection."""
    component = current["workflow"]
    directory = review_directory(output, component)
    item_id = current["selection"]["id"]
    if component == "client-file-preparation":
        return file_preparation_selection(current, directory)
    if component == "journal-sampling":
        context = read_json(directory / "model_review_context.json")
        selected = next(
            (item for item in context["review"]["items"] if item["id"] == item_id),
            None,
        )
        if selected is None:
            raise ValueError("Selection is absent from the maintained model context")
        return {"item": selected, "minimization": context["minimization"]}
    arguments = {
        "client_engagement": str(loaded["context_path"]),
        "review_payload_path": str(directory / "review_payload.json"),
    }
    if component == "concordato-plan-review":
        arguments = {
            "client_engagement": str(loaded["context_path"]),
            "review_reference": read_json(directory / "final_artifacts.json")[
                "review_reference"
            ],
        }
    return engine_context(component, arguments, item_id=item_id)


def engine_context(
    component: str, arguments: dict[str, Any], **selection: Any
) -> dict[str, Any]:
    """Call only registered source tools; model and widget transports stay distinct."""
    helper = workbench_module()
    completed = subprocess.run(
        [helper._node_executable(), str(ROOT / "mcp/selected-context.cjs")],
        input=json.dumps(
            {
                "component": component,
                "server": str(module_root(component) / "mcp/server.cjs"),
                "arguments": arguments,
                **selection,
            }
        ),
        text=True,
        capture_output=True,
        timeout=40,
        env={**os.environ, "PYTHON": os.environ.get("PYTHON") or sys.executable},
        check=False,
    )
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "Selected context was refused")
    return json.loads(completed.stdout)


def open_item_review(
    output: Path, operation: str, args: dict[str, Any], context: Path | None = None
) -> dict[str, Any]:
    """Use the specialist's existing Python service and assurance transaction."""
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(ROOT / "scripts/native_open_item_bridge.py"),
            str(module_root("open-item-reconciliation")),
        ],
        input=json.dumps(
            {
                "operation": operation,
                "output_dir": str(output),
                "arguments": args,
                "context": str(context) if context else None,
            }
        ),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if completed.returncode:
        raise ValueError(
            completed.stderr.strip().splitlines()[-1] or "Review was refused"
        )
    return json.loads(completed.stdout)


def dispatch(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    if tool.startswith("vera_workspace_browser_"):
        from types import SimpleNamespace

        from native_browser import dispatch as browser_dispatch

        return browser_dispatch(
            tool,
            args,
            module_root("browser-automation"),
            SimpleNamespace(atomic_json=atomic_json, write_lock=write_lock),
        )
    if tool.startswith("vera_workspace_fusion_"):
        from types import SimpleNamespace

        from native_fusion import dispatch as fusion_dispatch

        return fusion_dispatch(
            tool,
            args,
            module_root("fusione-guidata"),
            SimpleNamespace(atomic_json=atomic_json, write_lock=write_lock),
        )
    if tool.startswith("vera_workspace_transformation_"):
        from types import SimpleNamespace

        from native_transformation import dispatch as transformation_dispatch

        return transformation_dispatch(
            tool,
            args,
            module_root("trasformazione"),
            SimpleNamespace(atomic_json=atomic_json, write_lock=write_lock),
        )
    if tool.startswith("vera_workspace_website_"):
        from types import SimpleNamespace

        from native_website import dispatch as website_dispatch

        return website_dispatch(
            tool,
            args,
            module_root("presenza-digitale-studio"),
            SimpleNamespace(atomic_json=atomic_json, write_lock=write_lock),
        )
    if tool.startswith("vera_workspace_communication_"):
        from types import SimpleNamespace

        from native_communication import dispatch as communication_dispatch

        return communication_dispatch(
            tool,
            args,
            module_root("comunicazione-professionale"),
            SimpleNamespace(atomic_json=atomic_json, write_lock=write_lock),
        )
    config = configuration()
    if config["mode"] == "studio-archive":
        from native_archive_navigation import (
            archive_action,
            catalogue,
            lifecycle_action,
            resolve_binding,
        )

        if tool.startswith("vera_workspace_archive_import_"):
            from types import SimpleNamespace

            from native_archive_imports import dispatch as import_dispatch

            return import_dispatch(
                module_root("studio-archive"),
                tool,
                args,
                SimpleNamespace(atomic_json=atomic_json, write_lock=write_lock),
            )

        if tool.startswith("vera_workspace_business_plan_author_"):
            from types import SimpleNamespace

            from native_business_planning_authoring import dispatch as author_dispatch

            return author_dispatch(
                module_root("studio-archive"),
                module_root("business-planning"),
                tool,
                args,
                SimpleNamespace(
                    read_json=read_json,
                    digest=digest,
                    atomic_json=atomic_json,
                    ui_state_directory=ui_state_directory,
                    write_lock=write_lock,
                    load_binding=load_binding,
                ),
            )

        if tool in {
            "vera_workspace_archive_closure",
            "vera_workspace_archive_declare",
            "vera_workspace_archive_discard",
            "vera_workspace_archive_finalize",
            "vera_workspace_archive_complete",
        }:
            from types import SimpleNamespace

            from native_archive_closure import dispatch as closure_dispatch

            return closure_dispatch(
                module_root("studio-archive"),
                tool,
                args,
                SimpleNamespace(
                    read_json=read_json,
                    digest=digest,
                    load_binding=load_binding,
                    atomic_json=atomic_json,
                    ui_state_directory=ui_state_directory,
                    write_lock=write_lock,
                ),
            )

        if tool in {
            "vera_workspace_archive_inputs",
            "vera_workspace_archive_create_engagement",
            "vera_workspace_archive_prepare",
            "vera_workspace_archive_start",
        }:
            return lifecycle_action(module_root("studio-archive"), tool, args)

        if tool in {"vera_workspace_archive_setup", "vera_workspace_archive_refresh"}:
            if "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","):
                raise PermissionError("Reviewer authority is required")
            if args.get("confirmed") is not True:
                raise ValueError("Confirm the archive configuration action")
            return archive_action(
                module_root("studio-archive"),
                "setup" if tool.endswith("_setup") else "refresh",
            )
        if tool == "vera_workspace_open":
            result = catalogue(module_root("studio-archive"), args)
            for row in result["works"]:
                row["review_available"] = False
                if not row["inputs_valid"]:
                    continue
                binding = resolve_binding(
                    module_root("studio-archive"), row["work_ref"]
                )
                if binding["component"] == "bilancio-xbrl-it":
                    try:
                        connect_bilancio_binding(binding)
                    except (PermissionError, ValueError):
                        row["review_status"] = "canonical_connection_required"
                    else:
                        row["review_available"] = True
                    continue
                loaded = load_binding(binding)
                if loaded is not None:
                    output = Path(loaded["output_dir"])
                    component = binding["component"]
                    if component == "client-file-preparation":
                        row["source_groups_available"] = True
                    if component == "treasury-forecast":
                        row["setup_available"] = not (
                            output / "treasury_session.json"
                        ).is_file()
                    if component == "journal-bank-reconciliation":
                        row["setup_available"] = (
                            loaded["run"]["status"] in {"prepared", "running"}
                            and not (
                                review_directory(output, component)
                                / "review_payload.json"
                            ).is_file()
                        )
                    if component == "open-item-reconciliation":
                        row["setup_available"] = (
                            loaded["run"]["status"] in {"prepared", "running"}
                            and not (
                                review_directory(output, component)
                                / "review_payload.json"
                            ).is_file()
                        )
                    if component in {
                        "sales-plan",
                        "business-planning",
                        "business-valuation",
                        "variance-analysis",
                        "management-control-pack",
                        "composizione-negoziata",
                        "esg-reporting-assurance",
                        "previdenza-inps",
                        "lipe",
                        "aml-review",
                        "adeguati-assetti",
                        "scissione-guidata",
                        "invoice-xml",
                        "passive-invoice-audit",
                        "centrale-rischi-review",
                        "registro-imprese-sari",
                        "bandi-agevolazioni",
                        "patent-box-review",
                        "rating-legalita",
                    }:
                        row["setup_available"] = True
                        continue
                    if component == "financial-analysis":
                        row["setup_available"] = True
                        from types import SimpleNamespace

                        from native_financial_analysis import read_prepared
                        from native_financial_execution import audit_run

                        financial = audit_run(
                            output,
                            SimpleNamespace(
                                read_json=read_json,
                                ui_state_directory=ui_state_directory,
                            ),
                        )
                        row["review_status"] = (
                            "specialist_recovery_required"
                            if financial["recovery_required"]
                            else "intake_available"
                        )
                        if any(
                            (output / path / "pack_execution_receipt.json").is_file()
                            for path in ("", "prepared")
                        ):
                            try:
                                read_prepared(
                                    module_root(component), loaded, {}, read_json
                                )
                            except (OSError, ValueError):
                                row["review_status"] = "specialist_recovery_required"
                            else:
                                row["review_available"] = True
                        continue
                    row["review_available"] = (
                        (output / "treasury_session.json").is_file()
                        if component == "treasury-forecast"
                        else component
                        in {
                            "journal-bank-reconciliation",
                            "journal-sampling",
                            "check-entries",
                            "open-item-reconciliation",
                            "new-client",
                            "client-file-preparation",
                            "archive-organization",
                            "report-builder",
                            "concordato-plan-review",
                        }
                        and (
                            review_directory(output, component) / "review_payload.json"
                        ).is_file()
                    )
                    if component == "treasury-forecast" and row["review_available"]:
                        sys.path.insert(0, str(module_root(component) / "scripts"))
                        from treasury_core import TreasuryError

                        try:
                            treasury_record(loaded)
                        except (TreasuryError, ValueError):
                            row["review_available"] = False
                            row["review_status"] = "specialist_recovery_required"
            return result
        binding = resolve_binding(
            module_root("studio-archive"), args.get("work_ref", "")
        )
        if tool == "vera_workspace_resume_context":
            return {
                key: binding[key]
                for key in (
                    "work_ref",
                    "client_id",
                    "engagement_id",
                    "run_id",
                    "workflow_id",
                )
            }
        if binding["component"] == "bilancio-xbrl-it":
            binding = connect_bilancio_binding(binding)
    else:
        if tool in {
            "vera_workspace_archive_setup",
            "vera_workspace_archive_closure",
            "vera_workspace_archive_declare",
            "vera_workspace_archive_discard",
            "vera_workspace_archive_finalize",
            "vera_workspace_archive_complete",
            "vera_workspace_archive_refresh",
            "vera_workspace_archive_inputs",
            "vera_workspace_archive_create_engagement",
            "vera_workspace_archive_prepare",
            "vera_workspace_archive_start",
        }:
            raise ValueError("This operator-bound pilot retains its existing setup")
        binding = next(
            (b for b in config["bindings"] if b["work_ref"] == args.get("work_ref")),
            None,
        )
    if tool == "vera_workspace_open":
        sys.path.insert(0, str(module_root("studio-archive") / "scripts"))
        from client_ledger import load_engagement_manifest

        records = []
        for binding in config["bindings"]:
            loaded = load_binding(binding)
            client_root = Path(binding["client_root"])
            engagement = load_engagement_manifest(client_root, binding["engagement_id"])
            records.append(
                {
                    "work_ref": binding["work_ref"],
                    "client_id": binding["client_id"],
                    "client_label": client_root.name,
                    "engagement_id": binding["engagement_id"],
                    "engagement_label": engagement["label"],
                    "workflow": binding.get("component", binding["workflow_id"]),
                    "label": loaded["run"]["label"],
                    "status": loaded["run"]["status"],
                    "created_at": loaded["run"]["created_at"],
                    "setup_available": binding["workflow_id"]
                    in {
                        "financial-analysis",
                        "esg-reporting-assurance",
                        "previdenza-inps",
                        "business-valuation",
                        "sales-plan",
                        "business-planning",
                        "lipe",
                        "aml-review",
                        "adeguati-assetti",
                        "scissione-guidata",
                        "invoice-xml",
                        "passive-invoice-audit",
                        "centrale-rischi-review",
                        "registro-imprese-sari",
                        "bandi-agevolazioni",
                        "patent-box-review",
                        "rating-legalita",
                    }
                    or binding["workflow_id"] == "treasury-forecast"
                    and not (
                        Path(loaded["output_dir"]) / "treasury_session.json"
                    ).is_file()
                    or binding["workflow_id"]
                    in {
                        "journal-bank-reconciliation",
                        "open-item-reconciliation",
                    }
                    and not (
                        review_directory(
                            Path(loaded["output_dir"]), binding["workflow_id"]
                        )
                        / "review_payload.json"
                    ).is_file(),
                    "source_groups_available": binding["workflow_id"]
                    == "client-file-preparation",
                }
            )
        return {"works": records}
    if binding is None:
        raise PermissionError("Run is not authorised in this workspace")
    loaded = load_binding(binding)
    output = Path(loaded["output_dir"])
    if tool.startswith("vera_workspace_open_items_intake_"):
        from types import SimpleNamespace

        from native_open_items_intake import dispatch as intake_dispatch

        return intake_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("open-item-reconciliation"),
            SimpleNamespace(**globals()),
        )
    if binding["workflow_id"] == "patent-box-review":
        from types import SimpleNamespace

        from native_patent_box import audit_run as audit_patent_box
        from native_patent_box import dispatch as patent_box_dispatch
        from native_patent_box_authoring import audit_run as audit_patent_box_author
        from native_patent_box_authoring import dispatch as patent_box_author_dispatch

        patent_box_api = SimpleNamespace(**globals())
        if tool.startswith("vera_workspace_patent_box_author_"):
            return patent_box_author_dispatch(
                tool, args, binding, module_root("patent-box-review"), patent_box_api
            )
        author = audit_patent_box_author(output, patent_box_api)
        if author["recovery_required"] or (
            tool == "vera_workspace_patent_box_execute" and author["unfinished"]
        ):
            raise ValueError(
                "Patent Box model mandate requires disposition or recovery"
            )
        if tool.startswith("vera_workspace_patent_box_"):
            return patent_box_dispatch(
                tool, args, binding, module_root("patent-box-review"), patent_box_api
            )
        if audit_patent_box(output, patent_box_api)["recovery_required"]:
            raise ValueError("Patent Box operation requires ordinary recovery")
    if binding["workflow_id"] == "bandi-agevolazioni":
        from types import SimpleNamespace

        from native_bandi import audit_run as audit_bandi
        from native_bandi import dispatch as bandi_dispatch
        from native_bandi_authoring import audit_run as audit_bandi_authoring
        from native_bandi_authoring import dispatch as bandi_author_dispatch

        bandi_api = SimpleNamespace(**globals())
        if tool.startswith("vera_workspace_bandi_author_decision_draft_"):
            from native_bandi_decision_drafts import (
                dispatch as bandi_decision_draft_dispatch,
            )

            return bandi_decision_draft_dispatch(
                tool,
                args,
                binding,
                loaded,
                module_root("bandi-agevolazioni"),
                bandi_api,
            )
        if tool.startswith("vera_workspace_bandi_author_"):
            return bandi_author_dispatch(
                tool,
                args,
                binding,
                loaded,
                module_root("bandi-agevolazioni"),
                bandi_api,
            )
        if tool.startswith("vera_workspace_bandi_"):
            if (
                tool not in {"vera_workspace_bandi_setup", "vera_workspace_bandi_read"}
                and audit_bandi_authoring(output, bandi_api)["recovery_required"]
            ):
                raise ValueError(
                    "Grant contribution is uncertain; ordinary recovery required"
                )
            return bandi_dispatch(
                tool,
                args,
                binding,
                loaded,
                module_root("bandi-agevolazioni"),
                bandi_api,
            )
        if audit_bandi(output, bandi_api)["recovery_required"]:
            raise ValueError("Grant operation is uncertain; ordinary recovery required")
        if audit_bandi_authoring(output, bandi_api)["recovery_required"]:
            raise ValueError(
                "Grant contribution is uncertain; ordinary recovery required"
            )
    if binding["workflow_id"] == "registro-imprese-sari":
        from types import SimpleNamespace

        from native_sari_followup import audit_run as audit_sari_followup
        from native_sari_followup import dispatch as sari_followup_dispatch
        from native_sari_followup import ensure_run_ready

        followup_api = SimpleNamespace(**globals())
        ensure_run_ready(binding, loaded, followup_api)
        if tool.startswith("vera_workspace_sari_followup_"):
            return sari_followup_dispatch(
                tool,
                args,
                binding,
                loaded,
                module_root("registro-imprese-sari"),
                followup_api,
            )
        if audit_sari_followup(output, followup_api)["recovery_required"]:
            raise ValueError(
                "Registry follow-up creation is uncertain; ordinary recovery required"
            )
    if tool.startswith("vera_workspace_sari_review_"):
        from types import SimpleNamespace

        from native_sari_review import dispatch as sari_review_dispatch

        return sari_review_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("registro-imprese-sari"),
            SimpleNamespace(**globals()),
        )
    if tool.startswith("vera_workspace_sari_author_"):
        from types import SimpleNamespace

        from native_sari_authoring import dispatch as sari_author_dispatch

        return sari_author_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("registro-imprese-sari"),
            SimpleNamespace(**globals()),
        )
    if tool.startswith("vera_workspace_sari_"):
        from types import SimpleNamespace

        from native_sari_intake import dispatch as sari_dispatch

        return sari_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("registro-imprese-sari"),
            SimpleNamespace(**globals()),
        )
    if tool.startswith("vera_workspace_rating_"):
        from types import SimpleNamespace

        from native_rating import dispatch as rating_dispatch

        return rating_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("rating-legalita"),
            SimpleNamespace(**globals()),
        )
    if tool.startswith("vera_workspace_inps_"):
        from types import SimpleNamespace

        from native_inps import dispatch as inps_dispatch

        return inps_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("previdenza-inps"),
            SimpleNamespace(**globals()),
        )
    if tool.startswith("vera_workspace_cr_"):
        from types import SimpleNamespace

        from native_centrale_rischi import dispatch as cr_dispatch

        return cr_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("centrale-rischi-review"),
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if tool.startswith("vera_workspace_financial_"):
        from types import SimpleNamespace

        from native_financial_execution import dispatch as financial_dispatch

        return financial_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("financial-analysis"),
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if tool.startswith("vera_workspace_source_group_"):
        from types import SimpleNamespace

        from native_passive_sources import dispatch as group_dispatch

        return group_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("passive-invoice-audit"),
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if tool.startswith("vera_workspace_passive_"):
        from types import SimpleNamespace

        from native_passive_service import dispatch as passive_dispatch

        return passive_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("passive-invoice-audit"),
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if tool.startswith("vera_workspace_invoice_"):
        from types import SimpleNamespace

        from native_invoice import dispatch as invoice_dispatch

        return invoice_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("invoice-xml"),
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if tool.startswith("vera_workspace_scissione_"):
        from types import SimpleNamespace

        from native_scissione import dispatch as scissione_dispatch

        return scissione_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("scissione-guidata"),
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if tool.startswith(("vera_workspace_aml_", "vera_workspace_assetti_")):
        from types import SimpleNamespace

        from native_aml import dispatch as aml_dispatch

        return aml_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root(
                "aml-review"
                if tool.startswith("vera_workspace_aml_")
                else "adeguati-assetti"
            ),
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if binding["workflow_id"] in {
        "passive-invoice-audit",
        "aml-review",
        "adeguati-assetti",
        "scissione-guidata",
        "invoice-xml",
        "centrale-rischi-review",
        "composizione-negoziata",
        "rating-legalita",
    } and tool in {
        "vera_workspace_save",
        "vera_workspace_apply",
        "vera_workspace_draft_save",
    }:
        raise ValueError(
            "This workflow uses immutable proposals and its explicit complete professional decision service"
        )
    if tool.startswith("vera_workspace_esg_"):
        from types import SimpleNamespace

        if tool.startswith("vera_workspace_esg_author_"):
            from native_esg_authoring import dispatch as esg_dispatch
        else:
            from native_esg import dispatch as esg_dispatch

        return esg_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("esg-reporting-assurance"),
            SimpleNamespace(**globals()),
        )
    if tool.startswith("vera_workspace_cnc_"):
        from types import SimpleNamespace

        if tool.startswith("vera_workspace_cnc_authenticated_"):
            from native_cnc_authenticated import dispatch as cnc_dispatch
        elif tool.startswith("vera_workspace_cnc_history_"):
            from native_cnc_history import dispatch as cnc_dispatch
        else:
            from native_cnc import dispatch as cnc_dispatch

        return cnc_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("composizione-negoziata"),
            SimpleNamespace(**globals()),
        )
    if tool.startswith("vera_workspace_management_"):
        from types import SimpleNamespace

        if tool.startswith("vera_workspace_management_author_"):
            from native_management_authoring import dispatch as management_dispatch
        elif tool.startswith("vera_workspace_management_commentary_"):
            from native_management_commentary import dispatch as management_dispatch
        else:
            from native_management_execution import dispatch as management_dispatch

        return management_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("management-control-pack"),
            SimpleNamespace(**globals(), archive_root=module_root("studio-archive")),
        )
    if tool.startswith("vera_workspace_variance_"):
        from types import SimpleNamespace

        if tool.startswith("vera_workspace_variance_author_"):
            from native_variance_authoring import dispatch as variance_dispatch
        elif tool.startswith("vera_workspace_variance_narrative_"):
            from native_variance_narrative import dispatch as variance_dispatch
        elif tool.startswith("vera_workspace_variance_review_"):
            from native_variance_review import dispatch as variance_dispatch
        else:
            from native_variance import dispatch as variance_dispatch

        return variance_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("variance-analysis"),
            SimpleNamespace(
                archive_root=module_root("studio-archive"),
                node_executable=workbench_module()._node_executable,
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if binding["workflow_id"] in {
        "variance-analysis",
        "management-control-pack",
    } and tool in {
        "vera_workspace_save",
        "vera_workspace_apply",
        "vera_workspace_draft_save",
        "vera_workspace_draft_clear",
    }:
        raise ValueError(
            "This workflow preserves immutable calculations; use its exact native setup and maintained professional review workflow"
        )
    if tool.startswith("vera_workspace_valuation_"):
        from types import SimpleNamespace

        from native_valuation import dispatch as valuation_dispatch

        if tool.startswith("vera_workspace_valuation_review_"):
            from native_valuation_review import dispatch as valuation_dispatch
        elif tool.startswith("vera_workspace_valuation_author_"):
            from native_valuation_authoring import dispatch as valuation_dispatch

        return valuation_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("business-valuation"),
            SimpleNamespace(
                archive_root=module_root("studio-archive"),
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if tool.startswith("vera_workspace_business_plan_"):
        from types import SimpleNamespace

        from native_business_planning import dispatch as planning_dispatch

        return planning_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("business-planning"),
            SimpleNamespace(
                archive_root=module_root("studio-archive"),
                owned_archive=config["mode"] == "studio-archive",
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if tool.startswith("vera_workspace_treasury_"):
        from types import SimpleNamespace

        from native_treasury_preparation import dispatch as treasury_dispatch

        return treasury_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("treasury-forecast"),
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if tool.startswith("vera_workspace_sales_plan_"):
        from types import SimpleNamespace

        from native_sales_plan import dispatch as sales_dispatch

        return sales_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("sales-plan"),
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if binding["workflow_id"] == "sales-plan" and tool in {
        "vera_workspace_save",
        "vera_workspace_apply",
        "vera_workspace_draft_save",
    }:
        raise ValueError(
            "Sales Plan keeps immutable confirmed cases; revise assumptions through its maintained workflow"
        )
    if tool.startswith("vera_workspace_lipe_"):
        from types import SimpleNamespace

        from native_lipe import dispatch as lipe_dispatch

        return lipe_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("lipe"),
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if binding["workflow_id"] == "lipe" and tool in {
        "vera_workspace_save",
        "vera_workspace_apply",
        "vera_workspace_draft_save",
    }:
        raise ValueError(
            "LIPE preserves immutable reviewed cases; professional changes and signed approval remain in its maintained workflow"
        )
    if tool.startswith("vera_workspace_bank_"):
        from types import SimpleNamespace

        from native_bank_preparation import dispatch as bank_dispatch

        return bank_dispatch(
            tool,
            args,
            binding,
            loaded,
            module_root("journal-bank-reconciliation"),
            SimpleNamespace(
                read_json=read_json,
                digest=digest,
                ui_state_directory=ui_state_directory,
                write_lock=write_lock,
                atomic_json=atomic_json,
                load_binding=load_binding,
            ),
        )
    if binding.get(
        "component", binding["workflow_id"]
    ) == "financial-analysis" and tool in {
        "vera_workspace_save",
        "vera_workspace_apply",
    }:
        raise ValueError(
            "Financial Analysis has no mutable review service; update its professional contracts through the maintained workflow"
        )
    if tool == "vera_workspace_resume_context":
        return {
            key: binding[key]
            for key in (
                "work_ref",
                "client_id",
                "engagement_id",
                "run_id",
                "workflow_id",
            )
        }
    if tool == "vera_workspace_outputs":
        if binding["workflow_id"] in {
            "sales-plan",
            "lipe",
            "aml-review",
            "adeguati-assetti",
            "scissione-guidata",
            "invoice-xml",
            "centrale-rischi-review",
        }:
            if not args.get("revision") or not args.get("source_ref"):
                raise ValueError(
                    "Choose the exact immutable calculation or professional record revision before opening files"
                )
            current = snapshot(binding, loaded, args)
            if current["data"].get("authoring_recovery_required"):
                raise ValueError(
                    "Interrupted AML authoring requires recovery before output closure"
                )
            directory = output / current["data"]["selection"]["source_ref"]
            if binding["workflow_id"] in {
                "aml-review",
                "adeguati-assetti",
                "scissione-guidata",
                "invoice-xml",
            }:
                directory = output
            return {
                "status": (
                    "unfinalized_invoice_export"
                    if binding["workflow_id"] == "invoice-xml"
                    else (
                        "unfinalized_scissione_review"
                        if binding["workflow_id"] == "scissione-guidata"
                        else (
                            "unfinalized_assetti_review"
                            if binding["workflow_id"] == "adeguati-assetti"
                            else (
                                "unfinalized_aml_review"
                                if binding["workflow_id"] == "aml-review"
                                else "unfinalized_calculation"
                            )
                        )
                    )
                ),
                "outputs": [
                    {"name": name, "path": str(directory / name)}
                    for name in current["data"]["artifacts"]
                ],
            }
        return {"outputs": outputs(binding, loaded)}
    if tool == "vera_workspace_draft_read":
        path = draft_path(output, config["actor_id"], create=False)
        return {"draft": read_json(path) if path.exists() else None}
    if tool in {
        "vera_workspace_save",
        "vera_workspace_apply",
        "vera_workspace_draft_save",
        "vera_workspace_archive_execute",
        "vera_workspace_open_items_regenerate",
    }:
        if "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","):
            raise PermissionError("Reviewer authority is required")
        if loaded["run"]["status"] != "running":
            raise ValueError("Resume the Studio Archive run before saving")
        with write_lock(output):
            if tool == "vera_workspace_draft_save":
                current = snapshot(binding, loaded, args)
                draft = {
                    "work_ref": binding["work_ref"],
                    "revision": current["revision"],
                    "item_id": args.get("item_id"),
                    "source_ref": args.get("source_ref"),
                    "fields": args["fields"],
                }
                atomic_json(draft_path(output, config["actor_id"]), draft)
                return {"draft_saved": True}
            if args.get("human_reviewed") is not True:
                raise ValueError("Explicit human review is required")
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid submission key")
            receipt = ui_state_directory(output) / (
                "submission-" + digest([config["actor_id"], key]) + ".json"
            )
            fingerprint = digest(
                {"tool": tool, "actor": config["actor_id"], "args": args}
            )
            if receipt.exists():
                saved = read_json(receipt)
                if saved["request_sha256"] != fingerprint:
                    raise ValueError("Submission key was used for a different request")
                return saved["result"]
            current = snapshot(binding, loaded, args)
            if tool == "vera_workspace_open_items_regenerate":
                if current["workflow"] != "open-item-reconciliation":
                    raise ValueError("Regeneration requires an open-item run")
                if not args.get("expected_predecessor_checkpoint"):
                    raise ValueError("Separate predecessor checkpoint is required")
                regenerated = open_item_review(
                    review_directory(output, current["workflow"]),
                    "regenerate",
                    args,
                    Path(loaded["context_path"]),
                )
                result = {
                    **regenerated,
                    "saved": True,
                    "status": "regenerated",
                    "revision": output_revision(output, current["workflow"]),
                }
            elif tool == "vera_workspace_archive_execute":
                if current["workflow"] != "archive-organization":
                    raise ValueError(
                        "Archive execution requires an archive-organization run"
                    )
                if args.get("execution_approved") is not True or args.get("item_id"):
                    raise ValueError(
                        "Separate explicit approval of the complete archive operation is required"
                    )
                operation = args.get("operation")
                if operation not in {"apply", "rollback"}:
                    raise ValueError("Unknown archive execution operation")
                execution = current["data"]["archive_execution"]
                if not execution["approved_plan"]:
                    raise ValueError(
                        "Compile the professionally reviewed plan before execution"
                    )
                command = [
                    sys.executable,
                    str(
                        module_root("archive-organization")
                        / "scripts/archive_organization.py"
                    ),
                    operation,
                    "--client-engagement",
                    str(loaded["context_path"]),
                ]
                if operation == "apply":
                    command += [
                        "--approved-plan",
                        str(output / "approved_plan.json"),
                        "--explicit-approval",
                    ]
                completed = subprocess.run(
                    command, text=True, capture_output=True, timeout=120, check=False
                )
                response = json.loads(completed.stdout)
                if completed.returncode:
                    raise ValueError(
                        response.get("error", {}).get("message")
                        or "Archive execution was refused"
                    )
                result = {
                    "saved": True,
                    "status": response["status"],
                    "revision": output_revision(output, current["workflow"]),
                }
            elif current["kind"] == "treasury":
                from treasury_session import review_session

                if tool == "vera_workspace_apply":
                    review = args["review"]
                    if review["proposal_sha256"] != current["data"]["proposal_sha256"]:
                        raise ValueError("The reviewed proposal changed")
                    result = review_session(
                        output,
                        expected_record_sha256=current["revision"],
                        review=review,
                    )
                else:
                    result = review_session(
                        output,
                        expected_record_sha256=current["revision"],
                        decisions=selected_decisions(current, args),
                    )
                result = {
                    "saved": True,
                    "revision": result["record_sha256"],
                    "status": result["status"],
                }
            elif current["kind"] == "bilancio":
                if tool != "vera_workspace_save":
                    raise ValueError(
                        "Accounts approval remains in the professional workflow"
                    )
                result = bilancio_call(
                    "xbrl_workspace_review_issue",
                    {
                        "case_id": binding["case_id"],
                        "revision_id": current["revision"],
                        "issue_id": args["item_id"],
                        "action": args["action"],
                        "reason": args["reason"],
                        "human_reviewed": True,
                        "idempotency_key": key,
                    },
                )
                result = {
                    "saved": True,
                    "revision": result["saved"]["revision_id"],
                    "status": result["saved"]["state"],
                }
            else:
                helper = workbench_module()
                adapter = current["data"]["adapter"]
                # Existing review tools replace the complete decision set. Merge
                # from authoritative readback so editing one row retains others.
                previous = (current["data"].get("ui_decisions") or {}).get(
                    "decisions", []
                )
                merged = {row["item_id"]: row for row in previous}
                for row in selected_decisions(current, args):
                    merged[row["item_id"]] = row
                posted = {
                    "decisions": list(merged.values()),
                    "reviewer": config["actor_id"],
                    **(
                        {
                            "expected_predecessor_checkpoint": args[
                                "expected_predecessor_checkpoint"
                            ]
                        }
                        if args.get("expected_predecessor_checkpoint")
                        else {}
                    ),
                }
                directory = review_directory(output, current["workflow"])
                if current["workflow"] == "open-item-reconciliation":
                    result = open_item_review(
                        directory,
                        "apply" if tool == "vera_workspace_apply" else "save",
                        posted,
                    )
                elif current["workflow"] == "report-builder":
                    result = report_review(
                        output,
                        directory,
                        loaded["run"]["run_id"],
                        "apply" if tool == "vera_workspace_apply" else "save",
                        posted,
                    )
                elif current["workflow"] == "concordato-plan-review":
                    result = concordato_review(
                        output,
                        directory,
                        loaded,
                        "apply" if tool == "vera_workspace_apply" else "save",
                        posted,
                    )
                else:
                    result = helper.call_review_tool(
                        helper.LocalReviewWorkbench(
                            module_root(current["workflow"]), directory
                        ),
                        adapter[
                            (
                                "applyTool"
                                if tool == "vera_workspace_apply"
                                else "saveTool"
                            )
                        ],
                        posted,
                    )
                if result.get("ok") is False:
                    raise ValueError(str(result.get("error", "Review was not saved")))
                result = {
                    "saved": True,
                    "revision": output_revision(output, current["workflow"]),
                    "status": "applied" if tool.endswith("apply") else "saved",
                }
            atomic_json(receipt, {"request_sha256": fingerprint, "result": result})
            draft_path(output, config["actor_id"]).unlink(missing_ok=True)
            return result
    current = snapshot(binding, loaded, args)
    if tool == "vera_workspace_explain":
        if not current["selection"]:
            raise ValueError("Select one exact item before requesting an explanation")
        if current["kind"] == "bilancio":
            return bilancio_call(
                "xbrl_workspace_explain",
                {
                    "case_id": binding["case_id"],
                    "revision_id": current["revision"],
                    "issue_id": args["item_id"],
                    **(
                        {"source_ref": args["source_ref"]}
                        if args.get("source_ref")
                        else {}
                    ),
                },
            )
        evidence = current["selection"]
        if current["kind"] == "financial":
            evidence = {
                "artifact": evidence["title"],
                "purpose": evidence["purpose"],
                "prepared_context": evidence["prepared_context"],
                "source_scope": evidence["source_scope"],
                "professional_boundary": current["data"]["verification"],
                "report_ready": False,
            }
        elif current["kind"] == "sales":
            evidence = {
                "selected_record": evidence,
                "calculation_status": current["data"]["status"],
                "professional_boundary": current["data"]["verification"],
                "report_ready": False,
            }
        elif current["kind"] == "lipe":
            evidence = {
                "selected_record": evidence,
                "calculation_status": current["data"]["status"],
                "data_origin": current["data"]["data_origin"],
                "qualification": current["data"]["qualification"],
                "export_status": current["data"]["export_status"],
                "professional_boundary": current["data"]["verification"],
            }
        elif current["kind"] in {"aml", "assetti", "scissione"}:
            evidence = {
                "selected_record": evidence,
                "status": current["data"]["status"],
                "jurisdiction": current["data"].get("jurisdiction", "IT"),
                "as_of": current["data"]["as_of"],
                "assurance_limit": current["data"].get(
                    "assurance_limit", current["data"]["verification"]
                ),
                "professional_boundary": current["data"]["verification"],
            }
        if current["workflow"] in {
            "journal-sampling",
            "open-item-reconciliation",
            "check-entries",
            "journal-bank-reconciliation",
            "client-file-preparation",
            "concordato-plan-review",
        }:
            evidence = selected_model_context(current, output, loaded)
        result = {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "untrusted_evidence": evidence,
            "instruction": "Explain this exact selection; never save, approve or execute a decision from this read.",
        }
        if len(json.dumps(result).encode()) > 64_000:
            raise ValueError("Selected context is oversized")
        if (
            current["kind"] == "workbench"
            and output_revision(output, current["workflow"]) != current["revision"]
        ):
            raise ValueError("State changed during explanation: reopen this run")
        return result
    if tool != "vera_workspace_view":
        raise ValueError("Unknown workspace operation")
    return current


def main() -> None:
    request = json.loads(sys.stdin.read(MAX_BYTES + 1))
    result = dispatch(request["tool"], request["arguments"])
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
