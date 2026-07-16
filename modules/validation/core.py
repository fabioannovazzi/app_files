"""
core.py – class-aware dispatcher that logs which scraper won
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Optional

from modules.utilities.config import get_run_params
from modules.utilities.logging_utils import report_error

# 🔹 import the wrapper classes you added at the bottom of layers.py
from modules.validation.layers import _postprocess  # your helper is still in layers.py
from modules.validation.layers import (
    ACTIVE_LAYERS,
)

LOGGER = logging.getLogger(__name__)


def extract_page(url: str, *, min_len: int = 100, debug: bool = True) -> Optional[str]:
    if debug:
        LOGGER.info("\n=== %s\n", url)
    cite = (
        urllib.parse.urlparse(url).fragment
        or url.rstrip("/").split("#")[-1].split("/")[-1]
    ).lower()

    for layer in ACTIVE_LAYERS:
        start = time.perf_counter()
        try:
            txt = layer(url, cite=cite)
        except Exception as e:  # noqa: BLE001
            logging.exception(e)
            LOGGER.warning("Layer %s crashed: %s", layer.name, e, exc_info=True)
            report_error("extract_page layer error", e, get_run_params())
            continue

        ms = (time.perf_counter() - start) * 1000
        if debug:
            LOGGER.info(f"[{layer.name:<18}] {'✔' if txt else '✖'} {ms:5.0f} ms")

        if txt and len(txt) >= min_len:
            LOGGER.info("HIT %s %.0f ms – %s", layer.name, ms, url)
            return _postprocess(txt)

        # ➋ tell us why the layer didn’t qualify
        if (
            layer.name == "PDFExtractor"
            and url.lower().endswith(".pdf")
            and (not txt or len(txt) < min_len)
        ):
            LOGGER.info("    • PDFExtractor returned empty or short text")

    LOGGER.error("NO_METHOD %s", url)

    return None


__all__ = ["ACTIVE_LAYERS", "extract_page"]
