from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import polars as pl
from polars.exceptions import NoDataError

# Allow running the script directly without installing the package
sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.llm.llm_call_wrapper import init_llm_wrapper
from modules.llm.model_router import query_llm_return_json
from modules.utilities.session_context import SessionContext

__all__ = [
    "extract_claims_for_validation",
    "validate_analysis_markdown",
    "write_validation_artifacts",
]

REQUIRED_SECTION_LABELS = [
    "Winning now",
    "Brand context",
    "PDP/review validation of winners",
    "Innovation layer",
    "Innovation vs winners",
    "What did not produce a clear signal",
    "Standout products",
    "Factual synthesis",
]
ANALYTICAL_RECAP_LABEL = "Analytical recap block"
ANALYTICAL_RECAP_LABEL_ALIASES = [
    ANALYTICAL_RECAP_LABEL,
    "Analytical recap",
]
ANALYTICAL_RECAP_FIELD_LABELS = [
    "Winning now",
    "Emerging signal",
    "Brand effect level",
    "Confidence",
    "Most relevant examples",
]
LEVEL_VALUE_CHOICES = {"high", "medium", "low"}
BRAND_NOISE_TOKENS = {"professional", "professionnel"}
PRODUCT_NOISE_TOKENS = BRAND_NOISE_TOKENS | {
    "advanced",
    "ammonia",
    "color",
    "coloring",
    "colour",
    "cream",
    "creme",
    "free",
    "hair",
    "haircolor",
    "liqui",
    "new",
    "no",
    "oz",
    "performance",
    "permanent",
}
SYNTHETIC_BUNDLE_CLUSTER_MARKERS = {
    "cluster",
    "clusters",
    "story",
    "system",
    "systems",
    "language",
    "framing",
    "overlay",
}
NARRATIVE_REVIEW_VERDICTS = (
    "supported",
    "partly_supported",
    "unsupported",
    "overstated",
    "unclear",
)
NARRATIVE_QUERY_STOPWORDS = {
    "about",
    "across",
    "after",
    "also",
    "and",
    "are",
    "around",
    "because",
    "brand",
    "brands",
    "category",
    "claim",
    "claims",
    "clear",
    "clearest",
    "context",
    "does",
    "evidence",
    "example",
    "examples",
    "for",
    "from",
    "have",
    "here",
    "image",
    "images",
    "into",
    "layer",
    "line",
    "lines",
    "more",
    "most",
    "not",
    "now",
    "only",
    "other",
    "pack",
    "pdp",
    "product",
    "products",
    "review",
    "reviews",
    "same",
    "say",
    "signal",
    "story",
    "system",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "title",
    "titles",
    "top",
    "triples",
    "useful",
    "validates",
    "validation",
    "winner",
    "winners",
    "with",
}
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)%")
COUNT_RATIO_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
MULTIPLIER_RE = re.compile(r"(\d+(?:\.\d+)?)x")
BRAND_COUNT_RE = re.compile(r"across\s+(\d+)\s+brands?", re.IGNORECASE)
BACKTICK_RE = re.compile(r"`([^`]+)`")
BUNDLE_CONNECTOR_RE = re.compile(r"\s+(?:and|&)\s+", re.IGNORECASE)
PRODUCT_RANK_RE = re.compile(
    r"(?P<name>[^()\n]+?)\s*\(#(?P<rank>\d+)\s+Pareto\s+(?P<bucket>[ABC])\)",
    re.IGNORECASE,
)
PRODUCT_BUCKET_RE = re.compile(r"\bPareto\s+([ABC])\b", re.IGNORECASE)
PRODUCT_RANK_NUMBER_RE = re.compile(
    r"(?:rank(?:ed)?(?:\s+at)?\s*#?|position\s*#?|#)(\d+)\b",
    re.IGNORECASE,
)
TRAILING_PRODUCT_RANK_ANNOTATION_RE = re.compile(
    r"\s*\(#?\d+\s*(?:Pareto\s+)?[ABC]\)\s*$",
    re.IGNORECASE,
)
PRODUCT_RANK_ITEM_RE = re.compile(
    r"(?P<name>[^,\n]+?)\s*\(#(?P<rank>\d+)\s*(?:Pareto\s+)?(?P<bucket>[ABC])\)",
    re.IGNORECASE,
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9`])")
PERCENT_TOLERANCE = 0.11
MULTIPLIER_TOLERANCE = 0.02


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a category analysis markdown against a category evidence pack."
    )
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--analysis-markdown", type=Path, required=True)
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=None,
        help="Optional output prefix. Defaults to <analysis-markdown without suffix>.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when the overall status is fail.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM-guided claim extraction and fall back to sentence splitting.",
    )
    parser.add_argument(
        "--skip-output-contract",
        action="store_true",
        help="Skip validation of the expected report section and recap-block structure.",
    )
    parser.add_argument(
        "--skip-narrative-review",
        action="store_true",
        help="Skip the bounded LLM review for non-deterministic narrative claims.",
    )
    return parser.parse_args()


def _read_csv(path: Path) -> pl.DataFrame:
    return pl.read_csv(path, infer_schema_length=10000)


def _read_optional_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return _read_csv(path)
    except NoDataError:
        return pl.DataFrame()


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _fold_text(value: Any) -> str:
    text = _normalize_text(value).casefold()
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _canonical_text(value: Any) -> str:
    text = _fold_text(value)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _canonical_tokens(
    value: Any, *, ignored_tokens: set[str] | None = None
) -> set[str]:
    text = _fold_text(value)
    tokens = {token for token in re.split(r"[^a-z0-9]+", text) if token}
    if ignored_tokens:
        tokens = {token for token in tokens if token not in ignored_tokens}
    return tokens


def _bundle_parts(value: Any) -> tuple[str, ...]:
    text = _normalize_text(value).casefold()
    if not text:
        return ()

    def _normalize_bundle_part(part: str) -> str:
        part = part.strip()
        if "=" in part:
            _key, rhs = part.split("=", 1)
            part = rhs.strip()
        return part

    plus_parts = [
        _normalize_bundle_part(part) for part in text.split("+") if part.strip()
    ]
    if len(plus_parts) >= 2:
        return tuple(sorted(part for part in plus_parts if part))
    connector_parts = [
        _normalize_bundle_part(part)
        for part in BUNDLE_CONNECTOR_RE.split(text)
        if part.strip()
    ]
    if 2 <= len(connector_parts) <= 3:
        return tuple(sorted(part for part in connector_parts if part))
    return ()


def _bundle_label_matches(expected: Any, actual: Any) -> bool:
    if _canonical_text(expected) == _canonical_text(actual):
        return True
    expected_parts = _bundle_parts(expected)
    actual_parts = _bundle_parts(actual)
    return bool(expected_parts and actual_parts and expected_parts == actual_parts)


def _best_bundle_span(segment: str, label: str) -> tuple[int, int] | None:
    lowered_segment = segment.casefold()
    direct_label = _normalize_text(label).casefold()
    if direct_label:
        start = lowered_segment.find(direct_label)
        if start != -1:
            return start, start + len(direct_label)

    parts = tuple(part.casefold() for part in _bundle_parts(label))
    if not parts:
        return None

    part_spans: list[list[tuple[int, int]]] = []
    for part in parts:
        spans = [
            (match.start(), match.end())
            for match in re.finditer(re.escape(part), lowered_segment)
        ]
        if not spans:
            return None
        part_spans.append(spans)

    best_span: tuple[int, int] | None = None
    best_width: int | None = None
    for candidate in itertools.product(*part_spans):
        start = min(span[0] for span in candidate)
        end = max(span[1] for span in candidate)
        width = end - start
        if best_width is None or width < best_width:
            best_span = (start, end)
            best_width = width
    return best_span


def _localize_bundle_segment(segment: str, label: str) -> str:
    span = _best_bundle_span(segment, label)
    if span is None:
        return segment

    start, end = span
    clause_start = 0
    clause_end = len(segment)
    for match in re.finditer(r"[.;,]\s+", segment):
        if match.end() <= start:
            clause_start = match.end()
            continue
        if match.start() >= end:
            clause_end = match.start()
            break
    localized = segment[clause_start:clause_end].strip()
    return re.sub(r"^(?:and|but)\s+", "", localized, flags=re.IGNORECASE).strip()


def _looks_like_multi_claim_bundle_sentence(segment: str) -> bool:
    if len(BACKTICK_RE.findall(segment)) >= 2:
        return True
    if len(PERCENT_RE.findall(segment)) >= 4:
        return True
    lowered = segment.casefold()
    return (
        " vs " in lowered and " and " in lowered and ("`" in segment or "+" in segment)
    )


def _split_atomic_bundle_labels(label: str) -> list[str]:
    text = _normalize_text(label)
    if not text:
        return []
    parts = [
        _normalize_text(part)
        for part in re.split(r"\s*\+\s*", text)
        if _normalize_text(part)
    ]
    if len(parts) < 2:
        return []
    return parts


def _resolve_bundle_label_targets(
    segment: str,
    label: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any]:
    if _bundle_candidates(label, frames):
        return {"kind": "direct", "labels": [label]}

    lowered_segment = segment.casefold()
    atomic_parts = _split_atomic_bundle_labels(label)
    if "each" in lowered_segment and len(atomic_parts) >= 2:
        valid_atomic_parts = [
            part for part in atomic_parts if _bundle_candidates(part, frames)
        ]
        if len(valid_atomic_parts) == len(atomic_parts):
            return {"kind": "split", "labels": _unique_texts(valid_atomic_parts)}

    if "/" in label and any(
        marker in lowered_segment for marker in SYNTHETIC_BUNDLE_CLUSTER_MARKERS
    ):
        return {"kind": "non_deterministic", "reason": "synthetic_bundle_cluster"}

    return {"kind": "direct", "labels": [label]}


def _approx_equal(left: float | None, right: float | None, tolerance: float) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance


def _percent_from_fraction(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _split_segments(markdown_text: str) -> list[str]:
    segments: list[str] = []
    for block in markdown_text.splitlines():
        stripped = _normalize_text(block)
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        for sentence in SENTENCE_SPLIT_RE.split(stripped):
            sentence = _normalize_text(sentence)
            if sentence:
                segments.append(sentence)
    return segments


def _unique_texts(values: list[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _normalize_text(value)
        if not text:
            continue
        key = _canonical_text(text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def _plain_markdown_line(line: str) -> str:
    text = _normalize_text(line)
    if not text:
        return ""
    text = re.sub(r"^[#>\-\*\+\s]+", "", text)
    text = re.sub(r"^\d+[.)]\s*", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return _normalize_text(text)


def _line_starts_with_label(line: str, label: str) -> bool:
    plain = _plain_markdown_line(line).casefold()
    normalized_label = label.casefold()
    if plain == normalized_label:
        return True
    return plain.startswith(f"{normalized_label}:") or plain.startswith(
        f"{normalized_label} -"
    )


def _find_label_line(lines: list[str], label: str) -> int | None:
    for idx, line in enumerate(lines):
        if _line_starts_with_label(line, label):
            return idx
    return None


def _find_first_label_line(
    lines: list[str], labels: list[str]
) -> tuple[str, int] | None:
    for label in labels:
        idx = _find_label_line(lines, label)
        if idx is not None:
            return label, idx
    return None


def _extract_label_value(lines: list[str], label: str) -> str | None:
    start_idx = _find_label_line(lines, label)
    if start_idx is None:
        return None

    plain = _plain_markdown_line(lines[start_idx])
    value = re.sub(
        rf"^{re.escape(label)}\s*[:\-]?\s*",
        "",
        plain,
        count=1,
        flags=re.IGNORECASE,
    )
    if _normalize_text(value):
        return _normalize_text(value)

    for next_line in lines[start_idx + 1 :]:
        next_plain = _plain_markdown_line(next_line)
        if not next_plain:
            continue
        if any(
            _line_starts_with_label(next_line, other)
            for other in ANALYTICAL_RECAP_FIELD_LABELS
        ):
            return None
        return next_plain
    return None


def _normalize_level_value(value: str | None) -> str | None:
    if not value:
        return None
    matches = re.findall(r"\b(high|medium|low)\b", value.casefold())
    unique_matches = sorted(set(matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    return None


def _validate_output_contract(markdown_text: str) -> dict[str, list[dict[str, Any]]]:
    lines = markdown_text.splitlines()
    checked: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for label in REQUIRED_SECTION_LABELS:
        if _find_label_line(lines, label) is None:
            failures.append(
                {
                    "status": "fail",
                    "entity_type": "output_contract",
                    "entity": label,
                    "message": "missing required section",
                }
            )
            continue
        checked.append(
            {
                "status": "pass",
                "entity_type": "output_contract",
                "entity": label,
                "message": "required section present",
            }
        )

    recap_header = _find_first_label_line(lines, ANALYTICAL_RECAP_LABEL_ALIASES)
    if recap_header is None:
        failures.append(
            {
                "status": "fail",
                "entity_type": "output_contract",
                "entity": ANALYTICAL_RECAP_LABEL,
                "message": "missing analytical recap block",
            }
        )
        return {"checked": checked, "warnings": warnings, "failures": failures}
    recap_header_label, recap_header_idx = recap_header

    checked.append(
        {
            "status": "pass",
            "entity_type": "output_contract",
            "entity": recap_header_label,
            "message": "analytical recap block present",
        }
    )
    recap_lines = lines[recap_header_idx + 1 :]
    for label in ANALYTICAL_RECAP_FIELD_LABELS:
        value = _extract_label_value(recap_lines, label)
        if not value:
            failures.append(
                {
                    "status": "fail",
                    "entity_type": "output_contract",
                    "entity": label,
                    "message": "missing recap field value",
                }
            )
            continue
        if label in {"Brand effect level", "Confidence"}:
            normalized_level = _normalize_level_value(value)
            if normalized_level is None:
                failures.append(
                    {
                        "status": "fail",
                        "entity_type": "output_contract",
                        "entity": label,
                        "message": f"invalid recap value: {value}",
                    }
                )
                continue
            value = normalized_level
        checked.append(
            {
                "status": "pass",
                "entity_type": "output_contract",
                "entity": label,
                "message": f"recap value present: {value}",
            }
        )

    return {"checked": checked, "warnings": warnings, "failures": failures}


def _claim_extraction_system_prompt() -> str:
    return (
        "You are validating an analysis against a structured evidence package. "
        "Extract only concrete, checkable claims. "
        "Do not rewrite or improve the prose. "
        "Return strict JSON."
    )


def _claim_extraction_user_prompt(markdown_text: str) -> str:
    return f"""
Extract the checkable claims from this markdown analysis.

Rules:
- Keep only claims that could be checked against package files.
- Focus on:
  - bundle claims
  - brand share / over-index claims
  - product rank / Pareto bucket claims
- Mark review interpretation or broader narrative claims as non_deterministic.
- Preserve the original wording of the claim as much as possible.
- For bundle claims, normalize entity_text to package style by keeping only the value
  tokens joined by ` + `.
  Example: `product benefit=shine + product form=cream` -> `shine + cream`.
- Use `brand` only for claims that explicitly make a deterministic brand-share,
  catalog-share, or over-index statement.
- For brand claims, entity_text must be an actual brand name only.
  Do not label bundles, propositions, or generic clusters as brands.
- Plain brand mentions, review examples, or verbal brand comparisons are
  non_deterministic even when a brand name appears.
- Only use `product_rank` when the claim explicitly includes a rank and Pareto bucket.
- Output JSON with this shape:
{{
  "claims": [
    {{
      "claim_text": "...",
      "claim_type": "bundle|brand|product_rank|non_deterministic",
      "entity_text": "..."
    }}
  ]
}}

Markdown:
{markdown_text}
""".strip()


def extract_claims_for_validation(
    *,
    markdown_text: str,
    use_llm: bool = True,
) -> dict[str, Any]:
    if not use_llm:
        segments = _split_segments(markdown_text)
        return {
            "mode": "heuristic",
            "claims": [
                {
                    "claim_text": segment,
                    "claim_type": "unknown",
                    "entity_text": None,
                }
                for segment in segments
            ],
        }

    session = SessionContext.from_state({})
    init_llm_wrapper("", session=session)
    llm_wrapper = session.state["llm_wrapper"]
    try:
        response = query_llm_return_json(
            llm_wrapper,
            "reasonedJudgementQuery",
            _claim_extraction_system_prompt(),
            _claim_extraction_user_prompt(markdown_text),
        )
    except Exception:
        segments = _split_segments(markdown_text)
        return {
            "mode": "heuristic_fallback",
            "claims": [
                {
                    "claim_text": segment,
                    "claim_type": "unknown",
                    "entity_text": None,
                }
                for segment in segments
            ],
        }

    claims = (
        response["claims"]
        if isinstance(response, dict) and isinstance(response.get("claims"), list)
        else []
    )
    normalized_claims: list[dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_text = _normalize_text(claim.get("claim_text"))
        if not claim_text:
            continue
        normalized_claims.append(
            {
                "claim_text": claim_text,
                "claim_type": _normalize_text(claim.get("claim_type")) or "unknown",
                "entity_text": _normalize_text(claim.get("entity_text")) or None,
            }
        )
    if not normalized_claims:
        segments = _split_segments(markdown_text)
        return {
            "mode": "heuristic_fallback",
            "claims": [
                {
                    "claim_text": segment,
                    "claim_type": "unknown",
                    "entity_text": None,
                }
                for segment in segments
            ],
        }
    return {"mode": "llm", "claims": normalized_claims}


def _truncate_text(value: Any, *, limit: int = 220) -> str:
    text = _normalize_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _narrative_review_system_prompt() -> str:
    return (
        "You are reviewing one narrative claim against evidence snippets from a package. "
        "Use only the provided evidence. "
        "Do not use outside knowledge. "
        "Return strict JSON."
    )


def _narrative_review_user_prompt(
    claim: dict[str, Any], evidence_snippets: list[dict[str, str]]
) -> str:
    evidence_block = "\n".join(
        f"{item['id']}: {item['snippet']}" for item in evidence_snippets
    )
    return f"""
Review this claim using only the evidence snippets.

Claim: {claim["claim_text"]}
Entity: {_normalize_text(claim.get("entity_text")) or "N/A"}

Rules:
- `supported`: the evidence directly supports the claim.
- `partly_supported`: the evidence supports part of the claim, but not all of it.
- `unsupported`: the evidence points against the claim.
- `overstated`: the claim is directionally plausible but stronger than the evidence.
- `unclear`: the evidence is too weak, too indirect, or too incomplete.
- Keep the reason short and factual.
- Reference only snippet ids that materially support your judgment.

Evidence:
{evidence_block}

Return JSON:
{{
  "verdict": "supported|partly_supported|unsupported|overstated|unclear",
  "reason": "...",
  "evidence_ids": ["E1", "E2"]
}}
""".strip()


def _load_narrative_review_sources(
    package_dir: Path,
    frames: dict[str, pl.DataFrame],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    sources = {
        file_name: df.to_dicts()
        for file_name, df in frames.items()
        if not df.is_empty()
    }
    for file_name in (
        "top_seller_review_validation.csv",
        "bundle_review_validation.csv",
        "recent_product_pdp_extracts.csv",
    ):
        df = _read_optional_csv(package_dir / file_name)
        if not df.is_empty():
            sources[file_name] = df.to_dicts()
    return sources, _read_optional_json(package_dir / "summary.json")


def _narrative_query_tokens(claim: dict[str, Any]) -> set[str]:
    text = " ".join(
        part
        for part in (
            _normalize_text(claim.get("entity_text")),
            _normalize_text(claim.get("claim_text")),
        )
        if part
    )
    return {
        token
        for token in _canonical_tokens(text)
        if token not in NARRATIVE_QUERY_STOPWORDS and len(token) > 2
    }


def _narrative_search_text(file_name: str, row: dict[str, Any]) -> str:
    fields_by_source = {
        "top_seller_brand_comparison.csv": ["brand"],
        "recent_products.csv": [
            "product_name",
            "brand",
            "benefit",
            "ingredient_preference",
            "hair_condition",
            "product form",
        ],
        "top_seller_products.csv": [
            "product_name",
            "brand",
            "benefit",
            "ingredient_preference",
            "hair_condition",
            "product form",
        ],
        "top_seller_review_validation.csv": [
            "bundle_label",
            "product_name",
            "brand",
            "review_1_headline",
            "review_1_comment",
            "review_2_headline",
            "review_2_comment",
            "review_3_headline",
            "review_3_comment",
            "review_4_headline",
            "review_4_comment",
            "review_5_headline",
            "review_5_comment",
        ],
        "bundle_review_validation.csv": [
            "bundle_label",
            "product_name",
            "brand",
            "review_1_headline",
            "review_1_comment",
            "review_2_headline",
            "review_2_comment",
            "review_3_headline",
            "review_3_comment",
            "review_4_headline",
            "review_4_comment",
            "review_5_headline",
            "review_5_comment",
        ],
        "recent_product_pdp_extracts.csv": [
            "product_name",
            "summary",
            "description_excerpt",
            "badges",
            "benefit",
            "ingredient_preference",
            "product form",
        ],
    }
    fields = fields_by_source.get(file_name)
    if fields is None:
        fields = [
            key
            for key in (
                "brand",
                "product_name",
                "bundle_label",
                "attribute_value",
                "filter_value",
            )
            if key in row
        ]
    return " ".join(
        _normalize_text(row.get(field)) for field in fields if row.get(field)
    )


def _narrative_snippet(file_name: str, row: dict[str, Any]) -> str:
    if file_name == "top_seller_brand_comparison.csv":
        top_share = _percent_from_fraction(row.get("top_seller_share_of_cohort"))
        catalog_share = _percent_from_fraction(row.get("catalog_share"))
        ratio = _float_or_none(row.get("over_index_vs_catalog_share"))
        top_share_text = f"{top_share:.1f}%" if top_share is not None else "N/A"
        catalog_share_text = (
            f"{catalog_share:.1f}%" if catalog_share is not None else "N/A"
        )
        ratio_text = f"{ratio:.2f}x" if ratio is not None else "N/A"
        return (
            f"[{file_name}] brand={_normalize_text(row.get('brand'))}; "
            f"top_seller_share={top_share_text}; catalog_share={catalog_share_text}; "
            f"over_index={ratio_text}"
        )

    if file_name in {
        "top_seller_review_validation.csv",
        "bundle_review_validation.csv",
    }:
        review_bits = [
            _truncate_text(row.get(field), limit=140)
            for field in (
                "review_1_comment",
                "review_2_comment",
                "review_3_comment",
                "review_4_comment",
                "review_5_comment",
            )
            if _normalize_text(row.get(field))
        ]
        return (
            f"[{file_name}] bundle={_normalize_text(row.get('bundle_label'))}; "
            f"product={_normalize_text(row.get('product_name'))}; "
            f"brand={_normalize_text(row.get('brand'))}; "
            f"reviews={' | '.join(review_bits[:2])}"
        )

    if file_name == "recent_product_pdp_extracts.csv":
        return (
            f"[{file_name}] product={_normalize_text(row.get('product_name'))}; "
            f"summary={_truncate_text(row.get('summary'), limit=150)}; "
            f"description={_truncate_text(row.get('description_excerpt'), limit=150)}"
        )

    return (
        f"[{file_name}] "
        f"product={_normalize_text(row.get('product_name'))}; "
        f"brand={_normalize_text(row.get('brand'))}; "
        f"bundle={_normalize_text(row.get('bundle_label') or row.get('attribute_value') or row.get('filter_value'))}"
    )


def _narrative_candidate_score(
    *,
    file_name: str,
    row: dict[str, Any],
    claim: dict[str, Any],
    query_tokens: set[str],
) -> int:
    search_text = _narrative_search_text(file_name, row)
    if not search_text:
        return 0
    row_tokens = _canonical_tokens(search_text)
    overlap_count = len(query_tokens & row_tokens)
    if overlap_count == 0 and query_tokens:
        return 0

    score = overlap_count
    entity_text = _normalize_text(claim.get("entity_text"))
    entity_canonical = _canonical_text(entity_text)
    for field in (
        "brand",
        "product_name",
        "bundle_label",
        "attribute_value",
        "filter_value",
    ):
        candidate = _normalize_text(row.get(field))
        candidate_canonical = _canonical_text(candidate)
        if entity_canonical and candidate_canonical == entity_canonical:
            score += 6
        elif (
            entity_canonical
            and entity_canonical
            and entity_canonical in candidate_canonical
        ):
            score += 3

    lowered_claim = _normalize_text(claim.get("claim_text")).casefold()
    if "review" in lowered_claim and "review_validation" in file_name:
        score += 2
    if (
        any(token in lowered_claim for token in ("title", "pdp", "image"))
        and file_name == "recent_product_pdp_extracts.csv"
    ):
        score += 2
    if (
        any(
            token in lowered_claim
            for token in ("over-index", "catalog", "top-seller cohort")
        )
        and file_name == "top_seller_brand_comparison.csv"
    ):
        score += 2
    return score


def _narrative_evidence_snippets_for_claim(
    claim: dict[str, Any],
    sources: dict[str, list[dict[str, Any]]],
    summary_payload: dict[str, Any],
) -> list[dict[str, str]]:
    query_tokens = _narrative_query_tokens(claim)
    candidates: list[tuple[int, str]] = []
    seen_snippets: set[str] = set()
    for file_name, rows in sources.items():
        for row in rows:
            score = _narrative_candidate_score(
                file_name=file_name,
                row=row,
                claim=claim,
                query_tokens=query_tokens,
            )
            if score <= 0:
                continue
            snippet = _narrative_snippet(file_name, row)
            if snippet in seen_snippets:
                continue
            seen_snippets.add(snippet)
            candidates.append((score, snippet))

    candidates.sort(key=lambda item: item[0], reverse=True)
    snippets = [
        {"id": f"E{index}", "snippet": snippet}
        for index, (_score, snippet) in enumerate(candidates[:6], start=1)
    ]
    if summary_payload and not snippets:
        category_label = _normalize_text(summary_payload.get("category_label"))
        if category_label:
            snippets.append(
                {
                    "id": "E1",
                    "snippet": f"[summary.json] category={category_label}",
                }
            )
    return snippets


def _review_non_deterministic_claims_with_llm(
    *,
    package_dir: Path,
    frames: dict[str, pl.DataFrame],
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not claims:
        return []

    sources, summary_payload = _load_narrative_review_sources(package_dir, frames)
    session = SessionContext.from_state({})
    init_llm_wrapper("", session=session)
    llm_wrapper = session.state["llm_wrapper"]
    reviews: list[dict[str, Any]] = []

    for claim in claims:
        evidence_snippets = _narrative_evidence_snippets_for_claim(
            claim,
            sources,
            summary_payload,
        )
        if not evidence_snippets:
            reviews.append(
                {
                    "claim_text": claim["claim_text"],
                    "entity_text": claim.get("entity_text"),
                    "verdict": "unclear",
                    "reason": "No relevant package evidence snippets were retrieved.",
                    "evidence_ids": [],
                }
            )
            continue
        try:
            response = query_llm_return_json(
                llm_wrapper,
                "reasonedJudgementQuery",
                _narrative_review_system_prompt(),
                _narrative_review_user_prompt(claim, evidence_snippets),
            )
        except Exception:
            response = {}

        verdict = (
            _normalize_text(response.get("verdict"))
            if isinstance(response, dict)
            else ""
        )
        if verdict not in NARRATIVE_REVIEW_VERDICTS:
            verdict = "unclear"
        evidence_ids = (
            response.get("evidence_ids")
            if isinstance(response, dict)
            and isinstance(response.get("evidence_ids"), list)
            else []
        )
        reviews.append(
            {
                "claim_text": claim["claim_text"],
                "entity_text": claim.get("entity_text"),
                "verdict": verdict,
                "reason": (
                    _normalize_text(response.get("reason"))
                    if isinstance(response, dict)
                    else "" or "LLM review unavailable or inconclusive."
                ),
                "evidence_ids": [str(item) for item in evidence_ids[:3]],
                "evidence_snippets": evidence_snippets,
            }
        )
    return reviews


def _load_package_frames(package_dir: Path) -> dict[str, pl.DataFrame]:
    names = [
        "top_seller_pairs.csv",
        "top_seller_triples.csv",
        "innovation_pairs.csv",
        "innovation_triples.csv",
        "filter_comparison.csv",
        "mapped_attribute_comparison.csv",
        "resolved_core_comparison.csv",
        "top_seller_mapped_attribute_comparison.csv",
        "top_seller_brand_comparison.csv",
        "recent_products.csv",
        "top_seller_products.csv",
    ]
    return {name: _read_optional_csv(package_dir / name) for name in names}


def _bundle_candidates(
    label: str, frames: dict[str, pl.DataFrame]
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for file_name in (
        "top_seller_pairs.csv",
        "top_seller_triples.csv",
        "innovation_pairs.csv",
        "innovation_triples.csv",
    ):
        df = frames[file_name]
        if df.is_empty() or "bundle_label" not in df.columns:
            continue
        for row in df.to_dicts():
            if _bundle_label_matches(label, row.get("bundle_label")):
                candidates.append({"file": file_name, "row": row, "kind": "bundle"})

    df = frames["top_seller_mapped_attribute_comparison.csv"]
    if not df.is_empty() and "attribute_value" in df.columns:
        for row in df.to_dicts():
            if _bundle_label_matches(label, row.get("attribute_value")):
                candidates.append(
                    {
                        "file": "top_seller_mapped_attribute_comparison.csv",
                        "row": row,
                        "kind": "mapped",
                    }
                )

    for file_name, value_column in (
        ("mapped_attribute_comparison.csv", "attribute_value"),
        ("resolved_core_comparison.csv", "attribute_value"),
        ("filter_comparison.csv", "filter_value"),
    ):
        df = frames[file_name]
        if df.is_empty() or value_column not in df.columns:
            continue
        for row in df.to_dicts():
            if _bundle_label_matches(label, row.get(value_column)):
                candidates.append(
                    {
                        "file": file_name,
                        "row": row,
                        "kind": "single_attribute",
                    }
                )

    return candidates


def _context_priority(segment: str, file_name: str) -> int:
    lowered = segment.casefold()
    if "observation" in lowered and file_name == "filter_comparison.csv":
        return 4
    if "resolved" in lowered and file_name == "resolved_core_comparison.csv":
        return 4
    if "mapped" in lowered and file_name in {
        "mapped_attribute_comparison.csv",
        "top_seller_mapped_attribute_comparison.csv",
    }:
        return 4
    if "top seller" in lowered or "winning" in lowered or "winner" in lowered:
        if file_name.startswith("top_seller_"):
            return 3
    if "recent" in lowered or "emerging" in lowered or "innovation" in lowered:
        if file_name.startswith("innovation_"):
            return 3
        if file_name in {
            "filter_comparison.csv",
            "mapped_attribute_comparison.csv",
            "resolved_core_comparison.csv",
        }:
            return 3
    if file_name.startswith("top_seller_"):
        return 2
    if file_name.startswith("innovation_"):
        return 1
    if file_name in {
        "filter_comparison.csv",
        "mapped_attribute_comparison.csv",
        "resolved_core_comparison.csv",
    }:
        return 1
    return 0


def _score_bundle_candidate(
    segment: str,
    candidate: dict[str, Any],
    *,
    context_segment: str | None = None,
) -> tuple[bool, int, list[str]]:
    row = candidate["row"]
    file_name = candidate["file"]
    reasons: list[str] = []
    score = _context_priority(context_segment or segment, file_name)

    pcts = [float(match) for match in PERCENT_RE.findall(segment)]
    ratios = [float(match) for match in MULTIPLIER_RE.findall(segment)]
    count_pairs = [
        (int(left), int(right)) for left, right in COUNT_RATIO_RE.findall(segment)
    ]
    brand_match = BRAND_COUNT_RE.search(segment)

    if "pct_top_seller" in row or "pct_recent" in row:
        left_pct = _percent_from_fraction(
            row.get("pct_top_seller", row.get("pct_recent"))
        )
        right_pct = _percent_from_fraction(row.get("pct_other", row.get("pct_rest")))
        if len(pcts) >= 2:
            if not (
                _approx_equal(pcts[0], left_pct, PERCENT_TOLERANCE)
                and _approx_equal(pcts[1], right_pct, PERCENT_TOLERANCE)
            ):
                reasons.append(
                    f"percent mismatch: expected {left_pct:.1f}% vs {right_pct:.1f}%"
                )
                return False, score, reasons
            score += 2
        elif len(pcts) == 1:
            if not (
                _approx_equal(pcts[0], left_pct, PERCENT_TOLERANCE)
                or _approx_equal(pcts[0], right_pct, PERCENT_TOLERANCE)
            ):
                reasons.append(
                    f"single percent mismatch: expected one of {left_pct:.1f}% / {right_pct:.1f}%"
                )
                return False, score, reasons
            score += 1

    if count_pairs:
        left_count = _int_or_none(row.get("count_top_seller", row.get("count_recent")))
        left_base = _int_or_none(
            row.get(
                "top_seller_base",
                row.get("recent_base", row.get("recent_family_base")),
            )
        )
        if left_count is not None and left_base is not None:
            if (left_count, left_base) not in count_pairs:
                reasons.append(
                    f"count/base mismatch: expected {left_count}/{left_base}"
                )
                return False, score, reasons
            score += 1

    if brand_match:
        expected_brand_count = _int_or_none(
            row.get("top_seller_brand_count", row.get("recent_brand_count"))
        )
        if expected_brand_count != int(brand_match.group(1)):
            reasons.append(f"brand-count mismatch: expected {expected_brand_count}")
            return False, score, reasons
        score += 1

    if ratios:
        expected_ratio = _float_or_none(row.get("prevalence_ratio"))
        if expected_ratio is not None:
            if not any(
                _approx_equal(value, expected_ratio, MULTIPLIER_TOLERANCE)
                for value in ratios
            ):
                reasons.append(f"ratio mismatch: expected {expected_ratio:.2f}x")
                return False, score, reasons
            score += 1

    return True, score, reasons


def _best_bundle_candidate(
    segment: str,
    label: str,
    frames: dict[str, pl.DataFrame],
    *,
    context_segment: str | None = None,
) -> dict[str, Any] | None:
    candidates = _bundle_candidates(label, frames)
    if not candidates:
        return None

    valid: list[tuple[int, dict[str, Any]]] = []
    for candidate in candidates:
        ok, score, _reasons = _score_bundle_candidate(
            segment,
            candidate,
            context_segment=context_segment,
        )
        if ok:
            valid.append((score, candidate))

    if not valid:
        return {
            "status": "fail",
            "label": label,
            "segment": segment,
            "candidates": candidates,
        }

    valid.sort(key=lambda item: item[0], reverse=True)
    best_score, best_candidate = valid[0]
    equally_best = [candidate for score, candidate in valid if score == best_score]
    if len(equally_best) > 1:
        return {
            "status": "warning",
            "label": label,
            "segment": segment,
            "message": "multiple matching candidate rows",
            "candidates": equally_best,
        }
    return {
        "status": "pass",
        "label": label,
        "segment": segment,
        "candidate": best_candidate,
    }


def _brand_row_for_segment(
    segment: str, brand_df: pl.DataFrame
) -> dict[str, Any] | None:
    if brand_df.is_empty():
        return None
    segment_tokens = _canonical_tokens(segment, ignored_tokens=BRAND_NOISE_TOKENS)
    matches: list[tuple[int, dict[str, Any]]] = []
    for row in brand_df.to_dicts():
        brand = _normalize_text(row.get("brand"))
        if not brand:
            continue
        brand_tokens = _canonical_tokens(brand, ignored_tokens=BRAND_NOISE_TOKENS)
        if brand_tokens and brand_tokens.issubset(segment_tokens):
            score = len(brand_tokens)
            matches.append((score, row))
    if len(matches) == 1:
        return matches[0][1]
    if matches:
        matches.sort(key=lambda item: item[0], reverse=True)
        best_score, best_row = matches[0]
        if len(matches) == 1 or matches[1][0] < best_score:
            return best_row
    return None


def _brand_row_for_entity(
    brand_name: str | None, brand_df: pl.DataFrame
) -> dict[str, Any] | None:
    target = _canonical_text(brand_name)
    if brand_df.is_empty() or not target:
        return None
    target_tokens = _canonical_tokens(brand_name, ignored_tokens=BRAND_NOISE_TOKENS)
    matches: list[tuple[int, dict[str, Any]]] = []
    for row in brand_df.to_dicts():
        candidate_brand = _normalize_text(row.get("brand"))
        candidate = _canonical_text(candidate_brand)
        if not candidate:
            continue
        if candidate == target:
            return row
        candidate_tokens = _canonical_tokens(
            candidate_brand, ignored_tokens=BRAND_NOISE_TOKENS
        )
        if not target_tokens or not candidate_tokens:
            continue
        if target_tokens == candidate_tokens:
            matches.append((100, row))
            continue
        if target_tokens.issubset(candidate_tokens):
            score = (
                80 + len(target_tokens) - (len(candidate_tokens) - len(target_tokens))
            )
            matches.append((score, row))
            continue
        if candidate_tokens.issubset(target_tokens):
            score = (
                70
                + len(candidate_tokens)
                - (len(target_tokens) - len(candidate_tokens))
            )
            matches.append((score, row))
    if len(matches) == 1:
        return matches[0][1]
    if matches:
        matches.sort(key=lambda item: item[0], reverse=True)
        best_score, best_row = matches[0]
        if len(matches) == 1 or matches[1][0] < best_score:
            return best_row
    return None


def _looks_like_brand_share_claim(segment: str) -> bool:
    lowered = segment.casefold()
    markers = (
        "top-seller cohort",
        "top seller cohort",
        "catalog share",
        "over-index",
        "over index",
        "share of the top-seller cohort",
        "share of the top seller cohort",
        "share of catalog",
    )
    return any(marker in lowered for marker in markers)


def _validate_brand_segment(
    segment: str,
    brand_df: pl.DataFrame,
    *,
    brand_name: str | None = None,
    require_numeric_evidence: bool = False,
) -> dict[str, Any] | None:
    row = _brand_row_for_entity(brand_name, brand_df) or _brand_row_for_segment(
        segment, brand_df
    )
    if row is None:
        return None

    pcts = [float(match) for match in PERCENT_RE.findall(segment)]
    ratios = [float(match) for match in MULTIPLIER_RE.findall(segment)]
    expected_pcts = [
        _percent_from_fraction(row.get("top_seller_share_of_cohort")),
        _percent_from_fraction(row.get("catalog_share")),
    ]
    expected_ratio = _float_or_none(row.get("over_index_vs_catalog_share"))
    reasons: list[str] = []
    has_numeric_evidence = bool(pcts or ratios)

    if len(pcts) == 1:
        if not any(
            _approx_equal(pcts[0], expected_pct, PERCENT_TOLERANCE)
            for expected_pct in expected_pcts
            if expected_pct is not None
        ):
            reasons.append(
                f"brand single percent mismatch: expected one of {expected_pcts[0]:.1f}% or {expected_pcts[1]:.1f}%"
            )

    if len(pcts) >= 2:
        if not (
            _approx_equal(pcts[0], expected_pcts[0], PERCENT_TOLERANCE)
            and _approx_equal(pcts[1], expected_pcts[1], PERCENT_TOLERANCE)
        ):
            reasons.append(
                f"brand percent mismatch: expected {expected_pcts[0]:.1f}% and {expected_pcts[1]:.1f}%"
            )
    if ratios and expected_ratio is not None:
        if not any(
            _approx_equal(value, expected_ratio, MULTIPLIER_TOLERANCE)
            for value in ratios
        ):
            reasons.append(f"brand ratio mismatch: expected {expected_ratio:.2f}x")

    if require_numeric_evidence and not has_numeric_evidence:
        return {
            "status": "warning",
            "segment": segment,
            "brand": row["brand"],
            "file": "top_seller_brand_comparison.csv",
            "message": "brand claim missing numeric evidence to validate",
        }

    return {
        "status": "fail" if reasons else "pass",
        "segment": segment,
        "brand": row["brand"],
        "file": "top_seller_brand_comparison.csv",
        "expected": {
            "top_seller_share_of_cohort_pct": expected_pcts[0],
            "catalog_share_pct": expected_pcts[1],
            "over_index_vs_catalog_share": expected_ratio,
        },
        "reasons": reasons,
    }


def _find_product_row(
    product_name: str, frames: dict[str, pl.DataFrame]
) -> dict[str, Any] | None:
    target = _canonical_text(product_name)
    target_tokens = _canonical_tokens(product_name, ignored_tokens=PRODUCT_NOISE_TOKENS)
    best_row: dict[str, Any] | None = None
    best_candidate_canonical = ""
    best_score = -1
    tied = False
    for file_name in ("recent_products.csv", "top_seller_products.csv"):
        df = frames[file_name]
        if df.is_empty() or "product_name" not in df.columns:
            continue
        for row in df.to_dicts():
            candidate_name = _normalize_text(row.get("product_name"))
            candidate_canonical = _canonical_text(candidate_name)
            if not candidate_canonical:
                continue
            if target == candidate_canonical:
                return {"file": file_name, "row": row}
            if target in candidate_canonical or candidate_canonical in target:
                score = min(len(target), len(candidate_canonical))
                if score > best_score:
                    best_score = score
                    best_row = {"file": file_name, "row": row}
                    best_candidate_canonical = candidate_canonical
                    tied = False
                elif (
                    score == best_score
                    and best_row is not None
                    and candidate_canonical != best_candidate_canonical
                ):
                    tied = True
                continue
            candidate_tokens = _canonical_tokens(
                candidate_name,
                ignored_tokens=PRODUCT_NOISE_TOKENS,
            )
            if not target_tokens or not candidate_tokens:
                continue
            if target_tokens.issubset(candidate_tokens):
                score = (
                    50
                    + len(target_tokens)
                    - (len(candidate_tokens) - len(target_tokens))
                )
            else:
                shared_tokens = target_tokens & candidate_tokens
                if len(shared_tokens) < 2:
                    continue
                coverage = len(shared_tokens) / len(target_tokens)
                if coverage < 0.75:
                    continue
                score = 30 + len(shared_tokens)
            if score > best_score:
                best_score = score
                best_row = {"file": file_name, "row": row}
                best_candidate_canonical = candidate_canonical
                tied = False
            elif (
                score == best_score
                and best_row is not None
                and candidate_canonical != best_candidate_canonical
            ):
                tied = True
    if tied:
        return None
    return best_row


def _extract_product_rank_expectations(segment: str) -> tuple[int | None, str | None]:
    exact_match = PRODUCT_RANK_RE.search(segment)
    if exact_match is not None:
        return int(exact_match.group("rank")), exact_match.group("bucket").upper()
    rank_match = PRODUCT_RANK_NUMBER_RE.search(segment)
    bucket_match = PRODUCT_BUCKET_RE.search(segment)
    expected_rank = int(rank_match.group(1)) if rank_match is not None else None
    expected_bucket = (
        bucket_match.group(1).upper() if bucket_match is not None else None
    )
    return expected_rank, expected_bucket


def _normalize_product_name_for_matching(product_name: str) -> str:
    normalized = _normalize_text(product_name)
    normalized = _normalize_text(
        TRAILING_PRODUCT_RANK_ANNOTATION_RE.sub("", normalized)
    )
    return _normalize_text(
        re.sub(r"^(?:and|or)\s+", "", normalized, flags=re.IGNORECASE)
    )


def _extract_product_rank_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for match in PRODUCT_RANK_ITEM_RE.finditer(text):
        product_name = _normalize_product_name_for_matching(match.group("name"))
        if not product_name:
            continue
        entries.append(
            {
                "segment": _normalize_text(match.group(0)),
                "product_name": product_name,
                "expected_rank": int(match.group("rank")),
                "expected_bucket": match.group("bucket").upper(),
            }
        )
    return entries


def _validate_product_rank_entry(
    *,
    segment: str,
    product_name: str,
    expected_rank: int | None,
    expected_bucket: str | None,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any]:
    if expected_rank is None or expected_bucket is None:
        return {
            "status": "warning",
            "segment": segment,
            "product_name": product_name,
            "message": "product-rank claim missing rank or Pareto bucket",
        }
    hit = _find_product_row(product_name, frames)
    if hit is None:
        return {
            "status": "warning",
            "segment": segment,
            "product_name": product_name,
            "message": "product not matched in package",
        }
    row = hit["row"]
    actual_rank = _int_or_none(row.get("pareto_rank"))
    actual_bucket = _normalize_text(row.get("pareto_bucket")).upper()
    reasons: list[str] = []
    if actual_rank != expected_rank:
        reasons.append(f"rank mismatch: expected #{actual_rank}")
    if actual_bucket != expected_bucket:
        reasons.append(f"bucket mismatch: expected {actual_bucket}")
    return {
        "status": "fail" if reasons else "pass",
        "segment": segment,
        "product_name": row.get("product_name"),
        "file": hit["file"],
        "expected_rank": actual_rank,
        "expected_bucket": actual_bucket,
        "reasons": reasons,
    }


def _validate_product_rank_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
    *,
    product_name: str | None = None,
) -> list[dict[str, Any]]:
    if product_name:
        extracted_entries = _extract_product_rank_entries(product_name)
        if len(extracted_entries) >= 2:
            return [
                _validate_product_rank_entry(
                    segment=entry["segment"],
                    product_name=entry["product_name"],
                    expected_rank=entry["expected_rank"],
                    expected_bucket=entry["expected_bucket"],
                    frames=frames,
                )
                for entry in extracted_entries
            ]
        expected_rank, expected_bucket = _extract_product_rank_expectations(segment)
        return [
            _validate_product_rank_entry(
                segment=segment,
                product_name=_normalize_product_name_for_matching(product_name),
                expected_rank=expected_rank,
                expected_bucket=expected_bucket,
                frames=frames,
            )
        ]

    results: list[dict[str, Any]] = []
    for entry in _extract_product_rank_entries(segment):
        results.append(
            _validate_product_rank_entry(
                segment=entry["segment"],
                product_name=entry["product_name"],
                expected_rank=entry["expected_rank"],
                expected_bucket=entry["expected_bucket"],
                frames=frames,
            )
        )
    return results


def validate_analysis_markdown(
    *,
    package_dir: Path,
    analysis_markdown: Path,
    use_llm: bool = True,
    validate_output_contract: bool = True,
    review_non_deterministic: bool = False,
) -> dict[str, Any]:
    frames = _load_package_frames(package_dir)
    markdown_text = analysis_markdown.read_text(encoding="utf-8")
    contract_payload = (
        _validate_output_contract(markdown_text)
        if validate_output_contract
        else {"checked": [], "warnings": [], "failures": []}
    )
    extraction = extract_claims_for_validation(
        markdown_text=markdown_text,
        use_llm=use_llm,
    )
    claims = extraction["claims"]

    checked: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    non_deterministic_claims: list[dict[str, Any]] = []

    brand_df = frames["top_seller_brand_comparison.csv"]

    for claim in claims:
        segment = claim["claim_text"]
        claim_type = str(claim.get("claim_type") or "").strip().lower()
        entity_text = _normalize_text(claim.get("entity_text"))
        if claim_type == "non_deterministic":
            non_deterministic_claims.append(claim)
            continue

        labels = BACKTICK_RE.findall(segment)
        if claim_type == "bundle" and entity_text:
            labels.append(entity_text)
        labels = _unique_texts(labels)
        if claim_type == "bundle" and not labels:
            warnings.append(
                {
                    "status": "warning",
                    "segment": segment,
                    "entity_type": "bundle",
                    "entity": entity_text or "unknown",
                    "message": "bundle claim missing extractable entity label",
                }
            )
        for label in labels:
            label_resolution = _resolve_bundle_label_targets(segment, label, frames)
            if label_resolution["kind"] == "non_deterministic":
                non_deterministic_claims.append(
                    {
                        "claim_text": segment,
                        "claim_type": "non_deterministic",
                        "entity_text": label,
                        "reason": label_resolution["reason"],
                    }
                )
                continue
            for target_label in label_resolution["labels"]:
                localized_segment = _localize_bundle_segment(segment, target_label)
                result = _best_bundle_candidate(
                    localized_segment,
                    target_label,
                    frames,
                    context_segment=segment,
                )
                if result is None:
                    warnings.append(
                        {
                            "status": "warning",
                            "segment": localized_segment,
                            "label": target_label,
                            "message": "no matching package row found for label",
                        }
                    )
                    continue
                if result["status"] == "pass":
                    checked.append(
                        {
                            "status": "pass",
                            "segment": localized_segment,
                            "entity_type": "bundle",
                            "entity": target_label,
                            "file": result["candidate"]["file"],
                        }
                    )
                elif result["status"] == "warning":
                    warnings.append(
                        {
                            "status": "warning",
                            "segment": localized_segment,
                            "entity_type": "bundle",
                            "entity": target_label,
                            "file": result["candidates"][0]["file"],
                            "message": result["message"],
                        }
                    )
                else:
                    expected = []
                    for candidate in result["candidates"]:
                        row = candidate["row"]
                        expected.append(
                            {
                                "file": candidate["file"],
                                "bundle_label": row.get(
                                    "bundle_label", row.get("attribute_value")
                                ),
                            }
                        )
                    if _looks_like_multi_claim_bundle_sentence(segment):
                        warnings.append(
                            {
                                "status": "warning",
                                "segment": localized_segment,
                                "entity_type": "bundle",
                                "entity": target_label,
                                "message": "multi-claim bundle sentence could not be cleanly disambiguated",
                            }
                        )
                    else:
                        failures.append(
                            {
                                "status": "fail",
                                "segment": localized_segment,
                                "entity_type": "bundle",
                                "entity": target_label,
                                "expected_candidates": expected,
                            }
                        )

        if claim_type == "brand" and not _looks_like_brand_share_claim(segment):
            non_deterministic_claims.append(
                {
                    "claim_text": segment,
                    "claim_type": "non_deterministic",
                    "entity_text": entity_text or None,
                    "reason": "plain_brand_mention",
                }
            )
        elif claim_type == "brand":
            brand_result = _validate_brand_segment(
                segment,
                brand_df,
                brand_name=entity_text,
                require_numeric_evidence=True,
            )
            if brand_result is not None:
                if brand_result["status"] == "pass":
                    checked.append(
                        {
                            "status": "pass",
                            "segment": segment,
                            "entity_type": "brand",
                            "entity": brand_result["brand"],
                            "file": brand_result["file"],
                        }
                    )
                elif brand_result["status"] == "warning":
                    warnings.append(brand_result)
                else:
                    failures.append(brand_result)
            else:
                warnings.append(
                    {
                        "status": "warning",
                        "segment": segment,
                        "brand": entity_text or "unknown",
                        "message": "brand not matched in package",
                    }
                )

        product_results = _validate_product_rank_segment(
            segment,
            frames,
            product_name=entity_text if claim_type == "product_rank" else None,
        )
        for product_result in product_results:
            if product_result["status"] == "pass":
                checked.append(
                    {
                        "status": "pass",
                        "segment": segment,
                        "entity_type": "product",
                        "entity": product_result["product_name"],
                        "file": product_result["file"],
                    }
                )
            elif product_result["status"] == "warning":
                warnings.append(product_result)
            else:
                failures.append(product_result)

    overall_status = "pass"
    if failures or contract_payload["failures"]:
        overall_status = "fail"
    elif warnings or contract_payload["warnings"]:
        overall_status = "pass_with_warnings"

    narrative_claim_reviews: list[dict[str, Any]] = []
    if (
        review_non_deterministic
        and extraction.get("mode") == "llm"
        and non_deterministic_claims
    ):
        narrative_claim_reviews = _review_non_deterministic_claims_with_llm(
            package_dir=package_dir,
            frames=frames,
            claims=non_deterministic_claims,
        )

    narrative_verdict_counts = {
        verdict: sum(
            1 for item in narrative_claim_reviews if item.get("verdict") == verdict
        )
        for verdict in NARRATIVE_REVIEW_VERDICTS
    }

    return {
        "status": overall_status,
        "package_dir": str(package_dir.resolve()),
        "analysis_markdown": str(analysis_markdown.resolve()),
        "summary": {
            "checked_count": len(checked),
            "warning_count": len(warnings),
            "failure_count": len(failures),
            "non_deterministic_claim_count": len(non_deterministic_claims),
            "output_contract_checked_count": len(contract_payload["checked"]),
            "output_contract_warning_count": len(contract_payload["warnings"]),
            "output_contract_failure_count": len(contract_payload["failures"]),
            "narrative_review_count": len(narrative_claim_reviews),
            "narrative_verdict_counts": narrative_verdict_counts,
        },
        "checked": checked,
        "warnings": warnings,
        "failures": failures,
        "output_contract_checked": contract_payload["checked"],
        "output_contract_warnings": contract_payload["warnings"],
        "output_contract_failures": contract_payload["failures"],
        "non_deterministic_claims": non_deterministic_claims,
        "narrative_claim_reviews": narrative_claim_reviews,
        "unvalidated_note": (
            "This validator checks deterministic entity/metric fidelity for bundle, brand, "
            "and product-rank claims. Narrative claims may also receive a bounded LLM evidence "
            "review, but that review is advisory and does not change deterministic pass/fail."
        ),
    }


def _markdown_report(payload: dict[str, Any]) -> str:
    def _display_entity(item: dict[str, Any]) -> str:
        return (
            item.get("entity")
            or item.get("label")
            or item.get("brand")
            or item.get("product_name")
            or "unknown"
        )

    def _group_items(
        items: list[dict[str, Any]],
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in items:
            message = _normalize_text(item.get("message")) or _normalize_text(
                "; ".join(item.get("reasons", []))
            )
            key = (item.get("status", "unknown"), message or "unspecified")
            groups.setdefault(key, []).append(item)
        return groups

    lines = [
        f"# Validation Report: `{Path(payload['analysis_markdown']).name}`",
        "",
        f"Status: **{payload['status']}**",
        "",
        "## Summary",
        "",
        f"- Checked claims: `{payload['summary']['checked_count']}`",
        f"- Warnings: `{payload['summary']['warning_count']}`",
        f"- Failures: `{payload['summary']['failure_count']}`",
        f"- Output-contract checks: `{payload['summary'].get('output_contract_checked_count', 0)}`",
        f"- Output-contract warnings: `{payload['summary'].get('output_contract_warning_count', 0)}`",
        f"- Output-contract failures: `{payload['summary'].get('output_contract_failure_count', 0)}`",
        f"- Non-deterministic claims: `{payload['summary'].get('non_deterministic_claim_count', 0)}`",
        f"- Narrative LLM reviews: `{payload['summary'].get('narrative_review_count', 0)}`",
        "",
    ]

    blocking_issue_count = len(payload.get("output_contract_failures", [])) + len(
        payload.get("failures", [])
    )
    lines.extend(
        [
            "## What To Do",
            "",
            (
                f"- Fix `{blocking_issue_count}` blocking issue(s) first."
                if blocking_issue_count
                else "- No blocking issues found."
            ),
            (
                f"- Then review `{payload['summary']['warning_count']}` non-blocking warning(s)."
                if payload["summary"]["warning_count"]
                else "- No non-blocking warnings found."
            ),
        ]
    )
    if payload["summary"].get("narrative_review_count", 0):
        lines.append(
            f"- `{payload['summary'].get('narrative_review_count', 0)}` non-deterministic claim(s) received bounded LLM review."
        )
    elif payload["summary"].get("non_deterministic_claim_count", 0):
        lines.append(
            f"- `{payload['summary'].get('non_deterministic_claim_count', 0)}` claim(s) were left out of deterministic validation."
        )
    else:
        lines.append("- No claims were excluded as non-deterministic.")
    lines.append("")

    if payload.get("output_contract_failures"):
        lines.extend(["## Blocking: Output Contract", ""])
        for item in payload["output_contract_failures"]:
            lines.append(f"- `{item['entity']}`")
            if item.get("message"):
                lines.append(f"  Note: {item['message']}")
        lines.append("")

    if payload.get("output_contract_warnings"):
        lines.extend(["## Output Contract Warnings", ""])
        for item in payload["output_contract_warnings"]:
            lines.append(f"- `{item['entity']}`")
            if item.get("message"):
                lines.append(f"  Note: {item['message']}")
        lines.append("")

    if payload["failures"]:
        lines.extend(["## Blocking: Deterministic Claim Failures", ""])
        for item in payload["failures"]:
            entity = _display_entity(item)
            lines.append(f"- `{entity}`")
            lines.append(f"  Segment: {item['segment']}")
            if item.get("reasons"):
                lines.append(f"  Reasons: {'; '.join(item['reasons'])}")
        lines.append("")

    if payload["warnings"]:
        lines.extend(["## Review Needed", ""])
        for (_status, message), items in sorted(
            _group_items(payload["warnings"]).items(),
            key=lambda entry: len(entry[1]),
            reverse=True,
        ):
            examples = ", ".join(f"`{_display_entity(item)}`" for item in items[:4])
            lines.append(f"- `{len(items)}` item(s): {message}")
            if examples:
                lines.append(f"  Examples: {examples}")
        lines.append("")

    if payload["checked"]:
        checked_counts: dict[str, int] = {}
        for item in payload["checked"]:
            entity_type = _normalize_text(item.get("entity_type")) or "unknown"
            checked_counts[entity_type] = checked_counts.get(entity_type, 0) + 1
        lines.extend(["## Confirmed Checks", ""])
        for entity_type, count in sorted(checked_counts.items()):
            lines.append(f"- `{entity_type}`: `{count}`")
        lines.append("")

    if payload.get("narrative_claim_reviews"):
        lines.extend(["## Narrative LLM Review", ""])
        verdict_counts = payload["summary"].get("narrative_verdict_counts", {})
        for verdict in NARRATIVE_REVIEW_VERDICTS:
            count = verdict_counts.get(verdict, 0)
            if count:
                examples = [
                    item["claim_text"]
                    for item in payload["narrative_claim_reviews"]
                    if item.get("verdict") == verdict
                ][:2]
                lines.append(f"- `{verdict}`: `{count}`")
                for example in examples:
                    lines.append(f"  Example: {_truncate_text(example, limit=120)}")
        lines.append("")

    if payload.get("narrative_claim_reviews"):
        lines.extend(
            [
                "## Narrative Claim Outcomes",
                "",
                "These are claims from the Pro output that were reviewed by the advisory LLM pass.",
                "",
            ]
        )
        for item in payload["narrative_claim_reviews"][:8]:
            lines.append(
                f"- `{item.get('verdict', 'unclear')}`: {_truncate_text(item.get('claim_text'), limit=140)}"
            )
            reason = _normalize_text(item.get("reason"))
            if reason:
                lines.append(f"  Note: {reason}")
            evidence_ids = item.get("evidence_ids") or []
            if evidence_ids:
                lines.append(
                    f"  Evidence: {', '.join(str(evidence_id) for evidence_id in evidence_ids)}"
                )
        remaining = len(payload["narrative_claim_reviews"]) - 8
        if remaining > 0:
            lines.append(f"- ... and `{remaining}` more")
        lines.append("")
    elif payload.get("non_deterministic_claims"):
        lines.extend(
            [
                "## Narrative Claims",
                "",
                "These are claims from the Pro output that were left out of deterministic validation.",
                "",
            ]
        )
        for item in payload["non_deterministic_claims"][:8]:
            lines.append(f"- {item['claim_text']}")
        remaining = len(payload["non_deterministic_claims"]) - 8
        if remaining > 0:
            lines.append(f"- ... and `{remaining}` more")
        lines.append("")

    lines.extend(
        [
            "## Scope note",
            "",
            payload["unvalidated_note"],
            "",
        ]
    )
    return "\n".join(lines)


def write_validation_artifacts(
    *,
    payload: dict[str, Any],
    output_prefix: Path,
) -> tuple[Path, Path]:
    json_path = output_prefix.with_suffix(".validation.json")
    md_path = output_prefix.with_suffix(".validation.md")
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md_path.write_text(_markdown_report(payload), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    args = _parse_args()
    output_prefix = args.output_prefix or args.analysis_markdown.with_suffix("")
    payload = validate_analysis_markdown(
        package_dir=args.package_dir,
        analysis_markdown=args.analysis_markdown,
        use_llm=not args.no_llm,
        validate_output_contract=not args.skip_output_contract,
        review_non_deterministic=not args.no_llm and not args.skip_narrative_review,
    )
    json_path, md_path = write_validation_artifacts(
        payload=payload,
        output_prefix=output_prefix,
    )
    print(json_path)
    print(md_path)
    if args.strict and payload["status"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
