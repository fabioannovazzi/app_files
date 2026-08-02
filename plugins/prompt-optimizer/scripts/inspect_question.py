"""Inspect a legal/tax/compliance question before Codex optimizes the prompt."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "QuestionInventory",
    "angle_confirmation_for_question",
    "inspect_question_text",
    "jurisdiction_confirmation_for_question",
    "lawyer_intake_for_question",
    "jurisdiction_policy_for_language",
    "jurisdiction_policy_for_question",
    "source_domains_for_question",
    "write_inspection",
]

URL_RE = re.compile(r"https?://[^\s)\]>\"']+", re.IGNORECASE)
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
AMOUNT_RE = re.compile(
    r"(?:(?:EUR|USD|GBP|CHF)\s*)?(?:[$£\u20ac]\s*)?\b\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?\s*(?:EUR|USD|GBP|CHF|euro|euros)?",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*%")
ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9&.'-]+(?:\s+[A-Z][A-Za-z0-9&.'-]+){1,4}\b")
QUESTION_RE = re.compile(r"[^.!?]*\?")

LANGUAGE_MARKERS = {
    "it": ("che", "come", "iva", "imposta", "societa", "fiscale", "diritto"),
    "en": ("what", "how", "tax", "vat", "company", "law", "compliance"),
    "fr": ("quoi", "comment", "tva", "impot", "societe", "droit", "fiscal"),
    "de": ("was", "wie", "mwst", "steuer", "gesellschaft", "recht"),
    "es": (
        "qué",
        "que",
        "cómo",
        "como",
        "iva",
        "impuesto",
        "sociedad",
        "derecho",
        "fiscal",
    ),
}

JURISDICTION_CUES = {
    "Italy": ("italy", "italia", "italian", "italiano", "diritto italiano", "agenzia"),
    "France": (
        "france",
        "french",
        "french law",
        "droit francais",
        "droit français",
        "bofip",
    ),
    "Germany": ("germany", "deutschland", "german law", "deutsches recht", "ustg"),
    "European Union": (
        "eu",
        "ue",
        "european union",
        "unione europea",
        "eur-lex",
    ),
    "United States": ("united states", "usa", "irs", "federal"),
    "United Kingdom": ("united kingdom", "uk", "uk law", "hmrc"),
    "Canton of Geneva": (
        "canton of geneva",
        "canton de geneve",
        "canton de genève",
        "geneva",
        "genève",
    ),
    "Canton of Zurich": (
        "canton of zurich",
        "kanton zurich",
        "kanton zürich",
        "zurich",
        "zürich",
    ),
    "Canton of Valais": (
        "canton of valais",
        "canton du valais",
        "valais",
        "wallis",
    ),
    "Jersey": ("jersey",),
    "Singapore": ("singapore",),
    "Switzerland": (
        "switzerland",
        "swiss",
        "chf",
        "suisse",
        "schweiz",
        "geneva",
        "genève",
        "zurich",
        "zürich",
    ),
}

SOURCE_CLASS_HINTS = ()

NATIONAL_LIABILITY_TERMS = (
    "accountant",
    "accountants",
    "contract",
    "contractual",
    "confidentiality",
    "liabilities",
    "liability",
    "negligence",
    "professional secrecy",
    "professional-liability",
    "tax advisor",
    "tax advisers",
    "tax professional",
    "tort",
)

LEGAL_JURISDICTION_POLICIES = {
    "Italy": {
        "language": "jurisdiction",
        "default_jurisdiction": "Italian law",
        "jurisdiction_hints": ["Italy"],
        "user_notice": "Use Italian law unless the user specifies a different forum.",
        "source_focus": [
            "Italian legislation and official gazettes",
            "Agenzia delle Entrate guidance",
            "Italian case law and official court sources",
        ],
        "required_notice_terms": [["diritto italiano", "italian law"]],
    },
    "France": {
        "language": "jurisdiction",
        "default_jurisdiction": "French law",
        "jurisdiction_hints": ["France"],
        "user_notice": "Use French law unless the user specifies a different forum.",
        "source_focus": [
            "French legislation and official consolidated law portals",
            "BOFiP and other French authority guidance where relevant",
            "French case law and official court sources",
        ],
        "required_notice_terms": [["french law", "droit francais", "droit français"]],
    },
    "Germany": {
        "language": "jurisdiction",
        "default_jurisdiction": "German law",
        "jurisdiction_hints": ["Germany"],
        "user_notice": "Use German law unless the user specifies a different forum.",
        "source_focus": [
            "German legislation and official consolidated law portals",
            "German authority guidance where relevant",
            "German case law and official court sources",
        ],
        "required_notice_terms": [["german law", "deutsches recht", "diritto tedesco"]],
    },
    "United States": {
        "language": "jurisdiction",
        "default_jurisdiction": "United States law",
        "jurisdiction_hints": ["United States"],
        "user_notice": "Use United States law unless the user specifies a different forum.",
        "source_focus": [
            "United States federal and state legislation where relevant",
            "Official agency guidance",
            "United States case law and official court sources",
        ],
        "required_notice_terms": [
            ["united states law", "us law", "u.s. law", "federal"]
        ],
    },
    "United Kingdom": {
        "language": "jurisdiction",
        "default_jurisdiction": "UK law",
        "jurisdiction_hints": ["United Kingdom"],
        "user_notice": "Use UK law unless the user specifies a different forum.",
        "source_focus": [
            "UK legislation and official consolidated law portals",
            "HMRC and other UK authority guidance",
            "UK case law and official court sources",
        ],
        "required_notice_terms": [
            ["uk law", "united kingdom law", "united kingdom", "hmrc"]
        ],
    },
    "Switzerland": {
        "language": "jurisdiction",
        "default_jurisdiction": "Swiss law",
        "jurisdiction_hints": ["Switzerland"],
        "user_notice": "Use Swiss law unless the user specifies a canton or different forum.",
        "source_focus": [
            "Swiss federal legislation and official guidance",
            "Swiss tax authority or other agency guidance where relevant",
            "Swiss case law and official court sources",
        ],
        "required_notice_terms": [["swiss law", "droit suisse", "schweizer recht"]],
    },
    "Canton of Geneva": {
        "language": "jurisdiction",
        "default_jurisdiction": "Swiss law and Canton of Geneva",
        "jurisdiction_hints": ["Switzerland", "Canton of Geneva"],
        "user_notice": "Use Swiss law and Canton of Geneva unless the user specifies a different forum.",
        "source_focus": [
            "Swiss federal legislation and official guidance",
            "Canton of Geneva law, tax authority guidance, and official portals",
            "Swiss and Geneva case law where relevant",
        ],
        "required_notice_terms": [
            ["swiss law", "droit suisse", "schweizer recht"],
            [
                "canton of geneva",
                "canton de geneve",
                "canton de genève",
                "geneva",
                "genève",
            ],
        ],
    },
    "Canton of Zurich": {
        "language": "jurisdiction",
        "default_jurisdiction": "Swiss law and Canton of Zurich",
        "jurisdiction_hints": ["Switzerland", "Canton of Zurich"],
        "user_notice": "Use Swiss law and Canton of Zurich unless the user specifies a different forum.",
        "source_focus": [
            "Swiss federal legislation and official guidance",
            "Canton of Zurich law, tax authority guidance, and official portals",
            "Swiss and Zurich case law where relevant",
        ],
        "required_notice_terms": [
            ["swiss law", "droit suisse", "schweizer recht"],
            ["canton of zurich", "kanton zurich", "kanton zürich", "zurich", "zürich"],
        ],
    },
    "European Union": {
        "language": "jurisdiction",
        "default_jurisdiction": "European Union law",
        "jurisdiction_hints": ["European Union"],
        "user_notice": "Use European Union law only for EU-level issues or as context for national law.",
        "source_focus": [
            "EUR-Lex legislation and official EU portals",
            "Court of Justice of the European Union case law",
            "European Commission or authority guidance where relevant",
        ],
        "required_notice_terms": [["european union law", "eu law", "diritto ue"]],
    },
}


@dataclass(frozen=True)
class QuestionInventory:
    """Structured deterministic inventory for a research question."""

    language_hint: str
    character_count: int
    word_count: int
    urls: list[str]
    dates: list[str]
    years: list[str]
    amounts: list[str]
    percentages: list[str]
    entities: list[str]
    explicit_questions: list[str]
    jurisdiction_hints: list[str]
    source_class_hints: list[str]
    posture_hint: str
    objective_hint: str
    scope_hint: str
    topic_flags: list[str]
    requires_phased_workflow: bool

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable inventory."""

        return {
            "language_hint": self.language_hint,
            "character_count": self.character_count,
            "word_count": self.word_count,
            "urls": self.urls,
            "dates": self.dates,
            "years": self.years,
            "amounts": self.amounts,
            "percentages": self.percentages,
            "entities": self.entities,
            "explicit_questions": self.explicit_questions,
            "jurisdiction_hints": self.jurisdiction_hints,
            "source_class_hints": self.source_class_hints,
            "posture_hint": self.posture_hint,
            "objective_hint": self.objective_hint,
            "scope_hint": self.scope_hint,
            "topic_flags": self.topic_flags,
            "requires_phased_workflow": self.requires_phased_workflow,
        }


def _ordered_unique(items: list[str], *, limit: int | None = None) -> list[str]:
    """Return unique non-empty strings preserving order."""

    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = re.sub(r"\s+", " ", item.strip().strip(".,;:()[]{}"))
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if limit is not None and len(out) >= limit:
            break
    return out


def _language_hint(text: str) -> str:
    """Infer a rough language hint from deterministic marker counts."""

    lowered = text.casefold()
    scores = {
        lang: sum(
            1 for marker in markers if re.search(rf"\b{re.escape(marker)}\b", lowered)
        )
        for lang, markers in LANGUAGE_MARKERS.items()
    }
    best_lang, best_score = max(scores.items(), key=lambda item: item[1])
    return best_lang if best_score else "auto"


def _extract_explicit_questions(text: str) -> list[str]:
    """Extract explicit question sentences."""

    candidates = [fragment.strip() for fragment in QUESTION_RE.findall(text)]
    return _ordered_unique(candidates, limit=12)


def _contains_jurisdiction_marker(lowered_text: str, marker: str) -> bool:
    """Return whether lowered text contains a jurisdiction marker as a term."""

    normalized_marker = marker.casefold()
    if re.search(r"\w", normalized_marker):
        return (
            re.search(rf"(?<!\w){re.escape(normalized_marker)}(?!\w)", lowered_text)
            is not None
        )
    return normalized_marker in lowered_text


def _jurisdiction_hints(text: str) -> list[str]:
    """Return jurisdiction hints from known terms."""

    lowered = text.casefold()
    hints = []
    for jurisdiction, markers in JURISDICTION_CUES.items():
        if any(_contains_jurisdiction_marker(lowered, marker) for marker in markers):
            hints.append(jurisdiction)
    return hints


def _posture_hint(text: str) -> str:
    """Leave research posture to model-led review.

    Keyword routing produced false decisions when words such as ``before`` or
    ``audit`` appeared in facts rather than in the user's requested posture.
    Returning an explicit unresolved value is mechanically correct and keeps
    the semantic decision with Codex or the user.
    """

    return "unconfirmed"


def _objective_hint(text: str) -> str:
    """Leave the professional objective to model-led review."""

    return "unconfirmed"


def _scope_hint(jurisdictions: list[str]) -> str:
    """Leave legal scope to model-led review.

    Mentioned countries can be background facts rather than governing
    frameworks. Counting them cannot determine legal research scope.
    """

    return "unconfirmed"


def _legal_topic_flags(text: str, jurisdictions: list[str]) -> list[str]:
    """Return no legal topic flags.

    Legal topic classification is intentionally model-led. The deterministic
    layer only inventories raw cues and must not route legal matters into
    semantic topic buckets.
    """

    return []


def _requires_phased_workflow(
    *,
    explicit_question_count: int,
    scope_hint: str,
    topic_flags: list[str],
    word_count: int,
) -> bool:
    """Return whether deterministic inspection requires research phasing.

    Phasing is a legal/research judgment. Keep deterministic inspection from
    forcing a workflow based on brittle text patterns.
    """

    return False


def _complexity_profile(inventory: QuestionInventory) -> dict[str, Any]:
    """Record that deterministic inspection did not choose research phasing."""

    return {
        "topic_flags": inventory.topic_flags,
        "requires_phased_workflow": inventory.requires_phased_workflow,
        "required_controls": [],
        "recommended_phases": [],
    }


def source_domains_for_question(
    jurisdiction_policy: dict[str, Any],
    jurisdiction_hints: list[str],
    topic_flags: list[str],
    *,
    scope_hint: str = "domestic_only",
) -> list[str]:
    """Return no deterministic source domains.

    Source-domain curation is a legal relevance judgment and belongs to Codex's
    model-led drafting step after the framework is confirmed.
    """

    return []


def _effective_language(language: str, detected_language: str) -> str:
    """Return the output language inventory code."""

    if language != "auto":
        return language
    if detected_language in {"it", "en", "fr", "de", "es"}:
        return detected_language
    return "auto"


def jurisdiction_policy_for_language(
    language: str, detected_language: str = "auto"
) -> dict[str, Any]:
    """Return output-language inventory without selecting a legal framework."""

    effective_language = _effective_language(language, detected_language)
    return {
        "language": effective_language,
        "default_jurisdiction": "unconfirmed",
        "jurisdiction_hints": [],
        "possible_frameworks": [],
        "user_notice": (
            "No governing legal framework is selected by deterministic inspection. "
            "Confirm the framework before drafting."
        ),
        "source_focus": [],
        "required_notice_terms": [
            [
                "jurisdiction",
                "legal framework",
                "governing law",
                "framework",
                "hypothèse de juridiction",
                "cadre juridique",
            ]
        ],
        "policy_source": "inventory_only",
        "selection_status": "unconfirmed",
    }


def _framework_option_from_hint(jurisdiction: str) -> dict[str, Any]:
    """Return a possible framework option from a deterministic cue."""

    policy = LEGAL_JURISDICTION_POLICIES.get(jurisdiction)
    if policy is None:
        return {
            "id": jurisdiction.casefold().replace(" ", "_"),
            "hint": jurisdiction,
            "label": jurisdiction,
            "source_focus": [],
        }
    return {
        "id": jurisdiction.casefold().replace(" ", "_"),
        "hint": jurisdiction,
        "label": str(policy["default_jurisdiction"]),
        "source_focus": [],
    }


def _possible_frameworks_from_hints(
    jurisdictions: list[str],
) -> list[dict[str, Any]]:
    """Return possible frameworks from cues without choosing among them."""

    priority = [
        "Canton of Geneva",
        "Canton of Zurich",
        "Canton of Valais",
        "Italy",
        "France",
        "Germany",
        "United States",
        "United Kingdom",
        "Switzerland",
        "European Union",
        "Jersey",
        "Singapore",
    ]
    ordered = [item for item in priority if item in jurisdictions]
    return [_framework_option_from_hint(item) for item in ordered]


def jurisdiction_policy_for_question(
    language: str,
    detected_language: str = "auto",
    jurisdiction_hints: list[str] | None = None,
) -> dict[str, Any]:
    """Inventory possible legal frameworks without selecting one."""

    hints = _ordered_unique(jurisdiction_hints or [])
    policy = jurisdiction_policy_for_language(language, detected_language)
    possible_frameworks = _possible_frameworks_from_hints(hints)
    source_focus: list[str] = []
    for framework in possible_frameworks:
        source_focus.extend(str(item) for item in framework.get("source_focus", []))
    policy.update(
        {
            "jurisdiction_hints": hints,
            "possible_frameworks": possible_frameworks,
            "source_focus": _ordered_unique(source_focus),
            "policy_source": "inventory_only",
            "selection_status": "unconfirmed",
        }
    )
    return policy


def _jurisdiction_conflicts(
    jurisdictions: list[str], policy: dict[str, Any]
) -> list[str]:
    """Return jurisdiction conflicts.

    Deterministic inspection no longer selects a language-based default, so it
    has no deterministic basis for declaring conflicts.
    """

    return []


def _has_national_liability_surface(inventory: QuestionInventory) -> bool:
    """Return whether EU-level hints leave material national liability open."""

    searchable = " ".join(
        [
            *inventory.explicit_questions,
            *inventory.entities,
            *inventory.topic_flags,
        ]
    ).casefold()
    return any(term in searchable for term in NATIONAL_LIABILITY_TERMS)


def _jurisdiction_confirmation_reason(
    inventory: QuestionInventory, policy: dict[str, Any]
) -> str:
    """Return the reason a user-facing jurisdiction choice is required."""

    if not inventory.jurisdiction_hints:
        return (
            "The question does not identify a governing country, state, canton, "
            "or forum."
        )
    if set(inventory.jurisdiction_hints) == {
        "European Union"
    } and _has_national_liability_surface(inventory):
        return (
            "EU law is explicit, but professional, contract, tort, tax-advisory, "
            "and other liabilities can depend on national law."
        )
    return (
        "Deterministic inspection found possible legal-framework cues, but it "
        "does not choose governing law."
    )


def _structured_choice_option(
    option_id: str, label: str, description: str, instruction: str
) -> dict[str, str]:
    """Return one structured choice option."""

    return {
        "id": option_id,
        "label": label,
        "description": description,
        "instruction": instruction,
    }


def angle_confirmation_for_question(inventory: QuestionInventory) -> dict[str, Any]:
    """Record that angle confirmation is a model-led decision."""

    return {
        "required": False,
        "decision_owner": "codex_or_user",
        "determination_status": "not_determined_by_inspection",
        "mode": "model_led_confirmation_if_material",
        "reason": (
            "Deterministic inspection does not decide the research angle or "
            "whether confirmation is materially required."
        ),
        "question": "Codex should confirm the research angle only when materially unresolved.",
        "preferred_option_id": None,
        "options": [],
        "max_native_ui_options": 3,
        "allows_custom": True,
        "instruction": (
            "Codex must understand the question semantically, choose or propose "
            "the research angle, and ask only when an unresolved choice would "
            "materially change the answer. Generate any options from the facts."
        ),
    }


def jurisdiction_confirmation_for_question(
    inventory: QuestionInventory, jurisdiction_policy: dict[str, Any]
) -> dict[str, Any]:
    """Inventory framework cues without deciding whether confirmation is needed."""

    reason = _jurisdiction_confirmation_reason(inventory, jurisdiction_policy)
    options = []
    if "European Union" in inventory.jurisdiction_hints:
        options.append(
            _structured_choice_option(
                "eu_law_baseline",
                "EU law baseline",
                (
                    "Use EU-level rules, while flagging national-law liability as "
                    "unresolved."
                ),
                (
                    "Use EU law as the baseline and identify each point that requires "
                    "Member State law before giving a firm conclusion."
                ),
            )
        )
        options.append(
            _structured_choice_option(
                "eu_plus_member_state",
                "EU law plus a named Member State",
                (
                    "Use EU law together with the national law the user names before "
                    "drafting."
                ),
                (
                    "Ask the user to name the Member State and then analyze EU duties "
                    "together with that national framework."
                ),
            )
        )
    for framework in jurisdiction_policy.get("possible_frameworks", []):
        hint = str(framework["hint"])
        if hint == "European Union":
            continue
        options.append(
            _structured_choice_option(
                f"possible_framework_{str(framework['id'])}",
                str(framework["label"]),
                "Confirm this framework if it is the intended governing law.",
                f"Use {framework['label']} only if the user confirms it.",
            )
        )
    options.append(
        _structured_choice_option(
            "different_framework",
            "Different jurisdiction",
            (
                "Use a country, state, canton, forum, or source framework supplied "
                "by the user."
            ),
            (
                "Ask the user for the governing country, state, canton, forum, or "
                "source framework before drafting."
            ),
        )
    )
    options.append(
        _structured_choice_option(
            "custom_framework",
            "Custom framework",
            "Let the user specify a custom combination of jurisdictions or laws.",
            "Use the custom framework exactly as supplied by the user.",
        )
    )
    return {
        "required": False,
        "decision_owner": "codex_or_user",
        "determination_status": "not_determined_by_inspection",
        "mode": "model_led_confirmation_if_material",
        "reason": reason,
        "question": (
            "Codex should confirm the legal framework only when the user's text "
            "and context do not already resolve it."
        ),
        "preferred_option_id": None,
        "options": options,
        "max_native_ui_options": 3,
        "allows_custom": True,
        "instruction": (
            "Codex decides semantically whether the user's question already "
            "confirms the framework. Ask only when a material governing-law or "
            "source-framework choice remains unresolved."
        ),
    }


def lawyer_intake_for_question(
    inventory: QuestionInventory, jurisdiction_policy: dict[str, Any]
) -> dict[str, Any]:
    """Return the boundary for model-led legal intake.

    Deterministic inspection cannot know whether a missing fact is material or
    whether the question already implies the desired answer form. Codex should
    ordinarily proceed from a legal question to an optimized generation
    contract, asking only when semantic review identifies a consequential gap.
    """

    angle_confirmation = angle_confirmation_for_question(inventory)
    jurisdiction_confirmation = jurisdiction_confirmation_for_question(
        inventory, jurisdiction_policy
    )
    return {
        "mode": "model_led_ask_only_when_material",
        "decision_owner": "codex_or_user",
        "max_questions": 3,
        "questions": [],
        "angle_confirmation_required": angle_confirmation["required"],
        "jurisdiction_confirmation_required": jurisdiction_confirmation["required"],
        "output_format_options": [],
        "fast_path": (
            "Proceed from the legal question to an answer contract and optimized "
            "prompt when the intended output and framework are semantically clear. "
            "Ask only about a material ambiguity that would change the answer."
        ),
        "instruction": (
            "Do not ask the user whether to optimize the prompt. Infer the likely "
            "document type, generation route, research lens, and source strategy "
            "semantically; surface assumptions and request confirmation only when "
            "a consequential choice remains unresolved."
        ),
    }


def inspect_question_text(text: str) -> QuestionInventory:
    """Build a deterministic inventory for question text."""

    normalized = text.strip()
    urls = _ordered_unique(URL_RE.findall(normalized), limit=20)
    dates = _ordered_unique(DATE_RE.findall(normalized), limit=30)
    years = _ordered_unique(YEAR_RE.findall(normalized), limit=30)
    amounts = _ordered_unique(AMOUNT_RE.findall(normalized), limit=30)
    percentages = _ordered_unique(PERCENT_RE.findall(normalized), limit=30)
    entities = _ordered_unique(ENTITY_RE.findall(normalized), limit=30)
    explicit_questions = _extract_explicit_questions(normalized)
    jurisdictions = _jurisdiction_hints(normalized)
    word_count = len(re.findall(r"\S+", normalized))
    scope_hint = _scope_hint(jurisdictions)
    topic_flags = _legal_topic_flags(normalized, jurisdictions)
    requires_phased_workflow = _requires_phased_workflow(
        explicit_question_count=len(explicit_questions),
        scope_hint=scope_hint,
        topic_flags=topic_flags,
        word_count=word_count,
    )
    return QuestionInventory(
        language_hint=_language_hint(normalized),
        character_count=len(normalized),
        word_count=word_count,
        urls=urls,
        dates=dates,
        years=years,
        amounts=amounts,
        percentages=percentages,
        entities=entities,
        explicit_questions=explicit_questions,
        jurisdiction_hints=jurisdictions,
        source_class_hints=list(SOURCE_CLASS_HINTS),
        posture_hint=_posture_hint(normalized),
        objective_hint=_objective_hint(normalized),
        scope_hint=scope_hint,
        topic_flags=topic_flags,
        requires_phased_workflow=requires_phased_workflow,
    )


def _prompt_recipe(inventory: QuestionInventory, language: str) -> dict[str, Any]:
    """Return a deterministic prompt recipe for Codex to fill."""

    jurisdiction_policy = jurisdiction_policy_for_question(
        language, inventory.language_hint, inventory.jurisdiction_hints
    )
    complexity_profile = _complexity_profile(inventory)
    source_domains = source_domains_for_question(
        jurisdiction_policy,
        inventory.jurisdiction_hints,
        inventory.topic_flags,
        scope_hint=inventory.scope_hint,
    )
    required_prompt_elements = [
        "professional role",
        "explicit research lens with posture, objective, and scope",
        "source hierarchy",
        "citation and notes rules",
        "official URL reliability checks",
        "fact preservation",
        "user-facing jurisdiction assumption notice",
        "clarifying questions when essential facts are missing",
        "client-ready output structure",
        "residual uncertainty section",
    ]
    if inventory.requires_phased_workflow:
        required_prompt_elements.extend(complexity_profile["required_controls"])
    return {
        "language": language,
        "effective_language": jurisdiction_policy["language"],
        "detected_language_hint": inventory.language_hint,
        "angle_confirmation": angle_confirmation_for_question(inventory),
        "jurisdiction_policy": jurisdiction_policy,
        "jurisdiction_confirmation": jurisdiction_confirmation_for_question(
            inventory, jurisdiction_policy
        ),
        "jurisdiction_conflicts": _jurisdiction_conflicts(
            inventory.jurisdiction_hints, jurisdiction_policy
        ),
        "lens": {
            "posture": inventory.posture_hint,
            "objective": inventory.objective_hint,
            "scope": inventory.scope_hint,
        },
        "complexity_profile": complexity_profile,
        "source_domains": source_domains,
        "source_domain_policy": "model_curated_only",
        "lawyer_intake": lawyer_intake_for_question(inventory, jurisdiction_policy),
        "required_prompt_elements": required_prompt_elements,
        "fact_anchors": {
            "dates": inventory.dates,
            "years": inventory.years,
            "amounts": inventory.amounts,
            "percentages": inventory.percentages,
            "entities": inventory.entities,
            "urls": inventory.urls,
            "explicit_questions": inventory.explicit_questions,
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write stable UTF-8 JSON."""

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_inspection(
    question_text: str, output_dir: Path, language: str
) -> dict[str, Path]:
    """Write inspection artifacts and return their paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    inventory = inspect_question_text(question_text)
    inventory_path = output_dir / "question_inventory.json"
    recipe_path = output_dir / "prompt_recipe.json"
    write_json(inventory_path, inventory.to_dict())
    write_json(recipe_path, _prompt_recipe(inventory, language))
    return {"question_inventory": inventory_path, "prompt_recipe": recipe_path}


def _read_text(path: Path) -> str:
    """Read a UTF-8 text file."""

    return path.read_text(encoding="utf-8").strip()


def main() -> int:
    """Run question inspection from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "question_file",
        type=Path,
        help="UTF-8 file containing the source question or case.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for question_inventory.json and prompt_recipe.json.",
    )
    parser.add_argument(
        "--language", choices=["auto", "it", "en", "fr", "de", "es"], default="auto"
    )
    args = parser.parse_args()

    question_text = _read_text(args.question_file)
    if not question_text:
        parser.error("question_file is empty")
    write_inspection(question_text, args.output_dir, args.language)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
