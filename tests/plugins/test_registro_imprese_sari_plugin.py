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
    tmp_path: Path, *, package_case: bool = True, output_name: str = "private-case"
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
    )
    intake = _read_json(paths["intake"])
    intake.update(
        {
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
                "description": "ATTIVITA-SENSIBILE-TEST",
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
            "processing_authorization": {
                "approved": True,
                "approval_id": "PROCESS-APPROVAL-001",
                "approved_by_role": "professional_reviewer",
                "recorded_at": "2026-07-16T09:00:00+02:00",
            },
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
            "case_summary": "Caso sintetico source-backed per la verifica del flusso.",
            "position_matrix": [
                {
                    "id": "POSITION-001",
                    "title": "Posizione da verificare",
                    "detail": "Separare Registro Imprese, INPS e IVASS/RUI.",
                    "system": "DIRE",
                    "sequence": 1,
                    "source_ids": ["SRC-SARI-001", "CASE-INTAKE"],
                    "case_fact_ids": ["CASE-OPERATION", "CASE-ACTIVITY"],
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
            "sari_question_draft": "QUESITO-SENSIBILE-TEST",
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

    assert manifest["name"] == "registro-imprese-sari"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert fixtures["should_trigger"]
    assert fixtures["should_not_trigger"]
    assert 'data-theme="mparanza-plugin-icon-v1"' in icon


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


def test_inventory_records_model_download_approval_before_ocr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = _load_script("inventory_case")
    input_dir = tmp_path / "screenshots"
    input_dir.mkdir()
    (input_dir / "dire.jpg").write_bytes(b"synthetic-image")
    output_dir = tmp_path / "private-inventory"

    def fake_ocr(*_args: object, **_kwargs: object) -> dict[str, object]:
        receipt = _read_json(output_dir / "ocr_model_download_authorization.json")
        assert receipt["approval_id"] == "OCR-MODEL-APPROVAL-001"
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
        ocr_model_download_approval_id="OCR-MODEL-APPROVAL-001",
    )

    assert (output_dir / "ocr_model_download_authorization.json").exists()


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
            network_approval_id="NETWORK-APPROVAL-001",
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

    result = connector.run_search(
        output_dir=output_dir,
        run_id="SARI-AUTHORIZED-001",
        tenant="ptpo",
        expected_chamber="Camera di commercio sintetica",
        query="apertura posizione subagente assicurativo",
        network_approval_id="NETWORK-APPROVAL-001",
        written_use_authorization_id="RIGHTS-HOLDER-AUTHORIZATION-001",
        client=client,
    )

    receipt = _read_json(output_dir / "sari_network_receipt.json")
    assert result["returned_candidate_count"] == 0
    assert opener.call_count == connector.MAX_REQUESTS_PER_OPERATION == 2
    assert receipt["request_limit"] == 2


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
    output_dir = tmp_path / "source-run"
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
    assert manifest["source_count"] == 1


def test_synthetic_case_validates_and_packages_only_for_professional_review(
    tmp_path: Path,
) -> None:
    output_dir, audit = _prepare_case(tmp_path)

    assert audit["status"] == "passed"
    final_artifacts = _read_json(output_dir / "final_artifacts.json")
    review_payload = _read_json(output_dir / "review_payload.json")
    review_text = json.dumps(review_payload, ensure_ascii=False)
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
    assert "ATTIVITA-SENSIBILE-TEST" not in review_text
    assert "QUESITO-SENSIBILE-TEST" not in review_text
    assert "ATTIVITA-SENSIBILE-TEST" in (output_dir / "studio_checklist.md").read_text(
        encoding="utf-8"
    )


def test_mcp_render_minimizes_run_intake_and_decisions_reject_identifiers(
    tmp_path: Path,
) -> None:
    output_dir, _audit = _prepare_case(
        tmp_path,
        output_name="client-test.user@example.com",
    )
    run_intake = _read_json(output_dir / "run_intake.json")
    run_intake["client_name"] = "SHOULD-NOT-REACH-WIDGET"
    run_intake["professional_question"] = "SHOULD-NOT-REACH-WIDGET"
    review = _read_json(output_dir / "review_payload.json")

    rendered = _tool_call(
        "render_registro_imprese_sari_review",
        {"run_intake": run_intake, "review_payload": review},
    )

    assert rendered["isError"] is False
    public_run = rendered["structuredContent"]["run_intake"]
    assert "client_name" not in public_run
    assert "professional_question" not in public_run
    assert "output_dir" not in public_run
    assert public_run["run_id"] == review["run_id"]

    rejected = _tool_call(
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

    assert rejected["isError"] is True
    assert "direct identifier" in rejected["structuredContent"]["error"]

    rejected_reviewer = _tool_call(
        "save_registro_imprese_sari_decisions",
        {
            "review_payload": review,
            "decisions": [],
            "reviewer": "test.user@example.com",
        },
    )
    assert rejected_reviewer["isError"] is True
    assert "direct identifier" in rejected_reviewer["structuredContent"]["error"]

    rejected_source = _tool_call(
        "save_registro_imprese_sari_decisions",
        {
            "review_payload": review,
            "decisions": [],
            "decision_source": "test.user@example.com",
        },
    )
    assert rejected_source["isError"] is True
    assert "direct identifier" in rejected_source["structuredContent"]["error"]


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


def test_mcp_exposes_exact_four_tools_and_rejects_untrusted_review_fields() -> None:
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
                "data": {"case_summary": "campo non fidato"},
            }
        ],
        "privacy_notice": "Payload minimizzato.",
        "filing_status": "not_filed",
        "filing_authorized": False,
    }
    rejected = _tool_call(
        "validate_registro_imprese_sari_review", {"review_payload": review}
    )

    assert rejected["isError"] is True
    assert "case_summary is forbidden" in rejected["structuredContent"]["error"]


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
