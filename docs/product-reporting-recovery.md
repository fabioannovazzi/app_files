# Reporting and recovery across Vera, Clara and Lucia

All three products use the same runtime source in
`plugins/_shared/reporting-runtime`. `scripts/sync_reporting_runtime.py` copies
those exact bytes into each standalone package. Its check mode rejects drift.
The installed manifest selects the product; task text cannot select an endpoint,
product namespace or executable remedy.

Each primary mandate starts one durable random run before preparation. The host
AI chooses the actual process from that product's authored `usage/pipelines.json`.
Nested helpers, Studio Archive, report retrieval and retries reuse that task.
Completion means the requested result was verified and delivered, not merely
that a helper exited successfully. Feedback is the user's actual 1–5 stars and
optional comment, asked once after delivery. Missing outcomes and ratings remain
unknown and unrated. Synthetic acceptance is explicitly excluded from user metrics.

The readable model-data report remains local and must be shown after the result.
It records the actual model-visible phases and evidence basis; hashes are not
provider attestations. The shared builder creates the JSON and Markdown report,
then obtains a server-signed receipt and links that proof to the primary task.
Clara and Lucia use schema 2: product, opaque receipt UUID, version and report
digest, plus schema version. The server adds its timestamp and signature. Vera's
existing schema-1 proofs and retry bytes remain valid. Reopening a saved report
does not repeat analysis, read the source inputs or create another receipt.
Failed delivery retains the original request/event for exact acknowledgement and
retry without invalidating the professional result.

Registrations bind an installation permanently to one product. OAuth resource,
reported product, task owner, receipt product, feedback route and remedy download
must agree. Legacy unmapped identities remain Vera. A saved OAuth connection,
task-local installation and native computer proof remain distinct. The existing
native host identity is shared across products; its private key never enters
tool output. Physical-computer proof may be absent in a cloud guest.

Each product has a separate testing epoch. Preserve Vera's current epoch and
history. Initialize only Clara and Lucia at **Da provare**. Completed tasks after
the baseline contribute by proven computer: Fabio's designated Mac is an agent;
one or two other computers mean tried, three or more repeated. Apps, reinstalls
and repeated runs do not multiply one computer. Stars, receipt presence and
professional correctness are separate from these levels. No completion closes
an incident by itself.

Technical failures retain source-bound exception facts and private stderr for
the host AI to review. Only relevant technical evidence goes to the service.
The independent product incident connector remains usable when local helpers
cannot start. The operator agent diagnoses the exact evidence, sends a targeted
request, correction or verified product update, and checks the original
report/operation/input binding and current remedy revision. Only an observed
successful retry and verification of that original task establish recovery.
The service cannot wake an offline host or replace an already open conversation.

The existing monitor covers all three products, preserving its 08:00–23:00
Europe/Paris schedule, model, incident epoch, exact fixture reviews and email
deduplication. Product-specific usage is read with:

```
python scripts/manage_workflow_usage.py --product all summary --limit 100000
python scripts/manage_workflow_usage.py show <run-id>
python scripts/manage_workflow_usage.py --product clara testing-status
python scripts/manage_workflow_usage.py --product lucia testing-status
```

Never combine equally named pipelines across products or compare their version
numbers as one release stream. AI reviews feedback meaning; exact schema checks,
ownership, hashes, signed proofs and deduplication remain mechanical controls.
No Marketplace action is part of this release.
