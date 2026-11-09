"""Reproduce local synthetic Archive search scale without external services."""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path
from time import perf_counter

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "plugins/studio-archive/scripts"))
import archive_core as core


def main() -> None:
    """Retain the synthetic corpus, index and measured checks under outputs."""
    output = ROOT / "outputs/studio-archive-hardening/scale"
    studio = output / "Studio"
    state = output / "state"
    os.environ.pop("VERA_STUDIO_ARCHIVE_PROFILE_DIR", None)
    os.environ["VERA_STUDIO_ARCHIVE_STATE_DIR"] = str(state)
    studio.mkdir(parents=True, exist_ok=True)
    for client in range(100):
        folder = studio / f"Client{client:03}"
        folder.mkdir(exist_ok=True)
        for document in range(50):
            (folder / f"note{document:03}.txt").write_text(
                f"Synthetic archive search evidence Client{client:03} document{document:03}.\n"
                + "A fictional quarterly report for isolation and scale checks.\n" * 40,
                encoding="utf-8",
            )
    core.configure_archive(studio, state_dir=state)
    start = perf_counter()
    refreshed = core.refresh_archive(state_dir=state)
    refresh_seconds = perf_counter() - start
    status = core.studio_archive_status(state_dir=state)
    scope = next(
        row["scope_id"]
        for row in status["scopes"]
        if row["display_name"] == "Client042"
    )
    start = perf_counter()
    selected = core.search_archive(
        "quarterly", scope_id=scope, limit=20, state_dir=state
    )
    search_seconds = perf_counter() - start
    foreign = core.search_archive("Client043", scope_id=scope, state_dir=state)
    opened = core.open_archive_source(
        selected["results"][0]["source_id"], state_dir=state
    )
    assert status["document_count"] == 5000
    assert selected["result_count"] == 20
    assert all(row["scope_id"] == scope for row in selected["results"])
    assert foreign["result_count"] == 0
    assert opened["source_verified"] is True
    report = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "client_count": 100,
        "documents": status["document_count"],
        "refresh_seconds": refresh_seconds,
        "selected_query_seconds": search_seconds,
        "selected_result_count": selected["result_count"],
        "foreign_result_count": foreign["result_count"],
        "opened_result": opened,
        "refresh_result": refreshed,
        "limits": "Synthetic text on this local host; not OCR, network storage, Windows or live connector acceptance.",
    }
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
