#!/usr/bin/env python3
"""Repeatable local teaching sessions sharing Vera's confirmed onboarding profile.

Python checks exact IDs, revisions, file identity and handoff scope. The native
model chooses goals, questions, explanations and the user's understanding.
Each session has its own atomic checkpoint; the library is derived from these
files so a failed index update cannot lose an example. No network transport.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
from pathlib import Path
from typing import Any

from local_onboarding import (
    MARKER,
    OnboardingError,
    Store,
    _now,
    _read,
    _text,
    _write,
    eligible_workflows,
    teaching_contract,
)

__all__ = ["TeachingStore", "main"]


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise OnboardingError("Select a real local teaching session ID")
    return value


def _pair(data: Any) -> dict[str, str]:
    if not isinstance(data, dict):
        raise OnboardingError("Bind the two native chats")
    result = {
        k: _text(data.get(k), k) for k in ("teacher_thread_id", "worker_thread_id")
    }
    if result["teacher_thread_id"] == result["worker_thread_id"]:
        raise OnboardingError("Teaching and working chats must be distinct")
    return result


class TeachingStore(Store):
    """Use the same OS-user root, save lock and file-evidence contract as onboarding."""

    def __init__(self, root: Path | None = None, session_id: str | None = None) -> None:
        super().__init__(root)
        self.session_id = _identifier(session_id) if session_id else None
        self.sessions = self.root / "teaching" / "sessions"

    def _profile(self) -> dict[str, Any]:
        return Store(self.root).status()

    def _session_path(self, session_id: str) -> Path:
        path = self.sessions / _identifier(session_id) / "session.json"
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise OnboardingError(
                "Recover the real teaching directory; no linked state"
            )
        return path

    def _load(self, session_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        state = _read(self._session_path(session_id))
        self._validate_session(state, session_id, profile)
        return state

    def _validate_session(
        self, state: dict[str, Any], session_id: str, profile: dict[str, Any]
    ) -> None:
        """Reject incomplete persisted records before recovery or execution."""
        if (
            state.get("schema_version") != 1
            or state.get("session_id") != session_id
            or state.get("onboarding_id") != profile.get("onboarding_id")
            or type(state.get("revision")) is not int
            or state["revision"] < 1
            or state.get("phase") not in {"active", "paused", "complete"}
            or state.get("mode") not in {"show", "together"}
            or state.get("workflow_id") not in eligible_workflows()
        ):
            raise OnboardingError(
                "Recover invalid teaching state; never reset the profile"
            )
        _pair(state.get("pair"))
        for field in ("title", "goal", "updated_at"):
            _text(state.get(field), field)
        if state.get("directory") != str(self.sessions / session_id / "files"):
            raise OnboardingError("Teaching artifact directory changed")
        if state["phase"] == "complete" and (
            not state.get("demo")
            or not state.get("understanding")
            or (
                state["mode"] == "together"
                and not (state.get("practice") or state.get("application"))
            )
            or (state.get("real_work") and not state.get("application"))
        ):
            raise OnboardingError(
                "Completed example lacks the requested evidence and understanding"
            )

    def _all(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        if any(p.is_symlink() for p in (self.sessions, *self.sessions.parents)):
            raise OnboardingError("Reconnect the real teaching library")
        if not self.sessions.exists():
            return []
        return [self._load(p.name, profile) for p in sorted(self.sessions.iterdir())]

    def status(self) -> dict[str, Any]:
        """Read latest shared profile and local examples without reenrolling the user."""
        profile = self._profile()
        states = self._all(profile)
        active = [s for s in states if s["phase"] == "active"]
        if len(active) > 1:
            raise OnboardingError(
                "Multiple active teaching sessions need reconciliation"
            )
        result = {
            "onboarding_phase": profile["phase"],
            "profile": profile.get("profile"),
            "state_root": str(self.root),
            "active_session": active[0]["session_id"] if active else None,
            "pair": (
                max(states, key=lambda s: s["updated_at"])["pair"]
                if states
                else profile.get("pair")
            ),
            "examples": [
                {
                    "example_id": "onboarding:" + lesson["workflow_id"],
                    "workflow_id": lesson["workflow_id"],
                    "title": lesson["goal"],
                    "phase": lesson["status"],
                }
                for lesson in profile.get("lessons", [])
                if lesson["status"] == "complete"
            ]
            + [
                {
                    "example_id": s["session_id"],
                    "workflow_id": s["workflow_id"],
                    "title": s["title"],
                    "phase": s["phase"],
                    "updated_at": s["updated_at"],
                }
                for s in sorted(states, key=lambda s: s["updated_at"], reverse=True)
            ],
        }
        if self.session_id:
            result["session"] = self._load(self.session_id, profile)
        return result

    def lesson_root(self, lesson: dict[str, Any]) -> Path:
        """Bind tutorial evidence to this session, or explicitly selected real work."""
        if lesson.get("real_work_evidence"):
            return Path(lesson["real_work_evidence"])
        return self.sessions / _identifier(lesson["session_id"]) / "files"

    def begin(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Start a fresh example after onboarding; repetition never reuses old results."""
        data = data or {}
        if self._profile()["phase"] != "complete":
            raise OnboardingError(
                "Resume mandatory onboarding and its 3–4 lessons first"
            )
        with self._lock():
            current = self.status()
            if current["onboarding_phase"] != "complete":
                raise OnboardingError(
                    "Resume mandatory onboarding and its 3–4 lessons first"
                )
            if current["active_session"]:
                raise OnboardingError(
                    "Resume or pause the active teaching session first"
                )
            workflow = data.get("workflow_id")
            if workflow not in eligible_workflows():
                raise OnboardingError("Choose a supported operational workflow")
            previous = data.get("example_id")
            if previous is not None and not any(
                e["example_id"] == previous
                and e["workflow_id"] == workflow
                and e["phase"] == "complete"
                for e in current["examples"]
            ):
                raise OnboardingError("Choose a completed example of this workflow")
            mode = data.get("mode", "show")
            if mode not in {"show", "together"}:
                raise OnboardingError("Teaching mode is show or together")
            profile = self._profile()
            session_id = secrets.token_hex(16)
            state = {
                "schema_version": 1,
                "onboarding_id": profile["onboarding_id"],
                "session_id": session_id,
                "revision": 1,
                "phase": "active",
                "workflow_id": workflow,
                "title": _text(data.get("title"), "title"),
                "goal": _text(data.get("goal"), "goal"),
                "mode": mode,
                "pair": _pair(current["pair"]),
                "worker_token": secrets.token_hex(24),
                "directory": str(self.sessions / session_id / "files"),
                "voice_preference": "native_voice",
                "previous_example": previous,
                "created_at": _now(),
                "updated_at": _now(),
            }
            path = self._session_path(session_id)
            path.parent.mkdir(parents=True, mode=0o700)
            Path(state["directory"]).mkdir(mode=0o700)
            _write(path, state)
        self.session_id = session_id
        return self.status()

    def _state(self) -> dict[str, Any]:
        if not self.session_id:
            raise OnboardingError("Select --session from the local teaching library")
        if self._profile()["phase"] != "complete":
            raise OnboardingError("Resume mandatory onboarding first")
        return self._load(self.session_id, self._profile())

    def _verify_phase(self, state: dict[str, Any], phase: str) -> None:
        recorded = state[phase]
        evidence_state = state
        if phase == "application":
            evidence_state = {
                **state,
                "real_work_evidence": state["real_work"]["destination"],
            }
        actual = self._evidence(
            evidence_state,
            {**recorded, "artifacts": [a["path"] for a in recorded["artifacts"]]},
        )
        if actual["artifacts"] != recorded["artifacts"]:
            raise OnboardingError(
                "Saved result changed; inspect and record the current result"
            )
        self._verify_execution(evidence_state, phase)

    def change(
        self, action: str, revision: int, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Save one teacher decision; workers validate tokens between bounded steps."""
        with self._lock():
            state = self._state()
            if state["revision"] != revision:
                raise OnboardingError("Stale revision; reload before saving")
            if state["phase"] == "complete" and action not in {"focus", "feedback"}:
                raise OnboardingError(
                    "Start a fresh session to repeat a completed example"
                )
            if state["phase"] == "paused" and action not in {
                "resume",
                "pair",
                "checkpoint",
                "feedback",
                "focus",
            }:
                raise OnboardingError("Resume the paused session first")
            if action == "pair":
                state["pair"] = _pair(data)
                state["worker_token"] = secrets.token_hex(24)
            elif action in {"pause", "resume"}:
                if action == "resume" and any(
                    s["phase"] == "active" and s["session_id"] != self.session_id
                    for s in self._all(self._profile())
                ):
                    raise OnboardingError("Pause the other active session first")
                state["phase"] = "paused" if action == "pause" else "active"
                state["checkpoint"] = _text(
                    data.get("next_step"), "next step after interruption"
                )
                state["worker_token"] = secrets.token_hex(24)
            elif action == "checkpoint":
                state["checkpoint"] = _text(data.get("next_step"), "next step")
                if "question" in data:
                    state["last_question"] = _text(data["question"], "question")
                if "voice_preference" in data:
                    if data["voice_preference"] not in {
                        "native_voice",
                        "text_requested",
                    }:
                        raise OnboardingError(
                            "Use native voice or the user's explicit text choice"
                        )
                    state["voice_preference"] = data["voice_preference"]
            elif action in {"demo", "practice", "application"}:
                if action != "demo" and not state.get("demo"):
                    raise OnboardingError("Demonstrate and explain the workflow first")
                if state.get("real_work") and action != "application":
                    raise OnboardingError(
                        "Real work has started; retain the tutorial evidence"
                    )
                if action == "application" and not state.get("real_work"):
                    raise OnboardingError(
                        "Select the real-work files and destination first"
                    )
                target = (
                    {**state, "real_work_evidence": state["real_work"]["destination"]}
                    if action == "application"
                    else state
                )
                result = self._evidence(target, data)
                if (
                    action == "practice"
                    and result["artifacts"] == state["demo"]["artifacts"]
                ):
                    raise OnboardingError("Record the user's distinct attempt")
                result["execution"] = self._execution(
                    target, action, data, result["artifacts"], state["pair"]
                )
                state[action] = result
                state.pop("focus", None)
                if action == "demo":
                    state.pop("practice", None)
            elif action == "focus":
                phase = data.get("result", "demo")
                if phase not in {"demo", "practice", "application"} or not state.get(
                    phase
                ):
                    raise OnboardingError("Select an existing result to explain")
                self._verify_phase(state, phase)
                artifact = data.get("artifact")
                if artifact not in [a["path"] for a in state[phase]["artifacts"]]:
                    raise OnboardingError(
                        "The displayed artifact must belong to that result"
                    )
                host_result = data.get("host_result")
                if host_result not in {"opened", "queued", "user_confirmed"}:
                    raise OnboardingError("Record the actual native panel outcome")
                state["focus"] = {
                    "result": phase,
                    "artifact": artifact,
                    "location": _text(data.get("location"), "sheet, cell or section"),
                    "explanation": _text(
                        data.get("explanation"), "source-linked explanation"
                    ),
                    "host_result": host_result,
                    "recorded_at": _now(),
                }
            elif action == "use-files":
                self._select_real_work(state, data)
            elif action == "finish":
                if not state.get("demo") or (
                    state["mode"] == "together"
                    and not (state.get("practice") or state.get("application"))
                ):
                    raise OnboardingError(
                        "Finish needs demonstration and the requested guided attempt"
                    )
                if state.get("real_work") and not state.get("application"):
                    raise OnboardingError(
                        "Review the real-work result or pause; do not claim completion"
                    )
                if data.get("confirmed_by_user") is not True:
                    raise OnboardingError("Do not invent the user's understanding")
                for phase in ("demo", "practice", "application"):
                    if state.get(phase):
                        self._verify_phase(state, phase)
                state["understanding"] = _text(
                    data.get("understanding"),
                    "user understanding and professional checks",
                )
                state["phase"] = "complete"
                state.pop("worker_token", None)
            elif action == "feedback":
                state["feedback"] = _text(data.get("feedback"), "local feedback")
            else:
                raise OnboardingError("Unknown teaching transition")
            state["revision"] += 1
            state["updated_at"] = _now()
            path = self._session_path(state["session_id"])
            _write(path.with_name("session.previous.json"), _read(path))
            _write(path, state)
        return self.status()

    def _select_real_work(self, state: dict[str, Any], data: dict[str, Any]) -> None:
        if not state.get("demo") or state.get("real_work"):
            raise OnboardingError(
                "Explain the demo first; preserve an existing real-work handoff"
            )
        self._verify_phase(state, "demo")
        if data.get("selected_by_user") is not True:
            raise OnboardingError("Use only files and destination selected by the user")
        destination = (
            Path(_text(data.get("destination"), "real-work destination"))
            .expanduser()
            .absolute()
        )
        if (
            not destination.is_dir()
            or destination.resolve() != destination
            or destination.is_relative_to(self.root)
            or self.root.is_relative_to(destination)
        ):
            raise OnboardingError(
                "Select an ordinary real-work directory separate from the tutorial"
            )
        sources = data.get("sources")
        if not isinstance(sources, list) or not sources or len(sources) > 200:
            raise OnboardingError("Select 1 to 200 exact source files")
        records = []
        for source in sources:
            path = Path(_text(source, "selected source")).expanduser().absolute()
            if path.is_relative_to(self.root):
                raise OnboardingError(
                    "Select the user's files, not a tutorial artifact"
                )
            record = self._evidence(
                {**state, "real_work_evidence": str(path.parent)},
                {
                    "artifacts": [str(path)],
                    "prompt": state["goal"],
                    "review": "User-selected source identity",
                },
            )["artifacts"][0]
            records.append({"path": str(path), "sha256": record["sha256"]})
        state["real_work"] = {
            "sources": records,
            "destination": str(destination),
            "goal": _text(data.get("goal"), "real-work goal"),
            "selected_at": _now(),
        }
        state["worker_token"] = secrets.token_hex(24)

    def worker(self, thread_id: str, workflow: str, token: str) -> dict[str, Any]:
        """Return only the currently active, exact native worker assignment."""
        state = self._state()
        self.status()  # Detect conflicting active sessions before a worker can act.
        if (
            state["phase"] != "active"
            or state["pair"]["worker_thread_id"] != thread_id
            or state["workflow_id"] != workflow
            or not secrets.compare_digest(state.get("worker_token", ""), token)
        ):
            raise OnboardingError("This is not the active paired teaching assignment")
        if not (self.root / MARKER).is_file() or (self.root / MARKER).is_symlink():
            raise OnboardingError("Restore the tutorial's local-only marker")
        real = state.get("real_work")
        if real:
            for source in real["sources"]:
                path = Path(source["path"])
                actual = self._evidence(
                    {**state, "real_work_evidence": str(path.parent)},
                    {
                        "artifacts": [str(path)],
                        "prompt": real["goal"],
                        "review": "Recheck selected source",
                    },
                )
                if actual["artifacts"][0]["sha256"] != source["sha256"]:
                    raise OnboardingError(
                        "Selected source changed; review the handoff before proceeding"
                    )
        return {
            "session_id": state["session_id"],
            "workflow_contract": teaching_contract(workflow),
            "profile": self._profile()["profile"],
            "lesson": state,
            "teacher_thread_id": state["pair"]["teacher_thread_id"],
            "local_only": real is None,
            "assignment": "professional" if real else "tutorial",
        }

    def recover_session(self, source: Path) -> dict[str, Any]:
        """Recover an explicitly preserved matching checkpoint; revoke old worker tokens."""
        if not self.session_id:
            raise OnboardingError("Select the session to recover")
        target = self._session_path(self.session_id)
        restored = _read(source)
        with self._lock():
            if (
                target.exists()
                or restored.get("session_id") != self.session_id
                or restored.get("onboarding_id") != self._profile().get("onboarding_id")
            ):
                raise OnboardingError(
                    "Preserve the existing session and select its matching checkpoint"
                )
            self._validate_session(restored, self.session_id, self._profile())
            restored["phase"] = "paused"
            restored["worker_token"] = secrets.token_hex(24)
            restored["revision"] += 1
            _write(target, restored)
            self._load(self.session_id, self._profile())
        return self.status()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "status",
            "begin",
            "pair",
            "pause",
            "resume",
            "checkpoint",
            "demo",
            "practice",
            "focus",
            "use-files",
            "application",
            "finish",
            "feedback",
            "worker",
            "recover",
        ],
    )
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--session")
    parser.add_argument("--revision", type=int)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--thread-id")
    parser.add_argument("--workflow")
    parser.add_argument("--token")
    args = parser.parse_args(argv)
    try:
        store = TeachingStore(args.state_root, args.session)
        if args.command == "status":
            result = store.status()
        elif args.command == "worker":
            if not all((args.thread_id, args.workflow, args.token)):
                raise OnboardingError(
                    "Provide the native thread ID, workflow and exact token"
                )
            result = store.worker(args.thread_id, args.workflow, args.token)
        elif args.input is None:
            raise OnboardingError(
                "Write the exact input JSON to a local file and pass --input"
            )
        elif args.command == "begin":
            result = store.begin(_read(args.input))
        elif args.command == "recover":
            result = store.recover_session(args.input)
        elif args.revision is None:
            raise OnboardingError("Use the current --revision")
        else:
            result = store.change(args.command, args.revision, _read(args.input))
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0
    except (OnboardingError, OSError) as exc:
        sys.stdout.write(json.dumps({"status": "blocked", "error": str(exc)}) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
