"""Isolated calls to the shared public Business Planning compiler."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Replay canonical plans; never author business judgments or review stamps."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    import check_dependencies

    if check_dependencies.main([]):
        raise ValueError("Business Planning declared dependencies are unavailable")
    import reporting_table
    import run_business_plan
    import vera_assurance
    from business_planning_core import load_json
    from planning_report import compile_html
    from planning_workflow import build_plan, digest, validate_plan

    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "contract":
        result = {
            "implementation": {
                p.relative_to(root)
                .as_posix(): hashlib.sha256(p.read_bytes())
                .hexdigest()
                for p in sorted(
                    [
                        *(root / "scripts").glob("*.py"),
                        *(root / "assets").glob("report-interaction.*"),
                        root / "requirements.txt",
                    ]
                )
            }
        }
        shared = Path(vera_assurance.__file__).parent
        result["implementation"].update(
            {
                "vendor/modules/vera_assurance/"
                + p.relative_to(shared)
                .as_posix(): hashlib.sha256(p.read_bytes())
                .hexdigest()
                for p in sorted(shared.rglob("*.py"))
            }
        )
        result["implementation"]["vendor/modules/reporting_table.py"] = hashlib.sha256(
            Path(reporting_table.__file__).read_bytes()
        ).hexdigest()
    else:
        source_root = Path(request["source_root"])
        case = load_json(Path(request["case"]))
        plan = build_plan(case, source_root=source_root)
        # This includes the unchanged exact audience-release boundary.
        report = compile_html(plan, source_root=source_root)
        if request["operation"] == "prepare":
            exit_code = run_business_plan.main(
                [
                    "--case",
                    request["case"],
                    "--source-root",
                    request["source_root"],
                    "--output-dir",
                    request["output"],
                    "--client-engagement",
                    request["context"],
                ]
            )
            if exit_code not in {0, 2}:
                raise ValueError("Business Planning did not persist a normal result")
        if request["operation"] in {"prepare", "read"}:
            output = Path(request["output"])
            retained = load_json(output / "business_plan.json")
            validate_plan(retained, source_root=source_root)
            if (
                retained != plan
                or (output / "business_plan_review.html").read_text(encoding="utf-8")
                != report
            ):
                raise ValueError("Business Planning report differs from public replay")
            receipt = load_json(output / "execution_receipt.json")
            if (
                receipt["content_sha256"]
                != digest({k: v for k, v in receipt.items() if k != "content_sha256"})
                or receipt["status"] != plan["status"]
                or receipt["case_sha256"] != plan["case_sha256"]
                or receipt["calculations_sha256"] != plan["calculations_sha256"]
                or receipt["pdf_error"] is not None
                or receipt["pdf_mode"] is not None
            ):
                raise ValueError("Business Planning execution receipt disagrees")
            for row in receipt["outputs"]:
                path = output / row["path"]
                if (
                    path.parent != output
                    or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]
                ):
                    raise ValueError("Business Planning public artifact differs")
        elif request["operation"] != "inspect":
            raise ValueError("Unknown Business Planning operation")
        result = {"plan": plan, "report": report}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
