# Intelligence implementation status

## Implemented

- Eleven bounded semantic task contracts and mechanical next-task orchestration.
- Bounded task packets that do not copy the intake applicant object or local
  source paths by default, label evidence as untrusted, prohibit embedded
  instructions, and disclose that relevant facts or excerpts may identify the
  applicant without automatic anonymization.
- Strict, reference-closed recommendation output with task-scoped mutation
  permissions.
- Private `intelligence_register.json` recording exact input hashes, packet hash,
  model identity, prompt-template version, output, operator, and lifecycle.
- `MODEL_SUGGESTED`, `APPLYING`, `ACCEPTED`, `REJECTED`, `RETURNED`, and `STALE`
  states.
- Explicit professional accept/reject/return, asserted-not-authenticated reviewer
  metadata, idempotent recording, stale detection, two-phase application, retry
  finalization, and prevention of confirmed/blocked overwrite.
- Forced proposed status, model-inference facts, model-led assessments, open
  issues, and manual protected portal controls.
- Validation and dossier/manifest inclusion of the intelligence register.
- Offline representative contract evaluation covering valid proposals,
  reference escape, red flags, and protected portal controls.

## Deliberately not implemented

- An in-plugin provider call or cheaper wrapper call. Codex or another caller
  supplies the model response and records its exact identity; the workflow does
  not hide provider cost or provenance.
- Live portal automation, authentication, declaration acceptance, signature,
  payment, save, or transmission.
- Autonomous acceptance, professional confirmation, legal conclusion, source
  hierarchy, or eligibility rule library.
- A claim of semantic quality from structural tests alone.

## Evidence required before broad semantic claims

- Reviewed representative cases across several issuing authorities, instruments,
  source formats, amendments, and FAQ patterns.
- Qualified-professional gold traces at requirement and source-fragment level.
- Measured unsupported-claim rate, omission rate, reviewer override rate, red-flag
  recall, cost agreement, and time-to-reviewed-dossier against the prior process.
- Provider privacy, residency, retention, and contractual evidence for any model
  route enabled in a deployment.
- Authentication integration if reviewer identity must become more than locally
  asserted metadata.
