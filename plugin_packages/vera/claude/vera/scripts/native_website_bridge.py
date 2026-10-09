"""Fixed calls to the maintained studio website producer; no publish transport."""

from __future__ import annotations

import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Project complete records and call existing review/package helpers exactly."""
    request = json.loads(sys.stdin.buffer.read(2_000_001))
    module = Path(request["module"])
    sys.path.insert(0, str(module / "scripts"))
    import workflow_core as domain
    from native_website import bounded, files, read, regular

    workspace = Path(request["workspace"])
    manifest = domain._load_json(workspace / domain.WORKSPACE_MANIFEST)
    run = workspace / "runs" / request["run_id"]
    state = domain._load_json(domain._run_file(run, "run_state.json"))
    if state["run_id"] != request["run_id"]:
        raise ValueError("Website run identity changed")
    action = request["action"]
    if action == "snapshot":
        intake, register, _ = domain._verified_intake_and_sources(run)
        validation = domain.validate_run(run)
        records = {
            "state": state,
            "source_register": register,
            "review_events": domain._review_events(run),
        }
        for key, name in (
            ("brief", "site_brief_record.json"),
            ("site_validation", "site_validation.json"),
            ("quality", "quality_assessment_record.json"),
        ):
            path = domain._run_file(run, name)
            records[key] = read(path) if path.is_file() else None
        # Only exact maintained declarations form downloadable artifact identities.
        # A stale record remains readable with its issues, but yields no artifacts.
        artifacts = []
        packages = {}
        if validation["valid"]:
            exact_validation, quality, _ = domain._current_ready_site(run)
            for item in exact_validation["inventory"]:
                artifacts.append(
                    {"name": "work/site/" + item["path"], "sha256": item["sha256"]}
                )
            for viewport in quality["assessment"]["viewports"]:
                artifacts.append(
                    {
                        "name": viewport["screenshot_path"],
                        "sha256": viewport["screenshot_sha256"],
                    }
                )
            for kind in sorted(state["packages"]):
                package, package_path = domain._verify_current_package(run, kind)
                packages[kind] = package
                artifacts.append(
                    {
                        "name": package_path.relative_to(run).as_posix(),
                        "sha256": domain._sha256_file(package_path),
                    }
                )
                for item in package["files"]:
                    file_path = package_path.parent / "site" / item["path"]
                    regular(file_path)
                    artifacts.append(
                        {
                            "name": file_path.relative_to(run).as_posix(),
                            "sha256": item["sha256"],
                        }
                    )
            for kind in sorted(state["sites_bindings"]):
                package, _ = domain._verify_current_package(run, kind)
                domain._verified_sites_binding(run, kind, package)
                for name in (
                    ".openai/vera-release-binding.json",
                    ".openai/vera-site-package.zip",
                ):
                    path = domain._run_file(run, "work/sites-project/" + name)
                    regular(path)
                    artifacts.append(
                        {
                            "name": path.relative_to(run).as_posix(),
                            "sha256": domain._sha256_file(path),
                        }
                    )
        result = {
            "workspace_id": manifest["workspace_id"],
            "studio": manifest["owner"],
            "run_id": state["run_id"],
            "intake": intake,
            "records": records,
            "validation": validation,
            "required_review_scopes": sorted(domain.REVIEW_SCOPES),
            "packages": packages,
            "artifacts": artifacts,
            "model_context_transferred": False,
            "original_sources_returned": False,
            "sent_or_published": False,
        }
    else:
        if files(workspace) != request["expected_files"]:
            raise ValueError("Website changed before the public producer call")
        fields = request["fields"]
        if action == "review":
            output = domain.record_review(
                run,
                scope=fields["scope"],
                decision=fields["decision"],
                reviewer=fields["reviewer"],
            )
            result = {"review_log": domain._load_json(output)}
        elif action == "validate_site":
            result = {"validation": domain._load_json(domain.validate_site(run))}
        elif action in {"package_preview", "package_release"}:
            output = domain.package_website(run, kind=action.removeprefix("package_"))
            result = {"package": domain._load_json(output)}
        elif action in {"sites_preview_binding", "sites_release_binding"}:
            kind = "preview" if action == "sites_preview_binding" else "release"
            output = domain.prepare_sites_binding(run, kind=kind)
            result = {"binding": domain._load_json(output)}
        elif action == "validate_run":
            result = domain.validate_run(run)
        else:
            raise ValueError("Unsupported website producer operation")
    sys.stdout.write(bounded(result))


if __name__ == "__main__":
    # Isolated Python intentionally omits ambient imports; add only this fixed
    # installed adapter directory, then the fixed resolved public module above.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
