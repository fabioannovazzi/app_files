# Incident delivery permissions

The shared reporter retains `delivery_mode` on each queued event. A task that
explicitly selects `MPARANZA_INCIDENT_DELIVERY=local-only` is retained in
`local_only_tasks`; restarting its reporter does not authorize its evidence.
New unrelated automatic tasks can deliver without releasing restricted history.
Native report retries and related diagnostic supplements apply the same rule.
UUIDs, payloads, installation capabilities and receipts remain unchanged.

An older reporter stored one global `delivery_mode: local-only` flag. On reading
that state, the new reporter marks all previously unclassified queue entries and
pending native incident requests local-only. It does not infer permission from
their age, workflow or diagnostic text. New events carry their own permission.
The global flag remains as a guard for older automatic reporters sharing the
state; the new sender evaluates event and task permissions instead. Loaded old
native tools still need to be refreshed to obtain the corrected implementation.

## Authorizing one retained original report

Only after the user authorizes delivery of that exact retained report, prepare
a local JSON object containing `installation_id`, `task_id`, `report_id` and
`report_sha256`. Use null for `task_id` only if the retained entry has no task
scope. The hash is SHA-256 of the original report encoded as UTF-8 JSON with
`ensure_ascii=False`, sorted keys and separators `(',', ':')`, without a newline.
These are existing opaque identifiers and a content digest, not credentials.

From the installed product, use its ordinary permitted Python route:

```sh
python scripts/operational_incidents.py authorize-report-delivery --input exact-report-authorization.json
```

The command checks owner, task, report ID and exact report bytes under the state
lock. It records local authorization and sends nothing. A later native submission
of the same original report or a scoped retry can deliver that event; other
restricted entries remain queued. Authorizing a report does not authorize new
events in an explicitly local-only task. It does not change diagnostics, claim
recovery, replace an identity or flush a queue. Rejected schema corrections do
not inherit authorization for different report bytes.

Queued/local-only, server receipt, diagnostic reply and original-task recovery
are separate states. An explicit local-only result is not a network failure and
must not trigger a browser fallback that uploads the same restricted evidence.

## Regression evidence

`test_incident_delivery_permissions.py` covers later automatic tasks, retained
local-only tasks, native retries/supplements, legacy migration, exact selective
authorization and outage retries. `test_native_incident_transport.py` also runs
the actual native subprocess against a temporary HTTP service for all three
products. These checks do not establish deployment or installed-host acceptance.

## Automatic retry progress

A successful native incident status call replaces the retained pending-remedy
snapshot, including when the server returns an empty list. The managed launcher
uses this snapshot to record actual retry starts and results for the matching
original operation. A transport failure retains the last known snapshot; server
revision and original-input checks still govern recovery. Reading status does not
execute a remedy or mark an operation recovered.

## First public testing baseline

The public legend counts completed runs inside an explicit product baseline.
An installation without that baseline remains untried even when usage arrived.
Initialize it through the operator command, selecting an observed, registered
agent computer and a timezone-aware start time:

```sh
python scripts/manage_workflow_usage.py --product vera testing-initialize \
  --agent-device <registered-computer-uuid> --since <ISO-8601-start-time>
```

This includes already retained completions after that time without replaying
events. Identical repeated initialization returns the existing baseline. A
different time or computer list cannot replace an existing baseline, and a
product's initialization cannot change another product's counts. The store's
transaction lock serializes initialization across operator/API processes.
Historical usage remains intact. `testing-reset` remains a separate explicit
operation; deployment does not invoke it.
