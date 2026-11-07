"""Exact-ZIP CLI acceptance; deliberately does not claim native-host acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from openpyxl import load_workbook


@pytest.fixture
def installed(tmp_path):
    archive = os.environ.get("LUCIA_ACCEPTANCE_ZIP")
    if not archive:
        pytest.skip("Set LUCIA_ACCEPTANCE_ZIP to an exact staged candidate")
    install = tmp_path / "installazione Lucia è sola lettura"
    with ZipFile(archive) as zipped:
        zipped.extractall(install)
    manifests = list(install.rglob(".codex-plugin/plugin.json"))
    roots = [
        m.parent.parent
        for m in manifests
        if json.loads(m.read_text())["name"] == "lucia"
    ]
    assert len(roots) == 1
    root = roots[0]
    index = json.loads((root / "execution-files.json").read_text())
    for name, digest in index["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    for path in install.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    install.chmod(0o555)
    yield root
    for path in install.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    install.chmod(0o755)


def cli(root, script, *args, success=True):
    work_root = next(
        path
        for path in (root, *root.parents)
        if path.name == "installazione Lucia è sola lettura"
    ).parent
    result = subprocess.run(
        [
            os.environ.get("LUCIA_ACCEPTANCE_PYTHON", sys.executable),
            "-I",
            "-B",
            "-c",
            "import runpy,sys; from pathlib import Path; "
            "script=Path(sys.argv[1]); sys.path.insert(0,str(script.parent)); "
            "sys.argv=sys.argv[1:]; "
            "sys.addaudithook(lambda event,args: "
            "(_ for _ in ()).throw(RuntimeError('Network forbidden in acceptance')) "
            "if event in ('socket.connect','socket.getaddrinfo') else None); "
            "runpy.run_path(str(script),run_name='__main__')",
            str(root / "scripts" / script),
            *map(str, args),
        ],
        cwd=work_root,
        env={
            **{
                key: value
                for key, value in os.environ.items()
                if key not in {"PYTHONPATH", "PYTHONHOME"}
            },
            "MPARANZA_INCIDENT_DELIVERY": "local-only",
            "MPARANZA_INCIDENT_STATE_DIR": str(work_root / "stato reporting è"),
            "MPARANZA_INCIDENT_DEVICE_DIR": str(work_root / "dispositivo è"),
        },
        capture_output=True,
        text=True,
        timeout=45,
    )
    if success:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0, "Expected the specific invalid operation to fail"
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def prepare(root, work, workflow, *, second=False):
    source = work / "accordo.txt"
    source.write_text(
        "Cliente: Alfa S.r.l.\nPagamento entro 30 giorni.\nCompenso: EUR 1000.\n"
    )
    run = work / "result"
    args = [
        "prepare",
        "--run-dir",
        run,
        "--workflow",
        workflow,
        "--file",
        source,
        "--topic",
        "Pagamento",
    ]
    if second:
        other = work / "accordo-b.txt"
        other.write_text(
            "Cliente: Alfa S.r.l.\nPagamento entro 60 giorni.\nCompenso: EUR 1000.\n"
        )
        args.extend(["--file", other])
    cli(root, "legal_documents.py", *args)
    return run


def reviewed(run):
    review = json.loads((run / "review.json").read_text())
    evidence = json.loads((run / "evidence.json").read_text())
    review["context"].update(
        represented_party="Cliente Alfa S.r.l. (caso sintetico)",
        jurisdiction="Non fornita; lettura testuale senza parere di validità",
        instructions="Confrontare i termini di pagamento forniti",
        relationship="Cliente e prestatore; ulteriori fatti non forniti",
        formation="Non documentata",
        forum="Non fornito",
        legal_basis="Nessuna fonte normativa fornita o ricercata",
        firm_instructions="Nessuna",
        language="it",
    )
    for source, item in zip(evidence["sources"], review["items"]):
        quote = (
            "Pagamento entro 30 giorni."
            if source["id"] == "D001"
            else "Pagamento entro 60 giorni."
        )
        review["coverage"][source["id"]]["reviewed_anchors"] = [
            u["anchor"] for u in source["units"]
        ]
        item.update(
            status="supported",
            summary=quote,
            reasoning="Il testo indica il numero di giorni, senza specificare l'evento iniziale.",
            proposal="Chiarire la decorrenza nel testo concordato.",
            citations=[{"source_id": source["id"], "anchor": "line:2", "quote": quote}],
        )
    review["takeaways"] = [
        "Decorrenza non specificata nelle tre righe fornite; nessuna conclusione giuridica."
    ]
    if len(evidence["sources"]) == 2:
        review["differences"] = {
            "Pagamento": "La seconda versione indica 60 giorni anziché 30; la decorrenza resta non specificata."
        }
    write_json(run / "review.json", review)
    return review


@pytest.mark.parametrize(
    "workflow",
    [
        "revisione-contratti",
        "confronto-documenti",
        "revisione-documentale",
        "estrazione-clausole",
    ],
)
def test_exact_package_document_pipeline_delivers_source_linked_outputs(
    installed, tmp_path, workflow
):
    engine = "revisione-documentale" if workflow == "estrazione-clausole" else workflow
    run = prepare(
        installed,
        tmp_path,
        engine,
        second=workflow in {"confronto-documenti", "revisione-documentale"},
    )
    reviewed(run)
    if workflow == "confronto-documenti":
        cli(
            installed,
            "legal_documents.py",
            "compare",
            "--run-dir",
            run,
            "--before",
            "D001",
            "--after",
            "D002",
        )
    cli(
        installed,
        "legal_documents.py",
        "render",
        "--run-dir",
        run,
        "--review",
        run / "review.json",
    )
    assert "Pagamento entro 30 giorni" in (run / "review.html").read_text()
    workbook = load_workbook(run / "review.xlsx", read_only=True)
    assert len(workbook.sheetnames) >= 3
    assert json.loads((run / "validation.json").read_text())["valid"] is True


def test_exact_package_proofreading_delivers_findings_with_visual_gap(
    installed, tmp_path
):
    run = prepare(installed, tmp_path, "controllo-documento")
    review = reviewed(run)
    cli(installed, "legal_proofreading.py", "scaffold", "--run-dir", run)
    audit = json.loads((run / "proofreading.json").read_text())
    audit["context"] = review["context"]
    document = audit["documents"]["D001"]
    document["reviewed_anchors"] = ["line:1", "line:2", "line:3"]
    document["maps"] = {
        "entities": {
            "entries": [],
            "note": "La sola parte nominata è Alfa S.r.l.; il prestatore non è identificato nelle tre righe.",
        },
        "sections": {
            "entries": [],
            "note": "Tre righe senza sezioni numerate o indice.",
        },
        "terms": {
            "entries": [],
            "note": "Nessuna definizione espressa; Cliente indica il ruolo nella prima riga.",
        },
    }
    document["passes"] = {
        "definitions": {
            "status": "complete",
            "note": "Nessuna definizione espressa o uso contraddittorio nelle tre righe.",
        },
        "references": {
            "status": "complete",
            "note": "Nessun rinvio ad articoli o allegati nelle tre righe.",
        },
        "consistency": {
            "status": "complete",
            "note": "Il termine ha durata ma non un evento iniziale nelle tre righe.",
        },
        "entities": {
            "status": "complete",
            "note": "Alfa S.r.l. compare una sola volta, senza varianti; controparte non identificata.",
        },
        "numbers": {
            "status": "complete",
            "note": "30 giorni ed EUR 1000 indicano quantità diverse; non è presente un calcolo da verificare.",
        },
        "language": {
            "status": "complete",
            "note": "Tre enunciati sintetici leggibili; nessun refuso testuale individuato.",
        },
        "numbering": {
            "status": "complete",
            "note": "Righe non numerate; nessuna sequenza dichiarata da controllare.",
        },
        "formatting": {
            "status": "complete",
            "note": "TXT su tre righe, senza formattazione OOXML; controllo limitato alla struttura testuale.",
        },
    }
    audit["findings"] = [
        {
            "id": "F1",
            "severity": "medium",
            "category": "consistency",
            "kind": "uncertain",
            "citations": review["items"][0]["citations"],
            "issue": "Decorrenza non specificata",
            "reason": "Il numero di giorni non identifica da quale evento contare.",
            "fix": "Chiedere la decorrenza prevista prima di modificarla.",
        }
    ]
    write_json(run / "proofreading.json", audit)
    cli(installed, "legal_proofreading.py", "render", "--run-dir", run)
    assert "Decorrenza non specificata" in (run / "proofreading.html").read_text()
    assert "Parte assistita" in (run / "proofreading.html").read_text()
    assert "represented_party" not in (run / "proofreading.html").read_text()
    assert "Verifica visiva non completata" in (run / "proofreading.html").read_text()
    validation = json.loads((run / "proofreading-validation.json").read_text())
    assert validation["valid"] is True
    assert validation["complete"] is False


def test_exact_package_template_drafting_preserves_original(installed, tmp_path):
    source = tmp_path / "modello.md"
    source.write_text("Cliente: [CLIENTE]\nCompenso: [DA CONFERMARE]\n")
    run = tmp_path / "draft-run"
    cli(
        installed,
        "legal_documents.py",
        "prepare",
        "--run-dir",
        run,
        "--workflow",
        "redazione-da-modello",
        "--file",
        source,
        "--topic",
        "Identità",
    )
    review = json.loads((run / "review.json").read_text())
    review["context"].update(
        represented_party="Alfa S.r.l. (identità sintetica fornita)",
        jurisdiction="Non fornita",
        instructions="Sostituire soltanto il segnaposto del cliente",
        relationship="Ruolo cliente nel modello; controparte non fornita",
        formation="Non documentata",
        forum="Non fornito",
        legal_basis="Nessuna fonte fornita; sostituzione fattuale",
        firm_instructions="Modello Markdown selezionato, senza versione dichiarata",
        language="it",
    )
    write_json(run / "review.json", review)
    (run / "open-questions.md").write_text(
        "Compenso da confermare; non inserito senza indicazione.\n"
    )
    changes = run / "changes.json"
    write_json(
        changes,
        [
            {
                "anchor": "line:1",
                "old": "[CLIENTE]",
                "new": "Alfa S.r.l.",
                "basis": "Nome sintetico fornito nel mandato di prova",
            }
        ],
    )
    cli(
        installed,
        "legal_documents.py",
        "draft",
        "--run-dir",
        run,
        "--template",
        "D001",
        "--changes",
        changes,
    )
    assert (
        run / "draft.md"
    ).read_text() == "Cliente: Alfa S.r.l.\nCompenso: [DA CONFERMARE]\n"
    assert source.read_text() == "Cliente: [CLIENTE]\nCompenso: [DA CONFERMARE]\n"


def test_exact_package_rejects_fabricated_quote_then_recovers(installed, tmp_path):
    run = prepare(installed, tmp_path, "revisione-contratti")
    review = reviewed(run)
    review["items"][0]["citations"][0]["quote"] = "Pagamento mai dovuto."
    write_json(run / "review.json", review)
    cli(
        installed,
        "legal_documents.py",
        "render",
        "--run-dir",
        run,
        "--review",
        run / "review.json",
        success=False,
    )
    assert not (run / "review.html").exists()
    reviewed(run)
    cli(
        installed,
        "legal_documents.py",
        "render",
        "--run-dir",
        run,
        "--review",
        run / "review.json",
    )
    assert (run / "review.html").is_file()


def test_exact_package_missing_input_is_reported_without_false_output(
    installed, tmp_path
):
    run = tmp_path / "missing-run"
    result = cli(
        installed,
        "legal_documents.py",
        "prepare",
        "--run-dir",
        run,
        "--workflow",
        "revisione-contratti",
        "--file",
        tmp_path / "missing.pdf",
        "--topic",
        "Pagamento",
        success=False,
    )
    assert "missing.pdf" in result.stderr
    assert not (run / "review.html").exists()


def test_exact_package_unreadable_pdf_remains_visible(installed, tmp_path):
    from pypdf import PdfWriter

    source = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(source)
    run = tmp_path / "blank-run"
    cli(
        installed,
        "legal_documents.py",
        "prepare",
        "--run-dir",
        run,
        "--workflow",
        "revisione-contratti",
        "--file",
        source,
        "--topic",
        "Pagamento",
    )
    pack = json.loads((run / "evidence.json").read_text())
    assert pack["sources"][0]["warnings"]
    review = json.loads((run / "review.json").read_text())
    assert review["items"][0]["status"] != "not-stated"


def test_exact_package_progress_reopens_without_reinitializing(installed, tmp_path):
    run = prepare(installed, tmp_path, "revisione-contratti")
    cli(
        installed,
        "legal_matter.py",
        "init",
        "--run-dir",
        run,
        "--kind",
        "documenti",
        "--purpose",
        "Verifica dei termini di pagamento",
    )
    original = (run / "matter.json").read_bytes()
    cli(installed, "legal_matter.py", "status", "--run-dir", run)
    cli(installed, "legal_matter.py", "render", "--run-dir", run)
    assert (run / "matter.json").read_bytes() == original
    assert "Verifica dei termini di pagamento" in (run / "matter.html").read_text()


def build_local_test_report(installed, tmp_path):
    run = tmp_path / "privacy-run"
    run.mkdir()
    request = {
        "schema_version": 1,
        "workflow_id": "revisione-contratti",
        "run_id": "synthetic-edition-report",
        "runtime_profile": "openai-codex",
        "language": "it",
        "created_at": "2026-11-06T16:00:00+01:00",
        "professional_purpose": "Prova sintetica del report del percorso documentale",
        "phases": [
            {
                "phase_id": "fixture-review",
                "purpose": "Registrare il limite della prova CLI",
                "outcome": "not_measurable",
                "evidence_basis": "not_measurable",
                "source_extent": [],
                "locally_processed": [],
                "model_visible": [],
                "remained_local": [],
                "reason": "Questa prova esegue helper da ZIP; non misura i payload del modello né la consegna in una chat nativa.",
                "evidence_files": [],
            }
        ],
        "improvement_assessment": {"status": "not_assessed", "candidates": []},
        "contract_review": {
            "status": "not_assessed",
            "phase_ids": [],
            "reason": "Verifica meccanica della persistenza del report, non accettazione della sessione host.",
        },
    }
    input_path = run / "input.json"
    write_json(input_path, request)
    result = cli(
        installed,
        "model_data_report.py",
        "build",
        "--input",
        input_path,
        "--evidence-root",
        run,
        "--output-dir",
        run,
        "--local-only",
    )
    response = json.loads(result.stdout)
    assert response["server_receipt"]["status"] == "not_requested"
    report = run / "model_data_report.json"
    original = report.read_bytes()
    shown = cli(installed, "model_data_report.py", "show", "--report", report)
    assert "Report sui dati arrivati al modello" in shown.stdout
    assert report.read_bytes() == original
    assert json.loads(original)["schema_version"] == 2
    assert (run / "privacy_contract.json").is_file()
    assert not (run / "model_data_receipt.json").exists()


def test_exact_package_privacy_report_reopens_offline_with_honest_measurement_gap(
    installed, tmp_path
):
    build_local_test_report(installed, tmp_path)


def test_exact_package_managed_verification_does_not_reenter_installer(installed):
    result = cli(installed, "check_dependencies.py", "--managed-verify")
    assert "requires the base Python" not in result.stderr
    assert "setup failed" not in result.stderr


def test_exact_package_missing_dependencies_are_reported_without_installing(installed):
    # -S deliberately removes installed site packages for this absence-path test.
    result = subprocess.run(
        [
            os.environ.get("LUCIA_ACCEPTANCE_PYTHON", sys.executable),
            "-S",
            str(installed / "scripts/check_dependencies.py"),
            "--managed-verify",
        ],
        cwd=installed,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if (installed / "distribution.json").is_file():
        assert result.returncode == 1
        assert "Document dependency unavailable" in result.stderr
        assert "install" not in result.stdout
    else:
        # The unchanged full checker checks registered component presence here;
        # actual dependency preparation is delegated per selected component.
        assert result.returncode == 0


@pytest.mark.parametrize("suffix", [".txt", ".md", ".docx", ".pdf"])
def test_alternative_sources_preserve_accented_text_and_originals(
    installed, tmp_path, suffix
):
    from docx import Document
    from reportlab.pdfgen.canvas import Canvas

    source = tmp_path / ("Accordo società è" + suffix)
    lines = [
        "Cliente: Società Èlite S.r.l.",
        "Pagamento entro 30 giorni.",
        "Compenso: EUR 1200 oltre IVA.",
        "Durata: dodici mesi.",
        "Rinnovo automatico salvo disdetta con 45 giorni di preavviso.",
        "Si applica l'articolo 9, non presente nel documento fornito.",
    ]
    if suffix == ".docx":
        document = Document()
        for line in lines:
            document.add_paragraph(line)
        document.sections[0].header.paragraphs[0].text = "Versione riservata — sintesi"
        document.save(source)
    elif suffix == ".pdf":
        canvas = Canvas(str(source))
        for index, line in enumerate(lines):
            canvas.drawString(40, 780 - 25 * index, line)
        canvas.save()
    else:
        source.write_text("\n".join(lines), encoding="utf-8-sig")
    original = source.read_bytes()
    run = tmp_path / "risultato società è"
    cli(
        installed,
        "legal_documents.py",
        "prepare",
        "--run-dir",
        run,
        "--workflow",
        "revisione-contratti",
        "--file",
        source,
        "--topic",
        "Pagamento",
    )
    pack = json.loads((run / "evidence.json").read_text())
    review = reviewed(run)
    unit = next(
        u
        for u in pack["sources"][0]["units"]
        if "Pagamento entro 30 giorni." in u["text"]
    )
    review["items"][0]["citations"][0]["anchor"] = unit["anchor"]
    write_json(run / "review.json", review)
    cli(
        installed,
        "legal_documents.py",
        "render",
        "--run-dir",
        run,
        "--review",
        run / "review.json",
    )
    assert "Società Èlite" in " ".join(u["text"] for u in pack["sources"][0]["units"])
    assert (run / "originals" / ("D001" + suffix)).read_bytes() == original
    assert source.read_bytes() == original
    assert "Pagamento entro 30 giorni" in (run / "review.html").read_text()


@pytest.mark.parametrize("target", ["evidence.json", "originals/D001.txt"])
def test_stale_evidence_rejected_then_original_bytes_recover(
    installed, tmp_path, target
):
    run = prepare(installed, tmp_path, "revisione-contratti")
    reviewed(run)
    path = run / target
    original = path.read_bytes()
    path.write_bytes(original + b" altered")
    rejected = cli(
        installed,
        "legal_documents.py",
        "render",
        "--run-dir",
        run,
        "--review",
        run / "review.json",
        success=False,
    )
    assert "changed" in rejected.stderr
    assert not (run / "review.html").exists()
    path.write_bytes(original)
    cli(
        installed,
        "legal_documents.py",
        "render",
        "--run-dir",
        run,
        "--review",
        run / "review.json",
    )
    assert json.loads((run / "validation.json").read_text())["valid"] is True


def test_repeat_prepare_preserves_evidence_and_revision_archives_prior_output(
    installed, tmp_path
):
    run = prepare(installed, tmp_path, "revisione-contratti")
    evidence = (run / "evidence.json").read_bytes()
    rejected = cli(
        installed,
        "legal_documents.py",
        "prepare",
        "--run-dir",
        run,
        "--workflow",
        "revisione-contratti",
        "--file",
        tmp_path / "accordo.txt",
        "--topic",
        "Pagamento",
        success=False,
    )
    assert "already exists" in rejected.stderr
    assert (run / "evidence.json").read_bytes() == evidence
    review = reviewed(run)
    cli(
        installed,
        "legal_documents.py",
        "render",
        "--run-dir",
        run,
        "--review",
        run / "review.json",
    )
    previous = (run / "review.html").read_bytes()
    review["items"][0][
        "proposal"
    ] = "Precisare se i 30 giorni decorrono dalla ricezione della fattura."
    write_json(run / "review.json", review)
    cli(
        installed,
        "legal_documents.py",
        "render",
        "--run-dir",
        run,
        "--review",
        run / "review.json",
    )
    assert "ricezione della fattura" in (run / "review.html").read_text()
    assert any(p.read_bytes() == previous for p in run.glob("previous-*-review.html"))
    review["items"][0]["citations"][0]["anchor"] = "line:999"
    write_json(run / "review.json", review)
    cli(
        installed,
        "legal_documents.py",
        "render",
        "--run-dir",
        run,
        "--review",
        run / "review.json",
        success=False,
    )
    assert not (run / "review.html").exists()


@pytest.mark.parametrize(
    "name,payload",
    [
        ("corrotto.docx", b"not a zip"),
        ("corrotto.pdf", b"not a pdf"),
        ("non utf8.txt", b"\xff\xfe\xff"),
    ],
)
def test_corrupt_sources_remain_explicit_gaps(installed, tmp_path, name, payload):
    source = tmp_path / name
    source.write_bytes(payload)
    run = tmp_path / "corrotto risultato"
    cli(
        installed,
        "legal_documents.py",
        "prepare",
        "--run-dir",
        run,
        "--workflow",
        "revisione-contratti",
        "--file",
        source,
        "--topic",
        "Pagamento",
    )
    evidence = json.loads((run / "evidence.json").read_text())
    assert evidence["sources"][0]["error"]
    assert (
        json.loads((run / "review.json").read_text())["items"][0]["status"]
        != "not-stated"
    )
    assert not (run / "review.html").exists()


def test_usage_local_only_repeated_start_completion_and_failure_leave_delivery_intact(
    installed, tmp_path
):
    from uuid import uuid4

    run = prepare(installed, tmp_path, "revisione-contratti")
    reviewed(run)
    cli(
        installed,
        "legal_documents.py",
        "render",
        "--run-dir",
        run,
        "--review",
        run / "review.json",
    )
    deliverable = (run / "review.html").read_bytes()
    run_id = str(uuid4())
    start = [
        "start",
        "--run-id",
        run_id,
        "--pipeline",
        "revisione-contratti",
        "--host",
        "codex",
        "--sample-kind",
        "agent_test",
    ]
    cli(installed, "workflow_usage.py", *start)
    cli(installed, "workflow_usage.py", *start)
    cli(
        installed,
        "workflow_usage.py",
        "record",
        "--run-id",
        run_id,
        "--kind",
        "completed",
    )
    status = json.loads(
        cli(installed, "workflow_usage.py", "status", "--run-id", run_id).stdout
    )
    assert status["remote"] is None
    assert [r["event"]["kind"] for r in status["local_events"]] == [
        "started",
        "completed",
    ]
    assert status["queued"] == 2
    assert all(not r["acknowledged"] for r in status["local_events"])
    cli(
        installed,
        "workflow_usage.py",
        "stamp-report",
        "--run-id",
        run_id,
        "--report",
        run / "absent.json",
        "--output-dir",
        run,
        success=False,
    )
    assert (run / "review.html").read_bytes() == deliverable


def test_local_report_rejects_altered_report_without_recomputing_work(
    installed, tmp_path
):
    build_local_test_report(installed, tmp_path)
    report = tmp_path / "privacy-run/model_data_report.json"
    original = report.read_bytes()
    cli(installed, "model_data_report.py", "validate", "--report", report)
    payload = json.loads(original)
    payload["phases"][0]["outcome"] = "invented-success"
    write_json(report, payload)
    cli(
        installed, "model_data_report.py", "validate", "--report", report, success=False
    )
    report.write_bytes(original)
    cli(installed, "model_data_report.py", "show", "--report", report)
    assert report.read_bytes() == original


def test_receipt_retry_honors_local_only_without_attempting_network(
    installed, tmp_path
):
    from uuid import uuid4

    build_local_test_report(installed, tmp_path)
    run = tmp_path / "privacy-run"
    report = run / "model_data_report.json"
    original = report.read_bytes()
    result = json.loads(
        cli(
            installed,
            "workflow_usage.py",
            "stamp-report",
            "--run-id",
            str(uuid4()),
            "--report",
            report,
            "--output-dir",
            run,
        ).stdout
    )
    assert result["status"] == "not_requested"
    assert result["reason"] == "local_only"
    assert not (run / "model_data_receipt_request.json").exists()
    assert not (run / "model_data_receipt.json").exists()
    assert report.read_bytes() == original


def test_usage_build_report_binds_evidence_and_rejects_later_evidence_change(
    installed, tmp_path
):
    from uuid import uuid4

    build_local_test_report(installed, tmp_path)
    request = json.loads((tmp_path / "privacy-run/input.json").read_text())
    run = tmp_path / "usage report è"
    run.mkdir()
    request["run_id"] = run_id = str(uuid4())
    request["phases"][0]["evidence_files"] = ["proof.txt"]
    (run / "proof.txt").write_text(
        "Evidenza sintetica: file controllato, esposizione non misurata.\n"
    )
    write_json(run / "input.json", request)
    cli(
        installed,
        "workflow_usage.py",
        "start",
        "--run-id",
        run_id,
        "--pipeline",
        "revisione-contratti",
        "--host",
        "codex",
        "--sample-kind",
        "agent_test",
    )
    result = json.loads(
        cli(
            installed,
            "workflow_usage.py",
            "build-report",
            "--run-id",
            run_id,
            "--input",
            run / "input.json",
            "--evidence-root",
            run,
            "--output-dir",
            run,
            "--local-only",
        ).stdout
    )
    assert result["server_receipt"]["status"] == "not_requested"
    report = run / "model_data_report.json"
    cli(installed, "model_data_report.py", "validate", "--report", report)
    (run / "proof.txt").write_text("Altered evidence")
    result = cli(
        installed, "model_data_report.py", "validate", "--report", report, success=False
    )
    assert "evidence file changed" in result.stderr
    assert (run / "model_data_report.md").is_file()


def test_matter_revision_rejects_stale_write_and_reopens_answer(installed, tmp_path):
    run = prepare(installed, tmp_path, "revisione-contratti")
    cli(
        installed,
        "legal_matter.py",
        "init",
        "--run-dir",
        run,
        "--kind",
        "documenti",
        "--purpose",
        "Chiarire la decorrenza",
    )
    state = json.loads((run / "matter.json").read_text())
    state["purpose"] = (
        "Decorrenza chiarita: ricezione fattura, indicazione sintetica del cliente"
    )
    proposed = run / "proposta.json"
    write_json(proposed, state)
    cli(
        installed,
        "legal_matter.py",
        "save",
        "--run-dir",
        run,
        "--state",
        proposed,
        "--expected-revision",
        "0",
    )
    saved = (run / "matter.json").read_bytes()
    cli(
        installed,
        "legal_matter.py",
        "save",
        "--run-dir",
        run,
        "--state",
        proposed,
        "--expected-revision",
        "0",
        success=False,
    )
    cli(installed, "legal_matter.py", "status", "--run-dir", run)
    assert (run / "matter.json").read_bytes() == saved
    assert "ricezione fattura" in json.loads(saved)["purpose"]


def test_word_bridge_accepts_declared_clean_edit_rejects_unapplied_edit(
    installed, tmp_path
):
    from docx import Document

    original = tmp_path / "contratto è.docx"
    edited = tmp_path / "revisione è.docx"
    document = Document()
    document.add_paragraph("Pagamento entro 30 giorni.")
    document.save(original)
    document.paragraphs[0].text = "Pagamento entro 60 giorni."
    document.save(edited)
    request = tmp_path / "word-request.json"
    write_json(
        request,
        {
            "source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
            "mode": "clean",
            "edits": [
                {
                    "id": "E1",
                    "kind": "replace",
                    "anchor": "word/document.xml#p1",
                    "old": "30 giorni",
                    "new": "60 giorni",
                    "basis": "Modifica sintetica richiesta",
                }
            ],
        },
    )
    report = tmp_path / "word-verification.json"
    cli(
        installed,
        "legal_word_bridge.py",
        "--original",
        original,
        "--result",
        edited,
        "--request",
        request,
        "--report",
        report,
    )
    assert json.loads(report.read_text())["valid"] is True
    cli(
        installed,
        "legal_word_bridge.py",
        "--original",
        original,
        "--result",
        original,
        "--request",
        request,
        "--report",
        report,
        success=False,
    )
    assert not report.exists()
    prior = list(tmp_path.glob("previous-*-word-verification.json"))
    assert len(prior) == 1
    assert json.loads(prior[0].read_text())["valid"] is True


def test_every_packaged_python_module_loads_without_repository_or_other_plugin(
    installed, tmp_path
):
    code = """
import sys, importlib, importlib.util
from pathlib import Path
p, root = map(Path, sys.argv[1:3])
sys.path.insert(0, str(p.parent))
sys.path.append(str(root / 'scripts'))
for parent in p.parents:
    if parent == root.parent:
        break
    for suffix in ('vendor/modules', 'vendor'):
        if (parent / suffix).is_dir():
            sys.path.append(str(parent / suffix))
def deny(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo', 'subprocess.Popen'):
        raise RuntimeError('Module load attempted external action: ' + event)
sys.addaudithook(deny)
parts, q = [], p.parent
while (q / '__init__.py').exists():
    parts.insert(0, q.name)
    q = q.parent
if parts:
    sys.path.insert(0, str(q))
    importlib.import_module('.'.join(parts + ([p.stem] if p.stem != '__init__' else [])))
else:
    spec = importlib.util.spec_from_file_location('_audit_module', p)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
"""
    results = []
    for path in sorted(installed.rglob("*.py")):
        result = subprocess.run(
            [
                os.environ.get("LUCIA_ACCEPTANCE_PYTHON", sys.executable),
                "-I",
                "-B",
                "-c",
                code,
                str(path),
                str(installed),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=30,
            env={
                **os.environ,
                "MPARANZA_INCIDENT_DELIVERY": "local-only",
                "MPARANZA_INCIDENT_STATE_DIR": str(tmp_path / "isolated-state"),
            },
        )
        results.append(
            {
                "path": str(path.relative_to(installed)),
                "code": result.returncode,
                "stderr": result.stderr,
            }
        )
    write_json(tmp_path / "module-load-results.json", results)
    assert results
    assert [r for r in results if r["code"]] == []


def test_full_mcp_discovery_or_reduced_absence_matches_distribution(
    installed, tmp_path
):
    import shutil

    config = installed / ".mcp.json"
    if (installed / "distribution.json").exists():
        assert not config.exists()
        assert not list(installed.rglob("*.cjs"))
        return
    node = shutil.which("node")
    assert node, "MCP startup requires Node on this acceptance host"
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "isolated-lucia-audit", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    declaration = json.loads(config.read_text())["mcpServers"]["lucia"]
    result = subprocess.run(
        [node, *declaration["args"]],
        cwd=installed,
        input="".join(json.dumps(m) + "\n" for m in messages),
        text=True,
        capture_output=True,
        timeout=30,
        env={
            **os.environ,
            "MPARANZA_INCIDENT_DELIVERY": "local-only",
            "MPARANZA_INCIDENT_STATE_DIR": str(tmp_path / "mcp-state"),
            "MPARANZA_INCIDENT_DEVICE_DIR": str(tmp_path / "mcp-device"),
        },
    )
    assert result.returncode == 0, result.stderr
    replies = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    write_json(tmp_path / "mcp-discovery.json", replies)
    names = {
        tool["name"]
        for reply in replies
        if reply.get("id") == 2
        for tool in reply["result"]["tools"]
    }
    assert "check_studio_import_sources" in names
    assert len(names) >= 50


def test_representative_comparison_preserves_liability_exceptions(installed, tmp_path):
    before = tmp_path / "Accordo società A.md"
    after = tmp_path / "Accordo società B.md"
    a = [
        "Cliente: Società Èlite S.r.l.; fornitore: Beta S.r.l.",
        "Pagamento entro 30 giorni dalla ricezione della fattura.",
        "Compenso mensile: EUR 1200 oltre IVA; manutenzione del sito.",
        "Durata: 12 mesi senza rinnovo automatico.",
        "Responsabilità limitata a EUR 10000, salvo dolo o colpa grave.",
        "Il fornitore può interrompere immediatamente il servizio.",
        "Il servizio comprende gli interventi descritti nell'articolo 9.",
    ]
    b = [
        a[0],
        "Pagamento entro 60 giorni dalla ricezione della fattura.",
        "Compenso mensile: EUR 1440 oltre IVA; manutenzione del sito.",
        "Durata: 12 mesi, rinnovo automatico salvo disdetta con preavviso di 45 giorni.",
        "Responsabilità limitata a EUR 2000, salvo dolo o colpa grave. Il limite non opera per violazioni della riservatezza.",
        "Il fornitore può interrompere il servizio con preavviso di 30 giorni.",
        "Articolo 9: aggiornamenti mensili e correzione dei malfunzionamenti segnalati.",
    ]
    before.write_text("\n".join(a))
    after.write_text("\n".join(b))
    run = tmp_path / "confronto sostanziale è"
    topics = ["Pagamento", "Durata", "Responsabilità", "Servizio"]
    args = [
        "prepare",
        "--run-dir",
        run,
        "--workflow",
        "confronto-documenti",
        "--file",
        before,
        "--file",
        after,
    ]
    for topic in topics:
        args.extend(["--topic", topic])
    cli(installed, "legal_documents.py", *args)
    review = json.loads((run / "review.json").read_text())
    review["context"].update(
        represented_party="Cliente Società Èlite, caso sintetico",
        jurisdiction="Non fornita",
        instructions="Confrontare le condizioni conservando le eccezioni",
        relationship="Cliente e fornitore manutenzione",
        formation="Non documentata",
        forum="Non fornito",
        legal_basis="Solo testi selezionati; nessun giudizio di validità",
        firm_instructions="Nessuna",
        language="it",
    )
    differences = {
        "Pagamento": "Prezzo da EUR 1200 a EUR 1440 (+20%); pagamento da 30 a 60 giorni dalla ricezione fattura.",
        "Durata": "B introduce rinnovo automatico e disdetta a 45 giorni; durata dei rinnovi non precisata.",
        "Responsabilità": "Il limite scende da EUR 10000 a EUR 2000; entrambe escludono dolo e colpa grave. B aggiunge l'eccezione per riservatezza, da non omettere.",
        "Servizio": "A rinvia a un articolo 9 assente dal testo fornito e consente interruzione immediata. B descrive il servizio all'articolo 9 e richiede 30 giorni di preavviso.",
    }
    selected = {
        "Pagamento": [2, 3],
        "Durata": [4],
        "Responsabilità": [5],
        "Servizio": [6, 7],
    }
    for source_id in ["D001", "D002"]:
        review["coverage"][source_id]["reviewed_anchors"] = [
            f"line:{n}" for n in range(1, 8)
        ]
    for item in review["items"]:
        lines = a if item["source_id"] == "D001" else b
        item.update(
            status="supported",
            summary=" ".join(lines[n - 1] for n in selected[item["topic"]]),
            reasoning=differences[item["topic"]],
            proposal="Confermare la scelta commerciale e gli eventuali allegati con il cliente.",
            citations=[
                {
                    "source_id": item["source_id"],
                    "anchor": f"line:{n}",
                    "quote": lines[n - 1],
                }
                for n in selected[item["topic"]]
            ],
        )
    review["differences"] = differences
    review["takeaways"] = list(differences.values())
    write_json(run / "review.json", review)
    cli(
        installed,
        "legal_documents.py",
        "compare",
        "--run-dir",
        run,
        "--before",
        "D001",
        "--after",
        "D002",
    )
    cli(
        installed,
        "legal_documents.py",
        "render",
        "--run-dir",
        run,
        "--review",
        run / "review.json",
    )
    html = (run / "review.html").read_text()
    assert "Il limite non opera per violazioni della riservatezza" in html
    assert "(+20%)" in html
    assert "articolo 9 assente" in html
    workbook = load_workbook(run / "review.xlsx", read_only=True)
    values = [
        str(v)
        for sheet in workbook
        for row in sheet.values
        for v in row
        if v is not None
    ]
    assert any("riservatezza" in v and "EUR 2000" in v for v in values)
    assert json.loads((run / "validation.json").read_text())["valid"] is True
