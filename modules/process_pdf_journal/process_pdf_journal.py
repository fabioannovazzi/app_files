import logging
# file: journal_to_excel.py
import logging

import pdfplumber
import polars as pl
from modules.utilities.ui_notifier import ui

from .logic import parse_journal, to_excel_bytes

# parse_journal internally routes through the journal_ingest package which
# selects the best parsing strategy (including the new text-layout parser).


###############################################################################
# 3.  Main workflow
###############################################################################
def process_pdf_journal(pdf_file, header_row: int | None = None):
    ui.info("Parsing PDF. This may take some time...", icon="ℹ️")
    try:
        df_journal = parse_journal(pdf_file.getvalue(), header_row=header_row)
    except ValueError as e:
        logging.exception(e)
        ui.error("Something went wrong while parsing the PDF.")
        return None
    except (pl.exceptions.PolarsError, pdfplumber.PDFSyntaxError) as e:
        logging.exception(e)
        ui.error("Something went wrong while parsing the PDF.")
        return None
    except Exception as e:  # noqa: BLE001
        logging.exception(e)
        ui.error("Something went wrong while parsing the PDF.")
        return None

    ui.success(f"✅ Parsed {df_journal.height:,} journal lines.")
    excel_bytes = to_excel_bytes(df_journal)
    ui.download_button(
        "📥 Download converted PDF",
        data=excel_bytes,
        file_name="journal_with_movements.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return df_journal
