from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "audit-reconciliation"
FILE_PREPARATION_PLUGIN = ROOT / "plugins" / "client-file-preparation"


def test_plugin_manifest_and_marketplace_entry_are_valid():
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    marketplace = json.loads(
        (ROOT / ".agents" / "plugins" / "marketplace.json").read_text()
    )

    assert manifest["name"] == "audit-reconciliation"
    assert manifest["skills"] == "./skills/"
    assert manifest["interface"]["displayName"]
    manifest_text = json.dumps(manifest, ensure_ascii=False)
    for snippet in (
        "partite aperte",
        "mastrini",
        "distinte",
        "factoring",
        "compensazioni",
        "workpaper Excel/Word",
    ):
        assert snippet in manifest_text

    assert marketplace["plugins"] == []


def test_plugin_contains_no_customer_specific_artifacts_or_terms():
    forbidden = (
        "/users/",
        "\\users\\",
        "/home/",
        "/root/",
        "@gmail.com",
        "@icloud.com",
        "@outlook.com",
    )
    text_parts: list[str] = []
    for path in PLUGIN.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".py", ".md", ".json", ".txt"}:
            text_parts.append(path.read_text(encoding="utf-8", errors="ignore").lower())
    all_text = "\n".join(text_parts)

    assert not any(term in all_text for term in forbidden)
    assert not (PLUGIN / "examples").exists()


def test_file_preparation_engine_contains_no_customer_specific_artifacts_or_terms():
    forbidden = (
        "/users/",
        "\\users\\",
        "/home/",
        "/root/",
        "@gmail.com",
        "@icloud.com",
        "@outlook.com",
    )
    text_parts: list[str] = []
    for path in FILE_PREPARATION_PLUGIN.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".py", ".md", ".json", ".txt"}:
            text_parts.append(path.read_text(encoding="utf-8", errors="ignore").lower())
    all_text = "\n".join(text_parts)

    assert not any(term in all_text for term in forbidden)
    assert not (FILE_PREPARATION_PLUGIN / "examples").exists()


def test_plugin_beta_onboarding_and_prompt_bank_are_documented():
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    skill = (PLUGIN / "skills" / "audit-reconciliation" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    starter_prompts = (PLUGIN / "references" / "starter-prompts.md").read_text(
        encoding="utf-8"
    )
    combined = f"{readme}\n{skill}\n{starter_prompts}".lower()

    for snippet in (
        "Primo run beta",
        "First Run",
        "Prompt di avvio per beta user",
        "Starter Prompt Bank",
        "Riconciliazione completa",
        "Full open-item reconciliation",
        "Mastrino",
        "Missing-evidence request pack",
        "Reviewer sample / exception review",
        "Post-cut-off evidence review",
        "python scripts/check_dependencies.py",
        "periodo e cut-off",
        "file che contiene la popolazione",
        "assunzioni sulle evidenze",
        "Default factoring/anticipo",
        "Default factoring treatment",
        "stricter-than-default factoring treatment",
        "pagamento presente negli estratti conto",
        "source_pages.json",
    ):
        assert snippet.lower() in combined


def test_file_preparation_engine_run_guidance_and_prompt_bank_are_documented():
    readme = (FILE_PREPARATION_PLUGIN / "README.md").read_text(encoding="utf-8")
    skill = (
        FILE_PREPARATION_PLUGIN / "skills" / "client-file-preparation" / "SKILL.md"
    ).read_text(encoding="utf-8")
    workflow_reference = (
        FILE_PREPARATION_PLUGIN / "references" / "workflow-reference.md"
    ).read_text(encoding="utf-8")
    combined = f"{readme}\n{skill}\n{workflow_reference}".lower()

    for snippet in (
        "Primo run beta",
        "First Run",
        "Prompt di avvio per beta user",
        "Starter Prompt Bank",
        "Istruttoria completa fascicolo cliente",
        "730/Redditi PF first intake",
        "Geneva / Zurich intake",
        "UK Self Assessment intake",
        "FatturaPA XML formal check",
        "Structured fiscal fields",
        "Missing-document email pack",
        "Avviso intake",
        "python scripts/check_dependencies.py --folder",
        "cartella cliente",
        "giurisdizione",
        "anno target",
        "OCR",
        "dati fiscali strutturati",
        "bozza email cliente",
        "Geneva",
        "Zurich",
        "UK",
    ):
        assert snippet.lower() in combined
