"""Exercise a staged Clara ZIP with synthetic local-file workflows and retained evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

__all__ = ["main"]
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/clara_distribution"


def main() -> int:
    """Run actual packaged CLIs; do not substitute source imports or native acceptance."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reports-only", action="store_true")
    parser.add_argument("--helper-python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=args.reports_only)
    installed = output / "installed"
    if not args.reports_only:
        with ZipFile(args.package) as archive:
            archive.extractall(installed)
    if not (installed / ".codex-plugin/plugin.json").is_file():
        roots = list(installed.glob("*/plugins/clara/.codex-plugin/plugin.json"))
        if len(roots) != 1:
            raise ValueError("Expected one Clara root in exact ZIP")
        installed = roots[0].parents[1]
    results = {
        "package": str(args.package.resolve()),
        "sha256": hashlib.sha256(args.package.read_bytes()).hexdigest(),
        "evidence_level": "extracted_exact_package_cli_not_native_host_acceptance",
        "commands": [],
        "pipeline_outcomes": {},
        "privacy_outcome": "pending",
    }
    if args.reports_only:
        results = json.loads((output / "acceptance.json").read_text())
        assert (
            results["sha256"] == hashlib.sha256(args.package.read_bytes()).hexdigest()
        )
    environment = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        MPARANZA_INCIDENT_DELIVERY="local-only",
        MPARANZA_INCIDENT_STATE_DIR=str(output / "incident-state"),
        MPARANZA_INCIDENT_DEVICE_DIR=str(output / "device-state"),
    )

    def command(
        label: str, relative: str, *arguments: str, expected: int = 0
    ) -> subprocess.CompletedProcess[str]:
        label = ("retry-" + label) if args.reports_only else label
        result = subprocess.run(
            [
                str(args.helper_python),
                "-I",
                "-B",
                "-c",
                "import runpy,sys; from pathlib import Path; p=sys.argv.pop(1); "
                "sys.path.insert(0,str(Path(p).parent)); runpy.run_path(p,run_name='__main__')",
                str(installed / relative),
                *map(str, arguments),
            ],
            cwd=installed,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        (output / f"{label}.stdout.txt").write_text(result.stdout)
        (output / f"{label}.stderr.txt").write_text(result.stderr)
        results["commands"].append(
            {
                "label": label,
                "script": relative,
                "arguments": list(map(str, arguments)),
                "exit_code": result.returncode,
                "expected_exit": expected,
            }
        )
        (output / "acceptance.json").write_text(json.dumps(results, indent=2) + "\n")
        if result.returncode != expected:
            raise RuntimeError(
                f"{label}: exit {result.returncode}; see retained stderr"
            )
        return result

    if not args.reports_only:
        command("dependencies", "scripts/check_dependencies.py")
        assignment = output / "assignment"
        assignment.mkdir()
        shutil.copy2(FIXTURES / "assignment.md", assignment)
        shutil.copy2(FIXTURES / "contract.json", assignment / "draft.json")
        command(
            "assignment",
            "scripts/validate_advisory_contract.py",
            assignment / "draft.json",
            "--output-dir",
            assignment / "reviewed",
            "--source",
            f"assignment={assignment / 'assignment.md'}",
        )
        reviewed = json.loads(
            (assignment / "reviewed/advisory_contract.json").read_text()
        )
        assert reviewed["selected_clara_workflow"] == "clara:html-deck"
        assert reviewed["source_facts"][2]["literal_value"] == "EUR 12.5"
        invalid = json.loads((assignment / "draft.json").read_text())
        invalid["source_facts"][2]["literal_value"] = "EUR 99.9"
        (assignment / "invalid.json").write_text(json.dumps(invalid))
        command(
            "assignment-wrong-literal",
            "scripts/validate_advisory_contract.py",
            assignment / "invalid.json",
            "--output-dir",
            assignment / "rejected",
            "--source",
            f"assignment={assignment / 'assignment.md'}",
            expected=1,
        )
        assert not (assignment / "rejected/advisory_contract.json").exists()
        results["pipeline_outcomes"][
            "advisory-brief-planner"
        ] = "passed: contract and source literals; altered amount rejected"

        work = output / "deck-work"
        command(
            "deck-init",
            "skills/html-deck/scripts/init_html_deck.py",
            "--work-dir",
            work,
            "--title",
            "Synthetic diligence evidence",
            "--subtitle",
            "Financial and customer observations",
            "--language",
            "en",
        )
        shutil.copytree(FIXTURES / "deck", work, dirs_exist_ok=True)
        command(
            "deck-compose",
            "skills/html-deck/scripts/compose_html_deck.py",
            work / "deck-plan.json",
            "--output-dir",
            work,
            "--force",
        )
        command(
            "deck-build",
            "skills/html-deck/scripts/build_html_deck.py",
            work,
            "--output-root",
            output / "deck",
            "--package",
            output / "deck.zip",
            "--report",
            output / "deck-validation.json",
        )
        html_path = next((output / "deck").glob("*/index.html"))
        assert "Revenue is $25.4m" in html_path.read_text()
        command(
            "deck-browser",
            "skills/html-deck/scripts/browser_qa_html_deck.py",
            html_path,
            "--output-dir",
            output / "browser",
            "--report",
            output / "browser-qa.json",
            "--warnings-as-errors",
        )
        # Exercise the documented revision path from the delivered standalone HTML.
        inventory_path = output / "baseline-inventory.json"
        command(
            "revision-inspect",
            "skills/html-deck/scripts/inspect_html_deck.py",
            html_path,
            "--report",
            inventory_path,
        )
        inventory = json.loads(inventory_path.read_text())
        revision_map = {
            "schema_version": "clara.html_deck_revision_map.v1",
            "baseline_fingerprint": inventory["deck"]["normalized_dom_fingerprint"],
            "edit_targets": [
                {
                    "slide_id": "next-work",
                    "scope": "slide",
                    "reason": "Clarify the requested evidence review.",
                }
            ],
            "global_edits": [],
            "untouched_slides": ["diligence-evidence"],
            "protected_slides": [],
            "protected_components": [],
            "slide_changes": {"add": [], "remove": [], "rename": []},
        }
        map_path = output / "revision-map.json"
        map_path.write_text(json.dumps(revision_map, indent=2))
        command(
            "revision-map",
            "skills/html-deck/scripts/validate_revision_map.py",
            html_path,
            map_path,
            "--report",
            output / "revision-map-validation.json",
        )
        revised = output / "revised.html"
        revised.write_text(
            html_path.read_text().replace(
                "The supplied concentration snapshot does not establish customer retention.",
                "Review customer retention evidence before drawing a conclusion.",
            )
        )
        command(
            "revision-compare",
            "skills/html-deck/scripts/compare_html_deck_revision.py",
            html_path,
            revised,
            "--revision-map",
            map_path,
            "--report",
            output / "revision-comparison.json",
        )
        command(
            "revision-browser",
            "skills/html-deck/scripts/browser_qa_html_deck.py",
            revised,
            "--output-dir",
            output / "revision-browser",
            "--report",
            output / "revision-browser-qa.json",
            "--warnings-as-errors",
        )
        unauthorized = output / "unauthorized-revision.html"
        unauthorized.write_text(
            revised.read_text().replace("Revenue is $25.4m", "Revenue is $99.9m")
        )
        command(
            "revision-undeclared-change",
            "skills/html-deck/scripts/compare_html_deck_revision.py",
            html_path,
            unauthorized,
            "--revision-map",
            map_path,
            "--report",
            output / "revision-rejected.json",
            expected=1,
        )
        (work / "financial-facts.csv").write_text(
            (work / "financial-facts.csv")
            .read_text()
            .replace("25356432.55", "99999999.99")
        )
        command(
            "deck-altered-evidence",
            "skills/html-deck/scripts/compose_html_deck.py",
            work / "deck-plan.json",
            "--output-dir",
            output / "rejected-deck",
            expected=2,
        )
        shutil.copy2(FIXTURES / "deck/financial-facts.csv", work)
        results["pipeline_outcomes"][
            "html-deck"
        ] = "passed: source-bound quantitative deck, strict browser QA, altered evidence rejected; visual review separate"

        claims = output / "claims"
        claims.mkdir()
        shutil.copy2(FIXTURES / "claims.json", claims)
        # Input generation is separate from the packaged checker being accepted.
        from pptx import Presentation

        presentation = Presentation()
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        from pptx.util import Inches

        textbox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1))
        textbox.name = "clara-claim:revenue"
        textbox.text_frame.text = "Revenue is $25.4m"
        presentation.save(claims / "synthetic.pptx")
        command(
            "claims",
            "skills/claim-basis-map/scripts/render_claim_basis_map.py",
            claims / "claims.json",
            "--current-pptx",
            claims / "synthetic.pptx",
            "--output",
            claims / "claims.md",
            "--audit-output",
            claims / "claims.audit.json",
        )
        assert "Revenue is $25.4m" in (claims / "claims.md").read_text()
        textbox.text_frame.text = "Revenue is $99.9m"
        presentation.save(claims / "altered.pptx")
        command(
            "claims-drift",
            "skills/claim-basis-map/scripts/render_claim_basis_map.py",
            claims / "claims.json",
            "--current-pptx",
            claims / "altered.pptx",
            "--output",
            claims / "drift.md",
            "--audit-output",
            claims / "drift.audit.json",
            expected=1,
        )
        results["pipeline_outcomes"][
            "claim-basis-map"
        ] = "passed: current PPTX checked and sidecar written; altered claim rejected"
    if not args.reports_only:
        (output / "pipeline-evidence.json").write_text(
            json.dumps(results, indent=2) + "\n"
        )
    results["privacy_outcome"] = {}
    for workflow in results["pipeline_outcomes"]:
        report_dir = (
            output / ("privacy-retry" if args.reports_only else "privacy") / workflow
        )
        report_dir.mkdir(parents=True)
        shutil.copy2(output / "pipeline-evidence.json", report_dir)
        report_input = {
            "schema_version": 1,
            "workflow_id": workflow,
            "run_id": "run_" + uuid4().hex[:24],
            "runtime_profile": "openai-codex",
            "language": "en",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "professional_purpose": "Synthetic exact-package acceptance; no client engagement.",
            "phases": [
                {
                    "phase_id": "fixture-and-output-review",
                    "purpose": "Review synthetic inputs, helper results and failure diagnostics.",
                    "outcome": "not_measurable",
                    "evidence_basis": "host_attested",
                    "source_extent": [],
                    "locally_processed": [],
                    "model_visible": [],
                    "remained_local": [],
                    "reason": "Synthetic fixture content, source code and command results are available to the host agent. Exact provider payload extent is not measured; local execution does not imply no model exposure.",
                    "evidence_files": ["pipeline-evidence.json"],
                }
            ],
            "improvement_assessment": {"status": "none_supported", "candidates": []},
            "contract_review": {
                "status": "consistent",
                "phase_ids": ["fixture-and-output-review"],
                "reason": "Agent review: local selected-file processing and host-context review fit the retained workflow boundary. Hosted services and receipt transmission were not used in this test; provider-level measurement remains unknown.",
            },
        }
        input_path = report_dir / "input.json"
        input_path.write_text(json.dumps(report_input, indent=2) + "\n")
        try:
            command(
                "privacy-" + workflow,
                "scripts/model_data_report.py",
                "build",
                "--input",
                input_path,
                "--evidence-root",
                report_dir,
                "--output-dir",
                report_dir,
                "--local-only",
            )
            saved = report_dir / "model_data_report.json"
            before = saved.read_bytes()
            command(
                "privacy-validate-" + workflow,
                "scripts/model_data_report.py",
                "validate",
                "--report",
                saved,
            )
            command(
                "privacy-reopen-" + workflow,
                "scripts/model_data_report.py",
                "show",
                "--report",
                saved,
            )
            assert saved.read_bytes() == before
            # A failed report validation must leave the useful output and original
            # report intact; exercise the real CLI without retrying the pipeline.
            professional_files = [
                output / "assignment/reviewed/advisory_contract.json",
                output / "deck.zip",
                output / "claims/claims.md",
            ]
            professional_hashes = {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in professional_files
            }
            invalid_report = report_dir / "invalid-report.json"
            invalid_report.write_text('{"schema_version": 999}')
            command(
                "privacy-invalid-" + workflow,
                "scripts/model_data_report.py",
                "validate",
                "--report",
                invalid_report,
                expected=2,
            )
            assert saved.read_bytes() == before
            assert professional_hashes == {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in professional_files
            }
            results["privacy_outcome"][
                workflow
            ] = "local report built, validated and reopened unchanged; transmission not requested; provider measurement and server/userID receipt acceptance remain unverified"
        except RuntimeError as error:
            results["privacy_outcome"][workflow] = str(error)

    (output / "acceptance.json").write_text(json.dumps(results, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
