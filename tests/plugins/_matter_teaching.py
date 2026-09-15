"""Unapproved authored readings of the fictional matter-opening teaching files.

These regression fixtures are not shipped answers or learner decisions. Real
teaching reads current inputs and asks the learner to review the actual result.
"""

from __future__ import annotations

import copy
import csv
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

__all__ = ["prepare_intake", "review_and_deliver", "words"]

ROOT = Path(__file__).resolve().parents[2]


def words(language):
    return json.loads(
        (ROOT / "tests/fixtures/teaching_reviews/matter.json").read_text()
    )[language]


def _core():
    spec = importlib.util.spec_from_file_location(
        "matter_teaching_core",
        ROOT / "plugins/apertura-pratica/scripts/apertura_pratica_core.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_intake(output, language, previous=None):
    """Preserve case meaning while rebinding exact fresh evidence IDs."""
    path = output / "matter_intake.json"
    starter = json.loads(path.read_text())
    intake = copy.deepcopy(previous) if previous else starter
    prose = words(language)
    if previous:
        # Prior professional receipts are separate outputs, never carried forward.
        old_by_name = {
            item["original_name"]: item["evidence_id"]
            for item in previous["evidence_register"]
        }
        new_by_name = {
            item["original_name"]: item["evidence_id"]
            for item in starter["evidence_register"]
        }
        encoded = json.dumps(intake)
        for name, old_id in old_by_name.items():
            encoded = encoded.replace(json.dumps(old_id), json.dumps(new_by_name[name]))
        intake = json.loads(encoded)
        intake["run_id"] = starter["run_id"]
        intake["evidence_register"] = starter["evidence_register"]
    evidence = {row["original_name"]: row for row in intake["evidence_register"]}
    request_id = evidence[f"request-{language}.md"]["evidence_id"]
    supply_id = evidence[f"supply-{language}.md"]["evidence_id"]
    register = evidence["register.csv"]
    with (output / register["stored_path"]).open(
        newline="", encoding="utf-8-sig"
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert [row["Matter"] for row in rows] == ["DEMO-A", "DEMO-B", "DEMO-C"]
    assert {row["Client"] for row in rows} == {
        "Alfa Esempio Srl",
        "Omega Esempio Srl",
        "Iota Esempio Srl",
    }
    assert {row["Counterparty"] for row in rows} == {
        "Delta Esempio Srl",
        "Zeta Esempio Srl",
        "Kappa Esempio Srl",
    }
    intake["client"].update(
        display_name="Beta Laboratorio Srl",
        identity_status="reported",
        evidence_ids=[request_id],
    )
    if previous is None:
        intake["parties"] = [
            {
                "party_id": identity,
                "display_name": name,
                "party_type": kind,
                "roles": roles,
                "aliases": [],
                "identity_keys": [],
                "identity_status": "reported",
                "evidence_ids": [request_id],
                "assessment_basis": prose["identity"],
            }
            for identity, name, kind, roles in (
                (
                    "party-client-001",
                    "Beta Laboratorio Srl",
                    "organization",
                    ["client", "assisted_party"],
                ),
                (
                    "party-gamma",
                    "Gamma Forniture Srl",
                    "organization",
                    ["counterparty"],
                ),
                ("party-elena", "Elena Esempio", "individual", ["related_party"]),
            )
        ]
    summary = (
        (output / evidence[f"request-{language}.md"]["stored_path"])
        .read_text()
        .split("\n\n", 1)[1]
        .strip()
    )
    if previous:
        update = evidence[f"update-{language}.md"]
        summary += (
            "\n\n"
            + (output / update["stored_path"]).read_text().split("\n\n", 1)[1].strip()
        )
    intake["matter"].update(
        title=prose["title"],
        objective=prose["practice_objective" if previous else "objective"],
        requested_work=prose["requested_work"],
        summary=summary,
        jurisdiction={
            "status": "proposed",
            "primary": "IT",
            "additional": [],
            "basis": prose["posture"],
        },
        procedural_posture=prose["posture"],
        urgency="unknown",
    )
    intake["conflict_check"].update(
        register_scope="partial",
        register_snapshot_reference=register["sha256"],
        searched_at=_core().utc_now(),
        searched_party_ids=[p["party_id"] for p in intake["parties"]],
        search_method=prose["register"],
        candidates=[],
    )
    intake["conflict_check"]["professional_decision"]["basis"] = prose["review_note"]
    intake["engagement"]["scope_items"] = [
        {
            "scope_id": "scope-001",
            "description": prose["requested_work"],
            "status": "proposed",
            "evidence_ids": [request_id],
        }
    ]
    intake["engagement"]["exclusions"] = [prose["exclusions"]]
    intake["engagement"]["authority_status"] = "reported"
    intake["engagement"]["review"]["basis"] = prose["review_note"]
    intake["deadline_review"]["basis"] = prose["deadlines"]
    intake["missing_items"] = [
        {
            "item_id": key,
            "kind": kind,
            "description": prose[key],
            "requested_from": "firm" if key == "review_note" else "client",
            "blocking": True,
            "status": "open",
            "evidence_ids": ids,
        }
        for key, kind, ids in (
            ("documents", "document", [supply_id]),
            ("correspondence", "document", [request_id]),
            ("authority", "identity", [request_id]),
            ("review_note", "decision", [register["evidence_id"]]),
        )
    ]
    if previous:
        intake["missing_items"].append(
            {
                "item_id": "update_question",
                "kind": "decision",
                "description": prose["update_question"],
                "requested_from": "client",
                "blocking": True,
                "status": "open",
                "evidence_ids": [update["evidence_id"]],
            }
        )
    intake["folder_plan"] = [
        {
            "path": folder,
            "purpose": prose[key],
            "source_evidence_ids": ids,
            "status": "proposed",
        }
        for folder, key, ids in (
            ("01_Intake", "folder_intake", [request_id, register["evidence_id"]]),
            ("02_Evidence", "folder_evidence", [supply_id]),
            (
                "03_Correspondence",
                "folder_update",
                [update["evidence_id"]] if previous else [],
            ),
        )
    ]
    intake["model_assessment"] = {
        "provider": "test-fixture",
        "model": "unapproved-authored-source-reading",
        "recorded_at": _core().utc_now(),
        "assumptions": [],
        "unresolved_questions": [prose["review_note"]],
    }
    path.write_text(json.dumps(intake, ensure_ascii=False))
    return intake


def review_and_deliver(output, language, run_command, previous_output=None):
    """Render through MCP, apply a synthetic return, and retain real receipts."""
    core = _core()
    payload = core.load_json(output / "review_payload.json")
    node = shutil.which("node")
    assert node, "Matter-opening review needs the declared Node runtime."
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "render_apertura_pratica_review",
            "arguments": {"review_payload": payload},
        },
    }
    rendered = subprocess.run(
        [node, str(ROOT / "plugins/apertura-pratica/mcp/server.cjs")],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    result = json.loads(rendered.stdout)["result"]
    assert result["structuredContent"]["review_payload"] == payload
    prose = words(language)
    decisions = {
        "schema_version": "1.0",
        "workflow": "apertura-pratica",
        "run_id": payload["run_id"],
        "intake_sha256": payload["intake_sha256"],
        "review_payload_sha256": core.review_payload_hash(payload),
        "reviewer": "Synthetic regression reviewer, not a learner or real lawyer",
        "decision_source": "chat_confirmed",
        "confirmed_by_user": True,
        "saved_at": core.utc_now(),
        "decisions": [
            {"item_id": item["id"], "action": "return", "note": prose["review_note"]}
            for item in payload["items"]
        ],
    }
    decision_path = output / "pending_review_decisions.json"
    core.write_json(decision_path, decisions)
    run_command(
        "plugins/apertura-pratica/scripts/apply_review.py",
        output,
        decision_path,
        "--confirmed-by-user",
    )
    validation = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins/apertura-pratica/scripts/validate_run.py"),
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    # Native exit 1 describes this intentionally unresolved matter; 2 is an error.
    assert validation.returncode == 1, validation.stdout + validation.stderr
    receipts = core.load_json(output / "applied_decisions.json")
    assert {row["decision"] for row in receipts["scopes"].values()} == {"returned"}
    assert core.load_json(output / "validation_report.json")["status"] == "blocked"
    note = (
        prose["review_note"]
        + "\n\n"
        + (prose["update_question"] + "\n\n" if previous_output else "")
        + prose["next"]
    )
    (output / "teaching_review.md").write_text(note + "\n")
    display = core.display.labels(language)
    links = [
        (output / name, display[label])
        for name, label in (
            ("matter_opening_memo.md", "memo"),
            ("missing_information_request.md", "missing_title"),
            ("teaching_review.md", "next_action"),
            ("folder_plan.json", "folders"),
            ("review_payload.json", "review_payload"),
            ("pending_review_decisions.json", "saved_decisions"),
            ("applied_decisions.json", "applied_decisions"),
            ("validation_report.json", "validation_report"),
        )
    ]
    if previous_output:
        links.append(
            (previous_output / "matter_opening_memo.md", display["previous_memo"])
        )
    assert all(path.is_file() for path, _label in links)
    (output / "artifact_card.md").write_text(
        "# "
        + prose["title"]
        + "\n\n"
        + prose["next"]
        + "\n\n"
        + f"**{display['status']}:** {display['blocked']}\n\n"
        + f"[{display['run_directory']}]({output})\n\n"
        + "\n".join(f"- [{label}]({path})" for path, label in links)
        + "\n"
    )
