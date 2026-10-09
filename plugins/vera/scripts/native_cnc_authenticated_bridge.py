"""Reuse the fixed public CNC preparation and authenticated receipt contracts."""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Keep public identity verification and persistence authoritative."""
    root = Path(sys.argv[1])
    if root.name != "composizione-negoziata":
        raise PermissionError("Unsupported CNC authenticated service")
    sys.path.insert(0, str(root / "scripts"))
    import cnc_case as cnc
    import cnc_review_client as review

    args = json.loads(sys.stdin.read(2_000_001))
    context_path = Path(args["context"])
    ledger, load_context = cnc._dependencies()
    context = load_context(context_path, expected_workflow_id=cnc.WORKFLOW)
    history = ledger.load_workflow_history(
        Path(context["studio_client_folder"]["client_root"]),
        context["engagement_id"],
        cnc.WORKFLOW,
    )
    latest = history[-1]
    if latest["content_sha256"] != args["source_ref"]:
        raise ValueError("Reopen the current CNC case before review preparation/import")
    state = latest["payload"]
    node = state["nodes"][args["item_id"]]
    if node["id"] in state["stale_nodes"]:
        raise ValueError("Reanalyse stale CNC dependencies before review")
    output = Path(context["output_dir"])
    if args["operation"] == "prepare":
        before = set(output.glob("cnc-review-*.json"))
        sys.argv = [
            str(root / "scripts/cnc_case.py"),
            "--client-engagement",
            str(context_path),
            "--review-node",
            node["id"],
        ]
        cnc.main()
        created = set(output.glob("cnc-review-*.json")) - before
        if len(created) != 1:
            raise ValueError("Uncertain public CNC review preparation")
        path = created.pop()
        target = json.loads(path.read_bytes())
        if target["node"] != node or target["request"] != {
            "request_id": path.stem.removeprefix("cnc-review-"),
            "case_ref": review.case_reference(context),
            "role": state["role"],
            "node_ref": cnc.digest(node["id"]),
            "node_version": node["version"],
        }:
            raise ValueError("Public CNC review file differs from selected exact node")
        result = {"files": [str(path)], "target": target}
    elif args["operation"] == "import":
        receipt = args["receipt"]
        # Verify before any ordinary output write. A refused/unavailable service
        # leaves drafting available; never manufacture authenticated attribution.
        try:
            review.verify_receipt(
                receipt,
                context,
                node_id=node["id"],
                node_version=node["version"],
                role=state["role"],
                decision=receipt["decision"],
            )
        except (ValueError, urllib.error.URLError, TimeoutError) as exc:
            sys.stdout.write(
                json.dumps({"verification_pending": True, "error": str(exc)})
            )
            return
        update = {
            "expected_revision": latest["revision"],
            "idempotency_key": args["request_key"],
            "role": state["role"],
            "stage": state["stage"],
            "change_reason": args["reason"],
            "next_action": state["next_action"],
            "upsert_nodes": [],
            "reviews": [
                {
                    "node_id": node["id"],
                    "node_version": node["version"],
                    "decision": receipt["decision"],
                    "reviewer_ref": receipt["actor"],
                    "confirmation_ref": receipt["request_id"],
                    "reason": args["reason"],
                    "server_receipt": receipt,
                }
            ],
        }
        stem = args["request_key"]
        request_path = output / (stem + ".json")
        receipt_path = output / (stem + "-server-receipt.json")
        for path, value in ((request_path, update), (receipt_path, receipt)):
            with path.open("x", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
        # The unchanged public writer independently verifies the receipt again.
        # A failure after these writes remains uncertain and requires recovery.
        record = cnc.apply_request(context_path, update)
        memo = output / f"cnc-revision-{record['revision']:06d}.md"
        with memo.open("x", encoding="utf-8") as handle:
            handle.write(cnc.render_record(record))
        result = {
            "record": record,
            "files": [
                str(p)
                for p in (
                    request_path,
                    receipt_path,
                    memo,
                    output / f"workflow-revision-{record['revision']:06d}.json",
                )
            ],
        }
    else:
        raise ValueError("Unsupported authenticated CNC operation")
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
