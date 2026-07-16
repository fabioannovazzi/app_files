import polars as pl

from modules.utilities.utils import get_row_count
from src.final_pass_filter import clean_bank_not_matched


def test_clean_bank_not_matched_keeps_and_drops() -> None:
    data = [
        {
            "description": "29/06/24 COMPETENZE",
            "amount": -105.0,
            "accounting_date": "2024-06-29",
        },
        {
            "description": "10/06/24 F24 TELEMATICO DELEGA",
            "amount": -447.82,
            "accounting_date": "2024-06-10",
        },
        {
            "description": "BON.DA EXAMPLE SUPPLIER S.R.L.",
            "amount": 31160.72,
            "accounting_date": "2024-06-01",
        },
        {
            "description": "VOSTRA DISPOSIZIONE BONIFICO URG./ISTANTANEO RIF. MBVT123456",
            "amount": 0.0,
            "accounting_date": "2024-06-15",
        },
        {
            "description": "DISPOSIZIONE DI GIROCONTO (STESSA BANCA)",
            "amount": 0.0,
            "accounting_date": "2024-06-05",
        },
        {"description": "RIASSUNTO SCALARE DEL CONTO CORRENTE N. 503", "amount": 0.0},
        {
            "description": "SALDI PER VALUTA | NUMERI A DEBITO | NUMERI A CREDITO",
            "amount": 0.0,
        },
        {"description": "RILEVAZIONE COSTI", "amount": 0.0},
        {"description": "RILEVAZIONI VARIE", "amount": 0.0},
        {"description": "SEGNALAZIONI AI FINI ISEE", "amount": 0.0},
        {"description": "NUOVI ORARI FILIALE", "amount": 0.0},
        {
            "description": "MODULO STANDARD PER LE INFORMAZIONI DA FORNIRE AI DEPOSITANTI",
            "amount": 0.0,
        },
        {"description": "pagina 3 di 6", "amount": 0.0},
        {"description": "INDEX:;05034;...", "amount": 0.0},
        {"description": "COORDINATE BANCARIE INTERNAZIONALI IBAN", "amount": 0.0},
    ]
    df = pl.DataFrame(data)

    cleaned, report = clean_bank_not_matched(df, collect_stats=True)

    assert get_row_count(cleaned) == 5
    assert report.dropped_rows == 10
    assert any(key.startswith("drop") for key in report.counts_by_rule)


def test_clean_bank_not_matched_handles_date_typed_columns() -> None:
    from datetime import date

    df = pl.DataFrame(
        [
            {
                "description": "BON.DA EXAMPLE SUPPLIER S.R.L.",
                "amount": 31160.72,
                "accounting_date": date(2024, 6, 1),
            }
        ]
    )

    cleaned = clean_bank_not_matched(df)

    assert get_row_count(cleaned) == 1


def test_clean_bank_not_matched_drops_pure_numeric_balance() -> None:
    df = pl.DataFrame(
        [
            {
                "description": "01/12/2023    1.234,56    0    1.234,56",
                "amount": 0.0,
            }
        ]
    )

    cleaned, report = clean_bank_not_matched(df, collect_stats=True)
    assert get_row_count(cleaned) == 0
    assert report.counts_by_rule["drop_balance_summary"] == 1
    assert report.counts_by_rule["drop_pure_numeric_balance"] == 1


def test_rule_counters_sum_to_rows_dropped() -> None:
    data = [
        {
            "description": "29/06/24 COMPETENZE",
            "amount": -105.0,
            "accounting_date": "2024-06-29",
        },
        {
            "description": "10/06/24 F24 TELEMATICO DELEGA",
            "amount": -447.82,
            "accounting_date": "2024-06-10",
        },
        {
            "description": "BON.DA EXAMPLE SUPPLIER S.R.L.",
            "amount": 31160.72,
            "accounting_date": "2024-06-01",
        },
        {
            "description": "VOSTRA DISPOSIZIONE BONIFICO URG./ISTANTANEO RIF. MBVT123456",
            "amount": 0.0,
            "accounting_date": "2024-06-15",
        },
        {
            "description": "DISPOSIZIONE DI GIROCONTO (STESSA BANCA)",
            "amount": 0.0,
            "accounting_date": "2024-06-05",
        },
        {"description": "RIASSUNTO SCALARE DEL CONTO CORRENTE N. 503", "amount": 0.0},
        {
            "description": "SALDI PER VALUTA | NUMERI A DEBITO | NUMERI A CREDITO",
            "amount": 0.0,
        },
        {"description": "RILEVAZIONE COSTI", "amount": 0.0},
        {"description": "RILEVAZIONI VARIE", "amount": 0.0},
        {"description": "SEGNALAZIONI AI FINI ISEE", "amount": 0.0},
        {"description": "NUOVI ORARI FILIALE", "amount": 0.0},
        {
            "description": "MODULO STANDARD PER LE INFORMAZIONI DA FORNIRE AI DEPOSITANTI",
            "amount": 0.0,
        },
        {"description": "pagina 3 di 6", "amount": 0.0},
        {"description": "INDEX:;05034;...", "amount": 0.0},
        {"description": "COORDINATE BANCARIE INTERNAZIONALI IBAN", "amount": 0.0},
    ]
    df = pl.DataFrame(data)

    cleaned, report = clean_bank_not_matched(df, collect_stats=True)

    drop_total = sum(
        v for k, v in report.counts_by_rule.items() if k.startswith("drop")
    )
    assert drop_total == report.dropped_rows
