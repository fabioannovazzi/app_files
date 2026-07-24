from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT
    / "plugins"
    / "clara"
    / "skills"
    / "html-deck"
    / "scripts"
    / "evidence_bindings.py"
)
SKILL_ROOT = ROOT / "plugins" / "clara" / "skills" / "html-deck"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "clara_html_evidence"


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_html_deck_evidence_bindings_test",
        MODULE_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_script(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(path), *args],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def write_due_diligence_evidence(root: Path, module: Any) -> dict[str, Any]:
    financials = root / "financial-facts.csv"
    financials.write_text(
        "fact_id,display_order,label,value\n"
        "revenue,001,Revenue,25356432.55\n"
        "net-debt,002,Net debt,7844000.00\n",
        encoding="utf-8",
    )
    concentration = root / "customer-concentration.csv"
    concentration.write_text(
        "row_id,display_order,label,value\n"
        "customer-a,001,Customer A,0.184\n"
        "customer-b,002,Customer B,0.121\n"
        "customer-c,003,Customer C,0.087\n",
        encoding="utf-8",
    )
    bundle_path = root / "evidence-bundle.json"
    write_json(
        bundle_path,
        {
            "schema_version": "clara.evidence_bundle.v1",
            "bundle_id": "diligence-case",
            "description": "Deterministically prepared financial and customer facts.",
            "artifacts": [
                {
                    "id": "financial-facts",
                    "source_id": "source-financial-facts",
                    "path": financials.name,
                    "media_type": "text/csv",
                    "sha256": "",
                    "size_bytes": 0,
                    "snapshot_id": "closing-snapshot",
                    "table": {
                        "key_fields": ["fact_id"],
                        "order_by": ["display_order"],
                    },
                },
                {
                    "id": "customer-concentration",
                    "source_id": "source-customer-concentration",
                    "path": concentration.name,
                    "media_type": "text/csv",
                    "sha256": "",
                    "size_bytes": 0,
                    "snapshot_id": "closing-snapshot",
                    "table": {
                        "key_fields": ["row_id"],
                        "order_by": ["display_order"],
                    },
                },
            ],
        },
    )
    module.seal_evidence_bundle(bundle_path)
    return {
        "bundle_path": bundle_path,
        "financials": financials,
        "concentration": concentration,
    }


def binding_reference(binding_id: str, mode: str) -> dict[str, object]:
    return {"$binding": {"id": binding_id, "mode": mode}}


def evidence_template(
    text: str,
    **bindings: tuple[str, str],
) -> dict[str, object]:
    return {
        "$template": {
            "text": text,
            "bindings": {
                name: {"id": binding_id, "mode": mode}
                for name, (binding_id, mode) in bindings.items()
            },
        }
    }


def source_bound_documents(
    root: Path,
    module: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = write_due_diligence_evidence(root, module)
    bundle_path = evidence["bundle_path"]
    financials = evidence["financials"]
    concentration = evidence["concentration"]
    headline = evidence_template(
        "Revenue is {revenue}",
        revenue=("revenue", "display"),
    )
    plan = {
        "schema_version": "clara.html_deck_plan.v2",
        "allow_bespoke_html": False,
        "evidence": {
            "bundle": {
                "path": bundle_path.name,
                "sha256": file_sha256(bundle_path),
            },
            "numeric_policy": "require_bindings",
            "bindings": {
                "revenue": {
                    "kind": "table_cell",
                    "artifact_id": "financial-facts",
                    "row_key": {"fact_id": "revenue"},
                    "field": "value",
                    "value_type": "decimal",
                    "display": {
                        "decimals": 1,
                        "scale": "0.000001",
                        "rounding": "half_up",
                        "prefix": "$",
                        "suffix": "m",
                    },
                },
                "customer-series": {
                    "kind": "table_rows",
                    "artifact_id": "customer-concentration",
                    "fields": {"label": "label", "value": "value"},
                    "value_type": "records",
                },
            },
        },
        "slides": [
            {
                "id": "diligence-evidence",
                "layout_id": "visual-takeaway",
                "title": headline,
                "chapter": "evidence",
                "chapter_label": "Evidence",
                "tone": "light",
                "notes": "Explain the financial fact and the concentration profile.",
                "source_refs": [
                    "source-financial-facts",
                    "source-customer-concentration",
                ],
                "claim_refs": ["claim-revenue"],
                "slots": {
                    "eyebrow": "Financial evidence",
                    "title": headline,
                    "visual": {
                        "renderer": "data_visual",
                        "spec": {
                            "type": "bar",
                            "title": "Customer concentration",
                            "data": binding_reference("customer-series", "raw"),
                        },
                        "source_refs": ["source-customer-concentration"],
                    },
                    "takeaway_label": "Implication",
                    "takeaway": "The buyer should test resilience before pricing.",
                    "source_note": "Prepared diligence evidence.",
                },
            }
        ],
    }
    ledger = {
        "schema_version": "clara.html_deck_ledger.v2",
        "sources": [
            {
                "id": "source-financial-facts",
                "label": "Prepared financial facts",
                "kind": "calculation-output",
                "locator": financials.name,
                "sha256": file_sha256(financials),
                "publish_locator": False,
            },
            {
                "id": "source-customer-concentration",
                "label": "Prepared customer concentration",
                "kind": "calculation-output",
                "locator": concentration.name,
                "sha256": file_sha256(concentration),
                "publish_locator": False,
            },
        ],
        "slides": [
            {
                "slide_id": "diligence-evidence",
                "basis_status": "source-backed",
                "basis_note": "",
                "claims": [
                    {
                        "id": "claim-revenue",
                        "statement": evidence_template(
                            "Revenue is {revenue}",
                            revenue=("revenue", "display"),
                        ),
                        "classification": "fact",
                        "basis_status": "source-backed",
                        "basis_note": "",
                        "source_ids": ["source-financial-facts"],
                    }
                ],
            }
        ],
    }
    return plan, ledger


def write_source_bound_work(root: Path, module: Any) -> Path:
    work = root / "work"
    initialized = run_script(
        SKILL_ROOT / "scripts" / "init_html_deck.py",
        "--work-dir",
        str(work),
        "--title",
        "Diligence evidence brief",
        "--subtitle",
        "Financial and customer evidence",
        "--language",
        "en",
    )
    assert initialized.returncode == 0, initialized.stderr
    plan, ledger = source_bound_documents(work, module)
    write_json(work / "deck-plan.json", plan)
    write_json(work / "content-ledger.json", ledger)
    composed = run_script(
        SKILL_ROOT / "scripts" / "compose_html_deck.py",
        str(work / "deck-plan.json"),
        "--output-dir",
        str(work),
        "--force",
    )
    assert composed.returncode == 0, composed.stderr
    return work


def test_resolver_binds_same_decimal_to_prose_claim_and_chart_data(
    tmp_path: Path,
) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)

    result = module.resolve_source_bound_documents(
        plan=plan,
        ledger=ledger,
        base_dir=tmp_path,
    )

    resolved_slide = result.resolved_plan["slides"][0]
    assert resolved_slide["title"] == "Revenue is $25.4m"
    assert resolved_slide["slots"]["title"] == "Revenue is $25.4m"
    assert resolved_slide["slots"]["visual"]["spec"]["data"] == [
        {"label": "Customer A", "value": "0.184"},
        {"label": "Customer B", "value": "0.121"},
        {"label": "Customer C", "value": "0.087"},
    ]
    assert (
        result.resolved_ledger["slides"][0]["claims"][0]["statement"]
        == "Revenue is $25.4m"
    )
    revenue_uses = [
        use
        for use in result.evidence_ledger["bindings"]
        if use["binding_id"] == "revenue"
    ]
    assert len(revenue_uses) == 3
    assert {use["value_sha256"] for use in revenue_uses} == {
        revenue_uses[0]["value_sha256"]
    }
    assert {
        artifact["snapshot_id"] for artifact in result.evidence_ledger["artifacts"]
    } == {"closing-snapshot"}


def test_canonical_json_preserves_long_decimal_under_low_context_precision() -> None:
    module = load_module()
    exact_value = (
        "1234567890123456789012345678901234567890."
        "1234567890123456789012345678901234567897"
    )

    with localcontext() as context:
        context.prec = 4
        canonical = module.canonical_json_bytes({"value": Decimal(exact_value)})

    assert canonical == f'{{"value":"{exact_value}"}}'.encode()


def test_resolver_formats_long_decimal_without_context_loss(tmp_path: Path) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)
    exact_value = "123456789012345678901234567890"
    financials = tmp_path / "financial-facts.csv"
    financials.write_text(
        "fact_id,display_order,label,value\n"
        f"revenue,001,Revenue,{exact_value}\n"
        "net-debt,002,Net debt,7844000.00\n",
        encoding="utf-8",
    )
    bundle_path = tmp_path / "evidence-bundle.json"
    module.seal_evidence_bundle(bundle_path)
    plan["evidence"]["bundle"]["sha256"] = file_sha256(bundle_path)
    plan["evidence"]["bindings"]["revenue"]["display"] = {"decimals": 0}
    ledger["sources"][0]["sha256"] = file_sha256(financials)

    with localcontext() as context:
        context.prec = 4
        result = module.resolve_source_bound_documents(
            plan=plan,
            ledger=ledger,
            base_dir=tmp_path,
        )

    assert result.resolved_plan["slides"][0]["title"] == f"Revenue is {exact_value}"


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_bundle_sealer_rejects_nonstandard_json_constants(
    tmp_path: Path,
    constant: str,
) -> None:
    module = load_module()
    bundle_path = tmp_path / "evidence-bundle.json"
    bundle_path.write_text(
        (
            '{"schema_version":"clara.evidence_bundle.v1",'
            '"bundle_id":"nonstandard-json",'
            f'"description":{constant},"artifacts":[]}}'
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=rf"not valid JSON: non-standard JSON constant '{constant}'",
    ):
        module.seal_evidence_bundle(bundle_path)


def test_validate_evidence_bundle_returns_portable_receipts(tmp_path: Path) -> None:
    module = load_module()
    evidence = write_due_diligence_evidence(tmp_path, module)
    bundle_path = evidence["bundle_path"]

    result = module.validate_evidence_bundle(bundle_path)

    assert result == {
        "schema_version": "clara.evidence_bundle.v1",
        "bundle_id": "diligence-case",
        "sha256": file_sha256(bundle_path),
        "artifact_count": 2,
        "artifacts": [
            {
                "id": "customer-concentration",
                "source_id": "source-customer-concentration",
                "path": "customer-concentration.csv",
                "media_type": "text/csv",
                "sha256": file_sha256(evidence["concentration"]),
                "size_bytes": evidence["concentration"].stat().st_size,
                "snapshot_id": "closing-snapshot",
                "table": {
                    "key_fields": ["row_id"],
                    "order_by": ["display_order"],
                    "records_pointer": "",
                },
            },
            {
                "id": "financial-facts",
                "source_id": "source-financial-facts",
                "path": "financial-facts.csv",
                "media_type": "text/csv",
                "sha256": file_sha256(evidence["financials"]),
                "size_bytes": evidence["financials"].stat().st_size,
                "snapshot_id": "closing-snapshot",
                "table": {
                    "key_fields": ["fact_id"],
                    "order_by": ["display_order"],
                    "records_pointer": "",
                },
            },
        ],
    }
    assert all(
        not Path(receipt["path"]).is_absolute() for receipt in result["artifacts"]
    )


def test_validate_evidence_bundle_rejects_artifact_tamper(tmp_path: Path) -> None:
    module = load_module()
    evidence = write_due_diligence_evidence(tmp_path, module)
    evidence["financials"].write_text(
        evidence["financials"].read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        module.validate_evidence_bundle(evidence["bundle_path"])


def test_validate_evidence_bundle_rejects_malformed_artifact(tmp_path: Path) -> None:
    module = load_module()
    evidence = write_due_diligence_evidence(tmp_path, module)
    bundle_path = evidence["bundle_path"]
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    del bundle["artifacts"][0]["source_id"]
    write_json(bundle_path, bundle)

    with pytest.raises(ValueError, match="is missing fields"):
        module.validate_evidence_bundle(bundle_path)


def test_validate_evidence_bundle_rejects_duplicate_artifact(tmp_path: Path) -> None:
    module = load_module()
    evidence = write_due_diligence_evidence(tmp_path, module)
    bundle_path = evidence["bundle_path"]
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["artifacts"].append(dict(bundle["artifacts"][0]))
    write_json(bundle_path, bundle)

    with pytest.raises(ValueError, match="duplicate evidence artifact ID"):
        module.validate_evidence_bundle(bundle_path)


def test_validate_evidence_bundle_rejects_duplicate_json_field(tmp_path: Path) -> None:
    module = load_module()
    evidence = write_due_diligence_evidence(tmp_path, module)
    bundle_path = evidence["bundle_path"]
    bundle_text = bundle_path.read_text(encoding="utf-8")
    bundle_path.write_text(
        bundle_text.replace(
            '"source_id": "source-financial-facts",',
            (
                '"source_id": "source-financial-facts",\n'
                '      "source_id": "source-ambiguous",'
            ),
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate JSON field 'source_id'"):
        module.validate_evidence_bundle(bundle_path)


def test_extract_embedded_evidence_ledger_rejects_duplicate_json_field() -> None:
    module = load_module()
    html_text = (
        '<script id="claraEvidenceLedger" type="application/json">'
        '{"schema_version":"first","schema_version":"second"}'
        "</script>"
    )

    with pytest.raises(ValueError, match="duplicate JSON field 'schema_version'"):
        module.extract_embedded_evidence_ledger(html_text)


def test_validate_evidence_bundle_rejects_invalid_table_rows(tmp_path: Path) -> None:
    module = load_module()
    evidence = write_due_diligence_evidence(tmp_path, module)
    evidence["financials"].write_text(
        "fact_id,display_order,label,value\n"
        "revenue,001,Revenue,25356432.55\n"
        "revenue,002,Revenue duplicate,25356432.55\n",
        encoding="utf-8",
    )
    module.seal_evidence_bundle(evidence["bundle_path"])

    with pytest.raises(ValueError, match="duplicate table key"):
        module.validate_evidence_bundle(evidence["bundle_path"])


@pytest.mark.parametrize(
    ("field", "affix"),
    [
        ("prefix", "FY2026 "),
        ("suffix", " top 10"),
        ("suffix", "m²"),
    ],
)
def test_resolver_rejects_quantitative_display_affixes(
    tmp_path: Path,
    field: str,
    affix: str,
) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)
    plan["evidence"]["bindings"]["revenue"]["display"][field] = affix

    with pytest.raises(
        ValueError,
        match=rf"display\.{field} may not contain numeric characters",
    ):
        module.resolve_source_bound_documents(
            plan=plan,
            ledger=ledger,
            base_dir=tmp_path,
        )


def test_resolver_preserves_currency_and_unit_display_affixes(
    tmp_path: Path,
) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)
    plan["evidence"]["bindings"]["revenue"]["display"] = {
        "decimals": 2,
        "prefix": "€",
        "suffix": " kg",
    }

    result = module.resolve_source_bound_documents(
        plan=plan,
        ledger=ledger,
        base_dir=tmp_path,
    )

    assert result.resolved_plan["slides"][0]["title"] == "Revenue is €25356432.55 kg"


def test_resolver_rejects_unbound_quantitative_prose(tmp_path: Path) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)
    plan["slides"][0]["notes"] = "Explain the 2026 closing basis."

    with pytest.raises(ValueError, match="unbound values"):
        module.resolve_source_bound_documents(
            plan=plan,
            ledger=ledger,
            base_dir=tmp_path,
        )


def test_resolver_rejects_artifact_byte_drift(tmp_path: Path) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)
    concentration = tmp_path / "customer-concentration.csv"
    concentration.write_text(
        concentration.read_text(encoding="utf-8").replace("0.184", "0.194"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        module.resolve_source_bound_documents(
            plan=plan,
            ledger=ledger,
            base_dir=tmp_path,
        )


def test_resolver_rejects_nonfinite_decimal_values(tmp_path: Path) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)
    financials = tmp_path / "financial-facts.csv"
    financials.write_text(
        financials.read_text(encoding="utf-8").replace("25356432.55", "NaN"),
        encoding="utf-8",
    )
    module.seal_evidence_bundle(tmp_path / "evidence-bundle.json")
    plan["evidence"]["bundle"]["sha256"] = file_sha256(
        tmp_path / "evidence-bundle.json"
    )
    ledger["sources"][0]["sha256"] = file_sha256(financials)

    with pytest.raises(ValueError, match="finite decimal"):
        module.resolve_source_bound_documents(
            plan=plan,
            ledger=ledger,
            base_dir=tmp_path,
        )


def test_resolver_rejects_ledger_source_hash_mismatch(tmp_path: Path) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)
    ledger["sources"][0]["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="must carry artifact"):
        module.resolve_source_bound_documents(
            plan=plan,
            ledger=ledger,
            base_dir=tmp_path,
        )


def test_resolver_rejects_unused_binding_definitions(tmp_path: Path) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)
    plan["evidence"]["bindings"]["unused-copy"] = dict(
        plan["evidence"]["bindings"]["revenue"]
    )

    with pytest.raises(ValueError, match="unused bindings"):
        module.resolve_source_bound_documents(
            plan=plan,
            ledger=ledger,
            base_dir=tmp_path,
        )


def test_bundle_sealer_rejects_symbolic_link_artifacts(tmp_path: Path) -> None:
    module = load_module()
    outside = tmp_path.parent / f"{tmp_path.name}-outside.csv"
    outside.write_text("row_id,value\none,1\n", encoding="utf-8")
    linked = tmp_path / "linked.csv"
    linked.symlink_to(outside)
    bundle_path = tmp_path / "evidence-bundle.json"
    write_json(
        bundle_path,
        {
            "schema_version": "clara.evidence_bundle.v1",
            "bundle_id": "symlink-check",
            "artifacts": [
                {
                    "id": "linked-evidence",
                    "source_id": "source-linked-evidence",
                    "path": linked.name,
                    "media_type": "text/csv",
                    "sha256": "",
                    "size_bytes": 0,
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="symbolic link"):
        module.seal_evidence_bundle(bundle_path)


def test_resolver_rejects_duplicate_table_keys(tmp_path: Path) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)
    concentration = tmp_path / "customer-concentration.csv"
    concentration.write_text(
        concentration.read_text(encoding="utf-8") + "customer-a,004,Duplicate,0.011\n",
        encoding="utf-8",
    )
    module.seal_evidence_bundle(tmp_path / "evidence-bundle.json")
    plan["evidence"]["bundle"]["sha256"] = file_sha256(
        tmp_path / "evidence-bundle.json"
    )
    ledger["sources"][1]["sha256"] = file_sha256(concentration)

    with pytest.raises(ValueError, match="duplicate table key"):
        module.resolve_source_bound_documents(
            plan=plan,
            ledger=ledger,
            base_dir=tmp_path,
        )


def test_resolver_rejects_json_pointer_array_positions(tmp_path: Path) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)
    json_path = tmp_path / "contract-facts.json"
    write_json(json_path, {"facts": [{"value": "2.345"}]})
    bundle_path = tmp_path / "evidence-bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["artifacts"].append(
        {
            "id": "contract-facts",
            "source_id": "source-contract-facts",
            "path": json_path.name,
            "media_type": "application/json",
            "sha256": "",
            "size_bytes": 0,
        }
    )
    write_json(bundle_path, bundle)
    module.seal_evidence_bundle(bundle_path)
    plan["evidence"]["bundle"]["sha256"] = file_sha256(bundle_path)
    plan["evidence"]["bindings"]["contract-count"] = {
        "kind": "json_pointer",
        "artifact_id": "contract-facts",
        "pointer": "/facts/0/value",
        "value_type": "decimal",
        "display": {"decimals": 2},
    }
    plan["slides"][0]["slots"]["takeaway"] = evidence_template(
        "Flagged contracts total {count}",
        count=("contract-count", "display"),
    )
    plan["slides"][0]["source_refs"].append("source-contract-facts")
    ledger["sources"].append(
        {
            "id": "source-contract-facts",
            "label": "Prepared contract facts",
            "kind": "extraction-output",
            "locator": json_path.name,
            "sha256": file_sha256(json_path),
            "publish_locator": False,
        }
    )

    with pytest.raises(ValueError, match="may not address an array position"):
        module.resolve_source_bound_documents(
            plan=plan,
            ledger=ledger,
            base_dir=tmp_path,
        )


def test_decimal_display_uses_explicit_half_up_rounding(tmp_path: Path) -> None:
    module = load_module()
    plan, ledger = source_bound_documents(tmp_path, module)
    financials = tmp_path / "financial-facts.csv"
    financials.write_text(
        financials.read_text(encoding="utf-8").replace(
            "25356432.55",
            "2345000",
        ),
        encoding="utf-8",
    )
    module.seal_evidence_bundle(tmp_path / "evidence-bundle.json")
    plan["evidence"]["bundle"]["sha256"] = file_sha256(
        tmp_path / "evidence-bundle.json"
    )
    ledger["sources"][0]["sha256"] = file_sha256(financials)
    plan["evidence"]["bindings"]["revenue"]["display"] = {
        "decimals": 2,
        "scale": "0.000001",
        "rounding": "half_up",
        "prefix": "$",
        "suffix": "m",
    }

    result = module.resolve_source_bound_documents(
        plan=plan,
        ledger=ledger,
        base_dir=tmp_path,
    )

    assert result.resolved_plan["slides"][0]["title"] == "Revenue is $2.35m"


def test_adventureworks_regression_binds_original_headline_and_waterfall_values(
    tmp_path: Path,
) -> None:
    module = load_module()
    metrics_path = tmp_path / "adventureworks_metrics.csv"
    bridge_path = tmp_path / "adventureworks_sales_bridge.csv"
    shutil.copyfile(FIXTURE_ROOT / metrics_path.name, metrics_path)
    shutil.copyfile(FIXTURE_ROOT / bridge_path.name, bridge_path)
    bundle_path = tmp_path / "evidence-bundle.json"
    write_json(
        bundle_path,
        {
            "schema_version": "clara.evidence_bundle.v1",
            "bundle_id": "adventureworks-regression",
            "artifacts": [
                {
                    "id": "adventureworks-metrics",
                    "source_id": "source-adventureworks-metrics",
                    "path": metrics_path.name,
                    "media_type": "text/csv",
                    "sha256": "",
                    "size_bytes": 0,
                    "table": {
                        "key_fields": ["metric_id"],
                        "order_by": ["display_order"],
                    },
                },
                {
                    "id": "sales-bridge",
                    "source_id": "source-sales-bridge",
                    "path": bridge_path.name,
                    "media_type": "text/csv",
                    "sha256": "",
                    "size_bytes": 0,
                    "table": {
                        "key_fields": ["row_id"],
                        "order_by": ["display_order"],
                    },
                },
            ],
        },
    )
    module.seal_evidence_bundle(bundle_path)

    def metric_binding(
        row_id: str,
        *,
        decimals: int,
        scale: str = "1",
        sign: str = "auto",
        suffix: str = "",
        grouping: bool = False,
    ) -> dict[str, Any]:
        return {
            "kind": "table_cell",
            "artifact_id": "adventureworks-metrics",
            "row_key": {"metric_id": row_id},
            "field": "value",
            "value_type": "decimal",
            "display": {
                "decimals": decimals,
                "scale": scale,
                "sign": sign,
                "suffix": suffix,
                "grouping": grouping,
            },
        }

    plan = {
        "schema_version": "clara.html_deck_plan.v2",
        "allow_bespoke_html": False,
        "evidence": {
            "bundle": {
                "path": bundle_path.name,
                "sha256": file_sha256(bundle_path),
            },
            "numeric_policy": "require_bindings",
            "bindings": {
                "sales-uplift": metric_binding(
                    "sales-uplift",
                    decimals=2,
                    scale="0.000001",
                    sign="always",
                    suffix="m",
                ),
                "margin-uplift": metric_binding(
                    "gross-margin-uplift",
                    decimals=2,
                    scale="0.000001",
                    sign="always",
                    suffix="m",
                ),
                "actual-margin": metric_binding(
                    "actual-margin-rate",
                    decimals=2,
                    scale="100",
                    suffix="%",
                ),
                "unit-variance": metric_binding("unit-variance", decimals=0),
                "scenario-units": metric_binding(
                    "scenario-units",
                    decimals=0,
                    grouping=True,
                ),
                "sales-bridge": {
                    "kind": "table_rows",
                    "artifact_id": "sales-bridge",
                    "fields": {"label": "label", "value": "value"},
                    "value_type": "records",
                },
            },
        },
        "slides": [
            {
                "id": "plan-performance",
                "layout_id": "metric-contrast",
                "title": evidence_template(
                    "The sales uplift converts into {margin} of gross margin",
                    margin=("margin-uplift", "display"),
                ),
                "chapter": "evidence",
                "chapter_label": "Evidence",
                "tone": "light",
                "notes": "Separate mechanically observed values from interpretation.",
                "source_refs": ["source-adventureworks-metrics"],
                "claim_refs": ["claim-plan-performance"],
                "slots": {
                    "title": evidence_template(
                        "The sales uplift converts into {margin} of gross margin",
                        margin=("margin-uplift", "display"),
                    ),
                    "metrics": [
                        {
                            "label": "Gross sales uplift",
                            "value": binding_reference("sales-uplift", "display"),
                            "detail": "Actual versus Plan",
                            "tone": "accent",
                            "_fragment": 1,
                        },
                        {
                            "label": "Gross-margin uplift",
                            "value": binding_reference("margin-uplift", "display"),
                            "detail": "After discounts and cost",
                            "tone": "analytical",
                            "_fragment": 2,
                        },
                        {
                            "label": "Actual margin rate",
                            "value": binding_reference("actual-margin", "display"),
                            "detail": "Net-sales basis",
                            "tone": "neutral",
                            "_fragment": 3,
                        },
                        {
                            "label": "Unit variance",
                            "value": binding_reference("unit-variance", "display"),
                            "detail": evidence_template(
                                "{units} units in both scenarios",
                                units=("scenario-units", "display"),
                            ),
                            "tone": "risk",
                            "_fragment": 4,
                        },
                    ],
                },
            },
            {
                "id": "plan-bridge",
                "layout_id": "visual-takeaway",
                "title": "The sales bridge is entirely rate-driven",
                "chapter": "evidence",
                "chapter_label": "Evidence",
                "tone": "light",
                "notes": "Explain the prepared plot view without recalculating it.",
                "source_refs": ["source-sales-bridge"],
                "claim_refs": [],
                "slots": {
                    "title": "The sales bridge is entirely rate-driven",
                    "visual": {
                        "renderer": "data_visual",
                        "spec": {
                            "type": "waterfall",
                            "title": "Plan to Actual gross sales",
                            "data": binding_reference("sales-bridge", "raw"),
                        },
                    },
                    "takeaway_label": "What it proves",
                    "takeaway": "The prepared view carries the plotted values.",
                },
            },
        ],
    }
    ledger = {
        "schema_version": "clara.html_deck_ledger.v2",
        "sources": [
            {
                "id": "source-adventureworks-metrics",
                "label": "AdventureWorks prepared metrics",
                "kind": "calculation-output",
                "locator": metrics_path.name,
                "sha256": file_sha256(metrics_path),
                "publish_locator": False,
            },
            {
                "id": "source-sales-bridge",
                "label": "AdventureWorks prepared sales bridge",
                "kind": "plot-view",
                "locator": bridge_path.name,
                "sha256": file_sha256(bridge_path),
                "publish_locator": False,
            },
        ],
        "slides": [
            {
                "slide_id": "plan-performance",
                "basis_status": "source-backed",
                "basis_note": "",
                "claims": [
                    {
                        "id": "claim-plan-performance",
                        "statement": evidence_template(
                            "Gross sales uplift is {uplift}",
                            uplift=("sales-uplift", "display"),
                        ),
                        "classification": "fact",
                        "basis_status": "source-backed",
                        "basis_note": "",
                        "source_ids": ["source-adventureworks-metrics"],
                    }
                ],
            },
            {
                "slide_id": "plan-bridge",
                "basis_status": "speaker-judgement",
                "basis_note": "Interpretation remains an advisor judgement.",
                "claims": [],
            },
        ],
    }

    result = module.resolve_source_bound_documents(
        plan=plan,
        ledger=ledger,
        base_dir=tmp_path,
    )

    metrics = result.resolved_plan["slides"][0]["slots"]["metrics"]
    assert [item["value"] for item in metrics] == [
        "+3.03m",
        "+1.14m",
        "39.10%",
        "0",
    ]
    assert metrics[3]["detail"] == "15,912 units in both scenarios"
    assert result.resolved_plan["slides"][1]["slots"]["visual"]["spec"]["data"] == [
        {"label": "Plan", "value": "28.36"},
        {"label": "Rate uplift", "value": "3.03"},
    ]


def test_source_bound_build_recompiles_and_embeds_verified_evidence(
    tmp_path: Path,
) -> None:
    module = load_module()
    work = write_source_bound_work(tmp_path, module)

    built = run_script(
        SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(tmp_path / "dist"),
    )

    assert built.returncode == 0, built.stderr or built.stdout
    report = json.loads(built.stdout)
    assert report["evidence"]["status"] == "verified"
    index_path = Path(report["output"]["index_path"])
    html_text = index_path.read_text(encoding="utf-8")
    assert 'id="claraEvidenceLedger"' in html_text
    assert '"status":"verified"' in html_text
    assert file_sha256(work / "financial-facts.csv") in html_text


def test_source_bound_build_rejects_manually_changed_display_value(
    tmp_path: Path,
) -> None:
    module = load_module()
    work = write_source_bound_work(tmp_path, module)
    slides_path = work / "slides.html"
    slides_path.write_text(
        slides_path.read_text(encoding="utf-8").replace("$25.4m", "$99.9m"),
        encoding="utf-8",
    )

    built = run_script(
        SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(tmp_path / "dist"),
    )

    assert built.returncode == 2
    assert "drifted from deterministic recompilation" in built.stderr


def test_source_bound_build_rejects_manually_changed_evidence_ledger(
    tmp_path: Path,
) -> None:
    module = load_module()
    work = write_source_bound_work(tmp_path, module)
    evidence_ledger_path = work / "evidence-ledger.json"
    evidence_ledger_path.write_text(
        evidence_ledger_path.read_text(encoding="utf-8").replace(
            '"status": "verified"',
            '"status": "not_verified"',
        ),
        encoding="utf-8",
    )

    built = run_script(
        SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(tmp_path / "dist"),
    )

    assert built.returncode == 2
    assert "evidence ledger drifted" in built.stderr
