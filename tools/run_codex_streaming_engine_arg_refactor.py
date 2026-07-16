#!/usr/bin/env python3
"""
run_codex_streaming_engine_arg_refactor.py

Polars streaming guidance:
- Replace collect(streaming=True) with collect(engine="streaming") (idempotent).
- Do NOT strip selective streaming usage; only rename the argument form.
"""
import argparse, os, re, shutil, subprocess
from pathlib import Path
import tokenize as tkn

DEFAULT_EXCLUDES = {".venv","venv","env",".git","__pycache__",".pytest_cache",".mypy_cache","site-packages","dist","build","node_modules"}
STREAMING_ARG_RE = re.compile(r"\bcollect\s*\(\s*streaming\s*=\s*True", re.M)

def strip_strings_and_comments(p: Path) -> str:
    try:
        with tkn.open(str(p)) as f:
            out=[]
            for tok in tkn.generate_tokens(f.readline):
                if tok.type in (tkn.STRING, tkn.COMMENT): out.append(" ")
                elif tok.type==tkn.NL: out.append("\n")
                else: out.append(tok.string)
            return "".join(out)
    except Exception:
        return p.read_text(encoding="utf-8", errors="ignore")

def should_skip(p: Path, repo: Path, excluded: set[str]) -> bool:
    return any(part in excluded for part in p.relative_to(repo).parts)

def is_candidate_file(p: Path) -> bool:
    return bool(STREAMING_ARG_RE.search(strip_strings_and_comments(p)))

def build_prompt(paths: list[str], targets_file: str) -> str:
    files = "\n".join(f"- {x}" for x in paths)
    return f"""
Apply the following change **only** in the file listed and in "{targets_file}".

GUIDANCE
- Replace `collect(streaming=True)` with `collect(engine="streaming")`.
- Keep selective streaming usages; do not remove streaming where it exists.

FILES TO EDIT:
{files}

WHAT TO CHANGE
1) Rename the argument form in Polars collect calls:
   BEFORE: lf.collect(streaming=True)
   AFTER:  lf.collect(engine="streaming")

2) Do not duplicate an existing engine=... argument; if engine is already present, leave as is.

3) Idempotency: running again should result in no further diffs.
""".strip()

def resolve_codex(x:str)->str|None: return shutil.which(x) or None
def require_shell_deps_or_die():
    if os.name=="posix" and shutil.which("rg") is None:
        raise SystemExit("Install ripgrep (rg) first.")

def main():
    ap=argparse.ArgumentParser(description="Replace collect(streaming=True) → collect(engine=\"streaming\")")
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
    ap.add_argument("--git-message", default="codex: collect(streaming=True) → engine=\"streaming\"")
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
        raise SystemExit("No Python files matched patterns." if args.all else "No collect(streaming=True) patterns found.")

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

    print(f"[codex-streaming] Repo: {repo}; Targets: {len(targets_rel)}")
    for i,tr in enumerate(targets_rel,1):
        (repo/args.targets_file).write_text(tr+"\n", encoding="utf-8")
        prompt=build_prompt([tr], args.targets_file)
        cmd=base+[prompt]
        print(f"[codex-streaming] ({i}/{len(targets_rel)}) {tr}")
        if args.dry_run: print("  [dry-run] Would run:", " ".join(cmd)); continue
        subprocess.run(cmd, cwd=str(repo), check=True)

    if args.git_commit:
        subprocess.run(["git","add","-A"], cwd=str(repo), check=True)
        msg=f"{args.git_message} [{len(targets_rel)} files]"
        proc=subprocess.run(["git","commit","-m",msg], cwd=str(repo), text=True, capture_output=True)
        if proc.returncode==0:
            short=subprocess.run(["git","rev-parse","--short","HEAD"], cwd=str(repo), text=True, capture_output=True, check=True).stdout.strip()
            print(f"[codex-streaming] Committed as {short}")
        else:
            print("[codex-streaming] No commit performed. Git said:"); print(proc.stdout or proc.stderr)

if __name__=="__main__": main()
