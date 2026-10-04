"""Revision-bound native course chat handoffs; course state stays authoritative."""

from __future__ import annotations

import importlib
import secrets
import time
from pathlib import Path
from typing import Any

__all__ = ["CourseChats"]


class CourseChats:
    """Use the installed product's existing stores, never a second course profile."""

    def __init__(self, state_root: Path, plugin_root: Path) -> None:
        self.plugin_root = plugin_root
        self.onboarding = importlib.import_module("local_onboarding")
        self.teaching = importlib.import_module("local_teaching")
        self.store = self.onboarding.Store(state_root)
        self.product = self.store.product
        self.read = (
            self.onboarding._read
            if hasattr(self.onboarding, "_read")
            else importlib.import_module("desktop_teaching.onboarding")._read
        )
        self.write = (
            self.onboarding._write
            if hasattr(self.onboarding, "_write")
            else importlib.import_module("desktop_teaching.onboarding")._write
        )

    def state(self, session: str | None) -> tuple[Any, dict[str, Any]]:
        """Load a saved session or the shared introduction without changing progress."""
        if session:
            store = self.teaching.TeachingStore(self.store.root, session)
            return store, store.status()["session"]
        return self.store, self.store.status()

    def prepare(self, args: dict[str, Any]) -> dict[str, Any]:
        """Persist one bounded invitation only after storage and revision checks."""
        self.store.preflight()
        store, state = self.state(args.get("session_id"))
        if state["revision"] != args["revision"]:
            raise ValueError("Stale course revision; reopen the course panel")
        if state.get("phase") == "paused" or (
            state.get("phase") == "complete"
            and (args.get("session_id") or args["kind"] == "onboarding")
        ):
            raise ValueError("Resume the paused course or select a new course first")
        teacher = args["teacher_thread_id"]
        workflow = args["workflow_id"]
        # Exact installed product membership is a mechanical handoff boundary.
        if self.product == "vera":
            self.onboarding.teaching_contract(workflow)
        else:
            importlib.import_module("desktop_teaching.onboarding").teaching_contract(
                self.plugin_root, workflow
            )
        if args.get("session_id"):
            if args["kind"] != "teaching":
                raise ValueError("A repeatable session requires teaching mode")
            if state["workflow_id"] != workflow:
                raise ValueError("The session belongs to another workflow")
        elif args["kind"] == "onboarding":
            first = next(
                (
                    lesson
                    for lesson in state["lessons"]
                    if lesson["status"] != "complete"
                ),
                None,
            )
            if (
                state["phase"] != "teaching"
                or not first
                or first["workflow_id"] != workflow
                or first.get("paused")
            ):
                raise ValueError(
                    "Select the first unfinished, unpaused introduction lesson"
                )
        elif self.teaching.TeachingStore(self.store.root).status()["active_session"]:
            raise ValueError("Resume or pause the existing active session first")
        pair = (
            self.teaching.TeachingStore(self.store.root).status()["pair"]
            if args["kind"] == "teaching" and not args.get("session_id")
            else state.get("pair")
        )
        if pair and pair["teacher_thread_id"] != teacher:
            raise ValueError("Reopen the saved teacher chat before continuing")
        if pair and not args.get("replace_missing_worker", False):
            return {
                "product": self.product,
                "workflow_id": workflow,
                "title": args["title"],
                "action": "resume",
                "worker_thread_id": pair["worker_thread_id"],
                "state_root": str(self.store.root),
                "session_id": args.get("session_id"),
                "teacher_thread_id": teacher,
            }
        token = secrets.token_hex(24)
        invitation = {
            **args,
            "token": token,
            "expires": time.time() + 1800,
            "claimed_thread_id": None,
        }
        with self.store._lock():
            if self.state(args.get("session_id"))[1]["revision"] != args["revision"]:
                raise ValueError("Course changed; reopen the course panel")
            self.write(self.store.root / "chat-invitation.json", invitation)
        return {
            "product": self.product,
            "workflow_id": workflow,
            "title": args["title"],
            "action": "new",
            "invitation": token,
            "state_root": str(self.store.root),
            "teacher_thread_id": teacher,
        }

    def claim(self, token: str, thread_id: str) -> dict[str, Any]:
        """Bind the actual new native thread, then validate its current assignment."""
        self.store.preflight()
        path = self.store.root / "chat-invitation.json"
        with self.store._lock():
            invitation = self.read(path)
            if (
                not secrets.compare_digest(invitation["token"], token)
                or invitation["expires"] < time.time()
            ):
                raise ValueError(
                    "Invitation expired or replaced; return to the teacher"
                )
            claimed = invitation["claimed_thread_id"]
            if claimed and not invitation.get("bound"):
                raise ValueError(
                    "Previous binding was interrupted; reopen the course panel"
                )
            if claimed and claimed != thread_id:
                raise ValueError("Invitation already belongs to another working chat")
            if thread_id == invitation["teacher_thread_id"]:
                raise ValueError("Teacher and working chats must be distinct")
            if not claimed:
                state = self.state(invitation.get("session_id"))[1]
                if state["revision"] != invitation["revision"]:
                    raise ValueError(
                        "Course changed; return to the teacher for a fresh invitation"
                    )
                # Reserve before releasing the lock. A failed binding stays blocked,
                # never launches a duplicate chat or silently resets the course.
                invitation["claimed_thread_id"] = thread_id
                self.write(path, invitation)
        pair = {
            "teacher_thread_id": invitation["teacher_thread_id"],
            "worker_thread_id": thread_id,
        }
        session = invitation.get("session_id")
        if not invitation.get("bound"):
            store, state = self.state(session)
            if state["revision"] != invitation["revision"]:
                raise ValueError("Course changed during binding; return to the teacher")
            if invitation["kind"] == "onboarding":
                result = store.change("pair", state["revision"], pair)
                result = self.store.change(
                    "start",
                    result["revision"],
                    {"workflow_id": invitation["workflow_id"]},
                )
            elif not session:
                result = self.teaching.TeachingStore(self.store.root).begin(
                    {
                        "workflow_id": invitation["workflow_id"],
                        "title": invitation["title"],
                        "goal": invitation["goal"],
                        "mode": invitation.get("mode", "show"),
                        "pair": pair,
                    }
                )
                session = result["session"]["session_id"]
            else:
                store.change("pair", state["revision"], pair)
            invitation.update(bound=True, session_id=session)
            with self.store._lock():
                latest = self.read(path)
                if latest["token"] != token:
                    raise ValueError("Invitation changed; return to the teacher")
                self.write(path, invitation)
        store, state = self.state(session)
        lesson = (
            state
            if session
            else next(
                item
                for item in state["lessons"]
                if item["workflow_id"] == invitation["workflow_id"]
            )
        )
        result = store.worker(
            thread_id, invitation["workflow_id"], lesson["worker_token"]
        )
        result["instruction"] = (
            "Working chat bound and storage verified. Read workflow_contract.skill_path. Perform only the teacher's bounded assignment; return actual artifacts and status. Only the teacher records progress."
        )
        return result
