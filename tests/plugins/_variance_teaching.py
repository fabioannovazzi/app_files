"""Authored Codex interpretations for the fictional variance regression case.

These test-only notes exercise the normal delivery stage from native outputs.
They are not packaged answers, model calls, or professional approvals.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

__all__ = ["review_context", "write_variance_review"]

COPY = {
    "it": {
        "title": "Confrontare il risultato operativo con il budget",
        "perimeter": "Caso fittizio Officina Arco, una sola impresa; stessi mesi del 2026 nelle due versioni.",
        "signs": "Ricavi positivi e costi negativi; un aumento del risultato operativo è favorevole.",
        "materiality": "Nessuna soglia per questo esercizio; includere tutte le voci fornite.",
        "read": "Il risultato operativo supera il budget. Il contributo positivo dei ricavi è in parte assorbito da maggiori costi del venduto e spese operative. Le voci restano quelle del file: Revenue indica ricavi, COGS costo del venduto e Operating expenses spese operative.",
        "monthly": "Il dettaglio mensile mostra un contributo favorevole di gennaio e uno sfavorevole di febbraio. Nel secondo esercizio marzo aggiunge un contributo favorevole. Il nuovo risultato riguarda tre mesi: confrontalo con la versione precedente senza sostituirla.",
        "review": "I totali concordano con il prospetto fittizio fornito e tutti i contributi si riconciliano. Il file contiene solo importi: non permette di separare prezzo, volume e mix né di provare le cause commerciali. Prima dell’uso rivedi perimetro, segni, fonti e interpretazione; l’approvazione professionale e la scelta di una sequenza alternativa restano in sospeso.",
        "next": "Apri prima il report e il confronto per voce, poi il dettaglio mensile. Per ripetere, fornisci un nuovo file con budget e consuntivo degli stessi mesi, valuta e significato delle colonne. Nessun invio è previsto.",
        "totals": "Risultato nativo in EUR",
        "month": "Dettaglio mensile",
        "links": "File effettivi",
        "sweep": "Revisione delle sequenze alternative",
        "selection": "Per spiegare il risultato usa prima il confronto per voce. Nel primo esercizio l’alternativa 2 espone i ricavi aggregati e le singole voci di costo; l’alternativa 1 è più compatta ma mescola voce e mese. Nel secondo esercizio l’alternativa 3 segue i mesi, separando ricavi e costi di marzo. Sono letture proposte, non approvazioni.",
        "residual": "Ogni riga sottrae contributi già mostrati: una riga successiva Month o Category non è il totale indipendente di quel mese o di quella voce. Gli elevati residui delle altre sequenze lasciano fuori contributi importanti e le rendono meno adatte alla prima spiegazione. Nessuna sequenza dimostra una causa economica.",
        "small": "I pannelli per voce confermano che l’aumento dei ricavi compensa i due contributi negativi dei costi. Non presentare quei pannelli come effetti di prezzo o quantità.",
    },
    "en": {
        "title": "Compare operating profit with budget",
        "perimeter": "Fictional Officina Arco, one company; identical supplied 2026 months in both scenarios.",
        "signs": "Positive revenue and negative costs; higher operating profit is favorable.",
        "materiality": "No threshold for this exercise; retain every supplied category.",
        "read": "Operating profit exceeds budget. The positive revenue contribution is partly absorbed by higher cost of goods sold and operating expenses. Category names retain the source labels: Revenue, COGS and Operating expenses.",
        "monthly": "Monthly detail shows a favorable January contribution and an adverse February contribution. In the second exercise March adds a favorable contribution. The new result covers three months: compare it with the retained earlier version.",
        "review": "The totals match the supplied fictional statement and all contributions reconcile. The file contains amounts only: it cannot separate price, volume and mix or prove commercial causes. Review scope, signs, sources and interpretation before use; professional approval and the choice of an alternative sequence remain pending.",
        "next": "Open the report and category comparison first, then the monthly detail. To repeat, provide a new file with budget and actual for the same months, currency and column meanings. Nothing is sent.",
        "totals": "Native result in EUR",
        "month": "Monthly detail",
        "links": "Actual files",
        "sweep": "Review of alternative sequences",
        "selection": "Explain the result first through the category comparison. In the first exercise alternative 2 shows aggregate revenue and individual cost lines; alternative 1 is more compact but mixes category and month. In the second exercise alternative 3 follows months, separating March revenue and costs. These are proposed readings, not approvals.",
        "residual": "Each row removes contributions already shown: a later Month or Category row is not that month's or category's independent total. Large residuals in other sequences leave important contributions outside the selected rows and make them less useful for the first explanation. No sequence proves an economic cause.",
        "small": "The category panels confirm that increased revenue offsets the two adverse cost contributions. Do not describe those panels as price or quantity effects.",
    },
    "fr": {
        "title": "Comparer le résultat opérationnel au budget",
        "perimeter": "Cas fictif Officina Arco, une seule entreprise ; mêmes mois de 2026 dans les deux scénarios.",
        "signs": "Produits positifs et charges négatives ; une hausse du résultat opérationnel est favorable.",
        "materiality": "Aucun seuil pour cet exercice ; conserver toutes les rubriques fournies.",
        "read": "Le résultat opérationnel dépasse le budget. L’apport positif des produits est partiellement absorbé par la hausse du coût des ventes et des charges opérationnelles. Les noms restent ceux du fichier : Revenue désigne les produits, COGS le coût des ventes et Operating expenses les charges opérationnelles.",
        "monthly": "Le détail mensuel montre un apport favorable en janvier et défavorable en février. Dans le second exercice, mars ajoute un apport favorable. Le nouveau résultat porte sur trois mois : comparez-le à la première version conservée.",
        "review": "Les totaux concordent avec le relevé fictif fourni et les contributions se rapprochent. Le fichier ne contient que des montants : il ne permet ni de distinguer les effets de prix, volume et mix, ni d’établir les causes commerciales. Avant utilisation, revoyez périmètre, signes, sources et interprétation ; l’approbation professionnelle et le choix d’une séquence restent en attente.",
        "next": "Ouvrez d’abord le rapport et la comparaison par rubrique, puis le détail mensuel. Pour recommencer, fournissez budget et réalisé sur les mêmes mois, devise et sens des colonnes. Aucun envoi n’est effectué.",
        "totals": "Résultat natif en EUR",
        "month": "Détail mensuel",
        "links": "Fichiers produits",
        "sweep": "Revue des séquences alternatives",
        "selection": "Expliquez d’abord le résultat par rubrique. Dans le premier exercice, l’alternative 2 présente les produits agrégés et les charges détaillées ; l’alternative 1 est plus compacte mais mélange rubrique et mois. Dans le second exercice, l’alternative 3 suit les mois et sépare produits et charges de mars. Ce sont des lectures proposées, sans approbation.",
        "residual": "Chaque ligne retire les contributions déjà présentées : une ligne Month ou Category ultérieure ne représente pas le total indépendant du mois ou de la rubrique. Les soldes élevés d’autres séquences laissent des contributions importantes hors des lignes sélectionnées, ce qui les rend moins utiles pour la première explication. Aucune séquence ne prouve une cause économique.",
        "small": "Les panneaux par rubrique confirment que la hausse des produits compense les deux contributions défavorables des charges. Ne les décrivez pas comme des effets de prix ou de quantité.",
    },
    "de": {
        "title": "Operatives Ergebnis und Budget vergleichen",
        "perimeter": "Fiktiver Fall Officina Arco, ein Unternehmen; dieselben bereitgestellten Monate 2026 in beiden Szenarien.",
        "signs": "Positive Erlöse und negative Kosten; ein höheres operatives Ergebnis ist günstig.",
        "materiality": "Keine Schwelle für diese Übung; alle bereitgestellten Positionen berücksichtigen.",
        "read": "Das operative Ergebnis übertrifft das Budget. Der positive Umsatzbeitrag wird teilweise durch höhere Umsatzkosten und betriebliche Aufwendungen aufgezehrt. Die Namen entsprechen der Quelldatei: Revenue steht für Erlöse, COGS für Umsatzkosten und Operating expenses für betriebliche Aufwendungen.",
        "monthly": "Das Monatsdetail zeigt einen günstigen Beitrag im Januar und einen ungünstigen im Februar. In der zweiten Übung kommt im März ein günstiger Beitrag hinzu. Das neue Ergebnis umfasst drei Monate; vergleichen Sie es mit der aufbewahrten ersten Fassung.",
        "review": "Die Summen stimmen mit der fiktiven Ausgangsaufstellung überein; alle Beiträge lassen sich abstimmen. Die Datei enthält nur Beträge und trennt keine Preis-, Volumen- oder Mixeffekte. Wirtschaftliche Ursachen sind nicht belegt. Prüfen Sie Umfang, Vorzeichen, Quellen und Interpretation; fachliche Freigabe und Auswahl einer alternativen Folge stehen noch aus.",
        "next": "Öffnen Sie zunächst Bericht und Positionsvergleich, danach das Monatsdetail. Für eine Wiederholung liefern Sie Budget und Ist für dieselben Monate, die Währung und die Bedeutung der Spalten. Es erfolgt kein Versand.",
        "totals": "Natives Ergebnis in EUR",
        "month": "Monatsdetail",
        "links": "Erstellte Dateien",
        "sweep": "Prüfung alternativer Beitragsfolgen",
        "selection": "Erklären Sie das Ergebnis zuerst nach Position. In der ersten Übung zeigt Alternative 2 den Gesamtumsatz und einzelne Kostenpositionen; Alternative 1 ist kompakter, mischt aber Position und Monat. In der zweiten Übung folgt Alternative 3 den Monaten und trennt Erlöse und Kosten im März. Dies sind vorgeschlagene Lesarten, keine Freigaben.",
        "residual": "Jede Zeile zieht zuvor gezeigte Beiträge ab. Eine spätere Month- oder Category-Zeile ist daher nicht die eigenständige Summe dieses Monats oder dieser Position. Hohe Restbeträge anderer Folgen lassen wichtige Beiträge außerhalb der ausgewählten Zeilen und sind für die erste Erklärung weniger hilfreich. Keine Folge belegt wirtschaftliche Ursachen.",
        "small": "Die Positionsdiagramme bestätigen, dass höhere Erlöse die beiden ungünstigen Kostenbeiträge ausgleichen. Beschreiben Sie die Diagramme nicht als Preis- oder Mengeneffekte.",
    },
    "es": {
        "title": "Comparar resultado operativo y presupuesto",
        "perimeter": "Caso ficticio Officina Arco, una empresa; mismos meses aportados de 2026 en ambos escenarios.",
        "signs": "Ingresos positivos y costes negativos; un mayor resultado operativo es favorable.",
        "materiality": "Sin umbral en este ejercicio; conservar todas las partidas aportadas.",
        "read": "El resultado operativo supera el presupuesto. La contribución positiva de los ingresos queda parcialmente absorbida por mayores costes de ventas y gastos operativos. Los nombres conservan las etiquetas de origen: Revenue son ingresos, COGS coste de ventas y Operating expenses gastos operativos.",
        "monthly": "El detalle mensual muestra una contribución favorable en enero y desfavorable en febrero. En el segundo ejercicio marzo añade una contribución favorable. El nuevo resultado abarca tres meses; compáralo con la primera versión conservada.",
        "review": "Los totales coinciden con el documento ficticio aportado y todas las contribuciones concilian. El archivo solo contiene importes: no separa precio, volumen y mix ni demuestra causas comerciales. Revisa alcance, signos, fuentes e interpretación antes del uso; la aprobación profesional y la elección de una secuencia alternativa siguen pendientes.",
        "next": "Abre primero el informe y la comparación por partida, después el detalle mensual. Para repetir, aporta presupuesto y real de los mismos meses, moneda y significado de las columnas. No se realiza ningún envío.",
        "totals": "Resultado nativo en EUR",
        "month": "Detalle mensual",
        "links": "Archivos producidos",
        "sweep": "Revisión de secuencias alternativas",
        "selection": "Explica primero el resultado por partida. En el primer ejercicio la alternativa 2 muestra los ingresos agregados y los costes individuales; la alternativa 1 es más compacta, pero mezcla partida y mes. En el segundo ejercicio la alternativa 3 sigue los meses y separa ingresos y costes de marzo. Son lecturas propuestas, sin aprobación.",
        "residual": "Cada fila resta contribuciones ya mostradas: una fila posterior Month o Category no es el total independiente del mes o de la partida. Los grandes saldos de otras secuencias dejan aportes importantes fuera de las filas seleccionadas y resultan menos útiles para la primera explicación. Ninguna secuencia demuestra una causa económica.",
        "small": "Los paneles por partida confirman que el aumento de ingresos compensa las dos contribuciones desfavorables de los costes. No los describas como efectos de precio o cantidad.",
    },
}

# Case-specific editorial judgments, authored after reading both native sweeps.
# These are regression prose, not a production rule for selecting alternatives.
ALTERNATIVE_READINGS = {
    "it": {
        "compact": "Compatta e riconciliata; aprire il dettaglio dei mesi per distinguere ricavi e costi residui.",
        "category": "Utile per spiegare ricavi e costi; il dettaglio mensile chiarisce le compensazioni.",
        "small_first": "Riconciliata, ma parte da una piccola voce e rende meno evidente il quadro complessivo.",
        "cost_residual": "Lascia 2.000 EUR di spese operative nel residuo; espanderlo prima di spiegare l’intero risultato.",
        "missing_positive": "I contributi positivi rimasti in Altro sono essenziali; le sole righe selezionate non spiegano il risultato.",
        "mixed": "Riconciliata, ma alterna voce e mese; usare il dettaglio per evitare di sommare totali sovrapposti.",
        "monthly": "Utile per confrontare i mesi; i costi residui di marzo seguono i ricavi già selezionati.",
    },
    "en": {
        "compact": "Compact and reconciled; open the month detail to separate revenue and residual costs.",
        "category": "Useful for explaining revenue and costs; monthly detail clarifies offsetting contributions.",
        "small_first": "Reconciled, but starting with a small line makes the overall result harder to see.",
        "cost_residual": "Leaves EUR 2,000 of operating expenses in the residual; expand it before explaining the whole result.",
        "missing_positive": "Positive contributions remaining in Other are essential; selected rows alone do not explain the result.",
        "mixed": "Reconciled, but switches between category and month; use detail to avoid adding overlapping totals.",
        "monthly": "Useful for comparing months; March residual costs follow the revenue already selected.",
    },
    "fr": {
        "compact": "Compacte et rapprochée ; ouvrir le détail mensuel pour séparer produits et charges résiduelles.",
        "category": "Utile pour expliquer produits et charges ; le détail mensuel éclaire les compensations.",
        "small_first": "Rapprochée, mais commencer par une petite rubrique rend le résultat global moins lisible.",
        "cost_residual": "Laisse 2 000 EUR de charges opérationnelles dans le solde ; le détailler pour expliquer tout le résultat.",
        "missing_positive": "Les apports positifs restant dans Autres sont essentiels ; les lignes sélectionnées ne suffisent pas à expliquer le résultat.",
        "mixed": "Rapprochée, mais alterne rubrique et mois ; consulter le détail pour éviter des totaux qui se chevauchent.",
        "monthly": "Utile pour comparer les mois ; les charges résiduelles de mars suivent les produits déjà sélectionnés.",
    },
    "de": {
        "compact": "Kompakt und abgestimmt; Monatsdetails öffnen, um Erlöse und verbleibende Kosten zu trennen.",
        "category": "Hilfreich für Erlöse und Kosten; Monatsdetails erklären die gegenläufigen Beiträge.",
        "small_first": "Abgestimmt, beginnt aber mit einer kleinen Position und erschwert den Gesamtüberblick.",
        "cost_residual": "Lässt 2.000 EUR betriebliche Aufwendungen im Restbetrag; für die vollständige Erklärung aufschlüsseln.",
        "missing_positive": "Positive Beiträge unter Sonstige sind wesentlich; die ausgewählten Zeilen erklären das Ergebnis nicht vollständig.",
        "mixed": "Abgestimmt, wechselt aber zwischen Position und Monat; Details verhindern das Addieren überlappender Summen.",
        "monthly": "Hilfreich für den Monatsvergleich; die restlichen Märzkosten folgen auf bereits ausgewählte Erlöse.",
    },
    "es": {
        "compact": "Compacta y conciliada; abrir el detalle mensual para separar ingresos y costes residuales.",
        "category": "Útil para explicar ingresos y costes; el detalle mensual aclara las compensaciones.",
        "small_first": "Conciliada, pero empezar con una partida pequeña dificulta ver el resultado global.",
        "cost_residual": "Deja 2.000 EUR de gastos operativos en el saldo; detallarlo para explicar el resultado completo.",
        "missing_positive": "Las contribuciones positivas en Otros son esenciales; las filas seleccionadas no explican por sí solas el resultado.",
        "mixed": "Conciliada, pero alterna partida y mes; consultar el detalle para evitar sumar totales solapados.",
        "monthly": "Útil para comparar meses; los costes residuales de marzo siguen a los ingresos ya seleccionados.",
    },
}
CASE_READINGS = {
    "demo": (
        "compact",
        "category",
        "small_first",
        "small_first",
        "small_first",
        "cost_residual",
        "missing_positive",
        "missing_positive",
        "missing_positive",
        "missing_positive",
    ),
    "practice": (
        "mixed",
        "category",
        "monthly",
        "missing_positive",
        "missing_positive",
        "missing_positive",
        "missing_positive",
        "missing_positive",
        "missing_positive",
        "missing_positive",
    ),
}


def review_context(language: str) -> dict[str, str]:
    """Return the authored interpretation of this locale's supplied context."""
    return COPY[language]


def write_variance_review(output: Path, language: str, phase: str) -> Path:
    """Read current native data and write the exercise's authored delivery."""
    copy = COPY[language]
    variance = output / "variance"
    manifest = json.loads((variance / "model_use_manifest.json").read_text())
    assert manifest["default_model_use"]["raw_source_rows_included"] is False
    context = json.loads((variance / "standard_variance_context.json").read_text())
    totals = context["totals"]
    with (variance / "variance_results.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    lines = [
        f"# {copy['title']}",
        "",
        copy["perimeter"],
        "",
        copy["read"],
        "",
        f"## {copy['totals']}",
        "",
        "| PL EUR | AC EUR | Δ EUR |",
        "| ---: | ---: | ---: |",
        f"| {totals['amount_baseline']:,.0f} | {totals['amount_comparison']:,.0f} | {totals['total_delta']:+,.0f} |",
        "",
        copy["small"],
        "",
        f"## {copy['month']}",
        "",
        copy["monthly"],
        "",
        "| Month | Category | PL EUR | AC EUR | Δ EUR |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in sorted(rows, key=lambda r: (r["Month"], r["Category"])):
        lines.append(
            f"| {row['Month']} | {row['Category']} | {row['amount_baseline']} | {row['amount_comparison']} | {row['total_delta']} |"
        )
    lines.extend(
        [
            "",
            copy["signs"],
            "",
            copy["materiality"],
            "",
            copy["review"],
            "",
            copy["next"],
            "",
            f"## {copy['links']}",
            "",
            "[Word](variance/root_cause_client_report.docx) · [Δ](variance/total_by_dimension_bridge.png) · [Month](variance/exploded_variance_bridge.png) · [CSV](variance/variance_results.csv) · [Audit](variance/variance_audit.json)",
            "",
            f"[{copy['sweep']}](variance/codex_root_cause_sweep_analysis.md)",
            "",
        ]
    )
    note = output / "codex_business_analysis.md"
    note.write_text("\n".join(lines), encoding="utf-8")
    summary = json.loads((variance / "root_cause_sweep_summary.json").read_text())
    appendix = [
        f"# {copy['sweep']}",
        "",
        copy["selection"],
        "",
        copy["residual"],
        "",
        "| # | Rows | Labels | EUR | Dimensions | Mixed | Other EUR | Closure error EUR |",
        "| ---: | ---: | --- | --- | --- | --- | ---: | ---: |",
    ]
    for alt in summary["alternatives"]:
        values: list[Any] = [
            alt["alternative_result"],
            alt["row_count"],
            alt["selected_labels"],
            alt["selected_amounts"],
            alt["selected_sequence_bridge_dimensions"],
            alt["selected_sequence_has_mixed_dimensions"],
            alt["other_residual"],
            sum(float(value) for value in alt["selected_amounts"].split(" | "))
            + float(alt["other_residual"])
            - totals["total_delta"],
        ]
        appendix.append(
            "| " + " | ".join(str(v).replace("|", ";") for v in values) + " |"
        )
    appendix.append("")
    for number, reading in enumerate(CASE_READINGS[phase], 1):
        appendix.extend([f"{number}. {ALTERNATIVE_READINGS[language][reading]}", ""])
    appendix.extend(["", copy["review"], ""])
    (variance / "codex_root_cause_sweep_analysis.md").write_text(
        "\n".join(appendix), encoding="utf-8"
    )
    (output / "codex_run_review.md").write_text(
        f"[{copy['title']}](codex_business_analysis.md)\n", encoding="utf-8"
    )
    return note
