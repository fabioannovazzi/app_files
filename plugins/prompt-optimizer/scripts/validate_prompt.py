"""Validate and package Codex-written answer-generation instructions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

try:
    from inspect_question import (
        angle_confirmation_for_question,
        inspect_question_text,
        jurisdiction_confirmation_for_question,
        jurisdiction_policy_for_question,
    )
except ImportError:  # pragma: no cover - direct import fallback for tests
    sys.path.append(str(Path(__file__).resolve().parent))
    from inspect_question import (
        angle_confirmation_for_question,
        inspect_question_text,
        jurisdiction_confirmation_for_question,
        jurisdiction_policy_for_question,
    )

try:
    from .review_session import (
        synchronize_final_artifact_sizes,
        write_review_session_artifacts,
        write_run_intake,
    )
except ImportError:  # pragma: no cover - supports direct script imports
    import importlib.util

    _review_session_path = Path(__file__).resolve().parent / "review_session.py"
    _review_session_spec = importlib.util.spec_from_file_location(
        "mparanza_prompt_optimizer_review_session",
        _review_session_path,
    )
    assert _review_session_spec and _review_session_spec.loader
    _review_session = importlib.util.module_from_spec(_review_session_spec)
    sys.modules[_review_session_spec.name] = _review_session
    _review_session_spec.loader.exec_module(_review_session)
    synchronize_final_artifact_sizes = _review_session.synchronize_final_artifact_sizes
    write_review_session_artifacts = _review_session.write_review_session_artifacts
    write_run_intake = _review_session.write_run_intake

__all__ = [
    "render_prompt_package",
    "validate_answer_contract",
    "validate_prompt_contract_review",
    "validate_prompt_text",
    "write_validation",
]

ANSWER_CONTRACT_REQUIRED_FIELDS = (
    "schema_version",
    "question_domain",
    "generation_route",
    "document_type",
    "purpose",
    "audience",
    "output_language",
    "jurisdiction_status",
    "jurisdiction",
    "evidence_display",
    "validation_profile",
    "validation_scope",
    "correction_policy",
    "judgment_policy",
)
ANSWER_CONTRACT_ENUMS = {
    "question_domain": {"legal", "tax", "compliance", "mixed"},
    "generation_route": {
        "chatgpt_deep_research",
        "codex_direct",
        "external_document",
    },
    "jurisdiction_status": {
        "confirmed",
        "assumed",
        "unresolved",
        "not_applicable",
    },
    "evidence_display": {
        "inline_citations",
        "footnotes",
        "source_record_only",
        "mixed",
        "not_specified",
    },
    "validation_profile": {"source_identity_support_reasoning_and_judgment"},
    "validation_scope": {
        "all_material_claims",
        "selected_material_claims",
        "limited",
    },
    "correction_policy": {"correct_when_supported", "review_only"},
    "judgment_policy": {"flag_for_professional_review"},
}
PROMPT_CONTRACT_REVIEW_DIMENSIONS = (
    "question_and_material_facts",
    "generation_route",
    "document_type",
    "purpose",
    "audience",
    "output_language",
    "jurisdiction",
    "evidence_display",
    "research_lens",
    "validation_policy",
    "source_strategy",
)
PROMPT_CONTRACT_REVIEW_STATUSES = {
    "conforms",
    "partially_conforms",
    "does_not_conform",
    "uncertain",
    "not_reviewed",
}
PROMPT_CONTRACT_REVIEW_ACTIONS = {
    "accept",
    "reject",
    "edit",
    "mark_unclear",
    "request_more_documents",
}

LANGUAGE_LOCK_TERMS = {
    "it": ("lingua", "italiano"),
    "en": ("language", "english"),
    "fr": ("langue", "francais", "français"),
    "de": ("sprache", "deutsch"),
    "es": ("idioma", "español", "espanol"),
    "auto": (
        "language",
        "english",
        "lingua",
        "italiano",
        "langue",
        "francais",
        "français",
        "sprache",
        "deutsch",
    ),
}
SOURCE_TERMS = (
    "source",
    "sources",
    "fonti",
    "legislation",
    "legislazione",
    "case law",
    "giurisprudenza",
    "tax authority",
    "agenzia",
    "official",
    "ufficial",
    "url",
)
CITATION_TERMS = ("[1]", "[2]", "citation", "citazioni", "notes", "note", "footnote")
SOURCE_RECORD_TERMS = (
    "source record",
    "source map",
    "evidence record",
    "validation record",
    "registro delle fonti",
    "mappa delle fonti",
    "registro de fuentes",
)
CLARIFICATION_TERMS = (
    "clarifying question",
    "clarifying questions",
    "domande di chiarimento",
    "domanda di chiarimento",
    "domande chiarificatrici",
    "domanda chiarificatrice",
    "questions de clarification",
    "question de clarification",
    "questions clarificatrices",
    "rueckfragen",
    "ruckfragen",
    "klarstellungsfragen",
)
UNCERTAINTY_TERMS = (
    "uncertainty",
    "uncertain",
    "incertezza",
    "incertezze",
    "incertezze residue",
    "incertain",
    "incertitude",
    "incertitudes",
    "unsicherheit",
    "unsicherheiten",
)
PHASED_WORKFLOW_TERMS = (
    "phase 0",
    "phase 1",
    "phased",
    "modular workflow",
    "staged",
)
CHRONOLOGY_TERMS = ("chronology", "timeline", "chronologie", "cronologia")
CONFIDENCE_TERMS = (
    "confidence",
    "high confidence",
    "moderate confidence",
    "uncertain/practice-dependent",
    "practice-dependent",
)
AUTHORITY_SAFETY_TERM_GROUPS = [
    ["do not invent", "do not fabricate", "fabricated", "cannot be verified"],
    ["authority", "authorities", "case", "decision", "citation", "circular"],
]
LEGAL_REALISM_TERM_GROUPS = [
    ["black-letter", "black letter"],
    ["unsettled doctrine", "doctrine"],
    ["cantonal practice", "administrative practice", "local practice"],
    ["litigation strategy", "strategy"],
    ["evidentiary dependency", "evidence", "evidentiary"],
]
TRUST_SCOPE_TERM_GROUPS = [
    ["trust"],
    ["do not overclaim", "do not confuse", "tightly scoped", "scope control"],
]
TAX_SCOPE_TERM_GROUPS = [
    ["tax"],
    ["confirmed law", "uncertainty", "uncertain"],
    ["treaty-dependent", "do not assume treaty", "fact-dependent"],
]
URL_RE = re.compile(r"https?://[^\s),\]}\"'`<>]+", re.IGNORECASE)
DOMAIN_RE = re.compile(
    r"(?<![A-Za-z0-9@._-])"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}"
    r"(?:/[^\s),\]}\"'`<>]*)?",
    re.IGNORECASE,
)
LEGAL_ENTITY_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,4}\s+"
    r"(?:S\.r\.l\.|S\.p\.A\.|S\.a\.s\.|S\.n\.c\.|Ltd\.?|Limited|"
    r"GmbH|AG|SARL|SAS|LLC|Inc\.?|Corp\.?)(?=\s|[,;:()]|$)"
)
SOURCE_DOMAIN_SECTION_TERMS = (
    "qualified source domains",
    "source domains",
    "website/source list",
    "website list",
    "websites",
    "fonti e domini",
    "domini qualificati",
    "lista siti",
    "siti qualificati",
    "domaines qualifiés",
    "domaines sources",
    "quell-domains",
)
SOURCE_DOMAIN_LINE_TERMS = (
    "source domains:",
    "qualified source domains:",
    "websites:",
    "website list:",
    "fonti e domini:",
    "domini qualificati:",
    "siti qualificati:",
    "source-domain",
)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    """Return whether text contains any term case-insensitively."""

    lowered = text.casefold()
    return any(term.casefold() in lowered for term in terms)


def _contains_all_term_groups(text: str, term_groups: list[list[str]]) -> bool:
    """Return whether text contains at least one term from every group."""

    lowered = text.casefold()
    return all(
        any(term.casefold() in lowered for term in term_group)
        for term_group in term_groups
    )


def _has_research_lens(text: str) -> bool:
    """Return whether prompt explicitly states posture, objective, and scope."""

    posture_terms = (
        "posture",
        "postura",
        "angle",
        "angolo",
        "lente di ricerca",
        "research lens",
        "forschungsperspektive",
    )
    objective_terms = ("objective", "obiettivo", "objectif", "ziel")
    scope_terms = ("scope", "ambito", "portee", "portée", "umfang")
    return (
        _contains_any(text, posture_terms)
        and _contains_any(text, objective_terms)
        and _contains_any(text, scope_terms)
    )


def _requires_grouped_terms(text: str, term_groups: list[list[str]]) -> bool:
    """Return whether text contains at least one term from each group."""

    return _contains_all_term_groups(text, term_groups)


def _domain_candidate_blocks(text: str) -> list[str]:
    """Return prompt blocks likely to contain model-curated source domains."""

    blocks: list[str] = []
    active_lines: list[str] = []
    in_source_section = False
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.casefold()
        is_heading = stripped.startswith("#")
        if is_heading:
            if active_lines:
                blocks.append("\n".join(active_lines))
                active_lines = []
            heading_text = stripped.lstrip("#").strip().casefold()
            in_source_section = any(
                term in heading_text for term in SOURCE_DOMAIN_SECTION_TERMS
            )
            if in_source_section:
                active_lines.append(stripped)
            continue
        if any(term in lowered for term in SOURCE_DOMAIN_LINE_TERMS):
            active_lines.append(stripped)
        elif in_source_section:
            active_lines.append(stripped)
    if active_lines:
        blocks.append("\n".join(active_lines))
    return blocks


def _normalize_source_domain(value: str) -> str | None:
    """Normalize a mechanically parsed website/domain into a root URL."""

    stripped = value.strip().strip("`'\"()[]{}<>").rstrip(".,;:")
    if not stripped:
        return None
    if not stripped.startswith(("http://", "https://")):
        stripped = f"https://{stripped}"
    parsed = urlsplit(stripped)
    if not parsed.netloc or "." not in parsed.netloc:
        return None
    hostname = parsed.netloc.lower()
    return f"{parsed.scheme.lower()}://{hostname}/"


def _extract_source_domains(prompt_text: str) -> list[str]:
    """Mechanically extract model-curated source websites from source-list blocks.

    Deterministic parsing is justified here because it only transforms explicit
    domains already chosen by Codex/the user into stable output files; it does
    not choose legal frameworks, source relevance, or research scope.
    """

    candidates: list[str] = []
    for block in _domain_candidate_blocks(prompt_text):
        candidates.extend(URL_RE.findall(block))
        candidates.extend(DOMAIN_RE.findall(block))
    seen: set[str] = set()
    source_domains: list[str] = []
    for candidate in candidates:
        normalized = _normalize_source_domain(candidate)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        source_domains.append(normalized)
    return source_domains


def _parse_source_domains_text(source_domains_text: str) -> list[str]:
    """Parse a sidecar domain list written with commas, whitespace, or newlines."""

    candidates = URL_RE.findall(source_domains_text) + DOMAIN_RE.findall(
        source_domains_text
    )
    seen: set[str] = set()
    source_domains: list[str] = []
    for candidate in candidates:
        normalized = _normalize_source_domain(candidate)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        source_domains.append(normalized)
    return source_domains


def _normalize_source_domains(source_domains: list[str]) -> list[str]:
    """Normalize caller-supplied domains while preserving first-seen order."""

    seen: set[str] = set()
    normalized_domains: list[str] = []
    for source_domain in source_domains:
        normalized = _normalize_source_domain(str(source_domain))
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        normalized_domains.append(normalized)
    return normalized_domains


def _missing_anchors(question_text: str, prompt_text: str) -> list[str]:
    """Return mechanically exact fact anchors missing from the prompt.

    Dates, amounts, percentages, URLs, and company names carrying an explicit
    legal-form suffix are stable strings whose omission can be observed without
    interpreting legal meaning. Broader names and paraphrased facts remain part
    of the model-led semantic conformance review.
    """

    inventory = inspect_question_text(question_text)
    anchors = (
        inventory.dates
        + inventory.years
        + inventory.amounts
        + inventory.percentages
        + inventory.urls
        + list(dict.fromkeys(LEGAL_ENTITY_RE.findall(question_text)))
    )
    lowered_prompt = prompt_text.casefold()
    missing: list[str] = []
    for anchor in anchors:
        normalized = anchor.casefold()
        compact = re.sub(r"\s+", "", normalized)
        if normalized in lowered_prompt or compact in re.sub(
            r"\s+", "", lowered_prompt
        ):
            continue
        missing.append(anchor)
    return missing


def _missing_explicit_questions(question_text: str, prompt_text: str) -> list[str]:
    """Observe literal question overlap without treating it as semantic proof."""

    inventory = inspect_question_text(question_text)
    lowered_prompt = prompt_text.casefold()
    missing: list[str] = []
    for question in inventory.explicit_questions:
        compact_question = re.sub(r"\W+", "", question.casefold())
        compact_prompt = re.sub(r"\W+", "", lowered_prompt)
        if question.casefold() in lowered_prompt or compact_question in compact_prompt:
            continue
        missing.append(question)
    return missing


def validate_prompt_contract_review(
    prompt_contract_review: dict[str, Any],
) -> dict[str, Any]:
    """Validate the shape and recorded result of a model-led conformance review.

    The semantic statuses and analyses are authored by Codex or a professional
    reviewer. Fixed logic only checks that every required dimension was
    actually reviewed and that the explicit overall action is internally
    sufficient for acceptance.
    """

    missing_fields = [
        field
        for field in (
            "schema_version",
            "review_method",
            "overall_status",
            "reviewer_action",
        )
        if not isinstance(prompt_contract_review.get(field), str)
        or not str(prompt_contract_review.get(field) or "").strip()
    ]
    invalid_fields: list[str] = []
    if str(prompt_contract_review.get("schema_version") or "").strip() != "1.0":
        invalid_fields.append("schema_version")
    if (
        str(prompt_contract_review.get("review_method") or "").strip()
        != "model_led_semantic_conformance_review"
    ):
        invalid_fields.append("review_method")
    overall_status = str(prompt_contract_review.get("overall_status") or "").strip()
    if overall_status not in PROMPT_CONTRACT_REVIEW_STATUSES:
        invalid_fields.append("overall_status")
    reviewer_action = str(prompt_contract_review.get("reviewer_action") or "").strip()
    if reviewer_action not in PROMPT_CONTRACT_REVIEW_ACTIONS:
        invalid_fields.append("reviewer_action")

    dimensions = prompt_contract_review.get("dimensions")
    missing_dimensions: list[str] = []
    invalid_dimensions: list[str] = []
    attention_dimensions: list[str] = []
    if not isinstance(dimensions, dict):
        missing_fields.append("dimensions")
        missing_dimensions.extend(PROMPT_CONTRACT_REVIEW_DIMENSIONS)
    else:
        for dimension in PROMPT_CONTRACT_REVIEW_DIMENSIONS:
            assessment = dimensions.get(dimension)
            if not isinstance(assessment, dict):
                missing_dimensions.append(dimension)
                continue
            status = str(assessment.get("status") or "").strip()
            analysis = str(assessment.get("analysis") or "").strip()
            if status not in PROMPT_CONTRACT_REVIEW_STATUSES or not analysis:
                invalid_dimensions.append(dimension)
                continue
            if status != "conforms":
                attention_dimensions.append(dimension)

    shape_valid = not (
        missing_fields or invalid_fields or missing_dimensions or invalid_dimensions
    )
    conformance_accepted = (
        shape_valid
        and not attention_dimensions
        and overall_status == "conforms"
        and reviewer_action == "accept"
    )
    return {
        "status": "pass" if conformance_accepted else "fail",
        "record_status": "complete" if shape_valid else "incomplete",
        "conformance_status": overall_status or "not_reviewed",
        "missing_fields": list(dict.fromkeys(missing_fields)),
        "invalid_fields": list(dict.fromkeys(invalid_fields)),
        "missing_dimensions": missing_dimensions,
        "invalid_dimensions": invalid_dimensions,
        "attention_dimensions": attention_dimensions,
        "reviewer_action": reviewer_action,
        "policy": (
            "shape_and_recorded-outcome_validation_only; semantic conformance is "
            "model-led and must be accepted explicitly"
        ),
    }


def validate_answer_contract(answer_contract: dict[str, Any]) -> dict[str, Any]:
    """Validate only the explicit handoff shape chosen by Codex or the user.

    Deterministic validation is justified here because it checks a stable JSON
    contract. It does not infer the legal domain, generation route, document
    type, jurisdiction, audience, or evidentiary posture.
    """

    missing_fields = [
        field
        for field in ANSWER_CONTRACT_REQUIRED_FIELDS
        if not isinstance(answer_contract.get(field), str)
        or (
            field != "jurisdiction"
            and not str(answer_contract.get(field) or "").strip()
        )
    ]
    invalid_fields = [
        field
        for field, allowed in ANSWER_CONTRACT_ENUMS.items()
        if str(answer_contract.get(field) or "").strip() not in allowed
    ]
    jurisdiction_status = str(answer_contract.get("jurisdiction_status") or "").strip()
    jurisdiction = str(answer_contract.get("jurisdiction") or "").strip()
    if jurisdiction_status in {"confirmed", "assumed"} and not jurisdiction:
        invalid_fields.append("jurisdiction")
    invalid_fields = list(dict.fromkeys(invalid_fields))
    return {
        "status": "pass" if not missing_fields and not invalid_fields else "fail",
        "missing_fields": missing_fields,
        "invalid_fields": invalid_fields,
        "policy": (
            "shape_validation_only; document type, route, jurisdiction, and "
            "validation posture are model-led or user-confirmed"
        ),
    }


def validate_prompt_text(
    question_text: str,
    prompt_text: str,
    *,
    answer_contract: dict[str, Any],
    prompt_contract_review: dict[str, Any],
    language: str = "auto",
    source_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Return mechanical checks plus the model-led conformance boundary."""

    normalized_prompt = prompt_text.strip()
    language_terms = LANGUAGE_LOCK_TERMS.get(language, LANGUAGE_LOCK_TERMS["auto"])
    inventory = inspect_question_text(question_text)
    jurisdiction_policy = jurisdiction_policy_for_question(
        language, inventory.language_hint, inventory.jurisdiction_hints
    )
    missing_anchors = _missing_anchors(question_text, normalized_prompt)
    missing_questions = _missing_explicit_questions(question_text, normalized_prompt)
    answer_contract_audit = validate_answer_contract(answer_contract)
    prompt_contract_review_audit = validate_prompt_contract_review(
        prompt_contract_review
    )
    evidence_display = str(answer_contract.get("evidence_display") or "")
    document_type = str(answer_contract.get("document_type") or "").strip()
    citation_rules_present = _contains_any(normalized_prompt, CITATION_TERMS)
    if evidence_display in {"source_record_only", "not_specified"}:
        citation_rules_present = citation_rules_present or _contains_any(
            normalized_prompt,
            SOURCE_RECORD_TERMS,
        )
    checks = {
        "non_empty_prompt": bool(normalized_prompt),
        "language_lock": _contains_any(normalized_prompt, language_terms),
        "source_requirements": _contains_any(normalized_prompt, SOURCE_TERMS),
        "citation_rules": citation_rules_present,
        "jurisdiction_lock": _contains_all_term_groups(
            normalized_prompt, jurisdiction_policy["required_notice_terms"]
        ),
        "clarification_policy": _contains_any(normalized_prompt, CLARIFICATION_TERMS),
        "output_structure": bool(document_type)
        and document_type.casefold() in normalized_prompt.casefold(),
        "uncertainty_policy": _contains_any(normalized_prompt, UNCERTAINTY_TERMS),
        "research_lens": _has_research_lens(normalized_prompt),
        "fact_anchors_preserved": not missing_anchors,
        "answer_contract": answer_contract_audit["status"] == "pass",
        "prompt_contract_review": prompt_contract_review_audit["status"] == "pass",
    }
    if inventory.requires_phased_workflow:
        checks.update(
            {
                "phased_workflow": _contains_any(
                    normalized_prompt, PHASED_WORKFLOW_TERMS
                ),
                "chronology_control": _contains_any(
                    normalized_prompt, CHRONOLOGY_TERMS
                ),
                "confidence_protocol": _contains_any(
                    normalized_prompt, CONFIDENCE_TERMS
                ),
                "authority_safety_protocol": _requires_grouped_terms(
                    normalized_prompt, AUTHORITY_SAFETY_TERM_GROUPS
                ),
                "legal_realism_protocol": _requires_grouped_terms(
                    normalized_prompt, LEGAL_REALISM_TERM_GROUPS
                ),
            }
        )
        if "trust_asset_recovery" in inventory.topic_flags:
            checks["trust_scope_control"] = _requires_grouped_terms(
                normalized_prompt, TRUST_SCOPE_TERM_GROUPS
            )
        if "tax" in inventory.topic_flags:
            checks["tax_scope_control"] = _requires_grouped_terms(
                normalized_prompt, TAX_SCOPE_TERM_GROUPS
            )
    failed = [name for name, passed in checks.items() if not passed]
    status = "pass" if not failed else "fail"
    normalized_source_domains = (
        _normalize_source_domains(source_domains)
        if source_domains is not None
        else _extract_source_domains(normalized_prompt)
    )
    return {
        "status": status,
        "checks": checks,
        "angle_confirmation": angle_confirmation_for_question(inventory),
        "jurisdiction_policy": jurisdiction_policy,
        "jurisdiction_confirmation": jurisdiction_confirmation_for_question(
            inventory, jurisdiction_policy
        ),
        "source_domains": normalized_source_domains,
        "source_domain_policy": "model_curated_only",
        "source_domain_extraction_policy": "mechanical_prompt_or_sidecar_extraction_only",
        "topic_flags": inventory.topic_flags,
        "requires_phased_workflow": inventory.requires_phased_workflow,
        "missing_fact_anchors": missing_anchors,
        "missing_explicit_questions": missing_questions,
        "observations": {
            "literal_explicit_questions_preserved": not missing_questions,
            "literal_question_overlap_is_gating": False,
            "meaning": (
                "Literal overlap is an observation only; semantic preservation "
                "is decided in prompt_contract_review.json."
            ),
        },
        "answer_contract": answer_contract,
        "answer_contract_audit": answer_contract_audit,
        "prompt_contract_review": prompt_contract_review,
        "prompt_contract_review_audit": prompt_contract_review_audit,
        "assurance_boundary": {
            "mechanically_validated": (
                "answer-contract and review-record shape, exact dates, amounts, "
                "percentages, URLs, legal-form entity names, explicit prompt "
                "controls, source-domain parsing, and artifact packaging"
            ),
            "model_led": (
                "question meaning, material fact preservation, generation route, "
                "document type, purpose, audience, output language, jurisdiction, "
                "evidence display, research lens, validation policy, and source "
                "strategy"
            ),
            "not_certified": (
                "A passing audit records an accepted semantic review and passing "
                "mechanical controls; it does not certify legal correctness."
            ),
        },
        "failed_checks": failed,
    }


def _package_markdown(
    question_text: str, prompt_text: str, audit: dict[str, Any]
) -> str:
    """Return a human handoff package without duplicating the full prompt."""

    failed = audit.get("failed_checks") or []
    language = _package_language(audit)
    spanish = language == "es"
    failed_text = ", ".join(failed) if failed else ("ninguno" if spanish else "none")
    source_domains = audit.get("source_domains") or []
    answer_contract = audit.get("answer_contract") or {}
    contract_review = audit.get("prompt_contract_review") or {}
    contract_review_audit = audit.get("prompt_contract_review_audit") or {}
    deep_research = answer_contract.get("generation_route") == "chatgpt_deep_research"
    contract_labels = (
        (
            "Dominio de la pregunta",
            "Ruta de generación",
            "Tipo de documento",
            "Finalidad",
            "Destinatario",
            "Estado de la jurisdicción",
            "Jurisdicción",
            "Presentación de las fuentes",
            "Perfil de validación",
            "Alcance de validación",
            "Política de corrección",
            "Política de juicio profesional",
        )
        if spanish
        else (
            "Question domain",
            "Generation route",
            "Document type",
            "Purpose",
            "Audience",
            "Jurisdiction status",
            "Jurisdiction",
            "Evidence display",
            "Validation profile",
            "Validation scope",
            "Correction policy",
            "Professional-judgment policy",
        )
    )
    contract_values = (
        answer_contract.get("question_domain", ""),
        answer_contract.get("generation_route", ""),
        answer_contract.get("document_type", ""),
        answer_contract.get("purpose", ""),
        answer_contract.get("audience", ""),
        answer_contract.get("jurisdiction_status", ""),
        answer_contract.get("jurisdiction", "")
        or ("sin resolver" if spanish else "unresolved"),
        answer_contract.get("evidence_display", ""),
        answer_contract.get("validation_profile", ""),
        answer_contract.get("validation_scope", ""),
        answer_contract.get("correction_policy", ""),
        answer_contract.get("judgment_policy", ""),
    )
    contract_lines = [
        f"- {label}: {value}"
        for label, value in zip(contract_labels, contract_values, strict=True)
    ]
    if spanish:
        use_lines = (
            [
                "- Pegue `optimized_prompt.md` en Deep Research.",
                "- Pegue `source_domains_comma.txt` en el campo de sitios web de Deep Research.",
            ]
            if deep_research
            else [
                "- Use `optimized_prompt.md` como instrucciones para generar la respuesta.",
                "- Conserve `source_domains.txt` como lista de fuentes para la generación.",
            ]
        )
        use_lines.extend(
            [
                "- Conserve `answer_contract.json` con la respuesta generada.",
                "- Conserve `prompt_contract_review.json` como revisión semántica del prompt.",
                "- Considere `prompt_audit.json` como metadatos de validación legibles por máquina.",
            ]
        )
    else:
        use_lines = (
            [
                "- Paste `optimized_prompt.md` into Deep Research.",
                "- Paste `source_domains_comma.txt` into the Deep Research websites field.",
            ]
            if deep_research
            else [
                "- Use `optimized_prompt.md` as the answer-generation instructions.",
                "- Keep `source_domains.txt` as the source list for generation.",
            ]
        )
        use_lines.extend(
            [
                "- Keep `answer_contract.json` with the generated answer.",
                "- Keep `prompt_contract_review.json` as the semantic prompt review.",
                "- Treat `prompt_audit.json` as machine-readable validation metadata.",
            ]
        )
    source_domain_text = (
        "\n".join(f"- {domain}" for domain in source_domains)
        if source_domains
        else (
            (
                "No se proporcionó ni extrajo una lista explícita de sitios web. "
                "Añada un archivo auxiliar de dominios y vuelva a ejecutar la "
                "validación si Deep Research necesita el campo de sitios web."
            )
            if spanish
            else (
                "No explicit website list was provided or extracted. Add a sidecar "
                "source-domain file and rerun validation if Deep Research needs "
                "a websites field."
            )
        )
    )
    if spanish:
        sections = [
            "# Paquete de optimización del prompt",
            f"Estado de la auditoría: {audit.get('status')}",
            f"Controles fallidos: {failed_text}",
            "## Contrato de respuesta",
            "\n".join(contract_lines),
            "## Enfoque de investigación dirigido por el modelo",
            "\n".join(
                [
                    "- Responsable de la decisión: Codex o el usuario",
                    "- La inspección mecánica no selecciona el planteamiento, el objetivo ni el alcance jurídico.",
                    "- Las decisiones semánticas se documentan en el prompt y en su revisión de conformidad.",
                ]
            ),
            "## Revisión semántica del contrato del prompt",
            "\n".join(
                [
                    f"- Estado general: {contract_review.get('overall_status', 'not_reviewed')}",
                    f"- Acción del revisor: {contract_review.get('reviewer_action', 'mark_unclear')}",
                    f"- Estado de auditoría: {contract_review_audit.get('status', 'fail')}",
                    (
                        "- Dimensiones que requieren atención: "
                        f"{', '.join(contract_review_audit.get('attention_dimensions') or []) or 'ninguna'}"
                    ),
                ]
            ),
            "## Dominios de fuentes cualificados",
            source_domain_text,
            "## Pregunta de origen",
            question_text.strip(),
            "## Cómo utilizar los archivos",
            "\n".join(use_lines),
            "## Ubicación del prompt optimizado",
            "`optimized_prompt.md`",
        ]
        return "\n\n".join(sections).strip() + "\n"
    return (
        "\n\n".join(
            [
                "# Prompt Optimizer Package",
                f"Audit status: {audit.get('status')}",
                f"Failed checks: {failed_text}",
                "## Answer Contract",
                "\n".join(contract_lines),
                "## Model-Led Research Lens",
                "\n".join(
                    [
                        "- Decision owner: Codex or the user",
                        "- Mechanical inspection does not select posture, objective, or legal scope.",
                        "- Semantic choices are documented in the prompt and its conformance review.",
                    ]
                ),
                "## Prompt-Contract Semantic Review",
                "\n".join(
                    [
                        f"- Overall status: {contract_review.get('overall_status', 'not_reviewed')}",
                        f"- Reviewer action: {contract_review.get('reviewer_action', 'mark_unclear')}",
                        f"- Audit status: {contract_review_audit.get('status', 'fail')}",
                        (
                            "- Attention dimensions: "
                            f"{', '.join(contract_review_audit.get('attention_dimensions') or []) or 'none'}"
                        ),
                    ]
                ),
                "## Qualified Source Domains",
                source_domain_text,
                "## Source Question",
                question_text.strip(),
                "## What to Use",
                "\n".join(use_lines),
                "## Optimized Prompt Location",
                "`optimized_prompt.md`",
            ]
        ).strip()
        + "\n"
    )


def render_prompt_package(
    question_text: str,
    prompt_text: str,
    audit: dict[str, Any],
) -> str:
    """Render package Markdown from reviewed question, prompt, and audit state."""

    return _package_markdown(question_text, prompt_text, audit)


def _package_language(audit: dict[str, Any]) -> str:
    """Resolve the human package language without changing audit codes."""

    requested = str(audit.get("language") or "auto").strip().lower().replace("_", "-")
    if requested.startswith("es"):
        return "es"
    policy = audit.get("jurisdiction_policy")
    if isinstance(policy, dict):
        effective = str(policy.get("language") or "").strip().lower().replace("_", "-")
        if effective.startswith("es"):
            return "es"
    return "en"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write stable UTF-8 JSON."""

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_validation(
    question_text: str,
    prompt_text: str,
    output_dir: Path,
    *,
    answer_contract: dict[str, Any],
    prompt_contract_review: dict[str, Any],
    language: str = "auto",
    source_domains: list[str] | None = None,
    input_paths: list[Path] | None = None,
    client_engagement: dict[str, Any] | None = None,
    client_run_id: str | None = None,
) -> dict[str, Path]:
    """Write validation artifacts and return their paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_source_domains = (
        _normalize_source_domains(source_domains)
        if source_domains is not None
        else _extract_source_domains(prompt_text)
    )
    run_intake = write_run_intake(
        output_dir,
        question_text=question_text,
        prompt_text=prompt_text,
        language=language,
        source_domains=normalized_source_domains,
        answer_contract=answer_contract,
        prompt_contract_review=prompt_contract_review,
        input_paths=input_paths or [],
        client_engagement=client_engagement,
        client_run_id=client_run_id,
    )
    audit = validate_prompt_text(
        question_text,
        prompt_text,
        answer_contract=answer_contract,
        prompt_contract_review=prompt_contract_review,
        language=language,
        source_domains=normalized_source_domains,
    )
    audit["language"] = language
    prompt_path = output_dir / "optimized_prompt.md"
    answer_contract_path = output_dir / "answer_contract.json"
    prompt_contract_review_path = output_dir / "prompt_contract_review.json"
    audit_path = output_dir / "prompt_audit.json"
    package_path = output_dir / "prompt_package.md"
    source_domains_path = output_dir / "source_domains.txt"
    source_domains_comma_path = output_dir / "source_domains_comma.txt"
    readme_path = output_dir / "README_HUMAN.md"
    prompt_path.write_text(prompt_text.strip() + "\n", encoding="utf-8")
    write_json(answer_contract_path, answer_contract)
    write_json(prompt_contract_review_path, prompt_contract_review)
    write_json(audit_path, audit)
    source_domains_path.write_text(
        "\n".join(str(domain) for domain in audit.get("source_domains") or []) + "\n",
        encoding="utf-8",
    )
    source_domains_comma_path.write_text(
        ", ".join(str(domain) for domain in audit.get("source_domains") or []) + "\n",
        encoding="utf-8",
    )
    package_path.write_text(
        render_prompt_package(question_text, prompt_text, audit),
        encoding="utf-8",
    )
    readme_path.write_text(_readme_markdown(audit), encoding="utf-8")
    paths = {
        "optimized_prompt": prompt_path,
        "answer_contract": answer_contract_path,
        "prompt_contract_review": prompt_contract_review_path,
        "prompt_audit": audit_path,
        "prompt_package": package_path,
        "source_domains": source_domains_path,
        "source_domains_comma": source_domains_comma_path,
        "readme_human": readme_path,
    }
    review_session = write_review_session_artifacts(
        output_dir,
        run_id=run_intake.run_id,
        run_intake_path=run_intake.path,
        question_text=question_text,
        audit=audit,
        paths=paths,
    )
    run_root = (
        Path(str(client_engagement["run_root"])).expanduser().resolve(strict=True)
        if client_engagement is not None
        else None
    )

    def persisted_path(path: Path) -> str:
        if run_root is None:
            return str(path)
        try:
            return (
                path.expanduser().resolve(strict=True).relative_to(run_root).as_posix()
            )
        except ValueError as exc:
            raise ValueError(
                "Prompt Optimizer review artifact is outside the current run."
            ) from exc

    audit["review_session"] = {
        "run_id": review_session.run_id,
        "run_intake_path": persisted_path(review_session.run_intake_path),
        "review_payload_path": persisted_path(review_session.review_payload_path),
        "ui_decisions_path": persisted_path(review_session.ui_decisions_path),
        "final_artifacts_path": persisted_path(review_session.final_artifacts_path),
        "review_item_count": review_session.review_item_count,
    }
    write_json(audit_path, audit)
    synchronize_final_artifact_sizes(review_session.final_artifacts_path)
    paths.update(
        {
            "run_intake": run_intake.path,
            "review_payload": review_session.review_payload_path,
            "ui_decisions": review_session.ui_decisions_path,
            "final_artifacts": review_session.final_artifacts_path,
        }
    )
    return paths


def _readme_markdown(audit: dict[str, Any]) -> str:
    """Return a short human usage guide for the generated files."""

    source_domains = audit.get("source_domains") or []
    answer_contract = audit.get("answer_contract") or {}
    deep_research = answer_contract.get("generation_route") == "chatgpt_deep_research"
    if _package_language(audit) == "es":
        if deep_research:
            website_instruction = (
                "2. Pegue `source_domains_comma.txt` en el campo de sitios web de Deep Research."
                if source_domains
                else (
                    "2. `source_domains_comma.txt` está vacío porque no se proporcionó "
                    "ni extrajo ninguna lista de sitios web."
                )
            )
        else:
            website_instruction = (
                "2. Use `source_domains.txt` como lista de fuentes para la generación."
            )
        first_instruction = (
            "1. Pegue `optimized_prompt.md` en Deep Research."
            if deep_research
            else "1. Use `optimized_prompt.md` como instrucciones para generar la respuesta."
        )
        return "\n".join(
            [
                "# Cómo utilizar estos archivos",
                "",
                first_instruction,
                website_instruction,
                "3. Verifique que `prompt_contract_review.json` tenga estado `conforms` y acción `accept`.",
                "4. Conserve `answer_contract.json` con la respuesta para la validación.",
                "5. Use `source_domains.txt` para consultar la lista con un sitio web por línea.",
                (
                    "6. Consulte `prompt_audit.json` solo para depurar la validación; "
                    "registra qué controles del plugin se superaron."
                ),
                "",
            ]
        )
    if deep_research:
        website_instruction = (
            "2. Paste `source_domains_comma.txt` into the Deep Research websites field."
            if source_domains
            else (
                "2. `source_domains_comma.txt` is empty because no website list was "
                "provided or extracted."
            )
        )
    else:
        website_instruction = (
            "2. Use `source_domains.txt` as the source list for generation."
        )
    first_instruction = (
        "1. Paste `optimized_prompt.md` into Deep Research."
        if deep_research
        else "1. Use `optimized_prompt.md` as the instructions for generating the answer."
    )
    return "\n".join(
        [
            "# How to use these files",
            "",
            first_instruction,
            website_instruction,
            "3. Verify that `prompt_contract_review.json` records `conforms` and `accept`.",
            "4. Keep `answer_contract.json` with the answer for validation.",
            "5. Use `source_domains.txt` for the readable one-website-per-line list.",
            (
                "6. Ignore `prompt_audit.json` unless you are debugging validation; "
                "it only records which plugin checks passed."
            ),
            "",
        ]
    )


def _read_text(path: Path) -> str:
    """Read a UTF-8 text file."""

    return path.read_text(encoding="utf-8").strip()


def main() -> int:
    """Run prompt validation from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "question_file",
        type=Path,
        help="UTF-8 file containing the source question or case.",
    )
    parser.add_argument(
        "prompt_file",
        type=Path,
        help="UTF-8 file containing the Codex-written optimized prompt.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help=(
            "Directory for optimized_prompt.md, prompt_audit.json, "
            "prompt_contract_review.json, prompt_package.md, source_domains.txt, "
            "source_domains_comma.txt, and README_HUMAN.md."
        ),
    )
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument(
        "--language", choices=["auto", "it", "en", "fr", "de", "es"], default="auto"
    )
    parser.add_argument(
        "--source-domains-file",
        type=Path,
        help=(
            "Optional UTF-8 file containing model-curated websites/domains, "
            "separated by commas, whitespace, or newlines."
        ),
    )
    parser.add_argument(
        "--answer-contract-file",
        type=Path,
        required=True,
        help=(
            "UTF-8 JSON object written by Codex with the selected answer type, "
            "generation route, audience, jurisdiction status, and validation profile."
        ),
    )
    parser.add_argument(
        "--prompt-contract-review-file",
        type=Path,
        required=True,
        help=(
            "UTF-8 JSON object containing Codex's model-led semantic review of "
            "the optimized prompt against the question and answer contract."
        ),
    )
    args = parser.parse_args()

    input_paths = [
        args.question_file,
        args.prompt_file,
        args.answer_contract_file,
        args.prompt_contract_review_file,
    ]
    if args.source_domains_file is not None:
        input_paths.append(args.source_domains_file)
    try:
        client_context = load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="prompt-optimizer",
            input_paths=input_paths,
            output_dir=args.output_dir,
        )
    except AssuranceContractError as exc:
        parser.error(str(exc))

    question_text = _read_text(args.question_file)
    prompt_text = _read_text(args.prompt_file)
    answer_contract = json.loads(args.answer_contract_file.read_text(encoding="utf-8"))
    if not isinstance(answer_contract, dict):
        parser.error("answer_contract_file must contain a JSON object")
    prompt_contract_review = json.loads(
        args.prompt_contract_review_file.read_text(encoding="utf-8")
    )
    if not isinstance(prompt_contract_review, dict):
        parser.error("prompt_contract_review_file must contain a JSON object")
    if not question_text:
        parser.error("question_file is empty")
    if not prompt_text:
        parser.error("prompt_file is empty")
    source_domains = None
    if args.source_domains_file is not None:
        source_domains = _parse_source_domains_text(
            _read_text(args.source_domains_file)
        )
    write_validation(
        question_text,
        prompt_text,
        args.output_dir,
        answer_contract=answer_contract,
        prompt_contract_review=prompt_contract_review,
        language=args.language,
        source_domains=source_domains,
        input_paths=input_paths,
        client_engagement=client_context,
        client_run_id=str(client_context["run_id"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
