# Vera UTF-8 boundary verification

The candidate starts at `84c5876ef` (origin/main on 2026-11-13). All fixtures
are synthetic. No customer incident payloads or documents are included.

## Scope and decisions

The audit covers Vera, the 39 components registered in `components.json`,
shared reporting runtime and vendor modules, the extra Lucia/Clara sources
in `scripts/plugin_vendor_modules.json`, and Node MCP adapters. Python AST
inspection enumerated omitted encodings in `read_text`, `write_text`, text
subprocess calls and file opens; manual review separated binary/file-descriptor,
PDF/image/archive and external-command APIs from text files. Retained Python
`.source` files and the package-injected `local_helper_environment` were checked.
A final AST pass covered 847 Python/retained-source files in Vera, its
components and shared roots, with no pathlib text reads/writes lacking an encoding.

- Owned JSON, Markdown, manifest, request and resume-state files use UTF-8.
- Parent Python text pipes decode and encode UTF-8 explicitly.
- Python command vectors use `-X utf8`, including `-I` children. The isolated
  child therefore does not depend on ignored `PYTHONUTF8` or
  `PYTHONIOENCODING` variables. The managed non-isolated helper environment
  retains its existing explicit UTF-8 settings.
- Node adapters continue UTF-8 JSON transport and explicitly select UTF-8 in
  their Python children. Node Buffer snapshots, binary artifacts, hashes and
  immutable receipt contents remain byte operations. The owned PowerShell
  folder picker explicitly emits UTF-8 for its selected-path protocol.
- Existing explicit third-party input encodings remain unchanged. No blanket
  cp1252 fallback, replacement decoding, or record rewrite is introduced.
  Previously ASCII JSON remains UTF-8 compatible. Research records already
  had UTF-8 readers; their writer now agrees. Cowork retained request identity
  uses the same canonical JSON digest and response byte digest as before.
- Shared runtime revision 19 records installation history. Runtime reuse still
  checks actual interpreter/dependencies; revision equality is not a new gate.

## Regression coverage

`test_vera_utf8_boundaries.py` exercises:

1. A real native Bandi parent and isolated bridge with Unicode request paths
   and a saved Unicode dossier field returned intact; source bytes unchanged.
2. Research-record binding, persisted UTF-8 bytes and subsequent verification.
3. Cowork pending-request creation and response/host-record ingestion on resume,
   preserving request bytes and hashes. This is a file handoff test, not a live
   Anthropic model invocation.
4. Node MCP → isolated Python → managed helper execution, Unicode arguments,
   stdout/stderr, saved request and a service restart. Resume returns the saved
   result and the helper runs once.

The Windows workflow uses Python 3.12 with UTF-8 mode disabled and explicitly
requires `locale.getencoding()` and a default text file's encoding to be cp1252.
It proves a default write of the fixture would raise `UnicodeEncodeError`.
The subprocess tests record encoding and UTF-8-mode properties in retained
JUnit evidence. Linux/macOS results are separate portability evidence.

## Checks and encountered blocks

- Local macOS: 97 managed-runtime tests passed; 45 native execution/Unicode
  tests passed with process-control access; 17 additional reporting/icon/worker
  tests passed, with 7 Windows-only tests skipped on macOS.
- Recovered test-harness defects: isolated test-driver imports needed the
  repository path; the native fixture overrode the real runtime environment;
  installer mocks assumed fixed interpreter-argument positions. Tests were
  corrected without weakening production isolation or Unicode assertions.
- The restricted shell denied process inspection/cancellation and nested
  sandbox behavior. The native tests passed when rerun with required OS access.
- Native Windows completed all scenario operations under cp1252, but a PyMuPDF
  deprecation notice emitted by an imported test fixture polluted the research
  driver JSON. Fixture-import notices were redirected to stderr; the native
  Windows rerun passed all four tests.
- CI initially omitted PyMuPDF/python-docx used by the imported research fixture;
  the declared CI test dependencies were corrected.
- Package tests initially lacked built archives. Catalogue, course and privacy
  fingerprints became stale after source/version changes. Regeneration follows
  source review; final package verification is recorded below when complete.
- GitHub connector PR creation returned an integration-permission 403. The
  authenticated CLI created draft PR #995 and triggered native Windows CI.

## Privacy and live-host limits

Source review found no new recipient, model-context selection, network call or
professional action in this transport-only change. Governed privacy fingerprints
and generated contracts were refreshed after reviewing the changed source.

The synthetic tests do not establish fresh installed-host acceptance, real
Codex/Cowork model execution, readable privacy-report delivery or signed receipt
acceptance. No customer installation or Marketplace listing was changed.
Pipeline boundary results and privacy-report acceptance remain separate.

## Completed local package checks

- `build_product_release.py vera clara lucia` succeeded: Vera 0.1.631,
  Clara 0.1.418, Lucia 0.1.241, across Codex, ChatGPT upload, Cowork and
  Antigravity. Local Cowork startup checks passed for 24/3/7 MCP entries;
  Antigravity startup checks passed for each product.
- Package integrity/update-notification suites: 416 passed, 2 skipped.
- Rebuilt research/shared-runtime package tests: 121 passed.
- Reporting transport with authorized loopback access: 21 passed.
- The shared-runtime/release/verified-execution group passed 214 tests and
  skipped 8 platform cases in its initial run; the only failures were the
  then-unbuilt Cowork archives and sandbox-denied loopback listeners, both
  covered by the successful reruns above.

Formatting checks: Black and Isort passed for the changed Python source/test files.
The archive-size check measured 121.62 MiB, below the maintained 230 MiB guard.

## Native Windows evidence

[Windows job 132019599408](https://github.com/fabioannovazzi/app_files/actions/runs/43464424015/job/132019599408)
passed all four tests at source commit `af5cb7b6e`. Its retained artifact
`utf8-evidence-windows-latest/utf8-results.xml` records `default_encoding=cp1252`
and `utf8_mode=0` for Bandi, research and Cowork scenarios. The native job
restart test also passed. The actual non-ASCII fixture is `Synthetic Łódź → dossier`;
fixture directories and the retained native helper's argument path include
characters not representable in cp1252.

This is native GitHub-hosted Windows evidence, not a simulated locale or live
customer installation. The later source adjustment is Black formatting of
`scripts/local_helper_environment.py`; generated contracts/distributions are
rebuilt from that formatted source. No behavior was changed after this Windows
run. The entire PR's required CI remains separate from this focused result.

Native runner: Windows Server 2025 (`windows-2025-vs2026`, image
`20261103.298.1`), Python 3.12.10.

Final Vera archive SHA-256 values:

- `vera-chatgpt-upload.zip`: `6bb1e2c864bc513c79f20645e45dc4b292c8f29c47032527ee47752b02741756`
- `vera-claude-plugin.zip`: `cb9861dbfd37556199d04e719dc00370775e7af68237cdcd70ea5691e838de05`
- `vera-plugin.zip`: `1fe4f0c282b5b71b160c224a0204c5cb897cd472a62546bc434b913454538a83`

A normalized AST comparison of 117 changed Python source files found only
UTF-8 keyword arguments, interpreter UTF-8 options and policy-revision metadata;
the two additional expected changes were the owned PowerShell output encoding
and the review-adapter generator’s Python command templates.

Final `python scripts/build_product_release.py vera clara lucia --check`
passed after the last source formatting change, including all product/host ZIP
parity, retained privacy projections, MCP startup checks and version alignment.
