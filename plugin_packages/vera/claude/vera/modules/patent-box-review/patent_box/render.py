"""Render review workpapers, not a completed statutory penalty-protection file."""

from __future__ import annotations

import csv
import io
from typing import Any

__all__ = ["markdown", "reconciliation_csv"]


def markdown(result: dict[str, Any]) -> str:
    bases = result["bases"]
    out = [
        "# Patent Box – workpaper di calcolo",
        "",
        "**BOZZA DA RIVEDERE DAL PROFESSIONISTA**",
        "",
        f"Pratica: {result['case_id']} — periodo: {result['claim_period_id']}",
        "",
        (
            "Esempio sintetico."
            if result["demo"]
            else "Input normalizzati e classificazioni forniti dal professionista."
        ),
        "",
        "| Stato | Base imposte sui redditi EUR | Base IRAP EUR |",
        "|---|---:|---:|",
    ]
    for state, values in bases.items():
        out.append(f"| {state} | {values['income']} | {values['irap']} |")
    out += [
        "",
        f"Variazione aggiuntiva redditi: **{result['additional_deduction']['income']} EUR**.",
        f"Variazione aggiuntiva IRAP: **{result['additional_deduction']['irap']} EUR**.",
        "",
        "Le variazioni riguardano esclusivamente le componenti INCLUDED. Non sono un credito d'imposta o un risparmio fiscale già realizzato.",
        "",
        f"Verifica documentale separata: **{result['penalty_protection']['status']}**.",
        "",
        "## Esito per componente",
        "",
        "| Allocazione | Costo | IP | Esito | Motivi |",
        "|---|---|---|---|---|",
    ]
    for line in result["lines"]:
        out.append(
            f"| {line['allocation_id']} | {line['cost_id']} | {line['ip_id']} | {line['status']} | {', '.join(line['reasons']) or 'Controlli dichiarati superati'} |"
        )
    out += [
        "",
        "## Decisioni richieste",
        "",
        "Rivedere qualificazioni, evidenze, fonti, esclusioni e sospensioni. Completare coordinamento incentivi, mapping dichiarativo e fascicolo A/B. L'esito non attesta l'idoneità riconosciuta dall'Agenzia.",
        "",
        f"Input SHA-256: `{result['input_hash']}`",
        f"Regole SHA-256: `{result['rules_hash']}`",
        f"Risultato SHA-256: `{result['result_hash']}`",
        "",
    ]
    return "\n".join(out)


def reconciliation_csv(result: dict[str, Any]) -> str:
    stream = io.StringIO(newline="")
    keys = [
        "allocation_id",
        "cost_id",
        "ip_id",
        "mode",
        "status",
        "income_amount",
        "irap_amount",
        "reasons",
    ]
    writer = csv.DictWriter(stream, fieldnames=keys)
    writer.writeheader()
    for line in result["lines"]:
        row = dict(line)
        row["reasons"] = ";".join(row["reasons"])
        writer.writerow(row)
    return stream.getvalue()
