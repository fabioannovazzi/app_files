#!/usr/bin/env python3
"""Build a private local MCP Apps pilot with an isolated fictional archive."""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
from pathlib import Path

__all__ = ["build_pilot", "seed_demo"]

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "plugins" / "bilancio-xbrl-it"


def seed_demo(
    destination: Path, *, scenario: str = "aurora", storage_root: Path | None = None
) -> dict[str, str]:
    """Create fictional evidence through the existing ledger and accounting engine."""

    for component in ("bilancio-xbrl-it", "studio-archive"):
        sys.path.insert(0, str(ROOT / "plugins" / component / "scripts"))
    import client_ledger
    import xbrl_case

    scenarios = {
        "aurora": ("Officina Aurora S.r.l.", "a", "Cassa"),
        "boreale": ("Boreale S.r.l.", "b", "Banca Boreale"),
    }
    legal_name, client_suffix, cash_label = scenarios[scenario]
    case_id = f"{scenario}_2025"
    destination.mkdir(parents=True, exist_ok=False)
    client = destination / f"{legal_name} - dati fittizi"
    client.mkdir()
    client_id = "client_" + client_suffix * 24
    client_ledger.create_client_manifest(client, client_id)
    engagement = client_ledger.create_engagement(
        client, client_id, "Bilancio 2025 · prova UI"
    )
    source = destination / "bilancio-verifica-demo.csv"
    source.write_text(
        "account_code;account_description;opening_signed;period_debit;period_credit;closing_signed;prior_closing_signed\n"
        f"1000;{cash_label};90,00;10,00;0,00;100,00;90,00\n"
        "2000;Debiti;-90,00;0,00;10,00;-100,00;-90,00\n",
        encoding="utf-8",
    )
    receipt = client_ledger.import_document(
        client, client_id, engagement["engagement_id"], source, "source"
    )
    prepared = client_ledger.prepare_run(
        client,
        client_id,
        engagement["engagement_id"],
        "bilancio-xbrl-it",
        "ui-pilot",
        input_ids=[receipt["receipt"]["input_id"]],
        label="Bilancio 2025 · prova UI",
        idempotency_key="native-ui-demo",
    )
    run_id = prepared["run"]["run_id"]
    client_ledger.start_run(client, engagement["engagement_id"], run_id)
    loaded = client_ledger.load_run(client, engagement["engagement_id"], run_id)
    storage = storage_root or Path(loaded["output_dir"]) / "case-service"
    case_dir = storage / "demo_studio" / case_id
    if case_dir.exists():
        raise FileExistsError(f"Fictional case already exists: {case_dir}")
    case = xbrl_case.create_case(
        case_dir,
        {
            "case_id": case_id,
            "tenant_id": "demo_studio",
            "entity": {
                "legal_name": f"{legal_name} · dati fittizi",
                "tax_identifier": "IT00000000000",
                "registered_office": "Milano, Italia",
                "legal_form": "SRL",
                "accounting_framework": "OIC",
                "listed": False,
                "regulated_sector": False,
                "consolidated": False,
                "final_liquidation": False,
                "first_financial_year": False,
                "prior_year_form": "ABBREVIATED",
                "prior_period_start": "2024-01-01",
                "prior_period_end": "2024-12-31",
                "micro_exclusion_flags": [],
            },
            "period": {"start": "2025-01-01", "end": "2025-12-31"},
            "oic_rule_pack": "OIC_2024_2025.1",
            "filing_campaign_year": 2026,
            "taxonomy_checksum": "a" * 64,
        },
        json.loads(
            (COMPONENT / "rulepacks/it/statutory-forms-2026.1.json").read_bytes()
        ),
        "demo_reviewer",
    )
    case = xbrl_case.ingest_trial_balance(
        case, Path(receipt["imported_path"]), "demo_reviewer", case["revision_id"]
    )
    case = xbrl_case.confirm_parser(
        case, "TURNOVER_EXCLUDES_OPENING", "demo_reviewer", case["revision_id"]
    )
    case = xbrl_case.run_validation(case, "demo_reviewer", case["revision_id"])
    xbrl_case.save_case(case_dir, case)
    bindings = destination / "workspace-bindings.json"
    bindings.write_text(
        json.dumps(
            {
                "tenant_id": "demo_studio",
                "actor_id": "demo_reviewer",
                "bindings": [
                    {
                        "case_id": case["case_id"],
                        "client_root": str(client),
                        "client_id": client_id,
                        "engagement_id": engagement["engagement_id"],
                        "run_id": run_id,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "VERA_XBRL_STORAGE_ROOT": str(storage),
        "VERA_XBRL_TENANT_ID": "demo_studio",
        "VERA_XBRL_ACTOR_ID": "demo_reviewer",
        "VERA_XBRL_ROLES": "REVIEWER",
        "VERA_XBRL_PYTHON": sys.executable,
        "VERA_XBRL_WORKSPACE_BINDINGS": str(bindings),
        "VERA_XBRL_UI_ONLY": "1",
    }


def build_pilot(
    destination: Path, *, version: str = "0.0.4", reuse_demo: Path | None = None
) -> Path:
    """Package source without changing Vera's canonical manifest or public listings."""

    if not re.fullmatch(r"0\.0\.[0-9]+", version):
        raise ValueError("Private development versions must use 0.0.<number>")
    if reuse_demo is None:
        environment = None
    else:
        prior = reuse_demo.resolve()
        environment = json.loads((prior / "environment.json").read_bytes())
        if (
            environment["VERA_XBRL_TENANT_ID"] != "demo_studio"
            or environment["VERA_XBRL_ACTOR_ID"] != "demo_reviewer"
            or not Path(environment["VERA_XBRL_STORAGE_ROOT"])
            .resolve()
            .is_relative_to(prior / "fictional-archive")
            or not Path(environment["VERA_XBRL_WORKSPACE_BINDINGS"])
            .resolve()
            .is_relative_to(prior / "fictional-archive")
        ):
            raise ValueError(
                "Only a previously generated fictional archive can be reused"
            )
    destination.mkdir(parents=True, exist_ok=False)
    if environment is None:
        environment = seed_demo(destination / "fictional-archive")
    plugin = destination / "plugins" / "vera-workspace-pilot"
    plugin.mkdir(parents=True)
    for component in ("bilancio-xbrl-it", "studio-archive"):
        shutil.copytree(
            ROOT / "plugins" / component,
            plugin / "modules" / component,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
        )
    (plugin / ".codex-plugin").mkdir()
    (plugin / "assets").mkdir()
    shutil.copyfile(ROOT / "plugins/vera/assets/icon.svg", plugin / "assets/icon.svg")
    manifest = {
        "name": "vera-workspace-pilot",
        "version": version,
        "description": "Private fictional-data test of Vera's native case workspace.",
        "mcpServers": "./.mcp.json",
        "interface": {
            "displayName": "Vera · Workspace pilot",
            "shortDescription": "Private fictional Bilancio review",
            "iconSmall": "./assets/icon.svg",
            "iconLarge": "./assets/icon.svg",
        },
    }
    (plugin / ".codex-plugin/plugin.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    node = shutil.which("node") or str(
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    )
    mcp = {
        "mcpServers": {
            "veraWorkspace": {
                "title": "Fascicoli Vera",
                "command": node,
                "cwd": ".",
                "args": ["./modules/bilancio-xbrl-it/mcp/server.cjs"],
                "env": environment,
            }
        }
    }
    (plugin / ".mcp.json").write_text(json.dumps(mcp, indent=2), encoding="utf-8")
    market = destination / ".agents/plugins"
    market.mkdir(parents=True)
    (market / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "vera-ui-private",
                "interface": {"displayName": "Vera UI · private pilot"},
                "plugins": [
                    {
                        "name": "vera-workspace-pilot",
                        "source": {
                            "source": "local",
                            "path": "./plugins/vera-workspace-pilot",
                        },
                        "policy": {
                            "installation": "AVAILABLE",
                            "authentication": "ON_INSTALL",
                        },
                        "category": "Productivity",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (destination / "environment.json").write_text(
        json.dumps(environment, indent=2), encoding="utf-8"
    )
    return plugin


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--version", default="0.0.4")
    parser.add_argument("--reuse-demo", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.info(
        "Private pilot built at %s",
        build_pilot(
            args.destination.resolve(), version=args.version, reuse_demo=args.reuse_demo
        ),
    )
