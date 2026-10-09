"""Fixed calls to the unchanged synthetic CaseStore; no legal judgment engine."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Preserve complete case history and exact public export semantics."""
    request = json.loads(sys.stdin.read(2_000_001))
    module, root = Path(request["module"]), Path(request["workspace"])
    if module.name != "trasformazione":
        raise PermissionError("Unsupported synthetic producer")
    sys.path.insert(0, str(Path(__file__).parent))
    from native_transformation import bounded, files

    sys.path.insert(0, str(module / "scripts"))
    from transform_case import KINDS, CaseStore

    store = CaseStore(root)
    state = store.load()
    if state["case"]["id"] != request["case_id"]:
        raise PermissionError("Synthetic case identity changed")
    action = request["action"]
    if action != "snapshot":
        if files(root) != request["expected_files"]:
            raise ValueError("Synthetic case changed before the public call")
        fields = request["fields"]
        actor = fields["actor"]
        if action in {"update_case", "put", "branch", "import_evidence"}:
            record = json.loads(fields["record_json"])
            if not isinstance(record, dict):
                raise ValueError("Supply the complete public JSON object")
        if action == "update_case":
            state = store.update_case(record, actor)
        elif action == "put":
            state = store.put(fields["record_kind"], record, actor)
        elif action == "branch":
            if set(record) != {"title", "owner", "next_step", "dependencies"}:
                raise ValueError("Supply all exact branch fields")
            state = store.branch(fields["branch_id"], actor=actor, **record)
        elif action == "import_evidence":
            if set(record) != {"id", "source_ref", "origin", "locator"}:
                raise ValueError("Choose an exact bound synthetic source")
            item = next(
                (
                    r
                    for r in request["sources"]
                    if r["source_ref"] == record["source_ref"]
                ),
                None,
            )
            if item is None:
                raise PermissionError("Unknown selected synthetic source")
            state = store.import_evidence(
                record["id"],
                Path(item["path"]),
                record["origin"],
                record["locator"],
                actor,
            )
        elif action == "submit":
            state = store.submit(fields["branch_id"], actor)
        elif action == "review":
            state = store.review(
                fields["branch_id"],
                fields["proposal_digest"],
                actor,
                fields["decision"],
                fields["reason"],
            )
        elif action == "export":
            store.export()
        else:
            raise ValueError("Unknown synthetic operation")
        result = {
            "case_revision": state["revision"],
            "synthetic_only": True,
            "professional_validation": False,
        }
    else:
        artifacts = [
            {
                "name": row["local_path"],
                "sha256": row["sha256"],
                "kind": "synthetic_evidence",
            }
            for row in state["records"]["evidence"].values()
        ]
        exports = []
        # Replay historical exports with the unchanged formatter in isolation.
        # This binds displayed dossiers to their real history, not just mutable hashes.
        histories = sorted((root / "history").glob("*.json"))
        with tempfile.TemporaryDirectory(prefix="vera-transformation-replay-") as name:
            replay_root = Path(name)
            (replay_root / "history").mkdir()
            (replay_root / "evidence").mkdir()
            for path in (root / "evidence").iterdir():
                if path.is_file():
                    (replay_root / "evidence" / path.name).write_bytes(
                        path.read_bytes()
                    )
            for history in histories:
                (replay_root / "history" / history.name).write_bytes(
                    history.read_bytes()
                )
                directory = root / "exports" / ("revision-" + history.stem)
                if not directory.exists():
                    continue
                reproduced = CaseStore(replay_root).export()
                if {p.name for p in directory.iterdir()} != {
                    "case.json",
                    "dossier.md",
                    "manifest.json",
                }:
                    raise ValueError("Unexpected files in synthetic dossier")
                for path in reproduced.iterdir():
                    current = directory / path.name
                    if current.read_bytes() != path.read_bytes():
                        raise ValueError("Synthetic dossier differs from public replay")
                    item = {
                        "name": current.relative_to(root).as_posix(),
                        "sha256": hashlib.sha256(current.read_bytes()).hexdigest(),
                        "kind": "synthetic_dossier",
                    }
                    artifacts.append(item)
                exports.append(
                    {
                        "revision": int(history.stem),
                        "current": int(history.stem) == state["revision"],
                        "directory": directory.name,
                    }
                )
        result = {
            "state": state,
            "record_contract": {key: list(value) for key, value in KINDS.items()},
            "sources": [
                {
                    "source_ref": r["source_ref"],
                    "name": Path(r["path"]).name,
                    "sha256": hashlib.sha256(Path(r["path"]).read_bytes()).hexdigest(),
                }
                for r in request["sources"]
            ],
            "exports": exports,
            "artifacts": artifacts,
            "professional_validation": False,
        }
    sys.stdout.write(bounded(result))


if __name__ == "__main__":
    main()
