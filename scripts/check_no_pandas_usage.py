from __future__ import annotations

import re
import sys
from pathlib import Path

__all__ = ["main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "app.py",
    "modules",
    "plugins",
    "src",
    "ui",
    "scripts",
    "components",
)
ALLOWED_TO_PANDAS_FILES = {
    Path("modules/charting/draw_scatter.py"),
    Path("plugins/_shared/vendor/modules/charting/draw_scatter.py"),
}
IGNORED_FILES = {Path("scripts/check_no_pandas_usage.py")}
PATTERNS = (
    (
        re.compile(r"^\s*(import\s+pandas\b|from\s+pandas\b)", re.MULTILINE),
        set(),
    ),
    (re.compile(r"import_module\(\s*['\"]pandas['\"]\s*\)"), set()),
    (re.compile(r"\.to_pandas\s*\("), ALLOWED_TO_PANDAS_FILES),
)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for target in TARGETS:
        path = REPO_ROOT / target
        if not path.exists():
            continue
        if path.is_file() and path.suffix == ".py":
            files.append(path)
            continue
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    return files


def _relative(path: Path) -> Path:
    return path.relative_to(REPO_ROOT)


def main() -> int:
    """Return nonzero when disallowed pandas usage is present."""

    violations: list[str] = []
    for path in _iter_python_files():
        relative = _relative(path)
        if relative in IGNORED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, allowed_files in PATTERNS:
            if relative in allowed_files:
                continue
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{relative}:{line}: {match.group(0).strip()}")
    if violations:
        sys.stderr.write(
            "Disallowed pandas usage found. Use Polars; the only current "
            "exception is the datashader bridge in draw_scatter.py.\n"
        )
        sys.stderr.write("\n".join(violations) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
