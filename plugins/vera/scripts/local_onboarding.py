#!/usr/bin/env python3
"""Persist Vera's one-off OpenAI desktop onboarding using only the local stdlib.

Revisions, identifiers, hashes and transitions are mechanical integrity checks.
The native host model conducts the interview, chooses relevant workflows and
assesses the lesson; this module never classifies professional meaning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

__all__ = ["OnboardingError", "Store", "default_root", "main"]

MARKER = ".vera-onboarding-local-only"
PROFILE_FIELDS = {"language", "work", "interests", "experience", "preferences"}


class OnboardingError(ValueError):
    """Local state needs correction or recovery; never silently start over."""


def default_root() -> Path:
    """Use one OS-user location, independent of host, plugin version and cwd."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "Vera" / "onboarding"
    return Path.home() / ".local" / "share" / "vera" / "onboarding"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise OnboardingError(
            f"{field} must be non-empty text of at most 4000 characters"
        )
    return value.strip()


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
        raise OnboardingError(
            f"Recover the missing, linked or oversized local file: {path}"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OnboardingError(f"Recover invalid local JSON: {path}") from exc
    if not isinstance(value, dict):
        raise OnboardingError(f"Local file must contain an object: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    if path.is_symlink():
        raise OnboardingError("Refusing to replace a symlink")
    descriptor, temporary = tempfile.mkstemp(prefix=".save-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _validate(state: dict[str, Any]) -> None:
    if state.get("schema_version") != 1:
        raise OnboardingError(
            "Unsupported local schema; recover or migrate, never reset"
        )
    _text(state.get("onboarding_id"), "onboarding_id")
    if type(state.get("revision")) is not int or state["revision"] < 1:
        raise OnboardingError("Invalid local revision")
    if state.get("phase") not in {"interview", "teaching", "complete"}:
        raise OnboardingError("Invalid local phase")
    if not {"profile", "pair", "lessons", "interview_notes"} <= state.keys():
        raise OnboardingError("Local state is incomplete; recover the original profile")
    pair = state["pair"]
    if pair is not None:
        if not isinstance(pair, dict) or set(pair) != {
            "teacher_thread_id",
            "worker_thread_id",
        }:
            raise OnboardingError("Invalid native chat pair")
        for field, value in pair.items():
            _text(value, field)
        if pair["teacher_thread_id"] == pair["worker_thread_id"]:
            raise OnboardingError("Native chat pair must contain distinct threads")
    profile = state.get("profile")
    if profile is not None:
        if not isinstance(profile, dict) or set(profile) != PROFILE_FIELDS:
            raise OnboardingError("Invalid local professional profile")
        for field, value in profile.items():
            _text(value, field)
    elif state["phase"] != "interview":
        raise OnboardingError("Confirmed profile missing; recover local state")
    lessons = state.get("lessons")
    if not isinstance(lessons, list) or len(lessons) not in {0, 3, 4}:
        raise OnboardingError("Invalid local lesson plan")
    ids: list[str] = []
    for lesson in lessons:
        if not isinstance(lesson, dict):
            raise OnboardingError("Invalid lesson record")
        workflow_id = _text(lesson.get("workflow_id"), "workflow_id")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", workflow_id):
            raise OnboardingError("Invalid workflow ID in local state")
        ids.append(workflow_id)
        if lesson.get("status") not in {"pending", "active", "complete"}:
            raise OnboardingError("Invalid lesson status")
        if lesson["status"] == "complete" and not all(
            lesson.get(key) for key in ("demo", "practice", "understanding")
        ):
            raise OnboardingError("Completed lesson is missing its evidence")
    if len(ids) != len(set(ids)):
        raise OnboardingError("Duplicate lesson IDs")
    if sum(lesson["status"] == "active" for lesson in lessons) > 1:
        raise OnboardingError("Multiple active lessons")
    if state["phase"] == "complete" and (
        not lessons or any(lesson["status"] != "complete" for lesson in lessons)
    ):
        raise OnboardingError(
            "Incomplete lessons cannot count as onboarding completion"
        )


class Store:
    """A local profile shared explicitly by Codex and local ChatGPT Work."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_root()).expanduser().absolute()
        if any(part.is_symlink() for part in (self.root, *self.root.parents)):
            raise OnboardingError(
                "Reconnect the real local profile directory; symlinks are not supported"
            )
        self.path = self.root / "profile.json"
        self.enrollment = self.root / "enrollment.json"

    def status(self) -> dict[str, Any]:
        """Read without creating files or treating access/corruption as a new user."""
        if not self.root.exists():
            return {"phase": "required", "revision": 0, "state_root": str(self.root)}
        if not self.root.is_dir():
            raise OnboardingError("Local profile root is not a directory")
        entries = list(self.root.iterdir())  # Access errors must remain visible.
        if not entries:
            return {"phase": "required", "revision": 0, "state_root": str(self.root)}
        enrollment = _read(self.enrollment)
        state = _read(self.path)
        _validate(state)
        for lesson in state["lessons"]:
            if lesson["status"] in {"active", "complete"} and lesson.get(
                "directory"
            ) != str(self.root / "lessons" / lesson["workflow_id"]):
                raise OnboardingError(
                    "Lesson location changed; recover the original local scope"
                )
        if state["onboarding_id"] != enrollment.get("onboarding_id"):
            raise OnboardingError(
                "Profile and enrollment differ; reconnect the original profile"
            )
        return {**state, "state_root": str(self.root)}

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = self.root / ".saving"
        try:
            lock.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise OnboardingError(
                "Another save is active. Retry after it finishes. If interrupted, verify no save "
                "is running before removing the empty .saving directory; do not reset the profile."
            ) from exc
        try:
            yield
        finally:
            lock.rmdir()

    def begin(self) -> dict[str, Any]:
        """Enroll once, including an existing Vera user without this new record."""
        status = self.status()
        if status["phase"] != "required":
            return status
        with self._lock():
            # Recheck after acquiring the lock: two desktop chats can start together.
            if self.path.exists() or self.enrollment.exists():
                return self.status()
            if set(path.name for path in self.root.iterdir()) != {".saving"}:
                raise OnboardingError(
                    "Unrecognized existing state; recover rather than overwrite"
                )
            state = {
                "schema_version": 1,
                "onboarding_id": secrets.token_hex(16),
                "revision": 1,
                "phase": "interview",
                "profile": None,
                "interview_notes": "",
                "pair": None,
                "lessons": [],
                "created_at": _now(),
                "updated_at": _now(),
            }
            # Enrollment is a separate loss sentinel, not a version-dependent flag.
            _write(self.enrollment, {"onboarding_id": state["onboarding_id"]})
            (self.root / MARKER).write_text(
                "Vera onboarding: local-only tutorial artifacts.\n"
            )
            _write(self.path, state)
        return self.status()

    def _lesson(self, state: dict[str, Any], workflow: str) -> dict[str, Any]:
        for lesson in state["lessons"]:
            if lesson["workflow_id"] == workflow:
                return lesson
        raise OnboardingError("Workflow is not in this confirmed lesson plan")

    def _evidence(self, lesson: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        paths = data.get("artifacts")
        if not isinstance(paths, list) or not paths or len(paths) > 30:
            raise OnboardingError("Provide 1 to 30 real lesson artifact paths")
        root = (self.root / "lessons" / lesson["workflow_id"]).resolve()
        records = []
        for value in paths:
            path = Path(_text(value, "artifact"))
            if not path.is_absolute():
                path = root / path
            if any(part.is_symlink() for part in (path, *path.parents)):
                raise OnboardingError("Lesson evidence must not use symlinks")
            path = path.resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise OnboardingError("Evidence must be a real file inside this lesson")
            digestor = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digestor.update(chunk)
            digest = digestor.hexdigest()
            records.append({"path": str(path.relative_to(root)), "sha256": digest})
        return {
            "artifacts": records,
            "prompt": _text(data.get("prompt"), "the user's natural request"),
            "review": _text(
                data.get("review"), "observed output and professional checks"
            ),
            "recorded_at": _now(),
        }

    def change(
        self, action: str, revision: int, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Commit one checked transition; reject stale writers instead of losing work."""
        with self._lock():
            state = self.status()
            state.pop("state_root", None)
            if state.get("revision") != revision or state["phase"] == "required":
                raise OnboardingError(
                    "Stale revision or enrollment missing; reload status before saving"
                )
            if state["phase"] == "complete" and action not in {"profile", "feedback"}:
                raise OnboardingError(
                    "Onboarding is already complete; use normal Vera workflows"
                )
            if action == "notes":
                if state["phase"] != "interview":
                    raise OnboardingError("Interview is already confirmed")
                state["interview_notes"] = _text(data.get("notes"), "notes")
            elif action == "profile":
                if data.get("confirmed_by_user") is not True:
                    raise OnboardingError(
                        "Reflect the profile back and obtain user confirmation first"
                    )
                profile = data.get("profile")
                if not isinstance(profile, dict) or set(profile) != PROFILE_FIELDS:
                    raise OnboardingError(
                        f"Profile requires exactly {sorted(PROFILE_FIELDS)}"
                    )
                state["profile"] = {
                    key: _text(value, key) for key, value in profile.items()
                }
                state["profile_confirmed_at"] = _now()
                state["interview_notes"] = (
                    ""  # Keep the confirmed summary, not a transcript.
                )
                if state["phase"] == "interview":
                    state["phase"] = "teaching"
            elif action == "plan":
                if state["profile"] is None or any(
                    lesson["status"] != "pending" for lesson in state["lessons"]
                ):
                    raise OnboardingError(
                        "Confirm the profile first; do not replace started lessons"
                    )
                lessons = data.get("lessons")
                if not isinstance(lessons, list) or len(lessons) not in {3, 4}:
                    raise OnboardingError(
                        "Select three or four distinct relevant workflows"
                    )
                catalog = (
                    Path(__file__).parents[1]
                    / "skills"
                    / "vera"
                    / "references"
                    / "workflow-catalog.md"
                )
                # Exact skill IDs are membership facts; relevance remains model-led.
                eligible = set(
                    re.findall(r"^- `([a-z0-9-]+)`:", catalog.read_text(), re.M)
                ) - {
                    "prompt-optimizer",
                    "deep-research-validator",
                    "adversarial-opinion",
                    "privacy-surface-review",
                }
                selected = []
                for lesson in lessons:
                    if (
                        not isinstance(lesson, dict)
                        or lesson.get("workflow_id") not in eligible
                    ):
                        raise OnboardingError(
                            "Select a supported operational workflow from the catalog"
                        )
                    selected.append(
                        {
                            "workflow_id": lesson["workflow_id"],
                            "reason": _text(
                                lesson.get("reason"), "relevance to this professional"
                            ),
                            "goal": _text(lesson.get("goal"), "lesson goal"),
                            "status": "pending",
                        }
                    )
                state["lessons"] = selected
            elif action == "pair":
                teacher = _text(data.get("teacher_thread_id"), "teacher_thread_id")
                worker = _text(data.get("worker_thread_id"), "worker_thread_id")
                if teacher == worker:
                    raise OnboardingError("Teaching and working chats must be distinct")
                state["pair"] = {
                    "teacher_thread_id": teacher,
                    "worker_thread_id": worker,
                }
                for lesson in state["lessons"]:
                    if lesson["status"] == "active":
                        lesson["worker_token"] = secrets.token_hex(24)
            elif action == "feedback":
                state["feedback"] = _text(data.get("feedback"), "local feedback")
            else:
                workflow = _text(data.get("workflow_id"), "workflow_id")
                lesson = self._lesson(state, workflow)
                if action == "start":
                    if not state["pair"]:
                        raise OnboardingError(
                            "Create and bind the two native chats first"
                        )
                    first = next(
                        (
                            item
                            for item in state["lessons"]
                            if item["status"] != "complete"
                        ),
                        None,
                    )
                    if first is not lesson:
                        raise OnboardingError(
                            "Resume the first unfinished lesson before advancing"
                        )
                    if lesson["status"] == "pending":
                        lesson["status"] = "active"
                        lesson["worker_token"] = secrets.token_hex(24)
                    lesson_dir = self.root / "lessons" / workflow
                    lesson_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                    lesson["directory"] = str(lesson_dir)
                elif action in {"demo", "practice"}:
                    if lesson["status"] != "active":
                        raise OnboardingError(
                            "Start the lesson before recording evidence"
                        )
                    if action == "practice" and not lesson.get("demo"):
                        raise OnboardingError(
                            "Demonstrate and explain the result before practice"
                        )
                    evidence = self._evidence(lesson, data)
                    if (
                        action == "practice"
                        and evidence["artifacts"] == lesson["demo"]["artifacts"]
                    ):
                        raise OnboardingError(
                            "Record the user's own attempt, not the demonstration again"
                        )
                    lesson[action] = evidence
                    lesson.pop("understanding", None)
                    if action == "demo":
                        lesson.pop("practice", None)
                elif action == "finish":
                    if lesson["status"] != "active" or not all(
                        lesson.get(key) for key in ("demo", "practice")
                    ):
                        raise OnboardingError(
                            "A completed lesson needs demonstration and guided practice"
                        )
                    if data.get("confirmed_by_user") is not True:
                        raise OnboardingError(
                            "Check the user's understanding before completing the lesson"
                        )
                    self._verify_evidence(lesson)
                    lesson["understanding"] = _text(
                        data.get("understanding"),
                        "user understanding and remaining questions",
                    )
                    lesson["status"] = "complete"
                    lesson.pop("worker_token", None)
                    if all(item["status"] == "complete" for item in state["lessons"]):
                        state["phase"] = "complete"
                        state["completed_at"] = _now()
                else:
                    raise OnboardingError("Unknown local transition")
            state["revision"] += 1
            state["updated_at"] = _now()
            _validate(state)
            _write(self.root / "profile.previous.json", _read(self.path))
            _write(self.path, state)
        return self.status()

    def _verify_evidence(self, lesson: dict[str, Any]) -> None:
        for phase in ("demo", "practice"):
            recorded = lesson[phase]
            current = self._evidence(
                lesson,
                {
                    **recorded,
                    "artifacts": [item["path"] for item in recorded["artifacts"]],
                },
            )
            if current["artifacts"] != recorded["artifacts"]:
                raise OnboardingError(
                    "Lesson artifacts changed; review and record the actual results again"
                )

    def worker(self, thread_id: str, workflow: str, token: str) -> dict[str, Any]:
        """Authorize only the active lesson handoff, never a general onboarding bypass.

        This is routing coordination within one OS account, not host authentication.
        The assistant must obtain its actual thread ID from the native host.
        """
        state = self.status()
        lesson = self._lesson(state, workflow)
        if (
            state["phase"] != "teaching"
            or not state["pair"]
            or state["pair"]["worker_thread_id"] != thread_id
            or lesson["status"] != "active"
            or not secrets.compare_digest(lesson.get("worker_token", ""), token)
        ):
            raise OnboardingError(
                "This is not the current paired lesson; return to the teacher"
            )
        return {
            "onboarding_id": state["onboarding_id"],
            "profile": state["profile"],
            "lesson": lesson,
            "teacher_thread_id": state["pair"]["teacher_thread_id"],
            "local_only": True,
        }

    def recover(self, source: Path) -> dict[str, Any]:
        """Restore an explicitly selected local copy matching the enrollment sentinel."""
        restored = _read(source)
        _validate(restored)
        with self._lock():
            enrollment = _read(self.enrollment)
            if restored["onboarding_id"] != enrollment.get("onboarding_id"):
                raise OnboardingError(
                    "Recovery copy belongs to another professional profile"
                )
            if self.path.exists():
                raise OnboardingError(
                    "Preserve and inspect the existing profile before an explicit recovery"
                )
            restored["revision"] += 1
            _write(self.path, restored)
        return self.status()


def main(argv: list[str] | None = None) -> int:
    """Expose the same local lifecycle to either OpenAI desktop host."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-root",
        type=Path,
        help="Explicit local recovery/test root; normally omit",
    )
    parser.add_argument(
        "command",
        choices=[
            "status",
            "begin",
            "notes",
            "profile",
            "plan",
            "pair",
            "start",
            "demo",
            "practice",
            "finish",
            "feedback",
            "worker",
            "recover",
        ],
    )
    parser.add_argument("--revision", type=int)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--thread-id")
    parser.add_argument("--workflow")
    parser.add_argument("--token")
    args = parser.parse_args(argv)
    try:
        store = Store(args.state_root)
        if args.command == "status":
            result = store.status()
        elif args.command == "begin":
            result = store.begin()
        elif args.command == "recover":
            if args.input is None:
                raise OnboardingError(
                    "Select a verified local recovery copy with --input"
                )
            result = store.recover(args.input)
        elif args.command == "worker":
            if not all((args.thread_id, args.workflow, args.token)):
                raise OnboardingError(
                    "Provide the actual host thread ID, workflow and teacher's token"
                )
            result = store.worker(args.thread_id, args.workflow, args.token)
        else:
            if args.revision is None or args.input is None:
                raise OnboardingError(
                    "Mutations require --revision from status and --input JSON"
                )
            result = store.change(args.command, args.revision, _read(args.input))
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return 0
    except (OnboardingError, OSError) as exc:
        sys.stdout.write(
            json.dumps({"phase": "recovery_required", "error": str(exc)}) + "\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
