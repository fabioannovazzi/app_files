"""Project Clara's bounded local-file edition from maintained workflow source."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

__all__ = ["MARKETPLACE_WORKFLOWS", "marketplace_entries"]

MARKETPLACE_WORKFLOWS = frozenset(
    {"advisory-brief-planner", "html-deck", "claim-basis-map"}
)
# Existing reporting/runtime implementations stay intact. They are infrastructure,
# not public workflow entrypoints. Retain lineage helpers used by standalone
# decks and claim maps, but omit the unused case lifecycle and its normalizer.
SCRIPT_NAMES = frozenset(
    {
        "validate_advisory_contract.py",
        "html_deck_runtime.py",
        "local_helper_environment.py",
        "local_helper_environment.json",
        "local_helper_environment.cjs",
        "advisory_evidence_lineage.py",
        "advisory_lineage_labels.py",
        "case_store.py",
        "bounded_process.py",
        "render_attempt.py",
        "preparation_contract_kernel.py",
        "case_exchange_safety.py",
        "artifact_publication.py",
        "media_publication.py",
        "reporting_product.py",
        "workflow_usage.py",
        "operational_incidents.py",
        "diagnostic_context.py",
        "technical_runner.py",
        "model_data_report.py",
        "privacy_contract.py",
        "notarized_run_receipt.py",
        "selective_reporting.py",
        "verified_execution.py",
        "self_relaunch.py",
        "managed_python_runtime.py",
        "_managed_python_runtime.py",
        "_shared_python_runtime.py",
        "_locked_dependencies.py",
        "_python_bootstrap.py",
        "bootstrap_python_dependencies.py",
        "managed_ocr_runtime.py",
        "archive_cli.py",
        "archive_emit.py",
        "archive_projection.py",
        "archive_report_legacy.py",
        "archive_report_measurements.py",
        "archive_report_receipt.py",
        "archive_report_seal.py",
        "archive_report_store.py",
        "archive_reporting.py",
        "archive_reporting_failure.py",
        "public_http.py",
    }
)


def _json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _passage(text: str, start: str, end: str, replacement: str) -> str:
    """Require explicit source anchors to avoid unnoticed routing drift."""
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"Clara edition source passage changed: {start}")
    first = text.index(start)
    last = text.index(end, first)
    return text[:first] + replacement + text[last:]


def _project_skill(workflow: str, text: str, block: str) -> str:
    for marker, replacement in (
        ("MPARANZA_REPORTING", block),
        ("CLARA_OPENAI_ONBOARDING", ""),
    ):
        text, count = re.subn(
            rf"<!-- {marker}_BEGIN -->.*?<!-- {marker}_END -->",
            lambda match: replacement,
            text,
            flags=re.S,
        )
        if count != 1:
            raise ValueError(f"{workflow}: expected one {marker} source block")
    if workflow == "html-deck":
        text = _passage(text, "- For a Clara case, build only", "- Keep user data", "")
        text = _passage(
            text,
            "## Retain bound build artifacts",
            "## Decision boundary",
            "## Retain build artifacts\n\nKeep prior content-addressed builds and their source ledgers alongside revisions.\nThis edition builds standalone decks, not case-bound delivery receipts.\n\n",
        )
        text = text.replace(" \\\n  --case-dir <case-dir>", "")
        text = _passage(
            text,
            "For a deck that belongs to a Clara advisory case,",
            "Legacy v1 quantitative",
            "",
        )
        text = _passage(
            text, "For a case-bound deck, HTML checks", "## Codex-Native Run UX", ""
        )
        text = text.replace(
            "- for a case-bound deck, the `advisory_html_delivery_receipt.json` ready result;\n",
            "",
        )
        text = _passage(
            text,
            "Include this user-facing revision affordance",
            "Create `codex_run_review.md`",
            "For revisions, use this skill's revision mode with written feedback.\nNo publication has occurred merely because a deck is ready to review.\n",
        )
    elif workflow == "claim-basis-map":
        text = _passage(
            text,
            "When the deck is generated inside a Clara case",
            "When the deck generator",
            "",
        )
        text = text.replace(
            "  --case-dir <case-dir> \\\n  --evidence-register <case-dir>/advisory_evidence_register.json \\\n  --claim-register <case-dir>/advisory_claim_register.json \\\n",
            "",
        )
        text = _passage(text, "With `--case-dir`,", "Use `--snapshot-output", "")
        text = text.replace("plugins/clara/skills/", "skills/")
    elif workflow == "advisory-brief-planner":
        text = _passage(
            text,
            "For a durable advisory case,\nhandoff normally",
            "## Meaning and mechanical boundary",
            "Hand off only to an installed retained workflow. This edition does not\nmanage durable advisory cases or execute a wider analysis from the contract.\n\n",
        )
        text = _passage(
            text,
            "   `clara:advisory-case-director`",
            "3. Identify only material",
            "   a retained standalone workflow. The contract must not promise omitted\n   services or route to this planner recursively.\n",
        )
    if workflow == "claim-basis-map":
        text = text.replace(
            "The command also writes `deck.claims.audit.json`. Its authoritative\n"
            "`source: clara_claim_basis_map_audit` and `result` fields are what the advisory\n"
            "deliverable validator consumes.",
            "The command also writes `deck.claims.audit.json`, recording the source\n"
            "and result of this standalone claim check.",
        )
    return text


def marketplace_entries(package: Any, *, source_root: Path) -> dict[str, bytes]:
    """Build explicit reduced routing without mutating the complete edition."""
    from scripts.build_codex_plugin_zip import (
        add_portable_upload_manifests,
        add_vera_execution_manifest,
        project_chatgpt_manifest,
        source_zip_entries,
    )
    from scripts.project_product_privacy import project_privacy

    edition = source_root / "plugins/clara/distributions/marketplace"
    prefix = f"{package.package_root}/plugins/clara/"
    raw = {
        name.removeprefix(prefix): content
        for name, content in source_zip_entries(package).items()
        if name.startswith(prefix)
    }
    entries = {"LICENSE": (source_root / "LICENSE").read_bytes()}
    for name, content in raw.items():
        parts = name.split("/")
        if (
            (parts[0] == "scripts" and len(parts) == 2 and parts[1] in SCRIPT_NAMES)
            or (parts[0] == "skills" and parts[1] in MARKETPLACE_WORKFLOWS)
            or parts[0] in {"privacy", "contracts"}
            or name in {"usage/pipelines.json", "assets/icon.svg", "assets/icon.png"}
            or (len(parts) == 1 and name.startswith(("requirements", "constraints")))
        ):
            entries[name] = content
    # Diagnostic context hydration imports this package lazily. Keep its owned
    # library without exposing Archive workflows or depending on a sibling install.
    vendor = source_root / "plugins/_shared/vendor/modules/vera_assurance"
    for path in sorted(vendor.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".cjs"}:
            entries[
                f"vendor/modules/vera_assurance/{path.relative_to(vendor).as_posix()}"
            ] = path.read_bytes()
    entries["modules/README.md"] = b"No embedded workflow components in this edition.\n"
    entries["components.json"] = _json({"schema_version": 1, "plugins": []})
    usage = json.loads(entries["usage/pipelines.json"])
    usage["infrastructure"] = []
    entries["usage/pipelines.json"] = _json(usage)
    entries["requirements.txt"] = (
        b"jsonschema>=4.23,<5\npython-pptx>=0.6.23\nplaywright>=1.48.0\ndefusedxml>=0.7.1,<1\n"
    )
    checker = raw["scripts/check_dependencies.py"].decode()
    checker, count = re.subn(
        r"COMPONENTS = \(.*?\n\)", "COMPONENTS = ()", checker, count=1, flags=re.S
    )
    if count != 1:
        raise ValueError("Clara dependency component declaration changed")
    entries["scripts/check_dependencies.py"] = checker.encode()
    entries["skills/clara/SKILL.md"] = (edition / "router.md").read_bytes()
    for ref in ("workflow-catalog.md", "workflow-usage.md", "incident-recovery.md"):
        entries[f"skills/clara/references/{ref}"] = (edition / ref).read_bytes()
    contract = raw["skills/clara/references/model-data-report-contract.md"].decode()
    # Keep the schema and receipt interpretation; remove instructions for omitted
    # teaching and other products instead of leaving conflicting active routes.
    contract = (
        "# Run-level model-data report contract\n\n"
        + contract[contract.index("For Clara and Lucia, use this contract") :]
    )
    contract = _passage(
        contract,
        "Studio Archive also reuses this input schema",
        "## Clara and Lucia chat inputs",
        "",
    )
    contract = _passage(
        contract,
        "For a Studio Archive run,",
        "Never write a client report",
        "Keep reports and their privacy contract in the exact selected output folder. ",
    )
    contract = _passage(
        contract,
        "or engagement. For a managed client run,",
        "When several runs fit,",
        "or assignment. Use the recorded output folder. ",
    )
    contract = contract.replace(
        '"workflow_id": "variance-analysis"', '"workflow_id": "html-deck"'
    )
    entries["skills/clara/references/model-data-report-contract.md"] = contract.encode()
    block = (edition / "reporting-block.md").read_text()
    for workflow in MARKETPLACE_WORKFLOWS:
        name = f"skills/{workflow}/SKILL.md"
        entries[name] = _project_skill(workflow, entries[name].decode(), block).encode()
    # A component-generated evidence file may be supplied as an input, but this
    # edition must not direct users to an absent reporting engine.
    name = "skills/html-deck/references/evidence-bindings.md"
    text = entries[name].decode()
    if "`modules/reporting-engine/scripts/render_capability.py`" in text:
        text = text.replace(
            "`modules/reporting-engine/scripts/render_capability.py`",
            "An upstream reporting producer (outside this edition)",
        )
    entries[name] = text.encode()
    name = "skills/html-deck/references/quality-bar.md"
    entries[name] = entries[name].replace(
        b"- Clara Voice Capture slide ID/title metadata.",
        b"- Stable slide ID/title metadata for revisions.",
    )
    name = "skills/advisory-brief-planner/references/advisory-contract.md"
    entries[name] = entries[name].replace(
        b"required before delivery. These nested controls are the stable handoff consumed\ndirectly by `clara:advisory-deliverable-validator`.",
        b"required before delivery. These controls document the review required for the selected retained workflow; this edition does not include the full advisory validator.",
    )
    manifest = json.loads(project_chatgpt_manifest(raw[".codex-plugin/plugin.json"]))
    for key in ("mcpServers", "apps", "hooks", "extensions"):
        manifest.pop(key, None)
    description = "Plan bounded advisory assignments, build standalone HTML presentations and audit presentation claim bases. Requires local desktop execution."
    manifest["description"] = description
    manifest["keywords"] = ["clara", "presentations", "evidence", "assignment-planning"]
    manifest["interface"].update(
        {
            "shortDescription": "Presentations and evidence",
            "logo": "./assets/icon.png",
            "composerIcon": "./assets/icon.png",
            "longDescription": description
            + " Source-bound decks retain browser QA and professional review. No hosted interviews, voice, case lifecycle, teaching or native panels are included.",
            "capabilities": ["Read", "Write", "Analysis"],
            "defaultPrompt": [
                "Build a standalone HTML presentation from these selected sources.",
                "Map this presentation's claims to their supplied evidence.",
                "Plan a bounded presentation assignment from this brief.",
            ],
        }
    )
    manifest["requires_local_executor"] = True
    entries[".codex-plugin/plugin.json"] = _json(manifest)
    add_portable_upload_manifests(entries)
    portable = json.loads(entries["plugin.json"])
    portable["extensions"]["com.openai"]["requires_local_executor"] = True
    entries["plugin.json"] = _json(portable)
    entries["distribution.json"] = _json(
        {
            "schema_version": 1,
            "product": "clara",
            "edition": "marketplace",
            "workflows": sorted(MARKETPLACE_WORKFLOWS),
            "requires_local_executor": True,
            "bundled_mcp": False,
            "native_host_acceptance": "not_established_by_build",
        }
    )
    policy = json.loads((edition / "privacy-projection.json").read_text())
    project_privacy(
        entries,
        "clara",
        host="openai-codex",
        source_root=source_root,
        edition_policy=policy,
    )
    add_vera_execution_manifest(entries)
    return dict(sorted(entries.items()))
