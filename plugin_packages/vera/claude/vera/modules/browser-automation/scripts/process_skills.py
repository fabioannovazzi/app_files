"""Author named Vera skills and bind their execution to one exact browser process.

Authors decide purpose, support and acceptance. Serialization and hash checks are
mechanical: a selected skill must never execute a similarly named local process.
Export writes reviewable source; it neither publishes nor confers qualification.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from capability_pipeline import canonical_json_bytes, validate_capability
from process_lifecycle import ProcessStore

__all__ = ["begin_skill", "export_skill", "main"]
LOG = logging.getLogger(__name__)
CARD_FIELDS = {"display_name", "short_description", "default_prompt", "instructions"}


def _read(path: Path) -> Any:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("skill files must not follow symlinks")
    return json.loads(path.read_text(encoding="utf-8"))


def export_skill(
    store: ProcessStore, process_id: str, specification: dict[str, Any], output: Path
) -> Path:
    """Write one new developer-reviewed skill folder for the standard product builder."""
    required = CARD_FIELDS | {"name", "description", "result_checks", "model_data"}
    if set(specification) != required or not all(
        isinstance(value, str) and value.strip() for value in specification.values()
    ):
        raise ValueError(
            "skill needs authored identity, card, result checks and data boundary"
        )
    name = specification["name"]
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        raise ValueError("skill name must be a lowercase hyphenated slug")
    if f"${name}" not in specification["default_prompt"]:
        raise ValueError("default prompt must invoke this exact named skill")
    if any("\n" in specification[k] for k in CARD_FIELDS | {"name", "description"}):
        raise ValueError(
            "skill identity and Marketplace card fields must be single paragraphs"
        )
    current = store.resume(process_id)
    if not current["versions"]:
        raise ValueError("develop an executable procedure before authoring its skill")
    implementation = current["versions"][-1]
    capability = _read(Path(implementation["path"]))
    errors = validate_capability(capability)
    if errors or capability["status"] not in {"discovered", "validated_local"}:
        raise ValueError("skill requires a valid executable procedure, not a scaffold")
    target = output / name
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError("skill output must not follow symlinks")
    # Never overwrite an existing operation while exporting a new one.
    target.mkdir(parents=True, exist_ok=False)
    (target / "capability.json").write_bytes(canonical_json_bytes(capability))
    store.export_binding(process_id, target / "process.json")
    card = {key: specification[key] for key in sorted(CARD_FIELDS)}
    (target / "marketplace-card.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (target / "agents").mkdir()
    interface = {key: card[key] for key in CARD_FIELDS - {"instructions"}}
    (target / "agents/openai.yaml").write_text(
        "interface:\n"
        + "".join(
            f"  {key}: {json.dumps(value, ensure_ascii=False)}\n"
            for key, value in sorted(interface.items())
        ),
        encoding="utf-8",
    )
    description = current["description"]
    inputs = (
        "\n".join(
            f"- `{item['name']}` ({item['type']}): {item['purpose']}"
            for item in capability["inputs"]
        )
        or "No additional business parameters."
    )
    excluded = "\n".join(f"- {item}" for item in description["process"]["out_of_scope"])
    skill = f"""---
name: {name}
description: {json.dumps(specification['description'], ensure_ascii=False)}
---

# {card['display_name']}

{description['process']['objective']}

System: {description['site']}
Starting point: {description['start_state']}
Expected result: {description['end_condition']}

## Scope and inputs

Excluded work:
{excluded}

Obtain only missing business parameters:
{inputs}

## Execute this operation

This skill selects exactly the procedure in its adjacent `process.json` and
`capability.json`. Do not search the development catalog or substitute another
procedure. For a request outside this scope, explain the mismatch. For ambiguity,
clarify the intended business work before execution.

Resolve the shared module as `../../modules/browser-automation` from this skill
folder in an installed Vera package, or `../../../browser-automation` in source.
Run its `scripts/check_dependencies.py` under the existing managed requirements
environment. Read its `references/ordinary-use.md`, then prepare this exact skill:

```bash
python <module>/scripts/process_skills.py begin --skill <this-skill-folder> --input <observed-host.json>
```

Vera resolves those internal paths and observes the current callable host. The
operator supplies business inputs and handles authentication. The helper returns
the exact procedure inputs, persistent attempt and any required local verification.
On a block, show its report; never select another procedure or silently turn the
request into development. Qualified use calls the shared `executeProcess` runtime.
Existing action-time authorization and uncertainty/recovery rules apply.

## Check and deliver the result

{specification['result_checks']}

Read the actual outputs, save the evidence-bound result review, and deliver the
readable report with output links and exceptions. An interrupted or failed run
retains this same process identity for the development handoff. No blind replay.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

## What data reaches the model

{specification['model_data']}
"""
    (target / "SKILL.md").write_text(skill, encoding="utf-8")
    return target


def begin_skill(
    store: ProcessStore, skill: Path, host: dict[str, Any]
) -> dict[str, Any]:
    """Prepare only the procedure distributed in the selected named skill."""
    binding = _read(skill / "process.json")
    capability = _read(skill / "capability.json")
    store.sync_binding(skill / "process.json")
    attempt = store.begin(
        binding["process_id"],
        "use",
        host,
        version=capability["version"],
        pinned_version=True,
        skill_name=skill.name,
    )
    return {
        **attempt,
        "skill": skill.name,
        "procedure_version": capability["version"],
        "inputs": capability["inputs"],
        "runtime_path": str(Path(__file__).with_name("process_runtime.mjs")),
    }


def main(argv: list[str] | None = None) -> int:
    """Developer export and ordinary-use entry points; never ask users for paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "begin"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--process")
    parser.add_argument("--skill", type=Path)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        store = ProcessStore(args.root)
        payload = _read(args.input)
        if args.command == "export":
            if not args.process or args.output is None:
                raise ValueError("export needs a process and source skills directory")
            result: Any = {
                "skill_directory": str(
                    export_skill(store, args.process, payload, args.output)
                )
            }
        else:
            if args.skill is None:
                raise ValueError("begin needs the selected skill directory")
            result = begin_skill(store, args.skill, payload)
        LOG.info("%s", json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
        LOG.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
