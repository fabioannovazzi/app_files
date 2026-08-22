from __future__ import annotations

import asyncio
import importlib.util
import json
import stat
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
BROWSER_AUTOMATION_ROOT = ROOT / "plugins" / "browser-automation"
STUDIO_ARCHIVE_ROOT = ROOT / "plugins" / "studio-archive"
VERA_ROOT = ROOT / "plugins" / "vera"
RECORDER_PATH = BROWSER_AUTOMATION_ROOT / "scripts" / "record_agenzia_invoice_flow.py"


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


def test_present_browser_window_accepts_pointer_wrapped_native_window_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _load_recorder()
    restored: list[int] = []

    class Page:
        async def bring_to_front(self) -> None:
            return None

    class Session:
        async def send(
            self, command: str, _arguments: object | None = None
        ) -> dict[str, object]:
            if command == "Browser.getWindowForTarget":
                return {"windowId": 41}
            if command == "SystemInfo.getProcessInfo":
                return {"processInfo": [{"type": "browser", "id": 321}]}
            return {}

        async def detach(self) -> None:
            return None

    class Context:
        def __init__(self) -> None:
            self.browser = self

        async def new_cdp_session(self, _page: Page) -> Session:
            return Session()

        async def new_browser_cdp_session(self) -> Session:
            return Session()

    class NativeFunction:
        def __init__(self, implementation: object) -> None:
            self.implementation = implementation
            self.argtypes: object | None = None
            self.restype: object | None = None

        def __call__(self, *args: object) -> object:
            return self.implementation(*args)  # type: ignore[operator]

    class PointerHandle:
        value = 77

    def enum_windows(callback: object, parameter: object) -> object:
        return callback(PointerHandle(), parameter)  # type: ignore[operator]

    def get_class_name(
        _handle: object,
        class_name: object,
        _length: object,
    ) -> int:
        class_name.value = "Chrome_WidgetWin_1"  # type: ignore[attr-defined]
        return len(class_name.value)  # type: ignore[attr-defined]

    class User32:
        EnumWindows = NativeFunction(enum_windows)
        GetClassNameW = NativeFunction(get_class_name)
        GetWindowThreadProcessId = NativeFunction(
            lambda _handle, process_id: setattr(process_id._obj, "value", 321) or 1  # type: ignore[attr-defined]
        )

    import ctypes

    monkeypatch.setattr(recorder.sys, "platform", "win32")
    monkeypatch.setattr(
        ctypes, "WinDLL", lambda *_args, **_kwargs: User32(), raising=False
    )
    monkeypatch.setattr(
        ctypes,
        "WINFUNCTYPE",
        lambda *_args, **_kwargs: lambda callback: callback,
        raising=False,
    )
    monkeypatch.setattr(ctypes, "set_last_error", lambda _value: None, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
    monkeypatch.setattr(
        recorder,
        "_restore_windows_chrome_window",
        lambda handle: restored.append(handle) or True,
    )

    asyncio.run(recorder.present_browser_window(Context(), Page(), set()))

    assert restored == [77]


def test_present_browser_window_falls_back_when_enum_windows_has_no_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _load_recorder()
    restored: list[int] = []

    class Page:
        async def bring_to_front(self) -> None:
            return None

    class Session:
        async def send(
            self, command: str, _arguments: object | None = None
        ) -> dict[str, object]:
            if command == "Browser.getWindowForTarget":
                return {"windowId": 41}
            if command == "SystemInfo.getProcessInfo":
                return {"processInfo": [{"type": "browser", "id": 321}]}
            return {}

        async def detach(self) -> None:
            return None

    class Context:
        def __init__(self) -> None:
            self.browser = self

        async def new_cdp_session(self, _page: Page) -> Session:
            return Session()

        async def new_browser_cdp_session(self) -> Session:
            return Session()

    class NativeFunction:
        def __init__(self, implementation: object) -> None:
            self.implementation = implementation
            self.argtypes: object | None = None
            self.restype: object | None = None

        def __call__(self, *args: object) -> object:
            return self.implementation(*args)  # type: ignore[operator]

    class PointerHandle:
        def __init__(self, value: int | None) -> None:
            self.value = value

    def find_window(
        _desktop: object,
        previous: object,
        _class_name: object,
        _window_name: object,
    ) -> PointerHandle:
        previous_value = getattr(previous, "value", previous)
        if not previous_value:
            return PointerHandle(12)
        if previous_value == 12:
            return PointerHandle(77)
        return PointerHandle(None)

    def get_class_name(
        handle: object,
        class_name: object,
        _length: object,
    ) -> int:
        raw_handle = getattr(handle, "value", handle)
        class_name.value = (  # type: ignore[attr-defined]
            "Chrome_WidgetWin_1" if raw_handle == 77 else "OtherWindow"
        )
        return len(class_name.value)  # type: ignore[attr-defined]

    class User32:
        EnumWindows = NativeFunction(lambda *_args: False)
        GetClassNameW = NativeFunction(get_class_name)
        GetWindowThreadProcessId = NativeFunction(
            lambda _handle, process_id: setattr(process_id._obj, "value", 321) or 1  # type: ignore[attr-defined]
        )
        GetDesktopWindow = NativeFunction(lambda: PointerHandle(1))
        FindWindowExW = NativeFunction(find_window)

    import ctypes

    monkeypatch.setattr(recorder.sys, "platform", "win32")
    monkeypatch.setattr(
        ctypes, "WinDLL", lambda *_args, **_kwargs: User32(), raising=False
    )
    monkeypatch.setattr(
        ctypes,
        "WINFUNCTYPE",
        lambda *_args, **_kwargs: lambda callback: callback,
        raising=False,
    )
    monkeypatch.setattr(ctypes, "set_last_error", lambda _value: None, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
    monkeypatch.setattr(
        recorder,
        "_restore_windows_chrome_window",
        lambda handle: restored.append(handle) or True,
    )

    asyncio.run(recorder.present_browser_window(Context(), Page(), set()))

    assert restored == [77]


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
        ) -> dict[str, object]:
            commands.append((command, arguments))
            if command == "SystemInfo.getProcessInfo":
                return {"processInfo": [{"type": "browser", "id": 321}]}
            return {"windowId": 41}

        async def detach(self) -> None:
            commands.append(("detach", None))

    class Context:
        def __init__(self) -> None:
            self.browser = self

        async def new_cdp_session(self, _page: Page) -> Session:
            return Session()

        async def new_browser_cdp_session(self) -> Session:
            return Session()

    monkeypatch.setattr(recorder.sys, "platform", "win32")
    monkeypatch.setattr(
        recorder,
        "_windows_top_level_chrome_windows",
        lambda browser_process_ids=None: (
            {7, 11} if browser_process_ids is None else {11}
        ),
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
        ("SystemInfo.getProcessInfo", None),
        ("detach", None),
        ("detach", None),
    ]
    assert restored == [11]


def test_present_browser_window_uses_browser_target_for_process_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _load_recorder()
    page_commands: list[str] = []
    browser_commands: list[str] = []

    class Page:
        async def bring_to_front(self) -> None:
            return None

    class PageSession:
        async def send(
            self, command: str, _arguments: object | None = None
        ) -> dict[str, object]:
            page_commands.append(command)
            if command == "SystemInfo.getProcessInfo":
                raise RuntimeError(
                    "SystemInfo.getProcessInfo is only supported on the browser target"
                )
            return {"windowId": 41}

        async def detach(self) -> None:
            return None

    class BrowserSession:
        async def send(
            self, command: str, _arguments: object | None = None
        ) -> dict[str, object]:
            browser_commands.append(command)
            return {"processInfo": [{"type": "browser", "id": 321}]}

        async def detach(self) -> None:
            return None

    class Browser:
        async def new_browser_cdp_session(self) -> BrowserSession:
            return BrowserSession()

    class Context:
        browser = Browser()

        async def new_cdp_session(self, _page: Page) -> PageSession:
            return PageSession()

    monkeypatch.setattr(recorder.sys, "platform", "win32")
    monkeypatch.setattr(
        recorder,
        "_windows_top_level_chrome_windows",
        lambda _browser_process_ids=None: {11},
    )
    monkeypatch.setattr(
        recorder,
        "_restore_windows_chrome_window",
        lambda _handle: True,
    )

    asyncio.run(recorder.present_browser_window(Context(), Page(), set()))

    assert page_commands == [
        "Browser.getWindowForTarget",
        "Browser.setWindowBounds",
    ]
    assert browser_commands == ["SystemInfo.getProcessInfo"]


def test_windows_background_process_without_window_fails_before_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _load_recorder()
    monkeypatch.setattr(recorder.sys, "platform", "win32")
    monkeypatch.setattr(
        recorder,
        "_windows_top_level_chrome_windows",
        lambda _browser_process_ids=None: {7},
    )

    with pytest.raises(RuntimeError, match="prima dell'accesso"):
        asyncio.run(
            recorder._require_windows_desktop_window(
                {7},
                {321},
                attempts=1,
                interval_seconds=0,
            )
        )


@pytest.mark.parametrize("confirmation", ["visibile", "VISIBLE"])
def test_operator_visibility_confirmation_accepts_explicit_visible_response(
    monkeypatch: pytest.MonkeyPatch,
    confirmation: str,
) -> None:
    recorder = _load_recorder()

    async def respond(_function: object, _prompt: str) -> str:
        return confirmation

    monkeypatch.setattr(recorder.sys, "platform", "win32")
    monkeypatch.setattr(recorder.asyncio, "to_thread", respond)

    asyncio.run(recorder.confirm_operator_visible_browser())


@pytest.mark.parametrize("confirmation", ["", "stop"])
def test_operator_visibility_confirmation_stops_before_authentication(
    monkeypatch: pytest.MonkeyPatch,
    confirmation: str,
) -> None:
    recorder = _load_recorder()

    async def respond(_function: object, _prompt: str) -> str:
        return confirmation

    monkeypatch.setattr(recorder.sys, "platform", "win32")
    monkeypatch.setattr(recorder.asyncio, "to_thread", respond)

    with pytest.raises(RuntimeError, match="prima dell'accesso"):
        asyncio.run(recorder.confirm_operator_visible_browser())


def test_unrelated_chrome_window_cannot_satisfy_visibility_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _load_recorder()
    observed_process_filters: list[set[int] | None] = []

    class Page:
        async def bring_to_front(self) -> None:
            return None

    class Session:
        async def send(
            self, command: str, _arguments: object | None = None
        ) -> dict[str, object]:
            if command == "Browser.getWindowForTarget":
                return {"windowId": 41}
            if command == "SystemInfo.getProcessInfo":
                return {"processInfo": [{"type": "browser", "id": 321}]}
            return {}

        async def detach(self) -> None:
            return None

    class Context:
        def __init__(self) -> None:
            self.browser = self

        async def new_cdp_session(self, _page: Page) -> Session:
            return Session()

        async def new_browser_cdp_session(self) -> Session:
            return Session()

    monkeypatch.setattr(recorder.sys, "platform", "win32")

    def windows(browser_process_ids: set[int] | None = None) -> set[int]:
        observed_process_filters.append(browser_process_ids)
        return {91} if browser_process_ids is None else set()

    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr(recorder, "_windows_top_level_chrome_windows", windows)
    monkeypatch.setattr(recorder.asyncio, "sleep", no_wait)
    monkeypatch.setattr(
        recorder,
        "_restore_windows_chrome_window",
        lambda _handle: True,
    )

    with pytest.raises(RuntimeError, match="prima dell'accesso"):
        asyncio.run(recorder.present_browser_window(Context(), Page(), set()))

    assert observed_process_filters == [{321}] * 30


def test_browser_automation_skill_exposes_two_checkpoint_teaching_flow() -> None:
    skill = (
        BROWSER_AUTOMATION_ROOT / "skills" / "browser-automation" / "SKILL.md"
    ).read_text(encoding="utf-8")
    normalized_skill = " ".join(skill.split())

    assert "Supported procedure: Agenzia invoice flow" in skill
    assert "di' a voce oppure scrivi `pronto`" in normalized_skill
    assert "va bene anche `ready`" in normalized_skill
    assert "di' `visibile`" in normalized_skill
    assert "never infer visibility" in normalized_skill
    assert "di' a voce oppure scrivi `fatto`" in normalized_skill
    assert "va bene anche `done`" in normalized_skill
    assert "Do not read the JSON into model context" in skill
    assert "requirements-portal-recorder.txt" in skill


def test_vera_installs_recorder_optional_requirements_in_managed_module_runtime() -> (
    None
):
    requirements = (
        BROWSER_AUTOMATION_ROOT / "requirements-portal-recorder.txt"
    ).read_text(encoding="utf-8")
    wrapper = (VERA_ROOT / "skills" / "browser-automation" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    normalized_wrapper = " ".join(wrapper.split())

    assert "playwright>=1.48.0" in requirements.splitlines()
    assert "--module browser-automation --requirements" in normalized_wrapper
    assert "requirements-portal-recorder.txt run" in normalized_wrapper
    assert "starts the recorder in the same process" in normalized_wrapper
    assert "split setup and recorder launch into separate commands" in (
        normalized_wrapper
    )
    assert (
        "scripts/check_dependencies.py\n   --module browser-automation" not in wrapper
    )
    assert "missing-Playwright result is not a completed preflight" in (
        normalized_wrapper
    )
    assert "MPARANZA_NETWORK_PERMISSION_REQUIRED" in normalized_wrapper
    assert "Codex host network approval" in normalized_wrapper
    assert "Do not stop with a missing-Playwright diagnosis" in normalized_wrapper


def test_browser_automation_manifest_advertises_agenzia_teaching_route() -> None:
    manifest = json.loads(
        (BROWSER_AUTOMATION_ROOT / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["version"] == "0.1.2"
    assert "fatture-e-corrispettivi" in manifest["keywords"]
    assert "playwright" in manifest["keywords"]
    assert any(
        "Mostra a Vera" in prompt for prompt in manifest["interface"]["defaultPrompt"]
    )


def test_browser_automation_privacy_register_covers_agenzia_recording() -> None:
    privacy = json.loads(
        (
            ROOT
            / "plugins"
            / "vera"
            / "privacy"
            / "workstreams"
            / "browser-automation.json"
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


def test_studio_archive_no_longer_owns_agenzia_recorder() -> None:
    studio_skill = (
        STUDIO_ARCHIVE_ROOT / "skills" / "studio-archive" / "SKILL.md"
    ).read_text(encoding="utf-8")
    studio_manifest = json.loads(
        (STUDIO_ARCHIVE_ROOT / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )

    assert "Agenzia invoice-flow teaching" not in studio_skill
    assert "record_agenzia_invoice_flow.py" not in studio_skill
    assert not (STUDIO_ARCHIVE_ROOT / "requirements-portal-recorder.txt").exists()
    assert not (STUDIO_ARCHIVE_ROOT / "scripts" / RECORDER_PATH.name).exists()
    assert "playwright" not in studio_manifest["keywords"]
