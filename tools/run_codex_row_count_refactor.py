#!/usr/bin/env python3
"""
run_codex_row_count_refactor.py  (WSL/Ubuntu optimized; modules_to_scan-only)

Enforce guideline:
| Use `get_row_count(df)` for row counts and `df.width` for column counts; avoid `len(df)`, `df.shape[0]`, and `len(df.columns)` |

- Looks ONLY into paths listed in --paths-from (default: modules_to_scan.txt).
- With --all: include EVERY *.py under those listed subfolders (recursively).
- Without --all: include only files that likely use `len(df)` or `df.shape[0]` or `len(... .columns)`.
- Ignores strings/comments to reduce false positives.
- Excludes virtualenvs/vendor dirs by default.
- Runs Codex CLI to safely edit files with minimal, behavior-preserving diffs.

Usage (from repo root, in WSL/Ubuntu):

./run_codex_row_count_refactor.py \
  --paths-from modules_to_scan.txt \
  --test \
  --git-commit \
  --git-message "codex: enforce get_row_count/df.width guideline"

./run_codex_row_count_refactor.py \
  --paths-from modules_to_scan.txt \
  --all \
  --git-commit \
  --git-message "codex: enforce get_row_count/df.width guideline"

Common options:

  --import-stmt "from modules.utilities.utils import get_row_count"
     Ensures this import exists in edited files (inserted if missing).

  --dry-run
     Print what would run, without invoking Codex.
"""
import argparse
import os
import re
import shutil
import subprocess
import tokenize as tkn
from pathlib import Path

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
# Regex patterns for candidate detection
# ──────────────────────────────
# Patterns for forbidden row/col count usage
LEN_DF_RE = re.compile(r"\blen\s*\(\s*df[A-Za-z0-9_]*\s*\)")
LEN_COLUMNS_RE = re.compile(r"\blen\s*\(\s*[^)]+?\.columns\s*\)")
SHAPE_ZERO_RE = re.compile(r"\.shape\s*\[\s*0\s*\]")
SHAPE_ONE_RE = re.compile(r"\.shape\s*\[\s*1\s*\]")


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


def is_candidate_file(path: Path) -> bool:
    """Detect usage of len(df), df.shape[0], or len(....columns)."""
    code = strip_strings_and_comments(path)
    return bool(
        LEN_DF_RE.search(code)
        or SHAPE_ZERO_RE.search(code)
        or LEN_COLUMNS_RE.search(code)
        or SHAPE_ONE_RE.search(code)
    )


def build_prompt(
    inline_paths: list[str], targets_file: str, import_stmt: str | None
) -> str:
    """Build the Codex instruction prompt for enforcing get_row_count/width usage."""
    paths_block = "\n".join(f"- {p}" for p in inline_paths)
    import_clause = ""
    if import_stmt:
        import_clause = f"""
6) Imports
   - Ensure the following import exists at top-level (after stdlib imports, before local):\n
     {import_stmt}
   - Insert it if missing, without duplicating existing imports.
"""
    return f"""
Enforce the guideline below **only** in the file listed and in "{targets_file}".

GUIDELINE
| Use `get_row_count(df)` for row counts and `df.width` for column counts; avoid `len(df)`, `df.shape[0]`, and `len(df.columns)` |

FILES TO EDIT (relative to repo root):
{paths_block}

WHAT TO CHANGE
1) Replace row count retrieval via Python's len() or DataFrame.shape[0] with `get_row_count(obj)`:
   - BEFORE:
       n_rows = len(df)
       if df.shape[0] > 100: ...
   - AFTER:
       n_rows = get_row_count(df)
       if get_row_count(df) > 100: ...
   Ensure correctness for both Polars DataFrame and LazyFrame objects.

2) Replace column count retrieval via len(df.columns) or DataFrame.shape[1] with the `width` property of the DataFrame:
   - BEFORE: num_cols = len(df.columns)
   - AFTER:  num_cols = df.width

3) Only apply these changes when the object in question is a Polars DataFrame or LazyFrame (or clearly treated as such). Do **not** modify len() calls on ordinary lists, strings, or other non-DataFrame objects.

4) Preserve existing logic and flow:
   - Do not introduce additional data materialization; use `get_row_count` as a direct replacement.
   - If the code uses the row count multiple times in close proximity, it's acceptable (but not required) to call get_row_count once and reuse the value to avoid duplicate computation.
   - Keep any conditional checks or loops functionally identical.

5) Scope & idempotency:
   - Do not alter occurrences inside strings, comments, or unrelated code.
   - Running this tool again should result in no further changes (avoid leaving any `len(df)` or `.shape[0]` usages, and do not re-wrap existing correct uses of get_row_count or df.width).

{import_clause}""".strip()


def resolve_codex_binary(codex_arg: str) -> str | None:
    cand = shutil.which(codex_arg)
    if cand:
        return cand
    return None


def require_shell_deps_or_die():
    """Ensure required shell dependencies are available (e.g., ripgrep)."""
    if os.name == "posix" and shutil.which("rg") is None:
        raise SystemExit(
            "ripgrep (rg) not found. Install it first:\n"
            "  sudo apt update && sudo apt install -y ripgrep\n"
        )


# ──────────────────────────────
# Main
# ──────────────────────────────
def main():
    naming = get_naming_params()
    ap = argparse.ArgumentParser(
        description="Refactor len(df)/df.shape to get_row_count(df) and len(df.columns) to df.width (modules_to_scan-only)."
    )
    ap.add_argument("--repo", default=".", help="Repo root (default: .)")
    ap.add_argument(
        "--paths-from",
        default="modules_to_scan.txt",
        help="Text file with one subfolder, file, or glob per line (e.g., modules/charting, modules/data/**/*.py). Lines starting with # are ignored.",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Include all *.py under the listed subfolders/patterns (ignore the heuristic detector).",
    )
    ap.add_argument(
        "--exclude",
        nargs="*",
        default=sorted(DEFAULT_EXCLUDES),
        help="Folder names to ignore anywhere in the path.",
    )
    ap.add_argument(
        "--targets-file",
        default=".codex_targets.txt",
        help="Filename to write the target list.",
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
        default="codex: enforce get_row_count/df.width guideline",
        help="Commit message to use with --git-commit.",
    )
    ap.add_argument(
        "--import-stmt",
        default=None,
        help="Import statement to insert if missing, e.g. 'from modules.utilities.utils import get_row_count'.",
    )
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists():
        raise SystemExit(f"Repo path not found: {repo}")
    list_file = repo / args.paths_from
    if not list_file.exists():
        raise SystemExit(f"--paths-from file not found: {list_file}")

    excluded = set(args.exclude)
    patterns: list[str] = []
    explicit_files: list[Path] = []
    for raw in list_file.read_text(encoding="utf-8").splitlines():
        s = raw.strip().replace("\\", "/")
        if not s or s.startswith("#"):
            continue
        p = repo / s
        if p.is_dir():
            patterns.append((Path(s).as_posix().rstrip("/") + "/**/*.py"))
        elif p.is_file() and p.suffix == ".py":
            explicit_files.append(p.resolve())
        else:
            # treat as a glob pattern relative to repo
            patterns.append(s)
    # Build pool of files from listed patterns + explicit files, honoring excludes
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
    # Choose candidates: --all = entire pool; else apply detector
    candidates = pool if args.all else [p for p in pool if is_candidate_file(p)]
    if not candidates:
        raise SystemExit(
            "No Python files matched the listed subfolders/patterns."
            if args.all
            else "No row/column count misuse found in the listed subfolders."
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
    # Exclude package marker files everywhere
    targets = [p for p in targets if p.name != "__init__.py"]
    if not targets:
        raise SystemExit("No eligible Python files (after excluding __init__.py).")

    # ONE FILE AT A TIME
    targets_rel = [Path(p).relative_to(repo).as_posix() for p in targets]

    codex_bin = resolve_codex_binary(args.codex)
    if not codex_bin:
        raise SystemExit(
            "Could not find Codex CLI 'codex'. Install with:\n"
            "  npm i -g @openai/codex\n"
        )
    if not args.dry_run:
        require_shell_deps_or_die()

    # Base command used for every file
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

    print(f"[codex-wrapper] Repo: {repo}")
    print(f"[codex-wrapper] Targets: {len(targets_rel)} file(s)")
    print(f"[codex-wrapper] List file: {(repo / args.targets_file)}")
    print(f"[codex-wrapper] Excluding folders: {', '.join(sorted(excluded))}")
    if targets_rel:
        print(f"[codex-wrapper] First target: {targets_rel[0]}")

    for i, tr in enumerate(targets_rel, 1):
        # write a single-file targets file (the prompt references this filename)
        (repo / args.targets_file).write_text(tr + "\n", encoding="utf-8")

        # build a prompt for ONE file
        prompt = build_prompt([tr], args.targets_file, args.import_stmt)
        cmd = cmd_base + [prompt]

        print(f"[codex-wrapper] ({i}/{len(targets_rel)}) Running Codex on: {tr}")
        if args.dry_run:
            print("  [dry-run] Would run:", " ".join(cmd))
            continue

        try:
            subprocess.run(cmd, cwd=str(repo), check=True)
        except subprocess.CalledProcessError as e:
            raise SystemExit(
                f"[codex-wrapper] Codex failed on {tr} ({e.returncode})\n"
                f"STDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
            )

        if args.git_commit:
            subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
            commit_proc = subprocess.run(
                ["git", "commit", "-m", f"{args.git_message} [{tr}]"],
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
                print(f"[codex-wrapper] Committed {tr} as {commit}")
            else:
                print(
                    f"[codex-wrapper] No commit for {tr} (likely no changes). Git said:"
                )
                print(commit_proc.stdout or commit_proc.stderr)


if __name__ == "__main__":
    main()
