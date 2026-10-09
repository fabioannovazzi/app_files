"""Reproduce the synthetic large-journal memory check (macOS or Linux)."""

from __future__ import annotations

import argparse
import json
import logging
import resource
import sys
import time
from pathlib import Path

from reportlab.pdfgen import canvas

__all__ = ["main"]


def main() -> int:
    """Generate 951 pages and record reader peak RSS, completeness and elapsed time."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(
        0, str(Path(__file__).resolve().parents[2] / "plugins/_shared/vendor/modules")
    )
    from vera_journal_pdf import read_registration_pdf

    source = args.output_dir / "synthetic-journal-951.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(600, 800))
    for page_index in range(951):
        pdf.setFont("Helvetica", 9)
        for group in range(10):
            y = 755 - group * 66
            number = page_index * 10 + group + 1
            pdf.drawString(30, y, f"{number} ---- 01/01/2024 ---- Documento")
            pdf.drawString(30, y - 18, "6.30.055")
            pdf.drawString(200, y - 18, "Pagamento")
            pdf.drawString(410, y - 18, "100,00")
            pdf.drawString(120, y - 36, "7.10.001")
            pdf.drawString(200, y - 36, "Contropartita")
            pdf.drawString(500, y - 36, "100,00")
        pdf.showPage()
    pdf.save()
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    started = time.monotonic()
    records, diagnostics = read_registration_pdf(
        source,
        {
            "body": [20, 770],
            "columns": {
                "account_debit": [20, 110],
                "account_credit": [110, 195],
                "description": [195, 400],
                "debit": [400, 490],
                "credit": [490, 590],
            },
            "ignored_line_prefixes": [],
        },
    )
    result = {
        "pages": diagnostics["page_count"],
        "accepted": diagnostics["accepted"],
        "postings": len(records),
        "seconds": round(time.monotonic() - started, 2),
        "peak_rss_mib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            / (1024 * 1024 if sys.platform == "darwin" else 1024),
            2,
        ),
        "source_bytes": source.stat().st_size,
        "rejected_rows": diagnostics["rejected_rows"],
    }
    (args.output_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("%s", result)
    return 0 if result["accepted"] and result["postings"] == 19020 else 1


if __name__ == "__main__":
    raise SystemExit(main())
