#!/usr/bin/env python3
"""Host-command adapter for queued, minimum-context intelligence tasks."""

from __future__ import annotations

import json

# Deployment controls the argument vector; the adapter never invokes a shell.
import subprocess  # nosec B404
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

__all__ = ["CommandIntelligenceRunner", "intelligence_runner_from_json"]

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class CommandIntelligenceRunner:
    """Send one JSON packet to a host-controlled command over standard input."""

    command: tuple[str, ...]
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if not self.command or any(not item.strip() for item in self.command):
            raise ValueError("Intelligence command must contain non-empty arguments")
        if not 1 <= self.timeout_seconds <= 600:
            raise ValueError("Intelligence timeout must be from 1 to 600 seconds")

    def __call__(self, packet: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return the strict host response without applying it to case state."""

        request = json.dumps(
            packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        # The exact host vector receives only the bounded JSON packet on stdin.
        completed = subprocess.run(  # nosec B603
            list(self.command),
            input=request,
            capture_output=True,
            check=False,
            shell=False,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Host intelligence command did not complete successfully"
            )
        if len(completed.stdout) > MAX_RESPONSE_BYTES:
            raise ValueError("Host intelligence response exceeds the size limit")
        response = json.loads(completed.stdout)
        if not isinstance(response, Mapping) or set(response) != {
            "output",
            "model_metadata",
        }:
            raise ValueError(
                "Host intelligence response requires output and model_metadata"
            )
        if not isinstance(response["output"], Mapping) or not isinstance(
            response["model_metadata"], Mapping
        ):
            raise ValueError("Host intelligence response fields must be objects")
        return response


def intelligence_runner_from_json(
    raw_command: str, *, timeout_seconds: int = 120
) -> CommandIntelligenceRunner | None:
    """Build a no-shell runner from a host-controlled JSON command array."""

    if not raw_command.strip():
        return None
    parsed = json.loads(raw_command)
    if (
        not isinstance(parsed, Sequence)
        or isinstance(parsed, (str, bytes))
        or not all(isinstance(item, str) for item in parsed)
    ):
        raise ValueError("Intelligence command must be a JSON array of strings")
    return CommandIntelligenceRunner(tuple(parsed), timeout_seconds=timeout_seconds)
