"""Authored delivery notes for fictional Financial Analysis regression runs.

Exercise the skill's ordinary Codex review-note stage using actual prepared
results. Neither these notes nor their interpretation are shipped in a kit.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["write_financial_review"]

COPY = {
    "it": (
        "Posizione finanziaria netta",
        "Voce",
        "Importo EUR",
        "Finanziamento residuo",
        "Liquidità disponibile",
        "Risultato",
        "Caso fittizio Officina Arco. La definizione richiesta comprende il finanziamento e sottrae la liquidità disponibile alla stessa data.",
        "Voci escluse",
        "Deposito vincolato",
        "Debiti commerciali ordinari",
        "Il deposito resta vincolato; i debiti verso fornitori sono esclusi dalla definizione richiesta per questo esercizio.",
        "Il calcolo e i controlli interni sono completati. Il prospetto contiene solo quattro saldi: completezza, riscontro con documenti indipendenti e conclusione professionale restano da verificare. Prima dell’uso, rivedi definizione, fonti e data; per aggiornare l’analisi avvia un nuovo calcolo con i nuovi saldi.",
        "Risultato e dettaglio",
    ),
    "en": (
        "Net debt",
        "Item",
        "Amount EUR",
        "Outstanding bank loan",
        "Available cash",
        "Result",
        "Fictional Officina Arco case. The requested definition includes the loan and subtracts available cash at the same date.",
        "Excluded items",
        "Restricted deposit",
        "Ordinary trade payables",
        "The deposit remains restricted; supplier balances are excluded from the definition requested for this exercise.",
        "The calculation and internal checks are complete. The statement contains only four balances: completeness, independent source tie-out and professional conclusions still require review. Before use, review the definition, sources and date; update the analysis by starting a new calculation with the new balances.",
        "Result and line items",
    ),
    "fr": (
        "Endettement financier net",
        "Poste",
        "Montant EUR",
        "Emprunt bancaire restant dû",
        "Trésorerie disponible",
        "Résultat",
        "Cas fictif Officina Arco. La définition demandée retient l’emprunt et déduit la trésorerie disponible à la même date.",
        "Postes exclus",
        "Dépôt bloqué",
        "Dettes fournisseurs courantes",
        "Le dépôt reste bloqué ; les dettes fournisseurs sont exclues de la définition demandée pour cet exercice.",
        "Le calcul et les contrôles internes sont terminés. Le relevé ne contient que quatre soldes : exhaustivité, rapprochement avec des pièces indépendantes et conclusion professionnelle restent à vérifier. Avant utilisation, revoyez définition, sources et date ; actualisez l’analyse par un nouveau calcul avec les nouveaux soldes.",
        "Résultat et détail",
    ),
    "de": (
        "Nettofinanzverschuldung",
        "Posten",
        "Betrag EUR",
        "Offenes Bankdarlehen",
        "Verfügbare Liquidität",
        "Ergebnis",
        "Fiktiver Fall Officina Arco. Die gewünschte Definition berücksichtigt das Darlehen abzüglich der verfügbaren Liquidität zum selben Stichtag.",
        "Ausgeschlossene Posten",
        "Gebundene Einlage",
        "Laufende Lieferantenverbindlichkeiten",
        "Die Einlage bleibt gebunden; Lieferantenverbindlichkeiten sind nach der für diese Übung gewünschten Definition ausgeschlossen.",
        "Berechnung und interne Kontrollen sind abgeschlossen. Die Aufstellung enthält nur vier Salden: Vollständigkeit, Abgleich mit unabhängigen Belegen und fachliche Schlussfolgerung bleiben zu prüfen. Prüfen Sie vor der Verwendung Definition, Quellen und Stichtag; starten Sie zur Aktualisierung eine neue Berechnung mit den neuen Salden.",
        "Ergebnis und Einzelposten",
    ),
    "es": (
        "Deuda financiera neta",
        "Partida",
        "Importe EUR",
        "Préstamo bancario pendiente",
        "Efectivo disponible",
        "Resultado",
        "Caso ficticio Officina Arco. La definición solicitada incluye el préstamo y resta el efectivo disponible a la misma fecha.",
        "Partidas excluidas",
        "Depósito restringido",
        "Deudas comerciales ordinarias",
        "El depósito sigue restringido; las deudas con proveedores se excluyen de la definición solicitada para este ejercicio.",
        "El cálculo y los controles internos están terminados. El estado contiene solo cuatro saldos: deben revisarse la integridad, el contraste con documentos independientes y la conclusión profesional. Antes de usarlo, revisa definición, fuentes y fecha; actualiza el análisis iniciando otro cálculo con los nuevos saldos.",
        "Resultado y detalle",
    ),
}


def write_financial_review(output: Path, language: str) -> Path:
    """Present the current native metrics without recalculating the analysis."""
    result = json.loads((output / "prepared/fdd_result.json").read_text())
    metrics = {item["metric_id"]: item["value"] for item in result["metrics"]}
    items = {item["item_id"]: item for item in result["line_items"]}
    words = COPY[language]
    lines = [
        f"# {words[0]}",
        "",
        f"Officina Arco — {result['calculation_policy']['as_of_date']}",
        "",
        words[6],
        "",
        f"| {words[1]} | {words[2]} |",
        "| :--- | ---: |",
        f"| {words[3]} | {metrics['debt']} |",
        f"| {words[4]} | {metrics['cash']} |",
        f"| **{words[5]}** | **{metrics['net_debt']}** |",
        "",
        f"## {words[7]}",
        "",
        f"| {words[1]} | {words[2]} |",
        "| :--- | ---: |",
        f"| {words[8]} | {items['item.deposit']['amount']} |",
        f"| {words[9]} | {items['item.payables']['amount']} |",
        "",
        words[10],
        "",
        words[11],
        "",
        f"## {words[12]}",
        "",
        "- [fdd_result.json](prepared/fdd_result.json)",
        "- [fdd_line_items.json](prepared/fdd_line_items.json)",
        "- [financial_analysis_contract_audit.json](prepared/financial_analysis_contract_audit.json)",
        "",
    ]
    path = output / "codex_run_review.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
