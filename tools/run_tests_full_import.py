#!/usr/bin/env python3
import os, sys, importlib, pkgutil
from pathlib import Path

def main():
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    # Also add the src/ directory so modules like `parsers` and `journal_ingest` are importable.
    src_path = ROOT / "src"
    if src_path.exists() and str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    # Keep the environment deterministic and plugin-free
    os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    os.environ.setdefault("UI_SERVER_HEADLESS", "1")
    os.environ.setdefault("MPLBACKEND", "Agg")

    # 1) Pre-import your *real* code so pytest can’t shadow or half-stub it
    try:
        import modules  # your app package
    except Exception as e:
        print(f"[FATAL] cannot import package 'modules': {e!r}")
        sys.exit(1)

    names = [m.name for m in pkgutil.walk_packages(modules.__path__, modules.__name__ + ".")]
    failures = []
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as e:
            failures.append((name, e))

    if failures:
        print("\n[import-smoke] the following modules failed to import (real problems):")
        for name, e in failures:
            print(f"  - {name}: {type(e).__name__}: {e}")
        sys.exit(1)

    # 2) Run pytest in the same process (imports already done)
    try:
        import pytest
    except Exception as e:
        print(f"[FATAL] pytest not installed: {e!r}")
        sys.exit(1)

    args = sys.argv[1:] or ["-q", "--import-mode=importlib"]
    sys.exit(pytest.main(args))

if __name__ == "__main__":
    main()

