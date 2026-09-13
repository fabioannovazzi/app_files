#!/usr/bin/env python3
"""Prepare an isolated case for the current native working chat."""

from _desktop_teaching import PLUGIN_ROOT
from desktop_teaching.cases import main as _main
from desktop_teaching.cases import prepare_case


def main(argv=None):
    return _main(argv, plugin_root=PLUGIN_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
