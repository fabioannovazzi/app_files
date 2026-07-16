#!/usr/bin/env python3
"""
scan_ui_vs_logic_misplacements.py

Detector-only scanner that flags heavy data/compute imports inside UI modules.
It does NOT modify code.

Rules:
- heavy_imports_in_ui: file inside --ui-roots importing polars/numpy/pandas/sklearn/etc.

Outputs:
- Pretty text report (--report-out)
- JSON with structured findings (--json-out)
- Exit code: 0 on success/no findings; 2 if findings and --fail-on-find; 1 on error

Usage:
  ./scan_ui_vs_logic_misplacements.py --paths-from modules_to_scan.txt --ui-roots ui pages app --report-out reports/ui_logic.txt --json-out reports/ui_logic.json
"""
import argparse, re, sys, json, os, fnmatch
from pathlib import Path

DEFAULT_EXCLUDES = {".venv","venv","env",".git","__pycache__",".pytest_cache",".mypy_cache","site-packages","dist","build","node_modules"}

HEAVY_IMPORT_RE     = re.compile(r"^\s*import\s+(polars|numpy|pandas|sklearn|torch|tensorflow)\b", re.M)

def load_targets(repo: Path, paths_from: Path, excluded: set[str], ignore_globs: list[str]) -> list[Path]:
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
            if p.is_file() and p.suffix == ".py" and p.name != "__init__.py":
                rel = p.relative_to(repo).as_posix()
                if any(part in excluded for part in p.relative_to(repo).parts):
                    continue
                if any(fnmatch.fnmatch(rel, g) for g in ignore_globs):
                    continue
                pool.add(p.resolve())
    return sorted(pool)

def is_under_ui_roots(path: Path, repo: Path, ui_roots: list[str]) -> bool:
    rel = path.relative_to(repo).as_posix()
    parts = rel.split("/")
    return any(root.strip("/") in parts for root in ui_roots if root)

def scan_file(path: Path, repo: Path, ui_roots: list[str]) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    findings = []
    in_ui = is_under_ui_roots(path, repo, ui_roots)

    # Heavy imports inside UI
    if in_ui:
        for i, line in enumerate(text.splitlines(), start=1):
            if HEAVY_IMPORT_RE.search(line):
                findings.append({"file": str(path), "line": i, "rule": "heavy_imports_in_ui", "snippet": line.strip()})

    return findings

def main():
    ap = argparse.ArgumentParser(description="Detect heavy imports in UI modules.")
    ap.add_argument("--repo", default=".", help="Repo root (default: .)")
    ap.add_argument("--paths-from", default="modules_to_scan.txt", help="List of dirs/files/globs to scan")
    ap.add_argument("--exclude", nargs="*", default=sorted(DEFAULT_EXCLUDES), help="Folder names to exclude anywhere in path")
    ap.add_argument("--ignore-globs", nargs="*", default=[], help="Glob patterns (relative) to ignore (e.g., 'tests/**')")
    ap.add_argument("--ui-roots", nargs="*", default=["ui","pages","app"], help="Directories considered 'UI' (default: ui pages app)")
    ap.add_argument("--json-out", default=None, help="Write JSON findings to this path")
    ap.add_argument("--report-out", default=None, help="Write pretty text report to this path")
    ap.add_argument("--fail-on-find", action="store_true", help="Exit with code 2 if any findings")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    paths_from = (repo / args.paths_from)
    if not paths_from.exists():
        print(f"--paths-from file not found: {paths_from}", file=sys.stderr)
        sys.exit(1)

    targets = load_targets(repo, paths_from, set(args.exclude), args.ignore_globs)
    if not targets:
        print("No Python files found to scan within the listed paths.", file=sys.stderr)
        sys.exit(0)

    all_findings = []
    for p in targets:
        all_findings.extend(scan_file(p, repo, args.ui_roots))

    if args.json_out:
        out = {"summary": {"files_scanned": len(targets), "findings": len(all_findings)},
               "findings": all_findings}
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(out, indent=2), encoding="utf-8")

    if args.report_out:
        lines = [f"[ui-logic-detector] scanned={len(targets)} files, findings={len(all_findings)}"]
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
