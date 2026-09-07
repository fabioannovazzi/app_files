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
these files changes. Older policies cannot replace newer ones, and conflicting
recipes with the same revision are rejected before modifying installed packages.

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
