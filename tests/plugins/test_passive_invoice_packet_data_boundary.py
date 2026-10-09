"""Worker packet fields are selected structurally, without anonymizing prose."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


@pytest.fixture
def packet_core(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Load the requested real component for source or extracted-package checks."""
    root = Path(
        os.environ.get(
            "VERA_PACKET_TEST_COMPONENT_ROOT",
            Path(__file__).resolve().parents[2] / "plugins/passive-invoice-audit",
        )
    )
    scripts = root / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "passive_packet_boundary_core", scripts / "audit_core.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("prose_field", ["description", "causale", "related_document"])
def test_worker_prompt_omits_payment_fields_but_preserves_selected_prose(
    packet_core: ModuleType, prose_field: str
) -> None:
    # Arrange: all values are fictional; payment fields and allowed prose differ.
    prose_marker = "Fictional source prose: IBAN TEST-PROSE-ONLY"
    payment_marker = "TEST-DEDICATED-PAYMENT-ONLY"
    source_fields = {
        "description": {"lines": [{"description": prose_marker}]},
        "causale": {"causale": [prose_marker]},
        "related_document": {"related_documents": [{"document_id": prose_marker}]},
    }
    item = {
        "invoice": {
            "invoice_id": "fictional-invoice",
            "payments": [{"iban": payment_marker}],
            **source_fields[prose_field],
        },
        "match_state": "matched",
        "matched_movement": {"ledger_reference": "fictional-ledger", "lines": []},
    }

    # Act: produce the actual prompt that the worker transport receives.
    prompt = packet_core.build_luna_prompt([packet_core.build_packet(item)])

    # Assert: field omission does not promise anonymization of source text.
    assert payment_marker not in prompt
    assert prose_marker in prompt
