"""Unapproved, model-authored reading of the fictional New Client kit.

This test-only interpretation is not a shipped answer or a learner approval.
Production teaching must read the inputs and run the current workflow itself.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import mimetypes
import shutil
import subprocess
from pathlib import Path

__all__ = ["case_input", "review_and_deliver", "complete_case", "words"]

ROOT = Path(__file__).resolve().parents[2]


def words(language):
    return json.loads(
        (ROOT / "tests/fixtures/teaching_reviews/new-client.json").read_text()
    )[language]


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case_input(starter, run, language, previous=None):
    """Retain the preceding reported facts and bind the new run's actual notes."""
    value = copy.deepcopy(previous if previous is not None else starter)
    prose = words(language)
    evidence = []
    for binding in run["context"]["input_bindings"]:
        source = Path(binding["path"])
        evidence.append(
            {
                "evidence_id": (
                    "profile"
                    if source.name.startswith("profile-")
                    else "contact-update"
                ),
                "evidence_type": "fictional_interview_notes",
                "status": "available",
                "obtained_on": "2026-09-14",
                "expires_on": None,
                "local_path": str(source),
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )
    value["evidence_register"] = evidence
    value["client_file_preparation_binding"]["evidence_ids"] = [
        row["evidence_id"] for row in evidence
    ]
    if previous is None:
        facts = {
            "registered_identity": "Officina Arco Srl",
            "registered_address": "Via Esempio 10, Milano, Italia",
            "business_activity": prose["activity"],
            "representative_reported": "Elena Esempio",
            "shareholdings_reported": "Elena Esempio 60%; Paolo Prova 40%",
            "employee_count": "12",
        }
        value["party_facts"] = [
            {
                "fact_id": f"party-fact-{index:02}",
                "fact_code": key,
                "value": fact,
                "verification_status": "reported",
                "evidence_ids": ["profile"],
            }
            for index, (key, fact) in enumerate(facts.items(), start=1)
        ]
        value["engagement"]["services"][0]["description"] = prose["service"]
    else:
        value["party_facts"].append(
            {
                "fact_id": "contact-fact",
                "fact_code": "administrative_contact",
                "value": "Sara Campione; sara@arco.example; " + prose["contact_role"],
                "verification_status": "reported",
                "evidence_ids": ["contact-update"],
            }
        )
    return value


def _review_tool(run, name, decisions):
    node = shutil.which("node")
    assert node, "New Client persistent review requires the declared Node runtime."
    output = Path(run["output_dir"])
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": {
                "client_engagement": str(run["context_path"]),
                "run_intake": _read(output / "run_intake.json"),
                "review_payload": _read(output / "review_payload.json"),
                "final_artifacts": _read(output / "final_artifacts.json"),
                "ui_decisions": _read(output / "ui_decisions.json"),
                "decisions": decisions,
                "reviewer": "fictional-kit-regression-reviewer",
                "decision_source": "synthetic-regression-fixture",
            },
        },
    }
    process = subprocess.run(
        [node, str(ROOT / "plugins/new-client/mcp/server.cjs"), "--stdio"],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=ROOT,
    )
    assert process.returncode == 0, process.stderr
    response = next(
        json.loads(line)
        for line in process.stdout.splitlines()
        if json.loads(line).get("id") == 1
    )
    assert response["result"]["isError"] is False, response
    return response["result"]["structuredContent"]


def review_and_deliver(run, language, *, follow_up):
    """Exercise real local review persistence without simulating acceptance."""
    output = Path(run["output_dir"])
    prose = words(language)
    payload = _read(output / "review_payload.json")
    item = next(row for row in payload["items"] if row["id"] == "party:profile")
    decisions = [
        {
            "item_id": item["id"],
            "action": "request_more_documents",
            "requested_documents": [prose["questions"][0]],
            "reviewer_note": prose["review_note"],
        }
    ]
    assert _review_tool(run, "validate_new_client_review", [])["ok"] is True
    rendered = _review_tool(run, "render_new_client_review", [])
    assert rendered["decision_policy"]["can_persist"] is True
    assert str(output) not in json.dumps(rendered)
    saved = _review_tool(run, "save_new_client_decisions", decisions)
    assert saved["persisted"] is True
    # This first-use lesson stops at an incomplete review and a draft request.
    # There is no completed professional review to apply or accept.
    assert not (output / "applied_decisions.json").exists()
    assert "request_more_documents" in json.dumps(_read(output / "ui_decisions.json"))
    question_text = f"# {prose['questions_title']}\n\n{prose['questions_intro']}\n\n"
    question_text += "\n\n".join(
        f"{index}. {question}"
        for index, question in enumerate(prose["questions"], start=1)
    )
    (output / "client_questions.md").write_text(question_text + "\n", encoding="utf-8")
    review_text = f"# {prose['review_title']}\n\n{prose['review']}\n\n"
    if follow_up:
        review_text += prose["practice"] + "\n\n"
    review_text += prose["next"] + "\n"
    (output / "run_review.md").write_text(review_text, encoding="utf-8")
    card = f"# {prose['title']}\n\n{prose['summary']}\n\n"
    card += "\n".join(
        f"- [{prose[label]}]({output / file})"
        for label, file in (
            ("memo_link", "studio_new_client_memo.md"),
            ("questions_link", "client_questions.md"),
            ("review_link", "run_review.md"),
        )
    )
    card += (
        "\n\n"
        + (prose["practice"] + "\n\n" if follow_up else "")
        + prose["next"]
        + "\n"
    )
    (output / "artifact_card.md").write_text(card, encoding="utf-8")


def complete_case(run, client_root, run_command, language):
    """Create the actual local disclosure, seal all bytes, then close the ledger."""
    output = Path(run["output_dir"])
    context = run["context"]
    report_module = _module(
        "new_client_teaching_disclosure", "plugins/vera/scripts/model_data_report.py"
    )
    reason = {
        "it": "Questo controllo esegue codice locale su dati fittizi senza chiamate al modello o alla rete.",
        "en": "This check runs local code on fictional data without model or network calls.",
        "fr": "Ce contrôle exécute du code local sur des données fictives sans appel au modèle ou au réseau.",
        "de": "Diese Prüfung führt lokalen Code mit fiktiven Daten ohne Modell- oder Netzwerkaufrufe aus.",
        "es": "Esta comprobación ejecuta código local con datos ficticios sin llamadas al modelo ni a la red.",
    }[language]
    request = {
        "schema_version": 1,
        "workflow_id": "new-client",
        "run_id": context["run_id"],
        "runtime_profile": "openai-codex",
        "language": language,
        "created_at": "2026-09-15T08:00:00+00:00",
        "professional_purpose": reason,
        "phases": [
            {
                "phase_id": "fixture",
                "purpose": reason,
                "outcome": "no_case_data",
                "evidence_basis": "workflow_receipt",
                "source_extent": [],
                "locally_processed": [],
                "model_visible": [],
                "remained_local": [],
                "reason": reason,
                "evidence_files": [],
            }
        ],
        "improvement_assessment": {"status": "not_assessed", "candidates": []},
    }
    report, markdown = report_module.build_model_data_report(
        request, evidence_root=output
    )
    report_module.validate_model_data_report(report, evidence_root=output)
    (output / "model_data_report.json").write_text(json.dumps(report), encoding="utf-8")
    (output / "model_data_report.md").write_text(markdown, encoding="utf-8")
    output.chmod(0o700)
    for path in output.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    for action in ("seal", "validate"):
        run_command(
            "plugins/new-client/scripts/delivery_manifest.py",
            action,
            "--client-engagement",
            run["context_path"],
            "--output-dir",
            output,
        )
    ledger = _module(
        "new_client_teaching_ledger", "plugins/studio-archive/scripts/client_ledger.py"
    )
    declarations = [
        {
            "artifact_id": f"internal.teaching.{index}",
            "path": path.relative_to(output).as_posix(),
            "purpose": "Preserve actual fictional New Client execution and disclosure",
            "audience": "review",
            "media_type": mimetypes.guess_type(path.name)[0]
            or "application/octet-stream",
        }
        for index, path in enumerate(
            sorted(p for p in output.rglob("*") if p.is_file())
        )
    ]
    ledger.finalize_run(
        client_root, context["engagement_id"], context["run_id"], declarations
    )
    completed = ledger.complete_run(
        client_root, context["engagement_id"], context["run_id"]
    )
    assert completed["run"]["status"] == "completed"
    # Completion must not change any of the sealed output bytes.
    manifest = _read(output / "delivery_manifest.json")
    for receipt in manifest["artifacts"]:
        assert (
            hashlib.sha256((output / receipt["path"]).read_bytes()).hexdigest()
            == receipt["sha256"]
        )
    return ledger
