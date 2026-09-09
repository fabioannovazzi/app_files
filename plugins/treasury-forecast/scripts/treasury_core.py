"""Treasury arithmetic and explicit update contracts; no inferred payment facts."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

__all__ = [
    "TreasuryError",
    "build_forecast",
    "build_scenario",
    "digest",
    "money",
    "validate_record",
]

SCHEMA = "vera.treasury_forecast.v1"
ZERO = Decimal("0.00")
TABLE_KEYS = {
    "accounts": "account_id",
    "bank_movements": "movement_id",
    "open_items": "item_id",
    "planned_flows": "flow_id",
    "allocations": "allocation_id",
    "adjustments": "adjustment_id",
}


class TreasuryError(ValueError):
    """A supplied fact or mechanical invariant prevents a treasury run."""


def digest(value: Any) -> str:
    """Bind exact serializable content, without claiming authenticated authorship."""
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def money(value: Any) -> Decimal:
    """Cent precision is directly verifiable; never round or infer separators."""
    if not isinstance(value, str) or not re.fullmatch(r"-?\d+(?:\.\d{1,2})?", value):
        raise TreasuryError(f"Expected decimal-text EUR amount, received {value!r}")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise TreasuryError("Invalid money") from exc
    if not result.is_finite() or abs(result) > Decimal("999999999999.99"):
        raise TreasuryError("Money outside supported range")
    return result.quantize(Decimal("0.01"))


def _date(value: Any) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise TreasuryError("Expected ISO date YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise TreasuryError(f"Invalid date: {value}") from exc


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise TreasuryError(f"Missing or invalid {label}")
    return value


def _index(rows: Any, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list) or len(rows) > 100000:
        raise TreasuryError(f"Expected bounded {key} table")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise TreasuryError(f"Invalid {key} row")
        identity = _text(row[key], key)
        if identity in result:
            raise TreasuryError(f"Duplicate {key}: {identity}")
        result[identity] = row
    return result


def _signed(row: dict[str, Any]) -> Decimal:
    if row["side"] not in {"receivable", "payable"}:
        raise TreasuryError("side must be receivable or payable")
    amount = money(row["amount"])
    if amount < ZERO:
        raise TreasuryError("Outstanding/planned amounts must be nonnegative")
    return amount if row["side"] == "receivable" else -amount


def _identity(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        _text(row[key], key)
        for key in (
            "party_id",
            "side",
            "document_type",
            "document_number",
            "document_date",
            "installment",
        )
    )


def validate_record(record: dict[str, Any], *, accepted: bool = False) -> None:
    """Verify a record's exact content and its recorded review state."""
    if record.get("schema_version") != SCHEMA:
        raise TreasuryError("Unsupported treasury record")
    unsigned = {k: v for k, v in record.items() if k != "record_sha256"}
    if record.get("record_sha256") != digest(unsigned):
        raise TreasuryError("Treasury record digest mismatch")
    if accepted and record["status"] != "accepted":
        raise TreasuryError("Previous forecast must be professionally accepted")


def _validate_dataset(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if data.get("schema_version") != "vera.treasury_inputs.v1":
        raise TreasuryError("Unsupported treasury inputs")
    for key in ("client_id", "engagement_id", "company_id", "company_name", "coverage"):
        _text(data[key], key)
    if data["currency"] != "EUR":
        raise TreasuryError("The first treasury version accepts EUR only")
    start, end = _date(data["as_of"]), _date(data["horizon_end"])
    if not 1 <= (end - start).days <= 366:
        raise TreasuryError("Forecast horizon must be between 1 and 366 days")
    tables = {name: _index(data[name], key) for name, key in TABLE_KEYS.items()}
    if not tables["accounts"]:
        raise TreasuryError("At least one bank account is required")
    for account in tables["accounts"].values():
        money(account["balance"])
    for row in tables["open_items"].values():
        _identity(row)
        _date(row["document_date"])
        if _date(row["document_date"]) > start:
            raise TreasuryError("Open-item document date exceeds cutoff")
        if row["due_date"]:
            _date(row["due_date"])
        _signed(row)
    document_keys = [_identity(row) for row in tables["open_items"].values()]
    if len(set(document_keys)) != len(document_keys):
        raise TreasuryError("Same document/installment appears under multiple item IDs")
    for row in tables["planned_flows"].values():
        _signed(row)
        _text(row["description"], "planned-flow description")
        _text(row["basis"], "planned-flow basis")
        if row["expected_date"]:
            _date(row["expected_date"])
    return tables


def _cash_evidence(
    data: dict[str, Any],
    tables: dict[str, dict[str, Any]],
    previous: dict[str, Any] | None,
) -> tuple[dict[str, Decimal], dict[str, Decimal], list[dict[str, str]]]:
    """Validate supplied allocations; a balance decrease alone is never cash."""
    paid: dict[str, Decimal] = defaultdict(lambda: ZERO)
    adjusted: dict[str, Decimal] = defaultdict(lambda: ZERO)
    allocated: dict[str, Decimal] = defaultdict(lambda: ZERO)
    prior = previous["inputs"] if previous else None
    old_items = _index(prior["open_items"], "item_id") if prior else {}
    old_plans = _index(prior["planned_flows"], "flow_id") if prior else {}
    start = _date(prior["as_of"]) if prior else _date(data["as_of"])
    end = _date(data["as_of"])
    account_movements: dict[str, Decimal] = defaultdict(lambda: ZERO)
    notes = []
    for movement in tables["bank_movements"].values():
        if movement["account_id"] not in tables["accounts"]:
            raise TreasuryError("Movement references an undeclared bank account")
        if not start < _date(movement["date"]) <= end:
            raise TreasuryError("Bank movement lies outside the update interval")
        account_movements[movement["account_id"]] += money(movement["amount"])
    if previous:
        old_accounts = _index(prior["accounts"], "account_id")
        if set(old_accounts) != set(tables["accounts"]):
            raise TreasuryError("The declared account population changed")
        for key, row in tables["accounts"].items():
            if money(old_accounts[key]["balance"]) + account_movements[key] != money(
                row["balance"]
            ):
                raise TreasuryError(f"Bank balance does not reconcile: {key}")
    elif any(tables[name] for name in ("bank_movements", "allocations", "adjustments")):
        raise TreasuryError(
            "First run starts at actual cash; update evidence needs a predecessor"
        )
    for row in tables["allocations"].values():
        movement = tables["bank_movements"].get(row["movement_id"])
        if movement is None:
            raise TreasuryError("Allocation references an unknown bank movement")
        target_type = row["target_type"]
        if target_type not in {"item", "plan"}:
            raise TreasuryError("Allocation target_type must be item or plan")
        population = (
            tables["open_items"] if target_type == "item" else tables["planned_flows"]
        )
        prior_population = old_items if target_type == "item" else old_plans
        target = population.get(
            row["target_id"], prior_population.get(row["target_id"])
        )
        if target is None:
            raise TreasuryError("Allocation references an unknown obligation")
        amount = money(row["amount"])
        if amount <= ZERO:
            raise TreasuryError("Allocation amount must be positive")
        signed = money(movement["amount"])
        if (signed > ZERO) != (target["side"] == "receivable") or signed == ZERO:
            raise TreasuryError("Allocation direction disagrees with cash movement")
        allocated[row["movement_id"]] += amount
        paid[f"{target_type}:{row['target_id']}"] += amount
    for key, total in allocated.items():
        if total > abs(money(tables["bank_movements"][key]["amount"])):
            raise TreasuryError(
                "Cash movement has been allocated more than once in value"
            )
    for key, row in tables["bank_movements"].items():
        residual = abs(money(row["amount"])) - allocated[key]
        if residual:
            notes.append(
                {
                    "kind": "unallocated_cash",
                    "id": key,
                    "amount": f"{residual:.2f}",
                    "detail": "Included in actual bank cash; no invoice settlement inferred.",
                }
            )
    for row in tables["adjustments"].values():
        if (
            row["item_id"] not in old_items
            and row["item_id"] not in tables["open_items"]
        ):
            raise TreasuryError("Adjustment references an unknown item")
        if not start < _date(row["date"]) <= end:
            raise TreasuryError("Adjustment lies outside the update interval")
        _text(row["kind"], "adjustment kind")
        _text(row["evidence_ref"], "adjustment evidence")
        adjusted[row["item_id"]] += money(row["amount"])
    if previous:
        old_identity_ids = {_identity(row): key for key, row in old_items.items()}
        for key, row in tables["open_items"].items():
            prior_key = old_identity_ids.get(_identity(row))
            if prior_key is not None and prior_key != key:
                raise TreasuryError(
                    "Document identity was assigned a different stable item ID"
                )
        for key, old in old_items.items():
            current = tables["open_items"].get(key)
            if current and _identity(old) != _identity(current):
                raise TreasuryError(f"Stable item identity changed: {key}")
            expected = money(old["amount"]) - paid[f"item:{key}"] + adjusted[key]
            observed = money(current["amount"]) if current else ZERO
            if expected != observed or observed < ZERO:
                raise TreasuryError(f"Outstanding amount has unexplained change: {key}")
        for key, old in old_plans.items():
            if paid[f"plan:{key}"] > money(old["amount"]):
                raise TreasuryError(f"Plan settlement exceeds the prior amount: {key}")
            current = tables["planned_flows"].get(key)
            if current and paid[f"plan:{key}"]:
                if (
                    money(current["amount"])
                    != money(old["amount"]) - paid[f"plan:{key}"]
                ):
                    raise TreasuryError(
                        f"Remaining planned amount does not reflect settlement: {key}"
                    )
    return (
        {key: value for key, value in paid.items() if value},
        {key: value for key, value in adjusted.items() if value},
        notes,
    )


def _events(
    data: dict[str, Any],
    tables: dict[str, dict[str, Any]],
    previous: dict[str, Any] | None,
    decisions: dict[str, Any],
    paid: dict[str, Decimal],
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, str]]:
    events, issues = [], []
    prior_events = (
        {row["event_id"]: row for row in previous["events"]} if previous else {}
    )
    prior_plans = (
        _index(previous["inputs"]["planned_flows"], "flow_id") if previous else {}
    )
    replacements = dict(previous["replacements"]) if previous else {}
    for item in tables["open_items"].values():
        replaced = item["replaces_flow_id"]
        if replaced:
            if replaced in replacements and replacements[replaced] != item["item_id"]:
                raise TreasuryError(
                    "First version requires a single invoice per replaced planned flow"
                )
            plan = tables["planned_flows"].get(replaced, prior_plans.get(replaced))
            if replaced not in replacements and (
                plan is None or plan["side"] != item["side"]
            ):
                raise TreasuryError(
                    "Replacement references an unknown or incompatible plan"
                )
            if paid.get(f"plan:{replaced}", ZERO):
                raise TreasuryError(
                    "Allocate cash to the replacement invoice, not also to its plan"
                )
            replacements[replaced] = item["item_id"]
    for plan_id, item_id in replacements.items():
        item = tables["open_items"].get(item_id)
        if item and item["replaces_flow_id"] != plan_id:
            raise TreasuryError("A retained replacement relationship was removed")
    for key, old in prior_plans.items():
        if key not in tables["planned_flows"] and key not in replacements:
            residual = money(old["amount"]) - paid.get(f"plan:{key}", ZERO)
            if residual:
                raise TreasuryError(
                    f"Planned flow disappeared without settlement or replacement: {key}"
                )
    for kind, table, identity_key, date_key in (
        ("item", "open_items", "item_id", "due_date"),
        ("plan", "planned_flows", "flow_id", "expected_date"),
    ):
        for row in tables[table].values():
            if kind == "plan" and row[identity_key] in replacements:
                continue
            event_id = f"{kind}:{row[identity_key]}"
            amount = _signed(row)
            if amount == ZERO:
                continue
            source_date = row[date_key]
            decision = decisions.get(event_id)
            origin, basis, expected_date = (
                "source",
                row.get("basis", "Supplied due date"),
                source_date,
            )
            old = prior_events.get(event_id)
            if old and old["decision_origin"] in {"reviewed", "retained"}:
                if (
                    old["source_date"] == source_date
                    and old["expected_date"] > data["as_of"]
                ):
                    expected_date, basis, origin = (
                        old["expected_date"],
                        old["basis"],
                        "retained",
                    )
                else:
                    expected_date = ""
            if decision is not None:
                if set(decision) != {"expected_date", "basis"}:
                    raise TreasuryError(
                        "Date decision requires expected_date and basis only"
                    )
                expected_date = decision["expected_date"]
                basis = _text(decision["basis"], "date decision basis")
                _date(expected_date)
                origin = "reviewed"
            if not expected_date or _date(expected_date) <= _date(data["as_of"]):
                issues.append(
                    {
                        "kind": "expected_date_required",
                        "event_id": event_id,
                        "detail": "Specify a supported future cash date; an elapsed due date is not a forecast.",
                    }
                )
                expected_date = None
            event = {
                "event_id": event_id,
                "side": row["side"],
                "amount": f"{abs(amount):.2f}",
                "cash_amount": f"{amount:.2f}",
                "source_date": source_date,
                "expected_date": expected_date,
                "decision_origin": origin,
                "basis": basis,
                "description": row.get(
                    "description",
                    f"{row.get('party_name', '')} — {row.get('document_number', '')}",
                ),
                "replaces_flow_id": row.get("replaces_flow_id", ""),
            }
            events.append(event)
    if set(decisions) - {row["event_id"] for row in events}:
        raise TreasuryError("Decision targets an unknown, replaced or settled event")
    return sorted(events, key=lambda row: row["event_id"]), issues, replacements


def _schedule(
    opening: Decimal,
    start: str,
    end: str,
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    cash: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for event in events:
        when = event["expected_date"]
        if when and start < when <= end:
            cash[when] += money(event["cash_amount"])
    balance = opening
    daily = [{"date": start, "net_cash": "0.00", "closing_cash": f"{balance:.2f}"}]
    cursor = _date(start) + timedelta(days=1)
    while cursor <= _date(end):
        stamp = cursor.isoformat()
        balance += cash[stamp]
        daily.append(
            {
                "date": stamp,
                "net_cash": f"{cash[stamp]:.2f}",
                "closing_cash": f"{balance:.2f}",
            }
        )
        cursor += timedelta(days=1)
    weeks: dict[str, dict[str, str]] = {}
    for day in daily:
        when = _date(day["date"])
        week = (when - timedelta(days=when.weekday())).isoformat()
        if week not in weeks:
            weeks[week] = {
                "week_start": week,
                "net_cash": "0.00",
                "closing_cash": day["closing_cash"],
                "minimum_daily_cash": day["closing_cash"],
            }
        current = weeks[week]
        current["net_cash"] = (
            f"{money(current['net_cash']) + money(day['net_cash']):.2f}"
        )
        current["closing_cash"] = day["closing_cash"]
        current["minimum_daily_cash"] = (
            f"{min(money(current['minimum_daily_cash']), money(day['closing_cash'])):.2f}"
        )
    return daily, list(weeks.values())


def _comparison(
    record: dict[str, Any], previous: dict[str, Any] | None
) -> dict[str, Any] | None:
    if previous is None or record["as_of"] > previous["horizon_end"]:
        return None
    common_end = min(record["horizon_end"], previous["horizon_end"])
    old_daily = {row["date"]: row for row in previous["daily"]}
    new_daily = {row["date"]: row for row in record["daily"]}
    opening_difference = money(record["opening_cash"]) - money(
        old_daily[record["as_of"]]["closing_cash"]
    )
    old_events = {row["event_id"]: row for row in previous["events"]}
    new_events = {row["event_id"]: row for row in record["events"]}
    changes = []
    for key in sorted(set(old_events) | set(new_events)):
        old, new = old_events.get(key), new_events.get(key)
        old_cash = (
            money(old["cash_amount"])
            if old and record["as_of"] < old["expected_date"] <= common_end
            else ZERO
        )
        new_cash = (
            money(new["cash_amount"])
            if new and record["as_of"] < new["expected_date"] <= common_end
            else ZERO
        )
        if old != new:
            changes.append(
                {
                    "event_id": key,
                    "previous": old,
                    "current": new,
                    "cash_change_in_common_period": f"{new_cash - old_cash:.2f}",
                }
            )
    delta = money(new_daily[common_end]["closing_cash"]) - money(
        old_daily[common_end]["closing_cash"]
    )
    bridge = opening_difference + sum(
        (money(row["cash_change_in_common_period"]) for row in changes), ZERO
    )
    if delta != bridge:
        raise TreasuryError("Comparable forecast change does not reconcile")
    return {
        "through": common_end,
        "opening_variance": f"{opening_difference:.2f}",
        "previous_closing_cash": old_daily[common_end]["closing_cash"],
        "current_closing_cash": new_daily[common_end]["closing_cash"],
        "closing_variance": f"{delta:.2f}",
        "changes": changes,
        "horizon_extended": record["horizon_end"] > previous["horizon_end"],
    }


def build_forecast(
    inputs: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
    decisions: dict[str, Any] | None = None,
    review: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a draft or bind professional acceptance to the exact draft digest."""
    data = copy.deepcopy(inputs)
    if decisions is not None and (
        not isinstance(decisions, dict)
        or any(not isinstance(value, dict) for value in decisions.values())
    ):
        raise TreasuryError("Date decisions must be objects keyed by event ID")
    if review is not None and not isinstance(review, dict):
        raise TreasuryError("Professional review must be an object")
    tables = _validate_dataset(data)
    evidence_ids = {}
    if previous:
        validate_record(previous, accepted=True)
        for key in ("client_id", "engagement_id", "company_id", "currency"):
            if previous[key] != data[key]:
                raise TreasuryError(f"Previous forecast belongs to another {key}")
        if data["as_of"] <= previous["as_of"]:
            raise TreasuryError("An update cutoff must follow its predecessor")
    for name in ("bank_movements", "allocations", "adjustments"):
        seen = set(previous["evidence_ids"][name]) if previous else set()
        if seen.intersection(tables[name]):
            raise TreasuryError(f"Previously consumed evidence ID reused: {name}")
        evidence_ids[name] = sorted(seen.union(tables[name]))
    paid, adjusted, evidence_notes = _cash_evidence(data, tables, previous)
    events, issues, replacements = _events(
        data, tables, previous, decisions or {}, paid
    )
    opening = sum((money(row["balance"]) for row in tables["accounts"].values()), ZERO)
    daily, weekly = _schedule(opening, data["as_of"], data["horizon_end"], events)
    record = {
        "schema_version": SCHEMA,
        "workflow_id": "treasury-forecast",
        **{
            key: data[key]
            for key in (
                "client_id",
                "engagement_id",
                "company_id",
                "company_name",
                "currency",
                "as_of",
                "horizon_end",
                "coverage",
            )
        },
        "status": "needs_review" if issues else "draft_for_review",
        "inputs": data,
        "inputs_sha256": digest(data),
        "previous_record_sha256": previous["record_sha256"] if previous else None,
        "decisions": copy.deepcopy(decisions or {}),
        "events": events,
        "issues": issues,
        "replacements": replacements,
        "evidence_ids": evidence_ids,
        "evidence_notes": evidence_notes,
        "cash_allocations": {key: f"{value:.2f}" for key, value in paid.items()},
        "non_cash_adjustments": {
            key: f"{value:.2f}" for key, value in adjusted.items()
        },
        "opening_cash": f"{opening:.2f}",
        "daily": daily,
        "weekly": weekly,
        "minimum_daily_cash": f"{min(money(row['closing_cash']) for row in daily):.2f}",
        "first_negative_day": next(
            (row["date"] for row in daily if money(row["closing_cash"]) < ZERO), None
        ),
        "calculation_complete": not issues,
        "assurance_limit": "Exact calculations and recorded decisions; no guarantee of collections, forecast completeness or authenticated reviewer identity. Daily closing balances do not establish intraday liquidity.",
    }
    record["comparison"] = _comparison(record, previous) if not issues else None
    proposal_sha256 = digest(record)
    record["proposal_sha256"] = proposal_sha256
    record["review"] = None
    if review is not None:
        if issues:
            raise TreasuryError("Unresolved dates prevent acceptance")
        if set(review) != {
            "proposal_sha256",
            "reviewer_ref",
            "reviewed_at",
            "conclusion",
        }:
            raise TreasuryError("Incomplete professional review")
        if review["proposal_sha256"] != proposal_sha256:
            raise TreasuryError("Stale review does not match the recomputed forecast")
        _date(review["reviewed_at"])
        _text(review["reviewer_ref"], "reviewer")
        _text(review["conclusion"], "review conclusion")
        record["review"] = copy.deepcopy(review)
        record["status"] = "accepted"
    record["record_sha256"] = digest(record)
    return record


def build_scenario(record: dict[str, Any], dates: dict[str, str]) -> dict[str, Any]:
    """Calculate an explicitly hypothetical alternative without changing a record."""
    validate_record(record)
    if not isinstance(dates, dict) or not dates:
        raise TreasuryError("An alternative requires at least one date override")
    if not record["calculation_complete"]:
        raise TreasuryError("Resolve baseline dates before calculating an alternative")
    events = copy.deepcopy(record["events"])
    if set(dates) - {row["event_id"] for row in events}:
        raise TreasuryError("Scenario references an unknown event")
    for event in events:
        if event["event_id"] in dates:
            when = _date(dates[event["event_id"]])
            if when <= _date(record["as_of"]):
                raise TreasuryError("Alternative cash date must follow the cutoff")
            event["expected_date"] = when.isoformat()
    daily, weekly = _schedule(
        money(record["opening_cash"]), record["as_of"], record["horizon_end"], events
    )
    return {
        "schema_version": "vera.treasury_scenario.v1",
        "status": "hypothetical",
        "baseline_record_sha256": record["record_sha256"],
        "date_overrides": dates,
        "daily": daily,
        "weekly": weekly,
        "minimum_daily_cash": f"{min(money(row['closing_cash']) for row in daily):.2f}",
    }
