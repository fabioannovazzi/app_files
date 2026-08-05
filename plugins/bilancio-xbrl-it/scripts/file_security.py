#!/usr/bin/env python3
"""Host-injected malware scanner boundary for Bilancio source files.

The module never guesses that a file is clean. A deployment supplies an
executable command as a JSON array; the absolute file path is appended as one
argument and the command must exit successfully before parsing may continue.
"""

from __future__ import annotations

import json

# Deployment controls the argument vector; the adapter never invokes a shell.
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = ["CommandMalwareScanner", "scanner_from_json"]


@dataclass(frozen=True)
class CommandMalwareScanner:
    """Execute one host-controlled scanner command without invoking a shell."""

    command: tuple[str, ...]
    engine: str
    signature_version: str
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if not self.command or any(not item.strip() for item in self.command):
            raise ValueError("Scanner command must contain non-empty arguments")
        if not self.engine.strip() or not self.signature_version.strip():
            raise ValueError("Scanner engine and signature version are required")
        if not 1 <= self.timeout_seconds <= 600:
            raise ValueError("Scanner timeout must be from 1 to 600 seconds")

    def __call__(self, path: Path) -> Mapping[str, Any]:
        """Return a clean verdict only after the configured command succeeds."""

        # The exact host vector receives one separately appended file argument.
        completed = subprocess.run(  # nosec B603
            [*self.command, str(path)],
            capture_output=True,
            check=False,
            shell=False,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            raise ValueError(
                "Malware scanner rejected the file or could not establish a clean verdict"
            )
        return {
            "status": "CLEAN",
            "engine": self.engine,
            "signature_version": self.signature_version,
        }


def scanner_from_json(
    raw_command: str,
    *,
    engine: str,
    signature_version: str,
    timeout_seconds: int = 120,
) -> CommandMalwareScanner | None:
    """Build a scanner from a host-controlled JSON command array."""

    if not raw_command.strip():
        return None
    parsed = json.loads(raw_command)
    if (
        not isinstance(parsed, Sequence)
        or isinstance(parsed, (str, bytes))
        or not all(isinstance(item, str) for item in parsed)
    ):
        raise ValueError("Scanner command must be a JSON array of strings")
    return CommandMalwareScanner(
        tuple(parsed),
        engine=engine,
        signature_version=signature_version,
        timeout_seconds=timeout_seconds,
    )
