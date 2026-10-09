"""Optional ESG evidence/version consultation; semantic review stays with people."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash

__all__ = ["dispatch"]


def engine(root: Path, value: dict) -> dict:
    """Invoke only the fixed readonly bridge and maintained public resume."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_esg_bridge.py")),
            str(root),
        ],
        input=json.dumps(value),
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip().splitlines()[-1] or "ESG resume refused")
    return json.loads(result.stdout)


def limited(value: dict, maximum: int = 2_000_000) -> dict:
    """Keep complete chosen records or refuse; never silently truncate evidence."""
    if len(json.dumps(value, ensure_ascii=False).encode()) > maximum:
        raise ValueError(
            "Whole ESG content exceeds native limit; use the ordinary file route"
        )
    return value


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Bind exact versions and dependencies mechanically, without approving them."""
    if (
        binding["workflow_id"] != "esg-reporting-assurance"
        or root.name != binding["workflow_id"]
    ):
        raise PermissionError("ESG belongs to another workflow")
    action = tool.removeprefix("vera_workspace_esg_")
    output = Path(loaded["output_dir"])
    state_path = output / "esg_state.json"
    if state_path.is_symlink():
        raise PermissionError("Linked ESG state is unavailable")
    if not state_path.exists():
        if action != "setup":
            raise ValueError(
                "Start the partial ESG case through the ordinary specialist route"
            )
        return {
            "work_ref": binding["work_ref"],
            "setup_status": "case_required",
            "can_write": False,
            "rows": [],
            "total": 0,
            "offset": 0,
            "has_more": False,
            "limitations": [
                "Evidence/decision foundation only; no full ESG reporting or assurance"
            ],
            "actual_model_reads_verified": False,
        }
    recovered = engine(
        root, {"operation": "resume", "context": str(loaded["context_path"])}
    )
    summary, state = recovered["summary"], recovered["state"]
    pairs = list(zip(state["objects"], summary["objects"], strict=True))
    scope = [
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        binding,
        loaded["input_manifest"],
        loaded["run"],
        recovered["state_file_sha256"],
        engine(root, {"operation": "implementation"}),
        {
            p.name: file_hash(p)
            for p in (Path(__file__), Path(__file__).with_name("native_esg_bridge.py"))
        },
    ]
    revision = api.digest(scope)
    base = {
        "work_ref": binding["work_ref"],
        "revision": revision,
        "case_id": summary["case_id"],
        "case_revision": summary["revision"],
        "state_sha256": summary["state_sha256"],
        "run_status": loaded["run"]["status"],
        "can_write": False,
        "compliance_claim_enabled": False,
        "actual_model_reads_verified": False,
        "limitations": summary["limitations"],
    }
    if action == "setup":
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid ESG page offset")
        newest = list(reversed(pairs))
        return limited(
            {
                **base,
                "offset": offset,
                "total": len(pairs),
                "has_more": offset + 30 < len(pairs),
                "rows": [
                    {
                        "source_ref": item["sha256"],
                        "kind": item["kind"],
                        "id": item["id"],
                        "version": item["version"],
                        "current": row["current"],
                        "dependency_count": len(item["dependencies"]),
                    }
                    for item, row in newest[offset : offset + 30]
                ],
            }
        )
    selected = next(
        ((item, row) for item, row in pairs if item["sha256"] == args["source_ref"]),
        None,
    )
    if selected is None:
        raise PermissionError("Choose an exact ESG version in this owned run")
    item, row = selected
    value = {
        **base,
        "source_ref": item["sha256"],
        "reference": row["reference"],
        "current": row["current"],
        "record": item["record"],
        "dependencies": item["dependencies"],
        "version_record": item,
    }
    if action == "read":
        return limited(value)
    if action not in {"context", "outputs"}:
        raise ValueError("Unsupported readonly ESG action")
    if args["revision"] != revision:
        raise ValueError("Reopen this exact ESG version before continuing")
    if action == "context":
        wanted = {item["sha256"]}
        pending = [item]
        while pending:
            for dependency in pending.pop()["dependencies"]:
                dep = next((p for p, r in pairs if r["reference"] == dependency), None)
                if dep is None:
                    raise ValueError("ESG exact dependency is missing")
                if dep["sha256"] not in wanted:
                    wanted.add(dep["sha256"])
                    pending.append(dep)
        return limited(
            {
                **value,
                "dependency_records": [
                    {
                        "reference": r["reference"],
                        "current": r["current"],
                        "version_record": p,
                    }
                    for p, r in pairs
                    if p["sha256"] in wanted and p is not item
                ],
            },
            64000,
        )
    if item["kind"] != "artifact":
        raise ValueError("Only an exact partial draft has ordinary exported files")
    files = []
    for suffix, media in ((".md", "text/markdown"), (".json", "application/json")):
        path = output / ("esg-draft-" + item["sha256"] + suffix)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
            raise ValueError("Expected bounded ordinary ESG draft")
        raw = path.read_bytes()
        files.append(
            {
                "name": path.name,
                "path": str(path),
                "media_type": media,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "content": raw.decode("utf-8"),
            }
        )
    if file_hash(state_path) != recovered["state_file_sha256"]:
        raise ValueError("ESG state changed while opening exports")
    # Public resume checks these immutable files against the maintained renderer.
    latest = engine(
        root, {"operation": "resume", "context": str(loaded["context_path"])}
    )
    if latest["state_file_sha256"] != recovered["state_file_sha256"]:
        raise ValueError("ESG version changed while validating exports")
    return limited({**value, "files": files})
