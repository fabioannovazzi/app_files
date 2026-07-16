from __future__ import annotations

from copy import deepcopy
import json
import logging
from functools import lru_cache
from pathlib import Path
import shutil
import stat
from typing import Any, Dict, List

HERE = Path(__file__).parent
APP_ROOT = HERE.parent.parent
TAXONOMY_PATH = APP_ROOT / "config" / "attribute_taxonomy"
TAXONOMY_TEMPLATE_PATH = APP_ROOT / "attribute_taxonomy.example.json"
ATTRIBUTE_ACTIVITY_PATH = APP_ROOT / "attribute_activity.json"
ATTRIBUTE_ACTIVITY_TEMPLATE_PATH = APP_ROOT / "attribute_activity.example.json"
CATEGORY_ALIASES_PATH = APP_ROOT / "category_aliases.json"
CATEGORY_ALIASES_TEMPLATE_PATH = APP_ROOT / "category_aliases.example.json"
VISION_ALLOWLIST_PATH = APP_ROOT / "config" / "vision_allowlist.json"
WEB_ALLOWLIST_PATH = APP_ROOT / "config" / "web_allowlist.json"
TAXONOMY_MANIFEST_FILENAME = "manifest.json"
TAXONOMY_CATEGORIES_DIRNAME = "categories"

REVIEW_QUEUE_PATH = APP_ROOT / "taxonomy_review_queue.json"

# Normalize branches on load to guard against null children/synonyms and
# inconsistent types in legacy files.
logger = logging.getLogger(__name__)

try:
    # Local import to avoid heavy dependencies at module import time
    from .taxonomy_schema import validate_branch
except Exception as e:  # pragma: no cover - defensive import guard
    logger.warning("taxonomy_schema import failed; validation disabled: %s", e)
    validate_branch = None  # type: ignore

__all__ = [
    "get_attribute_taxonomy",
    "get_runtime_attribute_taxonomy",
    "get_attribute_activity",
    "get_category_alias_map",
    "save_attribute_taxonomy",
    "queue_taxonomy_review",
    "load_taxonomy_review_queue",
    "save_taxonomy_review_queue",
    "remove_taxonomy_review_entry",
    "aggregate_pending_values",
    "select_top_candidates",
    "get_taxonomy_storage_mtime",
]


def _leaf_status(node: Dict[str, Any]) -> str:
    node_id = str(node.get("id", "")).strip().lower()
    if node_id in {"unknown", "other"}:
        return "active"
    status = str(node.get("status") or "active").strip().lower()
    return status or "active"


def _retry_remove_readonly(func, path: str, _exc_info) -> None:
    """Clear read-only bits and retry backup cleanup on Windows."""

    target = Path(path)
    mode = stat.S_IREAD | stat.S_IWRITE
    if target.is_dir():
        mode |= stat.S_IEXEC
    try:
        target.chmod(mode)
    except OSError:
        pass
    func(path)


def _remove_existing_taxonomy_path(path: Path) -> None:
    """Remove a file or directory, tolerating read-only backup contents."""

    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, onerror=_retry_remove_readonly)
        return
    try:
        path.chmod(stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass
    path.unlink()


def _filter_active_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        children = node.get("children")
        if isinstance(children, list) and children:
            active_children = _filter_active_nodes(children)
            if not active_children:
                continue
            node_copy = deepcopy(node)
            node_copy["children"] = active_children
            filtered.append(node_copy)
            continue
        if _leaf_status(node) != "active":
            continue
        filtered.append(deepcopy(node))
    return filtered


def _is_taxonomy_directory(path: Path) -> bool:
    if path.exists():
        return path.is_dir()
    return path.suffix.lower() != ".json"


def _category_storage_filename(category: Dict[str, Any], *, fallback_index: int) -> str:
    raw = (
        category.get("id") or category.get("label") or f"category_{fallback_index:03d}"
    )
    token = _normalise_token(raw)
    if not token:
        token = f"category_{fallback_index:03d}"
    return f"{token}.json"


def _load_taxonomy_from_file(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_taxonomy_from_directory(path: Path) -> Dict[str, Any]:
    manifest_path = path / TAXONOMY_MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Taxonomy manifest not found: {manifest_path}")
    with manifest_path.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    if not isinstance(manifest, dict):
        raise ValueError(f"Invalid taxonomy manifest in {manifest_path}")

    categories_dir = path / TAXONOMY_CATEGORIES_DIRNAME
    manifest_categories = manifest.pop("category_files", [])
    branches: List[Dict[str, Any]] = []

    if isinstance(manifest_categories, list) and manifest_categories:
        entries = manifest_categories
    else:
        entries = [
            {"file": f"{TAXONOMY_CATEGORIES_DIRNAME}/{candidate.name}"}
            for candidate in sorted(categories_dir.glob("*.json"))
        ]

    for entry in entries:
        relative_file = None
        if isinstance(entry, str):
            relative_file = entry
        elif isinstance(entry, dict):
            relative_file = entry.get("file")
        if not isinstance(relative_file, str) or not relative_file.strip():
            continue
        branch_path = path / relative_file
        if not branch_path.is_file():
            raise FileNotFoundError(f"Taxonomy category file not found: {branch_path}")
        with branch_path.open(encoding="utf-8") as fh:
            branch = json.load(fh)
        if isinstance(branch, dict):
            branches.append(branch)

    manifest["categories"] = branches
    return manifest


def _save_taxonomy_to_file(path: Path, taxonomy: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(taxonomy, indent=4) + "\n"
    with tmp_path.open("w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        try:
            import os

            os.fsync(fh.fileno())
        except Exception as e:
            logger.warning("fsync failed when saving taxonomy: %s", e)
    tmp_path.replace(path)


def _save_taxonomy_to_directory(path: Path, taxonomy: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = path.with_name(f"{path.name}.tmp")
    backup_dir = path.with_name(f"{path.name}.bak")
    if tmp_dir.exists():
        _remove_existing_taxonomy_path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    categories_dir = tmp_dir / TAXONOMY_CATEGORIES_DIRNAME
    categories_dir.mkdir(parents=True, exist_ok=True)

    categories = taxonomy.get("categories", [])
    manifest: Dict[str, Any] = {
        key: deepcopy(value) for key, value in taxonomy.items() if key != "categories"
    }
    category_files: List[Dict[str, str]] = []
    used_names: set[str] = set()
    for index, category in enumerate(
        categories if isinstance(categories, list) else [], start=1
    ):
        if not isinstance(category, dict):
            continue
        filename = _category_storage_filename(category, fallback_index=index)
        while filename in used_names:
            stem = Path(filename).stem
            filename = f"{stem}_{index:03d}.json"
        used_names.add(filename)
        branch_path = categories_dir / filename
        branch_path.write_text(
            json.dumps(category, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )
        category_files.append(
            {
                "id": str(category.get("id") or "").strip(),
                "file": f"{TAXONOMY_CATEGORIES_DIRNAME}/{filename}",
            }
        )
    manifest["category_files"] = category_files
    (tmp_dir / TAXONOMY_MANIFEST_FILENAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )

    _remove_existing_taxonomy_path(backup_dir)
    if path.exists():
        path.replace(backup_dir)
    tmp_dir.replace(path)
    _remove_existing_taxonomy_path(backup_dir)


def get_taxonomy_storage_mtime(path: Path | None = None) -> float | None:
    target = path or TAXONOMY_PATH
    if not target.exists():
        return None
    if target.is_file():
        return float(target.stat().st_mtime)
    mtimes = [target.stat().st_mtime]
    for candidate in target.rglob("*.json"):
        mtimes.append(candidate.stat().st_mtime)
    return float(max(mtimes)) if mtimes else None


def get_attribute_taxonomy() -> Dict[str, Any]:
    """Return the attribute taxonomy from storage.

    Raises
    ------
    FileNotFoundError
        If the taxonomy storage does not exist.
    ValueError
        If the taxonomy payload is invalid.
    """

    json_path = TAXONOMY_PATH
    if not json_path.exists():
        if TAXONOMY_TEMPLATE_PATH.is_file():
            logger.info(
                "Using attribute taxonomy template at %s", TAXONOMY_TEMPLATE_PATH
            )
            json_path = TAXONOMY_TEMPLATE_PATH
        else:
            raise FileNotFoundError(
                f"Attribute taxonomy storage not found: {json_path}"
            )

    try:
        if _is_taxonomy_directory(json_path):
            data = _load_taxonomy_from_directory(json_path)
        else:
            data = _load_taxonomy_from_file(json_path)
        # Opportunistic normalization: clean each category branch in-memory.
        # If normalization changes the data, persist it back to disk so future
        # runs benefit from the canonical form (IDs/labels/synonyms cleaned,
        # selection coerced to single, reserved leaves ensured, etc.).
        if validate_branch and isinstance(data, dict):
            cats = data.get("categories")
            if isinstance(cats, list):
                new_cats: List[Dict[str, Any]] = []
                changed = False
                for c in cats:
                    if isinstance(c, dict):
                        try:
                            norm, _ = validate_branch(c)
                        except Exception:
                            logger.exception(
                                "validate_branch failed; returning original branch"
                            )
                            norm = c
                        else:
                            if norm != c:
                                changed = True
                        new_cats.append(norm)
                    else:
                        new_cats.append(c)
                data = dict(data)
                data["categories"] = new_cats
                if changed:
                    try:
                        save_attribute_taxonomy(data)
                        logger.info("Persisted normalized taxonomy JSON")
                    except Exception:
                        logger.exception("Failed to persist normalized taxonomy JSON")
        allow_map, no_image = _load_vision_allowlist()
        _, no_web = _load_web_allowlist()
        if allow_map or no_image or no_web:
            categories = data.get("categories")
            if isinstance(categories, list):
                for cat in categories:
                    if not isinstance(cat, dict):
                        continue
                    cid = _normalise_token(cat.get("id"))
                    if not cid:
                        continue
                    allow = allow_map.get(cid, [])
                    if allow:
                        attr_ids = {
                            str(a.get("id")).strip()
                            for a in (cat.get("attributes") or [])
                            if isinstance(a, dict) and a.get("id")
                        }
                        filtered = [attr for attr in allow if attr in attr_ids]
                        if filtered:
                            cat["image_allowlist"] = filtered
                        else:
                            cat.pop("image_allowlist", None)
                    else:
                        cat.pop("image_allowlist", None)
                    cat.pop("web_allowlist", None)
            if no_image:
                data["no_image_categories"] = no_image
            else:
                data.pop("no_image_categories", None)
            if no_web:
                data["no_web_categories"] = no_web
            else:
                data.pop("no_web_categories", None)
        return data
    except json.JSONDecodeError as exc:  # pragma: no cover - invalid JSON
        raise ValueError(f"Invalid JSON in {json_path}") from exc


def get_runtime_attribute_taxonomy() -> Dict[str, Any]:
    """Return the taxonomy filtered to active runtime leaves only."""

    taxonomy = deepcopy(get_attribute_taxonomy())
    categories = taxonomy.get("categories")
    if not isinstance(categories, list):
        return taxonomy

    for category in categories:
        if not isinstance(category, dict):
            continue
        attributes = category.get("attributes")
        if not isinstance(attributes, list):
            continue
        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue
            nodes = attribute.get("nodes")
            if not isinstance(nodes, list):
                continue
            attribute["nodes"] = _filter_active_nodes(nodes)

    return taxonomy


def _normalise_token(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "_")


@lru_cache(maxsize=1)
def _load_vision_allowlist() -> tuple[Dict[str, List[str]], List[str]]:
    if not VISION_ALLOWLIST_PATH.is_file():
        return {}, []
    try:
        with VISION_ALLOWLIST_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        logger.exception(
            "Failed to load vision allowlist from %s", VISION_ALLOWLIST_PATH
        )
        return {}, []

    allowlist_raw = data.get("image_allowlist", {}) if isinstance(data, dict) else {}
    allow_map: Dict[str, List[str]] = {}
    if isinstance(allowlist_raw, dict):
        for raw_key, raw_vals in allowlist_raw.items():
            key_norm = _normalise_token(raw_key)
            if not key_norm:
                continue
            vals: List[str] = []
            if isinstance(raw_vals, list):
                seen: set[str] = set()
                for item in raw_vals:
                    token = _normalise_token(item)
                    if not token or token in seen:
                        continue
                    seen.add(token)
                    vals.append(token)
            if vals:
                allow_map[key_norm] = vals

    no_image_raw = data.get("no_image_categories", []) if isinstance(data, dict) else []
    no_image: List[str] = []
    if isinstance(no_image_raw, list):
        seen: set[str] = set()
        for item in no_image_raw:
            token = _normalise_token(item)
            if not token or token in seen:
                continue
            seen.add(token)
            no_image.append(token)

    return allow_map, no_image


@lru_cache(maxsize=1)
def _load_web_allowlist() -> tuple[Dict[str, List[str]], List[str]]:
    if not WEB_ALLOWLIST_PATH.is_file():
        return {}, []
    try:
        with WEB_ALLOWLIST_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to load web allowlist from %s", WEB_ALLOWLIST_PATH)
        return {}, []

    allowlist_raw = data.get("web_allowlist", {}) if isinstance(data, dict) else {}
    allow_map: Dict[str, List[str]] = {}
    if isinstance(allowlist_raw, dict):
        for raw_key, raw_vals in allowlist_raw.items():
            key_norm = _normalise_token(raw_key)
            if not key_norm:
                continue
            vals: List[str] = []
            if isinstance(raw_vals, list):
                seen: set[str] = set()
                for item in raw_vals:
                    token = _normalise_token(item)
                    if not token or token in seen:
                        continue
                    seen.add(token)
                    vals.append(token)
            if vals:
                allow_map[key_norm] = vals

    no_web_raw = data.get("no_web_categories", []) if isinstance(data, dict) else []
    no_web: List[str] = []
    if isinstance(no_web_raw, list):
        seen: set[str] = set()
        for item in no_web_raw:
            token = _normalise_token(item)
            if not token or token in seen:
                continue
            seen.add(token)
            no_web.append(token)

    return allow_map, no_web


@lru_cache(maxsize=1)
def get_attribute_activity() -> Dict[str, Dict[str, str]]:
    """Return attribute activity flags keyed by category and attribute.

    The returned structure is ``{category: {attribute: status}}`` with both
    category IDs and labels (lowercased) as keys. Attribute status entries
    include both IDs and labels so callers can resolve activity by either
    identifier.
    """

    activity_path = ATTRIBUTE_ACTIVITY_PATH
    if not activity_path.is_file():
        if ATTRIBUTE_ACTIVITY_TEMPLATE_PATH.is_file():
            logger.info(
                "Using attribute activity template at %s",
                ATTRIBUTE_ACTIVITY_TEMPLATE_PATH,
            )
            activity_path = ATTRIBUTE_ACTIVITY_TEMPLATE_PATH
        else:
            return {}

    try:
        with activity_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):  # pragma: no cover - defensive
        return {}

    activity: Dict[str, Dict[str, str]] = {}
    categories = data.get("categories", [])
    if not isinstance(categories, list):
        return activity

    for category in categories:
        if not isinstance(category, dict):
            continue
        cat_keys = set()
        cid = str(category.get("id", "")).strip().lower()
        clabel = str(category.get("label", "")).strip().lower()
        if cid:
            cat_keys.add(cid)
        if clabel:
            cat_keys.add(clabel)

        attr_status: Dict[str, str] = {}
        for attr in category.get("attributes", []) or []:
            if not isinstance(attr, dict):
                continue
            status_raw = attr.get("status", "active")
            status = str(status_raw).strip().lower() or "active"
            aid = str(attr.get("id", "")).strip().lower()
            alab = str(attr.get("label", "")).strip().lower()
            if aid:
                attr_status[aid] = status
            if alab:
                attr_status[alab] = status

        if not attr_status:
            continue
        for cat_key in cat_keys:
            if not cat_key:
                continue
            existing = activity.setdefault(cat_key, {})
            existing.update(attr_status)

    return activity


@lru_cache(maxsize=1)
def get_category_alias_map() -> Dict[str, str]:
    """Return retailer → canonical category aliases."""

    alias_path = CATEGORY_ALIASES_PATH
    if not alias_path.is_file():
        if CATEGORY_ALIASES_TEMPLATE_PATH.is_file():
            logger.info(
                "Using category alias template at %s", CATEGORY_ALIASES_TEMPLATE_PATH
            )
            alias_path = CATEGORY_ALIASES_TEMPLATE_PATH
        else:
            return {}

    try:
        with alias_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):  # pragma: no cover - defensive
        logger.exception("Failed to load category aliases from %s", alias_path)
        return {}

    aliases_raw = data.get("aliases", {})
    if not isinstance(aliases_raw, dict):
        return {}

    alias_map: Dict[str, str] = {}
    for raw_key, raw_value in aliases_raw.items():
        key_norm = _normalise_token(raw_key)
        value_norm = _normalise_token(raw_value)
        if not key_norm or not value_norm:
            continue
        alias_map[key_norm] = value_norm
    return alias_map


def save_attribute_taxonomy(taxonomy: Dict[str, Any]) -> None:
    """Persist ``taxonomy`` to :data:`TAXONOMY_PATH`."""

    if _is_taxonomy_directory(TAXONOMY_PATH):
        _save_taxonomy_to_directory(TAXONOMY_PATH, taxonomy)
    else:
        _save_taxonomy_to_file(TAXONOMY_PATH, taxonomy)


def queue_taxonomy_review(entry: Dict[str, Any]) -> None:
    """Append ``entry`` to the taxonomy review queue."""

    queue = load_taxonomy_review_queue()
    queue.append(entry)
    save_taxonomy_review_queue(queue)


def load_taxonomy_review_queue() -> List[Dict[str, Any]]:
    """Return queued taxonomy review items."""

    if not REVIEW_QUEUE_PATH.is_file():
        return []
    with REVIEW_QUEUE_PATH.open(encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:  # pragma: no cover - corrupt queue
            return []


def save_taxonomy_review_queue(entries: List[Dict[str, Any]]) -> None:
    """Persist review ``entries`` to :data:`REVIEW_QUEUE_PATH`."""

    with REVIEW_QUEUE_PATH.open("w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=4)
        fh.write("\n")


def remove_taxonomy_review_entry(entry: Dict[str, Any]) -> None:
    """Remove ``entry`` from the review queue if present."""

    queue = load_taxonomy_review_queue()
    queue = [e for e in queue if e != entry]
    save_taxonomy_review_queue(queue)


def select_top_candidates(
    aggregated: List[Dict[str, Any]], top_k: int
) -> List[Dict[str, Any]]:
    """Return the ``top_k`` candidates sorted by descending ``count``.

    Parameters
    ----------
    aggregated:
        A list of dictionaries each containing a ``count`` key.
    top_k:
        The maximum number of candidates to return.
    """

    return sorted(aggregated, key=lambda x: x.get("count", 0), reverse=True)[:top_k]


def aggregate_pending_values(top_k: int) -> List[Dict[str, Any]]:
    """Group pending taxonomy review entries by value and count occurrences.

    Parameters
    ----------
    top_k:
        Maximum number of aggregated candidates to return.
    """

    queue = load_taxonomy_review_queue()
    if not queue:
        return []

    counts: Dict[tuple[str, str, str], int] = {}
    # Exclude trivial tokens from aggregation; keep concrete candidates only.
    trivial_values = {
        "other",
        "other (not in list)",
        "n/a",
        "n/a (not stated)",
        "unknown",
        "not in taxonomy",
        "",
    }
    for entry in queue:
        category = str(entry.get("category", "")).strip().lower()
        attribute = str(entry.get("attribute", "")).strip().lower()
        value = str(entry.get("value", "")).strip()
        if not (category and attribute and value):
            continue
        if value.strip().lower() in trivial_values:
            # Skip legacy or uninformative placeholders (e.g., 'other').
            continue
        cnt = entry.get("count", 1)
        try:
            cnt_int = int(cnt)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            cnt_int = 1
        key = (category, attribute, value)
        counts[key] = counts.get(key, 0) + cnt_int

    aggregated = [
        {
            "category": c,
            "attribute": a,
            "value": v,
            "count": n,
        }
        for (c, a, v), n in counts.items()
    ]
    return select_top_candidates(aggregated, top_k)
