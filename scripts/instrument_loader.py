"""Instrument ledger loader to inspect header detection and column mapping."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polars as pl

# Allow running the script directly without installing the package.
repo_root = Path(__file__).resolve().parents[1]
sys.path.extend([str(repo_root), str(repo_root / "src")])

from modules.utilities.utils import get_schema_and_column_names
from src.check_statements import (
    _detect_excel_header_polars,
    _infer_columns,
    _rebuild_df_with_header,
)

# Reuse the ledger keywords used in ``load_ledger_files``
LEDGER_KEYWORDS = {
    "date": [
        "data",
        "date",
        "data operazione",
        "data reg",
        "data registrazione",
        "fecha",
        "fecha operacion",
        "fecha registro",
        "datum",
        "daten",
        "valuta",
        "datavaluta",
        "valuedate",
        "data valuta",
    ],
    "description": [
        "descrizione",
        "descrizione causale",
        "descrizione agg",
        "causale",
        "descr",
        "desc",
        "descrizione aggiuntiva",
        "description",
        "description causale",
        "descripcion",
        "beschreibung",
        "descrizione deposito",
        "narrative",
        "riferimento",
        "reference",
    ],
    "debit": [
        "addebito",
        "uscite",
        "dare",
        "debit",
        "debe",
        "débit",
        "débito",
        "lastschrift",
        "prelievo",
    ],
    "credit": [
        "accredito",
        "entrate",
        "avere",
        "accrediti",
        "accreditation",
        "credit",
        "credito",
        "crédito",
        "haber",
        "gutschrift",
        "versamento",
        "deposito",
    ],
    "amount": [
        "importo",
        "amount",
        "importe",
        "betrag",
        "montant",
        "ammontare",
    ],
    "beneficiary": [
        "benef",
        "beneficiario",
        "beneficiary",
        "cliente",
        "fornitore",
        "cliente/fornitore",
        "beneficiario/cliente",
        "beneficiario/fornitore",
    ],
}


def main() -> None:
    """Run header detection and column inference for a sample ledger file."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ledger_file",
        type=Path,
        help="Path to the Excel ledger file to inspect.",
    )
    path = parser.parse_args().ledger_file.expanduser()
    if not path.exists():
        print(f"file not found: {path}")
        return
    content = path.read_bytes()
    header_row = _detect_excel_header_polars(content, max_rows=50)
    print("Detected header row:", header_row)
    df = _rebuild_df_with_header(content, header_row)
    print("DataFrame shape:", (df.height, df.width))
    columns, _ = get_schema_and_column_names(df)
    print("Columns:", columns)
    mapping = _infer_columns([str(c) for c in columns], LEDGER_KEYWORDS)
    print("Mapping:", mapping)
    print("First rows:")
    print(df.head())


if __name__ == "__main__":
    main()
