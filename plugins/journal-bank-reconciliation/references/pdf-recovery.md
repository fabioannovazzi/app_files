# Agent-led recovery of registration PDF layouts

Use this maintained recovery route after a registration-layout failure, before
closing the run as unsupported. The host agent interprets evidence and revises
recipes or writes a run-local adapter; tools perform bounded local trials and
exact replay. Keep the host's ordinary inspection, image viewing and coding
abilities available. The host chooses how to interpret unfamiliar evidence.
The installed checker independently reconstructs amounts and enforces controls.
No helper calls a model or changes the installed plugin. A local recovery is
not a reusable product fix. OCR-only sources cannot qualify through this text
word-reference contract; preserve their readable evidence and unresolved status.

## Same case, bounded attempts

Keep the same running Studio Archive context and immutable journal input. Use
only the workflow's existing output directory. The recovery tools write its
`pdf_recovery` child, retaining source and implementation hashes, inspection
artifacts, every candidate recipe and its diagnostics. Four distinct trials and
twelve targeted inspections are permitted. Identical recipes cannot be retried.
Do not reset the history or create another run to evade those limits. A changed
source or implementation invalidates the session.

1. Read the ordinary inspection and rejection reasons. Inspect the failed page
   and adjacent pages with `--pdf-recovery inspect --pdf-pages N ...`; at most
   three pages per request. Add `--pdf-region X0 TOP X1 BOTTOM` to focus evidence,
   and `--pdf-render` when a visual resolves the question. Each page returns at
   most 300 words and 1,200 glyphs with coordinates and explicit truncation flags.
   Request another region if the relevant evidence was truncated. Read the saved
   images through the host's image-viewing capability.
2. Form a concrete hypothesis from that evidence. Review the physical account,
   description and amount bands, registration structure, separator glyphs and
   footer meaning. Configure the maintained options or the run-local adapter
   contract below. Resolve routine
   coordinates yourself; ask the professional only for unresolved accounting
   meaning, currency or evidence. Never infer an opening total from the first
   printed total just to make the numbers agree.
3. Save the proposed ordinary workflow recipe in the run. Use
   `--pdf-recovery trial --recipe <proposed-recipe> --pdf-reason <evidence-and-change>`.
   With ruled-layout options, every trial first scans the complete PDF for
   unsupported negative amount notation or missing sign decisions. It reports
   all affected locations together. The retained
   attempt contains the complete list under `negative_amount_eligibility`;
   the tool response shows at most 50 issues. This scan checks notation only,
   not layout completeness. Partial reading scans all pages and retains the
   entries it can reconstruct with explicit issues. Both passes release page caches.
   A successful trial covers the entire source;
   it does not authorize sampling. Review the diagnostics and suggested failure
   pages. Revise only when new evidence explains the failure. Inspect additional
   pages not used to develop the recipe, including a continuation and the final
   total where available. The tool does not attest to the model's visual review.
4. After a successful trial and review of those independent pages, run
   `--pdf-recovery freeze` with the exact same recipe. This freshly replays the
   complete PDF and compares postings and diagnostics with the successful trial.
   It saves `frozen_layout.json` and `freeze_receipt.json`; neither is a mapping
   approval or a qualified population. Copy the exact frozen layout, including
   `source_sha256`, into the ordinary workflow recipe. Reinspect, obtain the
   existing source-mapping decision receipt, normalize and continue through all
   existing replay/qualification and downstream gates.
5. If inspection or trial limits are exhausted, or evidence remains ambiguous,
   retain the full recovery history, report the specific remaining problem and
   deliver the readable CSV and its unresolved issues, then close the run with
   its existing failed/blocked lifecycle. Do not adjust
   amounts, invent accounts, skip malformed registrations or relax controls.

For Journal Sampling use the existing `scripts/inspect_journal.py` command with
its bound input, `--output-dir <run-output>/normalization` and
`--client-engagement <context>`. The proposed layout is
`files[filename].layout` with `parser: registration_pdf`.
For Journal–Bank use the existing `scripts/inspect_inputs.py` command with its
bound bank/journal paths, output directory and context. The proposed layout is
`journal.files[filename].pdf_registration_layout`.
Both commands require `--pdf-currency <reviewed ISO code>` during recovery.
All other required command arguments and execution-integrity checks still apply.

## Run-local adapter contract

Use this when the built-in registration parser does not understand the source
structure. First run `--pdf-recovery inventory --recipe <recipe>`. Read its
local `inventory_path`: every PDF word has an ID, page, physical row, text and
coordinates. This full evidence stays local; select only necessary regions for
model reasoning. The proposed five column bands, body, separator rules and
explicit sign policy remain part of the mapping contract.

Write a Python adapter under the same workflow output directory using the
host's normal coding tools. It reads the inventory JSON on stdin and emits
exactly `{"rows": [...]}` on stdout. Each row has only:

```json
{
  "amount": "p1w12", "side": "debit",
  "account": ["p1w9"], "description": ["p1w10", "p1w11"],
  "date": "p1w4", "registration": "p1w2"
}
```

These IDs are illustrative, never defaults. An empty description is permitted.
Account and description references must retain source order and belong to the
reviewed bands between the registration header and that posting. Date and
registration references identify the same source header line. The date format
is explicitly `%d/%m/%Y` (default) or `%Y-%m-%d`. The adapter cannot supply
amounts, invent text, emit its own qualification or choose its own controls.

Add `agent_adapter: {"path": "<absolute run-local .py>", "sha256": "<code hash>"}`
to the layout and run the ordinary trial. Each distinct adapter/recipe revision
uses the same four-attempt budget. Record the diagnosis, source evidence and
change in `--pdf-reason`. The runner snapshots the code, runs it in a separate
Python process with a 60-second limit, and checks source/checker hashes before
and after execution. This is not an operating-system sandbox; normal host
permissions still apply. Do not use the adapter to modify installed checks,
access unrelated client files, install packages, or contact external services.

The independent checker obtains values from original PDF tokens, rejects
duplicated or unclaimed monetary tokens, checks physical sides and account
references, checks registration balances and recomputes printed running totals.
The adapter route requires reviewed printed controls on every page; absent
controls leave readable results unqualified. These mechanical checks do not
establish semantic correctness: review the actual account/header mapping and
scope through the existing source-bound decision receipt. Matching totals
alone never approve a source. Freeze reruns the exact code and checks the
complete source again. Subsequent normalization/reconciliation rechecks the
adapter digest and reruns the independent validator.

## Partial results and incident recovery

Every trial retains `readable-entries-NN.json` and a corresponding CSV with
`unqualified_requires_review` on each row. Ordinary PDF inspection also writes
`readable_pdf_entries.csv`; its inspection JSON holds the unresolved issues.
Show useful readable entries and explain the specific missing evidence. An
issue elsewhere does not erase them. Keep sampling, population statistics and
completed reconciliation blocked until the complete source qualifies.

Use the managed command so the existing incident outbox automatically records
handled failures, correction attempts and matching fresh replay as one episode.
Automatic reports contain fixed technical categories, check results and counts;
source text, amounts, paths, adapter code and free-text rationale stay local.
Inspect the retained attempt and supplement the original incident through the
existing incident connector with the relevant technical diagnosis and how the
correction addressed it, excluding client content. For example, report an
observed syntax issue as such, not a generic success claim. Respect local-only
delivery and retain its queue. Do not create a second incident for a retry.

A freeze reports extraction recovery, not completion of the original task.
Resume the same mapping/normalization/reconciliation workflow. Only after its
ordinary independent gates and actual outputs verify the original request may
the host send the existing original-task recovery outcome. Record remaining
unresolved issues even when part of the work succeeded. A reusable source fix
needs a separate code review and regression fixture; never auto-promote it.

## Optional ruled-layout contract

The existing `body`, five non-overlapping `columns` and source mapping remain.
Without any keys below the reader retains its existing layout and amount support;
unsupported negative formats receive the specific diagnostics described below.
Presence of a key enables the strict `rule_delimited.v1` extension. Its full
configuration is included in the normal source-mapping receipt and its code is
included in the implementation/replay receipts. The parent adapter identifiers
and versions remain unchanged for compatibility; extension version 1 is explicit
in reader diagnostics and these option semantics.

```json
{
  "rule_characters": {
    "text": "!",
    "x0": ["20", "96.8", "173.6", "404", "485.6", "567.2"],
    "tolerance": "0.5"
  },
  "border_art": {"characters": "+-"},
  "running_totals": {
    "labels": ["TOTALI PROGRESSIVI"],
    "opening_debit": "0",
    "opening_credit": "0",
    "required_each_page": true
  }
}
```

These coordinates are synthetic examples, not defaults for customer documents.

- `rule_characters` permits `!` or `|` only at the reviewed x positions within
  the body. Positions are sorted, unique decimal strings; tolerance is a decimal
  string greater than zero and at most one point. All configured positions must
  be observed on every page. Other punctuation remains. Characters are filtered
  before word grouping so account glyphs retain their own bounding boxes.
- `border_art` accepts exactly the configuration shown. Headers/continuations
  may be surrounded by `+`, `-` and spaces. Other text on a decorated header is
  rejected. Only wholly decorative lines are skipped. In this mode existing
  `ignored_line_prefixes` entries are exact nonmonetary line labels, not wildcard
  prefixes; `+-` cannot swallow a malformed header. Review actual printed header
  labels or place the ordinary page heading outside the body.
- `running_totals` identifies exact reviewed textual labels, ignoring whitespace
  and case to handle spaced lettering. Labels belong to the description band;
  each amount must occupy its reviewed amount band. The reader requires one
  control per page, recomputes each signed source side from the explicit opening
  totals plus source postings, and rejects mismatches or postings after the footer. A total
  may be outside the posting body but is still processed. Unrecognized monetary
  content outside the body is rejected. An opening balance requires source
  evidence; this option never supplies a missing registration or continuation.

### Reviewed negative amounts

Negative postings require both optional keys below in the layout. Record the
professional's decision in the ordinary source-mapping review; the recovery
trial and freeze do not approve accounting semantics. Do not add these choices
merely to make a failed trial pass.

```json
{
  "negative_amount_notation": "trailing_minus",
  "negative_amount_semantics": "signed_side"
}
```

- `negative_amount_notation`: `trailing_minus` accepts `25,88-` and
  `1.234,56-`; `leading_minus` accepts `-25,88`. Positive amounts remain valid.
  These are exact, mutually exclusive negative formats. Parentheses, mixed
  formats and doubled signs are not authorized by either choice.
- `negative_amount_semantics`: `signed_side` keeps the negative value in its
  printed debit/credit column; `opposite_side` emits the absolute amount on the
  other side, preserving the original account. For example, a debit `25,88-`
  becomes debit `-25.88` or credit `25.88`, respectively. There is no default.
- Registration balances use the emitted postings. Printed running totals always
  use signed source columns, including when output sides are reversed; they
  must reconcile to the source printout. Negative printed totals use the same
  reviewed notation. Diagnostics identify this basis as `signed_source_sides`.
- Negative posting records retain `source_amount_text`, `source_amount_side`
  and the chosen semantics alongside the existing page/row/account lineage.
  Both choices are sealed in the layout/replay/source-mapping receipts.
- Without a reviewed policy, trailing-minus and parenthesized amounts report
  `unsupported_negative_amount_notation`; leading-minus amounts report
  `negative_amount_side_requires_review`. Each issue includes its page, row,
  amount band and printed token. No qualified postings are emitted from an
  ineligible PDF; readable entries remain available separately.

An excerpt starting mid-registration remains incomplete. Every completed
registration must balance, every posting must have its account and amount, and
continuation dates must agree. Cumulative controls supplement those checks:
matching debit and credit alone cannot prove completeness. Duplicate registration
numbers, missing continuation markers, shifted rules and unassigned amounts
withhold the entire population. A successful synthetic test or single-page
inspection does not establish acceptance of an unseen full customer document.
