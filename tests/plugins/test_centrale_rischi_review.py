from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "centrale-rischi-review"
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from centrale_rischi_core import (  # noqa: E402
    COMMENTARY_SCHEMA,
    CentraleRischiContractError,
    build_analysis,
    build_inspection,
    build_model_context,
    finalize_commentary,
    load_source_tables,
    render_html,
    write_excel,
)


def _write_source(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "CR"
    sheet.append(
        (
            "Mese",
            "Intermediario",
            "Categoria",
            "Durata residua",
            "Accordato",
            "Operativo",
            "Utilizzato",
            "Garanzia",
            "Garantito",
            "Pregiudizievole",
        )
    )
    for row in (
        (
            "2025-01",
            "Banca A",
            "Autoliquidante",
            "Entro 12 mesi",
            1000,
            900,
            800,
            "Personale",
            300,
            "",
        ),
        ("2025-01", "Banca B", "A scadenza", "Oltre 5 anni", 600, 600, 500, "", 0, ""),
        (
            "2025-02",
            "Banca A",
            "Autoliquidante",
            "Entro 12 mesi",
            1000,
            900,
            950,
            "Personale",
            300,
            "",
        ),
        (
            "2025-02",
            "Banca B",
            "A scadenza",
            "Oltre 5 anni",
            600,
            600,
            450,
            "Reale",
            200,
            "Protesto segnalato",
        ),
        ("2025-02", "Banca C", "Sofferenze", "Da 1 a 5 anni", 100, 0, 100, "", 0, ""),
    ):
        sheet.append(row)
    workbook.save(path)


def _reviewed_recipe(inspection: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "vera.centrale_rischi_recipe.v1",
        "workflow_id": "centrale-rischi-review",
        "inventory_sha256": inspection["inventory_sha256"],
        "entity": "Synthetic S.r.l.",
        "currency": "EUR",
        "analysis_mode": "trend",
        "analysis_objective": "Explain current exposure and recent movement.",
        "audience": "professional",
        "source_kind": "tabular_export",
        "source_document_sha256": "",
        "table_id": inspection["tables"][0]["table_id"],  # type: ignore[index]
        "columns": {
            "reference_month": "Mese",
            "intermediary": "Intermediario",
            "risk_category": "Categoria",
            "residual_duration": "Durata residua",
            "granted": "Accordato",
            "operational_granted": "Operativo",
            "used": "Utilizzato",
            "guarantee_type": "Garanzia",
            "guaranteed_amount": "Garantito",
            "prejudicial_event": "Pregiudizievole",
        },
        "value_mappings": {
            "maturity": {
                "Entro 12 mesi": "short",
                "Da 1 a 5 anni": "medium",
                "Oltre 5 anni": "long",
            },
            "exposure_family": {
                "Autoliquidante": "performing",
                "A scadenza": "performing",
                "Sofferenze": "suffering",
            },
        },
        "control_totals": {"used": "1500"},
        "control_tolerance": "0.01",
        "mapping_review": {
            "status": "reviewed",
            "reviewer": "Test reviewer",
            "reviewed_at": "2026-08-25T12:00:00+02:00",
        },
    }


def _analysis_for(path: Path) -> tuple[dict[str, object], dict[str, object]]:
    tables = load_source_tables([path])
    inspection, _, _ = build_inspection(tables)
    return build_analysis(tables, _reviewed_recipe(inspection)), inspection


def test_inspection_does_not_assign_semantic_roles(tmp_path: Path) -> None:
    source = tmp_path / "cr.xlsx"
    _write_source(source)

    inspection, control, recipe = build_inspection(load_source_tables([source]))

    assert inspection["semantic_roles_assigned"] is False
    assert recipe["mapping_review"]["status"] == "pending"
    assert recipe["value_mappings"] == {"maturity": {}, "exposure_family": {}}
    assert Path(control["tables"][0]["absolute_path"]).is_absolute()
    assert "absolute_path" not in json.dumps(inspection)


def test_analysis_calculates_maturities_overruns_guarantees_and_kpis(
    tmp_path: Path,
) -> None:
    source = tmp_path / "cr.xlsx"
    _write_source(source)

    analysis, _ = _analysis_for(source)
    metrics = {item["metric_id"]: item for item in analysis["metrics"]}
    maturity = {item["maturity"]: item for item in analysis["maturity_summary"]}
    categories = {
        item["risk_category"]: item for item in analysis["risk_category_summary"]
    }

    assert analysis["status"] == "complete"
    assert metrics["cr.total_used"]["value"] == "1500"
    assert metrics["cr.available_resources"]["value"] == "150"
    assert metrics["cr.overrun_amount"]["value"] == "50"
    assert metrics["cr.overrun_count"]["value"] == 1
    assert metrics["cr.used_mom_change"]["value"] == "200"
    assert "cr.utilization_pct" not in metrics
    assert metrics["financial.dscr"]["availability"] == "unavailable"
    assert maturity["short"]["used"] == "950"
    assert maturity["medium"]["used"] == "100"
    assert maturity["long"]["used"] == "450"
    assert categories["Autoliquidante"]["utilization_pct"] == "105.56"
    assert categories["A scadenza"]["utilization_pct"] == "75"
    assert len(analysis["guarantees"]) == 2
    assert len(analysis["overruns"]) == 1
    assert len(analysis["prejudicial_events"]) == 1
    assert all(row["exposure_family"] != "suffering" for row in analysis["overruns"])


def test_analysis_rejects_unreviewed_or_incomplete_semantic_mapping(
    tmp_path: Path,
) -> None:
    source = tmp_path / "cr.xlsx"
    _write_source(source)
    tables = load_source_tables([source])
    inspection, _, _ = build_inspection(tables)
    recipe = _reviewed_recipe(inspection)
    del recipe["value_mappings"]["maturity"]["Oltre 5 anni"]

    with pytest.raises(CentraleRischiContractError, match="unmapped residual_duration"):
        build_analysis(tables, recipe)


def test_pdf_derived_rows_require_layout_provenance(tmp_path: Path) -> None:
    source = tmp_path / "cr.xlsx"
    _write_source(source)
    tables = load_source_tables([source])
    inspection, _, _ = build_inspection(tables)
    recipe = _reviewed_recipe(inspection)
    recipe["source_kind"] = "native_pdf_extraction"
    recipe["source_document_sha256"] = "a" * 64

    with pytest.raises(CentraleRischiContractError, match="provenance mapping"):
        build_analysis(tables, recipe)


def test_reconciled_mode_requires_external_evidence_adapter(tmp_path: Path) -> None:
    source = tmp_path / "cr.xlsx"
    _write_source(source)
    tables = load_source_tables([source])
    inspection, _, _ = build_inspection(tables)
    recipe = _reviewed_recipe(inspection)
    recipe["analysis_mode"] = "reconciled"

    with pytest.raises(CentraleRischiContractError, match="external-evidence"):
        build_analysis(tables, recipe)


def test_failed_declared_control_blocks_analysis(tmp_path: Path) -> None:
    source = tmp_path / "cr.xlsx"
    _write_source(source)
    tables = load_source_tables([source])
    inspection, _, _ = build_inspection(tables)
    recipe = _reviewed_recipe(inspection)
    recipe["control_totals"]["used"] = "1499"

    analysis = build_analysis(tables, recipe)

    assert analysis["status"] == "blocked"
    assert analysis["controls"][0]["status"] == "failed"


def test_model_context_is_bounded_and_excludes_source_paths(tmp_path: Path) -> None:
    source = tmp_path / "cr.xlsx"
    _write_source(source)
    analysis, _ = _analysis_for(source)

    context = build_model_context(analysis)

    assert "exposures" not in context
    assert "absolute_path" not in json.dumps(context)
    assert len(context["top_overruns"]) <= 20
    assert len(context["monthly_series"]) <= 36


def test_commentary_requires_existing_metric_references(tmp_path: Path) -> None:
    source = tmp_path / "cr.xlsx"
    _write_source(source)
    analysis, _ = _analysis_for(source)
    commentary = {
        "schema_version": COMMENTARY_SCHEMA,
        "workflow_id": "centrale-rischi-review",
        "observations": [{"text": "Utilizzo elevato.", "metric_ids": ["missing"]}],
        "hypotheses": [],
        "questions": [],
        "limitations": [],
    }

    with pytest.raises(CentraleRischiContractError, match="existing metric_ids"):
        finalize_commentary(analysis, commentary)


def test_renderers_create_reviewable_html_and_excel(tmp_path: Path) -> None:
    source = tmp_path / "cr.xlsx"
    _write_source(source)
    analysis, _ = _analysis_for(source)
    output = tmp_path / "analysis.xlsx"

    write_excel(output, analysis)
    rendered = render_html(analysis)
    workbook = load_workbook(output, read_only=True)

    assert "draft_pending_professional_review" in rendered
    assert "Centrale Rischi" in rendered
    assert set(workbook.sheetnames) == {
        "KPI",
        "Scadenze",
        "Categorie",
        "Esposizioni",
        "Garanzie",
        "Sconfinamenti",
        "Pregiudizievoli",
        "Serie mensile",
        "Controlli",
    }


def test_public_page_and_privacy_surface_are_registered() -> None:
    page = (
        ROOT / "static" / "shared" / "centrale-rischi-review" / "index.html"
    ).read_text(encoding="utf-8")
    manifest = json.loads(
        (
            ROOT
            / "plugins"
            / "vera"
            / "privacy"
            / "workstreams"
            / "centrale-rischi-review.json"
        ).read_text(encoding="utf-8")
    )

    main = page[page.index('<main class="page-shell"') : page.index("</main>")]
    assert 'data-model-data-workflow="centrale-rischi-review"' in main
    assert 'data-model-data-status="relevant"' in main
    assert main.rstrip().endswith("</section>")
    assert "Quali dati arrivano al modello" in page
    assert "What data reaches the model" in page
    assert manifest["workstream"] == "centrale-rischi-review"
    assert manifest["external_boundaries"] == []
