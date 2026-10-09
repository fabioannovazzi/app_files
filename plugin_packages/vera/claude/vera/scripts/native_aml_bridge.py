"""Isolated replay and append over the unchanged AML public record service."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Validate records and reproduce their memo without substituting AML reasoning."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    profiles = {"aml-review": "aml_review", "adeguati-assetti": "assetti_review"}
    if root.name not in profiles:
        raise PermissionError("Unsupported immutable record producer")
    module = importlib.import_module(profiles[root.name])
    build_record, digest, render_memo, save_record = (
        module.build_record,
        module.digest,
        module.render_memo,
        module.save_record,
    )

    directories = [root / "scripts"]
    if root.name == "aml-review":
        directories.append(root.parent / "new-client/scripts")
    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "implementation":
        result = {
            "sha256": digest(
                {
                    str(path.relative_to(root.parent)): hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
                    for directory in directories
                    for path in sorted(directory.glob("*.py"))
                }
            )
        }
    elif request["operation"] in {"inspect_proposal", "save_proposal"}:
        review = json.loads(Path(request["review"]).read_bytes())
        if review.get("professional_decision") is not None:
            raise PermissionError(
                "Model authoring cannot declare a professional decision"
            )
        produced = build_record(
            review,
            input_root=Path(request["inputs"]),
            client_id=request["client_id"],
            engagement_id=request["engagement_id"],
        )
        if request["operation"] == "save_proposal":
            save_record(produced, Path(request["output"]))
        result = {"record": produced, "memo": render_memo(produced)}
    else:
        record = json.loads(Path(request["record"]).read_bytes())
        produced = build_record(
            record["review"],
            input_root=Path(request["inputs"]),
            client_id=request["client_id"],
            engagement_id=request["engagement_id"],
        )
        if produced != record or Path(request["record"]).with_suffix(
            ".md"
        ).read_text() != render_memo(produced):
            raise ValueError(
                "AML record or memo cannot be replayed with the maintained engine"
            )
        if request["operation"] in {"decide", "validate_decision"}:
            review = {
                **record["review"],
                "professional_decision": json.loads(
                    Path(request["decision"]).read_bytes()
                ),
            }
            produced = build_record(
                review,
                input_root=Path(request["inputs"]),
                client_id=request["client_id"],
                engagement_id=request["engagement_id"],
            )
            ref = root.name + "-" + produced["record_sha256"]
            if request["operation"] == "decide":
                ref = save_record(produced, Path(request["output"])).stem
            result = {"record_ref": ref, "status": produced["status"]}
        elif request["operation"] == "replay":
            result = {"record_sha256": produced["record_sha256"]}
        else:
            raise ValueError("Unknown AML bridge operation")
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
