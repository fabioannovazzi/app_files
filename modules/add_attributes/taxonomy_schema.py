from __future__ import annotations

"""
Branch-local taxonomy schema, normalization and validation utilities.

Goals
- Enforce consistent structure and types (booleans, levels, IDs).
- Keep parents structure-only (no synonyms on non-leaf nodes).
- Ensure 'unknown' vs 'other' (labelled "not in taxonomy") leaves exist for selectable attributes.
- Canonicalize synonyms (lowercase, trimmed, de-duped, unicode fixed).
- Prevent intra-attribute synonym collisions (a synonym maps to one node).

This module is intentionally self-contained and does not apply any
cross-category centralization. Use it to validate a single generated
branch before persisting it to the taxonomy JSON.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ftfy import fix_text
from pydantic import BaseModel, Field, ValidationError, model_validator
from .policies import budgets as _default_budgets


LOGGER = logging.getLogger(__name__)

__all__ = [
    "Node",
    "Attribute",
    "Branch",
    "canonicalize_branch",
    "validate_branch",
    "branch_metrics",
]


ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
LEAF_STATUS_VALUES = {"active", "draft", "needs_review", "deprecated"}
GOVERNANCE_ACTION_VALUES = {"merge", "split"}


def _is_snake_case(value: str) -> bool:
    return bool(ID_PATTERN.match(value))


def _norm_text(s: str) -> str:
    """Normalize general text for labels.

    - Fix broken Unicode and strip zero-width chars.
    - Normalize dashes/minus to ASCII hyphen; map multiplication sign to 'x'.
    - Drop common trademark symbols.
    - Collapse internal whitespace; trim outer wrapping quotes/parentheses.
    - Trim trailing sentence punctuation (.,;:).
    """
    s = fix_text(str(s))
    # Strip zero-width characters
    s = s.replace("\u200b", "")
    # Normalize hyphens/dashes and minus sign to ASCII hyphen
    s = s.replace("\u2013", "-")  # en dash
    s = s.replace("\u2014", "-")  # em dash
    s = s.replace("\u2212", "-")  # minus sign
    # Normalize multiplication sign to 'x'
    s = s.replace("\u00D7", "x")
    # Drop common trademark-like symbols
    s = s.replace("\u2122", "")  # ™
    s = s.replace("\u00AE", "")  # ®
    s = s.replace("\u00A9", "")  # ©
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Strip wrapping quotes or parentheses if they wrap the entire token
    if (s.startswith("(") and s.endswith(")")) or (
        s.startswith("[") and s.endswith("]")
    ):
        inner = s[1:-1].strip()
        if inner:
            s = inner
    if (s.startswith("'") and s.endswith("'")) or (
        s.startswith('"') and s.endswith('"')
    ):
        inner = s[1:-1].strip()
        if inner:
            s = inner
    # Trim trailing light punctuation
    s = re.sub(r"[\.,;:]+$", "", s).strip()
    return s

def _sentence_case_if_all_caps(text: str) -> str:
    """Convert ALL‑CAPS labels to Sentence case, preserving reserved labels.

    Reserved labels kept as-is:
    - "N/A (not stated)"
    - "not in taxonomy"

    For other strings, if all cased characters are uppercase (e.g., "MATTE",
    "LONG WEAR", "SPF 50"), convert to "Matte", "Long wear", "Spf 50".
    """
    try:
        s = str(text)
    except Exception:
        return text
    if s in {"N/A (not stated)", "not in taxonomy"}:
        return s
    # isupper() returns True iff there is at least one cased char and all cased
    # chars are uppercase; non-letters (digits, punctuation) are ignored.
    if not s.isupper():
        return s
    # Convert to sentence case
    out = s[:1].upper() + s[1:].lower()
    # Restore known acronyms (case-insensitive)
    ACRONYMS = {
        r"\bspf\b": "SPF",
        r"\buva/uvb\b": "UVA/UVB",
        r"\buva-uvb\b": "UVA-UVB",
        r"\buva uvb\b": "UVA UVB",
    }
    for pat, repl in ACRONYMS.items():
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    # Preserve common mixed tokens with digits/hyphens
    # 24k -> 24K, 3d -> 3D (but avoid 1080p)
    out = re.sub(r"\b(\d+)([kd])\b", lambda m: m.group(1) + m.group(2).upper(), out)
    # usb-c -> USB-C, pci-e -> PCI-E (avoid wi-fi because first part len=2)
    out = re.sub(r"\b([a-z]{3,}-[a-z])\b", lambda m: m.group(0).upper(), out, flags=re.IGNORECASE)
    # hdmi-cec -> HDMI-CEC
    out = re.sub(r"\bhdmi-[a-z0-9]+\b", lambda m: m.group(0).upper(), out, flags=re.IGNORECASE)
    # explicit short forms
    out = re.sub(r"\b3d\b", "3D", out, flags=re.IGNORECASE)
    out = re.sub(r"\b4k\b", "4K", out, flags=re.IGNORECASE)
    return out


def _norm_synonym(s: str) -> str:
    """Return a canonical synonym token.

    - Fix broken unicode and trim via ``_norm_text``.
    - Lowercase.
    - Normalize hyphen-like punctuation and underscores to spaces so
      variants like "semi-matte" / "semi matte" / "semi_matte" collapse.
    - Collapse internal whitespace to a single space.
    """
    s = _norm_text(s)
    # Lowercase first so normalization is consistent
    s = s.lower()
    # Normalize ASCII hyphen, underscores, and common Unicode hyphens/dashes/minus to spaces
    s = s.replace("\u2212", "-")  # minus sign -> hyphen first
    s = s.replace("\u00D7", "x")   # multiplication sign -> x
    s = re.sub(r"[-_\u2010-\u2015]+", " ", s)
    # Collapse internal whitespace
    s = " ".join(s.split())
    # Strip wrapping quotes or parentheses when they wrap the entire token
    if (s.startswith("(") and s.endswith(")")) or (
        s.startswith("[") and s.endswith("]")
    ):
        inner = s[1:-1].strip()
        if inner:
            s = inner
    if (s.startswith("'") and s.endswith("'")) or (
        s.startswith('"') and s.endswith('"')
    ):
        inner = s[1:-1].strip()
        if inner:
            s = inner
    # Trim trailing light punctuation
    s = re.sub(r"[\.,;:]+$", "", s).strip()
    return s


def _norm_id_token(value: str) -> str:
    return _norm_text(value).strip().lower().replace(" ", "_")


def _norm_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _norm_text(value)
    return normalized or None


def _is_single_token_label(value: str) -> bool:
    token = _norm_synonym(value)
    return bool(token) and len(token.split()) == 1


def _is_reserved_leaf(node_id: str, label: str) -> bool:
    node_id_norm = str(node_id).strip().lower()
    label_norm = str(label).strip().lower()
    return node_id_norm in {"unknown", "other"} or label_norm in {
        "n/a (not stated)",
        "not in taxonomy",
    }


class Node(BaseModel):
    id: str
    label: str
    synonyms: Optional[List[str]] = None
    status: Optional[str] = None
    governance_action: Optional[str] = None
    successor_leaf_ids: Optional[List[str]] = None
    replacement_leaf_id: Optional[str] = Field(default=None, exclude=True)
    governance_reason: Optional[str] = None
    children: Optional[List["Node"]] = None

    @model_validator(mode="after")
    def _validate_self(self) -> "Node":  # type: ignore[override]
        # ids should be snake_case, except for reserved leaves 'unknown'/'other'
        if self.id not in {"unknown", "other"} and not _is_snake_case(self.id):
            raise ValueError(f"node.id must be snake_case: {self.id}")
        # normalize label
        self.label = _norm_text(self.label)
        self.label = _sentence_case_if_all_caps(self.label)
        # normalize synonyms
        if self.synonyms:
            self.synonyms = sorted({
                _norm_synonym(s) for s in self.synonyms if str(s).strip()
            })
            # remove any synonym identical to label (case-insensitive)
            self.synonyms = [s for s in self.synonyms if s != self.label.lower()]
        if self.status is not None:
            normalized_status = str(self.status).strip().lower()
            if normalized_status not in LEAF_STATUS_VALUES:
                raise ValueError(
                    f"node.status must be one of {sorted(LEAF_STATUS_VALUES)}: {self.id}"
                )
            self.status = normalized_status
        if self.governance_action is not None:
            normalized_action = str(self.governance_action).strip().lower()
            if not normalized_action:
                self.governance_action = None
            elif normalized_action not in GOVERNANCE_ACTION_VALUES:
                raise ValueError(
                    "node.governance_action must be one of "
                    f"{sorted(GOVERNANCE_ACTION_VALUES)}: {self.id}"
                )
            else:
                self.governance_action = normalized_action
        successor_ids: list[str] = []
        for successor_leaf_id in self.successor_leaf_ids or []:
            normalized_successor = _norm_id_token(str(successor_leaf_id))
            if normalized_successor and normalized_successor not in successor_ids:
                successor_ids.append(normalized_successor)
        self.successor_leaf_ids = successor_ids or None
        if self.replacement_leaf_id is not None:
            replacement_leaf_id = _norm_id_token(str(self.replacement_leaf_id))
            if not replacement_leaf_id:
                self.replacement_leaf_id = None
            else:
                self.replacement_leaf_id = replacement_leaf_id
                if self.successor_leaf_ids:
                    if self.governance_action not in {None, "merge"}:
                        raise ValueError(
                            "legacy replacement_leaf_id conflicts with governance_action "
                            f"for node: {self.id}"
                        )
                    if self.successor_leaf_ids != [replacement_leaf_id]:
                        raise ValueError(
                            "legacy replacement_leaf_id conflicts with successor_leaf_ids "
                            f"for node: {self.id}"
                        )
                else:
                    self.successor_leaf_ids = [replacement_leaf_id]
                    if self.governance_action is None:
                        self.governance_action = "merge"
        if self.governance_action is None and self.successor_leaf_ids:
            self.governance_action = (
                "merge" if len(self.successor_leaf_ids) == 1 else "split"
            )
        if self.governance_action is not None and not self.successor_leaf_ids:
            raise ValueError(
                f"node.governance_action requires successor_leaf_ids: {self.id}"
            )
        if self.governance_action == "merge" and len(self.successor_leaf_ids or []) != 1:
            raise ValueError(
                f"node.governance_action='merge' requires exactly one successor: {self.id}"
            )
        if self.governance_action == "split" and len(self.successor_leaf_ids or []) < 2:
            raise ValueError(
                f"node.governance_action='split' requires at least two successors: {self.id}"
            )
        self.governance_reason = _norm_optional_text(self.governance_reason)
        # parents must be structure-only (no synonyms)
        if self.children:
            if self.synonyms:
                # make it a hard error here; auto-pruning happens in normalization path
                raise ValueError(
                    f"parent node must not carry synonyms: {self.id}"
                )
            if self.status is not None:
                raise ValueError(f"parent node must not carry status: {self.id}")
            if self.governance_action is not None:
                raise ValueError(
                    f"parent node must not carry governance_action: {self.id}"
                )
            if self.successor_leaf_ids is not None:
                raise ValueError(
                    f"parent node must not carry successor_leaf_ids: {self.id}"
                )
            if self.replacement_leaf_id is not None:
                raise ValueError(
                    f"parent node must not carry replacement_leaf_id: {self.id}"
                )
            if self.governance_reason is not None:
                raise ValueError(
                    f"parent node must not carry governance_reason: {self.id}"
                )
            # normalize children recursively
            self.children = [Node.model_validate(ch) for ch in self.children]
            return self
        if _is_reserved_leaf(self.id, self.label):
            if self.status in {"draft", "needs_review", "deprecated"}:
                raise ValueError(
                    f"reserved leaf '{self.id}' cannot use status '{self.status}'"
                )
            if self.governance_action is not None or self.successor_leaf_ids:
                raise ValueError(
                    f"reserved leaf '{self.id}' cannot carry governance successors"
                )
        if self.successor_leaf_ids and self.id in set(self.successor_leaf_ids):
            raise ValueError(
                f"node.successor_leaf_ids must not point to self: {self.id}"
            )
        if (self.status or "active") == "active" and (
            self.governance_action is not None or self.successor_leaf_ids
        ):
            raise ValueError(
                f"active leaf '{self.id}' must not carry governance successors"
            )
        self.replacement_leaf_id = None
        return self


class Attribute(BaseModel):
    id: str
    label: str
    hierarchical: bool = Field(description="True if the attribute has a 2-level tree")
    levels: Optional[int] = None
    # Optional governance metadata
    selection: Optional[str] = Field(
        default=None, description="Value cardinality: 'single' or 'multi'"
    )
    scope: Optional[str] = Field(
        default=None, description="Scope of the value: 'product' or 'variant'"
    )
    kind: Optional[str] = Field(
        default=None,
        description="Semantic kind: 'composition' | 'performance' | 'regulatory'",
    )
    nodes: List[Node]

    @model_validator(mode="after")
    def _validate_attr(self) -> "Attribute":  # type: ignore[override]
        if not _is_snake_case(self.id):
            raise ValueError(f"attribute.id must be snake_case: {self.id}")
        self.label = _norm_text(self.label)
        self.label = _sentence_case_if_all_caps(self.label)

        # levels only makes sense when hierarchical
        if self.hierarchical:
            if self.levels is None:
                self.levels = 2
            elif self.levels != 2:
                raise ValueError("hierarchical attributes must have levels=2")
        else:
            if self.levels not in (None, 1):
                raise ValueError("non-hierarchical attributes must have levels=1 or None")
            self.levels = 1

        # validate optional governance fields if present
        if self.selection is not None:
            if self.selection not in {"single", "multi"}:
                raise ValueError("selection must be 'single' or 'multi'")
        if self.scope is not None:
            if self.scope not in {"product", "variant"}:
                raise ValueError("scope must be 'product' or 'variant'")
        if self.kind is not None:
            if self.kind not in {"composition", "performance", "regulatory"}:
                raise ValueError("kind must be 'composition' | 'performance' | 'regulatory'")

        # ensure 'unknown' and 'other' nodes exist at top level
        node_ids = {n.id for n in self.nodes}
        if "unknown" not in node_ids:
            self.nodes.append(Node(id="unknown", label="N/A (not stated)", synonyms=None))
        if "other" not in node_ids:
            self.nodes.append(Node(id="other", label="not in taxonomy", synonyms=None))

        # For flat attributes ensure no children exist
        if not self.hierarchical:
            for n in self.nodes:
                if n.children:
                    raise ValueError(
                        f"flat attribute '{self.id}' must not include children"
                    )

        # enforce synonym uniqueness across leaf nodes
        seen: Dict[str, str] = {}
        leaf_ids: Set[str] = set()
        governance_specs: List[Tuple[str, str, List[str]]] = []

        def _collect_leaf_ids(node: Node) -> None:
            if node.children:
                for child in node.children:
                    _collect_leaf_ids(child)
                return
            leaf_ids.add(node.id)
            if node.governance_action and node.successor_leaf_ids:
                governance_specs.append(
                    (node.id, node.governance_action, list(node.successor_leaf_ids))
                )

        for n in self.nodes:
            _collect_leaf_ids(n)
            if n.children:
                # parent: all children already validated
                continue
            for syn in (n.synonyms or []):
                owner = seen.get(syn)
                if owner and owner != n.id:
                    raise ValueError(
                        f"duplicate synonym '{syn}' across nodes '{owner}' and '{n.id}' in attribute '{self.id}'"
                    )
                seen[syn] = n.id

        effective_selection = self.selection or "single"
        for node_id, governance_action, successor_leaf_ids in governance_specs:
            for successor_leaf_id in successor_leaf_ids:
                if successor_leaf_id not in leaf_ids:
                    raise ValueError(
                        "successor_leaf_ids must point to existing leaves "
                        f"in attribute '{self.id}': {node_id} -> {successor_leaf_id}"
                    )
            if governance_action == "split" and effective_selection != "multi":
                raise ValueError(
                    "governance_action='split' requires selection='multi' "
                    f"for attribute '{self.id}'"
                )

        return self


class Branch(BaseModel):
    id: str
    label: str
    attributes: List[Attribute]
    guidance: Optional[str] = None

    @model_validator(mode="after")
    def _validate_branch(self) -> "Branch":  # type: ignore[override]
        if not _is_snake_case(self.id):
            raise ValueError(f"branch.id must be snake_case: {self.id}")
        self.label = _norm_text(self.label)
        self.label = _sentence_case_if_all_caps(self.label)
        if self.guidance:
            self.guidance = _norm_text(self.guidance)
        # enforce unique attribute IDs
        ids = [a.id for a in self.attributes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate attribute ids in branch")
        return self


# --------------------------
# Public helpers
# --------------------------


def canonicalize_branch(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a normalized copy of a draft branch dict.

    - Coerce booleans for 'hierarchical' (accepts 'true'/'false').
    - Normalize IDs, labels, synonyms; strip parent synonyms.
    - Ensure unknown/not-in-taxonomy nodes exist.
    - De-duplicate synonyms per node.
    """
    def coerce_bool(v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() == "true"
        return bool(v)

    branch: Dict[str, Any] = {
        "id": _norm_text(str(data.get("id", "")).strip() or "unknown_category").lower().replace(" ", "_"),
        "label": _norm_text(data.get("label") or data.get("id") or ""),
        "attributes": [],
    }
    if isinstance(data.get("guidance"), str):
        branch["guidance"] = _norm_text(str(data.get("guidance")))

    for a in (data.get("attributes") or []):
        attr_id = _norm_text(str(a.get("id", "")).strip() or "").lower().replace(" ", "_")
        attr_label = _norm_text(a.get("label") or a.get("id") or attr_id)
        hierarchical = coerce_bool(a.get("hierarchical", False))
        levels = a.get("levels")
        selection = a.get("selection") if isinstance(a.get("selection"), str) else None
        scope = a.get("scope") if isinstance(a.get("scope"), str) else None
        kind = a.get("kind") if isinstance(a.get("kind"), str) else None

        nodes: List[Dict[str, Any]] = []
        for n in (a.get("nodes") or []):
            node_id = _norm_text(str(n.get("id", "")).strip() or "").lower().replace(" ", "_")
            node_label = _norm_text(n.get("label") or n.get("id") or node_id)
            children = n.get("children") or []
            # strip synonyms on parents; keep on leaves only
            syns: List[str] = []
            status = None
            governance_action = None
            successor_leaf_ids = None
            governance_reason = None
            status_raw = n.get("status")
            if status_raw is not None:
                normalized_status = str(status_raw).strip().lower()
                if normalized_status:
                    status = normalized_status
            governance_action_raw = n.get("governance_action")
            if governance_action_raw is not None:
                normalized_action = str(governance_action_raw).strip().lower()
                if normalized_action:
                    governance_action = normalized_action
            successor_raw = n.get("successor_leaf_ids")
            if isinstance(successor_raw, list):
                successor_leaf_ids = []
                for successor_leaf_id in successor_raw:
                    normalized_successor = _norm_id_token(str(successor_leaf_id))
                    if (
                        normalized_successor
                        and normalized_successor not in successor_leaf_ids
                    ):
                        successor_leaf_ids.append(normalized_successor)
                if not successor_leaf_ids:
                    successor_leaf_ids = None
            replacement_raw = n.get("replacement_leaf_id")
            if replacement_raw is not None:
                normalized_replacement = _norm_id_token(str(replacement_raw))
                if normalized_replacement:
                    successor_leaf_ids = [normalized_replacement]
                    if governance_action is None:
                        governance_action = "merge"
            if governance_action is None and successor_leaf_ids:
                governance_action = (
                    "merge" if len(successor_leaf_ids) == 1 else "split"
                )
            governance_reason = _norm_optional_text(
                str(n.get("governance_reason"))
                if n.get("governance_reason") is not None
                else None
            )
            if not children:
                syns = [
                    _norm_synonym(s)
                    for s in (n.get("synonyms") or [])
                    if str(s).strip()
                ]
                # remove duplicate synonyms and those identical to label
                if syns:
                    syns = sorted({s for s in syns if s != node_label.lower()})
            child_nodes: Optional[List[Dict[str, Any]]] = None
            if children:
                child_nodes = []
                for ch in children:
                    ch_id = _norm_text(str(ch.get("id", "")).strip() or "").lower().replace(" ", "_")
                    ch_label = _norm_text(ch.get("label") or ch.get("id") or ch_id)
                    ch_syns = [
                        _norm_synonym(s)
                        for s in (ch.get("synonyms") or [])
                        if str(s).strip()
                    ]
                    if ch_syns:
                        ch_syns = sorted({s for s in ch_syns if s != ch_label.lower()})
                    child_node: Dict[str, Any] = {"id": ch_id, "label": ch_label}
                    if ch_syns:
                        child_node["synonyms"] = ch_syns
                    ch_status_raw = ch.get("status")
                    if ch_status_raw is not None:
                        ch_status = str(ch_status_raw).strip().lower()
                        if ch_status:
                            child_node["status"] = ch_status
                    ch_action_raw = ch.get("governance_action")
                    ch_action = None
                    if ch_action_raw is not None:
                        normalized_ch_action = str(ch_action_raw).strip().lower()
                        if normalized_ch_action:
                            ch_action = normalized_ch_action
                    ch_successors_raw = ch.get("successor_leaf_ids")
                    ch_successors = None
                    if isinstance(ch_successors_raw, list):
                        ch_successors = []
                        for successor_leaf_id in ch_successors_raw:
                            normalized_successor = _norm_id_token(
                                str(successor_leaf_id)
                            )
                            if (
                                normalized_successor
                                and normalized_successor not in ch_successors
                            ):
                                ch_successors.append(normalized_successor)
                        if not ch_successors:
                            ch_successors = None
                    ch_replacement_raw = ch.get("replacement_leaf_id")
                    if ch_replacement_raw is not None:
                        ch_replacement = _norm_id_token(str(ch_replacement_raw))
                        if ch_replacement:
                            ch_successors = [ch_replacement]
                            if ch_action is None:
                                ch_action = "merge"
                    if ch_action is None and ch_successors:
                        ch_action = (
                            "merge" if len(ch_successors) == 1 else "split"
                        )
                    if ch_action:
                        child_node["governance_action"] = ch_action
                    if ch_successors:
                        child_node["successor_leaf_ids"] = ch_successors
                    ch_reason = _norm_optional_text(
                        str(ch.get("governance_reason"))
                        if ch.get("governance_reason") is not None
                        else None
                    )
                    if ch_reason:
                        child_node["governance_reason"] = ch_reason
                    child_nodes.append(child_node)
            node_obj: Dict[str, Any] = {"id": node_id, "label": node_label}
            if syns:
                node_obj["synonyms"] = syns
            if status is not None:
                node_obj["status"] = status
            if governance_action is not None:
                node_obj["governance_action"] = governance_action
            if successor_leaf_ids is not None:
                node_obj["successor_leaf_ids"] = successor_leaf_ids
            if governance_reason:
                node_obj["governance_reason"] = governance_reason
            if child_nodes:
                node_obj["children"] = child_nodes
            nodes.append(node_obj)

        # ensure unknown/not-in-taxonomy
        top_ids = {n.get("id") for n in nodes}
        if "unknown" not in top_ids:
            nodes.append({"id": "unknown", "label": "N/A (not stated)"})
        if "other" not in top_ids:
            nodes.append({"id": "other", "label": "not in taxonomy"})

        branch["attributes"].append(
            {
                "id": attr_id,
                "label": attr_label,
                "hierarchical": hierarchical,
                "levels": levels,
                "selection": selection,
                "scope": scope,
                "kind": kind,
                "nodes": nodes,
            }
        )

    return branch


def _enforce_budgets(branch: Dict[str, Any], caps: Dict[str, int], warnings: List[str]) -> None:
    """Prune excessive synonyms and leaf nodes deterministically per budgets.

    - Keeps 'unknown' and 'other' ("not in taxonomy") leaves regardless of caps.
    - For synonyms, keeps the first K after canonical sorting.
    - For leaves, keeps the first K by label (ascending). Works for both flat and
      hierarchical attributes by pruning at the appropriate level.
    """
    max_nodes = int(caps.get("max_nodes_per_attribute", 0) or 0)
    max_syns = int(caps.get("max_synonyms_per_node", 0) or 0)

    for attr in branch.get("attributes", []):
        # Cap synonyms per leaf
        if max_syns > 0:
            for n in attr.get("nodes", []):
                # leaf
                if not n.get("children"):
                    syns = n.get("synonyms") or []
                    if max_syns and len(syns) > max_syns:
                        kept = syns[:max_syns]
                        if len(kept) != len(syns):
                            warnings.append(
                                f"pruned synonyms for {attr.get('id')}:{n.get('id')} to {max_syns}"
                            )
                        if kept:
                            n["synonyms"] = kept
                        else:
                            if "synonyms" in n:
                                del n["synonyms"]
                else:
                    # children leaves
                    for ch in n.get("children", []) or []:
                        syns = ch.get("synonyms") or []
                        if max_syns and len(syns) > max_syns:
                            kept = syns[:max_syns]
                            if len(kept) != len(syns):
                                warnings.append(
                                    f"pruned synonyms for {attr.get('id')}:{ch.get('id')} to {max_syns}"
                                )
                            if kept:
                                ch["synonyms"] = kept
                            else:
                                if "synonyms" in ch:
                                    del ch["synonyms"]

        # Cap number of leaves per attribute
        if max_nodes > 0:
            # Gather all leaves excluding reserved ones
            leaves: List[Tuple[List[Dict[str, Any]], int]] = []
            def collect_leaves(parent_list: List[Dict[str, Any]]):
                for idx, node in enumerate(parent_list):
                    if node.get("children"):
                        collect_leaves(node.get("children") or [])
                    else:
                        if node.get("id") in {"unknown", "other"}:
                            continue
                        leaves.append((parent_list, idx))

            collect_leaves(attr.get("nodes", []))
            if len(leaves) > max_nodes:
                # Sort candidates by label for deterministic pruning
                labeled: List[Tuple[str, List[Dict[str, Any]], int]] = []
                for parent_list, idx in leaves:
                    n = parent_list[idx]
                    labeled.append((str(n.get("label", "")).lower(), parent_list, idx))
                labeled.sort(key=lambda x: x[0])
                # Keep the first K; remove the rest from their parents (in reverse index order per parent)
                to_remove = set(id(x) for x in labeled[max_nodes:])
                # group by parent_list identity to delete safely
                buckets: Dict[int, List[int]] = {}
                for entry in labeled[max_nodes:]:
                    _, plist, idx = entry
                    buckets.setdefault(id(plist), []).append(idx)
                for plist_id, idxs in buckets.items():
                    # find the actual list object by matching id
                    target = None
                    # scan possible references (attr nodes and any children).
                    # exact identity matches retained in closure; here we just reuse the saved list
                    for parent_list, _ in leaves:
                        if id(parent_list) == plist_id:
                            target = parent_list
                            break
                    if target is None:
                        continue
                    for i in sorted(set(idxs), reverse=True):
                        try:
                            target.pop(i)
                        except Exception as e:
                            LOGGER.exception(
                                "Failed to prune leaf at index %d: %s", i, e
                            )
                warnings.append(
                    f"pruned leaf nodes for attribute {attr.get('id')} to {max_nodes}"
                )


def branch_metrics(branch: Dict[str, Any]) -> Dict[str, int]:
    """Compute simple metrics to track branch size and complexity."""
    attr_count = len(branch.get("attributes", []))
    leaf_count = 0
    synonym_count = 0
    for attr in branch.get("attributes", []):
        for n in attr.get("nodes", []):
            if n.get("children"):
                for ch in n.get("children") or []:
                    leaf_count += 1
                    synonym_count += len(ch.get("synonyms") or [])
            else:
                leaf_count += 1
                synonym_count += len(n.get("synonyms") or [])
    return {
        "attributes": attr_count,
        "leaves": leaf_count,
        "synonyms": synonym_count,
    }


def validate_branch(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Normalize and validate a branch. Returns (normalized_branch, warnings).

    The function will auto-prune some issues (e.g., duplicated synonyms within
    a node) and raise on structural errors. It also enforces synonym uniqueness
    across leaf nodes per attribute by dropping later duplicates deterministically
    and emitting a warning.
    """
    warnings: List[str] = []
    branch = canonicalize_branch(data)

    # De-duplicate duplicate leaf nodes deterministically within each attribute
    try:
        for attr in branch.get("attributes", []) or []:
            nodes = attr.get("nodes") or []
            # Deduplicate flat leaves at top level
            seen_top: Set[Tuple[str, str]] = set()
            dedup_top: List[Dict[str, Any]] = []
            for n in nodes:
                children = n.get("children")
                if children:
                    # Deduplicate children by (id,label)
                    seen_ch: Set[Tuple[str, str]] = set()
                    dedup_ch: List[Dict[str, Any]] = []
                    for ch in children:
                        lid = str(ch.get("id", "")).strip().lower()
                        lab = str(ch.get("label", "")).strip().lower()
                        key = (lid or lab, lab or lid)
                        if key in seen_ch:
                            warnings.append(
                                f"dedup leaf '{lab or lid}' in attribute '{attr.get('id')}'"
                            )
                            continue
                        seen_ch.add(key)
                        dedup_ch.append(ch)
                    if dedup_ch != children:
                        n = dict(n)
                        n["children"] = dedup_ch
                else:
                    lid = str(n.get("id", "")).strip().lower()
                    lab = str(n.get("label", "")).strip().lower()
                    key = (lid or lab, lab or lid)
                    if key in seen_top and lid not in {"unknown", "other"} and lab not in {
                        "n/a (not stated)",
                        "not in taxonomy",
                    }:
                        warnings.append(
                            f"dedup leaf '{lab or lid}' in attribute '{attr.get('id')}'"
                        )
                        continue
                    seen_top.add(key)
                dedup_top.append(n)
            if dedup_top != nodes:
                attr["nodes"] = dedup_top
    except Exception:
        # Non-fatal: if dedupe fails, continue with the original branch
        pass

    # Flag cross-attribute single-token label collisions. These labels are too
    # weak for deterministic matching and should be made explicit in the branch
    # itself (for example "sheer finish" vs "sheer coverage").
    try:
        single_token_label_owners: Dict[str, List[Tuple[str, str]]] = {}
        for attr in branch.get("attributes", []) or []:
            attr_id = str(attr.get("id", "")).strip().lower()
            for node in attr.get("nodes", []) or []:
                leaves = (node.get("children") or []) if node.get("children") else [node]
                for leaf in leaves:
                    leaf_id = str(leaf.get("id", "")).strip().lower()
                    leaf_label = str(leaf.get("label", "")).strip()
                    if _is_reserved_leaf(leaf_id, leaf_label) or not _is_single_token_label(
                        leaf_label
                    ):
                        continue
                    token = _norm_synonym(leaf_label)
                    owners = single_token_label_owners.setdefault(token, [])
                    owners.append((attr_id, leaf_id or token))

        for token, owners in sorted(single_token_label_owners.items()):
            attr_ids = {attr_id for attr_id, _leaf_id in owners}
            if len(attr_ids) <= 1:
                continue
            owner_text = ", ".join(
                f"{attr_id}:{leaf_id}" for attr_id, leaf_id in owners
            )
            warnings.append(
                "ambiguous single-token label "
                f"'{token}' appears across attributes: {owner_text}"
            )
    except Exception:
        pass

    # Enforce cross-attribute synonym uniqueness within the category. Keep leaf
    # labels as the stronger anchors and drop later conflicting synonyms.
    try:
        occupied_terms: Dict[str, Tuple[str, str, str]] = {}
        for attr in branch.get("attributes", []) or []:
            attr_id = str(attr.get("id", "")).strip().lower()
            for node in attr.get("nodes", []) or []:
                leaves = (node.get("children") or []) if node.get("children") else [node]
                for leaf in leaves:
                    leaf_id = str(leaf.get("id", "")).strip().lower()
                    leaf_label = str(leaf.get("label", "")).strip()
                    if leaf_id in {"unknown", "other"} or leaf_label.lower() in {
                        "n/a (not stated)",
                        "not in taxonomy",
                    }:
                        continue
                    label_token = _norm_synonym(leaf_label)
                    if label_token:
                        occupied_terms.setdefault(
                            label_token,
                            (attr_id, leaf_id or label_token, "label"),
                        )

        for attr in branch.get("attributes", []) or []:
            attr_id = str(attr.get("id", "")).strip().lower()
            for node in attr.get("nodes", []) or []:
                leaves = (node.get("children") or []) if node.get("children") else [node]
                for leaf in leaves:
                    leaf_id = str(leaf.get("id", "")).strip().lower()
                    syns = leaf.get("synonyms") or []
                    if not syns:
                        continue
                    kept_syns: List[str] = []
                    for synonym in syns:
                        syn_token = _norm_synonym(synonym)
                        if not syn_token:
                            continue
                        owner = occupied_terms.get(syn_token)
                        if owner and owner[0] != attr_id:
                            warnings.append(
                                "dropping cross-attribute synonym "
                                f"'{synonym}' from '{attr_id}:{leaf_id or leaf.get('label')}' "
                                f"because it is already owned by '{owner[0]}:{owner[1]}'"
                            )
                            continue
                        kept_syns.append(synonym)
                        occupied_terms.setdefault(
                            syn_token,
                            (attr_id, leaf_id or syn_token, "synonym"),
                        )
                    if kept_syns:
                        leaf["synonyms"] = kept_syns
                    elif "synonyms" in leaf:
                        del leaf["synonyms"]
    except Exception:
        pass

    # SPF modeling enforcement: avoid enumerated SPF buckets.
    # Prefer: (a) non-hierarchical 'sun_protection' (filter type: none/mineral/chemical/hybrid)
    #         (b) non-hierarchical 'spf' (numeric captured at classification time)
    #         (c) optional 'broad_spectrum' (yes/no)
    def _has_spf_bucket(attr: Dict[str, Any]) -> bool:
        def contains_spf_label(txt: str) -> bool:
            t = txt.lower()
            return ("spf" in t and any(ch.isdigit() for ch in t)) or (
                "spf" in t and ("+" in t or "<" in t or ">" in t or "–" in t or "-" in t)
            )

        for n in attr.get("nodes", []) or []:
            lab = str(n.get("label", ""))
            if contains_spf_label(lab):
                return True
            for ch in (n.get("children") or []):
                lab2 = str(ch.get("label", ""))
                if contains_spf_label(lab2):
                    return True
        return False

    def _ensure_attr(attrs: List[Dict[str, Any]], attr_id: str, label: str, nodes: List[Dict[str, Any]], *, selection: str = "single", scope: str = "product", kind: Optional[str] = None) -> None:
        if any((a.get("id") == attr_id) or (str(a.get("label", "")).strip().lower() == label.lower()) for a in attrs):
            return
        attrs.append(
            {
                "id": attr_id,
                "label": label,
                "hierarchical": False,
                "levels": 1,
                "selection": selection,
                "scope": scope,
                **({"kind": kind} if kind else {}),
                "nodes": nodes,
            }
        )

    attrs = branch.get("attributes", [])
    # Ensure sun_filter_type has a 'none' leaf with basic synonyms
    try:
        for a in attrs:
            aid = str(a.get("id", "")).strip().lower()
            alab = str(a.get("label", "")).strip().lower()
            if aid == "sun_filter_type" or alab == "sun filter type":
                leaves = a.get("nodes") or []
                has_none = False
                # Determine synonym budget so we don't evict existing synonyms
                try:
                    caps_local = _default_budgets()
                    max_syns_cap = int(caps_local.get("max_synonyms_per_node", 0) or 0)
                except Exception:
                    max_syns_cap = 0
                for n in leaves:
                    if not n.get("children"):
                        nid = str(n.get("id", "")).strip().lower()
                        nlab = str(n.get("label", "")).strip().lower()
                        if nid == "none" or nlab == "none":
                            has_none = True
                            # Merge minimal synonyms if missing, honoring the remaining budget
                            existing = [
                                str(s).strip().lower() for s in (n.get("synonyms") or []) if str(s).strip()
                            ]
                            syns_set = set(existing)
                            defaults = [
                                "no spf",
                                "no sunscreen",
                                "spf 0",
                                "no sun protection",
                                "no spf listed",
                                "non spf",
                            ]
                            candidates = [d for d in defaults if d not in syns_set]
                            if max_syns_cap > 0:
                                slots = max(0, max_syns_cap - len(syns_set))
                                add = candidates[:slots]
                            else:
                                add = candidates
                            merged = sorted(set(existing) | set(add))
                            if merged and existing != merged:
                                n["synonyms"] = merged
                            break
                if not has_none:
                    base_syns = [
                        "no spf",
                        "no sunscreen",
                        "spf 0",
                        "no sun protection",
                        "no spf listed",
                        "non spf",
                    ]
                    if max_syns_cap > 0:
                        base_syns = base_syns[: max_syns_cap]
                    leaves.insert(
                        0,
                        {
                            "id": "none",
                            "label": "none",
                            "synonyms": base_syns,
                        },
                    )
                    warnings.append("added 'none' leaf to sun_filter_type")
    except Exception:
        pass
    # Enforce selection governance with a cap on multi-select attributes.
    try:
        caps = _default_budgets()
        max_multi = int(caps.get("max_multi_leaves", 4) or 4)
    except Exception:
        max_multi = 4
    for a in attrs:
        # default invalid/missing selection to 'single'
        sel = str(a.get("selection", "single") or "single").strip().lower()
        if sel not in {"single", "multi"}:
            a["selection"] = "single"
            continue
        if sel == "multi":
            # count leaf nodes excluding unknown/other
            def _is_unk_or_other(obj: Dict[str, Any]) -> bool:
                i = str(obj.get("id", "")).strip().lower()
                l = str(obj.get("label", "")).strip().lower()
                return i in {"unknown", "other"} or l in {"n/a (not stated)", "not in taxonomy"}

            cnt = 0
            for n in a.get("nodes", []) or []:
                children = n.get("children") or []
                if children:
                    for ch in children:
                        if not _is_unk_or_other(ch):
                            cnt += 1
                else:
                    if not _is_unk_or_other(n):
                        cnt += 1
            if cnt > max_multi:
                a["selection"] = "single"
                warnings.append(
                    f"forced selection=single for attribute {a.get('id')} with {cnt} values (> {max_multi})"
                )
    for a in list(attrs):
        aid = str(a.get("id", "")).lower()
        alab = str(a.get("label", "")).lower()
        looks_like_sun = ("sun protection" in alab) or ("sun_protection" in aid) or (aid == "sun_protection")
        looks_like_spf = ("spf" in aid) or ("spf" in alab)
        if looks_like_sun or looks_like_spf:
            if _has_spf_bucket(a):
                # Replace with filter type nodes only
                a["hierarchical"] = False
                a["levels"] = 1
                a["label"] = a.get("label") or "Sun protection"
                a["nodes"] = [
                    {"id": "none", "label": "No sunscreen", "synonyms": ["no spf", "spf 0", "no sun protection", "sunscreen-free", "no sunscreen"]},
                    {"id": "mineral", "label": "Mineral (physical)", "synonyms": ["mineral", "physical", "zinc oxide", "titanium dioxide"]},
                    {"id": "chemical", "label": "Chemical (organic)", "synonyms": ["chemical", "organic filters", "avobenzone", "octinoxate", "octocrylene", "homosalate"]},
                    {"id": "hybrid", "label": "Hybrid (mineral + chemical)", "synonyms": ["hybrid", "mineral + chemical"]},
                ]
                # Add separate SPF numeric attribute and broad_spectrum boolean if missing
                _ensure_attr(
                    attrs,
                    "spf",
                    "SPF",
                    nodes=[{"id": "unknown", "label": "N/A (not stated)"}, {"id": "other", "label": "not in taxonomy"}],
                    selection="single",
                    scope="product",
                    kind="regulatory",
                )
                _ensure_attr(
                    attrs,
                    "broad_spectrum",
                    "Broad spectrum",
                    nodes=[
                        {"id": "yes", "label": "Yes", "synonyms": ["broad spectrum", "uva/uvb", "uva-uvb", "uva uvb"]},
                        {"id": "no", "label": "No"},
                    ],
                    selection="single",
                    scope="product",
                    kind="regulatory",
                )

    # First attempt strict validation; if it fails due to parent synonyms or
    # duplicate synonyms across nodes, try to auto-resolve then re-validate.
    try:
        Branch.model_validate(branch)
        # Enforce budgets with deterministic pruning
        caps = _default_budgets()
        _enforce_budgets(branch, caps, warnings)
        Branch.model_validate(branch)  # re-validate after pruning
        return branch, warnings
    except ValidationError as e:
        # Attempt soft fixes for common issues, then re-validate.
        # 1) Remove synonyms on any parent nodes (already done by canonicalize).
        # 2) Enforce per-attribute synonym uniqueness by dropping later duplicates.
        for attr in branch.get("attributes", []):
            # gather seen across leaves only
            seen: Set[str] = set()
            for n in attr.get("nodes", []):
                # skip parents
                if n.get("children"):
                    continue
                syns = n.get("synonyms") or []
                if not syns:
                    continue
                unique: List[str] = []
                for s in syns:
                    if s in seen:
                        warnings.append(
                            f"dropping duplicate synonym '{s}' in attribute '{attr.get('id')}'"
                        )
                        continue
                    seen.add(s)
                    unique.append(s)
                if unique:
                    n["synonyms"] = unique
                else:
                    if "synonyms" in n:
                        del n["synonyms"]
        # Re-validate
        # Enforce budgets and re-validate
        caps = _default_budgets()
        _enforce_budgets(branch, caps, warnings)
        Branch.model_validate(branch)
        # attach reason trace for observability
        warnings.append(f"auto-normalized branch due to validation error: {e.errors()[0].get('msg', 'invalid')}")
        return branch, warnings
