---
name: reporting-engine
description: Use when a user wants Clara to analyze a CSV/XLSX dataset, choose and render an appropriate business chart, inspect reporting capabilities, or check dataset compatibility.
---

# Reporting Engine

Resolve `../../modules/reporting-engine` from this skill directory when it
exists; otherwise resolve `../../../reporting-engine` in the repository. Read
that component's `skills/reporting-engine/SKILL.md` completely and follow it.
Treat the resolved component root as a read-only execution root for its scripts,
requirements, catalog, references, and vendored modules. Run component helpers
with that root as the working directory, but create every user run and artifact
outside the resolved component root, every Git repository, and every plugin
cache. Never place run artifacts in the packaged component.

Before running component helper scripts, delegate the dependency check from the
Clara root:

```bash
python scripts/check_dependencies.py --module reporting-engine
```

Reporting Engine is Clara's single user-facing route to the embedded chart
families. Inspect the user's question and actual dataset, use Codex reasoning to
choose the analysis that best answers the business question, and ask only when
a material field mapping or intent remains ambiguous. Then use the mechanical
profile and compatibility evidence to confirm that the required roles exist and
run `scripts/render_capability.py` through the Clara-owned adapter boundary.

The boundary is deliberate: deterministic scripts own schema inspection, exact
calculations, compatibility evidence, and rendering because those outputs are
mechanically verifiable. Codex owns semantic chart selection, interpretation,
and the decision about what belongs in the final report. Mechanical
compatibility may narrow choices but must not overrule the business question.

Clara embeds the chart-family components behind this reporting-engine contract.
Resolve charts through the `reporting-engine.*` adapter ids in the component's
`catalog/adapter_registry.json`; treat old family plugin names as provenance
and embedded component names, not as the caller-facing selection boundary.
