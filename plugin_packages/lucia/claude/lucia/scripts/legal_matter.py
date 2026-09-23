"""Local, resumable legal work: explicit questions, stages and output integrity."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jsonschema import Draft202012Validator
from legal_documents import read_pack

__all__ = ["initialize", "save", "status", "render", "main"]

LOGGER = logging.getLogger(__name__)
KINDS = (
    "documenti",
    "contenzioso-civile",
    "operazioni-ma",
    "lavoro",
    "recupero-crediti",
    "verifica-citazioni",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def initialize(run_dir: Path, kind: str, purpose: str) -> Path:
    """Bind work to selected evidence; stage design remains model-led."""
    read_pack(run_dir)
    if kind not in KINDS or not purpose.strip():
        raise ValueError("Choose the relevant workflow and state its purpose.")
    target = run_dir / "matter.json"
    state = {
        "schema_version": 1,
        "revision": 0,
        "kind": kind,
        "purpose": purpose,
        "language": "it",
        "questions": [],
        "stages": [],
        "notes": [],
        "output_hashes": {},
    }
    with target.open("xb") as handle:
        handle.write(_bytes(state))
    return target


def _safe_output(run_dir: Path, value: str, must_exist: bool = True) -> Path:
    target = (run_dir / value).resolve()
    if (
        Path(value).is_absolute()
        or not target.is_relative_to(run_dir.resolve())
        or (must_exist and not target.is_file())
    ):
        raise ValueError(
            f"Output must be an existing file in the selected run: {value}"
        )
    if (
        target.name in {"matter.json", "evidence.json", "review.json"}
        or "originals" in Path(value).parts
    ):
        raise ValueError("An original or state file is not a completed work product.")
    return target


def _check(run_dir: Path, state: dict[str, Any], verify_files: bool = True) -> None:
    schema = _load(Path(__file__).with_name("legal_matter.schema.json"))
    errors = [
        f"{e.json_path}: {e.message}"
        for e in Draft202012Validator(schema).iter_errors(state)
    ]
    if errors:
        raise ValueError("Invalid matter state: " + "; ".join(errors))
    pack = read_pack(run_dir)
    stage_ids = [stage["id"] for stage in state["stages"]]
    question_ids = [question["id"] for question in state["questions"]]
    if len(set(stage_ids)) != len(stage_ids) or len(set(question_ids)) != len(
        question_ids
    ):
        raise ValueError("Stage and question IDs must be unique.")
    units = {
        (s["id"], u["anchor"]): u["text"] for s in pack["sources"] for u in s["units"]
    }
    blocked = set()
    for question in state["questions"]:
        if set(question["blocks"]) - set(stage_ids):
            raise ValueError("A question blocks an unknown stage.")
        if (
            question["status"] in {"answered", "not-needed"}
            and not question["answer"].strip()
        ):
            raise ValueError(
                "A resolved question needs its answer or the reason it is no longer needed."
            )
        if question["status"] == "open":
            blocked.update(question["blocks"])
        for citation in question["citations"]:
            value = units.get((citation["source_id"], citation["anchor"]), "")
            quote_text = " ".join(citation["quote"].split())
            if not quote_text or quote_text not in " ".join(value.split()):
                raise ValueError(
                    "Question evidence quotation does not match the source."
                )
    for stage in state["stages"]:
        for output in stage["outputs"]:
            _safe_output(run_dir, output, must_exist=verify_files)
        if stage["status"] == "done":
            if stage["id"] in blocked:
                raise ValueError(
                    f"Stage {stage['id']} still depends on an unanswered question."
                )
            if not stage["outputs"]:
                raise ValueError("A completed stage needs its actual output files.")
        if stage["status"] in {"done", "not-required"} and not stage["note"].strip():
            raise ValueError("A finished or excluded stage needs an explanation.")


def save(run_dir: Path, state_path: Path, expected_revision: int) -> Path:
    """Serialize saves, retain history and atomically replace the current state."""
    lock = run_dir / "matter-save.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise ValueError(
            "Another save holds matter-save.lock. If its process stopped, inspect "
            "the current state and history before removing the stale lock and retrying."
        ) from error
    try:
        with handle:
            handle.write(f"pid={os.getpid()}\nexpected_revision={expected_revision}\n")
        return _save_locked(run_dir, state_path, expected_revision)
    finally:
        lock.unlink()


def _save_locked(run_dir: Path, state_path: Path, expected_revision: int) -> Path:
    """Validate under the save lock; a failed write leaves the current state intact."""
    target = run_dir / "matter.json"
    if state_path.resolve() == target.resolve():
        raise ValueError("Write proposed updates to a separate file, then save them.")
    previous = _load(target)
    if previous["revision"] != expected_revision:
        raise ValueError(
            "Matter changed since this update was prepared; reread before saving."
        )
    state = _load(state_path)
    if any(
        state.get(key) != previous[key]
        for key in ("kind", "schema_version", "revision")
    ):
        raise ValueError(
            "Keep the matter identity and loaded revision when proposing updates."
        )
    _check(run_dir, state)
    state["revision"] = expected_revision + 1
    state["output_hashes"] = {
        output: hashlib.sha256(_safe_output(run_dir, output).read_bytes()).hexdigest()
        for stage in state["stages"]
        if stage["status"] == "done"
        for output in stage["outputs"]
    }
    history = run_dir / "matter-history"
    history.mkdir(exist_ok=True)
    snapshot = history / f"revision-{expected_revision:04}.json"
    if snapshot.exists():
        if _load(snapshot) != previous:
            raise ValueError(
                "Saved history differs from current state; inspect before saving."
            )
    else:
        with snapshot.open("xb") as handle:
            handle.write(_bytes(previous))
            handle.flush()
            os.fsync(handle.fileno())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=run_dir, prefix="matter-next-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(_bytes(state))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def status(run_dir: Path) -> dict[str, Any]:
    """Reopen work and detect changed deliverables; never certify legal readiness."""
    state = _load(run_dir / "matter.json")
    _check(run_dir, state, verify_files=False)
    drift = []
    for output, checksum in state["output_hashes"].items():
        path = _safe_output(run_dir, output, must_exist=False)
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != checksum
        ):
            drift.append(output)
    blockers = {
        stage["id"]: [
            q["id"]
            for q in state["questions"]
            if q["status"] == "open" and stage["id"] in q["blocks"]
        ]
        for stage in state["stages"]
    }
    done = bool(state["stages"]) and all(
        s["status"] in {"done", "not-required"} for s in state["stages"]
    )
    return {
        "revision": state["revision"],
        "work_products_recorded": done and not drift,
        "open_questions": [
            q["id"] for q in state["questions"] if q["status"] == "open"
        ],
        "blocked_stages": {key: value for key, value in blockers.items() if value},
        "ready_stages": [
            s["id"]
            for s in state["stages"]
            if s["status"] == "pending" and not blockers[s["id"]]
        ],
        "changed_outputs": drift,
        "meaning": "Recorded workflow state and file integrity only; the lawyer retains professional approval.",
    }


def render(run_dir: Path) -> Path:
    """Show questions, answers and actual stage outputs in a readable local file."""
    state = _load(run_dir / "matter.json")
    current = status(run_dir)
    labels = _load(Path(__file__).with_name("legal_matter_labels.json"))[
        state["language"]
    ]
    esc = lambda value: html.escape(str(value), quote=True)
    questions = "".join(
        f"<article><h3>{esc(q['id'])} · {esc(q['question'])}</h3><p>{esc(q['reason'])}</p><p>{esc(labels[q['status']])}: {esc(q['answer'])}</p><p>{esc(labels['blocks'])}: {esc(', '.join(q['blocks']))}</p></article>"
        for q in state["questions"]
    )
    stages = "".join(
        f"<tr><th>{esc(stage['label'])}</th><td>{esc(labels[stage['status']])}</td><td>{esc(stage['note'])}</td><td>"
        + "<br>".join(
            f'<a href="{esc(quote(output, safe="/"))}">{esc(output)}</a>'
            for output in stage["outputs"]
        )
        + "</td></tr>"
        for stage in state["stages"]
    )
    target = run_dir / "matter.html"
    target.write_text(
        f"""<!doctype html><html lang="{state['language']}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(state['purpose'])}</title>
<style>body{{font:16px/1.6 'Instrument Sans',Arial,sans-serif;max-width:1000px;margin:40px auto;padding:0 24px;color:#172b4d}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #ccd5df;padding:12px;text-align:left;vertical-align:top}}article{{border-top:1px solid #ccd5df;padding:12px 0}}a{{color:#145ca4}}h1{{line-height:1.2}}</style>
<main><h1>{esc(state['purpose'])}</h1><p>{esc(labels['meaning'])}</p><h2>{esc(labels['questions'])}</h2>{questions}<h2>{esc(labels['stages'])}</h2><table>{stages}</table>
<h2>{esc(labels['integrity'])}</h2><p>{esc(', '.join(current['changed_outputs']) or labels['unchanged'])}</p><h2>{esc(labels['notes'])}</h2><ul>{''.join('<li>'+esc(n)+'</li>' for n in state['notes'])}</ul></main></html>""",
        encoding="utf-8",
    )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "save", "status", "render"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--kind", choices=KINDS, default="documenti")
    parser.add_argument("--purpose", default="")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--expected-revision", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(args.run_dir, args.kind, args.purpose)
        elif args.command == "save":
            if args.state is None or args.expected_revision is None:
                raise ValueError("Saving needs --state and --expected-revision.")
            result = save(args.run_dir, args.state, args.expected_revision)
        elif args.command == "render":
            result = render(args.run_dir)
        else:
            result = json.dumps(status(args.run_dir), ensure_ascii=False)
        LOGGER.info("%s", result)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        LOGGER.error("%s", error)
        return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
