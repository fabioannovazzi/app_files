"""Optional document verification uses trust sources without professional credentials."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from patent_box.contracts import ContractError
from patent_box.review_evidence import _configuration


def test_optional_document_tools_do_not_require_a_role_or_policy(tmp_path, monkeypatch):
    output = tmp_path / "case-output"
    output.mkdir()
    config = {
        name: str(tmp_path / name) for name in ("openssl", "trusted_roots", "crls")
    }
    path = tmp_path / "document-tools.json"
    path.write_text(json.dumps(config))
    original = path.read_bytes()
    monkeypatch.setenv("VERA_PATENT_BOX_AUTHORITY_CONFIG", str(path))
    assert _configuration(output) == {
        name: Path(value) for name, value in config.items()
    }
    assert path.read_bytes() == original


def test_case_outputs_cannot_supply_document_trust_sources(tmp_path, monkeypatch):
    output = tmp_path / "case-output"
    output.mkdir()
    path = tmp_path / "document-tools.json"
    path.write_text(
        json.dumps(
            {name: str(output / name) for name in ("openssl", "trusted_roots", "crls")}
        )
    )
    monkeypatch.setenv("VERA_PATENT_BOX_AUTHORITY_CONFIG", str(path))
    with pytest.raises(ContractError, match="outside case outputs"):
        _configuration(output)
