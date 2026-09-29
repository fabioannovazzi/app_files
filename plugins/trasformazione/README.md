# Vera: trasformazione societaria — synthetic prototype

This implements the first increment requested in the recovered Discord brief:
synthetic case → evidence → proposed analysis → review → exported dossier.
It does not handle real mandates, approve law/tax positions or send filings.

Use the current authenticated Codex session for reasoning. No model API key,
model client, external connector or third-party Python dependency is required.
The normal Vera managed runtime is Python 3.12.

From this module directory, with the repository `.venv` activated for development:

```sh
python scripts/check_dependencies.py
python scripts/demo.py --output /absolute/new/synthetic-case
```

The output directory must be new or empty and outside plugin source. The command
returns three dossier paths: missing valuation, simulated approval, and revised
valuation. The last dossier shows capital review as stale while independent
creditor collection remains approved for synthetic preparation. The tax branch
retains unresolved sources and an unknown tax basis. Earlier dossiers remain
available; restarting Python and reading the same folder preserves the case.

Use `scripts/transform_case.py --case-dir <folder> --help` for custom synthetic
cases. Read `references/record-contract.md` before authoring JSON proposals.
Evidence imports copy bytes and never execute source instructions. Unknown,
zero and reasoned non-applicability are distinct. The readable dossier uses
tables; full values, hashes and review history remain in JSON records.

Run the dedicated regressions from the repository root:

```sh
python -m pytest -q tests/plugins/test_trasformazione.py \
  --cov=plugins/trasformazione/scripts --cov-report=term-missing --cov-fail-under=80
```

`references/acceptance-matrix.json` preserves all 46 contributor scenarios.
Eleven have a tested mechanical subset; the remaining scenarios require
professional/legal qualification outside this increment. A test reference or
the contributor's reported 201 checks is not proof of operational acceptance.
The contributor's scripts were inspected but not executed.

Evidence recovery and attribution are recorded in `references/provenance.json`.
The engineering data-boundary review is `references/privacy-review.md`.
Vera routing and Codex/ChatGPT/Cowork packages include this prototype. Package
presence does not prove installation, Marketplace publication or professional
acceptance. There is no Studio Archive client-run adapter in this increment.
