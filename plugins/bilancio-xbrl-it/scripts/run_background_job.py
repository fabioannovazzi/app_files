#!/usr/bin/env python3
"""Run one queued Bilancio case operation through the trusted worker boundary."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from access_control import RequestContext
from case_service import CaseService
from file_security import scanner_from_json
from intelligence_runner import intelligence_runner_from_json

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Execute one integrity-checked job and emit its compact status resource."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--worker-id", default="bilancio-background-worker")
    parser.add_argument("--taxonomy-catalogue", type=Path)
    parser.add_argument("--taxonomy-package", type=Path)
    parser.add_argument("--taxonomy-registry", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--scanner-command-json")
    parser.add_argument("--scanner-engine")
    parser.add_argument("--scanner-signature-version")
    parser.add_argument("--intelligence-command-json")
    args = parser.parse_args(argv)
    context = RequestContext(
        tenant_id=args.tenant_id,
        actor_id=args.worker_id,
        roles=("SERVICE_WORKER",),
        originating_interface="background-worker",
    )
    try:
        scanner = scanner_from_json(
            (
                args.scanner_command_json
                if args.scanner_command_json is not None
                else os.environ.get("VERA_XBRL_SCANNER_COMMAND_JSON", "")
            ),
            engine=args.scanner_engine
            or os.environ.get("VERA_XBRL_SCANNER_ENGINE", "host-scanner"),
            signature_version=args.scanner_signature_version
            or os.environ.get("VERA_XBRL_SCANNER_SIGNATURE_VERSION", "host-managed"),
            timeout_seconds=int(
                os.environ.get("VERA_XBRL_SCANNER_TIMEOUT_SECONDS", "120")
            ),
        )
        intelligence_runner = intelligence_runner_from_json(
            (
                args.intelligence_command_json
                if args.intelligence_command_json is not None
                else os.environ.get("VERA_XBRL_INTELLIGENCE_COMMAND_JSON", "")
            ),
            timeout_seconds=int(
                os.environ.get("VERA_XBRL_INTELLIGENCE_TIMEOUT_SECONDS", "120")
            ),
        )
        service = CaseService(
            args.storage_root,
            args.taxonomy_catalogue,
            args.taxonomy_package,
            args.input_root,
            scanner,
            require_malware_scan=True,
            taxonomy_registry_path=args.taxonomy_registry,
            intelligence_runner=intelligence_runner,
        )
        result = service.run_job(context, args.case_id, args.job_id)
    except (OSError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
