# Professional communication history pseudonymization v1

This isolated session is the only model pass that may read the locally stripped
versions of the prior communications selected for this run. Read every exact
document in `history_pseudonymization_packet.json`. Do not open the raw history
snapshots or `history_identity_map.json`.

Return JSON matching `history_pseudonymization.schema.json`. Preserve each
complete communication's useful prose, order, headings, salutation type,
signature type, and formatting signals. Pseudonymize contextual identifiers
that fixed local patterns cannot reliably recognize: people, organizations,
addresses, locations, roles that identify a person, and identifying case facts.
Generalize or rephrase combinations of otherwise ordinary details when their
combination could identify a person or case. Do not shorten the document into
an excerpt or replace it with style observations.

Preserve every placeholder already inserted locally, including `[EMAIL_n]`,
`[PHONE_n]`, `[TAX_ID_n]`, `[ACCOUNT_n]`, and `[CASE_n]`. Use stable typed
placeholders such as `[PERSON_1]`, `[ORGANIZATION_1]`, `[ADDRESS_1]`, and
`[LOCATION_1]` for contextual identities. Return the contextual
identity-to-placeholder entries separately in `identity_mapping`; the local
recorder will keep that mapping outside every downstream model packet. Never
repeat locally stripped original identifiers, which are not present in this
session's inputs.

Outside `identity_mapping`, never repeat a contextual original in the
pseudonymized documents, transformation summaries, residual-risk statements,
or limitations. Do not introduce a new email address, phone number, tax or
account identifier, or case number. After local mechanical validation, an
independent fresh model session will review only the proposed derivatives for
residual contextual identification risk. Generation remains blocked until that
separate review is ready.

Prior communications remain style and format evidence only. Their technical
claims and case facts are not authority for the new communication. If a full
pseudonymized derivative cannot preserve the style-learning purpose without
material identification risk, set `ready_for_downstream_use` to `false` and
explain why. Do not read generation, claim-assurance, editorial-assessment, or
visual-assessment prompts in this session.
