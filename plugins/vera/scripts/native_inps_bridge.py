"""Owned INPS review over the unchanged acquisition and public MCP contracts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

__all__ = ["main"]


def read(path: Path) -> dict:
    """Read complete ordinary records; linked or oversized content is unavailable."""
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_nlink != 1
        or path.stat().st_size > 2_000_000
    ):
        raise ValueError("Expected a bounded regular INPS record")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("INPS record must be an object")
    return value


def main() -> None:
    """Verify the actual run before invoking only fixed public review tools."""
    root = Path(sys.argv[1])
    if root.name != "previdenza-inps":
        raise PermissionError("Unsupported INPS component")
    sys.path.insert(0, str(root / "scripts"))
    import package_case as package
    from acquisition_binding import (
        build_acquisition_binding,
        compare_acquisition_bindings,
    )

    raw_request = sys.stdin.read(2_000_001)
    if len(raw_request.encode()) > 2_000_000:
        raise ValueError("INPS request exceeds the complete-content limit")
    request = json.loads(raw_request)
    if request["operation"] == "implementation":
        directories = [
            root / "scripts",
            root / "schemas",
            root / "mcp",
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
            if p.is_file() and p.suffix in {".py", ".json", ".cjs", ".html"}
        }
        sys.stdout.write(json.dumps(result))
        return
    if request["operation"] not in {"read", "apply"}:
        raise ValueError("Unsupported native INPS operation")
    context = package.load_client_engagement_context_file(
        request["context"],
        expected_workflow_id="previdenza-inps",
        allowed_statuses=(
            ("running",)
            if request["operation"] == "apply"
            else ("running", "ready_for_review", "completed")
        ),
    )
    output = Path(context["output_dir"])
    review = read(output / "review_payload.json")
    intake = read(output / "run_intake.json")
    final = read(output / "final_artifacts.json")
    actual_sha = hashlib.sha256(
        (output / "review_payload.json").read_bytes()
    ).hexdigest()
    for value in (review, intake, final):
        if (
            value.get("run_id") != context["run_id"]
            or value.get("plugin") != "previdenza-inps"
            or value.get("workflow") != "previdenza-inps"
        ):
            raise PermissionError("INPS record belongs to another run")
    if final.get("review_payload_sha256") != actual_sha:
        raise ValueError("INPS final manifest no longer binds the exact review")
    binding = build_acquisition_binding(
        output / "file_inventory.json", output / "run_intake.json"
    )
    issues = compare_acquisition_bindings(final.get("acquisition_binding"), binding)
    if issues:
        raise ValueError("INPS acquisition changed; use the ordinary recovery workflow")
    arguments = {"review_payload": review, "final_artifacts": final}
    decisions_path = output / "ui_decisions.json"
    if decisions_path.exists():
        arguments["ui_decisions"] = read(decisions_path)
    # Closed runs use the same public shape/privacy validator without acquiring
    # persistence authority. The maintained ledger above verifies sealed files.
    if read(Path(context["run_manifest_path"]))["status"] == "running":
        arguments.update(
            run_intake=intake, client_engagement=str(Path(request["context"]))
        )
    completed = subprocess.run(
        [request["node"], str(Path(__file__).with_name("native_inps_rpc.cjs"))],
        input=json.dumps(
            {
                "root": str(root),
                "operation": request["operation"],
                "arguments": arguments,
                **(
                    {"decisions": request["decisions"]}
                    if request["operation"] == "apply"
                    else {}
                ),
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
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "Public INPS review refused")
    result = {"payload": json.loads(completed.stdout), "review_sha256": actual_sha}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
