#!/usr/bin/env python3
"""
run_codex_test_repair.py  (WSL/Ubuntu optimized; tests-only)

Purpose
-------
Scan your tests for common breakage patterns (stale imports, shadowing/stubs,
pandas-era assertions, empty/pointless tests, etc.) and ask Codex to _repair_
those tests in-place so they become useful again.

Design
------
- Same outer shape and CLI as your refactor wrapper (args, target list file,
  one-file-per-exec loop, git-commit option). Keeps the workflow consistent.
- Looks ONLY at paths listed in --paths-from (default: tests_to_scan.txt).
- With --all: include every test file (*.py) found under the listed paths.
- Without --all: include only _candidate_ tests found by the detector.
- Writes the current target path to a single-file "{targets_file}" that the
  prompt references ("edit only this file").
- Embeds per-file diagnostics (detected issues, shadowed packages, etc.) to
  give Codex enough context to make precise, minimal edits.

What it tries to improve
------------------------
1) Import errors caused by test-local stubs that shadow real packages
   (e.g., `tests/modules/...` overriding `modules/...`), or by sys.path hacks.
2) Stale imports / APIs (e.g., pandas-era checks after a Polars migration).
3) Pointless tests:
   - `test_*` functions with no assertions or only `print()`.
   - unconditional `pytest.skip()` or `return` at top-level inside test fn.
4) Brittle patching: replace hand-rolled stubs with localized monkeypatch/mocker.
5) Test readability/parametrization where trivial/obvious.

Usage
-----
Examples (from repo root, in WSL/Ubuntu):



# Dry run (print targets and the exact prompt, but do not invoke Codex):
./run_codex_test_repair.py --paths-from tests_to_scan.txt --dry-run

# For a single file:
./run_codex_test_repair.py --paths-from tests_to_scan.txt --test --test-file tests/test_top_hundred_streaming.py

# Add per-file pytest collection output to the prompt (more context for Codex):
./run_codex_test_repair.py --paths-from tests_to_scan.txt --pytest-diagnostics

  ./run_codex_test_repair.py \
    --paths-from tests_to_scan.txt \
    --git-commit \
    --git-message "codex: repair tests"

  ./run_codex_test_repair.py \
    --paths-from tests_to_scan.txt \
    --all \
    --git-commit \
    --git-message "codex: repair tests (all)"

  # Dry-run: see which files would be targeted + prompts constructed
  ./run_codex_test_repair.py --paths-from tests_to_scan.txt --dry-run

Notes
-----
- Requires the `codex` CLI on PATH (npm i -g @openai/codex).
- For detection (optional), it can run `pytest --collect-only` for a single file
  and embed the collector output into the prompt (disabled by default).
- Focuses on minimal, surgical changes — no test rewrites unless required to
  make the test meaningful and consistent with current code.
"""

import argparse
import ast
import os
import re
import shutil
import subprocess
import tokenize as tkn
from pathlib import Path
from typing import Iterable

from modules.utilities.config import get_naming_params

DEFAULT_EXCLUDES = {
    ".venv",
    "venv",
    "env",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "site-packages",
    "dist",
    "build",
    "node_modules",
}

# ──────────────────────────────
# Regex patterns for test hints
# ──────────────────────────────
PANDAS_IMPORT_RE = re.compile(r"\bimport\s+pandas\s+as\s+pd\b")
SYS_PATH_HACK_RE = re.compile(r"sys\.path\.insert\(\s*0\s*,\s*[^)]+?\)")
UNCONDITIONAL_SKIP_RE = re.compile(r"\bpytest\.skip\(\s*['\"]?.*?['\"]?\s*\)\s*$")
ONLY_PASS_IN_TEST_RE = re.compile(
    r"^\s*def\s+test_[A-Za-z0-9_]*\s*\([^)]*\)\s*:\s*pass\s*$", re.M
)


# Something that obviously looks like a shadow package path inside tests
def looks_like_shadow_package(path: Path, top_packages: set[str]) -> bool:
    # e.g., tests/modules/... or tests/<pkg>/...
    parts = set(path.parts)
    return "tests" in parts and any(pkg in parts for pkg in top_packages)


# ──────────────────────────────
# Utilities
# ──────────────────────────────
def strip_strings_and_comments(path: Path) -> str:
    """Return file contents with string literals and comments removed."""
    try:
        with tkn.open(str(path)) as f:
            tokens = tkn.generate_tokens(f.readline)
            out = []
            for tok in tokens:
                if tok.type in (tkn.STRING, tkn.COMMENT):
                    out.append(" ")
                elif tok.type == tkn.NL:
                    out.append("\n")
                else:
                    out.append(tok.string)
            return "".join(out)
    except Exception:
        return path.read_text(encoding="utf-8", errors="ignore")


def should_skip(path: Path, repo: Path, excluded: set[str]) -> bool:
    rel = path.relative_to(repo)
    return any(part in excluded for part in rel.parts)


def get_src_root(repo: Path) -> Path:
    """Heuristic for src layout vs flat layout."""
    if (repo / "src").is_dir():
        return repo / "src"
    return repo


def find_top_level_packages(repo: Path) -> set[str]:
    src = get_src_root(repo)
    pkgs: set[str] = set()
    for child in src.iterdir():
        if child.is_dir():
            if (child / "__init__.py").exists():
                pkgs.add(child.name)
            else:
                # namespace/implicit packages: consider dirs that have any .py files
                if any(p.suffix == ".py" for p in child.rglob("*.py")):
                    pkgs.add(child.name)
    return pkgs


def list_shadow_package_dirs(
    tests_root_candidates: Iterable[Path], top_packages: set[str]
) -> list[Path]:
    shadows = []
    for troot in tests_root_candidates:
        if not troot.exists():
            continue
        for pkg in top_packages:
            cand = troot / pkg
            if cand.is_dir():
                shadows.append(cand)
    return shadows


def ast_has_asserts(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.With):
            # with pytest.raises(...):
            for item in node.items:
                expr = ast.unparse(item.context_expr) if hasattr(ast, "unparse") else ""
                if "pytest.raises" in expr:
                    return True
        if isinstance(node, ast.Call):
            # pytest.fail / hypothesis checks can count as an assertion surrogate
            func = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if func in {"fail"}:
                return True
    return False


def file_has_meaningful_tests(path: Path) -> bool:
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
    except Exception:
        return True  # if we can't parse, let Codex fix; count as candidate
    tests = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]
    if not tests:
        return False
    for t in tests:
        # Does this test contain at least one assert/raises/fail?
        subtree = ast.Module(body=t.body, type_ignores=[])
        if ast_has_asserts(subtree):
            return True
    return False


def is_candidate_test_file(path: Path, repo: Path, top_packages: set[str]) -> bool:
    code = strip_strings_and_comments(path)
    # Quick wins: pandas imports, sys.path hacks, unconditional skip, pass-only test
    if PANDAS_IMPORT_RE.search(code):
        return True
    if SYS_PATH_HACK_RE.search(code):
        return True
    if UNCONDITIONAL_SKIP_RE.search(code):
        return True
    if ONLY_PASS_IN_TEST_RE.search(code):
        return True
    # Shadowed package present in its path?
    if looks_like_shadow_package(path, top_packages):
        return True
    # No meaningful asserts?
    if not file_has_meaningful_tests(path):
        return True
    return False


def resolve_codex_binary(codex_arg: str) -> str | None:
    cand = shutil.which(codex_arg)
    if cand:
        return cand
    return None


def require_shell_deps_or_die():
    """Ensure POSIX deps we rely on are present."""
    if os.name == "posix" and shutil.which("rg") is None:
        raise SystemExit(
            "ripgrep (rg) not found. Install it first:\n"
            "  sudo apt update && sudo apt install -y ripgrep\n"
        )


def run_pytest_collect_for_file(repo: Path, target: Path) -> str:
    """Optional: run pytest collection for a single file to capture import/collection errors."""
    try:
        proc = subprocess.run(
            ["pytest", "-q", "--collect-only", str(target)],
            cwd=str(repo),
            text=True,
            capture_output=True,
            check=False,
        )
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return out.strip()
    except Exception as e:
        return f"(pytest diagnostics unavailable: {e})"


def summarize_shadow_info(
    repo: Path, tests_roots: list[Path], top_packages: set[str]
) -> str:
    shadows = list_shadow_package_dirs(tests_roots, top_packages)
    if not shadows:
        return "No test-local shadow packages detected."
    lines = ["Detected test-local packages that may shadow production packages:"]
    for p in shadows:
        # show a few leaf files to provide context
        samples = sorted([str(x.relative_to(repo)) for x in p.rglob("*.py")])[:5]
        lines.append(f"- {p.relative_to(repo)} (sample files: {samples})")
    return "\n".join(lines)


# ──────────────────────────────
# Prompt builder
# ──────────────────────────────
def build_prompt_tests(
    inline_paths: list[str], targets_file: str, diagnostics: str
) -> str:
    paths_block = "\n".join(f"- {p}" for p in inline_paths)
    return f"""
REPAIR TESTS IN THE FILES BELOW (and only those listed and in "{targets_file}").
The tests are obsolete or misconfigured (shadowed packages, sys.path hacks, pandas-era checks,
missing assertions, or unconditional skip) and may currently fail due to missing inputs or brittle assumptions.
Make minimal, surgical edits so they become useful and consistent with the current codebase.

FILES TO EDIT (relative to repo root):
{paths_block}

DIAGNOSTICS (context only; do not edit paths unless targeting the file above):
{diagnostics}

GOAL
- Fix import failures and shadowing: avoid test-local package stubs that override real code.
  Prefer pytest monkeypatch/mocker for specific functions rather than shadow packages.
- Modernize assertions for Polars code where obvious: compare DataFrames via sorted rows,
  schema checks, and value equality, not pandas-only helpers.
- Ensure each test has at least one meaningful assertion (or pytest.raises).
- Remove unconditional pytest.skip() or convert to skipif with a clear condition/reason.
- Keep changes minimal. Preserve test intent and coverage. Do not change production code.
- Avoid tests that raise KeyError due to missing config keys or session state; provide dummy inputs or defaults for required keys (e.g., 'chosenChart', 'timelineChart', 'dateName', 'compareWithYearBefore').
- If the code under test expects a Polars LazyFrame or specific input data (e.g., a numeric column), provide a minimal DataFrame or LazyFrame with appropriate dummy data (such as one numeric column) to avoid runtime errors (e.g., "no numeric column found" or TypeErrors from None values).
- Avoid trivial or placeholder assertions: do not include `assert False` (unless marking a TODO) or any assertion that is always true/false without verifying real behavior.
- If a test scenario cannot be reliably constructed due to external dependencies or unclear inputs, use `pytest.skip("reason")` with a brief explanation instead of leaving a failing test.
- Tests should be idempotent: no side effects or order dependencies. Rerunning the tests should consistently produce the same outcome (pass or skip).

PLAYBOOK
1) If the test imports from a shadow package (e.g., 'tests/modules/...'):
   - Replace sys.path insertion with proper imports from the real package.
   - If a stub exists only to override a single function, delete that use and instead use
     pytest's monkeypatch/mocker within the test to replace the function during the test.
2) If the test fails on 'ImportError: cannot import name <X> from modules.utilities.utils':
   - Ensure the test imports the real 'modules.utilities.utils' module.
   - If this test relied on a stubbed version missing <X>, remove that reliance and
     monkeypatch only the necessary names inside the test.
3) Assertions:
   - If there are no assertions, add targeted assertions that verify the behavior under test.
   - Replace print-based checks with asserts.
4) Polars vs pandas:
   - If the test uses pandas-specific helpers, rewrite to idiomatic Polars checks, e.g.:
     * equality: sort rows/columns deterministically and compare to expected lists/dicts
     * schema: df.schema or df.columns checks
5) Style:
   - Keep parametrization where it reduces duplication (pytest.mark.parametrize).
   - Avoid changing function names unless adding 'test_' to enable collection.

CONSTRAINTS
- Edit ONLY the files shown in "FILES TO EDIT".
- Do NOT add new dependencies. You may add or adjust pytest fixtures.
- Keep diffs focused on the issues above (imports, assertions, minimal modernization).

ACCEPTANCE
- The file imports without errors and collects under 'pytest --collect-only'.
- At least one assertion (or raises) per test function.
- No unconditional 'pytest.skip()' left (unless converted to conditional skip).
- No test-local package shadowing of production code; use monkeypatch/mocker instead.
- No test fails due to missing configuration or data (all required keys/inputs are provided or the test is skipped).
- Tests pass (or skip) consistently even if run multiple times.
""".strip()


# ──────────────────────────────
# Main
# ──────────────────────────────
def main():
    naming = get_naming_params()
    ap = argparse.ArgumentParser(
        description="Repair misconfigured/obsolete tests with Codex (tests-only)."
    )
    ap.add_argument("--repo", default=".", help="Repo root (default: .)")
    ap.add_argument(
        "--paths-from",
        default="tests_to_scan.txt",
        help="Text file with one subfolder, file, or glob per line (e.g., tests, tests/**/*.py). Lines starting with # are ignored.",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Include all *.py under the listed subfolders/patterns (ignore detector).",
    )
    ap.add_argument(
        "--exclude",
        nargs="*",
        default=sorted(DEFAULT_EXCLUDES),
        help="Folder names to ignore anywhere in the path.",
    )
    ap.add_argument(
        "--targets-file",
        default=".codex_test_targets.txt",
        help="Filename to write the target list (single path per run).",
    )
    ap.add_argument(
        "--codex",
        default="codex",
        help="Codex CLI binary or full path (default: codex)",
    )
    ap.add_argument(
        "--model",
        default=naming["gpt5ThinkingMini"],
        help=(
            "LLM model to use (default: "
            f"{naming['gpt5ThinkingMini']} from config; supply --model for custom model)"
        ),
    )
    ap.add_argument(
        "--test",
        action="store_true",
        help="If set, only run on a single file (first match unless --test-file).",
    )
    ap.add_argument(
        "--test-file",
        default=None,
        help="Explicit test file path (must still be inside the listed paths).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would run without invoking Codex.",
    )
    ap.add_argument(
        "--git-commit",
        action="store_true",
        help="After Codex runs, git add -A && git commit.",
    )
    ap.add_argument(
        "--git-message",
        default="codex: repair tests",
        help="Commit message to use with --git-commit.",
    )
    ap.add_argument(
        "--pytest-diagnostics",
        action="store_true",
        help="Include 'pytest --collect-only' output for each target in the prompt.",
    )

    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists():
        raise SystemExit(f"Repo path not found: {repo}")

    list_file = repo / args.paths_from
    if not list_file.exists():
        raise SystemExit(f"--paths-from file not found: {list_file}")

    excluded = set(args.exclude)
    src_root = get_src_root(repo)
    top_packages = find_top_level_packages(repo)

    # Build patterns from --paths-from (subfolders/files/globs)
    patterns: list[str] = []
    explicit_files: list[Path] = []
    tests_roots: list[Path] = []
    for raw in list_file.read_text(encoding="utf-8").splitlines():
        s = raw.strip().replace("\\", "/")
        if not s or s.startswith("#"):
            continue
        p = repo / s
        if p.is_dir():
            tests_roots.append(p.resolve())
            patterns.append((Path(s).as_posix().rstrip("/") + "/**/*.py"))
        elif p.is_file() and p.suffix == ".py":
            explicit_files.append(p.resolve())
        else:
            patterns.append(s)

    pool_set = set(explicit_files)
    for pat in patterns:
        for p in repo.rglob(pat):
            if (
                p.is_file()
                and p.suffix == ".py"
                and p.name != "__init__.py"
                and not should_skip(p, repo, excluded)
            ):
                pool_set.add(p)
    pool = sorted(pool_set)

    # Choose candidates
    if args.all:
        candidates = pool
    else:
        candidates = [p for p in pool if is_candidate_test_file(p, repo, top_packages)]
    if not candidates:
        raise SystemExit(
            "No Python tests matched the listed subfolders/patterns."
            if args.all
            else "No obviously broken/obsolete tests found in the listed subfolders."
        )

    # TEST mode narrowing
    if args.test:
        if args.test_file:
            tf = (repo / args.test_file).resolve()
            if tf not in pool_set:
                raise SystemExit(
                    f"--test-file must be within the listed subfolders/patterns: {tf}"
                )
            if tf.name == "__init__.py":
                raise SystemExit("--test-file cannot be __init__.py")
            targets = [tf]
        else:
            targets = [candidates[0]]
    else:
        targets = candidates

    # Exclude __init__.py everywhere
    targets = [p for p in targets if p.name != "__init__.py"]
    if not targets:
        raise SystemExit("No eligible Python test files (after excluding __init__.py).")

    codex_bin = resolve_codex_binary(args.codex)
    if not codex_bin:
        raise SystemExit(
            "Could not find Codex CLI 'codex'. Install with:\n"
            "  npm i -g @openai/codex\n"
        )

    if not args.dry_run:
        require_shell_deps_or_die()

    # Useful global context
    shadow_summary = summarize_shadow_info(
        repo, tests_roots or [repo / "tests"], top_packages
    )

    cmd_base = [codex_bin, "exec"]
    if getattr(args, "full_auto", False):
        cmd_base.append("--full-auto")
    if args.model:
        cmd_base += ["--model", args.model]
    cmd_base += [
        "--config",
        "approval_policy=never",
        "--config",
        "sandbox_mode=danger-full-access",
        "--config",
        "model_reasoning_effort=high",
    ]

    print(f"[codex-tests] Repo: {repo}")
    print(f"[codex-tests] Targets: {len(targets)} file(s)")
    print(f"[codex-tests] List file: {(repo / args.targets_file)}")
    print(f"[codex-tests] Excluding folders: {', '.join(sorted(excluded))}")
    print(
        f"[codex-tests] Top-level packages: {', '.join(sorted(top_packages)) or '(none detected)'}"
    )
    print(f"[codex-tests] Shadow summary:\n{shadow_summary}\n")

    #
    # Iterate over each target test file.  We avoid committing after each file to
    # reduce noise in the git history.  A single commit will be executed after
    # all files have been repaired.  See the block following this loop for
    # commit handling.
    for i, tr_path in enumerate(targets, 1):
        tr_rel = Path(tr_path).relative_to(repo).as_posix()

        # Per-target diagnostics
        per_file_diag = [f"Target file: {tr_rel}"]
        per_file_diag.append(
            f"Top-level packages: {', '.join(sorted(top_packages)) or '(none detected)'}"
        )
        per_file_diag.append(shadow_summary)

        if args.pytest_diagnostics:
            per_file_diag.append("\nPYTEST --collect-only OUTPUT (for this file):\n")
            per_file_diag.append(run_pytest_collect_for_file(repo, tr_path))

        diagnostics = "\n".join(per_file_diag)

        # Write a single-file target list (the prompt references this filename)
        (repo / args.targets_file).write_text(tr_rel + "\n", encoding="utf-8")

        prompt = build_prompt_tests([tr_rel], args.targets_file, diagnostics)
        cmd = cmd_base + [prompt]

        print(f"[codex-tests] ({i}/{len(targets)}) Repairing: {tr_rel}")
        if args.dry_run:
            print("  [dry-run] Would run:", " ".join(cmd))
            continue

        try:
            subprocess.run(cmd, cwd=str(repo), check=True)
        except subprocess.CalledProcessError as e:
            raise SystemExit(
                f"[codex-tests] Codex failed on {tr_rel} ({e.returncode})\n"
                f"STDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
            )

        # Note: we intentionally avoid committing after each file.  A global
        # commit will be performed once all files have been processed.

    # After repairing all test files we optionally perform a single Git commit.
    # This summarises all test repairs into one commit and respects .gitignore.
    # If --git-commit is not provided, no commit is made.
    if args.git_commit:
        # Stage all changes (respecting .gitignore)
        subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
        summary_msg = f"{args.git_message} [{len(targets)} files]"
        commit_proc = subprocess.run(
            ["git", "commit", "-m", summary_msg],
            cwd=str(repo),
            text=True,
            capture_output=True,
        )
        if commit_proc.returncode == 0:
            commit = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(repo),
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            print(f"[codex-tests] Committed all changes in one commit as {commit}")
        else:
            print("[codex-tests] No commit performed (likely no changes). Git said:")
            print(commit_proc.stdout or commit_proc.stderr)


if __name__ == "__main__":
    main()
