# Intelligence acceptance matrix

| Public behavior | Required evidence | Gate |
| --- | --- | --- |
| Packet is bounded and state-aware | Tests across intake, sources, requirements, evidence, assessments, costs, forms, narratives, consistency, issues, and authority simulation | Required |
| Intake applicant object and local paths are not copied by default, while possible identity in relevant facts/excerpts and absence of automatic anonymization are disclosed | Packet inspection tests and privacy review | Required |
| Evidence cannot escape its packet | Unknown-reference negative tests | Required |
| Model output has no authority on record | Workbench byte-equivalence before decision | Required |
| Exact model provenance is retained | Schema and public workflow tests | Required |
| Repeating an exact record request does not create a second run | Stable idempotency-key retry and conflict tests | Required |
| Acceptance requires explicit professional confirmation | Missing-confirmation negative test | Required |
| Accepted content remains proposed | Normalization and application tests for every collection family | Required |
| Confirmed or blocked work cannot be overwritten | Update negative tests | Required |
| Changed inputs invalidate undecided intelligence | Intake, source, and workbench stale tests | Required |
| Interrupted acceptance is resumable and non-duplicating | `APPLYING` recovery tests | Required |
| Protected portal actions remain empty and manual | Contract and final-validator negative tests | Required |
| Validation cannot pass during partial application | `APPLYING` audit test | Required |
| Dossier discloses model contribution and decision state | Markdown, manifest, and hash assertions | Required |
| Structural evaluation passes | `intelligence_quality_cases.json` at 100% | Required |
| Semantic quality is acceptable | Qualified-professional representative evaluation; thresholds approved before broad rollout | Pilot blocker, not claimed by offline suite |

## Release quality gates

Run the component tests, filesystem/privacy tests, plugin packaging tests, static
format/type/security checks applicable to changed files, drift verification,
and package rebuild. A release must retain `ready_to_file=false`, no portal
actions, no secrets or credentials, and an explicit disclosure that structural
evaluation does not establish legal accuracy.
