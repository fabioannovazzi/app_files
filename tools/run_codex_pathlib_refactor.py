#!/usr/bin/env python3
"""
run_codex_pathlib_refactor.py  (WSL/Ubuntu optimized; modules_to_scan-only)

Enforce guideline:
| Use pathlib.Path for file system operations; avoid os.path |

- Scans only paths from --paths-from (default: modules_to_scan.txt)
- With --all: include every *.py in those paths; else detect files using os.path / os filesystem calls
- Ignores strings/comments; excludes common vendor/venv dirs
- Invokes Codex to make minimal, behavior-preserving edits
- Performs a single optional git commit at the end (not per file)
"""
import argparse, os, re, shutil, subprocess
from pathlib import Path
import tokenize as tkn

DEFAULT_EXCLUDES = {".venv","venv","env",".git","__pycache__",".pytest_cache",".mypy_cache","site-packages","dist","build","node_modules"}
OS_PATH_RE   = re.compile(r"\bos\.path\.")
OS_FS_RE     = re.compile(r"\bos\.(makedirs|remove|unlink|rmdir|renames|rename|listdir|scandir|walk|chdir|mkdir|rmdir)\b")

def strip_strings_and_comments(p: Path) -> str:
    try:
        with tkn.open(str(p)) as f:
            out=[];
            for tok in tkn.generate_tokens(f.readline):
                if tok.type in (tkn.STRING, tkn.COMMENT): out.append(" ")
                elif tok.type == tkn.NL: out.append("\n")
                else: out.append(tok.string)
            return "".join(out)
    except Exception:
        return p.read_text(encoding="utf-8", errors="ignore")

def should_skip(p: Path, repo: Path, excluded: set[str]) -> bool:
    return any(part in excluded for part in p.relative_to(repo).parts)

def is_candidate_file(p: Path) -> bool:
    code = strip_strings_and_comments(p)
    return bool(OS_PATH_RE.search(code) or OS_FS_RE.search(code))

def build_prompt(paths: list[str], targets_file: str) -> str:
    files = "\n".join(f"- {x}" for x in paths)
    return f"""
Enforce the guideline below **only** in the file listed and in "{targets_file}".

GUIDELINE
| Use pathlib.Path for file system operations; avoid os.path |

FILES TO EDIT (relative to repo root):
{files}

WHAT TO CHANGE
1) Replace os.path.* helpers with Path methods/operators:
   - join(a,b) → Path(a) / b
   - dirname(p) → Path(p).parent
   - basename(p) → Path(p).name
   - exists(p) → Path(p).exists()
   - isfile/isdir → Path(p).is_file() / .is_dir()
   - abspath/realpath → Path(p).resolve()
   - expanduser/expandvars if present → Path(os.path.expanduser(p)) (only if necessary)

2) Replace common os.* filesystem calls with Path equivalents:
   - os.makedirs(p, exist_ok=True) → Path(p).mkdir(parents=True, exist_ok=True)
   - os.remove/unlink(p) → Path(p).unlink()
   - os.rename(a,b) → Path(a).rename(b)
   - os.listdir(p) → [x.name for x in Path(p).iterdir()]
   - os.walk(p) → Path(p).rglob("*") (when appropriate), or keep walk if deep rewrite is unsafe

3) Insert `from pathlib import Path` if needed. Remove unused `import os` only if nothing else uses os.

4) Keep behavior and error handling. Do not alter unrelated logic. Be conservative where semantics are unclear.

5) Idempotency: running this again should not change anything further.
""".strip()

def resolve_codex_binary(x: str) -> str|None:
    return shutil.which(x) or None

def require_shell_deps_or_die():
    if os.name=="posix" and shutil.which("rg") is None:
        raise SystemExit("ripgrep (rg) not found. Install: sudo apt update && sudo apt install -y ripgrep")

def main():
    ap=argparse.ArgumentParser(description="Refactor os.path/os.* to pathlib.Path (modules_to_scan-only).")
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
    ap.add_argument("--git-message", default="codex: pathlib refactor")
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
        raise SystemExit("No Python files matched patterns." if args.all else "No os.path/os.* usage found.")

    if args.test:
        if args.test_file:
            tf=(repo/args.test_file).resolve()
            if tf not in pool: raise SystemExit("--test-file must be within listed paths")
            if tf.name=="__init__.py": raise SystemExit("--test-file cannot be __init__.py")
            targets=[tf]
        else:
            targets=[candidates[0]]
    else:
        targets=candidates
    targets=[p for p in targets if p.name!="__init__.py"]
    if not targets: raise SystemExit("No eligible Python files after excluding __init__.py.")
    targets_rel=[str(p.relative_to(repo).as_posix()) for p in targets]

    codex=resolve_codex_binary(args.codex)
    if not codex: raise SystemExit("Codex CLI 'codex' not found. Install: npm i -g @openai/codex")
    if not args.dry_run: require_shell_deps_or_die()

    base=[codex,"exec"]
    if getattr(args,"full_auto",False): base.append("--full-auto")
    if args.model: base+=["--model",args.model]
    base+=["--config","approval_policy=never","--config","sandbox_mode=danger-full-access","--config","model_reasoning_effort=high"]

    print(f"[codex-pathlib] Repo: {repo}")
    print(f"[codex-pathlib] Targets: {len(targets_rel)}")
    print(f"[codex-pathlib] List file: {(repo/args.targets_file)}")

    for i,tr in enumerate(targets_rel,1):
        (repo/args.targets_file).write_text(tr+"\n", encoding="utf-8")
        prompt=build_prompt([tr], args.targets_file)
        cmd=base+[prompt]
        print(f"[codex-pathlib] ({i}/{len(targets_rel)}) {tr}")
        if args.dry_run:
            print("  [dry-run] Would run:", " ".join(cmd)); continue
        try:
            subprocess.run(cmd, cwd=str(repo), check=True)
        except subprocess.CalledProcessError as e:
            raise SystemExit(f"Codex failed on {tr} ({e.returncode})")

    if args.git_commit:
        subprocess.run(["git","add","-A"], cwd=str(repo), check=True)
        msg=f"{args.git_message} [{len(targets_rel)} files]"
        proc=subprocess.run(["git","commit","-m",msg], cwd=str(repo), text=True, capture_output=True)
        if proc.returncode==0:
            short=subprocess.run(["git","rev-parse","--short","HEAD"], cwd=str(repo), text=True, capture_output=True, check=True).stdout.strip()
            print(f"[codex-pathlib] Committed all changes as {short}")
        else:
            print("[codex-pathlib] No commit performed. Git said:"); print(proc.stdout or proc.stderr)

if __name__=="__main__":
    main()
