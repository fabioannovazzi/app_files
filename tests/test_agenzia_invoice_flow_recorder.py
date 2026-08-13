from __future__ import annotations

import asyncio
import importlib.util
import json
import stat
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUDIO_ARCHIVE_ROOT = ROOT / "plugins" / "studio-archive"
VERA_ROOT = ROOT / "plugins" / "vera"
RECORDER_PATH = STUDIO_ARCHIVE_ROOT / "scripts" / "record_agenzia_invoice_flow.py"


def _load_recorder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_agenzia_invoice_flow_recorder_module", RECORDER_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_redact_text_removes_identifiers_and_private_terms() -> None:
    recorder = _load_recorder()

    result = recorder.redact_text(
        "Cliente Alpha SRL RSSMRA85T10A562S 12345678901 "
        "mario@example.com IT60X0542811101000000123456 ordine 987654",
        ("Cliente Alpha SRL",),
    )

    assert "Cliente Alpha SRL" not in result
    assert "RSSMRA85T10A562S" not in result
    assert "12345678901" not in result
    assert "mario@example.com" not in result
    assert "IT60X0542811101000000123456" not in result
    assert "987654" not in result
    assert "<private>" in result
    assert "<tax-id>" in result
    assert "<vat-id>" in result
    assert "<email>" in result
    assert "<iban>" in result


def test_sanitize_url_keeps_only_exact_agenzia_origin_and_path() -> None:
    recorder = _load_recorder()

    result = recorder.sanitize_url(
        "https://ivaservizi.agenziaentrate.gov.it/cons/cons-web/?token=secret#row"
    )

    assert result == "https://ivaservizi.agenziaentrate.gov.it/cons/cons-web/"


def test_sanitize_url_blocks_lookalike_and_non_https_origins() -> None:
    recorder = _load_recorder()

    assert (
        recorder.sanitize_url("https://agenziaentrate.gov.it.example.com/private")
        == "<blocked-origin>"
    )


def test_sanitize_url_redacts_identifiers_in_path() -> None:
    recorder = _load_recorder()

    result = recorder.sanitize_url(
        "https://ivaservizi.agenziaentrate.gov.it/result/12345678901/"
        "job-202608101234567890123456"
    )

    assert "12345678901" not in result
    assert "202608101234567890123456" not in result
    assert "<vat-id>" in result
    assert (
        recorder.sanitize_url("http://ivaservizi.agenziaentrate.gov.it/portale/")
        == "<blocked-origin>"
    )


def test_sanitize_element_drops_values_and_unknown_fields() -> None:
    recorder = _load_recorder()

    result = recorder.sanitize_element(
        {
            "event_type": "change",
            "tag": "input",
            "role": "textbox",
            "label": "Partita IVA 12345678901",
            "value": "12345678901",
            "outer_html": "<input value='12345678901'>",
            "unknown": "secret",
        }
    )

    assert result == {
        "event_type": "change",
        "label": "Partita IVA <vat-id>",
        "role": "textbox",
        "tag": "input",
    }


def test_build_download_record_hashes_name_without_saving_content() -> None:
    recorder = _load_recorder()

    class Download:
        suggested_filename = "IT12345678901_Fatture.zip"

    result = recorder.build_download_record(
        Download(), "https://ivaservizi.agenziaentrate.gov.it/cons/mass-web/result"
    )

    assert result["suffixes"] == [".zip"]
    assert result["content_saved"] is False
    assert "IT12345678901" not in json.dumps(result)
    assert "suggested_filename" not in result
    assert "download_path" not in result


def test_write_recording_creates_owner_only_review_file(tmp_path: Path) -> None:
    recorder = _load_recorder()
    recording = {
        "schema_version": recorder.SCHEMA_VERSION,
        "events": [],
        "snapshots": [],
        "downloads": [],
    }

    target = recorder.write_recording(tmp_path / "private", recording)

    assert json.loads(target.read_text(encoding="utf-8")) == recording
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700


def test_write_recording_rejects_forbidden_capture_fields(tmp_path: Path) -> None:
    recorder = _load_recorder()
    recording = {
        "schema_version": recorder.SCHEMA_VERSION,
        "events": [{"request_headers": {"Authorization": "secret"}}],
    }

    try:
        recorder.write_recording(tmp_path, recording)
    except ValueError as exc:
        assert "request_headers" in str(exc)
    else:
        raise AssertionError("forbidden recording fields were accepted")


def test_write_recording_does_not_overwrite_prior_recording(tmp_path: Path) -> None:
    recorder = _load_recorder()
    output_dir = tmp_path / "private"
    recording = {"schema_version": recorder.SCHEMA_VERSION, "events": []}
    recorder.write_recording(output_dir, recording)

    try:
        recorder.write_recording(output_dir, recording)
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("existing recording was overwritten")


def test_visible_chrome_session_explicitly_creates_headed_page_and_closes_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _load_recorder()
    calls: list[tuple[str, object]] = []

    class Page:
        async def bring_to_front(self) -> None:
            calls.append(("bring_to_front", None))

    class Context:
        pages: list[Page] = []

        async def new_page(self) -> Page:
            calls.append(("new_page", None))
            page = Page()
            self.pages.append(page)
            return page

        async def close(self) -> None:
            calls.append(("context_close", None))

    class Browser:
        context = Context()

        async def new_context(self, **kwargs: object) -> Context:
            calls.append(("new_context", kwargs))
            return self.context

        async def close(self) -> None:
            calls.append(("browser_close", None))

    class Chromium:
        browser = Browser()

        async def launch(self, **kwargs: object) -> Browser:
            calls.append(("launch", kwargs))
            return self.browser

    class Playwright:
        chromium = Chromium()

    monkeypatch.setattr(recorder.sys, "platform", "darwin")

    async def exercise() -> None:
        async with recorder._visible_chrome_session(Playwright(), "chrome"):
            calls.append(("yielded", None))

    asyncio.run(exercise())

    assert calls[0] == (
        "launch",
        {
            "channel": "chrome",
            "headless": False,
            "args": [
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-mode",
            ],
        },
    )
    assert calls[1] == (
        "new_context",
        {"accept_downloads": True, "no_viewport": True},
    )
    assert [name for name, _detail in calls] == [
        "launch",
        "new_context",
        "new_page",
        "bring_to_front",
        "yielded",
        "context_close",
        "browser_close",
    ]


def test_windows_browser_window_is_normalized_and_native_visibility_is_proven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _load_recorder()
    commands: list[tuple[str, object | None]] = []
    restored: list[int] = []

    class Page:
        async def bring_to_front(self) -> None:
            commands.append(("bring_to_front", None))

    class Session:
        async def send(
            self, command: str, arguments: object | None = None
        ) -> dict[str, int]:
            commands.append((command, arguments))
            return {"windowId": 41}

        async def detach(self) -> None:
            commands.append(("detach", None))

    class Context:
        async def new_cdp_session(self, _page: Page) -> Session:
            return Session()

    monkeypatch.setattr(recorder.sys, "platform", "win32")
    monkeypatch.setattr(
        recorder,
        "_windows_top_level_chrome_windows",
        lambda: {7, 11},
    )

    def restore(handle: int) -> bool:
        restored.append(handle)
        return True

    monkeypatch.setattr(recorder, "_restore_windows_chrome_window", restore)

    asyncio.run(recorder.present_browser_window(Context(), Page(), {7}))

    assert commands == [
        ("bring_to_front", None),
        ("Browser.getWindowForTarget", None),
        (
            "Browser.setWindowBounds",
            {
                "windowId": 41,
                "bounds": {
                    "windowState": "normal",
                    "left": 40,
                    "top": 40,
                    "width": 1200,
                    "height": 800,
                },
            },
        ),
        ("detach", None),
    ]
    assert restored == [11]


def test_windows_background_process_without_window_fails_before_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _load_recorder()
    monkeypatch.setattr(recorder.sys, "platform", "win32")
    monkeypatch.setattr(
        recorder,
        "_windows_top_level_chrome_windows",
        lambda: {7},
    )

    with pytest.raises(RuntimeError, match="prima dell'accesso"):
        asyncio.run(
            recorder._require_windows_desktop_window(
                {7},
                attempts=1,
                interval_seconds=0,
            )
        )


def test_studio_archive_skill_exposes_two_checkpoint_teaching_flow() -> None:
    skill = (STUDIO_ARCHIVE_ROOT / "skills" / "studio-archive" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "Teach Vera the Agenzia invoice-download flow" in skill
    assert "di' a voce oppure scrivi `pronto`" in skill
    assert "va bene anche `ready`" in skill
    assert "di' a voce oppure scrivi\n   `fatto`" in skill
    assert "va bene anche `done`" in skill
    assert "Do not read the JSON into model context" in skill
    assert "requirements-portal-recorder.txt" in skill


def test_vera_installs_recorder_optional_requirements_in_managed_module_runtime() -> (
    None
):
    requirements = (STUDIO_ARCHIVE_ROOT / "requirements-portal-recorder.txt").read_text(
        encoding="utf-8"
    )
    wrapper = (VERA_ROOT / "skills" / "studio-archive" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "playwright>=1.48.0" in requirements.splitlines()
    assert "--module studio-archive --requirements" in wrapper
    assert "requirements-portal-recorder.txt run" in wrapper
    assert "a missing-Playwright result is not a completed preflight" in wrapper
    assert "MPARANZA_NETWORK_PERMISSION_REQUIRED" in wrapper
    assert "Codex host network approval" in wrapper
    assert "Do not stop with a missing-Playwright diagnosis" in wrapper


def test_studio_archive_manifest_advertises_agenzia_teaching_route() -> None:
    manifest = json.loads(
        (STUDIO_ARCHIVE_ROOT / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["version"] == "0.1.19"
    assert "fatture-e-corrispettivi" in manifest["keywords"]
    assert "playwright" in manifest["keywords"]
    assert any(
        "Mostra a Vera" in prompt for prompt in manifest["interface"]["defaultPrompt"]
    )


def test_studio_archive_privacy_register_covers_agenzia_recording() -> None:
    privacy = json.loads(
        (
            ROOT
            / "plugins"
            / "vera"
            / "privacy"
            / "workstreams"
            / "studio-archive.json"
        ).read_text(encoding="utf-8")
    )
    boundaries = {item["id"]: item for item in privacy["external_boundaries"]}
    classes = {item["id"]: item for item in privacy["model_context"]["classes"]}
    controls = {item["id"]: item for item in privacy["security_controls"]}

    boundary = boundaries["codex-agenzia-invoice-flow-teaching"]
    assert boundary["optional"] is True
    assert boundary["requires_confirmation"] is True
    assert boundary["runtime_profiles"] == ["openai-codex"]
    assert "agenzia-flow-implementation-recording" in classes
    assert "privacy-bounded-agenzia-flow-recording" in controls
