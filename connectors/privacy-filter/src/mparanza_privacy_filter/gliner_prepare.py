"""Explicit setup-only download of the pinned GLiNER2-PII checkpoint."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .engines import GLINER2

__all__ = ["prepare_model", "main"]


def prepare_model(model_root: Path) -> None:
    """Cache weights, encoder configuration and tokenizer in one local directory."""
    from huggingface_hub import snapshot_download

    model_root = model_root.expanduser().resolve()
    model_root.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id="fastino/gliner2-privacy-filter-PII-multi",
        revision=GLINER2.revision,
        allow_patterns=[*GLINER2.required_files, "README.md"],
        local_dir=model_root / "checkpoint",
        token=False,
    )
    if not all(
        (model_root / "checkpoint" / name).is_file() for name in GLINER2.required_files
    ):
        raise RuntimeError("model_download_incomplete")
    (model_root / "ready.json").write_text(
        json.dumps({"engine": "gliner2", "model_revision": GLINER2.revision}),
        encoding="utf-8",
    )
    logging.info("GLiNER2-PII checkpoint and tokenizer prepared for offline filtering.")


def main() -> None:
    """Prepare model assets only during the separately invoked installation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    prepare_model(args.model_dir)


if __name__ == "__main__":
    main()
