# Cowork reporting acceptance

The October 18 live acceptance used the installed Vera 0.1.412 native Cowork
helper and the saved anonymous incident connector. It reproduced two separate
failures after a synthetic email draft was delivered:

- `completed` repeated `pipeline`, `host` and `sample_kind`, which are start-only
  fields. The server rejected the event but returned only a generic incident
  error. The advertised schema now expresses each event shape and rejection
  returns allowed contract field names without echoing submitted values.
- The saved OAuth connection owns remote-only runs but does not expose an
  installation key. It is not a computer identity, and one connection may be
  used on multiple computers.

For an unlinked connector run, its acknowledged event now returns a random,
15-minute `reporting.host_link.credentials` capability. Its credential-shaped
envelope is compatible with the already-installed native `incident_host_link`
tool. The native helper adds its private computer proof and observed app. The
server recognizes the capability in a separate ticket table and binds only the
original run in `workflow_run_hosts`. It does not register a new reporter,
replace the original owner, link the entire OAuth connection, or change the
professional outcome. A ticket cannot authorize status, events, receipts or
incidents. Only its hash is retained. Different native proof, product, app,
expired ticket or a conflicting existing run binding is rejected.

The exact acknowledged event can be replayed to refresh an expired ticket;
the event remains a duplicate, with the same owner, sequence and original
payload. `workflow_status` remains a read-only inspection and exposes no ticket.
Computer counts and public completion indicators use the verified run binding
first, then an existing proven local reporter binding. They never infer other
runs' computers from the same saved connection. The explicitly designated test
computer remains excluded from user counts even if a test was labelled `user`.

Live acceptance must verify the actual PostgreSQL run, original owner, received
events, valid signed receipt with the matching report hash, native Computer ID,
and test exclusion. A successful draft, local table, receipt issuance alone,
deployment or package download is insufficient. A fresh normal task is required
in addition to assisted recovery of an existing failed reporting episode.

Claude may retain a captured tool catalogue in an already-open conversation.
During acceptance, refreshing the saved connector's tool list exposed
`workflow_stamp` for new conversations; toggling the connector did not refresh
the old conversation's captured tools. The old report/request/run were preserved
and its actual signed receipt was relayed back for validation and linking.
Updating a plugin alone also left the old native helper running until Claude
restarted. These observed host lifecycle limits must not be reported as automatic
upgrades or proof of recovery on another user's installation.
