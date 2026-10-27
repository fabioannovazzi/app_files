from __future__ import annotations

import copy
import errno
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from unittest.mock import Mock
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
        "installed_distributions": runtime._resolved_dependencies(target),
    }
    (target / shared.RECEIPT).write_text(json.dumps(receipt))
    (runtime_root / shared.POLICY).write_text(
        json.dumps(
            {
                "runtime_key": key,
                "features": receipt["features"],
                "recipes": receipt["recipes"],
                "revision": shared.POLICY_REVISION,
            }
        )
    )
    return {
        **os.environ,
        "MPARANZA_RUNTIME_ROOT": str(runtime_root),
        "MPARANZA_INCIDENT_STATE_DIR": str(tmp_path / "incident-state"),
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "https_proxy": "http://127.0.0.1:9",
        "NO_PROXY": "localhost,127.0.0.1",
        "no_proxy": "localhost,127.0.0.1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _case(
    tmp_path: Path,
    *,
    registration_pdf: bool = False,
    unfamiliar_pdf: bool = False,
    journal_amount: str = "100.00",
) -> dict:
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
                        journal_amount if side == "journal" else "100.00",
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
        if unfamiliar_pdf and side == "journal":
            from tests.plugins.test_agentic_pdf_recovery import unfamiliar_source

            layout = unfamiliar_source(source)
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
    loaded = ledger.start_run(
        client, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    if unfamiliar_pdf:
        loaded["test_pdf_layout"] = layout
    return loaded


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
        "reviewer_ref": "agent.synthetic",
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
def test_managed_archive_writer_preserves_text_and_replays_same_run(
    tmp_path: Path, host: str
) -> None:
    root = ROOT / "plugins/vera"
    if host != "source":
        archive = (
            ROOT
            / "plugin_packages/vera"
            / ("vera-plugin.zip" if host == "codex" else "vera-claude-plugin.zip")
        )
        with ZipFile(archive) as bundle:
            bundle.extractall(tmp_path / "package")
        root = next(
            (tmp_path / "package").rglob("scripts/managed_python_runtime.py")
        ).parents[1]
    environment = {
        **_runtime_environment(root, tmp_path),
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(tmp_path / "archive-state"),
        "VERA_STUDIO_ARCHIVE_PROFILE_DIR": str(tmp_path / "archive-profile"),
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "archive-writer-regression",
        "VERA_STUDIO_ARCHIVE_PYTHON": sys.executable,
        "MPARANZA_INCIDENT_DELIVERY": "local-only",
    }
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    case = _case(archive_root, unfamiliar_pdf=True)
    component = root / "modules/studio-archive"
    if host == "source":
        component = root.parent / "studio-archive"

    def call(name: str, arguments: dict) -> dict:
        completed = subprocess.run(
            [shutil.which("node"), str(component / "mcp/server.cjs"), "--stdio"],
            input=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
            )
            + "\n",
            capture_output=True,
            text=True,
            env=environment,
            cwd=root,
            timeout=90,
            check=True,
        )
        reply = next(
            json.loads(line)
            for line in completed.stdout.splitlines()
            if json.loads(line).get("id") == 1
        )["result"]
        assert reply["isError"] is False, json.dumps(reply, ensure_ascii=False)
        return reply["structuredContent"]

    call("configure_studio_archive", {"archive_root": str(archive_root)})
    # Reproduce a chat worker that cannot write to the client folder, while
    # the separate Archive owner retains its authorized filesystem capability.
    if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file():
        denied_path = Path(case["output_dir"]) / "shell-write.txt"
        profile = (
            "(version 1)(allow default)(deny file-write* (subpath "
            + json.dumps(str(archive_root.resolve()))
            + "))"
        )
        denied = subprocess.run(
            [
                "/usr/bin/sandbox-exec",
                "-p",
                profile,
                sys.executable,
                "-c",
                "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('denied')",
                str(denied_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert denied.returncode != 0 and "PermissionError" in denied.stderr
        assert not denied_path.exists()
    content = "--not-an-option\n" + "è" * 20000
    arguments = {
        key: case["run"][key] for key in ("client_id", "engagement_id", "run_id")
    }
    arguments.update(name="draft.md", content=content)

    saved = call("write_studio_run_artifact", arguments)
    replayed = call("write_studio_run_artifact", arguments)

    assert Path(saved["path"]).read_text(encoding="utf-8") == content
    assert saved["run_id"] == case["run"]["run_id"]
    assert saved["sha256"] == replayed["sha256"]
    assert replayed["replayed"] is True
    assert saved["source_lineage"] == "unverified"

    from tests.plugins.test_agentic_pdf_recovery import ADAPTER

    adapter = call(
        "write_studio_run_artifact",
        {
            **arguments,
            "name": "pdf_adapter.py",
            "content": ADAPTER.replace("CHANGE", ""),
        },
    )
    layout = {
        **case["test_pdf_layout"],
        "agent_adapter": {"path": adapter["path"], "sha256": adapter["sha256"]},
    }
    inputs = {
        item["role"]: Path(item["path"]) for item in case["context"]["input_bindings"]
    }
    recipe = call(
        "write_studio_run_artifact",
        {
            **arguments,
            "name": "pdf_recipe.json",
            "content": json.dumps(
                {
                    "journal": {
                        "files": {
                            inputs["journal"].name: {"pdf_registration_layout": layout}
                        }
                    }
                }
            ),
        },
    )
    command = [
        sys.executable,
        str(root / "scripts/managed_python_runtime.py"),
        "--module",
        "journal-bank-reconciliation",
        "run",
        "scripts/inspect_inputs.py",
        str(inputs["source"]),
        str(inputs["journal"]),
        "--client-engagement",
        case["context_path"],
        "--output-dir",
        case["output_dir"],
        "--recipe",
        recipe["path"],
        "--pdf-currency",
        "EUR",
    ]

    trial = subprocess.run(
        [
            *command,
            "--pdf-recovery",
            "trial",
            "--pdf-reason",
            "Reviewed unfamiliar header",
        ],
        env=environment,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    assert trial.returncode == 0, trial.stderr
    attempt = json.loads(
        (Path(case["output_dir"]) / "pdf_recovery/attempt-01.json").read_text()
    )
    assert attempt["status"] == "ready_to_freeze"
    assert attempt["diagnostics"]["emitted_row_count"] == 4
    assert attempt["diagnostics"]["running_total_controls"][0]["matched"] is True
    assert Path(adapter["path"]).read_text() == ADAPTER.replace("CHANGE", "")
    verification = call(
        "verify_studio_run_report",
        {key: case["run"][key] for key in ("client_id", "engagement_id", "run_id")},
    )
    assert verification["status"] == "unavailable"  # This fixture run is still active.
    assert (
        json.loads((Path(case["run_root"]) / "run.json").read_text())["status"]
        == "running"
    )


@pytest.mark.parametrize(
    "host,tolerance,window,options,error",
    [
        ("source", "0", 0, [], None),
        ("source", "0.125", 3, [], None),
        (
            "source",
            "0.125",
            3,
            ["--tolerance", "0.125", "--date-window-days", "3"],
            None,
        ),
        ("source", "0.125", 3, ["--tolerance", "0.125"], None),
        ("source", "0.125", 3, ["--date-window-days", "3"], None),
        ("source", "0", 3, ["--tolerance", "1"], "Execution tolerance differs"),
        (
            "source",
            "0",
            3,
            ["--date-window-days", "7"],
            "Execution date window differs",
        ),
        ("codex", "0", 0, [], None),
        ("cowork", "0.125", 3, [], None),
    ],
)
def test_managed_pdf_inspection_sealing_reconciliation_and_stale_source(
    tmp_path: Path,
    host: str,
    tolerance: str,
    window: int,
    options: list[str],
    error: str | None,
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
    review = _decisions(json.loads(recipe.read_text()))
    review["relationship"].update(amount_tolerance=tolerance, date_window_days=window)
    decisions = json.dumps(review)
    sealed = run(
        "seal_review_receipts.py",
        "--output-dir",
        output,
        "--recipe",
        recipe,
        "--decisions-json",
        decisions,
    )
    assert sealed.returncode == 0, sealed.stderr
    assert len(list(output.glob("review_decisions.*.json"))) == 1
    sealed_recipe = json.loads(recipe.read_text())
    assert (
        sealed_recipe["bank"]["files"]["bank.pdf"]["mapping_decision"]["reviewer_ref"]
        == "agent.synthetic"
    )
    assert (
        sealed_recipe["relationship"]["decision"]["reviewer_ref"] == "agent.synthetic"
    )
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
        *options,
    )
    if error is not None:
        assert reconciled.returncode != 0
        assert error in reconciled.stderr
        assert (output / "reconciliation/reconciliation_audit.json").is_file()
        assert (output / "reconciliation/input_receipts.json").is_file()
        return
    assert reconciled.returncode == 0, reconciled.stderr
    audit = json.loads(
        (output / "reconciliation/reconciliation_audit.json").read_text()
    )
    assert audit["tolerance"] == tolerance
    assert audit["date_window_days"] == window
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


@pytest.mark.parametrize("copied_candidates", [["Amount", "Balance"], [], ["Stale"]])
def test_sealing_recomputes_copied_monetary_candidates(
    tmp_path: Path, copied_candidates: list[str]
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
    recipe = json.loads((output / "suggested_recipe.json").read_text())
    decisions = _decisions(recipe)
    filename, choice = next(iter(decisions["bank"]["files"].items()))
    choice["potential_monetary_columns"] = copied_candidates
    original_decisions = copy.deepcopy(decisions)
    receipts = json.loads((output / "input_receipts.json").read_text())["receipts"]

    sealed = sealer.seal_review_receipts(recipe, decisions, receipts, case["context"])

    file_recipe = sealed["bank"]["files"][filename]
    assert file_recipe["potential_monetary_columns"] == ["Amount", "Balance"]
    assert file_recipe["mapping_decision"]["content"]["potential_monetary_columns"] == [
        "Amount",
        "Balance",
    ]
    assert decisions == original_decisions


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
            "masked_balance",
            "potential monetary columns require a complete mapped-or-excluded disposition",
        ),
        (
            "unknown_field",
            "mapping decisions are incomplete or contain unknown fields",
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
    elif fault in {"balance", "masked_balance"}:
        choice = next(iter(decisions["bank"]["files"].values()))
        choice["excluded_monetary_columns"] = []
        if fault == "masked_balance":
            choice["potential_monetary_columns"] = []
    elif fault == "unknown_field":
        next(iter(decisions["bank"]["files"].values()))["decimal_seperator"] = ","
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
    if host != "source":
        markers = root / ".in_use"
        markers.mkdir()
        (markers / "71").write_text("")
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


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_inline_decisions_failed_write_never_seals_and_retry_preserves_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    core = load_core()
    sealer = _load(
        ROOT / "plugins/journal-bank-reconciliation/scripts/seal_review_receipts.py",
        "seal_inline_receipts",
    )
    case = _case(tmp_path)
    output = Path(case["output_dir"])
    inputs = {
        item["role"]: Path(item["path"]) for item in case["context"]["input_bindings"]
    }
    core.inspect_inputs(inputs["source"], inputs["journal"], output)
    recipe = output / "suggested_recipe.json"
    original = recipe.read_bytes()
    run_path = Path(case["run_root"]) / "run.json"
    original_run = run_path.read_bytes()
    decisions = _decisions(json.loads(original))
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
            "--decisions-json",
            json.dumps(decisions),
        ],
    )
    seal = Mock(wraps=sealer.seal_review_receipts)
    monkeypatch.setattr(sealer, "seal_review_receipts", seal)
    actual_operation = getattr(sealer.os, failure)
    denied = Mock(side_effect=PermissionError(errno.EPERM, "fixture denied write"))
    monkeypatch.setattr(sealer.os, failure, denied)

    failed = sealer.main()

    assert failed == 2
    seal.assert_not_called()
    assert recipe.read_bytes() == original
    assert list(output.glob("review_decisions.*.json")) == []
    monkeypatch.setattr(sealer.os, failure, actual_operation)

    retried = sealer.main()

    assert retried == 0
    seal.assert_called_once()
    retained = list(output.glob("review_decisions.*.json"))
    assert len(retained) == 1
    assert json.loads(retained[0].read_text()) == decisions
    sealed = recipe.read_bytes()
    assert sealer.main() == 0
    assert recipe.read_bytes() == sealed
    assert list(output.glob("review_decisions.*.json")) == retained
    assert run_path.read_bytes() == original_run


@pytest.mark.parametrize("host", ["source", "codex", "cowork"])
@pytest.mark.parametrize(
    "chosen_tolerance,matched,difference_artifact,visible_value",
    [
        ("0", 1, "unmatched_journal.csv", "100.12"),
        ("0.12", 2, "reconciliation_matches.csv", "0.12"),
    ],
)
def test_cli_changed_professional_tolerance_controls_matches_and_saved_explanation(
    tmp_path: Path,
    host: str,
    chosen_tolerance: str,
    matched: int,
    difference_artifact: str,
    visible_value: str,
) -> None:
    root = ROOT / "plugins/vera"
    if host != "source":
        archive = (
            ROOT
            / "plugin_packages/vera"
            / ("vera-plugin.zip" if host == "codex" else "vera-claude-plugin.zip")
        )
        with ZipFile(archive) as bundle:
            bundle.extractall(tmp_path / "package")
        root = next(
            (tmp_path / "package").rglob("scripts/managed_python_runtime.py")
        ).parents[1]
    environment = _runtime_environment(root, tmp_path)
    case = _case(tmp_path, journal_amount="100.12")
    output = Path(case["output_dir"])
    sources = {
        item["role"]: Path(item["path"]) for item in case["context"]["input_bindings"]
    }

    def run(script: str, *args: object) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(root / "scripts/managed_python_runtime.py"),
                "--module",
                "journal-bank-reconciliation",
                "run",
                f"scripts/{script}",
                "--client-engagement",
                str(case["context_path"]),
                *map(str, args),
            ],
            capture_output=True,
            text=True,
            env=environment,
            cwd=root,
            timeout=90,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    run(
        "inspect_inputs.py",
        sources["source"],
        sources["journal"],
        "--output-dir",
        output,
    )
    original_recipe = output / "suggested_recipe.json"
    review = _decisions(json.loads(original_recipe.read_text()))
    review["relationship"]["amount_tolerance"] = "1"
    first_decisions = output / "initial-decisions.json"
    first_decisions.write_text(json.dumps(review))
    run(
        "seal_review_receipts.py",
        "--output-dir",
        output,
        "--recipe",
        original_recipe,
        "--decisions",
        first_decisions,
    )
    previous = output / "previous"
    run(
        "run_reconciliation.py",
        sources["source"],
        sources["journal"],
        "--output-dir",
        previous,
        "--recipe",
        original_recipe,
    )
    previous_audit = (previous / "reconciliation_audit.json").read_bytes()
    previous_recipe = original_recipe.read_bytes()
    revised_recipe = output / "revised-recipe.json"
    revised_recipe.write_bytes(previous_recipe)
    review["relationship"]["amount_tolerance"] = chosen_tolerance
    decisions = output / "professional-change.json"
    decisions.write_text(json.dumps(review))

    # A supported policy revision followed by an ordinary invocation without flags.
    run(
        "seal_review_receipts.py",
        "--output-dir",
        output,
        "--recipe",
        revised_recipe,
        "--decisions",
        decisions,
    )
    revised = output / "revised"
    run(
        "run_reconciliation.py",
        sources["source"],
        sources["journal"],
        "--output-dir",
        revised,
        "--recipe",
        revised_recipe,
    )

    audit = json.loads((revised / "reconciliation_audit.json").read_text())
    intake = json.loads((revised / "run_intake.json").read_text())
    recipe = json.loads(revised_recipe.read_text())
    assert audit["tolerance"] == chosen_tolerance
    assert audit["matched_count"] == matched
    assert intake["assumptions"]["tolerance"] == chosen_tolerance
    assert (
        recipe["relationship"]["decision"]["content"]["policy"]["amount_tolerance"]
        == chosen_tolerance
    )
    assert (
        f"Matching tolerance: {chosen_tolerance}"
        in (revised / "review_notes.md").read_text()
    )
    assert "does not authorize write-offs" in (revised / "review_notes.md").read_text()
    assert "100.12" in (revised / "normalized_journal.csv").read_text()
    assert visible_value in (revised / difference_artifact).read_text()
    assert original_recipe.read_bytes() == previous_recipe
    assert (previous / "reconciliation_audit.json").read_bytes() == previous_audit
    # Downstream value verification replays the actual saved policy and allocations.
    load_core().validate_material_value_ledger(revised)
