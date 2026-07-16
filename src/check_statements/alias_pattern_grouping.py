from __future__ import annotations

"""Utilities to cluster alias-learning seeds into LLM-ready pattern groups."""

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

from src.check_statements.alias_seed import SeedPair


@dataclass(frozen=True)
class PatternExample:
    date: date
    bank_value: str
    ledger_value: str
    bank_description: str
    ledger_description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "date": self.date.isoformat(),
            "bank_value": self.bank_value,
            "ledger_value": self.ledger_value,
            "bank_description": self.bank_description,
            "ledger_description": self.ledger_description,
        }


@dataclass(frozen=True)
class PatternGroup:
    field: str
    bank_token: str
    ledger_token: str
    support: int
    dates: tuple[str, ...]
    bank_raw_values: tuple[str, ...]
    ledger_raw_values: tuple[str, ...]
    examples: tuple[PatternExample, ...]

    def to_payload(self, *, max_examples: int = 3) -> dict[str, object]:
        examples = self.examples[: max_examples]
        return {
            "field": self.field,
            "bank_token": self.bank_token,
            "ledger_token": self.ledger_token,
            "support": self.support,
            "dates": list(self.dates),
            "bank_raw_values": list(self.bank_raw_values),
            "ledger_raw_values": list(self.ledger_raw_values),
            "examples": [ex.to_dict() for ex in examples],
        }


def _field_priority(field: str, prefer_fields: Sequence[str]) -> int:
    try:
        return prefer_fields.index(field)
    except ValueError:
        return len(prefer_fields)


def group_seed_patterns(
    seeds: Sequence[SeedPair],
    *,
    min_support: int = 2,
    max_groups: int = 20,
    prefer_fields: Sequence[str] = (
        "beneficiary",
        "references",
        "description_tokens",
        "description",
    ),
    max_examples_per_group: int = 5,
) -> list[PatternGroup]:
    """Group seeds by feature → (bank_token, ledger_token) pairs."""

    if not seeds:
        return []

    class _GroupBucket:
        __slots__ = (
            "field",
            "bank",
            "ledger",
            "dates",
            "bank_raw",
            "ledger_raw",
            "examples",
            "seed_indices",
        )

        def __init__(self, field: str, bank: str, ledger: str) -> None:
            self.field = field
            self.bank = bank
            self.ledger = ledger
            self.dates: set[str] = set()
            self.bank_raw: set[str] = set()
            self.ledger_raw: set[str] = set()
            self.examples: list[PatternExample] = []
            self.seed_indices: set[int] = set()

    buckets: dict[tuple[str, str, str], _GroupBucket] = {}

    for seed_idx, seed in enumerate(seeds):
        for feature in seed.features:
            bank_norm = feature.bank.normalized
            ledger_norm = feature.ledger.normalized
            if not bank_norm or not ledger_norm:
                continue
            bank_raw_values: tuple[str, ...] = (
                feature.bank.raw if feature.bank.raw else (seed.bank_description,)
            )
            ledger_raw_values: tuple[str, ...] = (
                feature.ledger.raw if feature.ledger.raw else (seed.ledger_description,)
            )
            for b_tok in bank_norm:
                for l_tok in ledger_norm:
                    key = (feature.field, b_tok, l_tok)
                    bucket = buckets.get(key)
                    if bucket is None:
                        bucket = _GroupBucket(*key)
                        buckets[key] = bucket
                    if seed_idx not in bucket.seed_indices:
                        bucket.seed_indices.add(seed_idx)
                        bucket.dates.add(seed.date.isoformat())
                    bucket.bank_raw.update(bank_raw_values)
                    bucket.ledger_raw.update(ledger_raw_values)
                    if len(bucket.examples) < max_examples_per_group:
                        bank_value = bank_raw_values[0]
                        ledger_value = ledger_raw_values[0]
                        bucket.examples.append(
                            PatternExample(
                                date=seed.date,
                                bank_value=bank_value,
                                ledger_value=ledger_value,
                                bank_description=seed.bank_description,
                                ledger_description=seed.ledger_description,
                            )
                        )

    groups: list[PatternGroup] = []
    for bucket in buckets.values():
        support = len(bucket.dates)
        if support < min_support:
            continue
        groups.append(
            PatternGroup(
                field=bucket.field,
                bank_token=bucket.bank,
                ledger_token=bucket.ledger,
                support=support,
                dates=tuple(sorted(bucket.dates)),
                bank_raw_values=tuple(sorted(bucket.bank_raw)),
                ledger_raw_values=tuple(sorted(bucket.ledger_raw)),
                examples=tuple(bucket.examples),
            )
        )

    if not groups:
        return []

    groups.sort(
        key=lambda grp: (
            -grp.support,
            _field_priority(grp.field, prefer_fields),
            -len(grp.bank_token),
            grp.bank_token,
            grp.ledger_token,
        )
    )

    return groups[: max_groups]


__all__ = (
    "PatternExample",
    "PatternGroup",
    "group_seed_patterns",
)
