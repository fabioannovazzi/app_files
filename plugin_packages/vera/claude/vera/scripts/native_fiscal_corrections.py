"""Explicit fiscal corrections create a source-linked successor through public APIs.

Fixed identity, role, hash and receipt checks protect auditability. No document
classification, professional judgment, filing or Archive completion is inferred.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

__all__ = ["prepare_correction"]


def prepare_correction(binding: dict, loaded: dict, args: dict, api: Any) -> dict:
    """Conserve intent before ledger writes; never automatically repeat uncertain work."""
    if binding["workflow_id"] != "client-file-preparation":
        raise PermissionError("Fiscal corrections require the exact intake workflow")
    if "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","):
        raise PermissionError("Reviewer authority is required")
    if args.get("human_reviewed") is not True:
        raise ValueError("Explicit human review is required")
    key = args["idempotency_key"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
        raise ValueError("Invalid correction submission key")
    output = Path(loaded["output_dir"])
    directory = api.review_directory(output, "client-file-preparation")
    owner = api.configuration()
    signature = api.digest(
        {"actor": owner["actor_id"], "tenant": owner["tenant_id"], "arguments": args}
    )
    receipt = api.ui_state_directory(output) / (
        "fiscal-correction-" + api.digest([owner["actor_id"], key]) + ".json"
    )
    with api.write_lock(output):
        current = api.snapshot(binding, loaded, args)
        selected = current["selection"]
        if not selected or selected["item_type"] != "extracted_fiscal_field":
            raise ValueError("Select one exact fiscal field")
        api.file_preparation_handoff(directory)
        if receipt.exists():
            stored = api.read_json(receipt)
            if stored["signature"] != signature:
                raise ValueError("Correction submission key belongs to another request")
            if stored["status"] != "completed":
                raise ValueError(
                    "Correction outcome is uncertain; inspect its retained intent before recovery"
                )
            api.file_preparation_handoff(Path(stored["result"]["output_dir"]))
            return stored["result"]
        for pending_receipt in receipt.parent.glob("fiscal-correction-*.json"):
            if pending_receipt.name.endswith("-review.json"):
                continue
            previous_intent = api.read_json(pending_receipt)
            if (
                previous_intent.get("status") == "uncertain"
                and previous_intent.get("item_id") == selected["id"]
            ):
                raise ValueError(
                    "An earlier fiscal correction is uncertain; inspect its retained intent before another request"
                )
        import client_ledger

        if (
            client_ledger.load_engagement_manifest(
                Path(binding["client_root"]), binding["engagement_id"]
            )["status"]
            != "open"
        ):
            raise ValueError("Fiscal correction requires an open engagement")
        scripts = api.module_root("client-file-preparation") / "scripts"
        sys.path.insert(0, str(scripts))
        from fiscal_field_review import apply_field_corrections, field_identity
        from parse_fiscal_forms import FiscalField

        records = [
            json.loads(line)
            for line in (directory / "extracted/structured_fiscal_fields.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        reference = selected["data"]["field_ref"]
        previous = selected["data"].get("reviewed_correction")
        if previous:
            original = FiscalField(**previous["original"])
        else:
            original = next(
                (
                    FiscalField(**record)
                    for record in records
                    if field_identity(FiscalField(**record)) == reference
                ),
                None,
            )
        if original is None or field_identity(original) != reference:
            raise ValueError(
                "Fiscal correction field differs from the complete producer record"
            )
        payload = api.read_json(directory / "review_payload.json")
        document = next(
            item
            for item in payload["items"]
            if item["item_type"] == "document_inventory"
            and item["source_path"] == original.relative_path
        )
        text_path = directory / "extracted" / document["data"]["text_path"]
        if (
            not text_path.resolve().is_relative_to(directory.resolve())
            or text_path.is_symlink()
        ):
            raise ValueError("Fiscal correction source escapes the retained extraction")
        source = text_path.read_text(encoding="utf-8")
        decision = {
            "source_text_sha256": selected["data"]["source_text_sha256"],
            "value": args["value"],
            "basis": args["basis"],
            "reviewer": args["reviewer"],
            "confirmed_by_user": True,
        }
        apply_field_corrections(
            [original], {original.relative_path: source}, {reference: decision}
        )
        decisions_path = directory / "fiscal_field_corrections.json"
        decisions = api.read_json(decisions_path) if decisions_path.is_file() else {}
        decisions[reference] = decision
        proposal = receipt.with_name(receipt.stem + "-review.json")
        api.atomic_json(proposal, decisions)
        intent = {
            "signature": signature,
            "status": "uncertain",
            "source_revision": current["revision"],
            "item_id": selected["id"],
            "proposal_path": str(proposal),
        }
        api.atomic_json(receipt, intent)
        # The public ledger owns import receipts, exact original selections and the new run.
        sys.path.insert(0, str(api.module_root("studio-archive") / "scripts"))
        import client_ledger
        from native_archive_navigation import work_ref

        client_root = Path(binding["client_root"])
        imported = client_ledger.import_document(
            client_root,
            binding["client_id"],
            binding["engagement_id"],
            proposal,
            "support",
        )
        intent["imported_input_id"] = imported["receipt"]["input_id"]
        api.atomic_json(receipt, intent)
        kind_path = directory / "document_kind_decisions.json"
        kind_input_id = None
        if kind_path.is_file() and api.read_json(kind_path):
            kind_import = client_ledger.import_document(
                client_root,
                binding["client_id"],
                binding["engagement_id"],
                kind_path,
                "support",
            )
            kind_input_id = kind_import["receipt"]["input_id"]
            intent["document_kind_input_id"] = kind_input_id
        intent["imported_input_id"] = imported["receipt"]["input_id"]
        api.atomic_json(receipt, intent)
        prepared = client_ledger.prepare_run(
            client_root,
            binding["client_id"],
            binding["engagement_id"],
            "client-file-preparation",
            api.read_json(
                api.module_root("client-file-preparation") / ".codex-plugin/plugin.json"
            )["version"],
            input_ids=[
                row["binding_id"]
                for row in loaded["input_manifest"]["inputs"]
                if row["kind"] == "import"
            ]
            + [imported["receipt"]["input_id"]]
            + ([kind_input_id] if kind_input_id else []),
            upstream_artifacts=[
                {
                    "run_id": row["upstream_run_id"],
                    "artifact_id": row["upstream_artifact_id"],
                    "role": row["role"],
                }
                for row in loaded["input_manifest"]["inputs"]
                if row["kind"] == "upstream_artifact"
            ],
            label="Revisione dati fiscali",
            purpose="Regenerate the selected original sources with an explicitly reviewed fiscal correction.",
            idempotency_key="native-fiscal-" + signature[:40],
            new_run=True,
        )
        intent["successor_run_id"] = prepared["run"]["run_id"]
        api.atomic_json(receipt, intent)
        running = client_ledger.start_run(
            client_root, binding["engagement_id"], prepared["run"]["run_id"]
        )
        context = running["context"]
        support = next(
            row["path"]
            for row in context["input_bindings"]
            if row["binding_id"] == imported["receipt"]["input_id"]
        )
        intake = api.read_json(directory / "run_intake.json")
        command = [
            sys.executable,
            str(scripts / "build_file_preparation_outputs.py"),
            context["input_dir"],
            "--client-engagement",
            str(running["context_path"]),
            "--out",
            str(running["output_dir"]),
            "--language",
            payload["language"],
            "--jurisdiction",
            payload["jurisdiction"],
            "--fiscal-field-corrections",
            support,
        ]
        if kind_input_id:
            kind_support = next(
                row["path"]
                for row in context["input_bindings"]
                if row["binding_id"] == kind_input_id
            )
            command += ["--document-kind-decisions", kind_support]
        parameters = intake["assumptions"]
        year = parameters["target_year"]
        if parameters.get("ocr_requested") is False:
            command += ["--no-ocr"]
        if parameters.get("ocr_language"):
            command += ["--ocr-lang", parameters["ocr_language"]]
        if parameters.get("max_pages") is not None:
            command += ["--max-pages", str(parameters["max_pages"])]
        if year is not None:
            command += ["--year", str(year)]
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=120, check=False
        )
        if completed.returncode:
            raise ValueError(
                "Fiscal successor producer failed; inspect retained intent and run: "
                + completed.stderr[-2000:]
            )
        successor_output = Path(running["output_dir"])
        api.file_preparation_handoff(successor_output)
        result = {
            "status": "correction_generated",
            "revision": current["revision"],
            "source_work_ref": binding["work_ref"],
            "successor_work_ref": work_ref(
                binding["client_id"],
                binding["engagement_id"],
                prepared["run"]["run_id"],
            ),
            "successor_run_id": prepared["run"]["run_id"],
            "output_dir": str(successor_output),
            "native_successor_available": owner["mode"] == "studio-archive",
            "archive_completed": False,
        }
        api.atomic_json(receipt, {**intent, "status": "completed", "result": result})
        return result
