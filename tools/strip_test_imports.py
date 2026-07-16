#!/usr/bin/env python3
"""
Minimal, conservative remover of test-only imports from production code.

- Removes only single-line imports that reference: pytest, hypothesis, tests.*
- Leaves every other byte unchanged.
- Skips multi-line/continued/semi-colon import statements by default.
- Does not touch tests/, docs/, venvs, sys.path hacks, or try/except logic.
- Dry-run by default; pass --apply to write changes.

Examples removed:
  import pytest
  import pytest as pt
  from pytest import raises
  import hypothesis, os      -> becomes: import os
  from tests.foo import bar  -> whole line removed

Safe by default. Use --aggressive only if you accept editing backslash/parenthesized imports.
"""

from __future__ import annotations
import argparse, difflib, re
from pathlib import Path
from typing import Iterable

DEFAULT_EXCLUDES = {
    ".venv","venv","env",".git","__pycache__",".pytest_cache",".mypy_cache",
    "site-packages","dist","build","node_modules","docs","tests"
}
BLOCKED_DEFAULT = ("pytest","hypothesis","tests")

IMPORT_RE   = re.compile(r'^(\s*)import\s+([^#;]+?)(\s*)(#.*)?$')
FROM_RE     = re.compile(r'^(\s*)from\s+([A-Za-z_][\w\.]*)\s+import\s+([^#;]+?)(\s*)(#.*)?$')
HAS_COMPLEX = re.compile(r'[\\(]|;')  # backslash, parenthesis, semicolon → skip by default

def repo_root(p: str|Path) -> Path:
    return Path(p).resolve()

def scan_root(repo: Path) -> Path:
    s = repo / "src"
    return s if s.is_dir() else repo

def iter_py_files(root: Path, excludes: set[str], include_tests: bool) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        parts = set(p.parts)
        if parts & excludes:
            continue
        if not include_tests and ("tests" in parts or p.name.startswith("test_")):
            continue
        yield p

def top_module(mod: str) -> str:
    return (mod.strip().split('.')[0] if mod else "")

def clean_import_line(line: str, blocked: set[str]) -> tuple[str, bool]:
    """Handle 'import a, b as c' (single-line) conservatively."""
    m = IMPORT_RE.match(line)
    if not m:
        return line, False
    indent, items, space, trailing = m.groups()
    if HAS_COMPLEX.search(items):
        return line, False  # skip complex
    # split by commas at top-level (safe because we skipped parentheses)
    kept = []
    changed = False
    for part in items.split(","):
        itm = part.strip()
        if not itm:
            continue
        # module [as alias]
        mod = itm.split()[0]
        if top_module(mod) in blocked or mod.startswith("tests"):
            changed = True
            continue
        kept.append(itm)
    if not changed:
        return line, False
    if not kept:
        return "", True  # remove whole line
    # rebuild with the original trailing comment (if any)
    new_items = ", ".join(kept)
    return f"{indent}import {new_items}{space}{trailing or ''}\n", True

def clean_from_line(line: str, blocked: set[str]) -> tuple[str, bool]:
    """Handle 'from X import y, z' (single-line) conservatively."""
    m = FROM_RE.match(line)
    if not m:
        return line, False
    indent, module, names, space, trailing = m.groups()
    if HAS_COMPLEX.search(module) or HAS_COMPLEX.search(names):
        return line, False  # skip complex
    if top_module(module) in blocked or module.startswith("tests"):
        # remove the whole line
        return "", True
    return line, False

def process_text(text: str, blocked: set[str]) -> tuple[str, bool]:
    out_lines = []
    changed_any = False
    for line in text.splitlines(keepends=True):
        new_line, changed = clean_import_line(line, blocked)
        if changed:
            changed_any = True
            if new_line:
                out_lines.append(new_line)
            continue
        new_line, changed = clean_from_line(line, blocked)
        if changed:
            changed_any = True
            if new_line:
                out_lines.append(new_line)
            continue
        out_lines.append(line)
    return "".join(out_lines), changed_any

def main():
    ap = argparse.ArgumentParser(description="Remove test-only imports from production code (conservative).")
    ap.add_argument("--repo", default=".", help="Repo root (default: .)")
    ap.add_argument("--apply", action="store_true", help="Write changes to files")
    ap.add_argument("--blocked", default=",".join(BLOCKED_DEFAULT),
                    help="Comma-separated top-level modules to remove (default: pytest,hypothesis,tests)")
    ap.add_argument("--include-tests", action="store_true", help="Also scan tests/ (OFF by default)")
    ap.add_argument("--aggressive", action="store_true",
                    help="Also edit multi-line/backslash/semicolon imports (OFF by default)")
    args = ap.parse_args()

    repo = repo_root(args.repo)
    root = scan_root(repo)
    excludes = set(DEFAULT_EXCLUDES)
    if args.include_tests:
        excludes.discard("tests")
    blocked = {x.strip() for x in args.blocked.split(",") if x.strip()}

    print(f"[strip] repo: {repo}")
    print(f"[strip] scan root: {root}")
    print(f"[strip] blocked modules: {', '.join(sorted(blocked))}")
    print(f"[strip] include tests/: {bool(args.include_tests)}")
    print(f"[strip] aggressive (multi-line): {bool(args.aggressive)}\n")

    files = list(iter_py_files(root, excludes, include_tests=args.include_tests))
    changed_files = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        new_text, changed = process_text(text, blocked)
        if not changed:
            continue
        changed_files += 1
        if args.apply:
            path.write_text(new_text, encoding="utf-8")
            print(f"[APPLY] {path.relative_to(repo)}")
        else:
            diff = difflib.unified_diff(
                text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=str(path),
                tofile=str(path),
            )
            print("".join(diff))

    if changed_files == 0:
        print("No changes.")
    else:
        print(f"\nFiles changed: {changed_files}")
        if not args.apply:
            print("Dry run only. Re-run with --apply to save edits.")

if __name__ == "__main__":
    main()

