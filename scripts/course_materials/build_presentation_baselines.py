"""Rebuild fictional input decks for the correction lesson with current Clara.

These are the uncorrected source decks supplied to the learner, not demonstration
results. Composition and publication run in a temporary directory; only the
resulting fictional input files are copied into the authoring corpus.
"""

from __future__ import annotations

import argparse
import io
import logging
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

__all__ = ["main"]
ROOT = Path(__file__).resolve().parents[2]
MATERIALS = Path(__file__).resolve().parent
LANGUAGES = ("it", "en", "fr", "de", "es")
LOGGER = logging.getLogger(__name__)


def _command(name: str, *args: str | Path) -> None:
    script = ROOT / "plugins/clara/skills/html-deck/scripts" / name
    # Fixed local scripts only; no shell or command name supplied by the CLI.
    result = subprocess.run(  # nosec B603
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)


def _archive(work: Path) -> bytes:
    stream = io.BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        for source in sorted(work.iterdir()):
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"Unexpected baseline input: {source.name}")
            entry = ZipInfo(source.name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, source.read_bytes())
    return stream.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    destination = MATERIALS / "inputs/presentations"
    with tempfile.TemporaryDirectory(prefix="clara-teaching-baselines-") as temporary:
        for language in LANGUAGES:
            source = MATERIALS / "presentation_sources" / language
            expected = {
                "deck.json",
                "deck-plan.json",
                "content-ledger.json",
                f"brief-{language}.md",
            }
            if {p.name for p in source.iterdir()} != expected or any(
                p.is_symlink() or not p.is_file() for p in source.iterdir()
            ):
                raise ValueError(f"Unexpected source deck tree: {language}")
            work = Path(temporary) / language / "work"
            shutil.copytree(source, work)
            _command(
                "compose_html_deck.py",
                work / "deck-plan.json",
                "--output-dir",
                work,
                "--force",
            )
            output = work.parent / "built"
            _command("build_html_deck.py", work, "--output-root", output)
            pages = list(output.glob("*/index.html"))
            if len(pages) != 1:
                raise ValueError(f"Expected one built source deck: {language}")
            for name, payload in (
                (f"original-deck-{language}.html", pages[0].read_bytes()),
                (f"original-work-{language}.zip", _archive(work)),
            ):
                target = destination / name
                if args.check:
                    if (
                        not target.is_file()
                        or target.is_symlink()
                        or target.read_bytes() != payload
                    ):
                        raise ValueError(
                            f"Refresh the correction teaching input: {name}"
                        )
                else:
                    if target.is_symlink():
                        raise ValueError(f"Refusing linked teaching input: {name}")
                    target.write_bytes(payload)
            LOGGER.info(
                "%s source deck %s", "Verified" if args.check else "Rebuilt", language
            )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
