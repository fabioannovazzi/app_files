"""Generate discovery metadata by querying exact packaged services at build time."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

__all__ = ["add_vera_mcp_catalog"]

_CACHE: dict[str, bytes] = {}


def add_vera_mcp_catalog(entries: dict[str, bytes], prefix: str = "") -> None:
    """Keep all tools discoverable without starting specialists in user chats."""
    if prefix + "mcp-services.json" not in entries:
        return
    source = {
        name.removeprefix(prefix): data
        for name, data in entries.items()
        if name.startswith(prefix)
        and name.removeprefix(prefix)
        not in {"mcp-catalog.json", "execution-files.json"}
    }
    files = {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(source.items())
    }
    index = (
        json.dumps({"schema_version": 1, "files": files}, indent=2) + "\n"
    ).encode()
    key = hashlib.sha256(index).hexdigest()
    if key not in _CACHE:
        node = shutil.which("node")
        if node is None:
            raise ValueError("Node.js is required to generate Vera's tool catalogue")
        with tempfile.TemporaryDirectory(prefix="vera-mcp-catalog-") as temporary:
            # macOS /var is a symlink; existing execution isolation requires
            # real ancestors for the private runtime, including during builds.
            staging = Path(temporary).resolve()
            root = staging / "plugin"
            runtime = staging / "runtime"
            runtime.mkdir()
            for name, data in source.items():
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            (root / "execution-files.json").write_bytes(index)
            count = len(json.loads(source["mcp-services.json"])["mcpServers"])
            result = subprocess.run(
                [
                    node,
                    str(Path(__file__).with_suffix(".cjs")),
                    str(root),
                    str(runtime),
                ],
                capture_output=True,
                timeout=15 + count * 12,
                check=False,
            )
            if result.returncode:
                raise ValueError(
                    "Vera catalogue generation failed: " + result.stderr.decode()
                )
            catalog = json.loads(result.stdout)
            if len(catalog["services"]) != count:
                raise ValueError("Vera catalogue omits a configured service")
            _CACHE[key] = result.stdout
    entries[prefix + "mcp-catalog.json"] = _CACHE[key]
