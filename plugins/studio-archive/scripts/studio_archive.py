#!/usr/bin/env python3
"""Command-line interface for Vera Studio Archive."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from archive_core import (
    CLIENT_WORKFLOW_IDS,
    VERA_CLIENT_WORKFLOW_IDS,
    ArchiveError,
    authorize_studio_google_drive,
    bind_studio_client_google_drive,
    cancel_studio_client_workflow,
    close_studio_client_engagement,
    complete_studio_client_workflow,
    configure_archive,
    create_studio_client,
    create_studio_client_engagement,
    fail_studio_client_workflow,
    finalize_studio_client_workflow,
    get_studio_client_folder,
    import_studio_client_document,
    list_studio_client_engagements,
    list_studio_client_identities,
    match_studio_email_client,
    open_archive_source,
    open_studio_google_drive_source,
    plan_gmail_client_search,
    prepare_studio_client_workflow,
    recover_studio_client_ledger,
    refresh_archive,
    report_studio_client_retention,
    search_archive,
    set_studio_client_identity,
    snapshot_studio_client_folder,
    snapshot_studio_client_google_drive,
    start_check_entries_from_sample,
    start_studio_client_workflow,
    studio_archive_status,
    studio_google_drive_status,
)

__all__ = ["main"]


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser("configure")
    configure.add_argument("--archive-root", type=Path, required=True)

    subparsers.add_parser("status")
    subparsers.add_parser("clients")

    client_folder = subparsers.add_parser("client-folder")
    client_folder.add_argument("--client-id", required=True)

    create_client = subparsers.add_parser("create-client")
    create_client.add_argument("--legal-name", required=True)
    create_client.add_argument("--email-address", action="append", default=[])
    create_client.add_argument("--tax-identifier", action="append", default=[])

    create_engagement = subparsers.add_parser("create-engagement")
    create_engagement.add_argument("--client-id", required=True)
    create_engagement.add_argument("--engagement-label", required=True)

    import_document = subparsers.add_parser("import-document")
    import_document.add_argument("--client-id", required=True)
    import_document.add_argument("--source-path", type=Path, required=True)
    import_document.add_argument(
        "--role", choices=["journal", "source", "support"], required=True
    )
    import_document.add_argument("--engagement-id", required=True)

    engagements = subparsers.add_parser("engagements")
    engagements.add_argument("--client-id", required=True)

    snapshot_folder = subparsers.add_parser("snapshot-client-folder")
    snapshot_folder.add_argument("--client-id", required=True)
    snapshot_folder.add_argument("--engagement-id", required=True)

    authorize_drive = subparsers.add_parser("authorize-google-drive")
    authorize_drive.add_argument("--client-secrets", type=Path, required=True)

    subparsers.add_parser("google-drive-status")

    bind_drive = subparsers.add_parser("bind-google-drive")
    bind_drive.add_argument("--client-id", required=True)
    bind_drive.add_argument("--folder-id", required=True)

    snapshot_drive = subparsers.add_parser("snapshot-google-drive")
    snapshot_drive.add_argument("--client-id", required=True)
    snapshot_drive.add_argument("--engagement-id", required=True)

    open_drive = subparsers.add_parser("open-google-drive")
    open_drive.add_argument("--client-id", required=True)
    open_drive.add_argument("--engagement-id", required=True)
    open_drive.add_argument("--snapshot-input-id", required=True)
    open_drive.add_argument("--file-id", required=True)

    prepare_workflow = subparsers.add_parser("prepare-workflow")
    prepare_workflow.add_argument("--engagement-id", required=True)
    prepare_workflow.add_argument(
        "--workflow-id",
        choices=list(
            CLIENT_WORKFLOW_IDS
            if os.environ.get("LUCIA_ASSURANCE_HOST") == "1"
            else VERA_CLIENT_WORKFLOW_IDS
        ),
        required=True,
    )

    check_entries_handoff = subparsers.add_parser("start-check-entries-from-sample")
    check_entries_handoff.add_argument("--client-id", required=True)
    check_entries_handoff.add_argument("--engagement-id", required=True)
    check_entries_handoff.add_argument("--sample-run-id", required=True)
    check_entries_handoff.add_argument(
        "--support-input-id", action="append", default=[]
    )
    check_entries_handoff.add_argument("--label")
    check_entries_handoff.add_argument("--purpose")
    check_entries_handoff.add_argument("--idempotency-key")
    check_entries_handoff.add_argument("--new-run", action="store_true")
    prepare_workflow.add_argument("--input-id", action="append", default=[])
    prepare_workflow.add_argument(
        "--upstream-artifact",
        action="append",
        default=[],
        help="Exact upstream reference formatted run_id:artifact_id:role.",
    )
    prepare_workflow.add_argument("--label")
    prepare_workflow.add_argument("--purpose")
    prepare_workflow.add_argument(
        "--idempotency-key",
        help="Stable request key; use a different key for each intentionally separate run.",
    )
    prepare_workflow.add_argument(
        "--new-run",
        action="store_true",
        help="Create the explicit-new namespace; retries with the same key remain idempotent.",
    )

    for command in ("start-workflow", "cancel-workflow", "complete-workflow"):
        lifecycle = subparsers.add_parser(command)
        lifecycle.add_argument("--client-id", required=True)
        lifecycle.add_argument("--engagement-id", required=True)
        lifecycle.add_argument("--run-id", required=True)

    fail_workflow = subparsers.add_parser("fail-workflow")
    fail_workflow.add_argument("--client-id", required=True)
    fail_workflow.add_argument("--engagement-id", required=True)
    fail_workflow.add_argument("--run-id", required=True)
    fail_workflow.add_argument("--reason", required=True)

    finalize_workflow = subparsers.add_parser("finalize-workflow")
    finalize_workflow.add_argument("--client-id", required=True)
    finalize_workflow.add_argument("--engagement-id", required=True)
    finalize_workflow.add_argument("--run-id", required=True)
    finalize_workflow.add_argument("--artifacts-json", required=True)

    close_engagement = subparsers.add_parser("close-engagement")
    close_engagement.add_argument("--client-id", required=True)
    close_engagement.add_argument("--engagement-id", required=True)

    subparsers.add_parser("recover-ledger")

    retention = subparsers.add_parser("retention-report")
    retention.add_argument("--client-id", required=True)
    retention.add_argument("--older-than-days", type=int)

    configure_client = subparsers.add_parser("configure-client")
    configure_client.add_argument("--scope-id", required=True)
    configure_client.add_argument("--email-address", action="append", default=[])
    configure_client.add_argument("--legal-name", action="append", default=[])
    configure_client.add_argument("--tax-identifier", action="append", default=[])
    configure_client.add_argument("--replace-orphaned-scope-id")

    refresh = subparsers.add_parser("refresh")
    refresh.add_argument("--rebuild", action="store_true")
    refresh.add_argument("--enable-ocr", action="store_true")

    search = subparsers.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--scope-id", required=True)
    search.add_argument("--limit", type=int, default=10)

    open_source = subparsers.add_parser("open")
    open_source.add_argument("--source-id", required=True)
    open_source.add_argument("--context-chunks", type=int, default=0)

    plan_gmail = subparsers.add_parser("plan-gmail")
    plan_gmail.add_argument("--scope-id", required=True)
    plan_gmail.add_argument("--topic")
    plan_gmail.add_argument("--after")
    plan_gmail.add_argument("--before")

    match_email = subparsers.add_parser("match-email")
    match_email.add_argument("--header-address", action="append", required=True)
    match_email.add_argument("--headers-complete", action="store_true")
    match_email.add_argument("--expected-scope-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute one Studio Archive operation and emit structured JSON."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "configure":
            result = configure_archive(args.archive_root)
        elif args.command == "status":
            result = studio_archive_status()
        elif args.command == "clients":
            result = list_studio_client_identities()
        elif args.command == "client-folder":
            result = get_studio_client_folder(args.client_id)
        elif args.command == "create-client":
            result = create_studio_client(
                args.legal_name,
                email_addresses=args.email_address,
                tax_identifiers=args.tax_identifier,
            )
        elif args.command == "create-engagement":
            result = create_studio_client_engagement(
                args.client_id,
                args.engagement_label,
            )
        elif args.command == "import-document":
            result = import_studio_client_document(
                args.client_id,
                args.source_path,
                args.role,
                engagement_id=args.engagement_id,
            )
        elif args.command == "engagements":
            result = list_studio_client_engagements(args.client_id)
        elif args.command == "snapshot-client-folder":
            result = snapshot_studio_client_folder(
                args.client_id,
                args.engagement_id,
            )
        elif args.command == "authorize-google-drive":
            result = authorize_studio_google_drive(args.client_secrets)
        elif args.command == "google-drive-status":
            result = studio_google_drive_status()
        elif args.command == "bind-google-drive":
            result = bind_studio_client_google_drive(
                args.client_id,
                args.folder_id,
            )
        elif args.command == "snapshot-google-drive":
            result = snapshot_studio_client_google_drive(
                args.client_id,
                args.engagement_id,
            )
        elif args.command == "open-google-drive":
            result = open_studio_google_drive_source(
                args.client_id,
                args.engagement_id,
                args.snapshot_input_id,
                args.file_id,
            )
        elif args.command == "prepare-workflow":
            upstream_artifacts = []
            for raw_reference in args.upstream_artifact:
                parts = raw_reference.split(":", maxsplit=2)
                if len(parts) != 3:
                    raise ArchiveError(
                        "Upstream artifact must be run_id:artifact_id:role."
                    )
                upstream_artifacts.append(
                    {"run_id": parts[0], "artifact_id": parts[1], "role": parts[2]}
                )
            result = prepare_studio_client_workflow(
                args.engagement_id,
                args.workflow_id,
                input_ids=args.input_id,
                upstream_artifacts=upstream_artifacts,
                label=args.label,
                purpose=args.purpose,
                idempotency_key=args.idempotency_key,
                new_run=args.new_run,
            )
        elif args.command == "start-workflow":
            result = start_studio_client_workflow(
                args.client_id, args.engagement_id, args.run_id
            )
        elif args.command == "start-check-entries-from-sample":
            result = start_check_entries_from_sample(
                args.client_id,
                args.engagement_id,
                args.sample_run_id,
                support_input_ids=args.support_input_id,
                label=args.label,
                purpose=args.purpose,
                idempotency_key=args.idempotency_key,
                new_run=args.new_run,
            )
        elif args.command == "fail-workflow":
            result = fail_studio_client_workflow(
                args.client_id, args.engagement_id, args.run_id, args.reason
            )
        elif args.command == "cancel-workflow":
            result = cancel_studio_client_workflow(
                args.client_id, args.engagement_id, args.run_id
            )
        elif args.command == "finalize-workflow":
            artifact_payload = json.loads(args.artifacts_json)
            if not isinstance(artifact_payload, list):
                raise ArchiveError("artifacts-json must contain a JSON array.")
            result = finalize_studio_client_workflow(
                args.client_id,
                args.engagement_id,
                args.run_id,
                artifact_payload,
            )
        elif args.command == "complete-workflow":
            result = complete_studio_client_workflow(
                args.client_id, args.engagement_id, args.run_id
            )
        elif args.command == "close-engagement":
            result = close_studio_client_engagement(args.client_id, args.engagement_id)
        elif args.command == "recover-ledger":
            result = recover_studio_client_ledger()
        elif args.command == "retention-report":
            result = report_studio_client_retention(
                args.client_id, older_than_days=args.older_than_days
            )
        elif args.command == "configure-client":
            result = set_studio_client_identity(
                args.scope_id,
                email_addresses=args.email_address,
                legal_names=args.legal_name,
                tax_identifiers=args.tax_identifier,
                replace_orphaned_scope_id=args.replace_orphaned_scope_id,
            )
        elif args.command == "refresh":
            result = refresh_archive(
                rebuild=args.rebuild,
                enable_ocr=args.enable_ocr,
            )
        elif args.command == "search":
            result = search_archive(
                args.query,
                scope_id=args.scope_id,
                limit=args.limit,
            )
        elif args.command == "open":
            result = open_archive_source(
                args.source_id,
                context_chunks=args.context_chunks,
            )
        elif args.command == "plan-gmail":
            result = plan_gmail_client_search(
                args.scope_id,
                topic=args.topic,
                after=args.after,
                before=args.before,
            )
        else:
            result = match_studio_email_client(
                args.header_address,
                headers_complete=args.headers_complete,
                expected_scope_id=args.expected_scope_id,
            )
    except (ArchiveError, OSError, ValueError, sqlite3.Error) as exc:
        _emit(
            {
                "error": {
                    "code": getattr(exc, "code", "archive_operation_failed"),
                    "message": str(exc),
                }
            }
        )
        return 1
    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
