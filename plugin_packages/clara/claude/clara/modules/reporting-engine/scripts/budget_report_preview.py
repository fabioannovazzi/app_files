"""Serve one exact native Clara budget dashboard on loopback for local review."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

__all__ = ["report_bytes", "make_server", "main"]

CLARA_ROOT = Path(__file__).resolve().parents[3]
COMPONENT = next(
    path
    for path in (
        CLARA_ROOT / "modules/management-control-pack",
        CLARA_ROOT.parent / "management-control-pack",
    )
    if (path / "assets/budget-report.js").is_file()
)
REPORT = "management_control_dashboard.html"


class _ReportScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[str] = []
        self.in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"iframe", "object", "embed", "base", "form"} or any(
            name.startswith("on") or name == "srcdoc" for name, _ in attrs
        ):
            raise ValueError("Unexpected active content in budget dashboard")
        if tag == "script":
            if attrs or self.in_script:
                raise ValueError("Only the bundled inline report script is supported")
            self.in_script = True
            self.scripts.append("")

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self.scripts[-1] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_script = False


def report_bytes(report: Path) -> bytes:
    """Verify native output identity and the exact bundled presentation script."""
    if report.name != REPORT:
        raise ValueError("Select the native management_control_dashboard.html")
    receipt = json.loads((report.parent / "execution_receipt.json").read_text())
    if (
        receipt.get("schema_version") != "vera.management_control_execution_receipt.v1"
        or receipt.get("workflow_id") != "management-control-pack"
    ):
        raise ValueError("A native budget execution receipt is required")
    entries = [row for row in receipt["outputs"] if row.get("path") == REPORT]
    content = report.read_bytes()
    if (
        len(entries) != 1
        or entries[0].get("sha256") != hashlib.sha256(content).hexdigest()
        or entries[0].get("byte_count") != len(content)
    ):
        raise ValueError("The dashboard no longer matches its native receipt")
    parser = _ReportScripts()
    parser.feed(content.decode("utf-8"))
    parser.close()
    script = (COMPONENT / "assets/budget-report.js").read_text()
    if parser.in_script or parser.scripts != [script]:
        raise ValueError("The dashboard must use the current bundled report script")
    return content


def make_server(report: Path) -> tuple[ThreadingHTTPServer, str]:
    """Pin the report and receipt; serve no source files or other routes."""
    report = report.resolve()
    original = report_bytes(report)
    receipt = report.parent / "execution_receipt.json"
    receipt_hash = hashlib.sha256(receipt.read_bytes()).digest()
    script = (COMPONENT / "assets/budget-report.js").read_bytes()
    script_hash = base64.b64encode(hashlib.sha256(script).digest()).decode("ascii")
    route = "/" + secrets.token_urlsafe(24) + "/report.html"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != route:
                self.send_error(404)
                return
            try:
                content = report_bytes(report)
                if (
                    content != original
                    or hashlib.sha256(receipt.read_bytes()).digest() != receipt_hash
                ):
                    raise ValueError("Report changed; reopen its current preview")
            except (OSError, ValueError, KeyError, TypeError):
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
                "form-action 'none'; frame-ancestors 'none'; sandbox allow-scripts allow-modals",
            )
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    return server, f"http://127.0.0.1:{server.server_port}{route}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        server, url = make_server(args.report)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    with server:
        print(json.dumps({"url": url, "read_only": True}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
