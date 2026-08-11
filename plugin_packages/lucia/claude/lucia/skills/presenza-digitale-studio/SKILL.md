---
name: presenza-digitale-studio
description: Use when Lucia must refresh an existing law-firm website or create a first informational website from verified lawyer or firm materials, with responsive implementation, exact browser review, a reviewable preview, mechanical validation, and approval-bound publication. Applies the shared website workflow through Lucia's lawyer-specific confidentiality and professional-information profile.
---

# Presenza digitale dello studio

After substantive use of this workflow, read and follow the `Plugin Improvement
Feedback` section in `../lucia/SKILL.md`.

Read `references/lucia-lawyer-profile.md` completely. Its lawyer-specific
contract takes precedence over profession-specific references to Vera or a
commercialista in the shared component, but it does not weaken or replace the
component's evidence, implementation, responsive review, destination approval,
package binding, or publication gates.

Resolve `../../modules/presenza-digitale-studio` from this skill directory when
it exists; otherwise resolve `../../../presenza-digitale-studio` in the
repository. Read that module's
`skills/presenza-digitale-studio/SKILL.md` completely and follow it. Treat the
resolved module root as the plugin working directory for every command,
requirement, script, schema, reference, and asset. Do not copy or fork the
shared website machinery inside Lucia.

The canonical schema currently names an assistant-originated studio convention
`vera_default_proposal`. Preserve that opaque internal provenance value so the
shared scripts and schemas remain byte-identical, but label it as a Lucia
proposal in every user-facing review. Lucia's public experience and
deliverables are in Italian by default; language does not determine
jurisdiction, professional rules, or publication requirements.
