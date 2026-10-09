"""Fixed calls to the maintained studio-wide communication workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Expose complete existing review records, never raw history or model calls."""
    request = json.loads(sys.stdin.buffer.read(2_000_001))
    module = Path(request["module"])
    sys.path.insert(0, str(module / "scripts"))
    from workflow_core import (
        fresh_review_decisions,
        load_json,
        load_workspace,
        recompute_contribution_digest,
        run_dir_from_workspace,
        verify_package_manifest,
        verify_visual_manifest,
        verify_visual_preview_manifest,
        workflow_lock,
    )

    workspace = Path(request["workspace"])
    manifest = load_workspace(workspace)
    root = run_dir_from_workspace(workspace, request["run_id"])
    action = request["action"]
    if action == "snapshot":
        with workflow_lock(root):
            digest = recompute_contribution_digest(root)
            workbench = load_json(root / "content_workbench.json")
            intake = load_json(root / "run_intake.json")
            payload = load_json(root / "review_payload.json")
            if payload["contribution_digest"] != digest:
                raise ValueError("Review queue differs from the current contribution")
            artifacts = []
            final = None
            for filename, verifier in (
                ("visual_preview_manifest.json", verify_visual_preview_manifest),
                ("visual_manifest.json", verify_visual_manifest),
                ("final_artifacts.json", verify_package_manifest),
            ):
                if (root / filename).is_file():
                    verifier(root)
                    value = load_json(root / filename)
                    if filename == "final_artifacts.json":
                        final = value
                    for item in value["outputs"]:
                        path = Path(item["path"])
                        if not path.is_absolute():
                            path = root / path
                        if not path.resolve().is_relative_to(root.resolve()):
                            raise ValueError(
                                "Declared communication artifact escapes run"
                            )
                        artifacts.append(
                            {
                                "name": path.relative_to(root).as_posix(),
                                "sha256": item["sha256"],
                            }
                        )
            result = {
                "workspace_id": manifest["workspace_id"],
                "studio": manifest["owner"],
                "run_id": intake["run_id"],
                "intake": {
                    key: intake[key]
                    for key in (
                        "reference_date",
                        "language",
                        "jurisdiction",
                        "objective",
                        "audience",
                        "requested_channels",
                        "external_routes",
                    )
                },
                "contribution_digest": digest,
                "workbench": workbench,
                "review_payload": payload,
                "review_log": load_json(root / "review_log.json"),
                "current_semantic_decisions": fresh_review_decisions(root),
                "final": final,
                "artifacts": artifacts,
                "model_context_transferred": False,
                "history_or_identity_map_returned": False,
                "sent_or_published": False,
            }
    elif action == "semantic_review":
        from record_review import record_review_bundle

        record_review_bundle(
            root,
            Path(request["bundle_path"]),
            reviewer=request["reviewer"],
            confirmed_by_user=True,
        )
        result = {
            "operation": action,
            "review_log": load_json(root / "review_log.json"),
        }
    elif action in {"render_review", "package_review"}:
        from record_review import record_review

        record_review(
            root,
            scope="rendered_output" if action == "render_review" else "packaged_output",
            decision=request["decision"],
            reviewer=request["reviewer"],
            note=request["note"],
            confirmed_by_user=True,
            quality_checklist_confirmed=request["quality_checklist_confirmed"],
        )
        result = {
            "operation": action,
            "review_log": load_json(root / "review_log.json"),
        }
    elif action in {"render", "qa_preview"}:
        from render_visuals import render_visuals

        result = {
            "operation": action,
            "path": str(render_visuals(root, qa_preview=action == "qa_preview")),
        }
    elif action == "package":
        from package_communications import package_communications

        result = {"operation": action, "path": str(package_communications(root))}
    elif action == "validate":
        from validate_run import validate_run

        errors = validate_run(root)
        if errors:
            raise ValueError("Communication validation failed: " + "; ".join(errors))
        result = {
            "operation": action,
            "final": load_json(root / "final_artifacts.json"),
        }
    elif action == "promote_profile":
        from promote_studio_profile import promote_studio_profile

        result = {"operation": action, "path": str(promote_studio_profile(root))}
    else:
        raise ValueError("Unsupported communication operation")
    raw = json.dumps(result, ensure_ascii=False, allow_nan=False)
    if len(raw.encode()) > 2_000_000:
        raise ValueError("Complete communication projection exceeds native limit")
    sys.stdout.write(raw)


if __name__ == "__main__":
    main()
