from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping, Optional

from journal_ingest.config import LayoutConfig
from journal_ingest.core import BaseJournalParser


class JournalStrategyTextLayout(BaseJournalParser):
    """Parse plain text journal layouts using shape heuristics.

    The strategy expects mono-spaced text where each page is separated by a
    form-feed (``\f``).  It can operate on raw PDF bytes via an injected
    *extractor* callable or directly on pre-extracted text provided through
    ``meta['layout_text']``.
    """

    DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
    ACCOUNT_RE = re.compile(r"\d+(?:\s*[\/\-.]\s*\d+){1,3}")
    AMOUNT_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})*[.,]\d{2}")

    def __init__(
        self,
        config: LayoutConfig,
        extractor: Callable[[bytes], str] | None = None,
    ) -> None:
        self.config = config
        self.extractor = extractor

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _extract_text(self, file_bytes: bytes, meta: Mapping[str, Any] | None) -> str:
        if meta and meta.get("layout_text"):
            return meta["layout_text"]
        if self.extractor:
            return self.extractor(file_bytes)
        return ""

    @staticmethod
    def _parse_number(token: str) -> float:
        token = token.strip().replace("\u00a0", "")
        if "," in token and "." in token:
            decimal = "," if token.rfind(",") > token.rfind(".") else "."
            thousands = "." if decimal == "," else ","
        elif "," in token:
            decimal = ","
            thousands = ""
        else:
            decimal = "."
            thousands = ""
        token = token.replace(thousands, "").replace(decimal, ".")
        return float(token)

    def _parse_date(self, line: str) -> Optional[datetime]:
        match = self.DATE_RE.search(line)
        if not match:
            return None
        token = match.group(0)
        for fmt in self.config.date_formats:
            try:
                return datetime.strptime(token, fmt)
            except ValueError:
                continue
        return None

    def _parse_detail_line(self, line: str) -> dict[str, Any] | None:
        if self.config.detail_regex:
            m = re.match(self.config.detail_regex, line)
            if m:
                d = m.groupdict()
                return {
                    "line_no": int(d.get("line_no")) if d.get("line_no") else None,
                    "account_code": d.get("account_code"),
                    "account_desc": d.get("account_desc", ""),
                    "memo": d.get("memo", ""),
                    "debit_raw": d.get("debit"),
                    "credit_raw": d.get("credit"),
                }
        tokens = line.split()
        if not tokens:
            return None
        line_no: int | None = None
        idx = 0
        if re.fullmatch(r"\d+", tokens[0]):
            line_no = int(tokens[0])
            idx = 1
        account_code = None
        acct_idx = idx
        for j in range(idx, len(tokens)):
            if self.ACCOUNT_RE.fullmatch(tokens[j]):
                account_code = tokens[j]
                acct_idx = j
                break
        if not account_code:
            return None
        amount_tokens: list[str] = []
        for tok in reversed(tokens):
            if self.AMOUNT_RE.fullmatch(tok):
                amount_tokens.append(tok)
                if len(amount_tokens) == 2:
                    break
        amount_tokens = list(reversed(amount_tokens))
        if not amount_tokens:
            return None
        amt_start = len(tokens) - len(amount_tokens)
        desc_tokens = tokens[acct_idx + 1 : amt_start]
        account_desc = " ".join(desc_tokens).strip()
        debit = amount_tokens[0]
        credit = amount_tokens[1] if len(amount_tokens) > 1 else None
        return {
            "line_no": line_no,
            "account_code": account_code,
            "account_desc": account_desc,
            "memo": "",
            "debit_raw": debit,
            "credit_raw": credit,
        }

    # ------------------------------------------------------------------
    # BaseJournalParser API
    # ------------------------------------------------------------------
    def probe(self, file_bytes: bytes, meta: Mapping[str, Any] | None = None) -> float:
        text = self._extract_text(file_bytes, meta)
        if not text:
            return 0.0
        pages = text.split("\f")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return 0.0
        amount_lines = sum(bool(self.AMOUNT_RE.search(ln)) for ln in lines)
        date_lines = sum(bool(self.DATE_RE.match(ln)) for ln in lines)
        code_lines = sum(bool(self.ACCOUNT_RE.search(ln)) for ln in lines)
        page_count = max(1, len(pages))
        parts = [
            amount_lines / len(lines),
            min(1.0, date_lines / page_count),
            code_lines / len(lines),
        ]
        return sum(parts) / 3.0

    def parse(
        self, file_bytes: bytes, meta: Mapping[str, Any] | None = None
    ) -> Iterable[dict[str, Any]]:
        text = self._extract_text(file_bytes, meta)
        if not text:
            return []

        pages_raw = text.split("\f")
        lines: list[tuple[int, str]] = []
        for pno, page in enumerate(pages_raw, start=1):
            for ln in page.splitlines():
                ln = ln.rstrip()
                if ln:
                    lines.append((pno, ln))
        if not lines:
            return []

        page_count = len(pages_raw)
        freq: dict[str, int] = {}
        for _, ln in lines:
            freq[ln] = freq.get(ln, 0) + 1
        header_lines = {
            ln
            for ln, cnt in freq.items()
            if cnt / page_count > 0.6 and not self.AMOUNT_RE.search(ln)
        }
        lines = [(p, ln) for p, ln in lines if ln not in header_lines]

        rows: list[dict[str, Any]] = []
        prev_total: tuple[float, float] | None = None
        idx = 0
        while idx < len(lines):
            page = lines[idx][0]
            page_lines: list[str] = []
            while idx < len(lines) and lines[idx][0] == page:
                page_lines.append(lines[idx][1])
                idx += 1
            if not page_lines:
                continue

            if prev_total and page_lines:
                first = page_lines[0]
                amts = self.AMOUNT_RE.findall(first)
                if len(amts) == 2:
                    nums = [self._parse_number(a) for a in amts]
                    if (
                        abs(nums[0] - prev_total[0]) <= 0.01
                        and abs(nums[1] - prev_total[1]) <= 0.01
                    ):
                        page_lines = page_lines[1:]

            candidate_total: Optional[str] = None
            if page_lines:
                last = page_lines[-1]
                if len(self.AMOUNT_RE.findall(last)) == 2 and len(last.strip()) < 40:
                    candidate_total = page_lines.pop()

            current_date: Optional[datetime] = None
            current_rows: list[dict[str, Any]] = []
            for ln in page_lines:
                if self.DATE_RE.match(ln) and not self.AMOUNT_RE.findall(ln[10:]):
                    current_date = self._parse_date(ln)
                    continue
                detail = self._parse_detail_line(ln)
                if detail:
                    detail["entry_date"] = current_date
                    current_rows.append(detail)

            page_debit = sum(
                self._parse_number(r["debit_raw"])
                for r in current_rows
                if r.get("debit_raw")
            )
            page_credit = sum(
                self._parse_number(r["credit_raw"])
                for r in current_rows
                if r.get("credit_raw")
            )

            if candidate_total:
                amts = self.AMOUNT_RE.findall(candidate_total)
                nums = [self._parse_number(a) for a in amts]
                if (
                    len(nums) == 2
                    and abs(nums[0] - page_debit) <= 0.01
                    and abs(nums[1] - page_credit) <= 0.01
                ):
                    prev_total = (nums[0], nums[1])
                else:
                    detail = self._parse_detail_line(candidate_total)
                    if detail:
                        detail["entry_date"] = current_date
                        current_rows.append(detail)
                        page_debit = sum(
                            self._parse_number(r["debit_raw"])
                            for r in current_rows
                            if r.get("debit_raw")
                        )
                        page_credit = sum(
                            self._parse_number(r["credit_raw"])
                            for r in current_rows
                            if r.get("credit_raw")
                        )
                        prev_total = (page_debit, page_credit)
            else:
                prev_total = (page_debit, page_credit)

            by_date: dict[datetime, list[dict[str, Any]]] = {}
            for r in current_rows:
                dt = r.get("entry_date")
                if dt is None:
                    continue
                by_date.setdefault(dt, []).append(r)

            for dt, items in by_date.items():
                debit_sum = sum(
                    self._parse_number(r["debit_raw"])
                    for r in items
                    if r.get("debit_raw")
                )
                credit_sum = sum(
                    self._parse_number(r["credit_raw"])
                    for r in items
                    if r.get("credit_raw")
                )
                if abs(debit_sum - credit_sum) > 0.01:
                    raise AssertionError("entry not balanced")
                for r in items:
                    rows.append(
                        {
                            "entry_date": dt.date(),
                            "line_no": r.get("line_no"),
                            "account_code": r.get("account_code"),
                            "account_desc": r.get("account_desc", ""),
                            "memo": r.get("memo", ""),
                            "debit": (
                                self._parse_number(r["debit_raw"])
                                if r.get("debit_raw")
                                else None
                            ),
                            "credit": (
                                self._parse_number(r["credit_raw"])
                                if r.get("credit_raw")
                                else None
                            ),
                        }
                    )
        return rows
