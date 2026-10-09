"""Read selected public browser records and append explicit batch checks only."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """No browser, credentials, accounting execution or model calls in this bridge."""
    request = json.loads(sys.stdin.read(2_000_001))
    module = Path(request["module"])
    if module.name != "browser-automation":
        raise PermissionError("Unsupported browser review producer")
    sys.path.insert(0, str(Path(__file__).parent))
    from native_transformation import bounded, files, regular

    sys.path.insert(0, str(module / "scripts"))
    import batch_review
    from process_lifecycle import ProcessStore

    row = request["binding"]
    root = Path(row["directory"])
    if row["kind"] == "batch":
        sys.path.insert(0, str(module.parent / "studio-archive/scripts"))
        import client_ledger

        client = client_ledger.load_client_manifest(Path(row["client_root"]))
        engagement = client_ledger.load_engagement_manifest(
            Path(row["client_root"]), row["engagement_id"]
        )
        if client["client_id"] != row["client_id"]:
            raise PermissionError("Batch belongs to another Archive client")
        archive = {"client": client, "engagement": engagement}
        record = batch_review.read_review(root)
        if record["payload"]["batch_id"] != row["batch_id"]:
            raise PermissionError("Batch identity changed")
        if request["action"] == "record_review":
            if files(root) != request["expected_files"]:
                raise ValueError("Batch changed before conservation")
            batch_review.record_review(
                root,
                entry_id=request["item_id"],
                decision=request["fields"]["decision"],
                note=request["fields"]["note"],
                expected_revision=record["revision"],
            )
            record = batch_review.read_review(root)
        elif request["action"] != "snapshot":
            raise ValueError("Unknown batch operation")
        history = [
            json.loads(p.read_bytes()) for p in sorted(root.glob("review-*.json"))
        ]
        # Reproduce the current public HTML offline; reading never repairs live files.
        with tempfile.TemporaryDirectory(prefix="vera-browser-batch-replay-") as name:
            clone = Path(name).resolve()
            for path in sorted(root.glob("review-*.json")):
                regular(path)
                (clone / path.name).write_bytes(path.read_bytes())
            expected = batch_review.render_review(clone)
            target = root / expected.name
            regular(target)
            if not target.is_file() or target.read_bytes() != expected.read_bytes():
                raise ValueError(
                    "Current batch HTML differs or is missing; recover publicly"
                )
        result = {
            "record": record,
            "history": history,
            "archive": archive,
            "artifact": {
                "name": target.name,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            },
            "shared_implementation": {
                "client_ledger.py": hashlib.sha256(
                    Path(client_ledger.__file__).read_bytes()
                ).hexdigest()
            },
            "browser_executed": False,
            "accounting_correction_executed": False,
        }
    elif row["kind"] == "process" and request["action"] == "snapshot":
        if not (root / "processes.sqlite3").is_file():
            raise ValueError("Initialize the public process register first")
        store = ProcessStore(root)
        process = store.resume(row["process_id"])
        # Do not expose raw submission/status records or private execution output values.
        selected = {
            key: process[key]
            for key in (
                "process_id",
                "description",
                "versions",
                "inputs",
                "implementation_status",
                "available_in_qualified_environment",
                "attempts",
                "cr_ids",
                "qualification",
                "release_history",
                "routing_policy",
            )
        }
        attempts = [store.inspect(a["attempt_id"]) for a in process["attempts"]]
        result = {
            "process": selected,
            "attempts": attempts,
            "shared_implementation": {},
            "browser_executed": False,
        }
    else:
        raise PermissionError("Process panel is read only")
    sys.stdout.write(bounded(result))


if __name__ == "__main__":
    main()
