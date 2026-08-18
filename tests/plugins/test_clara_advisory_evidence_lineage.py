from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = ROOT / "plugins" / "clara" / "scripts"
LINEAGE_PATH = SCRIPTS_ROOT / "advisory_evidence_lineage.py"
CORE_PATH = SCRIPTS_ROOT / "advisor_case_core.py"
WEB_CAPTURE_PATH = SCRIPTS_ROOT / "capture_advisory_web_evidence.py"
RECORDED_AT = "2026-08-18T08:00:00+00:00"


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_ROOT))
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_ROOT))
    return module


def _lineage() -> Any:
    return _load(LINEAGE_PATH, "clara_advisory_evidence_lineage_test")


def _receipt(
    evidence_id: str,
    *,
    observation: str,
    evidence_type: str = "web_capture",
    capture_status: str = "captured",
    artifact_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "evidence_type": evidence_type,
        "recorded_at": RECORDED_AT,
        "recorded_by": "clara:clara",
        "capture_status": capture_status,
        "source": {
            "material_ids": [],
            "url": "https://example.test/inventory",
            "locator": "captured inventory page",
            "artifact_refs": artifact_refs or [],
        },
        "observation": observation,
        "scope": "The captured page at the recorded time.",
        "limitations": ["A listing count is not total company inventory."],
        "verification": {
            "status": "not_checked",
            "checked_at": "",
            "method": "",
            "notes": [],
        },
        "rechecks_evidence_id": "",
        "supersedes_evidence_id": "",
    }


def _claim(
    claim_id: str,
    statement: str,
    *,
    evidence_ids: list[str] | None = None,
    dependency_ids: list[str] | None = None,
    dependency_mode: str = "none",
    claim_type: str = "observation",
) -> dict[str, Any]:
    evidence_ids = evidence_ids or []
    dependency_ids = dependency_ids or []
    return {
        "id": claim_id,
        "statement": statement,
        "claim_type": claim_type,
        "recorded_at": RECORDED_AT,
        "recorded_by": "clara:clara",
        "provenance": {
            "workflow": "clara:clara",
            "step": "commercial evidence review",
            "artifact": "analysis.md",
            "locator": claim_id,
        },
        "evidence_links": [
            {
                "evidence_id": evidence_id,
                "relationship": "supports",
                "analysis": "The evidence directly records this observation.",
                "proves": statement,
                "does_not_prove": "Any broader population or conclusion.",
            }
            for evidence_id in evidence_ids
        ],
        "dependency": {
            "mode": dependency_mode,
            "claim_ids": dependency_ids,
            "derivation_type": "reasoning" if dependency_ids else "direct",
            "explanation": (
                "The conclusion requires every named premise."
                if dependency_ids
                else "Directly stated or observed."
            ),
            "calculation_evidence_id": "",
        },
        "decision_use": "supporting",
        "uncertainty": [],
        "professional_judgement_required": False,
        "appearances": [],
        "state": "active",
        "supersedes_claim_id": "",
    }


def test_initialize_lineage_creates_empty_structured_registers(tmp_path: Path) -> None:
    lineage = _lineage()

    paths = lineage.initialize_lineage(tmp_path)

    assert json.loads(paths["evidence_register"].read_text())["evidence"] == []
    assert json.loads(paths["claim_register"].read_text())["claims"] == []
    assert lineage.validate_lineage(tmp_path)["valid"] is True
    assert "does not prove that a claim is correct" in paths["evidence_map"].read_text()


def test_register_distinguishes_thirteen_listings_from_three_hundred_stock(
    tmp_path: Path,
) -> None:
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    listing_receipt = _receipt(
        "ev-web-13",
        observation="Thirteen vehicle listings were visible on the captured page.",
    )
    management_receipt = _receipt(
        "ev-management-300",
        observation="Management stated that the company had 300 vehicles in stock.",
        evidence_type="management_assertion",
        capture_status="assertion_only",
    )
    management_receipt["source"]["url"] = ""

    lineage.record_evidence(tmp_path, [listing_receipt, management_receipt])
    lineage.record_claims(
        tmp_path,
        [
            _claim(
                "cl-visible-13",
                "Thirteen vehicle listings were visible on the captured page.",
                evidence_ids=["ev-web-13"],
            ),
            _claim(
                "cl-management-300",
                "Management stated that the company had 300 vehicles in stock.",
                evidence_ids=["ev-management-300"],
                claim_type="assertion",
            ),
        ],
    )

    claims = json.loads((tmp_path / "advisory_claim_register.json").read_text())
    links = {
        item["id"]: item["evidence_links"][0]["evidence_id"]
        for item in claims["claims"]
    }
    assert links == {
        "cl-visible-13": "ev-web-13",
        "cl-management-300": "ev-management-300",
    }
    assert lineage.validate_lineage(tmp_path)["valid"] is True


def test_all_of_dependency_is_preserved_and_cycle_is_rejected(tmp_path: Path) -> None:
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    first = _claim("cl-a", "Premise A")
    second = _claim("cl-b", "Premise B")
    conclusion = _claim(
        "cl-x",
        "Conclusion X",
        dependency_ids=["cl-a", "cl-b"],
        dependency_mode="all_of",
        claim_type="conclusion",
    )
    lineage.record_claims(tmp_path, [first, second, conclusion])

    assert lineage.validate_lineage(tmp_path)["valid"] is True

    first["dependency"] = {
        "mode": "all_of",
        "claim_ids": ["cl-x"],
        "derivation_type": "reasoning",
        "explanation": "Invalid circular dependency.",
        "calculation_evidence_id": "",
    }
    payload = {"schema_version": "1.0", "claims": [first, second, conclusion]}
    (tmp_path / "advisory_claim_register.json").write_text(json.dumps(payload))

    audit = lineage.validate_lineage(tmp_path)
    assert audit["valid"] is False
    assert any("claim dependency cycle" in error for error in audit["errors"])


def test_artifact_identity_change_is_detected(tmp_path: Path) -> None:
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    snapshot = tmp_path / "source_materials" / "inventory.html"
    snapshot.parent.mkdir()
    snapshot.write_text("13 listings", encoding="utf-8")
    artifact = {
        "path": "source_materials/inventory.html",
        "path_reference": "case_relative",
        "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "byte_count": snapshot.stat().st_size,
        "media_type": "text/html",
    }
    lineage.record_evidence(
        tmp_path,
        [_receipt("ev-web-13", observation="13 listings", artifact_refs=[artifact])],
    )
    snapshot.write_text("12 listings", encoding="utf-8")

    audit = lineage.validate_lineage(tmp_path)
    assert audit["valid"] is False
    assert any("sha256 does not match" in error for error in audit["errors"])


def test_case_workspace_blocks_deleting_material_cited_by_evidence(
    tmp_path: Path,
) -> None:
    core = _load(CORE_PATH, "clara_advisor_case_core_lineage_test")
    case_dir = tmp_path / "case"
    core.initialize_case(
        case_dir,
        client="ClientCo",
        project="CDD",
        objective="Assess inventory",
        audience="Investment committee",
        now=__import__("datetime").datetime(
            2026, 8, 18, 8, tzinfo=__import__("datetime").timezone.utc
        ),
    )
    source = tmp_path / "management-note.txt"
    source.write_text("300 vehicles", encoding="utf-8")
    material = core.register_material(
        case_dir, source, summary="Management stock claim"
    )
    receipt = _receipt(
        "ev-management-300",
        observation="Management stated 300 vehicles.",
        evidence_type="management_assertion",
        capture_status="assertion_only",
    )
    receipt["source"]["url"] = ""
    receipt["source"]["material_ids"] = [material["id"]]
    lineage = _lineage()
    lineage.record_evidence(case_dir, [receipt])

    with pytest.raises(core.CaseWorkspaceError, match="cited by ev-management-300"):
        core.delete_materials(case_dir, [material["id"]])


class _Headers:
    def get_content_type(self) -> str:
        return "text/html"

    def get_content_charset(self) -> str:
        return "utf-8"


class _Response:
    status = 200
    headers = _Headers()

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return b"<html><body><p>13 vehicle listings</p><script>ignore</script></body></html>"

    def geturl(self) -> str:
        return "https://example.test/inventory"


class _Opener:
    def __init__(self) -> None:
        self.called = False

    def open(self, _request: Any, *, timeout: float) -> _Response:
        assert timeout == 3.0
        self.called = True
        return _Response()


def test_web_capture_preserves_response_and_explicit_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _load(WEB_CAPTURE_PATH, "clara_advisory_web_capture_test")
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    monkeypatch.setattr(
        capture.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    opener = _Opener()

    receipt = capture.capture_web_evidence(
        tmp_path,
        url="https://example.test/inventory",
        evidence_id="ev-web-13",
        observation="Thirteen vehicle listings were visible.",
        scope="The captured public page at the capture time.",
        limitations=["This does not establish total company stock."],
        recorded_at=__import__("datetime").datetime(
            2026, 8, 18, 8, tzinfo=__import__("datetime").timezone.utc
        ),
        timeout=3.0,
        opener=opener,
    )

    normalized = tmp_path / "source_materials/web/ev-web-13/normalized.txt"
    assert opener.called is True
    assert normalized.read_text().strip() == "13 vehicle listings"
    assert receipt["observation"] == "Thirteen vehicle listings were visible."
    assert receipt["limitations"] == ["This does not establish total company stock."]
    assert receipt["verification"]["status"] == "identity_verified"
    assert lineage.validate_lineage(tmp_path)["valid"] is True


def test_web_capture_rejects_loopback_before_opening(tmp_path: Path) -> None:
    capture = _load(WEB_CAPTURE_PATH, "clara_advisory_web_capture_unsafe_test")
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    opener = _Opener()

    with pytest.raises(capture.UnsafePublicUrlError, match="non-public"):
        capture.capture_web_evidence(
            tmp_path,
            url="http://127.0.0.1/private",
            evidence_id="ev-unsafe",
            observation="Private response.",
            scope="Attempted response.",
            opener=opener,
        )

    assert opener.called is False
