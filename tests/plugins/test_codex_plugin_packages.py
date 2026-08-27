from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build_codex_plugin_zip.py"
COMMERCIALISTA_MODULE_NAMES = {
    "archive-organization",
    "open-item-reconciliation",
    "bandi-agevolazioni",
    "bilancio-xbrl-it",
    "browser-automation",
    "startup-business-plan",
    "check-entries",
    "concordato-plan-review",
    "comunicazione-professionale",
    "presenza-digitale-studio",
    "deep-research-validator",
    "financial-analysis",
    "management-control-pack",
    "centrale-rischi-review",
    "sales-plan",
    "variance-analysis",
    "client-file-preparation",
    "new-client",
    "journal-bank-reconciliation",
    "passive-invoice-audit",
    "journal-sampling",
    "prompt-optimizer",
    "previdenza-inps",
    "registro-imprese-sari",
    "report-builder",
    "studio-archive",
}
STANDALONE_PLUGIN_NAMES = {"attribute-reporting", "clara", "lucia"}
PRIVATE_STANDALONE_PLUGIN_NAMES = {"attribute-reporting"}
UNIFIED_PLUGIN_NAMES = {"vera"}
VERA_DISCOVERY_TERMS = (
    "commercialista",
    "studi professionali",
    "contabilità",
    "controlli contabili",
    "scritture contabili",
    "riconciliazione bancaria",
    "bilancio civilistico",
    "ricerca fiscale",
    "ricerca normativa",
    "avvisi",
    "cartelle",
    "inps",
    "registro imprese",
    "dire",
    "concordato",
    "xbrl",
    "oic",
    "bandi",
    "agevolazioni",
    "comunicazione professionale",
    "controllo di gestione",
    "circolari clienti",
)
VERA_PUBLIC_PAGE_PATHS = (
    Path("static/shared/archive-organization/index.html"),
    Path("static/shared/check-entries/index.html"),
    Path("static/shared/startup-business-plan/index.html"),
    Path("static/shared/concordato-plan-review/index.html"),
    Path("static/shared/deep-research-validator/index.html"),
    Path("static/shared/financial-analysis/index.html"),
    Path("static/shared/management-control-pack/index.html"),
    Path("static/shared/centrale-rischi-review/index.html"),
    Path("static/shared/sales-plan/index.html"),
    Path("static/shared/journal-bank-reconciliation/index.html"),
    Path("static/shared/passive-invoice-audit/index.html"),
    Path("static/shared/journal-sampling/index.html"),
    Path("static/shared/new-client/geneva.html"),
    Path("static/shared/new-client/index.html"),
    Path("static/shared/new-client/uk.html"),
    Path("static/shared/new-client/zurich.html"),
    Path("static/shared/previdenza-inps/index.html"),
    Path("static/shared/prompt-optimizer/index.html"),
    Path("static/shared/registro-imprese-sari/index.html"),
    Path("static/shared/riconciliazione-partite/index.html"),
    Path("static/shared/report-builder/index.html"),
)
REPORTING_ENGINE_PLUGIN_NAMES = {
    "distribution-analysis",
    "funnel-analysis",
    "mix-contribution-analysis",
    "period-comparison",
    "scatter-bubble-analysis",
    "set-overlap-analysis",
    "statement-analysis",
    "variance-analysis",
}
WORKFLOW_PLUGIN_NAMES = (
    COMMERCIALISTA_MODULE_NAMES
    | REPORTING_ENGINE_PLUGIN_NAMES
    | (STANDALONE_PLUGIN_NAMES - PRIVATE_STANDALONE_PLUGIN_NAMES)
)
STANDARD_ACCOUNTING_PLUGIN_NAMES = UNIFIED_PLUGIN_NAMES
PLUGINS_WITH_LEGACY_USER_EMAIL: set[str] = set()
PLUGIN_PROVIDER_CONFIGS = (
    ROOT / "plugins" / "_shared" / "vendor" / "modules" / "utilities" / "config.py",
    ROOT
    / "plugins"
    / "_shared"
    / "variance"
    / "vendor"
    / "modules"
    / "utilities"
    / "config.py",
)
PLUGIN_MODEL_API_SCRIPT_EXCEPTIONS: set[Path] = set()
FORBIDDEN_PLUGIN_MODEL_API_PATTERNS = (
    "api.openai.com",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK",
    "GEMINI_API_KEY",
    "from openai",
    "import openai",
    "modules.llm.batch_runner",
    "modules.llm.model_router",
    "query_llm_return",
    "run_step_json",
    "run_step_text",
    "select_provider(",
)


def _restore_application_import_path() -> None:
    """Undo plugin-script import path pollution before importing the app."""
    root = str(ROOT)
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)

    plugins_root = ROOT / "plugins"
    for module_name, module in list(sys.modules.items()):
        if module_name != "modules" and not module_name.startswith("modules."):
            continue
        module_file = getattr(module, "__file__", None)
        if not module_file:
            del sys.modules[module_name]
            continue
        try:
            module_path = Path(module_file).resolve()
        except OSError:
            continue
        if plugins_root in module_path.parents:
            del sys.modules[module_name]


@pytest.mark.parametrize("config_path", PLUGIN_PROVIDER_CONFIGS)
def test_vendored_plugin_provider_router_fails_closed(config_path: Path) -> None:
    source = config_path.read_text(encoding="utf-8")
    select_provider_source = source[: source.index("def get_naming_params")]

    assert "QueryChoiceDict" not in select_provider_source
    assert "defaultFixQuery" not in source
    assert "checkPatternsQuery" not in source
    assert "descriptionNormaliserQuery" not in source
    assert "ocrFallbackQuery" not in source
    assert "web_search_preview" not in source
    assert "deepseek-reasoner" not in source
    assert "gemini-2.5" not in source
    assert "anthropicKey" not in source
    assert "deepseekKey" not in source

    spec = importlib.util.spec_from_file_location(
        f"plugin_vendor_config_{config_path.parent.parent.parent.name}",
        config_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for query_step in (
        "defaultFixQuery",
        "checkPatternsQuery",
        "descriptionNormaliserQuery",
        "ocrFallbackQuery",
    ):
        with pytest.raises(RuntimeError, match="disabled in local plugin runtimes"):
            module.select_provider(query_step)


def test_plugin_scripts_do_not_call_model_apis_except_voice() -> None:
    violations: list[str] = []

    for path in sorted((ROOT / "plugins").glob("*/scripts/*.py")):
        if path in PLUGIN_MODEL_API_SCRIPT_EXCEPTIONS:
            continue
        source = path.read_text(encoding="utf-8")
        matches = [
            pattern
            for pattern in FORBIDDEN_PLUGIN_MODEL_API_PATTERNS
            if pattern in source
        ]
        if matches:
            rel_path = path.relative_to(ROOT)
            violations.append(f"{rel_path}: {', '.join(matches)}")

    assert violations == []


NON_PLOTTING_REVIEW_TOOL_CONTRACTS = {
    "archive-organization": (
        "validate_archive_organization_review",
        "render_archive_organization_review",
        "save_archive_organization_decisions",
        "apply_archive_organization_decisions",
    ),
    "open-item-reconciliation": (
        "validate_open_item_reconciliation_review",
        "render_open_item_reconciliation_review",
        "get_open_item_reconciliation_case_context",
        "save_open_item_reconciliation_decisions",
        "apply_open_item_reconciliation_decisions",
    ),
    "check-entries": (
        "validate_check_entries_review",
        "render_check_entries_review",
        "get_check_entries_case_context",
        "save_check_entries_decisions",
        "apply_check_entries_decisions",
    ),
    "client-file-preparation": (
        "validate_client_file_preparation_review",
        "render_client_file_preparation_review",
        "save_client_file_preparation_decisions",
        "apply_client_file_preparation_decisions",
    ),
    "new-client": (
        "validate_new_client_review",
        "render_new_client_review",
        "save_new_client_decisions",
        "apply_new_client_decisions",
    ),
    "concordato-plan-review": (
        "validate_concordato_plan_review",
        "render_concordato_plan_review",
        "save_concordato_plan_decisions",
        "apply_concordato_plan_decisions",
    ),
    "deep-research-validator": (
        "validate_deep_research_review",
        "render_deep_research_review",
        "save_deep_research_decisions",
        "apply_deep_research_decisions",
    ),
    "journal-bank-reconciliation": (
        "validate_journal_bank_review",
        "render_journal_bank_review",
        "get_journal_bank_case_context",
        "save_journal_bank_decisions",
        "apply_journal_bank_decisions",
    ),
    "journal-sampling": (
        "validate_journal_sampling_review",
        "render_journal_sampling_review",
        "save_journal_sampling_decisions",
        "apply_journal_sampling_decisions",
    ),
    "prompt-optimizer": (
        "validate_prompt_optimizer_review",
        "render_prompt_optimizer_review",
        "save_prompt_optimizer_decisions",
        "apply_prompt_optimizer_decisions",
    ),
    "previdenza-inps": (
        "validate_previdenza_inps_review",
        "render_previdenza_inps_review",
        "save_previdenza_inps_decisions",
        "apply_previdenza_inps_decisions",
    ),
    "registro-imprese-sari": (
        "validate_registro_imprese_sari_review",
        "render_registro_imprese_sari_review",
        "save_registro_imprese_sari_decisions",
        "apply_registro_imprese_sari_decisions",
    ),
    "report-builder": (
        "validate_report_builder_review",
        "render_report_builder_review",
        "save_report_builder_decisions",
        "apply_report_builder_decisions",
    ),
}
ACCOUNTING_STATIC_PLUGIN_PAGES = (
    ROOT / "static" / "shared" / "vera" / "index.html",
    ROOT / "static" / "shared" / "archive-organization" / "index.html",
    ROOT / "static" / "shared" / "riconciliazione-partite" / "index.html",
    ROOT / "static" / "shared" / "new-client" / "index.html",
    ROOT / "static" / "shared" / "journal-sampling" / "index.html",
    ROOT / "static" / "shared" / "check-entries" / "index.html",
    ROOT / "static" / "shared" / "financial-analysis" / "index.html",
    ROOT / "static" / "shared" / "startup-business-plan" / "index.html",
    ROOT / "static" / "shared" / "management-control-pack" / "index.html",
    ROOT / "static" / "shared" / "centrale-rischi-review" / "index.html",
    ROOT / "static" / "shared" / "journal-bank-reconciliation" / "index.html",
    ROOT / "static" / "shared" / "report-builder" / "index.html",
    ROOT / "static" / "shared" / "concordato-plan-review" / "index.html",
    ROOT / "static" / "shared" / "previdenza-inps" / "index.html",
    ROOT / "static" / "shared" / "prompt-optimizer" / "index.html",
    ROOT / "static" / "shared" / "registro-imprese-sari" / "index.html",
    ROOT / "static" / "shared" / "deep-research-validator" / "index.html",
)
STANDALONE_STATIC_PLUGIN_PAGES = (
    ROOT / "static" / "shared" / "clara" / "index.html",
    ROOT / "static" / "shared" / "lucia" / "index.html",
)
STATIC_PLUGIN_PAGES = ACCOUNTING_STATIC_PLUGIN_PAGES + STANDALONE_STATIC_PLUGIN_PAGES
PUBLIC_PLUGIN_EXPLAINER_PAGES = (
    ROOT / "static" / "shared" / "clara" / "index.html",
    ROOT / "static" / "shared" / "lucia" / "index.html",
    ROOT / "static" / "shared" / "archive-organization" / "index.html",
    ROOT / "static" / "shared" / "check-entries" / "index.html",
    ROOT / "static" / "shared" / "concordato-plan-review" / "index.html",
    ROOT / "static" / "shared" / "deep-research-validator" / "index.html",
    ROOT / "static" / "shared" / "financial-analysis" / "index.html",
    ROOT / "static" / "shared" / "startup-business-plan" / "index.html",
    ROOT / "static" / "shared" / "management-control-pack" / "index.html",
    ROOT / "static" / "shared" / "centrale-rischi-review" / "index.html",
    ROOT / "static" / "shared" / "journal-bank-reconciliation" / "index.html",
    ROOT / "static" / "shared" / "journal-sampling" / "index.html",
    ROOT / "static" / "shared" / "new-client" / "index.html",
    ROOT / "static" / "shared" / "new-client" / "geneva.html",
    ROOT / "static" / "shared" / "new-client" / "uk.html",
    ROOT / "static" / "shared" / "new-client" / "zurich.html",
    ROOT / "static" / "shared" / "previdenza-inps" / "index.html",
    ROOT / "static" / "shared" / "prompt-optimizer" / "index.html",
    ROOT / "static" / "shared" / "registro-imprese-sari" / "index.html",
    ROOT / "static" / "shared" / "report-builder" / "index.html",
    ROOT / "static" / "shared" / "riconciliazione-partite" / "index.html",
)
ACCOUNTING_BUNDLE_ZIP = ROOT / "plugin_packages" / "vera" / "vera-plugin.zip"
VERA_DOWNLOAD_HREF = "/downloads/vera"
VERA_MARKETPLACE_HREF = (
    "https://chatgpt.com/auth/login?next="
    "%2Fplugins%2Fplugins_6a57ac5ce65c8191ae7bd0a51160eb7d"
)
VERA_PRODUCT_PAGE_HREF = "../vera/index.html"


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_codex_plugin_zip", BUILD_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def extracted_clara_plugin(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Extract the configured Clara package once for installed-runtime tests."""

    builder = load_builder()
    package = {item.plugin: item for item in builder.load_packages()}["clara"]
    extraction_root = tmp_path_factory.mktemp("extracted_clara_package")
    with ZipFile(package.output_zip) as archive:
        archive.extractall(extraction_root)
    return extraction_root / package.package_root / "plugins" / "clara"


def isolated_plugin_env() -> dict[str, str]:
    """Return an environment that cannot borrow repository Python paths."""

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def write_reporting_smoke_dataset(path: Path) -> None:
    """Write a tiny AC/PY sales dataset with known comparison totals."""

    path.write_text(
        "Date,Brand,Sales\n"
        "2025-01-31,Alpha,100\n"
        "2025-01-31,Beta,80\n"
        "2025-02-28,Alpha,110\n"
        "2025-02-28,Beta,85\n"
        "2025-03-31,Alpha,120\n"
        "2025-03-31,Beta,90\n"
        "2025-04-30,Alpha,130\n"
        "2025-04-30,Beta,95\n"
        "2025-05-31,Alpha,140\n"
        "2025-05-31,Beta,100\n"
        "2025-06-30,Alpha,150\n"
        "2025-06-30,Beta,105\n"
        "2026-01-31,Alpha,115\n"
        "2026-01-31,Beta,83\n"
        "2026-02-28,Alpha,125\n"
        "2026-02-28,Beta,90\n"
        "2026-03-31,Alpha,135\n"
        "2026-03-31,Beta,96\n"
        "2026-04-30,Alpha,145\n"
        "2026-04-30,Beta,103\n"
        "2026-05-31,Alpha,160\n"
        "2026-05-31,Beta,110\n"
        "2026-06-30,Alpha,180\n"
        "2026-06-30,Beta,165\n",
        encoding="utf-8",
    )


def test_configured_plugin_zips_match_repo_source() -> None:
    builder = load_builder()

    for package in builder.load_packages():
        expected = builder.expected_zip_entries(package)
        with ZipFile(package.output_zip) as archive:
            actual_names = {
                name for name in archive.namelist() if not name.endswith("/")
            }

            assert actual_names == set(expected)
            for name, content in expected.items():
                assert archive.read(name) == content


def test_vera_source_manifest_uses_approved_subtitle() -> None:
    manifest = json.loads(
        (ROOT / "plugins" / "vera" / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["interface"]["shortDescription"] == (
        "Assistente AI x commercialisti"
    )


@pytest.mark.parametrize("term", VERA_DISCOVERY_TERMS)
def test_vera_source_manifest_preserves_discovery_term(term: str) -> None:
    manifest = json.loads(
        (ROOT / "plugins" / "vera" / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )
    # This is a mechanical metadata contract, not a claim about marketplace rank.
    discovery_text = " ".join(
        (
            manifest["description"],
            manifest["interface"]["shortDescription"],
            *manifest["keywords"],
        )
    ).casefold()
    normalized_discovery_text = discovery_text.replace("-", " ")

    assert term in normalized_discovery_text


def test_vera_uses_one_public_skill_namespace() -> None:
    builder = load_builder()
    plugin_root = ROOT / "plugins" / "vera"
    manifest = json.loads(
        (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    declared_names = {
        builder.skill_frontmatter_name(skill_path)
        for skill_path in (plugin_root / "skills").glob("*/SKILL.md")
    }
    public_identities = {f"{manifest['name']}:{name}" for name in declared_names}
    router = (plugin_root / "skills" / "vera" / "SKILL.md").read_text(encoding="utf-8")

    assert None not in declared_names
    assert all(":" not in name for name in declared_names if name is not None)
    assert len(public_identities) == len(declared_names)
    assert all(identity.startswith("vera:") for identity in public_identities)
    assert "Vera workflow: vera:<specialist-skill>" in router
    assert "Vera workflow: <specialist-skill>" not in router


def test_vera_prefers_word_for_local_docx_visual_review() -> None:
    skill_path = ROOT / "plugins" / "vera" / "skills" / "vera" / "SKILL.md"
    skill_text = skill_path.read_text(encoding="utf-8")
    normalized_skill_text = " ".join(skill_text.split())

    assert "A structural DOCX check does not establish" in normalized_skill_text
    assert (
        "use Word as the preferred application and rendering reference"
        in normalized_skill_text
    )
    assert "LibreOffice may be used only as a fallback" in normalized_skill_text
    assert (
        "A LibreOffice launch, conversion, or local permission failure is not evidence "
        "that visual review is impossible" in normalized_skill_text
    )
    assert "Never describe a DOCX as visually validated" in normalized_skill_text


def test_chatgpt_upload_entries_put_vera_manifest_at_zip_root() -> None:
    builder = load_builder()
    vera = {bundle.name: bundle for bundle in builder.load_bundles()}["vera"]

    entries = builder.chatgpt_upload_entries(vera)
    manifest = json.loads(entries[".codex-plugin/plugin.json"])
    prompts = manifest["interface"]["defaultPrompt"]

    assert ".codex-plugin/plugin.json" in entries
    assert "skills/vera/references/public-process-page-contract.md" in entries
    assert "modules/previdenza-inps/.codex-plugin/plugin.json" in entries
    assert "modules/registro-imprese-sari/.codex-plugin/plugin.json" in entries
    projected_manifests = {
        name: json.loads(content)
        for name, content in entries.items()
        if name.endswith(".codex-plugin/plugin.json")
    }
    assert projected_manifests
    assert all(
        "apps" not in component_manifest and "mcpServers" not in component_manifest
        for component_manifest in projected_manifests.values()
    )
    assert "apps" not in manifest
    assert "mcpServers" not in manifest
    assert "screenshots" not in manifest["interface"]
    assert manifest["repository"] == "https://github.com/fabioannovazzi/app_files"
    assert manifest["license"] == "AGPL-3.0-only"
    assert manifest["author"]["name"] == "Fabio Annovazzi · Mparanza"
    assert manifest["interface"]["developerName"] == "Fabio Annovazzi · Mparanza"
    passive_invoice_manifest = projected_manifests[
        "modules/passive-invoice-audit/.codex-plugin/plugin.json"
    ]
    assert passive_invoice_manifest["author"]["name"] == ("Fabio Annovazzi · Mparanza")
    assert passive_invoice_manifest["interface"]["developerName"] == (
        "Fabio Annovazzi · Mparanza"
    )
    assert entries["LICENSE"] == (ROOT / "LICENSE").read_bytes()
    assert manifest["interface"]["shortDescription"] == (
        "Assistente AI x commercialisti"
    )
    assert len(prompts) == 3
    assert all(len(prompt) <= 128 for prompt in prompts)
    source_manifest = json.loads(
        (ROOT / "plugins" / "vera" / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["version"] == source_manifest["version"]
    assert manifest["interface"]["supportURL"] == "https://mparanza.com/support"
    assert prompts[0] == (
        "Trasforma questi export contabili in un pacchetto di controllo di gestione "
        "con P&L, Budget, aging, cassa e concentrazione."
    )
    assert any(
        "sito dello studio" in prompt and "preview responsive" in prompt
        for prompt in prompts
    )
    assert prompts[2] == (
        "Prepara un bilancio OIC intelligente anche da PDF: fammi rivedere "
        "estrazione e celle incerte, poi genera l’XBRL finale."
    )
    approved_description = (
        (ROOT / "docs" / "marketplace_copy" / "vera-long-description.txt")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert manifest["interface"]["longDescription"] == approved_description
    assert len(approved_description.split()) <= 120
    assert len(approved_description.split("\n\n")) == 3
    assert "bilancio civilistico OIC" in approved_description
    assert "concordato preventivo" in approved_description
    assert "ricerche fiscali o normative" in approved_description
    assert "Cerca la corrispondenza del cliente." not in approved_description
    assert "giudizio professionale restano al commercialista." in approved_description
    assert "New Client" not in approved_description
    assert "indicizzare" not in approved_description
    assert "consiglia Codex Desktop" not in approved_description
    assert "sessioni host" not in approved_description
    assert "claim assurance" not in approved_description
    assert "token" not in approved_description
    assert "Creative Production" not in approved_description
    assert "commercialista" in manifest["keywords"]
    assert "ricerca-fiscale" in manifest["keywords"]

    router_path = "skills/vera/SKILL.md"
    wrapper_path = "skills/studio-archive/SKILL.md"
    reference_path = "skills/studio-archive/references/marketplace-gmail.md"
    whatsapp_reference_path = "skills/studio-archive/references/whatsapp-desktop.md"
    gmail_evals_path = "evals/marketplace_gmail_cases.json"
    whatsapp_evals_path = "evals/whatsapp_desktop_cases.json"
    module_skill_path = "modules/studio-archive/skills/studio-archive/SKILL.md"
    assert router_path in entries
    assert wrapper_path in entries
    assert reference_path in entries
    assert whatsapp_reference_path in entries
    assert gmail_evals_path in entries
    assert whatsapp_evals_path in entries
    assert module_skill_path in entries
    router = entries[router_path].decode("utf-8")
    wrapper = entries[wrapper_path].decode("utf-8")
    module_skill = entries[module_skill_path].decode("utf-8")
    assert "No matching specialist workflow" in router
    assert "../<skill-name>/SKILL.md" in router
    assert "../../modules/studio-archive" in wrapper
    assert "setup_studio_archive" in wrapper
    assert "archive_folder_picker_unavailable" in wrapper
    assert not any(name.endswith("/WORKFLOW.md") for name in entries)
    assert "## Connected Gmail workflow" in module_skill
    assert "setup_studio_archive" in module_skill
    assert "native folder" in module_skill
    assert module_skill.index("get_profile") < module_skill.index("search_emails")
    assert module_skill.index("search_emails") < module_skill.index("batch_read_email")
    assert "at most 20 results per page" in module_skill
    assert "absence of an optional Cc" in module_skill
    assert "cannot prove" in module_skill
    assert "the absence of an undisclosed Bcc recipient" in module_skill
    assert "whatsapp-desktop-computer-use-v1" in module_skill
    assert "net.whatsapp.WhatsApp" in module_skill
    assert "one empty composer" in module_skill
    assert "never press Return" in module_skill
    gmail_section = module_skill.split(
        "## Connected Gmail workflow",
        maxsplit=1,
    )[
        1
    ].split("## Optional local Gmail enhancement", maxsplit=1)[0]
    for local_dependency in (
        "plan_studio_archive_gmail_search",
        "match_studio_archive_email",
        "configure_studio_archive_client",
        "python scripts/studio_archive.py",
    ):
        assert local_dependency not in gmail_section
    assert not any(
        name.rsplit("/", maxsplit=1)[-1] in {".app.json", ".mcp.json"}
        for name in entries
    )
    assert not any("mcp" in name.split("/") for name in entries)
    assert not any(name.startswith("vera-codex-plugin/") for name in entries)
    assert not any(name.startswith("plugins/vera/") for name in entries)
    assert not any(name.endswith("marketplace.json") for name in entries)


@pytest.mark.parametrize("plugin_name", ["clara", "lucia", "vera"])
def test_chatgpt_upload_entries_put_each_plugin_manifest_at_zip_root(
    plugin_name: str,
) -> None:
    builder = load_builder()
    targets = {package.plugin: package for package in builder.load_packages()}
    targets.update({bundle.name: bundle for bundle in builder.load_bundles()})

    entries = builder.chatgpt_upload_entries(targets[plugin_name])
    manifest = json.loads(entries[".codex-plugin/plugin.json"])

    assert manifest["name"] == plugin_name
    assert manifest["interface"]["supportURL"] == "https://mparanza.com/support"
    assert ".codex-plugin/plugin.json" in entries
    assert not any(name.startswith(f"{plugin_name}-codex-plugin/") for name in entries)
    projected_manifests = {
        name: json.loads(content)
        for name, content in entries.items()
        if name.endswith(".codex-plugin/plugin.json")
    }
    assert projected_manifests
    assert all(
        "apps" not in component_manifest and "mcpServers" not in component_manifest
        for component_manifest in projected_manifests.values()
    )
    projected_skills = {
        name: content.decode("utf-8")
        for name, content in entries.items()
        if name.endswith("/SKILL.md")
    }
    assert projected_skills
    card_bodies = {
        name: content[builder.skill_body_start(content) :].strip()
        for name, content in projected_skills.items()
        if name.startswith("skills/") and name.count("/") == 2
    }
    instruction_config = json.loads(
        (ROOT / "plugins" / plugin_name / builder.CHATGPT_SKILL_CARDS_FILE).read_text(
            encoding="utf-8"
        )
    )
    public_skill_names = set(instruction_config["skills"])
    if plugin_name in builder.SOURCE_PRESERVING_CHATGPT_PLUGINS:
        expected_card_bodies = {}
        for skill_name in public_skill_names:
            source = (
                ROOT / "plugins" / plugin_name / "skills" / skill_name / "SKILL.md"
            ).read_bytes()
            projected = builder.project_chatgpt_source_skill(source).decode("utf-8")
            expected_card_bodies[f"skills/{skill_name}/SKILL.md"] = projected[
                builder.skill_body_start(projected) :
            ].strip()
    else:
        expected_card_bodies = {
            f"skills/{skill_name}/SKILL.md": card["instructions"]
            for skill_name, card in instruction_config["skills"].items()
        }
    assert card_bodies == expected_card_bodies
    assert builder.CHATGPT_SKILL_CARDS_FILE not in entries
    for skill_name in public_skill_names:
        skill_prefix = f"skills/{skill_name}/"
        packaged_skill_files = {
            name.removeprefix(skill_prefix)
            for name in entries
            if name.startswith(skill_prefix)
        }
        assert {"SKILL.md", "agents/openai.yaml"} <= packaged_skill_files
        if plugin_name == "clara":
            assert packaged_skill_files == {"SKILL.md", "agents/openai.yaml"}
        else:
            assert "WORKFLOW.md" not in packaged_skill_files
    for name, body in card_bodies.items():
        skill_name = name.split("/")[1]
        interface_name = f"skills/{skill_name}/agents/openai.yaml"
        card = instruction_config["skills"][skill_name]
        expected_interface = builder.chatgpt_skill_interface(
            builder.ChatGPTSkillCard(
                display_name=card["display_name"],
                short_description=card["short_description"],
                default_prompt=card["default_prompt"],
                instructions=card["instructions"],
            )
        )
        assert entries[interface_name] == expected_interface
        if plugin_name == "clara":
            assert "\n\n" not in body, name
            assert builder.REQUIRED_CHATGPT_HEADING not in body, name
            assert builder.REQUIRED_CODEX_RECOMMENDATION not in body, name
            assert "Lavoro meglio con Codex perché" not in body, name
            assert builder.CODEX_DOWNLOAD_URL not in body, name
            assert not body.startswith("#"), name
    if plugin_name == "clara":
        deck_correction = card_bodies["skills/deck-correction/SKILL.md"]
        assert deck_correction.startswith("Attach the current presentation")
        assert "protects untouched content" in deck_correction
        assert "verification findings" in deck_correction
        reporting_interface = entries[
            "skills/reporting-engine/agents/openai.yaml"
        ].decode("utf-8")
        assert "this Excel file" in reporting_interface
        assert "Excel or CSV" not in reporting_interface
    if plugin_name == "vera":
        assert len(card_bodies) == 32
        assert all("`WORKFLOW.md`" not in body for body in card_bodies.values())
        router = card_bodies["skills/vera/SKILL.md"]
        assert "No matching specialist workflow" in router
        assert "../<skill-name>/SKILL.md" in router
        audit_wrapper = card_bodies["skills/open-item-reconciliation/SKILL.md"]
        assert "Resolve `../../modules/open-item-reconciliation`" in audit_wrapper
        full_workflow = entries[
            "modules/open-item-reconciliation/skills/open-item-reconciliation/SKILL.md"
        ].decode("utf-8")
        assert "# Open-item Reconciliation" in full_workflow
        assert "## Required Questions" in full_workflow
    if plugin_name == "lucia":
        assert set(card_bodies) == {
            "skills/lucia/SKILL.md",
            "skills/quesito-legale-fiscale/SKILL.md",
            "skills/prompt-optimizer/SKILL.md",
            "skills/deep-research-validator/SKILL.md",
            "skills/comunicazione-professionale/SKILL.md",
            "skills/presenza-digitale-studio/SKILL.md",
            "skills/apertura-pratica/SKILL.md",
        }
        router = card_bodies["skills/lucia/SKILL.md"]
        normalized_router = " ".join(router.split())
        assert "catalogo cresce attraverso workflow specialistici" in normalized_router
        assert (
            "aggiorna questa tabella quando entra una nuova funzione Lucia"
            in normalized_router
        )
        assert "esattamente due" not in normalized_router
        assert (
            "../../modules/prompt-optimizer"
            in card_bodies["skills/prompt-optimizer/SKILL.md"]
        )
        assert (
            "../../modules/deep-research-validator"
            in card_bodies["skills/deep-research-validator/SKILL.md"]
        )
        assert (
            "../../modules/comunicazione-professionale"
            in card_bodies["skills/comunicazione-professionale/SKILL.md"]
        )
        assert (
            "../../modules/presenza-digitale-studio"
            in card_bodies["skills/presenza-digitale-studio/SKILL.md"]
        )
        assert (
            "../../modules/apertura-pratica"
            in card_bodies["skills/apertura-pratica/SKILL.md"]
        )


@pytest.mark.parametrize("plugin_name", ["clara", "lucia", "vera"])
def test_committed_chatgpt_upload_uses_approved_card_copy(
    plugin_name: str,
) -> None:
    builder = load_builder()
    instruction_config = json.loads(
        (ROOT / "plugins" / plugin_name / builder.CHATGPT_SKILL_CARDS_FILE).read_text(
            encoding="utf-8"
        )
    )
    public_skill_names = set(instruction_config["skills"])
    if plugin_name in builder.SOURCE_PRESERVING_CHATGPT_PLUGINS:
        expected_bodies = {}
        for skill_name in public_skill_names:
            source = (
                ROOT / "plugins" / plugin_name / "skills" / skill_name / "SKILL.md"
            ).read_bytes()
            projected = builder.project_chatgpt_source_skill(source).decode("utf-8")
            expected_bodies[f"skills/{skill_name}/SKILL.md"] = projected[
                builder.skill_body_start(projected) :
            ].strip()
    else:
        expected_bodies = {
            f"skills/{skill_name}/SKILL.md": card["instructions"]
            for skill_name, card in instruction_config["skills"].items()
        }
    upload_zip = (
        ROOT / "plugin_packages" / plugin_name / f"{plugin_name}-chatgpt-upload.zip"
    )

    with ZipFile(upload_zip) as archive:
        actual_bodies = {
            name: content[builder.skill_body_start(content) :].strip()
            for name in archive.namelist()
            if name in expected_bodies
            for content in [archive.read(name).decode("utf-8")]
        }
        for skill_name in public_skill_names:
            skill_prefix = f"skills/{skill_name}/"
            packaged_skill_files = {
                name.removeprefix(skill_prefix)
                for name in archive.namelist()
                if name.startswith(skill_prefix) and not name.endswith("/")
            }
            assert {"SKILL.md", "agents/openai.yaml"} <= packaged_skill_files
            if plugin_name == "clara":
                assert packaged_skill_files == {"SKILL.md", "agents/openai.yaml"}
            else:
                assert "WORKFLOW.md" not in packaged_skill_files

    assert actual_bodies == expected_bodies
    assert len(actual_bodies) == len(public_skill_names)
    assert not any(
        body.startswith("Attach the relevant source material")
        or body.startswith("Allega i documenti pertinenti")
        for body in actual_bodies.values()
    )


@pytest.mark.parametrize("plugin_name", ["clara", "lucia", "vera"])
def test_cross_surface_plugins_define_chatgpt_runtime_in_main_skill(
    plugin_name: str,
) -> None:
    builder = load_builder()
    skill_path = ROOT / "plugins" / plugin_name / "skills" / plugin_name / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    assert builder.has_chatgpt_runtime_contract(content)


def test_chatgpt_card_projection_uses_approved_instructions() -> None:
    builder = load_builder()
    source = (
        "---\n"
        "name: deck-correction\n"
        "description: Correct a presentation.\n"
        "---\n\n"
        "# Local workflow\n\n"
        "Run python scripts/apply_changes.py.\n"
    ).encode("utf-8")
    approved_instructions = (
        "Attach the existing deck and feedback. Preserve untouched content and "
        "verify the approved changes."
    )

    projected = builder.project_chatgpt_card_skill(
        source,
        instructions=approved_instructions,
    ).decode("utf-8")

    body = projected[builder.skill_body_start(projected) :].strip()
    assert body == approved_instructions
    assert "scripts/apply_changes.py" not in body


def test_chatgpt_card_config_rejects_incomplete_coverage() -> None:
    builder = load_builder()
    config = json.dumps(
        {
            "schema_version": 2,
            "skills": {
                "deck-correction": {
                    "display_name": "Deck Correction",
                    "short_description": "Correct a presentation",
                    "default_prompt": "Use $deck-correction to correct this deck.",
                    "instructions": "Attach the deck and feedback.",
                }
            },
        }
    ).encode("utf-8")

    with pytest.raises(ValueError, match=r"missing=\['interview'\]"):
        builder.load_chatgpt_skill_cards(
            config,
            plugin_name="clara",
            expected_skills={"deck-correction", "interview"},
        )


def test_chatgpt_card_config_rejects_raw_slug_display_name() -> None:
    builder = load_builder()
    config = json.dumps(
        {
            "schema_version": 2,
            "skills": {
                "deck-correction": {
                    "display_name": "deck-correction",
                    "short_description": "Correct a presentation",
                    "default_prompt": "Use $deck-correction to correct this deck.",
                    "instructions": "Clara applies the requested deck corrections.",
                }
            },
        }
    ).encode("utf-8")

    with pytest.raises(ValueError, match="must not repeat the raw slug"):
        builder.load_chatgpt_skill_cards(
            config,
            plugin_name="clara",
            expected_skills={"deck-correction"},
        )


def test_chatgpt_card_config_requires_product_specific_instructions() -> None:
    builder = load_builder()
    config = json.dumps(
        {
            "schema_version": 2,
            "skills": {
                "deck-correction": {
                    "display_name": "Deck Correction",
                    "short_description": "Correct a presentation",
                    "default_prompt": "Use $deck-correction to correct this deck.",
                    "instructions": "Attach the deck and requested corrections.",
                }
            },
        }
    ).encode("utf-8")

    with pytest.raises(ValueError, match="must explain what Clara does"):
        builder.load_chatgpt_skill_cards(
            config,
            plugin_name="clara",
            expected_skills={"deck-correction"},
        )


def test_chatgpt_card_config_rejects_duplicate_visible_copy() -> None:
    builder = load_builder()
    config = json.dumps(
        {
            "schema_version": 2,
            "skills": {
                "deck-correction": {
                    "display_name": "Deck Correction",
                    "short_description": "Review professional evidence",
                    "default_prompt": "Use $deck-correction to correct this deck.",
                    "instructions": "Clara applies the requested deck corrections.",
                },
                "interview": {
                    "display_name": "Interview",
                    "short_description": "Review professional evidence",
                    "default_prompt": "Use $interview to prepare this interview.",
                    "instructions": "Clara prepares and reviews the interview evidence.",
                },
            },
        }
    ).encode("utf-8")

    with pytest.raises(
        ValueError,
        match="interview short_description duplicates deck-correction",
    ):
        builder.load_chatgpt_skill_cards(
            config,
            plugin_name="clara",
            expected_skills={"deck-correction", "interview"},
        )


def test_chatgpt_card_config_rejects_internal_runtime_copy() -> None:
    builder = load_builder()
    config = json.dumps(
        {
            "schema_version": 2,
            "skills": {
                "deck-correction": {
                    "display_name": "Deck Correction",
                    "short_description": "Correct a presentation",
                    "default_prompt": "Use $deck-correction to correct this deck.",
                    "instructions": (
                        "Clara applies the requested deck corrections. "
                        f"{builder.REQUIRED_CHATGPT_HEADING}"
                    ),
                }
            },
        }
    ).encode("utf-8")

    with pytest.raises(ValueError, match="contains internal runtime copy"):
        builder.load_chatgpt_skill_cards(
            config,
            plugin_name="clara",
            expected_skills={"deck-correction"},
        )


def test_vera_chatgpt_card_config_rejects_incomplete_router_paths() -> None:
    builder = load_builder()
    config_path = ROOT / "plugins" / "vera" / builder.CHATGPT_SKILL_CARDS_FILE
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    target = builder.VERA_CHATGPT_ROUTER_TARGETS["sales-plan"]
    route = f"`sales-plan` → `../../{target}`"
    payload["skills"]["vera"]["instructions"] = payload["skills"]["vera"][
        "instructions"
    ].replace(route, "", 1)

    with pytest.raises(
        ValueError,
        match=r"Marketplace root router paths are incomplete; missing=\['sales-plan'\]",
    ):
        builder.load_chatgpt_skill_cards(
            json.dumps(payload).encode("utf-8"),
            plugin_name="vera",
            expected_skills=set(payload["skills"]),
        )


def test_chatgpt_manifest_rejects_more_than_three_default_prompts() -> None:
    builder = load_builder()
    source_path = ROOT / "plugins" / "vera" / ".codex-plugin" / "plugin.json"
    manifest = json.loads(source_path.read_text(encoding="utf-8"))
    manifest["interface"]["defaultPrompt"] = ["one", "two", "three", "four"]

    with pytest.raises(
        ValueError,
        match=r"interface\.defaultPrompt must contain at most 3 prompts; found 4",
    ):
        builder.project_chatgpt_manifest(json.dumps(manifest).encode("utf-8"))


def test_chatgpt_manifest_rejects_default_prompt_over_character_limit() -> None:
    builder = load_builder()
    source_path = ROOT / "plugins" / "vera" / ".codex-plugin" / "plugin.json"
    manifest = json.loads(source_path.read_text(encoding="utf-8"))
    max_prompt_characters = 128
    manifest["interface"]["defaultPrompt"] = ["x" * (max_prompt_characters + 1)]

    with pytest.raises(
        ValueError,
        match=(
            r"interface\.defaultPrompt\[0\] must contain at most "
            r"128 characters; found 129"
        ),
    ):
        builder.project_chatgpt_manifest(json.dumps(manifest).encode("utf-8"))


def test_chatgpt_manifest_preserves_product_specific_long_description() -> None:
    builder = load_builder()
    source_path = ROOT / "plugins" / "clara" / ".codex-plugin" / "plugin.json"
    manifest = json.loads(source_path.read_text(encoding="utf-8"))
    expected = "Product-specific capability description."
    manifest["interface"]["longDescription"] = expected

    projected = json.loads(
        builder.project_chatgpt_manifest(json.dumps(manifest).encode("utf-8"))
    )

    assert projected["interface"]["longDescription"] == expected


def test_chatgpt_upload_zip_matches_source_without_replacing_install_zip(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    vera = {bundle.name: bundle for bundle in builder.load_bundles()}["vera"]
    install_zip_before = vera.output_zip.read_bytes()
    source_manifest_path = ROOT / "plugins" / "vera" / ".codex-plugin" / "plugin.json"
    source_manifest_before = source_manifest_path.read_bytes()
    output = tmp_path / "vera-chatgpt-upload.zip"

    result = builder.build_chatgpt_upload(vera, output)

    assert result == output
    assert builder.verify_chatgpt_upload(vera, output) == []
    assert vera.output_zip.read_bytes() == install_zip_before
    assert source_manifest_path.read_bytes() == source_manifest_before
    with ZipFile(output) as archive:
        names = {name for name in archive.namelist() if not name.endswith("/")}
        assert names == set(builder.chatgpt_upload_entries(vera))
        assert archive.read("LICENSE") == (ROOT / "LICENSE").read_bytes()
        assert archive.read(
            ".codex-plugin/plugin.json"
        ) == builder.project_chatgpt_manifest(source_manifest_before)


def _bundled_node_or_skip() -> str:
    node = shutil.which("node")
    if node is not None:
        return node
    candidates = sorted(
        (Path.home() / ".cache" / "codex-runtimes").glob("*/dependencies/node/bin/node")
    )
    if not candidates:
        pytest.skip("The Codex-bundled Node.js runtime is required for this test.")
    return candidates[-1].as_posix()


def _projected_review_tools(
    node: str,
    server_path: Path,
    *server_args: str,
) -> set[str]:
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    completed = subprocess.run(
        [node, server_path.as_posix(), *server_args, "--stdio"],
        cwd=server_path.parent.parent,
        input=json.dumps(message) + "\n",
        capture_output=True,
        check=True,
        text=True,
        timeout=20,
    )
    responses = [
        json.loads(line) for line in completed.stdout.splitlines() if line.strip()
    ]
    response = next(item for item in responses if item.get("id") == 1)
    return {tool["name"] for tool in response["result"]["tools"]}


def test_projected_vera_upload_keeps_executable_new_client_review_bridges(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    vera = {bundle.name: bundle for bundle in builder.load_bundles()}["vera"]
    upload = builder.build_chatgpt_upload(
        vera,
        tmp_path / "vera-chatgpt-upload.zip",
    )
    extracted = tmp_path / "projected-vera"
    with ZipFile(upload) as archive:
        archive.extractall(extracted)

    node = _bundled_node_or_skip()
    dispatcher = extracted / "scripts" / "run_component_mcp.cjs"
    assert dispatcher.is_file()
    for component in ("new-client", "client-file-preparation"):
        component_root = extracted / "modules" / component
        projected_server = component_root / "scripts" / "review_mcp_server.cjs"
        local_bridge = component_root / "scripts" / "review_server.py"

        assert projected_server.is_file()
        assert local_bridge.is_file()
        assert not (component_root / "mcp").exists()
        assert _projected_review_tools(node, dispatcher, component) == set(
            NON_PLOTTING_REVIEW_TOOL_CONTRACTS[component]
        )

        review_server = _load_module_from_path(
            f"projected_{component.replace('-', '_')}_review_server",
            local_bridge,
        )
        workbench = review_server.LocalReviewWorkbench(
            plugin_dir=component_root,
            output_dir=tmp_path,
        )
        assert workbench.mcp_server_path == projected_server


def test_projected_vera_journal_bank_dependency_check_succeeds(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    vera = {bundle.name: bundle for bundle in builder.load_bundles()}["vera"]
    extracted = tmp_path / "projected-vera"
    builder.write_entries_to_directory(
        extracted,
        builder.chatgpt_upload_entries(vera),
    )
    component_root = extracted / "modules" / "journal-bank-reconciliation"

    completed = subprocess.run(
        [sys.executable, "scripts/check_dependencies.py"],
        cwd=component_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert "OK: all selected plugin dependencies are importable" in completed.stdout


def test_projected_vera_journal_bank_dependency_check_rejects_mixed_layout(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    vera = {bundle.name: bundle for bundle in builder.load_bundles()}["vera"]
    extracted = tmp_path / "projected-vera"
    builder.write_entries_to_directory(
        extracted,
        builder.chatgpt_upload_entries(vera),
    )
    component_root = extracted / "modules" / "journal-bank-reconciliation"
    (component_root / ".app.json").write_bytes(
        (ROOT / "plugins" / "journal-bank-reconciliation" / ".app.json").read_bytes()
    )

    completed = subprocess.run(
        [sys.executable, "scripts/check_dependencies.py"],
        cwd=component_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode != 0
    assert "implementation host layouts cannot be mixed" in completed.stderr


def test_projected_vera_journal_bank_builds_exact_implementation_receipts(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    vera = {bundle.name: bundle for bundle in builder.load_bundles()}["vera"]
    extracted = tmp_path / "projected-vera"
    builder.write_entries_to_directory(
        extracted,
        builder.chatgpt_upload_entries(vera),
    )
    component_root = extracted / "modules" / "journal-bank-reconciliation"
    receipt_probe = (
        "import json, sys; "
        "sys.path.insert(0, 'scripts'); "
        "import journal_bank_core as core; "
        "print(json.dumps(core.build_implementation_artifact_receipts()))"
    )

    completed = subprocess.run(
        [sys.executable, "-c", receipt_probe],
        cwd=component_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    receipt_paths = {
        (receipt["root_id"], receipt["path"])
        for receipt in json.loads(completed.stdout)
    }
    assert ("implementation", "scripts/review_mcp_server.cjs") in receipt_paths
    assert ("implementation", "scripts/review_server.py") in receipt_paths
    assert ("implementation", ".app.json") not in receipt_paths
    assert ("implementation", ".mcp.json") not in receipt_paths
    assert ("implementation", "mcp/server.cjs") not in receipt_paths


def test_configured_bundle_zip_matches_repo_source() -> None:
    builder = load_builder()

    bundles = builder.load_bundles()
    assert {bundle.name for bundle in bundles} == {"vera"}
    for bundle in bundles:
        expected = builder.expected_zip_entries(bundle)
        with ZipFile(bundle.output_zip) as archive:
            actual_names = {
                name for name in archive.namelist() if not name.endswith("/")
            }

            assert actual_names == set(expected)
            for name, content in expected.items():
                assert archive.read(name) == content


def test_configured_downloads_include_repository_license() -> None:
    builder = load_builder()
    license_bytes = (ROOT / "LICENSE").read_bytes()

    for target in [*builder.load_packages(), *builder.load_bundles()]:
        entry_name = f"{target.package_root}/LICENSE"

        with ZipFile(target.output_zip) as archive:
            assert archive.read(entry_name) == license_bytes


def test_clara_download_includes_deck_revision_authorities() -> None:
    builder = load_builder()
    clara = {package.plugin: package for package in builder.load_packages()}["clara"]
    expected = builder.expected_zip_entries(clara)

    for relative_path in (
        "docs/specs/pptx_templates/ag-style-spec.md",
        "docs/specs/pptx_templates/bain-style-spec.md",
        ".agents/skills/advisory-output-shaper/SKILL.md",
    ):
        entry_name = f"{clara.package_root}/{relative_path}"
        assert expected[entry_name] == (ROOT / relative_path).read_bytes()


def test_accounting_bundle_contains_only_vera_and_its_modules() -> None:
    builder = load_builder()
    bundles = {bundle.name: bundle for bundle in builder.load_bundles()}

    standard_bundle = bundles["vera"]
    assert STANDALONE_PLUGIN_NAMES.isdisjoint(standard_bundle.plugin_names)
    assert set(standard_bundle.plugin_names) == STANDARD_ACCOUNTING_PLUGIN_NAMES

    standard_entries = builder.expected_zip_entries(standard_bundle)

    for plugin_name in REPORTING_ENGINE_PLUGIN_NAMES:
        assert not any(f"/plugins/{plugin_name}/" in name for name in standard_entries)
    for module_name in COMMERCIALISTA_MODULE_NAMES:
        module_path = f"/plugins/vera/modules/{module_name}/"
        assert any(module_path in name for name in standard_entries)
        assert not any(f"/plugins/{module_name}/" in name for name in standard_entries)


def test_vera_bundle_contains_browser_discovery_capabilities() -> None:
    builder = load_builder()
    vera = {bundle.name: bundle for bundle in builder.load_bundles()}["vera"]
    entries = builder.expected_zip_entries(vera)
    prefix = "vera-codex-plugin/plugins/vera/modules/browser-automation/"

    for relative_path in (
        "scripts/acceptance_fixture.py",
        "scripts/capability_pipeline.py",
        "scripts/capability_runtime.mjs",
        "scripts/check_installation.py",
        "scripts/discovery_pack.py",
        "scripts/discovery_runtime.mjs",
        "references/capability-contract.md",
        "references/discovery-playbook.md",
        "capabilities/gmail-search-export/capability.json",
        "capabilities/agenzia-invoice-zip/capability.json",
        "capabilities/teamsystem-process/capability.json",
    ):
        assert f"{prefix}{relative_path}" in entries
        assert (
            entries[f"{prefix}{relative_path}"]
            == (ROOT / "plugins" / "browser-automation" / relative_path).read_bytes()
        )
    assert f"{prefix}scripts/capability_contract.py" not in entries
    for retired_path in (
        "scripts/record_agenzia_invoice_flow.py",
        "references/agenzia_invoice_flow_recording.md",
        "requirements-portal-recorder.txt",
    ):
        assert f"{prefix}{retired_path}" not in entries


def test_vera_package_separates_plan_from_financial_analysis_engines() -> None:
    builder = load_builder()
    bundles = {bundle.name: bundle for bundle in builder.load_bundles()}
    packages = {package.plugin: package for package in builder.load_packages()}
    vera_entries = builder.expected_zip_entries(bundles["vera"])
    clara_entries = builder.expected_zip_entries(packages["clara"])
    engine_names = {
        "prepare_monthly_pnl_case.py",
        "prepare_working_capital_case.py",
        "prepare_customer_concentration_case.py",
        "prepare_fdd_case.py",
    }

    for engine_name in engine_names:
        vera_path = (
            "vera-codex-plugin/plugins/vera/modules/financial-analysis/scripts/"
            f"{engine_name}"
        )
        clara_path = f"clara-codex-plugin/plugins/clara/scripts/{engine_name}"
        assert vera_path in vera_entries
        assert clara_path not in clara_entries

    plan_path = (
        "vera-codex-plugin/plugins/vera/modules/sales-plan/scripts/"
        "prepare_sales_plan_case.py"
    )
    legacy_financial_path = (
        "vera-codex-plugin/plugins/vera/modules/financial-analysis/scripts/"
        "prepare_sales_plan_case.py"
    )
    assert plan_path in vera_entries
    assert legacy_financial_path not in vera_entries
    assert (
        "clara-codex-plugin/plugins/clara/scripts/prepare_sales_plan_case.py"
        not in (clara_entries)
    )


def test_vera_routes_every_commercialista_module() -> None:
    plugin_root = ROOT / "plugins" / "vera"
    components = json.loads(
        (plugin_root / "components.json").read_text(encoding="utf-8")
    )
    mcp_config = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
    routed_mcp_modules = {
        server["args"][-1] for server in mcp_config["mcpServers"].values()
    }
    skill_names = {
        path.parent.name for path in (plugin_root / "skills").glob("*/SKILL.md")
    }

    assert components["schema_version"] == 1
    assert set(components["plugins"]) == COMMERCIALISTA_MODULE_NAMES
    assert routed_mcp_modules == COMMERCIALISTA_MODULE_NAMES - {
        "bandi-agevolazioni",
        "browser-automation",
        "startup-business-plan",
        "comunicazione-professionale",
        "management-control-pack",
        "centrale-rischi-review",
        "passive-invoice-audit",
        "presenza-digitale-studio",
    }
    assert COMMERCIALISTA_MODULE_NAMES - {"client-file-preparation"} <= skill_names
    assert "client-file-preparation" not in skill_names
    assert components["workflow_roles"] == {
        "new-client": {
            "kind": "workflow",
            "internal_engines": ["client-file-preparation"],
        },
        "client-file-preparation": {
            "kind": "internal_engine",
            "parent_workflow": "new-client",
        },
    }


def test_component_package_selection_rebuilds_unified_bundles() -> None:
    builder = load_builder()

    targets = builder.select_packages(
        builder.load_packages(), builder.load_bundles(), ["check-entries"]
    )

    assert {target.target_name for target in targets} == {"vera"}


def test_generated_workbench_packages_include_local_review_server() -> None:
    builder = load_builder()
    shared_server = (ROOT / "scripts" / "serve_review_workbench.py").read_bytes()

    for package in builder.load_packages():
        plugin_dir = ROOT / "plugins" / package.plugin
        adapter_path = plugin_dir / "assets" / "review-workbench-adapter.json"
        if not adapter_path.exists():
            continue
        expected = builder.expected_zip_entries(package)
        entry_name = (
            f"{package.package_root}/plugins/{package.plugin}/scripts/review_server.py"
        )
        if (plugin_dir / "scripts" / "review_server.py").exists():
            assert entry_name in expected
            assert expected[entry_name] != shared_server
        else:
            assert expected[entry_name] == shared_server


def test_every_repo_plugin_is_classified_for_release() -> None:
    builder = load_builder()

    present_plugins = {path.name for path in builder.discover_plugin_dirs()}
    configured_plugins = {package.plugin for package in builder.load_packages()}
    for package in builder.load_packages():
        configured_plugins.update(
            builder.embedded_plugin_names(ROOT / "plugins" / package.plugin)
        )
    for bundle in builder.load_bundles():
        configured_plugins.update(bundle.plugin_names)
        for plugin_name in bundle.plugin_names:
            configured_plugins.update(
                builder.embedded_plugin_names(ROOT / "plugins" / plugin_name)
            )
    configured_plugins.update(builder.load_non_downloadable_plugins())

    assert present_plugins
    assert present_plugins == configured_plugins


def test_mcp_plugins_declare_app_manifest_for_widget_handoff() -> None:
    builder = load_builder()

    plugin_dirs = builder.discover_plugin_dirs()
    mcp_plugin_dirs = [path for path in plugin_dirs if (path / ".mcp.json").exists()]

    assert mcp_plugin_dirs
    for plugin_dir in mcp_plugin_dirs:
        manifest = json.loads(
            (plugin_dir / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        app_manifest_path = plugin_dir / ".app.json"

        assert manifest["mcpServers"] == "./.mcp.json"
        assert manifest["apps"] == "./.app.json"
        assert app_manifest_path.exists()
        assert json.loads(app_manifest_path.read_text(encoding="utf-8")) == {"apps": {}}


def test_plugin_skills_include_run_output_location_policy() -> None:
    builder = load_builder()

    for plugin_dir in builder.discover_plugin_dirs():
        skill_files = sorted((plugin_dir / "skills").glob("*/SKILL.md"))
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )

        assert builder.REQUIRED_OUTPUT_LOCATION_SNIPPET in combined_skill_text


def test_changed_plugin_sources_bump_manifest_version() -> None:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "plugins"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return

    changed_plugins = {
        path_parts[1]
        for line in result.stdout.splitlines()
        if line.strip()
        for path_parts in [Path(line).parts]
        if len(path_parts) >= 3 and path_parts[2] != "privacy"
    }

    for plugin_name in sorted(changed_plugins):
        manifest_path = ROOT / "plugins" / plugin_name / ".codex-plugin" / "plugin.json"
        if not manifest_path.exists():
            continue
        previous_result = subprocess.run(
            ["git", "show", f"HEAD:plugins/{plugin_name}/.codex-plugin/plugin.json"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
        if previous_result.returncode != 0:
            continue
        current_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous_manifest = json.loads(previous_result.stdout)

        assert current_manifest["version"] != previous_manifest["version"], (
            f"{plugin_name}: plugin source changed without a manifest version bump; "
            "Codex can keep using the installed same-version cache."
        )


def test_repo_local_marketplace_has_no_plugins() -> None:
    marketplace_path = ROOT / ".agents" / "plugins" / "marketplace.json"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))

    assert marketplace["name"] == "mp"
    assert marketplace["interface"]["displayName"] == "Mparanza"
    assert marketplace["plugins"] == []


def test_configured_plugin_zips_do_not_include_local_junk() -> None:
    builder = load_builder()
    forbidden_parts = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    forbidden_names = {".DS_Store"}

    for package in builder.load_packages():
        with ZipFile(package.output_zip) as archive:
            for name in archive.namelist():
                parts = set(Path(name).parts)
                assert not (parts & forbidden_parts)
                assert Path(name).name not in forbidden_names


def test_plotting_plugins_are_embedded_in_clara_package_only() -> None:
    builder = load_builder()

    assert builder.load_non_downloadable_plugins() == set()
    clara_package = {package.plugin: package for package in builder.load_packages()}[
        "clara"
    ]
    clara_components = set(builder.embedded_plugin_names(ROOT / "plugins" / "clara"))
    assert REPORTING_ENGINE_PLUGIN_NAMES <= clara_components
    assert "reporting-engine" not in clara_components
    assert not (ROOT / "plugins" / "reporting-engine").exists()
    assert (ROOT / "plugins" / "clara" / "modules" / "reporting-engine").is_dir()
    clara_entries = builder.expected_zip_entries(clara_package)
    component_prefix = f"{clara_package.package_root}/plugins/clara/modules"
    for plugin_name in REPORTING_ENGINE_PLUGIN_NAMES:
        assert (
            f"{component_prefix}/{plugin_name}/.codex-plugin/plugin.json"
            in clara_entries
        )
    assert (
        f"{component_prefix}/reporting-engine/catalog/png_gallery_manifest.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/catalog/mechanical_acceptance_summary.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/fixtures/mechanical_acceptance/universal_complete.csv"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/catalog/semantic_layer.schema.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/catalog/semantic_acceptance_summary.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/scripts/semantic_layer.py"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/scripts/dataset_intake.py"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/references/semantic_layer.md"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/fixtures/semantic_layer/retail_monthly.semantic.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/fixtures/semantic_layer/retail_monthly.snapshot_cases.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/fixtures/semantic_layer/retail_monthly_refresh.csv"
        in clara_entries
    )

    for target in [*builder.load_packages(), *builder.load_bundles()]:
        entries = builder.expected_zip_entries(target)
        for plugin_name in REPORTING_ENGINE_PLUGIN_NAMES:
            assert not any(
                f"{target.package_root}/plugins/{plugin_name}/" in name
                for name in entries
            )


@pytest.mark.parametrize(
    ("component", "runner"),
    (
        ("distribution-analysis", "run_distribution.py"),
        ("funnel-analysis", "run_funnel_analysis.py"),
        ("mix-contribution-analysis", "run_mix_contribution.py"),
        ("period-comparison", "run_period_comparison.py"),
        ("scatter-bubble-analysis", "run_scatter_bubble.py"),
        ("set-overlap-analysis", "run_set_overlap.py"),
        ("statement-analysis", "run_statement_analysis.py"),
        ("variance-analysis", "run_variance.py"),
    ),
)
def test_extracted_clara_chart_components_import_without_repository_paths(
    extracted_clara_plugin: Path,
    tmp_path: Path,
    component: str,
    runner: str,
) -> None:
    runner_path = extracted_clara_plugin / "modules" / component / "scripts" / runner

    result = subprocess.run(
        [sys.executable, str(runner_path), "--help"],
        cwd=tmp_path,
        env=isolated_plugin_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr
    assert "ImportError" not in result.stderr


def test_extracted_clara_semantic_fixture_validates(
    extracted_clara_plugin: Path,
) -> None:
    component_root = extracted_clara_plugin / "modules" / "reporting-engine"
    profiler_spec = importlib.util.spec_from_file_location(
        "extracted_reporting_engine_profiler",
        component_root / "scripts" / "profile_dataset.py",
    )
    semantic_spec = importlib.util.spec_from_file_location(
        "extracted_reporting_engine_semantic",
        component_root / "scripts" / "semantic_layer.py",
    )
    assert profiler_spec and profiler_spec.loader
    assert semantic_spec and semantic_spec.loader
    profiler = importlib.util.module_from_spec(profiler_spec)
    semantic = importlib.util.module_from_spec(semantic_spec)
    profiler_spec.loader.exec_module(profiler)
    semantic_spec.loader.exec_module(semantic)
    fixture_root = component_root / "fixtures" / "semantic_layer"
    profile = profiler.profile_dataset(
        fixture_root / "retail_monthly.csv", dataset_id="retail_monthly"
    )
    layer = json.loads(
        (fixture_root / "retail_monthly.semantic.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (component_root / "catalog" / "selection_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    report = semantic.validate_semantic_layer(layer, profile, manifest)

    assert report["status"] == "contract_valid"
    assert report["semantic_readiness"] == "ready_as_scoped_semantic_input"
    assert report["counts"]["analysis_validities"]["valid"] == 9
    assert report["errors"] == []


def test_extracted_clara_dataset_intake_keeps_first_upload_unreviewed(
    extracted_clara_plugin: Path,
    tmp_path: Path,
) -> None:
    component_root = extracted_clara_plugin / "modules" / "reporting-engine"
    fixture_root = component_root / "fixtures" / "semantic_layer"
    output_dir = tmp_path / "dataset-intake"

    result = subprocess.run(
        [
            sys.executable,
            str(component_root / "scripts" / "dataset_intake.py"),
            str(fixture_root / "retail_monthly.csv"),
            "--dataset-contract-id",
            "retail_monthly",
            "--output-dir",
            str(output_dir),
        ],
        cwd=tmp_path,
        env=isolated_plugin_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )

    receipt = json.loads(
        (output_dir / "dataset_intake.json").read_text(encoding="utf-8")
    )
    layer = json.loads(
        (output_dir / "semantic_layer.draft.json").read_text(encoding="utf-8")
    )
    assert result.returncode == 0, result.stderr
    assert receipt["status"] == "review_required"
    assert all(
        mapping["state"] == "unknown"
        for mapping in layer["business_metric_mappings"].values()
    )


def test_extracted_clara_semantic_acceptance_cli(
    extracted_clara_plugin: Path,
    tmp_path: Path,
) -> None:
    component_root = extracted_clara_plugin / "modules" / "reporting-engine"
    fixture_root = component_root / "fixtures" / "semantic_layer"
    output_path = tmp_path / "semantic_acceptance.json"

    result = subprocess.run(
        [
            sys.executable,
            str(component_root / "scripts" / "semantic_layer.py"),
            "acceptance",
            "--dataset",
            str(fixture_root / "retail_monthly.csv"),
            "--dataset-id",
            "retail_monthly",
            "--layer",
            str(fixture_root / "retail_monthly.semantic.json"),
            "--source",
            str(fixture_root / "retail_monthly_source_notes.md"),
            "--snapshot-suite",
            str(fixture_root / "retail_monthly.snapshot_cases.json"),
            "--output",
            str(output_path),
        ],
        cwd=tmp_path,
        env=isolated_plugin_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["result"] == "pass"
    assert report["validation"]["semantic_readiness"] == (
        "ready_as_scoped_semantic_input"
    )
    assert report["validation"]["counts"]["analysis_validities"]["valid"] == 9
    assert {
        case["case_id"]: case["actual_status"]
        for case in report["snapshot_reuse_proof"]
    } == {
        "origin_snapshot": "compatible",
        "changed_values_new_months_and_members": "compatible",
        "new_unclassified_column": "compatible_with_extensions",
        "bound_metrics_removed": "incompatible",
    }


def test_extracted_clara_attaches_refresh_to_existing_semantic_version(
    extracted_clara_plugin: Path,
    tmp_path: Path,
) -> None:
    component_root = extracted_clara_plugin / "modules" / "reporting-engine"
    fixture_root = component_root / "fixtures" / "semantic_layer"
    profiler_spec = importlib.util.spec_from_file_location(
        "extracted_reporting_engine_refresh_profiler",
        component_root / "scripts" / "profile_dataset.py",
    )
    assert profiler_spec and profiler_spec.loader
    profiler = importlib.util.module_from_spec(profiler_spec)
    profiler_spec.loader.exec_module(profiler)
    profile_path = tmp_path / "refresh_profile.json"
    profile_path.write_text(
        json.dumps(
            profiler.profile_dataset(
                fixture_root / "retail_monthly_refresh.csv",
                dataset_id="retail_monthly",
            )
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "snapshot_attachment.json"

    result = subprocess.run(
        [
            sys.executable,
            str(component_root / "scripts" / "semantic_layer.py"),
            "attach",
            "--profile",
            str(profile_path),
            "--layer",
            str(fixture_root / "retail_monthly.semantic.json"),
            "--output",
            str(output_path),
        ],
        cwd=tmp_path,
        env=isolated_plugin_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )

    attachment = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stderr
    assert attachment["attachment_status"] == "attached"
    assert attachment["compatibility"]["status"] == "compatible"
    assert attachment["semantic_version"] == 1


def test_extracted_clara_renders_known_period_comparison(
    extracted_clara_plugin: Path,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "sample_sales.csv"
    write_reporting_smoke_dataset(dataset)
    output_dir = tmp_path / "period_trend"
    renderer = (
        extracted_clara_plugin
        / "modules"
        / "reporting-engine"
        / "scripts"
        / "render_capability.py"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(renderer),
            "period_comparison.trend",
            str(dataset),
            "--output-dir",
            str(output_dir),
            "--role-bindings-json",
            json.dumps({"period_axis": "Date", "comparison_metric": "Sales"}),
            "--options-json",
            json.dumps(
                {
                    "period_window": {
                        "current": {"year": 2026, "month_cutoff": 6},
                        "previous": {"year": 2025, "month_cutoff": 6},
                    },
                    "current_period_label": "2026",
                    "previous_period_label": "2025",
                    "reporting_entity": "Clara smoke test",
                }
            ),
            "--currency",
            "EUR",
            "--artifact-mode",
            "data_and_render",
        ],
        cwd=tmp_path,
        env=isolated_plugin_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((output_dir / "render_manifest.json").read_text())
    context = json.loads((output_dir / "period_comparison_context.json").read_text())
    chart_path = output_dir / "year_over_year_line.png"

    assert manifest["runner"]["status"] == "ok"
    assert manifest["adapter_id"] == "reporting-engine.period_comparison"
    assert manifest["legacy_plugin_source"] == "period-comparison"
    assert context["totals"] == {
        "current": 1507.0,
        "previous": 1305.0,
        "delta": 202.0,
        "delta_percent": pytest.approx(15.478927203065135),
    }
    assert context["monthly"][-1]["current_amount"] == 345.0
    assert context["monthly"][-1]["previous_amount"] == 255.0
    assert chart_path.is_file()
    assert chart_path.stat().st_size > 0


def test_extracted_clara_renders_distribution_with_variant(
    extracted_clara_plugin: Path,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "sample_sales.csv"
    write_reporting_smoke_dataset(dataset)
    output_dir = tmp_path / "distribution_boxplot"
    renderer = (
        extracted_clara_plugin
        / "modules"
        / "reporting-engine"
        / "scripts"
        / "render_capability.py"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(renderer),
            "distribution.boxplot",
            str(dataset),
            "--output-dir",
            str(output_dir),
            "--role-bindings-json",
            json.dumps(
                {
                    "distribution_metric": "Sales",
                    "panel_dimension": "Brand",
                }
            ),
            "--currency",
            "EUR",
            "--artifact-mode",
            "data_and_render",
            "--include-variants",
        ],
        cwd=tmp_path,
        env=isolated_plugin_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((output_dir / "render_manifest.json").read_text())
    context = json.loads((output_dir / "distribution_context.json").read_text())
    recipe = json.loads((output_dir / "render_request_recipe.json").read_text())

    assert manifest["runner"]["status"] == "ok"
    assert manifest["adapter_id"] == "reporting-engine.distribution"
    assert manifest["legacy_plugin_source"] == "distribution-analysis"
    assert recipe["options"]["charts"] == ["boxplot"]
    assert recipe["mappings"]["small_multiples_dimension"] == "Brand"
    assert (output_dir / "boxplot.png").is_file()
    assert (output_dir / "boxplot_small_multiples.png").is_file()
    summary_by_period = {row["Period"]: row for row in context["summary"]}
    assert summary_by_period == {
        "~Jun-2025": {
            "Period": "~Jun-2025",
            "rows": 12,
            "mean": 108.75,
            "median": 102.5,
            "std": pytest.approx(22.066531630091262),
            "min": 80.0,
            "max": 150.0,
        },
        "~Jun-2026": {
            "Period": "~Jun-2026",
            "rows": 12,
            "mean": pytest.approx(125.58333333333333),
            "median": 120.0,
            "std": pytest.approx(31.601088397059808),
            "min": 83.0,
            "max": 180.0,
        },
    }


def test_all_repo_plugins_declare_and_check_dependencies() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        assert (plugin_root / "requirements.txt").exists(), plugin_name
        assert (plugin_root / "scripts" / "check_dependencies.py").exists(), plugin_name

        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        assert skill_files, plugin_name
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )
        assert "check_dependencies.py" in combined_skill_text, plugin_name
        assert "requirements" in combined_skill_text.lower(), plugin_name


def test_all_dependency_checkers_accept_explicit_requirements_files() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        checker = plugin_root / "scripts" / "check_dependencies.py"
        result = subprocess.run(
            [sys.executable, str(checker), "--help"],
            check=True,
            text=True,
            capture_output=True,
        )

        assert "--requirements" in result.stdout, plugin_name


def test_all_plugin_skills_define_material_choice_intake() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        assert skill_files, plugin_name
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )
        lowered_skill_text = combined_skill_text.lower()

        assert (
            "material choices" in lowered_skill_text
            or "material research-angle" in lowered_skill_text
        ), plugin_name
        assert (
            "ask only those unresolved choices in chat" in lowered_skill_text
            or "ask the choice in chat" in lowered_skill_text
        ), plugin_name
        assert "actual inputs" in lowered_skill_text, plugin_name
        assert "unless the facts cue them" in lowered_skill_text, plugin_name


def test_plugin_skills_do_not_require_continue_theater() -> None:
    builder = load_builder()
    banned_continue_prompts = (
        "type `continue`",
        "type continue",
        "enter `continue`",
        "enter continue",
        "write `continue`",
        "write continue",
        "say `continue`",
        "say continue",
        "reply `continue`",
        "reply continue",
    )
    required_checkpoint_terms = (
        "external",
        "destructive",
        "approval-sensitive",
        "material",
    )

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        assert skill_files, plugin_name
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )
        lowered_skill_text = combined_skill_text.lower()

        for phrase in banned_continue_prompts:
            assert phrase not in lowered_skill_text, plugin_name
        assert all(term in lowered_skill_text for term in required_checkpoint_terms), (
            f"{plugin_name}: skills must explain that explicit continuation or approval "
            "is only for external, destructive, approval-sensitive, or material decisions"
        )


def test_builder_source_validation_includes_interaction_pattern_audit(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    plugin_root = tmp_path / "bad-review"
    skill_root = plugin_root / "skills" / "bad-review"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text(
        "Ask the user to type continue before every step.",
        encoding="utf-8",
    )

    errors = builder.validate_plugin_interaction_patterns(plugin_root)

    assert any("interaction pattern continue_theater" in error for error in errors)
    assert any(
        "interaction pattern approval_boundary_missing" in error for error in errors
    )


def test_builder_source_validation_includes_workbench_demo_audit(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    plugin_root = tmp_path / "bad-workbench"
    adapter_root = plugin_root / "assets"
    adapter_root.mkdir(parents=True)
    (adapter_root / "review-workbench-adapter.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "plugin": "bad-workbench",
                "detailGroups": [{"title": "Evidence", "fields": ["support"]}],
                "localized": {"it": {"title": "Demo"}},
                "demo": {
                    "review_type": "bad_review",
                    "items": [
                        {
                            "id": "row-1",
                            "item_type": "matched_row",
                            "title": "Matched row",
                            "allowed_actions": ["accept"],
                            "recommended_action": "accept",
                            "data": {"status": "matched"},
                            "evidence": [],
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    errors = builder.validate_plugin_workbench_demo(plugin_root)

    assert any("workbench demo demo_queue_too_shallow" in error for error in errors)
    assert any("workbench demo demo_evidence_missing" in error for error in errors)


def test_builder_source_validation_includes_review_payload_contract_coverage(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    plugin_root = tmp_path / "uncovered-workbench"
    adapter_root = plugin_root / "assets"
    adapter_root.mkdir(parents=True)
    (adapter_root / "review-workbench-adapter.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "plugin": "uncovered-workbench",
                "demo": {"items": []},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    errors = builder.validate_plugin_contract_coverage(plugin_root)

    assert any(
        "review payload contract coverage generated_payload_contract_test_missing"
        in error
        for error in errors
    )


def test_builder_validation_matches_dependency_standard() -> None:
    builder = load_builder()

    assert (
        builder.validate_package_config(builder.load_packages(), builder.load_bundles())
        == []
    )
    assert builder.validate_bundle_config(builder.load_bundles()) == []
    for plugin_root in builder.discover_plugin_dirs():
        assert builder.validate_plugin_source(plugin_root) == []


def test_builder_rejects_redundant_plugin_namespace_in_skill_name(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    plugin_root = tmp_path / "vera"
    skill_path = plugin_root / "skills" / "journal-sampling" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\nname: vera:journal-sampling\ndescription: Invalid fixture.\n---\n",
        encoding="utf-8",
    )

    errors = builder.validate_plugin_skill_identities(plugin_root)

    assert errors == [
        "vera: skills/journal-sampling/SKILL.md name must be bare; Codex "
        "supplies the public vera: namespace",
        "vera: skills/journal-sampling/SKILL.md name must match its skill "
        "directory (journal-sampling)",
    ]


@pytest.mark.parametrize(
    "required_snippet",
    (
        "Should I transmit this technical problem to the developer so we can fix it?",
        "Do not continue with a chat interview, offer a fallback, or ask any",
        "does not authorize transmission of the user's improvement suggestion.",
        "Only in a later turn, after the failure-report choice has been handled",
        "credentials, secrets, or other identifying information.",
        "obtain separate suggestion-transmission consent.",
        "Should I transmit this suggestion to the developer so we can improve",
    ),
)
def test_builder_rejects_transmitted_feedback_policy_missing_safeguard(
    tmp_path: Path, required_snippet: str
) -> None:
    builder = load_builder()
    plugin_root = tmp_path / "vera"
    skill_path = plugin_root / "skills" / "vera" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    source_skill = (
        ROOT / "plugins" / "vera" / "skills" / "vera" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert required_snippet in source_skill
    skill_path.write_text(
        source_skill.replace(required_snippet, "", 1),
        encoding="utf-8",
    )

    errors = builder.validate_plugin_source(plugin_root)

    assert (
        "vera: skill instructions must include plugin improvement feedback policy"
        in errors
    )


def test_dependency_checkers_are_packaged_in_download_zips() -> None:
    builder = load_builder()

    for package in builder.load_packages():
        checker = (
            f"{package.package_root}/plugins/"
            f"{package.plugin}/scripts/check_dependencies.py"
        )
        requirements = (
            f"{package.package_root}/plugins/" f"{package.plugin}/requirements.txt"
        )
        with ZipFile(package.output_zip) as archive:
            names = set(archive.namelist())
            assert checker in names
            assert requirements in names


def test_clara_and_vera_package_managed_python_launchers() -> None:
    builder = load_builder()

    for package in builder.load_packages():
        if package.plugin not in {"clara", "vera"}:
            continue
        prefix = f"{package.package_root}/plugins/{package.plugin}/scripts/"
        with ZipFile(package.output_zip) as archive:
            names = set(archive.namelist())
        assert prefix + "managed_python_runtime.py" in names
        assert prefix + "_managed_python_runtime.py" in names


def test_standard_accounting_bundle_marketplace_contains_public_plugins() -> None:
    with ZipFile(ACCOUNTING_BUNDLE_ZIP) as archive:
        names = set(archive.namelist())
        marketplace = json.loads(
            archive.read("vera-codex-plugin/.agents/plugins/marketplace.json")
        )

    entries = marketplace["plugins"]
    bundled_plugins = {entry["name"] for entry in entries}

    assert marketplace["name"] == "mp-vera"
    assert marketplace["interface"]["displayName"] == "MP Vera"
    assert bundled_plugins == STANDARD_ACCOUNTING_PLUGIN_NAMES
    for entry in entries:
        plugin = entry["name"]
        assert entry["source"]["path"] == f"./plugins/{plugin}"
        assert (
            f"vera-codex-plugin/plugins/{plugin}/" ".codex-plugin/plugin.json"
        ) in names


def test_only_configured_plugin_zip_artifacts_are_committed() -> None:
    builder = load_builder()
    configured_targets = [*builder.load_packages(), *builder.load_bundles()]
    configured_zip_paths = sorted(
        target.output_zip.relative_to(ROOT).as_posix() for target in configured_targets
    )
    zip_paths = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "plugin_packages").glob("*/*.zip")
    }
    expected_install_zip_paths = {
        "plugin_packages/clara/clara-plugin.zip",
        "plugin_packages/lucia/lucia-plugin.zip",
        "plugin_packages/vera/vera-plugin.zip",
    }
    allowed_upload_zip_paths = {
        target.output_zip.with_name(f"{target.target_name}-chatgpt-upload.zip")
        .relative_to(ROOT)
        .as_posix()
        for target in configured_targets
    }
    claude_config = json.loads(
        (ROOT / "scripts" / "claude_plugin_packages.json").read_text(encoding="utf-8")
    )
    allowed_claude_zip_paths = {
        package["output_zip"] for package in claude_config["packages"]
    }

    assert {target.target_name for target in configured_targets} == {
        "clara",
        "lucia",
        "vera",
    }
    assert set(configured_zip_paths) == expected_install_zip_paths
    assert expected_install_zip_paths <= zip_paths
    assert zip_paths <= (
        expected_install_zip_paths | allowed_upload_zip_paths | allowed_claude_zip_paths
    )


def test_repo_plugins_declare_distinct_icons() -> None:
    builder = load_builder()
    icon_payloads = {}

    for package in builder.load_packages():
        manifest = json.loads(
            (package.plugin_dir / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        interface = manifest["interface"]
        icon_reference = interface["composerIcon"]
        assert interface["logo"] == icon_reference, package.plugin
        icon_path = package.plugin_dir / icon_reference.removeprefix("./")
        assert icon_path.exists(), package.plugin
        icon_payloads[package.plugin] = icon_path.read_bytes()

        with ZipFile(package.output_zip) as archive:
            icon_entry = (
                f"{package.package_root}/plugins/{package.plugin}/"
                f"{icon_reference.removeprefix('./')}"
            )
            assert icon_entry in archive.namelist()

    assert len(set(icon_payloads.values())) == len(icon_payloads)


def test_repo_plugins_declare_public_metadata() -> None:
    builder = load_builder()
    required_interface_fields = (
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
        "capabilities",
        "websiteURL",
        "privacyPolicyURL",
        "termsOfServiceURL",
        "supportURL",
        "defaultPrompt",
        "brandColor",
        "composerIcon",
        "logo",
    )

    for package in builder.load_packages():
        manifest = json.loads(
            (package.plugin_dir / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["name"] == package.plugin
        assert manifest["version"]
        assert manifest["description"]
        assert manifest["homepage"]
        assert manifest["repository"]
        assert manifest["license"]
        assert manifest["skills"] == "./skills/"
        assert manifest["author"]["name"]
        assert manifest["author"]["email"]
        assert manifest["keywords"]

        interface = manifest["interface"]
        for field in required_interface_fields:
            assert interface[field], f"{package.plugin}: {field}"
        assert package.category == interface["category"]
        assert len(interface["defaultPrompt"]) <= 3, package.plugin


def test_all_repo_plugins_declare_canonical_open_source_metadata() -> None:
    builder = load_builder()
    canonical_repository = "https://github.com/fabioannovazzi/app_files"

    for plugin_root in builder.discover_plugin_dirs():
        manifest = json.loads(
            (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        assert manifest["repository"] == canonical_repository, plugin_root.name
        assert manifest["license"] == "AGPL-3.0-only", plugin_root.name


def test_all_repo_plugins_include_end_of_run_feedback_policy() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )
        normalized_skill_text = " ".join(combined_skill_text.split())

        assert "## Plugin Improvement Feedback" in combined_skill_text, plugin_name
        if plugin_name in {"clara", "vera"}:
            assert (
                "Localize the consent question to the conversation language."
                in combined_skill_text
            ), plugin_name
            assert (
                "Vuoi che trasmetta questo problema tecnico allo sviluppatore "
                "così possiamo risolverlo?" in combined_skill_text
            ), plugin_name
            assert (
                "Should I transmit this technical problem to the developer so we "
                "can fix it?" in combined_skill_text
            ), plugin_name
            assert (
                "Do not continue with a chat interview, offer a fallback, or ask any "
                "suggestion question in the same turn." in normalized_skill_text
            ), plugin_name
            assert (
                "Consent to transmit the technical problem does not authorize "
                "transmission of the user's improvement suggestion."
                in normalized_skill_text
            ), plugin_name
            assert (
                "client or customer names or data, source documents, run or case "
                "details, credentials, secrets, or other identifying information"
                in normalized_skill_text
            ), plugin_name
            assert (
                "follow the normal text-suggestion path below: draft a separate "
                "sanitized suggestion, show its exact text, and obtain separate "
                "suggestion-transmission consent." in normalized_skill_text
            ), plugin_name
            assert (
                "Vuoi che trasmetta questo suggerimento allo sviluppatore così "
                f"possiamo migliorare {plugin_name.title()}?" in combined_skill_text
            ), plugin_name
            assert (
                "Should I transmit this suggestion to the developer so we can improve "
                f"{plugin_name.title()}?" in combined_skill_text
            ), plugin_name
            assert "scripts/change_requests.py submit-problem" in combined_skill_text
            assert (
                "scripts/change_requests.py reserve-suggestion-prompt"
                in combined_skill_text
            )
            assert "scripts/change_requests.py submit-suggestion" in combined_skill_text
            assert "scripts/change_requests.py start-interview" in combined_skill_text
            assert (
                "Always use the generic client-free string below" in combined_skill_text
            )
            generic_voice_command = (
                'python scripts/change_requests.py start-interview --opportunity "General '
                f"{plugin_name.title()} improvement suggestion; no client, customer, "
                'source, run, or case details supplied." --language <language>'
            )
            assert generic_voice_command in combined_skill_text
            assert "at most one minute" in combined_skill_text
            assert "only if needed, one short follow-up" in combined_skill_text
            specialist_handoff = (
                "After substantive use of this workflow, read and follow the "
                "`Plugin Improvement Feedback` section in "
                f"`../{plugin_name}/SKILL.md`."
            )
            for skill_file in skill_files:
                if skill_file.parent.name == plugin_name:
                    continue
                assert specialist_handoff in skill_file.read_text(
                    encoding="utf-8"
                ), skill_file
        else:
            assert (
                "Keep the improvement note local to chat or run artifacts."
                in combined_skill_text
            ), plugin_name
        assert "email those suggestions" not in combined_skill_text, plugin_name
        assert "personal email address" not in combined_skill_text, plugin_name


def test_all_repo_plugin_skills_include_codex_native_run_ux_contract() -> None:
    builder = load_builder()
    required_snippets = (
        "## Codex-Native Run UX",
        "checklist",
        "Run Intake table",
        "Decision Table",
        "Default output policy",
        "not choices to propose",
        "Artifact Card",
        "codex_run_review.md",
        "generated ZIPs",
    )

    for plugin_root in builder.discover_plugin_dirs():
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        assert skill_files, plugin_root.name

        for skill_file in skill_files:
            skill_text = skill_file.read_text(encoding="utf-8")
            normalized_skill_text = " ".join(skill_text.split())
            if plugin_root.name in {"lucia", "vera"} and (
                skill_file.parent.name == "quesito-legale-fiscale"
            ):
                assert "../prompt-optimizer/SKILL.md" in normalized_skill_text
                assert "../deep-research-validator/SKILL.md" in normalized_skill_text
                continue
            if plugin_root.name in {"lucia", "vera"} and (
                skill_file.parent.name != plugin_root.name
            ):
                assert "Read that module's" in normalized_skill_text
                assert "plugin working directory" in normalized_skill_text
                continue
            if plugin_root.name == "clara" and skill_file.parent.name in {
                "attribute-reporting",
                "brand-fit",
            }:
                assert "Read that component's" in normalized_skill_text
                assert "working directory" in normalized_skill_text
                continue
            for snippet in required_snippets:
                assert (
                    snippet in skill_text or snippet in normalized_skill_text
                ), f"{plugin_root.name}: {skill_file}"
            assert (
                "approval checkpoint" in skill_text
                or "inclusion checkpoint" in skill_text
                or "execution checkpoint" in skill_text
                or "approval checkpoint" in normalized_skill_text
                or "inclusion checkpoint" in normalized_skill_text
                or "execution checkpoint" in normalized_skill_text
            ), f"{plugin_root.name}: {skill_file}"


def test_only_legacy_email_plugins_include_user_run_notification_policy() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )

        if plugin_name not in PLUGINS_WITH_LEGACY_USER_EMAIL:
            assert "## User Run Notifications" not in combined_skill_text, plugin_name
            continue

        assert "## User Run Notifications" in combined_skill_text, plugin_name
        assert "At the start of a substantive plugin run" in combined_skill_text
        assert "recipient email address" in combined_skill_text, plugin_name
        assert "completion or handled-error email" in combined_skill_text, plugin_name
        assert "Codex Gmail connector" in combined_skill_text, plugin_name
        assert "plugin scripts, SMTP, Resend, mailto links" in combined_skill_text
        assert "Gmail is unavailable" in combined_skill_text, plugin_name
        assert "separate from Plugin Improvement Feedback" in combined_skill_text


def test_non_plotting_review_plugins_document_save_apply_contract() -> None:
    builder = load_builder()

    plugin_roots = {
        plugin_root.name: plugin_root for plugin_root in builder.discover_plugin_dirs()
    }
    for plugin_name, tool_names in NON_PLOTTING_REVIEW_TOOL_CONTRACTS.items():
        plugin_root = plugin_roots[plugin_name]
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )

        for tool_name in tool_names:
            assert tool_name in combined_skill_text, plugin_name
        assert "ui_decisions.json" in combined_skill_text, plugin_name
        assert "applied_decisions.json" in combined_skill_text, plugin_name
        assert "final_artifacts.json" in combined_skill_text, plugin_name


def test_all_repo_plugins_include_trigger_eval_fixtures() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        fixture_path = plugin_root / "evals" / "trigger_fixtures.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))

        assert payload["plugin"] == plugin_name
        assert payload["version"] == 1
        assert payload["should_trigger"], plugin_name
        assert payload["should_not_trigger"], plugin_name
        for case in payload["should_trigger"]:
            assert case["id"]
            assert case["prompt"]
            assert case["required_signals"]
        for case in payload["should_not_trigger"]:
            assert case["id"]
            assert case["prompt"]


def test_static_plugin_pages_do_not_show_feedback_mailto_footer() -> None:
    forbidden_snippets = (
        "mailto:",
        "Dicci cosa possiamo migliorare",
        "Tell us what we can improve",
        "Dites-nous ce que nous pouvons",
        "Sagen Sie uns, was wir verbessern",
        "feedback-note",
    )

    for page_path in STATIC_PLUGIN_PAGES:
        page = page_path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            assert snippet not in page, page_path.as_posix()


def test_static_plugin_pages_do_not_restore_retired_downloads_or_branding() -> None:
    stale_download_snippets = (
        'href="downloads/check-entries-plugin.zip',
        'href="downloads/concordato-plan-review-plugin.zip',
        'href="downloads/clara-plugin.zip',
        'href="downloads/deep-research-validator-plugin.zip',
        'href="downloads/distribution-analysis-plugin.zip',
        'href="downloads/client-file-preparation-plugin.zip',
        'href="downloads/new-client-plugin.zip',
        'href="downloads/journal-bank-reconciliation-plugin.zip',
        'href="downloads/journal-sampling-plugin.zip',
        'href="downloads/mix-contribution-analysis-plugin.zip',
        'href="downloads/period-comparison-plugin.zip',
        'href="downloads/prompt-optimizer-plugin.zip',
        'href="downloads/report-builder-plugin.zip',
        'href="downloads/riconciliazione-partite-plugin.zip',
        'href="downloads/scatter-bubble-analysis-plugin.zip',
        'href="downloads/variance-analysis-plugin.zip',
    )
    standard_pages = tuple(
        page_path
        for page_path in ACCOUNTING_STATIC_PLUGIN_PAGES
        if page_path.parent.name != "vera"
    )
    for page_path in standard_pages:
        page = page_path.read_text(encoding="utf-8")

        assert "Plugins4Accountants" not in page, page_path.as_posix()
        assert "Vera" in page, page_path.as_posix()
        assert "bundle" not in page.lower(), page_path.as_posix()
        assert "data-free-download-link" not in page, page_path.as_posix()
        assert VERA_DOWNLOAD_HREF not in page, page_path.as_posix()
        assert "Plugin Pack" not in page, page_path.as_posix()
        assert "Download ZIP" not in page, page_path.as_posix()
        assert "Scarica ZIP" not in page, page_path.as_posix()
        assert "Apri " "Vera" not in page, page_path.as_posix()
        for snippet in stale_download_snippets:
            assert snippet not in page, page_path.as_posix()

    for plugin_name in REPORTING_ENGINE_PLUGIN_NAMES:
        assert not (
            ROOT
            / "static"
            / "shared"
            / plugin_name
            / "downloads"
            / f"{plugin_name}-plugin.zip"
        ).exists()
        assert not (
            ROOT / "static" / "shared" / plugin_name / "LEGGIMI_INSTALLAZIONE.txt"
        ).exists()


def test_static_plugin_pages_share_quiet_white_theme() -> None:
    shell = (ROOT / "static" / "shared" / "plugin-page-shell.css").read_text(
        encoding="utf-8"
    )
    scale = (ROOT / "static" / "shared" / "function-page-scale.css").read_text(
        encoding="utf-8"
    )
    journey_shell = (ROOT / "static" / "shared" / "vera-journey.css").read_text(
        encoding="utf-8"
    )

    assert "--function-title-size: 2.875rem;" in scale
    assert "--function-section-title-size: 2.125rem;" in scale
    assert "--function-lead-size: 1.1875rem;" in scale
    assert "--plugin-hero-title-size: var(--function-title-size);" in shell
    assert "--plugin-section-title-size: var(--function-section-title-size);" in shell
    assert "--plugin-lead-size: var(--function-lead-size);" in shell
    assert "font-size: var(--plugin-hero-title-size)" in shell
    assert "font-size: var(--plugin-section-title-size)" in shell
    assert "font-size: var(--plugin-lead-size)" in shell
    assert "font-size: clamp(1.08rem" not in shell
    assert "--vj-white: #ffffff;" in journey_shell
    assert "background: var(--vj-white);" in journey_shell

    for page_path in ACCOUNTING_STATIC_PLUGIN_PAGES:
        page = page_path.read_text(encoding="utf-8")

        if "../vera-journey.css?v=" in page:
            assert re.search(
                r'href="\.\./vera-journey\.css\?v=[^"]+"',
                page,
            )
            continue

        assert (
            "--paper: #ffffff;" in page
            or "--bg: #ffffff;" in page
            or "--white: #FFFFFF;" in page
            or "--white: #ffffff;" in page
        ), page_path.as_posix()
        assert "font-size: clamp(3rem" not in page, page_path.as_posix()
        assert "font-size: clamp(42px, 7vw" not in page, page_path.as_posix()
        assert "background: rgba(251, 252, 251" not in page, page_path.as_posix()


@pytest.mark.parametrize(
    "page_path",
    (
        ROOT / "static" / "shared" / "vera" / "index.html",
        ROOT / "static" / "shared" / "clara" / "index.html",
        *VERA_PUBLIC_PAGE_PATHS,
    ),
)
def test_public_product_pages_load_instrument_sans(page_path: Path) -> None:
    page = page_path.read_text(encoding="utf-8")

    assert "family=Instrument+Sans" in page, page_path.as_posix()


@pytest.mark.parametrize(
    "stylesheet_path",
    (
        ROOT / "static" / "shared" / "plugin-page-shell.css",
        ROOT / "static" / "shared" / "vera" / "index.html",
        ROOT / "static" / "shared" / "clara" / "clara-page.css",
    ),
)
def test_public_product_styles_apply_instrument_sans_to_form_controls(
    stylesheet_path: Path,
) -> None:
    stylesheet = stylesheet_path.read_text(encoding="utf-8")

    assert 'font-family: "Instrument Sans"' in stylesheet
    assert re.search(
        r"button,\s*input,\s*optgroup,\s*select,\s*textarea\s*"
        r"\{\s*font-family:\s*inherit;",
        stylesheet,
    )


def test_public_plugin_explainer_pages_use_shared_white_shell() -> None:
    shell = (ROOT / "static" / "shared" / "plugin-page-shell.css").read_text(
        encoding="utf-8"
    )

    assert "--paper: #ffffff;" in shell
    assert "--bg: #ffffff;" in shell
    assert "--shadow: none;" in shell
    assert "display: block !important;" in shell
    assert "width: auto;" in shell
    assert "max-width: none;" in shell
    assert "height: 34px;" in shell
    assert ".brand::before" not in shell
    assert 'content: "Home";' not in shell
    assert "prefers-reduced-motion" in shell
    assert "linear-gradient" not in shell.lower()
    assert "radial-gradient" not in shell.lower()
    for color in ("#002060", "#0070c0", "#00b0f0", "#f3fbff"):
        assert color in shell
    for stale_accent in ("#496a60", "#27313a", "#e7eee9"):
        assert stale_accent not in shell

    for page_path in PUBLIC_PLUGIN_EXPLAINER_PAGES:
        page = page_path.read_text(encoding="utf-8")

        if page_path.parent.name in {"clara", "lucia"}:
            assert (
                f'href="{page_path.parent.name}-page.css?v=' in page
            ), page_path.as_posix()
        else:
            assert 'href="../plugin-page-shell.css' in page, page_path.as_posix()


@pytest.mark.parametrize("relative_path", VERA_PUBLIC_PAGE_PATHS)
def test_vera_downstream_pages_show_mparanza_logo(relative_path: Path) -> None:
    page = (ROOT / relative_path).read_text(encoding="utf-8")
    header_match = re.search(r"<header(?:\s[^>]*)?>.*?</header>", page, re.DOTALL)

    assert (
        'href="../plugin-page-shell.css?v=20260813-function-pages"' in page
    ), relative_path.as_posix()
    assert header_match is not None, relative_path.as_posix()
    if relative_path.name in {"geneva.html", "uk.html", "zurich.html"}:
        renderer = (
            ROOT / "static" / "shared" / "new-client" / "jurisdiction-pages.js"
        ).read_text(encoding="utf-8")
        assert '<header class="topbar"></header>' in page
        assert 'src="jurisdiction-pages.js?v=' in page
        assert 'class="brand"' in renderer
        assert (
            '<img src="https://mparanza.com/images/MPARANZA-HORIZONTAL.png" '
            'alt="Mparanza">' in renderer
        )
        return

    header = header_match.group(0)
    assert 'class="brand"' in header
    assert (
        '<img src="https://mparanza.com/images/MPARANZA-HORIZONTAL.png" '
        'alt="Mparanza">' in header
    )


def test_static_plugin_pages_are_public_and_plugin_downloads_are_removed() -> None:
    _restore_application_import_path()

    from fastapi.testclient import TestClient

    from src.fastapi_app_entry import app

    client = TestClient(app)
    paths = [
        path.relative_to(ROOT).as_posix() for path in ACCOUNTING_STATIC_PLUGIN_PAGES
    ]
    download_paths = ("/downloads/vera", "/downloads/clara")
    old_individual_free_download_paths = (
        "/static/shared/check-entries/downloads/check-entries-plugin.zip",
        "/static/shared/prompt-optimizer/downloads/prompt-optimizer-plugin.zip",
    )
    for path in paths:
        response = client.get(f"/{path}")

        assert response.status_code == 200, path
    for path in download_paths:
        response = client.get(path, follow_redirects=False)

        assert response.status_code == 404, path
    removed_pro_response = client.get(
        "/downloads/accounting-plugin-pack/pro", follow_redirects=False
    )
    assert removed_pro_response.status_code == 404
    for clara_asset in (
        "/static/shared/clara/index.html",
        "/static/shared/clara/clara-page.css",
        "/static/shared/clara/icon.svg",
        "/static/shared/product-navigation.css",
        "/static/shared/product-navigation.js",
    ):
        response = client.get(clara_asset)

        assert response.status_code == 200, clara_asset
    for path in old_individual_free_download_paths:
        response = client.get(path, follow_redirects=False)

        assert response.status_code == 404, path


def test_manual_vera_download_is_removed() -> None:
    _restore_application_import_path()

    from fastapi.testclient import TestClient

    from src.fastapi_app_entry import app

    with TestClient(app) as client:
        response = client.get(
            f"{VERA_DOWNLOAD_HREF}?lang=it",
            follow_redirects=False,
        )

        assert response.status_code == 404


def test_clara_downloads_and_removed_explainers_return_404(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _restore_application_import_path()

    from fastapi.testclient import TestClient

    from modules.auth import dependencies as auth_dependencies
    from modules.auth.config import get_auth_config
    from modules.auth.google_identity import GoogleUserInfo
    from modules.auth.session import create_session_cookie
    from modules.hosted_services import api as pdp_api
    from src.fastapi_app_entry import app

    pro_email = "pro@example.com"
    free_email = "free@example.com"
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"clara": [pro_email]}),
        encoding="utf-8",
    )
    structure_file = tmp_path / "permission_structure.json"
    structure_file.write_text(
        json.dumps(
            {
                "clara": [
                    "/downloads/clara",
                    "/static/shared/clara/downloads",
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "s" * 32)
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    get_auth_config.cache_clear()
    try:
        config = get_auth_config()
        removed_plugin_download_paths = (
            "/downloads/clara",
            "/static/shared/clara/downloads/clara-plugin.zip",
        )
        removed_download_paths = ("/downloads/accounting-plugin-pack/pro",)
        studio_redirect_paths = (
            "/static/shared/deep-research-validator/downloads/"
            "deep-research-validator-plugin.zip",
        )
        old_engine_download_paths = (
            "/static/shared/distribution-analysis/downloads/"
            "distribution-analysis-plugin.zip",
            "/static/shared/funnel-analysis/downloads/funnel-analysis-plugin.zip",
            "/static/shared/mix-contribution-analysis/downloads/"
            "mix-contribution-analysis-plugin.zip",
            "/static/shared/scatter-bubble-analysis/downloads/"
            "scatter-bubble-analysis-plugin.zip",
            "/static/shared/set-overlap-analysis/downloads/"
            "set-overlap-analysis-plugin.zip",
            "/static/shared/statement-analysis/downloads/statement-analysis-plugin.zip",
            "/static/shared/variance-analysis/downloads/variance-analysis-plugin.zip",
        )
        public_plugin_pages = (
            "/static/shared/deep-research-validator/index.html",
            "/static/shared/clara/index.html",
            "/static/shared/variance-analysis/index.html",
        )
        removed_plugin_pages = (
            "/static/shared/open-item-reconciliation/index.html",
            "/static/shared/reporting/index.html",
            "/static/shared/research/index.html",
            "/static/shared/mix-contribution-analysis/index.html",
            "/static/shared/period-comparison/index.html",
            "/static/shared/scatter-bubble-analysis/index.html",
            "/static/shared/distribution-analysis/index.html",
            "/static/shared/set-overlap-analysis/index.html",
            "/static/shared/funnel-analysis/index.html",
            "/static/shared/statement-analysis/index.html",
        )
        with TestClient(app) as free_client:
            token, _ = create_session_cookie(GoogleUserInfo(email=free_email), config)
            free_client.cookies.set(config.session_cookie_name, token)

            for page_path in public_plugin_pages:
                response = free_client.get(page_path, follow_redirects=False)
                assert response.status_code == 200

            for page_path in removed_plugin_pages:
                response = free_client.get(page_path, follow_redirects=False)
                assert response.status_code == 404

            for download_path in removed_plugin_download_paths:
                response = free_client.get(
                    f"{download_path}?lang=en", follow_redirects=False
                )
                assert response.status_code == 404
            for download_path in removed_download_paths:
                response = free_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
            for download_path in studio_redirect_paths:
                response = free_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
            for download_path in old_engine_download_paths:
                response = free_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404

        with TestClient(app) as pro_client:
            token, _ = create_session_cookie(GoogleUserInfo(email=pro_email), config)
            pro_client.cookies.set(config.session_cookie_name, token)

            for download_path in removed_plugin_download_paths:
                response = pro_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
            for download_path in removed_download_paths:
                response = pro_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
            for download_path in studio_redirect_paths:
                response = pro_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
            for download_path in old_engine_download_paths:
                response = pro_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        get_auth_config.cache_clear()


def test_clara_forbidden_page_has_no_vera_download() -> None:
    template = (ROOT / "templates" / "forbidden.html").read_text(encoding="utf-8")
    api_source = (ROOT / "modules" / "hosted_services" / "api.py").read_text(
        encoding="utf-8"
    )
    page_copy = f"{template}\n{api_source}"

    assert "Clara access" in template
    assert "Clara is available only to authorized users." in api_source
    assert "Download Vera" not in template
    assert "Pro Accounting Plugin Pack" not in api_source
    assert "standard Accounting Plugin Pack" not in template
    assert "standard_plugin_pack_href" not in template
    assert "accredited accountant access" not in page_copy
    assert "Pro Plugin Pack" not in page_copy


def test_reconciliation_page_explains_open_item_verification_problem() -> None:
    page = (
        ROOT / "static" / "shared" / "riconciliazione-partite" / "index.html"
    ).read_text(encoding="utf-8")

    assert "In pratica" not in page
    assert "Problema che risolve" in page
    assert (
        "Verifica se le partite indicate come aperte lo sono ancora al cut-off" in page
    )
    assert "Qui la riga di partenza è la partita aperta" in page
    assert "La riconciliazione banca-contabilità parte invece" in page
    assert "Cosa dai / cosa ottieni" in page
    assert "Excel conserva il dettaglio riga per riga" in page
    assert "Prompt pronti" in page
    assert "Verifica completa" in page
    assert "Possibili regolamenti non allocati" in page
    assert "Supporti post cut-off" in page
    assert "Usa il default factoring" not in page
    assert "Quattro passaggi per capire che cosa ha chiuso ogni partita" not in page
    assert "what closed each item" not in page


def test_new_client_page_describes_one_connected_client_journey() -> None:
    page = (ROOT / "static" / "shared" / "new-client" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        '<html lang="it">',
        "Nuovo cliente",
        "Un solo percorso per il nuovo cliente, dalla prima cartella ai riesami.",
        "Cosa fornisci",
        "Cosa prepara Vera",
        "Cosa ricevi",
        "Un solo percorso",
        "Le mancanze diventano richieste precise.",
        "Memo studio",
        "Richiesta cliente",
        "Nuovo cliente · Italia",
        "Documenti, incarico, privacy e antiriciclaggio nello stesso fascicolo.",
        'id="prompt-example"',
        'id="file-preparation"',
        'id="relationship"',
        'id="italy"',
    ):
        assert snippet in page
    for stale_snippet in (
        "plugin guida Codex",
        "check_dependencies.py",
        "gli script raccolgono",
        "Codex legge gli output",
        "First pass over a client folder",
        "Turn a messy client folder into a first work pack",
        "Complete intake",
        "XML invoices",
        "Tax fields",
        "Tax notice",
        "Operational first pass",
        "Istruttoria cliente",
        "Onboarding cliente",
    ):
        assert stale_snippet not in page


def test_new_client_page_explains_which_private_data_reaches_the_model() -> None:
    page = (ROOT / "static" / "shared" / "new-client" / "index.html").read_text(
        encoding="utf-8"
    )

    assert (
        'id="model-data" data-model-data-workflow="new-client" '
        'data-model-data-status="relevant"'
    ) in page
    main = page[page.index('<main class="page-shell"') : page.index("</main>")]
    assert main.rstrip().endswith("</section>")
    for snippet in (
        "Quali dati arrivano al modello",
        "What data reaches the model",
        "Quelles données parviennent au modèle",
        "Welche Daten das Modell erhält",
        "Qué datos recibe el modelo",
        "codice fiscale e partita IVA",
        "dati dei documenti di identità",
        "rappresentanti e titolari effettivi",
        "Non sono anonimizzati automaticamente",
        "model_handoff.json",
        "2.500 elementi e 1.500.000 byte",
        "CLIENT-001",
        "senza nomi delle parti, codici fiscali del cliente",
    ):
        assert snippet in page
    for key in (
        "model.title",
        "model.local.copy",
        "model.files.copy",
        "model.relationship.copy",
        "model.runtime.copy",
        "model.identifiers.title",
        "model.note",
    ):
        assert f'data-i18n="{key}"' in page
        assert page.count(f'"{key}":') == 5


def test_new_client_jurisdiction_pages_render_current_model_data_last() -> None:
    source = (
        ROOT / "static" / "shared" / "new-client" / "jurisdiction-pages.js"
    ).read_text(encoding="utf-8")
    model_copy = source.split("const modelCopy = {", 1)[1].split(
        "const jurisdictions = {", 1
    )[0]

    for heading in (
        "Quali dati arrivano al modello",
        "What data reaches the model",
        "Quelles données parviennent au modèle",
        "Qué datos recibe el modelo",
        "Welche Daten das Modell erhält",
    ):
        assert heading in model_copy
    for shared_detail in (
        "model_handoff.json",
        "CLIENT-001",
        "Mparanza",
    ):
        assert model_copy.count(shared_detail) == 5
    assert model_copy.count("Codex") == model_copy.count("Cowork") >= 5

    rendered = source.split("main.innerHTML = `", 1)[1].split(
        "const page = jurisdictions", 1
    )[0]
    assert rendered.count('data-model-data-workflow="new-client"') == 1
    assert rendered.count('data-model-data-status="relevant"') == 1
    assert rendered.rindex('data-model-data-workflow="new-client"') > rendered.rindex(
        'id="download"'
    )
    assert rendered.rindex("</section>") > rendered.rindex(
        'data-model-data-workflow="new-client"'
    )


@pytest.mark.parametrize(
    "relative_path",
    (
        Path("static/shared/archive-organization/index.html"),
        Path("static/shared/check-entries/index.html"),
        Path("static/shared/concordato-plan-review/index.html"),
        Path("static/shared/deep-research-validator/index.html"),
        Path("static/shared/journal-sampling/index.html"),
        Path("static/shared/new-client/index.html"),
        Path("static/shared/prompt-optimizer/index.html"),
    ),
)
def test_vera_process_model_data_copy_omits_provider_mapping(
    relative_path: Path,
) -> None:
    page = (ROOT / relative_path).read_text(encoding="utf-8")
    model_data = page[page.index("data-model-data-workflow=") :]

    assert "OpenAI" not in model_data
    assert "Anthropic" not in model_data


def test_bilancio_model_data_copy_omits_provider_mapping() -> None:
    function_copy = (ROOT / "static/shared/product-function-pages.js").read_text(
        encoding="utf-8"
    )
    bilancio_copy = function_copy.split("const bilancioModelData =", 1)[1].split(
        "Object.entries(bilancioModelData)", 1
    )[0]

    assert "OpenAI" not in bilancio_copy
    assert "Anthropic" not in bilancio_copy
    assert "Il modello usa gli stessi strumenti e limiti" in bilancio_copy
    assert "fino a 50 selettori esatti aggiuntivi complessivi" in bilancio_copy
    assert (
        "Il modello non riceve automaticamente i file sorgente, case.json o lo "
        "snapshot completo"
    ) in bilancio_copy


SHARED_PRODUCT_PAGE_PATHS = {
    Path("static/shared/deep-research-validator/index.html"),
    Path("static/shared/prompt-optimizer/index.html"),
}


@pytest.mark.parametrize("relative_path", VERA_PUBLIC_PAGE_PATHS)
def test_public_page_browser_title_uses_appropriate_brand(relative_path: Path) -> None:
    page = (ROOT / relative_path).read_text(encoding="utf-8")

    if relative_path in SHARED_PRODUCT_PAGE_PATHS:
        assert "| Mparanza</title>" in page
        assert "| Vera</title>" not in page
    else:
        assert "| Vera</title>" in page
        assert "| Mparanza" not in page


def test_new_client_jurisdiction_pages_define_local_scope() -> None:
    new_client_root = ROOT / "static" / "shared" / "new-client"
    jurisdiction_source = (new_client_root / "jurisdiction-pages.js").read_text(
        encoding="utf-8"
    )
    pages = {
        "geneva.html": ("geneva", "fr"),
        "zurich.html": ("zurich", "de"),
        "uk.html": ("uk", "en"),
    }

    for filename, (jurisdiction, default_language) in pages.items():
        page = (new_client_root / filename).read_text(encoding="utf-8")
        assert f'data-jurisdiction="{jurisdiction}"' in page
        assert f'data-presentation-language="{default_language}"' in page
        assert 'src="jurisdiction-pages.js?v=' in page
        assert f'slug: "{filename}"' in jurisdiction_source
        assert f'defaultLanguage: "{default_language}"' in jurisdiction_source
        assert f'hreflang="{default_language}"' in page
        assert 'hreflang="x-default"' in page

    assert "const page = jurisdictions[document.body.dataset.jurisdiction]" in (
        jurisdiction_source
    )
    assert "const language = page.defaultLanguage;" in jurisdiction_source
    assert "document.body.dataset.presentationLanguage = language" in (
        jurisdiction_source
    )
    assert "Report Builder" not in jurisdiction_source
    assert "dataset.jurisdiction =" not in jurisdiction_source
    for localized_scope in (
        "La preparazione documentale è disponibile per questo mercato; la "
        "configurazione professionale oggi prosegue con il country pack Italia.",
        "Document preparation is available for this market; professional setup "
        "currently continues with the Italy country pack.",
        "La préparation documentaire est disponible pour ce marché ; la mise en "
        "place professionnelle se poursuit actuellement avec le pack Italie.",
        "Die Dokumentvorbereitung ist für diesen Markt verfügbar; die "
        "professionelle Einrichtung wird derzeit mit dem Länderpaket Italien "
        "fortgesetzt.",
    ):
        assert localized_scope in jurisdiction_source


def test_new_client_page_is_the_native_italy_journey() -> None:
    page = (ROOT / "static" / "shared" / "new-client" / "index.html").read_text(
        encoding="utf-8"
    )

    for italy_journey_copy in (
        "Nuovo cliente · Italia",
        "Documenti, incarico, privacy e antiriciclaggio nello stesso fascicolo.",
        "Vera applica al rapporto professionale le fonti, i documenti e gli "
        "adempimenti previsti per lo studio italiano.",
    ):
        assert italy_journey_copy in page


def test_journal_sampling_page_matches_plugin_site_pattern() -> None:
    page = (ROOT / "static" / "shared" / "journal-sampling" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Crea un campione riproducibile da un giornale disordinato",
        "Journal Sampling",
        "Create a reproducible sample from a messy journal export",
        "Créer un échantillon reproductible depuis un journal désordonné",
        "Eine reproduzierbare Stichprobe aus einem uneinheitlichen Journal erstellen",
        "Sample selection you can replay",
        "Campione riproducibile e controllabile",
        "Create the sample from the work folder",
        "inspection.json",
        "suggested_recipe.json",
        "normalized_journal.csv",
        "sampling_audit.json",
    ):
        assert snippet in page
    for stale_snippet in (
        "Gli script Python deterministici",
        "Deterministic Python scripts",
        "How it runs in Codex",
    ):
        assert stale_snippet not in page


def test_homepage_routes_accountant_plugins_through_vera() -> None:
    source = (ROOT / "modules" / "hosted_services" / "api.py").read_text(
        encoding="utf-8"
    )

    assert source.count('"href": "/static/shared/vera/index.html"') == 5
    assert source.count('"label": "Vera"') == 5
    assert source.count('"tooltip_key": "vera"') == 5
    for direct_workflow_link in (
        '"href": "/static/shared/open-item-reconciliation/index.html"',
        '"href": "/static/shared/report-builder/index.html"',
        '"href": "/static/shared/new-client/index.html"',
        '"href": "/static/shared/new-client/uk.html"',
        '"href": "/static/shared/new-client/geneva.html"',
        '"href": "/static/shared/new-client/zurich.html"',
        '"href": "/static/shared/research/index.html"',
        '"href": "/static/shared/journal-sampling/index.html"',
        '"href": "/static/shared/check-entries/index.html"',
        '"href": "/static/shared/journal-bank-reconciliation/index.html"',
        '"href": "/static/shared/riconciliazione-partite/index.html"',
        '"href": "/static/shared/concordato-plan-review/index.html"',
    ):
        assert direct_workflow_link not in source


def test_prompt_optimizer_page_matches_plugin_site_pattern() -> None:
    page = (ROOT / "static" / "shared" / "prompt-optimizer" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Optimize Prompt",
        "Ottimizza prompt",
        "Optimiser le prompt",
        "Prompt optimieren",
        "Un brief che Deep Research può seguire e tu puoi controllare.",
        "Fornisci",
        "Vera prepara",
        "Ricevi",
        "Come viene preparato",
        "Da un quesito disordinato a una ricerca controllabile.",
        "Un solo prompt per iniziare.",
        "Un passaggio dentro un percorso più lungo.",
        "question_inventory.json",
        "prompt_recipe.json",
        "optimized_prompt.md",
        "prompt_audit.json",
        "prompt_package.md",
        "source_domains.txt",
        "source_domains_comma.txt",
        "README_HUMAN.md",
        "/?lang=${safeLang}",
    ):
        assert snippet in page

    assert VERA_PRODUCT_PAGE_HREF not in page


def test_prompt_optimizer_workflow_hides_internal_file_handoff_in_every_locale() -> (
    None
):
    page = (ROOT / "static" / "shared" / "prompt-optimizer" / "index.html").read_text(
        encoding="utf-8"
    )

    for user_facing_copy in (
        "Avvia Deep Research con il brief e i siti già preparati.",
        "Start Deep Research with the prepared brief and source sites.",
        "Lancez Deep Research avec le brief et les sites sources déjà préparés.",
        "Inicie Deep Research con el encargo y los sitios fuente ya preparados.",
        "Starten Sie Deep Research mit dem vorbereiteten Briefing und den Quellwebsites.",
    ):
        assert user_facing_copy in page

    for internal_handoff in (
        "Usa optimized_prompt.md come istruzione",
        "Use optimized_prompt.md as the instruction",
        "Utilisez optimized_prompt.md comme instruction",
        "Use optimized_prompt.md como instrucción",
        "Nutzen Sie optimized_prompt.md als Anweisung",
    ):
        assert internal_handoff not in page


def test_new_client_pages_keep_native_jurisdictions_and_localize_spanish_file_preparation() -> (
    None
):
    page = (ROOT / "static" / "shared" / "new-client" / "index.html").read_text(
        encoding="utf-8"
    )
    jurisdiction_source = (
        ROOT / "static" / "shared" / "new-client" / "jurisdiction-pages.js"
    ).read_text(encoding="utf-8")

    assert '<html lang="it">' in page
    assert 'new URLSearchParams(window.location.search).get("lang")' in page
    assert 'const isItaly = lang === "it";' in page
    assert 'document.querySelectorAll("[data-italy-only]")' in page
    assert (
        'data-video-modules="dati-fiscali-strutturati,avviso-intake,email-cliente"'
        in page
    )
    assert 'data-lang="' not in page
    assert 'id="market-' not in page
    assert "const language = page.defaultLanguage;" in jurisdiction_source
    assert "URLSearchParams" not in jurisdiction_source
    assert "window.location.replace" not in page


def test_vera_page_scopes_market_specific_functions_without_a_separate_bucket() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )
    core_start = page.index('id="core"')
    core_end = page.index("</section>", core_start)
    core = page[core_start:core_end]

    for module_link in (
        "../new-client/index.html#journey",
        "../avviso-intake/index.html",
        "../archive-organization/index.html",
        "../journal-sampling/index.html",
        "../check-entries/index.html#journey",
        "../journal-bank-reconciliation/index.html",
        "../riconciliazione-partite/index.html",
        "../sales-plan/index.html",
        "../startup-business-plan/index.html",
        "../variance-analysis/index.html",
        "../management-control-pack/index.html",
        "../centrale-rischi-review/index.html",
        "../financial-analysis/index.html",
        "../comunicazione-professionale/index.html",
        "../presenza-digitale-studio/index.html",
        "../report-builder/index.html",
        "../quesito-legale-fiscale/index.html",
        "../studio-archive/index.html",
        "../browser-automation/index.html",
    ):
        assert f'href="{module_link}"' in core
    for module_link in (
        "../bilancio-xbrl-it/index.html",
        "../bandi-agevolazioni/index.html",
        "../fatture-xml-check/index.html",
        "../report-enti-locali/index.html",
        "../concordato-plan-review/index.html",
        "../previdenza-inps/index.html",
        "../registro-imprese-sari/index.html",
    ):
        module = re.search(
            rf'<a class="module-row"[^>]+href="{re.escape(module_link)}"[^>]*>',
            core,
        )
        assert module is not None
        assert 'data-jurisdiction-item="it"' in module.group(0)
    assert core.count(" data-module-link") == 29
    assert core.count('class="module-row"') == 29
    assert core.count('data-jurisdiction-item="it"') == 7
    for language in ("en", "fr", "de"):
        assert f'data-jurisdiction-item="{language}"' not in core
    for area_id in (
        "area-clients",
        "area-matters",
        "area-accounting",
        "area-analysis",
        "area-research",
        "area-studio",
    ):
        assert f'<article class="workstream" id="{area_id}">' in core
    assert 'id="modello"' not in page
    assert 'id="core"' in page
    assert 'id="jurisdiction"' not in page
    assert 'id="video"' not in page
    assert 'id="installa"' in page
    assert "Core multilingue + pacchetto Italia" not in page
    assert "Cambia la lingua del lavoro, non la giurisdizione applicata" not in page
    assert "FatturaPA" in core
    assert "const jurisdictionsByPage" not in page
    assert "item.hidden = item.dataset.jurisdictionItem !== lang" in page
    assert (
        "https://chatgpt.com/auth/login?next=%2Fplugins%2Fplugins_6a57ac5ce65c8191ae7bd0a51160eb7d"
        in page
    )
    assert "data-vera-install-link" in page
    assert 'href="downloads/vera-cowork-plugin.zip"' in page
    assert "data-vera-cowork-download-link" in page
    for localized_title in (
        "Installazione",
        "Installation",
        "Instalación",
    ):
        assert localized_title in page
    for localized_eyebrow in (
        "Assistente AI per commercialisti",
        "AI companion for accountants",
        "AI companion pour les experts-comptables",
        "AI companion für Steuerberaterinnen und Steuerberater",
        "AI companion para asesores fiscales y contables",
    ):
        assert localized_eyebrow in page
    for localized_chatgpt_button in (
        "Installa per ChatGPT Work e Codex",
        "Install for ChatGPT Work and Codex",
        "Installer pour ChatGPT Work et Codex",
        "Für ChatGPT Work und Codex installieren",
        "Instalar para ChatGPT Work y Codex",
    ):
        assert localized_chatgpt_button in page
    for localized_cowork_button in (
        "Scarica per Claude Cowork",
        "Download for Claude Cowork",
        "Télécharger pour Claude Cowork",
        "Für Claude Cowork herunterladen",
        "Descargar para Claude Cowork",
    ):
        assert localized_cowork_button in page
    for stale_snippet in (
        "/downloads/vera",
        "data-download-link",
        "data-free-download-link",
        "manual ZIP",
        "ZIP manuale",
        "ZIP manuel",
        "manuelle ZIP",
        '"hero.eyebrow": "Vera · Codex per commercialisti"',
        '"hero.eyebrow": "Vera · Codex for accountants"',
        '"hero.eyebrow": "Vera · Codex pour les experts-comptables"',
        '"hero.eyebrow": "Vera · Codex für Steuerberaterinnen und Steuerberater"',
        '"hero.eyebrow": "Vera · Codex para asesores fiscales y contables"',
        "In Codex e Cowork, Vera lavora dai file nella cartella di progetto e prepara risultati durevoli e rivedibili.",
        "In Codex and Cowork, Vera works from the files in your project folder and prepares durable, reviewable outputs.",
        "Dans Codex et Cowork, Vera travaille à partir des fichiers du dossier de projet et prépare des résultats durables et révisables.",
        "In Codex und Cowork arbeitet Vera mit den Dateien im Projektordner und erstellt dauerhafte, prüfbare Ergebnisse.",
        "En Codex y Cowork, Vera trabaja con los archivos de la carpeta del proyecto y prepara resultados duraderos y revisables.",
    ):
        assert stale_snippet not in page


def test_vera_page_localizes_every_module_title() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    title_keys = (
        "module.newClient.title",
        "module.archiveOrganization.title",
        "module.archive.title",
        "module.sampling.title",
        "module.entries.title",
        "module.bank.title",
        "module.reconciliation.title",
        "module.plan.title",
        "module.variance.title",
        "module.managementPack.title",
        "module.financialAnalysis.title",
        "module.communication.title",
        "module.report.title",
        "module.question.title",
    )
    for title_key in title_keys:
        assert page.count(f'data-i18n="{title_key}"') == 1
        assert page.count(f'"{title_key}":') == 5

    visible_copy_keys = set(re.findall(r'data-i18n(?:-aria-label)?="([^"]+)"', page))
    for copy_key in visible_copy_keys:
        assert page.count(f'"{copy_key}":') == 5, copy_key

    for untranslated_italian_copy in (
        "matching rivedibile",
        "workpaper Excel",
        "Tie-out numerico",
        "fiscali e compliance",
        "pacchetto corretto",
    ):
        assert untranslated_italian_copy not in page


def test_vera_page_lists_client_file_workflows_without_an_extra_subgroup() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )
    area = re.search(
        r'<article class="workstream" id="area-clients">.*?</article>',
        page,
        flags=re.DOTALL,
    )

    assert area is not None
    area_markup = area.group(0)
    assert "module-cluster" not in area_markup
    assert "group.clientFile" not in page
    assert area_markup.index('id="new-client"') < area_markup.index(
        'id="studio-archive"'
    )
    assert area_markup.index('id="studio-archive"') < area_markup.index(
        'id="archive-organization"'
    )
    for workflow_id, href in (
        ("new-client", "../new-client/index.html#journey"),
        ("studio-archive", "../studio-archive/index.html"),
        ("archive-organization", "../archive-organization/index.html"),
    ):
        workflow = re.search(
            rf'<a[^>]+id="{workflow_id}".*?</a>',
            area_markup,
            flags=re.DOTALL,
        )
        assert workflow is not None
        assert f'href="{href}"' in workflow.group(0)
        assert "<p" not in workflow.group(0)


def test_vera_page_links_plan_separately_from_financial_analysis() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    plan = re.search(
        r'<a[^>]+id="sales-plan".*?</a>',
        page,
        flags=re.DOTALL,
    )
    assert plan is not None
    assert 'href="../sales-plan/index.html"' in plan.group(0)
    assert "data-module-link" in plan.group(0)
    assert "module-row__arrow" in plan.group(0)
    assert "module.plan.title" in plan.group(0)

    business_plan = re.search(
        r'<a[^>]+id="startup-business-plan".*?</a>',
        page,
        flags=re.DOTALL,
    )
    assert business_plan is not None
    assert 'href="../startup-business-plan/index.html"' in business_plan.group(0)
    assert "data-module-link" in business_plan.group(0)
    assert "module.startupBusinessPlan.title" in business_plan.group(0)

    management_pack = re.search(
        r'<a[^>]+id="management-control-pack".*?</a>',
        page,
        flags=re.DOTALL,
    )
    assert management_pack is not None
    assert 'href="../management-control-pack/index.html"' in management_pack.group(0)
    assert "module.managementPack.title" in management_pack.group(0)

    financial_analysis = re.search(
        r'<a[^>]+id="financial-analysis".*?</a>',
        page,
        flags=re.DOTALL,
    )
    assert financial_analysis is not None
    assert 'href="../financial-analysis/index.html"' in financial_analysis.group(0)
    assert "data-module-link" in financial_analysis.group(0)
    assert "module-row__arrow" in financial_analysis.group(0)
    assert "conto economico mensile" in page
    assert "monthly P&L" in page
    assert "Analisi finanziaria e due diligence" in page
    assert "Financial analysis and due diligence" in page
    assert "adjusted EBITDA" in page
    assert "net debt" in page
    for stale_count in (
        "Diciotto funzioni",
        "Eighteen capabilities",
        "Dix-huit fonctions",
        "Achtzehn Funktionen",
        "Dieciocho funciones",
        "Diciassette funzioni",
        "Seventeen capabilities",
        "Dix-sept fonctions",
        "Siebzehn Funktionen",
        "Diecisiete funciones",
        "Sedici funzioni",
        "Sixteen capabilities",
        "Seize fonctions",
        "Sechzehn Funktionen",
        "Dieciséis funciones",
        "Quattordici funzioni",
        "Fourteen capabilities",
        "Quatorze fonctions",
        "Vierzehn Funktionen",
        "Catorce funciones",
        "Tredici funzioni",
        "Thirteen capabilities",
        "Treize fonctions",
        "Dreizehn Funktionen",
        "Trece funciones",
    ):
        assert stale_count not in page


def test_vera_page_explains_variance_analysis_and_review_boundary() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )
    module = re.search(
        r'<a[^>]+id="variance-analysis".*?</a>',
        page,
        flags=re.DOTALL,
    )
    function_copy = (
        ROOT / "static" / "shared" / "product-function-pages.js"
    ).read_text(encoding="utf-8")
    variance_copy = function_copy.split('"variance-analysis":', 1)[1].split(
        '"bilancio-xbrl-it":', 1
    )[0]

    assert module is not None
    assert 'href="../variance-analysis/index.html"' in module.group(0)
    assert 'data-i18n="module.variance.title"' in module.group(0)
    assert "<p" not in module.group(0)
    assert '"variance-analysis"' in function_copy
    for required_concept in (
        "Confronta Actual, Budget, Forecast o periodi precedenti",
        "prezzo, volume e mix",
        "I calcoli restano separati dall'interpretazione gestionale.",
        "le prime 10 righe delle sole colonne candidate",
        "al massimo 10 righe di non più di 12 colonne nominate",
        "Il codice esamina l’intero file",
        "la somma degli scostamenti coincida con la variazione totale",
        "non tutte le righe del file né le colonne escluse",
        "può recuperare tutte le righe pertinenti",
        "al massimo i 50 scostamenti principali",
        "Vera non anonimizza né pseudonimizza automaticamente",
    ):
        assert required_concept in variance_copy
    for technical_term in (
        "manifest con hash",
        "ricetta sigillata",
        "pacchetto MCP",
        "token locale",
    ):
        assert technical_term not in variance_copy
    assert variance_copy.count('modelDataStatus: "relevant"') == 5
    assert 'modelDataStatus: "placeholder"' not in variance_copy
    for localized_title in (
        "Analisi degli scostamenti",
        "Variance analysis",
        "Analyse des écarts",
        "Abweichungsanalyse",
        "Análisis de desviaciones",
    ):
        assert localized_title in function_copy


def test_vera_page_explains_fiscal_document_extraction() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )
    function_page = (
        ROOT / "static" / "shared" / "dati-fiscali-strutturati" / "index.html"
    ).read_text(encoding="utf-8")
    function_copy = (
        ROOT / "static" / "shared" / "product-function-pages.js"
    ).read_text(encoding="utf-8")
    video_copy = (ROOT / "static" / "shared" / "video-library.js").read_text(
        encoding="utf-8"
    )

    assert "Estrazione dei dati fiscali dai documenti | Vera" in function_page
    assert "Estrazione dati fiscali" in page
    for localized_title in (
        "Estrazione dei dati fiscali dai documenti",
        "Extract tax data from documents",
        "Extraire les données fiscales des documents",
        "Steuerdaten aus Dokumenten extrahieren",
        "Extraer datos fiscales de documentos",
    ):
        assert localized_title in function_copy
        assert localized_title in video_copy
    for localized_title in (
        "Extract tax data from documents",
        "Extraire les données fiscales des documents",
        "Steuerdaten aus Dokumenten extrahieren",
        "Extraer datos fiscales de documentos",
    ):
        assert localized_title in page
    for required_copy in (
        "F24, CU, 730, Redditi PF",
        "I campi da estrarre sono definiti per ciascun tipo di documento supportato.",
        "l'affidabilità dell'estrazione",
        "Una tabella con una riga per ogni dato estratto",
        "I valori mancanti non vengono ricostruiti.",
        "dipendono dall'impaginazione originale",
    ):
        assert required_copy in function_copy
    assert "indicazioni sui campi richiesti" not in function_copy
    for old_title in (
        "Dati fiscali strutturati",
        "Structured fiscal data",
        "Données fiscales structurées",
        "Strukturierte Steuerdaten",
        "Datos fiscales estructurados",
    ):
        assert old_title not in page
        assert old_title not in function_copy
        assert old_title not in video_copy


def test_vera_page_explains_professional_communication_quality_contract() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )
    function_page = (
        ROOT / "static" / "shared" / "comunicazione-professionale" / "index.html"
    )
    function_copy = (
        ROOT / "static" / "shared" / "product-function-pages.js"
    ).read_text(encoding="utf-8")

    assert function_page.is_file()
    assert 'href="../comunicazione-professionale/index.html"' in page
    assert 'id="comunicazione-professionale"' not in page
    assert '"comunicazione-professionale"' in function_copy
    assert "Valuta una novità da fonti selezionate" in function_copy


def test_vera_page_explains_selected_history_pseudonymization_boundary() -> None:
    function_copy = (
        ROOT / "static" / "shared" / "product-function-pages.js"
    ).read_text(encoding="utf-8")

    for required_copy in (
        "non esplora l'archivio o la posta",
        "Un secondo passaggio indipendente vede solo le copie candidate",
        "La verifica delle affermazioni riceve contratto, bozza e tutte le fonti correnti",
        "gli input ripuliti e i pacchetti temporanei vengono eliminati",
        "È pseudonimizzazione, non anonimizzazione",
        "Il nucleo condiviso di Vera e Lucia applica lo stesso perimetro",
        "solo Codex può inviare facoltativamente a Creative Production",
    ):
        assert required_copy in function_copy
    assert 'modelDataStatus: "relevant"' in function_copy
    for localized_heading in (
        "What data reaches the model",
        "Quelles données parviennent au modèle",
        "Welche Daten das Modell erhält",
        "Qué datos recibe el modelo",
    ):
        assert localized_heading in (
            ROOT / "static" / "shared" / "product-function-page.js"
        ).read_text(encoding="utf-8")


def test_vera_page_explains_studio_website_quality_contract() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )
    function_page = (
        ROOT / "static" / "shared" / "presenza-digitale-studio" / "index.html"
    )
    function_copy = (
        ROOT / "static" / "shared" / "product-function-pages.js"
    ).read_text(encoding="utf-8")

    assert function_page.is_file()
    assert 'href="../presenza-digitale-studio/index.html"' in page
    assert 'id="presenza-digitale-studio"' not in page
    website_copy = function_copy.split('"presenza-digitale-studio":', 1)[1].split(
        '"apertura-pratica":', 1
    )[0]
    assert website_copy.count('modelDataStatus: "relevant"') == 5
    assert 'modelDataStatus: "not-relevant"' not in website_copy
    for expected_copy in (
        "Per ciascuna fonte, il brief registra lo scopo professionale, se serve ancora",
        "For every source, the brief records its professional purpose, whether it is still needed",
        "Pour chaque source, le brief consigne sa finalité professionnelle, si elle reste nécessaire",
        "Für jede Quelle hält das Briefing den beruflichen Zweck, den weiteren Bedarf",
        "Para cada fuente, el brief registra su finalidad profesional, si sigue siendo necesaria",
        "Il codice controlla soltanto che ogni fonte sia coperta",
        "Code checks only that every source is covered",
        "Le code vérifie seulement que chaque source est couverte",
        "Der Code prüft nur, ob jede Quelle abgedeckt ist",
        "El código solo comprueba que cada fuente esté cubierta",
        "Una fonte completa viene riaperta solo quando il piano la indica come necessaria",
        "A full source is reopened only when the plan marks it as necessary",
        "Une source complète n'est rouverte que si le plan la juge nécessaire",
        "Eine vollständige Quelle wird nur erneut geöffnet, wenn der Plan sie",
        "Una fuente completa se vuelve a abrir solo cuando el plan la considera necesaria",
        "Non accede all'archivio generale dello Studio, alle pratiche dei clienti, alla posta",
        "It does not access the firm's general archive, client matters, mailbox",
        "Il n'accède pas aux archives générales du cabinet, aux dossiers clients",
        "Es greift nicht auf das allgemeine Kanzleiarchiv, Mandantenakten, das Postfach",
        "No accede al archivo general del despacho, a expedientes de clientes, al correo",
        "Il modello riceve le fonti entro gli stessi limiti",
        "The model receives sources within the same limits",
        "Le modèle reçoit les sources dans les mêmes limites",
        "Das Modell erhält Quellen innerhalb derselben Grenzen",
        "El modelo recibe las fuentes dentro de los mismos límites",
    ):
        assert expected_copy in website_copy
    for removed_copy in (
        "Tra i dati non pubblici",
        "Codex usa il modello OpenAI",
        "For non-public data",
        "Codex uses the OpenAI model",
        "Parmi les données non publiques",
        "Codex utilise le modèle d'OpenAI",
        "Von den nicht öffentlichen Daten",
        "Codex verwendet das OpenAI-Modell",
        "Entre los datos no públicos",
        "Codex utiliza el modelo de OpenAI",
    ):
        assert removed_copy not in website_copy
    assert "Non rilevante per questo processo." not in website_copy


def test_financial_analysis_page_explains_accounting_fdd_and_review_boundary() -> None:
    page = (ROOT / "static" / "shared" / "financial-analysis" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Analisi finanziaria e due diligence | Vera",
        "Financial analysis and due diligence | Vera",
        "Analyse financière et due diligence | Vera",
        "Finanzanalyse und Due Diligence | Vera",
        "Análisis financiero y due diligence | Vera",
        "Conto economico mensile",
        "Capitale circolante",
        "Concentrazione clienti",
        "Monthly P&L",
        "working capital",
        "customer concentration",
        'id="due-diligence"',
        'href="#due-diligence"',
        "Quality of Earnings e adjusted EBITDA",
        "PFN e componenti debt-like",
        "Capitale circolante normalizzato e target",
        "Bridge EBITDA-to-cash ed Enterprise-to-Equity",
        "Registro passività potenziali",
        "Registro issue finanziarie",
        "Quality of Earnings and adjusted EBITDA",
        "Net debt and debt-like items",
        "Normalized working capital and target",
        "EBITDA-to-cash and Enterprise-to-Equity bridges",
        "Contingent-liability register",
        "Financial-issue register",
        "Registre des passifs éventuels",
        "Register der Eventualverbindlichkeiten",
        "Registro de pasivos contingentes",
        "data_package_manifest.json",
        "dataset_contract.json",
        "relationship_contract.json",
        "crosswalk_manifest.json",
        "analysis_pack_request.json",
        "reconciliation_result.json",
        "prepared_evidence_manifest.json",
        "fdd_result.json",
        "fdd_metrics.json",
        "pack_execution_receipt.json",
        "model_use_manifest.json",
        "contingent_liability_register.json",
        "financial_issue_register.json",
        'data-model-data-workflow="financial-analysis"',
        'data-model-data-status="relevant"',
        "Quali dati arrivano al modello",
        "What data reaches the model",
        "I calcoli non sono eseguiti dal modello",
        "applica regole deterministiche a tutti i dati approvati e inclusi nell’analisi",
        "il modello usa le tabelle e i risultati aggregati",
        "Una fonte originale viene riaperta solo per chiarire una questione specifica",
        "Vera non anonimizza né pseudonimizza i dati",
        'id="prompt-example"',
        'href="../vera/index.html?lang=it"',
    ):
        assert snippet in page

    visible_copy_keys = set(re.findall(r'data-i18n(?:-aria-label)?="([^"]+)"', page))
    for copy_key in visible_copy_keys:
        assert page.count(f'"{copy_key}":') == 5, copy_key

    assert page.count('class="function-model-data__copy" data-i18n="model.copy.') == 3

    for stale_snippet in (
        "Tre analisi finanziarie",
        "Three financial analyses",
        "Trois analyses financières",
        "Drei Finanzanalysen",
        "Tres análisis financieros",
        "Vera non anonimizza né pseudonimizza automaticamente",
        "Il codice applica regole definite",
        "non a un campione",
        "il modello usa normalmente le tabelle",
        "i risultati preparati",
        "Le fonti selezionate vengono importate in una run Studio Archive",
        "L’account del modello è scelto",
        "il processo non ha altre destinazioni esterne",
        "Provalo in Vera",
        "Try it in Vera",
        "Essayez dans Vera",
        "In Vera ausprobieren",
        "Pruébelo en Vera",
        "Nel percorso Vera",
        "In the Vera workflow",
        "Dans le parcours Vera",
        "Im Vera-Ablauf",
        "En el recorrido de Vera",
        'id="related"',
        'data-i18n="prompt.kicker"',
        'data-i18n="related.',
    ):
        assert stale_snippet not in page


@pytest.mark.parametrize(
    ("page_name", "workflow_id"),
    (
        ("financial-analysis", "financial-analysis"),
        ("startup-business-plan", "startup-business-plan"),
        ("management-control-pack", "management-control-pack"),
        ("centrale-rischi-review", "centrale-rischi-review"),
        ("sales-plan", "sales-plan"),
    ),
)
def test_accounting_process_page_ends_with_model_data_block(
    page_name: str, workflow_id: str
) -> None:
    page = (ROOT / "static" / "shared" / page_name / "index.html").read_text(
        encoding="utf-8"
    )
    main = page[page.index('<main class="page-shell"') : page.index("</main>")]

    assert main.count('class="function-model-data"') == 1
    assert f'data-model-data-workflow="{workflow_id}"' in main
    assert 'data-model-data-status="relevant"' in main
    assert main.rstrip().endswith("</section>")
    assert main.rindex('class="function-model-data"') > main.rindex('id="prompt"')


def test_sales_plan_page_explains_actual_to_plan_and_review_boundary() -> None:
    page = (ROOT / "static" / "shared" / "sales-plan" / "index.html").read_text(
        encoding="utf-8"
    )

    assert page.count('"meta.title": "Plan | Vera"') == 5
    for snippet in (
        "<title>Plan | Vera</title>",
        "Actual",
        "Plan",
        "Cina",
        "China",
        "USD",
        "Scope",
        "Periodo",
        "Priority",
        "sales_plan_scenario.csv",
        "assumption_application_ledger.csv",
        "scenario_summary.csv",
        "reconciliation.json",
        "prepared_evidence_manifest.json",
        "plan_execution_receipt.json",
        'data-model-data-workflow="sales-plan"',
        'data-model-data-status="relevant"',
        "Quali dati arrivano al modello",
        "What data reaches the model",
        "tutte le righe Actual osservate nel perimetro",
        "senza che il manifest ripeta il nome originale del file",
        "Vera non anonimizza né pseudonimizza automaticamente",
        'id="prompt-example"',
        'href="../vera/index.html?lang=it"',
    ):
        assert snippet in page

    visible_copy_keys = set(re.findall(r'data-i18n(?:-aria-label)?="([^"]+)"', page))
    for copy_key in visible_copy_keys:
        assert page.count(f'"{copy_key}":') == 5, copy_key

    for forbidden_financial_analysis_copy in (
        "Quality of Earnings",
        "adjusted EBITDA",
        "Net debt",
        "Monthly P&L",
        "Financial analysis and due diligence",
    ):
        assert forbidden_financial_analysis_copy not in page


def test_studio_archive_parity_copy_has_no_file_only_cowork_fallback() -> None:
    financial = (
        ROOT / "static" / "shared" / "financial-analysis" / "index.html"
    ).read_text(encoding="utf-8")
    sales = (ROOT / "static" / "shared" / "sales-plan" / "index.html").read_text(
        encoding="utf-8"
    )
    report_builder = (
        ROOT / "static" / "shared" / "report-builder" / "index.html"
    ).read_text(encoding="utf-8")
    function_copy = (
        ROOT / "static" / "shared" / "product-function-pages.js"
    ).read_text(encoding="utf-8")
    studio = (ROOT / "static" / "shared" / "studio-archive" / "index.html").read_text(
        encoding="utf-8"
    )
    journal = (
        ROOT / "static" / "shared" / "journal-sampling" / "index.html"
    ).read_text(encoding="utf-8")
    check_entries = (
        ROOT / "static" / "shared" / "check-entries" / "index.html"
    ).read_text(encoding="utf-8")
    archive_organization = (
        ROOT / "static" / "shared" / "archive-organization" / "index.html"
    ).read_text(encoding="utf-8")
    concordato = (
        ROOT / "static" / "shared" / "concordato-plan-review" / "index.html"
    ).read_text(encoding="utf-8")

    for page in (financial, sales):
        assert "In Codex and Cowork" not in page
        assert "portable Studio Archive" not in page
    variance_copy = function_copy.split('"variance-analysis":', 1)[1].split(
        '"bandi-agevolazioni":', 1
    )[0]
    assert "In Codex and Cowork" not in variance_copy
    assert "Selected data is imported into a portable Studio Archive run" not in (
        variance_copy
    )
    for public_copy in (financial, sales, report_builder, variance_copy):
        for global_boundary_copy in (
            "L’account del modello è scelto",
            "The firm or user selects the model account",
            "Le cabinet ou l’utilisateur choisit le compte du modèle",
            "Kanzlei oder Nutzer wählen das Modellkonto",
            "El despacho o usuario elige la cuenta del modelo",
            "Questo processo non ha altre destinazioni esterne",
            "This process has no other external destination",
            "Ce processus n'a pas d'autre destination externe",
            "Dieser Prozess hat kein weiteres externes Ziel",
            "Este proceso no tiene otros destinos externos",
        ):
            assert global_boundary_copy not in public_copy
    assert (
        "Studio Archive run and connected-file search work in Codex and Cowork"
        in studio
    )
    assert "To choose a client, the model receives every record’s label" in studio
    assert "The same reduced sample in every mode" in journal
    assert "One index and the same limits in every mode" in check_entries
    assert "The local-folder route scans" in archive_organization
    assert "Local-folder organization works in Codex and Cowork" in (
        archive_organization
    )
    assert "With local MCP and a linked run" in (archive_organization)
    assert "not enabled as a Cowork route" in archive_organization
    assert "When MCP is available, the model uses this path" in concordato
    assert "Local-folder mode runs in Codex Desktop and Cowork" in (
        ROOT
        / "plugins"
        / "archive-organization"
        / "skills"
        / "archive-organization"
        / "SKILL.md"
    ).read_text(encoding="utf-8")

    all_public_copy = "\n".join(
        (
            function_copy,
            studio,
            journal,
            check_entries,
            archive_organization,
            concordato,
        )
    )
    for stale_copy in (
        "in Cowork, they use the exact files connected by the user",
        "in Cowork they run only when the scripts are callable",
        "Cowork cannot scan or reorganize a local client folder",
        "Cowork cannot operate the Studio Archive ledger",
        "cannot create or finalize the Studio Archive run",
        "does not create that Studio Archive context",
        "Cowork and ChatGPT do not scan or apply",
        "compatible Vera context",
        "Organization requires Codex Desktop",
        "for a plan supplied in Cowork or ChatGPT",
        "not included in Cowork",
    ):
        assert stale_copy not in all_public_copy


def test_unlinked_family_explainer_pages_are_removed() -> None:
    for page_path in (
        ROOT / "static" / "shared" / "open-item-reconciliation" / "index.html",
        ROOT / "static" / "shared" / "reporting" / "index.html",
        ROOT / "static" / "shared" / "research" / "index.html",
    ):
        assert not page_path.exists()


def test_deep_research_validator_page_matches_plugin_site_pattern() -> None:
    page = (
        ROOT / "static" / "shared" / "deep-research-validator" / "index.html"
    ).read_text(encoding="utf-8")

    for snippet in (
        "Validate Deep Research",
        "Valida Deep Research",
        "Valider Deep Research",
        "Deep Research validieren",
        "Use it when",
        "Quando usarlo",
        "Review by material claim",
        "Revisione per affermazioni",
        "Select claims",
        "Sceglie le affermazioni",
        "Check sources",
        "Controlla le fonti",
        "Sapere quali conclusioni reggono, prima di usarle.",
        "Fornisci",
        "Vera prepara",
        "Ricevi",
        "Un solo prompt per iniziare.",
        "La validazione chiude il circuito della ricerca.",
        "document_inventory.json",
        "source_inventory.json",
        "claims_review.json",
        "validation_audit.json",
        "validated_document.md",
        "validation_package.md",
        "/?lang=${lang}",
    ):
        assert snippet in page


def test_previdenza_inps_page_explains_the_reviewable_case_journey() -> None:
    page = (ROOT / "static" / "shared" / "previdenza-inps" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Previdenza INPS",
        "INPS Social Security Review",
        "Revue de prévoyance INPS",
        "INPS-Sozialversicherung prüfen",
        "Porta un caso INPS disperso a un fascicolo pronto da rivedere.",
        "Fornisci",
        "Vera prepara",
        "Ricevi",
        "Cronologia del caso",
        "Matrice delle evidenze",
        "Dal fascicolo approvato alla relazione Word.",
        "case_records_validated.json",
        "evidence_matrix.csv",
        "studio_memo.docx",
        'href="../report-builder/index.html?lang=it"',
    ):
        assert snippet in page


def test_registro_imprese_sari_page_explains_the_practice_plan_journey() -> None:
    page = (
        ROOT / "static" / "shared" / "registro-imprese-sari" / "index.html"
    ).read_text(encoding="utf-8")

    for snippet in (
        "Registro Imprese e SARI",
        "Business Register and SARI",
        "Registre des entreprises et SARI",
        "Unternehmensregister und SARI",
        "Porta una richiesta camerale a un piano di pratica chiaro e citato.",
        "Fornisci",
        "Vera prepara",
        "Ricevi",
        "Piano della pratica",
        "Checklist DIRE",
        "Registro delle fonti",
        "practice_plan_validated.json",
        "dire_practice_plan.json",
        "review_handoff.md",
        'href="../prompt-optimizer/index.html?lang=it"',
    ):
        assert snippet in page


def test_homepage_does_not_expose_the_internal_deep_research_validator() -> None:
    source = (ROOT / "modules" / "hosted_services" / "api.py").read_text(
        encoding="utf-8"
    )
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert '"href": "/static/shared/deep-research-validator/index.html"' not in source
    assert 'href="../deep-research-validator/index.html"' not in page
    assert 'href="../quesito-legale-fiscale/index.html"' in page


def test_check_entries_page_matches_plugin_site_pattern() -> None:
    page = (ROOT / "static" / "shared" / "check-entries" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Check Entries",
        "Collega ogni scrittura campionata al supporto disponibile.",
        "Connect every sampled entry to its available support.",
        "Reliez chaque écriture échantillonnée à son justificatif disponible.",
        "Verbinden Sie jede Stichprobenbuchung mit dem verfügbaren Beleg.",
        "Cosa dai / cosa ottieni",
        "Entry checks tied to documents",
        "Controlli con supporto collegato",
        "Start broad, finish with targeted requests",
        "ZIP FatturaPA",
        "Authorized connection",
        "Targeted PDFs",
        "normalized_entries.csv",
        "invoice_inventory.json",
        "pdf_inventory.json",
        "check_results.csv",
        "check_audit.json",
        VERA_PRODUCT_PAGE_HREF,
        "/?lang=${safeLang}",
    ):
        assert snippet in page
    for stale_snippet in (
        "Deterministic Python scripts",
        "Gli script Python deterministici",
        "How it runs in Codex",
        'class="source-step"',
        "source-step__number",
        "0${index + 1}",
    ):
        assert stale_snippet not in page


def test_live_product_pages_do_not_use_numbered_step_labels() -> None:
    page_paths = (
        "463b7449445ad5b75aec5107a5d74ed80f205790e3661780adca1f74dfd14407",
        "4c8e62f349a776e9d2b0ca48f15796b72cb8d4e5a1cf0937a2e84bfc63dd52a9",
        "attribute-reporting/cashmere",
        "check-entries",
        "concordato-plan-review",
        "deep-research-validator",
        "financial-analysis",
        "startup-business-plan",
        "management-control-pack",
        "centrale-rischi-review",
        "journal-bank-reconciliation",
        "journal-sampling",
        "lucia",
        "previdenza-inps",
        "progetto-vera-ai",
        "prompt-optimizer",
        "registro-imprese-sari",
        "report-builder",
        "riconciliazione-partite",
        "sales-plan",
        "studio-archive",
        "clara",
        "vera",
    )
    rejected_numbered_component_tokens = (
        "assurance-step__number",
        "bandi-step__number",
        "bilancio-step__number",
        "source-step__number",
        "workflow-step__number",
        "journey-step__number",
        "journey-stage__number",
        "due-diligence-step__number",
        "privacy-entry__lane-index",
        "section-number",
        "layer-num",
        "trap-num",
        'class="journey-number"',
        'class="step-number"',
        'class="card-number"',
        "counter-reset: comms-step",
        "counter-reset: compliance-principle",
        "content: attr(data-step)",
        "counter-reset: workflow",
        "counter-increment: workflow",
    )

    for page_path in page_paths:
        page = (ROOT / "static" / "shared" / page_path / "index.html").read_text(
            encoding="utf-8"
        )

        assert re.search(r"<span(?: [^>]*)?>0?[1-9]</span>", page) is None
        for rejected_token in rejected_numbered_component_tokens:
            assert rejected_token not in page

    for stylesheet_path in (
        ROOT / "static" / "css" / "app.css",
        ROOT / "static" / "shared" / "clara" / "clara-page.css",
        ROOT / "static" / "shared" / "lucia" / "lucia-page.css",
        ROOT / "static" / "shared" / "vera-journey.css",
    ):
        stylesheet = stylesheet_path.read_text(encoding="utf-8")
        for rejected_token in rejected_numbered_component_tokens:
            assert rejected_token not in stylesheet

    data_handling = (ROOT / "templates" / "data_handling.html").read_text(
        encoding="utf-8"
    )
    assert re.search(r"<span(?: [^>]*)?>0?[1-9]</span>", data_handling) is None
    assert "privacy-entry__lane-index" not in data_handling


def test_homepage_routes_check_entries_through_vera() -> None:
    source = (ROOT / "modules" / "hosted_services" / "api.py").read_text(
        encoding="utf-8"
    )
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert '"href": "/static/shared/check-entries/index.html"' not in source
    assert "Verifica registrazioni" not in source
    assert "../check-entries/index.html" in page


def test_journal_bank_reconciliation_page_matches_plugin_site_pattern() -> None:
    page = (
        ROOT / "static" / "shared" / "journal-bank-reconciliation" / "index.html"
    ).read_text(encoding="utf-8")

    for snippet in (
        "Riconciliazione banca-contabilità",
        "Porta banca e contabilità in una riconciliazione con eccezioni visibili.",
        "Bring bank and accounting into one reconciliation with visible exceptions.",
        "Réunissez banque et comptabilité dans un rapprochement aux exceptions visibles.",
        "Führen Sie Bank und Buchhaltung in einer Abstimmung mit sichtbaren Ausnahmen zusammen.",
        "Cosa dai / cosa ottieni",
        "Prompt pronti",
        "Ready prompts",
        "Complete reconciliation",
        "Con campione movimenti",
        "Avec seuils explicites",
        "Mit festen Schwellen",
        "Matches and exceptions stay separate",
        "Abbinamenti ed eccezioni restano separati",
        "Keep thresholds explicit",
        "normalized_bank.csv",
        "normalized_journal.csv",
        "reconciliation_matches.csv",
        "unmatched_bank.csv",
        "unmatched_journal.csv",
        "reconciliation_audit.json",
        VERA_PRODUCT_PAGE_HREF,
        "/?lang=${safeLang}",
    ):
        assert snippet in page
    for stale_snippet in (
        "Deterministic Python scripts",
        "Codex handles changing customer formats",
        "Reviewable reconciliation, guided in Codex",
    ):
        assert stale_snippet not in page


def test_journal_bank_page_explains_the_bounded_model_data_flow() -> None:
    page = (
        ROOT / "static" / "shared" / "journal-bank-reconciliation" / "index.html"
    ).read_text(encoding="utf-8")

    assert (
        'id="model-data" data-model-data-workflow="journal-bank-reconciliation" '
        'data-model-data-status="relevant"'
    ) in page
    main = page[page.index("<main>") : page.index("</main>")]
    assert main.rstrip().endswith("</section>")
    assert main.rindex('<section class="function-model-data"') == main.index(
        '<section class="function-model-data" id="model-data"'
    )
    for snippet in (
        "Quali dati arrivano al modello",
        "What data reaches the model",
        "Quelles données parviennent au modèle",
        "Welche Daten das Modell erhält",
        "Qué datos recibe el modelo",
        "Il modello comprende la struttura",
        "Il codice elabora localmente l'intero perimetro",
        "Il modello riceve un indice dei casi da rivedere",
        "L'indice usa riferimenti opachi ai casi",
        "Il modello richiede il contesto di un caso quando serve",
        "I dati professionali non vengono anonimizzati né pseudonimizzati automaticamente",
    ):
        assert snippet in page
    for key in (
        "model.title",
        "model.structure.copy",
        "model.local.copy",
        "model.index.copy",
        "model.context.copy",
        "model.residual.title",
        "model.residual.copy",
        "model.note",
    ):
        assert f'data-journey="{key}"' in page
        assert page.count(f'"{key}":') == 5

    for snippet in (
        "Solo nel runtime Codex",
        "Cowork non esegue questo passaggio",
        "Only in the Codex runtime",
        "Uniquement dans l’environnement Codex",
        "Nur in der Codex-Laufzeit",
        "Solo en el entorno Codex",
    ):
        assert snippet in page


def test_homepage_routes_journal_bank_reconciliation_through_vera() -> None:
    source = (ROOT / "modules" / "hosted_services" / "api.py").read_text(
        encoding="utf-8"
    )
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert (
        '"href": "/static/shared/journal-bank-reconciliation/index.html"' not in source
    )
    assert "../journal-bank-reconciliation/index.html" in page


def test_report_builder_page_matches_plugin_site_pattern() -> None:
    page = (ROOT / "static" / "shared" / "report-builder" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Build report",
        "Turn source tables into a reviewable Word report.",
        "Da tabelle sorgente a un report Word rivedibile.",
        "Transformer les tableaux source en rapport Word révisable.",
        "Quelltabellen in einen prüfbaren Word-Bericht verwandeln.",
        "Ready prompts",
        "Prompt pronti",
        "Build a DOCX draft from spreadsheets, CSVs and readable PDFs.",
        "Prepara una bozza DOCX da Excel, CSV e PDF leggibili.",
        "Find tables",
        "Assign sections",
        "Draft report",
        "Open report.docx first",
        "Complete management report",
        "Relazione ente locale",
        "Annual financial statement",
        "inspection.json",
        "suggested_recipe.json",
        "report_tables.json",
        "report_analysis.json",
        "report_draft.md",
        "report.docx",
        "report_audit.json",
        VERA_PRODUCT_PAGE_HREF,
        "/?lang=${safeLang}",
    ):
        assert snippet in page


def test_report_builder_page_explains_bounded_model_data_flow() -> None:
    page = (ROOT / "static" / "shared" / "report-builder" / "index.html").read_text(
        encoding="utf-8"
    )

    assert (
        'id="model-data" data-model-data-workflow="report-builder" '
        'data-model-data-status="relevant"'
    ) in page
    main = page[page.index("<main>") : page.index("</main>")]
    assert main.rstrip().endswith("</section>")
    assert main.rindex('<section class="function-model-data"') == main.index(
        '<section class="function-model-data" id="model-data"'
    )
    for snippet in (
        "Quali dati arrivano al modello",
        "What data reaches the model",
        "Quelles données parviennent au modèle",
        "Welche Daten das Modell erhält",
        "Qué datos recibe el modelo",
        "tutte le righe e celle non vuote",
        "at most eight preview rows per table",
        "up to 16 exact columns and 100 source rows",
        "L'inventaire complet reste dans le contrôle local privé",
        "keine automatische Anonymisierung oder Pseudonymisierung",
        "No hay anonimización ni seudonimización automática",
        "Gli stessi limiti si applicano in ogni ambiente supportato",
        "the helper is not replaced by a direct read",
    ):
        assert snippet in page
    for key in ("model.label", "model.title", "model.conclusion", "model.copy"):
        assert f'data-i18n="{key}"' in page
        assert page.count(f'"{key}":') == 5


@pytest.mark.parametrize(
    ("relative_path", "title_assignment"),
    (
        (
            "vera/index.html",
            'document.title = strings["meta.title"]',
        ),
        (
            "report-builder/index.html",
            'document.title = `${copy[safeLang]["hero.title"]} | Vera`',
        ),
        (
            "concordato-plan-review/index.html",
            "document.title = `${t.hero.title} | Vera`",
        ),
    ),
)
def test_vera_pages_set_browser_title_from_active_locale(
    relative_path: str, title_assignment: str
) -> None:
    page = (ROOT / "static" / "shared" / relative_path).read_text(encoding="utf-8")

    assert title_assignment in page


def test_clara_page_matches_plugin_site_pattern() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "static" / "shared" / "clara" / "clara-page.css").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Clara",
        "AI companion for consultants",
        "Assistente AI per consulenti",
        "Clara adds presentations, narrated research videos, interviews, transcription, documents, retail analysis, and data analysis to Codex.",
        "Clara aggiunge a Codex presentazioni, video di ricerca narrati, interviste, trascrizione, documenti, analisi retail e analisi dei dati.",
        "Available functions",
        "Funzioni disponibili",
        "Presentations, videos, and documents",
        "Presentazioni, video e documenti",
        "Interviews and recordings",
        "Interviste e registrazioni",
        "Retail analysis",
        "Analisi retail",
        "Business analysis",
        "Analisi aziendale",
        "How to use Clara",
        "Come usare Clara",
        "Installation",
        "Installazione",
        "Install Clara for ChatGPT Work and Codex, or download the package for Claude Cowork.",
        "Installa Clara per ChatGPT Work e Codex oppure scarica il pacchetto per Claude Cowork.",
        "Install for ChatGPT Work and Codex",
        "Installa per ChatGPT Work e Codex",
        "Download for Claude Cowork",
        "Scarica per Claude Cowork",
        "https://chatgpt.com/auth/login?next=%2Fplugins%2Fplugins_6a57b17fb5848191be710192d93fe03a",
        "data-clara-install-link",
        "data-clara-cowork-download-link",
        "data-function-link",
        "/?lang=${safeLang}",
    ):
        assert snippet in page
    assert 'id="data-handling"' not in page
    assert 'id="presentations"' not in page
    assert 'id="videos"' not in page
    assert page.count('class="function-link"') == 10
    for stale_snippet in (
        "Clara prepares the work. The judgment remains yours.",
        "Clara prepara il lavoro. Il giudizio resta tuo.",
        "Clara prépare le travail. Le jugement reste le vôtre.",
        "Clara bereitet die Arbeit vor. Das fachliche Urteil bleibt bei Ihnen.",
        "Clara prepara el trabajo. El criterio sigue siendo tuyo.",
        "Clara works with you inside Codex.",
        "Lavora con te dentro Codex.",
        "Elle travaille avec vous dans Codex.",
        "Clara arbeitet mit Ihnen direkt in Codex.",
        "Clara trabaja contigo dentro de Codex.",
        "Clara · Codex for consultants",
        "Clara · Codex per consulenti",
        "Clara · Codex pour les consultants",
        "Clara · Codex für Beraterinnen und Berater",
        "Clara · Codex para consultores",
        "In Codex and Cowork, Clara works from the files in your project folder and prepares durable, reviewable outputs.",
        "In Codex e Cowork, Clara lavora dai file nella cartella di progetto e prepara risultati durevoli e rivedibili.",
        "Dans Codex et Cowork, Clara travaille à partir des fichiers du dossier de projet et prépare des résultats durables et révisables.",
        "In Codex und Cowork arbeitet Clara mit den Dateien im Projektordner und erstellt dauerhafte, prüfbare Ergebnisse.",
        "En Codex y Cowork, Clara trabaja con los archivos de la carpeta del proyecto y prepara resultados duraderos y revisables.",
        "Advisor Case Workspace",
        "A local Codex workspace for case materials, voice notes, judgement and reviewed outputs.",
        "Un workspace Codex locale per materiali, voce, judgement e output rivisti.",
        "Collaboration without a shared database",
        "Collaborazione senza database condiviso",
        "Fabio",
        "quando Clara non basta",
        "Client-pack inclusion gate",
        "Pending consultant judgement is never silently promoted",
        "Download Pro ZIP",
        "data-reporting-download-link",
        "data-pro-download-link",
        "data-clara-download-link",
        "/downloads/clara",
        "Download ZIP",
        "Scarica lo ZIP",
        "Télécharger le ZIP",
        "ZIP herunterladen",
        "manual fallback",
        "alternativa manuale",
        "Pro Plugin Pack",
        "/downloads/accounting-plugin-pack/pro",
        'href="downloads/clara-plugin.zip',
        "font-size: clamp",
        "Download not authorized",
        "Download non autorizzato",
        "Turn your sources into client-ready deliverables.",
        "Trasforma le tue fonti in deliverable pronti per il cliente.",
        "Create, revise, or follow an existing style",
        "Crea, correggi o segui uno stile esistente",
        "Choose the final format",
        "Scegli il formato finale",
        "Start with a folder and a normal request",
        "Parti da una cartella e da una richiesta normale",
        "When the project is more than a presentation",
        "Other Clara workflows",
        "Altri flussi di Clara",
        "Install the published Clara release",
        "Installa la versione pubblicata di Clara",
    ):
        assert stale_snippet not in page
    assert '"dd.' not in page
    assert (
        '<a class="button" href="https://chatgpt.com/auth/login?next=%2Fplugins%2F'
        'plugins_6a57b17fb5848191be710192d93fe03a" target="_blank" '
        'rel="noopener noreferrer" data-clara-install-link '
        'data-i18n="install.button">Install for ChatGPT Work and Codex</a>'
    ) in page
    assert (
        '<a class="button" href="downloads/clara-cowork-plugin.zip" download '
        'data-clara-cowork-download-link data-i18n="install.coworkButton">'
        "Download for Claude Cowork</a>"
    ) in page
    assert page.count('"hero.title": "Clara"') == 5
    assert '<h1 data-i18n="hero.title">Clara</h1>' in page
    assert "padding-left: clamp(32px, 5vw, 64px);" in styles
    assert "border-left: 1px solid var(--cyan);" in styles
    assert "font-size: clamp(64px, 10vw, 124px)" in styles
    assert "font-size: clamp(30px, 4vw, 43px)" in styles
    assert "font-size: clamp(21px, 2.4vw, 27px)" in styles


def test_clara_public_page_browser_title_is_clara() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "<title>Clara</title>" in page
    assert page.count('title: "Clara"') == 5
    assert "Clara | Mparanza" not in page


def test_clara_public_page_language_buttons_and_copy_keys_stay_in_sync() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )
    copy_start = page.index("const copy = {")
    copy_end = page.index("\n    };", copy_start)
    copy_block = page[copy_start:copy_end]
    copy_languages = set(
        re.findall(r"^      ([a-z]{2}): \{$", copy_block, re.MULTILINE)
    )
    language_buttons = set(re.findall(r'data-lang="([a-z]{2})"', page))
    visible_keys = set(
        re.findall(r'data-i18n(?:-aria-label|-content)?="([^"]+)"', page)
    )

    assert language_buttons == copy_languages == {"en", "it", "fr", "de", "es"}
    assert visible_keys
    for key in visible_keys:
        assert copy_block.count(f'"{key}"') == len(copy_languages), key
    for language in copy_languages:
        assert f'hreflang="{language}"' in page


def test_clara_public_page_removes_function_video_from_the_directory() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "presentationVideos" not in page
    assert 'id="presentation-video-link"' not in page
    assert 'id="presentation-video-thumbnail"' not in page
    assert 'id="presentation-video-duration"' not in page


def test_clara_public_page_keeps_copy_corrections_in_every_locale() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )
    copy_start = page.index("const copy = {")
    copy_end = page.index("\n    };", copy_start)
    copy_block = page[copy_start:copy_end]

    for text in (
        "Available functions",
        "Funzioni disponibili",
        "How to use Clara",
        "Come usare Clara",
        "Clara adds presentations, narrated research videos, interviews, transcription, documents, retail analysis, and data analysis to Codex.",
        "Clara aggiunge a Codex presentazioni, video di ricerca narrati, interviste, trascrizione, documenti, analisi retail e analisi dei dati.",
    ):
        assert text in page
    for key in (
        "functions.title",
        "functions.copy",
        "functions.deliverables",
        "functions.presentations",
        "functions.researchVideo",
        "functions.documents",
        "functions.research",
        "functions.interviews",
        "functions.transcription",
        "functions.retail",
        "functions.analysis",
        "functions.dataAnalysis",
    ):
        assert copy_block.count(f'"{key}"') == 5
    assert 'id="data-handling"' not in page
    assert 'id="presentations"' not in page
    return

    for text in (
        "Create or correct high-impact HTML decks and PowerPoint presentations.",
        "Crea e correggi deck HTML di impatto e presentazioni PowerPoint.",
        "Créez ou corrigez des decks HTML percutants et des présentations PowerPoint.",
        "Erstellen oder korrigieren Sie wirkungsvolle HTML-Decks und PowerPoint-Präsentationen.",
        "Crea o corrige presentaciones PowerPoint y decks HTML de alto impacto.",
        "Analyze Excel, CSV, and Parquet files with checked calculations and charts chosen to fit the question.",
        "Analizza file Excel, CSV e Parquet con calcoli controllati e grafici scelti in base alla domanda.",
        "Analysez des fichiers Excel, CSV et Parquet avec des calculs vérifiés et des graphiques choisis en fonction de la question.",
        "Analysieren Sie Excel-, CSV- und Parquet-Dateien mit geprüften Berechnungen und Diagrammen, die zur Fragestellung passen.",
        "Analiza archivos Excel, CSV y Parquet con cálculos comprobados y gráficos elegidos para responder a la pregunta.",
        "Start with an Excel, CSV, or Parquet file and describe the business question.",
        "Parti da un file Excel, CSV o Parquet e descrivi la domanda di business.",
        "Partez d'un fichier Excel, CSV ou Parquet et décrivez votre question métier.",
        "Beginnen Sie mit einer Excel-, CSV- oder Parquet-Datei und beschreiben Sie die geschäftliche Fragestellung.",
        "Parte de un archivo Excel, CSV o Parquet y describe la pregunta de negocio.",
        "Choose the deck format",
        "Scegli il formato del deck",
        "Choisissez le format du deck",
        "Wählen Sie das Deck-Format",
        "Elige el formato del deck",
        "choose an HTML deck for interactivity, navigation, and animations.",
        "scegli un deck HTML quando vuoi interattività, navigazione e animazioni.",
        "choisissez un deck HTML pour l'interactivité, la navigation et les animations.",
        "wählen Sie ein HTML-Deck für Interaktivität, Navigation und Animationen.",
        "elige un deck HTML para disponer de interactividad, navegación y animaciones.",
        "The project is not just a presentation",
        "Il progetto non è solo una presentazione",
        "Le projet n'est pas seulement une présentation",
        "Das Projekt ist nicht nur eine Präsentation",
        "El proyecto no es solo una presentación",
    ):
        assert text in page

    for key in (
        "meta.description",
        "aria.page_navigation",
        "aria.language",
        "aria.promise_strip",
        "formats.html.title.link",
        "retail.retailer_signals.copy.link",
        "retail.brand_fit.copy.link",
        "data.title",
        "data.copy",
        "data.local.kicker",
        "data.local.title",
        "data.local.copy",
        "data.local.model",
        "data.hosted.kicker",
        "data.hosted.title",
        "data.hosted.copy",
        "data.hosted.detail",
        "data.link",
    ):
        assert copy_block.count(f'"{key}"') == 5

    for stale_text in (
        "browser presentations",
        "Start with a folder and a normal request",
        "Parti da una cartella e da una richiesta normale",
        "Retailer Signals and Brand Fit are available now",
        "PowerPoint PPTX",
        "Formato HTML",
        "navigation, speaker notes, and animations.",
        "navigazione, note per chi presenta e animazioni.",
        "navigation, les notes de présentation et les animations.",
        "Navigation, Sprechernotizen und Animationen.",
        '"retail.retailer_signals.kicker"',
        '"retail.brand_fit.kicker"',
        'href="#workflow" class="button',
    ):
        assert stale_text not in page

    assert (
        '<a href="/static/shared/4c8e62f349a776e9d2b0ca48f15796b72cb8d4e5a1cf0937a2e84bfc63dd52a9/'
        'index.html#cover" target="_blank" rel="noopener noreferrer" '
        'data-i18n="formats.html.title.link">interactive</a>'
    ) in page


@pytest.mark.parametrize(
    (
        "two_categories",
        "automatic_anonymisation",
        "chatgpt_plan",
        "additional_recipient",
        "hosted_boundary",
        "hosted_service_detail",
    ),
    (
        (
            "Clara, Vera and Lucia follow the same two-category data policy.",
            "do not automatically anonymise data",
            "user’s existing ChatGPT plan",
            "do not send client files, prompts, or model-context content to Mparanza",
            "A separate processing boundary",
            "The data-handling page explains access, retention and deletion for each hosted service.",
        ),
        (
            "Clara, Vera e Lucia seguono la stessa regola con due categorie.",
            "non anonimizzano automaticamente i dati",
            "piano ChatGPT già utilizzato dall'utente",
            "non inviano a Mparanza file dei clienti, prompt o contenuti del contesto del modello",
            "Un confine di trattamento separato",
            "La pagina sulla gestione dei dati spiega accesso, conservazione e cancellazione per ogni servizio ospitato.",
        ),
        (
            "Clara, Vera et Lucia suivent la même règle en deux catégories.",
            "n'anonymisent pas automatiquement les données",
            "l'offre ChatGPT existante de l'utilisateur",
            "n'envoient à Mparanza ni fichiers clients, ni prompts, ni contenu du contexte du modèle",
            "Un périmètre de traitement distinct",
            "La page sur le traitement des données explique l’accès, la conservation et la suppression pour chaque service hébergé.",
        ),
        (
            "Für Clara, Vera und Lucia gilt dieselbe Regel mit zwei Kategorien.",
            "anonymisieren Daten nicht automatisch",
            "bestehenden ChatGPT-Tarif des Nutzers",
            "senden keine Mandantendateien, Prompts oder Inhalte des Modellkontexts an Mparanza",
            "Eine separate Verarbeitungsgrenze",
            "Die Seite zur Datenverarbeitung erläutert Zugriff, Aufbewahrung und Löschung für jeden gehosteten Dienst.",
        ),
        (
            "Clara, Vera y Lucia siguen la misma política de dos categorías.",
            "no anonimizan los datos automáticamente",
            "plan de ChatGPT que ya utiliza el usuario",
            "no envían a Mparanza archivos de clientes, prompts ni contenido del contexto del modelo",
            "Un límite de tratamiento separado",
            "La página sobre el tratamiento de datos explica el acceso, la conservación y la eliminación de cada servicio alojado.",
        ),
    ),
)
def test_clara_public_page_localizes_two_category_data_policy(
    two_categories: str,
    automatic_anonymisation: str,
    chatgpt_plan: str,
    additional_recipient: str,
    hosted_boundary: str,
    hosted_service_detail: str,
) -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )

    for text in (
        two_categories,
        automatic_anonymisation,
        chatgpt_plan,
        additional_recipient,
        hosted_boundary,
        hosted_service_detail,
    ):
        assert text in page


def test_homepage_routes_report_builder_through_vera() -> None:
    source = (ROOT / "modules" / "hosted_services" / "api.py").read_text(
        encoding="utf-8"
    )
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert '"href": "/static/shared/report-builder/index.html"' not in source
    assert "../report-builder/index.html" in page


def test_concordato_plan_review_page_matches_plugin_site_pattern() -> None:
    page = (
        ROOT / "static" / "shared" / "concordato-plan-review" / "index.html"
    ).read_text(encoding="utf-8")

    for snippet in (
        "Riesamina il caso, non soltanto i numeri del piano.",
        "Review the case, not only the plan numbers.",
        "Examinez le dossier, pas seulement les chiffres du plan.",
        "Prüfen Sie den Fall, nicht nur die Planzahlen.",
        "Il significato viene prima del tie-out.",
        "Meaning comes before the tie-out.",
        "Le sens précède le rapprochement.",
        "Die Bedeutung kommt vor dem Zahlenabgleich.",
        "Giudizio e meccanica non si confondono.",
        "Judgment and mechanics remain distinct.",
        "concordato_case_model.json",
        "creditor_treatment.csv",
        "creditor_class_summary.csv",
        "sources_and_uses.csv",
        "liquidity_schedule.csv",
        "concordato_review_workpaper.xlsx",
        "concordato_semantic_review.md",
        "concordato_preventivo_review_summary.docx",
        "concordato_tie_out_workpaper.xlsx",
        VERA_PRODUCT_PAGE_HREF,
        "/?lang=${safeLang}",
    ):
        assert snippet in page
    for stale_snippet in (
        "Revisione numeri di piano",
        "Concordato Plan Review",
        "schede rettificate",
        "adjusted schedules",
        "Tableaux ajustés",
        "Angepasste Aufstellungen",
        "adjusted DB",
    ):
        assert stale_snippet not in page


def test_homepage_routes_concordato_plan_review_through_vera() -> None:
    source = (ROOT / "modules" / "hosted_services" / "api.py").read_text(
        encoding="utf-8"
    )
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert '"href": "/static/shared/concordato-plan-review/index.html"' not in source
    assert "../concordato-plan-review/index.html" in page


def test_old_plotting_plugin_pages_are_removed() -> None:
    for page_path in (
        ROOT / "static" / "shared" / "mix-contribution-analysis" / "index.html",
        ROOT / "static" / "shared" / "period-comparison" / "index.html",
        ROOT / "static" / "shared" / "scatter-bubble-analysis" / "index.html",
        ROOT / "static" / "shared" / "distribution-analysis" / "index.html",
        ROOT / "static" / "shared" / "set-overlap-analysis" / "index.html",
        ROOT / "static" / "shared" / "funnel-analysis" / "index.html",
        ROOT / "static" / "shared" / "statement-analysis" / "index.html",
        ROOT / "static" / "shared" / "pro-charting" / "index.html",
    ):
        assert not page_path.exists()


def test_reporting_component_manifests_use_clara_homepage() -> None:
    for plugin_name in REPORTING_ENGINE_PLUGIN_NAMES:
        manifest = json.loads(
            (
                ROOT / "plugins" / plugin_name / ".codex-plugin" / "plugin.json"
            ).read_text(encoding="utf-8")
        )
        assert manifest["homepage"] == (
            "https://mparanza.com/static/shared/clara/index.html"
        )


def test_standard_family_plugin_manifests_use_family_homepages() -> None:
    expected_homepages = {
        "archive-organization": (
            "https://mparanza.com/static/shared/vera/index.html?lang=it"
        ),
        "open-item-reconciliation": (
            "https://mparanza.com/static/shared/riconciliazione-partite/index.html"
        ),
        "bandi-agevolazioni": (
            "https://mparanza.com/static/shared/vera/index.html?lang=it"
        ),
        "bilancio-xbrl-it": (
            "https://mparanza.com/static/shared/vera/index.html?lang=it"
        ),
        "check-entries": (
            "https://mparanza.com/static/shared/check-entries/index.html"
        ),
        "client-file-preparation": (
            "https://mparanza.com/static/shared/new-client/index.html#file-preparation"
        ),
        "new-client": ("https://mparanza.com/static/shared/new-client/index.html"),
        "concordato-plan-review": (
            "https://mparanza.com/static/shared/concordato-plan-review/index.html"
        ),
        "comunicazione-professionale": (
            "https://mparanza.com/static/shared/vera/index.html?lang=it"
        ),
        "presenza-digitale-studio": (
            "https://mparanza.com/static/shared/vera/index.html?lang=it"
        ),
        "journal-bank-reconciliation": (
            "https://mparanza.com/static/shared/journal-bank-reconciliation/index.html"
        ),
        "passive-invoice-audit": (
            "https://mparanza.com/static/shared/passive-invoice-audit/index.html"
        ),
        "journal-sampling": (
            "https://mparanza.com/static/shared/journal-sampling/index.html"
        ),
        "deep-research-validator": (
            "https://mparanza.com/static/shared/deep-research-validator/index.html"
        ),
        "financial-analysis": (
            "https://mparanza.com/static/shared/vera/index.html?lang=it"
        ),
        "management-control-pack": (
            "https://mparanza.com/static/shared/management-control-pack/index.html?lang=it"
        ),
        "centrale-rischi-review": (
            "https://mparanza.com/static/shared/centrale-rischi-review/index.html?lang=it"
        ),
        "sales-plan": ("https://mparanza.com/static/shared/sales-plan/index.html"),
        "startup-business-plan": (
            "https://mparanza.com/static/shared/startup-business-plan/index.html?lang=it"
        ),
        "prompt-optimizer": (
            "https://mparanza.com/static/shared/prompt-optimizer/index.html"
        ),
        "previdenza-inps": (
            "https://mparanza.com/static/shared/previdenza-inps/index.html"
        ),
        "registro-imprese-sari": (
            "https://mparanza.com/static/shared/registro-imprese-sari/index.html"
        ),
        "report-builder": (
            "https://mparanza.com/static/shared/report-builder/index.html"
        ),
        "browser-automation": (
            "https://mparanza.com/static/shared/browser-automation/index.html?lang=it"
        ),
        "studio-archive": ("https://mparanza.com/static/shared/vera/index.html"),
        "vera": ("https://mparanza.com/static/shared/vera/index.html?lang=it"),
        "clara": ("https://mparanza.com/static/shared/clara/index.html?lang=en"),
        "lucia": ("https://mparanza.com/static/shared/lucia/index.html"),
    }

    assert set(expected_homepages) | REPORTING_ENGINE_PLUGIN_NAMES == (
        WORKFLOW_PLUGIN_NAMES | {"vera"}
    )
    for plugin_name, expected_homepage in expected_homepages.items():
        manifest = json.loads(
            (
                ROOT / "plugins" / plugin_name / ".codex-plugin" / "plugin.json"
            ).read_text(encoding="utf-8")
        )

        assert manifest["homepage"] == expected_homepage


def test_vera_public_icon_matches_plugin_source() -> None:
    assert (ROOT / "static" / "shared" / "vera" / "icon.svg").read_bytes() == (
        ROOT / "plugins" / "vera" / "assets" / "icon.svg"
    ).read_bytes()


def test_clara_public_icon_matches_plugin_source() -> None:
    assert (ROOT / "static" / "shared" / "clara" / "icon.svg").read_bytes() == (
        ROOT / "plugins" / "clara" / "assets" / "icon.svg"
    ).read_bytes()


@pytest.mark.parametrize(
    ("page_name", "expected_home_href", "expected_product", "expected_links"),
    (
        (
            "vera",
            "/?lang=it",
            "Vera",
            (
                "#area-clients",
                "#area-matters",
                "#area-accounting",
                "#area-analysis",
                "#area-research",
                "#area-studio",
            ),
        ),
        (
            "clara",
            "/",
            "Clara",
            (
                "#area-deliverables",
                "#area-recordings",
                "#area-retail",
                "#area-analysis",
            ),
        ),
        (
            "lucia",
            "/?lang=it",
            "Lucia",
            (
                "#area-research",
                "#area-matters",
                "#area-studio",
            ),
        ),
    ),
)
def test_companion_headers_share_product_navigation(
    page_name: str,
    expected_home_href: str,
    expected_product: str,
    expected_links: tuple[str, ...],
) -> None:
    page = (ROOT / "static" / "shared" / page_name / "index.html").read_text(
        encoding="utf-8"
    )
    header = page.split('<header class="product-nav">', maxsplit=1)[1].split(
        "</header>", maxsplit=1
    )[0]
    link_hrefs = tuple(
        re.findall(
            r'<a\b(?=[^>]*\bdata-i18n="[^"]+")[^>]*\bhref="([^"]+)"',
            header,
        )
    )

    assert 'href="../product-navigation.css?v=' in page
    assert 'src="../product-navigation.js?v=' in page
    assert (
        f'<a class="product-nav__brand" href="{expected_home_href}" '
        'data-home-link aria-label="Mparanza">' in header
    )
    assert (
        '<img src="https://mparanza.com/images/MPARANZA-HORIZONTAL.png" '
        'alt="Mparanza">' in header
    )
    assert f'<span class="product-nav__product">{expected_product}</span>' in header
    assert link_hrefs == expected_links
    assert header.count("data-product-nav-menu") == 2
    assert header.count("data-product-nav-disclosure") == 1
    assert re.findall(r'data-lang="([a-z]{2})"', header) == [
        "it",
        "en",
        "fr",
        "de",
        "es",
    ]
    assert "data-current-language" in header
    assert "GitHub" not in header
    assert 'data-i18n="nav.download"' not in header
    assert 'src="icon.svg"' not in header


def test_companion_navigation_uses_one_scoped_responsive_system() -> None:
    stylesheet = (ROOT / "static" / "shared" / "product-navigation.css").read_text(
        encoding="utf-8"
    )
    script = (ROOT / "static" / "shared" / "product-navigation.js").read_text(
        encoding="utf-8"
    )

    assert ".product-nav__inner" in stylesheet
    assert ".product-nav__menu[data-menu-open] > .product-nav__links" in stylesheet
    assert ".product-nav__language-list button" in stylesheet
    assert "min-height: 44px;" in stylesheet
    assert "@media (max-width: 1080px)" in stylesheet
    assert "@media (max-width: 380px)" in stylesheet
    assert stylesheet.count("flex: 0 0 auto;") >= 3
    assert "[data-product-nav-menu-trigger]" in script
    assert "[data-product-nav-disclosure]" in script
    assert 'event.key === "Escape"' in script
    assert "menuTrigger?.focus()" in script
    assert 'querySelector("summary")?.focus()' in script


@pytest.mark.parametrize("page_name", ("vera", "clara", "lucia"))
def test_companion_pages_leave_improvement_guidance_on_support(
    page_name: str,
) -> None:
    page = (ROOT / "static" / "shared" / page_name / "index.html").read_text(
        encoding="utf-8"
    )

    assert 'class="improvement-note"' not in page
    assert '"improvement.' not in page


@pytest.mark.parametrize("page_name", ("vera", "clara", "lucia"))
def test_companion_pages_offer_skip_link_and_footer_source(page_name: str) -> None:
    page = (ROOT / "static" / "shared" / page_name / "index.html").read_text(
        encoding="utf-8"
    )
    header = page.split('<header class="product-nav">', maxsplit=1)[1].split(
        "</header>", maxsplit=1
    )[0]
    footer = page.split("<footer", maxsplit=1)[1].split("</footer>", maxsplit=1)[0]

    assert '<a class="skip-link" href="#main-content"' in page
    assert '<main id="main-content">' in page
    assert "github.com/fabioannovazzi/app_files/tree/main/plugins/" not in header
    source_branch = "main"
    assert (
        f"github.com/fabioannovazzi/app_files/tree/{source_branch}/plugins/{page_name}"
        in footer
    )


@pytest.mark.parametrize("page_name", ("vera", "clara", "lucia", "studio-archive"))
def test_product_page_footer_omits_repeated_product_label(page_name: str) -> None:
    page = (ROOT / "static" / "shared" / page_name / "index.html").read_text(
        encoding="utf-8"
    )

    footer = page.split("<footer", maxsplit=1)[1].split("</footer>", maxsplit=1)[0]

    assert 'data-i18n="footer.product"' not in footer
    assert 'data-i18n="hero.eyebrow"' not in footer
    assert '"footer.product"' not in page


def test_clara_public_page_uses_vera_visual_system() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )
    stylesheet = (ROOT / "static" / "shared" / "clara" / "clara-page.css").read_text(
        encoding="utf-8"
    )

    assert 'href="clara-page.css?v=' in page
    assert 'src="icon.svg"' in page
    assert 'class="function-directory"' in page
    assert page.count('class="function-link"') == 10
    for color in ("#002060", "#0070C0", "#00B0F0", "#FFFFFF"):
        assert color in stylesheet
    for black in ("#000000", "#171816"):
        assert black not in stylesheet


def test_vera_public_page_uses_deck_blue_palette_without_black() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    for color in ("#002060", "#0070C0", "#00B0F0", "#FFFFFF"):
        assert color in page
    for black in ("#000000", "#000", "#171816"):
        assert black not in page


@pytest.mark.parametrize(
    ("companion", "install_attribute"),
    (
        ("clara", "data-clara-install-link"),
        ("vera", "data-vera-install-link"),
    ),
)
def test_companion_overview_video_follows_the_intended_product_story(
    companion: str, install_attribute: str
) -> None:
    page = (ROOT / "static" / "shared" / companion / "index.html").read_text(
        encoding="utf-8"
    )
    if companion == "vera":
        assert page.index('id="installa"') < page.index('id="core"')
        assert 'id="jurisdiction"' not in page
        assert 'id="assurance"' not in page
        assert "data-featured-video" not in page
        assert 'id="video"' not in page
        assert page.count('class="overview-video"') == 0
        assert "install-panel__video" not in page
        return

    hero_start = page.index('<section class="hero">')
    hero_end = page.index("</section>", hero_start)
    hero = page[hero_start:hero_end]
    functions_start = page.index('<section id="functions">')
    assert 'id="download"' in hero
    assert install_attribute in hero
    assert 'id="clara-install-video-link"' in hero
    assert 'data-i18n-aria-label="install.video.title"' in hero
    assert 'class="video-story"' not in hero
    assert 'id="presentation-video-link"' not in page
    assert page.index('id="download"') < functions_start
    assert page.count('class="video-story"') == 0
    assert "download-panel" not in page


def test_homepage_links_all_three_companions_in_every_locale() -> None:
    source = (ROOT / "modules" / "hosted_services" / "api.py").read_text(
        encoding="utf-8"
    )

    assert '"href": "/static/shared/reporting/index.html"' not in source
    assert "/static/shared/pro-charting/index.html" not in source
    assert source.count('"href": "/static/shared/clara/index.html"') == 5
    assert source.count('"href": "/static/shared/vera/index.html"') == 5
    assert source.count('"href": "/static/shared/lucia/index.html"') == 5
    assert '"href": "/static/shared/variance-analysis/index.html"' not in source
    assert '"href": "/static/shared/period-comparison/index.html"' not in source
    assert '"href": "/static/shared/mix-contribution-analysis/index.html"' not in source
    assert '"href": "/static/shared/scatter-bubble-analysis/index.html"' not in source
    assert '"href": "/static/shared/distribution-analysis/index.html"' not in source
    assert "pro_charting_plugin" not in source
    assert '"label": "Reporting"' not in source
    assert source.count('"label": "Clara"') == 5
    assert source.count('"label": "Vera"') == 5
    assert source.count('"label": "Lucia"') == 5


@pytest.mark.parametrize("lang", ("en", "it", "fr", "de", "es"))
def test_homepage_content_exposes_companions_without_reporting_or_pro_badges(
    lang: str,
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    content = pdp_api._get_landing_page_content(lang)
    groups = content["sections"][0]["groups"]

    assert [group["id"] for group in groups] == ["clara", "vera", "lucia"]
    assert [group["links"][0]["href"] for group in groups] == [
        "/static/shared/clara/index.html",
        "/static/shared/vera/index.html",
        "/static/shared/lucia/index.html",
    ]


@pytest.mark.parametrize(
    ("lang", "expected_leads"),
    (
        (
            "en",
            {
                "clara": (
                    "A specialist plugin for presentations and ongoing project work."
                ),
                "vera": (
                    "A specialist plugin for client files, accounting checks, "
                    "reconciliations and reporting."
                ),
                "lucia": (
                    "A specialist plugin for framing legal research and checking "
                    "sources, claims and reasoning."
                ),
            },
        ),
        (
            "it",
            {
                "clara": (
                    "Un plugin specialistico per creare presentazioni e dare "
                    "continuità al lavoro sui progetti."
                ),
                "vera": (
                    "Un plugin specialistico per lavorare su fascicoli, controlli "
                    "contabili, riconciliazioni e report."
                ),
                "lucia": (
                    "Un plugin specialistico per impostare la ricerca legale e "
                    "verificare fonti, affermazioni e ragionamento."
                ),
            },
        ),
        (
            "fr",
            {
                "clara": (
                    "Un plugin spécialisé pour créer des présentations et "
                    "poursuivre le travail sur les projets dans la durée."
                ),
                "vera": (
                    "Un plugin spécialisé pour les dossiers clients, les contrôles "
                    "comptables, les rapprochements et les rapports."
                ),
                "lucia": (
                    "Un plugin spécialisé pour cadrer la recherche juridique et "
                    "vérifier les sources, les affirmations et le raisonnement."
                ),
            },
        ),
        (
            "de",
            {
                "clara": (
                    "Ein spezialisiertes Plugin für Präsentationen und die "
                    "fortlaufende Arbeit an Projekten."
                ),
                "vera": (
                    "Ein spezialisiertes Plugin für Mandantendateien, "
                    "Buchungsprüfungen, Abstimmungen und Berichte."
                ),
                "lucia": (
                    "Ein spezialisiertes Plugin, das juristische Recherchen "
                    "strukturiert und Quellen, Aussagen und Argumentation prüft."
                ),
            },
        ),
        (
            "es",
            {
                "clara": (
                    "Un plugin especializado para presentaciones y trabajo continuo "
                    "en proyectos."
                ),
                "vera": (
                    "Un plugin especializado para expedientes de clientes, controles "
                    "contables, conciliaciones e informes."
                ),
                "lucia": (
                    "Un plugin especializado para estructurar la investigación "
                    "jurídica y comprobar fuentes, afirmaciones y razonamiento."
                ),
            },
        ),
    ),
)
def test_homepage_product_propositions_remain_stable_when_skills_change(
    lang: str,
    expected_leads: dict[str, str],
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    groups = pdp_api._get_landing_page_content(lang)["sections"][0]["groups"]

    # These are product propositions, not a live inventory of installed skills.
    assert {group["id"]: group["lead"] for group in groups} == expected_leads


@pytest.mark.parametrize("lang", ("en", "it", "fr", "de", "es"))
def test_product_pages_use_direct_product_explanations_for_hero_and_metadata(
    lang: str,
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    groups = pdp_api._get_landing_page_content(lang)["sections"][0]["groups"]

    direct_leads = {
        "en": {
            "clara": "Clara adds presentations, narrated research videos, interviews, transcription, documents, retail analysis, and data analysis to Codex.",
            "vera": "Vera adds client files, accounting checks, reconciliations, analysis, reporting, communication, and research to Codex.",
            "lucia": "Lucia adds legal research, source validation, matter opening, professional communication, and firm websites to Codex.",
        },
        "it": {
            "clara": "Clara aggiunge a Codex presentazioni, video di ricerca narrati, interviste, trascrizione, documenti, analisi retail e analisi dei dati.",
            "vera": "Vera aggiunge a Codex fascicoli cliente, controlli contabili, riconciliazioni, analisi, report, comunicazione e ricerca.",
            "lucia": "Lucia aggiunge a Codex ricerca legale, verifica delle fonti, apertura pratica, comunicazione professionale e sito dello studio.",
        },
        "fr": {
            "clara": "Clara ajoute à Codex les présentations, les vidéos de recherche narrées, les entretiens, la transcription, les documents, l'analyse retail et l'analyse de données.",
            "vera": "Vera ajoute à Codex les dossiers clients, les contrôles comptables, les rapprochements, l'analyse, les rapports, la communication et la recherche.",
            "lucia": "Lucia ajoute à Codex la recherche juridique, la vérification des sources, l'ouverture de dossier, la communication professionnelle et le site du cabinet.",
        },
        "de": {
            "clara": "Clara ergänzt Codex um Präsentationen, vertonte Forschungsvideos, Interviews, Transkription, Dokumente, Retail-Analysen und Datenanalysen.",
            "vera": "Vera ergänzt Codex um Mandantenakten, Buchungsprüfungen, Abstimmungen, Analysen, Berichte, Kommunikation und Recherche.",
            "lucia": "Lucia ergänzt Codex um juristische Recherche, Quellenprüfung, Aktenanlage, professionelle Kommunikation und Kanzlei-Websites.",
        },
        "es": {
            "clara": "Clara añade a Codex presentaciones, vídeos de investigación narrados, entrevistas, transcripción, documentos, análisis retail y análisis de datos.",
            "vera": "Vera añade a Codex expedientes de clientes, controles contables, conciliaciones, análisis, informes, comunicación e investigación.",
            "lucia": "Lucia añade a Codex investigación jurídica, comprobación de fuentes, apertura de asuntos, comunicación profesional y sitios web del despacho.",
        },
    }

    for group in groups:
        page = (ROOT / "static" / "shared" / group["id"] / "index.html").read_text(
            encoding="utf-8"
        )
        lead = direct_leads[lang][group["id"]]
        assert f'"hero.lead": "{lead}"' in page
        assert f'"meta.description": "{lead}"' in page


@pytest.mark.parametrize("product", ("clara", "vera", "lucia"))
def test_product_pages_hide_internal_implementation_language(product: str) -> None:
    page = (ROOT / "static" / "shared" / product / "index.html").read_text(
        encoding="utf-8"
    )

    for internal_phrase in (
        "optimized_prompt.md",
        "source_domains_comma.txt",
        "owner-only",
        "append-only",
        "schema rigoroso",
        "hash ricalcolabili",
        "Implementato e testato",
        "Da provare nel pilot",
        "Giudizio anti-slop",
        "Si approvano i byte finali",
        "canonical implementations",
        "implementazioni canoniche",
        "registered, reviewable specialist legal functions",
        "funzioni legali specialistiche registrate",
        "Creative Production può",
        "Design skills refine",
        "Le skill di design",
        "prompt-by-prompt documentation",
        "documentazione prompt per prompt",
    ):
        assert internal_phrase.casefold() not in page.casefold()


@pytest.mark.parametrize("product", ("clara", "vera", "lucia"))
def test_product_pages_name_all_three_products_in_shared_data_copy(
    product: str,
) -> None:
    page = (ROOT / "static" / "shared" / product / "index.html").read_text(
        encoding="utf-8"
    )

    for localized_names in (
        "Clara, Vera and Lucia",
        "Clara, Vera e Lucia",
        "Clara, Vera et Lucia",
        "Clara, Vera und Lucia",
        "Clara, Vera y Lucia",
    ):
        assert localized_names in page


@pytest.mark.parametrize(
    ("lang", "expected_audience"),
    (
        ("en", "For independent lawyers"),
        ("it", "Per avvocati indipendenti"),
        ("fr", "Pour les avocats indépendants"),
        ("de", "Für selbständige Anwälte"),
        ("es", "Para abogados independientes"),
    ),
)
def test_homepage_lucia_targets_independent_lawyers(
    lang: str,
    expected_audience: str,
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    groups = pdp_api._get_landing_page_content(lang)["sections"][0]["groups"]
    lucia = next(group for group in groups if group["id"] == "lucia")

    assert lucia["audience"] == expected_audience
    assert lucia["title"] == expected_audience
    assert lucia["links"][0]["href"] == "/static/shared/lucia/index.html"
    assert len(lucia["proof"]) == 3


@pytest.mark.parametrize(
    (
        "lang",
        "expected_group_titles",
        "expected_audiences",
        "removed_section_titles",
    ),
    (
        (
            "en",
            ("For consultants", "For accountants", "For independent lawyers"),
            ("For consultants", "For accountants", "For independent lawyers"),
            ("Attribute Analysis", "Deck Toolkit"),
        ),
        (
            "it",
            ("Per consulenti", "Per commercialisti", "Per avvocati indipendenti"),
            ("Per consulenti", "Per commercialisti", "Per avvocati indipendenti"),
            ("Analisi attributi", "Toolkit presentazioni"),
        ),
        (
            "fr",
            (
                "Pour les consultants",
                "Pour les experts-comptables",
                "Pour les avocats indépendants",
            ),
            (
                "Pour les consultants",
                "Pour les experts-comptables",
                "Pour les avocats indépendants",
            ),
            ("Analyse des attributs", "Toolkit deck"),
        ),
        (
            "de",
            (
                "Für Beraterinnen und Berater",
                "Für Steuerberaterinnen und Steuerberater",
                "Für selbständige Anwälte",
            ),
            (
                "Für Beraterinnen und Berater",
                "Für Steuerberaterinnen und Steuerberater",
                "Für selbständige Anwälte",
            ),
            ("Attributanalyse", "Deck-Toolkit"),
        ),
        (
            "es",
            (
                "Para consultores",
                "Para profesionales contables",
                "Para abogados independientes",
            ),
            (
                "Para consultores",
                "Para profesionales contables",
                "Para abogados independientes",
            ),
            ("Análisis de atributos", "Herramientas de presentación"),
        ),
    ),
)
def test_homepage_only_exposes_professional_role_groups(
    lang: str,
    expected_group_titles: tuple[str, str, str],
    expected_audiences: tuple[str, str, str],
    removed_section_titles: tuple[str, str],
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    content = pdp_api._get_landing_page_content(lang)
    sections = content["sections"]
    serialized_sections = json.dumps(sections, ensure_ascii=False)

    assert len(sections) == 1
    assert sections[0]["preserve_order"] is True
    groups = sections[0]["groups"]
    assert tuple(group["title"] for group in groups) == expected_group_titles
    assert tuple(group["audience"] for group in groups) == expected_audiences
    assert tuple(group["links"][0]["href"] for group in groups) == (
        "/static/shared/clara/index.html",
        "/static/shared/vera/index.html",
        "/static/shared/lucia/index.html",
    )
    assert removed_section_titles[0] not in serialized_sections
    assert removed_section_titles[1] not in serialized_sections
    assert "/review/reports/page" not in serialized_sections
    assert "/review/brand-reports/page" not in serialized_sections
    assert "/review/product-hypotheses/page" not in serialized_sections
    assert "/slides/page" not in serialized_sections
    assert "/presentations/page" not in serialized_sections


def test_homepage_plugin_links_are_ordered_by_group_and_locale() -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    for lang in ("en", "it", "fr", "de", "es"):
        groups = pdp_api._get_landing_page_content(lang)["sections"][0]["groups"]
        assert [group["links"][0]["label"] for group in groups] == [
            "Clara",
            "Vera",
            "Lucia",
        ]


def test_vera_module_links_preserve_language_without_changing_market() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert 'href="../new-client/index.html#journey" data-module-link' in page
    assert 'url.searchParams.set("lang", lang)' in page
    assert "link.dataset.nativeLanguage" in page
    assert ": withLanguage(link.dataset.baseHref, lang)" in page
    assert 'es: "../new-client/index.html#file-preparation"' in page
    assert "const jurisdictionsByPage" not in page
    assert "item.hidden = item.dataset.jurisdictionItem !== lang" in page
    assert "window.location.replace" not in page


@pytest.mark.parametrize(
    ("page_name", "plugin_id", "install_marker"),
    (
        (
            "clara",
            "plugins_6a57b17fb5848191be710192d93fe03a",
            "data-clara-install-link",
        ),
        (
            "vera",
            "plugins_6a57ac5ce65c8191ae7bd0a51160eb7d",
            "data-vera-install-link",
        ),
    ),
)
def test_companion_install_flow_routes_login_to_same_listing(
    page_name: str, plugin_id: str, install_marker: str
) -> None:
    page = (ROOT / "static" / "shared" / page_name / "index.html").read_text(
        encoding="utf-8"
    )
    listing_url = f"https://chatgpt.com/plugins/{plugin_id}"
    login_url = f"https://chatgpt.com/auth/login?next=%2Fplugins%2F{plugin_id}"

    expected_count = 1
    assert page.count(login_url) == expected_count
    assert listing_url not in page
    assert page.count(install_marker) == expected_count
    assert 'data-i18n="hero.install"' not in page
    assert 'data-i18n="install.button"' in page
    assert 'data-i18n="install.open"' not in page
    assert 'data-i18n="install.signed_out"' not in page


@pytest.mark.parametrize(
    "localized_guidance",
    (
        "Install Clara for ChatGPT Work and Codex, or download the package for Claude Cowork.",
        "Installa Clara per ChatGPT Work e Codex oppure scarica il pacchetto per Claude Cowork.",
        "Installez Clara pour ChatGPT Work et Codex ou téléchargez le paquet pour Claude Cowork.",
        "Installieren Sie Clara für ChatGPT Work und Codex oder laden Sie das Paket für Claude Cowork herunter.",
        "Instala Clara para ChatGPT Work y Codex o descarga el paquete para Claude Cowork.",
    ),
)
def test_clara_install_flow_localizes_platform_choices(
    localized_guidance: str,
) -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )

    assert localized_guidance in page


def test_homepage_is_one_semantic_story_with_all_three_plugins() -> None:
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")

    narrative_markers = (
        'class="landing-opening"',
        'class="landing-harness"',
        'class="landing-open-source"',
        'class="landing-free"',
        'class="landing-security"',
        'class="landing-compliance"',
        'class="landing-bridge"',
        'class="landing-products"',
    )
    narrative_positions = [template.index(marker) for marker in narrative_markers]

    assert narrative_positions == sorted(narrative_positions)
    assert template.count("<h1") == 1
    assert 'id="main-content"' in template
    assert '<footer class="landing-footer">' in template
    assert template.index('<footer class="landing-footer">') > template.index("</main>")
    assert "{{ copy.operator_disclosure }}" in template
    assert 'href="#{{ group.id }}"' in template
    assert 'id="{{ group.id }}"' in template
    assert "{{ group.lead }}" in template
    assert "{{ group.description }}" in template
    assert "group.responsibility" not in template
    assert "landing-grid--single" not in template
    assert "body.landing-body.landing-home" in css
    assert ".landing-home .landing-harness" in css
    assert ".landing-home .landing-open-source" in css
    design_heading_selector = (
        ".landing-home .landing-open-source h2,\n"
        ".landing-home .landing-free h2,\n"
        ".landing-home .landing-security h2,\n"
        ".landing-home .landing-compliance h2,\n"
        ".landing-home .landing-bridge h2 {"
    )
    design_heading_css = css.split(design_heading_selector, maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    assert "color: var(--landing-ink);" in design_heading_css
    principle_body_selector = (
        ".landing-home .landing-open-source__body > p,\n"
        ".landing-home .landing-free__body > p {"
    )
    principle_body_css = css.split(principle_body_selector, maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    assert "color: var(--landing-muted);" in principle_body_css
    assert "font-size: clamp(1.1rem, 1.65vw, 1.35rem);" in principle_body_css
    assert "line-height: 1.62;" in principle_body_css
    assert "letter-spacing: -0.02em;" in principle_body_css
    assert "harness.consequence" not in template
    assert "landing-harness__consequence" not in css
    assert ".landing-home .landing-bridge" in css
    assert "harness.eyebrow" not in template
    assert "bridge.eyebrow" not in template
    assert ".landing-home .landing-product" in css
    footer_css = css.split(".landing-home .landing-footer p {", maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    assert "color: var(--landing-muted);" in footer_css
    assert "font-size: 0.75rem;" in footer_css
    assert "@media (prefers-reduced-motion: reduce)" in css


@pytest.mark.parametrize(
    ("lang", "expected_title", "inspect_fragment"),
    (
        ("en", "Open by design.", "inspect"),
        ("it", "Aperti per scelta.", "esaminare"),
        ("fr", "Ouverts par conception.", "examiner"),
        ("de", "Offen konzipiert.", "prüfen"),
        ("es", "Abiertos por diseño.", "examinar"),
    ),
)
def test_homepage_makes_open_source_explicit(
    lang: str,
    expected_title: str,
    inspect_fragment: str,
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    open_source = pdp_api._get_landing_page_content(lang)["open_source"]

    assert open_source["title"] == expected_title
    assert inspect_fragment in open_source["description"].casefold()
    normalized_description = open_source["description"].casefold().replace("-", " ")
    assert "open source" in normalized_description
    assert open_source["links"][0]["href"].startswith("https://github.com/")
    assert open_source["links"][1]["href"].endswith("/LICENSE")


@pytest.mark.parametrize(
    ("lang", "expected_title", "expected_description"),
    (
        (
            "en",
            "Free by design.",
            "Clara, Vera and Lucia are free to install and use. We welcome contributions "
            "to their development. We charge for consulting, implementation, "
            "and hosted services.",
        ),
        (
            "it",
            "Gratuiti per scelta.",
            "Clara, Vera e Lucia si possono installare e usare gratuitamente. Accogliamo "
            "volentieri contributi al loro sviluppo. Offriamo a pagamento "
            "consulenza, implementazione e servizi hosted.",
        ),
        (
            "fr",
            "Gratuits par conception.",
            "Clara, Vera et Lucia sont gratuites à installer et à utiliser. Nous accueillons "
            "volontiers les contributions à leur développement. Nous facturons nos "
            "prestations de conseil et de mise en œuvre, ainsi que nos services "
            "hébergés.",
        ),
        (
            "de",
            "Kostenlos konzipiert.",
            "Clara, Vera und Lucia können kostenlos installiert und genutzt werden. Wir "
            "freuen uns über Beiträge zu ihrer Weiterentwicklung. Wir stellen "
            "Beratungs- und Implementierungsleistungen sowie gehostete Services "
            "in Rechnung.",
        ),
        (
            "es",
            "Gratuitos por diseño.",
            "Clara, Vera y Lucia se pueden instalar y usar gratuitamente. Agradecemos las "
            "contribuciones a su desarrollo. Cobramos por la consultoría, la "
            "implementación y los servicios alojados.",
        ),
    ),
)
def test_homepage_makes_free_business_model_explicit(
    lang: str, expected_title: str, expected_description: str
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    free = pdp_api._get_landing_page_content(lang)["free"]

    assert free == {
        "id": "free",
        "title": expected_title,
        "description": expected_description,
    }


@pytest.mark.parametrize("lang", ("en", "it", "fr", "de", "es"))
def test_homepage_sections_omit_redundant_eyebrows(lang: str) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    content = pdp_api._get_landing_page_content(lang)

    assert "eyebrow" not in content["harness"]
    assert "eyebrow" not in content["bridge"]


def test_homepage_does_not_repeat_audience_labels_below_product_icons() -> None:
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    identity_markup = template.split(
        '<div class="landing-product__identity">', maxsplit=1
    )[1].split("</div>", maxsplit=1)[0]

    assert "group.audience" not in identity_markup
    assert '<p class="landing-product__role">{{ group.title }}</p>' in template


def test_homepage_localizes_navigation_and_language_links() -> None:
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    assert "copy.primary_navigation_label" in template
    assert "copy.language_selector_label" in template
    assert "copy.sign_out_button" not in template
    assert 'aria-label="{{ language_names[code] }}"' in template
    assert 'lang="{{ code }}"' in template
    assert 'hreflang="{{ code }}"' in template
    assert "data.detail" not in template


def test_homepage_tablet_header_reflows_before_mobile_breakpoint() -> None:
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")

    tablet_start = css.index("@media (max-width: 980px)")
    mobile_start = css.index("@media (max-width: 700px)", tablet_start)
    tablet_css = css[tablet_start:mobile_start]

    assert ".landing-home .landing-header" in tablet_css
    assert "grid-template-columns: minmax(0, 1fr)" in tablet_css
    assert ".landing-home .landing-controls" in tablet_css
    assert "justify-content: space-between" in tablet_css


@pytest.mark.parametrize("lang", ("en", "it", "fr", "de", "es"))
@pytest.mark.parametrize(
    ("group_index", "expected_group_id"),
    ((0, "clara"), (1, "vera"), (2, "lucia")),
)
def test_homepage_content_explains_specialist_method_and_each_plugin(
    lang: str,
    group_index: int,
    expected_group_id: str,
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    content = pdp_api._get_landing_page_content(lang)
    groups = content["sections"][0]["groups"]
    group = groups[group_index]

    assert content["hero"]["headline"]
    assert content["hero"]["subheadline"]
    assert content["hero"]["plugins_label"]
    assert "primary_cta" not in content["hero"]
    assert "Codex" not in content["hero"]["headline"]
    assert "ChatGPT Work" in content["hero"]["subheadline"]
    assert "Codex" in content["hero"]["subheadline"]
    assert "Claude Cowork" in content["hero"]["subheadline"]
    assert content["harness"]["id"] == "method"
    assert len(content["harness"]["layers"]) == 3
    assert "consequence" not in content["harness"]
    assert "consequence_label" not in content["harness"]
    assert content["bridge"]["id"] == "plugins"
    assert [item["id"] for item in groups] == ["clara", "vera", "lucia"]
    assert group["id"] == expected_group_id
    assert group["audience"]
    assert group["lead"]
    assert group["description"]
    assert "responsibility" not in group
    assert group["proof"]
    assert group["cta_label"]
    assert group["icon"].endswith(".svg")


@pytest.mark.parametrize(
    ("lang", "expected_opening", "expected_research", "rejected_fragment"),
    (
        (
            "en",
            "Vera works directly on the firm's files.",
            "tax and regulatory research",
            "ordinary language",
        ),
        (
            "it",
            "Vera lavora direttamente sui file dello studio.",
            "ricerche fiscali e normative",
            "parole normali",
        ),
        (
            "fr",
            "Vera travaille directement sur les fichiers du cabinet.",
            "recherches fiscales et réglementaires",
            "active le bon module",
        ),
        (
            "de",
            "Vera arbeitet direkt mit den Kanzleidateien.",
            "steuerliche und regulatorische Recherchen",
            "normalen Worten",
        ),
        (
            "es",
            "Vera trabaja directamente con los archivos del despacho.",
            "investigaciones fiscales y regulatorias",
            "lenguaje ordinario",
        ),
    ),
)
def test_homepage_vera_describes_the_task_without_literal_or_internal_language(
    lang: str,
    expected_opening: str,
    expected_research: str,
    rejected_fragment: str,
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    groups = pdp_api._get_landing_page_content(lang)["sections"][0]["groups"]
    description = next(group for group in groups if group["id"] == "vera")[
        "description"
    ]

    assert description.startswith(expected_opening)
    assert expected_research in description
    assert rejected_fragment not in description


@pytest.mark.parametrize(
    (
        "lang",
        "expected_eyebrow",
        "expected_headline",
        "expected_control_term",
        "rejected_fragment",
        "rejected_consequence_fragment",
    ),
    (
        (
            "en",
            "Plugins for professional work",
            "AI has the power. The method provides the control.",
            "control",
            "professional decides",
            "hallucinations",
        ),
        (
            "it",
            "Plugin per il lavoro professionale",
            "La potenza viene dall'AI. Il controllo, dal metodo.",
            "controllo",
            "professionista decide",
            "allucinazioni",
        ),
        (
            "fr",
            "Plugins pour les professionnels",
            "L'IA apporte la puissance. La méthode apporte le contrôle.",
            "contrôle",
            "professionnel décide",
            "hallucinations",
        ),
        (
            "de",
            "Plugins für professionelle Arbeit",
            "KI liefert die Leistung. Die Methode sorgt für Kontrolle.",
            "Kontrolle",
            "Fachperson entscheidet",
            "Halluzinationen",
        ),
        (
            "es",
            "Plugins para el trabajo profesional",
            "La IA aporta la potencia. El método aporta el control.",
            "control",
            "el profesional decide",
            "alucinaciones",
        ),
    ),
)
def test_homepage_positions_control_as_the_specialist_method(
    lang: str,
    expected_eyebrow: str,
    expected_headline: str,
    expected_control_term: str,
    rejected_fragment: str,
    rejected_consequence_fragment: str,
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    content = pdp_api._get_landing_page_content(lang)
    serialized_content = json.dumps(content, ensure_ascii=False)

    assert content["hero"]["eyebrow"] == expected_eyebrow
    assert "Mparanza ·" not in content["hero"]["eyebrow"]
    assert content["hero"]["headline"] == expected_headline
    assert expected_control_term.casefold() in content["hero"]["headline"].casefold()
    assert content["harness"]["id"] == "method"
    assert content["bridge"]["id"] == "plugins"
    assert rejected_fragment not in serialized_content
    assert rejected_consequence_fragment not in serialized_content
    assert '"responsibility"' not in serialized_content


@pytest.mark.parametrize(
    ("lang", "expected_description", "rejected_fragment"),
    (
        (
            "en",
            "Mparanza is Clara, Vera and Lucia: three plugins that bring specialist "
            "methods to three different professions.",
            "first two",
        ),
        (
            "it",
            "Mparanza è Clara, Vera e Lucia: tre plugin che incorporano metodi "
            "specialistici per tre professioni diverse.",
            "primi due",
        ),
        (
            "fr",
            "Mparanza, c'est Clara, Vera et Lucia : trois plugins qui intègrent des "
            "méthodes spécialisées pour trois métiers différents.",
            "deux premiers",
        ),
        (
            "de",
            "Mparanza, das sind Clara, Vera und Lucia: drei Plugins mit fachlichen "
            "Methoden für drei unterschiedliche Berufsgruppen.",
            "ersten beiden",
        ),
        (
            "es",
            "Mparanza es Clara, Vera y Lucia: tres plugins que incorporan métodos "
            "especializados para tres profesiones distintas.",
            "los dos primeros",
        ),
    ),
)
def test_homepage_presents_clara_vera_and_lucia_as_the_complete_set(
    lang: str,
    expected_description: str,
    rejected_fragment: str,
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    description = pdp_api._get_landing_page_content(lang)["bridge"]["description"]

    assert description == expected_description
    assert rejected_fragment not in description


@pytest.mark.parametrize(
    ("lang", "expected_blurb", "rejected_fragment"),
    (
        (
            "en",
            "Checks, review points, and expected outputs make the work reviewable.",
            "Codex connects",
        ),
        (
            "it",
            "Verifiche, punti di revisione e risultati attesi rendono il lavoro rivedibile.",
            "Codex collega",
        ),
        (
            "fr",
            "Les contrôles, les points de revue et les livrables attendus rendent le travail révisable.",
            "Codex relie",
        ),
        (
            "de",
            "Prüfungen, Prüfpunkte und erwartete Ergebnisse machen die Arbeit "
            "nachvollziehbar.",
            "Codex verbindet",
        ),
        (
            "es",
            "Los controles, los puntos de revisión y los resultados esperados hacen "
            "que el trabajo sea revisable.",
            "Codex conecta",
        ),
    ),
)
def test_homepage_attributes_control_to_the_specialist_method(
    lang: str,
    expected_blurb: str,
    rejected_fragment: str,
) -> None:
    _restore_application_import_path()

    from modules.hosted_services import api as pdp_api

    control_blurb = pdp_api._get_landing_page_content(lang)["harness"]["layers"][2][
        "blurb"
    ]

    assert control_blurb == expected_blurb
    assert rejected_fragment not in control_blurb


def test_homepage_app_css_link_is_cache_busted() -> None:
    base_template = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    source = (ROOT / "modules" / "hosted_services" / "api.py").read_text(
        encoding="utf-8"
    )

    assert "/static/css/app.css?v={{ app_css_asset_version" in base_template
    assert (
        '"app_css_asset_version": _static_asset_version("static/css/app.css")' in source
    )


def test_homepage_thesis_image_is_valid_and_cache_busted() -> None:
    from PIL import Image

    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "modules" / "hosted_services" / "api.py").read_text(
        encoding="utf-8"
    )
    image_path = ROOT / "static" / "icons" / "power_control.png"

    assert image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(image_path) as image:
        image.verify()

    assert "/static/icons/power_control.png?v={{ thesis_image_asset_version" in template
    assert '"thesis_image_asset_version": _static_asset_version(' in source
