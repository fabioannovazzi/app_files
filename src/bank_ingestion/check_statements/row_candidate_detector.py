"""Row Candidate Detector for bank statements."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, List, Sequence

from .filters import is_header_footer, is_summary_or_notice, is_total_or_balance_only
from .schemas import RowCandidate

# Row hint lexicon for simple inclusion scoring
ROW_HINTS = {
    "it": ["disposizione", "bonifico", "addebito", "accredito", "valuta"],
    "de": ["buchung", "\u00fcberweisung", "lastschrift", "gutschrift", "valuta"],
    "fr": ["op\u00e9ration", "virement", "pr\u00e9l\u00e8vement", "cr\u00e9dit", "valeur"],
    "en": ["transaction", "transfer", "debit", "credit", "value date"],
}


class RowCandidateDetector:
    """Detect transaction-like rows from raw lines."""

    DATE_RE = re.compile(
        r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})\b"
    )
    AMOUNT_RE = re.compile(
        r"[+-]?\d{1,3}(?:[.,'\s]\d{3})*(?:[.,]\d{2})"
    )

    def detect(
        self,
        page_lines: Sequence[Dict[str, float | str]],
        page_index: int,
        page_height: float,
        lang: str = "en",
    ) -> List[RowCandidate]:
        """Return row candidates for a single page.

        Args:
            page_lines: sequence of dicts with keys `text`, `x0`, `x1`, `y0`, `y1`.
            page_index: index of page within document.
            page_height: height of page for header/footer detection.
            lang: detected language code.
        """

        candidates: List[RowCandidate] = []
        hints = ROW_HINTS.get(lang, [])
        for line in page_lines:
            text = str(line.get("text", ""))
            x0 = float(line.get("x0", 0))
            x1 = float(line.get("x1", 0))
            y0 = float(line.get("y0", 0))
            y1 = float(line.get("y1", 0))
            features: Dict[str, float] = {}
            reason_flags: List[str] = []
            score = 0.0

            has_date = bool(self.DATE_RE.search(text))
            features["has_date"] = 1.0 if has_date else 0.0
            if has_date:
                score += 0.4
            else:
                reason_flags.append("no_date")

            has_amount = bool(self.AMOUNT_RE.search(text))
            features["has_amount"] = 1.0 if has_amount else 0.0
            if has_amount:
                score += 0.2
            else:
                reason_flags.append("no_amount")

            # crude column alignment bonus
            if x0 and x1:
                score += 0.1
                features["aligned"] = 1.0
            else:
                features["aligned"] = 0.0

            if any(h in text.lower() for h in hints):
                score += 0.1
                features["lexical_hint"] = 1.0
            else:
                features["lexical_hint"] = 0.0

            if is_summary_or_notice(text, lang):
                score -= 0.2
                reason_flags.append("summary_keyword")

            if is_header_footer(y0, page_height) or is_header_footer(y1, page_height):
                score -= 0.2
                reason_flags.append("footer_band")

            if is_total_or_balance_only(text):
                reason_flags.append("total_only")
                score -= 0.2

            score = max(0.0, min(1.0, score))

            if score >= 0.5:
                cand = RowCandidate(
                    page_index=page_index,
                    y_top=y0,
                    y_bottom=y1,
                    x_spans=[(x0, x1)],
                    raw_text=text,
                    lang=lang,
                    features=features,
                    reason_flags=reason_flags,
                    score=score,
                )
                candidates.append(cand)
        return candidates
