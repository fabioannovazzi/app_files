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
        "AUTH_PUBLIC_BASE_URL": "https://mparanza.com",
        "PDP_STORE_BACKEND": "postgres",
    }

    for key, value in values.items():
        if key in allowed_nonempty:
            assert value == allowed_nonempty[key]
        else:
            assert value == ""


def test_only_verified_cowork_zips_are_public() -> None:
    public_vera_zip = (
        ROOT / "static" / "shared" / "vera" / "downloads" / "vera-cowork-plugin.zip"
    )
    release_vera_zip = ROOT / "plugin_packages" / "vera" / "vera-cowork-plugin.zip"
    public_clara_zip = (
        ROOT / "static" / "shared" / "clara" / "downloads" / "clara-cowork-plugin.zip"
    )
    release_clara_zip = ROOT / "plugin_packages" / "clara" / "clara-cowork-plugin.zip"
    retired_plugin_zips = (
        ROOT / "protected_downloads" / "vera" / "vera-plugin.zip",
        ROOT / "static" / "shared" / "clara" / "downloads" / "clara-plugin.zip",
    )

    assert public_vera_zip.read_bytes() == release_vera_zip.read_bytes()
    assert public_clara_zip.read_bytes() == release_clara_zip.read_bytes()
    assert all(not path.exists() for path in retired_plugin_zips)


def test_public_pages_have_no_clara_or_vera_download_links() -> None:
    html = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "static").rglob("*.html")
    ).lower()

    assert "/downloads/vera" not in html
    assert "/downloads/clara" not in html
    assert "clara-plugin.zip" not in html
    assert "vera-plugin.zip" not in html


def test_vera_product_page_exposes_only_the_cowork_release_archive() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert page.count('href="downloads/vera-cowork-plugin.zip"') == 1
    assert page.count("data-vera-cowork-download-link") == 1


def test_clara_product_page_exposes_only_the_cowork_release_archive() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )

    assert page.count('href="downloads/clara-cowork-plugin.zip"') == 1
    assert page.count("data-clara-cowork-download-link") == 1


def test_vera_cowork_release_archive_is_served() -> None:
    from fastapi.testclient import TestClient

    from src.fastapi_app_entry import app

    expected = (
        ROOT / "static" / "shared" / "vera" / "downloads" / "vera-cowork-plugin.zip"
    ).read_bytes()
    response = TestClient(app).get(
        "/static/shared/vera/downloads/vera-cowork-plugin.zip"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.content == expected


def test_clara_cowork_release_archive_is_served() -> None:
    from fastapi.testclient import TestClient

    from src.fastapi_app_entry import app

    expected = (
        ROOT / "static" / "shared" / "clara" / "downloads" / "clara-cowork-plugin.zip"
    ).read_bytes()
    response = TestClient(app).get(
        "/static/shared/clara/downloads/clara-cowork-plugin.zip"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.content == expected


def test_only_product_pages_have_marketplace_install_actions() -> None:
    install_button_pages = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "static" / "shared").rglob("*.html")
        if "data-clara-install-link" in path.read_text(encoding="utf-8")
        or "data-vera-install-link" in path.read_text(encoding="utf-8")
    }

    assert install_button_pages == {
        "static/shared/clara/index.html",
        "static/shared/vera/index.html",
    }

    public_sources = tuple(
        path
        for path in (ROOT / "static" / "shared").rglob("*")
        if path.suffix in {".html", ".js"}
    )
    expected_pages_by_plugin_id = {
        "plugins_6a57ac5ce65c8191ae7bd0a51160eb7d": "static/shared/vera/index.html",
        "plugins_6a57b17fb5848191be710192d93fe03a": "static/shared/clara/index.html",
    }
    for plugin_id, expected_page in expected_pages_by_plugin_id.items():
        pages = {
            path.relative_to(ROOT).as_posix()
            for path in public_sources
            if plugin_id in path.read_text(encoding="utf-8")
        }
        assert pages == {expected_page}


def test_retired_duplicate_client_pages_are_absent() -> None:
    shared_root = ROOT / "static" / "shared"

    assert (shared_root / "new-client" / "index.html").is_file()
    assert not (shared_root / "client-intake").exists()
    assert not (shared_root / "client-onboarding").exists()


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
