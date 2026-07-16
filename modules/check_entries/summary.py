from __future__ import annotations

import datetime as _dt
import re
from typing import Iterable

import polars as pl

from modules.check_entries.constants import (
    LANGUAGE_ALIASES,
    LOCALIZED_STRINGS,
    MISMATCH_SEVERITY,
    SEVERITY_LABELS,
    MismatchSeverity,
)
from modules.check_entries.utils import flatten_mismatches
from src.io_utils import get_schema_and_column_names

# ---------------------------------------------------------------------------
# Localised templates and section headings
# ---------------------------------------------------------------------------
SUMMARY_TEMPLATE: dict[str, str] = {
    "eng": (
        "The check reviewed {total} entries with PDF: {passed} passed, {mismatches} mismatches, {no_pdf} without PDF."
    ),
    "ita": (
        "Il controllo ha analizzato {total} registrazioni con PDF: {passed} verificate, {mismatches} discordanze, {no_pdf} senza PDF."
    ),
    "fra": (
        "Le contrôle a analysé {total} écritures avec PDF : {passed} validées, {mismatches} divergences, {no_pdf} sans PDF."
    ),
    "deu": (
        "Die Prüfung hat {total} Buchungen mit PDF geprüft : {passed} korrekt, {mismatches} Abweichungen, {no_pdf} ohne PDF."
    ),
}

CATEGORY_SECTION = {
    "eng": "Mismatch categories",
    "ita": "Categorie di discordanze",
    "fra": "Catégories d'écart",
    "deu": "Abweichungskategorien",
}

EXAMPLES_SECTION = {
    "eng": "Representative examples",
    "ita": "Esempi rappresentativi",
    "fra": "Exemples représentatifs",
    "deu": "Beispiele",
}

MOVEMENT_LABEL = {
    "eng": "entry",
    "ita": "movimento",
    "fra": "mouvement",
    "deu": "Buchung",
}

SEVERITY_SUMMARY = {
    "eng": "Overall mismatches: {counts}.",
    "ita": "Nel complesso sono state rilevate {counts}.",
    "fra": "Au total, {counts}.",
    "deu": "Insgesamt wurden {counts} festgestellt.",
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _truncate_explanation(text: str, limit: int = 120) -> str:
    """Normalise dates and truncate *text* for display."""

    def _date_repl(match: re.Match[str]) -> str:
        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    text = re.sub(
        r"datetime\.date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)", _date_repl, text
    )
    text = text.replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _extract_amount_diff(expl: str) -> float | None:
    """Return absolute amount difference if it can be parsed."""

    m = re.search(r"expected\s+([\d.,]+)\D+found\s+([\d.,]+)", expl)
    if not m:
        m = re.search(r"previsto\s+([\d.,]+)\D+trovato\s+([\d.,]+)", expl)
    if m:
        a = float(m.group(1).replace(",", "."))
        b = float(m.group(2).replace(",", "."))
        return abs(a - b)
    return None


def _extract_date_diff(expl: str) -> int | None:
    """Return absolute date difference in days if ISO dates can be parsed."""

    dates = re.findall(r"(\d{4}-\d{2}-\d{2})", expl)
    if len(dates) >= 2:
        d1 = _dt.date.fromisoformat(dates[0])
        d2 = _dt.date.fromisoformat(dates[1])
        return abs((d2 - d1).days)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def summarize_results(
    llm_wrapper,  # kept for API compatibility; not used
    result_df: pl.DataFrame,
    lang: str = "eng",
    confirmed_ids: Iterable[str] | None = None,
) -> tuple[str, dict[str, pl.DataFrame]]:
    """Create a human-readable summary for *result_df*.

    The function aggregates mismatch information and returns a summary text and
    metrics. Only aggregate numbers are reported, with one example per mismatch
    type.
    """

    lang_code = LANGUAGE_ALIASES.get(lang.lower(), lang.lower())
    translations = LOCALIZED_STRINGS.get(lang_code, LOCALIZED_STRINGS["eng"])
    severity_labels = SEVERITY_LABELS.get(lang_code, SEVERITY_LABELS["eng"])
    movement_word = MOVEMENT_LABEL.get(lang_code, MOVEMENT_LABEL["eng"])

    reverse_severity_labels = {
        label.lower(): sev.value for sev, label in severity_labels.items()
    }
    severity_messages: list[str] = []

    def _resolve_severity(value: str | None) -> MismatchSeverity:
        """Return ``MismatchSeverity`` for *value* with fallback."""

        if value is None:
            return MismatchSeverity.MINOR
        canonical = reverse_severity_labels.get(value.lower(), value)
        try:
            return MismatchSeverity(canonical)
        except ValueError:
            severity_messages.append(
                f"Unknown mismatch severity '{value}', defaulting to {MismatchSeverity.MINOR.value}"
            )
            return MismatchSeverity.MINOR

    def _resolve_severity_str(value: str | None) -> str | None:
        if value is None:
            return None
        return _resolve_severity(value).value

    # ------------------------------------------------------------------
    # Overall counts
    # ------------------------------------------------------------------
    with_pdf = result_df.filter(pl.col("check_status") != "no_pdf").height
    passed = result_df.filter(pl.col("check_status").is_in(["ok", "verified"])).height
    mismatch_rows = result_df.filter(pl.col("check_status") == "mismatch")
    mismatch_count = mismatch_rows.height
    no_pdf = result_df.filter(pl.col("check_status") == "no_pdf").height

    # ------------------------------------------------------------------
    # Prepare mismatch details
    # ------------------------------------------------------------------
    mismatch_breakdown = pl.DataFrame(
        {"mismatch_type": [], "severity": [], "count": []}
    )
    severity_totals = pl.DataFrame({"severity": [], "count": []})
    examples_lines: list[str] = []
    beneficiary_lines: list[str] = []
    beneficiary_df = pl.DataFrame({"movement_number": [], "beneficiary_extracted": []})
    beneficiary_count = 0

    if mismatch_count:
        mismatch_rows = mismatch_rows.with_row_index("row_index")
        columns, _ = get_schema_and_column_names(mismatch_rows)
        explanation_col = "explanation"
        severity_col = "severity"
        if "mismatches" in columns:
            mismatch_rows, mapping = flatten_mismatches(mismatch_rows)
            explanation_col = mapping.get("explanation", explanation_col)
            severity_col = mapping.get("severity", severity_col)
            line_col = mapping.get("line_numbers")
            if line_col and line_col in get_schema_and_column_names(mismatch_rows)[0]:
                mismatch_rows = mismatch_rows.drop(line_col)
        flat_cols, _ = get_schema_and_column_names(mismatch_rows)
        if explanation_col not in flat_cols:
            mismatch_rows = mismatch_rows.with_columns(
                pl.lit("").alias(explanation_col)
            )
        if severity_col not in flat_cols:
            mismatch_rows = mismatch_rows.with_columns(pl.lit(None).alias(severity_col))

        # Determine mismatch type
        cat_names = {
            "amount_mismatch": translations["amount_mismatch"].split(":")[0],
            "date_mismatch": translations["date_mismatch"].split(":")[0],
            "beneficiary_mismatch": translations["beneficiary_mismatch"].split(":")[0],
            "timing_difference": translations.get(
                "timing_difference", "Timing difference"
            ).split(":")[0],
            "missing_transaction": translations.get(
                "missing_transaction", "Missing transaction"
            ).split(":")[0],
            "duplicate_transaction": translations.get(
                "duplicate_transaction", "Duplicate transaction"
            ).split(":")[0],
            "fraud": translations.get("fraud", "Fraud").split(":")[0],
        }
        if "mismatch_type" in flat_cols:
            mismatches_typed = mismatch_rows.with_columns(
                pl.col("mismatch_type").fill_null("other").alias("mismatch_type")
            )
        else:
            # Infer from explanation prefix
            mismatches_typed = mismatch_rows.with_columns(
                pl.when(
                    pl.col(explanation_col).str.starts_with(
                        cat_names["amount_mismatch"]
                    )
                )
                .then(pl.lit("amount_mismatch"))
                .when(
                    pl.col(explanation_col).str.starts_with(cat_names["date_mismatch"])
                )
                .then(pl.lit("date_mismatch"))
                .when(
                    pl.col(explanation_col).str.starts_with(
                        cat_names["beneficiary_mismatch"]
                    )
                )
                .then(pl.lit("beneficiary_mismatch"))
                .when(
                    pl.col(explanation_col).str.starts_with(
                        cat_names["timing_difference"]
                    )
                )
                .then(pl.lit("timing_difference"))
                .when(
                    pl.col(explanation_col).str.starts_with(
                        cat_names["missing_transaction"]
                    )
                )
                .then(pl.lit("missing_transaction"))
                .when(
                    pl.col(explanation_col).str.starts_with(
                        cat_names["duplicate_transaction"]
                    )
                )
                .then(pl.lit("duplicate_transaction"))
                .when(pl.col(explanation_col).str.starts_with(cat_names["fraud"]))
                .then(pl.lit("fraud"))
                .otherwise(pl.lit("other"))
                .alias("mismatch_type")
            )

        # Attach severity
        severity_map = {k: v.value for k, v in MISMATCH_SEVERITY.items()}
        if severity_col in get_schema_and_column_names(mismatches_typed)[0]:
            mismatches_typed = mismatches_typed.with_columns(
                pl.col(severity_col)
                .map_elements(_resolve_severity_str, return_dtype=pl.String)
                .fill_null(
                    pl.col("mismatch_type")
                    .replace(severity_map)
                    .fill_null(MismatchSeverity.MINOR.value)
                )
                .alias("severity")
            )
        else:
            mismatches_typed = mismatches_typed.with_columns(
                pl.col("mismatch_type")
                .replace(severity_map)
                .fill_null(MismatchSeverity.MINOR.value)
                .alias("severity")
            )

        # Breakdown counts
        mismatch_breakdown = (
            mismatches_typed.group_by(["mismatch_type", "severity"])
            .agg(pl.n_unique("movement_number").alias("count"))
            .sort(["mismatch_type", "severity"])
        )
        severity_totals = (
            mismatch_breakdown.group_by("severity")
            .agg(pl.col("count").sum().alias("count"))
            .sort("severity")
        )

        # Examples
        for type_ in mismatches_typed.select("mismatch_type").unique()["mismatch_type"]:
            group = mismatches_typed.filter(pl.col("mismatch_type") == type_)
            row = group.sort("row_index").row(0, named=True)
            movement = row.get("movement_number")
            if movement is None:
                movement = row.get("row_index")
            sev_enum = _resolve_severity(row["severity"])
            sev_label = severity_labels.get(sev_enum, row["severity"].capitalize())
            expl = _truncate_explanation(row.get(explanation_col, ""))
            diff_info = ""
            if type_ == "amount_mismatch":
                diff = _extract_amount_diff(expl)
                if diff is not None:
                    diff_info = f" (diff {diff})"
            elif type_ == "date_mismatch":
                diff = _extract_date_diff(expl)
                if diff is not None:
                    diff_info = f" ({diff} giorni)"
            type_label = cat_names.get(type_, type_)
            examples_lines.append(
                f"- {type_label}: {movement_word} {movement} – {sev_label} – {expl}{diff_info}"
            )

        beneficiary_rows = mismatches_typed.filter(
            pl.col("mismatch_type") == "beneficiary_mismatch"
        )
        if beneficiary_rows.height:
            beneficiary_df = beneficiary_rows.select(
                ["movement_number", "beneficiary_extracted"]
            ).unique()
            beneficiary_count = beneficiary_df.height
            for row in beneficiary_df.iter_rows(named=True):
                line = f"- {movement_word} {row['movement_number']}"
                name = row.get("beneficiary_extracted")
                if name:
                    line += f": {name}"
                beneficiary_lines.append(line)

    # ------------------------------------------------------------------
    # Summary text
    # ------------------------------------------------------------------
    template = SUMMARY_TEMPLATE.get(lang_code, SUMMARY_TEMPLATE["eng"])
    intro = template.format(
        total=with_pdf, passed=passed, mismatches=mismatch_count, no_pdf=no_pdf
    )

    categories_heading = CATEGORY_SECTION.get(lang_code, CATEGORY_SECTION["eng"])
    categories_lines = []
    for row in mismatch_breakdown.iter_rows(named=True):
        count = row["count"]
        if count == 0:
            continue
        sev_enum = _resolve_severity(row["severity"])
        sev_label = severity_labels.get(sev_enum, row["severity"].capitalize())
        type_label = cat_names.get(row["mismatch_type"], row["mismatch_type"])
        categories_lines.append(f"- {count} {sev_label} – {type_label}")

    severity_line = ""
    if severity_totals.height:
        counts = []
        for row in severity_totals.iter_rows(named=True):
            sev_enum = _resolve_severity(row["severity"])
            label = severity_labels.get(sev_enum, row["severity"].capitalize())
            counts.append(f"{row['count']} {label}")
        template = SEVERITY_SUMMARY.get(lang_code, SEVERITY_SUMMARY["eng"])
        severity_line = template.format(counts=", ".join(counts))

    summary_parts = [intro]
    if severity_line:
        summary_parts.append(severity_line)
    if categories_lines:
        summary_parts.append(categories_heading + "\n" + "\n".join(categories_lines))
    if beneficiary_count:
        noun = "entry" if beneficiary_count == 1 else "entries"
        section = f"{beneficiary_count} {noun} had beneficiary mismatches"
        if beneficiary_lines:
            section += "\n" + "\n".join(beneficiary_lines)
        summary_parts.append(section)
    if examples_lines:
        examples_heading = EXAMPLES_SECTION.get(lang_code, EXAMPLES_SECTION["eng"])
        summary_parts.append(examples_heading + "\n" + "\n".join(examples_lines))

    summary_text = "\n\n".join(summary_parts)

    metrics_df = pl.DataFrame(
        {
            "metric": [
                "rows_with_pdf",
                "passed",
                "mismatches",
                "rows_without_pdf",
            ],
            "value": [with_pdf, passed, mismatch_count, no_pdf],
        }
    )

    metrics_out: dict[str, pl.DataFrame] = {
        "metrics": metrics_df,
        "mismatch_breakdown": mismatch_breakdown,
    }
    if beneficiary_count:
        metrics_out["beneficiary_mismatches"] = beneficiary_df
    if severity_messages:
        metrics_out["messages"] = pl.DataFrame({"message": severity_messages})

    return summary_text, metrics_out
