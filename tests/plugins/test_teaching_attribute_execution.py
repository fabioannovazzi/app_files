"""Execute local assortment kit inputs; never manufacture semantic approvals.

The fixed localized model contributions below are regression fixtures. The
actual pipeline extracts, checks, calculates, renders and issues its verdict.
Live output review, voice interaction and learner understanding are separate.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tests.plugins._attribute_teaching import complete_model
from tests.plugins._teaching_release import prepared_kit, record_native_check

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/attribute-reporting/scripts"
TEXT = {
    "it": (
        "Rapporto sull’assortimento",
        "Dati fittizi per comprendere il processo. Non sono osservazioni di mercato.",
        "Prodotti nel pacchetto",
        "Il pacchetto contiene {{products}} prodotti, di cui {{recent}} nuovi arrivi e {{best}} best seller.",
        "Confronto dei nuovi arrivi",
        "La combinazione comprende {{focus}} del gruppo recente e {{baseline}} degli altri prodotti.",
        "Rivedi la definizione dei gruppi e le fonti prima di usare il rapporto.",
        "Mancano immagini e recensioni. I gruppi sono assegnati per l’esercizio; non indicano vendite, preferenze o cause.",
    ),
    "en": (
        "Assortment report",
        "Fictional data for learning the process. These are not market observations.",
        "Products in the package",
        "The package contains {{products}} products, including {{recent}} new arrivals and {{best}} best sellers.",
        "New-arrival comparison",
        "The combination represents {{focus}} of the recent group and {{baseline}} of the other products.",
        "Review the group definitions and sources before using the report.",
        "Images and reviews are absent. The groups are assigned for the exercise; they do not establish sales, preferences or causes.",
    ),
    "fr": (
        "Rapport sur l’assortiment",
        "Données fictives pour apprendre le processus. Ce ne sont pas des observations du marché.",
        "Produits du dossier",
        "Le dossier contient {{products}} produits, dont {{recent}} nouveautés et {{best}} meilleures ventes.",
        "Comparaison des nouveautés",
        "La combinaison représente {{focus}} du groupe récent et {{baseline}} des autres produits.",
        "Vérifiez la définition des groupes et les sources avant d’utiliser le rapport.",
        "Les images et avis sont absents. Les groupes sont attribués pour l’exercice ; ils n’établissent ni ventes, ni préférences, ni causes.",
    ),
    "de": (
        "Sortimentsbericht",
        "Fiktive Daten zum Erlernen des Ablaufs. Dies sind keine Marktbeobachtungen.",
        "Produkte im Paket",
        "Das Paket enthält {{products}} Produkte, darunter {{recent}} Neuheiten und {{best}} Bestseller.",
        "Vergleich der Neuheiten",
        "Die Kombination umfasst {{focus}} der neuen Gruppe und {{baseline}} der anderen Produkte.",
        "Prüfen Sie die Gruppendefinitionen und Quellen, bevor Sie den Bericht verwenden.",
        "Bilder und Bewertungen fehlen. Die Gruppen wurden für die Übung zugewiesen; sie belegen weder Verkäufe noch Präferenzen oder Ursachen.",
    ),
    "es": (
        "Informe del surtido",
        "Datos ficticios para aprender el proceso. No son observaciones del mercado.",
        "Productos del paquete",
        "El paquete contiene {{products}} productos, incluidos {{recent}} novedades y {{best}} más vendidos.",
        "Comparación de novedades",
        "La combinación representa {{focus}} del grupo reciente y {{baseline}} de los demás productos.",
        "Revisa la definición de los grupos y las fuentes antes de usar el informe.",
        "Faltan imágenes y reseñas. Los grupos se asignan para el ejercicio; no demuestran ventas, preferencias ni causas.",
    ),
}


DISPLAY = {
    "it": (
        "Stampa rapporto",
        "Confronto delle combinazioni di attributi",
        "Prodotti nel gruppo",
        "Non determinabile",
    ),
    "en": (
        "Print report",
        "Attribute combination comparison",
        "Products in group",
        "Unable to determine",
    ),
    "fr": (
        "Imprimer le rapport",
        "Comparaison des combinaisons d’attributs",
        "Produits du groupe",
        "Impossible à déterminer",
    ),
    "de": (
        "Bericht drucken",
        "Vergleich der Attributkombinationen",
        "Produkte der Gruppe",
        "Nicht feststellbar",
    ),
    "es": (
        "Imprimir informe",
        "Comparación de combinaciones de atributos",
        "Productos del grupo",
        "No se puede determinar",
    ),
}


def _load(path, name, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("language", TEXT)
@pytest.mark.parametrize("phase", ["demo", "practice"])
@prepared_kit("clara/attribute-reporting")
def test_assortment_kit_renders_native_comparisons_and_requires_independent_review(
    tmp_path, monkeypatch, language, phase, record_property
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    from courseware.library import CourseLibrary

    native = _load(
        SCRIPTS / "attribute_reporting.py", "teaching_attribute_reporting", monkeypatch
    )
    bridge = _load(
        SCRIPTS / "server_bridge_client.py", "teaching_attribute_bridge", monkeypatch
    )
    # The component must work without the development app's scraping package.
    # Exercise the real table loader; no replacement builder is injected.
    monkeypatch.setitem(sys.modules, "modules.pdp", None)
    kit = CourseLibrary(ROOT / "plugins/clara", {"attribute-reporting"}).render(
        "attribute-reporting", language, tmp_path / "kit"
    )
    archive = next(
        Path(p)
        for p in kit["source_files" if phase == "demo" else "practice_files"]
        if p.endswith(".zip")
    )
    package, output = tmp_path / "source", tmp_path / "report"
    bridge.extract_evidence_pack(archive, package)
    native.prepare_run(
        package,
        output,
        author_agent_id="synthetic-regression-author",
        language=language,
        require_browser_qa=True,
    )
    model_path = output / "report_model.json"
    model = json.loads(model_path.read_text())
    title, introduction, coverage, count_text, comparison, share_text, use, caveat = (
        TEXT[language]
    )
    model.update(
        title=title,
        subtitle=introduction,
        audience="Fictional product team",
        authoring_status="codex_complete",
    )
    for section in model["sections"]:
        section.update(title=title, summary=use, claim_ids=[], table_keys=[])
    model["sections"][0].update(
        title=coverage, summary=introduction, claim_ids=["coverage"]
    )
    model["sections"][3].update(
        title=comparison,
        claim_ids=["recent"],
        table_keys=["attribute_bundle_comparison_table"],
    )
    model["sections"][-1].update(summary=caveat)
    common = {
        "kind": "deterministic",
        "supporting_claim_ids": [],
        "confidence": "high",
        "product_ids": [],
        "caveat": caveat,
        "interpretation": use,
    }
    model["claims"] = [
        {
            **common,
            "claim_id": "coverage",
            "checker": "cohort_summary",
            "headline": coverage,
            "text_template": count_text,
            "evidence_refs": [
                {
                    "ref_id": ref,
                    "source": "summary.json",
                    "selector": {"json_path": [field]},
                    "format": "integer",
                }
                for ref, field in (
                    ("products", "product_count"),
                    ("recent", "recent_products"),
                    ("best", "top_seller_products"),
                )
            ],
        },
        {
            **common,
            "claim_id": "recent",
            "checker": "bundle_signal_emerging",
            "headline": comparison,
            "text_template": share_text,
            "evidence_refs": [
                {
                    "ref_id": ref,
                    "source": "innovation_pairs.csv",
                    "selector": {
                        "match": {
                            "bundle_key": (
                                "color=black + garment type=cardigan"
                                if phase == "demo"
                                else "color=blue + garment type=sweater"
                            )
                        },
                        "field": field,
                    },
                    "format": "percent_1",
                }
                for ref, field in (("focus", "pct_recent"), ("baseline", "pct_rest"))
            ],
        },
    ]
    complete_model(model, language, phase, common)
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2))

    native.render_report(output)
    verdict = native.finalize_report(output)

    html = (output / "report.html").read_text()
    assert title in html and introduction in html
    assert f'<html lang="{language}">' in html
    button, table_title, count_column, verdict_label = DISPLAY[language]
    assert f">{button}</button>" in html
    assert table_title in html and f">{count_column}</th>" in html
    assert f"<strong>{verdict_label}</strong>" in html
    assert 'data-correctness-verdict="pending"' not in html
    table_html = (
        output / "evidence/attribute_tables/attribute_bundle_comparison_table.html"
    ).read_text()
    assert f'<html lang="{language}">' in table_html
    assert table_title in table_html and f">{count_column}</th>" in table_html
    assert ("75.0%" if phase == "demo" else "100.0%") in html
    assert ("6.2%" if phase == "demo" else "12.5%") in html
    assert verdict["basis"]["mechanical_claims"] == "pass"
    assert verdict["basis"]["html_parity"] == "pass"
    assert verdict["basis"]["mapping_review"] == "not_applicable"
    assert verdict["label"] == "Unable to determine"
    review = json.loads((output / "semantic_review.json").read_text())
    assert review["overall_verdict"] == "unable_to_determine"
    assert review["claim_reviews"] == []
    assert not (output / "browser_qa.json").is_file()
    assert not (output / "mapping_submission_receipt.json").is_file()
    assert (output / "claim_ledger.json").is_file()
    with (
        output / "evidence/attribute_tables/product_signal_evidence_table.csv"
    ).open() as source:
        products = list(csv.DictReader(source))
    assert products[0]["attributes"] == "black | cardigan"
    assert "Sparse resolved attributes" not in products[0]["caveat"]
    record_native_check(
        record_property,
        root=ROOT,
        product="clara",
        workflow="attribute-reporting",
        language=language,
        phase=phase,
    )


@pytest.mark.parametrize("language", ["pt", "", "<script>", None])
def test_prepare_rejects_unsupported_language_before_writing(
    tmp_path, monkeypatch, language
):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    native = _load(
        SCRIPTS / "attribute_reporting.py", "attribute_invalid_language", monkeypatch
    )
    with pytest.raises(native.ContractError, match="Report language must"):
        native.prepare_run(
            tmp_path / "missing-input",
            tmp_path / "report",
            author_agent_id="synthetic",
            language=language,
        )
    assert not (tmp_path / "report").exists()
