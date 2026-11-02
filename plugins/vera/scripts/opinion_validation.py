"""Apply Vera's reader-facing citation policy to the shared opinion validator."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

__all__ = [
    "build_audit",
    "render_validation_package",
    "try_write_docx",
    "validate_answer_contract",
    "verify_opinion",
    "write_validation_package",
]

# Load a private instance of the shared engine. Vera extends its final artifact
# check without changing Lucia, standalone validation or archived receipts.
_product = Path(__file__).resolve().parents[1]
_shared_path = (
    _product / "modules/deep-research-validator/scripts/package_validation.py"
)
if not _shared_path.is_file():
    _shared_path = (
        _product.parent / "deep-research-validator/scripts/package_validation.py"
    )
_spec = importlib.util.spec_from_file_location(
    "vera_shared_opinion_validation", _shared_path
)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load opinion validator at {_shared_path}")
_shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_shared)
_shared_audit = _shared.build_audit


_LINK = re.compile(r"\[([^\]\n]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)")


def _readable(label: str) -> bool:
    """Numeric markers, raw URLs and bare source IDs do not name an authority."""
    label = label.strip()
    return bool(label) and not (
        label.isdecimal()
        or re.fullmatch(r"source-\d+", label, re.I)
        or label.startswith(("http://", "https://", "/"))
    )


def _beside(
    tail: str,
    checks: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    limit: str,
    needs_source: bool,
) -> bool:
    """Consume only the citation group immediately following this conclusion."""
    possible = []
    selected = [c for c in checks if c.get("opinion_citation")]
    for check in selected or checks:
        if check.get("identity_status") != "matches_cited_source":
            continue
        resolution, source = _shared._resolve_source(
            str(check.get("source_ref") or ""), sources
        )
        if (
            resolution != "resolved"
            or source is None
            or source.get("status") != "available"
        ):
            continue
        urls = {
            source[key]
            for key in ("url", "requested_url", "final_url")
            if isinstance(source.get(key), str)
            and source[key].startswith(("https://", "http://"))
        }
        possible.append((check, urls))
    # Ignore only trailing emphasis and sentence punctuation, never another line of prose.
    tail = tail.lstrip(" \t*_.,:;!?")
    found = set()
    while tail:
        link = _LINK.match(tail)
        matches = []
        for check, urls in possible:
            label = check.get("opinion_citation")
            if (
                link
                and link[2].partition("#")[0] in {url.partition("#")[0] for url in urls}
                and _readable(link[1])
                and (not label or label == link[1])
            ):
                matches.append((link[0], (check["source_ref"], label)))
            elif (
                not urls
                and isinstance(label, str)
                and _readable(label)
                and tail.startswith(f"({label})")
            ):
                matches.append((f"({label})", (check["source_ref"], label)))
        if not matches:
            if link:
                return False
            break
        token, ref = matches[0]
        found.add(ref)
        tail = tail[len(token) :].lstrip(" \t,;")
    return (
        (not needs_source or bool(found))
        and all(
            (c.get("source_ref"), c.get("opinion_citation")) in found for c in selected
        )
        and (not limit or tail.lstrip(". ").startswith(limit))
    )


def _statement(claim: dict[str, Any]) -> str:
    """Use the corrected wording if the reviewer changed the conclusion."""
    disposition = claim.get("disposition") or {}
    return str(
        disposition.get("revised_claim") or claim.get("claim_text") or ""
    ).strip()


def _citation_errors(review: dict[str, Any], inventory: dict[str, Any]) -> list[str]:
    """Check placement only; the substantive review owns coverage and support."""
    document = str(review.get("validated_document") or "")
    sources = [s for s in inventory.get("sources") or [] if isinstance(s, dict)]
    failures = []
    for index, claim in enumerate(review.get("claims") or [], 1):
        if not isinstance(claim, dict) or claim.get("materiality") != "material":
            continue
        disposition = claim.get("disposition") or {}
        if not isinstance(disposition, dict) or disposition.get("status") == "remove":
            continue
        statement = _statement(claim)
        limit = str(claim.get("opinion_limit") or "").strip()
        checks = [c for c in claim.get("source_checks") or [] if isinstance(c, dict)]
        support = (claim.get("support") or {}).get("status")
        judgment = (claim.get("professional_judgment") or {}).get("status")
        needs_source = support in {"supported", "partially_supported", "contradicted"}
        needs_limit = support != "supported" or judgment in {
            "professional_judgment_required",
            "uncertain",
            "contested",
        }
        occurrences = (
            list(re.finditer(re.escape(statement), document)) if statement else []
        )
        if (
            not occurrences
            or (needs_limit and not limit)
            or not all(
                _beside(document[m.end() :], checks, sources, limit, needs_source)
                for m in occurrences
            )
        ):
            failures.append(
                f"material_conclusion_evidence:{claim.get('claim_index', index)}"
            )
    return failures


def build_audit(
    document_inventory: dict[str, Any],
    source_inventory: dict[str, Any],
    claims_review: dict[str, Any],
    answer_contract: dict[str, Any],
    *,
    source_base_dir: Path | None = None,
    require_opinion: bool = False,
) -> dict[str, Any]:
    """Keep incomplete opinions available for correction, without marking them ready."""
    audit = _shared_audit(
        document_inventory,
        source_inventory,
        claims_review,
        answer_contract,
        source_base_dir=source_base_dir,
    )
    if (
        not claims_review.get("validated_document")
        or audit["record_integrity_status"] != "record_complete"
    ):
        return audit
    # A client-facing letter can explicitly contract for internal source
    # records. The final Vera opinion check always examines the visible text.
    if (
        not require_opinion
        and answer_contract.get("evidence_display") == "source_record_only"
        and not answer_contract.get("vera_opinion")
        and answer_contract.get("adversarial_policy") != "required"
    ):
        return audit
    failures = _citation_errors(claims_review, source_inventory)
    if audit["coverage_scope"] != "all_material_claims":
        failures.append("opinion_material_claim_coverage")
    audit["opinion_citations"] = "needs_revision" if failures else "checked"
    if failures:
        audit["failed_checks"].extend(failures)
        audit["status"] = audit["record_integrity_status"] = "record_incomplete"
        audit["delivery_readiness"] = "blocked"
    return audit


# Only this private instance of the writer uses the Vera opinion policy.
_shared.build_audit = build_audit
render_validation_package = _shared.render_validation_package
try_write_docx = _shared.try_write_docx
validate_answer_contract = _shared.validate_answer_contract
write_validation_package = _shared.write_validation_package


def verify_opinion(directory: Path) -> None:
    """Check the issued Markdown itself, including both positions in a combined run."""
    phases = (
        [directory / "position", directory / "adversarial"]
        if any((directory / phase).is_dir() for phase in ("position", "adversarial"))
        else [directory]
    )
    positions = []
    for phase in phases:
        if phase.is_symlink():
            raise ValueError("The opinion phase must be inside the selected run.")
        for name in (
            "claims_review.json",
            "validated_document.md",
            "document_inventory.json",
            "source_inventory.json",
            "answer_contract.json",
        ):
            if (phase / name).is_symlink():
                raise ValueError(f"{name}: expected a file in the selected opinion")
        review = json.loads((phase / "claims_review.json").read_bytes())
        text = (phase / "validated_document.md").read_text(encoding="utf-8").strip()
        if not text or text != str(review.get("validated_document") or "").strip():
            raise ValueError(
                f"{phase.name}: the opinion differs from its reviewed text"
            )
        sources = json.loads((phase / "source_inventory.json").read_bytes())
        audit = build_audit(
            json.loads((phase / "document_inventory.json").read_bytes()),
            sources,
            review,
            json.loads((phase / "answer_contract.json").read_bytes()),
            source_base_dir=phase,
            require_opinion=True,
        )
        if audit["record_integrity_status"] != "record_complete" or audit[
            "delivery_readiness"
        ] in {"blocked", "not_reliable", "revision_required"}:
            raise ValueError(
                f"{phase.name}: {audit['delivery_readiness']} {audit['failed_checks']}"
            )

        positions.append((review, sources))

    if len(positions) == 2:
        comparison_path = directory / "opinion_comparison.md"
        assessment_path = directory / "adversarial_assessment.json"
        if comparison_path.is_symlink() or assessment_path.is_symlink():
            raise ValueError("Expected comparison files inside the selected run.")
        comparison = comparison_path.read_text(encoding="utf-8")
        summary = json.loads(assessment_path.read_bytes())["comparison"]
        for key, (review, sources) in zip(
            ("original_conclusion", "opposing_conclusion"), positions
        ):
            text = summary[key]
            claims = [
                claim
                for claim in review["claims"]
                if claim.get("materiality") == "material"
                and (claim.get("disposition") or {}).get("status") != "remove"
                and _statement(claim)
                and _statement(claim) in text
            ]
            if (
                not claims
                or text not in comparison
                or _citation_errors(
                    {"claims": claims, "validated_document": text}, sources
                )
            ):
                raise ValueError(
                    f"comparison: cite the reviewed {key} beside its statement"
                )


if __name__ == "__main__":
    if sys.argv[1:2] == ["verify"]:
        if len(sys.argv) != 3:
            sys.exit("Usage: opinion_validation.py verify REVIEW_DIRECTORY")
        try:
            verify_opinion(Path(sys.argv[2]))
        except (OSError, ValueError) as error:
            sys.exit(str(error))
    else:
        sys.exit(_shared.main())
