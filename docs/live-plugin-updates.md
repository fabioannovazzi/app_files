# Vera live plugin updates

Vera's local MCP launchers now verify and pin the complete shipped package before
starting a component, product service, or persistent calculation worker. They run
from a private code directory outside Codex's replaceable plugin cache. Reinstalling
the same release or upgrading its cache no longer removes the running service's
working directory, Python helpers, assets or reporting bridge.

The code directory is `<shared-runtime-parent>/code`. Its key is the SHA-256 of the
complete execution-file index, not the version label. Every acquisition checks
source and cached bytes; files are single-link, read-only copies. A serialized
catalog lock makes publication atomic. Kernel reader leases retain live releases;
collection obtains an exclusive lease and checks directory identity before removal.
The store keeps two idle releases in addition to every live release. Professional
state, job logs, outputs and run bindings remain outside code storage.

An active Archive run records `execution-runtime.json` beside its context. Native
helper jobs and component review requests use that package across reconnects.
New runs use the current service's package. Review tokens remain associated with
the child that issued them. Existing services stay on their release until they
close: an update does not rewrite instructions in an already-open chat. A fresh
chat is still needed to select the new installation. If an old inactive release
has been collected, restore that exact verified package before resuming that run;
Vera does not silently recalculate it with a newer release.

## Managed local installation

From the repository's activated virtual environment:

```sh
python scripts/install_local_vera.py /absolute/path/to/vera-codex-plugin \
  --destination /absolute/persistent/path/managed-vera-sources \
  --expected-version 0.1.478
```

The updater verifies and stages the source before changing the selected local
registration, serializes cooperating installers, rechecks the selected source,
uses supported `codex plugin` commands, verifies the enabled version, and restores
the previous registration/install if its own switch fails. It keeps current and
previous managed sources and does not publish to a public directory.

Codex's registry API has no transactional switch. Staging is atomic; registration
is serialized and recoverable. Direct Codex UI/CLI updates do not participate in
this lock. The runtime's independent snapshots protect running services from cache
replacement, but cannot prevent a host from deliberately terminating them. Native
jobs retain their saved IDs/results. MCP transport reconnection and UI reopening
remain host responsibilities; no request is automatically replayed after failure.

## Regression evidence

`test_live_plugin_runtime.py` exercises cache deletion, same-version replacement,
upgrade, old-run reconnect, new-run selection, concurrent starts, tamper detection,
all registered local launchers and bounded idle storage. Native execution tests
exercise cancellation, repeated signals and detached-worker survival after SIGKILL.
`test_install_local_vera.py` exercises stale selection, failed install rollback,
concurrent updates and bounded managed sources. Cross-platform CI runs the native
and live-update tests on macOS, Linux and Windows. POSIX descriptor inheritance
protects detached workers even when the service's process group is killed; the
Windows branch uses kernel shared locks and needs its CI result before claiming
that platform's acceptance.
