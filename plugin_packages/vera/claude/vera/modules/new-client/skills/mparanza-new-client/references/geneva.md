> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Geneva adaptation of the existing function

For CH-GE use the existing document-intake phase with `jurisdiction=geneva` and the chosen output language. Keep the sealed intake evidence and the complete imported source population. Do not promote it through the Italian `promote_client_file_preparation.py` country pack.

Prepare a source-bound setup proposal and run `python scripts/jurisdiction_setup.py --client-engagement <context.json> --review <review.json>` from the New Client component. It uses the same Studio Archive workflow ID `new-client`, client/engagement binding, source hashes and professional review boundary. French and English memo presentation are available.

The JSON envelope has `schema_version: 1`, `jurisdiction: CH-GE`, `language`, `as_of`, `jurisdiction_basis`, `limitations`, `sources` (id, relative path, title, SHA-256), and `legal_basis` (title, public HTTPS URL, locator, checked_at, applicability). Record the actual client_name and mandate. Each of the five `domain_reviews` has domain (`identity`, `mandate`, `ownership`, `aml_applicability`, `privacy_roles`), title, status (`supported`, `unresolved`, `not_applicable`), assessment and source citations (`source_id`, `locator`). Explain exclusions; do not equate an absent document with a negative fact. `document_plan` contains id, title, purpose, next_action, status (`received`, `requested`, `missing`, `not_applicable`) and citations. Received documents require bound sources; a request remains outstanding.

Use the Swiss IDE and actual registry evidence in identity; never require an Italian codice fiscale or partita IVA. Assess AML applicability from the mandate, activity and relevant supervision or self-regulatory rules. Do not apply CNDCEC weighting, factor tables or intervals. Assess data-controller/processor roles under the actual Swiss and any evidenced cross-border context; no automatic GDPR Article 28 designation. Use the firm's reviewed Swiss mandate/privacy templates as sources, never invent approved templates.

The output is a content-addressed JSON setup dossier and readable memo with open domains and documents. It does not accept the mandate or certify AML/privacy compliance. Attach a professional_decision only after an actual review: proposal_sha256 from the draft, reviewer_ref, reviewed_at and conclusion. Changed evidence invalidates that decision. Existing Italian preparation and arithmetic remain available for IT.

Official starting sources and the complete catalogue assessment are in Vera’s `references/localization/geneva/`. Verify current applicability for each actual case.
