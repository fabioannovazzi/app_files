"""Isolated, local-only validation of an existing run disclosure pair."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Reuse maintained report schema/rendering; never infer transmission or build files."""
    root = Path(sys.argv[1])
    if root.name != "studio-archive":
        raise PermissionError("Unsupported archive report producer")
    sys.path.insert(0, str(root / "scripts"))
    import build_model_data_report  # noqa: F401
    import model_data_report as producer

    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "implementation":
        directories = [root / "scripts"]
        vendor = root / "vendor/modules"
        if not vendor.exists():
            vendor = root.parent / "_shared/vendor/modules"
        directories.append(vendor)
        files = {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for d in directories
            for p in sorted(d.rglob("*.py"))
        }
        files[str(Path(producer.__file__))] = hashlib.sha256(
            Path(producer.__file__).read_bytes()
        ).hexdigest()
        result = {
            "sha256": hashlib.sha256(
                json.dumps(files, sort_keys=True).encode()
            ).hexdigest()
        }
    elif request["operation"] == "report":
        output = Path(request["output"])
        path = output / "model_data_report.json"
        try:
            if path.stat().st_size > 2_000_000:
                raise ValueError("Model-data report exceeds native validation limit")
            value = json.loads(path.read_bytes())
            producer.validate_model_data_report(value, evidence_root=output)
            rebuilt, markdown = producer.build_model_data_report(
                {
                    k: v
                    for k, v in value.items()
                    if k not in {"report_id", "evidence", "limitations"}
                },
                evidence_root=output,
            )
            if (
                rebuilt != value
                or (output / "model_data_report.md").read_text() != markdown
            ):
                raise ValueError(
                    "Disclosure differs from the maintained report/rendered Markdown"
                )
            if (
                value["run_id"] != request["run_id"]
                or value["workflow_id"] != request["workflow_id"]
            ):
                raise ValueError("Disclosure belongs to another workflow run")
            result = {
                "valid": True,
                "report_id": value["report_id"],
                "text": markdown if len(markdown.encode()) <= 64_000 else None,
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result = {"valid": False, "reason": str(exc)}
    else:
        raise ValueError("Unknown archive disclosure operation")
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
