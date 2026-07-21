from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECRET_FILE = Path(".secrets/secrets.toml")


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


def test_clara_and_vera_plugin_zips_are_absent() -> None:
    plugin_zips = (
        ROOT / "protected_downloads" / "vera" / "vera-plugin.zip",
        ROOT / "static" / "shared" / "clara" / "downloads" / "clara-plugin.zip",
    )

    assert all(not path.exists() for path in plugin_zips)


def test_public_pages_have_no_clara_or_vera_download_links() -> None:
    html = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "static").rglob("*.html")
    ).lower()

    assert "/downloads/vera" not in html
    assert "/downloads/clara" not in html
    assert "clara-plugin.zip" not in html
    assert "vera-plugin.zip" not in html


def test_only_product_and_onboarding_gateway_pages_have_install_buttons() -> None:
    install_button_pages = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "static" / "shared").rglob("*.html")
        if "data-clara-install-link" in path.read_text(encoding="utf-8")
        or "data-vera-install-link" in path.read_text(encoding="utf-8")
    }

    assert install_button_pages == {
        "static/shared/clara/index.html",
        "static/shared/client-intake/index.html",
        "static/shared/client-onboarding/index.html",
        "static/shared/vera/index.html",
    }


def test_retired_clara_and_vera_download_urls_return_not_found() -> None:
    from fastapi.testclient import TestClient

    from src.fastapi_app_entry import app

    client = TestClient(app)
    retired_paths = (
        "/downloads/clara",
        "/downloads/vera",
        "/static/shared/clara/downloads/clara-plugin.zip",
        "/static/shared/journal-sampling/downloads/journal-sampling-plugin.zip",
    )

    for path in retired_paths:
        response = client.get(path, follow_redirects=False)

        assert response.status_code == 404, path
