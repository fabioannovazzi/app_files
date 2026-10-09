#!/usr/bin/env python3
"""Build the existing private pilot from canonical source with fictional runs.

This development harness deliberately uses workflow test fixtures. Its outputs
are mechanism evidence only and must never enter the customer-validation register.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from build_codex_plugin_zip import (
    load_vendor_module_config,
    shared_vendor_module_entries,
)
from build_vera_workspace_pilot import build_pilot, seed_demo

__all__ = ["build_rollout_pilot"]

ROOT = Path(__file__).resolve().parents[1]


def seed_reviewed_source_group_case(destination: Path) -> dict:
    """Register entirely fictional sources; never claim actual extraction review."""
    from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger

    base = destination / "fictional-reviewed-source-group"
    base.mkdir()
    fixture_path = (
        ROOT / "plugins/passive-invoice-audit/tests/test_passive_invoice_audit.py"
    )
    spec = importlib.util.spec_from_file_location(
        "private_geneva_fixture", fixture_path
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    canonical = fixture._reviewed_geneva_invoice(base)
    customer = base / "Originali CH-GE - dati fittizi"
    customer.mkdir()
    ledger = _load_customer_ledger()
    identity = "client_" + "e" * 24
    ledger.create_client_manifest(customer, identity)
    engagement = ledger.create_engagement(
        customer, identity, "Gruppo CH-GE - revisione dell'estrazione fittizia"
    )
    inputs = [
        ledger.import_document(
            customer, identity, engagement["engagement_id"], path, "source"
        )["receipt"]["input_id"]
        for path in (canonical, base / "invoice.txt")
    ]
    version = json.loads(
        (
            ROOT / "plugins/client-file-preparation/.codex-plugin/plugin.json"
        ).read_bytes()
    )["version"]
    prepared = ledger.prepare_run(
        customer,
        identity,
        engagement["engagement_id"],
        "client-file-preparation",
        version,
        input_ids=inputs,
        label="Originali CH-GE - dati e revisione fittizi",
        purpose="Prova tecnica con estrazione e revisione fittizie; nessuna esecuzione del modello o approvazione professionale.",
        idempotency_key="private-reviewed-source-group",
    )
    running = ledger.start_run(
        customer, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    binding = {
        "work_ref": "source-group-fictional",
        "client_root": str(customer),
        "client_id": identity,
        "engagement_id": engagement["engagement_id"],
        "run_id": running["run"]["run_id"],
        "workflow_id": "client-file-preparation",
    }
    (destination / "source-group-native-acceptance-case.json").write_text(
        json.dumps(
            {
                "scope": "Fictional sources and extraction review; no model/provider or professional acceptance.",
                "binding": binding,
                "inputs": [
                    {"id": row["binding_id"], "name": Path(row["path"]).name}
                    for row in running["context"]["input_bindings"]
                ],
                "grouping_attribution": "Absent. Supply actual test attribution and basis, explicit mappings and renewed confirmation in the panel.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return binding


def retained_private_profiles(plugin: Path) -> tuple[dict, dict, dict | None]:
    """Read a prior private pilot's exact scopes without migrating business files."""
    manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_bytes())
    if manifest["name"] != "vera-workspace-pilot":
        raise ValueError("Retain scopes only from the existing private pilot identity")
    servers = json.loads((plugin / ".mcp.json").read_bytes())["mcpServers"]
    environment = servers["veraNativeWorkspace"]["env"]
    config = json.loads(Path(environment["VERA_WORKSPACE_BINDINGS"]).read_bytes())
    if (
        config["actor_id"] != environment["VERA_WORKSPACE_ACTOR_ID"]
        or config["tenant_id"] != environment["VERA_WORKSPACE_TENANT_ID"]
        or len({row["work_ref"] for row in config["bindings"]})
        != len(config["bindings"])
    ):
        raise ValueError("Prior private pilot scopes are inconsistent")
    return environment, config, servers.get("veraOwnedWorkspace")


def seed_passive_review_case(destination: Path) -> dict:
    """Retain a declared fictional checkpoint, without a model or human approval."""
    import pytest

    from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
    from tests.plugins.test_vera_native_passive_audit import audit_workspace

    ledger = _load_customer_ledger()
    base = destination / "fictional-passive-review"
    base.mkdir()
    customer = base / "Fatture passive - checkpoint fittizio"
    customer.mkdir()
    identity = "client_" + "f" * 24
    ledger.create_client_manifest(customer, identity)
    engagement = ledger.create_engagement(
        customer, identity, "Prova UI - risposta semantica fittizia"
    )

    def create(workflow: str, *, input_files: dict[str, str]) -> dict:
        staging = base / "originals"
        staging.mkdir()
        inputs = []
        for name, content in input_files.items():
            source = staging / name
            source.write_text(content, encoding="utf-8")
            inputs.append(
                ledger.import_document(
                    customer, identity, engagement["engagement_id"], source, "source"
                )["receipt"]["input_id"]
            )
        component = json.loads(
            (ROOT / "plugins" / workflow / ".codex-plugin/plugin.json").read_bytes()
        )
        prepared = ledger.prepare_run(
            customer,
            identity,
            engagement["engagement_id"],
            workflow,
            component["version"],
            input_ids=inputs,
            label="Fatture passive - checkpoint fittizio",
            purpose="Prova meccanica del pannello con risposta semantica fittizia; nessuna esecuzione del modello o approvazione professionale.",
            idempotency_key="private-passive-review-case",
        )
        running = ledger.start_run(
            customer, engagement["engagement_id"], prepared["run"]["run_id"]
        )
        context = running["context"]
        return {
            "client_root": customer,
            "client_id": identity,
            "engagement_id": engagement["engagement_id"],
            "run_id": running["run"]["run_id"],
            "context": context,
            "output_dir": Path(context["output_dir"]),
        }

    with pytest.MonkeyPatch.context() as patch:
        work = audit_workspace.__wrapped__(
            base, patch, SimpleNamespace(param="ordinary"), create
        )
    binding = {
        "work_ref": "passive-fictional-checkpoint",
        "client_root": str(customer),
        **{key: work.work[key] for key in ("client_id", "engagement_id", "run_id")},
        "workflow_id": "passive-invoice-audit",
    }
    (destination / "passive-native-acceptance-case.json").write_text(
        json.dumps(
            {
                "scope": "Fictional UI mechanism test; no model/provider or professional acceptance.",
                "binding": binding,
                "recipe": work.recipe,
                "human_labels": "Absent. The native reviewer must supply explicit attribution, labels and renewed confirmation.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return binding


def owned_archive_environment(
    destination: Path, environment: dict[str, str], version: str
) -> dict[str, str]:
    """Seed an additional ordinary-archive profile without changing the original runs."""
    from tests._plugin_cli import workflow_cli
    from tests.plugins.test_treasury_delivery import SCRIPTS, archived_case
    from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger

    ledger = _load_customer_ledger()
    archive_root = destination / "fictional-archive"
    customer = archive_root / "Banca iniziale - dati fittizi"
    customer.mkdir()
    identity = "client_" + "c" * 24
    ledger.create_client_manifest(customer, identity)
    engagement = ledger.create_engagement(
        customer, identity, "Giornale e banca - prova iniziale"
    )
    staging = destination / "fictional-owned-inputs"
    staging.mkdir()
    selected = []
    for side in ("bank", "journal"):
        source = staging / (side + ".csv")
        source.write_text(
            "Date,Description,Amount,Reference,Currency,Entity_ref\n"
            "2025-01-10,Trasferimento fittizio "
            + side
            + ",-80,DEMO-001,CHF,entity.owned.demo\n"
            "2025-01-15,Pagamento fittizio "
            + side
            + ",-120,DEMO-002,CHF,entity.owned.demo\n",
            encoding="utf-8",
        )
        selected.append(
            ledger.import_document(
                customer, identity, engagement["engagement_id"], source, "source"
            )["receipt"]["input_id"]
        )
    component = json.loads(
        (
            ROOT / "plugins/journal-bank-reconciliation/.codex-plugin/plugin.json"
        ).read_bytes()
    )
    prepared = ledger.prepare_run(
        customer,
        identity,
        engagement["engagement_id"],
        "journal-bank-reconciliation",
        component["version"],
        input_ids=selected,
        label="Giornale e banca - dati fittizi",
        purpose="Verificare il percorso nativo dalla scelta delle fonti ai risultati da rivedere.",
        idempotency_key="private-owned-bank",
    )
    ledger.start_run(customer, engagement["engagement_id"], prepared["run"]["run_id"])

    # Its client ID differs from Aurora and the new initial bank client. Stage and
    # prepare at the final location; do not move Treasury's absolute source paths.
    treasury = archived_case(archive_root)
    manifest = next(
        Path(row["path"])
        for row in treasury["context"]["input_bindings"]
        if row["path"].endswith(".json")
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "run_treasury.py"),
            "prepare",
            "--client-engagement",
            str(treasury["context_path"]),
            "--manifest",
            str(manifest),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    owned = {
        key: value
        for key, value in environment.items()
        if key != "VERA_WORKSPACE_BINDINGS"
    }
    owned.update(
        VERA_STUDIO_ARCHIVE_SESSION_ID="vera-private-owned-" + version,
        VERA_STUDIO_ARCHIVE_STATE_DIR=str(destination / "private-owned-archive"),
    )
    child_environment = dict(os.environ)
    child_environment.update(owned)
    subprocess.run(
        [
            *workflow_cli(ROOT / "plugins/studio-archive/scripts/studio_archive.py"),
            "configure",
            "--archive-root",
            str(archive_root),
        ],
        env=child_environment,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        [
            *workflow_cli(ROOT / "plugins/studio-archive/scripts/studio_archive.py"),
            "recover-ledger",
        ],
        env=child_environment,
        capture_output=True,
        text=True,
        check=True,
    )
    (destination / "owned-environment.json").write_text(
        json.dumps(owned, indent=2), encoding="utf-8"
    )
    return owned


def build_rollout_pilot(
    destination: Path,
    *,
    version: str = "0.0.9",
    owned_archive: bool = False,
    passive_review_case: bool = False,
    reviewed_source_group_case: bool = False,
    retain_private_pilot: Path | None = None,
) -> Path:
    """Update the existing private identity; never create a public listing."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tests.plugins import test_archive_organization_plugin as archive
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        _prepare_sealed_mcp_review_run,
    )
    from tests.plugins.test_treasury_delivery import SCRIPTS, archived_case

    if retain_private_pilot is not None and passive_review_case:
        raise ValueError("Retain existing cases or seed a new passive case explicitly")
    retained = (
        retained_private_profiles(retain_private_pilot)
        if retain_private_pilot is not None
        else None
    )
    plugin = build_pilot(destination, version=version)
    environment = json.loads((destination / "environment.json").read_bytes())
    components = json.loads((ROOT / "plugins/vera/components.json").read_bytes())
    for component in components["plugins"]:
        target = plugin / "modules" / component
        if not target.exists():
            shutil.copytree(
                ROOT / "plugins" / component,
                target,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
            )
    shutil.copytree(
        ROOT / "plugins/_shared/vendor/modules",
        plugin / "vendor/modules",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )
    shutil.copytree(
        ROOT / "plugins/_shared/vendor/modules",
        plugin / "modules/_shared/vendor/modules",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )
    # Use the public packager's declared overlays, including the canonical
    # Archive disclosure helper; repository-relative fallbacks are unavailable.
    vendors = load_vendor_module_config()
    for component in ("vera", *components["plugins"]):
        vendor = (
            plugin / "vendor/modules"
            if component == "vera"
            else plugin / "modules" / component / "vendor/modules"
        )
        for name, source in shared_vendor_module_entries(
            vendors.get(component)
        ).items():
            target = vendor / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (plugin / "components.json").write_text(json.dumps(components))
    (plugin / "scripts").mkdir()
    # Retain the maintained native module closure. A second hand-maintained
    # list omitted new adapters while still copying their MCP declarations.
    for source in sorted((ROOT / "plugins/vera/scripts").glob("native_*")):
        if source.is_file() and source.suffix in {".py", ".cjs"}:
            shutil.copy2(source, plugin / "scripts" / source.name)
    shutil.copy2(
        ROOT / "plugins/vera/scripts/model_data_report.py",
        plugin / "scripts/model_data_report.py",
    )
    shutil.copy2(
        ROOT / "scripts/serve_review_workbench.py",
        plugin / "scripts/serve_review_workbench.py",
    )
    shutil.copytree(ROOT / "plugins/vera/mcp", plugin / "mcp")
    shutil.copytree(ROOT / "plugins/vera/ui", plugin / "ui")

    legacy_path = Path(environment["VERA_XBRL_WORKSPACE_BINDINGS"])
    legacy = json.loads(legacy_path.read_bytes())
    boreale = seed_demo(
        destination / "fictional-boreale",
        scenario="boreale",
        storage_root=Path(environment["VERA_XBRL_STORAGE_ROOT"]),
    )
    legacy["bindings"].extend(
        json.loads(Path(boreale["VERA_XBRL_WORKSPACE_BINDINGS"]).read_bytes())[
            "bindings"
        ]
    )
    legacy_path.write_text(json.dumps(legacy))
    bindings = [
        {
            **row,
            "work_ref": row["case_id"],
            "workflow_id": "bilancio-xbrl-it",
            "component": "bilancio-xbrl-it",
        }
        for row in legacy["bindings"]
    ]

    bank_root = destination / "fictional-bank"
    bank_root.mkdir()
    bank_output, _, _, _, _ = _prepare_sealed_mcp_review_run(
        bank_root, language="it", portable=True
    )
    bank_context = json.loads((bank_output.parent / "context.json").read_bytes())
    bindings.append(
        {
            "work_ref": "bank-fictional",
            "client_root": str(bank_root / "Managed Customer"),
            **{
                key: bank_context[key]
                for key in ("client_id", "engagement_id", "run_id")
            },
            "workflow_id": "journal-bank-reconciliation",
        }
    )

    treasury_root = destination / "fictional-treasury"
    treasury_root.mkdir()
    treasury = archived_case(treasury_root)
    manifest = next(
        Path(row["path"])
        for row in treasury["context"]["input_bindings"]
        if row["path"].endswith(".json")
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "run_treasury.py"),
            "prepare",
            "--client-engagement",
            str(treasury["context_path"]),
            "--manifest",
            str(manifest),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    bindings.append(
        {
            "work_ref": "treasury-fictional",
            "client_root": str(treasury["client"]),
            **{
                key: treasury["context"][key]
                for key in ("client_id", "engagement_id", "run_id")
            },
            "workflow_id": "treasury-forecast",
        }
    )

    archive_root = destination / "fictional-organization"
    archive_root.mkdir()
    archive_context_path, archive_snapshot, _ = archive.scenario._prepared_run(
        archive_root
    )
    archive.core.build_review_package(
        archive_context_path,
        archive.scenario._proposals(archive_root, archive_snapshot),
        language="it",
    )
    archive_context = json.loads(archive_context_path.read_bytes())
    bindings.append(
        {
            "work_ref": "archive-fictional",
            "client_root": str(archive_context_path.parents[5]),
            **{
                key: archive_context[key]
                for key in ("client_id", "engagement_id", "run_id")
            },
            "workflow_id": "archive-organization",
        }
    )

    if retained is not None:
        environment, prior_config, _ = retained
        bindings = list(prior_config["bindings"])
    if passive_review_case:
        bindings.append(seed_passive_review_case(destination))
    if reviewed_source_group_case:
        binding = seed_reviewed_source_group_case(destination)
        if any(row["work_ref"] == binding["work_ref"] for row in bindings):
            raise ValueError(
                "Prior source-group case already exists; retain it unchanged"
            )
        bindings.append(binding)
    config = destination / "fictional-workspace-bindings.json"
    config.write_text(
        json.dumps(
            {
                "tenant_id": prior_config["tenant_id"] if retained else "demo_studio",
                "actor_id": prior_config["actor_id"] if retained else "demo_reviewer",
                "bindings": bindings,
            },
            indent=2,
        )
    )
    environment.update(
        VERA_WORKSPACE_BINDINGS=str(config),
        VERA_WORKSPACE_TENANT_ID=(
            prior_config["tenant_id"] if retained else "demo_studio"
        ),
        VERA_WORKSPACE_ACTOR_ID=(
            prior_config["actor_id"] if retained else "demo_reviewer"
        ),
        VERA_WORKSPACE_ROLES=(
            environment["VERA_WORKSPACE_ROLES"] if retained else "REVIEWER"
        ),
        VERA_WORKSPACE_PYTHON=sys.executable,
    )
    mcp_path = plugin / ".mcp.json"
    mcp = json.loads(mcp_path.read_bytes())
    node = mcp["mcpServers"]["veraWorkspace"]["command"]
    mcp["mcpServers"]["veraWorkspace"]["env"] = environment
    mcp["mcpServers"]["veraNativeWorkspace"] = {
        "title": "Lavori dello studio",
        "command": node,
        "cwd": ".",
        "args": ["./mcp/workspace.cjs"],
        "env": environment,
    }
    if owned_archive or (retained and retained[2] is not None):
        mcp["mcpServers"]["veraOwnedWorkspace"] = {
            "title": "Archivio ordinario · prova privata",
            "command": node,
            "cwd": ".",
            "args": ["./mcp/workspace.cjs"],
            "env": (
                retained[2]["env"]
                if retained and retained[2] is not None
                else owned_archive_environment(destination, environment, version)
            ),
        }
    mcp_path.write_text(json.dumps(mcp, indent=2))
    (destination / "environment.json").write_text(json.dumps(environment, indent=2))
    return plugin


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--version", default="0.0.9")
    parser.add_argument("--owned-archive", action="store_true")
    parser.add_argument("--passive-review-case", action="store_true")
    parser.add_argument("--reviewed-source-group-case", action="store_true")
    parser.add_argument("--retain-private-pilot", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.info(
        "Private fictional rollout built at %s",
        build_rollout_pilot(
            args.destination.resolve(),
            version=args.version,
            owned_archive=args.owned_archive,
            passive_review_case=args.passive_review_case,
            reviewed_source_group_case=args.reviewed_source_group_case,
            retain_private_pilot=args.retain_private_pilot,
        ),
    )
