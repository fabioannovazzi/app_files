from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from modules.utilities.notifier import Notifier, get_notifier

__all__ = ["setup_logging", "report_error"]

LOGGER = logging.getLogger(__name__)


_UI_PROBE_PATH_MARKERS = (
    "wp-includes/wlwmanifest",
    "system/js/",
)


class _SuppressUIMediaNoise(logging.Filter):
    """Filter out noisy UI media errors triggered by bot probes."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 - short and clear
        message = record.getMessage()
        if record.name == "MediaFileHandler" and any(
            marker in message for marker in _UI_PROBE_PATH_MARKERS
        ):
            return False
        if "MediaFileStorageError" in message and any(
            marker in message for marker in _UI_PROBE_PATH_MARKERS
        ):
            return False
        return True


def setup_logging(run_params: dict) -> None:
    """Configure root logging based on run parameters."""
    level = logging.INFO
    logging.root.handlers.clear()
    logging.root.filters.clear()
    logging.root.setLevel(level)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    suppress_filter = _SuppressUIMediaNoise()

    if run_params["log_to_console"]:
        ch = logging.StreamHandler(stream=sys.stderr)
        ch.setLevel(level)
        ch.setFormatter(formatter)
        ch.addFilter(suppress_filter)
        logging.root.addHandler(ch)

    if run_params["log_to_file"]:
        log_dir = Path(__file__).resolve().parents[2] / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_path = log_dir / "app.log"
        fh = RotatingFileHandler(
            file_path,
            maxBytes=run_params["log_file_max_bytes"],
            backupCount=run_params["log_file_backup_count"],
            encoding="utf-8",
        )
        fh.setLevel(level)
        fh.setFormatter(formatter)
        fh.addFilter(suppress_filter)
        logging.root.addHandler(fh)

    logging.captureWarnings(True)


def report_error(
    message: str,
    exc: Exception | None = None,
    run_params: dict | None = None,
    notifier: Notifier | None = None,
) -> None:
    """Log an exception and optionally show a user-facing error."""
    if exc is not None:
        logging.exception(message, exc_info=exc)
    else:
        logging.error(message)
    if run_params and run_params["show_user_errors"]:
        get_notifier(notifier, LOGGER).error(message)
