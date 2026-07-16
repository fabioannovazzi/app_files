from __future__ import annotations

import json
import logging
import re
import time
from difflib import SequenceMatcher
from stat import S_IRUSR, S_IWUSR
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, MutableMapping, Tuple

import polars as pl

import modules.add_attributes.generate_taxonomy as _gen_tax
from modules.add_attributes.alias_index import load_alias_index
from modules.add_attributes.attribute_discovery import deduplicate_attributes
from modules.add_attributes.normalization import normalize_product_key
from modules.add_attributes.attribute_taxonomy import (
    TAXONOMY_PATH,
    get_attribute_activity,
    get_attribute_taxonomy,
    get_runtime_attribute_taxonomy,
    queue_taxonomy_review,
    save_attribute_taxonomy,
)
from modules.add_attributes.attribute_watcher import (
    detect_new_terms,
    suggest_new_nodes,
    update_taxonomy_with_suggestions,
)
from modules.add_attributes.generate_taxonomy import generate_category_taxonomy
from modules.add_attributes.taxonomy_patch import (
    normalize_all_categories,
    normalize_category,
)
from modules.add_attributes.synonym_enrichment import enrich_category_if_stale
from modules.add_attributes.grounding import ground_branch_with_web
from modules.add_attributes.tool_utils import build_web_search_request
from modules.add_attributes.validators import is_valid_product_name
from modules.llm.model_router import query_llm_return_json, should_use_flex
from modules.utilities.cache import get_cache_dir
from modules.utilities.config import get_naming_params, get_run_params
from modules.utilities.utils import get_schema_and_column_names
from modules.utilities.ui_notifier import ui
from modules.utilities.session_context import session_state
from src.file_lock import FileLock
from src.product_attribute_cache import load_cache, save_cache

logger = logging.getLogger(__name__)

__all__ = [
    "discover_objective_attributes_for_category",
    "classify_product_attributes",
    "classify_attributes_for_products",
]


NOT_IN_TAXONOMY_VALUE = "not in taxonomy"
NOT_IN_TAXONOMY_FLAG_SUFFIX = "not_in_taxonomy"

_CACHE_PLACEHOLDER_VALUES = {
    "",
    "n/a",
    "n/a (not stated)",
    "unknown",
    NOT_IN_TAXONOMY_VALUE,
}
_CACHE_PLACEHOLDER_PREFIXES = (
    "n/a",
    "unknown",
    NOT_IN_TAXONOMY_VALUE,
)

# Some leaf labels are too generic to be reliable deterministic aliases in
# long PDP descriptions (for example ingredient decks containing "seed oil").
# Keep their explicit multi-word synonyms, but skip the bare label token.
_GENERIC_DETERMINISTIC_LABEL_ALIASES = {"oil"}

# Forward-only normalization for values that became more explicit in the
# taxonomy. This is not for historical compatibility; it lets the current
# classifier continue emitting concise raw values while the final stored value
# remains unambiguous.
_LEGACY_VALUE_NORMALIZATION: dict[tuple[str, str, str], str] = {
    ("lipstick", "finish", "cream"): "cream finish",
    ("lipstick", "finish", "sheer"): "sheer finish",
    ("lipstick", "coverage", "buildable"): "buildable coverage",
    ("lipstick", "coverage", "full"): "full coverage",
    ("lipstick", "coverage", "medium"): "medium coverage",
    ("lipstick", "coverage", "sheer"): "sheer coverage",
    ("lip_balms", "finish", "sheer"): "sheer finish",
    ("lip_balms", "coverage", "sheer"): "sheer coverage",
    ("lip_gloss", "packaging type", "rollerball"): "rollerball packaging",
    ("lip_gloss", "applicator type", "rollerball"): "rollerball applicator",
    ("lip_oil", "color payoff", "clear"): "clear color payoff",
    ("lip_oil", "shade family", "clear"): "clear shade",
    ("face_primer", "form", "oil"): "oil formula",
    ("lip_treatments", "form", "oil"): "oil formula",
    ("bronzer", "pigment level", "buildable"): "buildable pigment",
    ("bronzer", "benefits", "buildable"): "layerable benefit",
    ("bronzer", "pigment level", "light"): "light pigment",
    ("bronzer", "shade depth", "light"): "light shade",
    ("bronzer", "pigment level", "medium"): "medium pigment",
    ("bronzer", "shade depth", "medium"): "medium shade",
    ("concealer", "coverage", "light"): "light coverage",
    ("concealer", "tone depth", "light"): "light tone",
    ("concealer", "coverage", "medium"): "medium coverage",
    ("concealer", "tone depth", "medium"): "medium tone",
    ("lip_stain", "coverage", "buildable"): "buildable coverage",
    ("lip_stain", "benefits", "buildable"): "layerable benefit",
    ("highlighter", "undertone", "universal"): "universal undertone",
    ("highlighter", "shade depth", "universal"): "universal shade depth",
    ("eyeshadow", "refillable", "yes"): "refillable",
    ("eyeshadow", "refillable", "no"): "not refillable",
    ("eyeshadow", "mirror included", "yes"): "mirror included",
    ("eyeshadow", "mirror included", "no"): "mirror not included",
    ("foundation", "coverage buildable", "yes"): "buildable coverage",
    ("foundation", "coverage buildable", "no"): "non-buildable coverage",
    ("foundation", "sensitive skin compatible", "yes"): "sensitive-skin friendly",
    ("foundation", "sensitive skin compatible", "no"): "not sensitive-skin friendly",
    ("foundation", "broad spectrum", "yes"): "broad spectrum",
    ("foundation", "broad spectrum", "no"): "not broad spectrum",
    ("palette", "mirror included", "yes"): "mirror included",
    ("palette", "mirror included", "no"): "mirror not included",
    ("palette", "applicator included", "yes"): "applicator included",
    ("palette", "applicator included", "no"): "applicator not included",
}


@dataclass
class _RetryRequest:
    """Container for queued second-pass classification attempts."""

    product_key: str
    product_name: str
    product_text: str
    deterministic_text: str
    category_value: Any
    retry_targets: List[str]
    retry_allowed: Dict[str, List[str]] | None
    nodes_by_label: Dict[str, List[dict]] | None
    alias_attr_map: Dict[str, Dict[str, str]] | None
    deterministic_blocked_aliases: Dict[str, set[str]] | None
    brand_cache: Dict[str, Dict[str, str]]
    cached_vals: Dict[str, str]
    raw_capture: Dict[str, str]
    notes_capture: Dict[str, str]
    order_index: int


@dataclass
class _ProductProcessingContext:
    """Persist product-level context until after fallback retries complete."""

    product_name: str
    product_key: str
    category_value: Any
    attrs: List[str]
    attr_meta_by_label: Dict[str, dict]
    hier_lookup: Dict[str, Dict[str, List[str]]]
    allowed_values: Dict[str, List[str]]
    nodes_by_label: Dict[str, List[dict]]
    brand_cache: Dict[str, Dict[str, str]]
    cached_vals: Dict[str, str]
    raw_capture: Dict[str, str]
    notes_capture: Dict[str, str]
    product_text: str
    deterministic_text: str
    order_index: int


@dataclass
class _PendingClassificationRequest:
    """Container for deferred first-pass classification calls."""

    product_name: str
    product_key: str
    product_text: str
    category_value: Any
    attrs: List[str]
    attr_meta_by_label: Dict[str, dict]
    hier_lookup: Dict[str, Dict[str, List[str]]]
    allowed_values: Dict[str, List[str]]
    nodes_by_label: Dict[str, List[dict]]
    brand_cache: Dict[str, Dict[str, str]]
    cached_vals: Dict[str, str]
    raw_capture: Dict[str, str]
    notes_capture: Dict[str, str]
    missing: List[str]
    allowed_subset: Dict[str, List[str]] | None
    attr_alias_map: Dict[str, Dict[str, str]] | None
    deterministic_blocked_aliases: Dict[str, set[str]] | None
    domain_list: List[str] | None
    deterministic_text: str
    order_index: int


def _normalize_legacy_allowed_value(
    category_value: Any,
    attribute_label: str,
    value: Any,
) -> str:
    normalized = _normalize_for_allowed(value)
    if not normalized:
        return normalized
    category_key = str(category_value).strip().lower()
    attribute_key = str(attribute_label).strip().lower()
    return _LEGACY_VALUE_NORMALIZATION.get(
        (category_key, attribute_key, normalized),
        normalized,
    )


ClassificationBucketKey = Tuple[
    Tuple[str, ...],
    Tuple[Tuple[str, Tuple[str, ...]], ...],
]


def _build_bucket_key(
    missing: List[str], allowed_subset: Dict[str, List[str]] | None
) -> ClassificationBucketKey:
    """Return a stable key that groups identical enum prompts together."""

    missing_key = tuple(missing)
    if not allowed_subset:
        return missing_key, ()
    enum_key = tuple(
        (attr, tuple(allowed_subset[attr]))
        for attr in missing
        if attr in allowed_subset
    )
    return missing_key, enum_key


try:  # optional dependency for novelty tracking; tests may monkeypatch
    from modules.add_attributes.novelty import append_novelty as _append_novelty

    append_novelty = _append_novelty
except Exception:
    append_novelty = None  # type: ignore[assignment]


def _strip_annotations_for_unknowns(text: str) -> str:
    """Return ``text`` stripped of audit/citation noise for unknown detection.

    - Removes inline markdown links like ``[label](url)``
    - Removes bare URLs
    - Truncates at the first parenthesis/dash which typically introduces notes
      like "(not stated)" or citations, keeping the leading token only.
    """
    try:
        t = str(text)
    except Exception:
        return ""
    # Lowercase and trim early for consistency
    t = t.strip().lower()
    if not t:
        return t
    # Strip markdown-style links and raw URLs
    t = re.sub(r"\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"https?://\S+", "", t)
    # Keep only the prefix before common annotation separators
    parts = re.split(r"\s*(?:\(|—|\-|–)\s*", t, maxsplit=1)
    t = parts[0].strip() if parts else t
    # Collapse internal whitespace
    t = re.sub(r"\s+", " ", t)
    return t


def _is_placeholder_cache_value(value: object | None) -> bool:
    """Return True when a cached value represents a placeholder sentinel."""

    if value is None:
        return True
    try:
        normalized = str(value).strip().lower()
    except Exception:
        return True
    if normalized in _CACHE_PLACEHOLDER_VALUES:
        return True
    return any(normalized.startswith(prefix) for prefix in _CACHE_PLACEHOLDER_PREFIXES)


def _is_trivial_placeholder(text: str) -> bool:
    """Return True only if ``text`` is a bare placeholder (no useful detail).

    This check is intentionally conservative: it does NOT strip content in
    parentheses or after dashes because the LLM may emit concrete candidates
    there (e.g., "Other (Maple)"). It only removes markdown links and raw URLs
    and then matches the full, trimmed lowercase string to known placeholders.
    """
    try:
        t = str(text)
    except Exception:
        return True
    # Remove markdown links and raw URLs only; keep the rest intact
    t = re.sub(r"\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"https?://\S+", "", t)
    t = t.strip().lower()
    if not t:
        return True
    if t in {
        "n/a",
        "n/a (not stated)",
        "unknown",
        "other",
        "other (not in list)",
        NOT_IN_TAXONOMY_VALUE,
    }:
        return True
    # Treat prefix forms of these placeholders as trivial too
    if t.startswith(NOT_IN_TAXONOMY_VALUE):
        return True
    if t.startswith("n/a"):
        return True
    if t.startswith("unknown"):
        return True
    # Do NOT treat "other (..)" as trivial; it may contain a real candidate
    return False


def _normalize_for_allowed(text: str) -> str:
    """Normalize a candidate value for matching against allowed leaves.

    - Lowercase and trim whitespace
    - Remove markdown links and raw URLs
    - Remove a trailing empty parenthesis block (e.g., "()") left after link stripping
    - Normalize hyphen-like punctuation and underscores to spaces
    - Collapse internal whitespace
    """
    t = str(text).strip().lower()
    t = re.sub(r"\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\(\s*\)$", "", t)
    # Normalize hyphen-like characters and underscores to spaces
    t = re.sub(r"[-_\u2010-\u2015]+", " ", t)
    # Remove trailing punctuation and whitespace (e.g., trailing '.' or ';')
    t = re.sub(r"[\s\.,;:]+$", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _pick_first_allowed_from_candidates(
    candidates: Iterable[str],
    allowed: List[str],
    *,
    alias_map: Dict[str, str] | None = None,
) -> str | None:
    """Pick the first allowed value (taxonomy order) supported by candidates."""
    if not candidates or not allowed:
        return None
    normalized: List[str] = []
    for cand in candidates:
        if cand is None:
            continue
        cand_text = str(cand).strip().lower()
        if not cand_text:
            continue
        cand_norm = _normalize_for_allowed(cand_text)
        if alias_map:
            token = _norm_token(cand_norm)
            mapped = alias_map.get(token) or alias_map.get(_norm_token(cand_text))
            if mapped:
                cand_norm = mapped
        normalized.append(cand_norm)
    if not normalized:
        return None
    normalized_set = set(normalized)
    for val in allowed:
        if val in normalized_set:
            return val
    return None


def _clean_queue_value(text: str) -> str:
    """Return ``text`` with evidence and trailing punctuation removed for queuing.

    This is deliberately narrower than `_normalize_for_allowed`:
    - Removes inline markdown links and bare URLs
    - Collapses internal whitespace
    - Strips only trailing punctuation/whitespace
    - Preserves original casing and hyphens to avoid changing semantics
    """
    try:
        t = str(text)
    except Exception:
        return ""
    # Drop markdown links and raw URLs
    t = re.sub(r"\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"https?://\S+", "", t)
    # Remove a trailing empty parenthesis left after link stripping
    t = re.sub(r"\(\s*\)$", "", t)
    # Collapse internal whitespace and strip trailing punctuation/space
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[\s\.,;:]+$", "", t)
    return t.strip()


def _parse_spf_value(text: str) -> int | None:
    """Extract a plausible SPF integer from ``text``.

    - Interprets "SPF 50+" as 50
    - Returns None for 0 or out-of-range values
    - Requires explicit SPF context to avoid unrelated numbers like "4-in-1"
    """
    try:
        s = str(text).lower()
    except Exception:
        return None
    # Common explicit no-SPF phrases
    if any(
        token in s for token in ("no spf", "no sunscreen", "spf 0", "no sun protection")
    ):
        return None
    import re

    bare_match = re.fullmatch(r"\s*(\d{1,3})\s*\+?\s*", s)
    if bare_match:
        val = int(bare_match.group(1))
        if 0 < val <= 150:
            return val

    patterns = (
        r"\bspf\s*[:#-]?\s*(\d{1,3})\s*\+?",
        r"\b(\d{1,3})\s*\+?\s*spf\b",
    )
    for pattern in patterns:
        match = re.search(pattern, s)
        if not match:
            continue
        try:
            val = int(match.group(1))
        except Exception:
            continue
        if 0 < val <= 150:
            return val
    return None


# Persist classification cache as a file within its own directory.
CLASSIFICATION_PARQUET = (
    get_cache_dir("attribute_classifications") / "attribute_classifications.parquet"
)


def _leaf_labels(nodes: List[dict]) -> List[str]:
    """Return all leaf node labels from a taxonomy tree in lowercase."""
    labels: List[str] = []
    for node in nodes or []:
        children = node.get("children")
        if children:
            labels.extend(_leaf_labels(children))
        else:
            label = node.get("label")
            if label:
                labels.append(str(label).lower())
    return labels


def _leaf_paths(
    nodes: List[dict],
    *,
    _path: List[str] | None = None,
    _result: MutableMapping[str, List[str]] | None = None,
) -> Dict[str, List[str]]:
    """Return a mapping of leaf labels to their full path."""
    if _result is None:
        _result = {}
    for node in nodes or []:
        label = node.get("label")
        if not label:
            continue
        label = str(label).lower()
        new_path = (_path or []) + [label]
        children = node.get("children")
        if children:
            _leaf_paths(children, _path=new_path, _result=_result)
        else:
            _result[label] = new_path
    return dict(_result)


def _leaf_synonym_map(nodes: List[dict]) -> Dict[str, str]:
    """Return mapping from synonyms and labels to leaf labels.

    Includes both raw lowercase tokens and a normalized variant (hyphens/underscores
    collapsed to spaces) so lookups with `_norm_token` succeed.
    Parents are ignored; only leaves contribute. Synonyms collide to the first-seen leaf.
    """
    mapping: Dict[str, str] = {}
    for node in nodes or []:
        children = node.get("children")
        if children:
            for ch in children:
                lab = str(ch.get("label", "")).strip().lower()
                if lab:
                    lab_token = _norm_token(lab)
                    if lab_token not in _GENERIC_DETERMINISTIC_LABEL_ALIASES:
                        mapping.setdefault(lab, lab)
                        mapping.setdefault(lab_token, lab)
                for s in ch.get("synonyms", []) or []:
                    sval = str(s).strip().lower()
                    if sval:
                        mapping.setdefault(sval, lab)
                        mapping.setdefault(_norm_token(sval), lab)
        else:
            lab = str(node.get("label", "")).strip().lower()
            if lab:
                lab_token = _norm_token(lab)
                if lab_token not in _GENERIC_DETERMINISTIC_LABEL_ALIASES:
                    mapping.setdefault(lab, lab)
                    mapping.setdefault(lab_token, lab)
            for s in node.get("synonyms", []) or []:
                sval = str(s).strip().lower()
                if sval:
                    mapping.setdefault(sval, lab)
                    mapping.setdefault(_norm_token(sval), lab)
    return mapping


def _leaf_synonyms_lookup(nodes: List[dict]) -> Dict[str, List[str]]:
    """Return mapping from leaf label to its synonym list (lowercased).

    Parents are ignored; only leaves contribute. Synonyms are returned in
    their normalized lowercase form to keep prompts compact and consistent.
    """
    out: Dict[str, List[str]] = {}
    for node in nodes or []:
        children = node.get("children")
        if children:
            for ch in children:
                lab = str(ch.get("label", "")).strip().lower()
                if not lab:
                    continue
                syns = [
                    str(s).strip().lower()
                    for s in (ch.get("synonyms") or [])
                    if str(s).strip()
                ]
                out[lab] = syns
        else:
            lab = str(node.get("label", "")).strip().lower()
            if not lab:
                continue
            syns = [
                str(s).strip().lower()
                for s in (node.get("synonyms") or [])
                if str(s).strip()
            ]
            out[lab] = syns
    return out


def _normalize_alias_source(text: str) -> str:
    """Lowercase ``text`` and collapse punctuation to single-space boundaries."""

    text_lc = str(text).lower()

    replaced = [ch if ch.isalnum() else " " for ch in text_lc]
    collapsed = re.sub(r"\s+", " ", "".join(replaced)).strip()

    return collapsed


_NEGATION_TOKENS = {"non", "anti", "no", "not", "without", "free"}


def _build_category_deterministic_blocked_aliases(
    nodes_by_label: Dict[str, List[dict]],
) -> Dict[str, set[str]]:
    """Return alias tokens that are ambiguous across attributes in one category.

    Deterministic matching should not fire on tokens that belong to multiple
    attributes inside the same category, because those are structurally
    ambiguous and should be resolved by explicit rules or the LLM stage.
    """

    token_owners: Dict[str, set[str]] = {}
    per_attr_tokens: Dict[str, set[str]] = {}
    for attr_label, nodes in nodes_by_label.items():
        tokens = {token for token in _leaf_synonym_map(nodes) if token}
        per_attr_tokens[attr_label] = tokens
        for token in tokens:
            token_owners.setdefault(token, set()).add(attr_label)

    return {
        attr_label: {
            token for token in tokens if len(token_owners.get(token, set())) > 1
        }
        for attr_label, tokens in per_attr_tokens.items()
    }


def _has_negation_neighbor(text: str, start: int, end: int) -> bool:
    """Return True when the match in ``text`` is adjacent to a negation token."""

    prefix = text[:start].rstrip()
    if prefix:
        prev_token = prefix.split(" ")[-1]
        if prev_token in _NEGATION_TOKENS:
            return True

    suffix = text[end:].lstrip()
    if suffix:
        next_token = suffix.split(" ", 1)[0]
        if next_token in _NEGATION_TOKENS:
            return True

    return False


def _deterministic_guess(product_name: str, alias_map: Dict[str, str]) -> str | None:
    """Conservatively find a unique alias match in product_name using word bounds.

    Returns the canonical leaf label if exactly one alias matches; otherwise None.
    """
    normalized_text = _normalize_alias_source(product_name)
    if not normalized_text:
        return None
    raw_text = str(product_name).lower()
    leaf_norm_cache: Dict[str, str] = {}
    leaf_scores: Dict[str, int] = {}
    canonical_counts: Dict[str, int] = {}
    for alias, leaf in alias_map.items():
        alias_norm = _normalize_alias_source(alias)
        if not alias_norm or len(alias_norm) < 3:
            continue
        pattern = re.compile(rf"(?<!\\w){re.escape(alias_norm)}(?!\\w)")
        matches = list(pattern.finditer(normalized_text))
        if not matches:
            continue
        if " " not in alias_norm:
            guard = rf"(?<![0-9a-z-]){re.escape(alias_norm)}(?![0-9a-z-])"
            if not re.search(guard, raw_text):
                continue
        for match in matches:
            if not _has_negation_neighbor(normalized_text, match.start(), match.end()):
                leaf_norm = leaf_norm_cache.get(leaf)
                if leaf_norm is None:
                    leaf_norm = _normalize_alias_source(leaf)
                    leaf_norm_cache[leaf] = leaf_norm
                if alias_norm == leaf_norm:
                    canonical_counts[leaf] = canonical_counts.get(leaf, 0) + 1
                    leaf_scores[leaf] = leaf_scores.get(leaf, 0) + 2
                else:
                    leaf_scores[leaf] = leaf_scores.get(leaf, 0) + 1
                break
    if canonical_counts:
        max_count = max(canonical_counts.values())
        candidates = [
            leaf for leaf, count in canonical_counts.items() if count == max_count
        ]
        if len(candidates) == 1:
            return candidates[0]
        best_score = max(leaf_scores.get(leaf, 0) for leaf in candidates)
        finalists = [
            leaf for leaf in candidates if leaf_scores.get(leaf, 0) == best_score
        ]
        return finalists[0] if len(finalists) == 1 else None
    if not leaf_scores:
        return None
    max_score = max(leaf_scores.values())
    leaves = [leaf for leaf, score in leaf_scores.items() if score == max_score]
    return leaves[0] if len(leaves) == 1 else None


def _deterministic_multi_hits(
    product_name: str, alias_map: Dict[str, str]
) -> List[str]:
    """Return a list of canonical leaf labels that match deterministically.

    Multiple aliases may match; returns unique, order-preserving leaf labels.
    """
    normalized_text = _normalize_alias_source(product_name)
    if not normalized_text:
        return []
    raw_text = str(product_name).lower()
    hits: List[str] = []
    for alias, leaf in alias_map.items():
        alias_norm = _normalize_alias_source(alias)
        if not alias_norm or len(alias_norm) < 3:
            continue
        pattern = re.compile(rf"(?<!\\w){re.escape(alias_norm)}(?!\\w)")
        matches = list(pattern.finditer(normalized_text))
        if not matches:
            continue
        if " " not in alias_norm:
            guard = rf"(?<![0-9a-z-]){re.escape(alias_norm)}(?![0-9a-z-])"
            if not re.search(guard, raw_text):
                continue
        for match in matches:
            if not _has_negation_neighbor(normalized_text, match.start(), match.end()):
                hits.append(leaf)
                break
    # dedupe preserving order
    seen = set()
    out: List[str] = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _leaf_id_label_pairs(nodes: List[dict]) -> List[tuple[str, str]]:
    """Return (leaf_id, leaf_label) pairs for a node list (handles children)."""
    pairs: List[tuple[str, str]] = []
    for n in nodes or []:
        children = n.get("children")
        if children:
            for ch in children:
                lid = (
                    str(ch.get("id", "")).strip().lower()
                    or str(ch.get("label", "")).strip().lower()
                )
                lab = str(ch.get("label", "")).strip().lower()
                if lab:
                    pairs.append((lid, lab))
        else:
            lid = (
                str(n.get("id", "")).strip().lower()
                or str(n.get("label", "")).strip().lower()
            )
            lab = str(n.get("label", "")).strip().lower()
            if lab:
                pairs.append((lid, lab))
    return pairs


def _norm_token(s: str) -> str:
    """Lowercase token normalization for matching.

    - Lowercase
    - Map unicode minus (U+2212) to '-'; hyphens/underscores to spaces
    - Map multiplication sign (×) to 'x'
    - Collapse whitespace
    - Strip wrapping quotes/parentheses if they wrap entire token
    - Trim trailing punctuation .,;:
    """
    t = str(s).lower()
    # Normalize special symbols first
    t = t.replace("\u2212", "-")  # minus sign
    t = t.replace("\u00d7", "x")  # multiplication sign
    # Normalize ASCII hyphen, underscores, and common Unicode hyphens/dashes
    t = re.sub(r"[-_\u2010-\u2015]+", " ", t)
    # Collapse whitespace
    t = " ".join(t.split())
    # Strip wrapping quotes or parentheses when they wrap entire token
    if (t.startswith("(") and t.endswith(")")) or (
        t.startswith("[") and t.endswith("]")
    ):
        inner = t[1:-1].strip()
        if inner:
            t = inner
    if (t.startswith("'") and t.endswith("'")) or (
        t.startswith('"') and t.endswith('"')
    ):
        inner = t[1:-1].strip()
        if inner:
            t = inner
    # Trim trailing light punctuation
    t = re.sub(r"[\.,;:]+$", "", t).strip()
    return t


def _normalize_attr_name(text: str) -> str:
    """Return a simplified key for fuzzy attribute matching."""
    return re.sub(r"\s+", " ", text.replace("_", " ").lower()).strip()


def _map_llm_keys(
    attributes: Iterable[str],
    llm_data: Dict[str, str],
    *,
    threshold: float = 0.6,
) -> Dict[str, str]:
    """Map LLM response keys to requested attributes using fuzzy matching.

    Attribute names and LLM keys are normalized in a case-insensitive way with
    underscores treated as spaces. When an exact match is not found,
    :class:`difflib.SequenceMatcher` selects the closest key above ``threshold``
    so that small wording variations do not drop valid results.
    """
    req_norm = {_normalize_attr_name(a): a for a in attributes}
    result: Dict[str, str] = {}
    for key, val in llm_data.items():
        if not isinstance(val, (str, int, float)):
            continue
        norm_key = _normalize_attr_name(key)
        target = req_norm.get(norm_key)
        if target is None:
            best_ratio = threshold
            best_match = None
            for rn, attr in req_norm.items():
                ratio = SequenceMatcher(None, norm_key, rn).ratio()
                if ratio >= best_ratio:
                    best_ratio = ratio
                    best_match = attr
            target = best_match
        if target:
            result[target] = str(val)
    return result


def discover_objective_attributes_for_category(
    llm_wrapper,
    category: str,
    existing_columns: Iterable[str],
    *,
    use_batch: bool = False,
    throttle: float = 1.0,
    service_tier: str = "flex",
    context: Dict[str, str] | None = None,
) -> List[str]:
    """Suggest factual attributes for ``category`` using an LLM.

    The taxonomy from :func:`get_attribute_taxonomy` is consulted firui. If the
    ``category`` exists there, its attributes are deduplicated against
    ``existing_columns`` and returned directly, avoiding an LLM call.

    Parameters
    ----------
    llm_wrapper:
        Wrapper managing the LLM invocation.
    category:
        Category name to query.
    existing_columns:
        Columns already present to avoid duplicates.
    use_batch:
        Whether to call the batch endpoint.
    throttle:
        Delay between non-batch requests.
    """
    taxonomy = get_attribute_taxonomy()
    cat_id = str(category).strip().lower()
    categories = taxonomy.get("categories", [])
    category_node = next(
        (c for c in categories if str(c.get("id", "")).strip().lower() == cat_id),
        None,
    )
    if category_node is not None:
        labels = []
        for a in category_node.get("attributes", []):
            label = a.get("label")
            if not label:
                continue
            labels.append(str(label).lower())
        # If the branch exists and has attributes, return them; otherwise fall
        # through to generation to populate the empty branch.
        if labels:
            return deduplicate_attributes(labels, list(existing_columns), None)

    # Use new generator when category is missing
    context = context or {}
    industry = context.get("industry")
    company = context.get("company")
    industry_desc = context.get("industry_description")

    try:
        naming = get_naming_params()
        query_step = naming["taxonomyGenerationQuery"]
        system_prompt = "You are an expert in product taxonomies. Return JSON only."

        if llm_wrapper is None:
            from modules.llm.batch_runner import run_step_json

            def _legacy_call(prompt: str) -> dict:
                responses = run_step_json(
                    llm_wrapper,
                    query_step,
                    system_prompt,
                    prompt,
                    reasoning_effort="high",
                )
                first = responses[0] if responses else {}
                return first if isinstance(first, dict) else {}

            branch = generate_category_taxonomy(
                category_name=category,
                existing_data=taxonomy,
                example_count=2,
                perform_review=True,
                industry=industry,
                industry_description=industry_desc,
                company=company,
                llm_call=_legacy_call,
            )
        else:
            branch = generate_category_taxonomy(
                llm_wrapper,
                category_name=category,
                existing_data=taxonomy,
                example_count=2,
                perform_review=True,
                industry=industry,
                industry_description=industry_desc,
                company=company,
                llm_call=lambda prompt: query_llm_return_json(
                    llm_wrapper,
                    query_step,
                    system_prompt,
                    prompt,
                    reasoning_effort="high",
                ),
            )
        # Optional: perform conservative web grounding pass (disabled by default)
        # To enable, set service_tier or gate via config in future.
        try:
            branch = ground_branch_with_web(
                llm_wrapper, branch, category, service_tier=None
            )
        except Exception:
            logger.exception("Web grounding failed for category '%s'", category)
    except TypeError as exc:
        # Backward-compat: older signature expects an llm_call callable instead of llm_wrapper
        if "llm_call" in str(exc):
            try:
                naming = get_naming_params()
                query_step = naming["taxonomyGenerationQuery"]

                def _adapter(prompt: str):
                    return query_llm_return_json(
                        llm_wrapper,
                        query_step,
                        "You are an expert in product taxonomies. Return JSON only.",
                        prompt,
                        reasoning_effort="high",
                    )

                branch = generate_category_taxonomy(
                    category_name=category,
                    existing_data=taxonomy,
                    example_count=2,
                    perform_review=True,
                    industry=industry,
                    industry_description=industry_desc,
                    company=company,
                    llm_call=_adapter,
                )
            except Exception as exc2:  # still failing
                logger.warning(
                    "Failed to generate taxonomy for '%s': %s", category, exc2
                )
                branch = {"id": category, "label": category, "attributes": []}
        else:
            logger.warning("Failed to generate taxonomy for '%s': %s", category, exc)
            branch = {"id": category, "label": category, "attributes": []}
    except Exception as exc:
        logger.warning("Failed to generate taxonomy for '%s': %s", category, exc)
        branch = {"id": category, "label": category, "attributes": []}

    # Only persist when the LLM produced attributes
    attrs_new = branch.get("attributes") or []
    if attrs_new:
        # Persist ONLY when the category is missing; never overwrite existing.
        if category_node is None:
            # Check for any existing node by id OR label (normalized)
            match_idx = None
            for i, c in enumerate(categories):
                cid = str(c.get("id", "")).strip().lower()
                clab = str(c.get("label", "")).strip().lower()
                if cid == cat_id or clab == cat_id:
                    match_idx = i
                    break
            if match_idx is None:
                taxonomy.setdefault("categories", []).append(branch)
                # Ensure the JSON file exists and is writable (from main branch)
                path = TAXONOMY_PATH
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists():
                    mode = path.stat().st_mode
                    if not mode & S_IWUSR:
                        path.chmod(mode | S_IWUSR)
                else:
                    path.touch(mode=S_IRUSR | S_IWUSR, exist_ok=True)
                save_attribute_taxonomy(taxonomy)
                logger.info("Appended new taxonomy branch: %s", branch.get("id"))
                # Ensure the just-created branch is fully normalized (IDs, synonyms, budgets)
                try:
                    cid = str(branch.get("id") or category).strip().lower()
                    normalize_category(cid)
                except Exception:
                    logger.exception(
                        "Normalization failed for new branch '%s'", category
                    )
                # Enrich machine-facing synonyms (hash-gated; high-quality web scoped)
                try:
                    enrich_category_if_stale(llm_wrapper, cid, service_tier="high")
                except Exception:
                    logger.exception(
                        "Synonym enrichment failed for '%s' (non-fatal)", cid
                    )
            else:
                logger.info(
                    "Category '%s' already exists (id/label match). Not overwriting.",
                    category,
                )
    else:
        logger.warning(
            "LLM generation returned no attributes for category '%s'", category
        )

    # Optionally call watcher here to detect emerging terms (requires product descriptions).
    # For example:
    # descriptions = load_recent_product_descriptions_for_category(category)  # implement in your app
    # candidates = detect_new_terms(descriptions, taxonomy, min_count=5)
    # if candidates:
    #     suggestions = suggest_new_nodes(candidates, category, llm_call)
    #     taxonomy = update_taxonomy_with_suggestions(taxonomy, suggestions)
    #     save_attribute_taxonomy(taxonomy)

    attrs = [
        str(a.get("label")).lower()
        for a in branch.get("attributes", [])
        if a.get("label")
    ]

    return deduplicate_attributes(attrs, list(existing_columns), llm_wrapper)


def classify_product_attributes(
    llm_wrapper,
    product_name: str,
    attributes: Iterable[str],
    *,
    category: str | None = None,
    allowed_values: Dict[str, List[str]] | None = None,
    attr_nodes: Dict[str, List[dict]] | None = None,
    attr_aliases: Dict[str, Dict[str, str]] | None = None,
    deterministic_blocked_aliases: Dict[str, set[str]] | None = None,
    deterministic_text: str | None = None,
    service_tier: str | None = None,
    domains: List[str] | None = None,
    raw_capture: Dict[str, str] | None = None,
    notes_capture: Dict[str, str] | None = None,
    deterministic_only: bool = False,
    enable_web_search: bool = True,
    query_step_override: str | None = None,
) -> Dict[str, str]:
    """Classify ``product_name`` values for the given ``attributes``.

    ``allowed_values`` optionally restricts each attribute to predefined options.
    The LLM may consult web search to verify official product information.
    """
    if not attributes:
        return {}
    attributes = [str(a).lower() for a in attributes]
    naming = get_naming_params()
    query_step = naming["attributeClassificationQuery"]
    context_lines: List[str] = []
    if category:
        context_lines.append(f"Category: {category}.")
    context_lines.append(f"Product: {product_name}.")
    if domains:
        context_lines.append(f"Search only on: {', '.join(domains)}.")
    # Stage 1: deterministic alias mapping (optional)
    values: Dict[str, str] = {}
    alias_source = deterministic_text or product_name
    if alias_source:
        for attr in attributes:
            if attr in {"spf", "spf_value"}:
                parsed_spf = _parse_spf_value(alias_source)
                if parsed_spf is not None:
                    values[attr] = str(parsed_spf)
    if allowed_values and attr_nodes and alias_source:
        for a in attributes:
            if a in values:
                continue
            nodes = attr_nodes.get(a)
            if not nodes:
                continue
            alias_map = _leaf_synonym_map(nodes)
            blocked_tokens = (
                deterministic_blocked_aliases.get(a, set())
                if deterministic_blocked_aliases
                else set()
            )
            if blocked_tokens:
                alias_map = {
                    token: canonical
                    for token, canonical in alias_map.items()
                    if token not in blocked_tokens
                }
            if attr_aliases and a in attr_aliases:
                alias_map.update(attr_aliases[a])
            hits = _deterministic_multi_hits(alias_source, alias_map)
            if not hits:
                continue
            allowed = allowed_values.get(a, [])
            guess = _pick_first_allowed_from_candidates(hits, allowed)
            if guess:
                values[a] = guess

    remaining = [a for a in attributes if a not in values]

    if deterministic_only:
        return values

    if allowed_values and remaining:
        # Build options text only for attributes that actually have enum options
        enum_attrs = [a for a in remaining if a in allowed_values]
        # Build structured JSON options with synonyms as aka per label
        options_obj: Dict[str, Any] = {"options": {}}
        for a in enum_attrs:
            labels = allowed_values[a]
            syn_lookup = (
                _leaf_synonyms_lookup(attr_nodes.get(a, [])) if attr_nodes else {}
            )
            choices: List[Dict[str, Any]] = []
            for lab in labels:
                lab_lc = str(lab).lower()
                aka = syn_lookup.get(lab_lc, [])
                choices.append({"label": lab, **({"aka": aka} if aka else {})})
            options_obj["options"][a] = choices
        options_json = json.dumps(options_obj, ensure_ascii=False)
        evidence_rule = (
            "Use web search if needed to consult official product information."
            if enable_web_search
            else "Use only the provided context. Do not use web search."
        )
        shared_rules = (
            "Rules:\n"
            "- For each attribute key in 'options', choose exactly one canonical 'label' from its liui.\n"
            "- If multiple labels apply, choose the first label as listed in the options.\n"
            "- The 'value' field must equal the chosen label exactly, or be 'n/a (not stated)', or 'not in taxonomy'.\n"
            "- Do NOT add citations, links, or extra text to 'value'.\n"
            "- If none of the options fit, set 'value' to 'not in taxonomy' and put your best guess in 'oov_candidate' (short phrase).\n"
            "- Add a short plain-text 'note' only if helpful (no links).\n"
            f"{evidence_rule}\n"
            'Return JSON {"values": {"Attribute": {"value": str, "oov_candidate": str|null, "note": str|null}}}'
        )
        # Numeric SPF contract (do not enumerate numbers as options)
        try:
            has_spf_numeric = any(a.lower() in {"spf", "spf_value"} for a in remaining)
        except Exception:
            has_spf_numeric = False
        if has_spf_numeric:
            shared_rules += (
                "\nAdditional rule for SPF: Do NOT choose from options. "
                "Return an integer between 1 and 150 for 'spf' (or 'spf_value'), if present. "
                "Interpret '50+' as 50. If no sunscreen value is stated, return 'N/A' for SPF."
            )
        context_block = "\n".join(context_lines)
        user_prompt = (
            f"{shared_rules}\n"
            f"Options (JSON):```json\n{options_json}\n```\n"
            "Context:\n"
            f"{context_block}"
        )
    elif not allowed_values:
        attr_list = ", ".join(attributes)
        evidence_rule = (
            "- If product information is unclear, perform a web search to check manufacturer descriptions.\n"
            if enable_web_search
            else "- Use only the provided context. Do not use web search.\n"
        )
        shared_rules = (
            "Rules:\n"
            "- Provide the canonical value for each attribute listed in the 'Attributes' section.\n"
            "- Return 'N/A' (or 'no idea') when you cannot determine an attribute; do not guess.\n"
            f"{evidence_rule}"
            'Return JSON {"values": {"Attribute": {"value": str, "oov_candidate": str|null, "note": str|null}}}'
        )
        context_block = "\n".join([f"Attributes: {attr_list}.", *context_lines])
        user_prompt = f"{shared_rules}\n" "Context:\n" f"{context_block}"
    else:
        # nothing remains to classify
        return values

    if enable_web_search:
        tools, extra_body = build_web_search_request(domains)
        tool_choice = "auto"
    else:
        tools = None
        extra_body = None
        tool_choice = "auto"

    # Prefer Flex only when the step is configured for batch ("batchFlex").
    if service_tier is None and should_use_flex(query_step):
        service_tier = "flex"
    # Clamp explicit Flex supplied by callers if step is not eligible
    elif service_tier == "flex" and not should_use_flex(query_step):
        service_tier = None

    from modules.llm.batch_runner import run_step_json

    resp = run_step_json(
        llm_wrapper,
        query_step,
        "You are an expert category product analyui. Return JSON only.",
        user_prompt,
        tools=tools,
        tool_choice=tool_choice,
        service_tier=service_tier,
        extra_body=extra_body,
    )[0]
    # Capture web search sources per product for audit when provided
    sources: List[dict] = []
    if isinstance(resp, dict):
        sources = resp.get("_sources") or []
    if sources:
        source_rows: List[dict] = []
        for s in sources:
            if not isinstance(s, dict):
                continue
            row = {
                "product": str(product_name),
                "category": str(category) if category else None,
                "url": s.get("url"),
                "title": s.get("title"),
                "snippet": s.get("snippet"),
            }
            source_rows.append(row)
        if source_rows:
            if audit_sources_store is not None:
                audit_sources_store.extend(source_rows)
            else:
                try:

                    src_rows = session_state.get("_attr_sources_rows") or []
                    src_rows.extend(source_rows)
                    session_state["_attr_sources_rows"] = src_rows
                except Exception:
                    pass
            try:
                from modules.add_attributes.sources_audit import (
                    append_sources as _append_sources,
                )

                _append_sources(source_rows)
            except Exception:
                pass
    # merge deterministic values with LLM output
    if isinstance(resp, dict):
        data = resp.get("values", resp)
        if isinstance(data, dict):
            normalized = {str(k).lower(): v for k, v in data.items()}
            # Preserve candidate and note from structured responses when present
            # Enforce structured contract; no backward-compat fallback
            try:
                for a in remaining if allowed_values else attributes:
                    entry = normalized.get(a)
                    candidate = None
                    note_val = None
                    if isinstance(entry, dict):
                        v_field = entry.get("value")
                        if v_field is not None:
                            normalized[a] = v_field
                        candidate = entry.get("oov_candidate")
                        note_val = entry.get("note")
                    else:
                        if raw_capture is not None and entry is not None:
                            try:
                                raw_capture[a] = str(entry)
                            except Exception:
                                pass
                        # Missing structured entry -> force explicit unknown
                        normalized[a] = "n/a (not stated)"
                    if raw_capture is not None and candidate is not None:
                        raw_capture[a] = str(candidate)
                    if notes_capture is not None and isinstance(
                        note_val, (str, int, float)
                    ):
                        notes_capture[a] = str(note_val).strip()
            except Exception:
                pass
            iter_attrs = remaining if allowed_values else attributes
            for attr in iter_attrs:
                val = normalized.get(attr)
                if isinstance(val, list):
                    # Collapse multi-valued outputs to a single allowed value
                    if attr in {"spf", "spf_value"}:
                        parsed = None
                        for item in val:
                            parsed = _parse_spf_value(item)
                            if parsed is not None:
                                break
                        if parsed is not None:
                            values[attr] = str(parsed)
                        else:
                            values[attr] = "N/A"
                        continue
                    if allowed_values and attr in allowed_values:
                        alias_map = None
                        if attr_nodes and attr in attr_nodes:
                            alias_map = _leaf_synonym_map(attr_nodes[attr])
                            if attr_aliases and attr in attr_aliases:
                                alias_map = {**attr_aliases[attr], **alias_map}
                        picked = _pick_first_allowed_from_candidates(
                            val, allowed_values[attr], alias_map=alias_map
                        )
                        values[attr] = picked if picked else NOT_IN_TAXONOMY_VALUE
                        continue
                    first = next((item for item in val if str(item).strip()), None)
                    if first is None:
                        continue
                    val = str(first)
                if isinstance(val, (str, int, float)):
                    val_lower = str(val).strip().lower()
                    val_clean = _strip_annotations_for_unknowns(val_lower)
                    # Numeric SPF handling: do not enumerate values; extract integer or set N/A
                    if attr in {"spf", "spf_value"}:
                        parsed = _parse_spf_value(val_lower)
                        if parsed is None and raw_capture is not None:
                            try:
                                candidate = raw_capture.get(attr)
                                parsed = (
                                    _parse_spf_value(candidate) if candidate else None
                                )
                            except Exception:
                                parsed = None
                        if parsed is not None:
                            val_norm = str(parsed)
                            values[attr] = val_norm
                            continue
                        # No parsable SPF -> treat as unknown
                        values[attr] = "N/A"
                        continue
                    # Canonicalize via alias map when available (non-numeric attributes)
                    if allowed_values and attr_nodes and attr in attr_nodes:
                        alias_map = _leaf_synonym_map(attr_nodes[attr])
                        if attr_aliases and attr in attr_aliases:
                            alias_map = {**attr_aliases[attr], **alias_map}
                        mapped = alias_map.get(_norm_token(val_lower))
                        if mapped:
                            val_lower = mapped
                    # Canonicalize taxonomy-provided unknown/other labels and loose variants
                    if val_clean in {
                        "no idea",
                        "unknown",
                        "n/a",
                        "na",
                        "",
                        "n/a (not stated)",
                    }:
                        val_norm = "N/A"
                    elif val_clean in {
                        "other",
                        "other (not in list)",
                        NOT_IN_TAXONOMY_VALUE,
                    }:
                        val_norm = NOT_IN_TAXONOMY_VALUE
                    else:
                        val_norm = val_lower
                    # When allowed values exist (enums), tolerate trailing citations/links for matching
                    if allowed_values and attr in allowed_values and val_norm != "N/A":
                        allowed = allowed_values[attr]
                        if val_norm not in allowed:
                            val_check = _normalize_for_allowed(val_norm)
                            if val_check in allowed:
                                val_norm = val_check
                            else:
                                # Safe auto-promotion from oov_candidate when it deterministically
                                # maps to a known leaf via synonyms or normalized label.
                                promoted = None
                                try:
                                    candidate = (
                                        raw_capture.get(attr)
                                        if raw_capture is not None
                                        else None
                                    )
                                except Exception:
                                    candidate = None
                                if candidate:
                                    alias_map2 = None
                                    if attr_nodes and attr in attr_nodes:
                                        alias_map2 = _leaf_synonym_map(attr_nodes[attr])
                                        if attr_aliases and attr in attr_aliases:
                                            alias_map2 = {
                                                **attr_aliases[attr],
                                                **alias_map2,
                                            }
                                    cand_map = None
                                    if alias_map2:
                                        cand_map = alias_map2.get(
                                            _norm_token(candidate)
                                        )
                                    if cand_map and cand_map in allowed:
                                        promoted = cand_map
                                    else:
                                        cand_norm = _normalize_for_allowed(candidate)
                                        if cand_norm in allowed:
                                            promoted = cand_norm
                                val_norm = (
                                    promoted if promoted else NOT_IN_TAXONOMY_VALUE
                                )
                    values[attr] = val_norm
    return values


def classify_attributes_for_products(
    llm_wrapper,
    df: pl.DataFrame,
    product_col: str,
    products: Iterable[str],
    attr_map: Dict[str, List[str]],
    *,
    group_col: str | None = None,
    groups: Iterable[str] | None = None,
    use_batch: bool | None = None,
    service_tier: str | None = None,
    domains_map: Dict[str, List[str]] | None = None,
    brand_col: str | None = None,
    desc_col: str | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
    audit_log: Dict[str, List[dict]] | None = None,
    deterministic_only: bool = False,
    enable_web_search: bool = True,
) -> pl.DataFrame:
    """Classify ``products`` according to ``attr_map``.

    ``domains_map`` restricts the LLM's web lookups to curated domains per
    product when provided. ``brand_col`` contributes to the LLM prompt while
    ``desc_col`` augments deterministic alias matching without polluting the
    prompt text.

    In non-batch mode, each result is appended to
    ``attribute_classifications.parquet`` to persist progress
    incrementally. The run configuration determines whether the batch
    endpoint is used when ``use_batch`` is not supplied.
    """

    if deterministic_only:
        use_batch = False
    elif use_batch is None:
        from modules.utilities.config import get_run_params, select_provider

        run_params = get_run_params()
        naming = get_naming_params()
        query_step = naming["attributeClassificationQuery"]
        query_dict = select_provider(query_step)
        use_batch = (
            run_params["llmBatchMode"]
            and query_dict.get("batchMode", True)
            and query_dict.get(naming["providerName"], query_dict.get("provider"))
            == "openai"
        )

    # Always normalize taxonomy before classification to ensure consistent
    # synonym handling and governance (runs quickly on small branches).
    try:
        normalize_all_categories()
    except Exception:
        logger.exception("Taxonomy normalization before classification failed")

    taxonomy = get_runtime_attribute_taxonomy()
    activity_map = get_attribute_activity() if not deterministic_only else {}
    cat_lookup: Dict[str, dict] = {}
    for c in taxonomy.get("categories", []) or []:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id", "")).strip().lower()
        if cid:
            cat_lookup[cid] = c
        clabel = str(c.get("label", "")).strip().lower()
        if clabel and clabel not in cat_lookup:
            cat_lookup[clabel] = c

    norm_attr_map: Dict[str, List[str]] = {
        str(k).strip().lower(): [str(a).lower() for a in v] for k, v in attr_map.items()
    }

    cache = load_cache()
    alias_index_data: Dict[str, Any] = {}
    try:
        loaded_alias_index = load_alias_index()
        if isinstance(loaded_alias_index, dict):
            alias_index_data = loaded_alias_index
    except Exception:
        logger.exception("Failed to load alias index; proceeding without aliases")
        alias_index_data = {}
    cache_updated = False
    # Periodic checkpoint to reduce risk of losing in-memory updates in case of
    # unexpected failures. Tunable; small enough to be safe, large enough to
    # avoid excessive disk IO.
    checkpoint_every = 10
    updates_since_checkpoint = 0
    records: List[dict] = []
    products = list(products)
    total = len(products)
    processed = 0

    audit_sources_store = (
        audit_log.setdefault("sources", []) if audit_log is not None else None
    )
    audit_raw_store = (
        audit_log.setdefault("raw_rows", []) if audit_log is not None else None
    )
    audit_notes_store = (
        audit_log.setdefault("notes", []) if audit_log is not None else None
    )

    columns, _ = get_schema_and_column_names(df)
    if product_col not in columns:
        raise ValueError(f"Column '{product_col}' not found in dataset")

    brand_available = bool(brand_col and brand_col in columns)
    desc_available = bool(desc_col and desc_col in columns)
    group_available = bool(group_col and group_col in columns)
    group_filter = set(groups) if groups else None

    product_rows: Dict[str, List[dict]] = {}
    for row in df.to_dicts():
        prod_val = row.get(product_col)
        key = normalize_product_key(prod_val)
        if key:
            product_rows.setdefault(key, []).append(row)

    def _stringify_component(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            parts = [str(v).strip() for v in value if str(v).strip()]
            return ", ".join(parts)
        return str(value).strip()

    unknown_tokens = {"no idea", "unknown", "n/a", "na", "", "n/a (not stated)"}

    # Metrics: track second-pass effectiveness across this run
    second_unknown_total = 0  # attributes unknown after first pass
    second_fixed_total = 0  # attributes resolved by the second pass
    second_products = 0  # products that required a second pass

    fallback_queue: List[_RetryRequest] = []
    product_contexts: List[_ProductProcessingContext] = []
    pending_buckets: Dict[
        ClassificationBucketKey, List[_PendingClassificationRequest]
    ] = {}

    try:
        for order_index, prod in enumerate(products):
            if not is_valid_product_name(prod):
                continue

            product_key = normalize_product_key(prod)
            rows = product_rows.get(product_key, [])
            if not rows:
                continue

            selected_rows = rows
            cat_val: Any = "All products"
            if group_available:
                scoped_rows = rows
                if group_filter is not None:
                    scoped_rows = [r for r in rows if r.get(group_col) in group_filter]
                    if not scoped_rows:
                        continue
                cat_candidate = next(
                    (
                        r.get(group_col)
                        for r in scoped_rows
                        if r.get(group_col) is not None
                    ),
                    None,
                )
                if cat_candidate is None:
                    continue
                cat_val = cat_candidate
                selected_rows = scoped_rows

            base_row = selected_rows[0]
            cat_key = (
                str(cat_val).strip().lower() if cat_val is not None else "all products"
            )
            if not cat_key:
                cat_key = "all products"

            hier_lookup: Dict[str, Dict[str, List[str]]] = {}
            allowed_values: Dict[str, List[str]] = {}
            attr_meta_by_label: Dict[str, dict] = {}
            attr_info: List[dict] = []
            nodes_by_label: Dict[str, List[dict]] = {}
            deterministic_blocked_aliases: Dict[str, set[str]] = {}
            if cat_key in cat_lookup:
                cat_node = cat_lookup[cat_key]
                attr_info = cat_node.get("attributes", []) or []
                requested_attrs = set(
                    norm_attr_map.get(
                        str(cat_val).strip().lower(),
                        norm_attr_map.get("all products", []),
                    )
                )
                attrs: List[str] = []
                cat_activity = (
                    activity_map.get(cat_key)
                    or activity_map.get(str(cat_node.get("id", "")).strip().lower())
                    or activity_map.get(str(cat_node.get("label", "")).strip().lower())
                    or {}
                )
                for info in attr_info:
                    label = info.get("label")
                    if not label:
                        continue
                    label_norm = str(label).lower()
                    info_id = str(info.get("id", "")).strip().lower()
                    if requested_attrs and (
                        label_norm not in requested_attrs
                        and info_id not in requested_attrs
                    ):
                        continue
                    status = cat_activity.get(
                        info_id,
                        cat_activity.get(label_norm, "active"),
                    )
                    if status != "active":
                        continue
                    attrs.append(label_norm)
                    attr_meta_by_label[label_norm] = info
                    nodes = info.get("nodes", []) or []
                    if label_norm not in {"spf", "spf_value"} and info_id not in {
                        "spf",
                        "spf_value",
                    }:
                        allowed_values[label_norm] = _leaf_labels(nodes)
                    hier_flag = info.get("hierarchical")
                    is_hier = (hier_flag is True) or (
                        isinstance(hier_flag, str) and hier_flag.lower() == "true"
                    )
                    if is_hier and int(info.get("levels", 1)) > 1:
                        hier_lookup[label_norm] = _leaf_paths(nodes)
                    nodes_by_label[label_norm] = nodes
                if nodes_by_label:
                    deterministic_blocked_aliases = (
                        _build_category_deterministic_blocked_aliases(nodes_by_label)
                    )
            else:
                attrs = norm_attr_map.get(
                    str(cat_val).strip().lower(),
                    norm_attr_map.get("all products", []),
                )

            if not attrs:
                records.append({product_col: prod, group_col or "group": cat_val})
                continue

            product_text = str(prod)
            if brand_available:
                brand_text = _stringify_component(base_row.get(brand_col))
                if brand_text:
                    product_text = f"{brand_text} {product_text}"
            deterministic_text = product_text
            if desc_available:
                desc_text = _stringify_component(base_row.get(desc_col))
                if desc_text:
                    deterministic_text = f"{product_text}. Description: {desc_text}"

            domain_list: List[str] | None = None
            if domains_map:
                raw_domains = domains_map.get(product_key) or []
                cleaned = [
                    str(val).strip()
                    for val in raw_domains
                    if isinstance(val, str) and str(val).strip()
                ]
                if cleaned:
                    domain_list = cleaned

            # Build normalized brand key (may be empty when brand column missing)
            brand_key = ""
            if brand_available:
                raw_brand = base_row.get(brand_col)
                parts: List[str] = []
                if isinstance(raw_brand, list):
                    parts = [
                        str(v).strip().lower() for v in raw_brand if str(v).strip()
                    ]
                elif raw_brand is not None:
                    parts = [
                        str(p).strip().lower()
                        for p in str(raw_brand).split(",")
                        if str(p).strip()
                    ]
                seen: set[str] = set()
                uniq: List[str] = []
                for p in parts:
                    if p not in seen:
                        seen.add(p)
                        uniq.append(p)
                if uniq:
                    brand_key = "+".join(uniq)

            cat_cache = cache.setdefault(cat_key, {})
            brand_cache = cat_cache.setdefault(brand_key, {})
            cached_vals = brand_cache.get(product_key, {})
            forced_refresh_attrs = {"spf", "spf_value"}
            if any(attr in cached_vals for attr in forced_refresh_attrs):
                cached_vals = {
                    attr: value
                    for attr, value in cached_vals.items()
                    if attr not in forced_refresh_attrs
                }
                brand_cache[product_key] = dict(cached_vals)
            missing = []
            for a in attrs:
                if a in forced_refresh_attrs:
                    missing.append(a)
                    continue
                if a not in cached_vals or _is_placeholder_cache_value(
                    cached_vals.get(a)
                ):
                    missing.append(a)
            # Treat cached placeholder values ("not in taxonomy", "N/A", etc.) as
            # missing so deterministic aliasing can refresh them when inputs change.
            allowed_subset = (
                {a: allowed_values[a] for a in missing if a in allowed_values}
                if allowed_values
                else None
            )

            alias_attr_map: Dict[str, Dict[str, str]] = {}
            if missing:
                try:
                    cat_bucket = alias_index_data.get("categories", {}).get(cat_key, {})
                    for a_lab, entry in cat_bucket.get("attributes", {}).items():
                        alias_attr_map[a_lab] = entry.get("aliases", {})
                except Exception:
                    logger.exception(
                        "Failed to load alias index; proceeding without aliases"
                    )
                    alias_attr_map = {}

            raw_capture: Dict[str, str] = {}
            notes_capture: Dict[str, str] = {}

            if not missing:
                current_vals = brand_cache.get(product_key, cached_vals)
                product_contexts.append(
                    _ProductProcessingContext(
                        product_name=str(prod),
                        product_key=product_key,
                        category_value=cat_val,
                        attrs=attrs,
                        attr_meta_by_label=attr_meta_by_label,
                        hier_lookup=hier_lookup,
                        allowed_values=allowed_values,
                        nodes_by_label=nodes_by_label,
                        brand_cache=brand_cache,
                        cached_vals=current_vals,
                        raw_capture=raw_capture,
                        notes_capture=notes_capture,
                        product_text=product_text,
                        deterministic_text=deterministic_text,
                        order_index=order_index,
                    )
                )
                continue
            if missing:
                pending_key = _build_bucket_key(missing, allowed_subset)
                pending_request = _PendingClassificationRequest(
                    product_name=str(prod),
                    product_key=product_key,
                    product_text=product_text,
                    category_value=cat_val,
                    attrs=attrs,
                    attr_meta_by_label=attr_meta_by_label,
                    hier_lookup=hier_lookup,
                    allowed_values=allowed_values,
                    nodes_by_label=nodes_by_label,
                    brand_cache=brand_cache,
                    cached_vals=cached_vals,
                    raw_capture=raw_capture,
                    notes_capture=notes_capture,
                    missing=missing,
                    allowed_subset=allowed_subset,
                    attr_alias_map=alias_attr_map if allowed_subset else None,
                    deterministic_blocked_aliases=(
                        {
                            attr: deterministic_blocked_aliases.get(attr, set())
                            for attr in missing
                        }
                        if deterministic_blocked_aliases
                        else None
                    ),
                    domain_list=domain_list,
                    deterministic_text=deterministic_text,
                    order_index=order_index,
                )
                pending_buckets.setdefault(pending_key, []).append(pending_request)
                continue

        if pending_buckets:
            bucket_items = sorted(
                pending_buckets.items(),
                key=lambda item: (
                    min(req.order_index for req in item[1]),
                    item[0],
                ),
            )
            if deterministic_only:
                for _, requests in bucket_items:
                    requests.sort(key=lambda req: req.order_index)
                    for request in requests:
                        current_vals = request.brand_cache.get(
                            request.product_key, request.cached_vals
                        )
                        pending_attrs = [
                            attr
                            for attr in request.missing
                            if attr not in current_vals
                            or _is_placeholder_cache_value(current_vals.get(attr))
                        ]
                        if not pending_attrs:
                            product_contexts.append(
                                _ProductProcessingContext(
                                    product_name=request.product_name,
                                    product_key=request.product_key,
                                    category_value=request.category_value,
                                    attrs=request.attrs,
                                    attr_meta_by_label=request.attr_meta_by_label,
                                    hier_lookup=request.hier_lookup,
                                    allowed_values=request.allowed_values,
                                    nodes_by_label=request.nodes_by_label,
                                    brand_cache=request.brand_cache,
                                    cached_vals=current_vals,
                                    raw_capture=request.raw_capture,
                                    notes_capture=request.notes_capture,
                                    product_text=request.product_text,
                                    deterministic_text=request.deterministic_text,
                                    order_index=request.order_index,
                                )
                            )
                            continue

                        allowed_subset = (
                            {
                                attr: values
                                for attr, values in (
                                    request.allowed_subset or {}
                                ).items()
                                if attr in pending_attrs
                            }
                            if request.allowed_subset
                            else None
                        )
                        alias_subset = (
                            {
                                attr: aliases
                                for attr, aliases in (
                                    request.attr_alias_map or {}
                                ).items()
                                if attr in pending_attrs
                            }
                            if request.attr_alias_map and allowed_subset
                            else None
                        )
                        new_vals = classify_product_attributes(
                            llm_wrapper,
                            request.product_text,
                            pending_attrs,
                            category=(
                                request.category_value
                                if request.category_value != "All products"
                                else None
                            ),
                            allowed_values=allowed_subset,
                            attr_nodes=(
                                {
                                    attr: request.nodes_by_label.get(attr, [])
                                    for attr in pending_attrs
                                }
                                if allowed_subset
                                else None
                            ),
                            attr_aliases=alias_subset,
                            deterministic_blocked_aliases=(
                                {
                                    attr: blocked
                                    for attr, blocked in (
                                        request.deterministic_blocked_aliases or {}
                                    ).items()
                                    if attr in pending_attrs
                                }
                                if request.deterministic_blocked_aliases
                                else None
                            ),
                            deterministic_text=request.deterministic_text,
                            service_tier=service_tier,
                            domains=request.domain_list,
                            raw_capture=request.raw_capture,
                            notes_capture=request.notes_capture,
                            deterministic_only=True,
                            enable_web_search=False,
                        )
                        if new_vals:
                            request.brand_cache.setdefault(
                                request.product_key, {}
                            ).update(new_vals)
                            cache_updated = True
                            updates_since_checkpoint += 1

                        current_vals = request.brand_cache.get(
                            request.product_key, request.cached_vals
                        )

                        if (
                            cache_updated
                            and updates_since_checkpoint >= checkpoint_every
                        ):
                            try:
                                save_cache(cache)
                            except Exception:
                                logger.exception("Checkpoint save_cache failed")
                            updates_since_checkpoint = 0

                        product_contexts.append(
                            _ProductProcessingContext(
                                product_name=request.product_name,
                                product_key=request.product_key,
                                category_value=request.category_value,
                                attrs=request.attrs,
                                attr_meta_by_label=request.attr_meta_by_label,
                                hier_lookup=request.hier_lookup,
                                allowed_values=request.allowed_values,
                                nodes_by_label=request.nodes_by_label,
                                brand_cache=request.brand_cache,
                                cached_vals=current_vals,
                                raw_capture=request.raw_capture,
                                notes_capture=request.notes_capture,
                                product_text=request.product_text,
                                deterministic_text=request.deterministic_text,
                                order_index=request.order_index,
                            )
                        )
            else:
                from modules.llm.llm_api import (
                    APIError,
                    APITimeoutError,
                    RateLimitError,
                )
                import httpx
                import random

                for _, requests in bucket_items:
                    requests.sort(key=lambda req: req.order_index)
                    for request in requests:
                        current_vals = request.brand_cache.get(
                            request.product_key, request.cached_vals
                        )
                        pending_attrs = [
                            attr
                            for attr in request.missing
                            if attr not in current_vals
                            or _is_placeholder_cache_value(current_vals.get(attr))
                        ]
                        if not pending_attrs:
                            product_contexts.append(
                                _ProductProcessingContext(
                                    product_name=request.product_name,
                                    product_key=request.product_key,
                                    category_value=request.category_value,
                                    attrs=request.attrs,
                                    attr_meta_by_label=request.attr_meta_by_label,
                                    hier_lookup=request.hier_lookup,
                                    allowed_values=request.allowed_values,
                                    nodes_by_label=request.nodes_by_label,
                                    brand_cache=request.brand_cache,
                                    cached_vals=current_vals,
                                    raw_capture=request.raw_capture,
                                    notes_capture=request.notes_capture,
                                    product_text=request.product_text,
                                    deterministic_text=request.deterministic_text,
                                    order_index=request.order_index,
                                )
                            )
                            continue

                        allowed_subset = (
                            {
                                attr: values
                                for attr, values in (
                                    request.allowed_subset or {}
                                ).items()
                                if attr in pending_attrs
                            }
                            if request.allowed_subset
                            else None
                        )
                        alias_subset = (
                            {
                                attr: aliases
                                for attr, aliases in (
                                    request.attr_alias_map or {}
                                ).items()
                                if attr in pending_attrs
                            }
                            if request.attr_alias_map and allowed_subset
                            else None
                        )
                        new_vals: Dict[str, str] = {}
                        for attempt in range(5):
                            try:
                                new_vals = classify_product_attributes(
                                    llm_wrapper,
                                    request.product_text,
                                    pending_attrs,
                                    category=(
                                        request.category_value
                                        if request.category_value != "All products"
                                        else None
                                    ),
                                    allowed_values=allowed_subset,
                                    attr_nodes=(
                                        {
                                            attr: request.nodes_by_label.get(attr, [])
                                            for attr in pending_attrs
                                        }
                                        if allowed_subset
                                        else None
                                    ),
                                    attr_aliases=alias_subset,
                                    deterministic_blocked_aliases=(
                                        {
                                            attr: blocked
                                            for attr, blocked in (
                                                request.deterministic_blocked_aliases
                                                or {}
                                            ).items()
                                            if attr in pending_attrs
                                        }
                                        if request.deterministic_blocked_aliases
                                        else None
                                    ),
                                    deterministic_text=request.deterministic_text,
                                    service_tier=service_tier,
                                    domains=request.domain_list,
                                    raw_capture=request.raw_capture,
                                    notes_capture=request.notes_capture,
                                    deterministic_only=deterministic_only,
                                    enable_web_search=enable_web_search,
                                )
                                request.brand_cache.setdefault(
                                    request.product_key, {}
                                ).update(new_vals)
                                cache_updated = True
                                updates_since_checkpoint += 1
                                break
                            except (
                                RateLimitError,
                                APIError,
                                APITimeoutError,
                                httpx.ReadTimeout,
                            ) as err:
                                status = getattr(err, "status_code", None)
                                if (
                                    isinstance(err, APIError)
                                    and status not in (429, None)
                                    and not (
                                        isinstance(status, int) and 500 <= status < 600
                                    )
                                ):
                                    raise
                                if (
                                    isinstance(err, APIError)
                                    and isinstance(status, int)
                                    and status >= 500
                                ):
                                    logger.warning(
                                        "LLM server error %s for '%s'. Skipping remaining attributes for this product.",
                                        status,
                                        request.product_name,
                                    )
                                    break
                                wait = (2**attempt) + random.uniform(0, 1)
                                logger.warning(
                                    "LLM rate/timeout error for '%s' (attempt %d/5): %s. Retrying in %.2fs",
                                    request.product_name,
                                    attempt + 1,
                                    err,
                                    wait,
                                )
                                time.sleep(wait)
                            except RuntimeError as err:
                                logger.warning(
                                    "LLM classification runtime error for '%s': %s. Skipping product.",
                                    request.product_name,
                                    err,
                                )
                                break
                            except Exception as err:
                                logger.exception(
                                    "LLM classification failed for '%s': %s",
                                    request.product_name,
                                    err,
                                )
                                new_vals = {}
                                break

                        current_vals = request.brand_cache.get(
                            request.product_key, request.cached_vals
                        )

                        retry_enabled = True
                        try:
                            retry_enabled = bool(
                                get_run_params()["attrClassificationRetryUnknowns"]
                            )
                        except Exception:
                            retry_enabled = True

                        if retry_enabled and request.domain_list and pending_attrs:
                            retry_targets = [
                                attr
                                for attr in pending_attrs
                                if str(current_vals.get(attr, "")).strip().lower()
                                in unknown_tokens
                            ]
                            if retry_targets:
                                second_products += 1
                                second_unknown_total += len(retry_targets)
                                retry_allowed = (
                                    {
                                        a: request.allowed_values[a]
                                        for a in retry_targets
                                        if a in request.allowed_values
                                    }
                                    if request.allowed_values
                                    else None
                                )
                                fallback_queue.append(
                                    _RetryRequest(
                                        product_key=request.product_key,
                                        product_name=request.product_name,
                                        product_text=request.product_text,
                                        deterministic_text=request.deterministic_text,
                                        category_value=request.category_value,
                                        retry_targets=retry_targets,
                                        retry_allowed=retry_allowed,
                                        nodes_by_label=(
                                            request.nodes_by_label
                                            if retry_allowed
                                            else None
                                        ),
                                        alias_attr_map=(
                                            request.attr_alias_map
                                            if retry_allowed
                                            else None
                                        ),
                                        deterministic_blocked_aliases=(
                                            request.deterministic_blocked_aliases
                                            if retry_allowed
                                            else None
                                        ),
                                        brand_cache=request.brand_cache,
                                        cached_vals=current_vals,
                                        raw_capture=request.raw_capture,
                                        notes_capture=request.notes_capture,
                                        order_index=request.order_index,
                                    )
                                )

                        if (
                            cache_updated
                            and updates_since_checkpoint >= checkpoint_every
                        ):
                            try:
                                save_cache(cache)
                            except Exception:
                                logger.exception("Checkpoint save_cache failed")
                            updates_since_checkpoint = 0

                        product_contexts.append(
                            _ProductProcessingContext(
                                product_name=request.product_name,
                                product_key=request.product_key,
                                category_value=request.category_value,
                                attrs=request.attrs,
                                attr_meta_by_label=request.attr_meta_by_label,
                                hier_lookup=request.hier_lookup,
                                allowed_values=request.allowed_values,
                                nodes_by_label=request.nodes_by_label,
                                brand_cache=request.brand_cache,
                                cached_vals=current_vals,
                                raw_capture=request.raw_capture,
                                notes_capture=request.notes_capture,
                                product_text=request.product_text,
                                deterministic_text=request.deterministic_text,
                                order_index=request.order_index,
                            )
                        )
        # After first-pass prompts, execute queued fallback retries.
        if fallback_queue and not deterministic_only:
            fallback_buckets: Dict[ClassificationBucketKey, List[_RetryRequest]] = {}
            for request in fallback_queue:
                bucket_key = _build_bucket_key(
                    request.retry_targets, request.retry_allowed
                )
                fallback_buckets.setdefault(bucket_key, []).append(request)

            bucket_items = sorted(
                fallback_buckets.items(),
                key=lambda item: (
                    min(req.order_index for req in item[1]),
                    item[0],
                ),
            )

            for _, requests in bucket_items:
                requests.sort(key=lambda req: req.order_index)
                for request in requests:
                    try:
                        fallback_vals = classify_product_attributes(
                            llm_wrapper,
                            request.product_text,
                            request.retry_targets,
                            category=(
                                request.category_value
                                if request.category_value != "All products"
                                else None
                            ),
                            allowed_values=request.retry_allowed,
                            attr_nodes=(
                                request.nodes_by_label
                                if request.retry_allowed
                                else None
                            ),
                            attr_aliases=(
                                request.alias_attr_map
                                if request.retry_allowed
                                else None
                            ),
                            deterministic_blocked_aliases=(
                                {
                                    attr: blocked
                                    for attr, blocked in (
                                        request.deterministic_blocked_aliases or {}
                                    ).items()
                                    if attr in request.retry_targets
                                }
                                if request.deterministic_blocked_aliases
                                else None
                            ),
                            deterministic_text=request.deterministic_text,
                            service_tier=service_tier,
                            domains=None,
                            raw_capture=request.raw_capture,
                            notes_capture=request.notes_capture,
                            deterministic_only=deterministic_only,
                            enable_web_search=enable_web_search,
                        )
                    except Exception as err:
                        logger.exception(
                            "Fallback classification failed for '%s': %s",
                            request.product_name,
                            err,
                        )
                        continue

                    if fallback_vals:
                        request.brand_cache.setdefault(request.product_key, {}).update(
                            fallback_vals
                        )
                        cache_updated = True
                        updates_since_checkpoint += 1

                    vals_after = request.brand_cache.get(
                        request.product_key, request.cached_vals
                    )
                    try:
                        fixed_now = sum(
                            1
                            for a in request.retry_targets
                            if str(vals_after.get(a, "")).strip().lower()
                            not in unknown_tokens
                            and vals_after.get(a) is not None
                            and str(vals_after.get(a)).strip() != ""
                        )
                        second_fixed_total += fixed_now
                    except Exception:
                        pass

                    if cache_updated and updates_since_checkpoint >= checkpoint_every:
                        try:
                            save_cache(cache)
                        except Exception:
                            logger.exception("Checkpoint save_cache failed")
                        updates_since_checkpoint = 0

        # Build final records after all classification passes complete.
        product_contexts.sort(key=lambda context: context.order_index)
        for context in product_contexts:
            prod = context.product_name
            cat_val = context.category_value
            attrs = context.attrs
            attr_meta_by_label = context.attr_meta_by_label
            hier_lookup = context.hier_lookup
            allowed_values = context.allowed_values
            raw_capture = context.raw_capture
            notes_capture = context.notes_capture
            product_text = context.product_text
            deterministic_text = context.deterministic_text
            vals = context.brand_cache.get(context.product_key, context.cached_vals)

            record = {product_col: prod, group_col or "group": cat_val}
            raw_record: Dict[str, Any] = {
                product_col: prod,
                group_col or "group": cat_val,
            }
            allowed_attrs = set(attrs or [])
            for attr, val in vals.items():
                if allowed_attrs and attr not in allowed_attrs:
                    continue
                val_lower = str(val).strip().lower()
                # Numeric SPF normalization at record time (overrides raw text)
                if attr in {"spf", "spf_value"}:
                    parsed = _parse_spf_value(val_lower)
                    if parsed is None and raw_capture is not None:
                        try:
                            candidate = raw_capture.get(attr)
                            parsed = _parse_spf_value(candidate) if candidate else None
                        except Exception:
                            parsed = None
                    if parsed is not None:
                        val_norm = str(parsed)
                    else:
                        val_norm = "N/A"
                else:
                    val_clean = _strip_annotations_for_unknowns(val_lower)
                    if val_clean in {
                        "no idea",
                        "unknown",
                        "n/a",
                        "na",
                        "",
                        "n/a (not stated)",
                    }:
                        val_norm = "N/A"
                    elif val_clean in {
                        "other",
                        "other (not in list)",
                        NOT_IN_TAXONOMY_VALUE,
                    }:
                        # Canonicalize to the taxonomy leaf label used in allowed values
                        # so it does not get treated as a 'not in taxonomy' sentinel.
                        val_norm = NOT_IN_TAXONOMY_VALUE
                    else:
                        val_norm = val_lower
                if val_norm not in {"N/A", NOT_IN_TAXONOMY_VALUE}:
                    val_norm = _normalize_legacy_allowed_value(cat_val, attr, val_norm)
                meta = attr_meta_by_label.get(attr, {})
                selection = str(meta.get("selection", "")).strip().lower()
                is_multi = selection == "multi"
                allowed = allowed_values.get(attr)
                raw_val = raw_capture.get(attr) if raw_capture is not None else None
                original_text = ""
                if isinstance(val, (str, int, float)):
                    try:
                        original_text = str(val).strip()
                    except Exception:
                        original_text = ""

                if (
                    allowed
                    and val_norm not in {"N/A", NOT_IN_TAXONOMY_VALUE}
                    and val_norm not in allowed
                ):
                    val_check = _normalize_for_allowed(val_norm)
                    if val_check in allowed:
                        val_norm = val_check
                    else:
                        candidate_for_map: str | None = None
                        if raw_val and not _is_trivial_placeholder(raw_val):
                            candidate_for_map = str(raw_val)
                        elif original_text and not _is_trivial_placeholder(
                            original_text
                        ):
                            candidate_for_map = original_text

                        promoted: str | None = None
                        if candidate_for_map:
                            try:
                                nodes = meta.get("nodes", [])
                                alias_map2 = _leaf_synonym_map(nodes)
                                mapped2 = alias_map2.get(_norm_token(candidate_for_map))
                                if mapped2 and mapped2 in allowed:
                                    promoted = mapped2
                                else:
                                    cand_norm = _normalize_legacy_allowed_value(
                                        cat_val, attr, candidate_for_map
                                    )
                                    if cand_norm in allowed:
                                        promoted = cand_norm
                            except Exception:
                                promoted = None

                        if promoted:
                            val_norm = promoted
                        else:
                            val_norm = NOT_IN_TAXONOMY_VALUE

                # Only queue/log when we have a concrete value that would be 'not in taxonomy'. Suppress for
                # generic unknowns and canonical other values regardless of case.
                lnorm = str(val_norm).lower()
                placeholders = {
                    "n/a",
                    "n/a (not stated)",
                    "other",
                    "other (not in list)",
                    NOT_IN_TAXONOMY_VALUE,
                }
                queue_candidate: str | None = None
                if lnorm == NOT_IN_TAXONOMY_VALUE:
                    candidate_source: str | None = None
                    if raw_val and not _is_trivial_placeholder(raw_val):
                        candidate_source = str(raw_val)
                        logger.info(
                            "Unmapped %s value '%s' for product '%s' in category '%s'",
                            attr,
                            raw_val,
                            prod,
                            cat_val,
                        )
                    elif original_text and not _is_trivial_placeholder(original_text):
                        candidate_source = original_text
                        logger.info(
                            "Unmapped %s value '%s' for product '%s' in category '%s'",
                            attr,
                            original_text,
                            prod,
                            cat_val,
                        )
                    if candidate_source:
                        queue_candidate = candidate_source

                if queue_candidate and not _is_trivial_placeholder(queue_candidate):
                    payload = {
                        "category": str(cat_val),
                        "attribute": str(attr),
                        "value": queue_candidate,
                        "product": str(prod),
                    }
                    try:
                        if queue_taxonomy_review is not None:
                            queue_taxonomy_review(payload)
                    except Exception:
                        pass
                    novelty_payload = {
                        "category": str(cat_val),
                        "attribute": str(attr),
                        "raw_value": queue_candidate,
                        "product": str(prod),
                        "source": "llm_inferred",
                    }
                    if append_novelty is not None:
                        try:
                            append_novelty(**novelty_payload)
                        except TypeError:
                            try:
                                append_novelty(novelty_payload)  # type: ignore[misc]
                            except Exception:
                                pass
                        except Exception:
                            pass

                if lnorm == NOT_IN_TAXONOMY_VALUE:
                    # Final normalization attempt before treating as unmapped.
                    if allowed and val_norm not in allowed:
                        try:
                            nodes = meta.get("nodes", [])
                            alias_map2 = _leaf_synonym_map(nodes)
                            mapped2 = alias_map2.get(_norm_token(val_norm))
                            if mapped2 and mapped2 in allowed:
                                val_norm = mapped2
                            else:
                                check2 = _normalize_legacy_allowed_value(
                                    cat_val,
                                    attr,
                                    val_norm,
                                )
                                if check2 in allowed:
                                    val_norm = check2
                        except Exception:
                            pass
                        lnorm = str(val_norm).lower()
                    # After the extra normalization, log if still truly unmapped
                    if (
                        allowed
                        and val_norm not in allowed
                        and lnorm not in placeholders
                    ):
                        logger.info(
                            "Unmapped %s value '%s' for product '%s' in category '%s'",
                            attr,
                            val_norm,
                            prod,
                            cat_val,
                        )
                        # Map remaining concrete not-in-taxonomy cases to the canonical fallback
                        val_norm = NOT_IN_TAXONOMY_VALUE

                # Stash raw value for export traceability when we normalized
                rv = raw_capture.get(attr)
                if rv and (lnorm == NOT_IN_TAXONOMY_VALUE or lnorm == "n/a"):
                    # Keep raw if not a trivial placeholder; also keep sentinel-with-annotation for audit
                    keep_raw = True
                    if _is_trivial_placeholder(rv):
                        try:
                            if not re.search(
                                r"^\s*(?:not in taxonomy|n/a|unknown)\s*\(",
                                str(rv).lower(),
                            ):
                                keep_raw = False
                        except Exception:
                            keep_raw = False
                    if keep_raw:
                        raw_record[f"{attr}_raw"] = str(rv)
                        # Attach any structured note captured for this attribute
                        if notes_capture.get(attr):
                            raw_record[f"{attr}_note"] = str(notes_capture.get(attr))

                if is_multi:
                    # One-hot encode leaves; derive matches from deterministic aliases and LLM-chosen value
                    nodes = meta.get("nodes", [])
                    attr_id = (
                        str(meta.get("id", attr)).strip().lower().replace(" ", "_")
                    )
                    alias_map = _leaf_synonym_map(nodes)
                    hits = set(_deterministic_multi_hits(deterministic_text, alias_map))
                    if allowed and val_norm in allowed:
                        hits.add(val_norm)
                    # Build label->id map for leaves
                    pairs = _leaf_id_label_pairs(nodes)
                    label_to_id = {lab: lid for lid, lab in pairs}
                    # Emit one-hot columns
                    for lab, lid in label_to_id.items():
                        col = f"{attr_id}__{lid}"
                        record[col] = lab in hits
                    # Unknown/other flags
                    unknown_col = f"{attr_id}__unknown"
                    record[unknown_col] = record.get(unknown_col, False) or (
                        val_norm == "N/A" and not hits
                    )
                    not_in_taxonomy_col = f"{attr_id}__{NOT_IN_TAXONOMY_FLAG_SUFFIX}"
                    # Mark 'not in taxonomy' only when no recognized hits and LLM indicated it
                    record[not_in_taxonomy_col] = record.get(
                        not_in_taxonomy_col, False
                    ) or (val_norm == NOT_IN_TAXONOMY_VALUE and not hits)
                    # Do not write single-value columns for multi-select
                    continue

                # single-select path
                if attr in hier_lookup:
                    record[f"{attr}_children"] = val_norm
                    parent_path = hier_lookup[attr].get(val_norm)
                    # Fallback: strip a trailing parenthetical annotation from the value
                    if not parent_path:
                        try:
                            val_no_paren = re.sub(
                                r"\s*\([^)]*\)\s*$", "", str(val_norm)
                            ).strip()
                        except Exception:
                            val_no_paren = str(val_norm)
                        if val_no_paren and val_no_paren != val_norm:
                            alt = hier_lookup[attr].get(val_no_paren)
                            if alt:
                                parent_path = alt
                                record[f"{attr}_children"] = val_no_paren
                    if parent_path and len(parent_path) >= 2:
                        record[attr] = str(parent_path[-2])
                    else:
                        record[attr] = val_norm
                else:
                    record[attr] = val_norm

            # Fill missing attributes with explicit N/A to avoid blank cells
            for a in attrs:
                if a not in record:
                    sel = (
                        str(attr_meta_by_label.get(a, {}).get("selection", ""))
                        .strip()
                        .lower()
                    )
                    if sel == "multi":
                        # For multi-select attributes, do not create single-value columns.
                        continue
                    if a in hier_lookup:
                        record[a] = "N/A"
                        record[f"{a}_children"] = "N/A"
                    else:
                        record[a] = "N/A"

            # Capture raw record row if any raw values were recorded
            has_raw_values = any(
                isinstance(k, str) and k.endswith("_raw") for k in raw_record.keys()
            )
            if has_raw_values:
                if audit_raw_store is not None:
                    audit_raw_store.append(dict(raw_record))
                else:
                    try:

                        rows = session_state.get("_attr_raw_rows") or []
                        rows.append(raw_record)
                        session_state["_attr_raw_rows"] = rows
                    except Exception:
                        pass

            # Persist per-attribute notes to a dedicated audit log
            try:
                if notes_capture:
                    from modules.add_attributes.notes_audit import (
                        append_notes as _append_attr_notes,
                    )

                    note_rows = []
                    for a, note_text in (notes_capture or {}).items():
                        try:
                            txt = str(note_text).strip()
                        except Exception:
                            txt = ""
                        if not txt:
                            continue
                        raw_val = None
                        try:
                            rv = raw_capture.get(a) if raw_capture is not None else None
                            if isinstance(rv, (str, int, float)):
                                raw_val = str(rv)
                        except Exception:
                            raw_val = None
                        note_rows.append(
                            {
                                "product": str(prod),
                                "category": (
                                    str(cat_val) if cat_val != "All products" else None
                                ),
                                "attribute": str(a),
                                "note": txt,
                                "raw_value": raw_val,
                            }
                        )
                    if note_rows:
                        if audit_notes_store is not None:
                            audit_notes_store.extend(note_rows)
                        _append_attr_notes(note_rows)
            except Exception:
                # Logging audit is best-effort and should not affect main flow
                pass

            # After processing all attributes, persist one row per product and update progress
            if not vals:
                records.append(record)
                processed += 1
                if progress_cb:
                    progress_cb(processed, total)
            else:
                df_record = pl.DataFrame([record], orient="row")
                with FileLock(CLASSIFICATION_PARQUET):
                    existing: pl.DataFrame | None = None
                    if CLASSIFICATION_PARQUET.exists():
                        try:
                            existing = pl.read_parquet(CLASSIFICATION_PARQUET)
                        except (OSError, pl.exceptions.PolarsError) as exc:
                            logger.warning(
                                "Classification cache at %s is unreadable; rebuilding it. error=%s",
                                CLASSIFICATION_PARQUET,
                                exc,
                            )
                            broken_path = CLASSIFICATION_PARQUET.with_name(
                                f"{CLASSIFICATION_PARQUET.stem}.corrupt_{int(time.time())}{CLASSIFICATION_PARQUET.suffix}"
                            )
                            try:
                                CLASSIFICATION_PARQUET.replace(broken_path)
                            except OSError:
                                CLASSIFICATION_PARQUET.unlink(missing_ok=True)
                    if existing is not None:
                        existing_cols, existing_schema = get_schema_and_column_names(
                            existing
                        )
                        new_cols, record_schema = get_schema_and_column_names(df_record)
                        all_cols = sorted({*existing_cols, *new_cols})
                        missing_in_existing = [
                            c for c in all_cols if c not in existing_cols
                        ]
                        if missing_in_existing:
                            existing = existing.with_columns(
                                [pl.lit(None).alias(c) for c in missing_in_existing]
                            )
                        missing_in_new = [c for c in all_cols if c not in new_cols]
                        if missing_in_new:
                            df_record = df_record.with_columns(
                                [pl.lit(None).alias(c) for c in missing_in_new]
                            )
                        existing = existing.select(all_cols)
                        df_record = df_record.select(all_cols)
                        existing_cols, existing_schema = get_schema_and_column_names(
                            existing
                        )
                        new_cols, record_schema = get_schema_and_column_names(df_record)
                        cast_map = {
                            col: dtype
                            for col, dtype in record_schema.items()
                            if existing_schema.get(col) == pl.Null and dtype != pl.Null
                        }
                        if cast_map:
                            existing = existing.cast(cast_map)
                            existing_cols, existing_schema = (
                                get_schema_and_column_names(existing)
                            )
                        reverse_cast_map = {
                            col: existing_schema[col]
                            for col in all_cols
                            if record_schema.get(col) == pl.Null
                            and existing_schema.get(col) != pl.Null
                        }
                        if reverse_cast_map:
                            df_record = df_record.cast(reverse_cast_map)
                            new_cols, record_schema = get_schema_and_column_names(
                                df_record
                            )
                        if existing.schema != df_record.schema:
                            raise TypeError("Schema mismatch after alignment")
                        pl.concat([existing, df_record], how="vertical").write_parquet(
                            CLASSIFICATION_PARQUET
                        )
                    else:
                        CLASSIFICATION_PARQUET.parent.mkdir(parents=True, exist_ok=True)
                        df_record.write_parquet(CLASSIFICATION_PARQUET)
                records.append(record)
                processed += 1
                if progress_cb:
                    progress_cb(processed, total)
    finally:
        if cache_updated:
            try:
                save_cache(cache)
            except Exception:
                logger.exception("Final save_cache failed")

    # Emit a concise summary for the run (best-effort; UI is optional)
    if second_unknown_total:
        rate = (
            (second_fixed_total / second_unknown_total) * 100
            if second_unknown_total
            else 0.0
        )
        logger.info(
            "Second pass recovered %d/%d attributes (%.1f%%) across %d products",
            second_fixed_total,
            second_unknown_total,
            rate,
            second_products,
        )
        try:
            ui.caption(
                f"Second pass recovered {second_fixed_total}/{second_unknown_total} attributes "
                f"({rate:.0f}%) across {second_products} products."
            )
        except Exception:
            pass
        try:
            session_state["attr_second_pass_metrics"] = {
                "unknown_after_first": second_unknown_total,
                "fixed_by_second": second_fixed_total,
                "products_second_pass": second_products,
            }
        except Exception:
            pass

    try:
        return pl.DataFrame(records, orient="row")
    except TypeError as e:  # pragma: no cover

        ui.write("attribute_classification orient error:", e)
        return pl.DataFrame(records)
