---
name: deterministic-judgment
description: Use when adding, reviewing, or choosing deterministic logic versus model-led reasoning, especially classifiers, validators, rule engines, source selection, legal/tax/compliance workflows, LLM fallbacks, or any change justified by determinism, repeatability, or token savings.
---

# Deterministic Judgment

Deterministic is not preferred by default. Use deterministic logic only when it
is demonstrably better for the specific job than model-led reasoning.

## Required Standard

Before adding or preserving deterministic logic, state the reason it should be
deterministic. A valid reason must identify at least one concrete advantage:

- mechanically verifiable correctness;
- lower observed error rate than model-led reasoning on representative cases;
- strict reproducibility required by an external contract;
- security, safety, or auditability that depends on fixed rules;
- performance or cost savings after quality is shown not to regress.

Invalid reasons:

- deterministic is better in theory;
- deterministic saves tokens;
- deterministic feels safer;
- deterministic makes the system look more engineered;
- the task has keywords that can be classified with simple string matching.

## Decision Rule

Use deterministic code for mechanical work: parsing stable formats, schema
validation, exact arithmetic, file packaging, cache keys, ID matching, simple
presence checks, and transformations with explicit contracts.

Use model-led reasoning for semantic judgment: legal or tax relevance, source
selection, topic taxonomy, research scope, document meaning, claim
interpretation, ambiguous intent, and anything where context changes the answer.

Hybrid designs are acceptable only when the boundary is clear: deterministic
code may collect evidence or enforce output shape, but it must not overrule
model judgment on semantic relevance unless tests show it is better.

## Implementation Requirements

- Include a short comment, docstring, or PR note explaining why any new
  deterministic rule is justified.
- Add representative tests for deterministic rules, including false-positive
  and false-negative cases when the rule gates behavior.
- For legal, tax, or compliance modules, do not let deterministic classifiers
  choose legal topics, governing framework, source domains, or research phasing.
- If deterministic output disagrees with model judgment on a semantic issue,
  prefer model judgment unless a documented benchmark or external requirement
  says otherwise.
- Remove deterministic logic that exists only because it is deterministic and
  has no demonstrated quality advantage.
