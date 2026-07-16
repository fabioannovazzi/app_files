# modules/add_attributes/attribute_watcher.py

import re
from typing import List, Dict, Any, Set, Tuple
from collections import Counter

def normalise_text(text: str) -> str:
    """Lowercase and strip punctuation for simple term extraction."""
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())

def collect_existing_terms(taxonomy: Dict[str, Any]) -> Set[str]:
    """Flattens all node labels and synonyms from the taxonomy."""
    terms: Set[str] = set()
    for cat in taxonomy.get("categories", []):
        for attr in cat.get("attributes", []):
            for node in attr.get("nodes", []):
                terms.add(str(node.get("label", "")).lower())
                syns = node.get("synonyms") or []
                terms.update(str(s).lower() for s in syns)
                # Flatten children
                for child in (node.get("children") or []):
                    terms.add(str(child.get("label", "")).lower())
                    syns2 = child.get("synonyms") or []
                    terms.update(str(s).lower() for s in syns2)
    return terms

def detect_new_terms(descriptions: List[str], taxonomy: Dict[str, Any], min_count: int = 5) -> List[str]:
    """Returns tokens not in taxonomy that appear at least `min_count` times."""
    existing = collect_existing_terms(taxonomy)
    tokens = Counter()
    for desc in descriptions:
        words = normalise_text(desc).split()
        for w in words:
            if w and w not in existing and len(w) > 2:
                tokens[w] += 1
    return [t for t, c in tokens.items() if c >= min_count]

def suggest_new_nodes(candidates: List[str], category_name: str, llm_call) -> Dict[str, List[Tuple[str, str]]]:
    """
    Sends candidate terms to the LLM to propose attribute id and branch placement.
    Returns a dict mapping attribute_id -> list of (new_id, new_label).
    """
    if not candidates:
        return {}
    prompt = (
        f"For the category '{category_name}', we detected these unknown terms in product descriptions: "
        f"{', '.join(candidates)}.\n"
        f"Which attribute and branch should each belong to, or are they irrelevant? "
        "Return JSON {attribute_id: [[new_id, new_label], ...], ...}. "
        "Omit any terms that don't fit."
    )
    response = llm_call(prompt)
    return json.loads(response)

def update_taxonomy_with_suggestions(taxonomy: Dict[str, Any], suggestions: Dict[str, List[Tuple[str, str]]]) -> Dict[str, Any]:
    """Merges new nodes into taxonomy attributes."""
    for cat in taxonomy.get("categories", []):
        for attr in cat.get("attributes", []):
            aid = attr.get("id")
            if aid in suggestions:
                for new_id, new_label in suggestions[aid]:
                    # avoid duplicates
                    ids = {n["id"] for n in attr["nodes"]}
                    if new_id not in ids:
                        attr["nodes"].insert(-2, {"id": new_id, "label": new_label})  # insert before unknown/other
    return taxonomy
