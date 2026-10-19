# Shared Python setup: Vera, Clara and Lucia

All products and their Codex/Cowork distributions install the same complete,
version-pinned, SHA-256-checked dependency graph. Python runs in one user-scoped
environment per operating-system host. A cloud Linux runtime and a Mac runtime
are separate instances of the same published policy.

`requirements-shared-core.lock` contains core and all its transitive dependencies.
`requirements-shared-ocr.lock` contains core plus optional OCR, resolved together.
OCR still requires explicit approval and remains enabled during later updates.
The managed launcher installs these locks with pip's `--require-hashes`; it never
resolves the broad input requirements at customer setup time. Published source
distributions are hash-checked too (matplotlib-venn has no wheel).

The Python compatibility policy is CPython 3.12. Patch/security releases within
3.12 are accepted; this is environment equivalence, not identical interpreter
binaries across operating systems. The lock records the supported Python family.
Dependency markers explicitly select platform/architecture variants. The existing
Numba/llvmlite x86_64 compatibility pair is retained; every variant is pinned.
Platform binaries and browser permissions still differ between hosts. Passing
Python checks is not proof of a working browser or native user interface.

Setup verifies installed versions against the active lock, removes obsolete
managed workflow packages under the exclusive installation lock, runs pip check
and the selected component's dependency check, then publishes its ready receipt.
Installer tools pip/setuptools/wheel may remain unless explicitly governed by the
lock. Subsequent launches compare actual installed distributions with that
receipt. Inherited PYTHONPATH and user site-packages cannot alter helper imports.
Failure leaves the ready receipt invalid. Running workflows hold reader leases;
setup waits up to 30 minutes for another setup/workflow to finish. A waiting
installer rechecks readiness and reuses a completed installation.

Cowork session startup does not launch Clara's dependency installation. Both
hosts use the managed launcher, which completes setup before executing a helper:

```sh
python3 scripts/managed_python_runtime.py --module <module> run scripts/check_dependencies.py
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

## Maintaining the lock

Build-time inputs are the shared requirements and the reviewed versions in
`constraints-shared-macos-py312.txt`. That historical filename is a seed for
resolution, not a macOS-only runtime rule. `scripts/shared-runtime/uv.lock` is the
common resolution; all three products receive identical exports. Regenerate
with the reviewed uv 0.12.10 tool, inspect the version/hash changes and bump
`POLICY_REVISION` across products before release:

```sh
python scripts/lock_shared_runtime.py --uv /path/to/uv
python scripts/lock_shared_runtime.py --uv /path/to/uv --check
python scripts/check_shared_runtime_revision.py --base-ref <previous-commit>
```

The package tests require the exact lock and shared-backend bytes in all host
formats. The cold-install matrix extracts both Codex and Cowork packages on
Linux, Windows and macOS, bootstraps with an empty PATH, checks all three products
reuse the same environment, and runs the same synthetic scatter data workflow.
It records actual distributions and lock identities. These are executable package
tests; they do not open Cowork or attest its native session lifecycle, browser
rendering, provider processing or professional acceptance.

## Privacy review of this change (2026-10-19)

Reviewed the shared installer, inventory helper, environment binding, Clara's
startup hook and changed Cowork instructions against the existing runtime
profiles and service contracts. The inventory helper reads installed package
metadata and published lock files; it receives no client files or prompts.
Dependency requests retain the existing configured-index boundary and fixed
interpreter-download boundary. Hashes and version pins narrow accepted package
content. Local inventory/receipt checks and removal of obsolete managed packages
add no external recipient. Client folders and professional outputs are not
cleanup targets. Startup no longer initiates a package download. Incident
transport, hosted voice/video routes and workflow model-context payloads are
unchanged; stripped PYTHONPATH prevents ambient Python modules from overriding
the managed code. The affected source fingerprints are refreshed for this
reviewed setup/instruction delta; other professional and hosted source behavior
is not newly certified. No provider-account, legal-compliance or native Cowork
acceptance claim is made. Cowork stays stopped during this engineering work.
