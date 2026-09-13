"""Load the bundled shared local runtime without network or extra dependencies."""

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for candidate in (
    PLUGIN_ROOT / "vendor/modules",
    PLUGIN_ROOT.parent / "_shared/vendor/modules",
):
    if (candidate / "desktop_teaching/onboarding.py").is_file():
        sys.path.insert(0, str(candidate))
        break
else:
    raise RuntimeError(
        "The installed local teaching runtime is missing; reinstall this plugin"
    )
