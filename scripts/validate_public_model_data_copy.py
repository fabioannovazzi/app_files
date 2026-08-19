#!/usr/bin/env python3
"""Flag internal implementation language in public model-data explanations.

The rules are deliberately narrow and deterministic. They detect literal
internal filenames and a small, reviewed vocabulary of implementation terms;
they do not attempt to judge whether prose is generally "too technical".
Professional terms and public formats such as Codex, Cowork, CSV, XML, PDF,
and Studio Archive remain allowed.
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

__all__ = ["Finding", "main", "validate_public_model_data_copy"]

LOGGER = logging.getLogger(__name__)

GOVERNED_PUBLIC_COPY = (
    Path("static/shared/journal-sampling/index.html"),
    Path("static/shared/check-entries/index.html"),
)


@dataclass(frozen=True)
class Finding:
    """One mechanically identified editorial issue."""

    path: Path
    line: int
    rule: str
    token: str
    guidance: str

    def format(self, repository_root: Path) -> str:
        """Return an actionable, repository-relative diagnostic."""

        relative = self.path.relative_to(repository_root)
        return (
            f"{relative}:{self.line}: {self.rule}: {self.token!r}. " f"{self.guidance}"
        )


@dataclass(frozen=True)
class _Rule:
    name: str
    pattern: re.Pattern[str]
    guidance: str


RULES = (
    _Rule(
        name="internal-filename",
        pattern=re.compile(
            r"\b[A-Za-z0-9][A-Za-z0-9_-]*\.(?:json|ya?ml|toml|py|[cm]?js)\b",
            re.IGNORECASE,
        ),
        guidance=(
            "Describe the file by its purpose, unless its literal name is needed "
            "by the professional."
        ),
    ),
    _Rule(
        name="internal-interface",
        pattern=re.compile(r"\b(?:MCP|CLI)\b"),
        guidance="Describe what the integrated or local path does in plain language.",
    ),
    _Rule(
        name="implementation-jargon",
        pattern=re.compile(
            r"\b(?:payload|widget|builder|handoff|helper|fallback)\b|"
            r"component-only|file-based|ref-\*",
            re.IGNORECASE,
        ),
        guidance="Replace the implementation term with its user-visible effect.",
    ),
    _Rule(
        name="component-internals",
        pattern=re.compile(
            r"metadati (?:visibili )?(?:soltanto|solo|riservati) al componente|"
            r"component-only metadata|"
            r"métadonnées réservées au composant|"
            r"(?:nur für die Komponente sichtbare|komponenteninterne) Metadaten|"
            r"metadatos (?:visibles únicamente|reservados) (?:para|al) componente",
            re.IGNORECASE,
        ),
        guidance=(
            "State directly that the detailed data is shown to the reviewer and "
            "does not reach the model."
        ),
    ),
)

MODEL_SECTION = re.compile(
    r"<section\b(?=[^>]*\bdata-model-data-workflow=)[^>]*>.*?</section>",
    re.IGNORECASE | re.DOTALL,
)
MODEL_STRING = re.compile(
    r"""(?:["']model\.[^"']+["']|\bmodelData(?:Conclusion|Title)?)"""
    r"""\s*:\s*(?P<literal>"(?:\\.|[^"\\])*")""",
    re.DOTALL,
)


def _model_copy_fragments(source: str) -> Iterable[tuple[int, str]]:
    """Yield source offsets and public model-copy fragments."""

    for match in MODEL_SECTION.finditer(source):
        yield match.start(), match.group(0)
    for match in MODEL_STRING.finditer(source):
        literal = match.group("literal")
        yield match.start("literal") + 1, literal[1:-1]


def _public_copy_files(repository_root: Path, *, all_public_pages: bool) -> list[Path]:
    if not all_public_pages:
        return [repository_root / relative for relative in GOVERNED_PUBLIC_COPY]
    shared = repository_root / "static" / "shared"
    return sorted(
        path
        for suffix in ("*.html", "*.js")
        for path in shared.rglob(suffix)
        if path.is_file()
    )


def validate_public_model_data_copy(
    repository_root: Path, *, all_public_pages: bool = False
) -> list[Finding]:
    """Return editorial findings in governed, or optionally all, public copy."""

    findings: list[Finding] = []
    for path in _public_copy_files(repository_root, all_public_pages=all_public_pages):
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        seen: set[tuple[int, str, str]] = set()
        for offset, fragment in _model_copy_fragments(source):
            for rule in RULES:
                for match in rule.pattern.finditer(fragment):
                    absolute_offset = offset + match.start()
                    line = source.count("\n", 0, absolute_offset) + 1
                    token = match.group(0)
                    key = (line, rule.name, token.casefold())
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append(
                        Finding(
                            path=path,
                            line=line,
                            rule=rule.name,
                            token=token,
                            guidance=rule.guidance,
                        )
                    )
    return findings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Flag internal filenames and implementation jargon in public "
            "model-data explanations."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (defaults to this checkout).",
    )
    parser.add_argument(
        "--all-public-pages",
        action="store_true",
        help=(
            "Audit every shared public HTML/JS source; the default enforced "
            "scope is the journal-audit chain."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the validator and return a shell-compatible status."""

    args = _parser().parse_args(argv)
    repository_root = args.root.resolve()
    findings = validate_public_model_data_copy(
        repository_root, all_public_pages=args.all_public_pages
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for finding in findings:
        LOGGER.error(finding.format(repository_root))
    if findings:
        LOGGER.error("Found %s public-copy editorial issue(s).", len(findings))
        return 1
    if args.all_public_pages:
        LOGGER.info("All public model-data copy uses plain, user-facing language.")
    else:
        LOGGER.info(
            "Governed journal-audit model-data copy uses plain, user-facing language."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
