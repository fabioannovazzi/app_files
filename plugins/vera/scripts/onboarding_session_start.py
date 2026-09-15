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
    # A public version GET carries no tutorial data. Skipping optional onboarding
    # must not suppress updates; only an active/recovering tutorial suppresses CRs.
    from check_for_update import session_start_output

    allow_change_requests = False
    if phase == "complete":
        from local_teaching import TeachingStore

        try:
            teaching = TeachingStore().status()
            allow_change_requests = not teaching["active_session"]
        except (OnboardingError, OSError):
            pass  # Preserve inaccessible teaching state; do not poll its CRs.
    output = session_start_output(include_change_requests=allow_change_requests)
    output["hookSpecificOutput"]["additionalContext"] += " " + message
    sys.stdout.write(json.dumps(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
