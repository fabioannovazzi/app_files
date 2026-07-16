from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def suppress_fastexcel_dtype_warnings() -> Iterator[None]:
    """Temporarily silence fastexcel dtype warnings emitted by polars.read_excel."""

    logger = logging.getLogger("fastexcel.types.dtype")
    previous_level = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(previous_level)
