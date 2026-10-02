"""Explicit setup-only downloads; never imported by the MCP server or worker."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from .contracts import MODEL_REVISION

__all__ = ["prepare_model", "main"]


def prepare_model(model_root: Path) -> None:
    """Download a pinned official checkpoint and warm its tokenizer cache."""
    import tiktoken
    from huggingface_hub import snapshot_download

    model_root = model_root.expanduser().resolve()
    model_root.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id="openai/privacy-filter",
        revision=MODEL_REVISION,
        allow_patterns=["original/*"],
        local_dir=model_root / "checkpoint",
        token=False,
    )
    config = json.loads(
        (model_root / "checkpoint" / "original" / "config.json").read_text()
    )
    os.environ["TIKTOKEN_CACHE_DIR"] = str(model_root / "tokenizer")
    tiktoken.get_encoding(config["encoding"])
    (model_root / "ready.json").write_text(
        json.dumps({"model_revision": MODEL_REVISION, "encoding": config["encoding"]}),
        encoding="utf-8",
    )
    logging.info("Checkpoint and tokenizer prepared for offline filtering.")


def main() -> None:
    """Prepare model assets during the separately invoked installation step."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    prepare_model(args.model_dir)


if __name__ == "__main__":
    main()
