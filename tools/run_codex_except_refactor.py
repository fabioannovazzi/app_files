#!/usr/bin/env python3
"""
run_codex_except_refactor.py  (WSL/Ubuntu optimized; modules_to_scan-only)

Enforce guideline:
| Avoid bare `except:` clauses or broad `except Exception:` catches |

- Looks ONLY into paths listed in --paths-from (default: modules_to_scan.txt).
- With --all: include EVERY *.py under those listed subfolders (recursively).
- Without --all: include only files that likely contain bare `except:` or `except Exception` usage.
- Ignores strings/comments to reduce false positives.
- Excludes virtualenvs/vendor dirs by default.
- Runs Codex CLI to edit exception handling to be more specific or properly handled.

Usage (from repo root, in WSL/Ubuntu):

./run_codex_except_refactor.py \
  --paths-from modules_to_scan.txt \
  --test \
  --git-commit \
  --git-message "codex: enforce exception handling guideline"

./run_codex_except_refactor.py \
  --paths-from modules_to_scan.txt \
  --all \
  --git-commit \
  --git-message "codex: enforce exception handling guideline"

Common options:

  --dry-run
     Print what would run, without invoking Codex.
"""
import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path
import tokenize as tkn

DEFAULT_EXCLUDES = {
    ".venv", "venv", "env", ".git", "__pycache__", ".pytest_cache", ".mypy_cache",
    "site-packages", "dist", "build", "node_modules"
}

# ──────────────────────────────
# Regex patterns for candidate detection
# ──────────────────────────────
# Patterns to detect bare or broad exception handlers
BARE_EXCEPT_RE  = re.compile(r"\bexcept\s*:\s")   # 'except:' with no exception specified
BROAD_EXCEPT_RE = re.compile(r"\bexcept\s+Exception\b")  # 'except Exception' (with or without 'as ...')

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
    """Detect broad exception usage (bare except or 'except Exception')."""
    code = strip_strings_and_comments(path)
    # Ensure it's not just the definition of an exception (no 'except Exception' usage in def lines)
    return bool(BARE_EXCEPT_RE.search(code) or BROAD_EXCEPT_RE.search(code))

def build_prompt(inline_paths: list[str], targets_file: str) -> str:
    """Build the Codex instruction prompt to refine exception handling."""
    paths_block = "\n".join(f"- {p}" for p in inline_paths)
    return f"""
Enforce the guideline below **only** in the file listed and in "{targets_file}".

GUIDELINE
| Avoid bare `except:` clauses or broad `except Exception:` catches; only suppress expected errors |

FILES TO EDIT (relative to repo root):
{paths_block}

WHAT TO CHANGE
1) Narrow overly broad exception handlers:
   - Replace `except:` (catching all exceptions) with specific exception types or at least `except Exception as e:` and handle it.
   - Replace generic `except Exception:` with one or more specific exceptions if possible, or otherwise handle and log the exception explicitly.

2) If the code can anticipate certain exception types, catch those explicitly:
   - BEFORE:
       try:
           risky_operation()
       except Exception:
           handle_failure()
   - AFTER:
       try:
           risky_operation()
       except (ValueError, KeyError) as e:
           handle_failure(e)
       except Exception as e:
           logging.exception("Unexpected error: %s", e)
           raise
   In the AFTER, specific expected errors (ValueError, KeyError) are caught and handled, while other unforeseen exceptions are logged and re-raised to avoid silent failure.

3) Do not leave bare `except:` blocks. Every caught exception should be named (with `as e` if used) and either handled or logged:
   - If an exception is truly safe to ignore, explicitly comment why and catch a specific subclass (not just Exception).
   - If using `pass` as a placeholder, consider logging a warning or removing the try/except if it's not needed.

4) Use the `logging` module for error reporting instead of print statements when adding logs. For example, use `logging.error()` or `logging.exception()` to record exceptions.

5) Preserve existing logic:
   - Do not alter the overall flow or functionality except to refine the exception handling.
   - Maintain any custom messages or behaviors in the original except blocks (e.g., if they were writing to a status message, keep that behavior).

6) Scope & idempotency:
   - Only modify broad exception handlers (`except:` or `except Exception`). Do not change already specific except clauses.
   - Running this tool again should result in no changes (the code should no longer contain bare `except:` or `except Exception` without proper handling).

7) Imports:
   - If adding logging calls, ensure `import logging` is present at the top of the file (insert if missing, in the appropriate section without duplicating).
""".strip()

def resolve_codex_binary(codex_arg: str) -> str|None:
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
    ap = argparse.ArgumentParser(
        description="Refactor broad exception clauses to more specific and handled exceptions (modules_to_scan-only)."
    )
    ap.add_argument("--repo", default=".", help="Repo root (default: .)")
    ap.add_argument(
        "--paths-from",
        default="modules_to_scan.txt",
        help="Text file with subfolders/files to scan (one path or glob per line, # for comments)."
    )
    ap.add_argument(
        "--all", action="store_true",
        help="Include all *.py files under listed paths (skip detection)."
    )
    ap.add_argument(
        "--exclude", nargs="*", default=sorted(DEFAULT_EXCLUDES),
        help="Folder names to ignore in paths."
    )
    ap.add_argument("--targets-file", default=".codex_targets.txt",
                    help="Filename to write the target list (default .codex_targets.txt).")
    ap.add_argument("--codex", default="codex",
                    help="Codex CLI binary or path (default 'codex').")
    ap.add_argument("--model", default=None,
                    help="Optional model override for Codex.")
    ap.add_argument("--test", action="store_true",
                    help="Run on a single file (the first candidate or given --test-file).")
    ap.add_argument("--test-file", default=None,
                    help="Specific file to test (must lie within listed paths).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would run without invoking Codex.")
    ap.add_argument("--git-commit", action="store_true",
                    help="Git commit changes after running Codex on each file.")
    ap.add_argument("--git-message", default="codex: enforce exception handling guideline",
                    help="Commit message to use with --git-commit.")
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
            if (p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
                and not should_skip(p, repo, excluded)):
                pool_set.add(p)
    pool = sorted(pool_set)
    candidates = pool if args.all else [p for p in pool if is_candidate_file(p)]
    if not candidates:
        raise SystemExit(
            "No Python files matched the listed patterns."
            if args.all else
            "No broad exception clauses found in the listed subfolders."
        )
    if args.test:
        if args.test_file:
            tf = (repo / args.test_file).resolve()
            if tf not in pool_set:
                raise SystemExit(f"--test-file must be within listed paths: {tf}")
            if tf.name == "__init__.py":
                raise SystemExit("--test-file cannot be __init__.py")
            targets = [tf]
        else:
            targets = [candidates[0]]
    else:
        targets = candidates
    targets = [p for p in targets if p.name != "__init__.py"]
    if not targets:
        raise SystemExit("No eligible Python files after excluding __init__.py.")

    targets_rel = [Path(p).relative_to(repo).as_posix() for p in targets]

    codex_bin = resolve_codex_binary(args.codex)
    if not codex_bin:
        raise SystemExit(
            "Codex CLI 'codex' not found. Install via:\n"
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
        "--config", "approval_policy=never",
        "--config", "sandbox_mode=danger-full-access",
        "--config", "model_reasoning_effort=high",
    ]

    print(f"[codex-wrapper] Repo: {repo}")
    print(f"[codex-wrapper] Targets: {len(targets_rel)} file(s)")
    print(f"[codex-wrapper] List file: {list_file}")
    print(f"[codex-wrapper] Excluding folders: {', '.join(sorted(excluded))}")
    if targets_rel:
        print(f"[codex-wrapper] First target: {targets_rel[0]}")

    for i, tr in enumerate(targets_rel, 1):
        (repo / args.targets_file).write_text(tr + "\n", encoding="utf-8")
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
        if args.git_commit:
            subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
            commit_proc = subprocess.run(
                ["git", "commit", "-m", f"{args.git_message} [{tr}]"],
                cwd=str(repo), text=True, capture_output=True
            )
            if commit_proc.returncode == 0:
                commit = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=str(repo), check=True, text=True, capture_output=True
                ).stdout.strip()
                print(f"[codex-wrapper] Committed {tr} as {commit}")
            else:
                print(f"[codex-wrapper] No commit for {tr} (likely no changes). Git said:")
                print(commit_proc.stdout or commit_proc.stderr)

if __name__ == "__main__":
    main()
