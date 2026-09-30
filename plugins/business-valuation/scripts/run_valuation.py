"""Prepare valuation workpapers inside one running Studio Archive engagement."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (
    ROOT / "vendor/modules",
    ROOT.parent.parent / "vendor/modules",
    ROOT.parent / "_shared/vendor/modules",
):
    if (candidate / "vera_assurance").is_dir():
        sys.path.insert(0, str(candidate))
        break

from valuation_case import (  # noqa: E402
    build_valuation,
    read_json,
    require,
    source_paths,
)
from valuation_report import write_package  # noqa: E402
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main", "run_case"]


def run_case(case_path: Path, context_path: Path) -> dict:
    """Validate exact receipts before reading case data or writing any outputs."""
    context = load_client_engagement_context_file(
        context_path, expected_workflow_id="business-valuation", input_paths=[case_path]
    )
    require(
        context["schema_version"] == "vera.client_workflow_context.v2",
        "Valuation requires a portable v2 context",
    )
    root = Path(context["run_root"]) / "inputs"
    output = Path(context["output_dir"])
    case = read_json(case_path)
    paths = source_paths(case, root)
    context = load_client_engagement_context_file(
        context_path,
        expected_workflow_id="business-valuation",
        input_paths=[case_path, *paths],
        output_dir=output,
    )
    if "plan_binding" in case:
        source = next(
            row
            for row in case["sources"]
            if row["id"] == case["plan_binding"]["source_id"]
        )
        plan_path = (root / source["path"]).resolve()
        binding = next(
            (
                row
                for row in context["input_bindings"]
                if Path(row["path"]).resolve() == plan_path
            ),
            None,
        )
        require(
            binding is not None
            and binding["kind"] == "upstream_artifact"
            and binding["upstream_workflow_id"] == "business-planning",
            "Plan must be a finalized same-engagement Business Planning artifact",
        )
    replay = output / "plan-replay"
    report = build_valuation(case, root, replay_parent=replay)
    revision = output / f"valuation-{report['case_sha256'][:20]}"
    if revision.exists():
        require(
            (revision / "artifacts.json").is_file(),
            "Incomplete prior export retained; review it before creating a new case revision",
        )
        artifacts = json.loads(
            (revision / "artifacts.json").read_text(encoding="utf-8")
        )
        for artifact in artifacts:
            name = Path(artifact["path"])
            require(
                len(name.parts) == 1 and not name.is_absolute(), "Invalid artifact path"
            )
            path = revision / name
            require(
                path.is_file()
                and not path.is_symlink()
                and hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"],
                "Existing valuation artifact changed",
            )
        require(
            read_json(revision / "valuation.json") == report,
            "Existing revision differs from current replay",
        )
    else:
        # Recheck receipts immediately before exporting to narrow source-change races.
        load_client_engagement_context_file(
            context_path,
            expected_workflow_id="business-valuation",
            input_paths=[case_path, *paths],
            output_dir=revision,
        )
        write_package(report, root, revision, replay_parent=replay)
    return {
        "status": report["status"],
        "output_dir": str(revision),
        "report_sha256": report["report_sha256"],
        "run_id": context["run_id"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_case(args.case, args.client_engagement)
    except (
        AssuranceContractError,
        ValueError,
        OSError,
        KeyError,
        TypeError,
        StopIteration,
    ) as exc:
        logging.error("Valuation blocked: %s", exc)
        return 2
    logging.info("%s", json.dumps(result, ensure_ascii=False))
    return 2 if result["status"] in {"blocked", "partial"} else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
