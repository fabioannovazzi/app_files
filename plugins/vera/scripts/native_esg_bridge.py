"""Isolated readonly ESG foundation over its maintained public resume contract."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Verify public state first; preserve exact version dependency metadata."""
    root = Path(sys.argv[1])
    if root.name != "esg-reporting-assurance":
        raise PermissionError("Unsupported ESG component")
    sys.path.insert(0, str(root / "scripts"))
    import esg_case as esg

    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "implementation":
        directories = [root / "scripts", root / "schemas"]
        directories += [
            p / "vera_assurance"
            for p in (
                root / "vendor/modules",
                root.parent.parent / "vendor/modules",
                root.parent / "_shared/vendor/modules",
            )
            if (p / "vera_assurance").is_dir()
        ][:1]
        result = {
            str(index)
            + "/"
            + str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for index, directory in enumerate(directories)
            for p in sorted(directory.rglob("*"))
            if p.is_file() and p.suffix in {".py", ".json"}
        }
    elif request["operation"] == "resume":
        context_path = Path(request["context"])
        context = esg.load_client_engagement_context_file(
            context_path,
            expected_workflow_id=esg.WORKFLOW,
            allowed_statuses=("running", "ready_for_review", "completed"),
        )
        summary = esg.resume_case(context_path)
        path = Path(context["output_dir"]) / "esg_state.json"
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > esg.MAX_BYTES
        ):
            raise PermissionError("Expected ordinary bounded ESG state")
        raw = path.read_bytes()
        state = json.loads(raw)
        # This is an exact-integrity check, never framework or sufficiency judgment.
        content = {k: v for k, v in state.items() if k != "sha256"}
        sha = hashlib.sha256(
            json.dumps(
                content,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        if sha != summary["state_sha256"] or state["sha256"] != sha:
            raise ValueError("ESG state changed during public resume; reopen")
        result = {
            "summary": summary,
            "state": state,
            "state_file_sha256": hashlib.sha256(raw).hexdigest(),
        }
    else:
        raise ValueError("Unsupported readonly ESG operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
