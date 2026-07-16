# Locales And Wording

Load this reference when choosing language settings or writing operational evidence requests.

Default operational language is Italian. Supported language packs are Italian, English, French, and German where implemented by the local language files.

Language affects labels and explanations only. Evidence thresholds, rule codes, and matching standards must stay language-neutral.

Infer the working language from the user's explicit request, marketplace/page prompt, or document context. If the language is not clear, ask once before running the workflow. Do not silently assume Italian for a non-Italian user.

When running helper scripts, pass the selected language explicitly in assumptions:

- `locale`: selected interface/report code;
- `report_language`: selected output language;
- `document_language`: selected source-document language, or `auto` only when the file set is mixed or unclear.

Supported codes are `it`, `en`, `fr`, and `de`.

For targeted evidence requests, do not expose internal labels such as `closed`, `open_supported`, `needs_evidence`, or rule names as operational categories. Use the localized categories produced by `scripts/build_missing_evidence_requests.py`.
