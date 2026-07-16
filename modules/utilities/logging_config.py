"""Centralized logging configuration for API processes."""

from __future__ import annotations

import logging
import logging.config
import os
from pathlib import Path
from typing import Any, Dict

__all__ = ["configure_logging"]

_CONFIGURED = False


def configure_logging(app_name: str = "application") -> None:
    """Initialize logging with console + rotating file handlers."""

    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = os.environ.get("MPARANZA_LOG_LEVEL", "INFO").upper()
    log_dir = Path("logs")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # pragma: no cover - filesystem fallback
        log_dir = Path.cwd()
    log_file = log_dir / f"{app_name}.log"

    log_format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    logging_config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": log_format,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "default",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_level,
                "formatter": "default",
                "filename": str(log_file),
                "encoding": "utf-8",
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 5,
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["console", "file"],
        },
    }

    try:
        logging.config.dictConfig(logging_config)
    except Exception:  # pragma: no cover - fallback for read-only environments
        logging.basicConfig(level=log_level, format=log_format)
        logging.getLogger(__name__).warning(
            "Fell back to basic logging configuration; unable to use file handler at %s",
            log_file,
        )
    else:
        logging.getLogger(__name__).info("Logging configured (file=%s level=%s)", log_file, log_level)
    _CONFIGURED = True
