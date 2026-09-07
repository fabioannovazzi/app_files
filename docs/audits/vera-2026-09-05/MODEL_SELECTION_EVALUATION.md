# T08 model-selection evidence

The initial comparison uses six wholly synthetic bank-to-journal decision probes
at the same low effort on gpt-5.6-luna and gpt-6-astra. It sends a purpose-written
instruction and synthetic facts only, with tool execution disabled. No repository
source, professional case records or client data is included in the prompts.

| Case | Evidence | Proposed expected result |
| --- | --- | --- |
| M01 | Exact amount, invoice reference and counterparty identify one of two entries | Link B1 to J1 |
| M02 | Equal amounts and counterparties, missing bank reference, two possible invoices | Abstain; request review |
| M03 | Two identical bank movements compete for a single journal amount | Abstain; do not reuse capacity or arbitrarily choose one movement |
| M04 | Bank reference explicitly names two invoices whose amounts sum to the settlement | Link B1 to J1 and J2 |
| M05 | Bank amount missing; journal amount explicitly zero | Abstain; missing is not zero |
| M06 | Exact reference with economically opposite signs under an explicit shared sign convention | Abstain; do not erase sign |

Expected results are proposed engineering assertions about the stated synthetic
facts. They are not independent professional acceptance. Every ordinary answer,
reason, prompt, event stream and stderr is retained for inspection. Raw equality
scoring is insufficient: narrative reasons and equivalent unordered target lists
must be reviewed before interpreting results.

Evidence: `/private/tmp/vera-remediation-01a07083/model-comparison/`.
The manifest is `cases.json`; `instructions.txt` and `schema.json` define the
request contract. `results.json` binds the manifest by SHA-256. Expected results
are excluded from each model prompt.

These simplified probes do not reproduce the full production packet, candidate
graph or specialist validators. They cannot qualify native isolation, establish
professional correctness, or justify a replacement model by themselves. A
replacement still requires representative production-packet comparisons,
reviewed outcomes and the host boundary acceptance in HOST_QUALIFICATION.md.
Production model selection and qualification pins remain unchanged.

Execution status: **completed**, 5 September 2026. Twelve retained event streams
contain completed turns. All twelve structured answers and narrative reasons
were inspected. At low effort, Luna matched 5/6 proposed outcomes and Astra 6/6.
Each case was run once; these counts do not estimate general model accuracy.

Luna's M06 answer incorrectly linked the opposite-sign entries and explained:
“equal absolute amount of EUR 100.00”. Astra instead abstained because the
explicit shared sign convention made these economically opposite movements.
Both models correctly abstained on ambiguous identifiers, contested capacity
and a missing amount in the other probes. Neither claimed accounting mutations.

The production source was then inspected: `_same_required_perimeter` calls
`_direction_compatible`; `same_sign` requires identical normalized directions.
Candidate generation applies this predicate, and semantic output validation
rejects suggested links outside eligible graph edges. The six existing public
reconciliation sign-policy regressions passed against a refreshed validation
copy matching all 29 current Journal–Bank/shared-assurance component files.
Evidence is `production-bindings.json` and `production-sign-policy.xml`. An
initial passing run used a copy predating the unrelated output-symlink fix; its
report is retained separately as `production-sign-policy-older-snapshot.xml`.

This isolated model failure is therefore not evidence that production accepts
such a match under a reviewed `same_sign` policy. It is a useful negative case
for subsequent production-packet model comparisons. No model replacement or
host qualification is approved by this result.
