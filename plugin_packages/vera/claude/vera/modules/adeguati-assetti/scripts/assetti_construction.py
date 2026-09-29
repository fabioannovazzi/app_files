"""Run construction work inside the existing native adeguati-assetti archive."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from construction_adapters import budget_rows
from construction_core import create_case, digest, require
from construction_exports import export_manual, save_snapshot, write_once
from construction_intake import render_form
from construction_store import CaseStore

__all__ = ["main"]

ROOT = Path(__file__).resolve().parents[1]


def _archive_loader():
    for vendor in (
        ROOT / "vendor/modules",
        ROOT.parent.parent / "vendor/modules",
        ROOT.parent / "_shared/vendor/modules",
    ):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    from vera_assurance import load_client_engagement_context_file

    return load_client_engagement_context_file


def _validate_evidence(state: dict, context: dict, context_path: Path, loader) -> None:
    """Recheck exact receipts and hashes, including when a prior snapshot is resumed."""
    root = Path(context["run_root"]) / "inputs"
    for evidence in state["evidence"].values():
        relative = Path(evidence["path"])
        require(
            not relative.is_absolute() and ".." not in relative.parts,
            "Evidence path must be relative to run inputs",
        )
        path = root / relative
        require(
            path.resolve().is_relative_to(root.resolve()),
            "Evidence escapes archive inputs",
        )
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != evidence["sha256"]
        ):
            # Hydrated upstream artifacts may have a new local name; identity is exact bytes.
            matches = [
                p
                for p in root.rglob("*")
                if p.is_file()
                and not p.is_symlink()
                and p.resolve().is_relative_to(root.resolve())
                and hashlib.sha256(p.read_bytes()).hexdigest() == evidence["sha256"]
            ]
            require(
                bool(matches),
                "Original evidence is missing or changed; import the original before continuing",
            )
            path = matches[0]
        loader(
            context_path, expected_workflow_id="adeguati-assetti", input_paths=[path]
        )
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == evidence["sha256"],
            "Evidence changed during validation",
        )


def main(argv: list[str] | None = None) -> int:
    """Persist every accepted event and deliver its immutable JSON and readable memo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-engagement", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("open")
    start.add_argument("--case-id", required=True)
    start.add_argument("--entity-name", required=True)
    start.add_argument("--actor", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--snapshot", type=Path, required=True)
    event = sub.add_parser("apply")
    event.add_argument("--event", type=Path, required=True)
    sub.add_parser("status")
    form = sub.add_parser("form")
    form.add_argument(
        "--questions",
        type=Path,
        help="Optional model-authored contextual questions in run outputs",
    )
    manual = sub.add_parser("manual")
    manual.add_argument("--manual-id", required=True)
    budget = sub.add_parser("budget")
    budget.add_argument("--artifact-id", required=True)
    budget.add_argument("--mapping", type=Path, required=True)
    args = parser.parse_args(argv)
    loader = _archive_loader()
    selected = (
        [args.event]
        if args.command == "apply"
        else (
            [args.snapshot]
            if args.command == "resume"
            else (
                [args.mapping]
                if args.command == "budget"
                else (
                    [args.questions]
                    if args.command == "form" and args.questions
                    else []
                )
            )
        )
    )
    context = loader(
        args.client_engagement,
        expected_workflow_id="adeguati-assetti",
        input_paths=selected,
    )
    require(
        context["schema_version"] == "vera.client_workflow_context.v2",
        "Construction requires portable Studio Archive v2",
    )
    output = Path(context["output_dir"])
    store = CaseStore(
        output / "assetti-construction.sqlite3",
        client_id=context["client_id"],
        engagement_id=context["engagement_id"],
    )
    if args.command == "open":
        catalog = json.loads(
            (ROOT / "references/construction-catalog.json").read_text(encoding="utf-8")
        )
        state = store.initialize(
            create_case(
                client_id=context["client_id"],
                engagement_id=context["engagement_id"],
                case_id=args.case_id,
                entity_name=args.entity_name,
                catalog=catalog,
                actor=args.actor,
                at=datetime.now(timezone.utc).isoformat(),
            )
        )
    elif args.command == "resume":
        state = json.loads(args.snapshot.read_text(encoding="utf-8"))
        # Resume only imported snapshots, never a model-authored JSON from outputs.
        require(
            args.snapshot.resolve().is_relative_to(
                (Path(context["run_root"]) / "inputs").resolve()
            ),
            "Resume requires an imported prior snapshot",
        )
        _validate_evidence(state, context, args.client_engagement, loader)
        state = store.initialize(state)
    else:
        state = store.read()
        _validate_evidence(state, context, args.client_engagement, loader)
        if args.command == "apply":
            envelope = json.loads(args.event.read_text(encoding="utf-8"))
            event_payload = envelope["event"]
            if event_payload["kind"] == "evidence":
                candidate = {"evidence": {"candidate": event_payload["payload"]}}
                _validate_evidence(candidate, context, args.client_engagement, loader)
            if event_payload["kind"] in {"artifact", "legacy_review"}:
                payload = event_payload["payload"]
                key = "document" if event_payload["kind"] == "artifact" else "record"
                if key in payload:
                    evidence_id = (
                        payload["source_id"]
                        if key == "document"
                        else payload["evidence_refs"][0]
                    )
                    evidence = state["evidence"][evidence_id]
                    candidates = [
                        Path(item["path"]) for item in context["input_bindings"]
                    ]
                    originals = [
                        path
                        for path in candidates
                        if hashlib.sha256(path.read_bytes()).hexdigest()
                        == evidence["sha256"]
                    ]
                    require(
                        bool(originals)
                        and json.loads(originals[0].read_text(encoding="utf-8"))
                        == payload[key],
                        "Embedded artifact differs from the exact imported original",
                    )
            state = store.commit(
                event_payload,
                request_id=envelope["request_id"],
                expected_revision=envelope["expected_revision"],
                actor=envelope["actor"],
                at=envelope["at"],
            )
    path = save_snapshot(state, output)
    if args.command == "form":
        questions = (
            json.loads(args.questions.read_text(encoding="utf-8"))
            if args.questions
            else None
        )
        rendered = render_form(state, questions=questions)
        form_hash = hashlib.sha256(rendered.encode()).hexdigest()
        write_once(output / f"visita-{form_hash}.html", rendered)
    elif args.command == "manual":
        export_manual(state, args.manual_id, output)
    elif args.command == "budget":
        require(args.artifact_id in state["artifacts"], "Unknown plan artifact")
        artifact = state["artifacts"][args.artifact_id]
        require(
            artifact["workflow_id"] == "business-planning"
            and artifact["adapter_status"] == "native_contract_verified",
            "Budget requires a verified native Business Planning artifact",
        )
        mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
        rows = budget_rows(artifact["document"], artifact, mapping)
        receipt = {
            "schema_version": "vera.assetti_budget_handoff.v1",
            "construction_snapshot_sha256": state["snapshot_sha256"],
            "artifact_id": args.artifact_id,
            "mapping": mapping,
            "rows": rows,
        }
        identity = digest(receipt)
        write_once(
            output / f"budget-{identity}.json",
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        )
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        write_once(output / f"budget-{identity}.csv", buffer.getvalue())
    logging.info("Construction revision %s saved: %s", state["revision"], path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
