from __future__ import annotations

import io
import logging
from pathlib import Path

import pytest

from modules.utilities import logging_utils as lu
from modules.utilities.logging_utils import report_error, setup_logging


def _base_params(**overrides):
    params = {
        "log_to_console": False,
        "log_to_file": False,
        "log_file_max_bytes": 1024,
        "log_file_backup_count": 2,
        "show_user_errors": False,
    }
    params.update(overrides)
    return params


def test_setup_logging_console_only_uses_stderr_and_formats(monkeypatch):
    # Arrange
    stderr_capture = io.StringIO()
    monkeypatch.setattr(lu, "sys", type("_S", (), {"stderr": stderr_capture}))
    params = _base_params(log_to_console=True)

    # Act
    setup_logging(params)

    # Assert
    # exactly one stream handler attached to root
    handlers = logging.root.handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.StreamHandler)
    # logging goes to our patched stderr and contains the message
    logging.getLogger("test_logger").info("hello world")
    out = stderr_capture.getvalue()
    assert "hello world" in out
    assert "[INFO]" in out and "test_logger" in out


def test_setup_logging_no_handlers_when_all_disabled():
    # Arrange
    params = _base_params()

    # Act
    setup_logging(params)

    # Assert
    assert logging.root.level == logging.INFO
    assert logging.root.handlers == []


def test_setup_logging_file_handler_installed_with_params(monkeypatch):
    # Arrange: stub RotatingFileHandler to avoid filesystem writes
    created = {}

    class FakeRotating(logging.Handler):
        def __init__(self, filename, maxBytes, backupCount, encoding):  # noqa: N803
            super().__init__()
            created["filename"] = filename
            created["maxBytes"] = maxBytes
            created["backupCount"] = backupCount
            created["encoding"] = encoding

        def emit(self, record):  # pragma: no cover - not used here
            pass

    monkeypatch.setattr(lu, "RotatingFileHandler", FakeRotating)
    params = _base_params(log_to_file=True)

    # Act
    setup_logging(params)

    # Assert: a single handler added and parameters propagated
    handlers = logging.root.handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], FakeRotating)
    # verify rotating params echoed
    assert created["maxBytes"] == params["log_file_max_bytes"]
    assert created["backupCount"] == params["log_file_backup_count"]
    assert created["encoding"] == "utf-8"
    # filename ends with logs/app.log irrespective of absolute base
    fname = Path(created["filename"])  # handles both str and Path
    assert fname.name == "app.log"


def test_report_error_with_exception_logs_exception_and_shows_user(monkeypatch):
    # Arrange
    called = {"exception": None, "notifier_error": None}

    def fake_exception(msg, *args, **kwargs):
        called["exception"] = (msg, kwargs.get("exc_info"))

    class StubNotifier:
        def info(self, _message, **_kwargs):
            return None

        def warning(self, _message, **_kwargs):
            return None

        def error(self, message, **_kwargs):
            called["notifier_error"] = message

    monkeypatch.setattr(logging, "exception", fake_exception)
    params = _base_params(show_user_errors=True)
    exc = ValueError("bad")
    notifier = StubNotifier()

    # Act
    report_error("boom", exc=exc, run_params=params, notifier=notifier)

    # Assert
    assert called["exception"] == ("boom", exc)
    assert called["notifier_error"] == "boom"


def test_report_error_without_exception_logs_error_only(monkeypatch):
    # Arrange
    log_called = {"error": None, "notifier": False}

    def fake_error(msg):
        log_called["error"] = msg

    class StubNotifier:
        def info(self, _message, **_kwargs):
            return None

        def warning(self, _message, **_kwargs):
            return None

        def error(self, _message, **_kwargs):  # should not be called
            log_called["notifier"] = True

    monkeypatch.setattr(logging, "error", fake_error)
    params = _base_params(show_user_errors=False)
    notifier = StubNotifier()

    # Act
    report_error("oops", run_params=params, notifier=notifier)

    # Assert
    assert log_called["error"] == "oops"
    assert log_called["notifier"] is False


def test_setup_logging_suppresses_known_media_noise(monkeypatch):
    # Arrange
    stderr_capture = io.StringIO()
    monkeypatch.setattr(lu, "sys", type("_S", (), {"stderr": stderr_capture}))
    params = _base_params(log_to_console=True)
    setup_logging(params)
    noisy_logger = logging.getLogger("MediaFileHandler")

    # Act: emit known bot probe noise and an unrelated message
    noisy_logger.error("Missing file wp-includes/wlwmanifest.xml")
    noisy_logger.error("Missing file system/js/whatever.js")
    noisy_logger.error("Missing file legitimate-report.csv")

    # Assert: bot probes suppressed, legitimate message logged
    out = stderr_capture.getvalue()
    assert "wp-includes/wlwmanifest.xml" not in out
    assert "system/js/whatever.js" not in out
    assert "legitimate-report.csv" in out
