#!/usr/bin/env python3
"""Open one bound, receipt-verified management report on loopback."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "vendor/modules", ROOT.parent / "_shared/vendor/modules"):
    if (candidate / "vera_assurance").is_dir():
        sys.path.insert(0, str(candidate))
        break

from vera_assurance import AssuranceContractError, load_client_engagement_context_file

REPORT = "management_control_dashboard_reviewed.html"


def report_bytes(context: Path, report: Path) -> bytes:
    """Read the exact declared report; no full pack enters model context."""
    receipt = report.parent / "commentary_receipt.json"
    if report.name != REPORT:
        raise ValueError("Select the current reviewed-draft management dashboard")
    load_client_engagement_context_file(
        context,
        expected_workflow_id="management-control-pack",
        input_paths=[report, receipt],
        allowed_statuses=("running", "ready_for_review", "completed"),
    )
    data = json.loads(receipt.read_text(encoding="utf-8"))
    if (
        data.get("schema_version") != "vera.management_control_commentary_receipt.v1"
        or data.get("workflow_id") != "management-control-pack"
        or data.get("status") != "draft_pending_professional_review"
    ):
        raise ValueError("A native reviewed-draft commentary receipt is required")
    entries = [row for row in data["outputs"] if row["path"] == REPORT]
    content = report.read_bytes()
    if len(entries) != 1 or hashlib.sha256(content).hexdigest() != entries[0]["sha256"]:
        raise ValueError("The report no longer matches its native receipt")
    return content


def make_server(context: Path, report: Path) -> tuple[ThreadingHTTPServer, str]:
    """Serve only a pinned report with the bundled presentation script allowed."""
    original = report_bytes(context, report)
    pinned = hashlib.sha256(original).digest()
    script = (ROOT / "assets/budget-report.js").read_bytes()
    script_hash = base64.b64encode(hashlib.sha256(script).digest()).decode("ascii")
    route = "/" + secrets.token_urlsafe(24) + "/report.html"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != route:
                self.send_error(404)
                return
            try:
                content = report_bytes(context, report)
                if hashlib.sha256(content).digest() != pinned:
                    raise ValueError("Report changed; reopen its current preview")
            except (AssuranceContractError, OSError, ValueError, KeyError, TypeError):
                self.send_error(409, "Report unavailable or changed")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'sha256-"
                + script_hash
                + "'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_args: object) -> None:
            # Do not log the private preview URL or case identity.
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    return server, f"http://127.0.0.1:{server.server_port}{route}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-engagement", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        server, url = make_server(args.client_engagement, args.report)
    except (AssuranceContractError, OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    with server:
        print(json.dumps({"url": url, "read_only": True}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
