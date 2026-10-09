from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import venv
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.plugins.test_journal_bank_reconciliation_plugin import (
    _load_customer_ledger,
    _write_pdf_table,
    load_core,
)

ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_environment(root: Path, tmp_path: Path) -> dict[str, str]:
    """Use installed test dependencies in an isolated, receipted managed venv."""
    runtime = _load(root / "scripts/_managed_python_runtime.py", "seal_test_runtime")
    shared = _load(root / "scripts/_shared_python_runtime.py", "seal_test_shared")
    runtime_root = (tmp_path / "runtime").resolve()
    target = runtime_root / "venv"
    venv.EnvBuilder(with_pip=False).create(target)
    site = next(target.glob("lib/python*/site-packages"))
    site.joinpath("test-dependencies.pth").write_text(
        "\n".join(path for path in sys.path if "site-packages" in path) + "\n"
    )
    key = runtime.runtime_key(runtime.runtime_python(target))
    receipt = {
        "features": ["core"],
        "runtime_key": key,
        "recipes": shared._recipes(root, {"core"}),
    }
    (target / shared.RECEIPT).write_text(json.dumps(receipt))
    (runtime_root / shared.POLICY).write_text(json.dumps({"runtime_key": key}))
    return {
        **os.environ,
        "MPARANZA_RUNTIME_ROOT": str(runtime_root),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _case(tmp_path: Path, *, registration_pdf: bool = False) -> dict:
    ledger = _load_customer_ledger()
    client = tmp_path / "client"
    client.mkdir()
    client_id = "client_555555555555555555555555"
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(
        client, client_id, "Synthetic receipt acceptance"
    )
    inputs = []
    for side in ("bank", "journal"):
        source = tmp_path / f"{side}.pdf"
        _write_pdf_table(
            source,
            [
                [
                    [
                        "Date",
                        "Description",
                        "Reference",
                        "Amount",
                        "Balance",
                        "Currency",
                    ],
                    [
                        "2026-01-10",
                        "Invoice Alpha",
                        "INV1001",
                        "100.00",
                        "1100.00",
                        "EUR",
                    ],
                    [
                        "2026-01-11",
                        "Payment Beta",
                        "INV1002",
                        "-25.00",
                        "1075.00",
                        "EUR",
                    ],
                ]
            ],
        )
        if registration_pdf:
            if side == "journal":
                from tests.plugins.test_journal_sampling_plugin import (
                    _write_registration_journal_pdf,
                )

                _write_registration_journal_pdf(source)
            else:
                _write_pdf_table(
                    source,
                    [
                        [
                            [
                                "Date",
                                "Description",
                                "Reference",
                                "Amount",
                                "Balance",
                                "Currency",
                            ],
                            [
                                "2024-01-01",
                                "Pagamento INV100",
                                "INV100",
                                "100.00",
                                "1100.00",
                                "EUR",
                            ],
                        ]
                    ],
                )
        imported = ledger.import_document(
            client,
            client_id,
            engagement["engagement_id"],
            source,
            "source" if side == "bank" else side,
        )
        inputs.append(imported["receipt"]["input_id"])
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement["engagement_id"],
        "journal-bank-reconciliation",
        "synthetic-test",
        input_ids=inputs,
    )
    return ledger.start_run(
        client, engagement["engagement_id"], prepared["run"]["run_id"]
    )


def _decisions(recipe: dict) -> dict:
    decision = {
        "header_rows": [1],
        "mapping": {
            "date": "Date",
            "description": "Description",
            "reference": "Reference",
            "amount": "Amount",
            "currency": "Currency",
        },
        "excluded_monetary_columns": ["Balance"],
        "date_convention": None,
        "decimal_separator": ".",
        "thousands_separator": None,
        "direction_value_mapping": {},
    }
    return {
        "reviewer_ref": "reviewer.synthetic",
        "reviewed_on": "2026-10-08",
        "bank": {
            "files": {key: copy.deepcopy(decision) for key in recipe["bank"]["files"]}
        },
        "journal": {
            "files": {
                key: copy.deepcopy(decision) for key in recipe["journal"]["files"]
            }
        },
        "relationship": {
            **recipe["relationship"]["policy"],
            "relationship_shape": "one_to_one",
            "direction_policy": "same_sign",
            "amount_tolerance": "0",
            "date_window_days": 0,
        },
    }


@pytest.mark.parametrize("host", ["source", "codex", "cowork"])
def test_managed_pdf_inspection_sealing_reconciliation_and_stale_source(
    tmp_path: Path, host: str
) -> None:
    root = ROOT / "plugins/vera"
    if host != "source":
        archive = (
            ROOT
            / "plugin_packages/vera"
            / ("vera-plugin.zip" if host == "codex" else "vera-claude-plugin.zip")
        )
        extracted = tmp_path / "package"
        with ZipFile(archive) as bundle:
            bundle.extractall(extracted)
        root = next(extracted.rglob("scripts/managed_python_runtime.py")).parents[1]
    environment = _runtime_environment(root, tmp_path)
    case = _case(tmp_path)
    output = Path(case["output_dir"])
    context = Path(case["context_path"])
    sources = {
        "bank" if item["role"] == "source" else item["role"]: Path(item["path"])
        for item in case["context"]["input_bindings"]
    }
    recipe = output / "suggested_recipe.json"

    def run(script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(root / "scripts/managed_python_runtime.py"),
                "--module",
                "journal-bank-reconciliation",
                "run",
                f"scripts/{script}",
                "--client-engagement",
                str(context),
                *map(str, args),
            ],
            capture_output=True,
            text=True,
            env=environment,
            cwd=root,
            timeout=90,
            check=False,
        )

    initial = run(
        "inspect_inputs.py", sources["bank"], sources["journal"], "--output-dir", output
    )
    assert initial.returncode == 0, initial.stderr
    inspection = json.loads((output / "inspection.json").read_text())
    assert inspection["bank"]["row_count"] == inspection["journal"]["row_count"] == 0
    assert inspection["qualification_status"] == "needs_review"
    decisions = output / "review_decisions.json"
    decisions.write_text(json.dumps(_decisions(json.loads(recipe.read_text()))))
    sealed = run(
        "seal_review_receipts.py",
        "--output-dir",
        output,
        "--recipe",
        recipe,
        "--decisions",
        decisions,
    )
    assert sealed.returncode == 0, sealed.stderr
    reinspection = run(
        "inspect_inputs.py",
        sources["bank"],
        sources["journal"],
        "--output-dir",
        output,
        "--recipe",
        recipe,
    )
    assert reinspection.returncode == 0, reinspection.stderr
    inspection = json.loads((output / "inspection.json").read_text())
    assert inspection["bank"]["row_count"] == inspection["journal"]["row_count"] == 2
    assert inspection["bank"]["files"][0]["unresolved_monetary_columns"] == []
    assert inspection["journal"]["files"][0]["unresolved_monetary_columns"] == []
    reconciled = run(
        "run_reconciliation.py",
        sources["bank"],
        sources["journal"],
        "--output-dir",
        output / "reconciliation",
        "--recipe",
        recipe,
        "--tolerance",
        "0",
        "--date-window-days",
        "0",
    )
    assert reconciled.returncode == 0, reconciled.stderr
    assert (output / "reconciliation/material_value_ledger.json").is_file()
    assert "matched=2" in reconciled.stderr

    # Public core reinspection is used here because the archive gate separately
    # rejects tampered imported bytes before the CLI reaches source qualification.
    core = load_core()
    sources["bank"].write_bytes(sources["bank"].read_bytes() + b"\n")
    stale = core.inspect_inputs(
        sources["bank"], sources["journal"], output / "stale", recipe
    )
    assert stale.bank["row_count"] == 0
    assert stale.bank["files"][0]["qualification_status"] == "needs_review"
    assert "stale" in "\n".join(stale.bank["files"][0]["limitations"])


@pytest.mark.parametrize(
    "fault, message",
    [
        ("reviewer", "reviewer_ref must be an explicit identifier"),
        ("date", "reviewed_on must be an explicit ISO date"),
        ("missing_file", "must review every inspected source exactly once"),
        (
            "balance",
            "potential monetary columns require a complete mapped-or-excluded disposition",
        ),
        (
            "policy",
            "relationship policy must contain the exact reviewed perimeter fields",
        ),
    ],
)
def test_sealing_incomplete_decisions_leaves_recipe_unchanged(
    tmp_path: Path, fault: str, message: str
) -> None:
    core = load_core()
    sealer = _load(
        ROOT / "plugins/journal-bank-reconciliation/scripts/seal_review_receipts.py",
        "seal_review_receipts",
    )
    case = _case(tmp_path)
    output = Path(case["output_dir"])
    sources = {
        "bank" if item["role"] == "source" else item["role"]: Path(item["path"])
        for item in case["context"]["input_bindings"]
    }
    core.inspect_inputs(sources["bank"], sources["journal"], output)
    recipe = json.loads((output / "suggested_recipe.json").read_text())
    original = copy.deepcopy(recipe)
    decisions = _decisions(recipe)
    if fault == "reviewer":
        decisions["reviewer_ref"] = ""
    elif fault == "date":
        decisions["reviewed_on"] = "today"
    elif fault == "missing_file":
        decisions["bank"]["files"] = {}
    elif fault == "balance":
        next(iter(decisions["bank"]["files"].values()))[
            "excluded_monetary_columns"
        ] = []
    else:
        decisions["relationship"].pop("default_currency")
    receipts = json.loads((output / "input_receipts.json").read_text())["receipts"]

    with pytest.raises(ValueError, match=message):
        sealer.seal_review_receipts(recipe, decisions, receipts, case["context"])

    assert recipe == original


@pytest.mark.parametrize(
    "script, message",
    [
        ("scripts/missing_sealer.py", "Managed runtime script not found:"),
        ("/outside/sealer.py", "Managed runtime script outside module root:"),
    ],
)
def test_launcher_explains_script_boundary_before_setup(
    script: str, message: str
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins/vera/scripts/managed_python_runtime.py"),
            "--module",
            "journal-bank-reconciliation",
            "run",
            script,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 2
    assert message in result.stderr
    assert "setup failed" not in result.stderr


@pytest.mark.parametrize("complete", [True, False], ids=["complete", "incomplete"])
def test_sealing_cli_publishes_only_complete_recipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, complete: bool
) -> None:
    core = load_core()
    sealer = _load(
        ROOT / "plugins/journal-bank-reconciliation/scripts/seal_review_receipts.py",
        "seal_review_receipts",
    )
    case = _case(tmp_path)
    output = Path(case["output_dir"])
    inputs = {
        item["role"]: Path(item["path"]) for item in case["context"]["input_bindings"]
    }
    core.inspect_inputs(inputs["source"], inputs["journal"], output)
    recipe = output / "suggested_recipe.json"
    original = recipe.read_bytes()
    decisions = _decisions(json.loads(original))
    if not complete:
        decisions["journal"]["files"] = {}
    decision_path = output / "review_decisions.json"
    decision_path.write_text(json.dumps(decisions))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "seal_review_receipts.py",
            "--client-engagement",
            case["context_path"],
            "--output-dir",
            str(output),
            "--recipe",
            str(recipe),
            "--decisions",
            str(decision_path),
        ],
    )

    result = sealer.main()

    assert result == (0 if complete else 2)
    assert bool(json.loads(recipe.read_text())["relationship"]["decision"]) is complete
    assert (recipe.read_bytes() != original) is complete
    assert list(output.glob(".review-receipts-*.tmp")) == []


@pytest.mark.parametrize("host", ["source", "codex", "cowork"])
def test_managed_registration_pdf_layout_sealing_and_reconciliation(
    tmp_path: Path,
    host: str,
) -> None:
    root = ROOT / "plugins/vera"
    if host != "source":
        archive = (
            ROOT
            / "plugin_packages/vera"
            / ("vera-plugin.zip" if host == "codex" else "vera-claude-plugin.zip")
        )
        extracted = tmp_path / "package"
        with ZipFile(archive) as bundle:
            bundle.extractall(extracted)
        root = next(extracted.rglob("scripts/managed_python_runtime.py")).parents[1]
    environment = _runtime_environment(root, tmp_path)
    case = _case(tmp_path, registration_pdf=True)
    output = Path(case["output_dir"])
    context = Path(case["context_path"])
    sources = {
        "bank" if item["role"] == "source" else item["role"]: Path(item["path"])
        for item in case["context"]["input_bindings"]
    }
    layout = {
        "body": [20, 770],
        "columns": {
            "account_debit": [20, 110],
            "account_credit": [110, 195],
            "description": [195, 400],
            "debit": [400, 490],
            "credit": [490, 590],
        },
        "ignored_line_prefixes": [],
    }
    recipe = output / "input_recipe.json"
    recipe.write_text(
        json.dumps(
            {
                "journal": {
                    "files": {
                        sources["journal"].name: {"pdf_registration_layout": layout}
                    }
                }
            }
        )
    )

    def run(script: str, *arguments: object) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(root / "scripts/managed_python_runtime.py"),
                "--module",
                "journal-bank-reconciliation",
                "run",
                f"scripts/{script}",
                "--client-engagement",
                str(context),
                *map(str, arguments),
            ],
            capture_output=True,
            text=True,
            env=environment,
            cwd=root,
            timeout=90,
            check=False,
        )

    inspected = run(
        "inspect_inputs.py",
        sources["bank"],
        sources["journal"],
        "--output-dir",
        output,
        "--recipe",
        recipe,
    )
    assert inspected.returncode == 0, inspected.stderr
    suggested = output / "suggested_recipe.json"
    decisions = _decisions(json.loads(suggested.read_text()))
    journal = next(iter(decisions["journal"]["files"].values()))
    journal.update(
        {
            "mapping": {
                "date": "Data",
                "account": "Conto",
                "description": "Descrizione",
                "debit": "Dare",
                "credit": "Avere",
                "reference": "Numero registrazione",
            },
            "excluded_monetary_columns": [],
            "pdf_registration_layout": layout,
        }
    )
    decision_path = output / "review_decisions.json"
    decision_path.write_text(json.dumps(decisions))
    sealed = run(
        "seal_review_receipts.py",
        "--output-dir",
        output,
        "--recipe",
        suggested,
        "--decisions",
        decision_path,
    )
    assert sealed.returncode == 0, sealed.stderr
    reconciled = run(
        "run_reconciliation.py",
        sources["bank"],
        sources["journal"],
        "--output-dir",
        output / "reconciliation",
        "--recipe",
        suggested,
        "--tolerance",
        "0",
        "--date-window-days",
        "0",
    )
    assert reconciled.returncode == 0, reconciled.stderr
    assert "matched=1" in reconciled.stderr
    normalized = (output / "reconciliation/normalized_journal.csv").read_text()
    assert "PDF page 1" in normalized and "PDF page 2" in normalized
    assert (output / "reconciliation/journal_bank_reconciliation.xlsx").is_file()
