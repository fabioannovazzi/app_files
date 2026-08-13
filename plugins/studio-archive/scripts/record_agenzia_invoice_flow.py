#!/usr/bin/env python3
"""Record a privacy-bounded Agenzia invoice-download interaction for Vera.

The recorder deliberately captures only mechanically useful UI structure. It
never records typed values, cookies, browser storage, HTML, screenshots,
request headers or bodies, or downloaded invoice bytes. This deterministic
boundary is justified because the excluded data classes are mechanically
identifiable and must not enter the implementation handoff.
"""

from __future__ import annotations

__all__ = [
    "ALLOWED_HOST_SUFFIX",
    "PORTAL_URL",
    "build_download_record",
    "is_allowed_url",
    "present_browser_window",
    "redact_text",
    "sanitize_element",
    "sanitize_url",
    "write_recording",
]

import argparse
import asyncio
import getpass
import hashlib
import json
import logging
import os
import re
import stat
import sys
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

LOGGER = logging.getLogger("agenzia-invoice-flow-recorder")

PORTAL_URL = "https://ivaservizi.agenziaentrate.gov.it/portale/"
ALLOWED_HOST_SUFFIX = ".agenziaentrate.gov.it"
SCHEMA_VERSION = "agenzia_invoice_flow_recording.v1"
MAX_TEXT_LENGTH = 180
MAX_INVENTORY_CONTROLS = 160

_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
_ITALIAN_TAX_CODE_RE = re.compile(
    r"(?i)\b[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}"
    r"[A-Z][0-9LMNPQRSTUV]{3}[A-Z]\b"
)
_ITALIAN_VAT_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")
_IBAN_RE = re.compile(r"(?i)\bIT\d{2}[A-Z]\d{10}[A-Z0-9]{12}\b")
_LONG_NUMBER_RE = re.compile(r"(?<!\w)\d{4,}(?!\w)")
_OPAQUE_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._~-]{24,}$")
_WHITESPACE_RE = re.compile(r"\s+")

_WINDOW_LEFT = 40
_WINDOW_TOP = 40
_WINDOW_WIDTH = 1200
_WINDOW_HEIGHT = 800

_ELEMENT_KEYS = {
    "event_type",
    "tag",
    "role",
    "accessible_name",
    "aria_label",
    "label",
    "placeholder",
    "title",
    "id",
    "name",
    "input_type",
    "href",
    "region",
}

_FORBIDDEN_RECORD_KEYS = {
    "value",
    "input_value",
    "password",
    "cookie",
    "cookies",
    "local_storage",
    "session_storage",
    "html",
    "outer_html",
    "inner_html",
    "request_headers",
    "response_headers",
    "request_body",
    "response_body",
    "download_path",
    "download_bytes",
}

_RECORDER_SCRIPT = r"""
(() => {
  if (window.__mparanzaAgenziaRecorderInstalled) return;
  window.__mparanzaAgenziaRecorderInstalled = true;

  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim().slice(0, 500);
  const labelFor = (element) => {
    if (!element) return "";
    if (element.labels && element.labels.length) {
      return clean(Array.from(element.labels).map((label) => label.innerText).join(" "));
    }
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
      return clean(labelledBy.split(/\s+/).map((id) => {
        const label = document.getElementById(id);
        return label ? label.innerText : "";
      }).join(" "));
    }
    return "";
  };
  const implicitRole = (element) => {
    const tag = element.tagName.toLowerCase();
    if (tag === "button") return "button";
    if (tag === "a" && element.hasAttribute("href")) return "link";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {
      const type = (element.getAttribute("type") || "text").toLowerCase();
      if (["button", "submit", "reset"].includes(type)) return "button";
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      return "textbox";
    }
    return "";
  };
  const describe = (eventType, originalTarget) => {
    const element = originalTarget && originalTarget.closest
      ? originalTarget.closest("a,button,input,select,textarea,[role],[tabindex]")
      : null;
    if (!element) return null;
    const tag = element.tagName.toLowerCase();
    const inTable = Boolean(element.closest("table,[role='table'],[role='grid'],[role='row']"));
    const label = inTable ? "" : labelFor(element);
    const ariaLabel = inTable ? "" : clean(element.getAttribute("aria-label"));
    const text = inTable ? "" : clean(element.innerText || element.textContent);
    const placeholder = inTable ? "" : clean(element.getAttribute("placeholder"));
    const title = inTable ? "" : clean(element.getAttribute("title"));
    return {
      event_type: eventType,
      tag,
      role: clean(element.getAttribute("role")) || implicitRole(element),
      accessible_name: ariaLabel || label || text || placeholder || title,
      aria_label: ariaLabel,
      label,
      placeholder,
      title,
      id: clean(element.id),
      name: clean(element.getAttribute("name")),
      input_type: clean(element.getAttribute("type")),
      href: tag === "a" ? clean(element.href) : "",
      region: inTable ? "table" : "page",
    };
  };
  const emit = (eventType, target) => {
    const payload = describe(eventType, target);
    if (payload && window.__mparanzaRecordAgenziaAction) {
      window.__mparanzaRecordAgenziaAction(payload);
    }
  };
  document.addEventListener("click", (event) => emit("click", event.target), true);
  document.addEventListener("change", (event) => emit("change", event.target), true);
})();
"""

_INVENTORY_SCRIPT = r"""
(elements) => elements.slice(0, 160).map((element) => {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim().slice(0, 500);
  const tag = element.tagName.toLowerCase();
  const inTable = Boolean(element.closest("table,[role='table'],[role='grid'],[role='row']"));
  let label = "";
  if (!inTable && element.labels && element.labels.length) {
    label = clean(Array.from(element.labels).map((item) => item.innerText).join(" "));
  }
  const ariaLabel = inTable ? "" : clean(element.getAttribute("aria-label"));
  const text = inTable ? "" : clean(element.innerText || element.textContent);
  const placeholder = inTable ? "" : clean(element.getAttribute("placeholder"));
  const title = inTable ? "" : clean(element.getAttribute("title"));
  let role = clean(element.getAttribute("role"));
  if (!role && tag === "button") role = "button";
  if (!role && tag === "a" && element.hasAttribute("href")) role = "link";
  if (!role && tag === "select") role = "combobox";
  if (!role && ["input", "textarea"].includes(tag)) role = "textbox";
  return {
    tag,
    role,
    accessible_name: ariaLabel || label || text || placeholder || title,
    aria_label: ariaLabel,
    label,
    placeholder,
    title,
    id: clean(element.id),
    name: clean(element.getAttribute("name")),
    input_type: clean(element.getAttribute("type")),
    href: tag === "a" ? clean(element.href) : "",
    region: inTable ? "table" : "page",
  };
})
"""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _hostname(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").casefold()
    except ValueError:
        return ""


def is_allowed_url(url: str) -> bool:
    """Return whether a URL is an exact Agenzia HTTPS origin."""

    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and (
        host == "agenziaentrate.gov.it" or host.endswith(ALLOWED_HOST_SUFFIX)
    )


def sanitize_url(url: str) -> str:
    """Keep only an allowed HTTPS origin and path, excluding query and fragment."""

    if not is_allowed_url(url):
        return "<blocked-origin>"
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    sanitized_segments: list[str] = []
    for segment in (parsed.path or "/").split("/"):
        redacted = _ITALIAN_TAX_CODE_RE.sub("<tax-id>", segment)
        redacted = _ITALIAN_VAT_RE.sub("<vat-id>", redacted)
        redacted = _LONG_NUMBER_RE.sub("<number>", redacted)
        if _OPAQUE_PATH_SEGMENT_RE.fullmatch(redacted) and any(
            character.isdigit() for character in redacted
        ):
            redacted = "<opaque-id>"
        sanitized_segments.append(redacted)
    path = "/".join(sanitized_segments) or "/"
    return urlunsplit(("https", f"{host}{port}", path, "", ""))


def redact_text(value: Any, redactions: Sequence[str] = ()) -> str:
    """Redact common identifiers and operator-supplied private terms."""

    text = _WHITESPACE_RE.sub(" ", str(value or "")).strip()
    for private_term in sorted(
        (term.strip() for term in redactions if term.strip()),
        key=len,
        reverse=True,
    ):
        text = re.sub(re.escape(private_term), "<private>", text, flags=re.IGNORECASE)
    text = _EMAIL_RE.sub("<email>", text)
    text = _IBAN_RE.sub("<iban>", text)
    text = _ITALIAN_TAX_CODE_RE.sub("<tax-id>", text)
    text = _ITALIAN_VAT_RE.sub("<vat-id>", text)
    text = _LONG_NUMBER_RE.sub("<number>", text)
    return text[:MAX_TEXT_LENGTH]


def sanitize_element(
    raw: Mapping[str, Any], redactions: Sequence[str] = ()
) -> dict[str, str]:
    """Return the fixed, value-free element description allowed in a recording."""

    sanitized: dict[str, str] = {}
    for key in sorted(_ELEMENT_KEYS):
        if key not in raw:
            continue
        value = raw[key]
        if key == "href":
            sanitized[key] = sanitize_url(str(value)) if value else ""
        else:
            sanitized[key] = redact_text(value, redactions)
    return sanitized


def build_download_record(download: Any, page_url: str) -> dict[str, Any]:
    """Record download shape without persisting its name, path, or bytes."""

    suggested_name = str(getattr(download, "suggested_filename", "") or "")
    suffixes = [suffix.casefold() for suffix in Path(suggested_name).suffixes[-2:]]
    return {
        "observed_at": _utc_now(),
        "page_url": sanitize_url(page_url),
        "suggested_name_sha256": hashlib.sha256(
            suggested_name.encode("utf-8")
        ).hexdigest(),
        "suffixes": suffixes,
        "content_saved": False,
    }


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _validate_recording(recording: Mapping[str, Any]) -> None:
    forbidden = sorted(set(_walk_keys(recording)) & _FORBIDDEN_RECORD_KEYS)
    if forbidden:
        raise ValueError(f"recording contains forbidden fields: {', '.join(forbidden)}")
    if recording.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("recording schema version is invalid")


def write_recording(output_dir: Path, recording: Mapping[str, Any]) -> Path:
    """Atomically write an owner-only JSON recording."""

    _validate_recording(recording)
    expanded = output_dir.expanduser()
    if expanded.exists() and expanded.is_symlink():
        raise ValueError("output directory cannot be a symbolic link")
    if expanded.exists():
        if not expanded.is_dir():
            raise ValueError("output directory must be a directory")
        if stat.S_IMODE(expanded.stat().st_mode) & 0o077:
            raise ValueError("existing output directory must be owner-only")
    else:
        expanded.mkdir(parents=True, exist_ok=False, mode=0o700)
    target = expanded / "agenzia_invoice_flow_recording.json"
    if target.exists():
        raise ValueError(
            "recording target already exists; choose a new output directory"
        )
    temporary = expanded / f".{target.name}.{os.getpid()}.tmp"
    payload = json.dumps(recording, indent=2, ensure_ascii=False) + "\n"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
        target.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


class AgenziaFlowRecorder:
    """Collect sanitized page transitions and user-selected control identities."""

    def __init__(self, context: Any, redactions: Sequence[str]) -> None:
        self.context = context
        self.redactions = tuple(redactions)
        self.active = False
        self.events: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []
        self.downloads: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self._tasks: set[asyncio.Task[Any]] = set()
        self._attached_pages: set[int] = set()

    def _schedule(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def begin(self) -> None:
        await self.context.expose_binding(
            "__mparanzaRecordAgenziaAction", self._receive_action
        )
        await self.context.add_init_script(_RECORDER_SCRIPT)
        self.active = True
        self.context.on("page", self._on_page)
        for page in self.context.pages:
            await self._attach_page(page)

    async def stop(self) -> None:
        self.active = False
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    async def _attach_page(self, page: Any) -> None:
        page_key = id(page)
        if page_key in self._attached_pages:
            return
        self._attached_pages.add(page_key)
        page.on("download", lambda download: self._on_download(page, download))
        page.on("framenavigated", lambda frame: self._on_navigation(page, frame))
        if is_allowed_url(page.url):
            try:
                await page.evaluate(_RECORDER_SCRIPT)
            except (RuntimeError, TypeError):
                LOGGER.debug("Recorder injection will retry after navigation.")
            await self.capture_snapshot(page, "recording_started")

    def _on_page(self, page: Any) -> None:
        self._schedule(self._attach_page(page))

    def _on_navigation(self, page: Any, frame: Any) -> None:
        if not self.active or frame != page.main_frame:
            return
        if not is_allowed_url(page.url):
            self.active = False
            self.warnings.append(
                "La registrazione si è fermata automaticamente perché la pagina "
                "ha lasciato l'origine HTTPS consentita dell'Agenzia delle Entrate."
            )
            LOGGER.warning(self.warnings[-1])
            return
        self.events.append(
            {
                "sequence": len(self.events) + 1,
                "observed_at": _utc_now(),
                "kind": "navigation",
                "page_url": sanitize_url(page.url),
            }
        )
        self._schedule(self._capture_after_settle(page, "navigation"))

    def _on_download(self, page: Any, download: Any) -> None:
        if not self.active or not is_allowed_url(page.url):
            return
        self.downloads.append(build_download_record(download, page.url))

    async def _receive_action(self, source: Mapping[str, Any], payload: Any) -> None:
        if not self.active or not isinstance(payload, Mapping):
            return
        page = source.get("page")
        if page is None or not is_allowed_url(page.url):
            self.active = False
            self.warnings.append(
                "Un evento di controllo proviene da un'origine Agenzia non "
                "consentita; registrazione interrotta."
            )
            return
        self.events.append(
            {
                "sequence": len(self.events) + 1,
                "observed_at": _utc_now(),
                "kind": "control_action",
                "page_url": sanitize_url(page.url),
                "control": sanitize_element(payload, self.redactions),
            }
        )
        self._schedule(self._capture_after_settle(page, "control_action"))

    async def _capture_after_settle(self, page: Any, reason: str) -> None:
        try:
            await page.wait_for_timeout(600)
            await self.capture_snapshot(page, reason)
        except (RuntimeError, TypeError):
            LOGGER.debug("Page changed before its sanitized inventory was available.")

    async def capture_snapshot(self, page: Any, reason: str) -> None:
        if not self.active or not is_allowed_url(page.url):
            return
        try:
            raw_controls = await page.locator(
                "a,button,input,select,textarea,[role],[tabindex]"
            ).evaluate_all(_INVENTORY_SCRIPT)
            title = await page.title()
        except (RuntimeError, TypeError):
            return
        controls: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw in raw_controls[:MAX_INVENTORY_CONTROLS]:
            if not isinstance(raw, Mapping):
                continue
            control = sanitize_element(raw, self.redactions)
            digest = hashlib.sha256(
                json.dumps(control, sort_keys=True).encode("utf-8")
            ).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            controls.append(control)
        self.snapshots.append(
            {
                "sequence": len(self.snapshots) + 1,
                "observed_at": _utc_now(),
                "reason": reason,
                "page_url": sanitize_url(page.url),
                "page_title": redact_text(title, self.redactions),
                "controls": controls,
            }
        )

    def build_recording(self, started_at: str) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": _utc_now(),
            "recording_started_at": started_at,
            "purpose": (
                "Rilevazione tecnica per realizzare un flusso guidato di download "
                "delle fatture dall'Agenzia delle Entrate."
            ),
            "capture_boundary": {
                "allowed_https_host_suffix": ALLOWED_HOST_SUFFIX,
                "captured": [
                    "sanitized control identities",
                    "origin-and-path-only page transitions",
                    "sanitized interactive-control inventories",
                    "hashed download names and filename suffixes",
                ],
                "excluded": [
                    "credentials and one-time codes",
                    "typed or selected field values",
                    "cookies and browser storage",
                    "HTML and page source",
                    "screenshots",
                    "network headers, query strings, and bodies",
                    "download paths, invoice bytes, and invoice contents",
                ],
                "operator_private_terms_configured": bool(self.redactions),
            },
            "events": self.events,
            "snapshots": self.snapshots,
            "downloads": self.downloads,
            "warnings": self.warnings,
            "review_before_sharing": {
                "required": True,
                "share_only": "agenzia_invoice_flow_recording.json",
                "instruction": (
                    "Apri e controlla il JSON. Eliminalo invece di condividerlo se "
                    "sono visibili dati di clienti, contribuenti, credenziali, "
                    "fatture o sessioni. Non condividere mai il profilo temporaneo "
                    "del browser."
                ),
            },
        }


def _private_redactions() -> tuple[str, ...]:
    LOGGER.info(
        "Facoltativo: inserisci nomi di clienti o altre diciture riservate che "
        "potrebbero apparire nel portale. Separa più termini con |. Rimarranno "
        "soltanto in memoria."
    )
    entered = getpass.getpass("Termini riservati da oscurare (oppure premi Invio): ")
    return tuple(term.strip() for term in entered.split("|") if term.strip())


def _windows_top_level_chrome_windows() -> set[int]:
    """Return Chrome top-level window handles on the interactive Windows desktop."""

    if sys.platform != "win32":
        return set()

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    enum_callback = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM,
    )
    user32.EnumWindows.argtypes = [enum_callback, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetClassNameW.argtypes = [
        wintypes.HWND,
        wintypes.LPWSTR,
        ctypes.c_int,
    ]
    user32.GetClassNameW.restype = ctypes.c_int
    handles: set[int] = set()

    @enum_callback
    def collect(handle: int, _parameter: int) -> bool:
        class_name = ctypes.create_unicode_buffer(256)
        if user32.GetClassNameW(handle, class_name, len(class_name)) > 0:
            if class_name.value.startswith("Chrome_WidgetWin_"):
                handles.add(int(handle))
        return True

    if not user32.EnumWindows(collect, 0):
        error_code = ctypes.get_last_error()
        raise OSError(error_code, "Impossibile enumerare le finestre di Windows")
    return handles


def _restore_windows_chrome_window(handle: int) -> bool:
    """Restore one Chrome HWND and verify a visible non-empty desktop rectangle."""

    if sys.platform != "win32":
        return True

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL

    window = wintypes.HWND(handle)
    user32.ShowWindow(window, 9)  # SW_RESTORE
    positioned = user32.SetWindowPos(
        window,
        wintypes.HWND(0),
        _WINDOW_LEFT,
        _WINDOW_TOP,
        _WINDOW_WIDTH,
        _WINDOW_HEIGHT,
        0x0040,  # SWP_SHOWWINDOW
    )
    user32.SetForegroundWindow(window)
    rectangle = wintypes.RECT()
    measured = user32.GetWindowRect(window, ctypes.byref(rectangle))
    return bool(
        positioned
        and measured
        and user32.IsWindowVisible(window)
        and rectangle.right > rectangle.left
        and rectangle.bottom > rectangle.top
    )


async def _require_windows_desktop_window(
    preexisting_windows: set[int],
    *,
    attempts: int = 30,
    interval_seconds: float = 0.1,
) -> None:
    """Fail before authentication unless a new visible Chrome HWND is proven."""

    if sys.platform != "win32":
        return
    for _attempt in range(attempts):
        new_windows = _windows_top_level_chrome_windows() - preexisting_windows
        if any(_restore_windows_chrome_window(handle) for handle in new_windows):
            return
        await asyncio.sleep(interval_seconds)
    raise RuntimeError(
        "Chrome è stato avviato, ma Windows non ha esposto una finestra visibile "
        "sul desktop corrente. La registrazione si è fermata prima dell'accesso."
    )


async def present_browser_window(
    context: Any,
    page: Any,
    preexisting_windows: set[int],
) -> None:
    """Create a mechanically verified, operator-visible browser presentation."""

    await page.bring_to_front()
    if sys.platform != "win32":
        return
    session = await context.new_cdp_session(page)
    try:
        result = await session.send("Browser.getWindowForTarget")
        window_id = result.get("windowId") if isinstance(result, Mapping) else None
        if not isinstance(window_id, int):
            raise RuntimeError(
                "Chrome non ha restituito una finestra controllabile; la "
                "registrazione si è fermata prima dell'accesso."
            )
        await session.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {
                    "windowState": "normal",
                    "left": _WINDOW_LEFT,
                    "top": _WINDOW_TOP,
                    "width": _WINDOW_WIDTH,
                    "height": _WINDOW_HEIGHT,
                },
            },
        )
    finally:
        await session.detach()
    await _require_windows_desktop_window(preexisting_windows)


@asynccontextmanager
async def _visible_chrome_session(
    playwright: Any,
    browser_channel: str,
) -> AsyncIterator[tuple[Any, Any]]:
    """Open an ephemeral headed Chrome context and close all local browser state."""

    preexisting_windows = _windows_top_level_chrome_windows()
    browser = await playwright.chromium.launch(
        channel=browser_channel,
        headless=False,
        args=[
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-mode",
        ],
    )
    context = None
    try:
        context = await browser.new_context(
            accept_downloads=True,
            no_viewport=True,
        )
        page = await context.new_page()
        await present_browser_window(context, page, preexisting_windows)
        yield context, page
    finally:
        if context is not None:
            await context.close()
        await browser.close()


async def _run(args: argparse.Namespace) -> Path:
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright non è disponibile. Installa prima i requisiti del plugin."
        ) from exc

    redactions = _private_redactions()
    started_at = ""
    recording: dict[str, Any] | None = None

    async with async_playwright() as playwright:
        try:
            async with _visible_chrome_session(
                playwright,
                args.browser_channel,
            ) as (context, page):
                await page.goto(PORTAL_URL, wait_until="domcontentloaded")
                LOGGER.info(
                    "Accedi personalmente, seleziona il contribuente o la delega "
                    "corretta e raggiungi Fatture e Corrispettivi. Non proseguire "
                    "se sono ancora visibili password, PIN, codice QR, codice "
                    "monouso o un'altra schermata di autenticazione. Quando hai "
                    "finito, di' a voce oppure scrivi 'pronto' a Vera; va bene "
                    "anche 'ready'."
                )
                await asyncio.to_thread(
                    input,
                    "Vera è in attesa di 'pronto' o 'ready' (poi premerà Invio): ",
                )

                eligible_pages = [
                    item for item in context.pages if is_allowed_url(item.url)
                ]
                if not eligible_pages:
                    raise RuntimeError(
                        "Non è aperta alcuna pagina autenticata dell'Agenzia delle "
                        "Entrate; non è stato registrato nulla."
                    )
                recorder = AgenziaFlowRecorder(context, redactions)
                await recorder.begin()
                started_at = _utc_now()
                LOGGER.info(
                    "Registrazione attiva. Esegui una volta il flusso di ricerca e "
                    "download delle fatture. I valori digitati e i file delle "
                    "fatture non saranno conservati. Alla fine, di' a voce oppure "
                    "scrivi 'fatto' a Vera; va bene anche 'done'."
                )
                await asyncio.to_thread(
                    input,
                    "Vera è in attesa di 'fatto' o 'done' (poi premerà Invio): ",
                )
                await recorder.stop()
                recording = recorder.build_recording(started_at)
        except PlaywrightError as exc:
            raise RuntimeError(
                f"Impossibile avviare e controllare il browser visibile "
                f"{args.browser_channel!r}. Installa Google Chrome oppure scegli "
                "un altro canale browser Playwright già installato."
            ) from exc

    if recording is None:
        raise RuntimeError("La registrazione non è stata completata.")
    return write_recording(args.output_dir, recording)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Registra una mappa tecnica e sanificata di un'interazione autenticata "
            "per il download delle fatture dall'Agenzia."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Cartella privata che riceverà il JSON da controllare.",
    )
    parser.add_argument(
        "--browser-channel",
        default="chrome",
        help="Canale browser Playwright installato (predefinito: chrome).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args(argv)
    try:
        target = asyncio.run(_run(args))
    except (OSError, RuntimeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Registrazione scritta in %s", target)
    LOGGER.info(
        "Controlla il JSON prima di condividerlo; non condividere il profilo "
        "del browser né ZIP di fatture."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
