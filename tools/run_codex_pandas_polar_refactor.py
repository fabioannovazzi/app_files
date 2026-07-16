#!/usr/bin/env python3
"""
run_codex_refactor.py  (WSL/Ubuntu optimized; modules_to_scan-only)

Refactors pandas-style leftovers (.loc[], df[mask], direct column assignment, etc.) to Polars.

- Looks ONLY into paths listed in --paths-from (default: modules_to_scan.txt).
- With --all: include EVERY *.py under those listed subfolders (recursively).
- Without --all: include only files that match pandas-style idioms.
- Detects: .loc[], .iloc[], boolean df[...], multi-line masks, named masks (df[mask]),
           direct column assignment df[col] = ..., .assign(), .where/.mask, .query,
           .merge, pd.concat, pivot_table, melt, value_counts, sort_values,
           .drop_duplicates, .at/.iat, .apply(axis=1), .dt.*, .str.*,
           set_index/reset_index, .drop, .fillna, .astype.
- Ignores strings/comments to reduce false positives.
- Excludes virtualenvs/vendor dirs by default.
- Embeds exact target list in the Codex prompt.
- Assumes POSIX shell (WSL/Ubuntu). Requires ripgrep (rg).

Usage (from repo root, in WSL/Ubuntu):

./run_codex_refactor.py \
  --paths-from modules_to_scan.txt \
  --test \
  --git-commit \
  --git-message "codex: Pandas→Polars refactor"

./run_codex_refactor.py \
  --paths-from modules_to_scan.txt \
  --test \
  --all \
  --git-commit \
  --git-message "codex: Pandas→Polars refactor"

./run_codex_refactor.py \
  --paths-from modules_to_scan.txt \
  --git-commit \
  --git-message "codex: Pandas→Polars refactor"

  ./run_codex_refactor.py \
  --paths-from modules_to_scan.txt \
  --all \
  --git-commit \
  --git-message "codex: Pandas→Polars refactor"

cd /path/to/app_files
source .venv/bin/activate
echo 'alias actapp="cd /path/to/your/repo && source .venv/bin/activate"' >> ~/.bashrc
source ~/.bashrc
actapp
Auto-activate when you enter the repo (optional, simple)
Append this to ~/.bashrc:

bash
Copy
Edit
# auto-activate .venv when cd'ing into a directory that has it
cd() {
  builtin cd "$@" || return
  if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
  fi
}
"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import tokenize as tkn
from pathlib import Path

from modules.utilities.config import get_naming_params

logger = logging.getLogger(__name__)

# ──────────────────────────────
# Regex patterns for pandas hints
# ──────────────────────────────
LOC_RE = re.compile(r"\.loc\s*\[")
ILOC_RE = re.compile(r"\.iloc\s*\[")

# Boolean bracket filters, spanning multiple lines
BOOLEAN_INDEX_RE = re.compile(
    r"\b[A-Za-z_]\w*\s*\[[^]]*(==|!=|>=|<=|>|<|&|\||~)[^]]*\]", re.S
)

# Named mask indexing: df[mask]
MASK_VAR_INDEX_RE = re.compile(r"\b[A-Za-z_]\w*\s*\[\s*[A-Za-z_]\w*\s*\]", re.S)

# Direct column assignment: df[col] = ... (RHS referencing same df[...] somewhere)
COL_ASSIGN_RE = re.compile(
    r"""\b([A-Za-z_]\w*)\s*\[\s*(?:['"][^'"]+['"]|[A-Za-z_]\w*)\s*\]\s*=\s*.+?\b\1\s*\[\s*(?:['"][^'"]+['"]|[A-Za-z_]\w*)\s*\]""",
    re.S,
)

# Other common pandas idioms (high-signal markers)
ASSIGN_FUNC_RE = re.compile(r"\.assign\s*\(")
WHERE_MASK_RE = re.compile(r"\.(where|mask)\s*\(")
QUERY_RE = re.compile(r"\.query\s*\(")
AT_IAT_RE = re.compile(r"\.(at|iat)\s*\[")
SORT_VALUES_RE = re.compile(r"\.sort_values\s*\(")
VALUE_COUNTS_RE = re.compile(r"\.value_counts\s*\(")
DROP_DUP_RE = re.compile(r"\.drop_duplicates\s*\(")
MERGE_RE = re.compile(r"\.merge\s*\(")
PD_CONCAT_RE = re.compile(r"\bpd\.concat\s*\(")
PIVOT_TABLE_RE = re.compile(r"\.pivot_table\s*\(")
MELT_RE = re.compile(r"\.melt\s*\(")
APPLY_AXIS1_RE = re.compile(r"\.apply\s*\(\s*lambda\b.*?axis\s*=\s*1", re.S)
DT_ACCESSOR_RE = re.compile(r"\.dt\.")
STR_ACCESSOR_RE = re.compile(r"\.str\.")
SET_RESET_INDEX_RE = re.compile(r"\.(set_index|reset_index)\s*\(")
DROP_RE = re.compile(r"\.drop\s*\(")
FILLNA_RE = re.compile(r"\.fillna\s*\(")
ASTYPE_RE = re.compile(r"\.astype\s*\(")

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
    except Exception as e:
        logger.warning("Tokenization failed for %s: %s", path, e)
        return path.read_text(encoding="utf-8", errors="ignore")


def should_skip(path: Path, repo: Path, excluded: set[str]) -> bool:
    rel = path.relative_to(repo)
    return any(part in excluded for part in rel.parts)


def is_candidate_file(path: Path) -> bool:
    """No pandas import requirement — we’re hunting for 'lonely' leftovers."""
    code = strip_strings_and_comments(path)
    tests = [
        LOC_RE,
        ILOC_RE,
        BOOLEAN_INDEX_RE,
        MASK_VAR_INDEX_RE,
        COL_ASSIGN_RE,
        ASSIGN_FUNC_RE,
        WHERE_MASK_RE,
        QUERY_RE,
        AT_IAT_RE,
        SORT_VALUES_RE,
        VALUE_COUNTS_RE,
        DROP_DUP_RE,
        MERGE_RE,
        PD_CONCAT_RE,
        PIVOT_TABLE_RE,
        MELT_RE,
        APPLY_AXIS1_RE,
        DT_ACCESSOR_RE,
        STR_ACCESSOR_RE,
        SET_RESET_INDEX_RE,
        DROP_RE,
        FILLNA_RE,
        ASTYPE_RE,
    ]
    return any(rx.search(code) for rx in tests)


def build_prompt(inline_paths: list[str], targets_file: str) -> str:
    """Build the Codex instruction prompt with concrete conversions."""
    paths_block = "\n".join(f"- {p}" for p in inline_paths)
    return f"""
Refactor pandas leftovers (.loc[], df[mask], direct column assignment, etc.) → Polars **only** in the files below and in "{targets_file}".

FILES TO EDIT (relative to repo root):
{paths_block}

GOAL
- Replace pandas-style row filters, column assignments, and common idioms with idiomatic Polars.
- Keep changes minimal and behavior-preserving. No unrelated refactors.

SCOPE OF CHANGES
1) Row filtering
   - `df[mask]` or `df.loc[mask]` → `df.filter(<pl-expr>)`
   - Build masks with `pl.col("col") <op> value`; combine via `&` / `|` / `~` with parentheses.
   - Examples:
     * `df[df["a"] > 0]` → `df.filter(pl.col("a") > 0)`
     * `df[(df.a == 3) & df.b.isin(L)]` → `df.filter((pl.col("a") == 3) & pl.col("b").is_in(L))`

2) Conditional updates (via .loc or boolean assignment)
   - `df.loc[mask, "c"] = expr` →
     `df.with_columns(pl.when(<mask-expr>).then(<expr-pl>).otherwise(pl.col("c")).alias("c"))`
   - Multiple columns: pass a list of aliases in `with_columns([...])`.

3) Direct column assignment
   - `df[col] = <expr possibly using df[...]>` →
     `df.with_columns((<pl-expr>).alias(col))`

4) Common pandas helpers → Polars
   - `.isin(seq)` → `pl.col("c").is_in(seq)`
   - `.between(lo, hi)` → `pl.col("c").is_between(lo, hi, closed="both")`
   - `.isna()` / `.notna()` → `.is_null()` / `.is_not_null()`
   - `.str.contains(pat, regex=...)` → `pl.col("s").str.contains(pat, literal=not regex)`
   - `.str.len()` → `.str.len_chars()` (or `.str.len_bytes()`)
   - `.dt.*` → Polars `.dt` namespace (e.g. `.dt.year()`)

5) Data shaping
   - `.merge(...)` → `df.join(other, on=..., how=...)`
   - `pd.concat([...], axis=0|1)` → `pl.concat([...], how="vertical"|"horizontal")`
   - `.pivot_table(...)` → `df.pivot(values=..., index=..., columns=..., aggregate_function=...)`
   - `.melt(...)` → `df.melt(id_vars=..., value_vars=..., variable_name=..., value_name=...)`
   - `.value_counts()` → `pl.col(x).value_counts()` or `df.group_by(x).len()`
   - `.drop_duplicates(subset=..., keep="first")` → `df.unique(subset=[...], keep="first")`
   - `.sort_values(by=..., ascending=...)` → `df.sort(by=[...], descending=[...])`
   - `.drop(..., axis=1)` → `df.drop([...])` or `df.select(pl.all().exclude([...]))`

6) Index handling
   - If pandas index is used, materialize it: `df = df.with_row_count("index")` and compare via `"index"`.
   - Avoid hidden index semantics.

7) Execution model
   - Keep existing eager vs lazy model. Don’t switch unless necessary.

8) Types & nulls
   - Preserve dtype/NA behavior; add explicit `cast` where pandas coerced types.
   - Use `fill_null(...)` to mirror `fillna(...)`.
   - Be careful with nullable integers when introducing nulls.

9) Row-wise apply
   - Replace `.apply(axis=1)` with vectorized Polars expressions when possible.
   - If not feasible, leave a clear TODO rather than adding slow row-wise UDFs.

10) Imports & cleanup
   - Ensure `import polars as pl` exists.
   - Remove unused `pandas` imports if present.
   - Keep variable names, function signatures, and external behavior unchanged.

AMBIGUITY RULE
- If a `df[mask]` or `.loc[...]` pattern appears and the object’s type is ambiguous, assume pandas-like semantics and convert to the closest Polars equivalent. Prefer `.filter(...)` for row masks and `.select(...)` for column masks.

CONSTRAINTS
- Edit **only** the files listed above / in "{targets_file}".
- Do **not** rename/move files or add dependencies.
- Keep diffs focused on pandas→Polars conversion described here.

ACCEPTANCE
- Edited files import without errors.
- Filters/assignments behave the same on representative inputs (nulls, strings, dates).
- Clear, parenthesized expressions; minimal diffs.
""".strip()


def resolve_codex_binary(codex_arg: str) -> str | None:
    cand = shutil.which(codex_arg)
    if cand:
        return cand
    return None


def require_shell_deps_or_die():
    """Codex often shells out to ripgrep for search. Ensure it's present on POSIX."""
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
        description="Refactor pandas leftovers → Polars (modules_to_scan-only)."
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
        help="Include all *.py under the listed subfolders/patterns (ignore pandas-heuristic detector).",
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
        default="codex: pandas→Polars refactor",
        help="Commit message to use with --git-commit.",
    )

    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists():
        raise SystemExit(f"Repo path not found: {repo}")

    # Require the list file to exist
    list_file = repo / args.paths_from
    if not list_file.exists():
        raise SystemExit(f"--paths-from file not found: {list_file}")

    excluded = set(args.exclude)

    # Build patterns ONLY from --paths-from (subfolders/files/globs)
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
                and p.name != "__init__.py"  # ← add this
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
            else "No pandas-style patterns found in the listed subfolders."
        )

    # TEST mode narrowing (must still be inside the listed pool)
    if args.test:
        if args.test_file:
            tf = (repo / args.test_file).resolve()
            if tf not in pool_set:
                raise SystemExit(
                    f"--test-file must be within the listed subfolders/patterns: {tf}"
                )
            if tf.name == "__init__.py":  # ← add this
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

    #
    # Iterate over each target file, invoking Codex on one file at a time.  The legacy
    # implementation committed after each file which could result in a flurry of
    # small, hard‑to‑review commits.  We still process files sequentially so
    # Codex operates on a single target at a time, but we defer any Git commits
    # until after the entire loop completes.  See the block after this loop for
    # commit handling.
    for i, tr in enumerate(targets_rel, 1):
        # write a single-file targets file (the prompt references this filename)
        (repo / args.targets_file).write_text(tr + "\n", encoding="utf-8")

        # build a prompt for ONE file
        prompt = build_prompt([tr], args.targets_file)
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

        # Note: we intentionally avoid committing after each file.  A global
        # commit will be performed once all files have been processed (see
        # below).  This prevents a proliferation of tiny commits and makes it
        # easier to review the overall refactor.  If you still prefer per‑file
        # commits, you can reintroduce similar logic here or add a separate
        # command‑line flag.

    # After processing all targets we optionally perform a single Git commit.
    # Doing a single commit at the end reduces commit noise and makes it
    # simpler to review changes in aggregate.  If --git-commit is not set
    # nothing will be committed, leaving it up to the caller to inspect and
    # commit manually.
    if args.git_commit:
        # Stage all changes except ignored files.  Because .codex_targets.txt
        # should be listed in .gitignore, it will not be staged.  Git will
        # silently ignore untracked/ignored files unless forced with -f.
        subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)

        # Use a generic message summarising the number of files processed.  We
        # avoid including specific filenames here because there may be many.
        summary_msg = f"{args.git_message} [{len(targets_rel)} files]"
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
            print(f"[codex-wrapper] Committed all changes in one commit as {commit}")
        else:
            # It's possible there were no staged changes.  Git will emit a
            # message like "nothing to commit" in this case.  Surface that
            # output to the user for clarity.
            print("[codex-wrapper] No commit performed (likely no changes). Git said:")
            print(commit_proc.stdout or commit_proc.stderr)


if __name__ == "__main__":
    main()
