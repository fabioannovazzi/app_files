#!/usr/bin/env python3
"""
scan_vectorization_candidates.py

Detector-only scanner that flags potential "row-by-row" patterns that AGENTS.md
discourages (favor vectorized Polars operations). It does NOT modify code.

Rules (heuristic; may include false positives):
- pandas-style: .iterrows(), .itertuples(), .apply(..., axis=1)
- generic loops: for ... in range(len(df)): (any variable), or len(some_df) in loops
- polars-style: .iter_rows(...), .rows(), Series.apply(...), .map_elements(...)

Outputs:
- Pretty text report (--report-out)
- JSON with structured findings (--json-out)
- Exit code: 0 on success/no findings; 2 if findings and --fail-on-find; 1 on error

Usage:
  ./scan_vectorization_candidates.py --paths-from modules_to_scan.txt --report-out reports/vectorize.txt --json-out reports/vectorize.json
"""
import argparse, re, sys, json, os, fnmatch
from pathlib import Path
import tokenize as tkn

DEFAULT_EXCLUDES = {".venv","venv","env",".git","__pycache__",".pytest_cache",".mypy_cache","site-packages","dist","build","node_modules"}

PATTERNS = [
    ("pandas_iterrows",      re.compile(r"\.\s*iterrows\s*\(")),
    ("pandas_itertuples",    re.compile(r"\.\s*itertuples\s*\(")),
    ("pandas_apply_axis1",   re.compile(r"\.apply\s*\([^)]*axis\s*=\s*1", re.I)),
    ("loop_range_len",       re.compile(r"\bfor\b\s+\w+(?:\s*,\s*\w+)?\s+in\s+range\s*\(\s*len\s*\(", re.I)),
    ("polars_iter_rows",     re.compile(r"\.\s*iter_rows\s*\(")),
    ("polars_rows",          re.compile(r"\.\s*rows\s*\(")),
    ("series_apply_lambda",  re.compile(r"\.apply\s*\(\s*lambda", re.I)),
    ("map_elements",         re.compile(r"\.map_elements\s*\(", re.I)),
]

def strip_strings_and_comments_text(text: str) -> str:
    # tokenize requires bytes-like reading; emulate via generate_tokens on lines
    from io import StringIO
    out = []
    try:
        for tok in tkn.generate_tokens(StringIO(text).readline):
            if tok.type in (tkn.STRING, tkn.COMMENT):
                out.append(" ")
            elif tok.type == tkn.NL:
                out.append("\n")
            else:
                out.append(tok.string)
        return "".join(out)
    except Exception:
        return text

def load_targets(repo: Path, paths_from: Path, all_mode: bool, excluded: set[str], ignore_globs: list[str]) -> list[Path]:
    patterns = []
    explicit = []
    for raw in paths_from.read_text(encoding="utf-8").splitlines():
        s = raw.strip().replace("\\", "/")
        if not s or s.startswith("#"):
            continue
        p = (repo / s)
        if p.is_dir():
            patterns.append((Path(s).as_posix().rstrip("/") + "/**/*.py"))
        elif p.is_file() and p.suffix == ".py":
            explicit.append(p.resolve())
        else:
            patterns.append(s)

    pool = set(explicit)
    for pat in patterns:
        for p in repo.rglob(pat):
            if (
                p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
            ):
                rel_parts = p.relative_to(repo).parts
                if any(part in excluded for part in rel_parts):
                    continue
                # ignore patterns
                rel = p.relative_to(repo).as_posix()
                if any(fnmatch.fnmatch(rel, g) for g in ignore_globs):
                    continue
                pool.add(p.resolve())
    return sorted(pool)

def scan_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    code = strip_strings_and_comments_text(text)
    code_lines = code.splitlines()
    raw_lines  = text.splitlines()
    findings = []
    for idx, line in enumerate(code_lines, start=1):
        for rule, rx in PATTERNS:
            if rx.search(line):
                snippet = raw_lines[idx-1].strip() if idx-1 < len(raw_lines) else ""
                findings.append({"file": str(path), "line": idx, "rule": rule, "snippet": snippet})
    return findings

def main():
    ap = argparse.ArgumentParser(description="Detect potential non-vectorized row-wise patterns (heuristic).")
    ap.add_argument("--repo", default=".", help="Repo root (default: .)")
    ap.add_argument("--paths-from", default="modules_to_scan.txt", help="List of dirs/files/globs to scan")
    ap.add_argument("--exclude", nargs="*", default=sorted(DEFAULT_EXCLUDES), help="Folder names to exclude anywhere in path")
    ap.add_argument("--ignore-globs", nargs="*", default=[], help="Glob patterns (relative) to ignore (e.g., 'tests/**')")
    ap.add_argument("--all", action="store_true", help="Scan all *.py under the listed paths")
    ap.add_argument("--json-out", default=None, help="Write JSON findings here")
    ap.add_argument("--report-out", default=None, help="Write pretty text report here")
    ap.add_argument("--fail-on-find", action="store_true", help="Exit with code 2 if any findings")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    paths_from = (repo / args.paths_from)
    if not paths_from.exists():
        print(f"--paths-from file not found: {paths_from}", file=sys.stderr)
        sys.exit(1)
    targets = load_targets(repo, paths_from, args.all, set(args.exclude), args.ignore_globs)
    if not targets:
        print("No Python files found to scan within the listed paths.", file=sys.stderr)
        sys.exit(0)

    all_findings = []
    for p in targets:
        all_findings.extend(scan_file(p))

    # Write outputs
    if args.json_out:
        out = {"summary": {"files_scanned": len(targets), "findings": len(all_findings)},
               "findings": all_findings}
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(out, indent=2), encoding="utf-8")

    if args.report_out:
        lines = [f"[vectorize-detector] scanned={len(targets)} files, findings={len(all_findings)}"]
        by_file = {}
        for f in all_findings:
            by_file.setdefault(f["file"], []).append(f)
        for fpath, items in sorted(by_file.items()):
            lines.append(f"\n{fpath}")
            for i in items:
                lines.append(f"  L{i['line']:>5}  {i['rule']:<22}  {i['snippet']}")
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_out).write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.fail_on_find and all_findings:
        sys.exit(2)
    sys.exit(0)

if __name__ == "__main__":
    main()
