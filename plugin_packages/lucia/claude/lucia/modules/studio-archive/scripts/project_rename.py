"""Rename a project atomically without replacing another directory."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

__all__ = ["rename_without_replacement"]


def rename_without_replacement(source: Path, destination: Path) -> None:
    """Use the OS no-replace operation: a preflight exists check alone races."""
    if os.name == "nt":
        # Windows rename fails if the destination exists, including empty folders.
        source.rename(destination)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = rename(os.fsencode(source), os.fsencode(destination), 4)
    else:
        rename = libc.renameat2
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if result:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(destination))
