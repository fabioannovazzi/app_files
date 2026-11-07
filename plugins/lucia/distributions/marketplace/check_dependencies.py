"""Prepare Lucia document dependencies through the shared managed runtime."""

from __future__ import annotations

import argparse
import importlib
import logging

from managed_python_runtime import main as runtime_main

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Probe imports during runtime validation; never recursively install itself."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--managed-verify", action="store_true")
    parser.add_argument("--requirements", action="append", default=[])
    args = parser.parse_args(argv)
    if args.managed_verify:
        # These imports are the actual document engine requirements. A failed
        # import prevents false readiness; successful validation must not install.
        try:
            for name in ("jsonschema", "lxml.etree", "pypdf", "openpyxl", "docx"):
                importlib.import_module(name)
        except ImportError as error:
            logging.error("Document dependency unavailable: %s", error)
            return 1
        return 0
    arguments = []
    for requirement in args.requirements:
        arguments.extend(["--requirements", requirement])
    return runtime_main([*arguments, "install"])


if __name__ == "__main__":
    raise SystemExit(main())
