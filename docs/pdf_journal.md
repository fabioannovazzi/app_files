# PDF Journal Fallback

The journal parser attempts multiple strategies (tables, text layout and OCR).
If both table extraction and layout analysis fail, a posting‑group fallback
reconstructs multi‑line entries. When that also fails, a simpler text-mode
parser scans individual lines with a compact regular expression:

```python
ACCT_PATTERN = r"(?P<conto>\d+(?:\s*[*/.-]\s*\d+)+)"
```

This matches account codes with mixed separators such as `27 / 5 / 3` or
`100/20/5/1`. Lines that fit the pattern are kept even when the description
cannot be split cleanly. Amounts and dates are parsed with the same
`parse_amount` and `parse_date_str` helpers used for the Excel parser so that
values like `1.234,56` or `€7.890,12` resolve consistently.

## Posting‑group fallback

`parse_pdf_posting_groups` groups lines from the row number (`riga`) until the
next monetary amount, then expands them into a single record. Header context
(date, causale, activity and branch) is inherited by each posting. Numeric
amounts are located on the page and their `x` positions clustered by
`infer_dare_avere_x_positions` into left (Dare) and right (Avere) columns.

```python
text = (
    "01/07/2024 FATTURA ACQUISTI\n"
    "1\n"
    "27 / 5 / 3\n"
    "Prot. 3088 Example Company S.r.l.\n"
    "37,22\n"
    "2\n"
    "11 / 45 / 2\n"
    "IVA c/acquisti\n"
    "8,19\n"
)
df = parse_pdf_posting_groups(text.encode())
```

| riga | conto   | descrizione_operazione                 | dare | avere |
| ---- | ------- | -------------------------------------- | ---- | ----- |
| 1    | 27/5/3  | Prot. 3088 Example Company S.r.l.       | 37.22|       |
| 2    | 11/45/2 | IVA c/acquisti                         |      | 8.19  |

Multi‑line descriptions are concatenated into `descrizione_operazione` when no
account description is present.
