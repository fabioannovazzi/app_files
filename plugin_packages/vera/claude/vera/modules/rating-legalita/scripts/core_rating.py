"""Vera Rating di legalita: nucleo di riferimento, v0.1, 2026-10-02.

Calcoli meccanici su fatti gia qualificati: correttezza aritmetica verificabile.
Non interpreta reati, provvedimenti, efficacia, dissociazione, titolarita o firme.
Nessuna rete, nessun accesso ad AGCM, nessun invio, nessuna API di modelli.
Fonte delle grandezze: delibera AGCM 31812/2026, artt. 7, 8, 10, 18, 21, 25.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

__all__ = [
    "debt_threshold",
    "debt_test",
    "safety_test",
    "traceability_test",
    "expected_expiry",
    "renewal_window",
    "application_route",
    "event_deadline",
    "transitional_expiry",
    "score",
    "final_readiness",
]

VERSION = "0.1.0"
RULESET = "AGCM-31812-2026-reviewed-2026-10-02"
EFFECTIVE = date(2026, 3, 16)


def money(value) -> Decimal:
    """Importi decimali esatti; None non significa zero."""
    if value is None or isinstance(value, bool):
        raise ValueError("Importo mancante o non valido")
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError("Importo non finito o negativo")
    return number


def debt_threshold(turnover) -> Decimal:
    """Soglia art. 7.2.c; il denominatore va qualificato dal professionista."""
    return min(money(turnover) * Decimal("0.005"), Decimal("50000"))


def debt_test(turnover, reviewed_final_uncovered_debt) -> bool:
    """Solo confronto numerico. Pagamenti/rateazioni/definitivita sono a monte."""
    return money(reviewed_final_uncovered_debt) <= debt_threshold(turnover)


def safety_test(reviewed_relevant_amounts: Iterable) -> bool:
    """Lettura applicativa prudenziale: ogni atto <=1200 e totale <=3600.

    Non qualifica atti endoprocedimentali, penalita penali o il relativo biennio.
    Un elenco vuoto deve significare assenza gia verificata, mai dati mancanti.
    """
    amounts = [money(x) for x in reviewed_relevant_amounts]
    return all(x <= Decimal("1200") for x in amounts) and sum(amounts) <= Decimal(
        "3600"
    )


def traceability_test(
    total_count: int, traced_count: int, *, complete: bool, perimeter_reviewed: bool
) -> bool | None:
    """Ipotesi metodologica: rapporto sul numero dei pagamenti sotto soglia.

    Periodo, soglia vigente, completezza e conteggio devono essere approvati.
    Zero operazioni non prova automaticamente il requisito.
    """
    if any(type(x) is not int for x in (total_count, traced_count)):
        raise ValueError("I conteggi devono essere interi")
    if any(type(x) is not bool for x in (complete, perimeter_reviewed)):
        raise ValueError("Le conferme devono essere booleani espliciti")
    if total_count < 0 or not 0 <= traced_count <= total_count:
        raise ValueError("Conteggi incoerenti")
    if not complete or not perimeter_reviewed or total_count == 0:
        return None
    return traced_count * 2 > total_count


def add_months(day: date, months: int) -> date:
    absolute = day.year * 12 + day.month - 1 + months
    year, zero_month = divmod(absolute, 12)
    month = zero_month + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def expected_expiry(release_date: date) -> date:
    """Controllo di coerenza: la scadenza del provvedimento resta autoritativa."""
    return add_months(release_date, 24 if release_date < EFFECTIVE else 36)


def renewal_window(official_expiry: date) -> tuple[date, date]:
    """Sei mesi di calendario e 60 giorni, entrambi inclusivi."""
    return add_months(official_expiry, -6), official_expiry - timedelta(days=60)


def application_route(submission_date: date, official_expiry: date) -> str:
    """Data di trasmissione effettiva, non data di apertura o salvataggio bozza."""
    opening, deadline = renewal_window(official_expiry)
    if submission_date < opening:
        return "rinnovo_non_ancora_presentabile"
    if submission_date <= deadline:
        return "rinnovo"
    return "nuova_attribuzione"


def event_deadline(event_date: date) -> date:
    """Art.21: 30 giorni dall'evento; nessuna proroga festiva automatica."""
    return event_date + timedelta(days=30)


def transitional_expiry(
    official_old_expiry: date,
    *,
    timely_notice: bool,
    authority_continuation_confirmed: bool,
) -> date | None:
    """Art.25.5: nessun prolungamento oltre la scadenza biennale.

    Se manca comunicazione tempestiva o riscontro AGCM non attribuisce validita.
    None significa valutazione necessaria, NON automaticamente rating scaduto.
    """
    if not timely_notice or not authority_continuation_confirmed:
        return None
    return min(official_old_expiry, date(2026, 11, 16))


def label(extra: int) -> str:
    if type(extra) is not int or not 0 <= extra <= 6:
        raise ValueError("Punteggio fuori intervallo")
    return "★" * (1 + extra // 3) + "+" * (extra % 3)


def score(
    *,
    base: str,
    premiums: dict[str, str],
    deduction: bool | None,
    prior_continuous_renewals: int = 0,
    timely_renewal: bool = False,
    approved_cap_policy: str | None = None,
) -> dict:
    """Stima, mai attribuzione AGCM. Un solo '+' per lettera a-h.

    Stati premi: supported / absent / unknown. Non presume fattibilita dei mancanti.
    base: verified / obstructed / undetermined. verified include ammissibilita,
    assenza ostacoli, completezza perimetro, attualita delle prove e review.
    L'eventuale ambiguita fra tetto e decurtazione e esposta, non nascosta.
    """
    if base not in {"verified", "obstructed", "undetermined"}:
        raise ValueError("Stato base non valido")
    if set(premiums) != set("abcdefgh"):
        raise ValueError("Sono richieste esattamente le otto lettere a-h")
    if not set(premiums.values()) <= {"supported", "absent", "unknown"}:
        raise ValueError("Stato premiale non valido")
    if deduction is not None and type(deduction) is not bool:
        raise ValueError("Decurtazione non valida")
    if type(prior_continuous_renewals) is not int or prior_continuous_renewals < 0:
        raise ValueError("Storico rinnovi non valido")
    if type(timely_renewal) is not bool:
        raise ValueError("Tipo rinnovo non valido")
    if approved_cap_policy not in {None, "net_then_cap", "cap_then_deduct"}:
        raise ValueError("Politica tetto non valida")
    supported = sum(x == "supported" for x in premiums.values())
    unknown = [k for k, v in premiums.items() if v == "unknown"]
    loyalty = int(timely_renewal and prior_continuous_renewals >= 3)
    result = {
        "ruleset": RULESET,
        "official_rating": None,
        "supported_premiums": supported,
        "unknown_premiums": unknown,
        "continuity_plus": loyalty,
        "estimated_rating": None,
        "score_status": base,
        "warnings": [],
    }
    if base != "verified":
        return result
    deductions = [0, 1] if deduction is None else [int(deduction)]
    candidates = set()
    for loss in deductions:
        net = min(6, max(0, supported + loyalty - loss))
        capped = min(6, max(0, min(6, supported) - loss + loyalty))
        if approved_cap_policy == "net_then_cap":
            candidates.add(net)
        elif approved_cap_policy == "cap_then_deduct":
            candidates.add(capped)
        else:
            candidates.update((net, capped))
    result["possible_estimates"] = [label(x) for x in sorted(candidates)]
    if deduction is None:
        result["warnings"].append("Decurtazione ANAC da verificare")
    if len(candidates) > 1 and deduction is not None:
        result["warnings"].append(
            "Ordine tetto/decurtazione da qualificare: non automatizzare"
        )
    if unknown:
        result["warnings"].append(
            "Premi non documentati esclusi dalla stima; fattibilita non assunta"
        )
    if len(candidates) == 1 and deduction is not None:
        result["estimated_rating"] = label(next(iter(candidates)))
        result["score_status"] = "stima_sui_requisiti_documentati"
    else:
        result["score_status"] = "stima_da_verificare"
    return result


def final_readiness(
    *,
    required_states: dict[str, str],
    source_current: bool,
    perimeter_complete: bool,
    declarations_complete: bool,
    reviewed_bundle_hash: str | None,
    actual_bundle_hash: str,
    field_map_verified: bool,
    attachments_complete: bool,
) -> dict:
    """Gate per predisposizione: un'approvazione non si trasferisce a file nuovi.

    Il chiamante deve generare l'universo required_states dal catalogo e dal caso,
    includere ogni soggetto/evento applicabile e verificare le motivazioni N/A.
    Questo helper non prova la completezza semantica dell'universo chiamante.
    """
    if not required_states:
        return {
            "ready": False,
            "blockers": ["Matrice requisiti vuota"],
            "submission_authorized": False,
        }
    confirmations = (
        source_current,
        perimeter_complete,
        declarations_complete,
        field_map_verified,
        attachments_complete,
    )
    if any(type(x) is not bool for x in confirmations):
        raise ValueError("Le conferme devono essere booleani espliciti")
    bad = [
        key
        for key, state in required_states.items()
        if state not in {"verified", "not_applicable_reviewed"}
    ]
    checks = {
        "Fonti da aggiornare": source_current,
        "Perimetro incompleto": perimeter_complete,
        "Dichiarazioni incomplete": declarations_complete,
        "Approvazione assente o superata": bool(reviewed_bundle_hash)
        and reviewed_bundle_hash == actual_bundle_hash,
        "Mappatura formulario da verificare": field_map_verified,
        "Allegati incompleti": attachments_complete,
    }
    blockers = ["Requisito aperto: " + key for key in bad]
    blockers += [message for message, passed in checks.items() if not passed]
    return {"ready": not blockers, "blockers": blockers, "submission_authorized": False}
