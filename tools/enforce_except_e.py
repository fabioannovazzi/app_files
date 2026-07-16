#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enforce uniform 'except Exception as e:' across a repo, without using any LLM.

Transforms only:
  1) 'except:'                        -> 'except Exception as e:'
  2) 'except Exception:'              -> 'except Exception as e:'
  3) 'except Exception as <name>:'    -> header -> 'except Exception as e:'
     and rename `<name>` to 'e' within that handler's body (conservative).

Leaves untouched:
  - 'except SomeError ...', 'except (ErrA, ErrB) ...', 'except* ...', 'except BaseException ...'
  - strings/comments (never touched)

Conservative rename:
  - Rename old alias -> 'e' only within the same except suite;
    skip nested scopes (def/class/lambda/comprehensions) and store positions.

Usage examples:
  python enforce_except_e.py --paths-from modules_to_scan.txt --write
  python enforce_except_e.py --root . --all --check
  python enforce_except_e.py --file path/to/file.py --verbose

Requires: libcst  (pip install libcst)
"""

from __future__ import annotations
import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Set

import libcst as cst
from libcst import CSTTransformer, RemovalSentinel
from libcst import Name, AsName, ExceptHandler
from libcst.metadata import PositionProvider


DEFAULT_EXCLUDES: Set[str] = {
    ".venv", "venv", "env", ".git", "__pycache__", ".pytest_cache", ".mypy_cache",
    "site-packages", "dist", "build", "node_modules"
}


@dataclass
class ExceptContext:
    old_name: Optional[str]
    rename_active: bool


class EnforceExceptE(CSTTransformer):
    """
    libcst transformer:
      - Standardizes specific except headers.
      - Conservatively renames the exception variable within that handler body only.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self):
        self._except_stack: List[ExceptContext] = []
        self._suspend_scope_depth: int = 0   # def/class/lambda/comprehension depth
        self._in_store_ctx: int = 0          # assignment targets etc.

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _current_ctx(self) -> Optional[ExceptContext]:
        return self._except_stack[-1] if self._except_stack else None

    def _should_rename(self, name_value: str) -> bool:
        ctx = self._current_ctx()
        if not ctx or not ctx.rename_active or ctx.old_name is None:
            return False
        if self._suspend_scope_depth > 0:
            return False
        if self._in_store_ctx > 0:
            return False
        return name_value == ctx.old_name

    # ── Scope suspension (avoid nested def/class/lambda and comprehensions) ────
    def visit_FunctionDef(self, node: cst.FunctionDef) -> Optional[bool]:
        self._suspend_scope_depth += 1
        return True

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
        self._suspend_scope_depth -= 1
        return updated_node

    def visit_ClassDef(self, node: cst.ClassDef) -> Optional[bool]:
        self._suspend_scope_depth += 1
        return True

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:
        self._suspend_scope_depth -= 1
        return updated_node

    def visit_Lambda(self, node: cst.Lambda) -> Optional[bool]:
        self._suspend_scope_depth += 1
        return True

    def leave_Lambda(self, original_node: cst.Lambda, updated_node: cst.Lambda) -> cst.Lambda:
        self._suspend_scope_depth -= 1
        return updated_node

    def visit_ListComp(self, node: cst.ListComp) -> Optional[bool]:
        self._suspend_scope_depth += 1
        return True

    def leave_ListComp(self, original_node: cst.ListComp, updated_node: cst.ListComp) -> cst.ListComp:
        self._suspend_scope_depth -= 1
        return updated_node

    def visit_DictComp(self, node: cst.DictComp) -> Optional[bool]:
        self._suspend_scope_depth += 1
        return True

    def leave_DictComp(self, original_node: cst.DictComp, updated_node: cst.DictComp) -> cst.DictComp:
        self._suspend_scope_depth -= 1
        return updated_node

    def visit_SetComp(self, node: cst.SetComp) -> Optional[bool]:
        self._suspend_scope_depth += 1
        return True

    def leave_SetComp(self, original_node: cst.SetComp, updated_node: cst.SetComp) -> cst.SetComp:
        self._suspend_scope_depth -= 1
        return updated_node

    def visit_GeneratorExp(self, node: cst.GeneratorExp) -> Optional[bool]:
        self._suspend_scope_depth += 1
        return True

    def leave_GeneratorExp(self, original_node: cst.GeneratorExp, updated_node: cst.GeneratorExp) -> cst.GeneratorExp:
        self._suspend_scope_depth -= 1
        return updated_node

    # ── Store-context tracking (skip renaming on targets) ──────────────────────
    def visit_AssignTarget(self, node: cst.AssignTarget) -> Optional[bool]:
        self._in_store_ctx += 1
        return True

    def leave_AssignTarget(self, original_node: cst.AssignTarget, updated_node: cst.AssignTarget) -> cst.AssignTarget:
        self._in_store_ctx -= 1
        return updated_node

    def visit_AnnAssign(self, node: cst.AnnAssign) -> Optional[bool]:
        self._in_store_ctx += 1
        return True

    def leave_AnnAssign(self, original_node: cst.AnnAssign, updated_node: cst.AnnAssign) -> cst.AnnAssign:
        self._in_store_ctx -= 1
        return updated_node

    def visit_AugAssign(self, node: cst.AugAssign) -> Optional[bool]:
        self._in_store_ctx += 1
        return True

    def leave_AugAssign(self, original_node: cst.AugAssign, updated_node: cst.AugAssign) -> cst.AugAssign:
        self._in_store_ctx -= 1
        return updated_node

    def visit_NamedExpr(self, node: cst.NamedExpr) -> Optional[bool]:
        self._in_store_ctx += 1
        return True

    def leave_NamedExpr(self, original_node: cst.NamedExpr, updated_node: cst.NamedExpr) -> cst.NamedExpr:
        self._in_store_ctx -= 1
        return updated_node

    # ── Except handler header + body management ───────────────────────────────
    def visit_ExceptHandler(self, node: ExceptHandler) -> Optional[bool]:
        ctx = ExceptContext(old_name=None, rename_active=False)

        if node.type is None:
            # bare except:
            ctx.rename_active = False

        elif isinstance(node.type, Name) and node.type.value == "Exception":
            if node.name is None:
                # 'except Exception:'
                ctx.rename_active = False
            else:
                if isinstance(node.name, AsName) and isinstance(node.name.name, Name):
                    old = node.name.name.value
                    if old != "e":
                        ctx.old_name = old
                        ctx.rename_active = True
        else:
            # other exception types: untouched
            pass

        self._except_stack.append(ctx)
        return True

    def leave_ExceptHandler(self, original_node: ExceptHandler, updated_node: ExceptHandler) -> ExceptHandler:
        ctx = self._except_stack.pop()

        # 1) bare except:
        if original_node.type is None:
            return updated_node.with_changes(type=Name("Exception"), name=AsName(name=Name("e")))

        # 2) except Exception:
        if isinstance(original_node.type, Name) and original_node.type.value == "Exception" and original_node.name is None:
            return updated_node.with_changes(name=AsName(name=Name("e")))

        # 3) except Exception as <name> (name != 'e'):
        if (
            isinstance(original_node.type, Name) and original_node.type.value == "Exception" and
            isinstance(original_node.name, AsName) and isinstance(original_node.name.name, Name) and
            original_node.name.name.value != "e"
        ):
            return updated_node.with_changes(name=AsName(name=Name("e")))

        return updated_node

    # ── Rename within handler body (conservative) ─────────────────────────────
    def leave_Name(self, original_node: Name, updated_node: Name) -> Name | RemovalSentinel:
        if self._should_rename(updated_node.value):
            return updated_node.with_changes(value="e")
        return updated_node


# ── Driver ─────────────────────────────────────────────────────────────────────
def process_file(path: Path, write: bool, verbose: bool) -> bool:
    src = path.read_text(encoding="utf-8")
    try:
        mod = cst.parse_module(src)
    except Exception as ex:
        if verbose:
            print(f"[skip-parse-error] {path}: {ex}")
        return False

    wrapper = cst.MetadataWrapper(mod)
    out = wrapper.visit(EnforceExceptE())

    if out.code != src:
        if write:
            path.write_text(out.code, encoding="utf-8")
        if verbose:
            print(f"[changed] {path}")
        return True
    else:
        if verbose:
            print(f"[ok] {path}")
        return False


def gather_files(
    root: Path,
    paths_from: Optional[Path],
    single_file: Optional[Path],
    include_all: bool,
    excludes: Set[str]
) -> List[Path]:
    if single_file:
        return [single_file.resolve()]

    candidates: Set[Path] = set()
    bases: List[Path] = []

    if paths_from and paths_from.exists():
        for line in paths_from.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            bases.append((root / s).resolve())
    else:
        bases.append(root.resolve())

    for base in bases:
        if base.is_file() and base.suffix == ".py":
            candidates.add(base)
        elif base.is_dir():
            for p in base.rglob("*.py"):
                rel_parts = p.relative_to(root).parts
                if any(part in excludes for part in rel_parts):
                    continue
                candidates.add(p.resolve())

    return sorted(candidates)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Enforce 'except Exception as e:' without LLMs (libcst).")
    ap.add_argument("--root", default=".", help="Repository root (default: current dir).")
    ap.add_argument("--paths-from", default=None, help="Optional file listing subpaths to scan (one per line).")
    ap.add_argument("--file", dest="single_file", default=None, help="Run on a single file path.")
    ap.add_argument("--all", action="store_true", help="Scan all *.py under root/paths-from (default).")
    ap.add_argument("--exclude", nargs="*", default=sorted(DEFAULT_EXCLUDES),
                    help="Folder names to exclude anywhere in the path.")

    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Write changes in-place (default).")
    mode.add_argument("--check", action="store_true", help="Exit 1 if any file would change; do not write.")
    ap.add_argument("--verbose", action="store_true", help="Print per-file status.")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"Root not found: {root}", file=sys.stderr)
        return 2

    paths_from = Path(args.paths_from).resolve() if args.paths_from else None
    if paths_from and not paths_from.exists():
        print(f"--paths-from not found: {paths_from}", file=sys.stderr)
        return 2

    single_file = Path(args.single_file).resolve() if args.single_file else None
    excludes = set(args.exclude)

    files = gather_files(root, paths_from, single_file, args.all, excludes)
    if not files:
        if args.verbose:
            print("No Python files found.")
        return 0

    changed_any = False
    for f in files:
        chg = process_file(f, write=not args.check, verbose=args.verbose)
        changed_any = changed_any or chg

    if args.check and changed_any:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
