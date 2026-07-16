from __future__ import annotations

"""Seed extraction utilities for alias-learning enrichment.

The helpers in this module collect high-signal text snippets from
candidate transaction pairs so that later stages (LLM, rule synthesis)
have richer context than beneficiary names alone.
"""

from dataclasses import dataclass
from datetime import date, datetime
import re
import unicodedata
from collections import Counter
from typing import Callable, Iterable, Mapping, Sequence, TYPE_CHECKING

from parsers.extractors import extract_references, normalise_name

from src.check_statements.classify import classify_op

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from src.check_statements.models import Transaction


def _fold(text: str) -> str:
    """Return ``text`` stripped of accents (ASCII fold)."""

    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def _normalize_basic(text: str) -> str:
    """Generic normalisation: ASCII fold, lower-case, collapse punctuation."""

    text = _fold(text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def _normalize_reference(text: str) -> str:
    """Tight normalisation for reference-like tokens."""

    text = _fold(text)
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _normalize_beneficiary(text: str) -> str:
    try:
        return normalise_name(text)
    except Exception:
        return _normalize_basic(text)


def _normalize_description(text: str) -> str:
    text = _fold(text)
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


STOPWORDS = {
    "bonifico",
    "bonific",
    "pagamento",
    "pagamenti",
    "pag",
    "fattura",
    "fatture",
    "stipendio",
    "stipendi",
    "salary",
    "salaries",
    "wage",
    "wages",
    "payroll",
    "transfer",
    "sepa",
    "bank",
    "payment",
    "transaction",
    "bon",
    "accredito",
    "addebito",
    "commissione",
    "commissioni",
    "commission",
    "commissions",
    "fee",
    "fees",
    "versamento",
    "versamenti",
}


def _description_tokens(text: str) -> list[str]:
    if not text:
        return []
    folded = _fold(text)
    tokens = re.findall(r"[A-Za-z0-9]+", folded)
    seen: dict[str, None] = {}
    for token in tokens:
        token = token.lower()
        if token in STOPWORDS:
            continue
        if len(token) < 3 and not token.isdigit():
            continue
        seen.setdefault(token)
    return list(seen.keys())


def _trim(text: str, limit: int = 160) -> str:
    text = (text or "").strip()
    text = text.replace("\n", " ").replace("\r", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _collect_metadata_strings(metadata: Mapping[str, object] | None) -> Mapping[str, list[str]]:
    if not metadata:
        return {}

    def _iter_values(value: object) -> Iterable[str]:
        if value is None:
            return
        if isinstance(value, str):
            raw = value.strip()
            if raw:
                yield raw
            return
        if isinstance(value, (int, float)):
            yield str(value)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                yield from _iter_values(item)
            return
        if isinstance(value, Mapping):
            for item in value.values():
                yield from _iter_values(item)

    result: dict[str, list[str]] = {}
    for key, value in metadata.items():
        key_str = str(key).strip()
        if not key_str:
            continue
        collected = list(_iter_values(value))
        if collected:
            result[key_str] = collected
    return result


@dataclass(frozen=True)
class SeedValues:
    raw: tuple[str, ...]
    normalized: tuple[str, ...]


@dataclass(frozen=True)
class SeedFeature:
    field: str
    bank: SeedValues
    ledger: SeedValues

    def has_both(self) -> bool:
        return bool(self.bank.normalized and self.ledger.normalized)


@dataclass(frozen=True)
class SeedPair:
    bank_index: int
    ledger_index: int
    amount: float
    date: date
    features: tuple[SeedFeature, ...]
    bank_description: str
    ledger_description: str

    def feature_by_field(self, field: str) -> SeedFeature | None:
        for feature in self.features:
            if feature.field == field:
                return feature
        return None

    def to_summary(self, max_values: int = 3) -> dict[str, object]:
        return {
            "bank_index": self.bank_index,
            "ledger_index": self.ledger_index,
            "amount": self.amount,
            "date": self.date.isoformat(),
            "features": {
                feature.field: {
                    "bank": list(feature.bank.raw[:max_values]),
                    "ledger": list(feature.ledger.raw[:max_values]),
                }
                for feature in self.features
            },
            "bank_description": self.bank_description,
            "ledger_description": self.ledger_description,
        }


def _build_feature(
    field: str,
    bank_values: Iterable[str],
    ledger_values: Iterable[str],
    *,
    normalizer: Callable[[str], str] | None = None,
    value_limit: int | None = None,
) -> SeedFeature | None:
    normalizer = normalizer or _normalize_basic

    def _normalise_many(values: Iterable[str]) -> SeedValues:
        normalised: list[str] = []
        raw: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            norm = normalizer(text)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            raw.append(text)
            normalised.append(norm)
            if value_limit is not None and len(raw) >= value_limit:
                break
        return SeedValues(tuple(raw), tuple(normalised))

    bank_norm = _normalise_many(bank_values)
    ledger_norm = _normalise_many(ledger_values)
    if not bank_norm.normalized and not ledger_norm.normalized:
        return None
    return SeedFeature(field=field, bank=bank_norm, ledger=ledger_norm)


def extract_seed_features(bank_txn: Transaction, ledger_txn: Transaction) -> list[SeedFeature]:
    features: list[SeedFeature] = []

    beneficiary_feature = _build_feature(
        "beneficiary",
        [bank_txn.beneficiary] if bank_txn.beneficiary else [],
        [ledger_txn.beneficiary] if ledger_txn.beneficiary else [],
        normalizer=_normalize_beneficiary,
        value_limit=1,
    )
    if beneficiary_feature:
        features.append(beneficiary_feature)

    bank_desc = _trim(bank_txn.description or "")
    ledger_desc = _trim(ledger_txn.description or "")
    description_feature = _build_feature(
        "description",
        [bank_desc] if bank_desc else [],
        [ledger_desc] if ledger_desc else [],
        normalizer=_normalize_description,
        value_limit=1,
    )
    if description_feature:
        features.append(description_feature)

    token_feature = _build_feature(
        "description_tokens",
        _description_tokens(bank_txn.description or ""),
        _description_tokens(ledger_txn.description or ""),
        normalizer=lambda value: value,
    )
    if token_feature:
        features.append(token_feature)

    bank_refs = list(dict.fromkeys((bank_txn.reference_ids or []) + extract_references(bank_txn.description or "")))
    ledger_refs = list(dict.fromkeys((ledger_txn.reference_ids or []) + extract_references(ledger_txn.description or "")))
    reference_feature = _build_feature(
        "references",
        bank_refs,
        ledger_refs,
        normalizer=_normalize_reference,
    )
    if reference_feature:
        features.append(reference_feature)

    bank_meta = _collect_metadata_strings(bank_txn.metadata)
    ledger_meta = _collect_metadata_strings(ledger_txn.metadata)
    for key in sorted(set(bank_meta) | set(ledger_meta)):
        feature = _build_feature(
            f"metadata.{key}",
            bank_meta.get(key, []),
            ledger_meta.get(key, []),
        )
        if feature:
            features.append(feature)

    tokenisable_metadata = {"extra_desc", "details", "counter_account_desc", "account_desc"}
    for meta_key in tokenisable_metadata:
        bank_tokens: list[str] = []
        ledger_tokens: list[str] = []
        for value in bank_meta.get(meta_key, []):
            bank_tokens.extend(_description_tokens(value))
        for value in ledger_meta.get(meta_key, []):
            ledger_tokens.extend(_description_tokens(value))
        if not bank_tokens and not ledger_tokens:
            continue
        token_feature = _build_feature(
            f"metadata_tokens.{meta_key}",
            bank_tokens,
            ledger_tokens,
            normalizer=lambda value: value,
        )
        if token_feature:
            features.append(token_feature)

    return features


def _coerce_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def collect_matched_seed_pairs(
    bank: Sequence[Transaction],
    ledger: Sequence[Transaction],
    matched_pairs: Sequence[tuple[int, int | tuple[int, ...] | None, str]],
    bank_candidates: Sequence[Sequence[int]],
    *,
    exclude_types: set[str] | None = None,
    existing_alias_map: Mapping[str, str] | None = None,
    excluded_hows: set[str] | None = None,
) -> list[SeedPair]:
    """Return high-signal matched pairs suitable for alias learning."""

    exclude_types = exclude_types or {"FEE"}
    excluded_hows = excluded_hows or {"reference", "iban", "ref_substring", "beneficiary"}

    candidate_lists: list[list[int]] = [list(cands) for cands in bank_candidates]
    ledger_candidate_counts: Counter[int] = Counter()
    for cands in candidate_lists:
        for li in cands:
            ledger_candidate_counts[li] += 1

    seeds: list[SeedPair] = []

    for bi, li, how in matched_pairs:
        if how in excluded_hows:
            continue
        if not isinstance(li, int):
            continue
        if bi < 0 or bi >= len(candidate_lists) or li < 0 or li >= len(ledger):
            continue
        cands = candidate_lists[bi]
        if li not in cands:
            continue
        if len(cands) != 1:
            continue
        if ledger_candidate_counts.get(li, 0) != 1:
            continue

        b_txn = bank[bi]
        l_txn = ledger[li]

        try:
            b_type = (b_txn.metadata or {}).get("op_type") or classify_op(b_txn.description)
        except Exception:
            b_type = "OTHER"
        try:
            l_type = (l_txn.metadata or {}).get("op_type") or classify_op(l_txn.description)
        except Exception:
            l_type = "OTHER"

        if b_type in exclude_types or l_type in exclude_types:
            continue

        if set(b_txn.reference_ids or []) & set(l_txn.reference_ids or []):
            continue

        b_iban = (b_txn.metadata or {}).get("iban")
        l_iban = (l_txn.metadata or {}).get("iban")
        if b_iban and l_iban and b_iban == l_iban:
            continue

        features = extract_seed_features(b_txn, l_txn)
        if not any(feature.bank.normalized or feature.ledger.normalized for feature in features):
            continue

        if existing_alias_map:
            ben_feature = next((f for f in features if f.field == "beneficiary"), None)
            if ben_feature and ben_feature.has_both():
                bk = ben_feature.bank.normalized[0]
                lk = ben_feature.ledger.normalized[0]
                if existing_alias_map.get(bk) == lk:
                    continue

        seeds.append(
            SeedPair(
                bank_index=bi,
                ledger_index=li,
                amount=float(b_txn.amount),
                date=_coerce_date(b_txn.date),
                features=tuple(features),
                bank_description=_trim(b_txn.description or ""),
                ledger_description=_trim(l_txn.description or ""),
            )
        )

    return seeds


__all__ = (
    "SeedValues",
    "SeedFeature",
    "SeedPair",
    "extract_seed_features",
    "collect_matched_seed_pairs",
)
