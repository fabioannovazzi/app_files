#!/usr/bin/env python3
"""Lucia local teaching entry point."""

from _desktop_teaching import PLUGIN_ROOT
from desktop_teaching.onboarding import MARKER, OnboardingError
from desktop_teaching.teaching import TeachingStore as _Store
from desktop_teaching.teaching import main as _main


class TeachingStore(_Store):
    """Bind all state and workflow checks to this installed product."""

    def __init__(self, root=None, session_id=None):
        super().__init__(root, session_id, plugin_root=PLUGIN_ROOT)


def main(argv=None):
    return _main(argv, plugin_root=PLUGIN_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
