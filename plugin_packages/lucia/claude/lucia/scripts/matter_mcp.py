"""Native matter-opening review with app-only evidence and guarded saved decisions."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as SchemaError

__all__ = ["MatterApp", "main"]

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = next(
    p
    for p in (ROOT / "modules/apertura-pratica", ROOT.parent / "apertura-pratica")
    if p.is_dir()
)
sys.path.insert(0, str(COMPONENT / "scripts"))
for vendor in (
    ROOT / "vendor/modules",
    ROOT / "modules/studio-archive/vendor/modules",
    ROOT.parent / "_shared/vendor/modules",
):
    if (vendor / "vera_assurance").is_dir():
        sys.path.insert(0, str(vendor))
        break
from apertura_pratica_core import (
    ValidationError,
    _validate_decisions,
    canonical_json_hash,
    load_json,
    read_pending_review,
    review_payload_hash,
    utc_now,
    validate_run,
    write_json,
)
from vera_assurance.serialization import exclusive_file_lock

URI = "ui://lucia/matter-opening-v1.html"
MIME = "text/html;profile=mcp-app"


def _stamp(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "absent"


class MatterApp:
    """Bind review decisions to the exact selected matter and pending revision."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        text = {"type": "string", "minLength": 1, "maxLength": 4000}
        self.tools = [
            {
                "name": "lucia_matter_open",
                "title": "Fascicolo nuova pratica",
                "description": "Open a prepared matter-opening review in the explicitly selected absolute run directory. Full evidence stays app-only. Saving retains pending decisions; applying and professional acceptance remain separate explicit steps.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"run_dir": text},
                    "required": ["run_dir"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": True, "openWorldHint": False},
                "_meta": {"ui": {"visibility": ["app", "model"], "resourceUri": URI}},
            },
            {
                "name": "lucia_matter_save",
                "title": "Salva il riesame",
                "description": "Save the lawyer's explicit pending review against the current intake, review and pending-decision revisions. Never applies decisions or opens another matter.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session": text,
                        "request_id": text,
                        "reviewer": text,
                        "decisions": {
                            "type": "array",
                            "maxItems": 500,
                            "items": {"type": "object"},
                        },
                    },
                    "required": ["session", "request_id", "reviewer", "decisions"],
                    "additionalProperties": False,
                },
                "annotations": {
                    "readOnlyHint": False,
                    "destructiveHint": False,
                    "openWorldHint": False,
                },
                "_meta": {"ui": {"visibility": ["app"]}},
            },
        ]

    @staticmethod
    def _load(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        validate_run(root)
        intake, review = load_json(root / "matter_intake.json"), load_json(
            root / "review_payload.json"
        )
        if (
            review.get("intake_sha256") != canonical_json_hash(intake)
            or review.get("run_id") != intake["run_id"]
        ):
            raise ValueError(
                "Prepara di nuovo il riesame per la versione corrente della pratica."
            )
        return intake, review

    @staticmethod
    def _result(session: str, root: Path, review: dict[str, Any]) -> dict[str, Any]:
        pending, status = read_pending_review(root, review)
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Fascicolo pronto nel pannello locale di Lucia. Le decisioni salvate restano da applicare.",
                }
            ],
            "structuredContent": {"status": "ready"},
            "_meta": {
                "matter": {
                    "session": session,
                    "review": review,
                    "review_payload_sha256": review_payload_hash(review),
                    "pending_review": pending,
                    "pending_review_status": status,
                }
            },
        }

    def open(self, directory: str) -> dict[str, Any]:
        root = Path(directory)
        if not root.is_absolute() or not root.is_dir():
            raise ValueError("Seleziona la cartella assoluta della pratica preparata.")
        root = root.resolve()
        intake, review = self._load(root)
        session = secrets.token_urlsafe(32)
        self.sessions[session] = {
            "root": root,
            "identity": (root.stat().st_dev, root.stat().st_ino),
            "intake": canonical_json_hash(intake),
            "review": review_payload_hash(review),
            "pending": _stamp(root / "pending_review_decisions.json"),
            "requests": {},
        }
        return self._result(session, root, review)

    def save(self, args: dict[str, Any]) -> dict[str, Any]:
        state = self.sessions.get(args["session"])
        if state is None:
            raise ValueError("Riapri la pratica dalla chat prima di salvare.")
        with exclusive_file_lock(state["root"] / ".native-review.lock"):
            return self._save_locked(args, state)

    def _save_locked(
        self, args: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        """Serialize the compare-and-save across panels and local processes."""
        signature = hashlib.sha256(
            json.dumps(args, sort_keys=True).encode()
        ).hexdigest()
        previous = state["requests"].get(args["request_id"])
        if previous:
            if previous[0] != signature:
                raise ValueError("La richiesta è cambiata; riapri il riesame.")
            return previous[1]
        root = state["root"]
        if (
            root.resolve() != root
            or (root.stat().st_dev, root.stat().st_ino) != state["identity"]
        ):
            raise ValueError("La cartella della pratica è cambiata.")
        intake, review = self._load(root)
        path = root / "pending_review_decisions.json"
        if path.is_symlink() or any(
            (
                canonical_json_hash(intake) != state["intake"],
                review_payload_hash(review) != state["review"],
                _stamp(path) != state["pending"],
            )
        ):
            raise ValueError(
                "La pratica o le decisioni sono cambiate. Riapri il riesame prima di salvare."
            )
        reviewer = args["reviewer"].strip()
        if not reviewer:
            raise ValueError("Indica il revisore.")
        pending = {
            "schema_version": "1.0",
            "workflow": "apertura-pratica",
            "run_id": intake["run_id"],
            "intake_sha256": state["intake"],
            "review_payload_sha256": state["review"],
            "reviewer": reviewer,
            "decision_source": "local_workbench",
            "confirmed_by_user": True,
            "saved_at": utc_now(),
            "decisions": args["decisions"],
        }
        _validate_decisions(pending, intake=intake, review_payload=review)
        choices = {item["id"]: item["allowed_actions"] for item in review["items"]}
        if any(
            decision["action"] not in choices[decision["item_id"]]
            for decision in args["decisions"]
        ):
            raise ValueError(
                "Una decisione non è disponibile per l’elemento selezionato."
            )
        write_json(path, pending)
        state["pending"] = _stamp(path)
        result = self._result(args["session"], root, review)
        state["requests"][args["request_id"]] = (signature, result)
        return result

    @staticmethod
    def resource() -> dict[str, Any]:
        html = (COMPONENT / "assets/apertura-pratica-review-widget.html").read_text()
        font = next(
            path
            for path in (
                ROOT
                / "modules/comunicazione-professionale/assets/fonts/InstrumentSans-Regular.ttf",
                ROOT.parent
                / "comunicazione-professionale/assets/fonts/InstrumentSans-Regular.ttf",
            )
            if path.is_file()
        )
        face = (
            "@font-face{font-family:'Instrument Sans';src:url(data:font/ttf;base64,"
            + base64.b64encode(font.read_bytes()).decode()
            + ") format('truetype');font-weight:400 700;font-display:swap}"
        )
        html = html.replace("</style>", face + "</style>", 1).replace(
            "<head>",
            "<head><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'\">",
            1,
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
        method, params = request["method"], request.get("params", {})
        if method == "initialize":
            return {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "lucia-matter-opening", "version": "1.0.0"},
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tools}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        if method == "resources/list":
            return {
                "resources": [
                    {"uri": URI, "name": "Fascicolo nuova pratica", "mimeType": MIME}
                ]
            }
        if method == "resources/read" and params.get("uri") == URI:
            return self.resource()
        if method == "tools/call":
            tool = next(
                (tool for tool in self.tools if tool["name"] == params.get("name")),
                None,
            )
            if tool:
                args = params.get("arguments", {})
                Draft202012Validator(tool["inputSchema"]).validate(args)
                return (
                    self.open(args["run_dir"])
                    if tool["name"] == "lucia_matter_open"
                    else self.save(args)
                )
        raise ValueError("Operazione non disponibile")


def main() -> None:
    """Handle MCP without sending private paths or raw exception data to chat."""
    app = MatterApp()
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
            SchemaError,
        ):
            response["result"] = {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": "Impossibile salvare o aprire questa versione. Riapri dalla chat il riesame corrente della pratica.",
                    }
                ],
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
