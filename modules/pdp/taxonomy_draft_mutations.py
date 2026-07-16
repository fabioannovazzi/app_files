from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping

__all__ = [
    "APPLICABLE_USER_PROPOSAL_TYPES",
    "PREVIEWABLE_USER_PROPOSAL_TYPES",
    "apply_user_taxonomy_proposal",
]


APPLICABLE_USER_PROPOSAL_TYPES = frozenset(
    {"add_synonym", "remove_synonym", "move_synonym", "rename_value", "add_value"}
)

PREVIEWABLE_USER_PROPOSAL_TYPES = frozenset(
    {*APPLICABLE_USER_PROPOSAL_TYPES, "merge_values", "split_value"}
)


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "_")


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _iter_leaf_nodes(nodes: Iterable[Mapping[str, Any]]) -> Iterable[dict[str, Any]]:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        children = node.get("children")
        if isinstance(children, list) and children:
            yield from _iter_leaf_nodes(children)
            continue
        yield node


def _find_attribute(
    taxonomy: dict[str, Any],
    *,
    category_key: str,
    attribute_id: str,
) -> dict[str, Any]:
    for category in taxonomy.get("categories") or []:
        if not isinstance(category, dict):
            continue
        if _normalize_key(category.get("id") or category.get("label")) != category_key:
            continue
        for attribute in category.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            if _normalize_key(attribute.get("id") or attribute.get("label")) == attribute_id:
                return attribute
    raise ValueError(f"Unknown taxonomy location: {category_key}/{attribute_id}")


def _find_leaf(attribute: Mapping[str, Any], *, value_id: str) -> dict[str, Any]:
    for node in _iter_leaf_nodes(attribute.get("nodes") or []):
        if _normalize_key(node.get("id") or node.get("label")) == value_id:
            return node
    raise ValueError(f"Unknown taxonomy value: {value_id}")


def _ensure_editable_leaf(node: Mapping[str, Any]) -> None:
    value_id = _normalize_key(node.get("id") or node.get("label"))
    if value_id in {"unknown", "other"}:
        raise ValueError(f"Reserved taxonomy value cannot be edited: {value_id}")


def _normalized_synonym_index(node: Mapping[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    for synonym in node.get("synonyms") or []:
        normalized = _normalize_text(synonym)
        if normalized:
            index[normalized] = str(synonym).strip()
    return index


def _set_synonyms(node: dict[str, Any], values: Iterable[str]) -> None:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        normalized = _normalize_text(text)
        if not normalized or normalized in seen:
            continue
        cleaned.append(text)
        seen.add(normalized)
    if cleaned:
        node["synonyms"] = cleaned
    else:
        node.pop("synonyms", None)


def _remove_leaf(nodes: list[Any], *, value_id: str) -> bool:
    for index, node in enumerate(list(nodes)):
        if not isinstance(node, dict):
            continue
        children = node.get("children")
        if isinstance(children, list) and children:
            if _remove_leaf(children, value_id=value_id):
                return True
            continue
        if _normalize_key(node.get("id") or node.get("label")) == value_id:
            del nodes[index]
            return True
    return False


def _replace_leaf(
    nodes: list[Any],
    *,
    value_id: str,
    replacements: list[dict[str, Any]],
) -> bool:
    for index, node in enumerate(list(nodes)):
        if not isinstance(node, dict):
            continue
        children = node.get("children")
        if isinstance(children, list) and children:
            if _replace_leaf(children, value_id=value_id, replacements=replacements):
                return True
            continue
        if _normalize_key(node.get("id") or node.get("label")) == value_id:
            nodes[index : index + 1] = replacements
            return True
    return False


def _collect_leaf_ids(attribute: Mapping[str, Any]) -> set[str]:
    return {
        _normalize_key(node.get("id") or node.get("label"))
        for node in _iter_leaf_nodes(attribute.get("nodes") or [])
        if _normalize_key(node.get("id") or node.get("label"))
    }


def _leaf_nodes_list(attribute: dict[str, Any]) -> list[Any]:
    nodes = attribute.get("nodes")
    if isinstance(nodes, list):
        return nodes
    attribute["nodes"] = []
    return attribute["nodes"]


def _normalized_new_value_labels(payload: Mapping[str, Any]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in payload.get("new_value_labels") or []:
        label = str(item).strip()
        normalized = _normalize_key(label)
        if not label or not normalized or normalized in seen:
            continue
        cleaned.append(label)
        seen.add(normalized)
    return cleaned


def _require_term(payload: Mapping[str, Any]) -> str:
    term_text = str(payload.get("term_text") or "").strip()
    if not term_text:
        raise ValueError("Proposal requires term_text.")
    return term_text


def apply_user_taxonomy_proposal(
    taxonomy: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposal_type = _normalize_key(payload.get("proposal_type"))
    if proposal_type not in PREVIEWABLE_USER_PROPOSAL_TYPES:
        raise ValueError(f"Unsupported draft-apply proposal type: {proposal_type}")

    category_key = _normalize_key(payload.get("category_key"))
    attribute_id = _normalize_key(payload.get("attribute_id"))
    value_id = _normalize_key(payload.get("value_id"))
    if not category_key or not attribute_id:
        raise ValueError("Proposal requires category_key and attribute_id.")

    draft = copy.deepcopy(dict(taxonomy))
    attribute = _find_attribute(draft, category_key=category_key, attribute_id=attribute_id)
    summary: dict[str, Any] = {
        "proposal_type": proposal_type,
        "category_key": category_key,
        "attribute_id": attribute_id,
    }

    if proposal_type == "add_value":
        new_label = str(payload.get("new_label") or "").strip()
        if not new_label:
            raise ValueError("add_value requires new_label.")
        if bool(attribute.get("hierarchical")):
            raise ValueError(
                "add_value is currently supported only for non-hierarchical attributes; V1 creates root-level leaves only."
            )
        new_value_id = _normalize_key(new_label)
        if not new_value_id:
            raise ValueError("add_value requires a usable new_label.")
        if new_value_id in {"unknown", "other"}:
            raise ValueError(f"Reserved taxonomy value cannot be created: {new_value_id}")
        if new_value_id in _collect_leaf_ids(attribute):
            raise ValueError(f"Taxonomy value already exists: {new_value_id}")
        _leaf_nodes_list(attribute).append({"id": new_value_id, "label": new_label})
        summary["value_id"] = new_value_id
        summary["new_label"] = new_label
        summary["created_value_id"] = new_value_id
        return draft, summary

    if not value_id:
        raise ValueError("Proposal requires value_id.")
    summary["value_id"] = value_id
    source_leaf = _find_leaf(attribute, value_id=value_id)
    _ensure_editable_leaf(source_leaf)

    if proposal_type == "rename_value":
        new_label = str(payload.get("new_label") or "").strip()
        if not new_label:
            raise ValueError("rename_value requires new_label.")
        previous_label = str(source_leaf.get("label") or source_leaf.get("id") or "").strip()
        if _normalize_text(previous_label) == _normalize_text(new_label):
            raise ValueError("rename_value requires a different label.")
        source_leaf["label"] = new_label
        summary["before_label"] = previous_label
        summary["after_label"] = new_label
        return draft, summary

    if proposal_type == "merge_values":
        target_ids = [
            _normalize_key(item)
            for item in (payload.get("target_value_ids") or [])
            if _normalize_key(item)
        ]
        if len(target_ids) != 1:
            raise ValueError("merge_values requires exactly one target_value_id.")
        target_leaf = _find_leaf(attribute, value_id=target_ids[0])
        _ensure_editable_leaf(target_leaf)
        target_value_id = _normalize_key(target_leaf.get("id") or target_leaf.get("label"))
        if target_value_id == value_id:
            raise ValueError("merge_values requires a different target value.")
        removed = _remove_leaf(attribute.get("nodes") or [], value_id=value_id)
        if not removed:
            raise ValueError(f"Unknown taxonomy value: {value_id}")
        summary["target_value_id"] = target_value_id
        summary["source_label"] = str(source_leaf.get("label") or source_leaf.get("id") or "").strip()
        summary["target_label"] = str(target_leaf.get("label") or target_leaf.get("id") or "").strip()
        summary["synonym_transfer_mode"] = "none"
        return draft, summary

    if proposal_type == "split_value":
        target_ids = [
            _normalize_key(item)
            for item in (payload.get("target_value_ids") or [])
            if _normalize_key(item)
        ]
        unique_target_ids = list(dict.fromkeys(target_ids))
        new_value_labels = _normalized_new_value_labels(payload)
        existing_leaf_ids = _collect_leaf_ids(attribute)
        existing_leaf_ids.discard(value_id)
        target_labels: list[str] = []
        created_nodes: list[dict[str, Any]] = []
        created_value_ids: list[str] = []
        seen_target_ids: set[str] = set()
        for target_id in unique_target_ids:
            if target_id == value_id:
                raise ValueError("split_value target values must differ from the source value.")
            target_leaf = _find_leaf(attribute, value_id=target_id)
            _ensure_editable_leaf(target_leaf)
            seen_target_ids.add(target_id)
            target_labels.append(
                str(target_leaf.get("label") or target_leaf.get("id") or "").strip()
            )
        for label in new_value_labels:
            target_id = _normalize_key(label)
            if target_id == value_id:
                raise ValueError("split_value target values must differ from the source value.")
            if target_id in existing_leaf_ids:
                raise ValueError(
                    f"split_value target value already exists: {target_id}. Use target_value_ids instead."
                )
            if target_id in seen_target_ids:
                continue
            seen_target_ids.add(target_id)
            created_value_ids.append(target_id)
            target_labels.append(label)
            created_nodes.append({"id": target_id, "label": label})
        if len(seen_target_ids) < 2:
            raise ValueError(
                "split_value requires at least two total targets across target_value_ids and new_value_labels."
            )
        replaced = _replace_leaf(
            attribute.get("nodes") or [],
            value_id=value_id,
            replacements=created_nodes,
        )
        if not replaced:
            raise ValueError(f"Unknown taxonomy value: {value_id}")
        summary["target_value_ids"] = [*unique_target_ids, *created_value_ids]
        summary["target_labels"] = target_labels
        summary["created_value_ids"] = created_value_ids
        summary["created_labels"] = new_value_labels
        summary["source_label"] = str(source_leaf.get("label") or source_leaf.get("id") or "").strip()
        summary["synonym_transfer_mode"] = "none"
        return draft, summary

    term_text = _require_term(payload)
    normalized_term = _normalize_text(term_text)
    label_text = str(source_leaf.get("label") or source_leaf.get("id") or "").strip()
    if normalized_term == _normalize_text(label_text):
        raise ValueError("Term matches the current value label and cannot be edited as a synonym.")

    current_index = _normalized_synonym_index(source_leaf)

    if proposal_type == "add_synonym":
        if normalized_term in current_index:
            raise ValueError("Synonym already exists on the selected value.")
        _set_synonyms(source_leaf, [*(source_leaf.get("synonyms") or []), term_text])
        summary["term_text"] = term_text
        return draft, summary

    if normalized_term not in current_index:
        raise ValueError("Selected synonym does not exist on the source value.")

    if proposal_type == "remove_synonym":
        remaining = [
            synonym
            for synonym in (source_leaf.get("synonyms") or [])
            if _normalize_text(synonym) != normalized_term
        ]
        _set_synonyms(source_leaf, remaining)
        summary["term_text"] = current_index[normalized_term]
        return draft, summary

    target_ids = [
        _normalize_key(item)
        for item in (payload.get("target_value_ids") or [])
        if _normalize_key(item)
    ]
    if len(target_ids) != 1:
        raise ValueError("move_synonym requires exactly one target_value_id.")
    target_leaf = _find_leaf(attribute, value_id=target_ids[0])
    _ensure_editable_leaf(target_leaf)
    if _normalize_key(target_leaf.get("id") or target_leaf.get("label")) == value_id:
        raise ValueError("move_synonym requires a different target value.")
    target_label = str(target_leaf.get("label") or target_leaf.get("id") or "").strip()
    if normalized_term == _normalize_text(target_label):
        raise ValueError("Synonym matches the target value label.")

    remaining = [
        synonym
        for synonym in (source_leaf.get("synonyms") or [])
        if _normalize_text(synonym) != normalized_term
    ]
    _set_synonyms(source_leaf, remaining)
    target_synonyms = list(target_leaf.get("synonyms") or [])
    if normalized_term not in _normalized_synonym_index(target_leaf):
        target_synonyms.append(current_index[normalized_term])
    _set_synonyms(target_leaf, target_synonyms)
    summary["term_text"] = current_index[normalized_term]
    summary["target_value_id"] = target_ids[0]
    return draft, summary
