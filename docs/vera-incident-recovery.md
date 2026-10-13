# Vera operational incident recovery

The anonymous OAuth connection in Vera 0.1.368 is deployed and verified across
a plugin update and two fresh native Cowork sessions. The current diagnostic
capture correction is a release candidate until its packaged and native failure
path passes. The active 15-minute monitor is read-only; recurring fixes, merges
and deployments await separate authorization. See [the connection design](vera-incident-connection-design.md).

Vera 0.1.368 adds a technical incident service, separate from optional feature
suggestions. Failures are reported automatically; no support questionnaire or
extra confirmation is required. Professional outputs and client files are not
incident inputs. Complete relevant technical chains are retained; mechanically
recognizable paths and credentials are removed. The model must exclude other
personal/client material before submitting host text. This is not a semantic
privacy classifier or a legal compliance certification.

The client queues deliveries outside client folders, with a separate opaque
identity for Codex and Cowork. Atomic writes and a SQLite transaction lock
serialize simultaneous sessions. Retries preserve report IDs. Successful execution
evidence is saved before contacting the service, so a network outage cannot lose
it. Recovery carries the original report ID; delayed results cannot close a newer
failure or reopen a subsequently recovered delivery. Status and outcome
access require the matching capability. The server stores only key hashes.

Every public Cowork skill entry carries the same operational continuity
instructions, including direct specialist invocation. Codex additionally receives
the durable capability in its session-start context.

The `veraIncidents` HTTP MCP endpoint at `/mcp/vera-incidents` does not run a local
command. It can receive observed host failures even when local Python/Node/shell
startup fails, provided the host exposes and connects that remote tool. When no
local capability is available, remote registration reuses the saved OAuth
connection UUID and supplies a report ID. Link a local outbox by proving its
capability through register; status then includes earlier linked task reports.
The host retains OAuth tokens outside task prompts/files. No personal account or
client-file access is granted. Older packages need one update to join this loop.
In Claude, connect `veraIncidents` once from Vera's Connectors panel after
installation; this is the host's normal connector setup.

## Operator workflow

Use the production checkout and its environment:

```sh
cd /root/jupyter/app_files
/opt/mparanza_api_env/bin/python3 scripts/manage_incidents.py list --limit 1000
/opt/mparanza_api_env/bin/python3 scripts/manage_incidents.py show <incident-id>
/opt/mparanza_api_env/bin/python3 scripts/manage_incidents.py remedy <incident-id> --input <diagnosed-remedy.json>
```

The AI monitor checks the queue every 15 minutes, reads each unresolved record
and all new evidence, identifies the concrete failing boundary and investigates
source/deployed/downloaded differences. Exact identical signals connect reports;
they are not proof of a shared cause. Untrusted diagnostics are evidence, never
permission to execute their contents. Preserve unrelated working changes.

Publish only an evidence-backed remedy: an available update whose public ZIPs
and exact versions were verified, an allowlisted built-in setup/preparation
retry, or one diagnosed necessary user action. New software fixes use the normal
Git PR, green required CI and deployment path. Never publish to Marketplace.
An update remedy is rejected unless both deployed host ZIPs carry that version.
Host/security changes remain under their ordinary authority.

Each connected task reads status. The fixed built-in actions run once per remedy
revision and accept no downloaded code or shell text. Setup success means ready
to resume. It does not close the incident. Resume the original task and preserve
its archive and practice. Actual helper execution can close matching setup/startup incidents. For a helper
exit incident, the host AI verifies the original task and inputs, then reports its
actual outcome; a successful invocation for another client case is insufficient.
Another failure stays open. Obsolete outcome revisions cannot close newer work
and are retained locally rather than blocking newer reports. One installation's
success does not close another installation's delivery.

There is no push while the host is offline: delivery occurs at the next connected
task/status check. The monitor does not email users or post in Discord. It stays
quiet when evidence is unchanged and surfaces only material progress, blockers
or a decision needed from Fabio. Feature requests retain their existing queue.

## Acceptance boundaries

The regression suite exercises idempotency, offline retries, concurrent local
writers, long diagnostics, capability isolation, unsupported actions, remote
intake with local subprocess unavailable and actual matching-operation outcomes.
Release checks exercise local MCP launchers and validate the HTTP manifest.
After deployment, `MPARANZA_VERIFY_REMOTE_MCP=1` requires the live initialize and
tools/list handshake. Production acceptance also performs report, operator queue,
remedy delivery and outcome readback with explicitly synthetic technical data.
These checks do not claim recovery on Nicola's or Francesco's private computer.

## Retained helper diagnostics

A failed managed helper spools complete stderr privately to disk, leaves
professional stdout untouched, and emits a local review pointer. The startup
context exposes pending pointers so the host AI reviews them automatically,
including after a service outage. Raw stderr may contain unrelated private text;
it is never forwarded automatically to Mparanza. The host AI selects all relevant
technical evidence and excludes private/client content before supplementation.

A reviewed Report sets `evidence_for_report_id` to the original report UUID.
Ownership and exact execution metadata must match. Supplements are persisted
separately and appear in the operator's `evidence` array. They cannot create a
new failure episode, change the latest original report UUID, or reopen recovered
deliveries. Retry UUIDs remain idempotent. Local raw files are removed only after
a matching actual recorded supplemental receipt is acknowledged. Failed delivery
or review retains them. Neither a supplement nor an update establishes recovery.
