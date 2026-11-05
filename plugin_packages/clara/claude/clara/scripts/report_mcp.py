"""Read-only native report app with exact receipt and bundled-script checks."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

__all__ = ["ReportApp", "main"]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules/reporting-engine/scripts"))
from budget_report_preview import report_bytes

URI = "ui://clara/budget-report-v1.html"
MIME = "text/html;profile=mcp-app"


class ReportApp:
    """Pin only reports explicitly opened by this local app session."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.tools = []
        for operation, field, title in [
            ("open", "report", "Budget e previsioni"),
            ("refresh", "session", "Aggiorna il report"),
        ]:
            self.tools.append(
                {
                    "name": "clara_report_" + operation,
                    "title": title,
                    "description": (
                        "Open the explicitly selected absolute native budget-dashboard path in the local app. Verifies the execution receipt and exact bundled script. Does not publish or expose sources or report data to the model."
                        if operation == "open"
                        else "Recheck the exact app-bound report and receipt, rejecting changes; no arbitrary path or new file can be selected."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            field: {"type": "string", "minLength": 1, "maxLength": 4000}
                        },
                        "required": [field],
                        "additionalProperties": False,
                    },
                    "annotations": {"readOnlyHint": True, "openWorldHint": False},
                    "_meta": {
                        "ui": (
                            {"visibility": ["app", "model"], "resourceUri": URI}
                            if operation == "open"
                            else {"visibility": ["app"]}
                        )
                    },
                }
            )

    @staticmethod
    def _result(session: str, content: bytes) -> dict[str, Any]:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Report verificato pronto nel pannello locale di Clara.",
                }
            ],
            "structuredContent": {"status": "ready"},
            "_meta": {"report": {"session": session, "html": content.decode("utf-8")}},
        }

    def open(self, report: str) -> dict[str, Any]:
        path = Path(report)
        if not path.is_absolute():
            raise ValueError("Select the report with its absolute path.")
        path = path.resolve()
        content = report_bytes(path)
        receipt = path.parent / "execution_receipt.json"
        session = secrets.token_urlsafe(32)
        self.sessions[session] = {
            "path": path,
            "content": content,
            "receipt": hashlib.sha256(receipt.read_bytes()).digest(),
        }
        return self._result(session, content)

    def refresh(self, session: str) -> dict[str, Any]:
        state = self.sessions.get(session)
        if state is None:
            raise ValueError("Reopen the selected report from the chat.")
        content = report_bytes(state["path"])
        receipt = state["path"].parent / "execution_receipt.json"
        if (
            content != state["content"]
            or hashlib.sha256(receipt.read_bytes()).digest() != state["receipt"]
        ):
            raise ValueError(
                "The report or receipt changed. Reopen the current report from the chat."
            )
        return self._result(session, content)

    @staticmethod
    def resource() -> dict[str, Any]:
        html = (ROOT / "ui/report.html").read_text()
        if "__FONT__" in html:
            # Development source; release builders embed the canonical local font.
            font = (
                ROOT.parent
                / "_shared/vendor/modules/courseware/assets/InstrumentSans-Regular.ttf"
            )
            html = html.replace(
                "__FONT__", base64.b64encode(font.read_bytes()).decode()
            )
        return {
            "contents": [
                {
                    "uri": URI,
                    "mimeType": MIME,
                    "text": html,
                    "_meta": {
                        "ui": {"csp": {"connectDomains": [], "resourceDomains": []}},
                        "openai/ui": {
                            "preferredDisplayMode": "fullscreen",
                            "availableDisplayModes": ["inline", "fullscreen"],
                        },
                    },
                }
            ]
        }

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        params = request.get("params", {})
        method = request["method"]
        if method == "initialize":
            return {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "clara-reports", "version": "1.0.0"},
            }
        if method == "ping":
            return {}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        if method == "resources/list":
            return {
                "resources": [
                    {"uri": URI, "name": "Budget e previsioni", "mimeType": MIME}
                ]
            }
        if method == "resources/read" and params.get("uri") == URI:
            return self.resource()
        if method == "tools/list":
            return {"tools": self.tools}
        if method == "tools/call":
            tool = next(
                (tool for tool in self.tools if tool["name"] == params.get("name")),
                None,
            )
            if tool is not None:
                args = params.get("arguments", {})
                Draft202012Validator(tool["inputSchema"]).validate(args)
                return (
                    self.open(args["report"])
                    if tool["name"].endswith("_open")
                    else self.refresh(args["session"])
                )
        raise ValueError("Unsupported operation")


def main() -> None:
    """Run the private local app transport without logging report contents."""
    app = ReportApp()
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except ValueError:
            continue
        if not isinstance(request, dict) or "id" not in request:
            continue
        response = {"jsonrpc": "2.0", "id": request["id"]}
        try:
            response["result"] = app.dispatch(request)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            StopIteration,
            ValidationError,
        ):
            response["result"] = {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": "Impossibile verificare questo report. Riapri dalla chat il report corrente con la sua ricevuta di esecuzione.",
                    }
                ],
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
