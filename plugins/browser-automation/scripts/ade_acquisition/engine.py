"""Durable acquisition orchestration, independent of browser and model providers."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .artifacts import inspect_invoice
from .contracts import CATEGORIES, AcquisitionError, Client, Plan, quarters
from .storage import Store, atomic_json

__all__ = ["Acquisition", "timestamp", "load_events"]


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_events(run: Path, *, allow_pending: bool = False) -> list[dict[str, Any]]:
    """Read complete events; a partial last write is never success evidence."""
    path = run / "events.jsonl"
    if not path.exists():
        return []
    lines = path.read_bytes().splitlines(keepends=True)
    if lines and not lines[-1].endswith(b"\n"):
        if not allow_pending:
            raise AcquisitionError("run-event-log-incomplete")
        lines.pop()
    try:
        return [json.loads(line) for line in lines]
    except (ValueError, UnicodeError) as exc:
        raise AcquisitionError("run-event-log-incomplete") from exc


class Acquisition:
    """Download original files once, persist every result and account for every scope."""

    def __init__(self, store: Store, run: Path, plan: Plan, portal: Any) -> None:
        self.store, self.run, self.plan, self.portal = store, run, plan, portal
        self.state: dict[str, Any] = {
            "schema_version": "vera-agenzia-status/v1",
            "run_id": run.name,
            "state": "running",
            "reports_ready": False,
            "started_at": timestamp(),
            "pid": os.getpid(),
            "downloaded": 0,
            "verified_existing": 0,
            "failed_documents": 0,
            "scopes_complete": 0,
            "scopes_incomplete": 0,
            "scopes": [],
            "scopes_expected": len(plan.clients)
            * len(plan.operations)
            * len(quarters(plan.date_from, plan.date_to)),
        }
        self.documents = 0
        self.cancelled = False

    def save_status(self) -> None:
        self.state["updated_at"] = timestamp()
        atomic_json(self.run / "status.json", self.state)

    def event(self, value: dict[str, Any]) -> None:
        descriptor = os.open(
            self.run / "events.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600
        )
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            stream.write(
                json.dumps({"at": timestamp(), **value}, ensure_ascii=False) + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())

    def checkpoint(self) -> None:
        if (self.run / "cancel.json").exists():
            self.cancelled = True
            raise AcquisitionError("cancelled")

    def _invoices(
        self,
        client: Client,
        operation: str,
        year: int,
        quarter: int,
        start: date,
        end: date,
        seen: set[str],
    ) -> int:
        self.checkpoint()
        expected = self.portal.search_invoices(client, operation, start, end)
        if expected < 0 or expected > self.plan.max_documents - self.documents:
            raise AcquisitionError("document-limit-exceeded")
        if expected > 50 and start < end:
            middle = start + (end - start) // 2
            left = self._invoices(client, operation, year, quarter, start, middle, seen)
            right = self._invoices(
                client, operation, year, quarter, middle + timedelta(days=1), end, seen
            )
            if left + right != expected:
                raise AcquisitionError("portal-population-changed")
            return expected
        if expected == 0:
            return 0
        processed, number = 0, 1
        while processed < expected:
            self.checkpoint()
            rows = self.portal.invoice_rows()
            if not rows or processed + len(rows) > expected:
                raise AcquisitionError("portal-invoice-count-mismatch")
            keys = [r["key"] for r in rows]
            if len(set(keys)) != len(keys) or seen.intersection(keys):
                raise AcquisitionError("portal-invoice-rows-repeated")
            for row in rows:
                self.checkpoint()
                seen.add(row["key"])
                self.documents += 1
                if self.documents > self.plan.max_documents:
                    raise AcquisitionError("document-limit-exceeded")
                base = {
                    "kind": "invoice",
                    "client": client.vat_number,
                    "operation": operation,
                    "year": year,
                    "quarter": quarter,
                    "portal_key": row["key"],
                }
                record = self.store.lookup(client, operation, row["key"])
                if record is not None:
                    self.state["verified_existing"] += 1
                    self.event(
                        {**base, "status": "verified_existing", "record": record}
                    )
                else:
                    try:
                        filename, data = self.portal.download_invoice(row)
                        metadata, xml = inspect_invoice(
                            data, filename, client, operation
                        )
                        record = self.store.retain(
                            client,
                            operation,
                            row["key"],
                            year,
                            quarter,
                            filename,
                            data,
                            metadata,
                            xml,
                        )
                        self.state["downloaded"] += 1
                        self.event({**base, "status": "downloaded", "record": record})
                    except AcquisitionError as exc:
                        self.state["failed_documents"] += 1
                        self.event({**base, "status": "failed", "error": exc.code})
                        if exc.code == "authentication-required":
                            raise
                    # Return even after an unavailable original; never substitute metadata.
                    self.portal.restore_invoices(
                        client, operation, start, end, number, expected, keys
                    )
                processed += 1
                self.save_status()
            if processed < expected:
                number += 1
                self.portal.next_page(number, self.portal.page_fingerprint())
        return processed

    def _scope(
        self,
        client: Client,
        operation: str,
        year: int,
        quarter: int,
        start: date,
        end: date,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "client": client.vat_number,
            "operation": operation,
            "year": year,
            "quarter": quarter,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
        }
        previous_failures = self.state["failed_documents"]
        if operation in CATEGORIES:
            result["portal_count"] = self._invoices(
                client, operation, year, quarter, start, end, set()
            )
        elif operation == "corrispettivi":
            devices = self.portal.cash_devices(client, start, end)
            if (
                sum(d["count"] for d in devices)
                > self.plan.max_documents - self.documents
            ):
                raise AcquisitionError("document-limit-exceeded")
            result["devices"] = []
            for device in devices:
                self.checkpoint()
                rows = self.portal.cash_rows(client, start, end, device)
                if len(rows) != device["count"]:
                    raise AcquisitionError("portal-cash-count-mismatch")
                self.event(
                    {
                        "kind": "cash",
                        **result,
                        "device": device["name"],
                        "rows": rows,
                        "portal_count": device["count"],
                    }
                )
                result["devices"].append({"name": device["name"], "count": len(rows)})
                self.documents += len(rows)
            result["portal_count"] = sum(d["count"] for d in devices)
        else:
            result["evidence"] = self.portal.stamp_duty(client, year, quarter)
            self.event({"kind": "stamp", **result})
            # Bolli are quarterly even when the invoice interval covers only part of it.
            result["period_basis"] = "whole_quarter"
            if result["evidence"]["status"] != "acquired":
                result["status"] = "not_available"
                return result
        result["status"] = (
            "complete"
            if self.state["failed_documents"] == previous_failures
            else "incomplete"
        )
        return result

    def execute(self) -> dict[str, Any]:
        """Preserve completed work on client, scope, session or cancellation failures."""
        from playwright.sync_api import Error as PlaywrightError

        self.save_status()
        stop = False
        for client in self.plan.clients:
            if stop:
                break
            try:
                self.checkpoint()
                self.portal.select_client(self.plan, client)
            except (AcquisitionError, PlaywrightError) as exc:
                code = (
                    exc.code
                    if isinstance(exc, AcquisitionError)
                    else "portal-action-failed"
                )
                self.event(
                    {
                        "kind": "client_failure",
                        "client": client.vat_number,
                        "error": code,
                    }
                )
                self.state["scopes_incomplete"] += len(self.plan.operations) * len(
                    quarters(self.plan.date_from, self.plan.date_to)
                )
                self.save_status()
                if code in {"authentication-required", "cancelled"}:
                    self.state["stop_reason"] = code
                    break
                continue
            for year, quarter, start, end in quarters(
                self.plan.date_from, self.plan.date_to
            ):
                if stop:
                    break
                for operation in self.plan.operations:
                    self.state["current"] = {
                        "client": client.vat_number,
                        "operation": operation,
                        "year": year,
                        "quarter": quarter,
                    }
                    self.save_status()
                    try:
                        result = self._scope(
                            client, operation, year, quarter, start, end
                        )
                    except (AcquisitionError, PlaywrightError) as exc:
                        code = (
                            exc.code
                            if isinstance(exc, AcquisitionError)
                            else "portal-action-failed"
                        )
                        result = {
                            "client": client.vat_number,
                            "operation": operation,
                            "year": year,
                            "quarter": quarter,
                            "status": "incomplete",
                            "error": code,
                        }
                        if code in {
                            "authentication-required",
                            "cancelled",
                            "document-limit-exceeded",
                        }:
                            self.state["stop_reason"] = code
                            stop = True
                    self.state["scopes"].append(result)
                    self.state[
                        (
                            "scopes_complete"
                            if result["status"] == "complete"
                            else "scopes_incomplete"
                        )
                    ] += 1
                    self.event({"kind": "scope", **result})
                    self.save_status()
                    if stop:
                        break
        total = (
            len(self.plan.clients)
            * len(self.plan.operations)
            * len(quarters(self.plan.date_from, self.plan.date_to))
        )
        self.state["scopes_expected"] = total
        self.state["scopes_not_attempted"] = max(
            0, total - self.state["scopes_complete"] - self.state["scopes_incomplete"]
        )
        self.state["state"] = (
            "cancelled"
            if self.cancelled
            else "complete" if self.state["scopes_complete"] == total else "partial"
        )
        self.state.pop("current", None)
        self.state["finished_at"] = timestamp()
        self.save_status()
        return self.state
