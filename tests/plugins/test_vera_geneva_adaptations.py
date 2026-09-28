"""Synthetic Geneva cases test shared calculations and jurisdiction boundaries."""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from tests.plugins.test_vera_studio_archive_component import (
    archive_core,
    indexed_archive,
)

ROOT = Path(__file__).resolve().parents[2]


def test_geneva_registry_keeps_jurisdiction_separate_from_language(tmp_path):
    from tests.plugins.test_registro_imprese_sari_plugin import (
        _load_script,
        _running_sari_workspace,
    )

    workspace = _running_sari_workspace(tmp_path)
    result = _load_script("initialize_case").initialize_case(
        Path(workspace["context"]["output_dir"]),
        run_id=workspace["run_id"],
        reference_date="2026-09-28",
        client_reference="synthetic-client",
        language="en",
        jurisdiction="CH-GE",
        client_engagement=workspace["context_path"],
    )
    assert json.loads(result["intake"].read_text())["jurisdiction"] == "CH-GE"
    assert json.loads(result["plan"].read_text())["jurisdiction"] == "CH-GE"
    url = "https://www.ge.ch/document/registre-du-commerce-documentation-formulaires"
    assert _load_script("case_core").validate_official_source_url(url) == url


def test_geneva_contribution_review_retains_institutional_basis(tmp_path):
    from tests.plugins.test_previdenza_inps_plugin import (
        _inventory_case,
        _load_script,
        _write_case_records,
        _write_claims,
    )

    _, output = _inventory_case(tmp_path, language="fr")
    records_path = _write_case_records(
        output / "case_records_draft.json", language="fr"
    )
    case = json.loads(records_path.read_text())
    case.update(
        jurisdiction="CH-GE",
        jurisdiction_basis="OCAS Genève; mandat synthétique; période 2021.",
    )
    records_path.write_text(json.dumps(case))
    claims_path = _write_claims(output / "claims_review.json")
    audit = _load_script("validate_case_records").validate_case_records(
        records_path, output / "file_inventory.json", output
    )
    assert audit["status"] == "passed"
    result = _load_script("package_case").package_case(
        output / "case_records_validated.json", claims_path, output
    )
    assert result["final_artifacts"]["status"] == "ready_for_professional_review"
    text = "\n".join(p.read_text() for p in output.glob("*.md"))
    assert "Revue du relevé de cotisations" in text
    assert "OCAS Genève" in text


@pytest.mark.parametrize(
    "component,script,factory",
    [
        ("new-client", "jurisdiction_setup", "setup_case"),
        ("bilancio-xbrl-it", "jurisdiction_accounts", "accounts_case"),
    ],
)
def test_geneva_adapter_runs_inside_real_archive_context(
    tmp_path, vera_workflow_workspace, component, script, factory
):
    case = globals()[factory](tmp_path)
    workspace = vera_workflow_workspace(
        component, input_files={"evidence.txt": (tmp_path / "evidence.txt").read_text()}
    )
    source = workspace["input_paths"][0]
    input_root = Path(workspace["context"]["run_root"]) / "inputs"
    case["sources"][0]["path"] = source.relative_to(input_root).as_posix()
    review = workspace["output_dir"] / "adapter-input.json"
    review.write_text(json.dumps(case))
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins" / component / "scripts" / f"{script}.py"),
            "--client-engagement",
            str(workspace["context_path"]),
            "--review",
            str(review),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    records = list(workspace["output_dir"].glob(f"{component}-*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record["client_id"] == workspace["context"]["client_id"]
    assert records[0].with_suffix(".md").is_file()


def test_professional_decision_cannot_move_to_another_client(tmp_path, monkeypatch):
    adapter = module(monkeypatch, "new-client", "jurisdiction_setup")
    case = setup_case(tmp_path)
    record = adapter.build_record(
        case, input_root=tmp_path, client_id="client-a", engagement_id="eng-a"
    )
    case["professional_decision"] = {
        "proposal_sha256": record["proposal_sha256"],
        "reviewer_ref": "reviewer",
        "conclusion": "Reviewed",
        "reviewed_at": "2026-09-28",
    }
    accepted = adapter.build_record(
        case, input_root=tmp_path, client_id="client-a", engagement_id="eng-a"
    )
    assert accepted["status"] == "professional_decision_recorded"
    with pytest.raises(ValueError, match="does not bind"):
        adapter.build_record(
            case, input_root=tmp_path, client_id="client-b", engagement_id="eng-a"
        )


def test_geneva_saved_record_is_idempotent_and_rejects_artifact_tampering(
    tmp_path, monkeypatch
):
    adapter = module(monkeypatch, "new-client", "jurisdiction_setup")
    from vera_assurance.jurisdiction import save

    record = adapter.build_record(
        setup_case(tmp_path),
        input_root=tmp_path,
        client_id="client-a",
        engagement_id="eng-a",
    )
    output = tmp_path / "output"
    path = save(record, adapter.render_memo(record), output)
    original = path.read_bytes()
    assert save(record, adapter.render_memo(record), output) == path
    assert path.read_bytes() == original
    path.with_suffix(".md").write_text("Altered after review")
    with pytest.raises(ValueError, match="Existing artifact differs"):
        save(record, adapter.render_memo(record), output)
    assert path.read_bytes() == original


def module(monkeypatch, component, name):
    monkeypatch.syspath_prepend(str(ROOT / "plugins" / component / "scripts"))
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    monkeypatch.delitem(sys.modules, name, raising=False)
    return importlib.import_module(name)


def envelope(tmp_path):
    source = tmp_path / "evidence.txt"
    source.write_text(
        "Synthetic Geneva evidence for mechanical checks, not professional acceptance."
    )
    return {
        "schema_version": 1,
        "jurisdiction": "CH-GE",
        "language": "fr",
        "as_of": "2026-09-28",
        "jurisdiction_basis": "Fictitious Geneva company; Swiss mandate.",
        "limitations": "Synthetic evidence only; professional assessment remains pending.",
        "sources": [
            {
                "id": "S1",
                "path": source.name,
                "title": "Synthetic evidence",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        ],
        "legal_basis": [
            {
                "title": "Illustrative Swiss framework",
                "url": "https://www.kmu.admin.ch/fr/comptabilite-obligatoire-lobligation-de-tenir-une-comptabilite",
                "locator": "Accounting framework",
                "checked_at": "2026-09-28",
                "applicability": "Test binding only; not a legal opinion.",
            }
        ],
    }


def citation():
    return [{"source_id": "S1", "locator": "line 1"}]


def accounts_case(tmp_path):
    case = envelope(tmp_path)
    case.update(
        entity_name="Exemple Sàrl",
        framework="CH-CO",
        currency="CHF",
        framework_assessment="Reviewed synthetic Swiss SME basis; no special entity regime.",
        trial_balance_basis="debit_positive_before_result_transfer",
        current_period_end="2026-06-30",
        prior_period_end="2025-06-30",
    )
    case["accounts"] = [
        {
            "id": "1000",
            "label": "Banque",
            "currency": "CHF",
            "current": "15000",
            "prior": "10000",
            "citations": citation(),
        },
        {
            "id": "2000",
            "label": "Fournisseurs",
            "currency": "CHF",
            "current": "-3000",
            "prior": "-2000",
            "citations": citation(),
        },
        {
            "id": "2800",
            "label": "Capital",
            "currency": "CHF",
            "current": "-8000",
            "prior": "-7000",
            "citations": citation(),
        },
        {
            "id": "3000",
            "label": "Ventes",
            "currency": "CHF",
            "current": "-9000",
            "prior": "-6000",
            "citations": citation(),
        },
        {
            "id": "4000",
            "label": "Charges",
            "currency": "CHF",
            "current": "5000",
            "prior": "5000",
            "citations": citation(),
        },
    ]
    case["statement_lines"] = [
        {
            "id": "cash",
            "group": "assets",
            "label": "Liquidités",
            "account_ids": ["1000"],
            "citations": citation(),
        },
        {
            "id": "payables",
            "group": "liabilities",
            "label": "Dettes fournisseurs",
            "account_ids": ["2000"],
            "citations": citation(),
        },
        {
            "id": "capital",
            "group": "equity",
            "label": "Capital",
            "account_ids": ["2800"],
            "citations": citation(),
        },
        {
            "id": "sales",
            "group": "income",
            "label": "Ventes",
            "account_ids": ["3000"],
            "citations": citation(),
        },
        {
            "id": "costs",
            "group": "expenses",
            "label": "Charges",
            "account_ids": ["4000"],
            "citations": citation(),
        },
    ]
    case["disclosure_review"] = [
        {
            "id": "notes",
            "title": "Annexe",
            "requirement": "Assess applicable notes and comparative presentation.",
            "assessment": "Professional completeness review outstanding.",
            "status": "unresolved",
            "citations": citation(),
        }
    ]
    return case


def test_swiss_accounts_reconcile_both_periods_and_keep_disclosure_open(
    tmp_path, monkeypatch
):
    adapter = module(monkeypatch, "bilancio-xbrl-it", "jurisdiction_accounts")
    result = adapter.build_record(
        accounts_case(tmp_path),
        input_root=tmp_path,
        client_id="client-a",
        engagement_id="eng-a",
    )
    assert result["results"]["result"] == {"current": "4000", "prior": "1000"}
    assert result["results"]["balance_reconciliation"] == {"current": "0", "prior": "0"}
    assert result["results"]["unresolved_disclosures"] == ["notes"]
    assert result["results"]["filing_ready"] is False
    assert "15000" in adapter.render_memo(result)
    assert "Comptes annuels" in adapter.render_memo(result)


@pytest.mark.parametrize(
    "fault",
    ["currency", "jurisdiction", "missing_account", "changed_source", "stale_review"],
)
def test_swiss_accounts_reject_unsupported_or_unbound_case(
    tmp_path, monkeypatch, fault
):
    adapter = module(monkeypatch, "bilancio-xbrl-it", "jurisdiction_accounts")
    case = accounts_case(tmp_path)
    if fault == "currency":
        case["accounts"][0]["currency"] = "EUR"
    elif fault == "jurisdiction":
        case["jurisdiction"] = "FR"
    elif fault == "missing_account":
        case["statement_lines"].pop()
    elif fault == "changed_source":
        (tmp_path / "evidence.txt").write_text("Changed after review")
    else:
        case["professional_decision"] = {"proposal_sha256": "stale"}
    with pytest.raises(ValueError):
        adapter.build_record(
            case, input_root=tmp_path, client_id="client-a", engagement_id="eng-a"
        )


def setup_case(tmp_path):
    case = envelope(tmp_path)
    case.update(client_name="Exemple Sàrl", mandate="Tenue et revue des comptes")
    case["domain_reviews"] = [
        {
            "domain": domain,
            "title": title,
            "status": "unresolved",
            "assessment": "Evidence and professional decision required.",
            "citations": citation(),
        }
        for domain, title in (
            ("identity", "Identité"),
            ("mandate", "Mandat"),
            ("ownership", "Détention"),
            ("aml_applicability", "Champ LBA"),
            ("privacy_roles", "Protection des données"),
        )
    ]
    case["document_plan"] = [
        {
            "id": "D1",
            "title": "Mandat",
            "purpose": "Confirm agreed scope",
            "next_action": "Obtain signed document",
            "status": "requested",
            "citations": [],
        }
    ]
    return case


def test_geneva_setup_keeps_requested_document_outstanding_and_no_italian_score(
    tmp_path, monkeypatch
):
    adapter = module(monkeypatch, "new-client", "jurisdiction_setup")
    result = adapter.build_record(
        setup_case(tmp_path),
        input_root=tmp_path,
        client_id="client-a",
        engagement_id="eng-a",
    )
    assert result["results"]["outstanding_document_ids"] == ["D1"]
    assert result["results"]["italian_aml_scoring_applied"] is False
    assert result["results"]["engagement_accepted"] is False
    assert "Ouverture du dossier" in adapter.render_memo(result)


def test_claimed_received_setup_document_requires_source(tmp_path, monkeypatch):
    adapter = module(monkeypatch, "new-client", "jurisdiction_setup")
    case = setup_case(tmp_path)
    case["document_plan"][0]["status"] = "received"
    with pytest.raises(ValueError, match="citations"):
        adapter.build_record(
            case, input_root=tmp_path, client_id="client-a", engagement_id="eng-a"
        )


def test_geneva_aml_rejects_italian_scoring(tmp_path, monkeypatch):
    from tests.plugins.test_vera_aml_review import case

    adapter = module(monkeypatch, "aml-review", "aml_review")
    review = case(tmp_path)
    review.update(
        jurisdiction="CH-GE",
        language="fr",
        jurisdiction_basis="Synthetic Geneva mandate",
        mandate_applicability={
            "status": "unresolved",
            "basis": "Await professional scope decision",
            "citations": citation(),
        },
        calculation_source_id="S1",
    )
    with pytest.raises(ValueError, match="Italian AML scoring"):
        adapter.build_record(
            review, input_root=tmp_path, client_id="a", engagement_id="b"
        )


@pytest.mark.parametrize(
    "jurisdiction,language", [("CH-GE", "fr"), ("CH-GE", "en"), ("IT", "fr")]
)
def test_review_language_does_not_select_jurisdiction(
    tmp_path, monkeypatch, jurisdiction, language
):
    from tests.plugins.test_vera_aml_review import case

    adapter = module(monkeypatch, "aml-review", "aml_review")
    review = case(tmp_path)
    review.update(
        jurisdiction=jurisdiction,
        language=language,
        jurisdiction_basis="Synthetic jurisdiction basis",
        mandate_applicability={
            "status": "out_of_scope",
            "basis": "Explicit synthetic mandate assessment",
            "citations": citation(),
        },
    )
    result = adapter.build_record(
        review, input_root=tmp_path, client_id="a", engagement_id="b"
    )
    assert result["review"]["jurisdiction"] == jurisdiction
    assert result["review"]["language"] == language
    assert result["calculation"] is None


def test_chf_treasury_keeps_amounts_and_labels_consistent(tmp_path, monkeypatch):
    from tests.plugins.test_treasury_forecast import first

    core = module(monkeypatch, "treasury-forecast", "treasury_core")
    report = module(monkeypatch, "treasury-forecast", "treasury_report")
    case = first()
    case["currency"] = "CHF"
    record = core.build_forecast(case)
    report.write_artifacts(tmp_path / "forecast", record)
    assert record["daily"][-1]["closing_cash"] == "15000.00"
    assert "CHF" in (tmp_path / "forecast/report.html").read_text()
    assert "€" not in (tmp_path / "forecast/report.md").read_text()
    from openpyxl import load_workbook

    workbook = load_workbook(tmp_path / "forecast/tesoreria.xlsx")
    assert workbook["Sintesi"]["A5"].value == "Cassa iniziale CHF"
    workbook.close()


def test_chf_treasury_rejects_euro_bank_account(monkeypatch):
    from tests.plugins.test_treasury_forecast import first

    core = module(monkeypatch, "treasury-forecast", "treasury_core")
    case = first()
    case["currency"] = "CHF"
    case["accounts"][0]["currency"] = "EUR"
    with pytest.raises(core.TreasuryError, match="Mixed currencies"):
        core.build_forecast(case)


def test_archive_resolves_display_and_compact_swiss_uid(indexed_archive, archive_core):
    result = archive_core.set_studio_client_identity(
        indexed_archive.scopes["Rossi"],
        tax_identifiers=["CHE-123.456.789"],
        state_dir=indexed_archive.state,
    )
    resolved = archive_core.resolve_studio_client_identity(
        "tax_identifier", "CHE123456789", state_dir=indexed_archive.state
    )
    assert resolved["matches"][0]["client_id"] == result["client"]["client_id"]


def test_archive_ocr_uses_explicit_french_and_reindexes_on_change(
    tmp_path, monkeypatch, archive_core
):
    from PIL import Image

    client = tmp_path / "Studio/Client"
    client.mkdir(parents=True)
    Image.new("RGB", (50, 50), color="white").save(client / "scan.png")
    state = tmp_path / "state"
    archive_core.configure_archive(client.parent, state_dir=state)
    calls = []
    runtime = ModuleType("vera_ocr")

    def extract(data, *, language, allow_model_download):
        calls.append((language, allow_model_download))
        return SimpleNamespace(
            status="ok", text="Pièce justificative", warnings=(), network_used=False
        )

    runtime.extract_text_from_image_bytes = extract
    monkeypatch.setitem(sys.modules, "vera_ocr", runtime)
    archive_core.refresh_archive(enable_ocr=True, ocr_language="it", state_dir=state)
    result = archive_core.refresh_archive(
        enable_ocr=True, ocr_language="fr", state_dir=state
    )
    assert calls == [("it", False), ("fr", False)]
    assert result["indexed_files"] == 1
    assert result["ocr_language"] == "fr"
