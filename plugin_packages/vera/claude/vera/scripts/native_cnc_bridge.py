"""Isolated maintained CNC validation and persistence; no semantic classifier."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Reuse public role, lineage, source, review and memo contracts unchanged."""
    root = Path(sys.argv[1])
    if root.name != "composizione-negoziata":
        raise PermissionError("Unsupported CNC service")
    sys.path.insert(0, str(root / "scripts"))
    import cnc_case as cnc

    ledger, load_context = cnc._dependencies()
    request = json.loads(sys.stdin.read(2_000_001))
    if request["operation"] == "implementation":
        directories = [root / "scripts", root.parent / "studio-archive/scripts"]
        directories += [
            p
            for p in (
                root / "vendor/modules",
                root.parent.parent / "vendor/modules",
                root.parent / "_shared/vendor/modules",
            )
            if (p / "vera_assurance").is_dir()
        ][:1]
        result = {
            "files": {
                str(index)
                + "/"
                + str(p.relative_to(directory)): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for index, directory in enumerate(directories)
                for p in sorted(directory.rglob("*.py"))
            }
        }
    else:
        context_path = Path(request["context"])
        context = load_context(
            context_path,
            expected_workflow_id=cnc.WORKFLOW,
            allowed_statuses=("running", "ready_for_review", "completed"),
        )
        if context["schema_version"] != "vera.client_workflow_context.v2":
            raise PermissionError("CNC requires a managed portable engagement")
        client = Path(context["studio_client_folder"]["client_root"])
        history = ledger.load_workflow_history(
            client, context["engagement_id"], cnc.WORKFLOW
        )
        rows, recovery = [], False
        role = None
        for record in history:
            loaded = ledger.load_run(client, context["engagement_id"], record["run_id"])
            state = record["payload"]
            if (
                state["schema_version"] != "vera.cnc_case.v1"
                or state["role"] not in cnc.ROLES
            ):
                raise ValueError("Unsupported CNC snapshot")
            if role is not None and role != state["role"]:
                raise PermissionError("CNC history crossed professional roles")
            role = state["role"]
            if cnc.stale_nodes(state["nodes"]) != state["stale_nodes"]:
                raise ValueError("CNC explicit dependency versions changed")
            for node in state["nodes"].values():
                if (
                    cnc.digest({k: v for k, v in node.items() if k != "version"})
                    != node["version"]
                ):
                    raise ValueError("CNC node version changed")
                for citation in node["citations"]:
                    cited = ledger.load_run(
                        client, context["engagement_id"], citation["run_id"]
                    )
                    match = next(
                        (
                            r
                            for r in cited["input_manifest"]["inputs"]
                            if r["binding_id"] == citation["binding_id"]
                        ),
                        None,
                    )
                    if (
                        match is None
                        or match["sha256"] != citation["sha256"]
                        or match["source_relative_path"]
                        != citation["source_relative_path"]
                    ):
                        raise ValueError("CNC source citation receipt changed")
            output = Path(loaded["output_dir"])
            snapshot = output / f"workflow-revision-{record['revision']:06d}.json"
            memo = output / f"cnc-revision-{record['revision']:06d}.md"
            if memo.is_symlink() or (
                memo.exists() and memo.read_text() != cnc.render_record(record)
            ):
                raise ValueError("CNC memo differs from the maintained renderer")
            recovery |= not memo.is_file()
            rows.append(
                {
                    "record": record,
                    "snapshot_path": str(snapshot),
                    "memo_path": str(memo),
                    "snapshot_sha256": hashlib.sha256(
                        snapshot.read_bytes()
                    ).hexdigest(),
                    "memo_sha256": (
                        hashlib.sha256(memo.read_bytes()).hexdigest()
                        if memo.is_file()
                        else None
                    ),
                }
            )
        if request["operation"] == "history":
            result = {"rows": rows, "role": role, "recovery_required": recovery}
        elif request["operation"] in {"preview", "apply"}:
            update = request["update"]
            if any("server_receipt" in row for row in update["reviews"]):
                raise PermissionError(
                    "Authenticated CNC receipt import stays on the user-selected specialist route"
                )
            if recovery:
                raise ValueError(
                    "Recover the ordinary missing CNC memo before new work"
                )
            if request["operation"] == "preview":
                if any(
                    r["idempotency_key"] == update["idempotency_key"] for r in history
                ):
                    raise ValueError(
                        "A preview requires an unused ordinary request identity"
                    )
                # The public validator runs against the real context/history. Only the
                # final ledger append is intercepted inside this isolated process.
                ledger.append_workflow_snapshot = lambda *args, **kwargs: {
                    "payload": dict(args[3])
                }
                result = cnc.apply_request(context_path, update)
            else:
                output = Path(context["output_dir"])
                request_path = Path(request["request_path"])
                if request_path.parent != output or request_path.is_symlink():
                    raise PermissionError("CNC request must remain in this run")
                if (
                    request_path.exists()
                    and json.loads(request_path.read_bytes()) != update
                ):
                    raise ValueError("CNC ordinary request changed")
                if not request_path.exists():
                    with request_path.open("x", encoding="utf-8") as handle:
                        json.dump(update, handle, ensure_ascii=False, indent=2)
                record = cnc.apply_request(context_path, update)
                memo = output / f"cnc-revision-{record['revision']:06d}.md"
                rendered = cnc.render_record(record)
                if memo.is_symlink() or (
                    memo.exists() and memo.read_text() != rendered
                ):
                    raise ValueError("Existing CNC memo changed")
                if not memo.exists():
                    with memo.open("x", encoding="utf-8") as handle:
                        handle.write(rendered)
                result = {
                    "record": record,
                    "memo_path": str(memo),
                    "request_path": str(request_path),
                }
        else:
            raise ValueError("Unknown native CNC operation")
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
