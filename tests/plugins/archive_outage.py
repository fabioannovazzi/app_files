"""Inject actual optional-storage failures into isolated synthetic native jobs."""

from __future__ import annotations

from pathlib import Path

__all__ = ["unavailable_archive_environment", "disable_archive_configuration"]


def disable_archive_configuration(monkeypatch, temporary: Path) -> None:
    """Start standalone/portable engines without usable optional service stores."""
    for key in (
        "VERA_STUDIO_ARCHIVE_STATE_DIR",
        "VERA_STUDIO_ARCHIVE_PROFILE_DIR",
        "VERA_REPORTING_STATE_DIR",
    ):
        unavailable = temporary / key
        unavailable.write_text("Synthetic unavailable optional service storage")
        monkeypatch.setenv(key, str(unavailable))


def unavailable_archive_environment(
    env: dict[str, str], output: Path | None, temporary: Path
) -> dict[str, str]:
    """Keep execution inputs/outputs intact while optional directories fail IO."""
    result = dict(env)
    for key in (
        "VERA_STUDIO_ARCHIVE_STATE_DIR",
        "VERA_STUDIO_ARCHIVE_PROFILE_DIR",
        "VERA_REPORTING_STATE_DIR",
    ):
        selected = Path(env.get(key, str(temporary / key))).resolve()
        if not selected.is_relative_to(temporary.resolve()):
            selected = temporary / key
        if selected.exists():
            selected.rename(selected.with_name(selected.name + "-before-outage"))
        selected.parent.mkdir(parents=True, exist_ok=True)
        selected.write_text("Synthetic unavailable Archive storage")
        result[key] = str(selected)
    if output is None:
        return result
    reporting = output.parent / "reporting"
    if reporting.exists():
        reporting.rename(output.parent / "reporting-before-outage")
    reporting.write_text("Synthetic unavailable reporting storage")
    return result
