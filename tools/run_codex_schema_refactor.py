#!/usr/bin/env python3
"""
run_codex_schema_refactor.py  (WSL/Ubuntu optimized; modules_to_scan-only)

Enforce guideline:
| Use `get_schema_and_column_names(df)` to retrieve column names and schema |
| Avoid inconsistent access via `df.columns` or `df.schema` |

- Looks ONLY into paths listed in --paths-from (default: modules_to_scan.txt).
- With --all: include EVERY *.py under those listed subfolders (recursively).
- Without --all: include only files that likely misuse `.columns` / `.schema` properties.
- Ignores strings/comments to reduce false positives.
- Excludes virtualenvs/vendor dirs by default.
- Runs Codex CLI to safely edit files with minimal, behavior-preserving diffs.

Usage (from repo root, in WSL/Ubuntu):

./run_codex_schema_refactor.py \
  --paths-from modules_to_scan.txt \
  --test \
  --git-commit \
  --git-message "codex: enforce schema/columns accessor guideline"

./run_codex_schema_refactor.py \
  --paths-from modules_to_scan.txt \
  --all \
  --git-commit \
  --git-message "codex: enforce schema/columns accessor guideline"

Common options:

  --import-stmt "from utils.schema_utils import get_schema_and_column_names"
     Ensures this import exists in edited files (inserted if missing).

  --columns-index 0
     Index (0 or 1) for the columns value in the tuple returned by
     get_schema_and_column_names(df). Default 0 ⇒ (columns, schema).

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
# Match attribute property access `.columns` / `.schema` not followed by '('
# to avoid e.g. `pyarrow.schema(...)` function calls.
PROP_COLUMNS_RE = re.compile(r"\.\s*columns\b(?!\s*\()")
PROP_SCHEMA_RE = re.compile(r"\.\s*schema\b(?!\s*\()")

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
    """Detect likely misuse of `.columns` / `.schema`."""
    code = strip_strings_and_comments(path)
    return bool(PROP_COLUMNS_RE.search(code) or PROP_SCHEMA_RE.search(code))


def build_prompt(
    inline_paths: list[str],
    targets_file: str,
    columns_index: int,
    import_stmt: str | None,
) -> str:
    """
    Build the Codex instruction prompt with concrete conversions.
    columns_index: 0 if get_schema_and_column_names(df) returns (columns, schema),
                   1 if it returns (schema, columns). Used for examples only;
                   Codex should hoist into local names rather than inline tuple indexing when possible.
    """
    paths_block = "\n".join(f"- {p}" for p in inline_paths)

    # Guidance for indexing used in examples and for unhoisted single uses
    col_idx = columns_index
    sch_idx = 1 - columns_index

    import_clause = ""
    if import_stmt:
        import_clause = f"""
10) Imports
   - Ensure the following import exists at top-level (after stdlib imports, before local):\n
     {import_stmt}
   - Insert it if missing, without duplicating existing imports.
"""

    return f"""
Enforce the guideline below **only** in the file listed and in "{targets_file}".

GUIDELINE
| Use `get_schema_and_column_names(df)` to retrieve column names and schema |
| Avoid inconsistent access via `df.columns` or `df.schema` |

FILES TO EDIT (relative to repo root):
{paths_block}

WHAT TO CHANGE
1) Replace property access to `.columns` and `.schema` on Polars DataFrame/LazyFrame
   (or code that clearly treats the object as a Polars frame) with the tuple returned
   by `get_schema_and_column_names(obj)`.

2) Prefer **hoisting a single call** per variable when both columns or schema are used
   within the same logical scope:
   - BEFORE:
       cols = df.columns
       if "x" in df.columns:
           ...
       t = df.schema.get("a")
   - AFTER:
       cols, schema = get_schema_and_column_names(df)
       if "x" in cols:
           ...
       t = schema.get("a")

   If only one of them is used once, doing a small inline replacement is acceptable.

3) Inline replacement examples (for single use sites):
   - `df.columns`  → `get_schema_and_column_names(df)[{col_idx}]`
   - `df.schema`   → `get_schema_and_column_names(df)[{sch_idx}]`

4) Respect existing variable names:
   - If the original code uses variables like `columns`, `schema`, or `colnames`, reuse those.
   - If introducing new locals, use `cols` and `schema`.
   - Avoid shadowing if names already exist in the visible scope.

5) Scope & correctness:
   - DO NOT modify occurrences inside strings, comments, or dead code blocks.
   - DO NOT change unrelated logic.
   - Ignore function calls like `pyarrow.schema(...)` — this is a different API.
   - Only refactor attribute property access `.columns` / `.schema` (no parentheses).
   - Keep lazy vs eager mode unchanged.

6) Idempotency:
   - Running this script again should result in no further diffs: avoid rewriting
     `get_schema_and_column_names(df)[...]` again, and don’t duplicate variables.

7) Type semantics:
   - Assume `get_schema_and_column_names(df)` returns a pair `(columns, schema)` when `--columns-index 0`,
     or `(schema, columns)` when `--columns-index 1`. Use this to select the correct index in any inline
     replacements. Prefer hoisting to named locals to avoid ambiguity.

8) Minimal, clear diffs:
   - Parenthesize complex expressions when needed for clarity.
   - Preserve function signatures, return values, and module interfaces.

9) Keep imports and formatting clean (respect existing import/grouping style).{import_clause}

AMBIGUITY RULE
- If static type is unclear, but the code uses the attribute `.columns` or `.schema` in a way consistent
  with a Polars DataFrame/LazyFrame (e.g., membership checks, iteration, dict-like access), perform the refactor.
- Skip obvious non-Polars cases (e.g., `pyarrow.schema(...)`, Pydantic model `.schema()`, SQLAlchemy `.schema`).

ACCEPTANCE
- Edited file imports without errors (assuming `get_schema_and_column_names` is reachable).
- Repeated runs of this tool produce zero changes (idempotent).
- Warnings about inconsistent access are eliminated by removing `.columns` / `.schema` property reads.
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
        description="Refactor `.columns` / `.schema` to get_schema_and_column_names(df) (modules_to_scan-only)."
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
        help="Include all *.py under the listed subfolders/patterns (ignore heuristic detector).",
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
        default="codex: enforce schema/columns accessor guideline",
        help="Commit message to use with --git-commit.",
    )

    ap.add_argument(
        "--columns-index",
        type=int,
        choices=(0, 1),
        default=0,
        help="Index used for columns in get_schema_and_column_names(df) tuple (0: columns first [default], 1: columns second).",
    )
    ap.add_argument(
        "--import-stmt",
        default=None,
        help="Import statement to insert if missing, e.g. 'from utils.schema_utils import get_schema_and_column_names'.",
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
            else "No `.columns` / `.schema` usages found in the listed subfolders."
        )

    # TEST mode narrowing (must still be inside the listed pool)
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

    #
    # Iterate over each target file.  We avoid committing after each file to
    # prevent a proliferation of tiny commits.  A single commit will be
    # performed after all files have been processed.  See the block following
    # this loop for commit handling.
    for i, tr in enumerate(targets_rel, 1):
        # write a single-file targets file (the prompt references this filename)
        (repo / args.targets_file).write_text(tr + "\n", encoding="utf-8")

        # build a prompt for ONE file
        prompt = build_prompt(
            [tr], args.targets_file, args.columns_index, args.import_stmt
        )
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
        # commit will be performed once all files have been processed (see below).
        # This reduces commit noise and makes it easier to review changes in bulk.

    # After processing all target files we optionally perform a single Git
    # commit.  This summarises all changes into one commit and respects
    # .gitignore (so .codex_targets.txt will not be staged).  If
    # --git-commit is not supplied, no commit is made.
    if args.git_commit:
        # Stage all changes (respecting .gitignore)
        subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
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
            print("[codex-wrapper] No commit performed (likely no changes). Git said:")
            print(commit_proc.stdout or commit_proc.stderr)


if __name__ == "__main__":
    main()
