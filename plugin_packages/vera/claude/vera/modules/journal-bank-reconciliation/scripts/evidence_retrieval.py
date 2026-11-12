"""Run-scoped indexed evidence access; queries collect, never adjudicate, evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from decimal import Decimal
from typing import Any, Mapping, Sequence

__all__ = ["EvidenceIndex", "RetrievalLimit", "DEFAULT_BUDGET", "query_schema"]
DEFAULT_BUDGET = {"context_bytes": 98304, "page_rows": 16, "max_rounds": 16}
FIELDS = (
    "transaction_id",
    "reference",
    "document_no",
    "movement_number",
    "party_ref",
    "counterparty",
    "counterparty_name",
    "beneficiary",
    "party_id",
    "counterparty_id",
    "group_id",
    "settlement_id",
    "linked_id",
)


class RetrievalLimit(RuntimeError):
    """Technical deferral, never an accounting doubt or evidence of absence."""


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def _cents(value: Any) -> int:
    if isinstance(value, (float, bool)):
        raise ValueError("Use exact decimal amounts")
    d = Decimal(str(value)) * 100
    if not d.is_finite() or d != d.to_integral_value():
        raise ValueError("Invalid exact cents")
    return int(d)


def query_schema() -> dict[str, Any]:
    """A closed read-only vocabulary; no paths, SQL, shell or network operations."""
    nullable = lambda kind: {"type": [kind, "null"]}
    props = {
        "side": {"type": "string", "enum": ["bank", "journal"]},
        "text": nullable("string"),
        "field": {"type": ["string", "null"], "enum": [None, *FIELDS]},
        "value": nullable("string"),
        "amount_min": nullable("string"),
        "amount_max": nullable("string"),
        "date_min": nullable("string"),
        "date_max": nullable("string"),
        "cursor": nullable("string"),
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": list(props),
    }


class EvidenceIndex:
    """SQLite B-tree/FTS indexes over exactly one caller-qualified population.

    Fixed predicates and exact counts are mechanical. No date/amount predicate
    is imposed unless requested. Aliases require caller-supplied provenance.
    """

    def __init__(
        self,
        bank: Sequence[Mapping],
        journal: Sequence[Mapping],
        binding: Mapping,
        relationship: Mapping,
        page_rows: int = 16,
    ):
        self.page_rows = page_rows
        self.rows: dict[str, dict[str, dict[str, Any]]] = {"bank": {}, "journal": {}}
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(
            """
            CREATE TABLE records(n INTEGER PRIMARY KEY, side TEXT, id TEXT, amount INTEGER, day TEXT, payload TEXT,
                                 UNIQUE(side,id));
            CREATE INDEX amount_lookup ON records(side,amount,day,n);
            CREATE INDEX date_lookup ON records(side,day,n);
            CREATE TABLE terms(side TEXT, field TEXT, value TEXT, n INTEGER, reason TEXT);
            CREATE INDEX term_lookup ON terms(side,field,value,n);
            CREATE INDEX reason_lookup ON terms(n,field,value);
            CREATE VIRTUAL TABLE words USING fts5(body);
        """
        )
        aliases_by_name: dict[str, list[Mapping[str, Any]]] = {}
        for alias in relationship.get("documented_aliases", []):
            if not isinstance(alias, dict) or not all(
                alias.get(k) for k in ("canonical", "alias", "source_ref")
            ):
                raise ValueError(
                    "Alias requires canonical name and documentary provenance"
                )
            aliases_by_name.setdefault(str(alias["canonical"]).casefold(), []).append(
                alias
            )
        n = 0
        for side, rows in (("bank", bank), ("journal", journal)):
            for row in rows:
                n += 1
                record = json.loads(json.dumps(dict(row), default=str))
                identifier = record["transaction_id"]
                if (
                    not isinstance(identifier, str)
                    or not identifier
                    or identifier in self.rows[side]
                ):
                    raise ValueError("Duplicate or invalid scoped source ID")
                self.rows[side][identifier] = record
                self.db.execute(
                    "INSERT INTO records VALUES(?,?,?,?,?,?)",
                    (
                        n,
                        side,
                        identifier,
                        _cents(record["amount_signed"]),
                        str(record.get("transaction_date", "")),
                        json.dumps(record),
                    ),
                )
                self.db.execute(
                    "INSERT INTO words(rowid,body) VALUES(?,?)",
                    (n, " ".join(str(v) for v in record.values())),
                )
                for field in FIELDS:
                    if record.get(field):
                        self.db.execute(
                            "INSERT INTO terms VALUES(?,?,?,?,?)",
                            (
                                side,
                                field,
                                str(record[field]).casefold(),
                                n,
                                "source field " + field,
                            ),
                        )
                for field in (
                    "party_ref",
                    "counterparty",
                    "counterparty_name",
                    "beneficiary",
                ):
                    for alias in aliases_by_name.get(
                        str(record.get(field, "")).casefold(), []
                    ):
                        self.db.execute(
                            "INSERT INTO terms VALUES(?,?,?,?,?)",
                            (
                                side,
                                field,
                                str(alias["alias"]).casefold(),
                                n,
                                "documented alias: " + str(alias["source_ref"]),
                            ),
                        )
        self.db.commit()
        self.binding = _hash(
            {"source": binding, "relationship": relationship, "rows": self.rows}
        )
        self.counts = {s: len(r) for s, r in self.rows.items()}

    def close(self) -> None:
        self.db.close()

    def search(self, query: Mapping) -> dict[str, Any]:
        allowed = set(query_schema()["properties"])
        if set(query) - allowed or query.get("side") not in self.rows:
            raise ValueError("Unknown evidence query or side")
        if len(json.dumps(query)) > 8192:
            raise RetrievalLimit("Query exceeds technical size limit")
        if any(
            value is not None and not isinstance(value, str) for value in query.values()
        ):
            raise ValueError("Evidence query values must be strings or null")
        base = {k: query.get(k) for k in sorted(allowed - {"cursor"})}
        signature = _hash({"binding": self.binding, "query": base})
        after = 0
        if query.get("cursor"):
            try:
                sig, num = query["cursor"].split(":")
                after = int(num)
            except (ValueError, AttributeError) as error:
                raise ValueError("Invalid retrieval cursor") from error
            if sig != signature or after < 0:
                raise ValueError("Cursor belongs to another query/source")
        clauses, args = ["r.side=?"], [query["side"]]
        field, value = query.get("field"), query.get("value")
        if field is not None or value is not None:
            if field not in FIELDS or not isinstance(value, str) or not value:
                raise ValueError(
                    "Exact field search requires a supported field and value"
                )
            clauses.append(
                "r.n IN (SELECT n FROM terms WHERE side=? AND field=? AND value=?)"
            )
            args.extend((query["side"], field, value.casefold()))
        if query.get("text"):
            words = re.findall(r"\w+", query["text"], flags=re.UNICODE)
            if not words:
                raise ValueError("Text query needs searchable terms")
            clauses.append("r.n IN (SELECT rowid FROM words WHERE words MATCH ?)")
            args.append(" AND ".join('"' + w + '"' for w in words))
        for key, op, col in (
            ("amount_min", ">=", "amount"),
            ("amount_max", "<=", "amount"),
            ("date_min", ">=", "day"),
            ("date_max", "<=", "day"),
        ):
            if query.get(key) is not None:
                clauses.append(f"r.{col}{op}?")
                args.append(_cents(query[key]) if col == "amount" else query[key])
        where = " AND ".join(clauses)
        # Without this hint SQLite can scan every row of a side for each FTS/term
        # lookup. Integer primary-key lookup is the measured selective plan.
        table = "records r NOT INDEXED" if field or query.get("text") else "records r"
        total = self.db.execute(
            "SELECT count(*) FROM " + table + " WHERE " + where,  # nosec B608
            args,
        ).fetchone()[0]
        unseen = self.db.execute(
            "SELECT count(*) FROM "  # nosec B608
            + table
            + " WHERE "
            + where
            + " AND r.n>?",
            [*args, after],
        ).fetchone()[0]
        found = self.db.execute(
            "SELECT r.n,r.id FROM "  # nosec B608
            + table
            + " WHERE "
            + where
            + " AND r.n>? ORDER BY r.n LIMIT ?",
            [*args, after, self.page_rows],
        ).fetchall()
        refs = [
            {
                "side": query["side"],
                "transaction_id": identifier,
                "reason": "matches explicit query predicates",
                "source_id": identifier,
            }
            for _, identifier in found
        ]
        if field:
            for ref, (n, _) in zip(refs, found):
                ref["reason"] = "; ".join(
                    x[0]
                    for x in self.db.execute(
                        "SELECT reason FROM terms WHERE n=? AND field=? AND value=?",
                        (n, field, str(value).casefold()),
                    )
                )
        total_cents = self.db.execute(
            "SELECT coalesce(sum(amount),0) FROM "  # nosec B608
            + table
            + " WHERE "
            + where,
            args,
        ).fetchone()[0]
        remaining = unseen - len(found)
        return {
            "query": dict(query),
            "total_amount": format(Decimal(total_cents) / 100, ".2f"),
            "totals_are_not_identity_evidence": True,
            "query_sha256": signature,
            "total_candidates": total,
            "returned": len(found),
            "remaining_unread": remaining,
            "previous_pages_count": total - unseen,
            "records": refs,
            "next_cursor": (
                f"{signature}:{found[-1][0]}" if remaining and found else None
            ),
            "coverage": (
                "complete_for_predicates" if not remaining else "partial_for_predicates"
            ),
            "absence_is_global": False,
        }

    def get(self, side: str, ids: Sequence[str]) -> list[dict]:
        """Exact ID access; never silently omit an unknown or cross-client ID."""
        try:
            return [self.rows[side][i] for i in dict.fromkeys(ids)]
        except KeyError as error:
            raise ValueError("Evidence ID outside the qualified run") from error
