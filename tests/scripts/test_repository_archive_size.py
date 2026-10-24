"""Prevent directory download rejection while permitting archives at the guard."""

from __future__ import annotations

import subprocess

import pytest

from scripts import check_repository_archive_size as guard


@pytest.mark.parametrize(
    ("size", "exit_code"),
    [(200 * 1024 * 1024, 0), (230 * 1024 * 1024, 0), (230 * 1024 * 1024 + 1, 1)],
)
def test_guard_enforces_compressed_byte_boundary(monkeypatch, caplog, size, exit_code):
    monkeypatch.setattr(guard, "archive_size", lambda root: size)
    caplog.set_level("INFO")

    result = guard.main()

    assert result == exit_code
    assert str(size) in caplog.text
    assert "256 MiB" in caplog.text


@pytest.mark.parametrize(
    "error", [OSError("git unavailable"), subprocess.CalledProcessError(1, "git")]
)
def test_guard_reports_failed_measurement_instead_of_accepting_zero(
    monkeypatch, caplog, error
):
    def fail(root):
        raise error

    monkeypatch.setattr(guard, "archive_size", fail)

    result = guard.main()

    assert result == 1
    assert "Cannot measure repository archive" in caplog.text


def test_archive_size_measures_head_and_ignores_untracked_builds(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "source.txt").write_text("canonical source\n")
    subprocess.run(["git", "add", "source.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    expected = subprocess.check_output(
        ["git", "archive", "--format=tar.gz", "HEAD"], cwd=tmp_path
    )
    (tmp_path / "local-build.zip").write_bytes(b"untracked" * 1000)

    actual = guard.archive_size(tmp_path)

    assert actual == len(expected)
