from __future__ import annotations

import base64
import csv
import hashlib
import html
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from datetime import date
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)
from urllib.parse import parse_qs, urlencode, urlparse

import polars as pl
import requests
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)

try:  # pragma: no cover - optional dependency during tests
    from fastapi.templating import Jinja2Templates
except Exception:  # noqa: BLE001
    Jinja2Templates = None  # type: ignore[misc,assignment]
import plotly.graph_objects as go
import plotly.io as pio
from fastapi.staticfiles import StaticFiles
from plotly.colors import qualitative as qual
from plotly.subplots import make_subplots
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from modules.add_attributes.attribute_taxonomy import get_attribute_taxonomy

try:  # pragma: no cover - optional scrape fallback
    from modules.add_attributes.pdp_attribute_export import (
        _fetch_parent_hero_url as _fetch_remote_parent_hero,
    )
except Exception:  # pragma: no cover - runtime fallback
    _fetch_remote_parent_hero = None
from modules.add_attributes.pdp_attribute_export import (
    _merge_attribute_values,
)
from modules.auth.api import router as auth_router
from modules.auth.api import site_router as auth_site_router
from modules.auth.config import get_auth_config
from modules.auth.dependencies import (
    get_allowed_page_keys_for_email,
    get_permission_key_for_path,
    get_site_permissions,
    maybe_current_user,
    require_authenticated_user,
    require_authenticated_user_for_site,
    require_site_permission_for_request,
)
from modules.auth.session import AuthenticatedUser
from modules.case_notes_voice.api import router as case_notes_voice_router
from modules.case_notes_voice.api import site_router as case_notes_voice_site_router
from modules.case_notes_voice.api import (
    start_voice_retention_cleanup,
    stop_voice_retention_cleanup,
)
from modules.change_requests import router as change_requests_router
from modules.charting import plot_horizontal_bar
from modules.check_entries.api import router as check_router
from modules.check_entries.api import site_router as check_site_router
from modules.hierarchy_fix.api import router as hierarchy_router
from modules.hierarchy_fix.api import site_router as hierarchy_site_router
from modules.hosted_interviews.api import admin_router as hosted_interviews_admin_router
from modules.hosted_interviews.api import (
    public_router as hosted_interviews_public_router,
)
from modules.hosted_interviews.api import site_router as hosted_interviews_site_router
from modules.identify_columns.api import router as identify_columns_router
from modules.llm.llm_call_wrapper import LLMCallWrapper
from modules.notifications.notifier import (
    notify_failed,
    notify_finished,
    process_pending_notifications,
)
from modules.pdp import attribute_resolution_history
from modules.pdp.attribute_mapping_paths import get_attribute_mapping_dir
from modules.pdp.attribute_reporting_api import router as attribute_reporting_router
from modules.pdp.attribute_review_logic import (
    PlaceholderValues,
    ReviewTables,
    apply_attribute_filters,
    build_category_lookup,
    category_options_for_tables,
    compute_attribute_coverage_report,
    ensure_record_identifiers,
    filter_tables_by_brands,
    filter_tables_by_categories,
    filter_tables_by_retailer,
    list_brands,
    list_retailers,
    load_stage_attribute_table,
    normalize_category_key,
    prepare_attribute_filters,
    repair_text_encoding,
)
from modules.pdp.data_handling_content import get_data_handling_content
from modules.pdp.deterministic_policy_api import router as deterministic_policy_router
from modules.pdp.deterministic_policy_api import (
    site_router as deterministic_policy_site_router,
)
from modules.pdp.explicit_rules_api import router as explicit_rules_router
from modules.pdp.explicit_rules_api import site_router as explicit_rules_site_router
from modules.pdp.hybrid_overlay import annotate_market_hybrid_claims
from modules.pdp.image_cache import (
    DEFAULT_IMAGE_ROOT,
    CachedImage,
    build_image_cache,
    find_local_image,
)
from modules.pdp.language import (
    LANDING_LANGUAGE_LABELS,
    LANGUAGE_LABELS,
    LANGUAGE_ORDER,
    SUPPORTED_LANGUAGES,
    get_navigation_label,
    get_page_copy,
    resolve_language,
)
from modules.pdp.legal_content import get_legal_page
from modules.pdp.postgres_compat import connect_pdp_database, pdp_database_exists
from modules.pdp.review_constants import DEFAULT_PDP_STORE_PATH
from modules.pdp.run_status_notifications import resolve_notification_recipients
from modules.pdp.sales_brief_config import (
    DEFAULT_BRIEF_HIGHLIGHT_COUNT,
    DEFAULT_BRIEF_MAX_FINDINGS,
    DEFAULT_BRIEF_MAX_PER_LENS,
    DEFAULT_DECK_PLAN_MAX_SLIDES,
    SALES_BRIEF_MAX_ATTRIBUTE_DIMENSIONS,
    SALES_BRIEF_MIN_ATTRIBUTE_COVERAGE,
    SALES_BRIEF_MIN_DISTINCT_VALUES,
    SALES_BRIEF_PREFERRED_ATTRIBUTE_IDS,
)
from modules.pdp.sales_dataset_download_permissions import (
    get_sales_dataset_download_permissions,
    is_sales_dataset_download_allowed,
    sales_dataset_download_permissions_configured,
)
from modules.pdp.sales_dataset_paths import (
    get_sales_dataset_name,
    list_available_sales_dataset_names,
)
from modules.pdp.sales_dataset_permissions import (
    get_sales_dataset_permissions,
    is_sales_dataset_allowed,
    sales_dataset_permissions_configured,
)
from modules.pdp.sales_join import (
    build_sales_calendar_and_join,
    compute_category_rollup,
    compute_dimension_shares,
    get_sales_dataset_metadata,
    join_sales_with_attributes,
    load_full_sales_data,
    load_sales_data,
    sales_categories,
)
from modules.pdp.store import PDPStore
from modules.pdp.taxonomy_governance_api import (
    issues_site_router as taxonomy_issues_site_router,
)
from modules.pdp.taxonomy_governance_api import router as taxonomy_governance_router
from modules.pdp.taxonomy_governance_api import (
    site_router as taxonomy_governance_site_router,
)
from modules.projects.api import router as projects_router
from modules.projects.api import site_router as projects_site_router
from modules.slides.api import get_storage as get_slides_storage
from modules.slides.api import is_any_ocr_running
from modules.slides.api import router as slides_router
from modules.slides.api import site_router as slides_site_router
from modules.utilities.cache import get_cache_dir
from modules.utilities.config import get_naming_params
from modules.utilities.json_record_store import JsonTableConnection
from modules.utilities.logging_config import configure_logging
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.utilities.session_cleanup import cleanup_sessions
from modules.utilities.session_context import (
    SessionContext,
    build_session_context,
    get_session_context,
    use_session_context,
)
from modules.utilities.utils import get_row_count, get_schema_and_column_names
from src.slides.loader import find_index_file
from src.slides.notebooklm_style import (
    get_prompt_style_chart_palette,
    load_notebooklm_style,
    resolve_prompt_style_key,
)

load_env_from_secrets_file()

configure_logging("pdp_api")


class RetailerResponse(BaseModel):
    retailers: List[str]
    brands: List[str]


class CategoryItem(BaseModel):
    key: str
    label: str


class CategoryResponse(BaseModel):
    categories: List[CategoryItem]


class SalesDatasetItem(BaseModel):
    key: str
    label: str
    download_allowed: bool = True


class SalesDatasetsResponse(BaseModel):
    selected_dataset: str
    datasets: List[SalesDatasetItem]


class BrandsResponse(BaseModel):
    brands: List[str]


class AttributeOption(BaseModel):
    id: str
    label: str
    column: str
    values: List[str]
    active: bool
    coverage_pct: float = 0.0
    non_placeholder_records: int = 0
    total_records: int = 0
    distinct_non_placeholder_values: int = 0


class AttributeMetadataResponse(BaseModel):
    placeholder_values: List[str]
    attributes: List[AttributeOption]
    price_band_values: List[str] = Field(default_factory=list)
    also_blush_values: List[str] = Field(default_factory=list)
    hybrid_values: Dict[str, List[str]] = Field(default_factory=dict)


class TaxonomyBranchNode(BaseModel):
    label: str
    synonyms: List[str] = Field(default_factory=list)
    depth: int


class TaxonomyBranchResponse(BaseModel):
    attribute_id: str
    attribute_label: str
    nodes: List[TaxonomyBranchNode]


class CoverageAttributeRow(BaseModel):
    id: str
    label: str
    column: str
    total: int
    filled: int
    filled_pct: float
    missing: int
    missing_pct: float
    not_in_taxonomy: int
    not_in_taxonomy_pct: float
    status: Optional[str] = None
    inactive_filled: Optional[int] = None
    inactive_filled_pct: Optional[float] = None
    confidence_support_avg: Optional[float] = None
    confidence_total_avg: Optional[float] = None
    confidence_pct: Optional[float] = None
    confidence_samples: Optional[int] = None


class CoverageCategoryRow(BaseModel):
    category_key: str
    category_label: str
    total: int
    attributes: List[CoverageAttributeRow]


class CoverageReportResponse(BaseModel):
    total_records: int
    source: Optional[str] = None
    attributes: List[CoverageAttributeRow]
    categories: List[CoverageCategoryRow]


class RecordsResponse(BaseModel):
    total: int
    limit: int
    records: List[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]] = None


class SalesMetricRow(BaseModel):
    month: str
    dimensions: Dict[str, Any]
    sales: float
    units: float
    sales_share: float
    units_share: float


class SalesMetricsResponse(BaseModel):
    total_sales: float
    total_units: float
    dimension_headers: List[str]
    rows: List[SalesMetricRow]
    months: List[str]


class SalesBriefAnalysisScopeResponse(BaseModel):
    report_mode: Literal["market_report", "brand_report"]
    dataset: str | None = None
    retailers: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    brands: List[str] = Field(default_factory=list)
    price_bands: List[str] = Field(default_factory=list)
    pareto_classes: List[str] = Field(default_factory=list)
    attribute_filters: Dict[str, List[str]] = Field(default_factory=dict)


class SalesBriefMetricResponse(BaseModel):
    key: str
    label: str
    value: float | None = None
    unit: str
    display_value: str | None = None


class SalesBriefEvidenceOptionResponse(BaseModel):
    chart_key: str
    chart_label: str
    chart_type: str
    chart_id: str | None = None
    chart_request: Dict[str, Any] | None = None


class SalesBriefFindingResponse(BaseModel):
    rank: int
    lens: str
    lens_label: str
    claim: str
    primary_evidence: SalesBriefEvidenceOptionResponse | None = None
    evidence_bullets: List[str] = Field(default_factory=list)
    confidence: str
    caution: str | None = None
    metrics: List[SalesBriefMetricResponse] = Field(default_factory=list)


class SalesBriefSectionResponse(BaseModel):
    lens: str
    title: str
    findings: List[SalesBriefFindingResponse] = Field(default_factory=list)


class SalesBriefArtifactResponse(BaseModel):
    title: str
    scope: str
    analysis_scope: SalesBriefAnalysisScopeResponse
    attribute_dimensions: List[str] = Field(default_factory=list)
    highlights: List[str] = Field(default_factory=list)
    sections: List[SalesBriefSectionResponse] = Field(default_factory=list)


class ChartResponse(BaseModel):
    chart_type: str
    figure: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    chart_id: str | None = None


def _build_external_base_url(
    request: Request,
    *,
    base_env_var: str = "",
) -> str:
    base_env = os.getenv(base_env_var, "").strip() if base_env_var else ""
    base = base_env.rstrip("/") if base_env else ""
    if not base:
        origin = str(request.headers.get("origin", "") or "").strip()
        if origin:
            parsed_origin = urlparse(origin)
            if parsed_origin.scheme and parsed_origin.netloc:
                base = f"{parsed_origin.scheme}://{parsed_origin.netloc}"
    if not base:
        referer = str(request.headers.get("referer", "") or "").strip()
        if referer:
            parsed_referer = urlparse(referer)
            if parsed_referer.scheme and parsed_referer.netloc:
                base = f"{parsed_referer.scheme}://{parsed_referer.netloc}"
    if not base:
        forwarded_host = str(request.headers.get("x-forwarded-host", "") or "").strip()
        if forwarded_host:
            forwarded_proto = (
                str(request.headers.get("x-forwarded-proto", request.url.scheme) or "")
                .split(",")[0]
                .strip()
            )
            host = forwarded_host.split(",")[0].strip()
            if host:
                scheme = forwarded_proto or request.url.scheme
                base = f"{scheme}://{host}"
    if not base:
        base = str(request.base_url).rstrip("/")
    return base


PALETTE_MAP: Dict[str, List[str]] = {
    "pastel": [
        "#aec7e8",
        "#ffbb78",
        "#98df8a",
        "#ff9896",
        "#c5b0d5",
        "#c49c94",
        "#f7b6d2",
        "#c7c7c7",
        "#dbdb8d",
        "#9edae5",
    ],
    "bold": [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
    ],
    "muted": [
        "#4b5563",
        "#9ca3af",
        "#6b7280",
        "#d1d5db",
        "#94a3b8",
        "#cbd5e1",
        "#c4b5fd",
        "#fbbf24",
        "#fb7185",
        "#22d3ee",
    ],
    "cirque": ["#343434", "#4E6551", "#88A98C", "#4395A7", "#0F4E59", "#5A3C4B"],
    "modern": ["#343434", "#3C511B", "#83905A", "#7C982E", "#C7EA5B", "#854210"],
    "blueGreen": ["#343434", "#1B3643", "#3B5C68", "#597F8E", "#7BA3AE", "#ACD5E5"],
    "khakiDenim": ["#343434", "#2E2A18", "#47462E", "#777A4E", "#AFB178", "#e7e9c9"],
    "polo": [
        "#343434",
        "#506B4E",
        "#71917C",
        "#685F4D",
        "#A48C73",
        "#2D4343",
        "#EFC84E",
        "#BA8F2A",
        "#CD685C",
        "#923620",
        "#5F838C",
        "#4F5971",
    ],
    "heatingUp": [
        "#245a58",
        "#409781",
        "#F3854D",
        "#08425A",
        "#2A7D9B",
        "#BFD83E",
        "#52C4D8",
        "#FFB93F",
        "#a5e0eb",
        "#dcf313",
        "#67BB48",
    ],
    "tableau": [
        "#343434",
        "#5778a4",
        "#e49444",
        "#79706e",
        "#85b6b2",
        "#d4a6c8",
        "#e7ca60",
        "#a87c9f",
        "#f1a2a9",
        "#967662",
        "#b8b0ac",
        "#9ecae9",
    ],
    "thinkcell": [
        "#343434",
        "#6da900",
        "#2c4863",
        "#787675",
        "#9FC95C",
        "#4f7403",
        "#034f7e",
        "#00776f",
        "#343434",
        "#c0c2c1",
        "#708cb5",
        "#9cb1cc",
    ],
    "powerbi": [
        "#343434",
        "#12239E",
        "#E66C37",
        "#6B007B",
        "#E044A7",
        "#4b3231",
        "#744EC2",
        "#D9B300",
        "#D64550",
        "#eddeff",
        "#bfe4ed",
        "#FE6DB6",
    ],
    "symphony": [
        "#343434",
        "#2159D6",
        "#2A4870",
        "#3FA9F5",
        "#303442",
        "#CCCCCC",
        "#FF3F72",
        "#7C42CE",
        "#F7931E",
        "#AF4141",
        "#A499B3",
        "#FFE100",
    ],
    "ibcs": [
        "#343434",
        "#808080",
        "#FF7900",
        "#AA8C00",
        "#FF008C",
        "#b35500",
        "#9f7692",
        "#5e4d00",
        "#b30062",
        "#514d89",
        "#ddb600",
        "#dbacb0",
    ],
    "bain": [
        "#343434",
        "#999A9A",
        "#818284",
        "#58585A",
        "#95A7B6",
        "#748B9E",
        "#506E86",
        "#B86D9B",
        "#A43D7A",
        "#891D59",
        "#AB8933",
        "#E9CD49",
    ],
    "mckinsey": [
        "#002960",
        "#868685",
        "#0065bd",
        "#b5b38c",
        "#009aa6",
        "#939d98",
        "#006983",
        "#7d9aaa",
        "#D4ba00",
        "#ad005b",
        "#66307c",
    ],
    "bcg": [
        "#00291C",
        "#337B68",
        "#025645",
        "#BDD9CD",
        "#D9B95B",
        "#E6B437",
        "#808080",
        "#B3B3B3",
        "#4D4D4D",
        "#0076B8",
        "#ADC0D7",
    ],
    "occ": [
        "#0053A1",
        "#A7A9AC",
        "#01B09C",
        "#52C9E9",
        "#BAD531",
        "#7A3F97",
        "#B9AD99",
        "#E86C5D",
        "#FFB25A",
        "#666668",
        "#B9E6DC",
    ],
    "deloitte": [
        "#1B6D77",
        "#00ABAB",
        "#43B02A",
        "#86BC25",
        "#C4D600",
        "#7F897E",
        "#ECF1B9",
        "#80D5D5",
        "#95a300",
        "#D0D0CE",
        "#6e7743",
    ],
    "greys": [
        "#bdbdbd",
        "#2F5574",
        "#969696",
        "#506D85",
        "#737373",
        "#738A9D",
        "#999999",
        "#96A7B6",
        "#666666",
        "#B9C5CE",
    ],
    "blues": [
        "#084594",
        "#c6dbef",
        "#2171b5",
        "#9ecae1",
        "#4292c6",
        "#CDE9FE",
        "#6baed6",
        "#B3F5FF",
        "#008DA6",
        "#ECF6FD",
        "#506D85",
    ],
    "oranges": [
        "#8c2d04",
        "#fdd0a2",
        "#d94801",
        "#fdae6b",
        "#f16913",
        "#fd8d3c",
        "#CA6602",
        "#FEEC9A",
        "#F59B00",
        "#FFE785",
        "#FFCD00",
    ],
    "purples": [
        "#4a1486",
        "#dadaeb",
        "#6a51a3",
        "#bcbddc",
        "#807dba",
        "#9e9ac8",
        "#403294",
        "#C0B6F2",
        "#5243AA",
        "#998DD9",
        "#6554C0",
    ],
    "browns": [
        "#660000",
        "#CC6633",
        "#663300",
        "#CC9933",
        "#996600",
        "#996666",
        "#8A0F0F",
        "#E16666",
        "#CA6602",
        "#FFCD00",
        "#F59B00",
    ],
}


def _resolve_palette(name: Optional[str]) -> List[str]:
    if name:
        key = name.strip()
        if key in PALETTE_MAP:
            return PALETTE_MAP[key]
    return list(qual.Pastel)


class StageTableResponse(BaseModel):
    table: str
    count: int
    records: List[Dict[str, Any]]


class HealthResponse(BaseModel):
    status: str = Field(default="ok")


_CACHE_STATE: Optional[dict] = None
_POSTFILL_TABLES_STATE: Optional[dict] = None
_COVERAGE_TABLES_STATE: Optional[dict] = None
_IMAGE_CACHE: Optional[Dict[str, List[CachedImage]]] = None
_REMOTE_IMAGE_ROOT = DEFAULT_IMAGE_ROOT / "__remote_cache" / "images"
_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9]+")
templates = Jinja2Templates(directory="templates") if Jinja2Templates else None
LOGGER = logging.getLogger(__name__)
SESSION_RETENTION_HOURS = 168  # seven days
SESSION_CLEANUP_INTERVAL_SECONDS = 24 * 3600  # run daily
_SESSION_CLEANUP_STOP = threading.Event()
_SESSION_CLEANUP_THREAD: Optional[threading.Thread] = None

APP_ROOT = Path(__file__).resolve().parents[2]
_MAPPING_DIR = get_attribute_mapping_dir()
_POSTFILL_ATTRIBUTE_CACHE_DIR = _MAPPING_DIR / "postfill_attribute_cache"
_WEB_FILL_AUDIT_CSV = _MAPPING_DIR / "attribute_web_fill_audit.csv"
_VISION_FILL_AUDIT_CSV = _MAPPING_DIR / "attribute_vision_fill_audit.csv"
_MIN_PROMOTION_SUPPORT_RUNS = max(
    int(getattr(attribute_resolution_history, "_MIN_SURE_SUPPORT_RUNS", 3)),
    1,
)


def _forbidden_message(detail: Any) -> str:
    if isinstance(detail, dict):
        message = detail.get("message")
        email = detail.get("email")
        if isinstance(message, str) and message.strip():
            if isinstance(email, str) and email.strip():
                return f"{message.strip()} (signed in as {email.strip()})"
            return message
    if isinstance(detail, str) and detail.strip():
        return detail
    return "You are not authorized to see this page. Please contact fabio@mparanza.com."


def _request_prefers_html(request: Request) -> bool:
    if request.method not in {"GET", "HEAD"}:
        return False
    accept_header = request.headers.get("accept", "")
    if not accept_header:
        return False
    media_types = {
        item.split(";", 1)[0].strip().lower()
        for item in accept_header.split(",")
        if item.strip()
    }
    return "text/html" in media_types or "application/xhtml+xml" in media_types


def _not_found_destination(path: str, lang: str) -> tuple[str, str]:
    destinations = (
        ("/review/brand-reports", "/review/brand-reports/page"),
        ("/review/reports", "/review/reports/page"),
        ("/review/product-hypotheses", "/review/product-hypotheses/page"),
        ("/presentations", "/presentations/page"),
        ("/slides", "/slides/page"),
    )
    for path_prefix, destination_path in destinations:
        if path.startswith(path_prefix):
            label = get_navigation_label(lang, destination_path) or "Open library"
            return f"{destination_path}?lang={lang}", label
    return f"/?lang={lang}", "Return home"


def _not_found_context(request: Request, detail: Any) -> Dict[str, Any]:
    _ = detail
    lang = request.query_params.get("lang") or resolve_language(request)
    primary_href, primary_label = _not_found_destination(request.url.path, lang)
    message = "The page may have moved, been deleted, or the URL may be incomplete."
    return {
        "request": request,
        "lang": lang,
        "requested_path": request.url.path,
        "primary_href": primary_href,
        "primary_label": primary_label,
        "message": message,
    }


def _run_session_cleanup() -> None:
    try:
        removed, scanned = cleanup_sessions(
            SESSION_RETENTION_HOURS,
            dry_run=False,
            logger=LOGGER,
        )
        LOGGER.info(
            "Session cleanup scanned %s artifacts and removed %s stale sessions",
            scanned,
            removed,
        )
    except Exception:
        LOGGER.exception("Session cleanup failed")


def _session_cleanup_loop() -> None:
    LOGGER.info(
        "Session cleanup worker started (interval=%sh, retention=%sh)",
        SESSION_CLEANUP_INTERVAL_SECONDS / 3600,
        SESSION_RETENTION_HOURS,
    )
    while not _SESSION_CLEANUP_STOP.is_set():
        _run_session_cleanup()
        if _SESSION_CLEANUP_STOP.wait(SESSION_CLEANUP_INTERVAL_SECONDS):
            break
    LOGGER.info("Session cleanup worker stopped")


def _start_session_cleanup() -> None:
    global _SESSION_CLEANUP_THREAD
    if _SESSION_CLEANUP_THREAD and _SESSION_CLEANUP_THREAD.is_alive():
        return
    _SESSION_CLEANUP_STOP.clear()
    _SESSION_CLEANUP_THREAD = threading.Thread(
        target=_session_cleanup_loop,
        name="session-cleanup-worker",
        daemon=True,
    )
    _SESSION_CLEANUP_THREAD.start()


def _stop_session_cleanup() -> None:
    _SESSION_CLEANUP_STOP.set()
    thread = _SESSION_CLEANUP_THREAD
    if thread and thread.is_alive():
        thread.join(timeout=5)


def _parse_price_to_float(value: object | None) -> float | None:
    """Best-effort price parser for price_band calculation."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    cleaned = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _compute_price_bands(
    tables: ReviewTables, normalized_keys: list[str]
) -> pl.DataFrame:
    variants = tables.variants
    category_col = None
    if "category_key" in variants.columns:
        category_col = "category_key"
    elif "category_label" in variants.columns:
        category_col = "category_label"
    if (
        variants.is_empty()
        or "price_raw" not in variants.columns
        or "variant_id" not in variants.columns
        or category_col is None
    ):
        return pl.DataFrame()

    price_df = variants.with_columns(
        pl.col("variant_id").cast(pl.Utf8).str.strip_chars().alias("variant_id_norm"),
        pl.col("price_raw")
        .map_elements(_parse_price_to_float, return_dtype=pl.Float64)
        .alias("price_numeric"),
        pl.col(category_col)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_lowercase()
        .alias("category_norm"),
    )
    if normalized_keys:
        price_df = price_df.filter(pl.col("category_norm").is_in(normalized_keys))
    price_df = price_df.drop_nulls(subset=["price_numeric"])
    if price_df.is_empty():
        return pl.DataFrame()

    series = price_df.get_column("price_numeric")
    try:
        low = float(series.quantile(0.35, interpolation="nearest"))
        high = float(series.quantile(0.85, interpolation="nearest"))
    except Exception:
        return pl.DataFrame()

    price_df = price_df.with_columns(
        pl.when(pl.col("price_numeric") > high)
        .then(pl.lit("premium"))
        .when(pl.col("price_numeric") < low)
        .then(pl.lit("value"))
        .otherwise(pl.lit("mid"))
        .alias("price_band"),
    )

    return price_df.select("variant_id_norm", "price_band")


def _filter_sales_frame(
    frame: pl.DataFrame,
    *,
    retailers: Sequence[str],
    category_labels: Sequence[str],
    brands: Sequence[str],
) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    df = frame
    retailers_norm = [str(r).strip().lower() for r in retailers if str(r).strip()]
    if retailers_norm and "merchant" in df.columns:
        df = df.filter(
            pl.col("merchant").cast(pl.Utf8).str.to_lowercase().is_in(retailers_norm)
        )
    categories_norm = [
        str(c).strip().lower() for c in category_labels if str(c).strip()
    ]
    if categories_norm and "category" in df.columns:
        df = df.filter(
            pl.col("category").cast(pl.Utf8).str.to_lowercase().is_in(categories_norm)
        )
    brands_norm = [str(b).strip().lower() for b in brands if str(b).strip()]
    if brands_norm and "brand" in df.columns:
        df = df.filter(
            pl.col("brand").cast(pl.Utf8).str.to_lowercase().is_in(brands_norm)
        )
    return df


def _overlay_sales_category_with_catalog_labels(
    sales_frame: pl.DataFrame,
    *,
    variants: pl.DataFrame,
) -> pl.DataFrame:
    """Use catalog-derived category labels when available (left join on SKU)."""
    if sales_frame.is_empty() or variants.is_empty():
        return sales_frame
    if not {"sku", "category"}.issubset(set(sales_frame.columns)):
        return sales_frame
    if not {"variant_id", "category_label"}.issubset(set(variants.columns)):
        return sales_frame

    lookup_cols: list[pl.Expr] = [
        pl.col("variant_id").cast(pl.Utf8).str.strip_chars().alias("variant_id_norm"),
        pl.col("category_label")
        .cast(pl.Utf8)
        .str.strip_chars()
        .alias("category_label_norm"),
    ]
    has_retailer = "retailer" in variants.columns and "merchant" in sales_frame.columns
    if has_retailer:
        lookup_cols.insert(
            0,
            pl.col("retailer")
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("retailer_norm"),
        )

    lookup = variants.select(lookup_cols).drop_nulls(
        subset=["variant_id_norm", "category_label_norm"]
    )
    lookup = lookup.unique(
        subset=(
            ["retailer_norm", "variant_id_norm"]
            if has_retailer
            else ["variant_id_norm"]
        )
    )
    if lookup.is_empty():
        return sales_frame

    join_left = ["variant_id_norm"]
    join_right = ["variant_id_norm"]
    sales_exprs: list[pl.Expr] = [
        pl.col("sku").cast(pl.Utf8).str.strip_chars().alias("variant_id_norm")
    ]
    drop_cols = {"variant_id_norm", "category_label_norm"}
    if has_retailer:
        join_left = ["merchant_norm", "variant_id_norm"]
        join_right = ["retailer_norm", "variant_id_norm"]
        sales_exprs.insert(
            0,
            pl.col("merchant")
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("merchant_norm"),
        )
        drop_cols.update({"merchant_norm", "retailer_norm"})

    joined = sales_frame.with_columns(sales_exprs).join(
        lookup,
        left_on=join_left,
        right_on=join_right,
        how="left",
    )
    joined = joined.with_columns(
        pl.coalesce(
            [
                pl.col("category_label_norm"),
                pl.col("category").cast(pl.Utf8).str.strip_chars(),
            ]
        ).alias("category")
    )
    drop_existing = sorted(col for col in drop_cols if col in joined.columns)
    if drop_existing:
        joined = joined.drop(drop_existing)
    return joined


def _compute_sales_price_bands(
    sales_frame: pl.DataFrame,
    *,
    retailers: Sequence[str],
    category_labels: Sequence[str],
    brands: Sequence[str],
) -> pl.DataFrame:
    """Compute premium/mid/value price bands on the full sales slice (not PDP coverage)."""
    sales_slice = _filter_sales_frame(
        sales_frame,
        retailers=retailers,
        category_labels=category_labels,
        brands=brands,
    )
    if sales_slice.is_empty() or "sku" not in sales_slice.columns:
        return pl.DataFrame()

    sku_col = pl.col("sku").cast(pl.Utf8).str.strip_chars().alias("variant_id_norm")

    if "price" in sales_slice.columns:
        price_values = (
            sales_slice.with_columns(
                sku_col,
                pl.col("price")
                .map_elements(_parse_price_to_float, return_dtype=pl.Float64)
                .alias("price_value"),
            )
            .drop_nulls(subset=["price_value"])
            .group_by("variant_id_norm")
            .agg(pl.col("price_value").median().alias("price_value"))
        )
    elif {"sales", "units"}.issubset(set(sales_slice.columns)):
        price_values = (
            sales_slice.with_columns(sku_col)
            .group_by("variant_id_norm")
            .agg(
                pl.col("sales").sum().alias("sales_total"),
                pl.col("units").sum().alias("units_total"),
            )
            .with_columns(
                pl.when(pl.col("units_total") > 0)
                .then(pl.col("sales_total") / pl.col("units_total"))
                .otherwise(None)
                .alias("price_value")
            )
            .drop_nulls(subset=["price_value"])
            .drop(["sales_total", "units_total"])
        )
    else:
        return pl.DataFrame()

    if price_values.is_empty() or "price_value" not in price_values.columns:
        return pl.DataFrame()

    series = price_values.get_column("price_value")
    try:
        low = float(series.quantile(0.35, interpolation="nearest"))
        high = float(series.quantile(0.85, interpolation="nearest"))
    except Exception:
        return pl.DataFrame()

    return price_values.with_columns(
        pl.when(pl.col("price_value") > high)
        .then(pl.lit("premium"))
        .when(pl.col("price_value") < low)
        .then(pl.lit("value"))
        .otherwise(pl.lit("mid"))
        .alias("price_band")
    ).select("variant_id_norm", "price_band")


def _compute_sales_pareto_classes(
    sales_frame: pl.DataFrame,
    *,
    retailers: Sequence[str],
    category_labels: Sequence[str],
    brands: Sequence[str],
) -> pl.DataFrame:
    """Compute A/B/C pareto classes on the full sales slice (not PDP coverage)."""
    sales_slice = _filter_sales_frame(
        sales_frame,
        retailers=retailers,
        category_labels=category_labels,
        brands=brands,
    )
    if sales_slice.is_empty() or not {"sku", "sales"}.issubset(
        set(sales_slice.columns)
    ):
        return pl.DataFrame()

    totals = (
        sales_slice.select(
            pl.col("sku").cast(pl.Utf8).str.strip_chars().alias("variant_id_norm"),
            pl.col("sales").cast(pl.Float64).alias("sales"),
        )
        .group_by("variant_id_norm")
        .agg(pl.col("sales").sum().alias("sales_total"))
        .sort("sales_total", descending=True)
    )
    if totals.is_empty():
        return pl.DataFrame()
    total_sales = float(totals.get_column("sales_total").sum() or 0.0)
    if total_sales <= 0:
        return pl.DataFrame()

    cum_share = pl.col("sales_total").cum_sum() / pl.lit(total_sales)
    return totals.with_columns(
        pl.when(cum_share <= 0.80 + 1e-9)
        .then(pl.lit("A"))
        .when(cum_share <= 0.95 + 1e-9)
        .then(pl.lit("B"))
        .otherwise(pl.lit("C"))
        .alias("pareto_class"),
    ).select("variant_id_norm", "pareto_class")


def _cache_to_tables(cache: dict | None) -> ReviewTables:
    if not cache:
        return ReviewTables(
            parents=pl.DataFrame(),
            variants=pl.DataFrame(),
            combined=pl.DataFrame(),
            parents_all=pl.DataFrame(),
        )
    return ReviewTables(
        parents=cache.get("parents", pl.DataFrame()),
        variants=cache.get("variants", pl.DataFrame()),
        combined=cache.get("combined", pl.DataFrame()),
        parents_all=cache.get("parents_all", pl.DataFrame()),
    )


def _get_tables() -> ReviewTables:
    tables = _load_postfill_review_tables()
    if tables is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Post-fill attribute cache is required but was not found. "
                f"Expected parquet files in '{_POSTFILL_ATTRIBUTE_CACHE_DIR}'. "
                "Run the current PDP attribute export flow to generate shared attributes."
            ),
        )
    return tables


def _build_postfill_combined_table(
    parents_df: pl.DataFrame, variants_df: pl.DataFrame
) -> pl.DataFrame:
    parent_id_expr = (
        pl.col("parent_product_id")
        if "parent_product_id" in parents_df.columns
        else pl.lit("")
    )
    parent_rows = parents_df.with_columns(
        pl.lit("parent").alias("record_type"),
        parent_id_expr.cast(pl.Utf8).alias("product"),
        pl.lit("").alias("variant"),
    )

    variant_parent_expr = (
        pl.col("parent_product_id")
        if "parent_product_id" in variants_df.columns
        else pl.lit("")
    )
    variant_id_expr = (
        pl.col("variant_id") if "variant_id" in variants_df.columns else pl.lit("")
    )
    variant_rows = variants_df.with_columns(
        pl.lit("variant").alias("record_type"),
        variant_parent_expr.cast(pl.Utf8).alias("product"),
        variant_id_expr.cast(pl.Utf8).alias("variant"),
    )
    return pl.concat([parent_rows, variant_rows], how="diagonal_relaxed")


def _load_postfill_review_tables() -> ReviewTables | None:
    global _POSTFILL_TABLES_STATE

    parents_path = _POSTFILL_ATTRIBUTE_CACHE_DIR / "parents.parquet"
    variants_path = _POSTFILL_ATTRIBUTE_CACHE_DIR / "variants.parquet"
    if not (parents_path.exists() and variants_path.exists()):
        return None

    combined_path = _POSTFILL_ATTRIBUTE_CACHE_DIR / "combined.parquet"
    parents_all_path = _POSTFILL_ATTRIBUTE_CACHE_DIR / "parents_all.parquet"
    candidates = [parents_path, variants_path, combined_path, parents_all_path]
    signature: tuple[tuple[str, float, int], ...] = tuple(
        (str(path), path.stat().st_mtime, path.stat().st_size)
        for path in candidates
        if path.exists()
    )
    if _POSTFILL_TABLES_STATE and _POSTFILL_TABLES_STATE.get("signature") == signature:
        cached = _POSTFILL_TABLES_STATE.get("tables")
        if isinstance(cached, ReviewTables):
            return cached

    parents_df = annotate_market_hybrid_claims(
        pl.read_parquet(parents_path), record_type="parent"
    )
    variants_df = annotate_market_hybrid_claims(
        pl.read_parquet(variants_path), record_type="variant"
    )
    if parents_all_path.exists():
        parents_all_df = annotate_market_hybrid_claims(
            pl.read_parquet(parents_all_path), record_type="parent"
        )
    else:
        parents_all_df = parents_df

    combined_df = _build_postfill_combined_table(parents_df, variants_df)

    tables = ReviewTables(
        parents=parents_df,
        variants=variants_df,
        combined=combined_df,
        parents_all=parents_all_df,
    )
    _POSTFILL_TABLES_STATE = {"signature": signature, "tables": tables}
    return tables


_STAGE_PLACEHOLDER_ALIASES = {
    "n/a",
    "n/a (not stated)",
    "na",
    "none",
    "unknown",
    "not stated",
}
_NOT_IN_TAXONOMY_VALUE = "not in taxonomy"
_STAGE_DETAIL_PLACEHOLDERS = _STAGE_PLACEHOLDER_ALIASES | {"null"}


def _strip_wrapping_quotes(text: str) -> str:
    result = text.strip()
    while len(result) >= 2 and (
        (result[0] == result[-1] == '"') or (result[0] == result[-1] == "'")
    ):
        result = result[1:-1].strip()
    return result


def _extract_not_in_taxonomy_detail(text: str) -> str | None:
    lowered = text.casefold()
    if not lowered.startswith(_NOT_IN_TAXONOMY_VALUE):
        return None
    suffix = text[len(_NOT_IN_TAXONOMY_VALUE) :].strip()
    if not suffix:
        return ""
    if suffix.startswith("(") and suffix.endswith(")") and len(suffix) > 2:
        detail = suffix[1:-1].strip()
    elif suffix.startswith(":") or suffix.startswith("-"):
        detail = suffix[1:].strip()
    else:
        detail = suffix.strip()
    return _strip_wrapping_quotes(detail)


def _is_placeholder_notax_detail(detail: str | None) -> bool:
    if detail is None:
        return False
    lowered = detail.strip().casefold()
    if not lowered:
        return True
    if lowered in _STAGE_DETAIL_PLACEHOLDERS:
        return True
    return lowered.startswith(_NOT_IN_TAXONOMY_VALUE)


def _normalize_stage_overlay_value(value: object | None) -> str | None:
    if value is None:
        return None
    text = _strip_wrapping_quotes(str(value))
    if not text:
        return None
    notax_detail = _extract_not_in_taxonomy_detail(text)
    if notax_detail is not None:
        if notax_detail == "":
            return _NOT_IN_TAXONOMY_VALUE
        if _is_placeholder_notax_detail(notax_detail):
            return "N/A"
        return f"not in taxonomy ({notax_detail})"
    lowered = text.casefold()
    if lowered in _STAGE_PLACEHOLDER_ALIASES:
        return "N/A"
    return text


def _normalize_stage_overlay_oov(value: object | None) -> str | None:
    if value is None:
        return None
    text = _strip_wrapping_quotes(str(value))
    if not text:
        return None
    lowered = text.casefold()
    if lowered in _STAGE_DETAIL_PLACEHOLDERS:
        return None
    detail = _extract_not_in_taxonomy_detail(text)
    if detail is not None:
        if _is_placeholder_notax_detail(detail):
            return None
        return detail or None
    return text


def _classify_stage_overlay_value(value: str | None) -> str:
    if value is None:
        return "placeholder"
    lowered = value.strip().casefold()
    if lowered.startswith(_NOT_IN_TAXONOMY_VALUE):
        detail = _extract_not_in_taxonomy_detail(value)
        if _is_placeholder_notax_detail(detail):
            return "placeholder"
        return "taxonomy_miss"
    if lowered in _STAGE_PLACEHOLDER_ALIASES:
        return "placeholder"
    return "meaningful"


def _choose_stage_overlay_value(
    explicit_value: str | None,
    det_value: str | None,
    llm_value: str | None,
) -> tuple[str | None, str | None]:
    explicit_kind = _classify_stage_overlay_value(explicit_value)
    det_kind = _classify_stage_overlay_value(det_value)
    llm_kind = _classify_stage_overlay_value(llm_value)

    if explicit_kind == "meaningful":
        return explicit_value, "deterministic_explicit"
    if explicit_kind == "taxonomy_miss":
        return explicit_value, "deterministic_explicit"

    if llm_kind == "meaningful":
        return llm_value, "llm"

    if llm_kind == "taxonomy_miss":
        if det_kind == "meaningful":
            return det_value, "deterministic"
        if det_kind == "placeholder":
            return llm_value, "llm"
        if llm_value is not None:
            return llm_value, "llm"
        return det_value, "deterministic"

    if det_kind == "meaningful":
        return det_value, "deterministic"
    if det_kind == "taxonomy_miss":
        return det_value, "deterministic"
    if llm_value is not None:
        return llm_value, "llm"
    if det_value is not None:
        return det_value, "deterministic"
    return None, None


def _format_stage_overlay_value(
    *,
    explicit_value: str | None = None,
    explicit_oov: str | None = None,
    det_value: str | None,
    det_oov: str | None,
    llm_value: str | None,
    llm_oov: str | None,
) -> str | None:
    chosen, chosen_source = _choose_stage_overlay_value(
        explicit_value,
        det_value,
        llm_value,
    )
    if chosen is None:
        return None
    if chosen.casefold() != _NOT_IN_TAXONOMY_VALUE:
        return chosen

    normalized_explicit_oov = _normalize_stage_overlay_oov(explicit_oov)
    normalized_det_oov = _normalize_stage_overlay_oov(det_oov)
    normalized_llm_oov = _normalize_stage_overlay_oov(llm_oov)

    if chosen_source == "deterministic_explicit":
        oov_candidate = normalized_explicit_oov
    elif chosen_source == "llm":
        oov_candidate = normalized_llm_oov
    else:
        oov_candidate = normalized_det_oov
    if not oov_candidate:
        fallback_order = [
            normalized_explicit_oov,
            normalized_det_oov,
            normalized_llm_oov,
        ]
        for candidate in fallback_order:
            if candidate:
                oov_candidate = candidate
                break
    if oov_candidate:
        return f"not in taxonomy ({oov_candidate})"
    return "N/A"


def _load_stage_overlay_value_frame(
    pdp_store_path: Path,
    *,
    row_type: str,
) -> pl.DataFrame:
    if not pdp_database_exists(pdp_store_path):
        return pl.DataFrame()

    stage_tables = (
        ("deterministic_explicit", "pdp_attributes_deterministic_explicit"),
        ("deterministic", "pdp_attributes_deterministic"),
        ("llm", "pdp_attributes_llm"),
    )
    entity_map: dict[tuple[str, str, str], dict[str, Any]] = {}

    with connect_pdp_database(pdp_store_path) as conn:
        for stage, table in stage_tables:
            query = (
                "SELECT retailer, row_type, parent_product_id, variant_id, "
                "attribute_id, value, oov_candidate "
                f"FROM {table} WHERE row_type = ?"
            )
            try:
                rows = conn.execute(query, [row_type]).fetchall()
            except Exception:
                rows = []
            for (
                retailer_val,
                _row_type_val,
                parent_id,
                variant_id,
                attr_id,
                value,
                oov_candidate,
            ) in rows:
                retailer_key = str(retailer_val or "").strip()
                parent_key = str(parent_id or "").strip()
                variant_key = (
                    str(variant_id or "").strip() if row_type == "variant" else ""
                )
                attribute_key = str(attr_id or "").strip()
                if not retailer_key or not parent_key or not attribute_key:
                    continue
                base_key = (retailer_key, parent_key, variant_key)
                entity = entity_map.setdefault(
                    base_key,
                    {
                        "meta": {
                            "retailer": retailer_key,
                            "parent_product_id": parent_key,
                            **(
                                {"variant_id": variant_key}
                                if row_type == "variant"
                                else {}
                            ),
                        },
                        "deterministic_explicit": {},
                        "deterministic": {},
                        "llm": {},
                    },
                )
                stage_bucket: dict[str, tuple[str | None, str | None]] = entity[stage]
                stage_bucket[attribute_key] = (
                    _normalize_stage_overlay_value(value),
                    _normalize_stage_overlay_oov(oov_candidate),
                )

    if not entity_map:
        return pl.DataFrame()

    rows_data: list[dict[str, Any]] = []
    for payload in entity_map.values():
        meta = dict(payload["meta"])
        explicit_values: dict[str, tuple[str | None, str | None]] = payload[
            "deterministic_explicit"
        ]
        deterministic_values: dict[str, tuple[str | None, str | None]] = payload[
            "deterministic"
        ]
        llm_values: dict[str, tuple[str | None, str | None]] = payload["llm"]
        attribute_ids = sorted(
            {
                *explicit_values.keys(),
                *deterministic_values.keys(),
                *llm_values.keys(),
            }
        )
        for attr_id in attribute_ids:
            explicit_value, explicit_oov = explicit_values.get(attr_id, (None, None))
            det_value, det_oov = deterministic_values.get(attr_id, (None, None))
            llm_value, llm_oov = llm_values.get(attr_id, (None, None))
            chosen = _format_stage_overlay_value(
                explicit_value=explicit_value,
                explicit_oov=explicit_oov,
                det_value=det_value,
                det_oov=det_oov,
                llm_value=llm_value,
                llm_oov=llm_oov,
            )
            if chosen is not None:
                meta[attr_id] = chosen
        rows_data.append(meta)

    try:
        return pl.DataFrame(rows_data, infer_schema_length=None)
    except Exception:
        LOGGER.exception(
            "Failed to build stage overlay frame for row_type=%s", row_type
        )
        return pl.DataFrame(rows_data, infer_schema_length=len(rows_data))


def _overlay_stage_values_on_tables(tables: ReviewTables) -> ReviewTables:
    pdp_store_path = Path(DEFAULT_PDP_STORE_PATH)
    if not pdp_store_path.exists():
        return tables

    try:
        parent_values = _load_stage_overlay_value_frame(
            pdp_store_path, row_type="parent"
        )
        variant_values = _load_stage_overlay_value_frame(
            pdp_store_path, row_type="variant"
        )
    except Exception:
        LOGGER.exception("Failed to load stage attribute overlays for coverage tables")
        return tables

    if parent_values.is_empty() and variant_values.is_empty():
        return tables

    parents_df = _merge_attribute_values(
        tables.parents,
        parent_values,
        left_on=["retailer", "parent_product_id"],
        right_on=["retailer", "parent_product_id"],
    )
    parents_all_df = _merge_attribute_values(
        tables.parents_all,
        parent_values,
        left_on=["retailer", "parent_product_id"],
        right_on=["retailer", "parent_product_id"],
    )
    variants_df = _merge_attribute_values(
        tables.variants,
        variant_values,
        left_on=["retailer", "parent_product_id", "variant_id"],
        right_on=["retailer", "parent_product_id", "variant_id"],
    )
    combined_df = _build_postfill_combined_table(parents_df, variants_df)
    return ReviewTables(
        parents=parents_df,
        variants=variants_df,
        combined=combined_df,
        parents_all=parents_all_df,
    )


def _get_tables_for_coverage() -> ReviewTables:
    global _COVERAGE_TABLES_STATE

    base_tables = _get_tables()
    postfill_signature = (
        tuple(_POSTFILL_TABLES_STATE.get("signature", ()))
        if isinstance(_POSTFILL_TABLES_STATE, dict)
        else tuple()
    )
    pdp_store_path = Path(DEFAULT_PDP_STORE_PATH)
    store_signature: tuple[float, int] | tuple[None, None]
    if pdp_store_path.exists():
        store_stat = pdp_store_path.stat()
        store_signature = (store_stat.st_mtime, store_stat.st_size)
    else:
        store_signature = (None, None)
    coverage_signature = (postfill_signature, store_signature)

    if (
        _COVERAGE_TABLES_STATE
        and _COVERAGE_TABLES_STATE.get("signature") == coverage_signature
    ):
        cached = _COVERAGE_TABLES_STATE.get("tables")
        if isinstance(cached, ReviewTables):
            return cached

    merged_tables = _overlay_stage_values_on_tables(base_tables)
    _COVERAGE_TABLES_STATE = {"signature": coverage_signature, "tables": merged_tables}
    return merged_tables


def _raise_if_review_reads_blocked_by_ocr() -> None:
    if is_any_ocr_running():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Review pages are temporarily unavailable while slide OCR is running. "
                "Try again later."
            ),
        )


def _get_image_cache() -> Dict[str, List[CachedImage]]:
    global _IMAGE_CACHE
    if _IMAGE_CACHE is None:
        _IMAGE_CACHE = build_image_cache(DEFAULT_IMAGE_ROOT)
    return _IMAGE_CACHE


def _annotate_records_with_sales_and_price(
    display_df: pl.DataFrame,
    tables: ReviewTables,
    retailer: Optional[Sequence[str] | str],
    selected_keys: Sequence[str],
    record_type: str,
) -> tuple[pl.DataFrame, Dict[str, Any]]:
    """Attach scraped-price bands and category metadata for catalog/coverage views."""
    del record_type
    if display_df.is_empty():
        return display_df, {}

    if isinstance(retailer, str):
        retailer_values = _normalize_retailers_param([retailer])
    else:
        retailer_values = _normalize_retailers_param(retailer or [])
    if not retailer_values:
        return display_df, {}
    retailer_norm = retailer_values[0]

    selected_norm = {
        str(key).strip().lower() for key in selected_keys if str(key).strip()
    }

    variants = tables.variants
    category_col: str | None = None
    if "category_key" in variants.columns:
        category_col = "category_key"
    elif "category_label" in variants.columns:
        category_col = "category_label"
    if (
        variants.is_empty()
        or "retailer" not in variants.columns
        or "parent_product_id" not in variants.columns
        or "price_raw" not in variants.columns
        or category_col is None
    ):
        return display_df, {}

    variants = variants.with_columns(
        pl.col("retailer")
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_lowercase()
        .alias("retailer_norm"),
        pl.col("parent_product_id")
        .cast(pl.Utf8)
        .str.strip_chars()
        .alias("parent_id_norm"),
        pl.col(category_col)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_lowercase()
        .alias("category_norm"),
        pl.col("price_raw")
        .map_elements(_parse_price_to_float, return_dtype=pl.Float64)
        .alias("price_numeric"),
    ).filter(pl.col("retailer_norm") == retailer_norm)
    if selected_norm:
        variants = variants.filter(pl.col("category_norm").is_in(list(selected_norm)))
    if variants.is_empty():
        return display_df, {}

    parent_prices = (
        variants.select(["category_norm", "parent_id_norm", "price_numeric"])
        .drop_nulls(subset=["category_norm", "parent_id_norm", "price_numeric"])
        .group_by(["category_norm", "parent_id_norm"])
        .agg(pl.col("price_numeric").median().alias("price_median"))
    )
    if parent_prices.is_empty():
        return display_df, {}

    thresholds = parent_prices.group_by("category_norm").agg(
        pl.col("price_median")
        .quantile(0.35, interpolation="nearest")
        .alias("low_price"),
        pl.col("price_median")
        .quantile(0.85, interpolation="nearest")
        .alias("high_price"),
    )

    annot_df = (
        parent_prices.join(thresholds, on="category_norm", how="left")
        .with_columns(
            pl.when(pl.col("price_median") > pl.col("high_price"))
            .then(pl.lit("premium"))
            .when(pl.col("price_median") < pl.col("low_price"))
            .then(pl.lit("value"))
            .otherwise(pl.lit("mid"))
            .alias("price_band"),
            pl.lit(retailer_norm).alias("retailer_norm"),
        )
        .select(["retailer_norm", "category_norm", "parent_id_norm", "price_band"])
    )
    if annot_df.is_empty():
        return display_df, {}

    band_counts_df = annot_df.group_by(["category_norm", "price_band"]).len(
        name="count"
    )
    totals_df = annot_df.group_by("category_norm").len(name="total_count")
    band_counts: dict[str, dict[str, int]] = {}
    for row in band_counts_df.iter_rows(named=True):
        category_norm = str(row["category_norm"])
        price_band = str(row["price_band"])
        count = int(row["count"] or 0)
        category_counts = band_counts.setdefault(category_norm, {})
        category_counts[price_band] = count

    category_meta: dict[str, Any] = {}
    for row in totals_df.iter_rows(named=True):
        category_norm = str(row["category_norm"])
        total_count = int(row["total_count"] or 0)
        counts = band_counts.get(category_norm, {})
        category_meta[category_norm] = {
            "price_band_shares": {
                "premium": (
                    counts.get("premium", 0) / total_count if total_count else 0.0
                ),
                "mid": counts.get("mid", 0) / total_count if total_count else 0.0,
                "value": counts.get("value", 0) / total_count if total_count else 0.0,
            },
            "meta_key": f"{retailer_norm}:{category_norm}",
        }

    work = display_df
    columns, _schema = get_schema_and_column_names(work)
    if "parent_product_id" not in columns:
        return work, category_meta
    if "retailer" not in work.columns:
        work = work.with_columns(pl.lit(retailer_norm).alias("retailer"))
    work = work.with_columns(
        pl.col("retailer")
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_lowercase()
        .alias("retailer_norm"),
        pl.col("parent_product_id")
        .cast(pl.Utf8)
        .str.strip_chars()
        .alias("parent_id_norm"),
    )
    work = work.join(
        annot_df.select(["retailer_norm", "parent_id_norm", "price_band"]),
        on=["retailer_norm", "parent_id_norm"],
        how="left",
    ).drop(["retailer_norm", "parent_id_norm"])
    return work, category_meta


def _refresh_image_cache() -> Dict[str, List[CachedImage]]:
    global _IMAGE_CACHE
    _IMAGE_CACHE = build_image_cache(DEFAULT_IMAGE_ROOT)
    return _IMAGE_CACHE


def _resolve_image_path(
    parent_id: str, variant_id: Optional[str], prefer_remote: bool = False
) -> Path | None:
    if not parent_id:
        return None
    parent_key = str(parent_id)
    variant_key = str(variant_id) if variant_id is not None else None
    if prefer_remote:
        remote = _download_remote_image(parent_key, variant_key)
        if remote and remote.exists():
            return remote
    cache = _get_image_cache()
    path = find_local_image(cache, parent_key, variant_key)
    if path and path.exists():
        return path
    cache = _refresh_image_cache()
    path = find_local_image(cache, parent_key, variant_key)
    if path and path.exists():
        return path
    downloaded = _download_remote_image(parent_key, variant_key)
    if downloaded and downloaded.exists():
        return downloaded
    return None


def _sanitize_remote_url(value: Any) -> str | None:
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.startswith("//"):
            return f"https:{candidate}"
        lower = candidate.lower()
        if lower.startswith("http://") or lower.startswith("https://"):
            return candidate
        return None
    if isinstance(value, Mapping):
        for key in ("url", "href", "src"):
            if key in value:
                resolved = _sanitize_remote_url(value[key])
                if resolved:
                    return resolved
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            resolved = _sanitize_remote_url(item)
            if resolved:
                return resolved
    return None


def _normalize_image_component(value: str | None, fallback: str = "x") -> str:
    if value is None:
        return fallback
    cleaned = _SAFE_NAME_PATTERN.sub("-", str(value)).strip("-")
    return cleaned.lower() or fallback


def _ensure_remote_image_dir() -> Path:
    _REMOTE_IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    return _REMOTE_IMAGE_ROOT


def _extract_remote_image_from_frame(
    frame: pl.DataFrame,
    parent_id: str,
    variant_id: str | None,
    *,
    require_variant: bool,
) -> tuple[str, str] | None:
    if frame.is_empty() or "parent_product_id" not in frame.columns:
        return None
    criteria = pl.col("parent_product_id") == parent_id
    if require_variant and variant_id:
        variant_expr: pl.Expr | None = None
        for column in ("variant_id", "variant", "variant_key"):
            if column not in frame.columns:
                continue
            expr = pl.col(column) == variant_id
            variant_expr = expr if variant_expr is None else (variant_expr | expr)
        if variant_expr is None:
            return None
        criteria = criteria & variant_expr
    filtered = frame.filter(criteria)
    if filtered.is_empty():
        return None
    available_cols = [
        column
        for column in ("hero_image_url", "swatch_image_url", "pdp_url")
        if column in filtered.columns
    ]
    if not available_cols:
        return None
    row = filtered.select(available_cols).to_dicts()[0]
    for image_type, field in (
        ("hero", "hero_image_url"),
        ("swatch", "swatch_image_url"),
    ):
        url = _sanitize_remote_url(row.get(field))
        if url:
            return url, image_type
    pdp_url = row.get("pdp_url")
    if isinstance(pdp_url, str):
        pdp_url = pdp_url.strip()
    else:
        pdp_url = None
    if pdp_url and _fetch_remote_parent_hero is not None:
        try:
            fetched = _fetch_remote_parent_hero(pdp_url)
        except Exception:  # pragma: no cover - defensive network fallback
            LOGGER.debug("Failed to scrape hero image for %s", pdp_url, exc_info=True)
            fetched = None
        if fetched:
            normalized = _sanitize_remote_url(fetched)
            if normalized:
                return normalized, "hero"
    return None


def _lookup_remote_image_url(
    parent_id: str, variant_id: str | None
) -> tuple[str, str] | None:
    tables = _get_tables()
    if variant_id:
        candidate = _extract_remote_image_from_frame(
            tables.variants,
            parent_id,
            variant_id,
            require_variant=True,
        )
        if candidate:
            return candidate
    parent_frame = (
        tables.parents_all if not tables.parents_all.is_empty() else tables.parents
    )
    candidate = _extract_remote_image_from_frame(
        parent_frame,
        parent_id,
        variant_id,
        require_variant=False,
    )
    return candidate


def _download_remote_image(parent_id: str, variant_id: str | None) -> Path | None:
    candidate = _lookup_remote_image_url(parent_id, variant_id)
    if not candidate:
        return None
    url, image_type = candidate
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        LOGGER.debug(
            "Remote image download failed (parent=%s, variant=%s, url=%s)",
            parent_id,
            variant_id,
            url,
            exc_info=True,
        )
        return None
    suffix = Path(urlparse(url).path).suffix or ".jpg"
    target_dir = _ensure_remote_image_dir()
    parent_component = _normalize_image_component(parent_id)
    name_components = [parent_component]
    if variant_id:
        name_components.append(_normalize_image_component(variant_id))
    name_components.append(image_type)
    file_name = "-".join(name_components) + suffix
    path = target_dir / file_name
    try:
        path.write_bytes(response.content)
    except OSError:
        return None
    _refresh_image_cache()
    return path


def _normalize_category_keys(keys: Sequence[str]) -> List[str]:
    normalized: List[str] = []
    for key in keys:
        transformed = normalize_category_key(str(key))
        if transformed:
            normalized.append(transformed)
    return normalized


def _normalize_taxonomy_identifier(value: str | None) -> str:
    """Normalize taxonomy identifiers for tolerant matching."""
    if not value:
        return ""
    cleaned = str(value).strip().lower()
    normalized = re.sub(r"[\s\-/]+", "_", cleaned)
    return normalized.strip("_")


def _find_category_meta(
    taxonomy: Mapping[str, object],
    category_key: str,
) -> Mapping[str, object] | None:
    normalized_target = _normalize_taxonomy_identifier(category_key)
    if not normalized_target:
        return None
    categories = taxonomy.get("categories") or []
    if not isinstance(categories, list):
        return None
    for category in categories:
        if not isinstance(category, Mapping):
            continue
        for candidate in (category.get("id"), category.get("label")):
            if (
                _normalize_taxonomy_identifier(str(candidate or ""))
                == normalized_target
            ):
                return category
    return None


def _coerce_taxonomy_nodes(
    attribute: Mapping[str, object],
) -> List[Mapping[str, object]]:
    nodes = attribute.get("nodes")
    if isinstance(nodes, list) and nodes:
        return nodes
    values = attribute.get("values")
    if not isinstance(values, list):
        return []
    coerced: List[Mapping[str, object]] = []
    for value in values:
        if isinstance(value, Mapping):
            if value.get("label") or value.get("id") or value.get("children"):
                coerced.append(value)
                continue
            raw_value = value.get("value")
            if raw_value:
                coerced.append(
                    {"label": raw_value, "synonyms": value.get("synonyms") or []}
                )
            continue
        label = str(value).strip()
        if label:
            coerced.append({"label": label})
    return coerced


def _flatten_taxonomy_nodes(
    nodes: Iterable[Mapping[str, object]],
    depth: int = 0,
) -> List[TaxonomyBranchNode]:
    flattened: List[TaxonomyBranchNode] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        label = str(node.get("label") or node.get("id") or "").strip()
        if not label:
            continue
        raw_synonyms = node.get("synonyms") or []
        if isinstance(raw_synonyms, str):
            raw_synonyms = [raw_synonyms]
        synonyms = [str(item).strip() for item in raw_synonyms if str(item).strip()]
        flattened.append(
            TaxonomyBranchNode(label=label, synonyms=synonyms, depth=depth)
        )
        children = node.get("children") or []
        if isinstance(children, list) and children:
            flattened.extend(_flatten_taxonomy_nodes(children, depth + 1))
    return flattened


def _category_labels_from_keys(
    category_lookup: Mapping[str, Mapping[str, object]],
    category_keys: Sequence[str],
) -> List[str]:
    labels: List[str] = []
    for key in category_keys:
        meta = category_lookup.get(key) or {}
        label = meta.get("label") or meta.get("id") or key
        if isinstance(label, str) and label.strip():
            labels.append(label.strip())
    return labels


def _normalize_retailers_param(raw: Sequence[str]) -> List[str]:
    normalized: list[str] = []
    for item in raw:
        if item is None:
            continue
        for part in str(item).split(","):
            cleaned = part.strip().lower()
            if cleaned:
                normalized.append(cleaned)
    return normalized


def _parse_attribute_filters(raw_filters: Sequence[str] | None) -> Dict[str, List[str]]:
    if not raw_filters:
        return {}
    selections: Dict[str, List[str]] = {}
    for item in raw_filters:
        if not item:
            continue
        attr_id, _, values_raw = item.partition(":")
        attr_key = attr_id.strip()
        if not attr_key:
            continue
        values: List[str] = []
        if values_raw:
            for value in values_raw.split("|"):
                cleaned = value.strip()
                if cleaned:
                    values.append(cleaned)
        if values:
            existing = selections.setdefault(attr_key, [])
            for value in values:
                if value not in existing:
                    existing.append(value)
    return selections


_HYBRID_FILTER_COLUMNS: tuple[str, ...] = (
    "also_blush",
    "also_highlighter",
    "also_cheek",
    "also_eyeliner",
)


def _is_hybrid_dimension_key(value: str) -> bool:
    return str(value or "").strip().lower() in _HYBRID_FILTER_COLUMNS


def _hybrid_dimension_label(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("also_"):
        suffix = normalized[len("also_") :].replace("_", " ").strip()
        if suffix:
            return f"Also {suffix}"
    return "Hybrid"


def _parse_binary_filter_values(
    values: Sequence[str] | None,
) -> tuple[bool, bool]:
    include_yes = False
    include_no = False
    if not values:
        return include_yes, include_no
    for raw_value in values:
        token = str(raw_value or "").strip().lower()
        if not token:
            continue
        if token in {"yes", "true", "1", "on"}:
            include_yes = True
        elif token in {"no", "false", "0", "off"}:
            include_no = True
    return include_yes, include_no


def _build_hybrid_filter_selection(
    *,
    also_blush: Sequence[str] | None = None,
    also_highlighter: Sequence[str] | None = None,
    also_cheek: Sequence[str] | None = None,
    also_eyeliner: Sequence[str] | None = None,
) -> dict[str, tuple[bool, bool]]:
    raw_filters: dict[str, Sequence[str] | None] = {
        "also_blush": also_blush,
        "also_highlighter": also_highlighter,
        "also_cheek": also_cheek,
        "also_eyeliner": also_eyeliner,
    }
    active: dict[str, tuple[bool, bool]] = {}
    for column_name in _HYBRID_FILTER_COLUMNS:
        include_yes, include_no = _parse_binary_filter_values(raw_filters[column_name])
        if include_yes != include_no:
            active[column_name] = (include_yes, include_no)
    return active


def _apply_boolean_yes_no_filter(
    frame: pl.DataFrame,
    *,
    column_name: str,
    include_yes: bool,
    include_no: bool,
) -> pl.DataFrame:
    if frame.is_empty() or include_yes == include_no:
        return frame
    if column_name not in frame.columns:
        return frame.head(0) if include_yes else frame
    _columns, schema = get_schema_and_column_names(frame)
    column_dtype = (schema or {}).get(column_name)
    if column_dtype == pl.Boolean:
        bool_expr = pl.col(column_name).fill_null(False)
    else:
        normalized = (
            pl.col(column_name).cast(pl.Utf8).str.strip_chars().str.to_lowercase()
        )
        bool_expr = normalized.is_in(("true", "1", "yes", "y")).fill_null(False)
    return frame.filter(bool_expr if include_yes else ~bool_expr)


def _apply_hybrid_filters(
    frame: pl.DataFrame,
    *,
    selection: Mapping[str, tuple[bool, bool]],
) -> pl.DataFrame:
    if frame.is_empty() or not selection:
        return frame
    result = frame
    for column_name in _HYBRID_FILTER_COLUMNS:
        if column_name not in selection:
            continue
        include_yes, include_no = selection[column_name]
        result = _apply_boolean_yes_no_filter(
            result,
            column_name=column_name,
            include_yes=include_yes,
            include_no=include_no,
        )
        if result.is_empty():
            return result
    return result


def _collect_hybrid_values(frame: pl.DataFrame) -> dict[str, list[str]]:
    if frame.is_empty():
        return {}
    values: dict[str, list[str]] = {}
    for column_name in _HYBRID_FILTER_COLUMNS:
        if column_name not in frame.columns:
            continue
        bool_expr = pl.col(column_name).cast(pl.Boolean).fill_null(False)
        summary = frame.select(
            bool_expr.any().alias("has_yes"),
            (~bool_expr).any().alias("has_no"),
        ).to_dicts()
        if not summary:
            continue
        has_yes = bool(summary[0].get("has_yes"))
        has_no = bool(summary[0].get("has_no"))
        if not has_yes and not has_no:
            continue
        options: list[str] = []
        if has_yes:
            options.append("yes")
        if has_no:
            options.append("no")
        values[column_name] = options
    return values


def _parse_also_blush_filter_values(
    values: Sequence[str] | None,
) -> tuple[bool, bool]:
    return _parse_binary_filter_values(values)


def _apply_also_blush_filter(
    frame: pl.DataFrame,
    *,
    include_yes: bool,
    include_no: bool,
) -> pl.DataFrame:
    return _apply_boolean_yes_no_filter(
        frame,
        column_name="also_blush",
        include_yes=include_yes,
        include_no=include_no,
    )


def _analysis_filter_value(analysis: str) -> str:
    normalized = (analysis or "").strip().lower()
    if normalized in {"not_in_taxonomy", "not-in-taxonomy", "not in taxonomy"}:
        return "Not in taxonomy"
    if normalized in {"found", "has value", "has_value"}:
        return "FOUND"
    return "N/A"


router = APIRouter(
    prefix="/review",
    tags=["review"],
)

site_router = APIRouter()
AUTH_DEPENDENCIES = [Depends(require_authenticated_user)]
SITE_AUTH_DEPENDENCIES = [Depends(require_authenticated_user_for_site)]
AUDIT_PERMISSION = Depends(require_site_permission_for_request)
AUDIT_SITE_DEPENDENCIES = [AUDIT_PERMISSION]
AUDIT_API_DEPENDENCIES = [*AUTH_DEPENDENCIES, AUDIT_PERMISSION]
BETA_LINKS: set[str] = set()
CLARA_PERMISSION_KEY = "clara"
CLARA_FORBIDDEN_COPY: dict[str, dict[str, str]] = {
    "en": {
        "title": "Clara access",
        "message": "Clara is available only to authorized users.",
        "return_home_label": "Return home",
    },
    "it": {
        "title": "Accesso Clara",
        "message": "Clara è disponibile solo per gli utenti autorizzati.",
        "return_home_label": "Torna alla home",
    },
    "fr": {
        "title": "Accès Clara",
        "message": "Clara est disponible uniquement pour les utilisateurs autorisés.",
        "return_home_label": "Retour à l'accueil",
    },
    "de": {
        "title": "Clara-Zugang",
        "message": "Clara ist nur für autorisierte Nutzer verfügbar.",
        "return_home_label": "Zur Startseite",
    },
    "es": {
        "title": "Acceso a Clara",
        "message": "Clara solo está disponible para usuarios autorizados.",
        "return_home_label": "Volver al inicio",
    },
}
_DEFAULT_PRESENTATIONS_ROOT = Path("presentations")


def _site_auth_exception_response(request: Request, exc: HTTPException) -> Response:
    location = (exc.headers or {}).get("Location")
    if location:
        return RedirectResponse(location, status_code=exc.status_code)
    if exc.status_code == status.HTTP_403_FORBIDDEN and templates is not None:
        lang = request.query_params.get("lang") or "en"
        detail = exc.detail
        page_key = detail.get("page") if isinstance(detail, dict) else None
        clara_access_required = page_key == CLARA_PERMISSION_KEY
        clara_forbidden_copy = CLARA_FORBIDDEN_COPY.get(
            lang, CLARA_FORBIDDEN_COPY["en"]
        )
        message = _forbidden_message(detail)
        if clara_access_required:
            message = clara_forbidden_copy["message"]
        return templates.TemplateResponse(
            "forbidden.html",
            {
                "request": request,
                "lang": lang,
                "message": message,
                "clara_access_required": clara_access_required,
                "forbidden_title": clara_forbidden_copy["title"],
                "return_home_label": clara_forbidden_copy["return_home_label"],
            },
            status_code=exc.status_code,
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


def _site_login_required_exception(request: Request) -> HTTPException:
    lang = request.query_params.get("lang")
    target = request.url.path or "/"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    params: list[tuple[str, str]] = [("redirect", target)]
    if lang:
        params.insert(0, ("lang", lang))
    return HTTPException(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        detail="Authentication required.",
        headers={"Location": f"/auth/page?{urlencode(params)}"},
    )


def _require_plugin_download_user(request: Request) -> AuthenticatedUser:
    user = require_authenticated_user_for_site(request)
    if user is None:
        raise _site_login_required_exception(request)
    return user


def _static_site_permission_response(request: Request) -> Response | None:
    return None


def _clara_permission_response(
    request: Request,
    page_key: str = CLARA_PERMISSION_KEY,
) -> Response | None:
    try:
        user = _require_plugin_download_user(request)
    except HTTPException as exc:
        return _site_auth_exception_response(request, exc)

    if user is None:
        return None
    permissions = get_site_permissions()
    normalized_email = user.email.strip().lower()
    allowed = permissions.get(page_key, set())
    if normalized_email in allowed:
        return None
    message = (
        "Clara is available only to authorized users."
        if page_key == CLARA_PERMISSION_KEY
        else "You are not authorized to see this page."
    )
    return _site_auth_exception_response(
        request,
        HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": message,
                "page": page_key,
                "email": user.email,
            },
        ),
    )


def _active_sales_dataset_name() -> str:
    """Return the currently active sales dataset identifier."""

    return get_sales_dataset_name()


_PRIMARY_SALES_DATASET = "us_cosmetics"


def _sort_sales_dataset_names(dataset_names: Sequence[str]) -> list[str]:
    """Sort dataset ids with the primary dataset first."""

    unique_names = sorted(
        {str(name).strip().lower() for name in dataset_names if str(name).strip()}
    )
    return sorted(
        unique_names,
        key=lambda name: (0 if name == _PRIMARY_SALES_DATASET else 1, name),
    )


def _select_sales_dataset(
    requested_dataset: str,
    allowed_datasets: Sequence[str],
) -> str:
    """Return the selected dataset from the allowed list."""

    allowed = _sort_sales_dataset_names(allowed_datasets)
    if not allowed:
        return requested_dataset
    if requested_dataset in allowed:
        return requested_dataset
    if _PRIMARY_SALES_DATASET in allowed:
        return _PRIMARY_SALES_DATASET
    return allowed[0]


def _sales_dataset_label(dataset_name: str | None) -> str:
    """Return a user-facing dataset label."""

    normalized_name = get_sales_dataset_name(dataset_name)
    if normalized_name == "us_cosmetics":
        return "US Cosmetics"
    return normalized_name.replace("_", " ").title()


def _requested_sales_dataset_name(request: Request) -> str:
    """Resolve the sales dataset requested by query parameter."""

    return get_sales_dataset_name(request.query_params.get("dataset"))


def _allowed_sales_datasets_for_user(user_email: str) -> list[str]:
    """Return dataset ids the user is allowed to access."""

    permissions = get_sales_dataset_permissions()
    if not sales_dataset_permissions_configured():
        return _sort_sales_dataset_names(list_available_sales_dataset_names())

    normalized_email = (user_email or "").strip().lower()
    if not normalized_email:
        return []
    allowed = [
        dataset_name
        for dataset_name, emails in permissions.items()
        if normalized_email in emails
    ]
    return _sort_sales_dataset_names(allowed)


def _allowed_sales_download_datasets_for_user(user_email: str) -> set[str]:
    """Return dataset ids the user can download for."""

    if not sales_dataset_download_permissions_configured():
        return set(_allowed_sales_datasets_for_user(user_email))

    permissions = get_sales_dataset_download_permissions()
    normalized_email = (user_email or "").strip().lower()
    if not normalized_email:
        return set()
    return {
        dataset_name
        for dataset_name, emails in permissions.items()
        if normalized_email in emails
    }


def require_sales_dataset_permission_for_request(
    request: Request,
) -> AuthenticatedUser | None:
    """Require access to the requested sales dataset when authentication is enabled."""

    user = require_authenticated_user(request)
    if user is None:
        return None

    active_dataset = _requested_sales_dataset_name(request)
    permissions = get_sales_dataset_permissions()
    if is_sales_dataset_allowed(active_dataset, user.email, permissions):
        return user

    dataset_query = str(request.query_params.get("dataset") or "").strip()
    request_path = request.url.path.rstrip("/")
    if not dataset_query and request_path in {
        "/review/sales/brief",
    }:
        allowed_datasets = _allowed_sales_datasets_for_user(user.email)
        if allowed_datasets:
            return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "forbidden",
            "message": "You are not authorized to access this sales dataset.",
            "dataset": active_dataset,
            "email": user.email,
        },
    )


SALES_DATASET_PERMISSION = Depends(require_sales_dataset_permission_for_request)


def require_sales_dataset_download_permission_for_request(
    request: Request,
) -> AuthenticatedUser | None:
    """Require download permission for the requested sales dataset when auth is enabled."""

    user = require_authenticated_user(request)
    if user is None:
        return None

    active_dataset = _requested_sales_dataset_name(request)
    permissions = get_sales_dataset_download_permissions()
    if is_sales_dataset_download_allowed(active_dataset, user.email, permissions):
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "forbidden",
            "message": "You are not authorized to download data for this sales dataset.",
            "dataset": active_dataset,
            "email": user.email,
        },
    )


SALES_DATASET_DOWNLOAD_PERMISSION = Depends(
    require_sales_dataset_download_permission_for_request
)


def _template_context(**extra: Any) -> dict[str, Any]:
    config = get_auth_config()
    base_context = {
        "auth_enabled": config.authentication_enabled,
        "app_css_asset_version": _static_asset_version("static/css/app.css"),
        "thesis_image_asset_version": _static_asset_version(
            "static/icons/power_control.png"
        ),
        "google_client_id": config.google_client_id,
    }
    base_context.update(extra)
    return base_context


def _presentations_root() -> Path:
    return _DEFAULT_PRESENTATIONS_ROOT


def _static_asset_version(path: str) -> str:
    try:
        return str(int(Path(path).stat().st_mtime))
    except OSError:
        return str(int(time.time()))


TOOLTIP_CONTENT: Dict[str, Dict[str, str]] = {
    "en": {
        "prompt": "Create a customised deep research prompt from your question.",
        "prompt_optimizer_plugin": "Download the Codex plugin for legal, tax and compliance Deep Research prompt optimization: fact anchors, research posture, source strategy, citations and deterministic validation.",
        "deep_research_validator_plugin": "Validate Deep Research outputs: claim support, source checks, reasoning review, corrected Markdown, DOCX and audit trail.",
        "check_entries": "Verify journal entries by comparing them with supporting documents.",
        "product_attributes": "Explore product attribute data across retailers and categories, with filters and detailed records.",
        "chat_report": "Ask questions about a sales report’s executive summary and source material.",
        "projects": "Browse retailer signals to see which attribute bundles appear to be winning, emerging, or overrepresented in the retailer environment.",
        "brand_reports": "Use brand fit reports to see which retailer signals the brand already covers, and where the brand may still have retailer-relevant product gaps.",
        "product_hypotheses": "Explore product hypotheses derived from retailer signals and brand fit.",
        "presentations": "View presentations",
        "slides_editor": "Build and edit executive slides directly in the browser.",
        "sales_by_dataset": "Explore joined sales metrics by attribute.",
        "nav_features": "Jump to a quick overview of every workflow that ships with Mparanza.",
        "nav_about": "Learn how the team behind Mparanza supports finance organisations.",
        "nav_why_us": "See why audit and revenue teams rely on Mparanza for AI-enabled reviews.",
        "new_client": "Open Vera's New Client workflow to prepare the client file, engagement, privacy, AML and monitoring in one source-linked journey.",
        "riconciliazione_plugin": "Download the Codex plugin for open-item reconciliation: open items, ledgers, journals, bank statements, support documents and reviewable Excel/Word outputs.",
        "journal_sampling_plugin": "Download the Codex plugin for journal sampling: variable journal extraction, column mapping, reproducible samples, diagnostics and audit trail.",
        "check_entries_plugin": "Download the Codex plugin for entry support testing: selected entries, supporting PDFs, deterministic checks, exceptions and audit trail.",
        "journal_bank_reconciliation_plugin": "Download the Codex plugin for journal-bank reconciliation: bank statements, journal or ledger rows, deterministic matching, exceptions and audit trail.",
        "report_builder_plugin": "Download the Codex plugin for report building: variable Excel, CSV and PDF inputs, section mapping, Codex narrative, DOCX and audit trail.",
        "concordato_plan_review_plugin": "Download the Codex plugin for concordato plan review: tie out plan numbers against balance, ledgers, adjusted DB and tax/social details, with Excel/Word outputs and audit trail.",
        "audit_reconciliation_family": "Audit and reconciliation workflows: journal sampling, entry support testing, journal-bank matching, open-item reconciliation and plan tie-out.",
        "research_family": "Research workflows: optimize a Deep Research prompt before the run, then validate the answer against cited sources after the run.",
        "reporting_plugin": "Reporting workflow for selecting useful charts, tables and checks before drafting commentary tied to those outputs.",
        "clara_plugin": "Organizes case materials, notes, and reviewed judgements into shareable client outputs.",
        "vera": "Vera works with accounting-firm files to prepare new-client work, checks, reconciliations, INPS case review, reports and tax or regulatory research.",
        "codex_accountants_group": "Guided procedures for documents, controls, reports, and tax or regulatory research.",
        "codex_consultants_group": "Guided procedures for turning materials, analysis, and expert judgement into client-ready outputs.",
        "mix_contribution_analysis_plugin": "Pro plugin for mix and contribution analysis: Mekko, BarMekko, stacked, Pareto, multitier, small multiples, Word report and output package.",
        "period_comparison_plugin": "Pro plugin for period-over-period analysis: previous-year column, line, by-period, waterfall, small multiples, Word report and output package.",
        "variance_analysis_plugin": "Pro plugin for sales variance: period split, price-volume-mix decomposition, net sales, margin bridge, waterfall when useful and audit trail.",
    },
    "it": {
        "prompt": "Crea un prompt ottimizzato da sottoporre a Deep Research.",
        "prompt_optimizer_plugin": "Scarica il plugin Codex per ottimizzare prompt Deep Research legali, fiscali e compliance: fatti, postura, fonti, citazioni e validazione deterministica.",
        "deep_research_validator_plugin": "Valida output Deep Research: supporto delle affermazioni, fonti, ragionamento, Markdown corretto, DOCX e audit trail.",
        "check_entries": "Verifica le registrazioni contabili confrontandole con i documenti di supporto.",
        "product_attributes": "Esplora gli attributi dei prodotti tra rivenditori e categorie con filtri e record dettagliati.",
        "chat_report": "Fai domande sulle conclusioni e sui dati usati in un report di vendite.",
        "projects": "Esplora i segnali dei retailer per vedere quali combinazioni di attributi sembrano vincenti, emergenti o sovrarappresentate nell'ambiente del retailer.",
        "brand_reports": "Usa i report brand fit per vedere quali segnali del retailer il brand copre già e dove il brand può avere ancora gap di prodotto rilevanti per il retailer.",
        "product_hypotheses": "Esplora ipotesi di prodotto derivate dai segnali dei retailer e dal brand fit.",
        "presentations": "Guarda le presentazioni",
        "slides_editor": "Crea e modifica le slide direttamente dal browser.",
        "sales_by_dataset": "Esplora le vendite arricchite per attributo.",
        "new_client": "Apri il percorso Nuovo cliente di Vera per preparare fascicolo, incarico, privacy, AML e monitoraggio in un unico flusso collegato alle fonti.",
        "riconciliazione_plugin": "Scarica il plugin Codex per la riconciliazione partite: partite, mastrini, giornale, banche, supporti esterni e output Excel/Word rivedibili.",
        "journal_sampling_plugin": "Scarica il plugin Codex per il campionamento del giornale: estrazione da formati variabili, mapping colonne, campioni riproducibili, diagnostiche e audit trail.",
        "check_entries_plugin": "Scarica il plugin Codex per il controllo scritture contabili: scritture selezionate, PDF di supporto, controlli deterministici, eccezioni e audit trail.",
        "journal_bank_reconciliation_plugin": "Scarica il plugin Codex per la riconciliazione giornale-banca: estratti conto, righe giornale o mastrino, matching deterministico, eccezioni e audit trail.",
        "report_builder_plugin": "Scarica il plugin Codex per la generazione report: Excel, CSV e PDF variabili, mapping sezioni, narrativa Codex, DOCX e audit trail.",
        "concordato_plan_review_plugin": "Scarica il plugin Codex per la revisione del piano di concordato: controllo numerico contro bilancio, mastrini, prospetti rettificati e dettagli tributari/previdenziali, con output Excel/Word e audit trail.",
        "audit_reconciliation_family": "Flussi di audit e riconciliazione: campionamento giornale, controllo scritture, matching banca-giornale, riconciliazione partite e tie-out del piano.",
        "research_family": "Flussi di ricerca: ottimizza il prompt Deep Research prima del run, poi valida la risposta contro le fonti citate.",
        "reporting_plugin": "Workflow di reporting per scegliere grafici, tabelle e controlli utili prima di scrivere commenti collegati agli output.",
        "clara_plugin": "Organizza materiali, note e valutazioni approvate in output condivisibili per il cliente.",
        "vera": "Vera lavora sui file dello studio per svolgere istruttorie, controlli, riconciliazioni, pratiche previdenziali INPS, report e ricerca fiscale o normativa.",
        "codex_accountants_group": "Procedure guidate per lavorare su documenti, controlli, report e ricerca fiscale.",
        "codex_consultants_group": "Procedure guidate per trasformare materiali, analisi e giudizio esperto in output per il cliente.",
        "mix_contribution_analysis_plugin": "Plugin Pro per analisi mix e contribuzione: Mekko, BarMekko, stacked, Pareto, multitier, small multiples, report Word e pacchetto output.",
        "period_comparison_plugin": "Plugin Pro per analisi periodo su periodo: colonne anno su anno, linea, periodi, waterfall, small multiples, report Word e pacchetto output.",
        "variance_analysis_plugin": "Plugin Pro per l'analisi della varianza delle vendite: suddivisione dei periodi, scomposizione prezzo-volume-mix, vendite nette, margine, waterfall quando serve e audit trail.",
        "nav_features": "Vai direttamente alla panoramica delle funzionalità e dei flussi di lavoro disponibili.",
        "nav_about": "Scopri chi è il team Mparanza e come supporta i reparti finance.",
        "nav_why_us": "Leggi perché i team di audit e revenue scelgono Mparanza.",
    },
    "fr": {
        "prompt": "Créez un prompt de recherche personnalisé à partir de votre question.",
        "prompt_optimizer_plugin": "Téléchargez le plugin Codex pour optimiser les prompts Deep Research juridiques, fiscaux et compliance : faits, posture, sources, citations et validation déterministe.",
        "deep_research_validator_plugin": "Validez les sorties Deep Research : support des affirmations, sources, raisonnement, Markdown corrigé, DOCX et audit trail.",
        "check_entries": "Vérifiez les écritures comptables en les comparant aux pièces justificatives.",
        "product_attributes": "Explorez les attributs produit par enseigne et par catégorie avec des filtres détaillés.",
        "chat_report": "Posez des questions sur les synthèses et les données utilisées dans un rapport de ventes.",
        "projects": "Parcourez les signaux retailers pour voir quelles combinaisons d'attributs semblent gagnantes, émergentes ou surreprésentées dans l'environnement du retailer.",
        "brand_reports": "Utilisez les rapports brand fit pour voir quels signaux retailer la marque couvre déjà et où la marque peut encore avoir des écarts produit pertinents pour le retailer.",
        "product_hypotheses": "Explorez des hypothèses produit dérivées des signaux retailers et du brand fit.",
        "presentations": "Voir les présentations",
        "slides_editor": "Créez et modifiez vos diapositives directement dans le navigateur.",
        "sales_by_dataset": "Explorez les ventes enrichies par attribut.",
        "nav_features": "Accédez rapidement au panorama des fonctionnalités et des workflows proposés.",
        "nav_about": "Découvrez qui compose l’équipe Mparanza et son accompagnement des finances.",
        "nav_why_us": "Comprenez pourquoi les équipes d’audit et commerciales font confiance à Mparanza.",
        "new_client": "Ouvrez le parcours Nouveau client de Vera pour préparer dossier, mission, confidentialité, LCB-FT et suivi dans un même flux relié aux sources.",
        "riconciliazione_plugin": "Téléchargez le plugin Codex pour le rapprochement des postes ouverts : postes, grands livres, journaux, relevés bancaires, justificatifs externes et sorties Excel/Word révisables.",
        "journal_sampling_plugin": "Téléchargez le plugin Codex pour l'échantillonnage du journal : extraction de formats variables, mapping des colonnes, échantillons reproductibles, diagnostics et audit trail.",
        "check_entries_plugin": "Téléchargez le plugin Codex pour le contrôle des écritures : écritures sélectionnées, PDF justificatifs, contrôles déterministes, exceptions et audit trail.",
        "journal_bank_reconciliation_plugin": "Téléchargez le plugin Codex pour le rapprochement journal-banque : relevés bancaires, lignes journal ou grand livre, matching déterministe, exceptions et audit trail.",
        "report_builder_plugin": "Téléchargez le plugin Codex pour générer des rapports : Excel, CSV et PDF variables, mapping des sections, narration Codex, DOCX et audit trail.",
        "concordato_plan_review_plugin": "Téléchargez le plugin Codex pour réviser un plan de concordat : rapprochement des chiffres avec bilan, grands livres, DB ajustée et dettes fiscales/sociales, avec dossiers Excel/Word et audit trail.",
        "audit_reconciliation_family": "Workflows d'audit et de rapprochement : échantillonnage du journal, contrôle des écritures, rapprochement journal-banque, postes ouverts et contrôle du plan.",
        "research_family": "Workflows de recherche : optimisez le prompt Deep Research avant le run, puis validez la réponse contre les sources citées.",
        "reporting_plugin": "Workflow de reporting pour sélectionner les graphiques, tables et contrôles utiles avant de rédiger un commentaire relié aux sorties.",
        "clara_plugin": "Organise les matériaux, notes et jugements validés en livrables client partageables.",
        "vera": "Vera travaille sur les fichiers du cabinet pour réaliser les revues de dossiers clients, contrôles, rapprochements, dossiers INPS, rapports et recherches fiscales ou réglementaires.",
        "codex_accountants_group": "Procédures guidées pour documents, contrôles, rapports et recherche fiscale ou réglementaire.",
        "codex_consultants_group": "Procédures guidées pour transformer matériaux, analyses et jugement expert en livrables client.",
        "mix_contribution_analysis_plugin": "Plugin Pro d'analyse mix et contribution : Mekko, BarMekko, stacked, Pareto, multitier, small multiples, rapport Word et package de sortie.",
        "period_comparison_plugin": "Plugin Pro pour l'analyse période sur période : colonnes année sur année, ligne, fenêtres de période, waterfall, small multiples, rapport Word et package de sortie.",
        "variance_analysis_plugin": "Plugin Pro d'analyse des écarts de ventes : découpage des périodes, décomposition prix-volume-mix, ventes nettes, marge, waterfall quand utile et audit trail.",
    },
    "de": {
        "prompt": "Erstellen Sie aus Ihrer Frage ein optimiertes Deep-Research-Prompt.",
        "prompt_optimizer_plugin": "Laden Sie das Codex-Plugin zur Optimierung von Deep-Research-Prompts für Recht, Steuern und Compliance herunter: Faktenanker, Posture, Quellen, Zitate und deterministische Validierung.",
        "deep_research_validator_plugin": "Validieren Sie Deep-Research-Ausgaben: Aussagenbelege, Quellen, Logik, korrigiertes Markdown, DOCX und Audit-Trail.",
        "check_entries": "Prüfen Sie Buchungssätze, indem Sie sie mit Belegen vergleichen.",
        "product_attributes": "Analysieren Sie Produktattribute über Händler und Kategorien mit detaillierten Filtern.",
        "chat_report": "Stellen Sie Fragen zu Zusammenfassungen und Erkenntnissen eines Verkaufsberichts.",
        "projects": "Durchsuchen Sie Retailer-Signale, um zu sehen, welche Attributbündel im Retailer-Umfeld als stark, aufkommend oder überrepräsentiert erscheinen.",
        "brand_reports": "Nutzen Sie brand-fit-Berichte, um zu sehen, welche Retailer-Signale die Marke bereits abdeckt und wo die Marke noch retailer-relevante Produktlücken haben kann.",
        "product_hypotheses": "Entdecken Sie Produkthypothesen, die aus Retailer-Signalen und brand fit abgeleitet werden.",
        "presentations": "Präsentationen ansehen",
        "slides_editor": "Erstellen und bearbeiten Sie Folien direkt im Browser.",
        "sales_by_dataset": "Analysieren Sie attribut-angereicherte Verkäufe nach Attribut.",
        "nav_features": "Springen Sie zur Übersicht aller verfügbaren Workflows und Funktionen.",
        "nav_about": "Erfahren Sie mehr über das Mparanza-Team und seine Unterstützung für Finanzabteilungen.",
        "nav_why_us": "Lesen Sie, warum Audit- und Vertriebsteams auf Mparanza setzen.",
        "new_client": "Öffnen Sie Veras Ablauf Neuer Mandant, um Akte, Auftrag, Datenschutz, AML und Monitoring in einem quellengebundenen Prozess vorzubereiten.",
        "riconciliazione_plugin": "Laden Sie das Codex-Plugin für Offene-Posten-Abstimmung herunter: offene Posten, Hauptbücher, Journale, Kontoauszüge, externe Nachweise und prüfbare Excel/Word-Arbeitspapiere.",
        "journal_sampling_plugin": "Laden Sie das Codex-Plugin für Journal-Stichproben herunter: variable Journalextraktion, Spalten-Mapping, reproduzierbare Stichproben, Diagnostik und Audit-Trail.",
        "check_entries_plugin": "Laden Sie das Codex-Plugin für Buchungsprüfung herunter: ausgewählte Buchungen, Beleg-PDFs, deterministische Prüfungen, Ausnahmen und Audit-Trail.",
        "journal_bank_reconciliation_plugin": "Laden Sie das Codex-Plugin für Journal-Bank-Abstimmung herunter: Kontoauszüge, Journal- oder Hauptbuchzeilen, deterministisches Matching, Ausnahmen und Audit-Trail.",
        "report_builder_plugin": "Laden Sie das Codex-Plugin für Berichtserstellung herunter: variable Excel-, CSV- und PDF-Eingaben, Abschnittszuordnung, Codex-Narrative, DOCX und Audit-Trail.",
        "concordato_plan_review_plugin": "Laden Sie das Codex-Plugin zur Prüfung eines Concordato-Plans herunter: Zahlenabgleich mit Bilanz, Hauptbüchern, angepasster DB und Steuer-/Sozialschulden, mit Excel/Word-Arbeitspapieren und Audit-Trail.",
        "audit_reconciliation_family": "Audit- und Abstimmungsworkflows: Journal-Stichproben, Buchungsprüfung, Journal-Bank-Abstimmung, offene Posten und Planabgleich.",
        "research_family": "Rechercheworkflows: Deep-Research-Prompt vor dem Lauf optimieren und die Antwort danach gegen zitierte Quellen validieren.",
        "reporting_plugin": "Reporting-Workflow zur Auswahl nützlicher Diagramme, Tabellen und Kontrollen vor dem Schreiben ausgabebezogener Kommentare.",
        "clara_plugin": "Organisiert Fallmaterialien, Notizen und freigegebene Einschätzungen zu teilbaren Kundenergebnissen.",
        "vera": "Vera arbeitet mit Kanzleidateien an Mandantenaufnahme, Prüfungen, Abstimmungen, INPS-Fällen, Berichten sowie steuerlicher oder regulatorischer Recherche.",
        "codex_accountants_group": "Geführte Verfahren für Dokumente, Kontrollen, Berichte sowie Steuer- und Regulierungsrecherche.",
        "codex_consultants_group": "Geführte Verfahren, um Materialien, Analysen und Expertenurteile in Kundenergebnisse zu verwandeln.",
        "mix_contribution_analysis_plugin": "Pro-Plugin für Mix- und Beitragsanalyse: Mekko, BarMekko, Stacked, Pareto, Multitier, Small Multiples, Word-Bericht und Ausgabepaket.",
        "period_comparison_plugin": "Pro-Plugin für Periodenvergleichsanalyse: Vorjahresspalten, Linie, Periodenfenster, Waterfall, Small Multiples, Word-Bericht und Ausgabepaket.",
        "variance_analysis_plugin": "Pro-Plugin für Verkaufsabweichungen: Periodensplit, Preis-Volumen-Mix-Zerlegung, Nettoverkauf, Margen-Bridge, Waterfall bei Bedarf und Audit-Trail.",
    },
    "es": {
        "prompt": "Crea un prompt de Deep Research personalizado a partir de tu pregunta.",
        "prompt_optimizer_plugin": "Descarga el plugin de Codex para optimizar prompts de Deep Research jurídicos, fiscales y de cumplimiento: hechos de referencia, enfoque de investigación, estrategia de fuentes, citas y validación determinista.",
        "deep_research_validator_plugin": "Valida resultados de Deep Research: respaldo de afirmaciones, comprobación de fuentes, revisión del razonamiento, Markdown corregido, DOCX y pista de auditoría.",
        "check_entries": "Comprueba los asientos contables comparándolos con los documentos justificativos.",
        "product_attributes": "Explora datos de atributos de producto entre retailers y categorías, con filtros y registros detallados.",
        "chat_report": "Haz preguntas sobre el resumen ejecutivo y el material de origen de un informe de ventas.",
        "projects": "Explora las señales de retailers para ver qué combinaciones de atributos parecen ganadoras, emergentes o sobrerrepresentadas en el entorno del retailer.",
        "brand_reports": "Usa los informes de afinidad de marca para ver qué señales del retailer ya cubre la marca y dónde puede seguir habiendo oportunidades de producto relevantes para el retailer.",
        "product_hypotheses": "Explora hipótesis de producto derivadas de las señales de retailers y la afinidad de marca.",
        "presentations": "Ver presentaciones",
        "slides_editor": "Crea y edita diapositivas ejecutivas directamente en el navegador.",
        "sales_by_dataset": "Explora métricas de ventas combinadas por atributo.",
        "nav_features": "Ve a una vista rápida de todos los flujos de trabajo incluidos en Mparanza.",
        "nav_about": "Conoce cómo el equipo de Mparanza ayuda a las organizaciones financieras.",
        "nav_why_us": "Descubre por qué los equipos de auditoría e ingresos confían en Mparanza para revisiones asistidas por IA.",
        "new_client": "Abre el flujo Nuevo cliente de Vera para preparar el expediente, el encargo, la privacidad, la prevención del blanqueo y el seguimiento en un recorrido vinculado a las fuentes.",
        "riconciliazione_plugin": "Descarga el plugin de Codex para conciliar partidas abiertas: partidas, libros mayores, diarios, extractos bancarios, justificantes y resultados revisables en Excel y Word.",
        "journal_sampling_plugin": "Descarga el plugin de Codex para muestreo del diario: extracción de diarios variables, asignación de columnas, muestras reproducibles, diagnósticos y pista de auditoría.",
        "check_entries_plugin": "Descarga el plugin de Codex para comprobar justificantes de asientos: asientos seleccionados, PDF justificativos, comprobaciones deterministas, excepciones y pista de auditoría.",
        "journal_bank_reconciliation_plugin": "Descarga el plugin de Codex para conciliar diario y banco: extractos bancarios, filas del diario o libro mayor, correspondencia determinista, excepciones y pista de auditoría.",
        "report_builder_plugin": "Descarga el plugin de Codex para generar informes: entradas variables de Excel, CSV y PDF, asignación de secciones, narrativa de Codex, DOCX y pista de auditoría.",
        "concordato_plan_review_plugin": "Descarga el plugin de Codex para revisar planes de concordato: concilia las cifras del plan con el balance, los libros mayores, los estados ajustados y el detalle fiscal y social, con resultados en Excel y Word y pista de auditoría.",
        "audit_reconciliation_family": "Flujos de auditoría y conciliación: muestreo del diario, comprobación de justificantes, conciliación diario-banco, partidas abiertas y conciliación del plan.",
        "research_family": "Flujos de investigación: optimiza un prompt de Deep Research antes de ejecutarlo y valida después la respuesta frente a las fuentes citadas.",
        "reporting_plugin": "Flujo de informes para seleccionar gráficos, tablas y comprobaciones útiles antes de redactar comentarios vinculados a esos resultados.",
        "clara_plugin": "Organiza materiales del caso, notas y valoraciones revisadas en entregables que pueden compartirse con el cliente.",
        "vera": "Vera trabaja con los archivos del despacho para preparar nuevos clientes, comprobaciones, conciliaciones, revisiones de expedientes del INPS, informes e investigación fiscal o regulatoria.",
        "codex_accountants_group": "Procedimientos guiados para documentos, controles, informes e investigación fiscal o regulatoria.",
        "codex_consultants_group": "Procedimientos guiados para convertir materiales, análisis y criterio experto en entregables listos para el cliente.",
        "mix_contribution_analysis_plugin": "Plugin Pro para análisis de mix y contribución: Mekko, BarMekko, apilados, Pareto, multinivel, múltiplos pequeños, informe de Word y paquete de resultados.",
        "period_comparison_plugin": "Plugin Pro para análisis entre periodos: columnas interanuales, línea, por periodo, cascada, múltiplos pequeños, informe de Word y paquete de resultados.",
        "variance_analysis_plugin": "Plugin Pro para desviaciones de ventas: división por periodos, descomposición precio-volumen-mix, ventas netas, puente de margen, cascada cuando sea útil y pista de auditoría.",
    },
}

LANDING_CONTENT: Dict[str, Dict[str, Any]] = {
    "en": {
        "primary": {
            "title": "",
            "links": [],
        },
        "sections": [
            {
                "preserve_order": True,
                "groups": [
                    {
                        "id": "vera",
                        "title": "Codex for accountants",
                        "tooltip_key": "codex_accountants_group",
                        "audience": "For accountants",
                        "lead": (
                            "A Codex plugin for client files, accounting checks, "
                            "reconciliations and reporting."
                        ),
                        "description": (
                            "Vera works directly on the firm's files. It handles new-client "
                            "work and journal sampling, checks entries, reconciles records, "
                            "and prepares reports or tax and regulatory research."
                        ),
                        "proof": [
                            "From new-client work to regulatory research",
                            "Reviewable checks and reconciliations",
                            "Workpapers ready for professional review",
                        ],
                        "cta_label": "Explore Vera",
                        "icon": "/static/shared/vera/icon.svg",
                        "links": [
                            {
                                "label": "Vera",
                                "href": "/static/shared/vera/index.html",
                                "active": True,
                                "tooltip_key": "vera",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "clara",
                        "title": "Codex for consultants",
                        "tooltip_key": "codex_consultants_group",
                        "audience": "For consultants",
                        "lead": (
                            "A Codex plugin for presentations and ongoing project work."
                        ),
                        "description": (
                            "Clara brings documents, notes, interviews and recordings together "
                            "in the project folder, then uses that context to create or revise "
                            "presentations, briefs and decision packs."
                        ),
                        "proof": [
                            "Project context carried forward",
                            "Evidence gathered in one workspace",
                            "Briefs, presentations and decision packs",
                        ],
                        "cta_label": "Explore Clara",
                        "icon": "/static/shared/clara/icon.svg",
                        "links": [
                            {
                                "label": "Clara",
                                "href": "/static/shared/clara/index.html",
                                "active": True,
                                "tooltip_key": "clara_plugin",
                                "public": True,
                            },
                        ],
                    },
                ],
            },
        ],
        "menu_links": [],
        "hero": {
            "id": "hero",
            "skip_label": "Skip to main content",
            "plugins_label": "Codex plugins",
            "eyebrow": "Codex plugins for professional work",
            "headline": "AI has the power. Codex provides the control.",
            "subheadline": (
                "Mparanza builds Codex plugins. Each gives Codex a "
                "specialist way of working for professional tasks."
            ),
        },
        "harness": {
            "id": "codex",
            "title": "The harness changes what AI can do.",
            "description": (
                "AI provides the capabilities. Codex puts them in a working environment "
                "that can use files, run tools, follow instructions and create outputs. "
                "That harness is what we mean by control."
            ),
            "layers": [
                {
                    "title": "Power",
                    "blurb": "The model reasons, analyzes and creates.",
                },
                {
                    "title": "Control",
                    "blurb": (
                        "Codex connects those capabilities to the files, tools and context "
                        "of the task."
                    ),
                },
                {
                    "title": "Professional use",
                    "blurb": (
                        "A Codex plugin defines the specialist method and expected outputs."
                    ),
                },
            ],
        },
        "open_source": {
            "id": "open-source",
            "title": "Open by design.",
            "description": (
                "Vera and Clara are open-source Codex plugins. "
                "You can inspect the methods, controls, and code before using them—and "
                "adapt them to your work."
            ),
            "links_label": "Open-source information",
            "links": [
                {
                    "label": "Inspect the source on GitHub",
                    "href": "https://github.com/fabioannovazzi/app_files",
                },
                {
                    "label": "Read the GNU AGPLv3 license",
                    "href": "https://github.com/fabioannovazzi/app_files/blob/main/LICENSE",
                },
            ],
        },
        "free": {
            "id": "free",
            "title": "Free by design.",
            "description": (
                "Vera and Clara are free to install and use. We welcome contributions "
                "to their development. We charge for consulting, implementation, "
                "and hosted services."
            ),
        },
        "security": {
            "id": "security",
            "title": "Secure by design.",
            "lead": (
                "In ordinary Vera and Clara workflows, Mparanza does not receive your client work."
            ),
            "description": (
                "Ordinary plugin workflows run inside your existing Codex environment. "
                "Your client prompts, files, and outputs do not pass through Mparanza."
            ),
            "cta_label": "See how your data is handled",
            "cta_href": "/data-handling",
        },
        "compliance": {
            "id": "compliance",
            "title": "Compliant by design.",
            "lead": ("Professional work may require Codex to read real client data."),
            "description": (
                "Vera and Clara do not automatically anonymise data. They may use "
                "local Python to filter or aggregate information when useful. Data "
                "supplied to the model is processed through the user's existing "
                "ChatGPT plan."
            ),
            "principles": [
                {
                    "title": "Use local Python when useful",
                    "blurb": "Filtering and aggregation can happen on your computer when they improve the work. They are not automatic anonymisation.",
                },
                {
                    "title": "Real data may reach the model",
                    "blurb": "Names, documents, original language, and case facts may enter the model context when the professional task needs them.",
                },
                {
                    "title": "Two processing categories",
                    "blurb": "Ordinary plugin functions use the existing ChatGPT plan. Mparanza-hosted services form a separate processing boundary.",
                },
            ],
            "closing": "One policy for Vera and Clara. No prompt-by-prompt paperwork.",
            "cta_label": "See how your data is handled",
            "cta_href": "/data-handling",
        },
        "bridge": {
            "id": "plugins",
            "title": "Codex by design.",
            "description": (
                "Mparanza is Vera and Clara: two plugins that apply the same Codex "
                "harness to two different professions."
            ),
        },
    },
    "it": {
        "primary": {
            "title": "",
            "links": [],
        },
        "sections": [
            {
                "preserve_order": True,
                "groups": [
                    {
                        "id": "vera",
                        "title": "Codex per commercialisti",
                        "tooltip_key": "codex_accountants_group",
                        "audience": "Per commercialisti",
                        "lead": (
                            "Un plugin Codex per lavorare su fascicoli, controlli contabili, "
                            "riconciliazioni e report."
                        ),
                        "description": (
                            "Vera lavora direttamente sui file dello studio. Gestisce "
                            "istruttorie e campionamenti, controlla le scritture, esegue "
                            "riconciliazioni e prepara report o ricerche fiscali e normative."
                        ),
                        "proof": [
                            "Dall'istruttoria alla ricerca fiscale",
                            "Controlli e riconciliazioni rivedibili",
                            "Carte di lavoro pronte per la revisione",
                        ],
                        "cta_label": "Scopri Vera",
                        "icon": "/static/shared/vera/icon.svg",
                        "links": [
                            {
                                "label": "Vera",
                                "href": "/static/shared/vera/index.html",
                                "active": True,
                                "tooltip_key": "vera",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "clara",
                        "title": "Codex per consulenti",
                        "tooltip_key": "codex_consultants_group",
                        "audience": "Per consulenti",
                        "lead": (
                            "Un plugin Codex per creare presentazioni e dare continuità "
                            "al lavoro sui progetti."
                        ),
                        "description": (
                            "Clara riunisce documenti, note, interviste e registrazioni "
                            "nella cartella del progetto e usa questo contesto per creare "
                            "o aggiornare presentazioni, note di sintesi e dossier "
                            "decisionali."
                        ),
                        "proof": [
                            "Contesto del progetto sempre disponibile",
                            "Materiali riuniti nella cartella del progetto",
                            "Presentazioni, sintesi e dossier decisionali",
                        ],
                        "cta_label": "Scopri Clara",
                        "icon": "/static/shared/clara/icon.svg",
                        "links": [
                            {
                                "label": "Clara",
                                "href": "/static/shared/clara/index.html",
                                "active": True,
                                "tooltip_key": "clara_plugin",
                                "public": True,
                            },
                        ],
                    },
                ],
            },
        ],
        "menu_links": [],
        "hero": {
            "id": "hero",
            "skip_label": "Vai al contenuto principale",
            "plugins_label": "Plugin Codex",
            "eyebrow": "Plugin Codex per il lavoro professionale",
            "headline": "La potenza viene dall'AI. Il controllo, da Codex.",
            "subheadline": (
                "Mparanza crea plugin Codex. Ogni plugin dà a Codex "
                "un metodo specialistico per il lavoro professionale."
            ),
        },
        "harness": {
            "id": "codex",
            "title": "L'ambiente operativo cambia ciò che l'AI può fare.",
            "description": (
                "Le capacità vengono dall'AI. Codex le mette al lavoro in un ambiente "
                "che può usare file e strumenti, seguire istruzioni e produrre risultati. "
                "È questo ambiente operativo che intendiamo per controllo."
            ),
            "layers": [
                {
                    "title": "Potenza",
                    "blurb": "Il modello ragiona, analizza e crea.",
                },
                {
                    "title": "Controllo",
                    "blurb": (
                        "Codex collega queste capacità ai file, agli strumenti e al "
                        "contesto del lavoro da svolgere."
                    ),
                },
                {
                    "title": "Utilità professionale",
                    "blurb": (
                        "Un plugin Codex definisce il metodo specialistico e i risultati "
                        "da produrre."
                    ),
                },
            ],
        },
        "open_source": {
            "id": "open-source",
            "title": "Aperti per scelta.",
            "description": (
                "Vera e Clara sono plugin Codex open source. "
                "Puoi esaminare i metodi, i controlli e il codice prima di usarli, e "
                "adattarli al tuo lavoro."
            ),
            "links_label": "Informazioni open source",
            "links": [
                {
                    "label": "Esamina il codice su GitHub",
                    "href": "https://github.com/fabioannovazzi/app_files",
                },
                {
                    "label": "Leggi la licenza GNU AGPLv3",
                    "href": "https://github.com/fabioannovazzi/app_files/blob/main/LICENSE",
                },
            ],
        },
        "free": {
            "id": "free",
            "title": "Gratuiti per scelta.",
            "description": (
                "Vera e Clara si possono installare e usare gratuitamente. Accogliamo "
                "volentieri contributi al loro sviluppo. Offriamo a pagamento "
                "consulenza, implementazione e servizi hosted."
            ),
        },
        "security": {
            "id": "security",
            "title": "Sicuri per scelta.",
            "lead": "Nei flussi ordinari di Vera e Clara, Mparanza non riceve il lavoro dei tuoi clienti.",
            "description": (
                "I normali workflow dei plugin operano nell'ambiente Codex che già usi. "
                "Prompt, file e risultati dei tuoi clienti non passano attraverso Mparanza."
            ),
            "cta_label": "Scopri come vengono gestiti i tuoi dati",
            "cta_href": "/data-handling",
        },
        "compliance": {
            "id": "compliance",
            "title": "Conformi per scelta.",
            "lead": "Il lavoro professionale può richiedere a Codex di leggere dati reali dei clienti.",
            "description": "Vera e Clara non anonimizzano automaticamente i dati. Possono usare Python in locale per filtrare o aggregare le informazioni quando è utile. I dati forniti al modello vengono trattati attraverso il piano ChatGPT già utilizzato dall'utente.",
            "principles": [
                {
                    "title": "Usa Python in locale quando serve",
                    "blurb": "Filtri e aggregazioni possono essere eseguiti sul tuo computer quando migliorano il lavoro. Non sono anonimizzazione automatica.",
                },
                {
                    "title": "I dati reali possono arrivare al modello",
                    "blurb": "Nomi, documenti, testo originale e fatti del caso possono entrare nel contesto del modello quando servono al lavoro professionale.",
                },
                {
                    "title": "Due categorie di trattamento",
                    "blurb": "Le normali funzioni dei plugin usano il piano ChatGPT esistente. I servizi hosted di Mparanza hanno un confine di trattamento separato.",
                },
            ],
            "closing": "Una regola per Vera e Clara. Nessuna burocrazia prompt per prompt.",
            "cta_label": "Scopri come vengono gestiti i tuoi dati",
            "cta_href": "/data-handling",
        },
        "bridge": {
            "id": "plugins",
            "title": "Codex per scelta.",
            "description": (
                "Mparanza è Vera e Clara: due plugin che applicano lo stesso ambiente "
                "operativo Codex a due professioni diverse."
            ),
        },
    },
    "fr": {
        "primary": {
            "title": "",
            "links": [],
        },
        "sections": [
            {
                "preserve_order": True,
                "groups": [
                    {
                        "id": "vera",
                        "title": "Codex pour les experts-comptables",
                        "tooltip_key": "codex_accountants_group",
                        "audience": "Pour les experts-comptables",
                        "lead": (
                            "Un plugin Codex pour les dossiers clients, les contrôles "
                            "comptables, les rapprochements et les rapports."
                        ),
                        "description": (
                            "Vera travaille directement sur les fichiers du cabinet. Elle "
                            "prépare les dossiers et les échantillons, contrôle les écritures, "
                            "effectue les rapprochements et produit des rapports ou des "
                            "recherches fiscales et réglementaires."
                        ),
                        "proof": [
                            "De l'ouverture du dossier à la recherche fiscale",
                            "Contrôles et rapprochements révisables",
                            "Feuilles de travail prêtes à être revues",
                        ],
                        "cta_label": "Découvrir Vera",
                        "icon": "/static/shared/vera/icon.svg",
                        "links": [
                            {
                                "label": "Vera",
                                "href": "/static/shared/vera/index.html",
                                "active": True,
                                "tooltip_key": "vera",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "clara",
                        "title": "Codex pour les consultants",
                        "tooltip_key": "codex_consultants_group",
                        "audience": "Pour les consultants",
                        "lead": (
                            "Un plugin Codex pour créer des présentations et poursuivre "
                            "le travail sur les projets dans la durée."
                        ),
                        "description": (
                            "Clara réunit dans le dossier du projet les documents, notes, "
                            "entretiens et enregistrements, puis s'appuie sur ce contexte "
                            "pour créer ou mettre à jour des présentations, des notes de "
                            "synthèse et des dossiers d'aide à la décision."
                        ),
                        "proof": [
                            "Contexte du projet conservé dans la durée",
                            "Sources réunies dans un même espace de travail",
                            "Présentations, synthèses et dossiers de décision",
                        ],
                        "cta_label": "Découvrir Clara",
                        "icon": "/static/shared/clara/icon.svg",
                        "links": [
                            {
                                "label": "Clara",
                                "href": "/static/shared/clara/index.html",
                                "active": True,
                                "tooltip_key": "clara_plugin",
                                "public": True,
                            },
                        ],
                    },
                ],
            },
        ],
        "menu_links": [],
        "hero": {
            "id": "hero",
            "skip_label": "Aller au contenu principal",
            "plugins_label": "Plugins Codex",
            "eyebrow": "Plugins Codex pour les professionnels",
            "headline": "L'IA apporte la puissance. Codex apporte le contrôle.",
            "subheadline": (
                "Mparanza crée des plugins Codex. Chacun donne à "
                "Codex une méthode spécialisée pour le travail professionnel."
            ),
        },
        "harness": {
            "id": "codex",
            "title": "L'environnement de travail change ce que l'IA peut faire.",
            "description": (
                "Les capacités viennent de l'IA. Codex les rend opérationnelles dans un "
                "environnement qui peut utiliser des fichiers et des outils, suivre des "
                "instructions et produire des livrables. C'est cet environnement de "
                "travail que nous appelons le contrôle."
            ),
            "layers": [
                {
                    "title": "Puissance",
                    "blurb": "Le modèle raisonne, analyse et crée.",
                },
                {
                    "title": "Contrôle",
                    "blurb": (
                        "Codex relie les capacités du modèle aux fichiers, aux outils et au "
                        "contexte de la tâche."
                    ),
                },
                {
                    "title": "Usage professionnel",
                    "blurb": (
                        "Un plugin Codex définit la méthode spécialisée et les livrables "
                        "à produire."
                    ),
                },
            ],
        },
        "open_source": {
            "id": "open-source",
            "title": "Ouverts par conception.",
            "description": (
                "Vera et Clara sont des plugins Codex open source. Vous pouvez examiner "
                "leurs méthodes, leurs contrôles et leur code avant de les utiliser — "
                "et les adapter à votre travail."
            ),
            "links_label": "Informations open source",
            "links": [
                {
                    "label": "Examiner le code sur GitHub",
                    "href": "https://github.com/fabioannovazzi/app_files",
                },
                {
                    "label": "Lire la licence GNU AGPLv3",
                    "href": "https://github.com/fabioannovazzi/app_files/blob/main/LICENSE",
                },
            ],
        },
        "free": {
            "id": "free",
            "title": "Gratuits par conception.",
            "description": (
                "Vera et Clara sont gratuites à installer et à utiliser. Nous accueillons "
                "volontiers les contributions à leur développement. Nous facturons nos "
                "prestations de conseil et de mise en œuvre, ainsi que nos services "
                "hébergés."
            ),
        },
        "security": {
            "id": "security",
            "title": "Sécurisés par conception.",
            "lead": (
                "Dans les flux ordinaires de Vera et Clara, Mparanza ne reçoit pas le travail de vos clients."
            ),
            "description": (
                "Les workflows ordinaires des plugins fonctionnent dans l'environnement "
                "Codex que vous utilisez déjà. Les prompts, fichiers et livrables de vos "
                "clients ne transitent pas par Mparanza."
            ),
            "cta_label": "Voir comment vos données sont traitées",
            "cta_href": "/data-handling",
        },
        "compliance": {
            "id": "compliance",
            "title": "Conformes par conception.",
            "lead": "Le travail professionnel peut nécessiter que Codex lise de vraies données clients.",
            "description": "Vera et Clara n'anonymisent pas automatiquement les données. Elles peuvent utiliser Python localement pour filtrer ou agréger des informations lorsque cela est utile. Les données fournies au modèle sont traitées dans le cadre de l'offre ChatGPT existante de l'utilisateur.",
            "principles": [
                {
                    "title": "Utiliser Python localement lorsque c'est utile",
                    "blurb": "Le filtrage et l'agrégation peuvent s'exécuter sur votre ordinateur lorsqu'ils améliorent le travail. Il ne s'agit pas d'une anonymisation automatique.",
                },
                {
                    "title": "Les données réelles peuvent parvenir au modèle",
                    "blurb": "Noms, documents, texte original et faits propres au dossier peuvent entrer dans le contexte du modèle lorsque le travail professionnel l'exige.",
                },
                {
                    "title": "Deux catégories de traitement",
                    "blurb": "Les fonctions ordinaires des plugins utilisent l'offre ChatGPT existante. Les services hébergés par Mparanza ont un périmètre de traitement distinct.",
                },
            ],
            "closing": "Une règle pour Vera et Clara. Aucune paperasse prompt par prompt.",
            "cta_label": "Voir comment vos données sont traitées",
            "cta_href": "/data-handling",
        },
        "bridge": {
            "id": "plugins",
            "title": "Codex par conception.",
            "description": (
                "Mparanza, c'est Vera et Clara : deux plugins qui appliquent le même "
                "environnement Codex à deux métiers différents."
            ),
        },
    },
    "de": {
        "primary": {
            "title": "",
            "links": [],
        },
        "sections": [
            {
                "preserve_order": True,
                "groups": [
                    {
                        "id": "vera",
                        "title": "Codex für Steuerberaterinnen und Steuerberater",
                        "tooltip_key": "codex_accountants_group",
                        "audience": "Für Steuerberaterinnen und Steuerberater",
                        "lead": (
                            "Ein Codex-Plugin für Mandantendateien, Buchungsprüfungen, "
                            "Abstimmungen und Berichte."
                        ),
                        "description": (
                            "Vera arbeitet direkt mit den Kanzleidateien. Sie übernimmt "
                            "Mandantenaufnahme und Stichproben, prüft Buchungen, stimmt "
                            "Unterlagen ab und erstellt Berichte oder steuerliche und "
                            "regulatorische Recherchen."
                        ),
                        "proof": [
                            "Von der Mandantenaufnahme bis zur Fachrecherche",
                            "Nachvollziehbare Prüfungen und Abstimmungen",
                            "Arbeitspapiere für die fachliche Prüfung",
                        ],
                        "cta_label": "Vera kennenlernen",
                        "icon": "/static/shared/vera/icon.svg",
                        "links": [
                            {
                                "label": "Vera",
                                "href": "/static/shared/vera/index.html",
                                "active": True,
                                "tooltip_key": "vera",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "clara",
                        "title": "Codex für Beraterinnen und Berater",
                        "tooltip_key": "codex_consultants_group",
                        "audience": "Für Beraterinnen und Berater",
                        "lead": (
                            "Ein Codex-Plugin für Präsentationen und die fortlaufende "
                            "Arbeit an Projekten."
                        ),
                        "description": (
                            "Clara bündelt Dokumente, Notizen, Interviews und Aufzeichnungen "
                            "im Projektordner. Diesen Kontext nutzt sie, um Präsentationen, "
                            "Briefings und Entscheidungsvorlagen zu erstellen oder zu "
                            "überarbeiten."
                        ),
                        "proof": [
                            "Projektkontext bleibt langfristig verfügbar",
                            "Quellen gebündelt in einem Arbeitsbereich",
                            "Briefings, Präsentationen und Entscheidungsvorlagen",
                        ],
                        "cta_label": "Clara kennenlernen",
                        "icon": "/static/shared/clara/icon.svg",
                        "links": [
                            {
                                "label": "Clara",
                                "href": "/static/shared/clara/index.html",
                                "active": True,
                                "tooltip_key": "clara_plugin",
                                "public": True,
                            },
                        ],
                    },
                ],
            },
        ],
        "menu_links": [],
        "hero": {
            "id": "hero",
            "skip_label": "Zum Hauptinhalt springen",
            "plugins_label": "Codex-Plugins",
            "eyebrow": "Codex-Plugins für professionelle Arbeit",
            "headline": "KI liefert die Leistung. Codex sorgt für Kontrolle.",
            "subheadline": (
                "Mparanza entwickelt Codex-Plugins. Jedes gibt "
                "Codex eine fachliche Arbeitsweise für professionelle Aufgaben."
            ),
        },
        "harness": {
            "id": "codex",
            "title": "Die Arbeitsumgebung verändert, was KI leisten kann.",
            "description": (
                "KI bringt die Fähigkeiten mit. Codex stellt eine Arbeitsumgebung "
                "bereit, die Dateien verarbeiten, Werkzeuge einsetzen, Anweisungen "
                "befolgen und Ergebnisse erzeugen kann. Diese Arbeitsumgebung meinen "
                "wir, wenn wir von Kontrolle sprechen."
            ),
            "layers": [
                {
                    "title": "Leistung",
                    "blurb": (
                        "Das Modell analysiert, zieht Schlüsse und erstellt Inhalte."
                    ),
                },
                {
                    "title": "Kontrolle",
                    "blurb": (
                        "Codex verbindet diese Fähigkeiten mit den Dateien, Werkzeugen und "
                        "dem Kontext der Aufgabe."
                    ),
                },
                {
                    "title": "Professioneller Einsatz",
                    "blurb": (
                        "Ein Codex-Plugin bringt die fachliche Methode mit und legt die "
                        "zu erstellenden Ergebnisse fest."
                    ),
                },
            ],
        },
        "open_source": {
            "id": "open-source",
            "title": "Offen konzipiert.",
            "description": (
                "Vera und Clara sind Open-Source-Plugins für Codex. Sie können Methoden, "
                "Kontrollen und Code vor der Verwendung prüfen und an Ihre Arbeit anpassen."
            ),
            "links_label": "Open-Source-Informationen",
            "links": [
                {
                    "label": "Quellcode auf GitHub prüfen",
                    "href": "https://github.com/fabioannovazzi/app_files",
                },
                {
                    "label": "GNU-AGPLv3-Lizenz lesen",
                    "href": "https://github.com/fabioannovazzi/app_files/blob/main/LICENSE",
                },
            ],
        },
        "free": {
            "id": "free",
            "title": "Kostenlos konzipiert.",
            "description": (
                "Vera und Clara können kostenlos installiert und genutzt werden. Wir "
                "freuen uns über Beiträge zu ihrer Weiterentwicklung. Wir stellen "
                "Beratungs- und Implementierungsleistungen sowie gehostete Services "
                "in Rechnung."
            ),
        },
        "security": {
            "id": "security",
            "title": "Sicher konzipiert.",
            "lead": (
                "Bei normalen Vera- und Clara-Abläufen erhält Mparanza Ihre Mandantenarbeit nicht."
            ),
            "description": (
                "Normale Plugin-Abläufe laufen in Ihrer bestehenden Codex-Umgebung. "
                "Prompts, Dateien und Ergebnisse Ihrer Mandanten laufen nicht über Mparanza."
            ),
            "cta_label": "Erfahren Sie, wie Ihre Daten verarbeitet werden",
            "cta_href": "/data-handling",
        },
        "compliance": {
            "id": "compliance",
            "title": "Für Compliance konzipiert.",
            "lead": "Professionelle Arbeit kann erfordern, dass Codex echte Mandantendaten liest.",
            "description": "Vera und Clara anonymisieren Daten nicht automatisch. Sie können Python lokal einsetzen, um Informationen zu filtern oder zu aggregieren, wenn dies nützlich ist. Daten, die dem Modell bereitgestellt werden, werden im Rahmen des bestehenden ChatGPT-Tarifs des Nutzers verarbeitet.",
            "principles": [
                {
                    "title": "Python lokal einsetzen, wenn es nützt",
                    "blurb": "Filtern und Aggregieren kann auf Ihrem Computer erfolgen, wenn es die Arbeit verbessert. Das ist keine automatische Anonymisierung.",
                },
                {
                    "title": "Echte Daten können das Modell erreichen",
                    "blurb": "Namen, Dokumente, Originalformulierungen und Fallfakten können in den Modellkontext gelangen, wenn die professionelle Aufgabe sie benötigt.",
                },
                {
                    "title": "Zwei Verarbeitungskategorien",
                    "blurb": "Normale Plugin-Funktionen nutzen den bestehenden ChatGPT-Tarif. Mparanza-gehostete Dienste haben eine separate Verarbeitungsgrenze.",
                },
            ],
            "closing": "Eine Regel für Vera und Clara. Kein Papierkram für jeden Prompt.",
            "cta_label": "Erfahren Sie, wie Ihre Daten verarbeitet werden",
            "cta_href": "/data-handling",
        },
        "bridge": {
            "id": "plugins",
            "title": "Für Codex konzipiert.",
            "description": (
                "Mparanza, das sind Vera und Clara: zwei Plugins, die dieselbe "
                "Codex-Arbeitsumgebung auf zwei Berufsgruppen ausrichten."
            ),
        },
    },
    "es": {
        "primary": {
            "title": "",
            "links": [],
        },
        "sections": [
            {
                "preserve_order": True,
                "groups": [
                    {
                        "id": "vera",
                        "title": "Codex para profesionales contables",
                        "tooltip_key": "codex_accountants_group",
                        "audience": "Para profesionales contables",
                        "lead": (
                            "Un plugin de Codex para expedientes de clientes, controles "
                            "contables, conciliaciones e informes."
                        ),
                        "description": (
                            "Vera trabaja directamente con los archivos del despacho. "
                            "Gestiona la incorporación de nuevos clientes y el muestreo "
                            "de diarios, comprueba asientos, concilia registros y prepara "
                            "informes o investigaciones fiscales y regulatorias."
                        ),
                        "proof": [
                            "De la incorporación de clientes a la investigación regulatoria",
                            "Comprobaciones y conciliaciones revisables",
                            "Papeles de trabajo listos para la revisión profesional",
                        ],
                        "cta_label": "Descubrir Vera",
                        "icon": "/static/shared/vera/icon.svg",
                        "links": [
                            {
                                "label": "Vera",
                                "href": "/static/shared/vera/index.html",
                                "active": True,
                                "tooltip_key": "vera",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "clara",
                        "title": "Codex para consultores",
                        "tooltip_key": "codex_consultants_group",
                        "audience": "Para consultores",
                        "lead": (
                            "Un plugin de Codex para presentaciones y trabajo continuo "
                            "en proyectos."
                        ),
                        "description": (
                            "Clara reúne documentos, notas, entrevistas y grabaciones en "
                            "la carpeta del proyecto y usa ese contexto para crear o revisar "
                            "presentaciones, informes breves y documentos para la toma de "
                            "decisiones."
                        ),
                        "proof": [
                            "Contexto del proyecto conservado",
                            "Evidencias reunidas en un solo espacio de trabajo",
                            "Informes, presentaciones y documentos de decisión",
                        ],
                        "cta_label": "Descubrir Clara",
                        "icon": "/static/shared/clara/icon.svg",
                        "links": [
                            {
                                "label": "Clara",
                                "href": "/static/shared/clara/index.html",
                                "active": True,
                                "tooltip_key": "clara_plugin",
                                "public": True,
                            },
                        ],
                    },
                ],
            },
        ],
        "menu_links": [],
        "hero": {
            "id": "hero",
            "skip_label": "Ir al contenido principal",
            "plugins_label": "Plugins de Codex",
            "eyebrow": "Plugins de Codex para el trabajo profesional",
            "headline": "La IA aporta la potencia. Codex aporta el control.",
            "subheadline": (
                "Mparanza crea plugins de Codex. Cada uno proporciona a Codex una "
                "forma de trabajo especializada para tareas profesionales."
            ),
        },
        "harness": {
            "id": "codex",
            "title": "El entorno de trabajo cambia lo que la IA puede hacer.",
            "description": (
                "La IA aporta las capacidades. Codex las sitúa en un entorno de trabajo "
                "capaz de usar archivos, ejecutar herramientas, seguir instrucciones y "
                "crear resultados. Ese entorno es lo que entendemos por control."
            ),
            "layers": [
                {
                    "title": "Potencia",
                    "blurb": "El modelo razona, analiza y crea.",
                },
                {
                    "title": "Control",
                    "blurb": (
                        "Codex conecta esas capacidades con los archivos, las herramientas "
                        "y el contexto de la tarea."
                    ),
                },
                {
                    "title": "Uso profesional",
                    "blurb": (
                        "Un plugin de Codex define el método especializado y los resultados "
                        "esperados."
                    ),
                },
            ],
        },
        "open_source": {
            "id": "open-source",
            "title": "Abiertos por diseño.",
            "description": (
                "Vera y Clara son plugins open source para Codex. Puedes examinar "
                "los métodos, los controles y el código antes de usarlos, y adaptarlos "
                "a tu trabajo."
            ),
            "links_label": "Información sobre código abierto",
            "links": [
                {
                    "label": "Examinar el código fuente en GitHub",
                    "href": "https://github.com/fabioannovazzi/app_files",
                },
                {
                    "label": "Leer la licencia GNU AGPLv3",
                    "href": "https://github.com/fabioannovazzi/app_files/blob/main/LICENSE",
                },
            ],
        },
        "free": {
            "id": "free",
            "title": "Gratuitos por diseño.",
            "description": (
                "Vera y Clara se pueden instalar y usar gratuitamente. Agradecemos las "
                "contribuciones a su desarrollo. Cobramos por la consultoría, la "
                "implementación y los servicios alojados."
            ),
        },
        "security": {
            "id": "security",
            "title": "Seguros por diseño.",
            "lead": (
                "En los flujos ordinarios de Vera y Clara, Mparanza no recibe el trabajo de tus clientes."
            ),
            "description": (
                "Los flujos ordinarios de los plugins funcionan dentro de tu entorno de "
                "Codex actual. Los prompts, archivos y resultados de tus clientes no "
                "pasan por Mparanza."
            ),
            "cta_label": "Ver cómo se tratan tus datos",
            "cta_href": "/data-handling",
        },
        "compliance": {
            "id": "compliance",
            "title": "Conformes por diseño.",
            "lead": (
                "El trabajo profesional puede requerir que Codex lea datos reales de "
                "clientes."
            ),
            "description": (
                "Vera y Clara no anonimizan los datos automáticamente. Pueden usar Python "
                "en local para filtrar o agregar información cuando resulte útil. Los datos "
                "facilitados al modelo se tratan mediante el plan de ChatGPT que ya usa el "
                "usuario."
            ),
            "principles": [
                {
                    "title": "Usa Python en local cuando resulte útil",
                    "blurb": (
                        "El filtrado y la agregación pueden realizarse en tu ordenador "
                        "cuando mejoran el trabajo. No son anonimización automática."
                    ),
                },
                {
                    "title": "Los datos reales pueden llegar al modelo",
                    "blurb": (
                        "Los nombres, documentos, el idioma original y los hechos del caso "
                        "pueden entrar en el contexto del modelo cuando la tarea profesional "
                        "los necesita."
                    ),
                },
                {
                    "title": "Dos categorías de tratamiento",
                    "blurb": (
                        "Las funciones ordinarias de los plugins usan el plan de ChatGPT "
                        "existente. Los servicios alojados por Mparanza constituyen un "
                        "límite de tratamiento separado."
                    ),
                },
            ],
            "closing": (
                "Una política para Vera y Clara. Sin documentación para cada prompt."
            ),
            "cta_label": "Ver cómo se tratan tus datos",
            "cta_href": "/data-handling",
        },
        "bridge": {
            "id": "plugins",
            "title": "Codex por diseño.",
            "description": (
                "Mparanza es Vera y Clara: dos plugins que aplican el mismo entorno de "
                "Codex a dos profesiones distintas."
            ),
        },
    },
}


def _render_legal_page(request: Request, slug: str) -> Response:
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )
    response = templates.TemplateResponse(
        request,
        "legal_page.html",
        _template_context(
            page=get_legal_page(slug),
            active_legal_page=slug,
            copy={},
            lang="en",
        ),
    )
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@site_router.get("/zero-retention", include_in_schema=False)
def zero_retention_page(request: Request) -> Response:
    return _render_legal_page(request, "zero-retention")


@site_router.get("/privacy", include_in_schema=False)
def privacy_page_redirect() -> RedirectResponse:
    return RedirectResponse(
        url="/zero-retention",
        status_code=status.HTTP_308_PERMANENT_REDIRECT,
    )


@site_router.get("/terms", include_in_schema=False)
def terms_page(request: Request) -> Response:
    return _render_legal_page(request, "terms")


@site_router.get("/support", include_in_schema=False)
def support_page(request: Request) -> Response:
    return _render_legal_page(request, "support")


@site_router.get("/data-handling", include_in_schema=False)
def data_handling_page(request: Request) -> Response:
    """Render Mparanza's localized public data-handling position."""

    lang = resolve_language(request)
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )
    response = templates.TemplateResponse(
        request,
        "data_handling.html",
        _template_context(
            page=get_data_handling_content(lang),
            copy={},
            lang=lang,
            language_labels=LANDING_LANGUAGE_LABELS,
            language_names=LANGUAGE_LABELS,
            language_order=LANGUAGE_ORDER,
            auth_enabled=False,
            google_client_id="",
        ),
    )
    response.headers["Cache-Control"] = "public, max-age=300"
    if lang != request.cookies.get("lang"):
        response.set_cookie("lang", lang, max_age=30 * 24 * 60 * 60, httponly=False)
    return response


@site_router.get("/", include_in_schema=False)
def landing_page(request: Request) -> Any:
    try:
        lang = resolve_language(request)
    except Exception:  # pragma: no cover - fallback if geolocation fails unexpectedly
        lang = "en"
    landing_page_content = _get_landing_page_content(lang)
    primary_section = landing_page_content["primary"]
    other_sections = landing_page_content["sections"]
    menu_links = landing_page_content["menu_links"]
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )
    tooltip_map = TOOLTIP_CONTENT.get(lang, TOOLTIP_CONTENT["en"])
    response = templates.TemplateResponse(
        request,
        "index.html",
        _template_context(
            primary_section=primary_section,
            sections=other_sections,
            menu_links=menu_links,
            hero=landing_page_content["hero"],
            harness=landing_page_content["harness"],
            open_source=landing_page_content["open_source"],
            free=landing_page_content["free"],
            security=landing_page_content["security"],
            compliance=landing_page_content["compliance"],
            bridge=landing_page_content["bridge"],
            copy=get_page_copy("landing", lang),
            lang=lang,
            language_labels=LANDING_LANGUAGE_LABELS,
            language_names=LANGUAGE_LABELS,
            language_order=LANGUAGE_ORDER,
            language_tooltips=tooltip_map,
            beta_links=BETA_LINKS,
            auth_enabled=False,
            google_client_id="",
        ),
    )
    cookie_lang = request.cookies.get("lang")
    if lang != cookie_lang:
        response.set_cookie("lang", lang, max_age=30 * 24 * 60 * 60, httponly=False)
    return response


@router.get("/retailers", response_model=RetailerResponse)
def list_review_retailers() -> RetailerResponse:
    _raise_if_review_reads_blocked_by_ocr()
    tables = _get_tables()
    retailers = list_retailers(tables)
    brands = list_brands(tables)
    return RetailerResponse(retailers=retailers, brands=brands)


@router.get("/categories", response_model=CategoryResponse)
def list_review_categories(
    retailer: Optional[List[str]] = Query(None),
    brands: Optional[List[str]] = Query(None),
) -> CategoryResponse:
    _raise_if_review_reads_blocked_by_ocr()
    tables = _get_tables()
    tables = filter_tables_by_retailer(tables, retailer)
    tables = filter_tables_by_brands(tables, brands or [])

    taxonomy = get_attribute_taxonomy()
    category_lookup = build_category_lookup(taxonomy)
    options = category_options_for_tables(category_lookup, tables)
    items = [CategoryItem(key=key, label=label) for label, key in options]
    return CategoryResponse(categories=items)


@router.get(
    "/sales/datasets",
    response_model=SalesDatasetsResponse,
    dependencies=[Depends(require_authenticated_user)],
)
def list_sales_datasets_endpoint(
    request: Request,
    dataset: str | None = Query(None),
) -> SalesDatasetsResponse:
    user = maybe_current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    allowed_datasets = _allowed_sales_datasets_for_user(user.email)
    if not allowed_datasets:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access any sales dataset.",
        )

    selected_dataset = _select_sales_dataset(
        requested_dataset=get_sales_dataset_name(dataset),
        allowed_datasets=allowed_datasets,
    )
    allowed_download_datasets = _allowed_sales_download_datasets_for_user(user.email)

    items = [
        SalesDatasetItem(
            key=name,
            label=_sales_dataset_label(name),
            download_allowed=name in allowed_download_datasets,
        )
        for name in allowed_datasets
    ]
    return SalesDatasetsResponse(
        selected_dataset=selected_dataset,
        datasets=items,
    )


@router.get(
    "/sales/retailers",
    response_model=RetailerResponse,
    dependencies=[SALES_DATASET_PERMISSION],
)
def list_sales_retailers_endpoint(
    dataset: str | None = Query(None),
) -> RetailerResponse:
    """Return retailer options scoped to the selected sales dataset."""

    sales_frame = load_full_sales_data(None, dataset=dataset)
    if sales_frame.is_empty():
        return RetailerResponse(retailers=[], brands=[])

    columns, _schema = get_schema_and_column_names(sales_frame)
    merchant_column = "merchant" if "merchant" in columns else None
    if merchant_column is None and "retailer" in columns:
        merchant_column = "retailer"
    if merchant_column is None:
        return RetailerResponse(retailers=[], brands=[])

    retailers = (
        sales_frame.select(
            pl.col(merchant_column)
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("retailer_norm")
        )
        .drop_nulls(subset=["retailer_norm"])
        .filter(pl.col("retailer_norm") != "")
        .get_column("retailer_norm")
        .unique()
        .sort()
        .to_list()
    )
    retailer_values = [str(value) for value in retailers]
    return RetailerResponse(retailers=retailer_values, brands=[])


@router.get(
    "/sales/categories",
    response_model=CategoryResponse,
    dependencies=[SALES_DATASET_PERMISSION],
)
def list_sales_categories_endpoint(
    retailer: Optional[List[str]] = Query(None),
    brands: Optional[List[str]] = Query(None, alias="brand"),
    dataset: str | None = Query(None),
) -> CategoryResponse:
    retailers = retailer or []
    sales_frame = load_full_sales_data(None, dataset=dataset)
    if sales_frame.is_empty():
        return CategoryResponse(categories=[])
    tables = _get_tables()
    tables = filter_tables_by_retailer(tables, retailers)
    tables = filter_tables_by_brands(tables, brands or [])
    sales_frame = _overlay_sales_category_with_catalog_labels(
        sales_frame, variants=tables.variants
    )

    taxonomy = get_attribute_taxonomy()
    category_lookup = build_category_lookup(taxonomy)
    options = category_options_for_tables(category_lookup, tables)

    allowed_labels = {
        label.lower() for label in sales_categories(sales_frame, retailers)
    }
    items = [
        CategoryItem(key=key, label=label)
        for label, key in options
        if isinstance(label, str) and label.lower() in allowed_labels
    ]
    return CategoryResponse(categories=items)


@router.get("/brands", response_model=BrandsResponse)
def list_review_brands_endpoint(
    request: Request,
    retailer: Optional[List[str]] = Query(None),
    category_keys: Optional[List[str]] = Query(None, alias="category"),
    view: Optional[str] = Query(None),
    dataset: str | None = Query(None),
) -> BrandsResponse:
    normalized_keys = _normalize_category_keys(category_keys or [])
    view_mode = (view or "").strip().lower()

    if view_mode == "sales" and normalized_keys:
        require_sales_dataset_permission_for_request(request)
        attr_tables = _get_tables()
        attr_tables = filter_tables_by_retailer(attr_tables, retailer)
        attr_tables = filter_tables_by_categories(attr_tables, normalized_keys)
        attr_brands = list_brands(attr_tables)
        attr_brands_lower = {b.lower(): b for b in attr_brands if isinstance(b, str)}

        sales_frame = load_full_sales_data(None, dataset=dataset)
        if not sales_frame.is_empty():
            sales_frame = _overlay_sales_category_with_catalog_labels(
                sales_frame, variants=attr_tables.variants
            )
            category_lookup = build_category_lookup(get_attribute_taxonomy())
            label_set = {
                lbl.lower()
                for lbl in _category_labels_from_keys(category_lookup, normalized_keys)
                if lbl
            }
            key_set = {key.lower() for key in normalized_keys if key}
            category_filter = label_set.union(key_set)

            sales_df = sales_frame
            if retailer:
                targets = {str(r).lower() for r in retailer}
                if targets:
                    sales_df = sales_df.filter(pl.col("merchant").is_in(list(targets)))
            if category_filter:
                sales_df = sales_df.filter(
                    pl.col("category").str.to_lowercase().is_in(list(category_filter))
                )

            if not sales_df.is_empty():
                filtered_sales = (
                    sales_df.group_by("brand")
                    .agg(pl.col("sales").sum().alias("total_sales"))
                    .filter(pl.col("total_sales") > 0)
                )
                sales_lower = {
                    repair_text_encoding(str(value).strip()).lower()
                    for value in filtered_sales.get_column("brand").to_list()
                    if isinstance(value, str) and value.strip()
                }
                brands = [
                    attr_brands_lower[b_lower]
                    for b_lower in sales_lower
                    if b_lower in attr_brands_lower
                ]
                return BrandsResponse(brands=sorted(set(brands)))

        return BrandsResponse(brands=[])

    # Catalog view or missing slice: use attribute tables without sales gating.
    tables = _get_tables()
    tables = filter_tables_by_retailer(tables, retailer)
    if normalized_keys:
        tables = filter_tables_by_categories(tables, normalized_keys)
    brands = list_brands(tables)
    return BrandsResponse(brands=brands)


@router.get("/brands/relevant", response_model=BrandsResponse)
def list_relevant_brands_endpoint(
    retailer: Optional[List[str]] = Query(None),
    category_keys: Optional[List[str]] = Query(None, alias="category"),
    record_type: str = Query("parent", pattern="^(parent|variant)$"),
    attribute_id: str = Query(..., min_length=1),
    analysis: str = Query("na", pattern="^(na|not_in_taxonomy|found)$"),
) -> BrandsResponse:
    _raise_if_review_reads_blocked_by_ocr()
    selected_keys = _normalize_category_keys(category_keys or [])
    if not selected_keys:
        return BrandsResponse(brands=[])

    tables = _get_tables_for_coverage()
    tables = filter_tables_by_retailer(tables, retailer)
    tables = filter_tables_by_categories(tables, selected_keys)

    parent_source = (
        tables.parents_all if not tables.parents_all.is_empty() else tables.parents
    )
    tables_for_filters = ReviewTables(
        parents=parent_source,
        variants=tables.variants,
        combined=tables.combined,
        parents_all=tables.parents_all,
    )

    taxonomy = get_attribute_taxonomy()
    category_lookup = build_category_lookup(taxonomy)
    filter_setup = prepare_attribute_filters(
        tables_for_filters, category_lookup, selected_keys
    )
    if (
        not filter_setup.attr_column_lookup
        or attribute_id not in filter_setup.attr_column_lookup
    ):
        return BrandsResponse(brands=[])

    if record_type == "variant":
        display_df = tables.variants
    else:
        display_df = parent_source

    if display_df.is_empty():
        return BrandsResponse(brands=[])

    filter_value = _analysis_filter_value(analysis)
    filter_map = _parse_attribute_filters([f"{attribute_id}:{filter_value}"])
    if filter_map:
        display_df = apply_attribute_filters(
            display_df,
            filter_map,
            filter_setup.attr_column_lookup,
            placeholder_values=filter_setup.placeholder_values,
        )

    columns, _ = get_schema_and_column_names(display_df)
    if "brand" not in columns:
        return BrandsResponse(brands=[])

    brand_values = {
        repair_text_encoding(str(value).strip())
        for value in display_df.get_column("brand").unique().to_list()
        if isinstance(value, str) and value.strip()
    }
    return BrandsResponse(brands=sorted(brand_values))


@router.get("/filters", response_model=AttributeMetadataResponse)
def fetch_attribute_metadata(
    retailer: Optional[List[str]] = Query(None),
    category_keys: List[str] = Query(..., alias="category"),
    brands: Optional[List[str]] = Query(None, alias="brand"),
    filters: Optional[List[str]] = Query(None),
    pareto: Optional[List[str]] = Query(None, description="Pareto buckets A/B/C"),
    price_band: Optional[List[str]] = Query(None, alias="price_band"),
    also_blush: Optional[List[str]] = Query(None, alias="also_blush"),
    also_highlighter: Optional[List[str]] = Query(None, alias="also_highlighter"),
    also_cheek: Optional[List[str]] = Query(None, alias="also_cheek"),
    also_eyeliner: Optional[List[str]] = Query(None, alias="also_eyeliner"),
    record_type: str = Query("parent", pattern="^(parent|variant)$"),
) -> AttributeMetadataResponse:
    selected_keys = _normalize_category_keys(category_keys)
    if not selected_keys:
        raise HTTPException(
            status_code=400, detail="At least one category key is required."
        )

    tables = _get_tables()
    tables = filter_tables_by_retailer(tables, retailer)
    tables = filter_tables_by_brands(tables, brands or [])
    tables = filter_tables_by_categories(tables, selected_keys)

    parent_source = (
        tables.parents_all if not tables.parents_all.is_empty() else tables.parents
    )
    if record_type == "variant":
        filter_tables = ReviewTables(
            parents=parent_source,
            variants=tables.variants,
            combined=(
                tables.variants if not tables.variants.is_empty() else tables.combined
            ),
            parents_all=tables.parents_all,
        )
    else:
        filter_tables = ReviewTables(
            parents=parent_source,
            variants=tables.variants,
            combined=tables.combined,
            parents_all=tables.parents_all,
        )

    taxonomy = get_attribute_taxonomy()
    category_lookup = build_category_lookup(taxonomy)
    filter_setup = prepare_attribute_filters(
        filter_tables, category_lookup, selected_keys
    )

    placeholder_set = {
        str(value).strip().lower() for value in filter_setup.placeholder_values
    }
    placeholder_list = sorted(placeholder_set)
    filter_frame = filter_setup.filter_source
    hybrid_filter_selection = _build_hybrid_filter_selection(
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
    )

    filter_map = _parse_attribute_filters(filters or None)
    if filter_map and filter_setup.attr_column_lookup:
        filter_frame = apply_attribute_filters(
            filter_frame,
            filter_map,
            filter_setup.attr_column_lookup,
            placeholder_values=filter_setup.placeholder_values,
        )

    def _apply_special_filters(
        df: pl.DataFrame, *, apply_hybrid_filters: bool = True
    ) -> pl.DataFrame:
        if df.is_empty():
            return df
        result = df
        if price_band:
            allowed = {
                str(val).strip().lower() for val in price_band if str(val).strip()
            }
            if allowed and "price_band" in result.columns:
                result = result.filter(
                    pl.col("price_band")
                    .cast(pl.Utf8)
                    .str.to_lowercase()
                    .is_in(list(allowed))
                )
        if apply_hybrid_filters:
            result = _apply_hybrid_filters(
                result,
                selection=hybrid_filter_selection,
            )
        return result

    try:
        filter_frame, _ = _annotate_records_with_sales_and_price(
            filter_frame,
            tables,
            retailer,
            selected_keys,
            record_type,
        )
    except Exception:
        filter_frame = filter_frame
    special_filter_frame = _apply_special_filters(
        filter_frame, apply_hybrid_filters=False
    )
    hybrid_values = _collect_hybrid_values(special_filter_frame)
    also_blush_values = hybrid_values.get("also_blush", [])

    filter_frame = _apply_special_filters(filter_frame)

    filter_columns = set(filter_frame.columns) if not filter_frame.is_empty() else set()

    def _valid_attribute_value_expr(column_name: str) -> pl.Expr:
        text_expr = pl.col(column_name).cast(pl.Utf8).str.strip_chars()
        lowered_expr = text_expr.str.to_lowercase()
        return (
            text_expr.is_not_null()
            & (text_expr != "")
            & ~lowered_expr.is_in(placeholder_list)
            & ~lowered_expr.str.starts_with("not in taxonomy")
        )

    def _is_placeholder_text(value: str) -> bool:
        lowered = str(value).strip().lower()
        return lowered in placeholder_set or lowered.startswith("not in taxonomy")

    key_candidates = (
        ("variant_id", "sku", "variant", "product")
        if record_type == "variant"
        else ("parent_product_id", "product", "sku")
    )
    key_column = next((name for name in key_candidates if name in filter_columns), None)
    record_key_expr: pl.Expr | None = None
    if key_column is not None:
        base_key_expr = pl.col(key_column).cast(pl.Utf8).str.strip_chars()
        if "retailer" in filter_columns:
            retailer_expr = pl.col("retailer").cast(pl.Utf8).str.strip_chars()
            record_key_expr = (
                pl.when(retailer_expr.is_not_null() & (retailer_expr != ""))
                .then(retailer_expr + pl.lit("::") + base_key_expr)
                .otherwise(base_key_expr)
            )
        else:
            record_key_expr = base_key_expr

    total_records = 0
    if not filter_frame.is_empty():
        if record_key_expr is not None:
            total_records = (
                filter_frame.select(record_key_expr.alias("_record_key"))
                .filter(
                    pl.col("_record_key").is_not_null() & (pl.col("_record_key") != "")
                )
                .unique()
                .height
            )
        if total_records <= 0:
            total_records = get_row_count(filter_frame)

    price_band_values: List[str] = []
    try:
        target_df = (
            filter_tables.variants
            if record_type == "variant"
            else (
                filter_tables.parents_all
                if not filter_tables.parents_all.is_empty()
                else filter_tables.parents
            )
        )
        if target_df is not None and not target_df.is_empty():
            if filter_map and filter_setup.attr_column_lookup:
                target_df = apply_attribute_filters(
                    target_df,
                    filter_map,
                    filter_setup.attr_column_lookup,
                    placeholder_values=filter_setup.placeholder_values,
                )
            try:
                target_df, _ = _annotate_records_with_sales_and_price(
                    target_df,
                    tables,
                    retailer,
                    selected_keys,
                    record_type,
                )
            except Exception:
                target_df = target_df
            target_df = _apply_special_filters(target_df)
            if "price_band" in target_df.columns:
                vals = (
                    target_df.get_column("price_band").drop_nulls().unique().to_list()
                )
                price_band_values = sorted(
                    {str(v).strip() for v in vals if str(v).strip()}
                )
    except Exception:
        price_band_values = []

    attributes: List[AttributeOption] = []
    for attr in filter_setup.valid_attributes:
        attr_id = str(attr["id"])
        attr_label = str(attr["label"])
        column_name = str(attr["column"])
        if column_name not in filter_columns:
            continue
        raw_values = (
            filter_frame.get_column(column_name).to_list()
            if not filter_frame.is_empty() and column_name in filter_frame.columns
            else []
        )
        value_buffer: List[str] = []
        seen: set[str] = set()
        for value in raw_values:
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            value_buffer.append(text)

        include_na = False
        if column_name and column_name in filter_columns:
            series = filter_frame.get_column(column_name)
            for item in series.to_list():
                if item is None:
                    include_na = True
                    break
                if isinstance(item, str) and _is_placeholder_text(item):
                    include_na = True
                    break

        if include_na and "N/A" not in value_buffer:
            value_buffer.append("N/A")

        value_buffer.sort(key=lambda item: item.lower())

        non_placeholder_records = 0
        distinct_non_placeholder_values = 0
        if not filter_frame.is_empty():
            valid_value_expr = _valid_attribute_value_expr(column_name)
            if record_key_expr is not None:
                non_placeholder_records = (
                    filter_frame.filter(valid_value_expr)
                    .select(record_key_expr.alias("_record_key"))
                    .filter(
                        pl.col("_record_key").is_not_null()
                        & (pl.col("_record_key") != "")
                    )
                    .unique()
                    .height
                )
            else:
                non_placeholder_records = filter_frame.filter(valid_value_expr).height

            distinct_non_placeholder_values = (
                filter_frame.filter(valid_value_expr)
                .select(
                    pl.col(column_name)
                    .cast(pl.Utf8)
                    .str.strip_chars()
                    .str.to_lowercase()
                    .alias("_attribute_value")
                )
                .unique()
                .height
            )

        coverage_pct = (
            float(non_placeholder_records) / float(total_records)
            if total_records > 0
            else 0.0
        )

        attributes.append(
            AttributeOption(
                id=attr_id,
                label=attr_label,
                column=column_name,
                values=value_buffer,
                active=bool(attr["active"]),
                coverage_pct=coverage_pct,
                non_placeholder_records=non_placeholder_records,
                total_records=total_records,
                distinct_non_placeholder_values=distinct_non_placeholder_values,
            )
        )
    return AttributeMetadataResponse(
        placeholder_values=sorted(filter_setup.placeholder_values),
        attributes=attributes,
        price_band_values=price_band_values,
        also_blush_values=also_blush_values,
        hybrid_values=hybrid_values,
    )


def _attach_coverage_confidence_metrics(
    report: dict[str, Any],
    *,
    frame: pl.DataFrame,
    record_type: str,
    placeholder_values: Sequence[str],
) -> None:
    attributes_raw = report.get("attributes")
    if not isinstance(attributes_raw, list) or not attributes_raw or frame.is_empty():
        return
    if "retailer" not in frame.columns or "parent_product_id" not in frame.columns:
        return

    column_to_attr: dict[str, str] = {}
    for entry in attributes_raw:
        if not isinstance(entry, dict):
            continue
        attr_id = str(entry.get("id") or "").strip()
        column = str(entry.get("column") or "").strip()
        if not attr_id or not column or column not in frame.columns:
            continue
        if column in column_to_attr:
            continue
        column_to_attr[column] = attr_id
    if not column_to_attr:
        return

    placeholder_set = {
        str(value).strip().lower() for value in placeholder_values if str(value).strip()
    }

    selected = frame.select(
        [
            pl.col("retailer")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .alias("retailer"),
            pl.col("parent_product_id")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .alias("parent_product_id"),
            (
                pl.col("variant_id").cast(pl.Utf8, strict=False).fill_null("")
                if "variant_id" in frame.columns
                else pl.lit("")
            ).alias("variant_id"),
            *[pl.col(column).alias(column) for column in column_to_attr],
        ]
    )
    if selected.is_empty():
        return

    melted = selected.unpivot(
        index=["retailer", "parent_product_id", "variant_id"],
        on=list(column_to_attr.keys()),
        variable_name="attribute_column",
        value_name="value",
    )
    if melted.is_empty():
        return

    filtered_values = (
        melted.with_columns(
            [
                pl.col("attribute_column")
                .replace(column_to_attr)
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .alias("attribute_id"),
                pl.col("value")
                .cast(pl.Utf8, strict=False)
                .str.strip_chars()
                .alias("_value"),
            ]
        )
        .with_columns(pl.col("_value").str.to_lowercase().alias("_value_lc"))
        .filter(
            (pl.col("attribute_id") != "")
            & (pl.col("retailer") != "")
            & (pl.col("parent_product_id") != "")
            & pl.col("_value").is_not_null()
            & (pl.col("_value") != "")
            & ~pl.col("_value_lc").is_in(list(placeholder_set))
            & ~pl.col("_value_lc").str.starts_with("not in taxonomy")
        )
        .select(
            ["retailer", "parent_product_id", "variant_id", "attribute_id", "_value"]
        )
        .group_by(
            ["retailer", "parent_product_id", "variant_id", "attribute_id"],
            maintain_order=True,
        )
        .agg(pl.col("_value").first().alias("_value"))
    )
    if filtered_values.is_empty():
        return

    values_by_attr: dict[str, dict[tuple[str, str, str], str]] = {}
    for row in filtered_values.to_dicts():
        attr_id = str(row.get("attribute_id") or "").strip()
        retailer = str(row.get("retailer") or "").strip()
        parent_id = str(row.get("parent_product_id") or "").strip()
        variant_id = str(row.get("variant_id") or "").strip()
        value = str(row.get("_value") or "").strip()
        if not attr_id or not retailer or not parent_id or not value:
            continue
        key = (retailer, parent_id, variant_id)
        values_by_attr.setdefault(attr_id, {})[key] = value
    if not values_by_attr:
        return

    store: PDPStore | None = None
    store_init_attempted = False

    def _coerce_support_total(
        payload: Mapping[str, Any] | None,
    ) -> tuple[float, float] | None:
        if not isinstance(payload, Mapping):
            return None
        support_raw = payload.get("support_runs")
        total_raw = payload.get("total_runs")
        if not isinstance(support_raw, (int, float)) or not isinstance(
            total_raw, (int, float)
        ):
            return None
        support = float(support_raw)
        total = float(total_raw)
        if total <= 0.0:
            return None
        return support, total

    def _collect_audit_rows_by_key(
        *,
        attribute_candidates: Sequence[str],
        keys: Sequence[tuple[str, str, str]],
    ) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
        nonlocal store, store_init_attempted
        if not attribute_candidates or not keys:
            return {}
        if not store_init_attempted:
            store_init_attempted = True
            try:
                store = PDPStore(DEFAULT_PDP_STORE_PATH)
            except RuntimeError:
                store = None
        if store is None:
            return {}
        key_set = set(keys)
        seen_rows: set[tuple[Any, ...]] = set()
        rows_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for candidate_attr_id in attribute_candidates:
            try:
                candidate_rows = store.fetch_attribute_audit_rows(
                    attribute_id=candidate_attr_id,
                    row_type=record_type,
                    keys=keys,
                )
            except RuntimeError:
                candidate_rows = []
            for row in candidate_rows:
                key = (
                    str(row.get("retailer") or "").strip(),
                    str(row.get("parent_product_id") or "").strip(),
                    str(row.get("variant_id") or "").strip(),
                )
                if key not in key_set:
                    continue
                dedupe_key = (
                    key[0],
                    key[1],
                    key[2],
                    row.get("timestamp"),
                    row.get("source"),
                    row.get("attribute_id"),
                    row.get("value"),
                    row.get("decision_rule"),
                )
                if dedupe_key in seen_rows:
                    continue
                seen_rows.add(dedupe_key)
                rows_by_key.setdefault(key, []).append(row)
        return rows_by_key

    for entry in attributes_raw:
        if not isinstance(entry, dict):
            continue
        attr_id = str(entry.get("id") or "").strip()
        attr_column = str(entry.get("column") or "").strip()
        key_to_value = values_by_attr.get(attr_id)
        if not key_to_value:
            continue

        keys = list(key_to_value.keys())
        attribute_candidates = _attribute_id_candidates(attr_id, attr_column)
        if not attribute_candidates:
            attribute_candidates = [attr_id]

        consensus_map = _collect_consensus_map(
            attribute_candidates=attribute_candidates,
            row_type=record_type,
            keys=keys,
        )
        support_total_pairs: list[tuple[float, float]] = []
        unresolved_keys: list[tuple[str, str, str]] = []
        for key in keys:
            consensus_pair = _coerce_support_total(consensus_map.get(key))
            if consensus_pair is not None:
                support_total_pairs.append(consensus_pair)
                continue
            unresolved_keys.append(key)

        if unresolved_keys:
            audit_rows_by_key = _collect_audit_rows_by_key(
                attribute_candidates=attribute_candidates,
                keys=unresolved_keys,
            )
            for key in unresolved_keys:
                payload = {
                    "value": key_to_value.get(key),
                    "source": None,
                }
                history_rows = audit_rows_by_key.get(key, [])
                if not _attach_history_metrics_from_audit_rows(payload, history_rows):
                    continue
                history_pair = _coerce_support_total(payload)
                if history_pair is not None:
                    support_total_pairs.append(history_pair)

        if not support_total_pairs:
            continue

        sample_count = len(support_total_pairs)
        support_sum = sum(support for support, _ in support_total_pairs)
        total_sum = sum(total for _, total in support_total_pairs)
        entry["confidence_support_avg"] = support_sum / float(sample_count)
        entry["confidence_total_avg"] = total_sum / float(sample_count)
        if total_sum > 0.0:
            entry["confidence_pct"] = support_sum / total_sum
        entry["confidence_samples"] = sample_count


@router.get("/coverage", response_model=CoverageReportResponse)
def fetch_attribute_coverage(
    retailer: Optional[List[str]] = Query(None),
    category_keys: List[str] = Query(..., alias="category"),
    brands: Optional[List[str]] = Query(None, alias="brand"),
    filters: Optional[List[str]] = Query(None),
    pareto: Optional[List[str]] = Query(None, description="Pareto buckets A/B/C"),
    price_band: Optional[List[str]] = Query(None, alias="price_band"),
    also_blush: Optional[List[str]] = Query(None, alias="also_blush"),
    also_highlighter: Optional[List[str]] = Query(None, alias="also_highlighter"),
    also_cheek: Optional[List[str]] = Query(None, alias="also_cheek"),
    also_eyeliner: Optional[List[str]] = Query(None, alias="also_eyeliner"),
    record_type: str = Query("parent", pattern="^(parent|variant)$"),
) -> CoverageReportResponse:
    _raise_if_review_reads_blocked_by_ocr()
    selected_keys = _normalize_category_keys(category_keys)
    if not selected_keys:
        raise HTTPException(
            status_code=400, detail="At least one category key is required."
        )

    tables = _get_tables_for_coverage()
    source = "postfill_stage_overlay"
    tables = filter_tables_by_retailer(tables, retailer)
    tables = filter_tables_by_brands(tables, brands or [])
    tables = filter_tables_by_categories(tables, selected_keys)

    parent_source = (
        tables.parents_all if not tables.parents_all.is_empty() else tables.parents
    )
    if record_type == "variant":
        filter_tables = ReviewTables(
            parents=parent_source,
            variants=tables.variants,
            combined=(
                tables.variants if not tables.variants.is_empty() else tables.combined
            ),
            parents_all=tables.parents_all,
        )
        target_df = (
            tables.variants if not tables.variants.is_empty() else tables.combined
        )
    else:
        filter_tables = ReviewTables(
            parents=parent_source,
            variants=tables.variants,
            combined=tables.combined,
            parents_all=tables.parents_all,
        )
        target_df = parent_source

    taxonomy = get_attribute_taxonomy()
    category_lookup = build_category_lookup(taxonomy)
    filter_setup = prepare_attribute_filters(
        filter_tables, category_lookup, selected_keys
    )

    filter_map = _parse_attribute_filters(filters or None)
    if filter_map and filter_setup.attr_column_lookup:
        target_df = apply_attribute_filters(
            target_df,
            filter_map,
            filter_setup.attr_column_lookup,
            placeholder_values=filter_setup.placeholder_values,
        )
    hybrid_filter_selection = _build_hybrid_filter_selection(
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
    )

    def _apply_special_filters(df: pl.DataFrame) -> pl.DataFrame:
        if df.is_empty():
            return df
        result = df
        if price_band:
            allowed = {
                str(val).strip().lower() for val in price_band if str(val).strip()
            }
            if allowed and "price_band" in result.columns:
                result = result.filter(
                    pl.col("price_band")
                    .cast(pl.Utf8)
                    .str.to_lowercase()
                    .is_in(list(allowed))
                )
        return _apply_hybrid_filters(result, selection=hybrid_filter_selection)

    try:
        target_df, _ = _annotate_records_with_sales_and_price(
            target_df,
            tables,
            retailer,
            selected_keys,
            record_type,
        )
    except Exception:
        target_df = target_df
    target_df = _apply_special_filters(target_df)

    report = compute_attribute_coverage_report(
        target_df,
        filter_setup,
        category_lookup,
    )
    _attach_coverage_confidence_metrics(
        report,
        frame=target_df,
        record_type=record_type,
        placeholder_values=filter_setup.placeholder_values,
    )
    report["source"] = source
    return CoverageReportResponse(**report)


@router.get("/taxonomy/branch", response_model=TaxonomyBranchResponse)
def fetch_taxonomy_branch(
    category: str = Query(
        ..., description="Category key or label for the taxonomy branch."
    ),
    attribute_id: str = Query(
        ..., description="Attribute id or label for the taxonomy branch."
    ),
) -> TaxonomyBranchResponse:
    _raise_if_review_reads_blocked_by_ocr()
    normalized = _normalize_category_keys([category])
    if not normalized:
        raise HTTPException(status_code=400, detail="A valid category key is required.")
    taxonomy = get_attribute_taxonomy()
    category_lookup = build_category_lookup(taxonomy)
    category_meta = category_lookup.get(normalized[0])
    if not category_meta:
        category_meta = _find_category_meta(taxonomy, category)
    if not category_meta:
        raise HTTPException(status_code=404, detail="Category not found in taxonomy.")
    attributes = category_meta.get("attributes") or []
    attr_match: Mapping[str, object] | None = None
    target = _normalize_taxonomy_identifier(attribute_id)
    for attr in attributes:
        if not isinstance(attr, Mapping):
            continue
        attr_id = _normalize_taxonomy_identifier(str(attr.get("id") or ""))
        attr_label = _normalize_taxonomy_identifier(str(attr.get("label") or ""))
        if attr_id == target or attr_label == target:
            attr_match = attr
            break
    if not attr_match:
        raise HTTPException(status_code=404, detail="Attribute not found in taxonomy.")
    nodes = _flatten_taxonomy_nodes(_coerce_taxonomy_nodes(attr_match))
    resolved_label = str(
        attr_match.get("label") or attr_match.get("id") or attribute_id
    ).strip()
    resolved_id = str(attr_match.get("id") or attribute_id).strip()
    return TaxonomyBranchResponse(
        attribute_id=resolved_id,
        attribute_label=resolved_label,
        nodes=nodes,
    )


@router.get("/records", response_model=RecordsResponse)
def fetch_records(
    retailer: Optional[List[str]] = Query(None),
    category_keys: List[str] = Query(..., alias="category"),
    brands: Optional[List[str]] = Query(None, alias="brand"),
    record_type: str = Query("parent", pattern="^(parent|variant)$"),
    filters: Optional[List[str]] = Query(None),
    limit: int = Query(24, ge=1, le=500),
    pareto: Optional[List[str]] = Query(None, description="Pareto buckets A/B/C"),
    price_band: Optional[List[str]] = Query(
        None, description="Price band premium/mid/value"
    ),
    also_blush: Optional[List[str]] = Query(None, alias="also_blush"),
    also_highlighter: Optional[List[str]] = Query(None, alias="also_highlighter"),
    also_cheek: Optional[List[str]] = Query(None, alias="also_cheek"),
    also_eyeliner: Optional[List[str]] = Query(None, alias="also_eyeliner"),
    audit_attribute_id: Optional[str] = Query(None, alias="audit_attribute_id"),
) -> RecordsResponse:
    _raise_if_review_reads_blocked_by_ocr()
    hybrid_filter_selection = _build_hybrid_filter_selection(
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
    )
    return _gather_records(
        retailer=retailer,
        category_keys=category_keys,
        brands=brands or [],
        record_type=record_type,
        filters=filters or [],
        limit=limit,
        download_all=False,
        pareto_filter=pareto or [],
        price_band_filter=price_band or [],
        hybrid_filter_selection=hybrid_filter_selection,
        audit_attribute_id=audit_attribute_id,
    )


@router.get("/records/download", response_model=RecordsResponse)
def download_records(
    retailer: Optional[List[str]] = Query(None),
    category_keys: List[str] = Query(..., alias="category"),
    brands: Optional[List[str]] = Query(None, alias="brand"),
    record_type: str = Query("parent", pattern="^(parent|variant)$"),
    filters: Optional[List[str]] = Query(None),
    pareto: Optional[List[str]] = Query(None, description="Pareto buckets A/B/C"),
    price_band: Optional[List[str]] = Query(
        None, description="Price band premium/mid/value"
    ),
    also_blush: Optional[List[str]] = Query(None, alias="also_blush"),
    also_highlighter: Optional[List[str]] = Query(None, alias="also_highlighter"),
    also_cheek: Optional[List[str]] = Query(None, alias="also_cheek"),
    also_eyeliner: Optional[List[str]] = Query(None, alias="also_eyeliner"),
) -> RecordsResponse:
    hybrid_filter_selection = _build_hybrid_filter_selection(
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
    )
    return _gather_records(
        retailer=retailer,
        category_keys=category_keys,
        brands=brands or [],
        record_type=record_type,
        filters=filters or [],
        limit=None,
        download_all=True,
        pareto_filter=pareto or [],
        price_band_filter=price_band or [],
        hybrid_filter_selection=hybrid_filter_selection,
        audit_attribute_id=None,
    )


def _normalize_text_list(
    values: Any, *, lower: bool = False, upper: bool = False
) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        if lower:
            text = text.lower()
        elif upper:
            text = text.upper()
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _parse_attribute_filter_tokens(raw_filters: Any) -> list[str]:
    tokens: list[str] = []
    if isinstance(raw_filters, list):
        for token in raw_filters:
            text = str(token or "").strip()
            if ":" not in text:
                continue
            attr_id, _, values_part = text.partition(":")
            attr_id = attr_id.strip()
            values = [v.strip() for v in values_part.split("|") if v.strip()]
            if not attr_id or not values:
                continue
            tokens.append(f"{attr_id}:{'|'.join(values)}")
        return tokens
    if isinstance(raw_filters, Mapping):
        for attr_id, values in raw_filters.items():
            attr_key = str(attr_id or "").strip()
            if not attr_key or not isinstance(values, list):
                continue
            cleaned = [str(v).strip() for v in values if str(v).strip()]
            if not cleaned:
                continue
            tokens.append(f"{attr_key}:{'|'.join(cleaned)}")
    return tokens


def _chart_payload_value(chart_data: Mapping[str, Any], key: str) -> Any:
    direct = chart_data.get(key)
    if direct is not None:
        return direct
    payload = chart_data.get("payload")
    if isinstance(payload, Mapping):
        return payload.get(key)
    return None


_SALES_VIEW_CHART_ID_PREFIXES = frozenset(
    {
        "stacked",
        "stacked-facets",
        "stacked-abs",
        "combo-total-abs",
        "slope",
        "slope-facets",
    }
)
_SALES_VIEW_SHORTCUT_DIMS = frozenset({"retailer", "brand", "pareto", "price_band"})
_SALES_VIEW_ALLOWED_METRICS = frozenset({"sales", "units", "price"})


def _infer_dataset_from_chart_id(chart_id: str) -> str | None:
    prefix = str(chart_id or "").split("_", 1)[0].strip().lower()
    if not prefix or prefix in _SALES_VIEW_CHART_ID_PREFIXES:
        return None
    inferred = prefix.replace("-", "_").strip()
    return inferred or None


def _resolve_sales_view_from_brief_chart(
    chart_id: str, chart_data: Mapping[str, Any], meta: Mapping[str, Any] | None
) -> dict[str, Any]:
    job_scope = meta.get("job_scope") if isinstance(meta, Mapping) else None
    if not isinstance(job_scope, Mapping):
        job_scope = {}

    dataset = str(job_scope.get("dataset") or "").strip().lower() or None
    if not dataset:
        dataset = _infer_dataset_from_chart_id(chart_id)

    retailers = _normalize_text_list(chart_data.get("retailers"))
    if not retailers:
        retailers = _normalize_text_list(job_scope.get("retailers"))

    category = str(chart_data.get("category_key") or "").strip()
    if not category:
        category = str(job_scope.get("category") or "").strip()

    brands = _normalize_text_list(job_scope.get("brands"))
    if not brands:
        brands = _normalize_text_list(chart_data.get("brands"))

    pareto = _normalize_text_list(job_scope.get("pareto"), upper=True)
    price_bands = _normalize_text_list(job_scope.get("price_bands"), lower=True)
    attribute_filters = _parse_attribute_filter_tokens(
        job_scope.get("attribute_filters")
    )

    dimensions: list[str] = []
    seen_dims: set[str] = set()
    raw_dims = chart_data.get("dimensions")
    if isinstance(raw_dims, list):
        for item in raw_dims:
            if not isinstance(item, Mapping):
                continue
            dim_id = str(item.get("id") or "").strip()
            if not dim_id:
                continue
            dim_key = dim_id.lower()
            if dim_key in seen_dims:
                continue
            seen_dims.add(dim_key)
            dimensions.append(dim_id)
    facet = chart_data.get("facet")
    if isinstance(facet, Mapping):
        facet_id = str(facet.get("id") or "").strip()
        facet_key = facet_id.lower()
        if facet_id and facet_key not in seen_dims:
            seen_dims.add(facet_key)
            dimensions.append(facet_id)

    chart_type = str(chart_data.get("chart_type") or "").strip().lower()
    period_mode = "rolling_12"
    month = ""
    metrics: list[str] = ["sales"]

    if chart_type in {"area", "stacked_column"}:
        period_mode = "single_month"
        if chart_type == "stacked_column":
            bar_metric = (
                str(_chart_payload_value(chart_data, "bar_metric") or "")
                .strip()
                .lower()
            )
            line_metric = (
                str(_chart_payload_value(chart_data, "line_metric") or "")
                .strip()
                .lower()
            )
            if bar_metric or line_metric:
                combo_metrics = []
                if bar_metric in _SALES_VIEW_ALLOWED_METRICS:
                    combo_metrics.append(bar_metric)
                if (
                    line_metric in _SALES_VIEW_ALLOWED_METRICS
                    and line_metric not in combo_metrics
                ):
                    combo_metrics.append(line_metric)
                metrics = combo_metrics or ["sales"]
    metric_override = (
        str(_chart_payload_value(chart_data, "metric") or "").strip().lower()
    )
    if metric_override in {"sales", "units"}:
        metrics = [metric_override]

    return {
        "dataset": dataset,
        "retailers": retailers,
        "categories": [category] if category else [],
        "brands": brands,
        "dimensions": dimensions,
        "shortcut_dimensions": [
            d for d in dimensions if d in _SALES_VIEW_SHORTCUT_DIMS
        ],
        "period_mode": period_mode,
        "month": month,
        "metrics": metrics,
        "pareto": pareto,
        "price_bands": price_bands,
        "attribute_filters": attribute_filters,
    }


def _plotly_html(fig: go.Figure) -> str:
    return pio.to_html(
        fig, include_plotlyjs="cdn", full_html=False, config={"displayModeBar": True}
    )


def _hex_to_rgba(hex_color: str, *, alpha: float) -> str:
    """Convert a `#RRGGBB` hex color to a Plotly-compatible `rgba(r,g,b,a)` string."""

    cleaned = str(hex_color or "").strip().lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(ch * 2 for ch in cleaned)
    if len(cleaned) != 6:
        return f"rgba(0,0,0,{alpha})"
    try:
        red = int(cleaned[0:2], 16)
        green = int(cleaned[2:4], 16)
        blue = int(cleaned[4:6], 16)
    except ValueError:
        return f"rgba(0,0,0,{alpha})"
    return f"rgba({red},{green},{blue},{alpha})"


def _dedupe_artifact_filename(filename: str, used: set[str]) -> str:
    candidate = str(filename)
    if candidate not in used:
        used.add(candidate)
        return candidate
    path = Path(candidate)
    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        next_name = f"{stem}_{index}{suffix}"
        if next_name not in used:
            used.add(next_name)
            return next_name
        index += 1


def _make_frame_csv_safe(df: pl.DataFrame) -> pl.DataFrame:
    """Convert nested/list columns so the frame can be written as a flat CSV."""

    if df.is_empty():
        return df

    exprs: list[pl.Expr] = []
    for name, dtype in df.schema.items():
        if isinstance(dtype, pl.Struct):
            exprs.append(pl.col(name).struct.json_encode().alias(name))
        elif isinstance(dtype, pl.List):
            if isinstance(dtype.inner, pl.Struct):
                exprs.append(
                    pl.col(name)
                    .list.eval(pl.element().struct.json_encode())
                    .list.join("|")
                    .alias(name)
                )
            else:
                exprs.append(
                    pl.col(name)
                    .list.eval(pl.element().cast(pl.Utf8, strict=False))
                    .list.join("|")
                    .alias(name)
                )

    return df if not exprs else df.with_columns(exprs)


def _records_to_flat_frame(records: Sequence[Mapping[str, Any]]) -> pl.DataFrame:
    """Convert record dictionaries into a flat DataFrame suitable for CSV export."""

    if not records:
        return pl.DataFrame()

    normalized_rows: list[dict[str, Any]] = []
    ordered_keys: list[str] = []
    seen_keys: set[str] = set()

    for record in records:
        row: dict[str, Any] = {}
        for key_raw, value in record.items():
            key = str(key_raw)
            if key not in seen_keys:
                seen_keys.add(key)
                ordered_keys.append(key)
            if isinstance(value, (dict, list)):
                row[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
            elif isinstance(value, tuple):
                row[key] = "|".join(str(item) for item in value)
            else:
                row[key] = value
        normalized_rows.append(row)

    frame = pl.DataFrame(normalized_rows)
    if frame.is_empty():
        return frame

    remaining = [name for name in frame.columns if name not in ordered_keys]
    ordered = [name for name in ordered_keys if name in frame.columns] + remaining
    return frame.select([pl.col(name) for name in ordered])


@router.get(
    "/sales/joined.csv",
    response_class=FileResponse,
    dependencies=[SALES_DATASET_PERMISSION, SALES_DATASET_DOWNLOAD_PERMISSION],
)
def download_sales_joined_csv(
    retailer: List[str] = Query(
        ..., description="Retailer/source(s) to pull sales data for."
    ),
    category_keys: List[str] = Query(..., alias="category"),
    brands: Optional[List[str]] = Query(None, alias="brand"),
    dimensions: Optional[List[str]] = Query(None, alias="dimension"),
    filters: Optional[List[str]] = Query(None),
    price_band: Optional[List[str]] = Query(None, alias="price_band"),
    pareto: Optional[List[str]] = Query(None, alias="pareto"),
    also_blush: Optional[List[str]] = Query(None, alias="also_blush"),
    also_highlighter: Optional[List[str]] = Query(None, alias="also_highlighter"),
    also_cheek: Optional[List[str]] = Query(None, alias="also_cheek"),
    also_eyeliner: Optional[List[str]] = Query(None, alias="also_eyeliner"),
    dataset: str | None = Query(None),
) -> FileResponse:
    """Download the unaggregated sales join for the selected slice."""

    if not retailer:
        raise HTTPException(
            status_code=400, detail="Retailer is required for sales view."
        )

    normalized_keys = _normalize_category_keys(category_keys)
    if not normalized_keys:
        raise HTTPException(
            status_code=400, detail="At least one category is required for sales view."
        )

    full_sales_frame = load_full_sales_data(None, dataset=dataset)
    if full_sales_frame.is_empty():
        raise HTTPException(status_code=400, detail="No sales data available.")

    tables = _get_tables()
    tables = filter_tables_by_retailer(tables, retailer)
    tables = filter_tables_by_brands(tables, brands or [])

    taxonomy = get_attribute_taxonomy()
    category_lookup = build_category_lookup(taxonomy)
    category_labels = _category_labels_from_keys(category_lookup, normalized_keys)
    if not category_labels:
        raise HTTPException(status_code=400, detail="No matching categories found.")

    tables = filter_tables_by_categories(tables, normalized_keys)
    full_sales_frame = _overlay_sales_category_with_catalog_labels(
        full_sales_frame, variants=tables.variants
    )
    filter_setup = prepare_attribute_filters(tables, category_lookup, normalized_keys)

    attr_labels = {attr["id"]: attr["label"] for attr in filter_setup.valid_attributes}
    dimensions_list = dimensions or []

    attribute_dim_ids = set(filter_setup.attr_column_lookup.keys())
    uses_pdp_attributes = any(dim in attribute_dim_ids for dim in dimensions_list)
    selected_hybrid_dimensions = {
        str(dim).strip().lower()
        for dim in dimensions_list
        if _is_hybrid_dimension_key(dim)
    }
    filter_map = _parse_attribute_filters(filters or None)
    hybrid_filter_selection = _build_hybrid_filter_selection(
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
    )
    active_filter_map = {
        attr_id: values
        for attr_id, values in filter_map.items()
        if attr_id in attribute_dim_ids
    }
    required_join_columns = {
        filter_setup.attr_column_lookup[attr_id]
        for attr_id in active_filter_map
        if attr_id in filter_setup.attr_column_lookup
    }
    required_join_columns.update(hybrid_filter_selection.keys())
    required_join_columns.update(selected_hybrid_dimensions)
    needs_pdp_join = (
        uses_pdp_attributes
        or bool(selected_hybrid_dimensions)
        or bool(active_filter_map)
        or bool(hybrid_filter_selection)
    )

    sales_frame = (
        load_sales_data(None, dataset=dataset) if needs_pdp_join else full_sales_frame
    )
    if sales_frame.is_empty():
        raise HTTPException(status_code=400, detail="No sales data available.")

    needs_price_band = "price_band" not in sales_frame.columns
    needs_pareto = True
    price_bands_df = (
        _compute_sales_price_bands(
            full_sales_frame,
            retailers=retailer,
            category_labels=category_labels,
            brands=brands or [],
        )
        if needs_price_band
        else pl.DataFrame()
    )
    pareto_df = pl.DataFrame()
    if "pareto_class" not in sales_frame.columns:
        pareto_df = _compute_sales_pareto_classes(
            full_sales_frame,
            retailers=retailer,
            category_labels=category_labels,
            brands=brands or [],
        )

    if not needs_pdp_join:
        # Prevent the sales join helper from restricting to PDP coverage.
        additions: list[pl.Expr] = []
        if "variant_id" not in sales_frame.columns and "sku" in sales_frame.columns:
            additions.append(
                pl.col("sku").cast(pl.Utf8).str.strip_chars().alias("variant_id")
            )
        if (
            "parent_product_id" not in sales_frame.columns
            and "sku" in sales_frame.columns
        ):
            additions.append(
                pl.col("sku").cast(pl.Utf8).str.strip_chars().alias("parent_product_id")
            )
        if (
            "category_label" not in sales_frame.columns
            and "category" in sales_frame.columns
        ):
            additions.append(
                pl.col("category")
                .cast(pl.Utf8)
                .str.strip_chars()
                .alias("category_label")
            )
        if additions:
            sales_frame = sales_frame.with_columns(additions)

    if needs_pareto and not pareto_df.is_empty():
        key_col = "variant_id" if "variant_id" in sales_frame.columns else "sku"
        sales_frame = (
            (
                sales_frame.drop("pareto_class")
                if "pareto_class" in sales_frame.columns
                else sales_frame
            )
            .with_columns(
                pl.col(key_col).cast(pl.Utf8).str.strip_chars().alias("variant_id_norm")
            )
            .join(pareto_df, on="variant_id_norm", how="left")
            .drop("variant_id_norm")
        )

    if needs_price_band and not price_bands_df.is_empty():
        key_col = "variant_id" if "variant_id" in sales_frame.columns else "sku"
        sales_frame = (
            (
                sales_frame.drop("price_band")
                if "price_band" in sales_frame.columns
                else sales_frame
            )
            .with_columns(
                pl.col(key_col).cast(pl.Utf8).str.strip_chars().alias("variant_id_norm")
            )
            .join(price_bands_df, on="variant_id_norm", how="left")
            .drop("variant_id_norm")
        )

    combined_lookup: dict[str, str] = dict(filter_setup.attr_column_lookup)
    combined_labels: dict[str, str] = dict(attr_labels)
    extra_dimensions = {
        "retailer": ("retailer", "Source"),
        "brand": ("brand", "Brands"),
        "pareto": ("pareto_class", "Pareto classes"),
        "price_band": ("price_band", "Price bands"),
    }
    for key, (col_name, label) in extra_dimensions.items():
        combined_lookup[key] = col_name
        combined_labels[key] = label
    for hybrid_key in _HYBRID_FILTER_COLUMNS:
        combined_lookup[hybrid_key] = hybrid_key
        combined_labels[hybrid_key] = _hybrid_dimension_label(hybrid_key)

    joined, _calendar, _group_cols, _headers = build_sales_calendar_and_join(
        tables,
        sales_frame,
        retailer,
        category_labels,
        brands or [],
        dimensions_list,
        combined_lookup,
        combined_labels,
        price_bands=(
            price_bands_df
            if needs_price_band and not price_bands_df.is_empty()
            else None
        ),
        required_columns=sorted(required_join_columns),
    )
    if "__all__" in joined.columns:
        joined = joined.drop("__all__")

    if active_filter_map and filter_setup.attr_column_lookup:
        joined = apply_attribute_filters(
            joined,
            active_filter_map,
            filter_setup.attr_column_lookup,
            placeholder_values=filter_setup.placeholder_values,
        )
    joined = _apply_hybrid_filters(joined, selection=hybrid_filter_selection)

    if price_band:
        allowed = {str(val).strip().lower() for val in price_band if str(val).strip()}
        if allowed and "price_band" in joined.columns:
            joined = joined.filter(
                pl.col("price_band")
                .cast(pl.Utf8)
                .str.to_lowercase()
                .is_in(list(allowed))
            )

    if pareto:
        allowed = {str(val).strip().upper() for val in pareto if str(val).strip()}
        if allowed and "pareto_class" in joined.columns:
            joined = joined.filter(
                pl.col("pareto_class")
                .cast(pl.Utf8)
                .str.to_uppercase()
                .is_in(list(allowed))
            )

    if joined.is_empty():
        raise HTTPException(
            status_code=400, detail="No sales rows after applying the current filters."
        )

    attribute_columns: list[tuple[str, str]] = []
    for attr in filter_setup.valid_attributes:
        if not isinstance(attr, dict):
            continue
        col = str(attr.get("column", "")).strip()
        if not col or col not in joined.columns:
            continue
        label = str(attr.get("label", col)).strip() or col
        attribute_columns.append((col, label))

    if attribute_columns:
        indicator_exprs = [
            pl.col(col)
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .fill_null("")
            .ne("")
            .any()
            .alias(col)
            for col, _label in attribute_columns
        ]
        present = joined.select(indicator_exprs).to_dicts()[0]
        attribute_columns = [
            (col, label) for col, label in attribute_columns if bool(present.get(col))
        ]

    def _first_available(candidates: Sequence[str]) -> str | None:
        for name in candidates:
            if name in joined.columns:
                return name
        return None

    export_fields: list[tuple[str, str]] = []
    for candidates, out_name in (
        (("month",), "month"),
        (("sales",), "sales"),
        (("units",), "units"),
        (
            ("product_description", "product_name", "variant_description"),
            "product_description",
        ),
        (("brand",), "brand"),
        (("retailer", "merchant"), "retailer"),
        (("category", "category_label", "category_key"), "category"),
        (("pareto_class",), "pareto"),
        (("price_band", "price_band_right"), "price_band"),
    ):
        src = _first_available(candidates)
        if src:
            export_fields.append((src, out_name))

    used_names: set[str] = set()
    export_exprs: list[pl.Expr] = []
    for src, out_name in export_fields:
        if out_name in used_names:
            continue
        export_exprs.append(
            pl.col(src) if src == out_name else pl.col(src).alias(out_name)
        )
        used_names.add(out_name)

    for src, label in attribute_columns:
        out_name = label
        if out_name in used_names:
            out_name = f"{out_name} ({src})"
        export_exprs.append(pl.col(src).alias(out_name))
        used_names.add(out_name)

    joined = joined.select(export_exprs)
    joined = _make_frame_csv_safe(joined)

    cache_dir = Path(get_cache_dir("review_sales_downloads"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    export_path = cache_dir / f"sales_joined_{uuid.uuid4().hex}.csv"
    joined.write_csv(export_path)

    category_label = category_labels[0] if category_labels else normalized_keys[0]
    category_slug = (
        re.sub(r"[^0-9a-zA-Z]+", "_", str(category_label)).strip("_").lower()
        or "category"
    )
    category_slug = category_slug[:80]

    return FileResponse(
        export_path,
        media_type="text/csv; charset=utf-8",
        filename=f"sales_joined_{category_slug}.csv",
    )


@router.get(
    "/sales/attribute-mapping.csv",
    response_class=FileResponse,
    dependencies=[SALES_DATASET_PERMISSION, SALES_DATASET_DOWNLOAD_PERMISSION],
)
def download_sales_attribute_mapping_csv(
    retailer: List[str] = Query(
        ..., description="Retailer/source(s) to pull attribute mappings for."
    ),
    category_keys: List[str] = Query(..., alias="category"),
    brands: Optional[List[str]] = Query(None, alias="brand"),
    filters: Optional[List[str]] = Query(None),
    record_type: str = Query("parent", pattern="^(parent|variant)$"),
    pareto: Optional[List[str]] = Query(None, alias="pareto"),
    price_band: Optional[List[str]] = Query(None, alias="price_band"),
    also_blush: Optional[List[str]] = Query(None, alias="also_blush"),
    also_highlighter: Optional[List[str]] = Query(None, alias="also_highlighter"),
    also_cheek: Optional[List[str]] = Query(None, alias="also_cheek"),
    also_eyeliner: Optional[List[str]] = Query(None, alias="also_eyeliner"),
    dataset: str | None = Query(None),
) -> FileResponse:
    """Download product-level attribute mappings as CSV for parents or variants."""

    del dataset  # Access enforced by dependencies; dataset does not alter catalog tables.

    normalized_keys = _normalize_category_keys(category_keys)
    if not normalized_keys:
        raise HTTPException(
            status_code=400, detail="At least one category key is required."
        )

    hybrid_filter_selection = _build_hybrid_filter_selection(
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
    )

    records_response = _gather_records(
        retailer=retailer,
        category_keys=normalized_keys,
        brands=brands or [],
        record_type=record_type,
        filters=filters or [],
        limit=None,
        download_all=True,
        pareto_filter=pareto or [],
        price_band_filter=price_band or [],
        hybrid_filter_selection=hybrid_filter_selection,
        audit_attribute_id=None,
    )
    if not records_response.records:
        raise HTTPException(
            status_code=400,
            detail="No attribute mapping rows found for the selected filters.",
        )

    export_df = _records_to_flat_frame(records_response.records)
    if export_df.is_empty():
        raise HTTPException(
            status_code=400,
            detail="No attribute mapping rows found for the selected filters.",
        )

    tables = _get_tables_for_coverage()
    tables = filter_tables_by_retailer(tables, retailer)
    tables = filter_tables_by_brands(tables, brands or [])
    tables = filter_tables_by_categories(tables, normalized_keys)
    parent_source = (
        tables.parents_all if not tables.parents_all.is_empty() else tables.parents
    )
    if record_type == "variant":
        filter_tables = ReviewTables(
            parents=parent_source,
            variants=tables.variants,
            combined=(
                tables.variants if not tables.variants.is_empty() else tables.combined
            ),
            parents_all=tables.parents_all,
        )
    else:
        filter_tables = ReviewTables(
            parents=parent_source,
            variants=tables.variants,
            combined=tables.combined,
            parents_all=tables.parents_all,
        )
    taxonomy = get_attribute_taxonomy()
    category_lookup = build_category_lookup(taxonomy)
    filter_setup = prepare_attribute_filters(
        filter_tables, category_lookup, normalized_keys
    )

    rename_map: dict[str, str] = {}
    used_names: set[str] = set(export_df.columns)
    for attr in filter_setup.valid_attributes:
        if not isinstance(attr, dict):
            continue
        column_name = str(attr.get("column", "")).strip()
        if not column_name or column_name not in export_df.columns:
            continue
        label = str(attr.get("label", column_name)).strip() or column_name
        target_name = label
        if target_name in used_names and target_name != column_name:
            target_name = f"{target_name} ({column_name})"
        if target_name != column_name:
            rename_map[column_name] = target_name
            used_names.remove(column_name)
            used_names.add(target_name)
    if rename_map:
        export_df = export_df.rename(rename_map)

    export_df = _make_frame_csv_safe(export_df)

    cache_dir = Path(get_cache_dir("review_sales_downloads"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    export_path = (
        cache_dir / f"sales_attribute_mapping_{record_type}_{uuid.uuid4().hex}.csv"
    )
    export_df.write_csv(export_path)

    taxonomy = get_attribute_taxonomy()
    category_lookup = build_category_lookup(taxonomy)
    category_labels = _category_labels_from_keys(category_lookup, normalized_keys)
    category_label = category_labels[0] if category_labels else normalized_keys[0]
    category_slug = (
        re.sub(r"[^0-9a-zA-Z]+", "_", str(category_label)).strip("_").lower()
        or "category"
    )
    category_slug = category_slug[:80]

    return FileResponse(
        export_path,
        media_type="text/csv; charset=utf-8",
        filename=f"sales_{record_type}_attribute_mapping_{category_slug}.csv",
    )


@router.get(
    "/sales/metrics",
    response_model=SalesMetricsResponse,
    dependencies=[SALES_DATASET_PERMISSION],
)
def fetch_sales_metrics(
    retailer: List[str] = Query(
        ..., description="Retailer/source(s) to pull sales data for."
    ),
    category_keys: List[str] = Query(..., alias="category"),
    brands: Optional[List[str]] = Query(None, alias="brand"),
    dimensions: Optional[List[str]] = Query(None, alias="dimension"),
    filters: Optional[List[str]] = Query(None),
    window_months: int = Query(12, ge=1, le=12),
    price_band: Optional[List[str]] = Query(None, alias="price_band"),
    pareto: Optional[List[str]] = Query(None, alias="pareto"),
    also_blush: Optional[List[str]] = Query(None, alias="also_blush"),
    also_highlighter: Optional[List[str]] = Query(None, alias="also_highlighter"),
    also_cheek: Optional[List[str]] = Query(None, alias="also_cheek"),
    also_eyeliner: Optional[List[str]] = Query(None, alias="also_eyeliner"),
    dataset: str | None = Query(None),
) -> SalesMetricsResponse:
    if not retailer:
        raise HTTPException(
            status_code=400, detail="Retailer is required for sales view."
        )

    normalized_keys = _normalize_category_keys(category_keys)
    if not normalized_keys:
        raise HTTPException(
            status_code=400, detail="At least one category is required for sales view."
        )

    months: List[str] = []
    full_sales_frame = load_full_sales_data(None, dataset=dataset)
    if full_sales_frame.is_empty():
        return SalesMetricsResponse(
            total_sales=0.0,
            total_units=0.0,
            dimension_headers=[],
            rows=[],
            months=months,
        )

    tables = _get_tables()
    tables = filter_tables_by_retailer(tables, retailer)
    tables = filter_tables_by_brands(tables, brands or [])

    taxonomy = get_attribute_taxonomy()
    category_lookup = build_category_lookup(taxonomy)
    category_labels = _category_labels_from_keys(category_lookup, normalized_keys)
    if not category_labels:
        return SalesMetricsResponse(
            total_sales=0.0,
            total_units=0.0,
            dimension_headers=[],
            rows=[],
            months=months,
        )

    tables = filter_tables_by_categories(tables, normalized_keys)
    full_sales_frame = _overlay_sales_category_with_catalog_labels(
        full_sales_frame, variants=tables.variants
    )
    filter_setup = prepare_attribute_filters(tables, category_lookup, normalized_keys)

    attr_labels = {attr["id"]: attr["label"] for attr in filter_setup.valid_attributes}
    dimensions_list = dimensions or []

    attribute_dim_ids = set(filter_setup.attr_column_lookup.keys())
    uses_pdp_attributes = any(dim in attribute_dim_ids for dim in dimensions_list)
    selected_hybrid_dimensions = {
        str(dim).strip().lower()
        for dim in dimensions_list
        if _is_hybrid_dimension_key(dim)
    }
    filter_map = _parse_attribute_filters(filters or None)
    hybrid_filter_selection = _build_hybrid_filter_selection(
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
    )
    active_filter_map = {
        attr_id: values
        for attr_id, values in filter_map.items()
        if attr_id in attribute_dim_ids
    }
    required_join_columns = {
        filter_setup.attr_column_lookup[attr_id]
        for attr_id in active_filter_map
        if attr_id in filter_setup.attr_column_lookup
    }
    required_join_columns.update(hybrid_filter_selection.keys())
    required_join_columns.update(selected_hybrid_dimensions)
    needs_pdp_join = (
        uses_pdp_attributes
        or bool(selected_hybrid_dimensions)
        or bool(active_filter_map)
        or bool(hybrid_filter_selection)
    )

    sales_frame = (
        load_sales_data(None, dataset=dataset) if needs_pdp_join else full_sales_frame
    )
    if sales_frame.is_empty():
        return SalesMetricsResponse(
            total_sales=0.0,
            total_units=0.0,
            dimension_headers=[],
            rows=[],
            months=months,
        )

    needs_price_band = "price_band" in dimensions_list or bool(price_band)
    needs_pareto = "pareto" in dimensions_list or bool(pareto)

    price_bands_df = (
        _compute_sales_price_bands(
            full_sales_frame,
            retailers=retailer,
            category_labels=category_labels,
            brands=brands or [],
        )
        if needs_price_band
        else pl.DataFrame()
    )
    pareto_df = (
        _compute_sales_pareto_classes(
            full_sales_frame,
            retailers=retailer,
            category_labels=category_labels,
            brands=brands or [],
        )
        if needs_pareto
        else pl.DataFrame()
    )

    if not needs_pdp_join:
        # Prevent the sales join helper from restricting to PDP coverage.
        additions: list[pl.Expr] = []
        if "variant_id" not in sales_frame.columns and "sku" in sales_frame.columns:
            additions.append(
                pl.col("sku").cast(pl.Utf8).str.strip_chars().alias("variant_id")
            )
        if (
            "parent_product_id" not in sales_frame.columns
            and "sku" in sales_frame.columns
        ):
            additions.append(
                pl.col("sku").cast(pl.Utf8).str.strip_chars().alias("parent_product_id")
            )
        if (
            "category_label" not in sales_frame.columns
            and "category" in sales_frame.columns
        ):
            additions.append(
                pl.col("category")
                .cast(pl.Utf8)
                .str.strip_chars()
                .alias("category_label")
            )
        if additions:
            sales_frame = sales_frame.with_columns(additions)

    if needs_pareto and not pareto_df.is_empty():
        if "pareto_class" in sales_frame.columns:
            sales_frame = sales_frame.drop("pareto_class")
        key_col = "variant_id" if "variant_id" in sales_frame.columns else "sku"
        sales_frame = (
            sales_frame.with_columns(
                pl.col(key_col).cast(pl.Utf8).str.strip_chars().alias("variant_id_norm")
            )
            .join(pareto_df, on="variant_id_norm", how="left")
            .drop("variant_id_norm")
        )

    if needs_price_band and "price_band" in sales_frame.columns:
        sales_frame = sales_frame.drop("price_band")

    combined_lookup: dict[str, str] = dict(filter_setup.attr_column_lookup)
    combined_labels: dict[str, str] = dict(attr_labels)
    extra_dimensions = {
        "retailer": ("retailer", "Source"),
        "brand": ("brand", "Brands"),
        "pareto": ("pareto_class", "Pareto classes"),
        "price_band": ("price_band", "Price bands"),
    }
    for key, (col_name, label) in extra_dimensions.items():
        combined_lookup[key] = col_name
        combined_labels[key] = label
    for hybrid_key in _HYBRID_FILTER_COLUMNS:
        combined_lookup[hybrid_key] = hybrid_key
        combined_labels[hybrid_key] = _hybrid_dimension_label(hybrid_key)

    joined, calendar, group_cols, headers = build_sales_calendar_and_join(
        tables,
        sales_frame,
        retailer,
        category_labels,
        brands or [],
        dimensions_list,
        combined_lookup,
        combined_labels,
        price_bands=(
            price_bands_df
            if needs_price_band and not price_bands_df.is_empty()
            else None
        ),
        required_columns=sorted(required_join_columns),
    )

    if active_filter_map and filter_setup.attr_column_lookup:
        joined = apply_attribute_filters(
            joined,
            active_filter_map,
            filter_setup.attr_column_lookup,
            placeholder_values=filter_setup.placeholder_values,
        )
    joined = _apply_hybrid_filters(joined, selection=hybrid_filter_selection)

    if price_band:
        allowed = {str(val).strip().lower() for val in price_band if str(val).strip()}
        if allowed and "price_band" in joined.columns:
            joined = joined.filter(
                pl.col("price_band")
                .cast(pl.Utf8)
                .str.to_lowercase()
                .is_in(list(allowed))
            )

    if not calendar.is_empty():
        months = [
            month.isoformat()
            for month in calendar.get_column("month").to_list()
            if month is not None and hasattr(month, "isoformat")
        ]

    if joined.is_empty() or calendar.is_empty():
        return SalesMetricsResponse(
            total_sales=0.0,
            total_units=0.0,
            dimension_headers=headers,
            rows=[],
            months=months,
        )

    if pareto:
        allowed = {str(val).strip().upper() for val in pareto if str(val).strip()}
        if allowed and "pareto_class" in joined.columns:
            joined = joined.filter(
                pl.col("pareto_class")
                .cast(pl.Utf8)
                .str.to_uppercase()
                .is_in(list(allowed))
            )

    category_rollup = compute_category_rollup(joined, calendar, window_months)
    if category_rollup.is_empty():
        return SalesMetricsResponse(
            total_sales=0.0,
            total_units=0.0,
            dimension_headers=headers,
            rows=[],
            months=months,
        )

    aggregated = compute_dimension_shares(
        joined,
        calendar,
        category_rollup,
        window_months,
        group_cols if group_cols else [],
        headers,
    )

    aggregated = aggregated.filter(
        (pl.col("sales_rolling") != 0) | (pl.col("units_rolling") != 0)
    )

    if aggregated.is_empty():
        return SalesMetricsResponse(
            total_sales=0.0,
            total_units=0.0,
            dimension_headers=headers,
            rows=[],
            months=months,
        )

    total_sales = float(
        aggregated.select(pl.col("category_sales_rolling")).max().item() or 0.0
    )
    total_units = float(
        aggregated.select(pl.col("category_units_rolling")).max().item() or 0.0
    )

    rows: List[SalesMetricRow] = []
    for record in aggregated.to_dicts():
        dimensions_map = (
            {header: record.get(header) or "" for header in headers} if headers else {}
        )
        month_val = record.get("month")
        month_str = (
            month_val.isoformat() if hasattr(month_val, "isoformat") else str(month_val)
        )
        rows.append(
            SalesMetricRow(
                month=month_str,
                dimensions=dimensions_map,
                sales=float(record.get("sales_rolling") or 0.0),
                units=float(record.get("units_rolling") or 0.0),
                sales_share=float(record.get("sales_share") or 0.0),
                units_share=float(record.get("units_share") or 0.0),
            )
        )

    return SalesMetricsResponse(
        total_sales=total_sales,
        total_units=total_units,
        dimension_headers=headers,
        rows=rows,
        months=months,
    )


@router.get(
    "/sales/metrics.csv",
    response_class=Response,
    dependencies=[SALES_DATASET_PERMISSION, SALES_DATASET_DOWNLOAD_PERMISSION],
)
def download_sales_metrics_csv(
    retailer: List[str] = Query(
        ..., description="Retailer/source(s) to pull sales data for."
    ),
    category_keys: List[str] = Query(..., alias="category"),
    brands: Optional[List[str]] = Query(None, alias="brand"),
    dimensions: Optional[List[str]] = Query(None, alias="dimension"),
    filters: Optional[List[str]] = Query(None),
    month: Optional[str] = Query(None, description="Month ISO date (YYYY-MM-DD)"),
    window_months: int = Query(12, ge=1, le=12),
    price_band: Optional[List[str]] = Query(None, alias="price_band"),
    pareto: Optional[List[str]] = Query(None, alias="pareto"),
    also_blush: Optional[List[str]] = Query(None, alias="also_blush"),
    also_highlighter: Optional[List[str]] = Query(None, alias="also_highlighter"),
    also_cheek: Optional[List[str]] = Query(None, alias="also_cheek"),
    also_eyeliner: Optional[List[str]] = Query(None, alias="also_eyeliner"),
    dataset: str | None = Query(None),
) -> Response:
    """Download CSV rows matching the current sales chart filters."""

    metrics = fetch_sales_metrics(
        retailer=retailer,
        category_keys=category_keys,
        brands=brands,
        dimensions=dimensions,
        filters=filters,
        window_months=window_months,
        price_band=price_band,
        pareto=pareto,
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
        dataset=dataset,
    )

    month_filter = str(month or "").strip()
    rows = metrics.rows
    if month_filter and month_filter != "__all_months__":
        rows = [row for row in rows if row.month == month_filter]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    metric_headers = ["Month", "Sales", "Units", "Sales share", "Unit share"]
    all_headers = metric_headers + metrics.dimension_headers
    writer.writerow(all_headers)

    for row in rows:
        dimensions_map = row.dimensions or {}
        writer.writerow(
            [
                row.month,
                row.sales,
                row.units,
                f"{row.sales_share * 100:.1f}%",
                f"{row.units_share * 100:.1f}%",
                *[
                    str(dimensions_map.get(header, "") or "")
                    for header in metrics.dimension_headers
                ],
            ]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="sales_metrics.csv"'},
    )


def _select_sales_brief_attribute_dimensions(
    metadata: AttributeMetadataResponse,
    *,
    focus_attributes: Sequence[str] | None = None,
    max_dimensions: int = SALES_BRIEF_MAX_ATTRIBUTE_DIMENSIONS,
) -> tuple[str, ...]:
    normalized_focus = [
        str(value).strip().lower()
        for value in (focus_attributes or [])
        if str(value).strip()
    ]
    lookup: dict[str, AttributeOption] = {}
    for attribute in metadata.attributes:
        lookup[str(attribute.id).strip().lower()] = attribute
        lookup[str(attribute.label).strip().lower()] = attribute
    selected: list[str] = []
    seen: set[str] = set()

    def add_attribute(attribute: AttributeOption) -> None:
        attr_id = str(attribute.id).strip()
        normalized_id = attr_id.lower()
        if not attr_id or normalized_id in seen:
            return
        selected.append(attr_id)
        seen.add(normalized_id)

    for token in normalized_focus:
        attribute = lookup.get(token)
        if attribute is not None:
            add_attribute(attribute)
        if len(selected) >= max_dimensions:
            return tuple(selected)

    preferred_rank = {
        attr_id: index
        for index, attr_id in enumerate(SALES_BRIEF_PREFERRED_ATTRIBUTE_IDS)
    }
    eligible = [
        attribute
        for attribute in metadata.attributes
        if attribute.active
        and attribute.coverage_pct >= SALES_BRIEF_MIN_ATTRIBUTE_COVERAGE
        and attribute.distinct_non_placeholder_values >= SALES_BRIEF_MIN_DISTINCT_VALUES
    ]
    for attribute in sorted(
        eligible,
        key=lambda current: (
            preferred_rank.get(str(current.id).strip().lower(), len(preferred_rank)),
            -float(current.coverage_pct),
            -int(current.distinct_non_placeholder_values),
            str(current.label).lower(),
        ),
    ):
        add_attribute(attribute)
        if len(selected) >= max_dimensions:
            return tuple(selected)

    if selected:
        return tuple(selected)

    fallback = sorted(
        (
            attribute
            for attribute in metadata.attributes
            if attribute.active and attribute.distinct_non_placeholder_values >= 2
        ),
        key=lambda current: (
            -float(current.coverage_pct),
            -int(current.distinct_non_placeholder_values),
            str(current.label).lower(),
        ),
    )
    for attribute in fallback:
        add_attribute(attribute)
        if len(selected) >= max_dimensions:
            break
    return tuple(selected)


def _build_sales_brief_chart_request(
    *,
    retailer: Sequence[str],
    category_keys: Sequence[str],
    brands: Sequence[str] | None,
    filters: Sequence[str] | None,
    price_band: Sequence[str] | None,
    pareto: Sequence[str] | None,
    also_blush: Sequence[str] | None,
    also_highlighter: Sequence[str] | None,
    also_cheek: Sequence[str] | None,
    also_eyeliner: Sequence[str] | None,
    dataset: str | None,
    chart_type: str,
    dimensions: Sequence[str] | None = None,
    metric: str = "sales",
    overlay_metric: str | None = None,
    window_months: int = 1,
    area_mode: str | None = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "retailer": list(retailer),
        "category": list(category_keys),
        "brand": list(brands or []),
        "filters": list(filters or []),
        "price_band": list(price_band or []),
        "pareto": list(pareto or []),
        "also_blush": list(also_blush or []),
        "also_highlighter": list(also_highlighter or []),
        "also_cheek": list(also_cheek or []),
        "also_eyeliner": list(also_eyeliner or []),
        "dimension": list(dimensions or []),
        "chart_type": chart_type,
        "metric": metric,
        "window_months": int(window_months),
    }
    if overlay_metric:
        request["overlay_metric"] = overlay_metric
    if area_mode:
        request["area_mode"] = area_mode
    if dataset is not None:
        request["dataset"] = dataset
    return request


def _build_sales_brief_chart_identity(
    *,
    chart_request: Mapping[str, Any],
    metrics_response: SalesMetricsResponse,
) -> str:
    retailer = [str(value).strip() for value in chart_request.get("retailer", [])]
    category_keys = [str(value).strip() for value in chart_request.get("category", [])]
    brands = [str(value).strip() for value in chart_request.get("brand", [])]
    dimensions = [str(value).strip() for value in chart_request.get("dimension", [])]
    filters = [str(value).strip() for value in chart_request.get("filters", [])]
    chart_type = str(chart_request.get("chart_type") or "").strip()
    metric = str(chart_request.get("metric") or "sales").strip()
    overlay_metric = str(chart_request.get("overlay_metric") or "").strip()
    area_mode = str(chart_request.get("area_mode") or "").strip()
    dataset = chart_request.get("dataset")

    retailer_norm = _normalize_retailers_param(retailer)
    category_key = _sales_chart_category_key(category_keys)
    selected_brands = [value for value in brands if value]
    placeholder_values_csv = _sales_chart_canonical_csv(
        sorted(
            {
                str(value).strip().lower()
                for value in PlaceholderValues
                if str(value).strip()
            }
        )
    )
    hybrid_filter_selection = _build_hybrid_filter_selection(
        also_blush=chart_request.get("also_blush"),
        also_highlighter=chart_request.get("also_highlighter"),
        also_cheek=chart_request.get("also_cheek"),
        also_eyeliner=chart_request.get("also_eyeliner"),
    )
    chart_universe = (
        "l4l"
        if _sales_chart_needs_l4l_universe(
            dimensions=dimensions,
            filters=filters,
            hybrid_filter_selection=hybrid_filter_selection,
        )
        else "full"
    )
    start_month_iso, end_month_iso = _sales_chart_month_bounds(metrics_response.rows)

    if chart_type == "stacked_column" and not dimensions:
        return _build_sales_chart_id(
            chart_family="combo_total_abs",
            category_key=category_key,
            metric=metric,
            line_metric=overlay_metric or ("units" if metric == "sales" else "sales"),
            retailers=retailer_norm,
            brands=selected_brands,
            universe=chart_universe,
            start_month=start_month_iso,
            end_month=end_month_iso,
            dataset_name=str(dataset) if dataset is not None else None,
        )

    if chart_type == "area" and len(dimensions) == 1 and area_mode == "percent":
        return _build_sales_chart_id(
            chart_family="stacked",
            category_key=category_key,
            segment_id=dimensions[0],
            metric=metric,
            retailers=retailer_norm,
            brands=selected_brands,
            universe=chart_universe,
            start_month=start_month_iso,
            end_month=end_month_iso,
            top_n=_sales_chart_top_n_for_segment(dimensions[0]),
            aggregation="monthly",
            placeholders_csv=placeholder_values_csv,
            dataset_name=str(dataset) if dataset is not None else None,
        )

    if chart_type == "slope" and len(dimensions) == 1:
        return _build_sales_chart_id(
            chart_family="slope",
            category_key=category_key,
            attribute_id="",
            brand_id=dimensions[0],
            retailers=retailer_norm,
            brands=selected_brands,
            universe=chart_universe,
            start_month=start_month_iso,
            end_month=end_month_iso,
            top_n=14,
            placeholders_csv=placeholder_values_csv,
            dataset_name=str(dataset) if dataset is not None else None,
        )

    raise ValueError(
        f"Unsupported sales brief chart request for canonical id: {chart_request}"
    )


def _build_sales_brief_numeric_payloads(
    *,
    retailer: Sequence[str],
    category_keys: Sequence[str],
    brands: Sequence[str] | None,
    filters: Sequence[str] | None,
    price_band: Sequence[str] | None,
    pareto: Sequence[str] | None,
    also_blush: Sequence[str] | None,
    also_highlighter: Sequence[str] | None,
    also_cheek: Sequence[str] | None,
    also_eyeliner: Sequence[str] | None,
    dataset: str | None,
    focus_attributes: Sequence[str] | None,
) -> tuple[dict[str, dict[str, Any]], tuple[str, ...]]:
    from modules.pdp.sales_finding_engine import (
        build_attribute_mix_numeric_payloads,
        build_slope_numeric_payload,
        build_stacked_share_numeric_payload,
        build_total_combo_numeric_payload,
    )

    common_args = dict(
        retailer=list(retailer),
        category_keys=list(category_keys),
        brands=list(brands or []),
        filters=list(filters or []),
        price_band=list(price_band or []),
        pareto=list(pareto or []),
        also_blush=list(also_blush or []),
        also_highlighter=list(also_highlighter or []),
        also_cheek=list(also_cheek or []),
        also_eyeliner=list(also_eyeliner or []),
        dataset=dataset,
    )

    monthly_totals = fetch_sales_metrics(
        dimensions=None,
        window_months=1,
        **common_args,
    )
    rolling_totals = fetch_sales_metrics(
        dimensions=None,
        window_months=12,
        **common_args,
    )
    price_metrics = fetch_sales_metrics(
        dimensions=["price_band"],
        window_months=1,
        **common_args,
    )
    brand_metrics = fetch_sales_metrics(
        dimensions=["brand"],
        window_months=1,
        **common_args,
    )
    attribute_metadata = fetch_attribute_metadata(
        retailer=list(retailer),
        category_keys=list(category_keys),
        brands=list(brands or []),
        filters=list(filters or []),
        pareto=list(pareto or []),
        price_band=list(price_band or []),
        also_blush=list(also_blush or []),
        also_highlighter=list(also_highlighter or []),
        also_cheek=list(also_cheek or []),
        also_eyeliner=list(also_eyeliner or []),
        record_type="parent",
    )
    attribute_dimensions = _select_sales_brief_attribute_dimensions(
        attribute_metadata,
        focus_attributes=focus_attributes,
    )
    attribute_metric_map = {
        attribute_id: fetch_sales_metrics(
            dimensions=[attribute_id],
            window_months=1,
            **common_args,
        )
        for attribute_id in attribute_dimensions
    }
    total_combo_monthly_request = _build_sales_brief_chart_request(
        retailer=retailer,
        category_keys=category_keys,
        brands=brands,
        filters=filters,
        price_band=price_band,
        pareto=pareto,
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
        dataset=dataset,
        chart_type="stacked_column",
        dimensions=(),
        metric="sales",
        overlay_metric="units",
        window_months=1,
    )
    total_combo_rolling_request = _build_sales_brief_chart_request(
        retailer=retailer,
        category_keys=category_keys,
        brands=brands,
        filters=filters,
        price_band=price_band,
        pareto=pareto,
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
        dataset=dataset,
        chart_type="stacked_column",
        dimensions=(),
        metric="sales",
        overlay_metric="units",
        window_months=12,
    )
    price_band_request = _build_sales_brief_chart_request(
        retailer=retailer,
        category_keys=category_keys,
        brands=brands,
        filters=filters,
        price_band=price_band,
        pareto=pareto,
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
        dataset=dataset,
        chart_type="area",
        dimensions=("price_band",),
        metric="sales",
        window_months=1,
        area_mode="percent",
    )
    brand_slope_request = _build_sales_brief_chart_request(
        retailer=retailer,
        category_keys=category_keys,
        brands=brands,
        filters=filters,
        price_band=price_band,
        pareto=pareto,
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
        dataset=dataset,
        chart_type="slope",
        dimensions=("brand",),
        metric="sales",
        window_months=1,
    )
    attribute_chart_metadata = {
        attribute_id: {
            "chart_request": _build_sales_brief_chart_request(
                retailer=retailer,
                category_keys=category_keys,
                brands=brands,
                filters=filters,
                price_band=price_band,
                pareto=pareto,
                also_blush=also_blush,
                also_highlighter=also_highlighter,
                also_cheek=also_cheek,
                also_eyeliner=also_eyeliner,
                dataset=dataset,
                chart_type="area",
                dimensions=(attribute_id,),
                metric="sales",
                window_months=1,
                area_mode="percent",
            ),
        }
        for attribute_id in attribute_dimensions
    }
    for attribute_id, metadata in attribute_chart_metadata.items():
        metadata["chart_id"] = _build_sales_brief_chart_identity(
            chart_request=metadata["chart_request"],
            metrics_response=attribute_metric_map[attribute_id],
        )
    numeric_payloads = {
        "total_combo_monthly": build_total_combo_numeric_payload(
            monthly_totals,
            chart_id=_build_sales_brief_chart_identity(
                chart_request=total_combo_monthly_request,
                metrics_response=monthly_totals,
            ),
            chart_request=total_combo_monthly_request,
            unit="USD",
            window_months=1,
        ),
        "total_combo_rolling_12": build_total_combo_numeric_payload(
            rolling_totals,
            chart_id=_build_sales_brief_chart_identity(
                chart_request=total_combo_rolling_request,
                metrics_response=rolling_totals,
            ),
            chart_request=total_combo_rolling_request,
            unit="USD",
            window_months=12,
        ),
        "stacked_share_price_band": build_stacked_share_numeric_payload(
            price_metrics,
            chart_id=_build_sales_brief_chart_identity(
                chart_request=price_band_request,
                metrics_response=price_metrics,
            ),
            chart_request=price_band_request,
            segment_key="price_band",
            dimension_label="Price bands",
        ),
        "slope_brand": build_slope_numeric_payload(
            brand_metrics,
            chart_id=_build_sales_brief_chart_identity(
                chart_request=brand_slope_request,
                metrics_response=brand_metrics,
            ),
            chart_request=brand_slope_request,
            segment_key="brand",
            dimension_label="Brands",
        ),
        "stacked_share_attribute_payloads": build_attribute_mix_numeric_payloads(
            attribute_metric_map,
            chart_metadata_by_dimension=attribute_chart_metadata,
        ),
    }
    return numeric_payloads, attribute_dimensions


def _build_sales_brief_response_payload(
    *,
    retailer: Sequence[str],
    category_keys: Sequence[str],
    brands: Sequence[str] | None,
    filters: Sequence[str] | None,
    price_band: Sequence[str] | None,
    pareto: Sequence[str] | None,
    also_blush: Sequence[str] | None,
    also_highlighter: Sequence[str] | None,
    also_cheek: Sequence[str] | None,
    also_eyeliner: Sequence[str] | None,
    dataset: str | None,
    focus_attributes: Sequence[str] | None,
    max_findings: int,
    max_per_lens: int,
    highlight_count: int,
) -> dict[str, Any]:
    from modules.pdp.sales_brief import (
        build_sales_brief_artifact,
        build_sales_brief_payload,
    )
    from modules.pdp.sales_finding_engine import build_analysis_scope

    normalized_categories = _normalize_category_keys(list(category_keys))
    if len(normalized_categories) != 1:
        raise HTTPException(
            status_code=400,
            detail="Sales brief currently supports exactly one category.",
        )

    numeric_payloads, attribute_dimensions = _build_sales_brief_numeric_payloads(
        retailer=retailer,
        category_keys=normalized_categories,
        brands=brands,
        filters=filters,
        price_band=price_band,
        pareto=pareto,
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
        dataset=dataset,
        focus_attributes=focus_attributes,
    )
    artifact = build_sales_brief_artifact(
        scope="single_category",
        analysis_scope=build_analysis_scope(
            dataset=dataset,
            retailers=list(retailer),
            categories=list(normalized_categories),
            brands=list(brands or []),
            price_bands=list(price_band or []),
            pareto_classes=list(pareto or []),
            attribute_filters=_parse_attribute_filters(filters or None),
        ),
        selection_context={},
        numeric_payloads=numeric_payloads,
        attribute_dimensions=attribute_dimensions,
        max_findings=max_findings,
        max_per_lens=max_per_lens,
        highlight_count=highlight_count,
    )
    return build_sales_brief_payload(artifact)


@router.get(
    "/sales/brief",
    response_model=SalesBriefArtifactResponse,
    response_model_exclude_none=True,
    dependencies=[SALES_DATASET_PERMISSION],
)
def fetch_sales_brief(
    retailer: List[str] = Query(
        ..., description="Retailer/source(s) to pull sales data for."
    ),
    category_keys: List[str] = Query(..., alias="category"),
    brands: Optional[List[str]] = Query(None, alias="brand"),
    filters: Optional[List[str]] = Query(None),
    price_band: Optional[List[str]] = Query(None, alias="price_band"),
    pareto: Optional[List[str]] = Query(None, alias="pareto"),
    also_blush: Optional[List[str]] = Query(None, alias="also_blush"),
    also_highlighter: Optional[List[str]] = Query(None, alias="also_highlighter"),
    also_cheek: Optional[List[str]] = Query(None, alias="also_cheek"),
    also_eyeliner: Optional[List[str]] = Query(None, alias="also_eyeliner"),
    focus_attributes: Optional[List[str]] = Query(None, alias="focus_attribute"),
    dataset: str | None = Query(None),
    max_findings: int = Query(DEFAULT_BRIEF_MAX_FINDINGS, ge=1, le=12),
    max_per_lens: int = Query(DEFAULT_BRIEF_MAX_PER_LENS, ge=1, le=4),
    highlight_count: int = Query(DEFAULT_BRIEF_HIGHLIGHT_COUNT, ge=1, le=6),
) -> SalesBriefArtifactResponse:
    return _build_sales_brief_response_payload(
        retailer=retailer,
        category_keys=category_keys,
        brands=brands,
        filters=filters,
        price_band=price_band,
        pareto=pareto,
        also_blush=also_blush,
        also_highlighter=also_highlighter,
        also_cheek=also_cheek,
        also_eyeliner=also_eyeliner,
        dataset=dataset,
        focus_attributes=focus_attributes,
        max_findings=max_findings,
        max_per_lens=max_per_lens,
        highlight_count=highlight_count,
    )


_SALES_CHART_ID_NON_ATTRIBUTE_DIMENSIONS = frozenset(
    {"retailer", "brand", "pareto", "price_band"}
)
_SALES_CHART_ID_SPEC_VERSION = "v1"
_SALES_CHART_ID_SAFE_SLUG = re.compile(r"[^a-z0-9]+")


def _sales_chart_safe_slug(value: str) -> str:
    base = str(value or "").strip().lower()
    base = _SALES_CHART_ID_SAFE_SLUG.sub("-", base).strip("-")
    return base or "brief"


def _sales_chart_canonical_csv(values: Iterable[str]) -> str:
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    unique = sorted(set(cleaned), key=str.casefold)
    return ",".join(unique)


def _sales_chart_dimension_id(value: str) -> str:
    raw = str(value or "").strip().lower()
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"}).strip("_-")
    return safe or "dimension"


def _sales_chart_category_key(category_keys: Sequence[str]) -> str:
    normalized = _normalize_category_keys(category_keys)
    if not normalized:
        return "category"
    if len(normalized) == 1:
        return normalized[0]
    return _sales_chart_canonical_csv(normalized)


def _sales_chart_filter_attribute_ids(filters: Sequence[str] | None) -> set[str]:
    if not filters:
        return set()
    attr_ids: set[str] = set()
    for raw in filters:
        token = str(raw or "").strip()
        if not token:
            continue
        attr_id, sep, _values = token.partition(":")
        if not sep:
            continue
        normalized = _sales_chart_dimension_id(attr_id)
        if normalized:
            attr_ids.add(normalized)
    return attr_ids


def _sales_chart_needs_l4l_universe(
    *,
    dimensions: Sequence[str],
    filters: Sequence[str] | None,
    hybrid_filter_selection: Mapping[str, Iterable[str]],
) -> bool:
    normalized_dims = [_sales_chart_dimension_id(dim) for dim in dimensions]
    selected_hybrid_dims = {
        dim for dim in normalized_dims if _is_hybrid_dimension_key(dim)
    }
    uses_pdp_attributes = any(
        dim
        and dim not in _SALES_CHART_ID_NON_ATTRIBUTE_DIMENSIONS
        and dim not in selected_hybrid_dims
        for dim in normalized_dims
    )
    has_attribute_filters = bool(_sales_chart_filter_attribute_ids(filters))
    has_hybrid_filters = any(
        bool(values) for values in hybrid_filter_selection.values()
    )
    return bool(
        uses_pdp_attributes
        or selected_hybrid_dims
        or has_attribute_filters
        or has_hybrid_filters
    )


def _sales_chart_month_bounds(rows: Sequence[SalesMetricRow]) -> tuple[str, str]:
    month_values: list[date] = []
    for row in rows:
        try:
            parsed = date.fromisoformat(str(row.month))
        except ValueError:
            continue
        month_values.append(parsed)
    if not month_values:
        return ("", "")
    month_values.sort()
    return (month_values[0].isoformat(), month_values[-1].isoformat())


def _sales_chart_top_n_for_segment(segment_id: str) -> int:
    normalized = _sales_chart_dimension_id(segment_id)
    if normalized == "brand":
        return 10
    if normalized == "price_band":
        return 5
    if normalized == "pareto":
        return 4
    return 8


def _sales_chart_clean_dimension_value(value: Any) -> str:
    text = str(value or "").strip()
    return text or "N/A"


def _sales_chart_windowed_months(
    rows: Sequence[SalesMetricRow],
    window_months: int,
) -> tuple[str, str, int] | None:
    months = sorted(
        {str(row.month or "").strip() for row in rows if str(row.month or "").strip()}
    )
    if len(months) < 2:
        return None
    span = max(1, int(window_months or 12))
    start_index = span if len(months) > span else 0
    if start_index >= len(months) - 1:
        start_index = max(0, len(months) - 2)
    start_month = months[start_index]
    end_month = months[-1]
    return (start_month, end_month, span)


def _sales_chart_auto_aggregate_slope_combos(
    all_combos: Sequence[str],
    start_shares: dict[str, float],
    end_shares: dict[str, float],
) -> tuple[list[str], str | None]:
    min_keep = 8
    max_keep = 18
    target_end_share = 90.0
    top_movers = 5
    if not all_combos or len(all_combos) <= max_keep:
        return list(all_combos), None

    metrics: list[tuple[str, float, float, float, float]] = []
    for combo in all_combos:
        start_val = float(start_shares.get(combo) or 0.0)
        end_val = float(end_shares.get(combo) or 0.0)
        metrics.append(
            (
                combo,
                start_val,
                end_val,
                abs(end_val - start_val),
                max(start_val, end_val),
            )
        )

    sorted_by_end = sorted(
        metrics,
        key=lambda item: (-item[2], -item[4], item[0]),
    )
    keep_set: set[str] = set()
    covered_end_share = 0.0
    for combo, _start, end_val, _delta, _max_share in sorted_by_end:
        if len(keep_set) >= max_keep:
            break
        if len(keep_set) < min_keep or covered_end_share < target_end_share:
            keep_set.add(combo)
            covered_end_share += end_val

    movers = sorted(
        [item for item in metrics if item[0] not in keep_set],
        key=lambda item: (-item[3], -item[4], item[0]),
    )
    for combo, _start, _end, _delta, _max_share in movers[:top_movers]:
        if len(keep_set) >= max_keep:
            break
        keep_set.add(combo)

    if len(keep_set) >= len(all_combos):
        return list(all_combos), None

    ordered_keep = sorted(
        list(keep_set),
        key=lambda combo: (
            -(end_shares.get(combo) or 0.0),
            -(start_shares.get(combo) or 0.0),
            combo,
        ),
    )
    other_combos = [combo for combo in all_combos if combo not in keep_set]
    if not other_combos:
        return ordered_keep, None
    other_start = sum(float(start_shares.get(combo) or 0.0) for combo in other_combos)
    other_end = sum(float(end_shares.get(combo) or 0.0) for combo in other_combos)
    other_label = f"Other ({len(other_combos)})"
    start_shares[other_label] = other_start
    end_shares[other_label] = other_end
    return [*ordered_keep, other_label], other_label


def _sales_chart_with_dataset_prefix(chart_id: str, dataset_name: str | None) -> str:
    normalized_chart_id = str(chart_id or "").strip()
    if not normalized_chart_id:
        return normalized_chart_id
    raw_dataset = str(dataset_name or "").strip()
    if not raw_dataset:
        return normalized_chart_id
    dataset_slug = _sales_chart_safe_slug(raw_dataset)
    prefix = f"{dataset_slug}_"
    if normalized_chart_id.startswith(prefix):
        return normalized_chart_id
    return f"{prefix}{normalized_chart_id}"


def _make_stable_chart_id(parts: Sequence[str]) -> str:
    joined = "|".join(str(part).strip() for part in parts if str(part).strip())
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]
    safe_prefix = "_".join(
        "".join(
            ch for ch in str(part).lower() if ch.isalnum() or ch in {"-", "_"}
        ).strip("_-")
        for part in parts[:3]
        if str(part).strip()
    )
    safe_prefix = safe_prefix[:60] if safe_prefix else "chart"
    return f"{safe_prefix}_{digest}"


def _sales_chart_cap_facet_values(
    chart_df: pl.DataFrame,
    *,
    facet_column: str,
    metric_column: str | None = None,
    max_panels: int = 4,
) -> tuple[pl.DataFrame, list[str]]:
    """Cap small-multiple facets and collapse excess values into an "Other" panel."""
    if facet_column not in chart_df.columns:
        return chart_df, []

    normalized = chart_df.with_columns(
        pl.col(facet_column)
        .cast(pl.Utf8)
        .str.strip_chars()
        .fill_null("N/A")
        .alias(facet_column)
    )
    if metric_column and metric_column in normalized.columns:
        facet_totals = (
            normalized.group_by(facet_column)
            .agg(
                pl.col(metric_column)
                .cast(pl.Float64, strict=False)
                .fill_null(0.0)
                .sum()
                .alias("__facet_total")
            )
            .sort(["__facet_total", facet_column], descending=[True, False])
        )
    else:
        facet_totals = (
            normalized.group_by(facet_column)
            .agg(pl.len().alias("__facet_total"))
            .sort(["__facet_total", facet_column], descending=[True, False])
        )

    ranked_facets = [
        str(value).strip() or "N/A"
        for value in facet_totals.get_column(facet_column).to_list()
    ]
    if len(ranked_facets) <= max_panels:
        return normalized, ranked_facets

    keep_count = max(1, max_panels - 1)
    kept_facets = ranked_facets[:keep_count]
    collapsed = normalized.with_columns(
        pl.when(pl.col(facet_column).is_in(kept_facets))
        .then(pl.col(facet_column))
        .otherwise(pl.lit("Other"))
        .alias(facet_column)
    )
    return collapsed, [*kept_facets, "Other"]


def _build_sales_chart_id(
    *,
    chart_family: str,
    category_key: str,
    segment_id: str | None = None,
    attribute_id: str | None = None,
    brand_id: str | None = None,
    facet_id: str | None = None,
    metric: str | None = None,
    line_metric: str | None = None,
    retailers: Sequence[str],
    brands: Sequence[str],
    universe: str,
    start_month: str = "",
    end_month: str = "",
    month: str = "",
    top_n: int | None = None,
    row_top_n: int | None = None,
    col_top_n: int | None = None,
    aggregation: str | None = None,
    start_window_start: str = "",
    start_window_end: str = "",
    end_window_start: str = "",
    end_window_end: str = "",
    window_months: int | None = None,
    placeholders_csv: str = "",
    dataset_name: str | None = None,
) -> str:
    chart_family_norm = _sales_chart_dimension_id(chart_family)
    category_norm = _sales_chart_dimension_id(category_key)
    segment_norm = _sales_chart_dimension_id(segment_id or "")
    attribute_norm = _sales_chart_dimension_id(attribute_id or "")
    brand_norm = _sales_chart_dimension_id(brand_id or "")
    facet_norm = _sales_chart_dimension_id(facet_id or "")
    metric_norm = _sales_chart_dimension_id(metric or "")
    line_metric_norm = _sales_chart_dimension_id(line_metric or "")
    start_month_norm = str(start_month or "").strip()
    end_month_norm = str(end_month or "").strip()
    month_norm = str(month or "").strip()
    start_window_start_norm = str(start_window_start or "").strip()
    start_window_end_norm = str(start_window_end or "").strip()
    end_window_start_norm = str(end_window_start or "").strip()
    end_window_end_norm = str(end_window_end or "").strip()
    universe_norm = _sales_chart_dimension_id(universe or "full")

    if chart_family_norm == "combo_total_abs":
        parts = [
            chart_family_norm,
            category_norm,
            metric_norm,
            line_metric_norm,
            f"retailers={_sales_chart_canonical_csv(retailers)}",
            f"brands={_sales_chart_canonical_csv(brands)}",
            f"universe={universe_norm}",
            f"start_month={start_month_norm}",
            f"end_month={end_month_norm}",
            f"spec={_SALES_CHART_ID_SPEC_VERSION}",
        ]
    elif chart_family_norm == "stacked_abs":
        parts = [
            chart_family_norm,
            segment_norm,
            category_norm,
            metric_norm,
            f"retailers={_sales_chart_canonical_csv(retailers)}",
            f"brands={_sales_chart_canonical_csv(brands)}",
            f"universe={universe_norm}",
            f"start_month={start_month_norm}",
            f"end_month={end_month_norm}",
            f"top_n={int(top_n or 8)}",
            f"placeholders={placeholders_csv}",
            f"spec={_SALES_CHART_ID_SPEC_VERSION}",
        ]
        if facet_norm:
            parts.append(f"facet={facet_norm}")
    elif chart_family_norm == "stacked":
        parts = [
            chart_family_norm,
            segment_norm,
            category_norm,
        ]
        if metric_norm:
            parts.append(f"metric={metric_norm}")
        parts.extend(
            [
                f"retailers={_sales_chart_canonical_csv(retailers)}",
                f"brands={_sales_chart_canonical_csv(brands)}",
                f"universe={universe_norm}",
                f"start_month={start_month_norm}",
                f"end_month={end_month_norm}",
                f"top_n={int(top_n or 8)}",
                f"agg={_sales_chart_dimension_id(aggregation or 'monthly')}",
                f"placeholders={placeholders_csv}",
                f"spec={_SALES_CHART_ID_SPEC_VERSION}",
            ]
        )
    elif chart_family_norm == "stacked_facets":
        parts = [
            chart_family_norm,
            segment_norm,
            category_norm,
            f"facet={facet_norm}",
        ]
        if metric_norm:
            parts.append(f"metric={metric_norm}")
        parts.extend(
            [
                f"retailers={_sales_chart_canonical_csv(retailers)}",
                f"brands={_sales_chart_canonical_csv(brands)}",
                f"universe={universe_norm}",
                f"start_month={start_month_norm}",
                f"end_month={end_month_norm}",
                f"top_n={int(top_n or 6)}",
                f"agg={_sales_chart_dimension_id(aggregation or 'monthly')}",
                f"placeholders={placeholders_csv}",
                f"spec={_SALES_CHART_ID_SPEC_VERSION}",
            ]
        )
    elif chart_family_norm in {"slope", "slope_facets", "timeline", "timeline_facets"}:
        parts = [
            chart_family_norm,
            attribute_norm,
            category_norm,
            brand_norm,
            f"retailers={_sales_chart_canonical_csv(retailers)}",
            f"brands={_sales_chart_canonical_csv(brands)}",
            f"universe={universe_norm}",
            f"top_n={int(top_n or 14)}",
            f"placeholders={placeholders_csv}",
            f"spec={_SALES_CHART_ID_SPEC_VERSION}",
        ]
        if (
            start_window_start_norm
            and start_window_end_norm
            and end_window_start_norm
            and end_window_end_norm
        ):
            months = int(window_months or 12)
            parts.extend(
                [
                    f"window=rolling_{months}m",
                    f"start_window_start={start_window_start_norm}",
                    f"start_window_end={start_window_end_norm}",
                    f"end_window_start={end_window_start_norm}",
                    f"end_window_end={end_window_end_norm}",
                ]
            )
        else:
            parts.extend(
                [
                    f"start_month={start_month_norm}",
                    f"end_month={end_month_norm}",
                ]
            )
        if facet_norm:
            parts.append(f"facet={facet_norm}")
    elif chart_family_norm in {
        "kernel_density",
        "histogram",
        "boxplot",
        "ecdf",
        "stripplot",
    }:
        parts = [
            chart_family_norm,
            category_norm,
            f"segment={segment_norm}",
            f"metric={metric_norm}",
            f"retailers={_sales_chart_canonical_csv(retailers)}",
            f"brands={_sales_chart_canonical_csv(brands)}",
            f"universe={universe_norm}",
            f"month={month_norm}",
            f"spec={_SALES_CHART_ID_SPEC_VERSION}",
        ]
    else:
        parts = [
            chart_family_norm,
            category_norm,
            f"retailers={_sales_chart_canonical_csv(retailers)}",
            f"brands={_sales_chart_canonical_csv(brands)}",
            f"spec={_SALES_CHART_ID_SPEC_VERSION}",
        ]

    raw_chart_id = _make_stable_chart_id(parts)
    return _sales_chart_with_dataset_prefix(raw_chart_id, dataset_name)


def _filter_placeholder_only_parents(
    parents: pl.DataFrame,
    *,
    variant_pool: pl.DataFrame | None,
    placeholder_values: Iterable[str],
    attribute_columns: Sequence[str],
) -> pl.DataFrame:
    """Drop parent rows that have no usable product name, no images, and only placeholder attributes.

    These rows typically come from incomplete PDP parsing and create "ID-only" cards in the catalog view.
    """
    if parents.is_empty():
        return parents
    if (
        "parent_product_id" not in parents.columns
        or "product_name" not in parents.columns
    ):
        return parents

    placeholders = {
        str(val).strip().lower() for val in placeholder_values if str(val).strip()
    }

    def _meaningful_column_expr(df: pl.DataFrame, col: str) -> pl.Expr:
        dtype = df.schema.get(col)
        if dtype == pl.Utf8:
            text = pl.col(col).cast(pl.Utf8).str.strip_chars()
            return (
                text.is_not_null()
                & (text != "")
                & ~text.str.to_lowercase().is_in(list(placeholders))
            )
        return pl.col(col).is_not_null()

    # Treat "product_name == parent_product_id" as missing (it creates ID-only cards).
    product_name_raw = pl.col("product_name").cast(pl.Utf8).str.strip_chars()
    parent_id_raw = pl.col("parent_product_id").cast(pl.Utf8).str.strip_chars()
    product_name_expr = (
        product_name_raw.is_not_null()
        & (product_name_raw != "")
        & ~product_name_raw.str.to_lowercase().is_in(list(placeholders))
        & (parent_id_raw.is_null() | (product_name_raw != parent_id_raw))
    )

    attr_cols = [col for col in attribute_columns if col in parents.columns]
    attr_exprs = [_meaningful_column_expr(parents, col) for col in attr_cols]
    has_meaningful_attrs = (
        pl.any_horizontal(attr_exprs) if attr_exprs else pl.lit(False)
    )

    image_exprs: list[pl.Expr] = []
    for col in ("hero_image_url", "swatch_image_url"):
        if col in parents.columns:
            image_exprs.append(_meaningful_column_expr(parents, col))
    has_parent_image = pl.any_horizontal(image_exprs) if image_exprs else pl.lit(False)

    has_variant_image_expr = pl.lit(False)
    if (
        variant_pool is not None
        and not variant_pool.is_empty()
        and "parent_product_id" in variant_pool.columns
        and (
            "hero_image_url" in variant_pool.columns
            or "swatch_image_url" in variant_pool.columns
        )
    ):
        select_cols = ["parent_product_id"]
        if "hero_image_url" in variant_pool.columns:
            select_cols.append("hero_image_url")
        if "swatch_image_url" in variant_pool.columns:
            select_cols.append("swatch_image_url")
        vp = variant_pool.select(select_cols)

        vp_exprs: list[pl.Expr] = []
        if "hero_image_url" in vp.columns:
            vp_exprs.append(
                _meaningful_column_expr(vp, "hero_image_url").alias("_hero_ok")
            )
        else:
            vp_exprs.append(pl.lit(False).alias("_hero_ok"))
        if "swatch_image_url" in vp.columns:
            vp_exprs.append(
                _meaningful_column_expr(vp, "swatch_image_url").alias("_swatch_ok")
            )
        else:
            vp_exprs.append(pl.lit(False).alias("_swatch_ok"))

        variant_images = (
            vp.with_columns(vp_exprs)
            .group_by("parent_product_id")
            .agg(
                (pl.col("_hero_ok").any() | pl.col("_swatch_ok").any()).alias(
                    "_has_variant_image"
                )
            )
        )
        parents = parents.join(variant_images, on="parent_product_id", how="left")
        has_variant_image_expr = pl.col("_has_variant_image").fill_null(False)

    has_any_image = has_parent_image | has_variant_image_expr
    filtered = parents.filter(product_name_expr | has_meaningful_attrs | has_any_image)
    return (
        filtered.drop("_has_variant_image")
        if "_has_variant_image" in filtered.columns
        else filtered
    )


def _parse_audit_evidence(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        return {"raw": text}
    return {"raw": str(raw)}


def _record_audit_key(
    record: Mapping[str, Any], record_type: str
) -> tuple[str, str, str] | None:
    retailer = str(record.get("retailer") or "").strip()
    parent_key = (
        record.get("parent_product_id") or record.get("product") or record.get("parent")
    )
    parent_id = str(parent_key or "").strip()
    if not parent_id:
        return None
    variant_id = ""
    if record_type == "variant":
        variant_key = record.get("variant_id") or record.get("variant")
        variant_id = str(variant_key or "").strip()
    return (retailer, parent_id, variant_id)


def _normalize_audit_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _attribute_id_candidates(
    attribute_id: str | None, attribute_column: str | None = None
) -> list[str]:
    candidates: list[str] = []

    def _add(value: str | None) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        if text not in candidates:
            candidates.append(text)
        lowered = text.lower()
        if lowered and lowered not in candidates:
            candidates.append(lowered)

    def _expand(value: str | None) -> None:
        text = _normalize_audit_value(value)
        if text is None:
            return
        collapsed = re.sub(r"\s+", " ", text)
        _add(collapsed)
        variants = [
            collapsed.replace("_", " "),
            collapsed.replace("_", "-"),
            collapsed.replace("_", "/"),
            collapsed.replace(" ", "_"),
            collapsed.replace("-", "_"),
            collapsed.replace("/", "_"),
            collapsed.replace("-", " "),
            collapsed.replace("/", " "),
        ]
        for variant in variants:
            _add(re.sub(r"\s+", " ", variant))

    _expand(attribute_id)
    _expand(attribute_column)
    return candidates


def _normalize_attribute_id_token(value: object) -> str:
    text = _normalize_audit_value(value) or ""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _attribute_id_normalized_candidates(
    attribute_candidates: Sequence[str],
) -> list[str]:
    normalized: list[str] = []
    for candidate in attribute_candidates:
        token = _normalize_attribute_id_token(candidate)
        if token and token not in normalized:
            normalized.append(token)
    return normalized


def _load_resolution_consensus_frame() -> pl.DataFrame:
    try:
        return attribute_resolution_history.read_resolution_consensus()
    except Exception:  # pragma: no cover - defensive
        return pl.DataFrame()


def _collect_consensus_map(
    *,
    attribute_candidates: Sequence[str],
    row_type: str,
    keys: Sequence[tuple[str, str, str]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not attribute_candidates or not keys:
        return {}
    consensus_df = _load_resolution_consensus_frame()
    required_cols = {
        "row_type",
        "retailer",
        "parent_product_id",
        "variant_id",
        "attribute_id",
        "support_runs",
        "total_runs",
        "agreement_rate",
        "certainty_class",
        "supporting_steps",
    }
    if consensus_df.is_empty() or not required_cols.issubset(set(consensus_df.columns)):
        return {}
    available_runs_raw = consensus_df.select(pl.col("total_runs").max()).item()
    available_runs = (
        int(available_runs_raw)
        if isinstance(available_runs_raw, (int, float)) and available_runs_raw > 0
        else None
    )

    normalized_candidates = _attribute_id_normalized_candidates(attribute_candidates)
    attribute_filter_expr = pl.col("attribute_id").is_in(list(attribute_candidates))
    if normalized_candidates:
        attribute_filter_expr = attribute_filter_expr | (
            pl.col("attribute_id")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .str.to_lowercase()
            .str.replace_all(r"[^a-z0-9]+", "")
            .is_in(normalized_candidates)
        )

    key_frame = pl.from_dicts(
        [
            {
                "retailer": retailer,
                "parent_product_id": parent_id,
                "variant_id": variant_id,
            }
            for retailer, parent_id, variant_id in keys
        ]
    ).unique()

    filtered = (
        consensus_df.filter((pl.col("row_type") == row_type) & attribute_filter_expr)
        .join(
            key_frame,
            on=["retailer", "parent_product_id", "variant_id"],
            how="inner",
        )
        .sort(
            [
                "retailer",
                "parent_product_id",
                "variant_id",
                "support_runs",
                "agreement_rate",
                "total_runs",
                "attribute_id",
            ],
            descending=[False, False, False, True, True, True, False],
        )
        .group_by(["retailer", "parent_product_id", "variant_id"], maintain_order=True)
        .agg(
            [
                pl.col("support_runs").first().alias("support_runs"),
                pl.col("total_runs").first().alias("total_runs"),
                pl.col("agreement_rate").first().alias("agreement_rate"),
                pl.col("certainty_class").first().alias("certainty_class"),
                pl.col("supporting_steps").first().alias("supporting_steps"),
            ]
        )
    )
    if filtered.is_empty():
        return {}

    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in filtered.to_dicts():
        key = (
            str(row.get("retailer") or "").strip(),
            str(row.get("parent_product_id") or "").strip(),
            str(row.get("variant_id") or "").strip(),
        )
        if not key[1]:
            continue
        support_runs_raw = row.get("support_runs")
        total_runs_raw = row.get("total_runs")
        support_runs = (
            int(support_runs_raw)
            if isinstance(support_runs_raw, (int, float))
            else None
        )
        total_runs = (
            int(total_runs_raw) if isinstance(total_runs_raw, (int, float)) else None
        )
        agreement_rate_raw = row.get("agreement_rate")
        agreement_rate = (
            float(agreement_rate_raw)
            if isinstance(agreement_rate_raw, (int, float))
            else None
        )
        certainty_class = _normalize_audit_value(row.get("certainty_class"))
        supporting_steps_raw = row.get("supporting_steps")
        supporting_steps: list[str] = []
        if isinstance(supporting_steps_raw, list):
            supporting_steps = [
                str(step).strip() for step in supporting_steps_raw if str(step).strip()
            ]
        result[key] = {
            "promoted": certainty_class == "sure",
            "support_runs": support_runs,
            "total_runs": total_runs,
            "available_runs": available_runs,
            "agreement_rate": agreement_rate,
            "certainty_class": certainty_class,
            "supporting_steps": supporting_steps,
        }
    return result


def _is_meaningful_audit_value(value: object) -> bool:
    text = _normalize_audit_value(value)
    if text is None:
        return False
    lowered = text.lower()
    if lowered in {"", "n/a", "na", "none", "unknown", "-", "--"}:
        return False
    if lowered.startswith("not in taxonomy"):
        return False
    return True


def _infer_supporting_step_from_audit_payload(payload: Mapping[str, Any]) -> str | None:
    evidence = payload.get("evidence")
    if isinstance(evidence, Mapping):
        step = _normalize_audit_value(evidence.get("step"))
        if step:
            return step
        stage_source = _normalize_audit_value(evidence.get("stage_source"))
        if stage_source:
            source = stage_source.lower()
            if source == "web":
                return "brand_web_search"
            if source == "llm":
                return "llm_pdp_lookup"
            return source

    source = (_normalize_audit_value(payload.get("source")) or "").lower()
    decision_rule = (_normalize_audit_value(payload.get("decision_rule")) or "").lower()
    combined = f"{source} {decision_rule}".strip()
    if "brand_web_search" in combined or "web_" in combined or source == "web":
        return "brand_web_search"
    if "vision" in combined:
        return "vision"
    if "llm" in combined:
        return "llm_pdp_lookup"
    if "cross_retailer_fill" in combined:
        return "cross_retailer_fill"
    if "parent_propagation" in combined:
        return "parent_propagation"
    if source:
        return source
    return None


def _attach_single_signal_metrics(payload: dict[str, Any]) -> None:
    if not _is_meaningful_audit_value(payload.get("value")):
        return
    if payload.get("promoted") is None:
        payload["promoted"] = False
    if payload.get("support_runs") is None:
        payload["support_runs"] = 1
    if payload.get("total_runs") is None:
        payload["total_runs"] = 1
    if payload.get("agreement_rate") is None:
        payload["agreement_rate"] = 1.0
    if payload.get("certainty_class") is None:
        payload["certainty_class"] = "uncertain"
    if payload.get("supporting_steps") is None:
        step = _infer_supporting_step_from_audit_payload(payload)
        payload["supporting_steps"] = [step] if step else []
    if payload.get("available_runs") is None:
        payload["available_runs"] = None


def _attach_history_metrics_from_audit_rows(
    payload: dict[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> bool:
    """Attach support/total metrics from explicit audit history rows when consensus is absent."""
    if not rows or not _is_meaningful_audit_value(payload.get("value")):
        return False

    payload_value = _normalize_audit_value(payload.get("value"))
    if not payload_value:
        return False

    payload_source = (_normalize_audit_value(payload.get("source")) or "").lower()

    history: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        value = _normalize_audit_value(row.get("value"))
        if not _is_meaningful_audit_value(value):
            continue
        source = (_normalize_audit_value(row.get("source")) or "").lower()
        timestamp = _normalize_audit_value(row.get("timestamp")) or ""
        dedupe_key = (source, timestamp, value.casefold())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        history.append((source, timestamp, value))

    if not history:
        return False

    scoped_history = history
    if payload_source:
        source_rows = [row for row in history if row[0] == payload_source]
        if source_rows:
            scoped_history = source_rows

    deterministic_seen = False
    collapsed_history: list[tuple[str, str, str]] = []
    for source, timestamp, value in scoped_history:
        if source == "deterministic":
            if deterministic_seen:
                continue
            deterministic_seen = True
        collapsed_history.append((source, timestamp, value))
    scoped_history = collapsed_history

    total_runs = len(scoped_history)
    support_runs = sum(
        1
        for _, _, value in scoped_history
        if value.casefold() == payload_value.casefold()
    )
    if total_runs <= 0 or support_runs <= 0:
        return False

    agreement_rate = float(support_runs) / float(total_runs)
    if payload.get("promoted") is None:
        payload["promoted"] = (
            support_runs == total_runs and total_runs >= _MIN_PROMOTION_SUPPORT_RUNS
        )
    payload["support_runs"] = support_runs
    payload["total_runs"] = total_runs
    payload["available_runs"] = total_runs
    payload["agreement_rate"] = agreement_rate
    if payload.get("certainty_class") is None:
        payload["certainty_class"] = (
            "sure"
            if (
                support_runs == total_runs and total_runs >= _MIN_PROMOTION_SUPPORT_RUNS
            )
            else "uncertain"
        )
    if payload.get("supporting_steps") is None:
        step = _infer_supporting_step_from_audit_payload(payload)
        payload["supporting_steps"] = [step] if step else []
    return True


def _build_audit_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": row.get("timestamp"),
        "source": row.get("source"),
        "decision_rule": row.get("decision_rule"),
        "value": row.get("value"),
        "evidence": _parse_audit_evidence(row.get("evidence_json")),
        "category_key": row.get("category_key"),
    }


def _parse_json_object(raw: object) -> dict[str, Any]:
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _parse_csv_attribute_list(raw: object) -> list[str]:
    if not isinstance(raw, str):
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _collect_csv_audit_candidates(
    *,
    attribute_id: str,
    row_type: str,
    keys: Sequence[tuple[str, str, str]],
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    key_set = set(keys)
    if not key_set:
        return {}
    candidates: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    if _WEB_FILL_AUDIT_CSV.is_file():
        web_cols = [
            "category_key",
            "source_retailer",
            "source_parent_product_id",
            "requested_parent_attributes",
            "requested_variant_attributes",
            "filled_parent_attributes",
            "filled_variant_attributes",
        ]
        web_df = pl.read_csv(_WEB_FILL_AUDIT_CSV)
        present_cols = [col for col in web_cols if col in web_df.columns]
        if present_cols:
            web_df = web_df.select(present_cols)
            for row in web_df.to_dicts():
                source_retailer = str(row.get("source_retailer") or "").strip()
                parent_id = str(row.get("source_parent_product_id") or "").strip()
                if not source_retailer or not parent_id:
                    continue
                category_key = _normalize_audit_value(row.get("category_key"))

                if row_type == "parent":
                    key = (source_retailer, parent_id, "")
                    if key not in key_set:
                        continue
                    requested = set(
                        _parse_csv_attribute_list(
                            row.get("requested_parent_attributes")
                        )
                    )
                    filled = _parse_json_object(row.get("filled_parent_attributes"))
                    if attribute_id not in requested and attribute_id not in filled:
                        continue
                    payload = filled.get(attribute_id)
                    value = payload.get("value") if isinstance(payload, dict) else None
                    confidence = (
                        payload.get("confidence") if isinstance(payload, dict) else None
                    )
                    evidence_url = (
                        payload.get("evidence_url")
                        if isinstance(payload, dict)
                        else None
                    )
                    candidates.setdefault(key, []).append(
                        {
                            "timestamp": None,
                            "source": "web",
                            "decision_rule": (
                                "web_confident" if value is not None else "web_no_value"
                            ),
                            "value": value,
                            "evidence": {
                                "confidence": confidence,
                                "evidence_url": evidence_url,
                                "provenance": "web_fill_audit_csv",
                            },
                            "category_key": category_key,
                        }
                    )
                elif row_type == "variant":
                    requested_variant_map = _parse_json_object(
                        row.get("requested_variant_attributes")
                    )
                    filled_variant_map = _parse_json_object(
                        row.get("filled_variant_attributes")
                    )
                    for variant_key, requested_values in requested_variant_map.items():
                        if not isinstance(variant_key, str):
                            continue
                        if isinstance(requested_values, list):
                            requested = {
                                str(item).strip()
                                for item in requested_values
                                if str(item).strip()
                            }
                        else:
                            requested = set()
                        variant_retailer = source_retailer
                        variant_id = variant_key
                        if ":" in variant_key:
                            retailer_part, variant_part = variant_key.split(":", 1)
                            variant_retailer = retailer_part.strip() or source_retailer
                            variant_id = variant_part.strip()
                        variant_id = str(variant_id or "").strip()
                        if not variant_id:
                            continue
                        key = (variant_retailer, parent_id, variant_id)
                        if key not in key_set:
                            continue
                        attrs = filled_variant_map.get(variant_key)
                        attrs_map = attrs if isinstance(attrs, dict) else {}
                        if (
                            attribute_id not in requested
                            and attribute_id not in attrs_map
                        ):
                            continue
                        payload = attrs_map.get(attribute_id)
                        value = (
                            payload.get("value") if isinstance(payload, dict) else None
                        )
                        confidence = (
                            payload.get("confidence")
                            if isinstance(payload, dict)
                            else None
                        )
                        evidence_url = (
                            payload.get("evidence_url")
                            if isinstance(payload, dict)
                            else None
                        )
                        candidates.setdefault(key, []).append(
                            {
                                "timestamp": None,
                                "source": "web",
                                "decision_rule": (
                                    "web_confident"
                                    if value is not None
                                    else "web_no_value"
                                ),
                                "value": value,
                                "evidence": {
                                    "confidence": confidence,
                                    "evidence_url": evidence_url,
                                    "provenance": "web_fill_audit_csv",
                                },
                                "category_key": category_key,
                            }
                        )

    if row_type == "parent" and _VISION_FILL_AUDIT_CSV.is_file():
        vision_cols = [
            "category_key",
            "source_retailer",
            "source_parent_product_id",
            "hero_image_url",
            "image_source",
            "image_path",
            "requested_attributes",
            "filled_attributes",
        ]
        vision_df = pl.read_csv(_VISION_FILL_AUDIT_CSV)
        present_cols = [col for col in vision_cols if col in vision_df.columns]
        if present_cols:
            vision_df = vision_df.select(present_cols)
            for row in vision_df.to_dicts():
                source_retailer = str(row.get("source_retailer") or "").strip()
                parent_id = str(row.get("source_parent_product_id") or "").strip()
                if not source_retailer or not parent_id:
                    continue
                key = (source_retailer, parent_id, "")
                if key not in key_set:
                    continue
                category_key = _normalize_audit_value(row.get("category_key"))
                requested = set(
                    _parse_csv_attribute_list(row.get("requested_attributes"))
                )
                filled = _parse_json_object(row.get("filled_attributes"))
                if attribute_id not in requested and attribute_id not in filled:
                    continue
                payload = filled.get(attribute_id)
                value = payload.get("value") if isinstance(payload, dict) else None
                confidence = (
                    payload.get("confidence") if isinstance(payload, dict) else None
                )
                candidates.setdefault(key, []).append(
                    {
                        "timestamp": None,
                        "source": "vision",
                        "decision_rule": (
                            "vision_confident"
                            if value is not None
                            else "vision_no_value"
                        ),
                        "value": value,
                        "evidence": {
                            "confidence": confidence,
                            "hero_image_url": row.get("hero_image_url"),
                            "image_source": row.get("image_source"),
                            "image_path": row.get("image_path"),
                            "provenance": "vision_fill_audit_csv",
                        },
                        "category_key": category_key,
                    }
                )

    return candidates


def _attach_attribute_audit(
    records: list[dict[str, Any]],
    *,
    record_type: str,
    attribute_id: str | None,
    attribute_column: str | None = None,
) -> None:
    if not attribute_id or not records:
        return
    attribute_candidates = _attribute_id_candidates(attribute_id, attribute_column)
    if not attribute_candidates:
        return
    keys: list[tuple[str, str, str]] = []
    for record in records:
        key = _record_audit_key(record, record_type)
        if key:
            keys.append(key)
    if not keys:
        return
    store = PDPStore(DEFAULT_PDP_STORE_PATH)
    audit_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    seen_rows: set[tuple[Any, ...]] = set()
    for candidate_attr_id in attribute_candidates:
        try:
            candidate_rows = store.fetch_attribute_audit_rows(
                attribute_id=candidate_attr_id,
                row_type=record_type,
                keys=keys,
            )
        except RuntimeError:
            candidate_rows = []
        for row in candidate_rows:
            dedupe_key = (
                row.get("timestamp"),
                row.get("source"),
                row.get("row_type"),
                row.get("retailer"),
                row.get("parent_product_id"),
                row.get("variant_id"),
                row.get("attribute_id"),
                row.get("value"),
                row.get("decision_rule"),
            )
            if dedupe_key in seen_rows:
                continue
            seen_rows.add(dedupe_key)
            rows.append(row)
    audit_rows_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            str(row.get("retailer") or "").strip(),
            str(row.get("parent_product_id") or "").strip(),
            str(row.get("variant_id") or "").strip(),
        )
        audit_rows_by_key.setdefault(key, []).append(row)

    for record in records:
        key = _record_audit_key(record, record_type)
        if not key or key in audit_map:
            continue
        candidates = audit_rows_by_key.get(key, [])
        if not candidates:
            continue
        target_value = _normalize_audit_value(
            record.get(attribute_column) if attribute_column else None
        )
        chosen: dict[str, Any] | None = None
        if target_value:
            for candidate in candidates:
                candidate_value = _normalize_audit_value(candidate.get("value"))
                if (
                    candidate_value
                    and candidate_value.casefold() == target_value.casefold()
                ):
                    chosen = candidate
                    break
        if chosen is None and target_value:
            for candidate in candidates:
                if _is_meaningful_audit_value(candidate.get("value")):
                    chosen = candidate
                    break
        if chosen is None:
            chosen = candidates[0]
        audit_map[key] = _build_audit_payload(chosen)

    unique_keys = list(dict.fromkeys(keys))
    unresolved_keys = [key for key in unique_keys if key not in audit_map]

    if unresolved_keys:
        try:
            ledger_df = attribute_resolution_history.read_resolution_ledger()
        except TypeError:
            try:
                # Test doubles may not accept keyword arguments.
                ledger_df = attribute_resolution_history.read_resolution_ledger()
            except Exception:  # pragma: no cover - defensive fallback
                ledger_df = pl.DataFrame()
        except Exception:  # pragma: no cover - defensive fallback
            ledger_df = pl.DataFrame()

        required_cols = {
            "row_type",
            "retailer",
            "parent_product_id",
            "variant_id",
            "attribute_id",
            "recorded_at",
            "source",
            "decision_rule",
            "value",
            "confidence",
            "evidence_url",
            "category_key",
            "step",
        }
        if not ledger_df.is_empty() and required_cols.issubset(set(ledger_df.columns)):
            normalized_candidates = _attribute_id_normalized_candidates(
                attribute_candidates
            )
            attribute_filter_expr = pl.col("attribute_id").is_in(attribute_candidates)
            if normalized_candidates:
                attribute_filter_expr = attribute_filter_expr | (
                    pl.col("attribute_id")
                    .cast(pl.Utf8, strict=False)
                    .fill_null("")
                    .str.to_lowercase()
                    .str.replace_all(r"[^a-z0-9]+", "")
                    .is_in(normalized_candidates)
                )
            key_frame = pl.from_dicts(
                [
                    {
                        "retailer": retailer,
                        "parent_product_id": parent_id,
                        "variant_id": variant_id,
                    }
                    for retailer, parent_id, variant_id in unresolved_keys
                ]
            ).unique()
            ledger_rows = (
                ledger_df.filter(
                    attribute_filter_expr & (pl.col("row_type") == record_type)
                )
                .join(
                    key_frame,
                    on=["retailer", "parent_product_id", "variant_id"],
                    how="inner",
                )
                .sort("recorded_at", descending=True)
                .to_dicts()
            )
            ledger_map: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            for row in ledger_rows:
                key = (
                    str(row.get("retailer") or "").strip(),
                    str(row.get("parent_product_id") or "").strip(),
                    str(row.get("variant_id") or "").strip(),
                )
                ledger_map.setdefault(key, []).append(row)

            for record in records:
                key = _record_audit_key(record, record_type)
                if not key or key in audit_map:
                    continue
                candidates = ledger_map.get(key, [])
                if not candidates:
                    continue
                target_value = _normalize_audit_value(
                    record.get(attribute_column) if attribute_column else None
                )
                chosen: dict[str, Any] | None = None
                if target_value:
                    for candidate in candidates:
                        candidate_value = _normalize_audit_value(candidate.get("value"))
                        if (
                            candidate_value
                            and candidate_value.casefold() == target_value.casefold()
                        ):
                            chosen = candidate
                            break
                if chosen is None and target_value:
                    for candidate in candidates:
                        if _is_meaningful_audit_value(candidate.get("value")):
                            chosen = candidate
                            break
                if chosen is None and candidates:
                    chosen = candidates[0]
                if chosen is None:
                    continue

                confidence = chosen.get("confidence")
                evidence_url = _normalize_audit_value(chosen.get("evidence_url"))
                evidence: dict[str, Any] = {
                    "provenance": "resolution_ledger",
                    "step": chosen.get("step"),
                }
                if confidence is not None:
                    evidence["confidence"] = confidence
                if evidence_url:
                    evidence["evidence_url"] = evidence_url
                audit_map[key] = {
                    "timestamp": chosen.get("recorded_at"),
                    "source": chosen.get("source"),
                    "decision_rule": chosen.get("decision_rule"),
                    "value": chosen.get("value"),
                    "evidence": evidence,
                    "category_key": chosen.get("category_key"),
                }

    unresolved_keys = [key for key in unique_keys if key not in audit_map]
    if unresolved_keys:
        stage_rows = []
        seen_stage_rows: set[tuple[Any, ...]] = set()
        for candidate_attr_id in attribute_candidates:
            try:
                candidate_rows = store.fetch_attribute_stage_rows(
                    attribute_id=candidate_attr_id,
                    row_type=record_type,
                    keys=unresolved_keys,
                    sources=("llm", "deterministic"),
                )
            except RuntimeError:
                candidate_rows = []
            for row in candidate_rows:
                dedupe_key = (
                    row.get("source"),
                    row.get("row_type"),
                    row.get("retailer"),
                    row.get("parent_product_id"),
                    row.get("variant_id"),
                    row.get("attribute_id"),
                    row.get("value"),
                    row.get("updated_at"),
                )
                if dedupe_key in seen_stage_rows:
                    continue
                seen_stage_rows.add(dedupe_key)
                stage_rows.append(row)

        stage_map: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in stage_rows:
            key = (
                str(row.get("retailer") or "").strip(),
                str(row.get("parent_product_id") or "").strip(),
                str(row.get("variant_id") or "").strip(),
            )
            stage_map.setdefault(key, []).append(row)

        source_priority = ("llm", "deterministic")
        for record in records:
            key = _record_audit_key(record, record_type)
            if not key or key in audit_map:
                continue
            candidates = stage_map.get(key, [])
            if not candidates:
                continue
            ordered_candidates: list[dict[str, Any]] = []
            for source in source_priority:
                source_rows = [
                    row
                    for row in candidates
                    if str(row.get("source") or "").strip() == source
                ]
                source_rows.sort(
                    key=lambda row: str(row.get("updated_at") or ""), reverse=True
                )
                ordered_candidates.extend(source_rows)
            other_rows = [
                row
                for row in candidates
                if str(row.get("source") or "").strip() not in source_priority
            ]
            other_rows.sort(
                key=lambda row: str(row.get("updated_at") or ""), reverse=True
            )
            ordered_candidates.extend(other_rows)

            target_value = _normalize_audit_value(
                record.get(attribute_column) if attribute_column else None
            )
            chosen: dict[str, Any] | None = None
            if target_value:
                for candidate in ordered_candidates:
                    candidate_value = _normalize_audit_value(candidate.get("value"))
                    if (
                        candidate_value
                        and candidate_value.casefold() == target_value.casefold()
                    ):
                        chosen = candidate
                        break
            if chosen is None and target_value:
                for candidate in ordered_candidates:
                    if _is_meaningful_audit_value(candidate.get("value")):
                        chosen = candidate
                        break
            if chosen is None:
                if ordered_candidates:
                    chosen = ordered_candidates[0]
                else:
                    continue

            chosen_source = str(chosen.get("source") or "").strip()
            decision_rule = (
                f"{chosen_source}_stage_value" if chosen_source else "stage_value"
            )
            evidence = {
                "updated_at": chosen.get("updated_at"),
                "stage_source": chosen_source or None,
            }
            oov_candidate = _normalize_audit_value(chosen.get("oov_candidate"))
            note = _normalize_audit_value(chosen.get("note"))
            if oov_candidate:
                evidence["oov_candidate"] = oov_candidate
            if note:
                evidence["note"] = note
            audit_map[key] = {
                "timestamp": chosen.get("updated_at"),
                "source": chosen_source or None,
                "decision_rule": decision_rule,
                "value": chosen.get("value"),
                "evidence": evidence,
                "category_key": None,
            }

    unresolved_keys = [key for key in unique_keys if key not in audit_map]
    if unresolved_keys:
        csv_candidates: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for candidate_attr_id in attribute_candidates:
            candidate_map = _collect_csv_audit_candidates(
                attribute_id=candidate_attr_id,
                row_type=record_type,
                keys=unresolved_keys,
            )
            for key, rows_for_key in candidate_map.items():
                csv_candidates.setdefault(key, []).extend(rows_for_key)
        source_priority = {"web": 0, "vision": 1}
        for record in records:
            key = _record_audit_key(record, record_type)
            if not key or key in audit_map:
                continue
            candidates = csv_candidates.get(key, [])
            if not candidates:
                continue
            ordered_candidates = sorted(
                candidates,
                key=lambda candidate: source_priority.get(
                    str(candidate.get("source") or "").strip(), 99
                ),
            )
            target_value = _normalize_audit_value(
                record.get(attribute_column) if attribute_column else None
            )
            chosen: dict[str, Any] | None = None
            if target_value:
                for candidate in ordered_candidates:
                    candidate_value = _normalize_audit_value(candidate.get("value"))
                    if (
                        candidate_value
                        and candidate_value.casefold() == target_value.casefold()
                    ):
                        chosen = candidate
                        break
            if chosen is None and target_value:
                for candidate in ordered_candidates:
                    if _is_meaningful_audit_value(candidate.get("value")):
                        chosen = candidate
                        break
            if chosen is None and ordered_candidates:
                chosen = ordered_candidates[0]
            if chosen is None:
                continue
            audit_map[key] = chosen

    consensus_map = _collect_consensus_map(
        attribute_candidates=attribute_candidates,
        row_type=record_type,
        keys=unique_keys,
    )

    for record in records:
        key = _record_audit_key(record, record_type)
        if key and key in audit_map:
            payload = dict(audit_map[key])
            consensus = consensus_map.get(key)
            if consensus:
                payload["promoted"] = bool(consensus.get("promoted"))
                payload["support_runs"] = consensus.get("support_runs")
                payload["total_runs"] = consensus.get("total_runs")
                payload["available_runs"] = consensus.get("available_runs")
                payload["agreement_rate"] = consensus.get("agreement_rate")
                payload["certainty_class"] = consensus.get("certainty_class")
                payload["supporting_steps"] = consensus.get("supporting_steps") or []
            else:
                history_rows = audit_rows_by_key.get(key, [])
                if not _attach_history_metrics_from_audit_rows(payload, history_rows):
                    _attach_single_signal_metrics(payload)
            record["attribute_audit"] = payload


def _gather_records(
    *,
    retailer: Optional[Sequence[str]],
    category_keys: List[str],
    brands: List[str],
    record_type: str,
    filters: List[str],
    limit: Optional[int],
    download_all: bool,
    pareto_filter: List[str],
    price_band_filter: List[str],
    hybrid_filter_selection: Mapping[str, tuple[bool, bool]],
    audit_attribute_id: str | None = None,
) -> RecordsResponse:
    selected_keys = _normalize_category_keys(category_keys)
    if not selected_keys:
        raise HTTPException(
            status_code=400, detail="At least one category key is required."
        )

    tables = _get_tables_for_coverage()
    tables = filter_tables_by_retailer(tables, retailer)
    tables = filter_tables_by_brands(tables, brands or [])
    tables = filter_tables_by_categories(tables, selected_keys)

    parent_source = (
        tables.parents_all if not tables.parents_all.is_empty() else tables.parents
    )
    tables_for_filters = ReviewTables(
        parents=parent_source,
        variants=tables.variants,
        combined=tables.combined,
        parents_all=tables.parents_all,
    )

    taxonomy = get_attribute_taxonomy()
    category_lookup = build_category_lookup(taxonomy)
    filter_setup = prepare_attribute_filters(
        tables_for_filters, category_lookup, selected_keys
    )

    if record_type == "variant":
        display_df = tables.variants
    else:
        display_df = parent_source
        variant_sample_df = tables.variants
    variant_samples: Dict[str, Dict[str, Any]] = {}

    filter_map = _parse_attribute_filters(filters or None)
    if filter_map and filter_setup.attr_column_lookup:
        display_df = apply_attribute_filters(
            display_df,
            filter_map,
            filter_setup.attr_column_lookup,
            placeholder_values=filter_setup.placeholder_values,
        )
        if record_type == "parent" and variant_sample_df is not None:
            variant_sample_df = apply_attribute_filters(
                variant_sample_df,
                filter_map,
                filter_setup.attr_column_lookup,
                placeholder_values=filter_setup.placeholder_values,
            )

    # Annotate with price-band fields and category metadata
    category_meta = {}
    try:
        display_df, category_meta = _annotate_records_with_sales_and_price(
            display_df,
            tables,
            retailer,
            selected_keys,
            record_type,
        )
        if (
            record_type == "parent"
            and variant_sample_df is not None
            and not variant_sample_df.is_empty()
        ):
            variant_sample_df, _ = _annotate_records_with_sales_and_price(
                variant_sample_df,
                tables,
                retailer,
                selected_keys,
                "variant",
            )
    except Exception:
        category_meta = {}

    def _apply_special_filters(df: pl.DataFrame) -> pl.DataFrame:
        if df.is_empty():
            return df
        result = df
        if price_band_filter:
            allowed = {
                str(val).strip().lower()
                for val in price_band_filter
                if str(val).strip()
            }
            if allowed and "price_band" in result.columns:
                result = result.filter(
                    pl.col("price_band")
                    .cast(pl.Utf8)
                    .str.to_lowercase()
                    .is_in(list(allowed))
                )
        return _apply_hybrid_filters(result, selection=hybrid_filter_selection)

    display_df = _apply_special_filters(display_df)
    if record_type == "parent" and variant_sample_df is not None:
        variant_sample_df = _apply_special_filters(variant_sample_df)

    if display_df.is_empty():
        effective_limit = 0 if download_all or limit is None else limit
        return RecordsResponse(total=0, limit=effective_limit, records=[])

    display_df = ensure_record_identifiers(display_df, record_type)

    if record_type == "parent":
        variant_pool = variant_sample_df if filter_map else tables.variants
        if variant_pool is not None and not variant_pool.is_empty():
            sample_df = ensure_record_identifiers(variant_pool, "variant")
            sample_records = sample_df.to_dicts()
            for sample in sample_records:
                parent_key = (
                    sample.get("parent_product_id")
                    or sample.get("product")
                    or sample.get("parent")
                )
                if not parent_key:
                    continue
                parent_key = str(parent_key)
                if parent_key and parent_key not in variant_samples:
                    variant_samples[parent_key] = sample

        # Drop placeholder-only parent rows that have no usable name and no images.
        display_df = _filter_placeholder_only_parents(
            display_df,
            variant_pool=variant_pool,
            placeholder_values=filter_setup.placeholder_values,
            attribute_columns=[
                str(attr.get("column", ""))
                for attr in filter_setup.valid_attributes
                if isinstance(attr, dict) and str(attr.get("column", "")).strip()
            ],
        )

    total = display_df.height
    if download_all or limit is None:
        effective_limit = total
        limited = display_df
    else:
        effective_limit = limit
        limited = display_df.head(limit) if limit < total else display_df
    records = limited.to_dicts()

    if record_type == "variant":
        parent_url_map: dict[str, str] = {}
        parent_candidates = parent_source
        if parent_candidates is not None and not parent_candidates.is_empty():
            if (
                "parent_product_id" in parent_candidates.columns
                and "pdp_url" in parent_candidates.columns
            ):
                for row in parent_candidates.select(
                    ["parent_product_id", "pdp_url"]
                ).to_dicts():
                    pid = str(row.get("parent_product_id") or "").strip()
                    url = str(row.get("pdp_url") or "").strip()
                    if pid and url:
                        parent_url_map.setdefault(pid, url)

        if parent_url_map:
            for record in records:
                parent_key = (
                    record.get("parent_product_id")
                    or record.get("product")
                    or record.get("parent")
                )
                pid = str(parent_key or "").strip()
                if not pid:
                    continue
                current_url = str(record.get("pdp_url") or "").strip()
                if not current_url:
                    fallback = parent_url_map.get(pid)
                    if fallback:
                        record["pdp_url"] = fallback

    if record_type == "parent" and variant_samples:

        def _first_value(*candidates: Any) -> str | None:
            for candidate in candidates:
                if isinstance(candidate, str):
                    stripped = candidate.strip()
                    if stripped:
                        return stripped
            return None

        for record in records:
            parent_key = (
                record.get("parent_product_id")
                or record.get("product")
                or record.get("parent")
            )
            if not parent_key:
                continue
            parent_key = str(parent_key)
            sample = variant_samples.get(parent_key)
            if not sample:
                continue

            hero_missing = not _first_value(record.get("hero_image_url"))
            swatch_missing = not _first_value(record.get("swatch_image_url"))

            if hero_missing:
                hero_candidate = _first_value(
                    sample.get("hero_image_url"),
                    sample.get("swatch_image_url"),
                )
                if hero_candidate:
                    record["hero_image_url"] = hero_candidate
            if swatch_missing:
                swatch_candidate = _first_value(sample.get("swatch_image_url"))
                if swatch_candidate:
                    record["swatch_image_url"] = swatch_candidate

            if sample.get("variant_id"):
                record.setdefault("sample_variant_id", sample.get("variant_id"))
            if sample.get("variant"):
                record.setdefault("sample_variant_name", sample.get("variant"))

    # Attach category-level metadata if available (computed first, fallback to cache)
    if not category_meta:
        try:
            meta_blob = (
                _CACHE_STATE.get("metadata", {}) if "_CACHE_STATE" in globals() else {}
            )
            if meta_blob and selected_keys:
                retailer_norm = (retailer or "").strip().lower()
                for key in selected_keys:
                    category_norm = str(key).strip().lower()
                    meta_key = f"{retailer_norm}:{category_norm}"
                    meta = meta_blob.get("category_meta", {}).get(meta_key)
                    if meta:
                        category_meta[category_norm] = meta
        except Exception:
            category_meta = {}

    for record in records:
        if "brand" in record and isinstance(record["brand"], str):
            record["brand"] = repair_text_encoding(record["brand"])
        if "retailer" in record and isinstance(record["retailer"], str):
            record["retailer"] = repair_text_encoding(record["retailer"])
        if "product_name" in record and isinstance(record["product_name"], str):
            record["product_name"] = repair_text_encoding(record["product_name"])
        if "variant_description" in record and isinstance(
            record["variant_description"], str
        ):
            record["variant_description"] = repair_text_encoding(
                record["variant_description"]
            )
        if "title_raw" in record and isinstance(record["title_raw"], str):
            record["title_raw"] = repair_text_encoding(record["title_raw"])
        if "title_normalized" in record and isinstance(record["title_normalized"], str):
            record["title_normalized"] = repair_text_encoding(
                record["title_normalized"]
            )

    def _normalize_text(value: object) -> str | None:
        if isinstance(value, str):
            text = repair_text_encoding(value).strip()
            return text or None
        return None

    def _compose_pdp_text(record: Mapping[str, Any]) -> str:
        existing = _normalize_text(record.get("pdp_text"))
        if existing:
            return existing

        fallback_fields = (
            "product_description",
            "description_markdown",
            "description",
            "long_description",
            "short_description",
            "usage",
            "ingredients",
            "restrictions",
            "benefits",
            "how_to_use",
            "details",
            "variant_description",
        )
        parts: list[str] = []
        seen: set[str] = set()
        for field in fallback_fields:
            value = record.get(field)
            if isinstance(value, (list, tuple)):
                candidates = value
            else:
                candidates = (value,)
            for candidate in candidates:
                text = _normalize_text(candidate)
                if not text or text in seen:
                    continue
                seen.add(text)
                parts.append(text)

        return "\n".join(parts).strip()

    for record in records:
        pdp_text = _compose_pdp_text(record)
        if pdp_text:
            record["pdp_text"] = pdp_text

    audit_attribute_column = (
        filter_setup.attr_column_lookup.get(audit_attribute_id)
        if audit_attribute_id
        else None
    )
    _attach_attribute_audit(
        records,
        record_type=record_type,
        attribute_id=audit_attribute_id,
        attribute_column=audit_attribute_column,
    )

    return RecordsResponse(
        total=total, limit=effective_limit, records=records, metadata=category_meta
    )


@router.get("/debug", response_model=StageTableResponse)
def fetch_stage_table(
    table: str = Query(
        ...,
        description=(
            "One of pdp_attributes_deterministic_explicit, "
            "pdp_attributes_deterministic, pdp_attributes_llm, pdp_attribute_values"
        ),
    ),
    retailer: Optional[str] = Query(None),
    parent_product_id: Optional[List[str]] = Query(None, alias="parent"),
    variant_id: Optional[List[str]] = Query(None, alias="variant"),
) -> StageTableResponse:
    parent_ids = parent_product_id or []
    variant_ids = variant_id or []
    try:
        table_df = load_stage_attribute_table(
            DEFAULT_PDP_STORE_PATH,
            table,
            retailer,
            parent_ids,
            variant_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    records = table_df.to_dicts() if not table_df.is_empty() else []
    return StageTableResponse(table=table, count=len(records), records=records)


@router.get("/images/{parent_id}")
def fetch_local_image(
    parent_id: str,
    variant_id: Optional[str] = Query(None, alias="variant"),
    prefer_remote: bool = Query(False),
) -> FileResponse:
    path = _resolve_image_path(parent_id, variant_id, prefer_remote=prefer_remote)
    if not path:
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(path)


@router.get("/health", response_model=HealthResponse, include_in_schema=False)
def healthcheck() -> HealthResponse:
    return HealthResponse()


def _build_presentations_router(presentations_dir: Path) -> APIRouter:
    """Create a router serving presentation assets with access control."""

    base_dir = presentations_dir.resolve()
    router = APIRouter(
        prefix="/presentations",
        include_in_schema=False,
        dependencies=[Depends(require_site_permission_for_request)],
    )

    def _resolve_requested_path(requested_path: str) -> Path:
        relative_str = requested_path.lstrip("/")
        target = (base_dir / relative_str).resolve()
        try:
            target.relative_to(base_dir)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found.",
            ) from exc
        if target.is_dir():
            index_file = find_index_file(target)
            if index_file is not None:
                return index_file
        return target

    def _serve_presentation_file(requested_path: str = "") -> FileResponse:
        target = _resolve_requested_path(requested_path)
        if target.suffix.lower() == ".pdf":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found.",
            )
        if not target.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found.",
            )
        return FileResponse(target)

    router.add_api_route(
        "",
        _serve_presentation_file,
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    router.add_api_route(
        "/{requested_path:path}",
        _serve_presentation_file,
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    return router


def _redirect_to_review_page(request: Request) -> RedirectResponse:
    target = "/review/page"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(url=target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@site_router.get(
    "/review/page",
    include_in_schema=False,
    dependencies=[Depends(require_site_permission_for_request)],
)
def review_page(request: Request) -> Any:
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )
    lang = resolve_language(request)
    page_label = get_navigation_label(lang, "/review/page")
    response = templates.TemplateResponse(
        request,
        "review_react.html",
        _template_context(
            lang=lang,
            page_label=page_label,
            copy=get_page_copy("product_attributes", lang),
            asset_version=_static_asset_version("static/js/review-react.js"),
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@site_router.get(
    "/review",
    include_in_schema=False,
    dependencies=[Depends(require_site_permission_for_request)],
)
def review_page_root(request: Request) -> Any:
    return _redirect_to_review_page(request)


@site_router.get(
    "/review/react",
    include_in_schema=False,
    dependencies=[Depends(require_site_permission_for_request)],
)
def review_page_react(request: Request) -> Any:
    return _redirect_to_review_page(request)


def _mark_interrupted_background_jobs() -> None:
    """Fail durable background jobs that were left active by an old process."""

    stores: list[tuple[str, object]] = []

    try:
        from modules.check_entries import api as check_entries_api

        stores.append(("check entries", check_entries_api._RUN_JOB_STORE))
    except Exception as exc:  # noqa: BLE001 - startup cleanup is best effort
        LOGGER.warning("Unable to load check entries job store: %s", exc)

    try:
        from modules.slides import pptx_jobs as slide_pptx_jobs
        from modules.slides import print_jobs as slide_print_jobs

        stores.append(("slide PDF export", slide_print_jobs))
        stores.append(("slide PPTX export", slide_pptx_jobs))
    except Exception as exc:  # noqa: BLE001 - startup cleanup is best effort
        LOGGER.warning("Unable to load slide export job trackers: %s", exc)

    for label, store_obj in stores:
        marker = getattr(store_obj, "mark_interrupted_jobs", None)
        if not callable(marker):
            continue
        try:
            interrupted = int(marker() or 0)
        except Exception as exc:  # noqa: BLE001 - do not block app startup
            LOGGER.warning("Unable to mark interrupted %s jobs: %s", label, exc)
            continue
        if interrupted:
            LOGGER.warning(
                "Marked %s interrupted %s job(s) after server restart.",
                interrupted,
                label,
            )


@site_router.get(
    "/review/coverage/page",
    include_in_schema=False,
    dependencies=[Depends(require_site_permission_for_request)],
)
def review_coverage_page(request: Request) -> Any:
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )
    lang = resolve_language(request)
    page_label = get_navigation_label(lang, "/review/coverage/page")
    response = templates.TemplateResponse(
        request,
        "review_coverage.html",
        _template_context(
            lang=lang,
            page_label=page_label,
            copy=get_page_copy("product_attributes", lang),
            asset_version=_static_asset_version("static/js/review-coverage-react.js"),
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def create_app() -> FastAPI:
    app = FastAPI(
        title="PDP Attribute Review API",
        openapi_tags=[
            {"name": "review", "description": "PDP attribute review endpoints"}
        ],
        swagger_ui_parameters={"persistAuthorization": True},
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(get_auth_config().trusted_hosts),
    )

    @app.middleware("http")
    async def _attach_session_context(request: Request, call_next):
        session_ctx = build_session_context(request)
        with use_session_context(session_ctx):
            response = await call_next(request)
        return response

    @app.middleware("http")
    async def _protect_static_site_pages(request: Request, call_next):
        permission_response = _static_site_permission_response(request)
        if permission_response is not None:
            return permission_response
        return await call_next(request)

    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.include_router(auth_router)
    app.include_router(auth_site_router)
    app.include_router(site_router)
    app.include_router(hosted_interviews_site_router)
    app.include_router(hosted_interviews_public_router)
    app.include_router(change_requests_router)
    protected_site_routers = [
        (check_site_router, AUDIT_SITE_DEPENDENCIES),
        (hierarchy_site_router, SITE_AUTH_DEPENDENCIES),
        (slides_site_router, [Depends(require_site_permission_for_request)]),
        (
            projects_site_router,
            [Depends(require_site_permission_for_request)],
        ),
        (
            explicit_rules_site_router,
            [Depends(require_site_permission_for_request)],
        ),
        (
            deterministic_policy_site_router,
            [Depends(require_site_permission_for_request)],
        ),
        (
            taxonomy_governance_site_router,
            [Depends(require_site_permission_for_request)],
        ),
        (
            taxonomy_issues_site_router,
            [Depends(require_site_permission_for_request)],
        ),
        (
            case_notes_voice_site_router,
            [Depends(require_site_permission_for_request)],
        ),
    ]
    for protected_router, dependencies in protected_site_routers:
        app.include_router(protected_router, dependencies=list(dependencies))
    app.include_router(_build_presentations_router(_presentations_root()))
    app.include_router(router, dependencies=AUTH_DEPENDENCIES)
    app.include_router(check_router, dependencies=AUDIT_API_DEPENDENCIES)
    app.include_router(identify_columns_router, dependencies=AUDIT_API_DEPENDENCIES)
    app.include_router(explicit_rules_router, dependencies=AUTH_DEPENDENCIES)
    app.include_router(deterministic_policy_router, dependencies=AUTH_DEPENDENCIES)
    app.include_router(taxonomy_governance_router, dependencies=AUTH_DEPENDENCIES)
    app.include_router(hierarchy_router, dependencies=AUTH_DEPENDENCIES)
    app.include_router(slides_router, dependencies=AUTH_DEPENDENCIES)
    app.include_router(projects_router, dependencies=AUTH_DEPENDENCIES)
    app.include_router(hosted_interviews_admin_router)
    app.include_router(attribute_reporting_router)
    app.include_router(
        case_notes_voice_router,
        dependencies=[Depends(require_site_permission_for_request)],
    )

    @app.on_event("startup")
    async def _startup_cleanup() -> None:
        _mark_interrupted_background_jobs()
        process_pending_notifications()
        _start_session_cleanup()
        start_voice_retention_cleanup()

    @app.on_event("shutdown")
    async def _shutdown_cleanup() -> None:
        stop_voice_retention_cleanup()
        _stop_session_cleanup()

    async def _render_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        if exc.status_code == status.HTTP_403_FORBIDDEN and templates is not None:
            lang = request.query_params.get("lang") or resolve_language(request)
            context = {
                "request": request,
                "lang": lang,
                "message": _forbidden_message(exc.detail),
            }
            return templates.TemplateResponse(
                "forbidden.html", context, status_code=exc.status_code
            )
        if (
            exc.status_code == status.HTTP_404_NOT_FOUND
            and templates is not None
            and _request_prefers_html(request)
        ):
            return templates.TemplateResponse(
                "not_found.html",
                _not_found_context(request, exc.detail),
                status_code=exc.status_code,
            )
        return await http_exception_handler(request, exc)

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> Response:
        return await _render_http_exception(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def _starlette_http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        return await _render_http_exception(request, exc)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        error_id = uuid.uuid4().hex[:12]
        LOGGER.exception(
            "Unhandled API exception error_id=%s method=%s path=%s has_query=%s",
            error_id,
            request.method,
            request.url.path,
            bool(request.url.query),
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": f"Internal server error (error_id={error_id})",
                "error_id": error_id,
            },
        )

    return app


app = create_app()


def _order_links_by_reference(
    links: Sequence[Dict[str, Any]],
    reference_links: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Order links to match the reference href sequence."""
    if not links:
        return []
    if not reference_links:
        return list(links)
    remaining = list(links)
    ordered: List[Dict[str, Any]] = []
    for ref in reference_links:
        if not isinstance(ref, dict):
            continue
        ref_href = ref.get("href")
        if not ref_href:
            continue
        for index, link in enumerate(remaining):
            if not isinstance(link, dict):
                continue
            if link.get("href") == ref_href:
                ordered.append(link)
                remaining.pop(index)
                break
    ordered.extend(remaining)
    return ordered


def _get_landing_page_content(lang: str) -> Dict[str, Any]:
    content = LANDING_CONTENT.get(lang) or LANDING_CONTENT["en"]
    sections = []
    for section in content.get("sections", []):
        copied_section = {**section, "links": list(section.get("links", []))}
        if section.get("groups"):
            copied_section["groups"] = [
                {**group, "links": list(group.get("links", []))}
                for group in section.get("groups", [])
            ]
        sections.append(copied_section)
    if lang != "en":
        reference_sections = LANDING_CONTENT["en"].get("sections", [])
        for section, reference in zip(sections, reference_sections):
            if section.get("preserve_order"):
                continue
            section["links"] = _order_links_by_reference(
                section.get("links", []),
                reference.get("links", []) if isinstance(reference, dict) else [],
            )
    return {
        "primary": content.get("primary"),
        "sections": sections,
        "menu_links": content.get("menu_links", []),
        "hero": content.get("hero"),
        "harness": content.get("harness", {}),
        "open_source": content.get("open_source", {}),
        "free": content.get("free", {}),
        "security": content.get("security", {}),
        "compliance": content.get("compliance", {}),
        "bridge": content.get("bridge", {}),
    }
