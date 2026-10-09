"""Exact owned registry packages over the maintained validate/render/save/apply service."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

__all__ = ["main"]


def read(path: Path) -> dict:
    """Regular whole records are mechanical provenance, never professional acceptance."""
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_nlink != 1
        or path.stat().st_size > 2_000_000
    ):
        raise ValueError("Expected a bounded regular registry record")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Registry record must be a complete object")
    return value


def main() -> None:
    """Keep portable ownership context inside the public service's actual token scope."""
    root = Path(sys.argv[1])
    if root.name != "registro-imprese-sari":
        raise PermissionError("Unsupported registry review component")
    raw = sys.stdin.read(2_000_001)
    if len(raw.encode()) > 2_000_000:
        raise ValueError("Registry bridge request exceeds complete-content limit")
    request = json.loads(raw)
    if request["operation"] == "implementation":
        directories = [
            root / "scripts",
            root / "mcp",
            root / "schemas",
            root / "assets",
        ]
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
            str(i)
            + "/"
            + p.relative_to(directory)
            .as_posix(): hashlib.sha256(p.read_bytes())
            .hexdigest()
            for i, directory in enumerate(directories)
            for p in sorted(directory.rglob("*"))
            if p.is_file() and p.suffix in {".py", ".cjs", ".json", ".html"}
        }
        sys.stdout.write(json.dumps(result))
        return
    if request["operation"] not in {"read", "preflight", "save", "apply"}:
        raise ValueError("Unsupported registry public-review operation")
    sys.path.insert(0, str(root / "scripts"))
    from case_core import load_client_engagement_context_file, sha256_file

    context = load_client_engagement_context_file(
        Path(request["context"]),
        expected_workflow_id=root.name,
        allowed_statuses=(
            ("running",)
            if request["operation"] in {"save", "apply"}
            else ("running", "ready_for_review", "completed")
        ),
    )
    output = Path(context["output_dir"])
    review, intake, final, audit = [
        read(output / name)
        for name in (
            "review_payload.json",
            "run_intake.json",
            "final_artifacts.json",
            "practice_validation_audit.json",
        )
    ]
    for value in (review, intake, final, audit):
        if value["plugin"] != root.name or value["run_id"] != context["run_id"]:
            raise PermissionError("Registry package belongs to another run")
    if final["review_payload_sha256"] != sha256_file(
        output / "review_payload.json"
    ) or final["validation_audit_sha256"] != sha256_file(
        output / "practice_validation_audit.json"
    ):
        raise ValueError("Registry review or validation audit changed")
    bound_files = {
        "case_intake_draft.json": "case_intake_sha256",
        "practice_plan_draft.json": "practice_plan_sha256",
        "official_sources.json": "official_sources_sha256",
        "local_evidence_inventory.json": "local_evidence_inventory_sha256",
        "case_intake_validated.json": "case_intake_validated_sha256",
        "practice_plan_validated.json": "practice_plan_validated_sha256",
    }
    for name, key in bound_files.items():
        expected = final["bindings"][key]
        if expected is None and name != "local_evidence_inventory.json":
            raise ValueError("Registry mandatory validated-case binding missing")
        if expected is not None and sha256_file(output / name) != expected:
            raise ValueError("Registry validated-case source binding changed")
    decisions = read(output / "ui_decisions.json")
    if (
        decisions["plugin"] != root.name
        or decisions["run_id"] != context["run_id"]
        or decisions["review_payload_sha256"] != final["review_payload_sha256"]
    ):
        raise ValueError("Registry saved choices belong to another review")
    arguments = {
        "review_payload": review,
        "final_artifacts": final,
        "ui_decisions": decisions,
    }
    running = read(Path(context["run_manifest_path"]))["status"] == "running"
    if running:
        arguments.update(
            run_intake=intake, client_engagement=str(Path(request["context"]).resolve())
        )
    result = subprocess.run(
        [request["node"], str(Path(__file__).with_name("native_sari_review_rpc.cjs"))],
        input=json.dumps(
            {
                "root": str(root),
                "operation": request["operation"],
                "arguments": arguments,
                "choices": request.get("choices", {}),
            }
        ),
        text=True,
        capture_output=True,
        check=False,
        timeout=75,
        env={
            **os.environ,
            "PYTHON": sys.executable,
            "VERA_CLIENT_WORKFLOW_PYTHON": sys.executable,
        },
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "Registry public review refused"
        )
    payload = json.loads(result.stdout)
    sys.stdout.write(
        json.dumps(
            {"payload": payload, "review_sha256": final["review_payload_sha256"]}
        )
    )


if __name__ == "__main__":
    main()
