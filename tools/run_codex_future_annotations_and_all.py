#!/usr/bin/env python3
"""
run_codex_future_annotations_and_all.py

Enforce guideline:
| Start new modules with `from __future__ import annotations` and define `__all__` to enumerate exported names |

- Detect files missing the future import and/or __all__
- Ask Codex to insert the import at the top and create/update a minimal __all__ listing public API
- Keep diff minimal; do not change runtime behavior
"""
import argparse, os, re, shutil, subprocess
from pathlib import Path

DEFAULT_EXCLUDES = {".venv","venv","env",".git","__pycache__",".pytest_cache",".mypy_cache","site-packages","dist","build","node_modules"}
FUTURE_RX = re.compile(r"^\s*from\s+__future__\s+import\s+annotations\b", re.M)
ALL_RX    = re.compile(r"^\s*__all__\s*=", re.M)

def should_skip(p: Path, repo: Path, excluded: set[str]) -> bool:
    return any(part in excluded for part in p.relative_to(repo).parts)

def is_candidate_file(p: Path) -> bool:
    txt = p.read_text(encoding="utf-8", errors="ignore")
    need_future = not FUTURE_RX.search(txt)
    need_all    = not ALL_RX.search(txt)
    return bool(need_future or need_all)

def build_prompt(paths: list[str], targets_file: str) -> str:
    files="\n".join(f"- {x}" for x in paths)
    return f"""
Apply the guideline below **only** in the file listed and in "{targets_file}".

GUIDELINE
| Start modules with `from __future__ import annotations` and define `__all__` to enumerate exported names |

FILES TO EDIT:
{files}

WHAT TO CHANGE
1) If missing, insert at the very top (after any shebang or encoding line):
   `from __future__ import annotations`

2) Ensure there is a module-level `__all__ = [...]` that enumerates the public API:
   - Include top-level functions and classes whose names **do not** start with underscore.
   - Optionally include obvious module-level constants (UPPER_SNAKE_CASE).
   - If an __all__ already exists, update it to include current public names without removing existing entries unless they no longer exist.
   - Keep alphabetical order.

3) Do not alter runtime behavior. Do not move definitions around. Keep imports tidy.

4) Idempotency: Do not duplicate the future import or rewrite an unchanged __all__.
""".strip()

def resolve_codex(x: str)->str|None: return shutil.which(x) or None
def require_shell_deps_or_die():
    if os.name=="posix" and shutil.which("rg") is None:
        raise SystemExit("Install ripgrep (rg): sudo apt update && sudo apt install -y ripgrep")

def main():
    import argparse
    ap=argparse.ArgumentParser(description="Enforce future annotations and __all__")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--paths-from", default="modules_to_scan.txt")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--exclude", nargs="*", default=sorted(DEFAULT_EXCLUDES))
    ap.add_argument("--targets-file", default=".codex_targets.txt")
    ap.add_argument("--codex", default="codex")
    ap.add_argument("--model", default=None)
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--test-file", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--git-commit", action="store_true")
    ap.add_argument("--git-message", default="codex: add future annotations and __all__")
    args=ap.parse_args()

    repo=Path(args.repo).resolve()
    if not repo.exists(): raise SystemExit(f"Repo not found: {repo}")
    list_file=repo/args.paths_from
    if not list_file.exists(): raise SystemExit(f"--paths-from not found: {list_file}")

    excluded=set(args.exclude)
    patterns=[]; explicit=[]
    for raw in list_file.read_text(encoding="utf-8").splitlines():
        s=raw.strip().replace("\\","/")
        if not s or s.startswith("#"): continue
        p=repo/s
        if p.is_dir(): patterns.append((Path(s).as_posix().rstrip("/")+"/**/*.py"))
        elif p.is_file() and p.suffix==".py": explicit.append(p.resolve())
        else: patterns.append(s)

    pool=set(explicit)
    for pat in patterns:
        for p in repo.rglob(pat):
            if p.is_file() and p.suffix==".py" and p.name!="__init__.py" and not should_skip(p,repo,excluded):
                pool.add(p)
    pool=sorted(pool)
    candidates=pool if args.all else [p for p in pool if is_candidate_file(p)]
    if not candidates:
        raise SystemExit("No Python files matched patterns." if args.all else "All files already have future import and __all__.")

    if args.test:
        if args.test_file:
            tf=(repo/args.test_file).resolve()
            if tf not in pool: raise SystemExit("--test-file must be within listed paths")
            if tf.name=="__init__.py": raise SystemExit("--test-file cannot be __init__.py")
            targets=[tf]
        else: targets=[candidates[0]]
    else: targets=candidates
    targets=[p for p in targets if p.name!="__init__.py"]
    if not targets: raise SystemExit("No eligible Python files after excluding __init__.py.")
    targets_rel=[str(p.relative_to(repo).as_posix()) for p in targets]

    codex=resolve_codex(args.codex)
    if not codex: raise SystemExit("Codex CLI not found. Install: npm i -g @openai/codex")
    if not args.dry_run: require_shell_deps_or_die()

    base=[codex,"exec"]
    if getattr(args,"full_auto",False): base.append("--full-auto")
    if args.model: base+=["--model",args.model]
    base+=["--config","approval_policy=never","--config","sandbox_mode=danger-full-access","--config","model_reasoning_effort=high"]

    print(f"[codex-headers] Repo: {repo}; Targets: {len(targets_rel)}")
    for i,tr in enumerate(targets_rel,1):
        (repo/args.targets_file).write_text(tr+"\n", encoding="utf-8")
        prompt=build_prompt([tr], args.targets_file)
        cmd=base+[prompt]
        print(f"[codex-headers] ({i}/{len(targets_rel)}) {tr}")
        if args.dry_run: print("  [dry-run] Would run:", " ".join(cmd)); continue
        subprocess.run(cmd, cwd=str(repo), check=True)

    if args.git_commit:
        subprocess.run(["git","add","-A"], cwd=str(repo), check=True)
        msg=f"{args.git_message} [{len(targets_rel)} files]"
        proc=subprocess.run(["git","commit","-m",msg], cwd=str(repo), text=True, capture_output=True)
        if proc.returncode==0:
            short=subprocess.run(["git","rev-parse","--short","HEAD"], cwd=str(repo), text=True, capture_output=True, check=True).stdout.strip()
            print(f"[codex-headers] Committed as {short}")
        else:
            print("[codex-headers] No commit performed. Git said:"); print(proc.stdout or proc.stderr)

if __name__=="__main__": main()
