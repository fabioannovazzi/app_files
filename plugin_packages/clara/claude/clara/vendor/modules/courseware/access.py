"""Verify local course storage with real I/O, never inferred permissions."""

from __future__ import annotations

import errno
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

__all__ = ["CourseAccessError", "verify_course_access"]


class CourseAccessError(OSError):
    """Keep the failed operation and native error available for host remediation."""

    def __init__(self, directory: Path, operation: str, error: OSError) -> None:
        super().__init__(f"Course paused: {operation} failed in {directory}: {error}")
        self.directory = directory
        self.operation = operation
        self.original = error
        self.cleanup_errors: list[str] = []

    def as_dict(self) -> dict[str, Any]:
        """Report evidence without assigning an unverified Windows/security cause."""
        return {
            "status": "blocked",
            "reason": "course_file_access",
            "directory": str(self.directory),
            "operation": self.operation,
            "error": str(self.original),
            "error_type": type(self.original).__name__,
            "errno": self.original.errno,
            "winerror": getattr(self.original, "winerror", None),
            "filename": self.original.filename,
            "filename2": self.original.filename2,
            "cleanup_errors": self.cleanup_errors,
            "next_step": (
                "Pause teaching. Request the host's access approval for this exact "
                "directory and operation, or connect that same directory as the "
                "course workspace. Then retry the check and save in that chat. "
                "If an approved retry fails, inspect the exact error; do not "
                "continue exercises, move the course, or reset saved progress."
            ),
        }


def _probe(directory: Path) -> None:
    """Exercise the same create/read/replace/delete operations as local saves."""
    operation = "create_directory"
    probe: Path | None = None
    failure: CourseAccessError | None = None
    try:
        if any(path.is_symlink() for path in (directory, *directory.parents)):
            raise OSError(errno.ELOOP, "Use the existing real course directory")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        probe = Path(tempfile.mkdtemp(prefix=".course-access-", dir=directory))
        target = probe / "check.txt"
        replacement = probe / "replacement.txt"
        operation = "write_file"
        target.write_text("course access check\n", encoding="utf-8")
        operation = "read_file"
        if target.read_text(encoding="utf-8") != "course access check\n":
            raise OSError(errno.EIO, "Course test file did not round-trip")
        operation = "update_file"
        target.write_text("updated\n", encoding="utf-8")
        if target.read_text(encoding="utf-8") != "updated\n":
            raise OSError(errno.EIO, "Course test update did not round-trip")
        operation = "replace_file"
        replacement.write_text("replacement\n", encoding="utf-8")
        replacement.replace(target)
        if target.read_text(encoding="utf-8") != "replacement\n":
            raise OSError(errno.EIO, "Course test replacement did not round-trip")
        operation = "delete_file"
        target.unlink()
        operation = "delete_directory"
        probe.rmdir()
        probe = None
    except OSError as exc:
        failure = CourseAccessError(directory, operation, exc)
    finally:
        if probe is not None:
            # Touch only this invocation's private probe, never existing course data.
            for path in (probe / "replacement.txt", probe / "check.txt", probe):
                try:
                    if path == probe:
                        path.rmdir()
                    else:
                        path.unlink(missing_ok=True)
                except OSError as exc:
                    if failure is None:
                        failure = CourseAccessError(directory, "cleanup", exc)
                    failure.cleanup_errors.append(f"{path}: {exc}")
    if failure is not None:
        raise failure from failure.original


def verify_course_access(directories: Iterable[Path]) -> dict[str, Any]:
    """Mechanically prove current I/O capability; never cache an approval as proof."""
    checked: list[str] = []
    for directory in dict.fromkeys(
        path.expanduser().absolute() for path in directories
    ):
        _probe(directory)
        checked.append(str(directory))
    return {"status": "ready", "directories": checked}
