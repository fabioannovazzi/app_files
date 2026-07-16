import datetime as dt
import hashlib
import json
import logging
import io
import random
import time
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, NamedTuple

import polars as pl
from modules.utilities.ui_notifier import ui
from modules.utilities.session_context import session_state
from polars.exceptions import ColumnNotFoundError

from modules.add_attributes.attribute_activity import (
    get_attribute_activity_config,
    get_active_attribute_ids_for_category,
)
from modules.add_attributes.attribute_classification import (
    classify_attributes_for_products,
    discover_objective_attributes_for_category,
)
from modules.add_attributes.normalization import normalize_product_key
from modules.add_attributes.attribute_discovery import discover_attributes_for_category
from modules.add_attributes.attribute_product_insight import (
    group_stats_and_tests,
    train_decision_tree,
)
from modules.add_attributes.attribute_scoring import score_attributes_for_products
from modules.add_attributes.attribute_taxonomy import (
    aggregate_pending_values,
    get_attribute_activity,
    get_attribute_taxonomy,
    get_taxonomy_storage_mtime,
    load_taxonomy_review_queue,
    save_attribute_taxonomy,
    save_taxonomy_review_queue,
)
from modules.add_attributes.grouping import select_grouping_level
from modules.add_attributes.pareto import (
    compute_pareto_ranking,
    infer_amount_column,
)
from modules.add_attributes.validators import is_valid_product_name
from modules.charting import plot_horizontal_bar
from modules.layout.widgets import searchable_selectbox_with_state
from modules.llm import model_router
from modules.llm.llm_call_wrapper import init_llm_wrapper
from modules.utilities.session_context import SessionContext

SOURCE_DETERMINISTIC = "Product Text"
SOURCE_DETERMINISTIC_LLM = "Web Search"
SOURCE_EXCEL = "Excel"


def _normalize_attr_source(value: str | None) -> str | None:
    if value in {"LLM", "Deterministic + LLM"}:
        return SOURCE_DETERMINISTIC_LLM
    if value == "Deterministic":
        return SOURCE_DETERMINISTIC
    return value


def _llm_enabled(source: str | None) -> bool:
    return source == SOURCE_DETERMINISTIC_LLM


logger = logging.getLogger(__name__)
from modules.utilities.config import get_naming_params
from modules.utilities.helpers import drop_columns
from modules.utilities.utils import ensure_lazyframe, get_schema_and_column_names
from src.attribute_excel_logic import merge_attributes_from_excel, shared_columns
from src.attribute_merge_logic import merge_attribute_results
from src.category_lookup import lookup_category_websites
from src.io_utils import convert_df_excel, convert_df_parquet
from src.merchant_brand_lookup import lookup_websites


def process_taxonomy_review_queue(
    llm_wrapper,
    entries: List[Dict[str, Any]] | None = None,
) -> None:
    """Validate queued attribute values and update taxonomy."""

    queue = load_taxonomy_review_queue()
    if not queue:
        return
    to_process = entries or queue
    remaining = [e for e in queue if e not in to_process]
    taxonomy = get_attribute_taxonomy()
    naming = get_naming_params()
    query_step = naming["attributeClassificationQuery"]
    updated = False
    for entry in to_process:
        attribute = str(entry.get("attribute", "")).strip().lower()
        category = str(entry.get("category", "")).strip().lower()
        value = str(entry.get("value", "")).strip()
        if not (attribute and category and value):
            continue
        user_prompt = (
            f"Is '{value}' a valid value for attribute '{attribute}' within category '{category}'? "
            "Return JSON {'valid': true/false}"
        )
        resp = model_router.query_llm_return_json(
            llm_wrapper,
            query_step,
            "You verify product attribute taxonomy values. Return JSON only.",
            user_prompt,
            tools=[{"type": "web_search_preview"}],
            tool_choice="auto",
        )
        is_valid = False
        if isinstance(resp, dict):
            val = resp.get("valid")
            if isinstance(val, bool):
                is_valid = val
            elif isinstance(val, str):
                is_valid = val.lower() in {"yes", "true"}
        if not is_valid:
            continue
        cat_node = next(
            (
                c
                for c in taxonomy.get("categories", [])
                if str(c.get("id", "")).strip().lower() == category
            ),
            None,
        )
        if cat_node is None:
            continue
        attr_node = next(
            (
                a
                for a in cat_node.get("attributes", [])
                if str(a.get("id", "")).strip().lower() == attribute
            ),
            None,
        )
        if attr_node is None:
            continue
        nodes = attr_node.setdefault("nodes", [])
        if value.lower() not in {str(n.get("label", "")).lower() for n in nodes}:
            nodes.append({"label": value})
            updated = True
    if updated:
        save_attribute_taxonomy(taxonomy)
    save_taxonomy_review_queue(remaining)


def _discover_scoring_attributes(
    groups: list[str],
    existing_cols: list[str],
    llm_wrapper,
    *,
    use_batch: bool,
    throttle: float,
    service_tier: str,
) -> dict[str, list[str]]:
    """Discover subjective attributes for ``groups`` and store the result."""

    attr_map: dict[str, list[str]] = {}
    for grp in groups:
        attr_map[grp] = discover_attributes_for_category(
            llm_wrapper,
            grp,
            existing_cols,
            use_batch=use_batch,
            throttle=throttle,
            service_tier=service_tier,
        )
    session_state["attr_suggestions"] = attr_map
    session_state["attr_attrs_confirmed"] = True
    return attr_map


def _discover_objective_attributes(
    groups: list[str],
    existing_cols: list[str],
    llm_wrapper,
    *,
    use_batch: bool,
    throttle: float,
    service_tier: str,
) -> dict[str, list[str]]:
    """Discover objective attributes for ``groups`` and store the result."""
    naming = get_naming_params()
    industry_key = naming["industry"]
    company_key = naming["companyName"]
    industry_desc_key = naming["industryDescription"]
    # Prefer session state; fall back to paramDict persisted earlier in the app
    param_dict = session_state.get("attr_param_dict", {}) or {}
    industry = session_state.get(industry_key) or param_dict.get(industry_key)
    company = session_state.get(company_key) or param_dict.get(company_key)
    industry_desc = session_state.get(industry_desc_key) or param_dict.get(
        industry_desc_key
    )

    try:
        taxonomy = get_attribute_taxonomy()
    except (FileNotFoundError, ValueError):  # pragma: no cover - defensive
        taxonomy = {}
    known = {
        str(c.get("id", "")).strip().lower() for c in taxonomy.get("categories", [])
    }

    attr_map: dict[str, list[str]] = {}
    for grp in groups:
        normalized = grp.strip().lower()
        missing_from_taxonomy = normalized not in known
        if missing_from_taxonomy and not (industry or company or industry_desc):
            LOGGER.info(
                "Skipping attribute discovery for '%s' - missing industry/company",
                grp,
            )
            ui.info(
                "Industry or company context is required to generate attributes for new categories.",
            )
            attr_map[grp] = []
            continue

        attr_map[grp] = discover_objective_attributes_for_category(
            llm_wrapper,
            grp,
            existing_cols,
            use_batch=use_batch,
            throttle=throttle,
            service_tier=service_tier,
            context={
                "industry": industry,
                "company": company,
                "industry_description": industry_desc,
            },
        )
    session_state["attr_obj_suggestions"] = attr_map
    session_state["attr_obj_attrs_confirmed"] = True
    return attr_map


@dataclass
class EnrichAttributesResult:
    """Container for data enriched with attribute values and website info."""

    data: pl.DataFrame
    websites: pl.DataFrame


LOGGER = logging.getLogger(__name__)


def _record_excel_attribute_columns(
    df: pl.DataFrame | pl.LazyFrame, columns: list[str]
) -> None:
    """Persist attribute column metadata for downstream filter/dimension widgets."""

    df_cols, _ = get_schema_and_column_names(df)
    df_cols_lower = {c.lower(): c for c in df_cols}

    valid: list[str] = []
    resolved_map: dict[str, str] = {}
    for col in columns:
        actual = df_cols_lower.get(col.lower())
        if actual:
            valid.append(actual)
            resolved_map[actual] = actual

    lf = ensure_lazyframe(df)
    collected_values: dict[str, list[str]] = {}
    for column in valid:
        try:
            series = (
                lf.select(pl.col(column).drop_nulls().cast(pl.Utf8).unique())
                .collect()
                .get_column(column)
            )
            values = series.to_list() if series is not None else []
        except Exception:  # pragma: no cover - defensive
            values = []
        collected_values[column] = values[:100]

    stored_cols = set(session_state.get("attr_excel_columns", []))
    stored_cols.update(valid)
    session_state["attr_excel_columns"] = sorted(stored_cols)

    stored_values = dict(session_state.get("attr_excel_column_values", {}))
    stored_values.update(collected_values)
    session_state["attr_excel_column_values"] = stored_values

    dims = set(session_state.get("attr_dimension_columns") or [])
    dims.update(valid)
    session_state["attr_dimension_columns"] = sorted(dims)


def _load_brand_aliases(path: Path) -> dict[str, str]:
    """Load brand alias mappings from ``path``."""

    logger = logging.getLogger(__name__)
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        logger.warning("Brand alias file not found: %s", path)
        return {}
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in brand alias file: %s", path)
        return {}

    if not isinstance(raw, dict):
        logger.warning("Expected object in brand alias file %s; ignoring", path)
        return {}

    aliases: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, str):
            aliases[key.strip().lower()] = value.strip()
        else:
            logger.debug("Skipping non-string alias mapping for key %s", key)
    return aliases


BRAND_ALIASES_PATH = Path(__file__).resolve().parents[2] / "brand_aliases.json"
BRAND_ALIASES: dict[str, str] = _load_brand_aliases(BRAND_ALIASES_PATH)


def resolve_domains_for_dataset(
    df: pl.DataFrame,
    *,
    brand_col: str | None,
    merchant_col: str | None,
    category_col: str | None,
    default_category: str,
    llm_wrapper,
    service_tier: str | None = None,
) -> Dict[str, List[str]]:
    """Return website domains for each product in ``df``.

    Parameters
    ----------
    df:
        DataFrame containing at least a ``product_col`` column alongside the
        optional brand/merchant/category columns supplied via the keyword
        arguments.
    brand_col, merchant_col:
        Optional column names to resolve websites from. Columns that are
        absent in ``df`` are ignored.
    category_col, default_category:
        Deprecated for domain restriction. Category websites are no longer
        appended to the allowlist to avoid pulling in competitor brand sites.
    llm_wrapper:
        Wrapper object passed to the lookup utilities.
    service_tier:
        Optional service tier forwarded to ``lookup_websites``.

    Returns
    -------
    dict[str, list[str]]
        Mapping of lowercase product names to a list of deduplicated website
        domains. Entries are included even when no domains were resolved for a
        product to make downstream lookups predictable.
    """

    columns, _ = get_schema_and_column_names(df)
    if "product_col" not in columns:
        raise ValueError("resolve_domains_for_dataset expects a 'product_col' column")

    brand_available = bool(brand_col and brand_col in columns)
    merchant_available = bool(merchant_col and merchant_col in columns)
    category_available = bool(category_col and category_col in columns)

    # Collect unique brand/merchant names for batched lookup.
    names: set[str] = set()

    if brand_available:
        brand_series = df.get_column(brand_col).drop_nulls()
        brand_values = brand_series.to_list()
        if brand_series.dtype == pl.List:
            brand_values = [
                b
                for items in brand_series.to_list()
                for b in (items if isinstance(items, list) else [])
            ]
        for raw in brand_values:
            if raw is None:
                continue
            parts = (
                raw
                if isinstance(raw, list)
                else [p.strip() for p in str(raw).split(",")]
            )
            for part in parts:
                if not isinstance(part, str):
                    part = str(part)
                norm = part.strip().lower()
                if norm:
                    names.add(BRAND_ALIASES.get(norm, norm))

    if merchant_available:
        merchant_series = df.get_column(merchant_col).drop_nulls()
        merchant_values = merchant_series.to_list()
        if merchant_series.dtype == pl.List:
            merchant_values = [
                m
                for items in merchant_series.to_list()
                for m in (items if isinstance(items, list) else [])
            ]
        for raw in merchant_values:
            if raw is None:
                continue
            items = raw if isinstance(raw, list) else [raw]
            for item in items:
                if not isinstance(item, str):
                    item = str(item)
                norm = item.strip().lower()
                if norm:
                    names.add(BRAND_ALIASES.get(norm, norm))

    brand_merch_map: Dict[str, str | None]
    if names:
        brand_merch_map = lookup_websites(
            llm_wrapper,
            names,
            aliases=BRAND_ALIASES,
            service_tier=service_tier,
        )
    else:
        brand_merch_map = {}

    # Category websites are intentionally not looked up nor appended to the
    # domain list for product attribute classification/queries. This avoids
    # mixing competitor brand domains into the search scope.

    domains_map: Dict[str, List[str]] = {}
    for row in df.to_dicts():
        product_raw = row.get("product_col")
        product_key = normalize_product_key(product_raw)
        if not product_key:
            continue

        # Ensure an entry exists even if no domains are found for this row
        domains_map.setdefault(product_key, [])

        domains: list[str] = []

        if brand_available:
            raw = row.get(brand_col)
            values = (
                (
                    raw
                    if isinstance(raw, list)
                    else [part.strip() for part in str(raw).split(",")]
                )
                if raw is not None
                else []
            )
            for val in values:
                if not isinstance(val, str):
                    val = str(val)
                norm = val.strip().lower()
                if not norm:
                    continue
                canon = BRAND_ALIASES.get(norm, norm)
                site = brand_merch_map.get(canon)
                if site:
                    domains.append(site)

        if merchant_available:
            raw = row.get(merchant_col)
            items = raw if isinstance(raw, list) else [raw] if raw is not None else []
            for item in items:
                if not isinstance(item, str):
                    item = str(item)
                norm = item.strip().lower()
                if not norm:
                    continue
                canon = BRAND_ALIASES.get(norm, norm)
                site = brand_merch_map.get(canon)
                if site:
                    domains.append(site)

        # Note: we no longer add category-level websites to domains.

        # Union domains across all rows for the same product key
        if domains:
            prev = domains_map.get(product_key) or []
            domains_map[product_key] = list(dict.fromkeys(prev + domains))

    return domains_map


def _save_category_branch(category: str, attributes: list[str]) -> bool:
    """Append a new category with ``attributes`` to the taxonomy file.

    Parameters
    ----------
    category:
        Category identifier to add.
    attributes:
        Attribute identifiers belonging to the category.

    Returns
    -------
    bool
        ``True`` if the category was appended, ``False`` otherwise.
    """

    try:
        taxonomy = get_attribute_taxonomy()
    except (FileNotFoundError, ValueError) as exc:  # pragma: no cover - defensive
        LOGGER.error("Unable to load taxonomy: %s", exc)
        return False

    cat_id = category.strip().lower()
    existing = {
        str(c.get("id", "")).strip().lower() for c in taxonomy.get("categories", [])
    }
    existing.update(
        str(c.get("label", "")).strip().lower() for c in taxonomy.get("categories", [])
    )
    if cat_id in existing:
        return False
    # Additional guard: avoid duplicates when an existing category matches by label
    by_label = {
        str(c.get("label", "")).strip().lower() for c in taxonomy.get("categories", [])
    }
    if cat_id in by_label:
        return False

    branch = {
        "id": category,
        "label": category,
        "attributes": [{"id": a, "label": a} for a in attributes],
    }
    taxonomy.setdefault("categories", []).append(branch)
    try:
        # Use centralized atomic writer for consistency and crash safety
        save_attribute_taxonomy(taxonomy)
        # Normalize the new branch so required leaves/synonyms are canonical
        try:
            from modules.add_attributes.taxonomy_patch import normalize_category
            from modules.add_attributes.synonym_enrichment import (
                enrich_category_if_stale,
            )

            cid = str(category).strip().lower()
            normalize_category(cid)
            # Use session's llm_wrapper if present to run enrichment best-effort
            llm_wrapper = None
            try:
                from modules.utilities.ui_notifier import ui
                from modules.utilities.session_context import session_state

                llm_wrapper = session_state.get("llm_wrapper")
            except Exception:
                llm_wrapper = None
            if llm_wrapper is not None:
                enrich_category_if_stale(llm_wrapper, cid, service_tier="high")
        except Exception:
            LOGGER.exception(
                "Normalization/enrichment failed for category '%s'", category
            )
    except OSError as exc:  # pragma: no cover - defensive
        LOGGER.error("Failed to update taxonomy: %s", exc)
        return False
    return True


def _ensure_taxonomy_categories(
    categories: list[str], attr_map: dict[str, list[str]]
) -> list[str]:
    """Ensure the taxonomy JSON has branches for all ``categories``.

    Attempts to persist missing categories using any discovered attributes in
    ``attr_map``. Returns the list of categories still missing after the
    operation. This allows the UI to halt follow-up steps (classification)
    when the taxonomy update could not be written or yielded empty branches.
    """
    if not categories:
        return []

    try:
        taxonomy = get_attribute_taxonomy()
    except (FileNotFoundError, ValueError):  # pragma: no cover - defensive
        taxonomy = {"categories": []}

    existing = {
        str(c.get("id", "")).strip().lower() for c in taxonomy.get("categories", [])
    }
    existing.update(
        str(c.get("label", "")).strip().lower() for c in taxonomy.get("categories", [])
    )

    # Persist missing categories using any discovered attributes if present
    for cat in categories:
        norm = str(cat).strip().lower()
        if norm in existing:
            continue
        attrs = attr_map.get(cat) or attr_map.get(norm) or []
        if attrs:
            _save_category_branch(cat, attrs)

    # Reload and compute which are still missing
    try:
        taxonomy = get_attribute_taxonomy()
    except (FileNotFoundError, ValueError):  # pragma: no cover - defensive
        taxonomy = {"categories": []}
    existing = {
        str(c.get("id", "")).strip().lower() for c in taxonomy.get("categories", [])
    }
    remaining = [cat for cat in categories if str(cat).strip().lower() not in existing]
    return remaining


def _list_non_numeric_columns(df: pl.LazyFrame | pl.DataFrame) -> list[str]:
    """Return column names from ``df`` that are **not** numeric."""
    _, schema = get_schema_and_column_names(df)
    cols: list[str] = []
    for name, dtype in schema.items():
        try:
            if not dtype.is_numeric():
                cols.append(name)
        except Exception as e:
            logging.exception(e)
            ui.error("Something went wrong while inferring column types.")
            # Defensive: if dtype has no ``is_numeric`` method just keep the name
            cols.append(name)
    return cols


def _list_date_columns(df: pl.LazyFrame | pl.DataFrame) -> list[str]:
    """Return columns with date or datetime type."""
    _, schema = get_schema_and_column_names(df)
    return [name for name, dtype in schema.items() if dtype in (pl.Date, pl.Datetime)]


def _pick_column(
    label: str,
    *,
    all_cols: list[str],
    chosen: set[str],
    key: str,
    default: str | None = None,
    allow_none: bool = False,
    help_text: str | None = None,
) -> str | None:
    """Select box that hides columns already in ``chosen``."""
    base = sorted([c for c in all_cols if c not in chosen])
    options: list[str | None]
    if allow_none:
        options = [None, *base]
    else:
        options = base.copy()

    if not options:
        # Guard against empty option list when columns are exhausted.
        options = [None] if allow_none else [""]

    prev = session_state.get(key, default)
    if prev not in options:
        prev = None if allow_none else options[0]
    index = options.index(prev) if prev in options else 0
    choice = searchable_selectbox_with_state(
        label,
        options,
        key=key,
        index=index,
        help=help_text,
        format_func=lambda value: "None" if value is None else value,
    )
    if isinstance(choice, str):
        chosen.add(choice)
    return choice


def _available_groups(lf: pl.LazyFrame, group_col: str) -> list[str]:
    """Return a list of unique group values for ``group_col``."""
    return (
        lf.select(pl.col(group_col).unique()).collect().get_column(group_col).to_list()
    )


def _available_periods(lf: pl.LazyFrame, period_col: str) -> list[str]:
    """Return a list of unique period labels for ``period_col``."""
    return (
        lf.select(pl.col(period_col).unique())
        .collect()
        .get_column(period_col)
        .to_list()
    )


def _sanitize_selection(defaults: list[str] | None, options: list[str]) -> list[str]:
    """Ensure all default selections exist in ``options``."""
    if not defaults:
        return []
    return [d for d in defaults if d in options]


def _extend_with_extra_columns(
    result_df: pl.DataFrame,
    source_df: pl.DataFrame,
    product_col: str,
    *,
    key_prefix: str,
) -> pl.DataFrame:
    """Join user-selected text columns from ``source_df`` onto ``result_df``."""

    result_cols, _ = get_schema_and_column_names(result_df)
    existing = {c.lower() for c in result_cols}
    candidates: list[str] = []
    _, schema = get_schema_and_column_names(source_df)
    for name, dtype in schema.items():
        if dtype == pl.Utf8 and name.lower() not in existing and name != product_col:
            max_n = (
                source_df.group_by(product_col)
                .agg(pl.col(name).n_unique().alias("n"))
                .get_column("n")
                .max()
            )
            if max_n == 1:
                candidates.append(name)

    if not candidates:
        # No text fields uniquely identify each product. Skip extending.
        return result_df

    selected = ui.multiselect(
        "Additional columns", candidates, key=f"{key_prefix}_extra_cols"
    )

    if not selected:
        return result_df

    extras = (
        source_df.select([product_col] + selected)
        .group_by(product_col)
        .agg([pl.first(c).alias(c.lower()) for c in selected])
    )
    return result_df.join(extras, on=product_col, how="left")


def _merge_attribute_results(
    df: pl.DataFrame, mapping: dict[str, str | None]
) -> pl.DataFrame:
    """Merge scored or classified attributes stored in ``session_state``."""
    scores = session_state.get("attr_scores")
    classification = session_state.get("attr_classification")
    _, group_col = session_state.get("attr_group_choice", ("none", None))
    include_scores = False
    try:
        return merge_attribute_results(
            df,
            mapping,
            scores,
            classification,
            group_col=group_col,
            include_scores=include_scores,
        )
    except (ValueError, ColumnNotFoundError) as exc:
        ui.warning(str(exc))
        return df


class _ColumnField(NamedTuple):
    label: str
    ui_key: str
    state_key: str
    result_key: str
    allow_none: bool
    help_text: str


@dataclass
class _LineSelectorConfig:
    show: bool
    allow_none: bool
    required: bool


@dataclass
class _FieldConfig:
    fields: list[_ColumnField]
    required: set[str]
    line: _LineSelectorConfig

    def __iter__(self):
        yield self.fields
        yield self.line


_COLUMN_STATE_MAP: dict[str, str] = {
    "product_column": "attr_product_col",
    "category_column": "attr_category_col",
    "subcategory_column": "attr_subcategory_col",
    "merchant_column": "attr_merchant_col",
    "brand_column": "attr_brand_col",
    "description_column": "attr_description_col",
}


def _field_configuration_for_source(source_mode: str) -> _FieldConfig:
    base_fields: list[_ColumnField] = [
        _ColumnField(
            "Attribute mapping column",
            "attr_product_select",
            "attr_product_col",
            "product_column",
            False,
            "Key column to attach attributes (product parent/product/SKU).",
        ),
        _ColumnField(
            "Category column",
            "attr_category_select",
            "attr_category_col",
            "category_column",
            True,
            "Broad product grouping; improves attribute suggestions.",
        ),
        _ColumnField(
            "Subcategory column",
            "attr_subcategory_select",
            "attr_subcategory_col",
            "subcategory_column",
            True,
            "More specific grouping under category.",
        ),
        _ColumnField(
            "Merchant column",
            "attr_merchant_select",
            "attr_merchant_col",
            "merchant_column",
            True,
            "Seller/retailer name; helps website lookup.",
        ),
        _ColumnField(
            "Brand column",
            "attr_brand_select",
            "attr_brand_col",
            "brand_column",
            True,
            "Brand name; scopes web search and appears in export.",
        ),
        _ColumnField(
            "Description column",
            "attr_description_select",
            "attr_description_col",
            "description_column",
            True,
            "Short product description to provide extra context.",
        ),
    ]
    if source_mode == SOURCE_EXCEL:
        fields = base_fields[:2]
        required = {"product_column", "category_column"}
        line_cfg = _LineSelectorConfig(show=False, allow_none=True, required=False)
    elif source_mode == SOURCE_DETERMINISTIC:
        allowed_keys = {
            "product_column",
            "category_column",
            "subcategory_column",
            "description_column",
            "brand_column",
        }
        fields = [f for f in base_fields if f.result_key in allowed_keys]
        required = {"product_column", "category_column", "subcategory_column"}
        line_cfg = _LineSelectorConfig(show=True, allow_none=True, required=False)
    else:
        # Default: Web Search mode keeps richer context but hides description
        fields = [f for f in base_fields if f.result_key != "description_column"]
        required = {"product_column", "category_column", "subcategory_column"}
        line_cfg = _LineSelectorConfig(show=True, allow_none=True, required=False)
    return _FieldConfig(fields=fields, required=required, line=line_cfg)


def _render_inference_form(
    result: dict[str, str | None], columns: list[str], *, source_mode: str
) -> None:
    """UI layer: display inference results and allow user corrections."""
    blocked = {"date", "time"}
    filtered = [c for c in columns if not any(b in c.lower() for b in blocked)]
    chosen: set[str] = set()

    if "attr_cols_saved" not in session_state:
        session_state["attr_cols_saved"] = False

    config = _field_configuration_for_source(source_mode)
    fields = config.fields
    required_keys: set[str] = set(config.required)
    line_cfg = config.line
    selections: dict[str, str | None] = {}

    with ui.form("attr_form"):
        for field in fields:
            filled = {
                key
                for key in required_keys
                if key in selections or result.get(key) is not None
            }
            if field.result_key not in required_keys and filled != required_keys:
                break
            default_val = session_state.get(
                field.state_key, result.get(field.result_key)
            )
            choice = _pick_column(
                field.label,
                all_cols=filtered,
                chosen=chosen,
                key=field.ui_key,
                default=default_val,
                allow_none=field.allow_none,
                help_text=field.help_text,
            )
            selections[field.result_key] = (
                None if (field.allow_none and choice == "None") else choice
            )
        # Optional Product Parent column (LLM source only; excluded from mapping; export-only)
        if line_cfg.show:
            line_default = session_state.get("attr_line_col")
            line_choice = _pick_column(
                "Product Parent column",
                all_cols=filtered,
                chosen=chosen,
                key="attr_line_select",
                default=line_default,
                allow_none=line_cfg.allow_none,
                help_text=(
                    "Product parent grouping; optional. Included in Excel export only."
                ),
            )
            line_value = (
                None
                if (line_cfg.allow_none and line_choice in {None, "None"})
                else line_choice
            )
        else:
            line_value = None
        submitted = ui.form_submit_button("Save selections")

    if submitted:
        for field in fields:
            session_state[field.state_key] = selections.get(field.result_key)
        mapping = {}
        for field in fields:
            mapping[field.result_key] = session_state.get(
                field.state_key, result.get(field.result_key)
            )
        hidden_keys = set(_COLUMN_STATE_MAP) - {f.result_key for f in fields}
        for hidden_key in hidden_keys:
            state_key = _COLUMN_STATE_MAP.get(hidden_key)
            if state_key:
                session_state.pop(state_key, None)
            mapping[hidden_key] = None
        session_state["attr_inference_result"] = mapping
        if source_mode == SOURCE_EXCEL:
            session_state.pop("attr_excel_merge_signature", None)
        session_state["attr_cols_saved"] = True
        session_state.pop("attr_save_prompt_shown", None)
        session_state["attr_line_col"] = line_value


def column_inference(
    df: pl.DataFrame | pl.LazyFrame | None,
) -> dict[str, str | None] | None:
    """Let the user choose the relevant columns manually."""

    result = session_state.get("attr_inference_result")

    if df is not None:
        if result is None:
            result = {
                "product_column": None,
                "category_column": None,
                "subcategory_column": None,
                "merchant_column": None,
                "brand_column": None,
                "description_column": None,
            }
        lf = df.lazy() if isinstance(df, pl.DataFrame) else df
        columns = _list_non_numeric_columns(lf)
        excel_bytes = session_state.get("attr_excel_bytes")
        if excel_bytes:
            try:
                shared = shared_columns(df, excel_bytes)
            except Exception as e:  # pragma: no cover - defensive
                logging.exception(e)
                ui.warning("Failed to read uploaded Excel file; showing all columns")
                LOGGER.exception("shared_columns failed", exc_info=e)
            else:
                columns = [c for c in columns if c in shared]
        if columns:
            stored_source = session_state.get("attr_source", SOURCE_DETERMINISTIC_LLM)
            source_mode = _normalize_attr_source(stored_source)
            _render_inference_form(result, columns, source_mode=source_mode)
            result = session_state.get("attr_inference_result", result)
        else:
            ui.warning("No common columns with uploaded Excel file")

    return result


def _render_pareto_step(
    mapping: dict, df: pl.DataFrame | pl.LazyFrame, param_dict: dict, llm_wrapper
) -> pl.DataFrame | pl.LazyFrame:
    """UI layer for Pareto ranking and product selection.

    Returns the dataset with a ``TopProduct`` column after confirmation.
    """
    product_col = mapping.get("product_column")
    if not product_col:
        ui.warning("Attribute mapping column not defined.")
        return df

    grouping_choice = session_state.get("attr_group_choice", ("none", None))
    group_col = grouping_choice[1]

    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    amount_col = session_state.get("attr_amount_col")
    if amount_col is None:
        amount_col = infer_amount_column(llm_wrapper, lf)
        if amount_col:
            session_state["attr_amount_col"] = amount_col

    if amount_col is None:
        ui.warning("Unable to detect amount column for Pareto ranking.")
        return df

    groups: list[str] | None = None
    pct_options = [0.1, 1, 3, 5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]
    pct_default = session_state.get("attr_pct", 3.0)
    pct_index = pct_options.index(pct_default) if pct_default in pct_options else 2

    if group_col:
        group_choices = _available_groups(lf, group_col)
        prev = session_state.get("attr_groups")
        group_defaults = _sanitize_selection(prev, group_choices) or group_choices[:1]
        groups = session_state.get("attr_groups", group_defaults)
    else:
        group_choices = []
        group_defaults = []

    naming = get_naming_params()
    date_found_key = naming["dateColFound"]
    likely_dates_key = naming["likelyDateCols"]
    date_name = naming["dateName"]

    date_col: str | None = None
    include_launches_default = session_state.get("attr_include_launches", True)

    if param_dict.get(date_found_key) and param_dict.get(likely_dates_key):
        candidates: list[str] = param_dict[likely_dates_key]
        columns, _ = get_schema_and_column_names(lf)
        candidate = date_name if date_name in columns else candidates[0]
        if candidate in columns:
            date_col = candidate

    period_col: str | None = None
    period_choices: list[str] = []
    period_defaults: list[str] | None = None
    period_found_key = naming["periodColFound"]
    likely_period_key = naming["likelyPeriodCols"]
    period_name = naming["periodName"]

    if param_dict.get(period_found_key) and param_dict.get(likely_period_key):
        candidates = param_dict[likely_period_key]
        columns, _ = get_schema_and_column_names(lf)
        candidate = period_name if period_name in columns else candidates[0]
        if candidate in columns:
            period_col = candidate
            period_choices = _available_periods(lf, period_col)
            prev = session_state.get("attr_periods", period_choices)
            period_defaults = (
                _sanitize_selection(prev, period_choices) or period_choices
            )

    periods_state = (
        session_state.get("attr_periods", period_defaults)
        if period_defaults is not None
        else None
    )

    include_launches_input = include_launches_default if date_col else False

    with ui.form("attr_top_form"):
        if group_col:
            selected_groups = ui.multiselect(
                "Choose group to analyse",
                group_choices,
                default=groups,
                key="attr_group_select",
            )
        else:
            selected_groups = None
        pct_input = searchable_selectbox_with_state(
            "% of products", pct_options, key="pct_of_products", index=pct_index
        )
        if date_col:
            include_launches_input = ui.checkbox(
                "Include launches",
                value=include_launches_default,
                help=(
                    "Adds products that sold in the current window but had no sales "
                    "in the immediately previous window."
                ),
            )
        else:
            include_launches_input = False
        if period_col:
            periods_input = ui.multiselect(
                "Choose periods to analyse",
                period_choices,
                default=periods_state,
                key="attr_period_select",
            )
        else:
            periods_input = None
        form_submitted = ui.form_submit_button(
            "Confirm top products",
            help="Save the selected products for use in the next steps.",
        )

    if form_submitted:
        if group_col:
            session_state["attr_groups"] = selected_groups
            groups = selected_groups
        session_state["attr_pct"] = pct_input
        pct_default = pct_input
        if date_col:
            session_state["attr_include_launches"] = include_launches_input
        if period_col:
            session_state["attr_periods"] = periods_input
            periods_state = periods_input

    pct = pct_default
    include_launches = include_launches_input if date_col else False
    periods = periods_state

    ranking = compute_pareto_ranking(
        lf,
        product_col,
        amount_col,
        group_col=group_col,
        groups=groups,
        period_col=period_col,
        periods=periods,
    )
    ranking = (
        drop_columns(ranking, ["rank"])
        .sort("total_amount", descending=True)
        .with_row_index("rank", offset=1)
    )
    session_state["attr_ranking"] = ranking
    total_products = ranking.height
    n_select = max(1, int(total_products * pct / 100))
    selected = ranking.head(n_select)

    baseline_count = selected.height
    launch_summary: tuple[int, float] | None = None

    if date_col and include_launches:
        launches = _find_recent_launch_products(
            lf,
            product_col,
            amount_col,
            date_col,
            group_col=group_col,
            groups=groups,
            period_col=period_col,
            periods=periods,
            exclude_products=set(selected[product_col].to_list()),
        )
        if launches.height > 0:
            launch_products = launches[product_col].to_list()
            launch_rows = ranking.filter(pl.col(product_col).is_in(launch_products))
            selected = (
                pl.concat([selected, launch_rows])
                .unique(subset=[product_col])
                .sort("rank")
            )
            added_count = selected.height - baseline_count
            if added_count > 0:
                launch_summary = (added_count, float(launches["total_amount"].sum()))
    total_rev = ranking["total_amount"].sum()
    share = (selected["total_amount"].sum() / total_rev * 100) if total_rev else 0.0
    message = (
        f"{n_select} top sellers selected out of {total_products} products, "
        f"representing {share:.1f}% of revenues."
    )
    if date_col and include_launches:
        if launch_summary:
            added_count, added_revenue = launch_summary
            launch_label = "launch" if added_count == 1 else "launches"
            message += f" Added {added_count} {launch_label}"
            if added_revenue:
                message += f" (~{added_revenue:,.0f} in sales)."
            else:
                message += "."
        else:
            message += " No additional launches were identified."
    message += f" {selected.height} products will be classified."
    ui.write(message)
    if form_submitted:
        # Ensure unique product list to avoid accidental duplicates downstream
        top_products = list(dict.fromkeys(selected[product_col].to_list()))
        session_state["attr_top_products"] = top_products
        full_df = lf.collect() if isinstance(lf, pl.LazyFrame) else df
        full_df = full_df.with_columns(
            pl.col(product_col).is_in(top_products).alias("TopProduct")
        )
        session_state["attr_marked_df"] = full_df
        session_state["attr_top_data"] = full_df.filter(pl.col("TopProduct"))

        # Clear website information; enrichment occurs after classification.
        session_state.pop("attr_websites", None)

        session_state["attr_top_confirmed"] = True
        df = full_df
    return df


def _find_recent_launch_products(
    data: pl.DataFrame | pl.LazyFrame,
    product_col: str,
    amount_col: str,
    date_col: str,
    *,
    group_col: str | None,
    groups: list[str] | None,
    period_col: str | None,
    periods: list[str] | None,
    exclude_products: set[str],
) -> pl.DataFrame:
    """Return recent launch products absent in the previous window."""

    def _empty() -> pl.DataFrame:
        return pl.DataFrame(
            schema=[(product_col, pl.Utf8), ("total_amount", pl.Float64)]
        )

    lf = ensure_lazyframe(data)
    base = lf
    if group_col and groups:
        base = base.filter(pl.col(group_col).is_in(groups))

    base = base.with_columns(
        pl.col(date_col).cast(pl.Date, strict=False).alias("_launch_date")
    )
    current = base
    if period_col and periods:
        current = current.filter(pl.col(period_col).is_in(periods))

    stats = current.select(
        pl.col("_launch_date").drop_nulls().min().alias("start"),
        pl.col("_launch_date").drop_nulls().max().alias("end"),
    ).collect()
    if stats.height == 0:
        return _empty()

    start = _as_date(stats[0, "start"])
    end = _as_date(stats[0, "end"])
    if start is None or end is None:
        return _empty()

    window_days = max(1, (end - start).days + 1)
    prev_end = start - dt.timedelta(days=1)
    prev_start = prev_end - dt.timedelta(days=window_days - 1)
    if prev_start > prev_end:
        return _empty()

    current_sales = (
        current.filter(pl.col("_launch_date").is_between(start, end, closed="both"))
        .group_by(product_col)
        .agg(pl.col(amount_col).sum().alias("total_amount"))
    )
    if current_sales.limit(1).collect().height == 0:
        return _empty()

    previous_products = (
        base.filter(
            pl.col("_launch_date").is_between(prev_start, prev_end, closed="both")
        )
        .group_by(product_col)
        .agg(pl.count().alias("_count"))
        .select(product_col)
    )

    launches = current_sales.join(previous_products, on=product_col, how="anti")
    if exclude_products:
        launches = launches.filter(~pl.col(product_col).is_in(list(exclude_products)))

    return launches.collect()


def _as_date(value: object) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


def _render_attribute_discovery(
    mapping: dict,
    lf: pl.LazyFrame,
    llm_wrapper,
    *,
    use_batch: bool = False,
    throttle: float = 1.0,
    service_tier: str | None = None,
) -> None:
    """UI for attribute discovery using an LLM.

    Parameters
    ----------
    mapping:
        Column mapping information.
    lf:
        Source data as a lazy frame.
    llm_wrapper:
        LLM wrapper used for queries.
    use_batch:
        Whether to call the batch endpoint.
    throttle:
        Delay between non-batch requests.
    """
    source_mode = _normalize_attr_source(session_state.get("attr_source"))
    if source_mode != SOURCE_DETERMINISTIC_LLM:
        return
    if not session_state.get("attr_top_confirmed"):
        ui.info("Confirm top products firui.")
        return

    level, group_col = session_state.get("attr_group_choice", ("none", None))
    if group_col:
        groups = session_state.get("attr_groups")
        if not groups:
            groups = (
                lf.select(pl.col(group_col).unique())
                .collect()
                .get_column(group_col)
                .to_list()
            )
    else:
        groups = ["All products"]

    df = lf.collect()
    existing_cols, _ = get_schema_and_column_names(df)

    groups_key = tuple(groups)
    stored_key = session_state.get("attr_last_groups")
    attr_map = session_state.get("attr_suggestions")
    if attr_map is None or stored_key != groups_key:
        if llm_wrapper:
            attr_map = _discover_scoring_attributes(
                groups,
                existing_cols,
                llm_wrapper,
                use_batch=use_batch,
                throttle=throttle,
                service_tier=service_tier,
            )
            session_state["attr_last_groups"] = groups_key

    if (
        ui.button("Get scoring attribute suggestions", key="attr_gen_attrs")
        and llm_wrapper
    ):
        attr_map = _discover_scoring_attributes(
            groups,
            existing_cols,
            llm_wrapper,
            use_batch=use_batch,
            throttle=throttle,
            service_tier=service_tier,
        )
        session_state["attr_last_groups"] = groups_key

    if not attr_map:
        return

    for g in groups:
        attrs = attr_map.get(g, [])
        txt = ", ".join(attrs)
        edited = ui.text_input(f"Attributes for {g}", txt, key=f"attr_edit_{g}")
        attr_map[g] = [a.strip() for a in edited.split(",") if a.strip()]
    session_state["attr_suggestions"] = attr_map
    session_state["attr_attrs_confirmed"] = True


def _score_attributes_batch(
    llm_wrapper,
    data: pl.DataFrame,
    product_col: str,
    products: list[str],
    attr_map: Dict[str, List[str]],
    *,
    group_col: str | None,
    groups: list[str] | None,
    output_mode: str,
    use_batch: bool,
    service_tier: str,
    progress_cb: Callable[[int, int], None] | None = None,
) -> pl.DataFrame:
    """Return attribute scores using the selected LLM mode."""

    return score_attributes_for_products(
        llm_wrapper,
        data,
        product_col,
        products,
        attr_map,
        group_col=group_col,
        groups=groups,
        output_mode=output_mode,
        use_batch=use_batch,
        service_tier=service_tier,
        progress_cb=progress_cb,
    )


def _classify_attributes_batch(
    llm_wrapper,
    data: pl.DataFrame,
    product_col: str,
    products: list[str],
    attr_map: Dict[str, List[str]],
    *,
    group_col: str | None,
    groups: list[str] | None,
    use_batch: bool,
    service_tier: str,
    merchant_col: str | None = None,
    brand_col: str | None = None,
    category_col: str | None = None,
    desc_col: str | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
    deterministic_only: bool = False,
) -> pl.DataFrame:
    """Return objective attribute classifications via the selected LLM mode."""

    # Track taxonomy mtime (without triggering any reclassification behavior)
    try:
        mtime = get_taxonomy_storage_mtime()
        if mtime is not None:
            session_state["attr_taxonomy_mtime"] = float(mtime)
    except Exception:
        pass

    domains_map: Dict[str, List[str]] | None = None
    default_category = "All products"
    if groups:
        first_group = next((g for g in groups if g is not None), None)
        if first_group is not None:
            default_category = str(first_group)
    elif attr_map:
        default_category = str(next(iter(attr_map.keys())))

    if deterministic_only:
        use_batch = False

    aggregated_pending: list[dict[str, Any]] = []
    try:
        aggregated_pending = aggregate_pending_values(top_k=20)
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("Failed to aggregate taxonomy review queue: %s", exc)
    if aggregated_pending:
        try:
            save_taxonomy_review_queue(aggregated_pending)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Failed to persist aggregated taxonomy queue: %s", exc)

    if llm_wrapper and products:
        # Require market context before attempting website resolution
        try:
            naming_ctx = get_naming_params()
            industry_key = naming_ctx["industry"]
            industry_desc_key = naming_ctx["industryDescription"]
            industry_val = session_state.get(industry_key) or (
                session_state.get("attr_param_dict", {}).get(industry_key)
                if isinstance(session_state.get("attr_param_dict"), dict)
                else None
            )
            industry_desc_val = session_state.get(industry_desc_key) or (
                session_state.get("attr_param_dict", {}).get(industry_desc_key)
                if isinstance(session_state.get("attr_param_dict"), dict)
                else None
            )
        except Exception:
            industry_val = None
            industry_desc_val = None

        if not (industry_val or industry_desc_val):
            ui.warning(
                "Provide the market Industry (or an Industry description) before website lookups."
            )
            domains_map = {}
        else:
            normalized_products = tuple(
                sorted({normalize_product_key(p) for p in products if p})
            )
            cache_state = session_state.get("attr_domains_state")
            cache_key = (
                normalized_products,
                product_col,
                brand_col,
                merchant_col,
                category_col,
                default_category,
            )
            if isinstance(cache_state, dict) and cache_state.get("key") == cache_key:
                cached_map = cache_state.get("map")
                if isinstance(cached_map, dict):
                    domains_map = cached_map
            if domains_map is None:
                cols_needed = {product_col}
                for optional in (brand_col, merchant_col, category_col):
                    if optional:
                        cols_needed.add(optional)
                data_cols, _ = get_schema_and_column_names(data)
                present_cols = [c for c in cols_needed if c in data_cols]
                if not present_cols:
                    present_cols = [product_col]
                domain_df = data.select(
                    [pl.col(c) for c in dict.fromkeys(present_cols)]
                )
                rename_map = (
                    {product_col: "product_col"} if product_col != "product_col" else {}
                )
                if rename_map:
                    domain_df = domain_df.rename(rename_map)
                # Restrict website resolution to the selected products only to avoid
                # unnecessary lookups across the entire dataset.
                if products:
                    prod_keys = [normalize_product_key(p) for p in products if p]
                    domain_df = domain_df.filter(
                        pl.col("product_col")
                        .cast(pl.Utf8)
                        .map_elements(normalize_product_key, return_dtype=pl.Utf8)
                        .is_in(prod_keys)
                    )
                try:
                    domains_map = resolve_domains_for_dataset(
                        domain_df,
                        brand_col=brand_col,
                        merchant_col=merchant_col,
                        category_col=category_col,
                        default_category=default_category,
                        llm_wrapper=llm_wrapper,
                        service_tier=service_tier,
                    )
                except Exception as exc:  # pragma: no cover - defensive logging
                    LOGGER.warning("Domain resolution failed: %s", exc)
                    domains_map = {}
                session_state["attr_domains_state"] = {
                    "key": cache_key,
                    "map": domains_map,
                }

    try:
        session_state.pop("_attr_raw_rows", None)
        session_state.pop("_attr_sources_rows", None)
    except Exception:
        pass
    result = classify_attributes_for_products(
        llm_wrapper,
        data,
        product_col,
        products,
        attr_map,
        group_col=group_col,
        groups=groups,
        use_batch=use_batch,
        service_tier=service_tier,
        domains_map=domains_map,
        brand_col=brand_col,
        desc_col=desc_col,
        progress_cb=progress_cb,
        deterministic_only=deterministic_only,
    )
    # Deterministic remap: update current result rows where value is 'not in taxonomy'
    try:

        def _build_leaf_label_map(
            tax: Dict[str, Any],
        ) -> Dict[tuple[str, str], Dict[str, str]]:
            def _norm(s: str) -> str:
                t = str(s).lower()
                return " ".join(re.sub(r"[-_\u2010-\u2015]+", " ", t).split())

            mp: Dict[tuple[str, str], Dict[str, str]] = {}
            for c in tax.get("categories", []) or []:
                cid = str(c.get("id", "")).strip().lower()
                for a in c.get("attributes", []) or []:
                    alab = str(a.get("label", a.get("id", ""))).strip().lower()
                    d: Dict[str, str] = {}
                    for n in a.get("nodes", []) or []:
                        if n.get("children"):
                            for ch in n.get("children") or []:
                                lid = str(ch.get("label", ""))
                                d.setdefault(_norm(lid), lid)
                                for s in ch.get("synonyms") or []:
                                    d.setdefault(_norm(s), lid)
                        else:
                            lid = str(n.get("label", ""))
                            d.setdefault(_norm(lid), lid)
                            for s in n.get("synonyms") or []:
                                d.setdefault(_norm(s), lid)
                    mp[(cid, alab)] = d
            return mp

        tax = get_attribute_taxonomy()
        leaf_map = _build_leaf_label_map(tax)
        gcol = group_col or "group"
        raw_rows = session_state.get("_attr_raw_rows") or []
        raw_idx: Dict[tuple[str, str], Dict[str, str]] = {}
        for rr in raw_rows:
            try:
                pk = (
                    str(rr.get(product_col, "")).strip().lower(),
                    str(rr.get(gcol, "")).strip().lower(),
                )
            except Exception:
                continue
            vals: Dict[str, str] = {}
            for k, v in rr.items():
                if isinstance(k, str) and k.endswith("_raw") and v is not None:
                    vals[k[:-4].strip().lower()] = str(v)
            if vals:
                raw_idx[pk] = vals
        # Remap
        rows = (
            result.to_dicts()
            if isinstance(result, pl.DataFrame)
            else result.collect().to_dicts()
        )
        changed = False
        for row in rows:
            try:
                prod = str(row.get(product_col, "")).strip().lower()
                cat = str(row.get(gcol, "")).strip().lower()
            except Exception:
                continue
            raw_vals = raw_idx.get((prod, cat))
            if not raw_vals:
                continue
            for attr, raw_val in raw_vals.items():
                if attr not in row:
                    continue
                cur = str(row.get(attr, "")).strip().lower()
                if cur != "not in taxonomy":
                    continue
                key = (cat, attr)
                m = leaf_map.get(key)
                if not m:
                    continue
                norm = " ".join(
                    re.sub(r"[-_\u2010-\u2015]+", " ", str(raw_val).lower()).split()
                )
                mapped = m.get(norm)
                if mapped:
                    row[attr] = mapped
                    src_col = f"attr_source_{attr}"
                    row[src_col] = "remap"
                    changed = True
        if changed:
            result = pl.DataFrame(rows)
            # Persist deterministic remaps to the product attribute cache so
            # subsequent runs do not retain stale 'not in taxonomy' values.
            try:
                from src.product_attribute_cache import load_cache, save_cache

                cache = load_cache()
                cache_changed = False
                for row in rows:
                    try:
                        prod_key = str(row.get(product_col, "")).strip().lower()
                        cat_key = str(row.get(gcol, "")).strip().lower()
                    except Exception:
                        continue
                    if not (prod_key and cat_key):
                        continue
                    # For each attribute remapped in this row, update the cache entry
                    for k, v in list(row.items()):
                        if not (isinstance(k, str) and k.startswith("attr_source_")):
                            continue
                        if v != "remap":
                            continue
                        attr_name = k[len("attr_source_") :].strip().lower()
                        new_val = str(row.get(attr_name, "")).strip().lower()
                        if not new_val:
                            continue
                        cat_bucket = cache.setdefault(cat_key, {})
                        updated_here = False
                        # Try to update any brand bucket that contains this product
                        for brand_key, prod_map in list(cat_bucket.items()):
                            if isinstance(prod_map, dict) and prod_key in prod_map:
                                prod_attrs = prod_map.setdefault(prod_key, {})
                                if isinstance(prod_attrs, dict):
                                    prod_attrs[attr_name] = new_val
                                    updated_here = True
                                    cache_changed = True
                        # If product not found under any brand, fall back to brandless bucket
                        if not updated_here:
                            prod_map = cat_bucket.setdefault("", {})
                            prod_attrs = prod_map.setdefault(prod_key, {})
                            if isinstance(prod_attrs, dict):
                                prod_attrs[attr_name] = new_val
                                cache_changed = True
                if cache_changed:
                    save_cache(cache)
            except Exception as e:
                LOGGER.warning("Failed to persist deterministic remaps to cache: %s", e)
    except Exception as e:
        LOGGER.warning("Deterministic remap failed: %s", e)
    return result


def _render_attribute_scoring(
    mapping: dict, df: pl.DataFrame | pl.LazyFrame
) -> pl.DataFrame:
    """UI for scoring selected products against confirmed attributes."""
    source_mode = _normalize_attr_source(session_state.get("attr_source"))
    if source_mode != SOURCE_DETERMINISTIC_LLM:
        return df
    if not session_state.get("attr_attrs_confirmed"):
        llm_wrapper = session_state.get("llm_wrapper")
        if llm_wrapper:
            lf = df.lazy() if isinstance(df, pl.DataFrame) else df
            level, group_col = session_state.get("attr_group_choice", ("none", None))
            if group_col:
                groups = session_state.get("attr_groups")
                if not groups:
                    groups = (
                        lf.select(pl.col(group_col).unique())
                        .collect()
                        .get_column(group_col)
                        .to_list()
                    )
            else:
                groups = ["All products"]
            existing_cols, _ = get_schema_and_column_names(lf)
            use_batch = session_state.get("attr_llm_mode", "flex") == "batch"
            service_tier = session_state.get(
                "attr_service_tier", "flex" if not use_batch else "standard"
            )
            _discover_scoring_attributes(
                groups,
                existing_cols,
                llm_wrapper,
                use_batch=use_batch,
                throttle=1.0,
                service_tier=service_tier,
            )
        if not session_state.get("attr_attrs_confirmed"):
            ui.info("Confirm attributes firui.")
            return df

    products = session_state.get("attr_top_products")
    if not products:
        ui.info("Select top products firui.")
        return df

    attr_map = session_state.get("attr_suggestions")
    if not attr_map:
        ui.info("No attributes defined.")
        return df

    _, group_col = session_state.get("attr_group_choice", ("none", None))
    product_col = mapping.get("product_column")
    data = df.collect() if isinstance(df, pl.LazyFrame) else df
    llm_wrapper = session_state.get("llm_wrapper")

    mode = ui.radio(
        "Attribute output",
        ["Confidence", "Explanation", "None"],
        index=2,
        key="attr_score_mode",
    )
    output_mode = mode.lower()

    if ui.button("Score attributes", key="attr_score_btn"):
        groups = session_state.get("attr_groups")
        progress = ui.progress(0)
        with ui.spinner("Scoring attributes…"):
            use_batch = session_state.get("attr_llm_mode", "flex") == "batch"
            service_tier = session_state.get(
                "attr_service_tier", "flex" if not use_batch else "standard"
            )
            merchant_col = mapping.get("merchant_column")
            brand_col = mapping.get("brand_column")
            category_col = mapping.get("category_column")
            desc_col = mapping.get("description_column")
            total_products = len(products)

            def _clamped_progress(p: int, t: int) -> None:
                try:
                    pct = int((p / max(1, t)) * 100)
                except Exception as e:
                    logger.warning(
                        "Progress percentage calculation failed: p=%s t=%s err=%s",
                        p,
                        t,
                        e,
                    )
                    pct = 0
                pct = max(0, min(100, pct))
                progress.progress(pct)

            progress_cb = _clamped_progress if not use_batch else None
            scores = _score_attributes_batch(
                llm_wrapper,
                data,
                product_col,
                products,
                attr_map,
                group_col=group_col,
                groups=groups,
                output_mode=output_mode,
                use_batch=use_batch,
                service_tier=service_tier,
                progress_cb=progress_cb,
            )
        try:
            progress.progress(100)
        except Exception as e:
            logger.warning("Failed to update progress to 100%%: %s", e)
        top_data = session_state.get("attr_top_data")
        if isinstance(scores, pl.DataFrame) and isinstance(top_data, pl.DataFrame):
            top_flag = top_data.select([product_col, "TopProduct"]).unique()
            scores = scores.join(top_flag, on=product_col, how="left")
        session_state["attr_scores"] = scores

    scores = session_state.get("attr_scores")
    if isinstance(scores, pl.DataFrame) and scores.height > 0:
        ui.dataframe(scores)
        ui.download_button(
            "Download attribute scores (Excel)",
            data=convert_df_excel(scores),
            file_name="attribute_scores.xlsx",
            mime=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            key="attr_score_download_excel",
        )
        auto_join = session_state.get("attr_auto_join", True)
        join_btn = False
        if not auto_join:
            join_btn = ui.button(
                "Join attributes to main dataset",
                key="attr_join_btn_score",
            )
        merged = False
        if auto_join or join_btn:
            classification = session_state.get("attr_classification")
            _, group_col = session_state.get("attr_group_choice", ("none", None))
            try:
                df = merge_attribute_results(
                    df,
                    mapping,
                    scores,
                    classification,
                    group_col=group_col,
                )
                ui.info("Attributes merged into main dataset")
                merged = True
            except ValueError as exc:  # pragma: no cover - UI side effect
                ui.warning(str(exc))
        if merged:
            df_dl = df.collect() if isinstance(df, pl.LazyFrame) else df
            ui.download_button(
                "Download joined dataset",
                data=convert_df_parquet(df_dl),
                file_name="joined_dataset.parquet",
                mime="application/x-parquet",
                key="attr_joined_download_scoring",
            )
        # Caption about running attribute analysis removed as that feature is no
        # longer available.
    return df


def _fetch_top_websites(
    top_df: pl.DataFrame, mapping: dict, llm_wrapper
) -> pl.DataFrame:
    """Return website information for confirmed top products."""

    columns, _ = get_schema_and_column_names(top_df)

    category_col = mapping.get("category_column")
    category_val = ""
    if category_col and category_col in columns and top_df.height > 0:
        non_null = top_df.get_column(category_col).drop_nulls()
        if non_null.len() > 0:
            category_val = str(non_null.to_list()[0])

    if category_val and llm_wrapper:
        merchant_col = mapping.get("merchant_column")
        brand_col = mapping.get("brand_column")
        missing = [c for c in (merchant_col, brand_col) if c and c not in columns]
        if missing:
            msg = "Skipping website lookup: missing required column(s): " + ", ".join(
                missing
            )
            LOGGER.warning(msg)
            ui.warning(msg)
            return pl.DataFrame()
        try:
            # Use the same service tier logic as attribute mapping
            use_batch = session_state.get("attr_llm_mode", "flex") == "batch"
            service_tier = session_state.get(
                "attr_service_tier", "flex" if not use_batch else "standard"
            )
            # Require market context for safe website lookups
            naming_ctx = get_naming_params()
            industry_key = naming_ctx["industry"]
            industry_desc_key = naming_ctx["industryDescription"]
            industry_val = session_state.get(industry_key) or (
                session_state.get("attr_param_dict", {}).get(industry_key)
                if isinstance(session_state.get("attr_param_dict"), dict)
                else None
            )
            industry_desc_val = session_state.get(industry_desc_key) or (
                session_state.get("attr_param_dict", {}).get(industry_desc_key)
                if isinstance(session_state.get("attr_param_dict"), dict)
                else None
            )
            if not (industry_val or industry_desc_val):
                ui.warning(
                    "Provide the market Industry (or an Industry description) before website lookups."
                )
                return pl.DataFrame()
            result = enrich_attributes(
                top_df,
                category_val,
                lambda *_a, **_k: {},
                merchant_col=merchant_col,
                brand_col=brand_col,
                category_col=category_col,
                llm_wrapper=llm_wrapper,
                service_tier=service_tier,
            )
            return result.websites
        except ValueError:
            return pl.DataFrame()

    return pl.DataFrame()


def _prepare_objective_attribute_map(
    lf: pl.LazyFrame | pl.DataFrame,
    data: pl.DataFrame,
    group_col: str | None,
    llm_wrapper: Any,
    *,
    apply_activity_gate: bool = True,
) -> dict[str, list[str]]:
    """Load objective attributes from the taxonomy and record missing groups."""

    # Determine the groups in scope for this run
    groups = session_state.get("attr_groups")
    if not groups:
        if group_col:
            groups = (
                lf.select(pl.col(group_col).unique())
                .collect()
                .get_column(group_col)
                .to_list()
            )
        else:
            groups = ["All products"]
        session_state["attr_groups"] = groups

    # Reuse cached suggestions only if they fully cover the current groups.
    existing = session_state.get("attr_obj_suggestions")
    if isinstance(existing, dict) and groups:

        def _has_group(g: str) -> bool:
            gl = str(g).strip().lower()
            return (g in existing) or (gl in existing)

        if all(_has_group(g) for g in groups):
            return existing

    try:
        taxonomy = get_attribute_taxonomy()
    except (FileNotFoundError, ValueError):  # pragma: no cover - defensive
        taxonomy = {}

    # Accept both taxonomy id and label as keys (case-insensitive)
    cat_map: dict[str, dict] = {}
    for c in taxonomy.get("categories", []) or []:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id", "")).strip().lower()
        if cid:
            cat_map[cid] = c
        clabel = str(c.get("label", "")).strip().lower()
        if clabel and clabel not in cat_map:
            cat_map[clabel] = c

    attr_map: dict[str, list[str]] = {}
    missing: list[str] = []
    activity_map = get_attribute_activity() if apply_activity_gate else {}

    for grp in groups:
        key = str(grp).strip().lower()
        cat = cat_map.get(key)
        if cat:
            cat_activity = (
                activity_map.get(key)
                or activity_map.get(str(cat.get("id", "")).strip().lower())
                or activity_map.get(str(cat.get("label", "")).strip().lower())
                or {}
            )
            attrs: list[str] = []
            for attr in cat.get("attributes", []) or []:
                attr_id = str(attr.get("id", "")).strip().lower()
                attr_label = str(attr.get("label", "")).strip().lower()
                status = "active"
                if apply_activity_gate:
                    status = cat_activity.get(
                        attr_id,
                        cat_activity.get(attr_label, "active"),
                    )
                if status != "active":
                    continue
                attr_value = str(attr.get("id", "")).strip()
                if attr_value:
                    attrs.append(attr_value)
            attr_map[grp] = attrs
        else:
            missing.append(grp)

    session_state["attr_obj_missing"] = missing
    session_state["attr_obj_suggestions"] = attr_map
    return attr_map


def _render_attribute_classification(
    mapping: dict,
    df: pl.DataFrame | pl.LazyFrame,
    *,
    fetch_websites: bool = True,
) -> pl.DataFrame:
    """Classify products using objective attributes."""
    source_mode = _normalize_attr_source(session_state.get("attr_source"))
    if source_mode == SOURCE_EXCEL:
        return df

    # Recover top products when possible to avoid forcing users to re-confirm
    products = session_state.get("attr_top_products")
    deterministic_only = source_mode == SOURCE_DETERMINISTIC
    llm_wrapper = None if deterministic_only else session_state.get("llm_wrapper")
    _, group_col = session_state.get("attr_group_choice", ("none", None))
    product_col = mapping.get("product_column")
    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    data = df.collect() if isinstance(df, pl.LazyFrame) else df
    if not products:
        marked = session_state.get("attr_marked_df")
        if (
            isinstance(marked, pl.DataFrame)
            and product_col in marked.columns
            and "TopProduct" in marked.columns
        ):
            recovered = (
                marked.filter(pl.col("TopProduct")).get_column(product_col).to_list()
            )
            if recovered:
                products = list(dict.fromkeys(recovered))
                session_state["attr_top_products"] = products
    if not products:
        ui.info("Select top products firui.")
        return df

    attr_map = _prepare_objective_attribute_map(
        lf,
        data,
        group_col,
        llm_wrapper,
        apply_activity_gate=not deterministic_only,
    )

    # Removed: NIT-only re-run policy and checkbox. Standard behavior is to NOT re-run
    # cached 'not in taxonomy' or 'N/A' values unless inputs fundamentally change.

    rank_has_totals = session_state.get("attr_rank_has_totals", False)

    to_discover: list[str] = []
    if ui.button("Classify products", key="attr_classify_btn"):
        # Block classification until market context is provided
        try:
            naming_ctx = get_naming_params()
            industry_key = naming_ctx["industry"]
            industry_desc_key = naming_ctx["industryDescription"]
            industry_val = session_state.get(industry_key) or (
                session_state.get("attr_param_dict", {}).get(industry_key)
                if isinstance(session_state.get("attr_param_dict"), dict)
                else None
            )
            industry_desc_val = session_state.get(industry_desc_key) or (
                session_state.get("attr_param_dict", {}).get(industry_desc_key)
                if isinstance(session_state.get("attr_param_dict"), dict)
                else None
            )
        except Exception:
            industry_val = None
            industry_desc_val = None
        if not (industry_val or industry_desc_val):
            ui.error(
                "Please provide the market Industry (or an Industry description) before running classification."
            )
            fetch_websites = False
            session_state.pop("attr_websites", None)
        use_batch = False
        if not deterministic_only:
            use_batch = session_state.get("attr_llm_mode", "flex") == "batch"
        service_tier = session_state.get(
            "attr_service_tier", "flex" if not use_batch else "standard"
        )
        missing = session_state.get("attr_obj_missing") or []
        sel_groups = session_state.get("attr_groups") or []
        empty_groups = [
            g
            for g in sel_groups
            if not (attr_map.get(g) or attr_map.get(str(g).strip().lower()))
        ]
        to_discover = sorted({*missing, *empty_groups})
        if to_discover and llm_wrapper and not deterministic_only:
            info_txt = (
                "Generating taxonomy branch for: "
                + ", ".join(to_discover)
                + " — this may take a while"
            )
            with ui.spinner(info_txt):
                discovered = _discover_objective_attributes(
                    to_discover,
                    get_schema_and_column_names(data)[0],
                    llm_wrapper,
                    use_batch=use_batch,
                    throttle=1.0,
                    service_tier=service_tier,
                )
            attr_map.update(discovered)
            session_state["attr_obj_suggestions"] = attr_map
            # Persist only truly missing categories
            if missing:
                ui.caption("Saving taxonomy updates…")
                with ui.spinner("Writing taxonomy JSON…"):
                    still_missing = _ensure_taxonomy_categories(missing, attr_map)
                if still_missing:
                    # Ignore perpetual lip gloss mismatch while normalization replaces spaces with underscores.
                    unresolved = [
                        cat
                        for cat in still_missing
                        if str(cat).strip().lower().replace(" ", "_")
                        not in {"lip_gloss", "lipgloss"}
                    ]
                    if unresolved:
                        msg = (
                            "Taxonomy branches are not persisted automatically. "
                            "Proceeding without saving for: " + ", ".join(unresolved)
                        )
                        LOGGER.info(msg)
                        ui.info(msg)
                    # Continue classification using in-memory suggestions
                    session_state["attr_obj_missing"] = unresolved
                else:
                    session_state["attr_obj_missing"] = []
            created_non_empty = [
                g
                for g in to_discover
                if (attr_map.get(g) or attr_map.get(str(g).strip().lower()))
            ]
            if created_non_empty:
                ui.success("Attributes prepared for: " + ", ".join(created_non_empty))
            else:
                ui.warning(
                    "No attributes could be generated. Provide industry/company context and try again."
                )

        if not attr_map:
            if deterministic_only and to_discover:
                ui.info(
                    "Product Text-only mode cannot generate new taxonomy branches. "
                    "Switch to 'Web Search' to create attributes for missing categories."
                )
            else:
                ui.info("No attributes defined.")
            return df

        # Avoid running classification when no attributes are available for
        # the selected groups; otherwise the table will contain only products
        # without any attribute columns.
        existing_groups = session_state.get("attr_groups")
        sel_groups = existing_groups or list(attr_map.keys())
        non_empty_attrs = [
            a
            for g in sel_groups
            for a in (attr_map.get(g) or attr_map.get(str(g).strip().lower()) or [])
        ]
        if not non_empty_attrs and not attr_map:
            ui.info(
                "No attributes available for the selected groups. Classification skipped."
            )
            return df

        groups = existing_groups or sel_groups
        merchant_col = mapping.get("merchant_column")
        brand_col = mapping.get("brand_column")
        category_col = mapping.get("category_column")
        desc_col = mapping.get("description_column")
        progress = ui.progress(0)
        with ui.spinner("Classifying attributes…"):
            total_products = len(products)

            def _clamped_progress(p: int, t: int) -> None:
                try:
                    pct = int((p / max(1, t)) * 100)
                except Exception:
                    pct = 0
                pct = max(0, min(100, pct))
                progress.progress(pct)

            progress_cb = _clamped_progress if not use_batch else None
            table = _classify_attributes_batch(
                llm_wrapper,
                data,
                product_col,
                products,
                attr_map,
                group_col=group_col,
                groups=groups,
                use_batch=use_batch,
                service_tier=service_tier,
                merchant_col=merchant_col,
                brand_col=brand_col,
                category_col=category_col,
                desc_col=desc_col,
                progress_cb=progress_cb,
                deterministic_only=deterministic_only,
            )
        try:
            progress.progress(100)
        except Exception as e:
            logger.warning("Failed to update progress to 100%%: %s", e)
        top_data = session_state.get("attr_top_data")
        ranking = session_state.get("attr_ranking")
        rank_has_totals = False
        if isinstance(table, pl.DataFrame) and isinstance(top_data, pl.DataFrame):
            amount_col = session_state.get("attr_amount_col")
            naming = get_naming_params()
            price_name = naming["priceName"]
            units_name = naming["unitsName"]
            volume_name = naming["volumeName"]

            # 1) Aggregate contextual columns from the TopProduct subset
            context_candidates: list[str] = []
            brand_col = mapping.get("brand_column")
            if isinstance(brand_col, str):
                context_candidates.append(brand_col)
            category_for_join = mapping.get("category_column")
            if isinstance(category_for_join, str):
                context_candidates.append(category_for_join)
            segment_for_join = mapping.get("subcategory_column")
            if isinstance(segment_for_join, str):
                context_candidates.append(segment_for_join)
            desc_col = mapping.get("description_column")
            if isinstance(desc_col, str):
                context_candidates.append(desc_col)
            line_col = session_state.get("attr_line_col")
            if isinstance(line_col, str):
                context_candidates.append(line_col)

            context_join = None
            existing_cols = set(table.columns)
            join_exprs: list[pl.Expr] = []
            for col_name in dict.fromkeys(context_candidates):
                if (
                    col_name
                    and col_name in top_data.columns
                    and col_name not in existing_cols
                ):
                    join_exprs.append(pl.col(col_name).first().alias(col_name))
            if join_exprs:
                context_join = top_data.group_by(product_col).agg(join_exprs)

            # 2) Prefer totals, price, rank and cum % from Pareto ranking (global scope)
            rank_join = None
            if isinstance(ranking, pl.DataFrame) and product_col in ranking.columns:
                rank_cols = [product_col]
                for c in (
                    "rank",
                    "total_amount",
                    "total_units",
                    "total_volume",
                    price_name,
                    "cum_amount_pct",
                    "cum_share",
                ):
                    if c in ranking.columns and c not in rank_cols:
                        rank_cols.append(c)
                rank_join = ranking.select(rank_cols)
                rank_has_totals = "total_amount" in rank_join.columns

            # 3) Fallback to deriving totals/price from TopProduct subset when
            # ranking is unavailable or missing totals (e.g. in certain tests)
            totals_join = None
            needs_totals = (
                amount_col
                and amount_col in top_data.columns
                and (rank_join is None or "total_amount" not in rank_join.columns)
            )
            if needs_totals:
                totals_exprs: list[pl.Expr] = [
                    pl.col(amount_col).sum().alias("total_amount")
                ]
                totals_exprs.append(
                    pl.col(amount_col).is_not_null().sum().alias("_amount_count")
                )
                if units_name:
                    lower_map = {c.lower(): c for c in top_data.columns}
                    units_col = lower_map.get(str(units_name).lower())
                    if units_col and units_col in top_data.columns:
                        totals_exprs.append(
                            pl.col(units_col).sum().alias("total_units")
                        )
                if volume_name:
                    lower_map_v = {c.lower(): c for c in top_data.columns}
                    vol_col = lower_map_v.get(str(volume_name).lower())
                    if vol_col and vol_col in top_data.columns:
                        totals_exprs.append(pl.col(vol_col).sum().alias("total_volume"))
                totals_join = top_data.group_by(product_col).agg(totals_exprs)
                if "_amount_count" in totals_join.columns:
                    totals_join = totals_join.with_columns(
                        pl.when(pl.col("_amount_count") == 0)
                        .then(pl.lit(None))
                        .otherwise(pl.col("total_amount"))
                        .alias("total_amount")
                    ).drop("_amount_count")
                if "total_units" in totals_join.columns:
                    totals_join = totals_join.with_columns(
                        pl.when(pl.col("total_units") != 0)
                        .then(pl.col("total_amount") / pl.col("total_units"))
                        .otherwise(None)
                        .alias(price_name)
                    )
                elif "total_volume" in totals_join.columns:
                    totals_join = totals_join.with_columns(
                        pl.when(pl.col("total_volume") != 0)
                        .then(pl.col("total_amount") / pl.col("total_volume"))
                        .otherwise(None)
                        .alias(price_name)
                    )

            # 4) Apply joins: context columns -> rank/totals
            if context_join is not None:
                table = table.join(context_join, on=product_col, how="left")
            if rank_join is not None:
                table = table.join(rank_join, on=product_col, how="left")
            if totals_join is not None:
                join_cols = [
                    c
                    for c in totals_join.columns
                    if c == product_col or c not in table.columns
                ]
                if len(join_cols) > 1:
                    table = table.join(
                        totals_join.select(join_cols), on=product_col, how="left"
                    )

            # 5) Sort by rank if present else by total_amount
            if isinstance(table, pl.DataFrame):
                if "rank" in table.columns:
                    table = table.sort("rank", nulls_last=True)
                elif "total_amount" in table.columns:
                    table = table.sort("total_amount", descending=True, nulls_last=True)

            # 5b) Recompute cumulative percent based on current order
            if "total_amount" in table.columns:
                total_amt = float(table.select(pl.col("total_amount").sum()).item())
                if total_amt > 0:
                    table = table.with_columns(
                        (pl.cum_sum("total_amount") / pl.lit(total_amt) * 100).alias(
                            "cum_amount_pct"
                        )
                    )

            # 6) Round key numeric columns for readability in the UI too
            to_round = []
            for col_name in (
                "total_amount",
                "total_units",
                "total_volume",
                price_name,
                "cum_amount_pct",
            ):
                if col_name in table.columns:
                    to_round.append(
                        pl.col(col_name).cast(pl.Float64).round(1).alias(col_name)
                    )
            if to_round:
                table = table.with_columns(to_round)

            # 7) Add a user-friendly cumulative percent column name
            pretty_cum_name = "Cumulative % on total amount"
            if (
                "cum_amount_pct" in table.columns
                and pretty_cum_name not in table.columns
            ):
                table = table.with_columns(
                    pl.col("cum_amount_pct").alias(pretty_cum_name)
                )

            table = drop_columns(table, ["TopProduct", "cum_amount_pct", "cum_share"])
        # Heuristic quality check: quarantine clearly broken single-select attributes
        # Hide columns with poor signal to avoid exposing nonsensical results
        if isinstance(table, pl.DataFrame) and table.height > 0:
            naming = get_naming_params()
            price_col = naming["priceName"]
            extras = {
                brand_col or "",
                "total_amount",
                "total_units",
                "total_volume",
                price_col,
                "rank",
                "cum_amount_pct",
                "cum_share",
                "Cumulative % on total amount",
                product_col,
                (group_col or "group"),
            }
            candidate_cols = [
                c
                for c in table.columns
                if "__" not in c
                and c not in extras
                and not c.startswith("attr_source_")
            ]
            hide: list[str] = []
            bad_entries: list[dict] = []
            # Build attribute-id lookup per category (by id or label) for review entries
            try:
                taxonomy = get_attribute_taxonomy()
            except Exception as e:
                logger.exception(
                    "Failed to load attribute taxonomy; proceeding without: %s", e
                )
                taxonomy = {}
            cat_by_key = {}
            for cnode in taxonomy.get("categories", []) or []:
                cid = str(cnode.get("id", "")).strip().lower()
                clab = str(cnode.get("label", "")).strip().lower()
                cat_by_key[cid] = cnode
                cat_by_key[clab] = cnode
            group_field = group_col or "group"
            for col in candidate_cols:
                try:
                    stats = table.select(
                        pl.len().alias("total"),
                        pl.col(col).is_null().sum().alias("nulls"),
                        pl.col(col)
                        .cast(pl.Utf8)
                        .str.to_lowercase()
                        .eq("n/a")
                        .sum()
                        .alias("nacnt"),
                        pl.col(col)
                        .cast(pl.Utf8)
                        .str.to_lowercase()
                        .eq("not in taxonomy")
                        .sum()
                        .alias("othercnt"),
                        pl.col(col).n_unique().alias("nuniq"),
                    ).to_dicts()[0]
                except Exception as e:
                    logger.exception("Failed stats for column '%s': %s", col, e)
                    continue
                total = int(stats.get("total", 0) or 0)
                nulls = int(stats.get("nulls", 0) or 0)
                nacnt = int(stats.get("nacnt", 0) or 0)
                othercnt = int(stats.get("othercnt", 0) or 0)
                nuniq = int(stats.get("nuniq", 0) or 0)
                denom = max(1, total - nulls)
                bad_ratio = (nacnt + othercnt) / denom
                if bad_ratio >= 0.6 or nuniq > 30:
                    hide.append(col)
                    # Prepare review entries from non-N/A/not-in-taxonomy values grouped by category
                    if group_field in table.columns:
                        val_df = table.select(
                            pl.col(group_field)
                            .cast(pl.Utf8)
                            .str.to_lowercase()
                            .alias("cat"),
                            pl.col(col).cast(pl.Utf8).str.strip_chars().alias("val"),
                        ).filter(
                            pl.col("val").is_not_null()
                            & (pl.col("val").str.to_lowercase() != "n/a")
                            & (pl.col("val").str.to_lowercase() != "not in taxonomy")
                            & (pl.col("val") != "")
                        )
                        if val_df.height > 0:
                            counts = (
                                val_df.group_by(["cat", "val"])
                                .len()
                                .rename({"len": "count"})
                            )
                            for row in counts.iter_rows(named=True):
                                cat_key = str(row["cat"]).strip().lower()
                                cnode = cat_by_key.get(cat_key)
                                if not cnode:
                                    continue
                                # map attribute label -> id within this category
                                attr_id = None
                                for a in cnode.get("attributes", []) or []:
                                    lab = str(a.get("label", "")).strip().lower()
                                    aid = str(a.get("id", "")).strip().lower()
                                    if (
                                        lab == col.strip().lower()
                                        or aid == col.strip().lower()
                                    ):
                                        attr_id = aid or lab
                                        break
                                if not attr_id:
                                    continue
                                bad_entries.append(
                                    {
                                        "category": str(cnode.get("id", cat_key))
                                        .strip()
                                        .lower(),
                                        "attribute": attr_id,
                                        "value": str(row["val"]).strip(),
                                        "count": (
                                            int(row["count"])
                                            if isinstance(row["count"], int)
                                            else 1
                                        ),
                                    }
                                )
            if hide:
                if not deterministic_only:
                    table = table.drop(hide, strict=False)
                    ui.warning(
                        "Hidden low-quality attribute columns due to poor signal: "
                        + ", ".join(sorted(hide))
                    )
            if bad_entries:
                # Stash for optional reactive improvement run
                session_state["attr_bad_cols"] = hide
                session_state["attr_bad_entries"] = bad_entries
        # Derive SPF buckets for UI/analytics to avoid high-cardinality numeric values
        try:
            spf_col = next(
                (c for c in ("spf", "spf_value") if c in table.columns), None
            )
            if spf_col:
                spf_num = pl.col(spf_col).cast(pl.Int64, strict=False)
                table = table.with_columns(
                    pl.when(spf_num.is_null())
                    .then(pl.lit("N/A"))
                    .when((spf_num >= 6) & (spf_num <= 14))
                    .then(pl.lit("Low (6–14)"))
                    .when((spf_num >= 15) & (spf_num <= 29))
                    .then(pl.lit("Medium (15–29)"))
                    .when((spf_num >= 30) & (spf_num <= 49))
                    .then(pl.lit("High (30–49)"))
                    .when(spf_num >= 50)
                    .then(pl.lit("Very high (50+)"))
                    .otherwise(pl.lit("N/A"))
                    .alias("spf")
                )
        except Exception:
            # Non-fatal; keep original table if bucketing fails
            pass
        # Ensure a single row per join key before storing classification
        try:
            join_keys: list[str] = []
            if product_col and product_col in table.columns:
                join_keys.append(product_col)
            grp_key = session_state.get("attr_group_choice", ("none", None))[1]
            if grp_key and grp_key in table.columns:
                join_keys.append(grp_key)
            if join_keys:
                table = table.unique(subset=join_keys, maintain_order=True)
        except Exception as e:
            logger.exception("Failed to deduplicate classification rows: %s", e)
        session_state["attr_classification"] = table
        # Caption: number of captured sources and log path
        try:
            sources_rows = session_state.get("_attr_sources_rows") or []
            if isinstance(sources_rows, list) and sources_rows:
                from modules.add_attributes.sources_audit import get_sources_log_path

                ui.caption(
                    f"Captured {len(sources_rows)} sources (saved to: {get_sources_log_path()})"
                )
        except Exception:
            pass

        if fetch_websites and isinstance(top_data, pl.DataFrame):
            websites = _fetch_top_websites(top_data, mapping, llm_wrapper)
            session_state["attr_websites"] = websites
        session_state["attr_rank_has_totals"] = rank_has_totals

    table = session_state.get("attr_classification")
    ranking_df = session_state.get("attr_ranking")
    rank_has_totals = session_state.get("attr_rank_has_totals", False)
    if isinstance(table, pl.DataFrame) and table.height > 0:
        # Take a snapshot for export before any UI edits
        export_table = table.clone()
        ranking_snapshot: pl.DataFrame | None = None
        if isinstance(ranking_df, pl.DataFrame) and ranking_df.height > 0:
            ranking_snapshot = ranking_df.clone()
            session_state["attr_ranking"] = ranking_snapshot
        csv_payload = export_table
        excel_payload = export_table
        if ranking_snapshot is not None:
            product_key = (
                mapping.get("product_column") if isinstance(mapping, dict) else None
            )
            if isinstance(product_key, str):
                try:
                    join_cols = [
                        c for c in ranking_snapshot.columns if c != product_key
                    ]
                    if join_cols:
                        excel_payload = export_table.join(
                            ranking_snapshot.select([product_key] + join_cols),
                            on=product_key,
                            how="left",
                        )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "Failed to merge ranking snapshot into export payload: %s", exc
                    )
                    excel_payload = export_table
        try:
            csv_payload.write_csv(io.BytesIO())
        except Exception:
            pass
        if not rank_has_totals and "rank" in table.columns:
            table = table.drop("rank")
        # Build optional Audit — Not in taxonomy sheet with raw values (wide -> long)
        audit_oov: pl.DataFrame | None = None
        try:
            product_col = mapping.get("product_column")
            grp_key = session_state.get("attr_group_choice", ("none", None))[1]
            raw_rows = session_state.get("_attr_raw_rows")
            if isinstance(product_col, str) and isinstance(raw_rows, list) and raw_rows:
                raw_df = pl.DataFrame(raw_rows, orient="row")
                # Construct long-form rows: one per attribute_raw column
                records: list[dict] = []
                # Create lookup from main table for normalized values
                main_lookup = table
                for rr in raw_rows:
                    prod_val = rr.get(product_col)
                    grp_val = rr.get(grp_key) if isinstance(grp_key, str) else None
                    for k, v in rr.items():
                        if not (isinstance(k, str) and k.endswith("_raw")):
                            continue
                        attr = k[:-4]
                        raw_val = v
                        # Skip plain placeholders; keep sentinel-with-annotation (e.g., "not in taxonomy (…)")
                        keep_row = True
                        note_val = None
                        # Prefer a structured note captured from the LLM, when available
                        try:
                            structured = rr.get(f"{attr}_note")
                            if isinstance(structured, (str, int, float)):
                                s = str(structured).strip()
                                if s:
                                    note_val = s
                        except Exception:
                            pass
                        try:
                            from modules.add_attributes.attribute_classification import (
                                _is_trivial_placeholder,
                            )

                            if _is_trivial_placeholder(raw_val):
                                # Include if there is an explanatory annotation after the sentinel
                                m = re.search(
                                    r"^\s*(?:not in taxonomy|n/a|unknown)\s*\(([^)]*)\)",
                                    str(raw_val).lower(),
                                )
                                if m:
                                    # Only set from raw annotation when structured note is absent
                                    if not note_val:
                                        note_val = m.group(1)
                                    keep_row = True
                                else:
                                    keep_row = False
                        except Exception:
                            keep_row = True
                        if not keep_row:
                            continue
                        norm_val = None
                        try:
                            if (
                                isinstance(main_lookup, pl.DataFrame)
                                and attr in main_lookup.columns
                            ):
                                if (
                                    isinstance(grp_key, str)
                                    and grp_key in main_lookup.columns
                                ):
                                    row = main_lookup.filter(
                                        (pl.col(product_col) == prod_val)
                                        & (pl.col(grp_key) == grp_val)
                                    )
                                else:
                                    row = main_lookup.filter(
                                        pl.col(product_col) == prod_val
                                    )
                                if row.height > 0:
                                    norm_val = row.get_column(attr).item()
                        except Exception:
                            norm_val = None
                        rec = {
                            product_col: prod_val,
                            "attribute": attr,
                            "normalized": norm_val,
                            "raw_value": raw_val,
                        }
                        if isinstance(grp_key, str):
                            rec[grp_key] = grp_val
                        if note_val is not None:
                            rec["note"] = note_val
                        records.append(rec)
                if records:
                    audit_oov = pl.DataFrame(records, orient="row")
        except Exception as e:
            logger.warning("Failed to prepare Audit — Not in taxonomy sheet: %s", e)
        # Optionally include the user-selected Product Parent column in the Excel export only
        try:
            product_col = mapping.get("product_column")
            line_col = session_state.get("attr_line_col")
            top_data = session_state.get("attr_top_data")
            if (
                isinstance(top_data, pl.DataFrame)
                and isinstance(product_col, str)
                and product_col in top_data.columns
                and isinstance(line_col, str)
                and line_col in top_data.columns
                and product_col in export_table.columns
            ):
                line_join = top_data.group_by(product_col).agg(
                    pl.col(line_col).first().alias(line_col)
                )
                export_table = export_table.join(line_join, on=product_col, how="left")
        except Exception as e:
            logger.warning("Failed to include Product Parent column in export: %s", e)
        # Show the unified product table with attributes + metrics
        table = ui.data_editor(table, num_rows="dynamic")
        session_state["attr_classification"] = table
        # Round selected numeric columns to a single decimal for export
        # (keeps UI precision intact while making Excel easier to read)
        try:
            naming = get_naming_params()
            price_col = naming["priceName"]
        except Exception as e:
            logger.warning("Failed to resolve priceName; defaulting to 'price': %s", e)
            price_col = "price"
        # Recompute cumulative percent for the export based on current order
        if "total_amount" in export_table.columns:
            total_amt = float(export_table.select(pl.col("total_amount").sum()).item())
            if total_amt > 0:
                export_table = export_table.with_columns(
                    (pl.cum_sum("total_amount") / pl.lit(total_amt) * 100).alias(
                        "cum_amount_pct"
                    )
                )

        round_exprs: list[pl.Expr] = []
        if "total_amount" in export_table.columns:
            round_exprs.append(
                pl.col("total_amount").cast(pl.Float64).round(1).alias("total_amount")
            )
        if "total_units" in export_table.columns:
            round_exprs.append(
                pl.col("total_units").cast(pl.Float64).round(1).alias("total_units")
            )
        if "total_volume" in export_table.columns:
            round_exprs.append(
                pl.col("total_volume").cast(pl.Float64).round(1).alias("total_volume")
            )
        if "total_volume" in export_table.columns:
            round_exprs.append(
                pl.col("total_volume").cast(pl.Float64).round(1).alias("total_volume")
            )
        if price_col in export_table.columns:
            round_exprs.append(
                pl.col(price_col).cast(pl.Float64).round(1).alias(price_col)
            )
        # Include cumulative percentage columns when present
        if "cum_amount_pct" in export_table.columns:
            round_exprs.append(
                pl.col("cum_amount_pct")
                .cast(pl.Float64)
                .round(1)
                .alias("cum_amount_pct")
            )
        if "cum_share" in export_table.columns:
            round_exprs.append(
                pl.col("cum_share").cast(pl.Float64).round(1).alias("cum_share")
            )
        if round_exprs:
            export_table = export_table.with_columns(round_exprs)
        # Add friendly cumulative percent column
        pretty_cum_name = "Cumulative % on total amount"
        if (
            "cum_amount_pct" in export_table.columns
            and pretty_cum_name not in export_table.columns
        ):
            export_table = export_table.with_columns(
                pl.col("cum_amount_pct").alias(pretty_cum_name)
            )
        # Keep both cum_amount_pct and cum_share in the UI table; export pruning happens later
        columns_to_prune = [
            "cum_price_pct",
            "cum_share",
            "Segment_attr",
            "Merchant",
            "TopProduct",
            "ParetoThresholdPct",
            pretty_cum_name,
        ]
        # Build optional Audit — Sources sheet (aggregated one row per product)
        audit_sources_rows = session_state.get("_attr_sources_rows")
        audit_sources_agg: pl.DataFrame | None = None
        try:
            if isinstance(audit_sources_rows, list) and audit_sources_rows:
                src_df = pl.DataFrame(audit_sources_rows, orient="row")
                # Keep only relevant columns and aggregate into a single text field per product/group
                cols = [
                    c
                    for c in ["product", "category", "url", "title"]
                    if c in src_df.columns
                ]
                src_df = src_df.select(cols)
                # Build a display string per source as "title | url" (or url if title missing)
                disp = (
                    pl.when(pl.col("title").is_not_null() & (pl.col("title") != ""))
                    .then(pl.col("title") + pl.lit(" | ") + pl.col("url"))
                    .otherwise(pl.col("url"))
                    .alias("_disp")
                )
                src_df = src_df.with_columns(disp)
                group_keys = ["product"] + (
                    ["category"] if "category" in src_df.columns else []
                )
                audit_sources_agg = (
                    src_df.group_by(group_keys)
                    .agg(
                        pl.col("_disp")
                        .drop_nulls()
                        .unique()
                        .str.join("\n")
                        .alias("sources")
                    )
                    .sort(group_keys)
                )
        except Exception as e:
            logger.warning("Failed to prepare Audit — Sources sheet: %s", e)
            audit_sources_agg = None

        # Optionally include Audit — Notes sheet (LLM-provided attribute notes)
        audit_notes_df: pl.DataFrame | None = None
        try:
            from modules.add_attributes.notes_audit import (
                load_notes,
                get_notes_log_path,
            )

            try:
                product_col = mapping.get("product_column")
            except Exception:
                product_col = None
            notes = load_notes()
            if (
                isinstance(notes, pl.DataFrame)
                and notes.height > 0
                and isinstance(product_col, str)
                and product_col in export_table.columns
            ):
                # Filter to current products; keep simple schema
                prods = (
                    export_table.select(pl.col(product_col).cast(pl.Utf8).alias("_p"))
                    .get_column("_p")
                    .drop_nulls()
                )
                cols_keep = [
                    c
                    for c in [
                        "product",
                        "category",
                        "attribute",
                        "note",
                        "raw_value",
                        "timestamp",
                    ]
                    if c in notes.columns
                ]
                audit_notes_df = notes.filter(pl.col("product").is_in(prods)).select(
                    cols_keep
                )
                # De-duplicate identical notes for the same product/attribute
                dedup_keys = [
                    c
                    for c in ["product", "category", "attribute", "note", "raw_value"]
                    if c in cols_keep
                ]
                if dedup_keys:
                    audit_notes_df = audit_notes_df.unique(
                        subset=dedup_keys, keep="first"
                    )
                # Sort for stable, readable output
                sort_keys = [
                    c for c in ["product", "attribute", "timestamp"] if c in cols_keep
                ]
                if sort_keys:
                    audit_notes_df = audit_notes_df.sort(sort_keys)
                # Do not display a caption about notes log path
        except Exception as e:
            logger.warning("Failed to prepare Audit — Notes sheet: %s", e)
            audit_notes_df = None

        # Single or multi-sheet export depending on audit content
        overview_sheet = export_table
        payload_sheet: pl.DataFrame | None = None
        try:

            def _prune_columns(df: pl.DataFrame | None) -> pl.DataFrame | None:
                if not isinstance(df, pl.DataFrame):
                    return df
                drop_cols = [c for c in columns_to_prune if c in df.columns]
                if drop_cols:
                    return df.drop(drop_cols)
                return df

            pruned_overview = _prune_columns(export_table)
            if isinstance(pruned_overview, pl.DataFrame):
                overview_sheet = pruned_overview

            if isinstance(excel_payload, pl.DataFrame):
                payload_sheet = _prune_columns(excel_payload)
            else:
                payload_sheet = None

            sheets = {"Product overview": overview_sheet}
            if isinstance(audit_oov, pl.DataFrame) and audit_oov.height > 0:
                sheets["Audit — Not in taxonomy"] = audit_oov
            if (
                isinstance(audit_sources_agg, pl.DataFrame)
                and audit_sources_agg.height > 0
            ):
                sheets["Audit — Sources"] = audit_sources_agg
            if isinstance(audit_notes_df, pl.DataFrame) and audit_notes_df.height > 0:
                sheets["Audit — Notes"] = audit_notes_df
            if len(sheets) > 1:
                from src.io_utils import convert_book_excel

                excel_bytes = convert_book_excel(sheets)
            else:
                single_sheet = (
                    payload_sheet
                    if isinstance(payload_sheet, pl.DataFrame)
                    else overview_sheet
                )
                excel_bytes = convert_df_excel(single_sheet)
        except Exception as e:
            logger.warning(
                "Failed to export Excel workbook; falling back to single sheet: %s", e
            )
            fallback_sheet = (
                payload_sheet
                if isinstance(payload_sheet, pl.DataFrame)
                else overview_sheet
            )
            excel_bytes = convert_df_excel(fallback_sheet)
        ui.download_button(
            "Download product overview (Excel)",
            data=excel_bytes,
            file_name="product_overview.xlsx",
            mime=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            key="attr_overview_download_excel",
        )
        auto_join = session_state.get("attr_auto_join", True)
        join_btn = False
        if not auto_join:
            join_btn = ui.button(
                "Join attributes to main dataset",
                key="attr_join_btn_classify",
            )
        merged = False
        if auto_join or join_btn:
            scores = session_state.get("attr_scores")
            _, group_col = session_state.get("attr_group_choice", ("none", None))
            try:
                df = merge_attribute_results(
                    df,
                    mapping,
                    scores,
                    table,
                    group_col=group_col,
                )
                ui.info("Attributes merged into main dataset")
                merged = True
            except ValueError as exc:  # pragma: no cover - UI side effect
                ui.warning(str(exc))
        if merged:
            df_dl = df.collect() if isinstance(df, pl.LazyFrame) else df
            ui.download_button(
                "Download joined dataset",
                data=convert_df_parquet(df_dl),
                file_name="joined_dataset.parquet",
                mime="application/x-parquet",
                key="attr_joined_download_classification",
            )
        # Removed legacy guidance for deleted "attribute analysis" feature
    websites_df = session_state.get("attr_websites")
    if isinstance(websites_df, pl.DataFrame):
        if websites_df.height == 0:
            ui.info("No websites were resolved for the selected merchants/brands.")
        else:
            ui.success("Websites were resolved for the selected merchants/brands.")
    return df


def add_attributes(
    df,
    paramDict,
    col1Array,
    *,
    fetch_websites: bool = True,
):
    """Entry point for the Add Attributes tab.

    The dataframe **with** the original date column is stored under
    ``attr_merged_df_with_date``. A version without the date column is returned
    to the caller and saved in ``attr_merged_df``. If a previously merged
    dataframe with dates exists it is used as the starting point so reruns
    operate on the enriched data without losing date information during the UI
    steps.
    """
    df = session_state.get(
        "attr_merged_df_with_date", session_state.get("attr_merged_df", df)
    )

    # Make paramDict available to downstream steps that need context
    session_state["attr_param_dict"] = paramDict

    stored_source = _normalize_attr_source(session_state.get("attr_source"))
    if stored_source != session_state.get("attr_source"):
        session_state["attr_source"] = stored_source

    result = None
    with col1Array[0]:
        # First choose the attribute source
        options = ["PDP", SOURCE_DETERMINISTIC, SOURCE_DETERMINISTIC_LLM, SOURCE_EXCEL]
        default_source = session_state.get("attr_source", "PDP")
        if default_source not in options:
            default_source = "PDP"
        source = ui.radio(
            "Attribute source",
            options,
            index=options.index(default_source),
            key="attr_source",
        )
        if source == "PDP":
            ui.caption(
                "PDP pulls attributes from richer product detail content. (Not yet implemented; defaults to Product Text for now.)"
            )
        elif source == SOURCE_DETERMINISTIC:
            ui.caption(
                "Product Text derives attributes directly from the product title or description."
            )
        else:
            ui.caption("Web Search augments product text with targeted site lookups.")

        prev_source = session_state.get("attr_prev_source")
        if prev_source != source:
            if prev_source is not None:
                session_state["attr_cols_saved"] = False
                session_state.pop("attr_save_prompt_shown", None)
            session_state["attr_prev_source"] = source

        llm_enabled = _llm_enabled(source)
        deterministic_only = source == SOURCE_DETERMINISTIC
        pdp_placeholder = source == "PDP"

        # Show workflow choices only when LLM classification/scoring is available
        if llm_enabled:
            ui.radio(
                "Attribute workflow",
                [
                    "Attribute Classification",
                    "Attribute Scoring",
                ],
                index=0,
                key="attr_mode",
            )
        elif deterministic_only or pdp_placeholder:
            session_state["attr_mode"] = "Attribute Classification"

        llm_mode = "flex"
        service_tier = "flex"
        session_state["attr_llm_mode"] = llm_mode
        session_state["attr_service_tier"] = service_tier

        if source == SOURCE_EXCEL:
            uploaded = ui.file_uploader("Attribute Excel file", type=["xlsx", "xlsm"])
            if uploaded is not None:
                excel_bytes = uploaded.read()
                session_state["attr_excel_bytes"] = excel_bytes
                session_state["attr_excel_md5"] = hashlib.md5(excel_bytes).hexdigest()
                session_state.pop("attr_excel_merge_signature", None)
            session_state.pop("attr_group_choice", None)
            session_state["attr_cols_saved"] = False
            session_state.pop("attr_save_prompt_shown", None)
        else:
            session_state.pop("attr_excel_bytes", None)
            session_state.pop("attr_excel_md5", None)
            session_state.pop("attr_excel_merge_signature", None)

        if pdp_placeholder:
            ui.info(
                "PDP workflow is not implemented yet. The regular Product Text flow will run."
            )

        if llm_enabled:
            init_llm_wrapper("", SessionContext.from_state(session_state))
            llm_wrapper = session_state.get("llm_wrapper")
            ui.caption(
                "Web Search uses product text plus curated site lookups to classify attributes."
            )
        else:
            llm_wrapper = None

        # Prompt the user to select the relevant columns
        result = column_inference(df)

    with col1Array[1]:
        source_mode = _normalize_attr_source(session_state.get("attr_source"))
        if result and df is not None and session_state.get("attr_cols_saved"):
            if source_mode == SOURCE_EXCEL:
                if (
                    session_state.get("attr_excel_bytes")
                    and result.get("product_column")
                    and result.get("category_column")
                ):
                    merge_signature = (
                        result["product_column"],
                        result["category_column"],
                        session_state.get("attr_excel_md5"),
                    )
                    if (
                        session_state.get("attr_excel_merge_signature")
                        == merge_signature
                    ):
                        ui.info("Attributes already merged")
                    else:
                        try:
                            before_cols, _ = get_schema_and_column_names(df)
                            df, diagnostics = merge_attributes_from_excel(
                                df,
                                session_state["attr_excel_bytes"],
                                product_col=result["product_column"],
                                category_col=result["category_column"],
                                return_debug=True,
                                enforce_taxonomy=False,
                                exclude_numeric=True,
                            )
                            try:
                                logger.info(
                                    "merge-excel: resulting columns=%s",
                                    get_schema_and_column_names(df)[0],
                                )
                            except Exception:
                                pass
                            after_cols, _ = get_schema_and_column_names(df)
                        except Exception as e:  # pragma: no cover - defensive path
                            logging.exception(e)
                            ui.warning(str(e))
                        else:
                            new_cols = [c for c in after_cols if c not in before_cols]
                            merged_cols = diagnostics.get("merged_columns", [])
                            effective_cols = new_cols or merged_cols

                            if new_cols:
                                ui.info(
                                    "Dataframe joined: added attribute columns "
                                    + ", ".join(new_cols)
                                )
                                ui.caption(
                                    f"Before: {before_cols}\nAfter: {after_cols}"
                                )
                            elif merged_cols:
                                ui.info(
                                    "Dataframe joined: updated attribute columns "
                                    + ", ".join(merged_cols)
                                )
                                ui.caption(
                                    f"Before: {before_cols}\nAfter: {after_cols}"
                                )
                            else:
                                shared = diagnostics.get("shared_columns", [])
                                matched = diagnostics.get("matched_columns", [])
                                enforce_taxonomy = diagnostics.get(
                                    "enforce_taxonomy", True
                                )

                                messages: list[str] = []
                                if matched:
                                    messages.append(
                                        "Excel columns available to merge: "
                                        + ", ".join(matched)
                                    )
                                if shared:
                                    messages.append(
                                        "Shared columns between dataset and Excel: "
                                        + ", ".join(shared)
                                    )
                                numeric_skipped = diagnostics.get(
                                    "numeric_columns_skipped", []
                                )
                                if numeric_skipped:
                                    messages.append(
                                        "Skipped numeric columns: "
                                        + ", ".join(numeric_skipped)
                                    )
                                duplicate_products = diagnostics.get(
                                    "duplicate_products", []
                                )
                                if duplicate_products:
                                    messages.append(
                                        "Duplicate product keys in Excel; kept first entry for: "
                                        + ", ".join(duplicate_products)
                                    )
                                if diagnostics.get("row_count_changed"):
                                    messages.append(
                                        "Row count changed from "
                                        f"{diagnostics.get('original_row_count')} to {diagnostics.get('joined_row_count')}"
                                    )

                                if enforce_taxonomy:
                                    missing_by_cat = diagnostics.get(
                                        "categories_missing_columns", {}
                                    )
                                    categories_without_allowed = diagnostics.get(
                                        "categories_without_allowed", []
                                    )
                                    if missing_by_cat:
                                        detail = "; ".join(
                                            f"{cat}: expected {', '.join(values)}"
                                            for cat, values in missing_by_cat.items()
                                        )
                                        messages.append(
                                            "No attribute columns found for categories "
                                            + detail
                                        )
                                    if categories_without_allowed:
                                        messages.append(
                                            "Categories missing from taxonomy: "
                                            + ", ".join(categories_without_allowed)
                                        )

                                if not messages:
                                    messages.append(
                                        "Excel file did not contain additional attribute columns."
                                    )
                                ui.warning(
                                    "No matching attributes were merged.\n"
                                    + "\n".join(messages)
                                )

                            if effective_cols:
                                _record_excel_attribute_columns(df, effective_cols)

                            session_state["attr_excel_merge_signature"] = (
                                merge_signature
                            )
            else:
                lf = df.lazy() if isinstance(df, pl.DataFrame) else df
                choice, info = select_grouping_level(result, lf)
                session_state["attr_group_choice"] = (choice, info)
        elif result and not session_state.get("attr_cols_saved"):
            if not session_state.get("attr_save_prompt_shown"):
                ui.info("Save the column selections to continue.")
                session_state["attr_save_prompt_shown"] = True

    with col1Array[1]:
        source_mode = _normalize_attr_source(session_state.get("attr_source"))
        if source_mode != SOURCE_EXCEL:
            if (
                result
                and df is not None
                and session_state.get("attr_cols_saved")
                and "attr_group_choice" in session_state
            ):
                df = _render_pareto_step(result, df, paramDict, llm_wrapper)
            elif result and not session_state.get("attr_cols_saved"):
                if not session_state.get("attr_save_prompt_shown"):
                    ui.info("Save the column selections to continue.")
                    session_state["attr_save_prompt_shown"] = True

    with col1Array[2]:
        source_mode = _normalize_attr_source(session_state.get("attr_source"))
        if source_mode != SOURCE_EXCEL:
            if (
                result
                and df is not None
                and session_state.get("attr_cols_saved")
                and "attr_group_choice" in session_state
            ):
                lf = df.lazy() if isinstance(df, pl.DataFrame) else df
                mode = session_state.get("attr_mode")
                use_batch = False
                if not deterministic_only:
                    use_batch = session_state.get("attr_llm_mode", "flex") == "batch"
                service_tier = session_state.get(
                    "attr_service_tier", "flex" if not use_batch else "standard"
                )
                throttle = 1.0
                if mode != "Attribute Classification":
                    _render_attribute_discovery(
                        result,
                        lf,
                        llm_wrapper,
                        use_batch=use_batch,
                        throttle=throttle,
                        service_tier=service_tier,
                    )
        elif result and not session_state.get("attr_cols_saved"):
            if not session_state.get("attr_save_prompt_shown"):
                ui.info("Save the column selections to continue.")
                session_state["attr_save_prompt_shown"] = True

    with col1Array[3]:
        if (
            result
            and df is not None
            and session_state.get("attr_cols_saved")
            and "attr_group_choice" in session_state
        ):
            source_mode = _normalize_attr_source(session_state.get("attr_source"))
            if source_mode != SOURCE_EXCEL:
                mode = session_state.get("attr_mode")
                if mode == "Attribute Classification":
                    df = _render_attribute_classification(
                        result, df, fetch_websites=fetch_websites
                    )
                else:
                    df = _render_attribute_scoring(result, df)
        elif result and not session_state.get("attr_cols_saved"):
            if not session_state.get("attr_save_prompt_shown"):
                ui.info("Save the column selections to continue.")
                session_state["attr_save_prompt_shown"] = True

    # Preserve a copy with the date column for subsequent reruns/UI steps
    session_state["attr_merged_df_with_date"] = df

    naming = get_naming_params()
    date_col = naming["dateName"]
    columns, _ = get_schema_and_column_names(df)
    final_df = drop_columns(df, [date_col]) if date_col in columns else df

    # Use pre-fetched website information if available
    websites = session_state.get("attr_websites")
    if not isinstance(websites, pl.DataFrame):
        websites = pl.DataFrame()

    session_state["attr_merged_df"] = final_df

    return EnrichAttributesResult(final_df, websites)


def enrich_attributes(
    mapping_df: pl.DataFrame,
    category: str,
    query_llm: Callable[[str, list[str] | None], Dict[str, Any]],
    throttle: float = 0.0,
    *,
    merchant_col: str | None = None,
    brand_col: str | None = None,
    category_col: str | None = None,
    llm_wrapper=None,
    service_tier: str | None = None,
) -> EnrichAttributesResult:
    """Fill missing attribute columns using an LLM.

    Parameters
    ----------
    mapping_df:
        Product data with potential missing attributes.
    category:
        Product category to reference in the attribute taxonomy.
    query_llm:
        Callable used to fetch attribute values from an LLM.
    throttle:
        Optional delay in seconds after each successful LLM call.
    merchant_col, brand_col:
        Optional column names for merchant and brand lookup.
    category_col:
        Optional column name for product category website lookup.
    llm_wrapper:
        Wrapper used for website resolution when provided.
    service_tier:
        Service tier used for merchant and brand website lookups.

    Notes
    -----
    LLM requests that raise ``RuntimeError`` are retried with
    exponential backoff and random jitter to mitigate rate limits.
    """

    taxonomy = get_attribute_taxonomy()
    try:
        activity_config = get_attribute_activity_config()
    except (FileNotFoundError, ValueError) as exc:
        LOGGER.warning("Unable to load attribute activity configuration: %s", exc)
        activity_config = {}
    cat_node = next(
        (
            c
            for c in taxonomy.get("categories", [])
            if c.get("id", "").lower() == category.lower()
        ),
        None,
    )
    if not cat_node:
        raise ValueError(f"Category '{category}' not found in taxonomy")

    attr_keys: List[str] = [
        a.get("id") for a in cat_node.get("attributes", []) if a.get("id")
    ]

    active_attr_ids, category_configured = get_active_attribute_ids_for_category(
        category, activity_config
    )
    if category_configured:
        active_attr_keys = [key for key in attr_keys if key in active_attr_ids]
    else:
        active_attr_keys = list(attr_keys)

    for key in attr_keys:
        src_col = f"attr_source_{key}"
        if (
            f"{key}_raw" in get_schema_and_column_names(mapping_df)[0]
            and key not in get_schema_and_column_names(mapping_df)[0]
        ):
            mapping_df = mapping_df.rename({f"{key}_raw": key})
        if key not in get_schema_and_column_names(mapping_df)[0]:
            mapping_df = mapping_df.with_columns(pl.lit(None).alias(key))
        if src_col not in get_schema_and_column_names(mapping_df)[0]:
            mapping_df = mapping_df.with_columns(pl.lit(None).alias(src_col))

    records: List[Dict[str, Any]] = []
    website_rows: List[Dict[str, Any]] = []
    skipped = 0
    queried = 0

    cols, _ = get_schema_and_column_names(mapping_df)
    product_col = next(
        (c for c in cols if "product" in c.lower()),
        cols[0],
    )

    rate_limit_errors: tuple[type[Exception], ...] = (RuntimeError,)
    max_retries = 5

    websites: dict[str, str | None] = {}
    if llm_wrapper and (merchant_col or brand_col):
        names: set[str] = set()
        if merchant_col and merchant_col in cols:
            merchants = (
                mapping_df.get_column(merchant_col).drop_nulls().unique().to_list()
            )
            for val in merchants:
                norm = str(val).strip().lower()
                if norm:
                    names.add(BRAND_ALIASES.get(norm, norm))
        if brand_col and brand_col in cols:
            brand_series = mapping_df.get_column(brand_col).drop_nulls()
            brand_iter: Iterable[str]
            if brand_series.dtype == pl.List:
                brand_iter = (
                    b
                    for lst in brand_series.to_list()
                    for b in lst
                    if isinstance(b, str)
                )
            else:
                brand_iter = brand_series.to_list()
            for val in brand_iter:
                for part in str(val).split(","):
                    norm = part.strip().lower()
                    if norm:
                        names.add(BRAND_ALIASES.get(norm, norm))
        if names:
            websites = lookup_websites(
                llm_wrapper, names, aliases=BRAND_ALIASES, service_tier=service_tier
            )

    # Category websites are not used to scope search anymore.
    category_sites: dict[str, list[str]] = {}

    for row in mapping_df.to_dicts():
        prod_name = str(row.get(product_col, ""))

        # Category sites intentionally ignored.
        cat_sites = None

        brand_sites: list[str] = []
        if brand_col and row.get(brand_col) is not None:
            val = row.get(brand_col)
            raw_brands = (
                val
                if isinstance(val, list)
                else [part.strip() for part in str(val).split(",")]
            )
            for b in raw_brands:
                if isinstance(b, str):
                    norm = b.strip().lower()
                    if norm:
                        canon = BRAND_ALIASES.get(norm, norm)
                        site = websites.get(canon)
                        if site:
                            brand_sites.append(site)

        merchant_sites: list[str] = []
        if merchant_col and row.get(merchant_col) is not None:
            val = row.get(merchant_col)
            merchant_vals = val if isinstance(val, list) else [val]
            for merch in merchant_vals:
                if merch:
                    norm = str(merch).strip().lower()
                    if norm:
                        canon = BRAND_ALIASES.get(norm, norm)
                        site = websites.get(canon)
                        if site:
                            merchant_sites.append(site)

        domains: list[str] = []
        domains.extend(brand_sites)
        domains.extend(merchant_sites)
        # Skip category-level sites
        domains = list(dict.fromkeys(domains))

        website_rows.append({"product": prod_name, "websites": domains})

        missing_dims = [k for k in active_attr_keys if row.get(k) is None]
        if not is_valid_product_name(prod_name) or not missing_dims:
            skipped += 1
            records.append(row)
            continue

        dims_txt = " and ".join(missing_dims)

        prompt = f"Give me {dims_txt} for: '{prod_name}'"
        if domains:
            # Instruct the model to focus only on the provided domains.
            prompt += f" Search only on: {', '.join(domains)}."

        resp: Dict[str, Any] = {}
        for attempt in range(max_retries):
            try:
                resp = query_llm(prompt, domains or None) or {}
                if throttle > 0:
                    time.sleep(throttle)
                break
            except rate_limit_errors as err:
                wait = (2**attempt) + random.uniform(0, 1)
                LOGGER.warning(
                    "LLM rate limit encountered: %s. Retrying in %.2f seconds",
                    err,
                    wait,
                )
                time.sleep(wait)

        for dim in missing_dims:
            val = resp.get(dim)
            dim_l = str(dim).strip().lower()
            if dim_l in {"spf", "spf_value"}:
                parsed = None
                try:
                    s = str(val) if val is not None else ""
                    s_l = s.strip().lower()
                    if any(
                        p in s_l
                        for p in (
                            "no spf",
                            "no sunscreen",
                            "spf 0",
                            "no sun protection",
                            "non spf",
                        )
                    ):
                        parsed = None
                    else:
                        m = re.search(r"(\d{1,3})\s*\+?", s_l)
                        if m:
                            parsed = int(m.group(1))
                            if parsed <= 0 or parsed > 150:
                                parsed = None
                except Exception:
                    parsed = None
                if parsed is not None:
                    row[dim] = str(parsed)
                    row[f"attr_source_{dim}"] = "llm"
                else:
                    row[dim] = "N/A"
                    row[f"attr_source_{dim}"] = "llm"
                continue
            if dim_l == "sun_filter_type":
                if val is None:
                    row[dim] = "N/A"
                else:
                    s = str(val).strip().lower()
                    if ("mineral" in s and "chemical" in s) or s.replace(
                        "-", " "
                    ).strip() in {
                        "mineral chemical",
                        "mineral-chemical",
                        "hybrid",
                        "combo filters",
                        "mixed filters",
                    }:
                        row[dim] = "hybrid"
                    elif s in {
                        "mineral",
                        "physical",
                        "titanium dioxide",
                        "zinc oxide",
                        "inorganic filters",
                        "mineral sunscreen",
                        "non-chemical",
                        "zinc/titanium",
                    }:
                        row[dim] = "mineral"
                    elif s in {
                        "chemical",
                        "organic filters",
                        "absorber filters",
                        "uv chemical filters",
                        "avobenzone/oxybenzone",
                        "avobenzone",
                        "octinoxate",
                        "octocrylene",
                    }:
                        row[dim] = "chemical"
                    elif s in {
                        "none",
                        "no spf",
                        "no sunscreen",
                        "spf 0",
                        "no sun protection",
                        "no spf listed",
                        "non spf",
                    }:
                        row[dim] = "none"
                    else:
                        row[dim] = str(val).strip()
                row[f"attr_source_{dim}"] = "llm"
                continue
            if val is not None:
                row[dim] = str(val).strip()
                row[f"attr_source_{dim}"] = "llm"
            else:
                row[dim] = "N/A"
        records.append(row)
        queried += 1

    ui.caption(f"Skipped {skipped:,} rows, queried LLM for {queried:,} rows")
    for row in records:
        for key in attr_keys:
            if key in row and row[key] is not None:
                row[key] = str(row[key])
    schema_overrides = {key: pl.String for key in attr_keys}
    data_df = pl.DataFrame(records, schema_overrides=schema_overrides)
    for key in attr_keys:
        if key in data_df.columns:
            data_df = data_df.with_columns(
                pl.when(pl.col(key).is_null())
                .then(pl.lit("N/A"))
                .otherwise(pl.col(key))
                .alias(key)
            )
    websites_df = pl.DataFrame(website_rows)
    return EnrichAttributesResult(data=data_df, websites=websites_df)


if __name__ == "__main__":

    def _fake_llm(prompt: str, _domains: list[str] | None = None) -> Dict[str, str]:
        resp: Dict[str, str] = {}
        if "finish" in prompt:
            resp["finish"] = "matte"
        if "form" in prompt:
            resp["form"] = "bullet"
        return resp

    data = pl.DataFrame(
        {
            "Product": ["Has finish", "Has form", "None"],
            "finish": ["matte", None, None],
            "form": [None, "bullet", None],
            "attr_source_finish": ["rule", None, None],
            "attr_source_form": [None, "rule", None],
        }
    )

    result = enrich_attributes(data, "lipstick", _fake_llm, throttle=0)
    logging.info(result)
