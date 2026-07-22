from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "registro-imprese-sari"
SCRIPTS_ROOT = PLUGIN_ROOT / "scripts"
NODE_FALLBACK = (
    Path.home()
    / ".cache"
    / "codex-runtimes"
    / "codex-primary-runtime"
    / "dependencies"
    / "node"
    / "bin"
    / "node"
)
PRIVATE_CLIENT_IDENTITY = {
    "name": "Mario Rossi",
    "tax_code": "RSSMRA80A01H501U",
    "vat_number": "12345678901",
    "email": "mario.rossi@example.com",
    "pec": "mario.rossi@pec.example.it",
    "phone": "+39 333 1234567",
    "address": "Via Roma 1, Milano",
}
PRIVATE_ACTIVITY_DESCRIPTION = (
    "Intermediazione assicurativa svolta da Mario Rossi come subagente."
)
PRIVATE_CASE_SUMMARY = (
    "Mario Rossi, codice fiscale RSSMRA80A01H501U e partita IVA 12345678901, "
    "chiede l'apertura della posizione per l'attività descritta nel fascicolo."
)
PRIVATE_PROPOSED_VALUE = (
    "Iscrizione come impresa individuale con avvio il 1 agosto 2026."
)
PRIVATE_DOCUMENT_QUOTE = "Il sottoscritto Mario Rossi dichiara l'avvio dell'attività."
PRIVATE_SARI_QUESTION = (
    "Per Mario Rossi (RSSMRA80A01H501U), quali passaggi DIRE servono per "
    "l'apertura descritta nel fascicolo?"
)


class _FakeHeaders:
    def __init__(self, content_type: str) -> None:
        self.content_type = content_type

    def get_content_type(self) -> str:
        return self.content_type


class _FakeResponse:
    def __init__(self, raw: bytes, content_type: str, final_url: str) -> None:
        self.raw = raw
        self.headers = _FakeHeaders(content_type)
        self.final_url = final_url

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return self.final_url

    def read(self, size: int) -> bytes:
        return self.raw[:size]


class _FakeOpener:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.call_count = 0

    def open(self, *_args: object, **_kwargs: object) -> _FakeResponse:
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


def _module_from_path(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_script(module_name: str) -> ModuleType:
    """Load a component script without leaking its generic case_core import."""

    previous_core = sys.modules.get("case_core")
    unique_prefix = f"registro_imprese_sari_test_{module_name}"
    core = _module_from_path(
        f"{unique_prefix}_case_core", SCRIPTS_ROOT / "case_core.py"
    )
    sys.modules["case_core"] = core
    try:
        return _module_from_path(unique_prefix, SCRIPTS_ROOT / f"{module_name}.py")
    finally:
        if previous_core is None:
            sys.modules.pop("case_core", None)
        else:
            sys.modules["case_core"] = previous_core


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _node_or_skip() -> str:
    node = shutil.which("node")
    if node:
        return node
    if NODE_FALLBACK.is_file():
        return str(NODE_FALLBACK)
    pytest.skip("Node.js is required for MCP execution tests")


def _mcp_request(request: dict[str, object]) -> dict[str, object]:
    completed = subprocess.run(
        [_node_or_skip(), str(PLUGIN_ROOT / "mcp" / "server.cjs"), "--stdio"],
        input=json.dumps(request) + "\n",
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip(), completed.stderr
    return json.loads(completed.stdout.strip())


def _tool_call(name: str, arguments: dict[str, object]) -> dict[str, object]:
    response = _mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert "result" in response, response
    return response["result"]


def _confirmation() -> dict[str, object]:
    return {
        "confirmed_by_id": "REVIEWER-001",
        "confirmed_by_role": "professional_reviewer",
        "confirmed_at": "2026-07-16T09:00:00+02:00",
        "basis": "Conferma professionale sintetica per il test.",
    }


def _prepare_case(
    tmp_path: Path,
    *,
    package_case: bool = True,
    output_name: str = "private-case",
    language: str = "it",
) -> tuple[Path, dict[str, object]]:
    initialize_case = _load_script("initialize_case")
    register_source = _load_script("register_official_source")
    validate_case = _load_script("validate_practice_case")
    packager = _load_script("package_practice")

    output_dir = tmp_path / output_name
    paths = initialize_case.initialize_case(
        output_dir,
        run_id="SARI-TEST-001",
        reference_date="2026-07-16",
        client_reference="CLIENT-REF-001",
        language=language,
    )
    intake = _read_json(paths["intake"])
    intake.update(
        {
            "client_identity": PRIVATE_CLIENT_IDENTITY.copy(),
            "competent_chamber": {
                "tenant": "ptpo",
                "name": "Camera di commercio sintetica",
                "territorial_basis": "Sede dichiarata nel territorio sintetico",
                "confirmation_status": "confirmed",
            },
            "subject": {
                "legal_form": "Impresa individuale",
                "confirmation_status": "confirmed",
            },
            "activity": {
                "description": PRIVATE_ACTIVITY_DESCRIPTION,
                "classification_status": "confirmed",
                "ateco_proposal": None,
            },
            "requested_operation": {
                "description": "Apertura della posizione Registro Imprese",
                "position_types": ["registro_imprese", "inps", "ivass_rui"],
                "effective_date": "2026-08-01",
                "confirmation_status": "confirmed",
            },
            "professional_question": "Quali passaggi devono essere predisposti in DIRE?",
        }
    )
    _write_json(paths["intake"], intake)

    source = register_source.register_source(
        output_dir=output_dir,
        run_id="SARI-TEST-001",
        source_id="SRC-SARI-001",
        source_type="official_sari_selected_result",
        title="Scheda SARI sintetica selezionata",
        official_url=(
            "https://supportospecialisticori.infocamere.it/"
            "sariWeb/ptpo?apriContenuto=TEST001"
        ),
        publisher="InfoCamere / Camera di commercio",
        territorial_applicability="Territorio sintetico",
        authorization_basis="browser_assisted_metadata",
        authorization_reference="BROWSER-SELECTION-TEST-001",
        selected_by="professional_reviewer",
        updated_date="2026-07-15",
    )
    assert source["artifact_path"] is None

    plan = _read_json(paths["plan"])
    confirmed_item = {
        "review_status": "confirmed",
        "confirmation": _confirmation(),
    }
    plan.update(
        {
            "case_summary": PRIVATE_CASE_SUMMARY,
            "review_context": {
                "client_name": PRIVATE_CLIENT_IDENTITY["name"],
                "client_email": PRIVATE_CLIENT_IDENTITY["email"],
                "activity_description": PRIVATE_ACTIVITY_DESCRIPTION,
            },
            "position_matrix": [
                {
                    "id": "POSITION-001",
                    "title": "Posizione da verificare",
                    "detail": "Separare Registro Imprese, INPS e IVASS/RUI.",
                    "system": "DIRE",
                    "sequence": 1,
                    "source_ids": ["SRC-SARI-001", "CASE-INTAKE"],
                    "case_fact_ids": [
                        "CASE-CLIENT",
                        "CASE-OPERATION",
                        "CASE-ACTIVITY",
                    ],
                    "proposed_value": PRIVATE_PROPOSED_VALUE,
                    "document_quotes": [
                        {
                            "text": PRIVATE_DOCUMENT_QUOTE,
                            "source_id": "CASE-INTAKE",
                            "location": "Dichiarazione del cliente, pagina 1",
                        }
                    ],
                    **confirmed_item,
                }
            ],
            "dire_steps": [
                {
                    "id": "DIRE-STEP-001",
                    "title": "Predisposizione pratica",
                    "detail": "Compilare la bozza solo dopo la conferma dei perimetri.",
                    "system": "DIRE",
                    "sequence": 1,
                    "source_ids": ["SRC-SARI-001"],
                    "case_fact_ids": ["CASE-CHAMBER", "CASE-EFFECTIVE-DATE"],
                    **confirmed_item,
                }
            ],
            "sari_question_draft": PRIVATE_SARI_QUESTION,
            "professional_review": {
                "status": "reviewed",
                "reviewer_id": "REVIEWER-001",
                "reviewer_role": "professional_reviewer",
                "reviewed_at": "2026-07-16T09:00:00+02:00",
                "notes": "Revisione sintetica completata.",
            },
        }
    )
    _write_json(paths["plan"], plan)

    audit = validate_case.validate_practice_case(
        paths["intake"],
        paths["plan"],
        output_dir / "official_sources.json",
        output_dir,
    )
    if package_case:
        packager.package_practice(output_dir)
    return output_dir, audit


def test_plugin_metadata_icon_and_trigger_fixtures_are_complete() -> None:
    manifest = _read_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    fixtures = _read_json(PLUGIN_ROOT / "evals" / "trigger_fixtures.json")
    icon = (PLUGIN_ROOT / "assets" / "icon.svg").read_text(encoding="utf-8")
    widget = (
        PLUGIN_ROOT / "assets" / "registro-imprese-sari-review-widget.html"
    ).read_text(encoding="utf-8")

    assert manifest["name"] == "registro-imprese-sari"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert fixtures["should_trigger"]
    assert fixtures["should_not_trigger"]
    assert 'data-theme="mparanza-plugin-icon-v1"' in icon
    assert "privacy_notice" not in widget
    assert "Metadati minimizzati" not in widget


@pytest.mark.parametrize(
    "query",
    [
        "apertura test.user@example.com",
        "posizione TSTUSR80A01H501U",
        "impresa 12345678901",
        "contatto +39 333 1234567",
    ],
)
def test_public_sari_query_rejects_direct_identifiers(query: str) -> None:
    case_core = _load_script("case_core")

    with pytest.raises(case_core.PrivacyError, match="direct identifiers"):
        case_core.assert_generic_public_query(query)


def test_public_sari_query_normalizes_generic_terms() -> None:
    case_core = _load_script("case_core")

    assert (
        case_core.assert_generic_public_query(
            "  apertura   posizione   subagente assicurativo  "
        )
        == "apertura posizione subagente assicurativo"
    )


def test_inventory_counts_shared_paddleocr_ok_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = _load_script("inventory_case")
    input_dir = tmp_path / "screenshots"
    input_dir.mkdir()
    (input_dir / "dire.jpg").write_bytes(b"synthetic-image")
    monkeypatch.setattr(
        inventory,
        "_ocr_image",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "text": "Testo OCR locale",
            "warnings": [],
            "engine": "paddleocr",
            "network_used": False,
        },
    )

    payload = inventory.inventory_case(
        input_dir,
        tmp_path / "private-inventory",
        run_id="OCR-TEST-001",
    )

    assert payload["ocr"]["successful_image_count"] == 1
    assert payload["ocr"]["model_network_used"] is False
    assert payload["ocr"]["visual_confirmation_required"] is True
    assert payload["documents"][0]["extraction_status"] == "ok"
    assert (
        "ocr_text_requires_visual_confirmation"
        in payload["documents"][0]["limitations"]
    )


def test_inventory_records_model_download_route_before_ocr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = _load_script("inventory_case")
    input_dir = tmp_path / "screenshots"
    input_dir.mkdir()
    (input_dir / "dire.jpg").write_bytes(b"synthetic-image")
    output_dir = tmp_path / "private-inventory"

    def fake_ocr(*_args: object, **_kwargs: object) -> dict[str, object]:
        receipt = _read_json(output_dir / "ocr_model_download_receipt.json")
        assert receipt["route_selected"] is True
        assert receipt["model_download_allowed"] is True
        assert receipt["case_content_network_transfer"] is False
        return {
            "status": "models_unavailable",
            "text": "",
            "warnings": ["models_unavailable"],
            "engine": "paddleocr",
            "network_used": False,
        }

    monkeypatch.setattr(inventory, "_ocr_image", fake_ocr)

    inventory.inventory_case(
        input_dir,
        output_dir,
        run_id="OCR-APPROVAL-001",
        allow_ocr_model_download=True,
    )

    assert (output_dir / "ocr_model_download_receipt.json").exists()


def test_direct_connector_fails_closed_without_written_use_authorization(
    tmp_path: Path,
) -> None:
    connector = _load_script("sari_connector")

    class NetworkMustNotRun:
        def initialize_tenant(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("network client must not run before authorization")

    output_dir = tmp_path / "blocked-run"
    with pytest.raises(
        connector.SariConnectorError, match="written_use_authorization_id"
    ):
        connector.run_search(
            output_dir=output_dir,
            run_id="SARI-BLOCKED-001",
            tenant="ptpo",
            expected_chamber="Camera di commercio",
            query="apertura posizione subagente assicurativo",
            written_use_authorization_id="",
            client=NetworkMustNotRun(),
        )

    assert not output_dir.exists()


def test_direct_connector_rejects_even_allowlisted_redirects() -> None:
    connector = _load_script("sari_connector")
    handler = connector._RejectRedirectHandler()

    with pytest.raises(connector.SariConnectorError, match="redirects are not allowed"):
        handler.redirect_request(
            None,
            None,
            302,
            "Found",
            {},
            "https://supportospecialisticori.infocamere.it/sariWeb/ptpo/",
        )


def test_sari_client_rejects_unexpected_content_type() -> None:
    connector = _load_script("sari_connector")
    tenant_url = "https://supportospecialisticori.infocamere.it/sariWeb/ptpo"
    client = connector.SariClient()
    client.opener = _FakeOpener([_FakeResponse(b"{}", "application/json", tenant_url)])

    with pytest.raises(
        connector.SariConnectorError, match="unexpected SARI content type"
    ):
        client.initialize_tenant("ptpo", expected_chamber="Camera di commercio")


def test_sari_client_rejects_oversized_response() -> None:
    connector = _load_script("sari_connector")
    tenant_url = "https://supportospecialisticori.infocamere.it/sariWeb/ptpo"
    client = connector.SariClient()
    client.opener = _FakeOpener(
        [
            _FakeResponse(
                b"x" * (connector.MAX_RESPONSE_BYTES + 1),
                "text/html",
                tenant_url,
            )
        ]
    )

    with pytest.raises(connector.SariConnectorError, match="response exceeds"):
        client.initialize_tenant("ptpo", expected_chamber="Camera di commercio")


def test_authorized_search_uses_exactly_two_requests_and_records_budget(
    tmp_path: Path,
) -> None:
    connector = _load_script("sari_connector")
    initializer = _load_script("initialize_case")
    tenant_url = "https://supportospecialisticori.infocamere.it/sariWeb/ptpo"
    search_url = "https://supportospecialisticori.infocamere.it/sariWeb/faq/get/"
    tenant_html = b'<input id="titoloAssistenza" value="Camera di commercio sintetica">'
    search_json = json.dumps({"result": {"_numDocs": 0, "_listdocs": []}}).encode(
        "utf-8"
    )
    opener = _FakeOpener(
        [
            _FakeResponse(tenant_html, "text/html", tenant_url),
            _FakeResponse(search_json, "application/json", search_url),
        ]
    )
    client = connector.SariClient()
    client.opener = opener
    output_dir = tmp_path / "authorized-search"
    initializer.initialize_case(
        output_dir,
        run_id="SARI-AUTHORIZED-001",
        reference_date="2026-07-16",
        client_reference="CLIENT-AUTHORIZED-001",
    )

    result = connector.run_search(
        output_dir=output_dir,
        run_id="SARI-AUTHORIZED-001",
        tenant="ptpo",
        expected_chamber="Camera di commercio sintetica",
        query="apertura posizione subagente assicurativo",
        written_use_authorization_id="RIGHTS-HOLDER-AUTHORIZATION-001",
        client=client,
    )

    receipt = _read_json(output_dir / "sari_network_receipt.json")
    run_intake = _read_json(output_dir / "run_intake.json")
    connector_entries = run_intake["data_posture"]["external_connectors_used"]
    connector_entry = connector_entries[0]
    route_entry = run_intake["data_posture"]["external_routes_used"][0]
    connector_step = run_intake["execution_trace"][-1]
    assert result["returned_candidate_count"] == 0
    assert opener.call_count == connector.MAX_REQUESTS_PER_OPERATION == 2
    assert receipt["request_limit"] == 2
    assert receipt["route_selected"] is True
    assert receipt["network_used"] is True
    assert "network_approval_id" not in receipt
    assert receipt["written_use_authorization_id"] == (
        "RIGHTS-HOLDER-AUTHORIZATION-001"
    )
    assert len(connector_entries) == 1
    assert connector_entry["connector"] == "authorized_sari_json_read_only"
    assert connector_entry["origin"] == connector.SARI_ORIGIN
    assert connector_entry["tenant"] == "ptpo"
    assert connector_entry["operation"] == "search"
    assert connector_entry["credentials_used"] is False
    assert connector_entry["status"] == "completed"
    assert connector_entry["completed_at"]
    assert route_entry == {
        "route": "authorized_sari_json_read_only",
        "destination_or_origin": connector.SARI_ORIGIN,
        "payload_category": "generic_public_query_or_selected_card_identifier",
        "network_used": True,
        "access_basis": (
            "written_use_authorization_id:RIGHTS-HOLDER-AUTHORIZATION-001"
        ),
    }
    assert "external_execution_approval" not in run_intake["data_posture"]
    assert connector_step["kind"] == "external_official_source_read"
    assert connector_step["status"] == "passed"


def test_connector_failure_does_not_record_use_or_completion(tmp_path: Path) -> None:
    connector = _load_script("sari_connector")
    initializer = _load_script("initialize_case")
    output_dir = tmp_path / "failed-search"
    initializer.initialize_case(
        output_dir,
        run_id="SARI-FAILED-001",
        reference_date="2026-07-16",
        client_reference="CLIENT-FAILED-001",
    )

    class FailingClient:
        def initialize_tenant(self, *_args: object, **_kwargs: object) -> None:
            raise connector.SariConnectorError("synthetic network failure")

    with pytest.raises(connector.SariConnectorError, match="synthetic network failure"):
        connector.run_search(
            output_dir=output_dir,
            run_id="SARI-FAILED-001",
            tenant="ptpo",
            expected_chamber="Camera di commercio sintetica",
            query="apertura posizione subagente assicurativo",
            written_use_authorization_id="RIGHTS-HOLDER-AUTHORIZATION-001",
            client=FailingClient(),
        )

    run_intake = _read_json(output_dir / "run_intake.json")
    assert run_intake["data_posture"]["external_connectors_used"] == []
    assert run_intake["data_posture"]["external_routes_used"] == []
    assert "external_execution_approval" not in run_intake["data_posture"]
    assert not (output_dir / "sari_network_receipt.json").exists()
    assert len(run_intake["execution_trace"]) == 1
    assert run_intake["execution_trace"][0]["kind"] == "deterministic_initialization"


def test_sari_client_blocks_third_request_before_network() -> None:
    connector = _load_script("sari_connector")
    client = connector.SariClient()
    client.tenant = "ptpo"
    client.request_count = connector.MAX_REQUESTS_PER_OPERATION
    opener = _FakeOpener([])
    client.opener = opener

    with pytest.raises(connector.SariConnectorError, match="2-request limit"):
        client.search("apertura posizione", limit=1)

    assert opener.call_count == 0


def test_search_normalization_does_not_infer_applicability() -> None:
    connector = _load_script("sari_connector")
    payload = {
        "result": {
            "_numDocs": 1,
            "_listdocs": [
                {
                    "id_scheda": "CARD-001",
                    "titolo": "<strong>Apertura posizione</strong>",
                    "dt_ultima_modifica": "2026-07-15",
                    "tipo_scheda": "scheda",
                    "_abstract": [{"testo": ["<p>Procedura ufficiale</p>"]}],
                }
            ],
        }
    }

    result = connector.normalize_search_result(payload, limit=10)

    assert result["semantic_classification"] == "not_performed"
    assert result["candidates"][0]["selection_status"] == (
        "candidate_requires_human_selection"
    )
    assert result["candidates"][0]["title"] == "Apertura posizione"


def test_browser_selected_source_registers_metadata_only_and_forbids_snapshot(
    tmp_path: Path,
) -> None:
    registration = _load_script("register_official_source")
    initializer = _load_script("initialize_case")
    output_dir = tmp_path / "source-run"
    initializer.initialize_case(
        output_dir,
        run_id="SOURCE-TEST-001",
        reference_date="2026-07-16",
        client_reference="CLIENT-SOURCE-001",
    )
    source = registration.register_source(
        output_dir=output_dir,
        run_id="SOURCE-TEST-001",
        source_id="SRC-001",
        source_type="official_sari_selected_result",
        title="Scheda SARI selezionata",
        official_url="https://supportospecialisticori.infocamere.it/sariWeb/ptpo",
        publisher="InfoCamere",
        territorial_applicability="Prato e Pistoia",
        authorization_basis="browser_assisted_metadata",
        authorization_reference="BROWSER-SELECTION-001",
        selected_by="professional_reviewer",
    )
    snapshot = tmp_path / "source.html"
    snapshot.write_text("contenuto non autorizzato", encoding="utf-8")

    assert source["artifact_path"] is None
    assert source["artifact_sha256"] is None
    assert source["selected_by"] == "professional_reviewer"
    assert source["authorization_basis"] == "browser_assisted_metadata"
    assert source["authorization_reference"] == "BROWSER-SELECTION-001"
    assert not (output_dir / "sources").exists()
    with pytest.raises(ValueError, match="cannot persist content"):
        registration.register_source(
            output_dir=output_dir,
            run_id="SOURCE-TEST-001",
            source_id="SRC-002",
            source_type="official_sari_selected_result",
            title="Scheda SARI selezionata",
            official_url="https://supportospecialisticori.infocamere.it/sariWeb/ptpo",
            publisher="InfoCamere",
            territorial_applicability="Prato e Pistoia",
            authorization_basis="browser_assisted_metadata",
            authorization_reference="BROWSER-SELECTION-002",
            selected_by="professional_reviewer",
            snapshot=snapshot,
        )
    manifest = _read_json(output_dir / "official_sources.json")
    run_intake = _read_json(output_dir / "run_intake.json")
    assert manifest["source_count"] == 1
    assert run_intake["data_posture"]["external_connectors_used"] == []
    assert run_intake["data_posture"]["external_routes_used"] == []
    assert "external_execution_approval" not in run_intake["data_posture"]
    assert run_intake["execution_trace"][-1]["kind"] == "local_source_registration"


def test_synthetic_case_validates_and_packages_only_for_professional_review(
    tmp_path: Path,
) -> None:
    output_dir, audit = _prepare_case(tmp_path)

    assert audit["status"] == "passed"
    final_artifacts = _read_json(output_dir / "final_artifacts.json")
    validated_intake = _read_json(output_dir / "case_intake_validated.json")
    local_plan = _read_json(output_dir / "dire_practice_plan.json")
    review_payload = _read_json(output_dir / "review_payload.json")
    review_text = json.dumps(review_payload, ensure_ascii=False)
    checklist_text = (output_dir / "studio_checklist.md").read_text(encoding="utf-8")
    sari_question_text = (output_dir / "sari_question_draft.md").read_text(
        encoding="utf-8"
    )
    handoff_text = (output_dir / "review_handoff.md").read_text(encoding="utf-8")
    draft_disclaimer = "BOZZA PER REVISIONE PROFESSIONALE — NON PRONTA PER IL DEPOSITO"
    assert final_artifacts["status"] == "ready_for_professional_review"
    assert final_artifacts["professional_review_required"] is True
    assert final_artifacts["ready_to_file"] is False
    assert final_artifacts["portal_access_performed"] is False
    assert final_artifacts["signature_performed"] is False
    assert final_artifacts["submission_performed"] is False
    contract = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_plugin_review_contract.py"),
            str(output_dir),
            "--strict-data-posture",
            "--strict-output-paths",
            "--strict-execution-trace",
            "--strict-output-content",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert contract.returncode == 0, contract.stdout + contract.stderr
    assert review_payload["filing_status"] == "not_filed"
    assert review_payload["filing_authorized"] is False
    assert "privacy_notice" not in review_payload
    assert local_plan["limitations"] == []
    assert checklist_text.count(draft_disclaimer) == 1
    assert draft_disclaimer not in sari_question_text
    assert draft_disclaimer not in handoff_text
    assert validated_intake["client_identity"] == PRIVATE_CLIENT_IDENTITY
    assert local_plan["case_summary"] == PRIVATE_CASE_SUMMARY
    assert local_plan["position_matrix"][0]["proposed_value"] == PRIVATE_PROPOSED_VALUE
    assert local_plan["position_matrix"][0]["document_quotes"][0]["text"] == (
        PRIVATE_DOCUMENT_QUOTE
    )
    assert PRIVATE_CLIENT_IDENTITY["name"] in checklist_text
    assert PRIVATE_CLIENT_IDENTITY["tax_code"] in checklist_text
    assert PRIVATE_CLIENT_IDENTITY["vat_number"] in checklist_text
    assert PRIVATE_CLIENT_IDENTITY["email"] in checklist_text
    assert PRIVATE_CLIENT_IDENTITY["pec"] in checklist_text
    assert PRIVATE_CLIENT_IDENTITY["phone"] in checklist_text
    assert PRIVATE_CLIENT_IDENTITY["address"] in checklist_text
    assert PRIVATE_ACTIVITY_DESCRIPTION in checklist_text
    assert PRIVATE_CASE_SUMMARY in checklist_text
    assert PRIVATE_SARI_QUESTION in sari_question_text
    assert review_payload["case_context"]["client_identity"] == PRIVATE_CLIENT_IDENTITY
    assert review_payload["case_context"]["case_summary"] == PRIVATE_CASE_SUMMARY
    assert review_payload["case_context"]["sari_question_draft"] == (
        PRIVATE_SARI_QUESTION
    )
    assert PRIVATE_ACTIVITY_DESCRIPTION in review_text
    assert PRIVATE_CASE_SUMMARY in review_text
    assert PRIVATE_PROPOSED_VALUE in review_text
    assert PRIVATE_DOCUMENT_QUOTE in review_text
    assert PRIVATE_SARI_QUESTION in review_text


def test_spanish_case_packages_localized_checklist_handoff_and_review_payload(
    tmp_path: Path,
) -> None:
    output_dir, audit = _prepare_case(tmp_path, language="es")

    checklist = (output_dir / "studio_checklist.md").read_text(encoding="utf-8")
    sari_question = (output_dir / "sari_question_draft.md").read_text(encoding="utf-8")
    handoff = (output_dir / "review_handoff.md").read_text(encoding="utf-8")
    review = _read_json(output_dir / "review_payload.json")
    run_intake = _read_json(output_dir / "run_intake.json")
    final_artifacts = _read_json(output_dir / "final_artifacts.json")
    assert audit["status"] == "passed"
    assert "BORRADOR PARA REVISIÓN PROFESIONAL" in checklist
    assert "| Concepto | Valor | Estado |" in checklist
    assert "## Fuentes oficiales seleccionadas" in checklist
    assert "## Resultado de los controles mecánicos" in checklist
    assert "Pregunta para el servicio de soporte SARI — borrador" in sari_question
    assert "El profesional debe aprobar el texto" in sari_question
    assert "# Entrega para revisión" in handoff
    assert "La aplicación de decisiones nunca inicia sesión" in handoff
    assert review["language"] == "es"
    assert run_intake["language"] == "es"
    assert str(run_intake["inferred_task"]).startswith("Preparar un borrador")
    assert final_artifacts["language"] == "es"
    assert final_artifacts["caveats"][-1].startswith("Toda fuente SARI")
    assert final_artifacts["next_actions"][0].startswith("Resuelva todos")
    audit_item = next(
        item for item in review["items"] if item["item_type"] == "audit_check"
    )
    assert audit_item["title"] == "Controles mecánicos de la práctica"
    contract = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_plugin_review_contract.py"),
            str(output_dir),
            "--strict-data-posture",
            "--strict-output-paths",
            "--strict-execution-trace",
            "--strict-output-content",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert contract.returncode == 0, contract.stdout + contract.stderr


def test_registro_imprese_widget_selects_spanish_copy_from_review_language() -> None:
    widget_path = PLUGIN_ROOT / "assets" / "registro-imprese-sari-review-widget.html"
    script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const html = fs.readFileSync(process.argv[1], "utf8");
const body = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const definitions = body.split('document.getElementById("search").addEventListener')[0];
const context = {};
vm.createContext(context);
new vm.Script(`${definitions}\nglobalThis.result = { language: languageFor({ review_payload: { language: "es" } }), queue: copyFor({ review_payload: { language: "es" } }).queueTitle, save: copyFor({ review_payload: { language: "es" } }).saveButton };`).runInContext(context);
process.stdout.write(JSON.stringify(context.result));
"""
    completed = subprocess.run(
        [_node_or_skip(), "-e", script, str(widget_path)],
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "language": "es",
        "queue": "Cola de revisión",
        "save": "Guardar",
    }


@pytest.mark.parametrize("secret_field", ["credentials", "cookie", "token", "session"])
def test_private_case_validation_rejects_secret_or_session_material(
    tmp_path: Path,
    secret_field: str,
) -> None:
    output_dir, initial_audit = _prepare_case(tmp_path, package_case=False)
    validate_case = _load_script("validate_practice_case")
    plan_path = output_dir / "practice_plan_draft.json"
    plan = _read_json(plan_path)
    plan["review_context"][secret_field] = "forbidden-test-value"
    _write_json(plan_path, plan)

    audit = validate_case.validate_practice_case(
        output_dir / "case_intake_draft.json",
        plan_path,
        output_dir / "official_sources.json",
        output_dir,
    )

    assert initial_audit["status"] == "passed"
    assert audit["status"] == "schema_error"
    assert audit["error_count"] == 1
    assert audit["issues"][0]["code"] == "secret_or_session_material_forbidden"
    assert audit["issues"][0]["path"] == (
        f"practice_plan.review_context.{secret_field}"
    )


def test_mcp_review_preserves_case_identifiers_but_omits_local_paths(
    tmp_path: Path,
) -> None:
    output_dir, _audit = _prepare_case(
        tmp_path,
        output_name="client-test.user@example.com",
    )
    run_intake = _read_json(output_dir / "run_intake.json")
    run_intake["client_name"] = PRIVATE_CLIENT_IDENTITY["name"]
    run_intake["professional_question"] = PRIVATE_SARI_QUESTION
    review = _read_json(output_dir / "review_payload.json")
    final_artifacts = _read_json(output_dir / "final_artifacts.json")

    rendered = _tool_call(
        "render_registro_imprese_sari_review",
        {
            "run_intake": run_intake,
            "review_payload": review,
            "final_artifacts": final_artifacts,
        },
    )

    assert rendered["isError"] is False
    review_run = rendered["structuredContent"]["run_intake"]
    assert review_run["client_name"] == PRIVATE_CLIENT_IDENTITY["name"]
    assert review_run["professional_question"] == PRIVATE_SARI_QUESTION
    assert "output_dir" not in review_run
    assert review_run["run_id"] == review["run_id"]
    assert PRIVATE_CASE_SUMMARY in json.dumps(
        rendered["structuredContent"]["review_payload"], ensure_ascii=False
    )
    rendered_final = rendered["structuredContent"]["final_artifacts"]
    assert rendered_final["outputs"] == final_artifacts["outputs"]
    assert rendered_final["caveats"] == final_artifacts["caveats"]
    assert rendered_final["next_actions"] == final_artifacts["next_actions"]

    saved = _tool_call(
        "save_registro_imprese_sari_decisions",
        {
            "review_payload": review,
            "decisions": [
                {
                    "item_id": review["items"][0]["id"],
                    "action": "mark_unclear",
                    "reviewer_note": "Scrivere a test.user@example.com",
                }
            ],
        },
    )

    assert saved["isError"] is False
    assert (
        saved["structuredContent"]["ui_decisions"]["decisions"][0]["reviewer_note"]
        == "Scrivere a test.user@example.com"
    )

    saved_reviewer = _tool_call(
        "save_registro_imprese_sari_decisions",
        {
            "review_payload": review,
            "decisions": [],
            "reviewer": "test.user@example.com",
        },
    )
    assert saved_reviewer["isError"] is False
    assert saved_reviewer["structuredContent"]["ui_decisions"]["reviewer"] == (
        "test.user@example.com"
    )

    saved_source = _tool_call(
        "save_registro_imprese_sari_decisions",
        {
            "review_payload": review,
            "decisions": [],
            "decision_source": "test.user@example.com",
        },
    )
    assert saved_source["isError"] is False
    assert saved_source["structuredContent"]["ui_decisions"]["decision_source"] == (
        "test.user@example.com"
    )


def test_packaging_rejects_source_tampering_after_validation(tmp_path: Path) -> None:
    output_dir, audit = _prepare_case(tmp_path, package_case=False)
    packager = _load_script("package_practice")
    sources_path = output_dir / "official_sources.json"
    sources = _read_json(sources_path)
    sources["sources"][0]["title"] = "Titolo alterato dopo la validazione"
    _write_json(sources_path, sources)

    assert audit["status"] == "passed"
    with pytest.raises(ValueError, match="official sources hash"):
        packager.package_practice(output_dir)


def test_packaged_case_passes_shared_strict_review_contract(tmp_path: Path) -> None:
    output_dir, _audit = _prepare_case(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_plugin_review_contract.py"),
            str(output_dir),
            "--strict-data-posture",
            "--strict-output-paths",
            "--strict-execution-trace",
            "--strict-output-content",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_mcp_exposes_exact_four_tools_and_accepts_professional_case_fields() -> None:
    listed = _mcp_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
    tools_by_name = {tool["name"]: tool for tool in listed["result"]["tools"]}
    tool_names = set(tools_by_name)
    assert tool_names == {
        "validate_registro_imprese_sari_review",
        "render_registro_imprese_sari_review",
        "save_registro_imprese_sari_decisions",
        "apply_registro_imprese_sari_decisions",
    }
    assert (
        tools_by_name["validate_registro_imprese_sari_review"]["annotations"][
            "idempotentHint"
        ]
        is True
    )
    for write_or_token_tool in (
        "render_registro_imprese_sari_review",
        "save_registro_imprese_sari_decisions",
        "apply_registro_imprese_sari_decisions",
    ):
        assert (
            tools_by_name[write_or_token_tool]["annotations"]["idempotentHint"] is False
        )

    review = {
        "schema_version": "1.0",
        "plugin": "registro-imprese-sari",
        "workflow": "registro-imprese-sari",
        "run_id": "MCP-PRIVACY-001",
        "review_type": "registro_imprese_practice_review",
        "status": "draft_for_professional_review",
        "item_count": 1,
        "items": [
            {
                "id": "audit-001",
                "item_type": "audit_check",
                "title": "Controllo meccanico",
                "allowed_actions": ["accept", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "data": {
                    "case_summary": PRIVATE_CASE_SUMMARY,
                    "client_name": PRIVATE_CLIENT_IDENTITY["name"],
                    "codice_fiscale": PRIVATE_CLIENT_IDENTITY["tax_code"],
                    "document_quote": PRIVATE_DOCUMENT_QUOTE,
                    "proposed_value": PRIVATE_PROPOSED_VALUE,
                    "sari_question_draft": PRIVATE_SARI_QUESTION,
                },
            }
        ],
        "filing_status": "not_filed",
        "filing_authorized": False,
    }
    accepted = _tool_call(
        "validate_registro_imprese_sari_review", {"review_payload": review}
    )

    assert accepted["isError"] is False
    serialized = json.dumps(accepted["structuredContent"], ensure_ascii=False)
    assert PRIVATE_CASE_SUMMARY in serialized
    assert PRIVATE_CLIENT_IDENTITY["tax_code"] in serialized
    assert PRIVATE_DOCUMENT_QUOTE in serialized
    assert PRIVATE_PROPOSED_VALUE in serialized
    assert PRIVATE_SARI_QUESTION in serialized


@pytest.mark.parametrize("secret_field", ["credentials", "cookie", "token", "session"])
def test_mcp_review_rejects_secret_or_session_material(secret_field: str) -> None:
    review = {
        "schema_version": "1.0",
        "plugin": "registro-imprese-sari",
        "workflow": "registro-imprese-sari",
        "run_id": "MCP-SECRET-001",
        "review_type": "registro_imprese_practice_review",
        "status": "draft_for_professional_review",
        "item_count": 1,
        "items": [
            {
                "id": "audit-001",
                "item_type": "audit_check",
                "title": "Controllo meccanico",
                "allowed_actions": ["accept", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "data": {secret_field: "forbidden-test-value"},
            }
        ],
        "filing_status": "not_filed",
        "filing_authorized": False,
    }

    rejected = _tool_call(
        "validate_registro_imprese_sari_review", {"review_payload": review}
    )

    assert rejected["isError"] is True
    assert "credential or session material" in rejected["structuredContent"]["error"]


def test_mcp_persists_and_applies_review_decisions_without_portal_actions(
    tmp_path: Path,
) -> None:
    output_dir, _audit = _prepare_case(tmp_path)
    run_intake = _read_json(output_dir / "run_intake.json")
    review = _read_json(output_dir / "review_payload.json")
    decisions = [
        {"item_id": item["id"], "action": "accept"} for item in review["items"]
    ]

    saved = _tool_call(
        "save_registro_imprese_sari_decisions",
        {
            "run_intake": run_intake,
            "review_payload": review,
            "decisions": decisions[:1],
            "reviewer": "REVIEWER-001",
        },
    )
    assert saved["isError"] is False
    assert saved["structuredContent"]["persisted"] is True
    assert saved["structuredContent"]["status"] == "partial_review"
    assert (output_dir / "ui_decisions.json").exists()

    applied = _tool_call(
        "apply_registro_imprese_sari_decisions",
        {
            "run_intake": run_intake,
            "review_payload": review,
            "decisions": decisions,
            "reviewer": "REVIEWER-001",
        },
    )
    assert applied["isError"] is False
    result = applied["structuredContent"]
    assert result["persisted"] is True
    assert result["blocker_count"] == 0
    assert result["application_status"] == "reviewed_no_portal_action"
    assert result["ready_to_file"] is False
    assert result["portal_actions_performed"] is False
    assert (output_dir / "applied_decisions.json").exists()
    final_artifacts = _read_json(output_dir / "final_artifacts.json")
    assert final_artifacts["ready_to_file"] is False
    assert final_artifacts["filing_status"] == "not_filed"
    assert final_artifacts["portal_access_performed"] is False
    assert final_artifacts["signature_performed"] is False
    assert final_artifacts["submission_performed"] is False
    contract = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_plugin_review_contract.py"),
            str(output_dir),
            "--strict-data-posture",
            "--strict-output-paths",
            "--strict-execution-trace",
            "--strict-output-content",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert contract.returncode == 0, contract.stdout + contract.stderr


def test_widget_render_round_trip_persists_with_opaque_context(
    tmp_path: Path,
) -> None:
    output_dir, _audit = _prepare_case(tmp_path)
    private_run_intake = _read_json(output_dir / "run_intake.json")
    review = _read_json(output_dir / "review_payload.json")
    process = subprocess.Popen(
        [_node_or_skip(), str(PLUGIN_ROOT / "mcp" / "server.cjs"), "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None

    def call_tool(
        request_id: int, name: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
            )
            + "\n"
        )
        process.stdin.flush()
        line = process.stdout.readline()
        assert line, process.stderr.read()
        response = json.loads(line)
        assert "result" in response, response
        return response["result"]

    try:
        rendered = call_tool(
            1,
            "render_registro_imprese_sari_review",
            {"run_intake": private_run_intake, "review_payload": review},
        )
        rendered_payload = rendered["structuredContent"]
        public_run_intake = rendered_payload["run_intake"]
        persistence_token = rendered_payload["persistence_token"]
        assert rendered_payload["persistence_available"] is True
        assert "output_dir" not in public_run_intake
        assert isinstance(persistence_token, str)
        assert str(output_dir) not in json.dumps(rendered_payload)

        decisions = [
            {"item_id": item["id"], "action": "accept"} for item in review["items"]
        ]
        widget_arguments = {
            "run_intake": public_run_intake,
            "persistence_token": persistence_token,
            "review_payload": rendered_payload["review_payload"],
            "decisions": decisions,
            "decision_source": "mcp_widget",
        }
        saved = call_tool(
            2,
            "save_registro_imprese_sari_decisions",
            widget_arguments,
        )
        applied = call_tool(
            3,
            "apply_registro_imprese_sari_decisions",
            widget_arguments,
        )
    finally:
        process.stdin.close()
        return_code = process.wait(timeout=10)
        stderr = process.stderr.read()

    assert return_code == 0, stderr
    assert saved["structuredContent"]["persisted"] is True
    assert applied["structuredContent"]["persisted"] is True
    assert (output_dir / "ui_decisions.json").exists()
    assert (output_dir / "applied_decisions.json").exists()
