"""Opt-in physical rules for reviewed character-grid journals.

Rules implement explicit layout decisions, not semantic inference. Exact glyph
ownership and Decimal totals are mechanically replayable from the original PDF.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "RuleLayout",
    "RULE_KEYS",
    "money_candidate",
    "negative_notation",
    "signed_amount",
]
RULE_KEYS = frozenset(
    {
        "rule_characters",
        "border_art",
        "running_totals",
        "negative_amount_notation",
        "negative_amount_semantics",
    }
)
MONEY = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$|^-?\d+,\d{2}$")
UNSIGNED_MONEY = r"(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}"
NEGATIVE_NOTATIONS = {
    "leading_minus": re.compile(rf"-{UNSIGNED_MONEY}"),
    "trailing_minus": re.compile(rf"{UNSIGNED_MONEY}-"),
    "parentheses": re.compile(rf"\({UNSIGNED_MONEY}\)"),
}
HEADER = re.compile(
    r"^[+\-\s]*(?P<number>\d+)\s*-{2,}\s*"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s*-{2,}[+\-\s]*(?P<description>)$"
)
CONTINUATION = re.compile(
    r"^[+\-\s]*seguito registrazione del\s+" r"(?P<date>\d{2}/\d{2}/\d{4})\s*[+\-\s]*$",
    re.IGNORECASE,
)
Reject = Callable[[int, int, str], None]


def negative_notation(token: str) -> str | None:
    """Recognize exact printed syntax without authorizing its accounting meaning."""
    return next(
        (
            name
            for name, pattern in NEGATIVE_NOTATIONS.items()
            if pattern.fullmatch(token)
        ),
        None,
    )


def money_candidate(token: str) -> bool:
    """Recognize money for completeness checks, including unsupported negatives."""
    return bool(MONEY.fullmatch(token) or negative_notation(token))


def signed_amount(token: str) -> Decimal:
    """Decode syntax only after the reviewed policy has authorized the token."""
    negative = negative_notation(token) is not None
    magnitude = token.strip("-()").replace(".", "").replace(",", ".")
    return Decimal(magnitude) * (-1 if negative else 1)


def _number(value: Any) -> float:
    if not isinstance(value, str):
        raise ValueError("Rule coordinates require finite decimal text")
    from . import _coordinate

    return _coordinate(value)


def _canonical_money(value: Any) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d{1,2})?", value):
        raise ValueError("Opening totals require nonnegative canonical decimal text")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid opening total") from exc


def _label(value: str) -> str:
    return "".join(value.split()).casefold()


class RuleLayout:
    """Validate reviewed options and account separately for printed controls."""

    def __init__(self, layout: dict[str, Any]) -> None:
        self.body = tuple(float(v) for v in layout["body"])
        self.rule: str | None = None
        self.positions: list[float] = []
        self.tolerance = 0.0
        self.border = "border_art" in layout
        self.labels: set[str] = set()
        self.running = {"debit": Decimal("0"), "credit": Decimal("0")}
        self.totals: list[dict[str, Any]] = []
        self.removed = 0
        self.page_total_count = 0
        self.seen_registrations: set[str] = set()
        self.negative_notation = layout.get("negative_amount_notation")
        self.negative_semantics = layout.get("negative_amount_semantics")
        if {"negative_amount_notation", "negative_amount_semantics"}.intersection(
            layout
        ):
            if self.negative_notation not in ("leading_minus", "trailing_minus"):
                raise ValueError(
                    "negative_amount_notation requires leading_minus or trailing_minus"
                )
            if self.negative_semantics not in ("signed_side", "opposite_side"):
                raise ValueError(
                    "negative_amount_semantics requires signed_side or opposite_side"
                )
        if "rule_characters" in layout:
            rule = layout["rule_characters"]
            if not isinstance(rule, dict) or set(rule) != {"text", "x0", "tolerance"}:
                raise ValueError("rule_characters requires text, x0 and tolerance")
            if rule["text"] not in ("!", "|"):
                raise ValueError(
                    "Rule character must be a supported vertical separator"
                )
            positions = rule["x0"]
            if not isinstance(positions, list) or not 2 <= len(positions) <= 20:
                raise ValueError("Rule positions require 2 to 20 coordinates")
            self.positions = [_number(v) for v in positions]
            self.tolerance = _number(rule["tolerance"])
            if not 0 < self.tolerance <= 1:
                raise ValueError(
                    "Rule tolerance must be greater than zero and at most 1 point"
                )
            if self.positions != sorted(set(self.positions)) or self.positions[0] < 0:
                raise ValueError(
                    "Rule positions must be sorted, unique and nonnegative"
                )
            if any(
                b - a <= 2 * self.tolerance
                for a, b in zip(self.positions, self.positions[1:])
            ):
                raise ValueError("Rule position tolerance windows must not overlap")
            self.rule = rule["text"]
        if self.border and layout["border_art"] != {"characters": "+-"}:
            raise ValueError('border_art must be {"characters": "+-"}')
        if "running_totals" in layout:
            totals = layout["running_totals"]
            if not isinstance(totals, dict) or set(totals) != {
                "labels",
                "opening_debit",
                "opening_credit",
                "required_each_page",
            }:
                raise ValueError(
                    "running_totals needs labels, opening totals and required_each_page"
                )
            labels = totals["labels"]
            if (
                not isinstance(labels, list)
                or not labels
                or any(not isinstance(v, str) or not v.strip() for v in labels)
            ):
                raise ValueError("Running-total labels must be explicit nonempty text")
            self.labels = {_label(v) for v in labels}
            if len(self.labels) != len(labels) or any(
                not any(c.isalpha() for c in v) for v in self.labels
            ):
                raise ValueError("Running-total labels must be distinct textual labels")
            if totals["required_each_page"] is not True:
                raise ValueError(
                    "Reviewed running totals must be required on every page"
                )
            self.running = {
                side: _canonical_money(totals[f"opening_{side}"])
                for side in self.running
            }

    def amount_issue(self, token: str) -> str | None:
        """Enforce explicit notation and sign decisions; never infer a policy."""
        notation = negative_notation(token)
        if notation is None:
            return None
        if notation == "leading_minus" and self.negative_notation is None:
            return "negative_amount_side_requires_review"
        if notation != self.negative_notation:
            return "unsupported_negative_amount_notation"
        return None

    def negative_eligibility(
        self, path: Path, bands: dict[str, tuple[float, float]]
    ) -> dict[str, Any]:
        """Scan every page for unsupported amount syntax, with bounded page memory.

        This is a mechanical eligibility check, not a layout qualification. It
        retains all locations so recovery need not discover one page per trial.
        """
        import pdfplumber

        issues: list[dict[str, Any]] = []
        page_count = 0
        removed = self.removed
        with pdfplumber.open(path) as document:
            for page_count, page in enumerate(document.pages, 1):
                try:
                    # Geometry is checked by the ordinary parser. This pass only
                    # diagnoses recognized negative tokens in amount/unowned bands.
                    words = self.words(page, page_count, lambda *_: None)
                    row = 0
                    top: float | None = None
                    for word in sorted(
                        words, key=lambda w: (float(w["top"]), float(w["x0"]))
                    ):
                        if top is None or abs(top - float(word["top"])) > 2:
                            row += 1
                            top = float(word["top"])
                        token = str(word["text"])
                        reason = self.amount_issue(token)
                        if reason is None:
                            continue
                        center = (float(word["x0"]) + float(word["x1"])) / 2
                        side = next(
                            (
                                s
                                for s, (left, right) in bands.items()
                                if left <= center < right
                            ),
                            "unassigned",
                        )
                        if side not in ("debit", "credit", "unassigned"):
                            continue
                        issues.append(
                            {
                                "source_page": page_count,
                                "source_row": row,
                                "side": side,
                                "amount_text": token,
                                "notation": negative_notation(token),
                                "reason": reason,
                            }
                        )
                finally:
                    page.close()
        self.removed = removed
        return {"page_count": page_count, "issue_count": len(issues), "issues": issues}

    def words(
        self, page: Any, page_number: int, reject: Reject
    ) -> list[dict[str, Any]]:
        self.page_total_count = 0
        if self.rule is None:
            return list(page.extract_words(x_tolerance=1, y_tolerance=2))
        found = [0] * len(self.positions)

        def keep(obj: dict[str, Any]) -> bool:
            if (
                obj.get("object_type") != "char"
                or obj.get("text") != self.rule
                or not self.body[0] <= float(obj["top"]) < self.body[1]
            ):
                return True
            for index, position in enumerate(self.positions):
                if abs(float(obj["x0"]) - position) <= self.tolerance:
                    found[index] += 1
                    return False
            return True

        filtered = page.filter(keep)
        try:
            words: list[dict[str, Any]] = filtered.extract_words(
                x_tolerance=1, y_tolerance=2
            )
            if not all(found):
                reject(page_number, 0, "reviewed_rule_positions_not_present_on_page")
            self.removed += sum(found)
            return words
        finally:
            filtered.close()

    def total(
        self,
        line: list[dict[str, Any]],
        bands: dict[str, tuple[float, float]],
        page: int,
        row: int,
        reject: Reject,
    ) -> bool:
        """Consume only an exact reviewed label; verify amounts against postings."""
        text = " ".join(
            str(w["text"]) for w in line if not money_candidate(str(w["text"]))
        )
        if _label(text) not in self.labels:
            return False
        self.page_total_count += 1
        values: dict[str, list[str]] = {"debit": [], "credit": []}
        for word in line:
            token = str(word["text"])
            center = (float(word["x0"]) + float(word["x1"])) / 2
            if money_candidate(token):
                issue = self.amount_issue(token)
                if issue:
                    reject(page, row, issue)
                    continue
                owners = [s for s in values if bands[s][0] <= center < bands[s][1]]
                if len(owners) != 1:
                    reject(page, row, "running_total_outside_reviewed_amount_bands")
                    continue
                side = owners[0]
                if (
                    float(word["x0"]) < bands[side][0] - 1
                    or float(word["x1"]) > bands[side][1] + 1
                ):
                    reject(page, row, "word_crosses_reviewed_column")
                values[side].append(token)
            elif not bands["description"][0] <= center < bands["description"][1]:
                reject(page, row, "running_total_label_outside_description_band")
        if any(len(tokens) != 1 for tokens in values.values()):
            reject(page, row, "running_total_requires_two_amounts")
            return True
        printed = {s: signed_amount(v[0]) for s, v in values.items()}
        matches = printed == self.running
        if not matches:
            reject(page, row, "running_total_does_not_match_postings")
        self.totals.append(
            {
                "source_page": page,
                "source_row": row,
                "printed": {s: str(v) for s, v in printed.items()},
                "recomputed": {s: str(v) for s, v in self.running.items()},
                "matched": matches,
            }
        )
        return True

    def close_page(self, page: int, reject: Reject) -> None:
        if self.labels and self.page_total_count != 1:
            reject(page, 0, "page_requires_one_reviewed_running_total")

    def diagnostics(self) -> dict[str, Any]:
        return {
            "layout_extension": "rule_delimited.v1",
            "removed_rule_character_count": self.removed,
            "running_total_controls": self.totals,
            **(
                {
                    "negative_amount_notation": self.negative_notation,
                    "negative_amount_semantics": self.negative_semantics,
                    "running_total_basis": "signed_source_sides",
                }
                if self.negative_notation is not None
                else {}
            ),
        }
