#!/usr/bin/env python3
"""Surface one-time Clara change-request status messages in Claude Cowork."""

from __future__ import annotations

import json
import os
from pathlib import Path

from change_requests import check_fixed_requests

__all__ = ["main"]


def main() -> int:
    """Poll opaque local receipts and emit a Claude SessionStart message."""

    plugin_root = Path(
        os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parents[1])
    ).expanduser()
    plugin_data_value = os.environ.get("CLAUDE_PLUGIN_DATA")
    plugin_data = Path(plugin_data_value).expanduser() if plugin_data_value else None
    message = check_fixed_requests(plugin_root, plugin_data)
    if message:
        print(json.dumps({"systemMessage": message}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
