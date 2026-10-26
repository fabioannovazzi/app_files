"""Authenticated browser capabilities and synthetic technical reports for tests."""

from __future__ import annotations

from uuid import uuid4

from modules.operational_incidents.recovery import RecoverySessions
from modules.operational_incidents.store import IncidentStore
from modules.workflow_usage.products import Product

__all__ = ["browser_headers", "technical_report"]


def browser_headers(store: IncidentStore, product: Product = "vera") -> dict[str, str]:
    """Create a real browser capability for an independent anonymous owner."""
    token, _ = RecoverySessions(store).create(product)
    return {
        "Origin": "https://mparanza.com",
        "X-Mparanza-Recovery": "1",
        "Cookie": f"__Host-mpr_{product}_recovery={token}",
    }


def technical_report():
    return {
        "report_id": str(uuid4()),
        "product_version": "0.1.368",
        "host": "cowork",
        "platform": "linux",
        "workflow": "journal-sampling",
        "stage": "execution-startup",
        "diagnostics": [
            {
                "component": "host-exec",
                "error_type": "CreateProcessError",
                "stage": "execution-startup",
                "message": "synthetic startup failure",
                "evidence_source": "observed-tool-result",
            }
        ],
    }
