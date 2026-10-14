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

For Geneva invoices use actual supporting PDFs/scans/exports and the existing booked-ledger audit. The FatturaPA parser remains available for real Italian XML. For reviewed non-XML evidence pass one JSON population as --invoice-source to the same run_audit.py. Do not fabricate XML or treat a QR payment slip alone as a complete invoice.

The input contract is `schema_version: vera.reviewed_invoices.v1`, `jurisdiction: CH-GE`, `invoices` and professional_review. Each invoice has source_path relative to the population file, exact source_sha256, locator and fields. The fields are exactly supplier_vat (existing canonical party-identifier slot; a reviewed IDE is permitted), supplier_name, customer_tax_id, customer_name, invoice_number, invoice_date (ISO), document_type (actual source meaning), currency (CHF/EUR), gross_amount, lines, vat_summaries and credit_note (boolean). Unknown optional party IDs/names remain empty strings. Amounts use ungrouped dot decimals. Lines require description, line_total and source locator; retain supported quantity/rate information when present. Tax summaries are explicit reviewed rate/base/tax fields or an empty list when not established. No tax rate or legal treatment is inferred by the adapter.

The professional_review contains content_sha256 of canonical UTF-8 JSON without professional_review (sorted keys, ensure_ascii false, compact separators), reviewer_ref, reviewer_role (authorized_user or professional_reviewer), and reviewed_at. Obtain the actual review before recording it; never manufacture consent. Code verifies source and review digests before both initial execution and resume. It then reuses matching, currency separation, arithmetic comparisons, native semantic screening, exception workpapers and review states. Original document locators stay in the packet. Synthetic adapter checks do not qualify any particular firm's export or establish invoice correctness.

Official starting sources and the complete catalogue assessment are in Vera’s `references/localization/geneva/`. Verify current applicability for each actual case.
