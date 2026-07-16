#!/usr/bin/env python3
"""
run_codex_llm_wrapper_refactor.py  (WSL/Ubuntu optimized; modules_to_scan-only)

Enforce guidelines from section "LLM Wrapper Integration":
- Use the unified LLM wrapper (`llm_wrapper`) and query functions instead of direct OpenAI API calls.
- Initialize the LLM wrapper once and pass it through logic layers; do not call providers directly or multiple times.
- Use `modules.llm.model_router.query_llm_return_json` or `query_llm_return_text` for LLM calls, with appropriate `query_step`.

- Looks ONLY into paths listed in --paths-from (default: modules_to_scan.txt).
- With --all: include EVERY *.py under those subfolders.
- Without --all: include only files that likely use direct OpenAI API calls.
- Excludes strings/comments to reduce false positives.
- Excludes virtualenvs/vendor dirs.
- Runs Codex CLI to refactor code to use the common LLM wrapper approach.

Usage (from repo root):

./run_codex_llm_wrapper_refactor.py \
  --paths-from modules_to_scan.txt \
  --test \
  --git-commit \
  --git-message "codex: enforce llm wrapper integration guidelines"

./run_codex_llm_wrapper_refactor.py \
  --paths-from modules_to_scan.txt \
  --all \
  --git-commit \
  --git-message "codex: enforce llm wrapper integration guidelines"

Common options:

  --import-modelrouter "from modules.llm import model_router"
     Use a custom import statement for the model_router if needed (default inserts 'from modules.llm import model_router').

  --dry-run
     Print targets and prompts without running Codex.
"""

import argparse
import os
import re
import shutil
import subprocess
import tokenize as tkn
from pathlib import Path

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
# Regex patterns for LLM direct usage detection
# ──────────────────────────────
# Detect calls to get_openai_client() or direct .create calls
LLM_CLIENT_CALL_RE = re.compile(r"\bget_openai_client\s*\(")
OPENAI_CREATE_RE = re.compile(r"\.chat\.(completions|completion)\.create\s*\(")


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
    """Detect usage of direct OpenAI client calls."""
    code = strip_strings_and_comments(path)
    # Skip files that only define clients (no actual usage outside definitions)
    if "def get_openai_client" in code:
        # likely the llm_client module; skip it
        return False
    return bool(LLM_CLIENT_CALL_RE.search(code) or OPENAI_CREATE_RE.search(code))


def build_prompt(
    inline_paths: list[str], targets_file: str, modelrouter_import: str | None
) -> str:
    """Build the Codex instruction prompt to refactor direct LLM calls to use llm_wrapper and query functions."""
    paths_block = "\n".join(f"- {p}" for p in inline_paths)
    import_clause = ""
    if modelrouter_import:
        import_clause = f"""
7) Imports
   - Ensure the following import is present at top-level (after other imports):\n
     {modelrouter_import}
   - Insert it if missing (without duplicating existing imports).
"""
    return f"""
Enforce the guideline below **only** in the file listed and in "{targets_file}".

GUIDELINE
| Standardize LLM calls via a single wrapper: initialise once with `init_llm_wrapper`, pass the `llm_wrapper` through layers, and use `query_llm_return_json`/`query_llm_return_text` for calling models (mapped via `select_provider`) instead of direct API calls. |

FILES TO EDIT (relative to repo root):
{paths_block}

WHAT TO CHANGE
1) Remove direct usage of OpenAI clients. Instead, use the unified LLM interface:
   - Do not call `get_openai_client()` or use its returned client object to send requests.
   - Use `modules.llm.model_router.query_llm_return_text` or `query_llm_return_json` to send prompts via the `llm_wrapper`.
   - Ensure an `llm_wrapper` is available in this context:
       * In UI code, call `init_llm_wrapper(\"\")` once (if not already done) and get `llm_wrapper` from the session context.
       * In logic functions, accept an `llm_wrapper` parameter (passed down from the UI) rather than calling `get_*_client()` internally.

2) Modify function signatures and calls if needed to pass `llm_wrapper`:
   - If a function currently obtains an LLM client internally, add an `llm_wrapper` parameter to that function and adjust any internal calls to use it.
   - Update calls to that function (in the same file) to pass the `llm_wrapper` along.
   - Do **not** call `init_llm_wrapper` inside lower-level functions; assume the wrapper is initialized at the top-level and provided.

3) Use the appropriate query function for the response type:
   - If the code expects a JSON/dict result, use `query_llm_return_json(llm_wrapper, query_step, system_prompt, user_prompt, tools=..., tool_choice=...)`.
   - If a plain text is needed, use `query_llm_return_text(...)` similarly.
   - Break down any composed prompt into `system_prompt` (e.g., instructions) and `user_prompt` (main query) if applicable. If there's no distinct system message, use an empty string for system_prompt.

4) Determine the correct `query_step` for each call:
   - Identify what kind of operation or prompt is being made (e.g., summarization, question answering, data correction). Use an existing query_step key from `modules.utilities.config.select_provider` if one matches the purpose.
   - If no existing query_step is suitable, introduce a specific query_step for the feature instead of reusing a retired legacy key.

5) Remove any hard-coded model or provider references:
   - Eliminate usage of literal model names (e.g., "gpt-4") or provider strings. The `select_provider(query_step)` inside `query_llm_return_*` will choose the appropriate model and provider.
   - If the code sets up special parameters (like temperature, or tool usage), pass them via the query function arguments if supported, otherwise omit or set them to defaults consistent with the unified approach.

6) Clean up:
   - Delete unused imports of `openai` or its exceptions if those calls are removed.
   - Remove any now-unused helper functions or client initializations.
   - Ensure any status messages or logging around the LLM call remain meaningful (e.g., use `ui.caption` or logging around query_llm_return if needed).

{import_clause}
ACCEPTANCE
- The code uses `query_llm_return_text/json` with an available `llm_wrapper` instead of direct API calls.
- Functions that perform LLM operations have `llm_wrapper` passed in rather than creating clients internally.
- No direct OpenAI client calls remain in this file.
""".strip()


def resolve_codex_binary(codex_arg: str) -> str | None:
    cand = shutil.which(codex_arg)
    if cand:
        return cand
    return None


def require_shell_deps_or_die():
    """Ensure required shell tools (like ripgrep) are available."""
    if os.name == "posix" and shutil.which("rg") is None:
        raise SystemExit(
            "ripgrep (rg) is not installed. Please install it:\n"
            "  sudo apt update && sudo apt install -y ripgrep\n"
        )


# ──────────────────────────────
# Main
# ──────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="Refactor direct LLM API usage to use the unified llm_wrapper (modules_to_scan-only)."
    )
    ap.add_argument("--repo", default=".", help="Repository root directory.")
    ap.add_argument(
        "--paths-from",
        default="modules_to_scan.txt",
        help="Text file with paths/globs to scan for LLM direct usage (one per line).",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Include all *.py files under the specified paths (skip usage detection).",
    )
    ap.add_argument(
        "--exclude",
        nargs="*",
        default=sorted(DEFAULT_EXCLUDES),
        help="Directory names to exclude from scanning.",
    )
    ap.add_argument(
        "--targets-file",
        default=".codex_targets.txt",
        help="File to write the current target path (for Codex prompt reference).",
    )
    ap.add_argument(
        "--codex", default="codex", help="Codex CLI executable (name or path)."
    )
    ap.add_argument("--model", default=None, help="Optional Codex model name.")
    ap.add_argument(
        "--test",
        action="store_true",
        help="Run on only the first matching file (or specified --test-file).",
    )
    ap.add_argument(
        "--test-file",
        default=None,
        help="Specific file to run on (for testing; must be within listed paths).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be executed without calling Codex.",
    )
    ap.add_argument(
        "--git-commit",
        action="store_true",
        help="Git commit each file's changes after Codex (separate commit per file).",
    )
    ap.add_argument(
        "--git-message",
        default="codex: enforce llm wrapper integration guidelines",
        help="Commit message prefix to use with --git-commit.",
    )
    ap.add_argument(
        "--import-modelrouter",
        default="from modules.llm import model_router",
        help="Import statement to ensure for model_router usage (default: 'from modules.llm import model_router').",
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
    candidates = pool if args.all else [p for p in pool if is_candidate_file(p)]
    if not candidates:
        raise SystemExit(
            "No Python files matched the given patterns."
            if args.all
            else "No direct LLM API usage found in the listed paths."
        )
    if args.test:
        if args.test_file:
            tf = (repo / args.test_file).resolve()
            if tf not in pool_set:
                raise SystemExit(f"--test-file must be within the listed paths: {tf}")
            if tf.name == "__init__.py":
                raise SystemExit("--test-file cannot be __init__.py")
            targets = [tf]
        else:
            targets = [candidates[0]]
    else:
        targets = candidates
    targets = [p for p in targets if p.name != "__init__.py"]
    if not targets:
        raise SystemExit(
            "No eligible Python files to process after excluding __init__.py."
        )

    targets_rel = [Path(p).relative_to(repo).as_posix() for p in targets]

    codex_bin = resolve_codex_binary(args.codex)
    if not codex_bin:
        raise SystemExit(
            "Could not find Codex CLI 'codex'. Install via:\n"
            "  npm i -g @openai/codex\n"
        )
    if not args.dry_run:
        require_shell_deps_or_die()

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
    print(f"[codex-wrapper] List file: {list_file}")
    print(f"[codex-wrapper] Excluding folders: {', '.join(sorted(excluded))}")
    if targets_rel:
        print(f"[codex-wrapper] First target: {targets_rel[0]}")

    for i, tr in enumerate(targets_rel, 1):
        (repo / args.targets_file).write_text(tr + "\n", encoding="utf-8")
        prompt = build_prompt([tr], args.targets_file, args.import_modelrouter)
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
