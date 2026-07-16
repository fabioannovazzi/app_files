from __future__ import annotations

import subprocess
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECRET_FILE = Path(".secrets/secrets.toml")
EXPECTED_PLUGIN_ZIPS = {
    "protected_downloads/vera/vera-plugin.zip",
    "static/shared/clara/downloads/clara-plugin.zip",
}
FORBIDDEN_ARCHIVE_PARTS = {".secrets", "credentials.toml"}
OBSOLETE_PROVIDER_MARKERS = (
    "anthropickey",
    "geminikey",
    "deepseekkey",
    "waba_token",
    "waba_number_id",
)


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_live_secret_file_is_absent_untracked_and_ignored() -> None:
    assert not (ROOT / SECRET_FILE).exists()
    assert _git("ls-files", "--error-unmatch", SECRET_FILE.as_posix()).returncode != 0
    assert _git("check-ignore", "-q", SECRET_FILE.as_posix()).returncode == 0


def test_sanitized_secret_example_contains_only_safe_values() -> None:
    example_path = ROOT / "config" / "secrets.example.toml"
    values = tomllib.loads(example_path.read_text(encoding="utf-8"))
    allowed_nonempty = {
        "AUTH_ENABLED": "false",
        "AUTH_COOKIE_SECURE": "true",
        "PDP_STORE_BACKEND": "postgres",
    }

    for key, value in values.items():
        if key in allowed_nonempty:
            assert value == allowed_nonempty[key]
        else:
            assert value == ""


def test_only_clara_and_vera_plugin_zips_are_tracked() -> None:
    result = _git("ls-files", "-z", "--", "*.zip")
    assert result.returncode == 0
    tracked_zips = {path for path in result.stdout.split("\0") if path}

    assert tracked_zips == EXPECTED_PLUGIN_ZIPS


def test_plugin_zips_exclude_secrets_and_obsolete_providers() -> None:
    for relative_path in sorted(EXPECTED_PLUGIN_ZIPS):
        with zipfile.ZipFile(ROOT / relative_path) as archive:
            for entry in archive.infolist():
                entry_path = Path(entry.filename)
                lowered_parts = {part.lower() for part in entry_path.parts}
                assert not lowered_parts.intersection(FORBIDDEN_ARCHIVE_PARTS)
                assert not any(part.startswith(".env") for part in lowered_parts)
                assert entry_path.suffix.lower() not in {".key", ".pem"}

                if entry.is_dir():
                    continue
                payload = archive.read(entry)
                try:
                    text = payload.decode("utf-8").lower()
                except UnicodeDecodeError:
                    continue
                assert not any(marker in text for marker in OBSOLETE_PROVIDER_MARKERS)
