---
name: reporting-engine
description: Use when a user wants Clara to analyze a CSV/XLSX/Parquet dataset, choose and render an appropriate business chart, inspect reporting capabilities, or check dataset compatibility.
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
families. For a semantic reporting run, inspect the user's question, actual
dataset, and source-backed dataset semantic layer. If no reviewed semantic layer
exists, profile the dataset, create a scaffold and authoring context with
`scripts/semantic_layer.py`, inspect authoritative business sources, author or
review the semantic document, and validate it before treating profiler
candidates as meaningful fields. Ask only when a material field mapping, source
conflict, or intent remains unresolved. Then use the mechanical profile and
compatibility evidence to confirm that the required roles exist and run
`scripts/render_capability.py` through the Clara-owned adapter boundary.

The boundary is deliberate: deterministic scripts own schema inspection, exact
calculations, compatibility evidence, and rendering because those outputs are
mechanically verifiable. Codex owns semantic chart selection, interpretation,
and the decision about what belongs in the final report. Mechanical
compatibility may narrow choices but must not overrule the business question.
Semantic-layer validation is also deterministic and proves wiring rather than
truth. Codex or a human owns metric definitions, aggregation rules, dimension
meaning, period scope, and analysis validity. This workflow does not add an
automatic selector or future report orchestrator; Codex may currently reason
from the reviewed layer and manifest when the user asks for a chart.

Clara embeds the chart-family components behind this reporting-engine contract.
Resolve charts through the `reporting-engine.*` adapter ids in the component's
`catalog/adapter_registry.json`; treat old family plugin names as provenance
and embedded component names, not as the caller-facing selection boundary.
