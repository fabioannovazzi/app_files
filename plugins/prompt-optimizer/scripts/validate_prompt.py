"""Validate and package a Codex-written Deep Research prompt."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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
    from .review_session import write_review_session_artifacts, write_run_intake
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
    write_review_session_artifacts = _review_session.write_review_session_artifacts
    write_run_intake = _review_session.write_run_intake

__all__ = [
    "render_prompt_package",
    "validate_prompt_text",
    "write_validation",
]

LANGUAGE_LOCK_TERMS = {
    "it": ("lingua", "italiano"),
    "en": ("language", "english"),
    "fr": ("langue", "francais", "français"),
    "de": ("sprache", "deutsch"),
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
STRUCTURE_TERMS = (
    "premise",
    "premises",
    "analysis",
    "conclusion",
    "notes",
    "premesse",
    "analisi",
    "conclusioni",
    "note",
    "analyse",
    "schlussfolgerung",
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
    """Return fact anchors found in the source question but missing in the prompt."""

    inventory = inspect_question_text(question_text)
    anchors = (
        inventory.dates
        + inventory.years
        + inventory.amounts
        + inventory.percentages
        + inventory.urls
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
    """Return explicit source questions not preserved verbatim or near-verbatim."""

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


def validate_prompt_text(
    question_text: str,
    prompt_text: str,
    *,
    language: str = "auto",
    source_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Return deterministic audit results for an optimized prompt."""

    normalized_prompt = prompt_text.strip()
    language_terms = LANGUAGE_LOCK_TERMS.get(language, LANGUAGE_LOCK_TERMS["auto"])
    inventory = inspect_question_text(question_text)
    jurisdiction_policy = jurisdiction_policy_for_question(
        language, inventory.language_hint, inventory.jurisdiction_hints
    )
    structure_hits = [
        term
        for term in STRUCTURE_TERMS
        if term.casefold() in normalized_prompt.casefold()
    ]
    missing_anchors = _missing_anchors(question_text, normalized_prompt)
    missing_questions = _missing_explicit_questions(question_text, normalized_prompt)
    checks = {
        "non_empty_prompt": bool(normalized_prompt),
        "language_lock": _contains_any(normalized_prompt, language_terms),
        "source_requirements": _contains_any(normalized_prompt, SOURCE_TERMS),
        "citation_rules": _contains_any(normalized_prompt, CITATION_TERMS),
        "jurisdiction_lock": _contains_all_term_groups(
            normalized_prompt, jurisdiction_policy["required_notice_terms"]
        ),
        "clarification_policy": _contains_any(normalized_prompt, CLARIFICATION_TERMS),
        "output_structure": len(set(structure_hits)) >= 3,
        "uncertainty_policy": _contains_any(normalized_prompt, UNCERTAINTY_TERMS),
        "research_lens": _has_research_lens(normalized_prompt),
        "fact_anchors_preserved": not missing_anchors,
        "explicit_questions_preserved": not missing_questions,
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
        "failed_checks": failed,
    }


def _package_markdown(
    question_text: str, prompt_text: str, audit: dict[str, Any]
) -> str:
    """Return a human handoff package without duplicating the full prompt."""

    failed = audit.get("failed_checks") or []
    failed_text = ", ".join(failed) if failed else "none"
    inventory = inspect_question_text(question_text)
    source_domains = audit.get("source_domains") or []
    source_domain_text = (
        "\n".join(f"- {domain}" for domain in source_domains)
        if source_domains
        else (
            "No explicit website list was provided or extracted. Add a sidecar "
            "source-domain file and rerun validation if Deep Research needs "
            "a websites field."
        )
    )
    return (
        "\n\n".join(
            [
                "# Prompt Optimizer Package",
                f"Audit status: {audit.get('status')}",
                f"Failed checks: {failed_text}",
                "## Deterministic Research Lens",
                "\n".join(
                    [
                        f"- Posture: {inventory.posture_hint}",
                        f"- Objective: {inventory.objective_hint}",
                        f"- Scope: {inventory.scope_hint}",
                        f"- Topic flags: {', '.join(inventory.topic_flags) or 'none'}",
                        (
                            "- Requires phased workflow: "
                            f"{inventory.requires_phased_workflow}"
                        ),
                    ]
                ),
                "## Qualified Source Domains",
                source_domain_text,
                "## Source Question",
                question_text.strip(),
                "## What to Use",
                "\n".join(
                    [
                        "- Paste `optimized_prompt.md` into Deep Research.",
                        (
                            "- Paste `source_domains_comma.txt` into the Deep "
                            "Research websites field."
                        ),
                        (
                            "- Use `source_domains.txt` only when you want the "
                            "same list one website per line."
                        ),
                        "- Treat `prompt_audit.json` as machine-readable validation metadata.",
                    ]
                ),
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
    language: str = "auto",
    source_domains: list[str] | None = None,
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
    )
    audit = validate_prompt_text(
        question_text,
        prompt_text,
        language=language,
        source_domains=normalized_source_domains,
    )
    audit["language"] = language
    prompt_path = output_dir / "optimized_prompt.md"
    audit_path = output_dir / "prompt_audit.json"
    package_path = output_dir / "prompt_package.md"
    source_domains_path = output_dir / "source_domains.txt"
    source_domains_comma_path = output_dir / "source_domains_comma.txt"
    readme_path = output_dir / "README_HUMAN.md"
    prompt_path.write_text(prompt_text.strip() + "\n", encoding="utf-8")
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
    audit["review_session"] = {
        "run_id": review_session.run_id,
        "run_intake_path": str(review_session.run_intake_path),
        "review_payload_path": str(review_session.review_payload_path),
        "ui_decisions_path": str(review_session.ui_decisions_path),
        "final_artifacts_path": str(review_session.final_artifacts_path),
        "review_item_count": review_session.review_item_count,
    }
    write_json(audit_path, audit)
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
    website_instruction = (
        "2. Paste `source_domains_comma.txt` into the Deep Research websites field."
        if source_domains
        else (
            "2. `source_domains_comma.txt` is empty because no website list was "
            "provided or extracted."
        )
    )
    return "\n".join(
        [
            "# How to use these files",
            "",
            "1. Paste `optimized_prompt.md` into Deep Research.",
            website_instruction,
            "3. Use `source_domains.txt` for the readable one-website-per-line list.",
            (
                "4. Ignore `prompt_audit.json` unless you are debugging validation; "
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
            "prompt_package.md, source_domains.txt, source_domains_comma.txt, "
            "and README_HUMAN.md."
        ),
    )
    parser.add_argument(
        "--language", choices=["auto", "it", "en", "fr", "de"], default="auto"
    )
    parser.add_argument(
        "--source-domains-file",
        type=Path,
        help=(
            "Optional UTF-8 file containing model-curated websites/domains, "
            "separated by commas, whitespace, or newlines."
        ),
    )
    args = parser.parse_args()

    question_text = _read_text(args.question_file)
    prompt_text = _read_text(args.prompt_file)
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
        language=args.language,
        source_domains=source_domains,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
