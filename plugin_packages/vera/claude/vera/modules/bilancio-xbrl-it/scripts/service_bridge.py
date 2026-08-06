#!/usr/bin/env python3
"""One-shot JSON bridge from the MCP server to the authenticated case service."""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from access_control import RequestContext
from case_service import CaseService
from file_security import scanner_from_json

__all__ = ["main"]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUTORY_RULE_PACKS = (
    PLUGIN_ROOT / "rulepacks" / "it" / "statutory-forms-2016.1.json",
    PLUGIN_ROOT / "rulepacks" / "it" / "statutory-forms-2026.1.json",
)
DEFAULT_DISCLOSURE_RULE_PACK = (
    PLUGIN_ROOT / "rulepacks" / "it" / "disclosures-2026.1.json"
)


def _trusted_rule_pack(environment_key: str, default_path: Path) -> dict[str, Any]:
    """Load one deployment-selected rule pack from a regular local file."""

    configured = Path(os.environ.get(environment_key, str(default_path)))
    if configured.is_symlink() or not configured.is_file():
        raise ValueError(f"Configured rule pack is unavailable: {environment_key}")
    payload = json.loads(configured.resolve().read_bytes())
    if not isinstance(payload, dict):
        raise ValueError(f"Configured rule pack is not an object: {environment_key}")
    return payload


def _trusted_statutory_rule_packs() -> list[dict[str, Any]]:
    """Load the deployment registry of effective statutory-form packs."""

    configured = os.environ.get("VERA_XBRL_STATUTORY_RULE_PACK", "").strip()
    paths = (Path(configured),) if configured else DEFAULT_STATUTORY_RULE_PACKS
    packs = [
        _trusted_rule_pack("VERA_XBRL_STATUTORY_RULE_PACK", path) for path in paths
    ]
    if len({str(pack.get("id")) for pack in packs}) != len(packs):
        raise ValueError("Configured statutory rule-pack identifiers must be unique")
    return packs


def _effective_statutory_rule_pack(
    packs: Sequence[Mapping[str, Any]], period_start: str
) -> dict[str, Any]:
    """Resolve exactly one deployment-controlled pack for a reporting period."""

    start = date.fromisoformat(period_start)
    matches = [
        pack
        for pack in packs
        if date.fromisoformat(str(pack["effective_from"]))
        <= start
        <= date.fromisoformat(str(pack["effective_to"]))
    ]
    if len(matches) != 1:
        raise ValueError(
            "Reporting period must resolve to exactly one configured statutory rule pack"
        )
    return dict(matches[0])


def _locked_statutory_rule_pack(
    packs: Sequence[Mapping[str, Any]], locked_id: str
) -> dict[str, Any]:
    """Resolve exactly one deployment-controlled pack already locked to a case."""

    matches = [pack for pack in packs if str(pack.get("id")) == locked_id]
    if len(matches) != 1:
        raise ValueError(
            "The case statutory rule pack is not available in the deployment registry"
        )
    return dict(matches[0])


def _context() -> RequestContext:
    required = {
        "storage": os.environ.get("VERA_XBRL_STORAGE_ROOT", ""),
        "tenant": os.environ.get("VERA_XBRL_TENANT_ID", ""),
        "actor": os.environ.get("VERA_XBRL_ACTOR_ID", ""),
        "roles": os.environ.get("VERA_XBRL_ROLES", ""),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise PermissionError(
            f"Authenticated XBRL service environment is incomplete: {', '.join(missing)}"
        )
    return RequestContext(
        tenant_id=required["tenant"],
        actor_id=required["actor"],
        roles=tuple(
            item.strip() for item in required["roles"].split(",") if item.strip()
        ),
        originating_interface="codex-mcp",
    )


def _mutation(
    service: CaseService,
    context: RequestContext,
    arguments: Mapping[str, Any],
    operation: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return service.mutate(
        context,
        str(arguments["case_id"]),
        operation,
        payload,
        str(arguments["revision_id"]),
        str(arguments["idempotency_key"]),
    )


def _dispatch(
    service: CaseService,
    context: RequestContext,
    tool: str,
    arguments: Mapping[str, Any],
    statutory_rule_packs: Sequence[Mapping[str, Any]],
    disclosure_rule_pack: Mapping[str, Any],
) -> Any:
    if tool == "xbrl_case_create":
        statutory_rule_pack = _effective_statutory_rule_pack(
            statutory_rule_packs,
            str(arguments["payload"]["period"]["start"]),
        )
        return service.create(
            context,
            arguments["payload"],
            statutory_rule_pack,
            str(arguments["idempotency_key"]),
        )
    if tool == "xbrl_document_ingest":
        kind = str(arguments["document_kind"])
        operations = {
            "TRIAL_BALANCE": "ingest",
            "PDF_TRIAL_BALANCE": "ingest_pdf",
            "PRIOR_XBRL": "ingest_prior_xbrl",
        }
        if kind not in operations:
            raise ValueError(f"Unsupported XBRL document kind: {kind}")
        operation = operations[kind]
        return _mutation(
            service,
            context,
            arguments,
            operation,
            {
                "source_path": arguments["source_path"],
                "sheet": arguments.get("sheet"),
                "ocr_enabled": arguments.get("ocr_enabled", True),
                "ocr_language": arguments.get("ocr_language", "it"),
            },
        )
    if tool == "xbrl_case_analyze":
        operation = str(arguments["operation"])
        operation_payload = dict(arguments["payload"])
        if operation == "determine_forms":
            summary = service.get(context, str(arguments["case_id"]))
            statutory_rule_pack = _locked_statutory_rule_pack(
                statutory_rule_packs,
                str(summary["rule_pack_versions"]["statutory_rule_pack"]),
            )
            operation_payload["rule_pack"] = dict(statutory_rule_pack)
        elif operation == "activate_disclosures":
            operation_payload["rule_pack"] = dict(disclosure_rule_pack)
        return _mutation(
            service,
            context,
            arguments,
            operation,
            operation_payload,
        )
    if tool == "xbrl_mapping_get_review_packet":
        return service.get(context, str(arguments["case_id"]), "mappings")
    if tool == "xbrl_mapping_apply_decisions":
        return _mutation(
            service,
            context,
            arguments,
            "apply_mappings",
            {"decisions": arguments["decisions"]},
        )
    if tool == "xbrl_questionnaire_get":
        return service.get(context, str(arguments["case_id"]), "questions")
    if tool == "xbrl_questionnaire_submit":
        return _mutation(
            service,
            context,
            arguments,
            "record_answers",
            {"answers": arguments["answers"]},
        )
    if tool == "xbrl_draft_generate":
        return _mutation(
            service,
            context,
            arguments,
            str(arguments["operation"]),
            arguments["payload"],
        )
    if tool == "xbrl_case_validate":
        return _mutation(service, context, arguments, "validate", {})
    if tool == "xbrl_case_prepare_xbrl_review":
        return _mutation(service, context, arguments, "prepare_xbrl_review", {})
    if tool == "xbrl_case_approve":
        return _mutation(
            service,
            context,
            arguments,
            "approve",
            {"declaration": arguments["declaration"]},
        )
    if tool == "xbrl_case_export":
        return _mutation(service, context, arguments, "export", {})
    if tool == "xbrl_case_get_workpaper":
        return service.get(context, str(arguments["case_id"]), "workpaper")
    if tool == "xbrl_case_artifact_download_grant":
        return service.issue_artifact_download(
            context,
            str(arguments["case_id"]),
            str(arguments["artifact_id"]),
            str(arguments["idempotency_key"]),
            ttl_seconds=int(arguments.get("ttl_seconds", 300)),
        )
    if tool == "xbrl_case_get_intelligence_packet":
        return service.intelligence_packet(
            context,
            str(arguments["case_id"]),
            str(arguments["task"]),
            [str(item) for item in arguments.get("subject_ids", [])],
        )
    if tool == "xbrl_case_record_intelligence":
        return _mutation(
            service,
            context,
            arguments,
            "record_intelligence",
            {
                "task": arguments["task"],
                "subject_ids": arguments.get("subject_ids", []),
                "output": arguments["output"],
                "model_metadata": arguments["model_metadata"],
            },
        )
    if tool == "xbrl_case_enqueue_job":
        return service.enqueue_job(
            context,
            str(arguments["case_id"]),
            str(arguments["job_id"]),
            str(arguments["operation"]),
            arguments.get("payload", {}),
            str(arguments["revision_id"]),
            max_attempts=int(arguments.get("max_attempts", 3)),
        )
    if tool == "xbrl_case_job_get":
        return service.get_job(
            context,
            str(arguments["case_id"]),
            str(arguments["job_id"]),
        )
    if tool == "xbrl_case_get_review_view":
        return service.review_view(
            context,
            str(arguments["case_id"]),
            str(arguments["view"]),
            offset=int(arguments.get("offset", 0)),
            limit=int(arguments.get("limit", 200)),
        )
    raise ValueError(f"Unsupported MCP tool: {tool}")


def main() -> int:
    """Read one request and emit one compact JSON response."""

    try:
        request = json.loads(sys.stdin.read())
        context = _context()
        statutory_rule_packs = _trusted_statutory_rule_packs()
        disclosure_rule_pack = _trusted_rule_pack(
            "VERA_XBRL_DISCLOSURE_RULE_PACK", DEFAULT_DISCLOSURE_RULE_PACK
        )
        catalogue = os.environ.get("VERA_XBRL_TAXONOMY_CATALOGUE", "")
        package = os.environ.get("VERA_XBRL_TAXONOMY_PACKAGE", "")
        input_root = os.environ.get("VERA_XBRL_INPUT_ROOT", "")
        presentation_rule_pack = os.environ.get(
            "VERA_XBRL_STATUTORY_PRESENTATION_RULE_PACK", ""
        )
        schedule_taxonomy_rule_pack = os.environ.get(
            "VERA_XBRL_SCHEDULE_TAXONOMY_RULE_PACK", ""
        )
        scanner = scanner_from_json(
            os.environ.get("VERA_XBRL_SCANNER_COMMAND_JSON", ""),
            engine=os.environ.get("VERA_XBRL_SCANNER_ENGINE", "host-scanner"),
            signature_version=os.environ.get(
                "VERA_XBRL_SCANNER_SIGNATURE_VERSION", "host-managed"
            ),
            timeout_seconds=int(
                os.environ.get("VERA_XBRL_SCANNER_TIMEOUT_SECONDS", "120")
            ),
        )
        service = CaseService(
            Path(os.environ["VERA_XBRL_STORAGE_ROOT"]),
            Path(catalogue) if catalogue else None,
            Path(package) if package else None,
            Path(input_root) if input_root else None,
            scanner,
            require_malware_scan=True,
            artifact_signing_secret=(
                os.environ["VERA_XBRL_ARTIFACT_SIGNING_SECRET"].encode("utf-8")
                if os.environ.get("VERA_XBRL_ARTIFACT_SIGNING_SECRET")
                else None
            ),
            artifact_download_base_url=(
                os.environ.get("VERA_XBRL_ARTIFACT_DOWNLOAD_BASE_URL") or None
            ),
            retention_days=(
                int(os.environ["VERA_XBRL_RETENTION_DAYS"])
                if os.environ.get("VERA_XBRL_RETENTION_DAYS")
                else None
            ),
            taxonomy_registry_path=(
                Path(os.environ["VERA_XBRL_TAXONOMY_REGISTRY"])
                if os.environ.get("VERA_XBRL_TAXONOMY_REGISTRY")
                else None
            ),
            statutory_presentation_rule_pack_path=(
                Path(presentation_rule_pack) if presentation_rule_pack else None
            ),
            schedule_taxonomy_rule_pack_path=(
                Path(schedule_taxonomy_rule_pack)
                if schedule_taxonomy_rule_pack
                else None
            ),
        )
        result = _dispatch(
            service,
            context,
            str(request["tool"]),
            request.get("arguments", {}),
            statutory_rule_packs,
            disclosure_rule_pack,
        )
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0
    except (KeyError, OSError, PermissionError, TypeError, ValueError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
