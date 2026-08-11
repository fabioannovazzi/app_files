---
name: comunicazione-professionale
description: Use when Lucia must decide whether a legal or professional development is worth communicating and prepare source-backed client emails, LinkedIn posts, newsletters, website articles, FAQs, client alerts, circulars, or visual explainers for a lawyer's review. Applies the shared communication workflow through Lucia's lawyer-specific confidentiality, professional-information, claim, audience, and publication profile.
---

# Comunicazione professionale

After substantive use of this workflow, read and follow the `Plugin Improvement
Feedback` section in `../lucia/SKILL.md`.

Read `references/lucia-lawyer-profile.md` completely. Its lawyer-specific
contract takes precedence over profession-specific references to Vera or a
commercialista in the shared component, but it does not weaken or replace the
component's evidence, claim-assurance, editorial-review, rendering, approval,
or packaging gates.

Resolve `../../modules/comunicazione-professionale` from this skill directory
when it exists; otherwise resolve `../../../comunicazione-professionale` in the
repository. Read that module's
`skills/comunicazione-professionale/SKILL.md` completely and follow it. Treat
the resolved module root as the plugin working directory for every command,
requirement, script, schema, prompt, reference, and visual asset. Do not copy or
fork the shared mechanics inside Lucia.

The canonical schema currently names an assistant-originated studio convention
`vera_default_proposal`. Preserve that opaque internal provenance value so the
shared scripts and schemas remain byte-identical, but label it as a Lucia
proposal in every user-facing review. Lucia's public experience and
deliverables are in Italian by default, while sources may be in any language
required by the subject and jurisdiction.
