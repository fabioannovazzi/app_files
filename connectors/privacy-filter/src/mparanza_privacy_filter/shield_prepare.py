"""Explicit pinned PII-Shield setup, including model and upstream NER bootstrap."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .shield_ready import snapshot

__all__ = ["main"]


def main() -> None:
    """Downloads happen here, before any client-document processing."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--npm", type=Path, required=True)
    args = parser.parse_args()
    root = args.model_dir.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    node, npm = args.node.resolve(strict=True), args.npm.resolve(strict=True)
    env = dict(os.environ)
    setup_bin = root / "setup-bin"
    setup_bin.mkdir(exist_ok=True)
    # Upstream's explicit setup invokes `npm`; expose the supplied CLI only here.
    if os.name == "nt":
        if any(char in str(node) + str(npm) for char in '%"&|^<>\r\n'):
            parser.error("Unsupported shell characters in Node/npm setup paths.")
        (setup_bin / "npm.cmd").write_text(f'@"{node}" "{npm}" %*\n')
    else:
        shim = setup_bin / "npm"
        if shim.is_symlink():
            shim.unlink()
        shim.symlink_to(npm)
    env["PATH"] = os.pathsep.join(
        (str(node.parent), str(setup_bin), env.get("PATH", ""))
    )
    env["PII_SHIELD_DATA_DIR"] = str(root / "upstream")
    env["PII_SHIELD_MODELS_DIR"] = str(root / "upstream/models")
    subprocess.run(
        [
            str(node),
            str(npm),
            "install",
            "--prefix",
            str(root / "cli"),
            "pii-shield@2.2.0",
        ],
        env=env,
        check=True,
    )  # nosec B603
    cli = root / "cli/node_modules/pii-shield/dist/cli/bin.mjs"
    command = [str(node), str(cli)]
    subprocess.run(
        [*command, "install-model", "--yes"], env=env, check=True
    )  # nosec B603
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        sample = Path(temporary) / "setup.txt"
        sample.write_text("John Smith writes to setup@example.com.")
        env["PII_SHIELD_MAPPINGS_DIR"] = str(Path(temporary) / "mappings")
        result = subprocess.run(
            [
                *command,
                "anonymize",
                str(sample),
                "--out",
                str(Path(temporary) / "out"),
                "--no-review",
                "--json",
            ],
            env=env,
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )  # nosec B603
        if json.loads(result.stdout)["ner_ready"] is not True:
            parser.error(
                "PII-Shield NER setup did not finish; no readiness receipt written."
            )
    (root / "shield.json").write_text(json.dumps({"node": str(node), "cli": str(cli)}))
    (root / "shield-ready.json").write_text(
        json.dumps({"version": "2.2.0", "files": snapshot(root)})
    )


if __name__ == "__main__":
    main()
