# Studio Archive runtime correction

Incident: `41b95b28-ae17-4a0a-8b7d-4a4ae8ccfdeb`.
Original report: `b3f1c6a2-7d54-4e0b-9a1e-5c2d8f6e4a71`.
Release source: `9b74daa60` (`origin/main`, Vera 0.1.391).
Candidate: Vera 0.1.393; Studio Archive 0.1.48; Lucia 0.1.113; Clara 0.1.288.

## Observed

The original MCP server selected, in order, `VERA_STUDIO_ARCHIVE_PYTHON`,
`PYTHON`, `$VIRTUAL_ENV/bin/python`, the repository `.venv/bin/python`,
`python3`, then `python`. It selected the first candidate without checking
its version and invoked `studio_archive.py` directly. The two bare names
were not probed; normally the first bare name, `python3`, won. It did not
invoke the product managed launcher.

On the development Mac, `/usr/bin/python3` resolves to
`/Library/Developer/CommandLineTools/usr/bin/python3`, CPython 3.9.6.
Calling `Path.stat(follow_symlinks=False)` under that interpreter reproduced
the exact TypeError. The repository environment is CPython 3.12.13.
The incident service's original report explicitly lists the worker version
as unavailable. The failed Cowork worker's actual executable/version remains
unknown; the broker version does not establish the worker version.

Vera's README, managed runtime and Studio Archive dependency checker specify
CPython 3.12. Python 3.9 is a bootstrap/compatibility regression target, not
a supported full plugin runtime.

## Change

The MCP server uses the product managed launcher in both installed and source
layouts. Its selected executable is only the bootstrap interpreter; the
managed launcher selects and validates CPython 3.12 for the worker.
Standalone component installations use the CLI, which now rejects unsupported
interpreters before importing worker dependencies and reports the version,
executable path and supported launcher. Both archive metadata calls now use
`Path.lstat()`, preserving the no-symlink-following behavior on Python 3.9.
No client file, archive layout, ledger schema or receipt format changes.

A release build also exposed a staging-order fault: the system ZIP path preserved
file times while sorted entries wrote the index before later members. A slow
staging pass could therefore fail the existing final-package timestamp check.
The builder now materializes execution indices last. A regression crosses
multiple simulated ZIP clock ticks and checks the stored ZIP timestamps; the
strict verifier remains unchanged.

The user withdrew the contenzioso tributario course from the release
manifests for Vera and Lucia. `release_plan.json` explicitly excludes those
two courses; the catalog builder retains their authored definitions and
translations while omitting their generated package copies and catalog
entries. The professional workflow remains available. The preceding
directory-scanner test's public website deletions remain in place.

## Python API audit

Inspected 776 Python source files across Vera, its registered components and
shared vendor sources, plus all five retained `.source` Python files. Also
parsed all 877 Python/retained-source entries in the final Cowork archive,
including injected helpers. All parsed using Python 3.12 grammar. A targeted AST
and text review found no candidate APIs requiring Python newer than the
declared 3.12 runtime. This is a targeted source audit, not proof of every
dynamic execution path or third-party dependency's compatibility.

| Feature | Observed use | Required Python | Disposition |
| --- | --- | --- | --- |
| `Path.stat(follow_symlinks=False)` | Both Studio Archive calls | 3.10 | Replaced with `lstat()` |
| `Path.stat(follow_symlinks=False)` | `previdenza-inps/scripts/register_portal_export.py`: 223, 595, 673 | 3.10 | Valid on supported 3.12; not part of bootstrap |
| `DirEntry.stat/is_file/is_dir(follow_symlinks=False)` and `os.stat(..., follow_symlinks=False)` | Discovery and descriptor-based integrity controls | Before 3.9 | Retained; different APIs from `Path.stat` |
| `Path.readlink()` | `previdenza-inps/scripts/case_core.py`: 781 | 3.9 | Retained |
| `removeprefix` / `removesuffix` | 75 calls across registered sources | 3.9 | Retained |
| `zip(strict=...)` | 57 calls, including charting and trial-balance adapters | 3.10 | Retained for 3.12 |
| `match` statements | None | 3.10 | No change |
| Union / bitwise-or expressions | Includes postponed annotations, runtime unions, set and dict operations | Runtime type unions need 3.10 | Valid on 3.12; no plugin-wide 3.9 support claimed |
| Post-3.12 candidates | No `TypeIs`, `ReadOnly`, `NoDefault`, `PythonFinalizationError`, `ThreadingMock`, `InterpreterPoolExecutor`, `Path.full_match/copy_into/move_into`, `glob(recurse_symlinks=...)` or `map(strict=...)` found | 3.13+ | No change |

The version thresholds above follow the official Python documentation:
[Path.stat and lstat](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.stat),
[Path.readlink](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.readlink),
[str.removeprefix and removesuffix](https://docs.python.org/3.12/library/stdtypes.html#str.removeprefix),
and [zip strict](https://docs.python.org/3.12/library/functions.html#zip).

## Verification and acceptance boundary

Final package-verifier suite: **45 passed**, with **100%** coverage of
`scripts/verify_vera_package.py` (required minimum 80%). The broader combined
run passed 1,351 tests with 27 platform/capability skips; its sole failure was
the course-drift fixture tied to the withdrawn lesson. That fixture now uses
a retained course and passes in the final 45-test gate. Source/package parity
and all-host version alignment were checked across Vera, Clara and Lucia.

The dependency-free discovery and refresh/import regressions run the actual core against a
regular file, a symlink and a newly added top-level folder under CPython
3.9.6 and 3.12.13. It verifies discovery excludes the link and preserves
the original bytes. Both tests also pass on Python 3.9.6, including the full blocked-import, refresh and successful-import sequence. Run them with either interpreter:

```sh
python tests/plugins/studio_archive_discovery_regression.py
```

The supported-runtime suite checks the original blocked import, then refresh
and successful document import, with source-byte and symlink assertions.
MCP tests isolate dependency provisioning using a test-only managed launcher;
they verify an old bootstrap delegates to the 3.12 worker. Separate existing
managed-runtime tests exercise the real runtime selection logic.
CLI tests verify the structured unsupported-runtime error.

Package builds regenerate the SHA-256 execution manifest from final host
bytes and invoke the unchanged verifier for all six assured modules.
No installed plugin cache is edited by this correction.

A synthetic source/package pass does not establish recovery of the original
Cowork task. Install the released package through the host's supported update
flow, obtain fresh worker identity, repeat the original refresh and import
with the original selected archive/client/engagement, verify the imported
receipt and retained source, then record the actual outcome against the
original report and applicable remedy revision. Keep the incident open until
that original-task verification succeeds.

## Shared Clara review binding

CI identified a stale `learn-with-clara` engineering review because it governs
the shared course build and public catalogue. The inspected course-manifest
withdrawal changes that fingerprint without adding a recipient or data class.
Refresh that binding and the root/update-service version bindings, then rebuild
Clara 0.1.288 from its unchanged workflow source. Clara privacy regressions pass.

## Shared Lucia archive review binding

The packaged-runtime CI also checks Lucia's native matter-opening review against
the shared archive implementation. Review the changed launcher and retain the
existing case-data boundaries; document managed runtime downloads before worker
execution and refresh this exact governed-source binding. All 26 Lucia plugin
regressions pass. Rebuild Lucia 0.1.113 after this review update.
