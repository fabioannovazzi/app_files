from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Iterator

import pytest

if "journal_ingest" not in sys.modules:
    journal_pkg = types.ModuleType("journal_ingest")
    journal_pkg.__path__ = []  # type: ignore[attr-defined]

    config_mod = types.ModuleType("journal_ingest.config")
    config_mod.get_recipe = lambda *_a, **_k: {}  # type: ignore[attr-defined]

    core_mod = types.ModuleType("journal_ingest.core")

    class _ParserConfidenceError(RuntimeError):
        pass

    class _ValidationError(RuntimeError):
        pass

    core_mod.ParserConfidenceError = _ParserConfidenceError  # type: ignore[attr-defined]
    core_mod.ValidationError = _ValidationError  # type: ignore[attr-defined]

    router_mod = types.ModuleType("journal_ingest.router")
    router_mod.Router = lambda *_a, **_k: None  # type: ignore[attr-defined]

    strategies_mod = types.ModuleType("journal_ingest.strategies")
    strategies_mod.JournalStrategyExcel = object  # type: ignore[attr-defined]
    strategies_mod.JournalStrategyOcr = object  # type: ignore[attr-defined]
    strategies_mod.JournalStrategyTableArea = object  # type: ignore[attr-defined]
    strategies_mod.JournalStrategyTablePDF = object  # type: ignore[attr-defined]
    strategies_mod.JournalStrategyTextLayout = object  # type: ignore[attr-defined]
    strategies_mod.JournalStrategyTextPDF = object  # type: ignore[attr-defined]
    strategies_mod.TablePDFParser = object  # type: ignore[attr-defined]
    strategies_mod.TextPDFParser = object  # type: ignore[attr-defined]

    journal_pkg.config = config_mod  # type: ignore[attr-defined]
    journal_pkg.core = core_mod  # type: ignore[attr-defined]
    journal_pkg.router = router_mod  # type: ignore[attr-defined]
    journal_pkg.strategies = strategies_mod  # type: ignore[attr-defined]

    sys.modules["journal_ingest"] = journal_pkg
    sys.modules["journal_ingest.config"] = config_mod
    sys.modules["journal_ingest.core"] = core_mod
    sys.modules["journal_ingest.router"] = router_mod
    sys.modules["journal_ingest.strategies"] = strategies_mod

if "multipart" not in sys.modules:
    multipart_module = types.ModuleType("multipart")
    multipart_submodule = types.ModuleType("multipart.multipart")

    def _parse_options_header(value: str) -> tuple[str, dict[str, str]]:
        return "", {}

    multipart_submodule.parse_options_header = _parse_options_header  # type: ignore[attr-defined]
    multipart_module.multipart = multipart_submodule  # type: ignore[attr-defined]
    multipart_module.parse_options_header = _parse_options_header  # type: ignore[attr-defined]
    multipart_module.__version__ = "0.0"
    sys.modules["multipart"] = multipart_module
    sys.modules["multipart.multipart"] = multipart_submodule

if "parsers.extractors" not in sys.modules:
    extractors_mod = types.ModuleType("parsers.extractors")
    extractors_mod.normalise_name = lambda value: value  # type: ignore[attr-defined]
    extractors_mod.extract_beneficiary = lambda value: value  # type: ignore[attr-defined]
    extractors_mod.extract_references = lambda value: value  # type: ignore[attr-defined]
    sys.modules["parsers.extractors"] = extractors_mod

if "finance" not in sys.modules:
    finance_pkg = types.ModuleType("finance")
    finance_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["finance"] = finance_pkg

if "finance.ledger" not in sys.modules:
    ledger_pkg = types.ModuleType("finance.ledger")
    ledger_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["finance.ledger"] = ledger_pkg

if "finance.ledger.ignore_patterns" not in sys.modules:
    ledger_ignore_mod = types.ModuleType("finance.ledger.ignore_patterns")
    ledger_ignore_mod.load_ignore_patterns = lambda *_a, **_k: []  # type: ignore[attr-defined]
    sys.modules["finance.ledger.ignore_patterns"] = ledger_ignore_mod

if "finance.bank_statements" not in sys.modules:
    bank_pkg = types.ModuleType("finance.bank_statements")
    bank_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["finance.bank_statements"] = bank_pkg

if "finance.bank_statements.ignore_patterns" not in sys.modules:
    bank_ignore_mod = types.ModuleType("finance.bank_statements.ignore_patterns")
    bank_ignore_mod.DROP_PATTERNS = []  # type: ignore[attr-defined]
    bank_ignore_mod.ALL_PATTERNS = []  # type: ignore[attr-defined]
    sys.modules["finance.bank_statements.ignore_patterns"] = bank_ignore_mod

if "pypandoc" not in sys.modules:
    pypandoc_mod = types.ModuleType("pypandoc")
    pypandoc_mod.convert_file = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    sys.modules["pypandoc"] = pypandoc_mod

pytest.importorskip("fastapi")
from fastapi.responses import (
    HTMLResponse,  # type: ignore  # pylint: disable=wrong-import-position
)
from fastapi.testclient import (
    TestClient,  # type: ignore  # pylint: disable=wrong-import-position
)

from modules.auth import dependencies as auth_dependencies
from modules.auth.config import get_auth_config
from modules.auth.session import GoogleUserInfo, create_session_cookie
from modules.pdp.api import app


def _unset_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_var in ("AUTH_ENABLED", "GOOGLE_CLIENT_ID", "AUTH_SESSION_SECRET"):
        monkeypatch.delenv(env_var, raising=False)


AUTHORIZED_EMAIL = "authorized@example.com"
PRESENTATIONS_ONLY_EMAIL = "presentations-only@example.com"
SLIDES_ONLY_EMAIL = "slides-only@example.com"
UNAUTHORIZED_EMAIL = "tester@example.com"
MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
    b"\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01"
    b"\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _write_permission_structure(
    tmp_path: Path, structure: dict[str, list[str]]
) -> Path:
    structure_file = tmp_path / "permission_structure.json"
    structure_file.write_text(json.dumps(structure), encoding="utf-8")
    return structure_file


PRESENTATION_DECK_URL = "/presentations/example-deck/index.html"
PRESENTATION_DECK_DIRECTORY = "/presentations/example-deck/"
EXPECTED_DECK_SNIPPET = "example-deck"


def _configure_default_test_permissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"deck_toolkit": [AUTHORIZED_EMAIL]}),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {"deck_toolkit": ["/presentations", "/slides"]},
    )
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()


def _configure_launch_report_viewer_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    include_document: bool,
    include_podcast: bool,
    include_video: bool = False,
) -> Any:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"attribute_analysis": [AUTHORIZED_EMAIL, UNAUTHORIZED_EMAIL]}),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {"attribute_analysis": ["/review/reports"]},
    )
    launch_report_permissions_file = tmp_path / "launch_report_permissions.json"
    launch_report_permissions_file.write_text(
        json.dumps({"launch_report_one": [AUTHORIZED_EMAIL]}),
        encoding="utf-8",
    )

    pdf_root = tmp_path / "launch_reports"
    pdf_root.mkdir(parents=True, exist_ok=True)
    (pdf_root / "Launch Report One.pdf").write_bytes(b"%PDF-1.4\n%EOF\n")

    document_root = tmp_path / "launch_report_documents"
    document_root.mkdir(parents=True, exist_ok=True)
    if include_document:
        (document_root / "Launch Report One.pdf").write_bytes(b"%PDF-1.4\n%EOF\n")

    podcast_root = tmp_path / "launch_report_podcasts"
    podcast_root.mkdir(parents=True, exist_ok=True)
    if include_podcast:
        (podcast_root / "Launch Report One.m4a").write_bytes(b"podcast-bytes")

    video_root = tmp_path / "launch_report_videos"
    video_root.mkdir(parents=True, exist_ok=True)
    if include_video:
        (video_root / "Launch Report One.mp4").write_bytes(b"video-bytes")

    import modules.projects.api as projects_api

    monkeypatch.setattr(projects_api, "_launch_reports_pdf_root", lambda: pdf_root)
    monkeypatch.setattr(
        projects_api,
        "_launch_report_documents_root",
        lambda: document_root,
    )
    monkeypatch.setattr(
        projects_api,
        "_launch_report_podcasts_root",
        lambda: podcast_root,
    )
    monkeypatch.setattr(
        projects_api,
        "_launch_report_videos_root",
        lambda: video_root,
    )
    monkeypatch.setattr(
        projects_api,
        "_ensure_cache_fresh",
        lambda *_args, **_kwargs: {"page_count": 2},
    )
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)

    from modules.projects import permissions as presentation_permissions

    monkeypatch.setattr(
        presentation_permissions,
        "_LAUNCH_REPORT_PERMISSIONS_FILE",
        launch_report_permissions_file,
    )
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    presentation_permissions._load_launch_report_permissions.cache_clear()
    return presentation_permissions


def _configure_brand_report_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    site_emails: list[str],
    document_emails: list[str],
    include_document: bool = False,
    include_podcast: bool = False,
) -> Any:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"attribute_analysis": site_emails}),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {"attribute_analysis": ["/review/brand-reports"]},
    )
    brand_report_permissions_file = tmp_path / "brand_report_permissions.json"
    brand_report_permissions_file.write_text(
        json.dumps({"example_brand_report": document_emails}),
        encoding="utf-8",
    )

    pdf_root = tmp_path / "brand_reports"
    pdf_root.mkdir(parents=True, exist_ok=True)
    (pdf_root / "example_brand_report.pdf").write_bytes(b"%PDF-1.4\n%EOF\n")

    document_root = tmp_path / "brand_report_documents"
    document_root.mkdir(parents=True, exist_ok=True)
    if include_document:
        (document_root / "example_brand_report.pdf").write_bytes(b"%PDF-1.4\n%EOF\n")

    podcast_root = tmp_path / "brand_report_podcasts"
    podcast_root.mkdir(parents=True, exist_ok=True)
    if include_podcast:
        (podcast_root / "example_brand_report.m4a").write_bytes(b"podcast-bytes")

    import modules.projects.api as projects_api

    monkeypatch.setattr(projects_api, "_brand_reports_pdf_root", lambda: pdf_root)
    monkeypatch.setattr(
        projects_api,
        "_brand_report_documents_root",
        lambda: document_root,
    )
    monkeypatch.setattr(
        projects_api,
        "_brand_report_podcasts_root",
        lambda: podcast_root,
    )
    monkeypatch.setattr(
        projects_api,
        "_ensure_cache_fresh",
        lambda *_args, **_kwargs: {"page_count": 2},
    )
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)

    from modules.projects import permissions as presentation_permissions

    monkeypatch.setattr(
        presentation_permissions,
        "_BRAND_REPORT_PERMISSIONS_FILE",
        brand_report_permissions_file,
    )
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    presentation_permissions._load_brand_report_permissions.cache_clear()
    return presentation_permissions


def _configure_product_hypotheses_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    site_emails: list[str],
    document_emails: list[str],
) -> Any:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"attribute_analysis": site_emails}),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {"attribute_analysis": ["/review/product-hypotheses"]},
    )
    concept_permissions_file = tmp_path / "concept_permissions.json"
    concept_permissions_file.write_text(
        json.dumps({"example_concept_site": document_emails}),
        encoding="utf-8",
    )

    concepts_root = tmp_path / "concept_sites"
    site_root = concepts_root / "example_concept_site"
    site_root.mkdir(parents=True, exist_ok=True)
    (site_root / "board.png").write_bytes(MINIMAL_PNG_BYTES)
    (site_root / "index.html").write_text(
        (
            "<!doctype html><html><body>"
            '<div class="imageWrap"><img src="board.png" alt="Hypothesis board"></div>'
            '<a href="velvet-care-lip-stylo/index.html">Open PDP website</a>'
            "</body></html>"
        ),
        encoding="utf-8",
    )
    nested_root = site_root / "velvet-care-lip-stylo"
    nested_root.mkdir(parents=True, exist_ok=True)
    (nested_root / "index.html").write_text(
        (
            "<!doctype html><html><body>"
            '<figure class="board-frame"><img src="../board.png" alt="PDP board"></figure>'
            "Velvet Care Lip Stylo"
            "</body></html>"
        ),
        encoding="utf-8",
    )

    import modules.projects.api as projects_api

    monkeypatch.setattr(projects_api, "_concept_sites_root", lambda: concepts_root)
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)

    from modules.projects import permissions as presentation_permissions

    monkeypatch.setattr(
        presentation_permissions,
        "_CONCEPT_PERMISSIONS_FILE",
        concept_permissions_file,
    )
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    presentation_permissions._load_concept_permissions.cache_clear()
    return presentation_permissions


def _capture_projects_template_context(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    import modules.projects.api as projects_api

    captured: dict[str, Any] = {}

    def _template_response(
        request: object,
        name: str,
        context: dict[str, Any],
    ) -> HTMLResponse:
        _ = request
        captured["name"] = name
        captured["context"] = context
        return HTMLResponse("captured")

    monkeypatch.setattr(projects_api.templates, "TemplateResponse", _template_response)
    return captured


def _capture_pdp_template_context(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    import modules.pdp.api as pdp_api

    captured: dict[str, Any] = {}

    def _template_response(
        name: str,
        context: dict[str, Any],
        *,
        status_code: int = 200,
    ) -> HTMLResponse:
        captured["name"] = name
        captured["context"] = context
        captured["status_code"] = status_code
        return HTMLResponse("captured", status_code=status_code)

    monkeypatch.setattr(pdp_api.templates, "TemplateResponse", _template_response)
    return captured


def _enable_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "dummy-secret")


def _make_authenticated_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    email: str,
) -> Iterator[TestClient]:
    _enable_auth_env(monkeypatch)
    get_auth_config.cache_clear()
    with TestClient(app) as test_client:
        config = get_auth_config()
        token, _ = create_session_cookie(
            GoogleUserInfo(email=email),
            config,
        )
        cookie_header = f"{config.session_cookie_name}={token}"
        test_client.cookies.set(config.session_cookie_name, token, domain="testserver")
        test_client.headers.update({"cookie": cookie_header})
        yield test_client
    get_auth_config.cache_clear()


@contextmanager
def _authenticated_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    email: str,
) -> Iterator[TestClient]:
    client_iter = _make_authenticated_client(monkeypatch, email=email)
    client = next(client_iter)
    try:
        yield client
    finally:
        with suppress(StopIteration):
            next(client_iter)


@pytest.fixture()
def client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[TestClient]:
    """Provide an authenticated client for site routes."""

    _configure_default_test_permissions(monkeypatch, tmp_path)
    yield from _make_authenticated_client(monkeypatch, email=AUTHORIZED_EMAIL)


@pytest.fixture()
def client_without_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[TestClient]:
    """Authenticated user lacking presentations permission."""

    _configure_default_test_permissions(monkeypatch, tmp_path)
    yield from _make_authenticated_client(monkeypatch, email=UNAUTHORIZED_EMAIL)


@pytest.fixture()
def unauthenticated_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[TestClient]:
    """Provide a client requiring login (auth enabled but no cookie)."""

    _configure_default_test_permissions(monkeypatch, tmp_path)
    _enable_auth_env(monkeypatch)
    get_auth_config.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_auth_config.cache_clear()


@pytest.fixture(autouse=True)
def _reset_auth_on_exit(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    yield
    _unset_auth_env(monkeypatch)
    get_auth_config.cache_clear()


def test_presentations_page_renders_content_for_authorized_user(
    client: TestClient,
) -> None:
    response = client.get("/presentations/page?lang=en")
    assert response.status_code == 200


def test_presentations_page_honors_language_parameter(client: TestClient) -> None:
    response = client.get("/presentations/page?lang=it")
    assert response.status_code == 200


def test_presentations_page_redirects_to_login_when_unauthenticated(
    unauthenticated_client: TestClient,
) -> None:
    response = unauthenticated_client.get(
        "/presentations/page?lang=en",
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"].startswith("/")


def test_presentations_page_forbidden_without_permission(
    client_without_permission: TestClient,
) -> None:
    response = client_without_permission.get(
        "/presentations/page?lang=en",
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_presentations_forbidden_without_permission(
    client_without_permission: TestClient,
) -> None:
    response = client_without_permission.get(
        PRESENTATION_DECK_URL,
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_presentations_redirect_when_unauthenticated(
    unauthenticated_client: TestClient,
) -> None:
    response = unauthenticated_client.get(
        PRESENTATION_DECK_URL,
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"].startswith("/")


def test_presentations_render_for_authorized_user(client: TestClient) -> None:
    response = client.get(
        PRESENTATION_DECK_URL,
        follow_redirects=False,
    )
    assert response.status_code == 404


def test_presentations_router_enforces_permissions_flow(
    client_without_permission: TestClient,
    unauthenticated_client: TestClient,
    client: TestClient,
) -> None:
    """Full integration covering unauthorized, unauthenticated, and happy paths."""

    deck_path = PRESENTATION_DECK_DIRECTORY

    forbidden_response = client_without_permission.get(
        deck_path,
        follow_redirects=False,
    )
    assert forbidden_response.status_code == 403

    unauthenticated_response = unauthenticated_client.get(
        deck_path,
        follow_redirects=False,
    )
    assert unauthenticated_response.status_code == 307
    assert unauthenticated_response.headers["location"].startswith("/")

    authorized_response = client.get(
        deck_path,
        follow_redirects=False,
    )
    assert authorized_response.status_code == 404


def test_presentations_use_deck_toolkit_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps(
            {
                "deck_toolkit": [AUTHORIZED_EMAIL, PRESENTATIONS_ONLY_EMAIL],
            }
        ),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {
            "deck_toolkit": ["/presentations"],
        },
    )
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    try:
        with _authenticated_client(
            monkeypatch, email=PRESENTATIONS_ONLY_EMAIL
        ) as deck_client:
            page_response = deck_client.get("/presentations/page?lang=en")
            assert page_response.status_code == 200
            deck_response = deck_client.get(
                PRESENTATION_DECK_URL,
                follow_redirects=False,
            )
            assert deck_response.status_code == 404
        with _authenticated_client(
            monkeypatch, email=SLIDES_ONLY_EMAIL
        ) as blocked_client:
            presentations_page = blocked_client.get(
                "/presentations/page?lang=en", follow_redirects=False
            )
            assert presentations_page.status_code == 403
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()


def test_permission_expiry_blocks_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps(
            {
                "presentations": [
                    {"email": AUTHORIZED_EMAIL, "expires_at": "2999-01-01T00:00:00Z"},
                    {"email": UNAUTHORIZED_EMAIL, "expires_at": "2000-01-01T00:00:00Z"},
                ],
            }
        ),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {"presentations": ["/presentations"]},
    )
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            allowed_response = allowed_client.get(
                "/presentations/page?lang=en", follow_redirects=False
            )
            assert allowed_response.status_code == 200
        with _authenticated_client(
            monkeypatch, email=UNAUTHORIZED_EMAIL
        ) as blocked_client:
            blocked_response = blocked_client.get(
                "/presentations/page?lang=en", follow_redirects=False
            )
            assert blocked_response.status_code == 403
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()


def test_check_page_is_auth_only_and_deep_research_validator_static_is_public(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({}),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {},
    )
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            check_response = allowed_client.get(
                "/check/page?lang=en", follow_redirects=False
            )
            assert check_response.status_code == 200
            plugin_response = allowed_client.get(
                "/static/shared/deep-research-validator/index.html",
                follow_redirects=False,
            )
            assert plugin_response.status_code == 200

        with _authenticated_client(
            monkeypatch, email=UNAUTHORIZED_EMAIL
        ) as blocked_client:
            check_response = blocked_client.get(
                "/check/page?lang=en", follow_redirects=False
            )
            assert check_response.status_code == 200
            plugin_response = blocked_client.get(
                "/static/shared/deep-research-validator/index.html",
                follow_redirects=False,
            )
            assert plugin_response.status_code == 200
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()


def test_presentations_pdf_blocks_unauthorized_deck_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"presentations": [AUTHORIZED_EMAIL, UNAUTHORIZED_EMAIL]}),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {"presentations": ["/presentations"]},
    )
    presentation_permissions_file = tmp_path / "presentation_permissions.json"
    presentation_permissions_file.write_text(
        json.dumps({"deck_one": [AUTHORIZED_EMAIL]}),
        encoding="utf-8",
    )
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir(parents=True, exist_ok=True)
    (pdf_root / "Deck One.pdf").write_bytes(b"%PDF-1.4\n%EOF\n")
    import modules.projects.api as projects_api

    monkeypatch.setattr(projects_api, "_pdf_root", lambda: pdf_root)
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    from modules.projects import permissions as presentation_permissions

    monkeypatch.setattr(
        presentation_permissions,
        "_PRESENTATION_PERMISSIONS_FILE",
        presentation_permissions_file,
    )
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    presentation_permissions._load_presentation_permissions.cache_clear()
    try:
        with _authenticated_client(
            monkeypatch, email=UNAUTHORIZED_EMAIL
        ) as blocked_client:
            response = blocked_client.get(
                "/presentations/pdf/deck_one?lang=en",
                follow_redirects=False,
            )
            assert response.status_code == 403
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_presentation_permissions.cache_clear()


def test_launch_reports_page_requires_attribute_analysis_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"attribute_analysis": [AUTHORIZED_EMAIL]}),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {"attribute_analysis": ["/review/reports"]},
    )
    launch_report_permissions_file = tmp_path / "launch_report_permissions.json"
    launch_report_permissions_file.write_text(
        json.dumps({"launch_report_one": [AUTHORIZED_EMAIL]}),
        encoding="utf-8",
    )
    pdf_root = tmp_path / "launch_reports"
    pdf_root.mkdir(parents=True, exist_ok=True)
    (pdf_root / "Launch Report One.pdf").write_bytes(b"%PDF-1.4\n%EOF\n")
    import modules.projects.api as projects_api

    monkeypatch.setattr(projects_api, "_launch_reports_pdf_root", lambda: pdf_root)
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    from modules.projects import permissions as presentation_permissions

    monkeypatch.setattr(
        presentation_permissions,
        "_LAUNCH_REPORT_PERMISSIONS_FILE",
        launch_report_permissions_file,
    )
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    presentation_permissions._load_launch_report_permissions.cache_clear()
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/reports/page?lang=en", follow_redirects=False
            )
            assert response.status_code == 200
        with _authenticated_client(
            monkeypatch, email=UNAUTHORIZED_EMAIL
        ) as blocked_client:
            response = blocked_client.get(
                "/review/reports/page?lang=en", follow_redirects=False
            )
            assert response.status_code == 403
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_brand_reports_page_uses_separate_root_and_permissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_brand_report_environment(
        monkeypatch,
        tmp_path,
        site_emails=[AUTHORIZED_EMAIL],
        document_emails=[AUTHORIZED_EMAIL],
    )
    captured = _capture_projects_template_context(monkeypatch)
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/brand-reports/page?lang=en",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert captured["name"] == "projects.html"
        assert captured["context"]["page_label"] == "Brand fit"
        assert captured["context"]["viewer_base_path"] == "/review/brand-reports/pdf"
        assert captured["context"]["copy"]["page_help"].startswith(
            "Use brand fit reports"
        )

        documents = captured["context"]["documents"]
        assert len(documents) == 1
        assert documents[0]["doc_id"] == "example_brand_report"
        assert documents[0]["title"] == "example brand report"
        assert documents[0]["allowed"] is True
        assert documents[0]["indent_level"] == 0
        assert "validation" not in documents[0]
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_brand_report_permissions.cache_clear()


def test_product_hypotheses_page_uses_concept_sites_root_and_permissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_product_hypotheses_environment(
        monkeypatch,
        tmp_path,
        site_emails=[AUTHORIZED_EMAIL],
        document_emails=[AUTHORIZED_EMAIL],
    )
    captured = _capture_projects_template_context(monkeypatch)
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/product-hypotheses/page?lang=en",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert captured["name"] == "projects.html"
        assert captured["context"]["page_label"] == "Product hints"
        assert (
            captured["context"]["viewer_base_path"] == "/review/product-hypotheses/site"
        )
        assert (
            captured["context"]["copy"]["page_help"]
            == "Explore product hypotheses derived from retailer signals and brand fit."
        )

        documents = captured["context"]["documents"]
        assert len(documents) == 1
        assert documents[0]["doc_id"] == "example_concept_site"
        assert documents[0]["title"] == "example concept site"
        assert documents[0]["allowed"] is True
        assert documents[0]["indent_level"] == 0
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_concept_permissions.cache_clear()


def test_concept_site_blocks_unauthorized_document_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_product_hypotheses_environment(
        monkeypatch,
        tmp_path,
        site_emails=[AUTHORIZED_EMAIL, UNAUTHORIZED_EMAIL],
        document_emails=[AUTHORIZED_EMAIL],
    )
    try:
        with _authenticated_client(
            monkeypatch, email=UNAUTHORIZED_EMAIL
        ) as blocked_client:
            response = blocked_client.get(
                "/review/product-hypotheses/site/example_concept_site/",
                follow_redirects=False,
            )
            assert response.status_code == 403
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_concept_permissions.cache_clear()


def test_concept_site_redirects_to_slash_and_serves_nested_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_product_hypotheses_environment(
        monkeypatch,
        tmp_path,
        site_emails=[AUTHORIZED_EMAIL],
        document_emails=[AUTHORIZED_EMAIL],
    )
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            redirect_response = allowed_client.get(
                "/review/product-hypotheses/site/example_concept_site?lang=en",
                follow_redirects=False,
            )
            assert redirect_response.status_code == 307
            assert (
                redirect_response.headers["location"]
                == "/review/product-hypotheses/site/example_concept_site/?lang=en"
            )

            page_response = allowed_client.get(
                "/review/product-hypotheses/site/example_concept_site/?lang=en",
                follow_redirects=False,
            )
            assert page_response.status_code == 200
            assert "text/html" in page_response.headers["content-type"]
            assert "Open PDP website" in page_response.text
            assert "Signal-informed hypothesis artifact" in page_response.text
            assert "mparanza-hypothesis-artifact-watermark" in page_response.text
            assert 'src="data:image/png;base64,' in page_response.text
            assert 'src="board.png"' not in page_response.text

            asset_response = allowed_client.get(
                "/review/product-hypotheses/site/example_concept_site/board.png",
                follow_redirects=False,
            )
            assert asset_response.status_code == 200
            assert asset_response.headers["content-type"] == "image/png"
            assert asset_response.content == MINIMAL_PNG_BYTES

            nested_response = allowed_client.get(
                "/review/product-hypotheses/site/example_concept_site/velvet-care-lip-stylo/index.html?lang=en",
                follow_redirects=False,
            )
            assert nested_response.status_code == 200
            assert "Velvet Care Lip Stylo" in nested_response.text
            assert "Signal-informed hypothesis artifact" in nested_response.text
            assert 'src="data:image/png;base64,' in nested_response.text
            assert 'src="../board.png"' not in nested_response.text
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_concept_permissions.cache_clear()


def test_concept_site_overlay_preserves_open_board_image_links(tmp_path: Path) -> None:
    from bs4 import BeautifulSoup

    import modules.projects.api as projects_api

    assets_root = tmp_path / "concept_site"
    assets_root.mkdir()
    (assets_root / "board.png").write_bytes(MINIMAL_PNG_BYTES)
    html = """
    <html>
      <body>
        <figure class="board-frame"><img src="board.png" alt="Board"></figure>
        <a href="board.png">Open board image</a>
      </body>
    </html>
    """

    injected = projects_api._inject_concept_site_image_overlay(
        html,
        base_dir=assets_root,
        asset_root=assets_root,
    )
    soup = BeautifulSoup(injected, "html.parser")
    image = soup.select_one(".board-frame > img")
    link = soup.find("a", string="Open board image")

    assert image is not None
    assert link is not None
    assert image["src"].startswith("data:image/png;base64,")
    assert link["href"] == "board.png"
    assert link["target"] == "_blank"
    assert link["rel"] == ["noopener"]
    assert "board.png" not in image["src"]


def test_concept_site_overlay_targets_figure_hero_images() -> None:
    from bs4 import BeautifulSoup

    import modules.projects.api as projects_api

    html = """
    <html>
      <head><title>Blush hypothesis workspace</title></head>
      <body>
        <header><a class="logo" href="index.html">Product hints</a></header>
        <p class="eyebrow">Blush</p>
        <h1>Buildable Pressed Powder Blush</h1>
        <p>Example catalog support remains relevant evidence.</p>
        <section><div class="heroVisual"><img src="data:image/png;base64,abc" alt="Foundation"></div></section>
        <article><div class="cardimg"><img src="data:image/png;base64,ghi" alt="Lipstick"></div></article>
        <article class="hypCard"><a href="pdp.html"><img src="data:image/png;base64,jkl" alt="Linked board"></a></article>
        <main><figure><img src="data:image/png;base64,abc" alt="Hero"></figure></main>
        <article class="hypCard"><figure><img src="data:image/png;base64,def" alt="Card"></figure></article>
        <footer><span>Product Hypotheses</span></footer>
      </body>
    </html>
    """

    injected = projects_api._inject_concept_site_image_overlay(html)
    soup = BeautifulSoup(injected, "html.parser")
    captions = soup.select(".mparanza-hypothesis-artifact-watermark")

    assert "Signal-informed hypothesis artifact" in injected
    assert len(captions) == 5
    assert [caption.previous_sibling.name for caption in captions] == [
        "img",
        "div",
        "img",
        "img",
        "img",
    ]
    assert [caption.get_text() for caption in captions] == [
        "Signal-informed hypothesis artifact \u00b7 non-operational"
    ] * 5
    assert "mparanza-hypothesis-artifact-figure" not in captions[0].parent["class"]
    assert "cardimg" in captions[1].previous_sibling["class"]
    assert (
        "mparanza-hypothesis-artifact-figure"
        not in captions[1].previous_sibling["class"]
    )
    assert captions[2].parent.name == "a"
    assert "mparanza-hypothesis-artifact-frame" in captions[2].parent["class"]
    assert captions[2].parent.parent["class"] == ["hypCard"]
    assert "mparanza-hypothesis-artifact-figure" in captions[3].parent["class"]
    assert "mparanza-hypothesis-artifact-figure" in captions[4].parent["class"]
    assert "overflow: visible !important" in injected
    assert "height: auto !important" in injected
    assert soup.select_one("#mparanza-hypothesis-review-style") is not None
    assert (
        'font-family: "Instrument Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif !important'
        in injected
    )
    assert (
        "--mparanza-hypothesis-review-bg: linear-gradient(180deg, #ffffff 0%, #fbfcfd 100%)"
        in injected
    )
    assert (
        "background: var(--mparanza-hypothesis-review-surface) !important" in injected
    )
    assert "background-image: none !important" in injected
    assert ".step-card::after" in injected
    assert "content: none !important" in injected
    assert "clamp(1.65rem, 2.8vw, 2.65rem)" in injected
    assert "--mparanza-hypothesis-review-shadow: none" in injected
    assert soup.select_one(".logo").get_text(strip=True) == "Product hints"
    assert soup.select_one(".eyebrow").get_text(strip=True) == "Blush"
    assert (
        soup.select_one("h1").get_text(strip=True) == "Buildable Pressed Powder Blush"
    )
    assert soup.select_one("title").get_text(strip=True) == "Blush hypothesis workspace"
    assert "Example catalog support remains relevant evidence." in injected
    assert "insertAdjacentElement" not in injected
    assert "position: absolute" not in injected


def test_brand_reports_pdf_blocks_unauthorized_document_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_brand_report_environment(
        monkeypatch,
        tmp_path,
        site_emails=[AUTHORIZED_EMAIL, UNAUTHORIZED_EMAIL],
        document_emails=[AUTHORIZED_EMAIL],
    )
    try:
        with _authenticated_client(
            monkeypatch, email=UNAUTHORIZED_EMAIL
        ) as blocked_client:
            response = blocked_client.get(
                "/review/brand-reports/pdf/example_brand_report?lang=en",
                follow_redirects=False,
            )
            assert response.status_code == 403
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_brand_report_permissions.cache_clear()


def test_brand_reports_missing_document_renders_not_found_page_for_browser(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_brand_report_environment(
        monkeypatch,
        tmp_path,
        site_emails=[AUTHORIZED_EMAIL],
        document_emails=[AUTHORIZED_EMAIL],
    )
    captured = _capture_pdp_template_context(monkeypatch)
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/brand-reports/pdf/missing_brand_report?lang=en",
                headers={"accept": "text/html"},
                follow_redirects=False,
            )
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("text/html")
        assert captured["name"] == "not_found.html"
        assert captured["status_code"] == 404
        assert captured["context"]["requested_path"] == (
            "/review/brand-reports/pdf/missing_brand_report"
        )
        assert captured["context"]["message"] == (
            "The page may have moved, been deleted, or the URL may be incomplete."
        )
        assert captured["context"]["primary_href"] == (
            "/review/brand-reports/page?lang=en"
        )
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_brand_report_permissions.cache_clear()


def test_brand_reports_missing_document_keeps_json_for_api_clients(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_brand_report_environment(
        monkeypatch,
        tmp_path,
        site_emails=[AUTHORIZED_EMAIL],
        document_emails=[AUTHORIZED_EMAIL],
    )
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/brand-reports/pdf/missing_brand_report?lang=en",
                headers={"accept": "application/json"},
                follow_redirects=False,
            )
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        assert response.json() == {"detail": "Document not found."}
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_brand_report_permissions.cache_clear()


def test_brand_report_viewer_shows_companion_controls_without_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_brand_report_environment(
        monkeypatch,
        tmp_path,
        site_emails=[AUTHORIZED_EMAIL],
        document_emails=[AUTHORIZED_EMAIL],
        include_document=True,
        include_podcast=True,
    )
    captured = _capture_projects_template_context(monkeypatch)
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/brand-reports/pdf/example_brand_report?lang=en",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert captured["name"] == "pdf_viewer.html"
        assert (
            captured["context"]["podcast_url"]
            == "/review/brand-reports/pdf/example_brand_report/podcast"
        )
        assert (
            captured["context"]["document_switch_url"]
            == "/review/brand-reports/pdf/example_brand_report?lang=en&page=1&variant=document"
        )
        assert captured["context"]["report_switch_url"] == ""
        assert captured["context"]["viewer_variant"] == "report"
        assert captured["context"]["viewer_variant_label"] == "Brand report"
        assert captured["context"]["validation_layer_url"] == ""
        assert (
            captured["context"]["ai_accuracy_disclaimer"]
            == "AI can be inaccurate; please double-check its responses."
        )
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_brand_report_permissions.cache_clear()


def test_brand_report_document_variant_uses_companion_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_brand_report_environment(
        monkeypatch,
        tmp_path,
        site_emails=[AUTHORIZED_EMAIL],
        document_emails=[AUTHORIZED_EMAIL],
        include_document=True,
        include_podcast=False,
    )
    captured = _capture_projects_template_context(monkeypatch)
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/brand-reports/pdf/example_brand_report?lang=en&page=1&variant=document",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert captured["name"] == "pdf_viewer.html"
        assert captured["context"]["viewer_variant"] == "document"
        assert captured["context"]["viewer_variant_label"] == "Document version"
        assert (
            captured["context"]["report_switch_url"]
            == "/review/brand-reports/pdf/example_brand_report?lang=en&page=1"
        )
        assert captured["context"]["document_switch_url"] == ""
        assert captured["context"]["validation_layer_url"] == ""
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_brand_report_permissions.cache_clear()


def test_launch_reports_page_orders_parent_reports_before_indented_children(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"attribute_analysis": [AUTHORIZED_EMAIL]}),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {"attribute_analysis": ["/review/reports"]},
    )
    launch_report_permissions_file = tmp_path / "launch_report_permissions.json"
    launch_report_permissions_file.write_text(json.dumps({}), encoding="utf-8")
    pdf_root = tmp_path / "launch_reports"
    pdf_root.mkdir(parents=True, exist_ok=True)
    for filename in (
        "Category A Variant 1.pdf",
        "Category A.pdf",
        "Category A Variant 2.pdf",
        "Category B Variant 1.pdf",
        "Category B.pdf",
        "Category B Variant 2.pdf",
        "Category B Variant 3.pdf",
        "Category B Variant 4.pdf",
        "Category C.pdf",
        "Category C Variant 1.pdf",
        "Category C Variant 2.pdf",
    ):
        (pdf_root / filename).write_bytes(b"%PDF-1.4\n%EOF\n")
    import modules.projects.api as projects_api

    monkeypatch.setattr(projects_api, "_launch_reports_pdf_root", lambda: pdf_root)
    listing_groups = (
        ("category_a", ("category_a_variant_1", "category_a_variant_2")),
        (
            "category_b",
            (
                "category_b_variant_1",
                "category_b_variant_2",
                "category_b_variant_3",
                "category_b_variant_4",
            ),
        ),
        ("category_c", ("category_c_variant_1", "category_c_variant_2")),
    )
    monkeypatch.setattr(projects_api, "_LAUNCH_REPORT_LIST_GROUPS", listing_groups)
    monkeypatch.setattr(
        projects_api,
        "_LAUNCH_REPORT_CHILD_IDS",
        frozenset(child for _, children in listing_groups for child in children),
    )
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    from modules.projects import permissions as presentation_permissions

    monkeypatch.setattr(
        presentation_permissions,
        "_LAUNCH_REPORT_PERMISSIONS_FILE",
        launch_report_permissions_file,
    )
    captured = _capture_projects_template_context(monkeypatch)
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    presentation_permissions._load_launch_report_permissions.cache_clear()
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/reports/page?lang=en", follow_redirects=False
            )
        assert response.status_code == 200
        assert captured["name"] == "projects.html"
        documents = captured["context"]["documents"]
        assert [document["doc_id"] for document in documents] == [
            "category_a",
            "category_a_variant_1",
            "category_a_variant_2",
            "category_b",
            "category_b_variant_1",
            "category_b_variant_2",
            "category_b_variant_3",
            "category_b_variant_4",
            "category_c",
            "category_c_variant_1",
            "category_c_variant_2",
        ]
        assert {
            document["doc_id"]: document["indent_level"] for document in documents
        } == {
            "category_a": 0,
            "category_a_variant_1": 1,
            "category_a_variant_2": 1,
            "category_b": 0,
            "category_b_variant_1": 1,
            "category_b_variant_2": 1,
            "category_b_variant_3": 1,
            "category_b_variant_4": 1,
            "category_c": 0,
            "category_c_variant_1": 1,
            "category_c_variant_2": 1,
        }
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_launch_reports_page_includes_provisional_validation_states(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"attribute_analysis": [AUTHORIZED_EMAIL]}),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {"attribute_analysis": ["/review/reports"]},
    )
    launch_report_permissions_file = tmp_path / "launch_report_permissions.json"
    launch_report_permissions_file.write_text(json.dumps({}), encoding="utf-8")
    pdf_root = tmp_path / "launch_reports"
    pdf_root.mkdir(parents=True, exist_ok=True)
    for filename in (
        "Category A.pdf",
        "Category A Variant 1.pdf",
        "Category A Variant 2.pdf",
        "Category A Variant 3.pdf",
        "Category A Variant 4.pdf",
        "Category A Variant 5.pdf",
        "Category A Variant 6.pdf",
        "Summary Report.pdf",
        "Summary Report Variant 1.pdf",
    ):
        (pdf_root / filename).write_bytes(b"%PDF-1.4\n%EOF\n")

    validation_root = pdf_root / "validation"
    validation_root.mkdir(parents=True, exist_ok=True)
    for stem, status_value, resolver_status, report_type, summary in (
        ("Category A", "fail", "unresolved", None, None),
        (
            "Category A Variant 1",
            "fail",
            "matched",
            None,
            {"claim_count": 4, "unresolved_count": 40},
        ),
        (
            "Category A Variant 2",
            "pass_with_warnings",
            "matched",
            None,
            {"claim_count": 20, "unresolved_count": 25},
        ),
        (
            "Category A Variant 3",
            "pass_with_warnings",
            "matched",
            None,
            {"claim_count": 80, "non_claim_count": 0, "unresolved_count": 20},
        ),
        ("Category A Variant 4", "fail", "matched", None, None),
        ("Category A Variant 5", "pass_with_warnings", "matched", None, None),
        ("Category A Variant 6", "pass", "matched", None, None),
        ("Summary Report", "not_validated", "summary_report", "summary_report", None),
        (
            "Summary Report Variant 1",
            "pass_with_warnings",
            "summary_report",
            "summary_report",
            None,
        ),
    ):
        payload = {
            "status": status_value,
            "resolver": {"status": resolver_status},
        }
        if report_type is not None:
            payload["report_type"] = report_type
        if summary is not None:
            payload["summary"] = summary
        (validation_root / f"{stem}.validation.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    import modules.projects.api as projects_api

    monkeypatch.setattr(projects_api, "_launch_reports_pdf_root", lambda: pdf_root)
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    from modules.projects import permissions as presentation_permissions

    monkeypatch.setattr(
        presentation_permissions,
        "_LAUNCH_REPORT_PERMISSIONS_FILE",
        launch_report_permissions_file,
    )
    captured = _capture_projects_template_context(monkeypatch)
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    presentation_permissions._load_launch_report_permissions.cache_clear()
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/reports/page?lang=en", follow_redirects=False
            )
        assert response.status_code == 200
        documents = {
            document["doc_id"]: document
            for document in captured["context"]["documents"]
        }
        expected_badges = {
            "category_a": ("pending", "validation_status_pending", ""),
            "category_a_variant_1": (
                "unknown",
                "validation_status_unknown",
                "validation_status_unknown_short",
            ),
            "category_a_variant_2": (
                "unknown",
                "validation_status_unknown",
                "validation_status_unknown_short",
            ),
            "category_a_variant_3": ("noted", "validation_status_noted", ""),
            "category_a_variant_4": ("caution", "validation_status_caution", ""),
            "category_a_variant_5": ("noted", "validation_status_noted", ""),
            "category_a_variant_6": ("checked", "validation_status_checked", ""),
            "summary_report": ("summary", "validation_status_summary", ""),
            "summary_report_variant_1": ("noted", "validation_status_noted", ""),
        }
        for doc_id, (state, label_key, short_label_key) in expected_badges.items():
            badge = documents[doc_id]["validation"]
            assert badge["state"] == state
            assert badge["label_key"] == label_key
            assert badge.get("short_label_key", "") == short_label_key
            assert badge["tooltip"]
        assert (
            "Resolved 4/44 text units"
            in documents["category_a_variant_1"]["validation"]["tooltip"]
        )
        assert (
            "Package matching failed"
            in documents["category_a"]["validation"]["tooltip"]
        )
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_launch_reports_pdf_blocks_unauthorized_deck_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"attribute_analysis": [AUTHORIZED_EMAIL, UNAUTHORIZED_EMAIL]}),
        encoding="utf-8",
    )
    structure_file = _write_permission_structure(
        tmp_path,
        {"attribute_analysis": ["/review/reports"]},
    )
    launch_report_permissions_file = tmp_path / "launch_report_permissions.json"
    launch_report_permissions_file.write_text(
        json.dumps({"launch_report_one": [AUTHORIZED_EMAIL]}),
        encoding="utf-8",
    )
    pdf_root = tmp_path / "launch_reports"
    pdf_root.mkdir(parents=True, exist_ok=True)
    (pdf_root / "Launch Report One.pdf").write_bytes(b"%PDF-1.4\n%EOF\n")
    import modules.projects.api as projects_api

    monkeypatch.setattr(projects_api, "_launch_reports_pdf_root", lambda: pdf_root)
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    from modules.projects import permissions as presentation_permissions

    monkeypatch.setattr(
        presentation_permissions,
        "_LAUNCH_REPORT_PERMISSIONS_FILE",
        launch_report_permissions_file,
    )
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    presentation_permissions._load_launch_report_permissions.cache_clear()
    try:
        with _authenticated_client(
            monkeypatch, email=UNAUTHORIZED_EMAIL
        ) as blocked_client:
            response = blocked_client.get(
                "/review/reports/pdf/launch_report_one?lang=en",
                follow_redirects=False,
            )
            assert response.status_code == 403
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_launch_report_viewer_shows_companion_controls_when_assets_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_launch_report_viewer_environment(
        monkeypatch,
        tmp_path,
        include_document=True,
        include_podcast=True,
        include_video=True,
    )
    captured = _capture_projects_template_context(monkeypatch)
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/reports/pdf/launch_report_one?lang=en",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert captured["name"] == "pdf_viewer.html"
        assert (
            captured["context"]["podcast_url"]
            == "/review/reports/pdf/launch_report_one/podcast"
        )
        assert (
            captured["context"]["video_url"]
            == "/review/reports/pdf/launch_report_one/video"
        )
        assert (
            captured["context"]["document_switch_url"]
            == "/review/reports/pdf/launch_report_one?lang=en&page=1&variant=document"
        )
        assert captured["context"]["report_switch_url"] == ""
        assert captured["context"]["viewer_variant"] == "report"
        assert (
            captured["context"]["validation_layer_url"]
            == "/review/reports/pdf/launch_report_one/validation-layer"
        )
        assert (
            captured["context"]["ai_accuracy_disclaimer"]
            == "AI can be inaccurate; please double-check its responses."
        )
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_launch_report_viewer_hides_companion_controls_when_assets_are_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_launch_report_viewer_environment(
        monkeypatch,
        tmp_path,
        include_document=False,
        include_podcast=False,
    )
    captured = _capture_projects_template_context(monkeypatch)
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/reports/pdf/launch_report_one?lang=en",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert captured["name"] == "pdf_viewer.html"
        assert captured["context"]["podcast_url"] == ""
        assert captured["context"]["video_url"] == ""
        assert captured["context"]["document_switch_url"] == ""
        assert captured["context"]["report_switch_url"] == ""
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_launch_report_document_variant_uses_companion_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_launch_report_viewer_environment(
        monkeypatch,
        tmp_path,
        include_document=True,
        include_podcast=False,
    )
    captured = _capture_projects_template_context(monkeypatch)
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/reports/pdf/launch_report_one?lang=en&page=1&variant=document",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert captured["name"] == "pdf_viewer.html"
        assert captured["context"]["viewer_variant"] == "document"
        assert captured["context"]["viewer_variant_label"] == "Document version"
        assert (
            captured["context"]["report_switch_url"]
            == "/review/reports/pdf/launch_report_one?lang=en&page=1"
        )
        assert captured["context"]["document_switch_url"] == ""
        assert captured["context"]["validation_layer_url"] == ""
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_launch_report_validation_layer_maps_cached_blocks_to_validation_states(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_launch_report_viewer_environment(
        monkeypatch,
        tmp_path,
        include_document=False,
        include_podcast=False,
    )
    import modules.projects.api as projects_api

    pdf_root = projects_api._launch_reports_pdf_root()
    reading_root = pdf_root / ".launch_report_reading_cache" / "launch_report_one"
    reading_root.mkdir(parents=True, exist_ok=True)
    assets_root = reading_root / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)
    (assets_root / "page.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + (200).to_bytes(4, "big")
        + (100).to_bytes(4, "big")
    )
    (reading_root / "slide_analysis.json").write_text(
        json.dumps(
            {
                "slides": [
                    {
                        "slideNumber": 1,
                        "assetPath": "assets/page.png",
                        "blocks": [
                            {
                                "blockId": "block-1",
                                "type": "bullet_item",
                                "detectedType": "text",
                                "text": "Recent matte is 26%",
                                "readingOrder": 0,
                                "bbox": {"x": 10, "y": 20, "w": 100, "h": 40},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                            {
                                "blockId": "block-2",
                                "type": "footer_meta",
                                "detectedType": "text",
                                "text": "Footer text",
                                "readingOrder": 1,
                                "bbox": {"x": 10, "y": 80, "w": 90, "h": 20},
                                "confidence": 0.42,
                                "auditStatus": "suspicious",
                                "auditReason": "OCR audit flagged this block.",
                            },
                            {
                                "blockId": "block-3",
                                "type": "table_title",
                                "detectedType": "text",
                                "text": "Shade Bundles (Top Sellers vs. Others)",
                                "readingOrder": 2,
                                "bbox": {"x": 10, "y": 50, "w": 120, "h": 20},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                            {
                                "blockId": "block-4",
                                "type": "table_title",
                                "detectedType": "text",
                                "text": "11% (Rest)",
                                "readingOrder": 3,
                                "bbox": {"x": 140, "y": 50, "w": 50, "h": 20},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    validation_root = pdf_root / "validation"
    validation_root.mkdir(parents=True, exist_ok=True)
    (validation_root / "launch_report_one.validation.json").write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "status": "verified",
                        "claim_family": "bundle_metric",
                        "claim_text": "Recent matte is 26%",
                        "slide_number": 1,
                        "page_number": 1,
                        "source_kind": "bullet",
                        "block_id": "block-1",
                        "details": {
                            "aggregation_rule_id": "bundle_metric_v1",
                            "reasons": ["matched package metric within tolerance"],
                        },
                    }
                ],
                "unresolved": [],
                "non_claims": [
                    {
                        "status": "non_claim",
                        "claim_family": "filter_non_claim",
                        "claim_text": "Shade Bundles (Top Sellers vs. Others)",
                        "slide_number": 1,
                        "page_number": 1,
                        "source_kind": "block_text",
                        "block_id": "block-3",
                        "details": {"filter_rule_id": "NF03"},
                    }
                ],
                "mapping_issues": [
                    {
                        "status": "ocr_layout_mapping_issue",
                        "claim_family": "ocr_layout_mapping_issue",
                        "claim_text": "11% (Rest)",
                        "slide_number": 1,
                        "page_number": 1,
                        "source_kind": "block_text",
                        "block_id": "block-4",
                        "details": {
                            "mapping_issue_type": "matrix_row_fragmentation_and_cell_order_scramble"
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/reports/pdf/launch_report_one/validation-layer"
                "?lang=en&page=1",
                follow_redirects=False,
            )
        assert response.status_code == 200
        payload = response.json()
        items = {item["block_id"]: item for item in payload["items"]}
        assert payload["available"] is True
        assert payload["validation_available"] is True
        assert payload["summary"]["sure"] == 1
        assert payload["summary"]["reading_issue"] == 2
        assert payload["summary"]["non_claim"] == 1
        assert items["block-1"]["state"] == "sure"
        assert items["block-1"]["bbox_source"] == {"width": 200, "height": 100}
        assert items["block-1"]["results"][0]["claim_family"] == "bundle_metric"
        assert "bundle_metric_v1" not in items["block-1"]["tooltip"]
        assert "matched package metric within tolerance" in items["block-1"]["tooltip"]
        assert items["block-2"]["state"] == "reading_issue"
        assert items["block-3"]["state"] == "non_claim"
        assert "NF03" not in items["block-3"]["tooltip"]
        assert items["block-4"]["state"] == "reading_issue"
        assert (
            "matrix_row_fragmentation_and_cell_order_scramble"
            in items["block-4"]["tooltip"]
        )
        assert items["block-2"]["bbox"] == {
            "x": 10.0,
            "y": 80.0,
            "w": 90.0,
            "h": 20.0,
        }
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_launch_report_validation_layer_uses_reconstructed_table_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_launch_report_viewer_environment(
        monkeypatch,
        tmp_path,
        include_document=False,
        include_podcast=False,
    )
    import modules.projects.api as projects_api

    pdf_root = projects_api._launch_reports_pdf_root()
    reading_root = pdf_root / ".launch_report_reading_cache" / "launch_report_one"
    reading_root.mkdir(parents=True, exist_ok=True)
    assets_root = reading_root / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)
    (assets_root / "page.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + (200).to_bytes(4, "big")
        + (100).to_bytes(4, "big")
    )
    (reading_root / "slide_analysis.json").write_text(
        json.dumps(
            {
                "slides": [
                    {
                        "slideNumber": 1,
                        "assetPath": "assets/page.png",
                        "blocks": [
                            {
                                "blockId": "block-10",
                                "type": "table_title",
                                "detectedType": "text",
                                "text": "Attribute Bundle",
                                "readingOrder": 0,
                                "groupId": "group-2",
                                "groupKind": "table",
                                "bbox": {"x": 10, "y": 10, "w": 60, "h": 10},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                            {
                                "blockId": "block-11",
                                "type": "table_title",
                                "detectedType": "text",
                                "text": "Recent (%)",
                                "readingOrder": 1,
                                "groupId": "group-2",
                                "groupKind": "table",
                                "bbox": {"x": 80, "y": 10, "w": 50, "h": 10},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                            {
                                "blockId": "block-12",
                                "type": "table_title",
                                "detectedType": "text",
                                "text": "Rest (%)",
                                "readingOrder": 2,
                                "groupId": "group-2",
                                "groupKind": "table",
                                "bbox": {"x": 140, "y": 10, "w": 40, "h": 10},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                            {
                                "blockId": "block-13",
                                "type": "table_title",
                                "detectedType": "text",
                                "text": "Red + High Shine",
                                "readingOrder": 3,
                                "groupId": "group-2",
                                "groupKind": "table",
                                "bbox": {"x": 10, "y": 30, "w": 60, "h": 10},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                            {
                                "blockId": "block-14",
                                "type": "table_title",
                                "detectedType": "text",
                                "text": "24% (11 products)",
                                "readingOrder": 4,
                                "groupId": "group-2",
                                "groupKind": "table",
                                "bbox": {"x": 80, "y": 30, "w": 50, "h": 10},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                            {
                                "blockId": "block-15",
                                "type": "table_title",
                                "detectedType": "text",
                                "text": "11% (Rest)",
                                "readingOrder": 5,
                                "groupId": "group-2",
                                "groupKind": "table",
                                "bbox": {"x": 140, "y": 30, "w": 40, "h": 10},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                            {
                                "blockId": "block-20",
                                "type": "table_title",
                                "detectedType": "text",
                                "text": "Wine + Stick",
                                "readingOrder": 6,
                                "groupId": "group-2",
                                "groupKind": "table",
                                "bbox": {"x": 10, "y": 80, "w": 60, "h": 10},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                            {
                                "blockId": "block-21",
                                "type": "table_title",
                                "detectedType": "text",
                                "text": "24% (11 products)",
                                "readingOrder": 7,
                                "groupId": "group-2",
                                "groupKind": "table",
                                "bbox": {"x": 80, "y": 80, "w": 50, "h": 10},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                            {
                                "blockId": "block-22",
                                "type": "table_title",
                                "detectedType": "text",
                                "text": "13% (Rest)",
                                "readingOrder": 8,
                                "groupId": "group-2",
                                "groupKind": "table",
                                "bbox": {"x": 140, "y": 80, "w": 40, "h": 10},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                            {
                                "blockId": "block-30",
                                "type": "bullet_item",
                                "detectedType": "text",
                                "text": "The innovation layer reveals a modest emerging signal.",
                                "readingOrder": 9,
                                "bbox": {"x": 10, "y": 100, "w": 80, "h": 18},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    validation_root = pdf_root / "validation"
    validation_root.mkdir(parents=True, exist_ok=True)
    (validation_root / "launch_report_one.validation.json").write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "status": "verified",
                        "claim_family": "bundle_metric",
                        "claim_text": "Red + High Shine | 24% (11 products) | 11% (Rest)",
                        "slide_number": 1,
                        "page_number": 1,
                        "source_kind": "table_row",
                        "block_id": "group-2",
                        "block_type": "table",
                    },
                    {
                        "status": "verified",
                        "claim_family": "bundle_metric",
                        "claim_text": "Wine + Stick | 24% (11 products) | 13% (Rest)",
                        "slide_number": 1,
                        "page_number": 1,
                        "source_kind": "table_row",
                        "block_id": "group-2",
                        "block_type": "table",
                    },
                ],
                "unresolved": [],
                "non_claims": [],
                "mapping_issues": [],
            }
        ),
        encoding="utf-8",
    )

    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/reports/pdf/launch_report_one/validation-layer"
                "?lang=en&page=1",
                follow_redirects=False,
            )
        assert response.status_code == 200
        payload = response.json()
        texts = {item["text"]: item for item in payload["items"]}
        assert "Red + High Shine | 24% (11 products) | 11% (Rest)" in texts
        reconstructed = texts["Red + High Shine | 24% (11 products) | 11% (Rest)"]
        assert reconstructed["state"] == "sure"
        assert reconstructed["source_kind"] == "table_row"
        assert reconstructed["bbox"] == {
            "x": 10.0,
            "y": 30.0,
            "w": 170.0,
            "h": 10.0,
        }
        assert reconstructed["source_block_ids"] == [
            "block-13",
            "block-14",
            "block-15",
        ]
        assert "Wine + Stick | 24% (11 products) | 13% (Rest)" in texts
        assert "Attribute Bundle" not in texts
        assert "Recent (%)" not in texts
        assert "Rest (%)" not in texts
        assert "Red + High Shine" not in texts
        assert "Wine + Stick" not in texts
        assert "24% (11 products)" not in texts
        assert "11% (Rest)" not in texts
        assert "13% (Rest)" not in texts
        assert payload["summary"]["sure"] == 2
        assert payload["summary"]["unknown"] == 1
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_launch_report_validation_layer_uses_structured_table_model_rows(
    tmp_path: Path,
) -> None:
    import modules.projects.api as projects_api

    pdf_root = tmp_path / "launch_reports"
    reading_root = pdf_root / ".launch_report_reading_cache" / "launch_report_one"
    reading_root.mkdir(parents=True, exist_ok=True)
    (reading_root / "slide_analysis.json").write_text(
        json.dumps(
            {
                "slides": [
                    {
                        "slideNumber": 1,
                        "blocks": [
                            {
                                "blockId": "block-table",
                                "type": "table",
                                "detectedType": "table",
                                "text": (
                                    "Category Lane\nDominant Attributes\nMarket Signal\n"
                                    "Primary Lane\nMatte\n40%\nSecondary Lane\nGlow\n12%"
                                ),
                                "readingOrder": 0,
                                "bbox": {"x": 10, "y": 20, "w": 180, "h": 90},
                                "confidence": 0.92,
                                "auditStatus": "ok",
                                "tableModel": {
                                    "row_count": 3,
                                    "column_count": 3,
                                    "header_rows": 1,
                                    "rows": [
                                        {
                                            "cells": [
                                                {"text": "Category Lane"},
                                                {"text": "Dominant Attributes"},
                                                {"text": "Market Signal"},
                                            ]
                                        },
                                        {
                                            "cells": [
                                                {"text": "Primary Lane"},
                                                {"text": "Matte"},
                                                {"text": "40%"},
                                            ]
                                        },
                                        {
                                            "cells": [
                                                {"text": "Secondary Lane"},
                                                {"text": "Glow"},
                                                {"text": "12%"},
                                            ]
                                        },
                                    ],
                                },
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    validation_root = pdf_root / "validation"
    validation_root.mkdir(parents=True, exist_ok=True)
    (validation_root / "launch_report_one.validation.json").write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "status": "verified",
                        "claim_family": "bundle_metric",
                        "claim_text": (
                            "Primary Lane: Dominant Attributes Matte; "
                            "Market Signal 40%"
                        ),
                        "slide_number": 1,
                        "page_number": 1,
                        "source_kind": "table_row",
                        "block_id": "block-table",
                    }
                ],
                "unresolved": [
                    {
                        "status": "unresolved",
                        "claim_family": "unclassified",
                        "claim_text": (
                            "Secondary Lane: Dominant Attributes Glow; "
                            "Market Signal 12%"
                        ),
                        "slide_number": 1,
                        "page_number": 1,
                        "source_kind": "table_row",
                        "block_id": "block-table",
                    }
                ],
                "non_claims": [],
                "mapping_issues": [],
            }
        ),
        encoding="utf-8",
    )

    document = projects_api.PdfDocument(
        doc_id="launch_report_one",
        title="Launch Report One",
        path=pdf_root / "launch_report_one.pdf",
    )
    payload = projects_api._build_launch_report_validation_layer_payload(
        document,
        page=1,
        pdf_root=pdf_root,
    )

    texts = {item["text"]: item for item in payload["items"]}
    primary_text = "Primary Lane: Dominant Attributes Matte; Market Signal 40%"
    secondary_text = "Secondary Lane: Dominant Attributes Glow; Market Signal 12%"
    assert texts[primary_text]["state"] == "sure"
    assert texts[primary_text]["bbox"] == {
        "x": 10.0,
        "y": 50.0,
        "w": 180.0,
        "h": 30.0,
    }
    assert texts[secondary_text]["state"] == "unknown"
    assert texts[secondary_text]["state_label"] == "Unresolved"
    assert payload["summary"]["sure"] == 1
    assert payload["summary"]["unknown"] == 1
    assert len(payload["items"]) == 2


def test_launch_report_validation_layer_summary_counts_full_document(
    tmp_path: Path,
) -> None:
    import modules.projects.api as projects_api

    pdf_root = tmp_path / "launch_reports"
    reading_root = pdf_root / ".launch_report_reading_cache" / "launch_report_one"
    reading_root.mkdir(parents=True, exist_ok=True)
    (reading_root / "slide_analysis.json").write_text(
        json.dumps(
            {
                "slides": [
                    {
                        "slideNumber": 1,
                        "blocks": [
                            {
                                "blockId": "block-1",
                                "type": "bullet_item",
                                "detectedType": "text",
                                "text": "Matte share is 40%",
                                "readingOrder": 0,
                                "bbox": {"x": 10, "y": 20, "w": 100, "h": 20},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            }
                        ],
                    },
                    {
                        "slideNumber": 2,
                        "blocks": [
                            {
                                "blockId": "block-2",
                                "type": "bullet_item",
                                "detectedType": "text",
                                "text": "Glow is structurally emerging",
                                "readingOrder": 0,
                                "bbox": {"x": 10, "y": 20, "w": 100, "h": 20},
                                "confidence": 0.95,
                                "auditStatus": "ok",
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    validation_root = pdf_root / "validation"
    validation_root.mkdir(parents=True, exist_ok=True)
    (validation_root / "launch_report_one.validation.json").write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "status": "verified",
                        "claim_family": "bundle_metric",
                        "claim_text": "Matte share is 40%",
                        "slide_number": 1,
                        "page_number": 1,
                        "source_kind": "bullet",
                        "block_id": "block-1",
                    }
                ],
                "unresolved": [
                    {
                        "status": "unresolved",
                        "claim_family": "unclassified",
                        "claim_text": "Glow is structurally emerging",
                        "slide_number": 2,
                        "page_number": 2,
                        "source_kind": "bullet",
                        "block_id": "block-2",
                    }
                ],
                "non_claims": [],
                "mapping_issues": [],
            }
        ),
        encoding="utf-8",
    )

    document = projects_api.PdfDocument(
        doc_id="launch_report_one",
        title="Launch Report One",
        path=pdf_root / "launch_report_one.pdf",
    )
    payload = projects_api._build_launch_report_validation_layer_payload(
        document,
        page=1,
        pdf_root=pdf_root,
    )

    assert len(payload["items"]) == 1
    assert payload["items"][0]["text"] == "Matte share is 40%"
    assert payload["page_summary"]["sure"] == 1
    assert payload["page_summary"]["unknown"] == 0
    assert payload["summary"]["sure"] == 1
    assert payload["summary"]["unknown"] == 1
    assert payload["document_summary"] == payload["summary"]


def test_launch_report_podcast_route_returns_inline_audio(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_launch_report_viewer_environment(
        monkeypatch,
        tmp_path,
        include_document=False,
        include_podcast=True,
    )
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/reports/pdf/launch_report_one/podcast?lang=en",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/mp4")
        assert response.headers["content-disposition"].startswith("inline;")
        assert response.content == b"podcast-bytes"
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_launch_report_video_route_returns_inline_video(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_launch_report_viewer_environment(
        monkeypatch,
        tmp_path,
        include_document=False,
        include_podcast=False,
        include_video=True,
    )
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/reports/pdf/launch_report_one/video?lang=en",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("video/mp4")
        assert response.headers["content-disposition"].startswith("inline;")
        assert response.content == b"video-bytes"
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_launch_report_video_route_supports_byte_ranges(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    presentation_permissions = _configure_launch_report_viewer_environment(
        monkeypatch,
        tmp_path,
        include_document=False,
        include_podcast=False,
        include_video=True,
    )
    try:
        with _authenticated_client(
            monkeypatch, email=AUTHORIZED_EMAIL
        ) as allowed_client:
            response = allowed_client.get(
                "/review/reports/pdf/launch_report_one/video?lang=en",
                headers={"Range": "bytes=0-4"},
                follow_redirects=False,
            )
        assert response.status_code == 206
        assert response.headers["content-type"].startswith("video/mp4")
        assert response.headers["accept-ranges"] == "bytes"
        assert response.headers["content-range"] == "bytes 0-4/11"
        assert response.content == b"video"
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        presentation_permissions._load_launch_report_permissions.cache_clear()


def test_pdf_viewer_suppresses_media_context_menu() -> None:
    template_path = Path("templates/pdf_viewer.html")

    template_text = template_path.read_text(encoding="utf-8")

    assert 'controlsList="nodownload"' in template_text
    assert "pdf-viewer__ai-disclaimer" in template_text
    assert "ai_accuracy_disclaimer" in template_text
    assert "function suppressContextMenu(element)" in template_text
    assert (
        "[image, podcastPlayer, videoPlayer].forEach(suppressContextMenu)"
        in template_text
    )
    assert "-webkit-touch-callout: none;" in template_text
