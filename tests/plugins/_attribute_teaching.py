"""Authored model contribution for the fictional complete report regression.

These are test-only narratives, not distributed answers or review approvals.
The pipeline resolves every displayed quantity from the current input package.
"""

from __future__ import annotations

__all__ = ["complete_model"]

COPY = {
    "it": [
        "Best seller",
        "Presenza dei marchi",
        "Confronto tra gruppi",
        "Prodotti di esempio",
        "Metodo e limiti",
        "Cardigan neri",
        "Maglioni blu",
        "I cardigan neri rappresentano {{focus}} dei best seller e {{baseline}} degli altri prodotti.",
        "Riva rappresenta {{catalog}} del catalogo e {{cohort}} del gruppo best seller.",
        "Confronta le combinazioni nei due gruppi: una presenza maggiore non dimostra vendite o domanda futura.",
        "Apri i prodotti collegati per risalire agli attributi e ai gruppi assegnati nel caso fittizio. Le immagini non sono disponibili.",
    ],
    "en": [
        "Best sellers",
        "Brand presence",
        "Comparison between groups",
        "Example products",
        "Method and limitations",
        "Black cardigans",
        "Blue sweaters",
        "Black cardigans represent {{focus}} of best sellers and {{baseline}} of other products.",
        "Riva represents {{catalog}} of the catalogue and {{cohort}} of the best-seller group.",
        "Compare the combinations in both groups: greater presence does not establish sales or future demand.",
        "Open the linked products to trace the attributes and group assignments in the fictional case. Images are unavailable.",
    ],
    "fr": [
        "Meilleures ventes",
        "Présence des marques",
        "Comparaison entre groupes",
        "Exemples de produits",
        "Méthode et limites",
        "Cardigans noirs",
        "Pulls bleus",
        "Les cardigans noirs représentent {{focus}} des meilleures ventes et {{baseline}} des autres produits.",
        "Riva représente {{catalog}} du catalogue et {{cohort}} du groupe des meilleures ventes.",
        "Comparez les combinaisons dans les deux groupes : une présence supérieure ne prouve ni ventes ni demande future.",
        "Ouvrez les produits liés pour retrouver les attributs et groupes attribués dans le cas fictif. Les images sont indisponibles.",
    ],
    "de": [
        "Bestseller",
        "Markenpräsenz",
        "Vergleich der Gruppen",
        "Produktbeispiele",
        "Methode und Grenzen",
        "Schwarze Cardigans",
        "Blaue Pullover",
        "Schwarze Cardigans machen {{focus}} der Bestseller und {{baseline}} der übrigen Produkte aus.",
        "Riva stellt {{catalog}} des Katalogs und {{cohort}} der Bestsellergruppe.",
        "Vergleichen Sie die Kombinationen beider Gruppen: Eine stärkere Präsenz belegt weder Verkäufe noch künftige Nachfrage.",
        "Öffnen Sie die verknüpften Produkte, um Attribute und Gruppenzuordnung des fiktiven Falls nachzuvollziehen. Bilder fehlen.",
    ],
    "es": [
        "Más vendidos",
        "Presencia de marcas",
        "Comparación entre grupos",
        "Productos de ejemplo",
        "Método y límites",
        "Cárdigans negros",
        "Jerséis azules",
        "Los cárdigans negros representan {{focus}} de los más vendidos y {{baseline}} de los demás productos.",
        "Riva representa {{catalog}} del catálogo y {{cohort}} del grupo de más vendidos.",
        "Compara las combinaciones de ambos grupos: una mayor presencia no demuestra ventas ni demanda futura.",
        "Abre los productos vinculados para comprobar los atributos y grupos asignados en el caso ficticio. No hay imágenes disponibles.",
    ],
}


def complete_model(model, language, phase, common):
    """Fill the normal analytical sections using explicit source-bound claims."""
    (
        winning,
        brands,
        bridge,
        products,
        method,
        black,
        blue,
        winning_text,
        brand_text,
        compare,
        product_text,
    ) = COPY[language]
    sections = {s["section_id"]: s for s in model["sections"]}
    sections["winning_now"].update(title=winning, summary=black, claim_ids=["winning"])
    sections["brand_context"].update(title=brands, summary=compare, claim_ids=["brand"])
    sections["winner_emerging_bridge"].update(
        title=bridge, summary=compare, claim_ids=[]
    )
    sections["product_evidence"].update(
        title=products, summary=product_text, claim_ids=[]
    )
    sections["method_and_caveats"]["title"] = method
    recent = model["claims"][1]
    recent["headline"] = black if phase == "demo" else blue
    recent["text_template"] = recent["headline"] + ": " + recent["text_template"]
    recent["product_ids"] = (
        ["fictional-01", "fictional-02"]
        if phase == "demo"
        else ["fictional-07", "fictional-08"]
    )
    model["claims"].extend(
        [
            {
                **common,
                "claim_id": "winning",
                "checker": "bundle_signal_winning_now",
                "headline": black,
                "text_template": winning_text,
                "product_ids": ["fictional-01", "fictional-02"],
                "evidence_refs": [
                    {
                        "ref_id": ref,
                        "source": "top_seller_pairs.csv",
                        "selector": {
                            "match": {
                                "bundle_key": "color=black + garment type=cardigan"
                            },
                            "field": field,
                        },
                        "format": "percent_1",
                    }
                    for ref, field in [
                        ("focus", "pct_top_seller"),
                        ("baseline", "pct_other"),
                    ]
                ],
            },
            {
                **common,
                "claim_id": "brand",
                "checker": "brand_fact",
                "headline": brands,
                "text_template": brand_text,
                "evidence_refs": [
                    {
                        "ref_id": ref,
                        "source": "top_seller_brand_comparison.csv",
                        "selector": {"match": {"brand": "Riva"}, "field": field},
                        "format": "percent_1",
                    }
                    for ref, field in [
                        ("catalog", "catalog_share"),
                        ("cohort", "top_seller_share_of_cohort"),
                    ]
                ],
            },
        ]
    )
    bridge_copy = {
        "it": [
            "Nel primo esempio la stessa combinazione di cardigan neri compare nei due confronti.",
            "Nella prova i best seller restano cardigan neri, mentre il confronto dei nuovi arrivi evidenzia maglioni blu. Non sono lo stesso segnale.",
        ],
        "en": [
            "In the first example the same black-cardigan combination appears in both comparisons.",
            "In practice the best sellers remain black cardigans, while the new-arrival comparison highlights blue sweaters. These are different signals.",
        ],
        "fr": [
            "Dans le premier exemple, la même combinaison de cardigans noirs apparaît dans les deux comparaisons.",
            "Dans l’exercice, les meilleures ventes restent les cardigans noirs, tandis que les nouveautés font ressortir les pulls bleus. Ce sont des signaux différents.",
        ],
        "de": [
            "Im ersten Beispiel erscheint dieselbe Kombination schwarzer Cardigans in beiden Vergleichen.",
            "In der Übung bleiben schwarze Cardigans die Bestseller, während der Neuheitenvergleich blaue Pullover hervorhebt. Es sind unterschiedliche Signale.",
        ],
        "es": [
            "En el primer ejemplo, la misma combinación de cárdigans negros aparece en ambas comparaciones.",
            "En la práctica, los más vendidos siguen siendo cárdigans negros, mientras las novedades destacan jerséis azules. Son señales distintas.",
        ],
    }
    local_copy = {
        "it": "Leggi le schede e confrontale con la tabella dei prodotti. Immagini e siti reali non fanno parte del caso fittizio.",
        "en": "Read the cards and compare them with the product table. Images and real websites are not part of the fictional case.",
        "fr": "Lisez les fiches et comparez-les au tableau des produits. Les images et sites réels ne font pas partie du cas fictif.",
        "de": "Lesen Sie die Karten und vergleichen Sie sie mit der Produkttabelle. Bilder und reale Websites gehören nicht zum fiktiven Fall.",
        "es": "Lee las fichas y compáralas con la tabla de productos. Las imágenes y los sitios reales no forman parte del caso ficticio.",
    }
    sections["winner_emerging_bridge"]["summary"] = (
        bridge_copy[language][phase == "practice"] + " " + compare
    )
    sections["product_evidence"]["summary"] = local_copy[language]
    model["featured_products"] = [
        {
            "product_id": "fictional-01",
            "role": "winning_now",
            "rationale": black,
            "supporting_claim_ids": ["winning"],
        },
        {
            "product_id": "fictional-02" if phase == "demo" else "fictional-07",
            "role": "emerging_signal",
            "rationale": black if phase == "demo" else blue,
            "supporting_claim_ids": ["recent"],
        },
    ]
