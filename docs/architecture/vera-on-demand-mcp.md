# Vera services on demand

The public MCP entry point advertises every individual tool, resource and prompt
from a catalogue generated from the packaged specialists. Discovery must not
start any specialist. Codex continues to select skills and tools, including for
requests that do not mention Vera. Exact tool-name routing is mechanical protocol
work; no keyword classifier or additional model interprets the user's request.

The first call starts only its owning service and forwards the host's initialize
parameters. Concurrent first calls share that startup. Used services remain alive
for the transport lifetime so review references and recording bindings survive.
Closing the host connection closes worker inputs; existing native execution owns
the separate lifetime of active professional jobs. There is no automatic idle
shutdown and no shared cross-chat worker pool in this release.

Acceptance requirements:

- One Vera entry process, no specialist processes for initialize and discovery.
- The complete individual tool schemas, annotations, panel metadata, resources,
  prompts and service instructions remain available.
- First use starts only the selected service; repeat and simultaneous calls reuse
  it. Separate chats retain independent service state.
- Tool results, errors, notifications, cancellation and app resource reads route
  correctly. Worker failure never silently retries a potentially mutating call.
- Existing review references, outgoing-data recording, execution isolation and
  long-running job ownership retain their contracts.
- Catalogue generation and packaged parity cover Codex, upload and Cowork
  projections, including Cowork's omitted native course service.
- Test extracted packages, real review workflows and a fresh installed Codex
  session; measure idle counts, first-use counts and startup latency.
- Run required CI, merge and deploy through git, verify public ZIP bytes, and
  remove only this task's branch/worktree. No Marketplace publication.

Build-time discovery is read-only and uses a temporary runtime. The catalogue is
bound by the existing execution manifest. It is regenerated from final host bytes,
not copied from an older release or populated by launching services in user chats.

The extracted 0.1.499 Codex candidate was measured on macOS on 2026-10-26:
discovery advertised 607 tools and 20 resources with one process; the first
`describe_vera_financial_analysis` call used three processes, a repeat stayed at
three, and reading the workspace resource used four. All tracked PIDs exited
after transport closure. Initialization took 0.200 seconds and the first tool
call took 0.203 seconds in that sample; these are observations, not latency
guarantees. A synthetic dated reconciliation retained its calculation and saved
review across reinstall and reconnect. A separate regression verifies native
jobs survive connection closure and reconnect without executing twice.
