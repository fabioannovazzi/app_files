**Learning Plan — Alias‑Only V1 (Global Rules)**

**Scope**
- Learn reusable alias rules only (no regex in V1).
- Use only pairs that match by amount and date and are unique within a small window.
- Do not use rows that fail amount+date alignment in this phase.
- Send patterns (not rows) to the LLM for confirmation.

**Seed Selection**
- Uniqueness: exactly one bank row and one ledger row for that amount on that date (start same‑day; relax to ±1 day only if needed).
- Alignment: same sign/direction and same currency.
- Exclude: fees, interest, FX, reversals.
- Strength filter: exclude pairs already matched by strong signals (IBAN/ID/exact beneficiary); keep weak tags (e.g., payroll) if still unique.
- Burst guard: skip days where that amount occurs more than once on either side.

**Normalization & Tokens**
- Normalize: lowercase, ASCII‑fold, strip punctuation, collapse spaces.
- Drop generic stopwords: BONIFICO, PAGAMENTO, FATTURA, STIPENDIO, and similar.
- Extract candidate tokens per side: distinctive words, VAT/IBAN tails if present.
- Keep raw strings alongside normalized for examples.

**Pattern Grouping (pure code)**
- Form candidate token‑pair groups: bank_token ↔ ledger_token observed together in ≥2 (prefer 3+) distinct seed dates.
- Keep 5–10 short examples per group; ignore singletons.
- Rank groups by support and token distinctiveness (rarer tokens first).

**LLM Confirmation (per pattern, not per row)**
- Ask only: do these two tokens refer to the same counterparty/alias? If yes, return one canonical name and a minimal normalization rule (e.g., “strip company suffixes; collapse spaces”).
- Inputs are minimal: the two tokens + a few short example strings.
- Cap patterns per run and examples per pattern.

**Auto‑Validation**
- Support threshold met (≥2; prefer 3+ distinct dates).
- Back‑test on current dataset: applying the alias must not create many‑to‑many or one‑to‑many collisions.
- Consistency: direction/op_type remain coherent after application.
- Reject if driven by generic tokens or if any collision appears.

**Rule Store (global now; future‑proofed)**
- Apply all learned rules globally in V1.
- Persist each rule with reserved fields for later demotion: company_key=None, bank_key=None (unset ⇒ global).
- Store: canonical_name, operations, support_count, examples_hash, created_at, last_seen, scope="global", company_key, bank_key.
- Conflict handling: for now, latest accepted global rule wins; later, scoped rules (when used) take precedence over global.

**Runtime Application**
- Load rules at start of reconciliation.
- Pre‑normalize names on both sides using accepted alias rules (global).
- Run the existing matching pipeline; high‑probability pairs should lift to higher steps.
- After run, collect new seeds; regroup patterns; confirm within budget; auto‑validate; persist accepted rules.

**Controls & Metrics**
- Budgets: max patterns per run (e.g., 10–20), max examples per pattern (5–10).
- Track: seeds count, groups formed, patterns sent, rules accepted, collisions (should be zero), incremental matches gained.
- Adjust thresholds later based on observed precision/recall.

**Future Options (not in V1)**
- Demotion by scope: when bank/client IDs are available, set company_key/bank_key to scope rules; engine prefers scoped over global.
- Add reference/ID regex extraction as Phase 2 (with its own validation gates).
- Rule lifecycle: expiration/demotion of stale or drifting rules once scoping exists.

---

**Status Update — 2025-09-25**

- **Current implementation**: alias learning executes one batch per reconciliation (up to 20 pattern groups) and persists accepted proposals; all statement-loader LLM hooks were removed, so ingestion now relies solely on deterministic parsing plus OCR.
- **Safeguards in place**: canonical-name sanitiser rejects noisy answers, saved patterns auto-apply on the next run, and the UI cache reset clears both rules and pattern files.
- **Still outstanding**: refine prompts/input structure to improve first-pass answers, introduce a second acceptance step before rules are saved, and consider testing a stronger model if quality remains low.
