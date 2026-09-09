"""Persist approved document conventions; all semantic judgments belong to the host.

Fixed rules protect identity, file integrity and explicit version transitions.
They do not classify legal documents or judge professional correctness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

__all__ = [
    "initialize",
    "prepare",
    "propose",
    "approve",
    "disable",
    "list_profiles",
    "attach",
    "record_review",
    "verify_review",
    "main",
]

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
KINDS = {"structure", "voice", "evidence_presentation", "formatting"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", value):
        raise ValueError("Invalid local identifier")
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected non-empty text")
    return value


def _path(path: Path) -> Path:
    path = path.expanduser().absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Symlink paths are not supported")
    return path.resolve()


def _bytes(path: Path) -> bytes:
    path = _path(path)
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Expected a single-link regular file")
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("File exceeds 50 MB")
    return path.read_bytes()


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _write(path: Path, data: bytes) -> None:
    path = _path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _save(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    record = {"payload": payload, "sha256": _digest(payload)}
    _write(path, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode())
    return record


def _read(path: Path) -> dict[str, Any]:
    record = json.loads(_bytes(path))
    if not isinstance(record, dict) or set(record) != {"payload", "sha256"}:
        raise ValueError("Invalid integrity record")
    if not isinstance(record["payload"], dict) or record["sha256"] != _digest(
        record["payload"]
    ):
        raise ValueError("Record digest mismatch")
    return record


def _workspace(path: Path) -> tuple[Path, dict[str, Any]]:
    root = _path(path)
    record = _read(root / "workspace.json")["payload"]
    if record["path"] != str(root):
        raise ValueError("Workspace moved; select its original location")
    if os.name == "posix" and (
        root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077
    ):
        raise ValueError("Workspace must be owned by this user with mode 0700")
    return root, record


@contextmanager
def _lock(root: Path) -> Iterator[None]:
    lock = _path(root / ".writer-lock")
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ValueError("Workspace busy; do not remove an active writer lock") from exc
    try:
        yield
    finally:
        lock.rmdir()


def initialize(workspace: Path, owner: str) -> dict[str, Any]:
    """Create one explicitly selected, private workspace outside installed code."""
    root = _path(workspace)
    if root == Path.home().resolve() or any(
        (parent / ".git").exists()
        or (parent / ".codex-plugin").exists()
        or (parent / ".claude-plugin").exists()
        or (parent / "Vera/client.json").exists()
        or (parent / "pyvenv.cfg").exists()
        for parent in (root, *root.parents)
    ):
        raise ValueError(
            "Choose a workspace outside repositories, plugins, client folders and runtimes"
        )
    if any(
        root.is_relative_to(Path.home() / folder)
        for folder in (".codex/plugins", ".claude/plugins")
    ):
        raise ValueError("Choose a workspace outside plugin caches")
    if root.exists() and any(root.iterdir()):
        raise ValueError("Choose an empty directory; existing work is never adopted")
    _text(owner)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        root.chmod(0o700)
    return _save(
        root / "workspace.json",
        {
            "schema_version": 1,
            "workspace_id": uuid4().hex,
            "owner": owner,
            "path": str(root),
            "created_at": _now(),
        },
    )


def _head(root: Path, profile: str) -> dict[str, Any] | None:
    path = root / "profiles" / _identifier(profile) / "current.json"
    return _read(path) if path.exists() else None


def list_profiles(workspace: Path) -> list[dict[str, Any]]:
    """List metadata only; the host selects suitability semantically."""
    root, _ = _workspace(workspace)
    return [
        {
            key: record["payload"][key]
            for key in ("profile_id", "document_type", "language", "version", "active")
        }
        for record in (
            _read(path) for path in sorted(root.glob("profiles/*/current.json"))
        )
    ]


def prepare(
    workspace: Path,
    profile: str,
    document_type: str,
    language: str,
    examples: list[Path],
) -> dict[str, Any]:
    """Snapshot only the selected examples and bind the current profile revision."""
    root, identity = _workspace(workspace)
    _identifier(profile)
    _text(document_type)
    _text(language)
    if not examples:
        raise ValueError("Select at least one example or corrected document")
    selected = [(_path(path), _bytes(path)) for path in examples]
    if any(
        path.suffix.lower() not in {".md", ".txt", ".pdf", ".docx"}
        for path, _ in selected
    ):
        raise ValueError("Use readable DOCX, PDF, Markdown or text examples")
    with _lock(root):
        head = _head(root, profile)
        if head and (head["payload"]["document_type"], head["payload"]["language"]) != (
            document_type,
            language,
        ):
            raise ValueError(
                "Use a separate profile for a different document type or language"
            )
        session = uuid4().hex
        directory = root / "sessions" / session
        sources = []
        for index, (path, content) in enumerate(selected, 1):
            relative = f"examples/E{index}{path.suffix.lower()}"
            _write(directory / relative, content)
            sources.append(
                {
                    "id": f"E{index}",
                    "path": relative,
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        return _save(
            directory / "session.json",
            {
                "workspace_id": identity["workspace_id"],
                "session_id": session,
                "profile_id": profile,
                "document_type": document_type,
                "language": language,
                "base_sha256": head["sha256"] if head else None,
                "sources": sources,
                "created_at": _now(),
            },
        )


def _session(root: Path, identity: dict[str, Any], session: str) -> dict[str, Any]:
    directory = root / "sessions" / _identifier(session)
    data = _read(directory / "session.json")["payload"]
    if (
        data["workspace_id"] != identity["workspace_id"]
        or data["session_id"] != session
    ):
        raise ValueError("Session belongs to another workspace")
    for source in data["sources"]:
        source_path = _path(directory / source["path"])
        if not source_path.is_relative_to(directory / "examples"):
            raise ValueError("Example path escapes the session")
        if hashlib.sha256(_bytes(source_path)).hexdigest() != source["sha256"]:
            raise ValueError("Selected example changed")
    return data


def propose(workspace: Path, session: str, proposal: dict[str, Any]) -> dict[str, Any]:
    """Persist a model-led proposal and readable evidence for professional review."""
    root, identity = _workspace(workspace)
    with _lock(root):
        data = _session(root, identity, session)
        if set(proposal) != {"scope", "conventions", "excluded_case_content"}:
            raise ValueError(
                "Proposal requires scope, conventions and excluded_case_content"
            )
        _text(proposal["scope"])
        _text(proposal["excluded_case_content"])
        conventions = proposal["conventions"]
        if not isinstance(conventions, list) or not conventions:
            raise ValueError("Propose at least one convention")
        for item in conventions:
            if not isinstance(item, dict) or set(item) != {
                "kind",
                "instruction",
                "source_id",
                "locator",
                "reason",
            }:
                raise ValueError(
                    "Each convention requires kind, instruction, source_id, locator and reason"
                )
            if item["kind"] not in KINDS or item["source_id"] not in {
                s["id"] for s in data["sources"]
            }:
                raise ValueError("Invalid convention kind or example reference")
            for key in ("instruction", "locator", "reason"):
                _text(item[key])
        record = _save(
            root / "sessions" / session / "proposal.json",
            {**data, "proposal": proposal},
        )
        lines = [f"# {data['document_type']}", "", proposal["scope"], ""]
        for item in conventions:
            lines.extend(
                [
                    f"- {item['instruction']}",
                    f"  {item['source_id']} · {item['locator']} · {item['reason']}",
                ]
            )
        lines.extend(
            ["", proposal["excluded_case_content"], "", f"SHA-256: {record['sha256']}"]
        )
        _write(
            root / "sessions" / session / "proposal.md",
            ("\n".join(lines) + "\n").encode(),
        )
        return record


def _confirmed(reviewer: str, confirmed: bool) -> None:
    _text(reviewer)
    if confirmed is not True:
        raise ValueError("Explicit professional approval is required")


def _publish(root: Path, profile: str, payload: dict[str, Any]) -> dict[str, Any]:
    directory = root / "profiles" / profile
    revision = directory / f"v{payload['version']:04d}.json"
    if revision.exists():
        raise ValueError(
            "Revision exists; inspect interrupted publication before retrying"
        )
    _save(revision, payload)
    return _save(directory / "current.json", payload)


def approve(
    workspace: Path,
    session: str,
    proposal_sha256: str,
    reviewer: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Activate exactly the reviewed proposal; reject stale or edited proposals."""
    _confirmed(reviewer, confirmed)
    root, identity = _workspace(workspace)
    with _lock(root):
        data = _session(root, identity, session)
        proposal = _read(root / "sessions" / session / "proposal.json")
        if proposal["sha256"] != proposal_sha256 or any(
            proposal["payload"][key] != value for key, value in data.items()
        ):
            raise ValueError("Proposal changed; review the current proposal")
        head = _head(root, data["profile_id"])
        if (head["sha256"] if head else None) != data["base_sha256"]:
            raise ValueError("Stale proposal; prepare against the current version")
        return _publish(
            root,
            data["profile_id"],
            {
                "workspace_id": identity["workspace_id"],
                "profile_id": data["profile_id"],
                "document_type": data["document_type"],
                "language": data["language"],
                "version": head["payload"]["version"] + 1 if head else 1,
                "active": True,
                "previous_sha256": data["base_sha256"],
                "proposal_sha256": proposal_sha256,
                "session_id": session,
                "conventions": proposal["payload"]["proposal"]["conventions"],
                "scope": proposal["payload"]["proposal"]["scope"],
                "reviewer": reviewer,
                "approved_at": _now(),
            },
        )


def disable(
    workspace: Path, profile: str, reviewer: str, confirmed: bool = False
) -> dict[str, Any]:
    """Disable future reuse while preserving prior case and revision evidence."""
    _confirmed(reviewer, confirmed)
    root, _ = _workspace(workspace)
    with _lock(root):
        head = _head(root, profile)
        if head is None:
            raise ValueError("Profile does not exist")
        return _publish(
            root,
            profile,
            {
                **head["payload"],
                "active": False,
                "version": head["payload"]["version"] + 1,
                "previous_sha256": head["sha256"],
                "reviewer": reviewer,
                "approved_at": _now(),
            },
        )


def _case(context: Path, output: Path, inputs: list[Path]) -> dict[str, Any]:
    for candidate in (ROOT / "vendor/modules", ROOT.parent / "_shared/vendor/modules"):
        if (candidate / "vera_assurance").is_dir():
            sys.path.insert(0, str(candidate))
            break
    from vera_assurance import load_client_engagement_context_file

    return load_client_engagement_context_file(
        context,
        expected_workflow_id="prompt-optimizer",
        input_paths=inputs,
        output_dir=output,
    )


def attach(
    workspace: Path,
    profile: str,
    context: Path,
    output: Path,
    document_type: str,
    language: str,
) -> dict[str, Any]:
    """Snapshot approved instructions into one managed case, without old examples."""
    root, identity = _workspace(workspace)
    output = _path(output)
    case = _case(context, output, [])
    head = _head(root, profile)
    if head is None or not head["payload"]["active"]:
        raise ValueError("No active approved profile")
    data = head["payload"]
    if data["workspace_id"] != identity["workspace_id"]:
        raise ValueError("Profile belongs to another workspace")
    if (data["document_type"], data["language"]) != (document_type, language):
        raise ValueError(
            "Profile does not match the selected document type and language"
        )
    snapshot = {
        key: data[key]
        for key in (
            "workspace_id",
            "profile_id",
            "document_type",
            "language",
            "version",
            "scope",
        )
    }
    snapshot.update(
        {
            "profile_sha256": head["sha256"],
            "case_sha256": _digest(case),
            "conventions": [
                {"kind": item["kind"], "instruction": item["instruction"]}
                for item in data["conventions"]
            ],
        }
    )
    target = output / "document_style.json"
    with _lock(output):
        if target.exists():
            if _read(target)["payload"] != snapshot:
                raise ValueError(
                    "Run already bound to another profile revision; start a new run"
                )
            return _read(target)
        return _save(target, snapshot)


def record_review(
    context: Path, output: Path, document: Path, assessment: dict[str, Any]
) -> dict[str, Any]:
    """Bind the host's semantic review to exact draft and style bytes."""
    output = _path(output)
    document = _path(document)
    case = _case(context, output, [document, output / "document_style.json"])
    binding = _read(output / "document_style.json")
    if binding["payload"]["case_sha256"] != _digest(case):
        raise ValueError("Style binding belongs to another case")
    dimensions = {
        "style_application",
        "case_facts_and_authorities",
        "no_prior_case_carryover",
    }
    if set(assessment) != dimensions:
        raise ValueError("Review all three required dimensions")
    for value in assessment.values():
        if not isinstance(value, dict) or set(value) != {"status", "reason"}:
            raise ValueError("Each review requires status and reason")
        if value["status"] not in {"conforms", "needs_review"}:
            raise ValueError("Invalid review status")
        _text(value["reason"])
    return _save(
        output / "document_style_review.json",
        {
            "style_sha256": binding["sha256"],
            "case_sha256": _digest(case),
            "document_path": str(document),
            "document_sha256": hashlib.sha256(_bytes(document)).hexdigest(),
            "method": "host_model_semantic_review",
            "assessment": assessment,
            "ready": all(
                value["status"] == "conforms" for value in assessment.values()
            ),
            "reviewed_at": _now(),
        },
    )


def verify_review(context: Path, output: Path) -> dict[str, Any]:
    """Reject stale style reviews; this does not certify the model's judgment."""
    output = _path(output)
    review = _read(output / "document_style_review.json")
    data = review["payload"]
    document = Path(data["document_path"])
    case = _case(
        context,
        output,
        [
            document,
            output / "document_style.json",
            output / "document_style_review.json",
        ],
    )
    if (
        data["case_sha256"] != _digest(case)
        or data["style_sha256"] != _read(output / "document_style.json")["sha256"]
        or data["document_sha256"] != hashlib.sha256(_bytes(document)).hexdigest()
    ):
        raise ValueError("Draft, case or style changed; repeat review")
    if not data["ready"]:
        raise ValueError("Document still needs professional review")
    return review


def main(argv: list[str] | None = None) -> int:
    """Operate private teaching and drafting records on the user's behalf."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "init",
            "list",
            "prepare",
            "propose",
            "approve",
            "disable",
            "attach",
            "review",
            "verify",
        ],
    )
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--owner")
    parser.add_argument("--profile")
    parser.add_argument("--document-type")
    parser.add_argument("--language", default="it")
    parser.add_argument("--example", type=Path, action="append", default=[])
    parser.add_argument("--session")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--proposal-sha256")
    parser.add_argument("--reviewer")
    parser.add_argument("--confirmed-by-user", action="store_true")
    parser.add_argument("--client-engagement", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--document", type=Path)
    args = parser.parse_args(argv)
    required = {
        "init": ["workspace", "owner"],
        "list": ["workspace"],
        "prepare": ["workspace", "profile", "document_type"],
        "propose": ["workspace", "session", "input"],
        "approve": ["workspace", "session", "proposal_sha256", "reviewer"],
        "disable": ["workspace", "profile", "reviewer"],
        "attach": [
            "workspace",
            "profile",
            "client_engagement",
            "output_dir",
            "document_type",
        ],
        "review": ["client_engagement", "output_dir", "document", "input"],
        "verify": ["client_engagement", "output_dir"],
    }
    if any(getattr(args, key) is None for key in required[args.command]):
        parser.error("Missing arguments: " + ", ".join(required[args.command]))
    try:
        if args.command == "init":
            result = initialize(args.workspace, args.owner)
        elif args.command == "list":
            result = list_profiles(args.workspace)
        elif args.command == "prepare":
            result = prepare(
                args.workspace,
                args.profile,
                args.document_type,
                args.language,
                args.example,
            )
        elif args.command == "propose":
            result = propose(
                args.workspace, args.session, json.loads(_bytes(args.input))
            )
        elif args.command == "approve":
            result = approve(
                args.workspace,
                args.session,
                args.proposal_sha256,
                args.reviewer,
                args.confirmed_by_user,
            )
        elif args.command == "disable":
            result = disable(
                args.workspace, args.profile, args.reviewer, args.confirmed_by_user
            )
        elif args.command == "attach":
            result = attach(
                args.workspace,
                args.profile,
                args.client_engagement,
                args.output_dir,
                args.document_type,
                args.language,
            )
        elif args.command == "review":
            result = record_review(
                args.client_engagement,
                args.output_dir,
                args.document,
                json.loads(_bytes(args.input)),
            )
        else:
            result = verify_review(args.client_engagement, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        LOGGER.error("DOCUMENT_STYLE_FAILED: %s", exc)
        return 1
    LOGGER.info("%s", json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
