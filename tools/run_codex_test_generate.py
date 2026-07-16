#!/usr/bin/env python3
"""
run_codex_test_generate.py  (WSL/Ubuntu-optimized; focus: USEFUL tests, not coverage)

Goal
----
Generate *useful*, minimal, high-signal PyTest tests for important code paths.
No reliance on coverage %. We target value/risk via:
  - recently changed modules/functions (git),
  - higher-complexity functions,
  - public APIs,
  - explicit lists you provide.

Design principles
-----------------
- Script lives under tools/ and auto-detects repo root as parent of tools/.
- One Codex exec per target test file (reduces noise; clean diffs).
- Prompts encode a "Useful Tests Charter": AAA structure, deterministic inputs,
  no network/I/O (except tmp_path), no sys.path hacks, meaningful assertions,
  clear invariants, Polars-aware checks when applicable.
- Zero new deps by default (optionally allow Hypothesis via flag).
- Never edits production code; only creates/edits tests/* files.

Usage
-----
# 0) List areas to consider (globs/dirs/files), one per line:
#    repo-root/modules_to_target.txt   e.g.:
#    src
#    modules/**/*.py

# 1) Generate tests for high-value targets (changed  public  complex):
python3 tools/run_codex_test_generate.py \
  --paths-from modules_to_target.txt \
  --strategy changed public complex \
  --git-commit \
  --git-message "codex: add useful tests (risk-based)"

python3 tools/run_codex_test_generate.py \
  --paths-from modules_to_target.txt \
  --strategy changed public complex \
  --resume --skip-existing \
  --git-commit \
  --git-message "codex: add useful tests (resume)"

Resume from a specific point (if you know the last file that completed):

python3 tools/run_codex_test_generate.py \
  --paths-from modules_to_target.txt \
  --strategy changed public complex \
  --resume --skip-existing \
  --start-from tests/modules/add_attributes/test_modules_add_attributes_pareto.py


Batching (to avoid running into token limits again):

python3 tools/run_codex_test_generate.py \
  --paths-from modules_to_target.txt \
  --strategy changed public complex \
  --resume --skip-existing \
  --limit-modules 25

# 2) If you want to focus just on recent changes since a date or range:
python3 tools/run_codex_test_generate.py \
  --paths-from modules_to_target.txt \
  --strategy changed \
  --since "2025-08-01" \
  --git-commit

# 3) For an explicit list of functions (one per line: <module>:<qualname>):
#    repo-root/functions_to_test.txt   e.g.:
#    mypkg.mod:parse_date
#    mypkg.tools.cleaner:Cleaner.run
python3 tools/run_codex_test_generate.py \
  --paths-from modules_to_target.txt \
  --strategy explicit \
  --functions-from functions_to_test.txt \
  --git-commit

Requirements
------------
- Codex CLI on PATH: npm i -g @openai/codex
- git available for changed-file strategies
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

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
    "tests",  # exclude tests from source pool by default
}

# ──────────────────────────────────────────────────────────────────────────────
# Path  repo utilities (script sits in tools/)
# ──────────────────────────────────────────────────────────────────────────────


def repo_root_from_tools() -> Path:
    # tools/run_codex_test_generate.py -> repo root is parent of tools/
    return Path(__file__).resolve().parents[1]


def ensure_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# created by run_codex_test_generate.py\n", encoding="utf-8")


def run(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)


def resolve_codex_binary(codex_arg: str) -> Optional[str]:
    return shutil.which(codex_arg)


def should_skip(path: Path, repo: Path, excluded: set[str]) -> bool:
    rel = path.relative_to(repo)
    return any(part in excluded for part in rel.parts)


def get_src_root(repo: Path) -> Path:
    return repo / "src" if (repo / "src").is_dir() else repo


def module_import_from_path(repo: Path, src_root: Path, py_file: Path) -> str:
    """
    Derive a module import path from a source file.

    We prefer to compute the path relative to ``src_root`` when possible,
    but if the file isn't under that tree (e.g. it lives in a top‑level
    ``modules`` directory), fall back to making it relative to the repo root.

    This prevents ``ValueError: ... is not in the subpath of ...`` when
    processing files outside ``src_root``.
    """
    base = src_root if src_root.exists() else repo
    try:
        rel = py_file.relative_to(base)
    except ValueError:
        # Fallback: compute relative to repo root if not under src_root
        rel = py_file.relative_to(repo)
    # Convert '__init__.py' to its package path; strip suffix from other files
    if rel.name == "__init__.py":
        rel = rel.parent
    else:
        rel = rel.with_suffix("")
    return ".".join(rel.parts)


def default_test_file_for_module(repo: Path, src_root: Path, src_file: Path) -> Path:
    """
    Determine the location of the test file for a given source file.

    If the source file lives under src_root, derive the path relative to src_root;
    otherwise, fall back to deriving it relative to the repository root. This allows
    modules in other top-level directories (e.g. `modules/`) to be handled gracefully.

    Example:
      src/pkg/foo.py         -> tests/pkg/test_foo.py
      modules/add/bar.py     -> tests/modules/add/test_bar.py
    """
    base = src_root if src_root.exists() else repo
    try:
        rel = src_file.relative_to(base)
    except ValueError:
        # Fallback: handle modules outside src_root
        rel = src_file.relative_to(repo)
    if rel.name == "__init__.py":
        stem = f"test_{rel.parent.name}.py"
        target_rel = Path("tests") / rel.parent / stem
    else:
        # Build a unique test file name from all parts of the relative path
        parts = rel.with_suffix(
            ""
        ).parts  # e.g. ('modules','deep_research_prompt','logic')
        test_name = "test_" + "_".join(parts) + ".py"
        target_rel = Path("tests") / rel.parent / test_name
    return (repo / target_rel).resolve()


# ──────────────────────────────────────────────────────────────────────────────
# Source scanning  function discovery
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class FunctionInfo:
    name: str
    qualname: str
    lineno: int
    end_lineno: int
    is_method: bool
    complexity: int
    has_docstring: bool


def _end_lineno(node: ast.AST) -> int:
    if hasattr(node, "end_lineno") and isinstance(node.end_lineno, int):
        return int(node.end_lineno)
    end_ln = getattr(node, "lineno", 0)
    for ch in ast.walk(node):
        ln = getattr(ch, "lineno", None)
        if isinstance(ln, int) and ln > end_ln:
            end_ln = ln
    return end_ln


BRANCH_NODES = (
    ast.If,
    ast.For,
    ast.While,
    ast.Try,
    ast.With,
    ast.BoolOp,
    ast.IfExp,
    ast.Match,
)  # coarse cyclomatic


def estimate_complexity(fn: ast.AST) -> int:
    c = 1
    for n in ast.walk(fn):
        if isinstance(n, BRANCH_NODES):
            c += 1
        elif isinstance(n, ast.comprehension):
            c += 1
        elif isinstance(n, ast.Call) and getattr(
            getattr(n.func, "id", None), "lower", lambda: ""
        )() in {"any", "all"}:
            c += 1
    return c


def functions_in_file(src_path: Path) -> List[FunctionInfo]:
    try:
        code = src_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(code)
    except Exception:
        return []
    out: List[FunctionInfo] = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.cls: List[str] = []

        def visit_ClassDef(self, node: ast.ClassDef):
            self.cls.append(node.name)
            self.generic_visit(node)
            self.cls.pop()

        def _add(self, node: ast.AST, name: str):
            # Build a qualified name by combining class names and the function name.
            qual = ".".join(self.cls + [name]) if self.cls else name
            ds = ast.get_docstring(node) is not None
            out.append(
                FunctionInfo(
                    name=name,
                    qualname=qual,
                    lineno=getattr(node, "lineno", 1),
                    end_lineno=_end_lineno(node),
                    is_method=bool(self.cls),
                    complexity=estimate_complexity(node),
                    has_docstring=ds,
                )
            )

        def visit_FunctionDef(self, node: ast.FunctionDef):
            self._add(node, node.name)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self._add(node, node.name)
            self.generic_visit(node)

    V().visit(tree)
    return out


def list_source_pool(repo: Path, paths_from: Path, excluded: set[str]) -> List[Path]:
    if not paths_from.exists():
        raise SystemExit(f"--paths-from file not found: {paths_from}")
    patterns: List[str] = []
    explicit: List[Path] = []
    for raw in paths_from.read_text(encoding="utf-8").splitlines():
        s = raw.strip().replace("\\", "/")
        if not s or s.startswith("#"):
            continue
        p = repo / s
        if p.is_dir():
            patterns.append(Path(s).as_posix().rstrip("/") + "/**/*.py")
        elif p.is_file() and p.suffix == ".py":
            explicit.append(p.resolve())
        else:
            patterns.append(s)

    pool_set = set(explicit)
    for pat in patterns:
        for p in repo.rglob(pat):
            if (
                p.is_file()
                and p.suffix == ".py"
                and p.name != "__init__.py"
                and not should_skip(p, repo, excluded)
            ):
                pool_set.add(p.resolve())
    # Drop any already under tests/
    pool = [p for p in sorted(pool_set) if "/tests/" not in p.as_posix()]
    return pool


# ──────────────────────────────────────────────────────────────────────────────
# Strategies: changed, public, complex, explicit
# ──────────────────────────────────────────────────────────────────────────────


def git_changed_files(
    repo: Path, since: Optional[str], commit_range: Optional[str]
) -> set[Path]:
    changed: set[Path] = set()
    if commit_range:
        proc = run(["git", "diff", "--name-only", commit_range], cwd=repo)
        for line in (proc.stdout or "").splitlines():
            pp = (repo / line.strip()).resolve()
            if pp.suffix == ".py":
                changed.add(pp)
    elif since:
        proc = run(
            ["git", "log", f"--since={since}", "--name-only", "--pretty=format:"],
            cwd=repo,
        )
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            pp = (repo / line).resolve()
            if pp.suffix == ".py":
                changed.add(pp)
    else:
        # Fallback: compare to the first commit or HEAD~50
        proc = run(["git", "diff", "--name-only", "HEAD~50...HEAD"], cwd=repo)
        for line in (proc.stdout or "").splitlines():
            pp = (repo / line.strip()).resolve()
            if pp.suffix == ".py":
                changed.add(pp)
    return changed


def explicit_functions_from(
    repo: Path, src_root: Path, functions_file: Optional[Path]
) -> Dict[Path, List[str]]:
    """
    Returns {abs_src_file: [qualname, ...]} for explicit function targets like:
      mypkg.mod:parse_date
      mypkg.tools.cleaner:Cleaner.run
    """
    mapping: Dict[Path, List[str]] = {}
    if not functions_file or not functions_file.exists():
        return mapping
    for raw in functions_file.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        mod, qual = s.split(":", 1)
        # Convert module path to file
        mod_path = (src_root / Path(mod.replace(".", "/") + ".py")).resolve()
        if mod_path.exists():
            mapping.setdefault(mod_path, []).append(qual.strip())
    return mapping


# ──────────────────────────────────────────────────────────────────────────────
# Selection/scoring for usefulness (not coverage!)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class TargetFn:
    src_file: Path
    import_path: str
    test_file: Path
    func: FunctionInfo
    score: int
    signals: List[str]


def rank_functions_for_usefulness(
    repo: Path,
    src_root: Path,
    pool: List[Path],
    strategy_changed: bool,
    strategy_public: bool,
    strategy_complex: bool,
    explicit_map: Dict[Path, List[str]],
    since: Optional[str],
    commit_range: Optional[str],
    include_private: bool,
    focus_regex: Optional[re.Pattern],
    max_per_module: int,
) -> List[TargetFn]:
    changed_files = (
        git_changed_files(repo, since, commit_range) if strategy_changed else set()
    )
    targets: List[TargetFn] = []

    for src in pool:
        fns = functions_in_file(src)
        if not fns:
            continue

        # Precompute
        mod_import = module_import_from_path(repo, src_root, src)
        test_file = default_test_file_for_module(repo, src_root, src)
        is_changed = src in changed_files
        explicit_list = explicit_map.get(src, [])

        # Score each function
        scored: List[TargetFn] = []
        for fn in fns:
            if not include_private and fn.name.startswith("_"):
                if fn.qualname not in explicit_list:
                    continue

            signals: List[str] = []
            score = 0

            # Explicit target gets highest priority
            if explicit_list and (
                fn.qualname in explicit_list or fn.name in explicit_list
            ):
                score += 100
                signals.append("explicit")

            # Changed files get a healthy boost
            if is_changed:
                score += 20
                signals.append("changed")

            # Public API preference
            if strategy_public and not fn.name.startswith("_") and not fn.is_method:
                score += 10
                signals.append("public_api")

            # Complexity weighting (cap moderate)
            if strategy_complex:
                score += min(
                    15, max(0, fn.complexity - 2)
                )  # complexity > 2 gains points
                if fn.complexity >= 6:
                    signals.append(f"complexity={fn.complexity}")

            # Docstring presence suggests stable contract
            if fn.has_docstring:
                score += 3
                signals.append("docstring")

            # Focus filter
            if focus_regex and not (
                focus_regex.search(fn.qualname) or focus_regex.search(src.as_posix())
            ):
                continue

            # Polars hints: encourage tests; avoid UI/integration
            try:
                text = src.read_text(encoding="utf-8", errors="ignore") or ""
                if "import polars" in text or " as pl" in text:
                    score += 3
                    signals.append("polars")
            except Exception:
                pass

            if score > 0:
                scored.append(
                    TargetFn(
                        src_file=src,
                        import_path=mod_import,
                        test_file=test_file,
                        func=fn,
                        score=score,
                        signals=signals,
                    )
                )

        if not scored:
            continue

        # Pick top-N useful per module
        scored.sort(key=lambda t: (-t.score, t.func.lineno))
        for t in scored[:max_per_module]:
            targets.append(t)

    # Order modules with most signal first
    targets.sort(key=lambda t: (-t.score, t.src_file.as_posix(), t.func.lineno))
    return targets


# ──────────────────────────────────────────────────────────────────────────────
# Context helpers for prompt
# ──────────────────────────────────────────────────────────────────────────────


def slice_source(path: Path, start: int, end: int, max_lines: int = 180) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return "(source not readable)"
    start = max(1, start)
    end = min(len(lines), end)
    seg = lines[start - 1 : end]
    if len(seg) > max_lines:
        seg = seg[:max_lines]
    return "\n".join(seg)


def grep_usages(
    repo: Path, import_path: str, fn_name: str, max_hits: int = 5
) -> List[str]:
    """
    Best-effort: uses ripgrep (rg) if available to find call sites like 'mod.fn('
    Not required. Returns small snippets for context.
    """
    if shutil.which("rg") is None:
        return []
    q1 = rf"{re.escape(import_path.split('.')[-1])}\s*\.\s*{re.escape(fn_name)}\s*\("
    q2 = rf"{re.escape(fn_name)}\s*\("
    out = []
    for q in [q1, q2]:
        proc = run(["rg", "-n", "-S", "-m", str(max_hits), q, "."], cwd=repo)
        hits = [ln for ln in (proc.stdout or "").splitlines() if "/tests/" not in ln]
        out.extend(hits)
        if len(out) >= max_hits:
            break
    return out[:max_hits]


# ──────────────────────────────────────────────────────────────────────────────
# Prompt builder (USEFUL TESTS charter)
# ──────────────────────────────────────────────────────────────────────────────

USEFUL_CHARTER = """
USEFUL TESTS CHARTER (follow strictly)
- Emphasize behaviour & contracts over line-count coverage.
- Arrange–Act–Assert; minimal inputs; deterministic; no network; no external I/O (except tmp_path).
- Import real modules (no sys.path hacks; no test-local package shadowing).
- One 'Act' per test; use pytest.mark.parametrize for multiple obvious cases.
- Verify clear invariants: return shape/types, idempotence, order-agnostic equality when appropriate, error handling.
- For Polars: prefer 'from polars.testing import assert_frame_equal, assert_series_equal';
  compare deterministically (sort rows/columns if order is unspecified).
- Avoid brittle asserts on string repr/float formatting; assert semantics.
- If the code requires time/rand/env, inject/freeze via monkeypatch.
- Do not add new dependencies unless '--allow-hypothesis' is specified.
"""

ACCEPTANCE = """
ACCEPTANCE
- Edit ONLY the single test file listed in '{targets_file}' (create if missing).
- Tests collect: 'pytest --collect-only {test_rel}' succeeds.
- Each added test has at least one meaningful assertion (or pytest.raises) and is deterministic.
- No unconditional pytest.skip(); use skipif with a real condition if necessary.
- No production code is modified; diffs are limited to the single test file.
"""


def build_prompt(
    repo: Path,
    test_rel: str,
    targets_file: str,
    group: List[TargetFn],
    allow_hypothesis: bool,
) -> str:
    blocks = []
    for t in group:
        src_rel = (
            t.src_file.relative_to(repo).as_posix()
            if str(t.src_file).startswith(str(repo))
            else str(t.src_file)
        )
        excerpt = slice_source(t.src_file, t.func.lineno, t.func.end_lineno, 160)
        usages = grep_usages(repo, t.import_path, t.func.name, max_hits=5)
        doc_note = "Docstring present" if t.func.has_docstring else "No docstring"
        usages_str = "\n".join(usages) if usages else "(none found)"
        blocks.append(
            textwrap.dedent(
                f"""
        ─────────────────────────────────────────────────────────────
        MODULE: {t.import_path}   FILE: {src_rel}
        FUNCTION: {t.func.qualname}  (lines {t.func.lineno}-{t.func.end_lineno})
        HINTS: score={t.score} signals={','.join(t.signals) or '-'}  |  {doc_note}  |  complexity={t.func.complexity}
        SOURCE EXCERPT:
        {excerpt}

        SAMPLE USAGES FOUND (best-effort; context only):
        {textwrap.indent(usages_str, prefix="  ")}
        """
            ).strip()
        )

    charter = USEFUL_CHARTER
    if allow_hypothesis:
        charter += "\n- Property tests allowed (Hypothesis): only when they add clear signal and remain fast."

    blocks_str = "\n\n".join(blocks)
    charter_str = charter.strip()
    acceptance_str = ACCEPTANCE.format(
        targets_file=targets_file, test_rel=test_rel
    ).strip()
    return textwrap.dedent(
        f"""
EDIT THIS SINGLE TEST FILE (and only this file):
- {test_rel}
- The same path is written to "{targets_file}".

GOAL
Write *useful*, minimal tests that validate real behaviour and contracts of the
functions listed below. Avoid noise. Prefer a 'golden path', a boundary/edge case,
and one negative/validation case where appropriate. Keep tests short.

TARGETS
{blocks_str}

{charter_str}

{acceptance_str}

IMPLEMENTATION NOTES
- Import path is given per module (e.g., 'from {group[0].import_path} import <fn>').
- If a function expects DataFrames (Polars), build tiny deterministic frames and assert schema  values with assert_frame_equal.
- For UI-dependent code, avoid UI; stub session context and required config via monkeypatch.
- Prefer parametrization over loops/conditionals in tests. Keep one Act per test.
"""
    ).strip()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main():
    naming = get_naming_params()
    ap = argparse.ArgumentParser(
        description="Generate USEFUL tests (risk/value-based) with Codex."
    )
    ap.add_argument(
        "--repo", default=None, help="Repo root; default: parent of tools/ (auto)."
    )
    ap.add_argument(
        "--paths-from",
        default="modules_to_target.txt",
        help="Relative to repo root. Dirs/files/globs, one per line.",
    )
    ap.add_argument(
        "--strategy",
        nargs="*",
        default=["changed", "public", "complex"],
        choices=["changed", "public", "complex", "explicit", "all"],
        help="Selection strategies (combine freely). 'all' means everything in --paths-from pool.",
    )
    ap.add_argument(
        "--since",
        default=None,
        help="Git since (e.g., '2025-08-01' or '14.days.ago'). Used by 'changed'.",
    )
    ap.add_argument(
        "--commit-range",
        default=None,
        help="Git commit range (e.g., 'origin/main...HEAD'). Used by 'changed'.",
    )
    ap.add_argument(
        "--functions-from",
        default="functions_to_test.txt",
        help="File listing <module>:<qualname>, one per line, for 'explicit' strategy.",
    )
    ap.add_argument(
        "--exclude",
        nargs="*",
        default=sorted(DEFAULT_EXCLUDES),
        help="Folder names to ignore anywhere in the path.",
    )
    ap.add_argument(
        "--include-private",
        action="store_true",
        help="Allow private functions (starting with '_').",
    )
    ap.add_argument(
        "--focus", default=None, help="Regex to filter file paths or qualnames."
    )
    ap.add_argument(
        "--max-per-module", type=int, default=3, help="Max functions per module."
    )
    ap.add_argument(
        "--limit-modules", type=int, default=0, help="Max modules to process (0 = all)."
    )
    ap.add_argument(
        "--targets-file",
        default=".codex_test_targets.txt",
        help="Write the single test path here for each Codex call.",
    )
    ap.add_argument(
        "--codex", default="codex", help="Codex CLI binary (default: codex)."
    )
    ap.add_argument(
        "--model",
        default=naming["gpt5ThinkingMini"],
        help=(
            "Model id (default: "
            f"{naming['gpt5ThinkingMini']} from config; use --model for custom model)"
        ),
    )
    ap.add_argument(
        "--allow-hypothesis",
        action="store_true",
        help="Permit Hypothesis/property tests.",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="Build prompts; do not invoke Codex."
    )
    ap.add_argument(
        "--git-commit",
        action="store_true",
        help="git add -A && git commit once at end.",
    )
    ap.add_argument(
        "--git-message", default="codex: add useful tests", help="Commit message."
    )
    # --- resume controls ---
    ap.add_argument(
        "--resume", action="store_true", help="Skip test files recorded in --done-file."
    )
    ap.add_argument(
        "--done-file",
        default=".codex_tests_done.txt",
        help="Path to a file where each successfully generated test path is recorded.",
    )
    ap.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip a target if the test file already contains a real test (e.g. 'def test_').",
    )
    ap.add_argument(
        "--start-from",
        default=None,
        help="Optional: relative test path to start from (skips earlier targets).",
    )
    args = ap.parse_args()

    # repo root = parent of tools/ by default
    repo = Path(args.repo).resolve() if args.repo else repo_root_from_tools()
    if not repo.exists():
        raise SystemExit(f"Repo path not found: {repo}")
    src_root = get_src_root(repo)

    paths_from = repo / args.paths_from
    excluded = set(args.exclude)

    pool = list_source_pool(repo, paths_from, excluded)
    if not pool:
        raise SystemExit(
            "No Python source files found under the listed paths (after exclusions)."
        )

    # Strategies
    strategy_changed = "changed" in args.strategy
    strategy_public = "public" in args.strategy or "all" in args.strategy
    strategy_complex = "complex" in args.strategy or "all" in args.strategy
    strategy_explicit = "explicit" in args.strategy

    explicit_map: Dict[Path, List[str]] = {}
    if strategy_explicit:
        explicit_map = explicit_functions_from(
            repo, src_root, (repo / args.functions_from)
        )

    focus_rx = re.compile(args.focus) if args.focus else None

    # Rank for usefulness
    targets = rank_functions_for_usefulness(
        repo=repo,
        src_root=src_root,
        pool=pool,
        strategy_changed=strategy_changed,
        strategy_public=strategy_public,
        strategy_complex=strategy_complex,
        explicit_map=explicit_map,
        since=args.since,
        commit_range=args.commit_range,
        include_private=args.include_private,
        focus_regex=focus_rx,
        max_per_module=args.max_per_module,
    )
    if not targets:
        raise SystemExit(
            "No functions matched the usefulness selection criteria. "
            "Try adjusting --strategy, --since/--commit-range, or --focus."
        )

    # Group by test file, keep one codex exec per file
    by_test: Dict[Path, List[TargetFn]] = {}
    for t in targets:
        by_test.setdefault(t.test_file, []).append(t)

    items = list(by_test.items())
    if args.limit_modules > 0:
        items = items[: args.limit_modules]

    # ---------- resume / filtering ----------
    done_path = repo / args.done_file
    done_set: set[str] = set()
    if args.resume and done_path.exists():
        done_set = {
            ln.strip()
            for ln in done_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        }

    def has_real_tests(p: Path) -> bool:
        try:
            s = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return False
        # Heuristic: treat files that already have real tests as done
        return "def test_" in s or "pytest.mark.parametrize" in s or "assert " in s

    start_from_rel = args.start_from.replace("\\", "/") if args.start_from else None
    started = start_from_rel is None
    filtered: list[tuple[Path, list[TargetFn]]] = []
    for tf, grp in items:
        rel = tf.relative_to(repo).as_posix()
        # start-from gate
        if not started:
            if rel == start_from_rel:
                started = True
            else:
                continue
        # done-file gate
        if args.resume and rel in done_set:
            continue
        # existing-test-content gate
        if args.skip_existing and tf.exists() and has_real_tests(tf):
            if args.resume:
                done_set.add(rel)  # treat as done from now on
            continue
        filtered.append((tf, grp))
    items = filtered

    codex_bin = resolve_codex_binary(args.codex)
    if not codex_bin:
        raise SystemExit(
            "Could not find Codex CLI 'codex'. Install with: npm i -g @openai/codex"
        )

    # Build the base codex command
    cmd_base = [codex_bin, "exec"]
    if args.model:
        cmd_base += ["--model", args.model]
    # Append configuration flags (do not reassign cmd_base)
    cmd_base += [
        "--config",
        "approval_policy=never",
        "--config",
        "sandbox_mode=danger-full-access",
        "--config",
        "model_reasoning_effort=high",
    ]

    print(f"[codex-generate] Repo: {repo}")
    print(f"[codex-generate] Source modules selected: {len(items)}")
    print(
        f"[codex-generate] Writing single-target path into: {(repo / args.targets_file)}"
    )

    for i, (test_file, group) in enumerate(items, 1):
        test_rel = test_file.relative_to(repo).as_posix()
        print(
            f"[codex-generate] ({i}/{len(items)}) target test file: {test_rel}  (functions: {len(group)})"
        )

        ensure_file(test_file)
        (repo / args.targets_file).write_text(test_rel + "\n", encoding="utf-8")

        prompt = build_prompt(
            repo,
            test_rel,
            args.targets_file,
            group,
            allow_hypothesis=args.allow_hypothesis,
        )
        if args.dry_run:
            print("  [dry-run] Prompt (truncated):")
            print(textwrap.shorten(prompt, width=1200, placeholder=" …"))
            continue

        proc = subprocess.run(
            cmd_base + [prompt], cwd=str(repo), text=True, capture_output=True
        )
        if proc.returncode != 0:
            print(f"[codex-generate] Codex non-zero for {test_rel}:")
            print(proc.stdout or proc.stderr)
        else:
            # Mark as completed (append this test file path to the done file)
            try:
                with (repo / args.done_file).open("a", encoding="utf-8") as df:
                    df.write(test_rel + "\n")
            except Exception:
                pass

    if args.git_commit:
        subprocess.run(["git", "add", "-A"], cwd=str(repo))
        msg = f"{args.git_message} [{len(items)} modules]"
        subprocess.run(["git", "commit", "-m", msg], cwd=str(repo))
        print("[codex-generate] committed.")


if __name__ == "__main__":
    main()
