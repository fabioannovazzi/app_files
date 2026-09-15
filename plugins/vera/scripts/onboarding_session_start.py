#!/usr/bin/env python3
"""Expose optional tutorial status without gating ordinary professional work."""

from __future__ import annotations

import json
import sys

from local_onboarding import OnboardingError, Store

__all__ = ["main"]


def main() -> int:
    """Expose status, never interview content, in startup context."""
    try:
        state = Store().status()
        phase = state["phase"]
    except (OnboardingError, OSError):
        phase = "recovery_required"
    message = (
        f"Vera local tutorial status: {phase}. Onboarding is optional. "
        "Continue ordinary work without onboarding, even if its profile is missing, "
        "unfinished, inaccessible or corrupt, or tutorial setup fails. "
        "Only start or resume a tutorial when the user asks; do not repeatedly offer it. "
        "For that tutorial read skills/vera/references/local-onboarding.md and "
        "skills/learn-with-vera/SKILL.md. Preserve saved progress and validate "
        "native lesson worker handoffs. Do not run onboarding for other plugins. "
        "Do not transmit onboarding/profile/lesson feedback to Mparanza."
    )
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": message,
                }
            }
        )
        + "\n"
    )
    if phase == "complete":
        from local_teaching import TeachingStore

        try:
            teaching = TeachingStore().status()
        except (OnboardingError, OSError):
            return (
                0  # Preserve an inaccessible local teaching record, with no call-home.
            )
        if teaching["active_session"]:
            return 0  # No optional update/CR request while a tutorial is active.
        from check_for_update import main as check_updates

        return check_updates()
    # No version request or CR polling while onboarding is pending or inaccessible.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
