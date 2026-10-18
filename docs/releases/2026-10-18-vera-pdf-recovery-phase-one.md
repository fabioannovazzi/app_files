# Vera PDF recovery, phase one

Character-grid journals can merge a printed `!` column rule into an account word,
place registration headers inside `+---+` borders, and print cumulative totals
in the same amount columns as postings. These structures now have an explicit,
opt-in layout contract in the shared registration reader. Existing layout
recipes retain their previous parsing behavior and diagnostics.

The host agent can recover a layout through the maintained Journal Sampling and
Journal–Bank inspection commands: inspect selected pages or regions, propose a
recipe from the evidence, run a deterministic trial, revise after a diagnosed
failure, then freeze the exact recipe after a fresh full-source replay. The
session remains inside the existing source-bound client run. It retains every
attempt, allows four distinct trials and twelve inspections, and rejects stale
source/implementation identities and repeated recipes.

The parser removes only separator glyphs at reviewed positions before grouping
words. It preserves punctuation elsewhere, carries registrations across pages,
validates explicit continuation markers and checks each registration's exact
debit/credit closure. Reviewed cumulative totals are separate controls, checked
against explicit source-supported opening totals plus postings. Malformed
headers, unassigned amounts, shifted rules, duplicate registrations and failed
controls withhold the entire population. A frozen recipe still requires the
existing mapping decision, normalization, replay and professional review gates.

The module references document the recipe and commands:

- `plugins/journal-sampling/references/pdf-recovery.md`
- `plugins/journal-bank-reconciliation/references/pdf-recovery.md`

Regression evidence includes invented ruled journals, corrupt and incomplete
populations, a byte-exact snapshot of the pre-change reader for differential
legacy tests, and the full inspect/trial/freeze cycle through both workflows in
source, Codex and Cowork managed launchers. The CI PDF job includes these cases
and enforces at least 80% shared-reader coverage. Implementation inventories and
receipts cover both new shared modules, including downstream Vouching.

The 1,274-page synthetic ruled fixture produces 3,821 expected postings; the
existing 951-page fixture produces 19,020. Run their reproducible scale checks:

```sh
python tests/plugins/journal_pdf_memory_benchmark.py --grid --pages 1274 --output-dir /tmp/vera-grid-check
python tests/plugins/journal_pdf_memory_benchmark.py --output-dir /tmp/vera-legacy-check
```

These fixtures do not establish performance or acceptance on the unseen full
customer journal. The supplied one-page excerpt begins mid-registration and
remains unqualified. Independent rendered-page inspection remains an agent
responsibility; a tool receipt does not attest that the model performed it.

Vera candidate 0.1.413 contains this work. The three changed embedded modules
have incremented versions. Rebuilt privacy and course bindings preserve authored
lessons and existing jurisdiction judgments. Clara's generated privacy binding
also changes because its teaching register includes the shared course directory;
its workflow and policy are unchanged.

The deployment CI also exposed nine stale Clara/Lucia editorial digest bindings
already present on the base commit. Exact comparison with their historically
reviewed course objects confirmed that only reporting-helper source fingerprints
had changed. The refreshed bindings record that bounded source review and retain
all historical editorial judgments. The initial CI native teaching stage passed
1,710 tests (three skips), with 90.54% courseware coverage; its later metadata
failure is retained as such. Final-head CI must independently pass the complete
release gate.

The release integrates main `e217a2c7aab6cc3fad21d921ef1264125e8233c6`
(PR #862) before deployment. Its reporting and host-link changes are preserved.
The PDF implementation merged without source conflicts. Combined course bindings
were regenerated only after verifying complete authored-content equality against
both parents; both sets of source compatibility records and all historical
editorial judgments remain. Generated packages are rebuilt from the combined
source, retaining Vera 0.1.413 and main's Clara/Lucia versions.

Phase two is excluded: no generated parsers, runtime product edits, developer
feedback transport, shared learning or automatic promotion of a recovered
recipe into Vera. Deployment, publication and installed-host acceptance are
separate from this source and package candidate.
