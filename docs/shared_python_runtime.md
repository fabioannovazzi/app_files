# Shared Mparanza Python runtime

Vera, Clara and Lucia share one CPython 3.12 virtual environment per OS host.
The target is `~/.local/share/mparanza/runtime/venv` on macOS/Linux and
`%LOCALAPPDATA%/mpr/venv` on Windows. `MPARANZA_RUNTIME_ROOT` overrides its parent.
Client projects never own it. Separate OS hosts, including a Cowork VM, cannot
share native binaries or this filesystem environment.

`requirements-shared-core.txt` is the union of the products and their non-OCR
optional requirements. `requirements-shared-ocr.txt` enables OCR in the same
interpreter after approval. Enabled OCR persists across subsequent updates.
macOS uses the checked-in Python 3.12 constraints. Windows/Linux resolve the same
published requirements; native acceptance must be tested on those hosts.

All three products must ship byte-identical shared recipes, constraints and
`_shared_python_runtime.py`. Increment `POLICY_REVISION` together whenever any of
these files changes. The revision records installation history; it never decides
whether a workflow can run. Reuse a completed environment when its actual package
versions and the selected component's imports satisfy the declared requirements,
even if another product installed a newer or different recipe. Reuse leaves the
existing policy, receipt and enabled OCR unchanged. Only a missing dependency,
an incompatible package or an incomplete installation triggers managed repair.

Launch setup from base Python through `scripts/managed_python_runtime.py install`.
Use `--requirements requirements-shared-ocr.txt install` to enable approved OCR.
Run workflow helpers through the same launcher. Managed Python processes hold a
reader lease until exit; setup requires the exclusive lock and returns a busy
error after 60 seconds if workflows are still running. Externally activated OCR
also holds a reader lease. The startup hook is concurrency protection, not an
isolation or security boundary between client matters.

There is one mutable environment. Setup invalidates readiness before mutation
and restores it only after dependency validation. A failed update requires repair;
it does not silently execute a partial installation or create fallback generations.

Local migration must verify the actual installed package launchers, representative
core/document/chart/OCR workflows, and absence of active old-runtime readers before
removing an explicit inventory of historical caches. A different dependency hash
alone does not establish that an old environment is unused. Preserve OCR models.

## Automatic first installation

An existing shared environment is reused regardless of the host Python version.
When Python 3.12 and uv are missing, setup downloads an official uv 0.12.10 wheel
from PyPI, verifies its published SHA-256, and provisions CPython 3.12 under the
shared runtime parent. No pip, uv, administrator access, shell-profile edits or
system Python replacement is required for this bootstrap. Supported bootstrap
platforms are macOS Intel/Apple Silicon, Windows x64/ARM64, and Linux x64/ARM64.
Internet access and writable user storage are required; failures report the
actual download, checksum or storage error and can be retried. Native workflow
compatibility still requires acceptance testing on each supported platform.

## Launcher-independent interpreter identity (policy revision 4)

For an existing environment, readiness and setup probe that environment's Python
executable. They verify CPython 3.12 and record its platform when installing.
The ready receipt and feature policy must describe the same completed
installation. They do not infer native compatibility from the
Python used to launch the command. On cold start, discovery or automatic
provisioning selects Python first; its verified identity is recorded in policy,
and the created venv is checked against that identity before installing packages.

The identity probe uses `-I -S`: it ignores caller Python configuration and does
not load site hooks, including the managed reader lease. This prevents a probe
from deadlocking while setup owns the writer lock. Actual workflow processes
still take the normal reader lease. An unavailable interpreter, wrong Python
implementation/minor version fails before receipt or policy mutation. A changed
platform label does not require a rebuild: the selected interpreter, declared
package versions and component imports are checked directly. Compatible reuse
preserves installation history. If a dependency really fails, setup repairs it
under the same writer lock and records the current interpreter identity.

Revision 4 updates the backend hash, so the first upgrade from revision 3 follows
the existing serialized recipe-update path after active workflows finish, keeps
the same interpreter and enabled OCR, and validates before restoring readiness.
Deploy the three product packages together. Compatible environments are reused
without changing their recorded installation history.
No shared runtime is rebuilt merely because the launcher's platform differs.


## Revision 7: repair the LIPE recipe upgrade

The LIPE release added `tzdata>=2024.1` while keeping revision 6. Machines
already using the preceding revision-6 recipe rejected this conflict.
Revision 7 originally let the managed installer upgrade that existing environment under
its writer lock, retain enabled OCR and validate dependencies before restoring
readiness. Current execution checks the installed dependencies directly instead
of rejecting a recipe revision. Do not remove metadata or create a separate
environment to bypass a failed installation.

`scripts/check_shared_runtime_revision.py --base-ref <previous-commit>` rejects
changed shared recipes, macOS constraints or backend code without a strictly
higher coordinated revision. Product release CI compares against the PR base
or the previous pushed commit. The package release builder also checks product
parity. Cross-platform runtime tests cover upgrading an already installed
revision-6 environment with and without OCR, retaining the interpreter and
executing a workflow after the upgrade.

Reporting parses string dates with the explicit Polars string API. Shared runtime recipes require Polars 2.x, excluding unqualified major version 3; component regressions also preserve the supported 1.x parsing behavior. Shared policy revision 10 advances the recipe monotonically and pins macOS to Polars 2.0.0. Cross-platform fresh-package CI must render an actual chart before release.
