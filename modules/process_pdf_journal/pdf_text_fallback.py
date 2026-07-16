"""Text-mode fallback parser for journal PDFs."""

from __future__ import annotations

import io
import re
from pathlib import Path
import logging
from typing import Any

import pdfplumber
import polars as pl

_AMOUNT_PATTERN = r"[€]?\d{1,3}(?:\.\d{3})*,\d{2}"
_AMOUNT_RE = re.compile(_AMOUNT_PATTERN)

# account code: one or more numeric segments optionally separated by slashes,
# dots, dashes or asterisks
ACCT_PATTERN = r"(?P<conto>\d+(?:\s*[*/.-]\s*\d+)*)"
ROW_RE = re.compile(
    r"^(?P<riga>\d+)\s+"
    + ACCT_PATTERN
    + r"\s+(?P<descrizione>.+?)\s+(?P<amount>"
    + _AMOUNT_PATTERN
    + r")\s*$"
)


def _as_bytes(data: Any) -> bytes:
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, (str, Path)):
        return Path(data).read_bytes()
    return data.read()


def infer_dare_avere_x_positions(page: pdfplumber.page.Page) -> tuple[float, float]:
    """Return approximate centres for the Dare and Avere columns.

    The function inspects all numeric amount words on *page* and splits their
    ``x`` coordinates into two groups using a simple mean split. The average of
    the left and right groups is returned. When only one group is detected the
    same value is returned for both columns.
    """

    words = page.extract_words(x_tolerance=1, y_tolerance=3)
    xs = [
        (w["x0"] + w["x1"]) / 2
        for w in words
        if _AMOUNT_RE.fullmatch(w.get("text", ""))
    ]
    if not xs:
        return 0.0, 0.0
    mean = sum(xs) / len(xs)
    left = [x for x in xs if x <= mean] or [mean]
    right = [x for x in xs if x > mean] or [mean]
    return sum(left) / len(left), sum(right) / len(right)


def _parse_header(
    lines: list[str], i: int
) -> tuple[Any | None, str | None, str | None, str | None, int]:
    """Parse a header starting at ``lines[i]``.

    Returns the parsed ``(date, causale, attivita, filiale, new_index)``. If no
    header is found the tuple ``(None, None, None, None, i)`` is returned.
    """

    tokens = lines[i].split()
    if not tokens:
        return None, None, None, None, i

    from .logic import parse_date_str

    date_token = tokens[0]
    current_date = parse_date_str(date_token)
    if current_date is None:
        return None, None, None, None, i
    current_causale = lines[i][len(date_token) :].strip()

    attivita: str | None = None
    filiale: str | None = None
    j = i + 1
    while j < len(lines):
        ln = lines[j].strip()
        if (
            not ln
            or re.fullmatch(r"\d+", ln)
            or re.search(r"\d\s*[*/.-]\s*\d", ln)
            or _AMOUNT_RE.search(ln)
        ):
            break

        if re.match(r"^\d+\s*-\s*.+$", ln):
            left, right = ln.split("-", 1)
            if attivita is None:
                attivita = left.strip()
            if filiale is None:
                filiale = right.strip()
            j += 1
            continue

        if attivita is None:
            attivita = ln
        elif filiale is None:
            filiale = ln
        j += 1

    return current_date, current_causale, attivita, filiale, j


def parse_pdf_text_mode(data: Any) -> pl.DataFrame:
    """Parse journal-like lines from *data* using text heuristics.

    Parameters
    ----------
    data:
        Bytes, path or file-like object with the PDF contents.
    """

    pdf_bytes = _as_bytes(data)
    rows: list[dict[str, Any]] = []
    current_date: Any | None = None
    current_causale: str | None = None
    current_attivita: str | None = None
    current_filiale: str | None = None

    # delayed import to avoid circular dependency
    from .logic import parse_amount as _parse_amount

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            i = 0
            while i < len(lines):
                ln = lines[i]
                up = ln.upper()
                if (
                    up.startswith("PARTITA IVA")
                    or up.startswith("CODICE FISCALE")
                    or "GIORNALE DI CONTABILIT" in up
                    or up.startswith("ATTIVITA FILIALE DATA REGISTRAZIONE CAUSALE")
                    or up.startswith("RIPORTI")
                    or up.startswith("TOTALE PAGINA")
                    or up.startswith("ULTIMA RIGA")
                ):
                    i += 1
                    continue

                date, causale, attivita, filiale, new_i = _parse_header(lines, i)
                if date is not None:
                    current_date = date
                    current_causale = causale
                    current_attivita = attivita
                    current_filiale = filiale
                    i = new_i
                    continue

                m = ROW_RE.match(ln)
                if not m:
                    i += 1
                    continue
                riga = m.group("riga")
                conto = m.group("conto").replace(" ", "")
                desc = m.group("descrizione").strip()
                amount = _parse_amount(m.group("amount"))
                if re.search(r"\s{2,}", desc):
                    account_desc, operation_desc = re.split(r"\s{2,}", desc, 1)
                    account_desc = account_desc.strip()
                    operation_desc = operation_desc.strip()
                else:
                    account_desc = None
                    operation_desc = desc
                rows.append(
                    {
                        "data": current_date,
                        "causale": current_causale,
                        "attivita": current_attivita,
                        "filiale": current_filiale,
                        "riga": riga,
                        "conto": conto,
                        "descrizione_conto": account_desc,
                        "descrizione_operazione": operation_desc,
                        "amount": amount,
                    }
                )
                i += 1

    return pl.DataFrame(rows) if rows else pl.DataFrame()


def parse_pdf_group_lines(data: Any) -> pl.DataFrame:
    """Group lines until a monetary amount is encountered, then parse.

    Parameters
    ----------
    data:
        Bytes, path or file-like object with the PDF contents.

    Returns
    -------
    pl.DataFrame
        DataFrame with columns: data, causale, riga, conto,
        descrizione_conto, descrizione_operazione, amount and any
        additional header fields as ``field2``, ``field3`` and so on.
    """

    pdf_bytes = _as_bytes(data)
    rows: list[dict[str, Any]] = []
    buffer: list[str] = []
    current_headers: dict[str, Any] = {"data": None, "causale": None}
    header_field_names = ["causale"]

    from .logic import parse_amount as _parse_amount
    from .logic import parse_date_str

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                ln = line.strip()
                if not ln:
                    continue
                up = ln.upper()
                if (
                    up.startswith("PARTITA IVA")
                    or up.startswith("CODICE FISCALE")
                    or "GIORNALE DI CONTABILIT" in up
                    or up.startswith("ATTIVITA FILIALE DATA REGISTRAZIONE CAUSALE")
                    or up.startswith("RIPORTI")
                    or up.startswith("TOTALE PAGINA")
                    or up.startswith("ULTIMA RIGA")
                ):
                    continue
                m_header = re.match(r"(\d{2}/\d{2}/\d{4})\s+(\S.*)", ln)
                if m_header:
                    current_date = parse_date_str(m_header.group(1))
                    rest = m_header.group(2)
                    tokens = [
                        tok.strip() for tok in re.split(r"\s{2,}", rest) if tok.strip()
                    ]
                    while len(header_field_names) < len(tokens):
                        header_field_names.append(f"field{len(header_field_names) + 1}")
                    current_headers = {"data": current_date}
                    for name, token in zip(header_field_names, tokens):
                        current_headers[name] = token
                    for name in header_field_names[len(tokens) :]:
                        current_headers[name] = None
                    buffer.clear()
                    continue

                if not buffer:
                    if re.match(r"\d+", ln.strip()):
                        logging.info("starting buffer %s", ln)
                        buffer.append(ln)
                    else:
                        continue
                else:
                    buffer.append(ln)

                if _AMOUNT_RE.search(ln):
                    candidate = " ".join(buffer)
                    buffer.clear()
                    m = ROW_RE.match(candidate)
                    if not m:
                        continue
                    riga = m.group("riga")
                    conto = m.group("conto").replace(" ", "")
                    desc = m.group("descrizione").strip()
                    amount = _parse_amount(m.group("amount"))
                    if re.search(r"\s{2,}", desc):
                        account_desc, operation_desc = re.split(r"\s{2,}", desc, 1)
                        account_desc = account_desc.strip()
                        operation_desc = operation_desc.strip()
                    else:
                        account_desc = None
                        operation_desc = desc
                    rows.append(
                        {
                            **current_headers,
                            "riga": riga,
                            "conto": conto,
                            "descrizione_conto": account_desc,
                            "descrizione_operazione": operation_desc,
                            "amount": amount,
                        }
                    )

    return pl.DataFrame(rows) if rows else pl.DataFrame()


def parse_pdf_posting_groups(data: Any) -> pl.DataFrame:
    """Parse multi-line postings grouped from riga to amount.

    Parameters
    ----------
    data:
        Bytes, path or file-like object with the PDF content.

    Returns
    -------
    pl.DataFrame
        A DataFrame with columns: data, causale, attivita, filiale,
        riga, conto, descrizione_conto, descrizione_operazione,
        dare and avere.

        Returns an empty DataFrame if no rows are found.
    """

    pdf_bytes = _as_bytes(data)
    rows: list[dict[str, Any]] = []
    current_date: Any | None = None
    current_causale: str | None = None
    current_attivita: str | None = None
    current_filiale: str | None = None

    from .logic import parse_amount as _parse_amount

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            left_x, right_x = infer_dare_avere_x_positions(page)
            amount_iter = iter(
                (
                    (w["x0"] + w["x1"]) / 2
                    for w in page.extract_words(x_tolerance=1, y_tolerance=3)
                    if _AMOUNT_RE.fullmatch(w.get("text", ""))
                )
            )
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            i = 0
            while i < len(lines):
                ln = lines[i]
                up = ln.upper()

                if (
                    up.startswith("PARTITA IVA")
                    or up.startswith("CODICE FISCALE")
                    or "GIORNALE DI CONTABILIT" in up
                    or up.startswith("ATTIVITA FILIALE DATA REGISTRAZIONE CAUSALE")
                    or up.startswith("RIPORTI")
                    or up.startswith("TOTALE PAGINA")
                    or up.startswith("ULTIMA RIGA")
                ):
                    i += 1
                    continue

                date, causale, attivita, filiale, new_i = _parse_header(lines, i)
                if date is not None:
                    current_date = date
                    current_causale = causale
                    current_attivita = attivita
                    current_filiale = filiale
                    i = new_i
                    continue

                if re.fullmatch(r"\d+", ln):
                    buffer = [ln]
                    j = i + 1
                    while j < len(lines):
                        next_ln = lines[j]
                        if _AMOUNT_RE.search(next_ln):
                            buffer.append(next_ln)
                            j += 1
                            break
                        if re.fullmatch(r"\d+", next_ln) and len(buffer) > 1:
                            break
                        buffer.append(next_ln)
                        j += 1
                    candidate = " ".join(
                        part.strip() for part in buffer if part.strip()
                    )
                    candidate = re.sub(r"^(\d+)\s+", r"\1 ", candidate)
                    m = ROW_RE.match(candidate)
                    if m:
                        riga = m.group("riga")
                        conto = m.group("conto").replace(" ", "")
                        descr = m.group("descrizione").strip()
                        amount = _parse_amount(m.group("amount"))
                        x_amt = next(amount_iter, None)
                        dare = avere = None
                        if x_amt is not None and right_x != left_x:
                            if abs(x_amt - right_x) < abs(x_amt - left_x):
                                avere = amount
                            else:
                                dare = amount
                        else:
                            dare = amount
                        if re.search(r"\s{2,}", descr):
                            account_desc, operation_desc = re.split(r"\s{2,}", descr, 1)
                            account_desc = account_desc.strip()
                            operation_desc = operation_desc.strip()
                        else:
                            account_desc = None
                            operation_desc = descr
                        rows.append(
                            {
                                "data": current_date,
                                "causale": current_causale,
                                "attivita": current_attivita,
                                "filiale": current_filiale,
                                "riga": riga,
                                "conto": conto,
                                "descrizione_conto": account_desc,
                                "descrizione_operazione": operation_desc,
                                "dare": dare,
                                "avere": avere,
                            }
                        )
                    i = j
                    continue

                i += 1

    return pl.DataFrame(rows) if rows else pl.DataFrame()
