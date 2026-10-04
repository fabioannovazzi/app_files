"""Delegate Vera studio-format setup to its shared communications profile store."""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["main"]
ROOT = Path(__file__).resolve().parents[1]
packaged = ROOT / "modules/comunicazione-professionale/scripts"
source = ROOT.parent / "comunicazione-professionale/scripts"
sys.path.insert(0, str(packaged if packaged.is_dir() else source))
from studio_document_format import main

if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
