"""Project Lucia's reviewed desktop document edition from current product source."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

__all__ = ["MARKETPLACE_WORKFLOWS", "marketplace_entries"]

MARKETPLACE_WORKFLOWS = frozenset(
    {
        "revisione-contratti",
        "controllo-documento",
        "confronto-documenti",
        "revisione-documentale",
        "estrazione-clausole",
        "redazione-da-modello",
    }
)
# Exclude execution entrypoints for omitted lifecycle/UI workflows, not shared
# reporting/runtime dependencies. No component or nested registration is copied.
EXCLUDED_SCRIPTS = frozenset(
    {
        "_desktop_teaching.py",
        "course_chat_bridge.py",
        "local_courses.py",
        "local_onboarding.py",
        "local_onboarding_case.py",
        "local_teaching.py",
        "onboarding_session_start.py",
        "lucia_studio_archive.py",
        "legal_playbook.py",
        "legal_playbook.schema.json",
        "legal_playbook_labels.json",
        "legal_citations.py",
        "legal_citations.schema.json",
        "legal_citations_labels.json",
        "legal_negotiation.py",
        "legal_negotiation.schema.json",
        "legal_negotiation_labels.json",
        "incident_tool_schemas.json",
    }
)


def _json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _replace(text: str, before: str, after: str) -> str:
    """Reject source drift rather than accidentally retain excluded routing."""
    if text.count(before) != 1:
        raise ValueError(f"Lucia edition source passage changed: {before[:90]}")
    return text.replace(before, after)


def marketplace_entries(package: Any, *, source_root: Path) -> dict[str, bytes]:
    """Keep maintained document engines and explicit edition-specific instructions."""
    from scripts.build_codex_plugin_zip import (
        add_portable_upload_manifests,
        add_vera_execution_manifest,
        project_chatgpt_manifest,
        source_zip_entries,
    )
    from scripts.project_product_privacy import project_privacy

    root = source_root / "plugins/lucia"
    edition = root / "distributions/marketplace"
    prefix = f"{package.package_root}/plugins/lucia/"
    raw = {
        name.removeprefix(prefix): content
        for name, content in source_zip_entries(package).items()
        if name.startswith(prefix)
    }
    entries = {"LICENSE": (source_root / "LICENSE").read_bytes()}
    for name, content in raw.items():
        parts = name.split("/")
        keep = (
            (
                parts[0] == "scripts"
                and len(parts) == 2
                and "mcp" not in parts[1]
                and parts[1] not in EXCLUDED_SCRIPTS
            )
            or (parts[0] == "skills" and parts[1] in MARKETPLACE_WORKFLOWS)
            or parts[0] == "privacy"
            or name == "usage/pipelines.json"
            or name == "assets/icon.svg"
            or (len(parts) == 1 and name.startswith(("requirements", "constraints")))
        )
        if name == "skills/revisione-contratti/references/practice-workflow.md":
            keep = False
        if keep:
            entries[name] = content
    entries["modules/README.md"] = (
        b"This edition embeds no workflow components. See distribution.json.\n"
    )
    entries["components.json"] = _json(
        {"schema_version": 1, "plugins": [], "workflow_roles": {}}
    )
    entries["scripts/check_dependencies.py"] = (
        edition / "check_dependencies.py"
    ).read_bytes()
    entries["skills/lucia/SKILL.md"] = (edition / "router.md").read_bytes()
    for ref in ("workflow-usage.md", "incident-recovery.md"):
        entries[f"skills/lucia/references/{ref}"] = (edition / ref).read_bytes()
    # Keep the actual report schema and interpretation contract; edition-specific
    # delivery below supersedes native transport suggestions in this common text.
    contract = raw["skills/lucia/references/model-data-report-contract.md"].decode()
    # Project only the ordinary Lucia contract; omitted lifecycle instructions
    # must not remain an executable fallback in this edition.
    contract = contract[contract.index("## Clara and Lucia chat inputs and drafts") :]
    start = contract.index("For Vera, if the user prohibits receipt transmission")
    end = contract.index("Otherwise the receipt-enabled", start)
    contract = (
        contract[:start]
        + "For a user-prohibited receipt transmission, add `--local-only` to the build command. Retain the local report and do not retry transmission without later authorization.\n\n"
        + contract[end:]
    )
    start = contract.index("For a Studio Archive run, declare")
    end = contract.index("Never write a client report in plugin source.", start)
    contract = (
        contract[:start]
        + "Keep reports in this task's chosen output folder. "
        + contract[end:]
    )
    start = contract.index("For a managed client run, use Studio Archive")
    end = contract.index("When several runs fit", start)
    contract = (
        contract[:start] + "Use the recorded document run folder. " + contract[end:]
    )
    contract = (
        "# Model-data report — document edition\n\nUse CLI delivery in workflow-usage.md. Reporting failures remain separate from the document outcome.\n\n"
        + contract
    )
    entries["skills/lucia/references/model-data-report-contract.md"] = contract.encode()
    block = (edition / "reporting-block.md").read_text()
    for workflow in MARKETPLACE_WORKFLOWS:
        name = f"skills/{workflow}/SKILL.md"
        text = entries[name].decode()
        text, count = re.subn(
            r"<!-- MPARANZA_REPORTING_BEGIN -->.*?<!-- MPARANZA_REPORTING_END -->",
            block,
            text,
            flags=re.S,
        )
        if count != 1:
            raise ValueError(f"{workflow}: expected one current reporting block")
        if workflow == "revisione-contratti":
            text = _replace(
                text,
                "Se l'utente richiede la tabella delle posizioni negoziali di un Word revisionato,\nleggi `../posizioni-negoziali/SKILL.md` e riusa prove e contesto già preparati.\n",
                "La tabella specialistica delle posizioni negoziali non è inclusa in questa edizione.\n",
            )
            text = _replace(
                text,
                "reuse the\nexisting legal-question workflow only when the user requests that wider work.",
                "that separate research workflow is not included in this edition.",
            )
        if workflow == "confronto-documenti":
            start = text.index("Per una sintesi delle revisioni Word")
            end = text.index("Read `", start)
            text = (
                text[:start]
                + "Il confronto richiede almeno due documenti selezionati.\n\n"
                + text[end:]
            )
        entries[name] = text.encode()
    name = "skills/revisione-contratti/references/document-workflow.md"
    text = entries[name].decode()
    text = _replace(
        text,
        "Choose topics semantically for the brief; these are examples.",
        "Do not create the run directory before prepare; keep preliminary logs in "
        "its parent. The helper creates a new run and refuses to overwrite existing "
        "evidence. Reopen existing work instead of preparing over it.\n\n"
        "Choose topics semantically for the brief; these are examples.",
    )
    start = text.index("If a reusable firm workflow was selected")
    end = text.index("Reuse the installed shared Python environment.", start)
    text = (
        text[:start]
        + "Use the user's supplied firm instructions as task context; this edition does not manage firm playbooks.\n\n"
        + text[end:]
    )
    text = _replace(
        text,
        "A specialist practice workflow may explicitly\nrequire source research through Lucia's canonical legal/tax journey; follow that\nworkflow's research contract while retaining these evidence and data boundaries.",
        "Specialist practice and legal research workflows are not included in this edition.",
    )
    entries[name] = text.encode()
    manifest = json.loads(project_chatgpt_manifest(raw[".codex-plugin/plugin.json"]))
    for key in ("mcpServers", "apps", "hooks", "extensions"):
        manifest.pop(key, None)
    description = "Revisione di contratti e documenti, confronto versioni, estrazione clausole e bozze da modelli forniti. Richiede esecuzione locale desktop."
    manifest["description"] = description
    manifest["keywords"] = ["lucia", "documenti", "contratti", "avvocati"]
    manifest["interface"]["longDescription"] = (
        description
        + " Output HTML/Excel e proposte motivate con fonti e lacune. Word con revisioni richiede la capacità documentale dell’host. Non include ricerca legale, apertura pratica, Archive, corsi o pannelli nativi."
    )
    manifest["interface"]["capabilities"] = ["Read", "Write", "Analysis"]
    entries[".codex-plugin/plugin.json"] = _json(manifest)
    add_portable_upload_manifests(entries)
    portable = json.loads(entries["plugin.json"])
    portable["extensions"]["com.openai"]["requires_local_executor"] = True
    entries["plugin.json"] = _json(portable)
    manifest = json.loads(entries[".codex-plugin/plugin.json"])
    manifest["requires_local_executor"] = True
    entries[".codex-plugin/plugin.json"] = _json(manifest)
    entries["distribution-review.json"] = (
        edition / "privacy-projection.json"
    ).read_bytes()
    entries["distribution.json"] = _json(
        {
            "schema_version": 1,
            "product": "lucia",
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
        "lucia",
        host="openai-codex",
        source_root=source_root,
        edition_policy=policy,
    )
    add_vera_execution_manifest(entries)
    return dict(sorted(entries.items()))
