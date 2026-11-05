"""Native firm-method app: explicitly selected folder, immutable versions, CAS."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
from legal_playbook import ROOT, validate_playbook

__all__ = ["MethodApp", "main"]

URI = "ui://lucia/firm-method-v1.html"
MIME = "text/html;profile=mcp-app"


def _read(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    if len(raw) > 1_000_000:
        raise ValueError("Le istruzioni superano il limite di 1 MB.")
    return validate_playbook(json.loads(raw)), hashlib.sha256(raw).hexdigest()


class MethodApp:
    """Keep app save authority bound to one explicitly selected local folder."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        string = {"type": "string", "minLength": 1, "maxLength": 4000}
        self.tools = [
            {
                "name": "lucia_method_open",
                "title": "Istruzioni dello studio",
                "description": "Open the native firm-method editor in the explicitly selected existing studio folder. Optional filename selects an existing saved version in that folder; omit only to create a declared NDA example to adapt. No client documents are opened. No save occurs until the user saves in the app.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"directory": string, "filename": string},
                    "required": ["directory"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": True, "openWorldHint": False},
                "_meta": {"ui": {"resourceUri": URI, "visibility": ["app", "model"]}},
            },
            {
                "name": "lucia_method_save",
                "title": "Salva le istruzioni",
                "description": "Save a new validated version in the app's selected folder, preserving existing files and rejecting stale or unknown sessions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session": string,
                        "revision": string,
                        "request_id": string,
                        "value": {"type": "object"},
                    },
                    "required": ["session", "revision", "request_id", "value"],
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
        self.tools.append(
            {
                "name": "lucia_method_import",
                "title": "Apri istruzioni salvate",
                "description": "Load a user-selected instruction file into the same explicitly selected folder scope. Does not save or open any path from its content.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"session": string, "value": {"type": "object"}},
                    "required": ["session", "value"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": True, "openWorldHint": False},
                "_meta": {"ui": {"visibility": ["app"]}},
            }
        )

    def _result(self, data: dict[str, Any]) -> dict[str, Any]:
        data = {**data, "directory": str(self.sessions[data["session"]]["directory"])}
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Istruzioni dello studio pronte nell’app locale.",
                }
            ],
            "structuredContent": {"status": "ready"},
            "_meta": {"method": data},
        }

    def open(self, args: dict[str, Any]) -> dict[str, Any]:
        directory = Path(args["directory"])
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError(
                "Seleziona una cartella dello studio esistente con percorso assoluto."
            )
        directory = directory.resolve()
        source = None
        revision = secrets.token_hex(32)
        filename = args.get("filename")
        if filename:
            if Path(filename).name != filename or filename in {".", ".."}:
                raise ValueError("Seleziona un file nella cartella scelta.")
            source = directory / filename
            if source.resolve().parent != directory or source.is_symlink():
                raise ValueError("Il file deve appartenere alla cartella scelta.")
            value, revision = _read(source)
        else:
            value, _ = _read(ROOT / "assets/playbook-nda.json")
        session = secrets.token_urlsafe(32)
        self.sessions[session] = {
            "directory": directory,
            "directory_identity": (directory.stat().st_dev, directory.stat().st_ino),
            "source": source,
            "revision": revision,
            "value": value,
            "requests": {},
        }
        return self._result(
            {
                "session": session,
                "revision": revision,
                "value": value,
                "example": source is None,
                "path": str(source) if source is not None else None,
            }
        )

    def save(self, args: dict[str, Any]) -> dict[str, Any]:
        state = self.sessions.get(args["session"])
        if state is None:
            raise ValueError("Riapri le istruzioni dalla chat prima di salvare.")
        signature = hashlib.sha256(
            json.dumps(args, sort_keys=True).encode()
        ).hexdigest()
        previous = state["requests"].get(args["request_id"])
        if previous:
            if previous[0] != signature:
                raise ValueError(
                    "La richiesta di salvataggio è cambiata; riapri le istruzioni."
                )
            return previous[1]
        if args["revision"] != state["revision"]:
            raise ValueError(
                "La versione è cambiata; riapri le istruzioni prima di salvare."
            )
        directory = state["directory"]
        if (
            directory.resolve() != directory
            or not directory.is_dir()
            or (directory.stat().st_dev, directory.stat().st_ino)
            != state["directory_identity"]
        ):
            raise ValueError("La cartella scelta non è più disponibile.")
        source = state["source"]
        if source is not None and (
            source.is_symlink() or _read(source)[1] != state["revision"]
        ):
            raise ValueError("Il file è cambiato; riapri la versione corrente.")
        value = validate_playbook(json.loads(json.dumps(args["value"])))
        baseline = state["value"]
        if value["id"] == baseline["id"]:
            if (
                value["version"] != baseline["version"]
                or value["derived_from"] != baseline["derived_from"]
            ):
                raise ValueError("Riapri la versione selezionata prima di salvare.")
            value["version"] = baseline["version"] + (value != baseline)
        elif value["version"] != 1 or value["derived_from"] != {
            "id": baseline["id"],
            "version": baseline["version"],
        }:
            raise ValueError(
                "Crea una copia della versione aperta prima di cambiare identità."
            )
        if value == baseline and source is not None:
            return self._result(
                {
                    "session": args["session"],
                    "revision": state["revision"],
                    "value": baseline,
                    "filename": source.name,
                    "path": str(source),
                }
            )
        raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
        if len(raw) > 1_000_000:
            raise ValueError("Le istruzioni superano il limite di 1 MB.")
        target = directory / f"{value['id']}-v{value['version']}.json"
        # Exclusive creation preserves every prior version and rejects collisions.
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
        revision = hashlib.sha256(raw).hexdigest()
        state.update(source=target, revision=revision, value=value)
        result = self._result(
            {
                "session": args["session"],
                "revision": revision,
                "value": value,
                "filename": target.name,
                "path": str(target),
            }
        )
        state["requests"][args["request_id"]] = (signature, result)
        return result

    def import_value(self, args: dict[str, Any]) -> dict[str, Any]:
        previous = self.sessions.get(args["session"])
        if previous is None:
            raise ValueError(
                "Riapri le istruzioni dalla chat prima di caricare un file."
            )
        value = validate_playbook(args["value"])
        if len(json.dumps(value).encode()) > 1_000_000:
            raise ValueError("Le istruzioni superano il limite di 1 MB.")
        session, revision = secrets.token_urlsafe(32), secrets.token_hex(32)
        self.sessions[session] = {
            "directory": previous["directory"],
            "directory_identity": previous["directory_identity"],
            "source": None,
            "revision": revision,
            "value": value,
            "requests": {},
        }
        return self._result({"session": session, "revision": revision, "value": value})

    def resource(self) -> dict[str, Any]:
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
        labels = (ROOT / "scripts/legal_playbook_labels.json").read_text()
        html = (
            (ROOT / "assets/playbook-editor.html")
            .read_text()
            .replace("__FONT_DATA__", base64.b64encode(font.read_bytes()).decode())
            .replace(
                "__LABEL_DATA__", labels.replace("<", "\\u003c").replace("&", "\\u0026")
            )
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

    def dispatch(self, message: dict[str, Any]) -> dict[str, Any]:
        params = message.get("params", {})
        method = message["method"]
        if method == "initialize":
            return {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "lucia-firm-method", "version": "1.0.0"},
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
                    {"uri": URI, "name": "Istruzioni dello studio", "mimeType": MIME}
                ]
            }
        if method == "resources/read" and params.get("uri") == URI:
            return self.resource()
        if method == "tools/call":
            tool = next(
                (tool for tool in self.tools if tool["name"] == params.get("name")),
                None,
            )
            if tool is not None:
                args = params.get("arguments", {})
                Draft202012Validator(tool["inputSchema"]).validate(args)
                if tool["name"] == "lucia_method_open":
                    return self.open(args)
                if tool["name"] == "lucia_method_import":
                    return self.import_value(args)
                return self.save(args)
        raise ValueError("Operazione non disponibile.")


def main() -> None:
    """Serve newline-delimited MCP requests without logging private file data."""
    app = MethodApp()
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except ValueError:
            continue
        if not isinstance(request, dict) or "id" not in request:
            continue
        response: dict[str, Any] = {"jsonrpc": "2.0", "id": request["id"]}
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
            # Validation messages can quote private field values; never echo them.
            text = "Impossibile aprire o salvare questa versione. Verifica i campi e riapri le istruzioni correnti dalla chat. I file già salvati sono conservati."
            response["result"] = {
                "isError": True,
                "content": [{"type": "text", "text": text}],
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
