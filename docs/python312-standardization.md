# One Python version for Vera, Clara and Lucia

All three products now select CPython 3.12 for managed workflow execution. A host Python may start the setup utility, but the environment is created using a verified 3.12 executable. Existing 3.10/3.11 environments are preserved and are not selected by the new ABI key. Already installed 3.12 environments remain reusable when their dependency receipts match.

Setup first uses the current interpreter if it is CPython 3.12, then searches for python3.12 (or the Windows py -3.12 launcher). If neither is available, an already installed uv can provision the declared CPython 3.12 distribution. Without either mechanism, setup stops with a concrete installation instruction. No additional Python version is installed for compatibility testing.

All product CI jobs use Python 3.12. The previous 3.10/3.12 test matrix is removed; simulated negative tests still verify rejection or redirection from other host versions. Fresh Cowork tests cover Vera, Clara and Lucia and assert the installed interpreter receipt is 3.12.

This standardizes the interpreter version, not the dependency graphs: separate component virtual environments remain. Optional OCR setup keeps its existing approval boundary. Existing user environments are not deleted. uv Python download behavior is documented at https://docs.astral.sh/uv/guides/install-python/ .

Validation and release results will be recorded in outputs/python312-standardization.

## Local validation

- Final runtime/package/privacy/version-gate regression run: 645 passed, no failures, errors or skips.
- Shared runtime coverage: 84.95%; 24 kernel files pass the unsuppressed configured Mypy check.
- Black/Isort and runtime security scan pass. All product ZIPs match source; Vera 18 and Lucia 4 packaged MCP servers initialize and list tools.
- Prior source coverage: 80.22%; no src files changed in this release. Fresh Linux CI remains required before merge.
