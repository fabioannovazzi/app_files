#!/usr/bin/env python3
"""Serve generated review-workbench widgets with local decision write-back."""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

__all__ = [
    "LocalReviewWorkbench",
    "build_session_payload",
    "call_review_tool",
    "create_review_http_server",
    "main",
    "render_review_html",
    "serve_review",
]

ROOT = Path(__file__).resolve().parents[1]
MAX_ITEMS = 3000
MAX_POST_BYTES = 1_000_000
ALLOWED_ACTIONS = {
    "accept",
    "reject",
    "edit",
    "mark_unclear",
    "request_more_documents",
    "skip",
}
LOGGER = logging.getLogger(__name__)
NODE_OVERRIDE_ENV = "MPARANZA_REVIEW_NODE"
REVIEW_TOKEN_HEADER = "X-Mparanza-Review-Token"


@dataclass(frozen=True)
class LocalReviewWorkbench:
    """Plugin/run paths for a local review-workbench session."""

    plugin_dir: Path
    output_dir: Path

    @property
    def plugin(self) -> str:
        """Return the plugin directory name."""

        return self.plugin_dir.name

    @property
    def adapter_path(self) -> Path:
        """Return the workbench adapter path."""

        return self.plugin_dir / "assets" / "review-workbench-adapter.json"

    @property
    def mcp_server_path(self) -> Path:
        """Return the available plugin review-tool server path."""

        candidates = (
            self.plugin_dir / "mcp" / "server.cjs",
            self.plugin_dir / "scripts" / "review_mcp_server.cjs",
        )
        return next((path for path in candidates if path.is_file()), candidates[0])


def _read_json_object(path: Path, *, required: bool = False) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise ValueError(f"{path.name} is required in the output folder")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path.name} is not readable JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _plugin_dir_from_args(plugin: str | None, plugin_dir: str | None) -> Path:
    if plugin_dir:
        directory = Path(plugin_dir).expanduser().resolve()
    elif plugin:
        repo_plugin_dir = (ROOT / "plugins" / plugin).resolve()
        directory = repo_plugin_dir if repo_plugin_dir.exists() else ROOT.resolve()
    else:
        candidates = [
            Path(__file__).resolve().parents[1],
            Path.cwd().resolve(),
            Path.cwd().resolve().parent,
        ]
        directory = next(
            (
                candidate
                for candidate in candidates
                if (candidate / ".codex-plugin").exists()
            ),
            Path(),
        )
        if not directory:
            raise ValueError(
                "pass --plugin or --plugin-dir when not running inside a plugin"
            )
    if not (directory / ".codex-plugin" / "plugin.json").exists():
        raise ValueError(f"plugin directory is invalid: {directory}")
    if plugin:
        manifest = _read_json_object(directory / ".codex-plugin" / "plugin.json")
        manifest_name = manifest.get("name")
        if manifest_name != plugin:
            raise ValueError(
                f'plugin directory is for "{manifest_name}", not "{plugin}"'
            )
    if not (directory / "assets" / "review-workbench-adapter.json").exists():
        raise ValueError(
            f"plugin has no generated review workbench adapter: {directory}"
        )
    if not LocalReviewWorkbench(
        plugin_dir=directory,
        output_dir=directory,
    ).mcp_server_path.is_file():
        raise ValueError(
            f"plugin has no review-tool server for decision write-back: {directory}"
        )
    return directory


def _output_dir(path: str | Path) -> Path:
    directory = Path(path).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f"output folder does not exist: {directory}")
    return directory


def _validate_loopback_host(host: str) -> str:
    normalized = host.strip()
    if normalized.lower() == "localhost":
        return normalized
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise ValueError(
            "review server host must be localhost or a loopback IP"
        ) from exc
    if not address.is_loopback:
        raise ValueError("review server host must be localhost or a loopback IP")
    return normalized


def _review_url(host: str, port: int) -> str:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return f"http://{host}:{port}/review"
    if address.version == 6:
        return f"http://[{host}]:{port}/review"
    return f"http://{host}:{port}/review"


def _server_class(host: str) -> type[ThreadingHTTPServer]:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return ThreadingHTTPServer
    if address.version != 6:
        return ThreadingHTTPServer

    class IPv6ThreadingHTTPServer(ThreadingHTTPServer):
        address_family = socket.AF_INET6

    return IPv6ThreadingHTTPServer


def _adapter(workbench: LocalReviewWorkbench) -> dict[str, Any]:
    return _read_json_object(workbench.adapter_path, required=True)


def _widget_path(workbench: LocalReviewWorkbench) -> Path:
    html_files = sorted(
        path
        for path in (workbench.plugin_dir / "assets").glob("*.html")
        if path.is_file()
    )
    if len(html_files) != 1:
        raise ValueError(
            f"expected exactly one review widget HTML asset for {workbench.plugin}"
        )
    return html_files[0]


def _validate_review_payload(
    workbench: LocalReviewWorkbench,
    adapter: dict[str, Any],
    review_payload: Any,
) -> dict[str, Any]:
    if not isinstance(review_payload, dict):
        raise ValueError("review_payload must be a JSON object")
    if review_payload.get("plugin") != workbench.plugin:
        raise ValueError(f'review_payload.plugin must be "{workbench.plugin}"')
    for field_name in ("schema_version", "workflow", "run_id"):
        if (
            not isinstance(review_payload.get(field_name), str)
            or not review_payload[field_name].strip()
        ):
            raise ValueError(f"review_payload.{field_name} must be a non-empty string")
    items = review_payload.get("items")
    if not isinstance(items, list):
        raise ValueError("review_payload.items must be an array")
    if len(items) > MAX_ITEMS:
        raise ValueError(f"review_payload.items exceeds {MAX_ITEMS} items")
    if review_payload.get("item_count") != len(items):
        raise ValueError(
            "review_payload.item_count must equal review_payload.items.length"
        )
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"review_payload.items[{index}] must be an object")
        for field_name in ("id", "item_type", "title"):
            if (
                not isinstance(item.get(field_name), str)
                or not item[field_name].strip()
            ):
                raise ValueError(
                    f"review_payload.items[{index}].{field_name} must be a non-empty string"
                )
        allowed_actions = item.get("allowed_actions")
        if not isinstance(allowed_actions, list) or not allowed_actions:
            raise ValueError(
                f"review_payload.items[{index}].allowed_actions must be a non-empty array"
            )
        for action in allowed_actions:
            if action not in ALLOWED_ACTIONS:
                raise ValueError(
                    "review_payload.items"
                    f"[{index}].allowed_actions contains unsupported action: {action}"
                )
    if not isinstance(adapter.get("saveTool"), str) or not adapter["saveTool"]:
        raise ValueError("review-workbench adapter is missing saveTool")
    if not isinstance(adapter.get("applyTool"), str) or not adapter["applyTool"]:
        raise ValueError("review-workbench adapter is missing applyTool")
    return review_payload


def _empty_ui_decisions(review_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": review_payload.get("schema_version", "1.0"),
        "plugin": review_payload.get("plugin"),
        "workflow": review_payload.get("workflow"),
        "run_id": review_payload["run_id"],
        "decided_at": None,
        "decision_source": "not_collected",
        "review_payload_path": "review_payload.json",
        "decisions": [],
        "decision_count": 0,
        "item_count": review_payload["item_count"],
        "status": "pending_review",
    }


def _raw_session_payload(workbench: LocalReviewWorkbench) -> dict[str, Any]:
    """Load server-owned run artifacts without exposing them to the browser."""

    adapter = _adapter(workbench)
    run_intake = _read_json_object(
        workbench.output_dir / "run_intake.json",
        required=True,
    )
    review_payload = _validate_review_payload(
        workbench,
        adapter,
        _read_json_object(workbench.output_dir / "review_payload.json", required=True),
    )
    ui_decisions = _read_json_object(workbench.output_dir / "ui_decisions.json")
    final_artifacts = _read_json_object(workbench.output_dir / "final_artifacts.json")
    if run_intake.get("run_id") and run_intake["run_id"] != review_payload["run_id"]:
        raise ValueError("run_intake.run_id must match review_payload.run_id")
    return {
        "widget_type": adapter.get("widgetType", f"{workbench.plugin}_review"),
        "run_intake": run_intake,
        "review_payload": review_payload,
        "ui_decisions": ui_decisions or _empty_ui_decisions(review_payload),
        "final_artifacts": final_artifacts or None,
        "decision_policy": {
            "save_tool": adapter["saveTool"],
            "apply_tool": adapter["applyTool"],
            "can_persist": True,
            "fallback": "local_review_server",
        },
    }


def _render_tool_name(adapter: dict[str, Any]) -> str:
    save_tool = adapter.get("saveTool")
    if (
        not isinstance(save_tool, str)
        or not save_tool.startswith("save_")
        or not save_tool.endswith("_decisions")
    ):
        raise ValueError("review-workbench adapter saveTool cannot resolve render tool")
    return f"render_{save_tool.removeprefix('save_').removesuffix('_decisions')}_review"


def _is_absolute_path(value: str) -> bool:
    """Return whether a string is an absolute POSIX or Windows path."""

    return Path(value).is_absolute() or bool(re.match(r"^[A-Za-z]:[\\/]", value))


def _known_absolute_paths(value: Any) -> tuple[str, ...]:
    """Collect exact absolute paths present in server-owned review artifacts."""

    paths: set[str] = set()

    def visit(candidate: Any) -> None:
        if isinstance(candidate, dict):
            for item in candidate.values():
                visit(item)
        elif isinstance(candidate, list):
            for item in candidate:
                visit(item)
        elif isinstance(candidate, str) and _is_absolute_path(candidate):
            paths.add(candidate)

    visit(value)
    return tuple(sorted(paths, key=len, reverse=True))


def _sanitize_browser_payload(
    value: Any,
    *,
    field: str | None = None,
    redactions: tuple[str, ...] = (),
) -> Any:
    """Remove server-only paths and private QA text from any plugin render result."""

    empty_path_lists = {"input_paths", "local_files_read"}
    dropped_fields = {"output_dir", "required_text"}
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key in dropped_fields:
                continue
            if key in empty_path_lists:
                sanitized[key] = []
                continue
            sanitized[key] = _sanitize_browser_payload(
                item,
                field=key,
                redactions=redactions,
            )
        return sanitized
    if isinstance(value, list):
        return [
            _sanitize_browser_payload(item, field=field, redactions=redactions)
            for item in value
        ]
    if isinstance(value, str):
        sanitized_text = value
        for absolute_path in redactions:
            sanitized_text = sanitized_text.replace(absolute_path, "<local-path>")
        if _is_absolute_path(sanitized_text):
            return "<local-path>"
        return sanitized_text
    return value


def build_session_payload(workbench: LocalReviewWorkbench) -> dict[str, Any]:
    """Return the plugin-rendered, browser-safe local review session."""

    raw_session = _raw_session_payload(workbench)
    rendered = _mcp_tool_result(
        workbench,
        _render_tool_name(_adapter(workbench)),
        {
            "run_intake": raw_session["run_intake"],
            "review_payload": raw_session["review_payload"],
            "ui_decisions": raw_session["ui_decisions"],
            "final_artifacts": raw_session["final_artifacts"],
        },
    )
    if rendered.get("ok") is False:
        raise ValueError(str(rendered.get("error") or "plugin render tool failed"))
    rendered_review = rendered.get("review_payload")
    if not isinstance(rendered_review, dict):
        raise ValueError("plugin render tool returned no review_payload")
    if (
        rendered_review.get("plugin") != workbench.plugin
        or rendered_review.get("run_id") != raw_session["review_payload"]["run_id"]
    ):
        raise ValueError("plugin render tool returned a mismatched review session")
    redactions = _known_absolute_paths(
        {
            "session": raw_session,
            "workbench_output_dir": workbench.output_dir.resolve().as_posix(),
        }
    )
    sanitized = _sanitize_browser_payload(rendered, redactions=redactions)
    if not isinstance(sanitized, dict):
        raise ValueError("sanitized plugin render result must remain an object")
    return sanitized


def _script_json(value: Any) -> str:
    """Encode JSON for an executable script without allowing tag termination."""

    return (
        json.dumps(value, ensure_ascii=False, default=str)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _bridge_html(workbench: LocalReviewWorkbench, session_token: str) -> str:
    payload_json = _script_json(
        build_session_payload(workbench),
    )
    plugin_json = _script_json(workbench.plugin)
    token_json = _script_json(session_token)
    return f"""<script>
    (function () {{
      const serverPayload = {payload_json};
      const pluginName = {plugin_json};
      const reviewToken = {token_json};
      const stateKey = `${{pluginName}}:${{serverPayload.review_payload?.run_id || "run"}}`;
      function readState() {{
        try {{ return JSON.parse(window.sessionStorage.getItem(stateKey) || "null"); }}
        catch {{ return null; }}
      }}
      window.openai = {{
        toolOutput: serverPayload,
        widgetState: readState(),
        setWidgetState(value) {{
          try {{ window.sessionStorage.setItem(stateKey, JSON.stringify(value || null)); }}
          catch {{ }}
        }},
        async callTool(name, args) {{
          const response = await fetch("/api/call-tool", {{
            method: "POST",
            headers: {{
              "Content-Type": "application/json",
              "{REVIEW_TOKEN_HEADER}": reviewToken,
            }},
            body: JSON.stringify({{ name, args: args || {{}} }}),
          }});
          const result = await response.json();
          if (!response.ok || result.ok === false) {{
            throw new Error(result.error || `Local review server call failed: ${{name}}`);
          }}
          if (result.ui_decisions) serverPayload.ui_decisions = result.ui_decisions;
          if (result.final_artifacts) serverPayload.final_artifacts = result.final_artifacts;
          if (result.applied_decisions) serverPayload.applied_decisions = result.applied_decisions;
          return result;
        }},
      }};
    }}());
</script>
  """


def render_review_html(
    workbench: LocalReviewWorkbench,
    *,
    session_token: str | None = None,
) -> str:
    """Render the generated widget with a local ``window.openai`` bridge."""

    html = _widget_path(workbench).read_text(encoding="utf-8")
    needle = "  <script>\n    const CONFIG = "
    if needle not in html:
        raise ValueError("review widget script insertion point not found")
    token = session_token or secrets.token_urlsafe(32)
    return html.replace(needle, _bridge_html(workbench, token) + needle, 1)


def _server_tool_args(
    workbench: LocalReviewWorkbench,
    posted_args: dict[str, Any],
) -> dict[str, Any]:
    session = _raw_session_payload(workbench)
    decisions = posted_args.get("decisions")
    if decisions is not None and not isinstance(decisions, list):
        raise ValueError("decisions must be an array when provided")
    args = {
        "run_intake": session["run_intake"],
        "review_payload": session["review_payload"],
        "ui_decisions": session["ui_decisions"],
        "final_artifacts": session["final_artifacts"],
        "decision_source": "local_review_server",
    }
    if decisions is not None:
        args["decisions"] = decisions
    reviewer = posted_args.get("reviewer")
    if isinstance(reviewer, str) and reviewer.strip():
        args["reviewer"] = reviewer.strip()
    return args


def _codex_runtime_node_candidates() -> list[Path]:
    """Return bounded Node.js candidates supplied by local Codex runtimes."""

    runtime_root = Path.home() / ".cache" / "codex-runtimes"
    if not runtime_root.is_dir():
        return []
    return sorted(runtime_root.glob("*/dependencies/node/bin/node"), reverse=True)


def _node_executable() -> str:
    override = os.environ.get(NODE_OVERRIDE_ENV)
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve().as_posix()
        raise ValueError(
            f"{NODE_OVERRIDE_ENV} must point to an executable Node.js file"
        )
    node = shutil.which("node")
    if node is not None:
        return node
    for candidate in _codex_runtime_node_candidates():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve().as_posix()
    raise ValueError(
        "Node.js is required to call the plugin review-tool server; install Node.js "
        f"or set {NODE_OVERRIDE_ENV} to its executable path"
    )


def _mcp_tool_result(
    workbench: LocalReviewWorkbench, name: str, args: dict[str, Any]
) -> dict[str, Any]:
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": args},
    }
    completed = subprocess.run(
        [_node_executable(), workbench.mcp_server_path.as_posix(), "--stdio"],
        input=json.dumps(message) + "\n",
        capture_output=True,
        text=True,
        check=False,
        cwd=workbench.plugin_dir,
        timeout=30,
    )
    if completed.returncode != 0:
        raise ValueError((completed.stderr or completed.stdout).strip())
    responses = [
        json.loads(line) for line in completed.stdout.splitlines() if line.strip()
    ]
    response = next((item for item in responses if item.get("id") == 1), None)
    if response is None:
        raise ValueError("MCP server returned no tools/call response")
    if "error" in response:
        raise ValueError(str(response["error"].get("message") or response["error"]))
    result = response.get("result")
    if not isinstance(result, dict):
        raise ValueError("MCP tools/call result must be a JSON object")
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    return result


def call_review_tool(
    workbench: LocalReviewWorkbench,
    name: str,
    posted_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call the plugin MCP review tool using server-owned run artifacts."""

    if not isinstance(name, str) or not name.strip():
        raise ValueError("tool name must be a non-empty string")
    args = _server_tool_args(workbench, posted_args or {})
    adapter = _adapter(workbench)
    allowed_tools = {adapter["saveTool"], adapter["applyTool"]}
    if name not in allowed_tools:
        raise ValueError(f"unsupported local review tool: {name}")
    result = _mcp_tool_result(workbench, name, args)
    redactions = _known_absolute_paths(
        {
            "tool_args": args,
            "workbench_output_dir": workbench.output_dir.resolve().as_posix(),
        }
    )
    sanitized = _sanitize_browser_payload(result, redactions=redactions)
    if not isinstance(sanitized, dict):
        raise ValueError("sanitized plugin tool result must remain an object")
    return sanitized


def create_review_http_server(
    workbench: LocalReviewWorkbench,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[ThreadingHTTPServer, str]:
    """Return a configured local review server and its review URL."""

    build_session_payload(workbench)
    safe_host = _validate_loopback_host(host)
    session_token = secrets.token_urlsafe(32)
    httpd = _server_class(safe_host)(
        (safe_host, port),
        _handler(workbench, session_token=session_token),
    )
    actual_port = httpd.server_address[1]
    return httpd, _review_url(safe_host, actual_port)


def _handler(
    workbench: LocalReviewWorkbench,
    *,
    session_token: str,
) -> type[BaseHTTPRequestHandler]:
    class ReviewWorkbenchHandler(BaseHTTPRequestHandler):
        server_version = "LocalReviewWorkbench/1.0"

        def log_message(self, format_string: str, *args: object) -> None:
            LOGGER.info("%s - %s", self.client_address[0], format_string % args)

        def _json_response(
            self,
            payload: dict[str, Any],
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _html_response(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            route = urlparse(self.path).path
            try:
                if route in {"/", "/review", "/review_ui.html"}:
                    self._html_response(
                        render_review_html(
                            workbench,
                            session_token=session_token,
                        )
                    )
                    return
                if route == "/api/session":
                    self._json_response(build_session_payload(workbench))
                    return
                if route == "/api/health":
                    session = build_session_payload(workbench)
                    self._json_response(
                        {
                            "ok": True,
                            "plugin": workbench.plugin,
                            "run_id": session["review_payload"]["run_id"],
                        }
                    )
                    return
                self.send_error(HTTPStatus.NOT_FOUND.value, "Not found")
            except (OSError, TypeError, ValueError) as exc:
                self._json_response(
                    {"ok": False, "error": str(exc)},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def do_POST(self) -> None:
            route = urlparse(self.path).path
            if route != "/api/call-tool":
                self.send_error(HTTPStatus.NOT_FOUND.value, "Not found")
                return
            try:
                supplied_token = self.headers.get(REVIEW_TOKEN_HEADER, "")
                if not secrets.compare_digest(supplied_token, session_token):
                    self._json_response(
                        {"ok": False, "error": "invalid local review session token"},
                        status=HTTPStatus.FORBIDDEN,
                    )
                    return
                content_type = self.headers.get("Content-Type", "")
                media_type = content_type.partition(";")[0].strip().lower()
                if media_type != "application/json":
                    self._json_response(
                        {
                            "ok": False,
                            "error": "Content-Type must be application/json",
                        },
                        status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                    )
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_POST_BYTES:
                    raise ValueError(f"request body exceeds {MAX_POST_BYTES} bytes")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                name = payload.get("name")
                args = (
                    payload.get("args") if isinstance(payload.get("args"), dict) else {}
                )
                self._json_response(call_review_tool(workbench, str(name or ""), args))
            except json.JSONDecodeError as exc:
                self._json_response(
                    {"ok": False, "error": f"invalid JSON request: {exc}"},
                    status=HTTPStatus.BAD_REQUEST,
                )
            except (OSError, subprocess.SubprocessError, TypeError, ValueError) as exc:
                self._json_response(
                    {"ok": False, "error": str(exc)},
                    status=HTTPStatus.BAD_REQUEST,
                )

    return ReviewWorkbenchHandler


def serve_review(
    workbench: LocalReviewWorkbench,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
) -> None:
    """Serve the review UI on localhost and optionally open a browser."""

    httpd, url = create_review_http_server(workbench, host=host, port=port)
    LOGGER.info("%s review server: %s", workbench.plugin, url)
    LOGGER.info("Output folder: %s", workbench.output_dir)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Stopping %s review server", workbench.plugin)
    finally:
        httpd.server_close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Open a generated plugin review workbench in a local browser and "
            "persist decisions into the run output folder."
        )
    )
    parser.add_argument("output_dir", help="Run output folder with review_payload.json")
    parser.add_argument(
        "--plugin", help="Plugin name under the repository plugins folder"
    )
    parser.add_argument("--plugin-dir", help="Explicit plugin directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Start the server without opening the browser automatically.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parser().parse_args(argv)
    try:
        workbench = LocalReviewWorkbench(
            plugin_dir=_plugin_dir_from_args(args.plugin, args.plugin_dir),
            output_dir=_output_dir(args.output_dir),
        )
        serve_review(
            workbench,
            host=args.host,
            port=args.port,
            open_browser=not args.no_open,
        )
    except (OSError, TypeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
