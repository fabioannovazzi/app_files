# Bilancio intelligente — fixed product thesis

## Decision

The accounting process already exists. Vera makes its execution intelligent.

Vera is not justified by XBRL generation, because established statutory-account
software already produces XBRL. It is not defined by rare-event detection,
because exceptions are only one place where intelligence helps. It does not
invent a replacement accounting process.

The product object is a complete, reviewable, explainable bilancio. XBRL is one
required delivery format that happens to be generated from the approved
canonical bilancio.

## What intelligent execution means

Traditional software mainly waits for the operator to select mappings, find
missing information, decide which questions matter, reuse prior text, explain
movements, complete tables, and resolve inconsistencies. Vera participates in
that work by:

- understanding the supplied accounting evidence and its limitations;
- reusing reviewed client decisions without blindly carrying them forward;
- proposing classifications with reasons and contrary evidence;
- recognizing ambiguity rather than silently choosing;
- identifying which evidence or confirmation is actually missing;
- asking only questions activated by the current case;
- explaining changes, inconsistencies, and possible next actions;
- preparing schedules and notes from accepted structured facts;
- directing professional attention to consequential decisions;
- presenting the full result for professional review.

The same behavior improves ordinary small-company cases and unusual cases. The
thesis is not that conventional software handles normal cases while Vera handles
exceptions. The distinction is that conventional software executes supplied
instructions while Vera helps understand what should be done next.

## Architecture consequence

```text
accounting evidence and client history
→ intelligent interpretation and workflow participation
→ accepted canonical facts, schedules, disclosures, and decisions
→ deterministic calculation, reconciliation, and validation
→ professional review and immutable approval
→ XBRL and other output adapters
```

The canonical case model is the source of truth. No model writes authoritative
totals, changes accepted facts, approves the accounts, or constructs final XML.
Exact arithmetic, explicit statutory rules, revision integrity,
reconciliations, and XML construction remain deterministic because their
correctness and reproducibility are mechanically verifiable or required for
auditability.

Semantic accounting meaning, evidence sufficiency, ambiguous relevance,
explanations, and narrative drafting are model-assisted and professionally
reviewed. Intelligence is continuous across the workflow rather than a separate
feature switched on after conventional preparation.

## Delivery and evaluation consequence

Building dependable plumbing first is a technical dependency, not a market
test of the thesis. The team is committed to the intelligent bilancio. Tests
measure whether it has been implemented well:

- accounting and XBRL correctness;
- useful and explainable mapping proposals;
- recognition of ambiguity and missing evidence;
- relevance of questions and next actions;
- safe reuse of prior decisions and text;
- factual fidelity of narrative drafts;
- reduced repeated work and investigation;
- preservation of professional judgement and review authority.

Do not describe product execution as testing whether the thesis should be
pursued. Implement the thesis and test the quality, safety, and usefulness of
the implementation.
