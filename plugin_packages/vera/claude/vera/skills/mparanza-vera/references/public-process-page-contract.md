> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Public process model-data explanation contract

Use this contract whenever Vera adds or changes a public page or named product-page
section that explains a registered user-facing process.

## Required block

Every public process explanation must contain one visible block headed, in the
active language, **“Quali dati arrivano al modello”** / **“What data reaches the
model”**. This entire block must be the final block in the public process
explanation, after every description, step, output, review boundary and call to
action. No process content may follow it. The heading sits directly above the
process-specific conclusion.

Mark the block with the registered workflow ID and one explicit status:

```html
data-model-data-workflow="<registered-workflow-id>"
data-model-data-status="relevant|not-relevant"
```

Localize the complete block wherever the page is localized. Do not leave the
heading or conclusion in a fallback language.

## Model-led status decision

Choose `relevant` or `not-relevant` from inspected workflow evidence: the
complete workflow skill, privacy manifest, runtime profiles, scripts, schemas,
MCP payload builders and runtime-specific package projection. This is semantic
product judgment. A deterministic test must not select the status or approve the
reason.

Use `relevant` when the distinction materially helps a professional understand
the process. State, as applicable:

- what deterministic or local code processes, including whether it processes
  the full population;
- every model-visible phase and the exact data classes, rows, columns, files,
  samples or bounds it can receive;
- stop conditions and what stays out of later model phases;
- differences between Claude and Cowork.

Use `not-relevant` only when the distinction adds no useful process information.
Write **“Non rilevante per questo processo”** / **“Not relevant to this process”**
and one concrete, evidence-backed reason. For example, the website-building
process can state that the website and the materials selected to build it are
intended for publication. `not-relevant` is never a fallback for an incomplete
review and never means that no data reaches the selected model runtime.

Do not recommend anonymization or pseudonymization generically. Mention either
only when it is actually implemented or when the inspected professional purpose
makes it material to this process.

## Separation from the global page

`/data-handling` explains the shared account, local-processing, hosted-service
and external-destination boundaries. It is not a central per-process register
and must not duplicate these process-specific blocks.

The block is an explanation, not a consent banner or per-case privacy notice.
The governed privacy manifest remains the engineering record of model context,
runtime profiles, external boundaries and security controls.

## Mechanical enforcement

Tests may enforce registered workflow IDs, allowed status values, one block per
public process explanation, final-block placement, heading-before-conclusion
order and complete locale keys. Those checks are mechanically verifiable. They
must not infer a status from keywords, decide professional relevance or certify
that the copy is substantively correct.
