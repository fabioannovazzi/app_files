"""Build fictional existing-package inputs with the current comparison engine.

These packages are inputs to Attribute Reporting, not finished reports or
server receipts. The assigned cohorts and product descriptions are authored
fiction. Native helpers calculate and audit every supplied comparison.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import polars as pl

__all__ = ["build", "main"]

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import build_retailer_category_evidence_pack as native  # noqa: E402

DESTINATION = Path(__file__).parent / "inputs/attributes"
LABELS = {
    "it": ("Rivenditore fittizio", "Maglieria", "Capo fittizio"),
    "en": ("Fictional retailer", "Knitwear", "Fictional garment"),
    "fr": ("Distributeur fictif", "Maille", "Vêtement fictif"),
    "de": ("Fiktiver Händler", "Strickwaren", "Fiktives Kleidungsstück"),
    "es": ("Minorista ficticio", "Prendas de punto", "Prenda ficticia"),
}
WARNINGS = {
    "it": (
        "Dati fittizi per la lezione: non rappresentano un rivenditore, osservazioni di mercato, una raccolta web o una ricevuta del server.",
        "Il pacchetto non contiene recensioni dei consumatori né immagini dei prodotti.",
    ),
    "en": (
        "Fictional teaching input: no retailer, market observation, web collection or server receipt is represented.",
        "Consumer reviews and product images are not included in this package.",
    ),
    "fr": (
        "Données fictives pour la leçon : elles ne représentent aucun distributeur, observation de marché, collecte web ou reçu du serveur.",
        "Le dossier ne contient ni avis de consommateurs ni images des produits.",
    ),
    "de": (
        "Fiktive Schulungsdaten: keine Darstellung eines echten Händlers, einer Marktbeobachtung, Web-Erhebung oder Serverbestätigung.",
        "Das Paket enthält keine Verbraucherbewertungen oder Produktbilder.",
    ),
    "es": (
        "Datos ficticios para la lección: no representan un minorista, observaciones del mercado, una captura web ni un recibo del servidor.",
        "El paquete no contiene opiniones de consumidores ni imágenes de productos.",
    ),
}


def _package(language: str, phase: str) -> bytes:
    retailer_label, category_label, product_label = LABELS[language]
    recent = {1, 2, 4, 6} if phase == "demo" else {7, 8, 9, 10}
    rows = [
        {
            "listing_identity": f"fictional-{i:02}",
            "parent_product_id": f"fictional-{i:02}",
            "product_name": f"{product_label} {i:02}",
            "brand": "Riva" if i % 2 else "Lago",
            "color": "black" if i <= 4 else ("blue" if i <= 10 else "cream"),
            "garment type": "cardigan" if i <= 4 else "sweater",
            "listing_status": "recent" if i in recent else "rest",
            "top_seller_status": "top_seller" if i in {1, 2, 3, 5} else "other",
            "sale_pressure_status": "other",
            "pdp_url": f"https://example.invalid/products/fictional-{i:02}",
        }
        for i in range(1, 21)
    ]
    matrix = pl.DataFrame(rows)
    attributes = ["color", "garment type"]
    frames = {
        "product_filter_matrix": matrix,
        "recent_products": matrix.filter(pl.col("listing_status") == "recent"),
        "top_seller_products": matrix.filter(
            pl.col("top_seller_status") == "top_seller"
        ),
        "sale_pressure_products": matrix.filter(
            pl.col("sale_pressure_status") == "sale_pressure"
        ),
        "top_seller_brand_comparison": native._build_brand_top_seller_comparison(
            matrix
        ),
    }
    for name, status, focus, baseline in (
        ("innovation", "listing_status", "recent", "rest"),
        ("top_seller", "top_seller_status", "top_seller", "other"),
        ("sale_pressure", "sale_pressure_status", "sale_pressure", "other"),
    ):
        for size, label in ((2, "pairs"), (3, "triples")):
            frames[f"{name}_{label}"] = native._build_focus_bundle_signals(
                df=matrix,
                attribute_columns=attributes,
                bundle_size=size,
                status_column=status,
                focus_label=focus,
                other_label=baseline,
                focus_prefix=focus,
                other_prefix=baseline,
            )
    integrity = native._build_launch_package_integrity_audit(
        retailer="fictional",
        category_key="teaching-knitwear",
        bundle_attribute_columns=attributes,
        **{
            key: frame
            for key, frame in frames.items()
            if key != "top_seller_brand_comparison"
        },
    )
    if integrity["status"] != "pass":
        raise ValueError(
            f"Fictional source package failed its native audit: {integrity}"
        )
    # A reproducible source input carries check results, not an execution-time
    # claim. Retain every check and issue; omit only the volatile timestamp.
    integrity.pop("generated_at")
    integrity["teaching_input"] = True
    summary: dict[str, Any] = {
        "retailer": "fictional",
        "retailer_label": retailer_label,
        "category_key": "teaching-knitwear",
        "category_label": category_label,
        "product_count": 20,
        "recent_products": 4,
        "top_seller_products": 4,
        "recent_definition": "The new-arrivals cohort explicitly assigned in this fictional source matrix.",
        "top_seller_definition": "The best-seller cohort explicitly assigned in this fictional source matrix; no sales quantities are supplied.",
        "diagnostic_warnings": [
            {"code": code, "message": message}
            for code, message in zip(
                ("fictional_teaching_data", "no_consumer_reviews"),
                WARNINGS[language],
                strict=True,
            )
        ],
    }
    manifest = {
        "files": {
            **{key: f"{key}.csv" for key in frames},
            "summary": "summary.json",
            "integrity": "package_integrity.json",
        },
        "retailer": "fictional",
        "category_key": "teaching-knitwear",
        "data_origin": "authored_fictional_input",
        "server_receipts": False,
    }
    files = {
        f"{key}.csv": frame.write_csv().encode("utf-8") for key, frame in frames.items()
    }
    for name, value in (
        ("summary", summary),
        ("pack_manifest", manifest),
        ("package_integrity", integrity),
    ):
        files[f"{name}.json"] = (
            json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 9, 14, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100600 << 16
            archive.writestr(entry, data)
    return stream.getvalue()


def build(*, check: bool = False) -> None:
    """Build or compare the exact ten source archives without model/API calls."""
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for language in LABELS:
        for phase in ("demo", "practice"):
            path = DESTINATION / f"assortment-{phase}-{language}.zip"
            expected = _package(language, phase)
            if check:
                if not path.is_file() or path.read_bytes() != expected:
                    raise ValueError(
                        f"Stale Attribute Reporting teaching input: {path}"
                    )
            else:
                path.write_bytes(expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    build(check=parser.parse_args().check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
