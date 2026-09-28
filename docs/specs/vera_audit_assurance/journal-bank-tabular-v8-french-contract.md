# Tabular adapter v8: reviewed French dates

The explicit reviewed mapping `date_locale: fr` selects
`journal_bank.tabular.v8`, version `8`. It preserves the source, mapping,
implementation and review-receipt bindings of the existing adapter. Changing
the locale requires a new source-bound mapping review. French is a parsing
setting, not a choice of governing law or currency.

Accepted textual dates contain day, French month, four-digit year separated
by horizontal spaces. Case and accents are normalized. Full month names and
the explicit abbreviations janv, févr, avr, juil, sept, oct, nov and déc are
supported, optionally followed by a full stop. Calendar validity is required.
Unknown words, two-digit textual years and invalid dates reject the source;
there is no model fallback or partial population emission.

No locale retains the v6 path; Italian or summary-only mappings retain v7.
The frozen v7 contract is unchanged. Numeric date conventions, exact reviewed
summary exclusions, amount parsing and matching methods remain common.
Synthetic French date and receipt regressions establish mechanical behavior.
No independent real-source holdout or Geneva professional acceptance is claimed.
