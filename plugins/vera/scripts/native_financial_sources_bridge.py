"""Purpose recording remains owned by the unchanged Financial model-use service."""

from __future__ import annotations

import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Project sealed identities or invoke the exact public named-source authorizer."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    import model_use

    request = json.loads(sys.stdin.read(128001))
    directory = Path(request["directory"])
    manifest = directory / "prepared" / model_use.MANIFEST_NAME
    case = directory / "case" / "case.json"
    if request["operation"] == "inventory":
        value = model_use.validate_manifest(json.loads(manifest.read_bytes()))
        result = {"sources": value["source_population"]["source_artifacts"]}
    elif request["operation"] == "authorize":
        result = model_use.authorize_evidence(
            manifest_path=manifest,
            case_path=case,
            pack_id=request["pack_id"],
            source_artifact_id=request["source_artifact_id"],
            reason=request["question"],
            selectors=request["selectors"],
            client_engagement_path=Path(request["context"]),
        )
        result["source_locator"] = (
            Path(result.pop("authorized_source_path"))
            .relative_to(case.parent)
            .as_posix()
        )
        receipt = Path(result.pop("receipt_path"))
        result["receipt_locator"] = receipt.relative_to(directory).as_posix()
        result["receipt"] = json.loads(receipt.read_bytes())
    else:
        raise ValueError("Unknown Financial source request operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
