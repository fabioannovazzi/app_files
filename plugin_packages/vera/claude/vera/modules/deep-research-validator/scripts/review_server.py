#!/usr/bin/env python3
"""Serve generated review-workbench widgets with local decision write-back."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_helper_environment import local_helper_environment  # noqa: E402


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
REQUIRE_VERA_CUSTOMER_RUN = True
VERA_REVIEW_WORKFLOW_IDS = frozenset(
    {
        "archive-organization",
        "open-item-reconciliation",
        "check-entries",
        "client-file-preparation",
        "concordato-plan-review",
        "deep-research-validator",
        "financial-analysis",
        "journal-bank-reconciliation",
        "journal-sampling",
        "new-client",
        "previdenza-inps",
        "prompt-optimizer",
        "registro-imprese-sari",
        "report-builder",
        "sales-plan",
    }
)


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


def _validate_vera_customer_run(
    workbench: LocalReviewWorkbench,
    *,
    read_only: bool = False,
) -> dict[str, Any] | None:
    """Validate review ownership; only rendering may read a finalized run."""

    if not REQUIRE_VERA_CUSTOMER_RUN:
        return None
    manifest = _read_json_object(
        workbench.plugin_dir / ".codex-plugin" / "plugin.json",
        required=True,
    )
    plugin = manifest.get("name")
    if plugin not in VERA_REVIEW_WORKFLOW_IDS:
        return None
    module_roots = (
        workbench.plugin_dir / "vendor" / "modules",
        workbench.plugin_dir.parent / "_shared" / "vendor" / "modules",
    )
    module_root = next(
        (root for root in module_roots if (root / "vera_assurance").is_dir()),
        None,
    )
    if module_root is None:
        raise ValueError("Vera customer-run validator is unavailable")
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))
    from vera_assurance import (  # noqa: PLC0415
        load_client_engagement_context_file,
        load_client_workflow_context_for_output,
    )

    if read_only:
        output_root = next(
            (
                ancestor
                for ancestor in (workbench.output_dir, *workbench.output_dir.parents)
                if ancestor.name == "outputs"
                and (ancestor.parent / "context.json").is_file()
            ),
            None,
        )
        if output_root is None:
            raise ValueError(
                "workflow output is not inside a portable customer-folder run"
            )
        return load_client_engagement_context_file(
            output_root.parent / "context.json",
            expected_workflow_id=str(plugin),
            output_dir=workbench.output_dir,
            allowed_statuses=("running", "ready_for_review", "completed"),
        )
    return load_client_workflow_context_for_output(
        workbench.output_dir,
        expected_workflow_id=str(plugin),
    )


def _with_vera_customer_context(
    workbench: LocalReviewWorkbench,
    args: dict[str, Any],
    *,
    read_only: bool = False,
) -> dict[str, Any]:
    """Add the live customer-run path to one server-owned MCP call."""

    client_context = _validate_vera_customer_run(workbench, read_only=read_only)
    if client_context is None:
        return args
    context_path = client_context.get("context_path")
    if not isinstance(context_path, str) or not context_path:
        raise ValueError("Vera customer-run context path is unavailable")
    return {**args, "client_engagement": context_path}








def _adapter(workbench: LocalReviewWorkbench) -> dict[str, Any]:
    return _read_json_object(workbench.adapter_path, required=True)




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
    decisions = {
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
    content_sha256 = review_payload.get("content_sha256")
    if isinstance(content_sha256, str) and content_sha256:
        decisions["review_payload_content_sha256"] = content_sha256
    return decisions


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
    applied_decisions = _read_json_object(
        workbench.output_dir / "applied_decisions.json"
    )
    final_artifacts = _read_json_object(workbench.output_dir / "final_artifacts.json")
    if run_intake.get("run_id") and run_intake["run_id"] != review_payload["run_id"]:
        raise ValueError("run_intake.run_id must match review_payload.run_id")
    if applied_decisions and (
        applied_decisions.get("run_id") != review_payload["run_id"]
        or applied_decisions.get("plugin") != workbench.plugin
    ):
        raise ValueError("Applied decisions must belong to this review run")
    return {
        "widget_type": adapter.get("widgetType", f"{workbench.plugin}_review"),
        "run_intake": run_intake,
        "review_payload": review_payload,
        "ui_decisions": ui_decisions or _empty_ui_decisions(review_payload),
        "applied_decisions": applied_decisions or None,
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
    # Run-intake assumptions are server-owned context and may contain client names
    # or other private case labels. They are not required to operate the browser
    # review controls, so exclude the field rather than guessing which text is safe.
    dropped_fields = {"assumptions", "output_dir", "required_text"}
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
    read_only = False
    render_args = {
        "run_intake": raw_session["run_intake"],
        "review_payload": raw_session["review_payload"],
        "ui_decisions": raw_session["ui_decisions"],
        "final_artifacts": raw_session["final_artifacts"],
    }
    if workbench.plugin == "journal-sampling":
        render_args = {
            "model_review_context": _read_json_object(
                workbench.output_dir / "model_review_context.json", required=True
            )
        }
    if (
        raw_session["run_intake"].get("path_reference") == "run_root_relative"
        or workbench.plugin == "archive-organization"
    ):
        render_args = _with_vera_customer_context(
            workbench, render_args, read_only=True
        )
        context_path = render_args.get("client_engagement")
        if context_path:
            run = _read_json_object(
                Path(context_path).parent / "run.json", required=True
            )
            read_only = run.get("status") != "running"
    rendered = _mcp_tool_result(
        workbench,
        _render_tool_name(_adapter(workbench)),
        render_args,
        browser_payload=True,
    )
    if rendered.get("ok") is False:
        raise ValueError(str(rendered.get("error") or "plugin render tool failed"))
    rendered_review = rendered.get("review_payload")
    if not isinstance(rendered_review, dict):
        raise ValueError("plugin render tool returned no review_payload")
    expected_review_id = (
        render_args["model_review_context"]["review_ref"]
        if workbench.plugin == "journal-sampling"
        else raw_session["review_payload"]["run_id"]
    )
    if (
        rendered_review.get("plugin") != workbench.plugin
        or rendered_review.get("run_id") != expected_review_id
    ):
        raise ValueError("plugin render tool returned a mismatched review session")
    if workbench.plugin == "journal-sampling":
        # The MCP call has replayed and bound the current persisted review.
        # Opaque aliases belong to model context; the local human-facing widget
        # needs the verified filenames for traceability and declared downloads.
        rendered = {**rendered, **raw_session}
    redactions = _known_absolute_paths(
        {
            "session": raw_session,
            "tool_args": render_args,
            "workbench_output_dir": workbench.output_dir.resolve().as_posix(),
        }
    )
    # Restore the persisted apply result through the same path redaction as the
    # live tool response. A page reload must not reset its applied counter.
    rendered["applied_decisions"] = raw_session["applied_decisions"]
    if workbench.plugin == "new-client":
        # The native model response omits free-text decisions. The validated
        # local browser must still reopen the user's saved notes and requests.
        rendered["ui_decisions"] = raw_session["ui_decisions"]
    rendered["local_review_read_only"] = read_only
    sanitized = _sanitize_browser_payload(rendered, redactions=redactions)
    if not isinstance(sanitized, dict):
        raise ValueError("sanitized plugin render result must remain an object")
    return sanitized








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
    if workbench.plugin == "journal-sampling":
        args = {
            "model_review_context": _read_json_object(
                workbench.output_dir / "model_review_context.json", required=True
            ),
            "decision_source": "local_review_server",
        }
    if decisions is not None:
        args["decisions"] = decisions
    reviewer = posted_args.get("reviewer")
    if isinstance(reviewer, str) and reviewer.strip():
        args["reviewer"] = reviewer.strip()
    return args


def _codex_runtime_node_candidates() -> list[Path]:
    """Return bounded Node.js candidates supplied by local Claude runtimes."""

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
    workbench: LocalReviewWorkbench,
    name: str,
    args: dict[str, Any],
    *,
    browser_payload: bool = False,
) -> dict[str, Any]:
    if browser_payload and name != _render_tool_name(_adapter(workbench)):
        raise ValueError("component metadata is only available to browser rendering")
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": args},
    }
    command = [_node_executable(), workbench.mcp_server_path.as_posix(), "--stdio"]
    if workbench.plugin_dir.name == "archive-organization":
        # References belong to one server process. Validate the canonical local
        # package and use its reference within the same bounded invocation.
        # callTool retains the server's binding, digest and persistence checks.
        command = [
            _node_executable(),
            "-e",
            "const fs = require('node:fs');"
            "const server = require(process.argv[1]);"
            "const request = JSON.parse(fs.readFileSync(0, 'utf8'));"
            "try { const args = request.params.arguments;"
            "const validated = server.callTool(server.TOOL_NAMES.validateReview, args);"
            "const result = server.callTool(request.params.name, "
            "{...args, review_reference: validated.review_reference.reference});"
            "process.stdout.write(JSON.stringify({id:request.id,result:{structuredContent:{ok:true,...result}}}));"
            "} catch(error) { process.stdout.write(JSON.stringify({id:request.id,"
            "error:{message:error.message}})); }",
            workbench.mcp_server_path.as_posix(),
        ]
    completed = subprocess.run(
        command,
        input=json.dumps(message) + "\n",
        capture_output=True,
        text=True,
        check=False,
        cwd=workbench.plugin_dir,
        # The local server is already running in the selected environment.
        # Its Node bridge defaults to that Python even when launched directly
        # without shell activation. Preserve an explicit component override.
        env=local_helper_environment(python=os.environ.get("PYTHON") or sys.executable),
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
    if (
        browser_payload
        and isinstance(structured, dict)
        and structured.get("ok") is True
    ):
        metadata = result.get("_meta")
        private = (
            metadata.get("private_review_payload")
            if isinstance(metadata, dict)
            else None
        )
        if isinstance(private, dict):
            # Component-only metadata stays in the local browser session. The
            # normal MCP caller continues to receive only structuredContent.
            return private
    if isinstance(structured, dict):
        if (
            browser_payload
            and name == _render_tool_name(_adapter(workbench))
            and structured.get("ok") is not False
        ):
            metadata = result.get("_meta")
            private = (
                metadata.get("private_review_payload")
                if isinstance(metadata, dict)
                else None
            )
            if isinstance(private, dict):
                return private
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
    args = _with_vera_customer_context(
        workbench,
        _server_tool_args(workbench, posted_args or {}),
    )
    adapter = _adapter(workbench)
    allowed_tools = {adapter["saveTool"], adapter["applyTool"]}
    if name not in allowed_tools:
        raise ValueError(f"unsupported local review tool: {name}")
    result = _mcp_tool_result(workbench, name, args)
    if (
        workbench.plugin in {"journal-sampling", "archive-organization", "new-client"}
        and result.get("ok") is True
    ):
        # A successful mutation returns a minimized model summary. Reload the
        # actual persisted successor for browser counters and file downloads.
        persisted = _raw_session_payload(workbench)
        result = {
            **result,
            **{
                key: persisted[key]
                for key in ("ui_decisions", "applied_decisions", "final_artifacts")
            },
        }
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
