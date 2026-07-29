# Vera · Cowork directory submission

This file is the review pack for the Cowork listing. It describes only
capabilities that must pass the Cowork acceptance suite before submission.

## Listing

- **Name:** Vera
- **Compatibility target:** Cowork
- **Developer:** Mparanza
- **Category:** Productivity
- **Website:** https://mparanza.com/static/shared/vera/index.html?lang=it
- **Privacy policy:** https://mparanza.com/privacy
- **Terms:** https://mparanza.com/terms
- **Support:** https://mparanza.com/support

Vera assists Italian accounting practices with evidence-based intake, document
review, accounting checks, research preparation, and reviewable workpapers.
She keeps sources, missing evidence, assumptions, and professional decisions
visible. All legal, tax, accounting, audit, social-security, and filing outputs
remain drafts for review by a qualified professional.

**Public description**

> Assistente AI per commercialisti. Vera aiuta il commercialista a seguire il
> lavoro di ogni cliente, dall’inizio alla revisione finale. Raccoglie, ordina e
> ritrova i documenti del cliente, controlla i dati contabili, seleziona
> campioni, riconcilia movimenti e prepara report. Aiuta anche a riesaminare
> casi di concordato preventivo e a preparare pratiche INPS e Registro
> Imprese/DIRE. Prepara richieste mirate per Deep Research su temi legali,
> fiscali e normativi e verifica le risposte rispetto alle fonti citate. Mostra
> le fonti, i punti da chiarire e le decisioni da prendere. Il giudizio
> professionale resta al commercialista.

## Required review prompts

The files referenced below are synthetic and live under `samples/cowork/`.

1. **Prepare a research prompt**

   > Vera, read `research-question-it.txt`. Prepare a source-backed Deep
   > Research prompt in Italian. Preserve every material fact, separate facts
   > from assumptions, state the source hierarchy, and save the reviewable
   > prompt package in a new output folder.

2. **Validate a supplied research report**

   > Vera, review `research-report-it.md` against the sources it cites. Separate
   > supported, partially supported, and unsupported material claims. Produce a
   > corrected review draft and an audit note; do not answer the underlying tax
   > question from memory.

3. **Prepare a new-client intake**

   > Vera, inspect the synthetic files in `new-client/`. Prepare the first
   > reviewable intake, identify missing evidence and unresolved professional
   > choices, and draft the focused client questions. Do not treat any sample
   > document as signed, complete, or legally effective.

## Acceptance conditions

- The plugin installs and identifies itself as **Vera** in Cowork.
- Each prompt completes with only a connected folder and Cowork file tools.
- Local MCP servers may improve review interaction but are not required for the
  three review prompts.
- No plugin updater, feedback transmission, WhatsApp control, local archive
  indexing, live INPS capture, filing, sending, signing, payment, or submission
  occurs.
- Missing dependencies or permissions produce a useful file-first fallback and
  an explicit limitation rather than a false success claim.
- Review uses only the synthetic files in this package.

## Optional connector check

Gmail is tested separately with synthetic messages and Anthropic's approved
Gmail connector. It is not required for the base acceptance run and Vera never
sends mail.

## Release validation

Run from the repository root:

```bash
source .venv/bin/activate
python scripts/build_claude_plugin_zip.py
python scripts/build_claude_plugin_zip.py --check
python scripts/build_codex_plugin_zip.py --check
python plugins/vera/skills/privacy-surface-review/scripts/validate_privacy_surfaces.py
python -m pytest tests/plugins/test_claude_plugin_packages.py \
  tests/plugins/test_vera_cowork_privacy.py \
  tests/plugins/test_prompt_optimizer_plugin.py \
  tests/plugins/test_deep_research_validator_plugin.py \
  -k 'not static_page_and_skill_match_plugin_contract' -q
```

Upload `plugin_packages/vera/vera-claude-plugin.zip` for a file-install smoke
test. The generated directory is the marketplace source referenced by
`.claude-plugin/marketplace.json`.

If the Anthropic CLI is installed in the release environment, also run its
strict plugin validator against the generated plugin directory and repository
marketplace. The CLI was not available on the 2026-07-27 acceptance machine,
so this pack does not claim that local CLI validation ran.

## Final candidate

- **Version:** 0.1.61
- **Archive:** `plugin_packages/vera/vera-claude-plugin.zip`
- **SHA-256:** `ad446581ccd1a6073cb0deb28c84b2d136112d29a0eac3b7a4aac0a826f99d73`
- **Size:** 2,302,999 bytes
- **Archive entries:** 394

Two consecutive builds produced the same SHA-256. The archive has a direct
plugin root, deterministic timestamps, no duplicate or traversal paths, no
symlinks, and no CRC errors. The generated directory and ZIP payload are
byte-identical.

## Manual Cowork smoke record

On 2026-07-27, the 0.1.50 acceptance archive with SHA-256
`d85dcb02f5c3fa8dd7d8401c00819a89cc65d51d5a030ac4f74f29c6f1d2aba6`
was uploaded through **Customize → Plugins → Upload plugin**. It replaced the
earlier local test copy. The plugin manager showed Vera enabled,
`Uploaded from file`, `Just now`, and 17 skills. The final candidate above was
rebuilt after that smoke test to persist the marketplace homepage and public
description and to refresh the matching service-integrity fingerprint; those
changes are covered by the automated package and privacy checks below.

The desktop app was restarted before the final run. In Cowork session
`local_8be2a665-8629-4d3b-9b04-98eb1ef0c563`, a natural-language request
invoked `new-client` against only:

- `01-visura-demo.txt`
- `02-mandato-demo.txt`
- `document-index.csv`

The final package was written to
`/private/tmp/vera-cowork-acceptance.ymrlA7/prompt-3/vera-output-new-client-0.1.50`.
Its run ID is `new-client-202607271121210000-badaf2c63828`. The whole-delivery
manifest seals 21 artifacts across two directories, excluding the manifest
itself: the 15-artifact New Client contract package, the hash-bound
`new_client_input.json`, three byte-identical source-evidence copies,
`run_review.md`, and `client_questions.md`.

The delivered package passed these checks:

- the output root and its `source-evidence/` directory are `0700`;
- every regular file is `0600`;
- the packaged `validate_contract()` returned
  `contract_validated_for_professional_review`;
- the installed `delivery_manifest.py validate` command returned
  `delivery_validated_for_professional_review`;
- its exact all-file coverage, file receipts, directory count, and package hash
  `8696c4ce032d4caba30b772bea0b89515fe7ec1154e8fbe462f2809e36df0905`
  validate;
- source-evidence copies match the three connected-folder inputs byte for byte;
- a case-insensitive scan of output paths and contents found no occurrence of
  `codex`, `claude`, `openai`, or `anthropic`;
- `final_artifacts.json` is `blocked`, `review_payload.json` is
  `pending_review`, and `ui_decisions.json` contains zero decisions;
- professional review is required; signature, client communication, and
  relationship activation are all false;
- no web search or connector was used or recorded.

A read-only audit in the same session identified the loaded runtime as
`vera` 0.1.50, counted 17 installed skill directories, confirmed
`agents/vera.md`, confirmed
`modules/new-client/scripts/delivery_manifest.py`, and resolved the
session-mounted package root as
`/sessions/epic-bold-rubin/mnt/.remote-plugins/plugin_01UHs2vP8E9qjeNrhzDFwRA3`.

The first task after one desktop restart encountered Cowork's transient
`Workspace still starting` error before any plugin command executed. Retrying
after the isolated workspace finished booting succeeded. This is recorded as a
host startup condition, not hidden as a successful plugin run.

## Defects found and closed during acceptance

- A 0.1.47 run proved generation and contract validation but required a
  follow-up `chmod` after Cowork copied the package to the connected folder.
  The shared Cowork contract now requires post-copy `0700`/`0600` reapplication
  and verification; 0.1.49 performed it without remediation.
- A 0.1.48 run passed privacy, receipt, and contract checks but wrote
  `Route beyond Claude` in `run_review.md`. The projection contract now forbids
  host, platform, and model-provider names in all assistant-authored
  user-facing paths, headings, labels, narrative text, and status summaries.
  The final 0.1.50 output passed the whole-tree scan.
- A 0.1.49 run passed the base validator but left an older run ID in a
  supplemental review file. The new whole-delivery validator now scans every
  delivered assistant-authored file and requires one exact run ID across the
  package; it deterministically rejects that archived 0.1.49 delivery.
- The first 0.1.50 delivery attempt retained scratch paths in its source
  evidence register. The whole-delivery seal rejected it before success was
  claimed. Vera rebuilt the package with delivery-relative
  `source-evidence/` paths, reapplied private modes, sealed it, and validated
  the exact connected-folder copy.
- Prompt Optimizer and Deep Research Validator were corrected so temporary
  drafts are not declared as final artifacts and receipt byte sizes are
  refreshed after final audit writes.

## Known limits

- The base acceptance run exercised file-first generation and review handoff,
  not an optional persistent save/apply review interface.
- The whole-delivery manifest is a deterministic local integrity receipt, not
  a cryptographic signature against a writer able to replace the package and
  recompute every receipt. It verifies POSIX modes but does not attest
  ownership, ACLs, extended attributes, mount state, or concurrent mutation.
- The generated Cowork package intentionally retains inert, nested
  implementation descriptors and widget code for five shared modules. They are
  not root-discoverable or activated by Cowork. Whether marketplace review
  objects to those inert bytes can only be established by Anthropic's review.
- This record proves local file installation and a real Cowork run. It does
  not claim that Vera has been submitted to or approved by the public
  marketplace.
