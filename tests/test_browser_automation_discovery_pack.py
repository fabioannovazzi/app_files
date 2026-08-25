from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import stat
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "plugins" / "browser-automation"
SCRIPTS = COMPONENT / "scripts"
CAPABILITY_PATH = COMPONENT / "capabilities" / "gmail-search-export" / "capability.json"


def _load_module(path: Path, name: str) -> ModuleType:
    """Load one dependency-free browser automation module."""

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _modules() -> tuple[ModuleType, ModuleType]:
    pipeline = _load_module(SCRIPTS / "capability_pipeline.py", "capability_pipeline")
    sys.modules["capability_pipeline"] = pipeline
    pack = _load_module(SCRIPTS / "discovery_pack.py", "test_discovery_pack")
    return pipeline, pack


def _capability() -> dict[str, object]:
    return json.loads(CAPABILITY_PATH.read_text(encoding="utf-8"))


def _discovery(capability: dict[str, object]) -> dict[str, object]:
    observations = []
    for milestone in capability["milestones"]:
        observations.append(
            {
                "milestone_id": milestone["id"],
                "intent": milestone["intent"],
                "origin": capability["site"]["allowed_origins"][0],
                "path": "/mail/u/0/",
                "controls": [
                    {
                        "kind": "role",
                        "role": "main",
                        "value": None,
                        "exact": False,
                    }
                ],
                "action": f"Observe {milestone['id']} without retaining values.",
                "outcome": f"The {milestone['id']} state was distinguishable.",
                "uncertainties": [],
            }
        )
    return {
        "schema_version": "browser-discovery/v2",
        "record_id": "gmail-developer-discovery",
        "recorded_at": "2026-08-25T09:00:00+02:00",
        "site": copy.deepcopy(capability["site"]),
        "process": copy.deepcopy(capability["process"]),
        "runtime": copy.deepcopy(capability["runtime"]),
        "authority": copy.deepcopy(capability["authority"]),
        "privacy": copy.deepcopy(capability["privacy"]),
        "observations": observations,
        "branches": ["A visible-result path and an empty-result path were observed."],
        "downloads": [],
        "review": {
            "operator_reviewed": False,
            "approved_for_capability_authoring": False,
            "reviewed_at": None,
            "approval_id": None,
        },
    }


def _draft_and_discovery(
    pipeline: ModuleType,
) -> tuple[dict[str, object], dict[str, object]]:
    draft = _capability()
    discovery = _discovery(draft)
    draft["provenance"] = {
        "source": "live_discovery_unreviewed",
        "discovery_record_sha256": pipeline.sha256_payload(discovery),
        "discovery_approval_id": None,
        "discovery_approved_at": None,
        "portable_bundle_contains_private_evidence": False,
    }
    return draft, discovery


def _state(origin: str, path: str, fingerprint: str) -> dict[str, object]:
    return {
        "origin": origin,
        "path": path,
        "control_fingerprint": fingerprint,
    }


def _evidence(
    pipeline: ModuleType,
    draft: dict[str, object],
    discovery: dict[str, object],
    *,
    approved: bool,
    mode: str = "hybrid",
) -> dict[str, object]:
    origin = draft["site"]["allowed_origins"][0]
    timeline = []
    for index, milestone in enumerate(draft["milestones"]):
        actor = "operator" if index < 2 else "model"
        if mode == "guided":
            actor = "operator"
        elif mode == "autonomous":
            actor = "model"
        timeline.append(
            {
                "sequence": index + 1,
                "actor": actor,
                "observation_index": index,
                "milestone_id": milestone["id"],
                "action_ids": [action["id"] for action in milestone["actions"]],
                "intent": milestone["intent"],
                "before": _state(origin, "/mail/u/0/", f"{index + 1:x}" * 64),
                "after": _state(origin, "/mail/u/0/", f"{index + 5:x}" * 64),
                "state_change": f"Reached the {milestone['id']} control state.",
                "outcome": "The expected bounded state was distinguishable.",
                "postcondition": "The declared milestone condition was observable.",
                "uncertainties": [],
            }
        )
    evidence_privacy = {
        "model_data": [
            "Prompt objective, visible control labels, query-free paths, state changes, and model interpretations needed to discover the declared process."
        ],
        "portable_artifact_excludes": [
            "credentials",
            "cookies",
            "browser_storage",
            "session_urls",
            "page_html",
            "unreviewed_screenshots",
            "network_bodies",
            "downloaded_file_bytes",
            "observed_private_values",
            "raw_guided_capture",
        ],
        "private_evidence_retained": False,
    }
    return {
        "schema_version": "browser-discovery-evidence/v1",
        "session_id": "gmail-developer-session",
        "recorded_at": "2026-08-25T09:15:00+02:00",
        "mode": mode,
        "site": copy.deepcopy(draft["site"]),
        "process": copy.deepcopy(draft["process"]),
        "runtime": copy.deepcopy(draft["runtime"]),
        "authority": copy.deepcopy(draft["authority"]),
        "privacy": evidence_privacy,
        "prompt_summary": "Discover a reusable Gmail metadata-search capability.",
        "boundary": {
            "start_state": "Authenticated Gmail shell with search available.",
            "end_condition": "A bounded metadata artifact or empty result is produced.",
            "input_names": [item["name"] for item in draft["inputs"]],
            "output_names": [item["name"] for item in draft["outputs"]],
            "consequential_action_ids": [],
        },
        "timeline": timeline,
        "branches": ["Visible results and empty results are separate terminal paths."],
        "visual_evidence": [],
        "known_limits": ["The transfer pack is not runtime validation."],
        "discovery_record_sha256": pipeline.sha256_payload(discovery),
        "capability_draft_sha256": pipeline.sha256_payload(draft),
        "review": {
            "operator_reviewed": approved,
            "approved_for_developer_transfer": approved,
            "reviewed_at": "2026-08-25T09:30:00+02:00" if approved else None,
            "approval_id": "developer-transfer-one" if approved else None,
        },
    }


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _set_nested(
    payload: dict[str, object], path: tuple[object, ...], value: object
) -> None:
    """Set one nested test value without duplicating fixture construction."""

    current: Any = payload
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value


def _change_evidence_site(
    _pipeline: ModuleType,
    _draft: Any,
    _discovery: Any,
    evidence: Any,
) -> None:
    evidence["site"]["name"] = "Changed site"


def _change_draft_privacy(
    pipeline: ModuleType,
    draft: Any,
    _discovery: Any,
    evidence: Any,
) -> None:
    draft["privacy"]["model_data"].append("Changed model context")
    evidence["capability_draft_sha256"] = pipeline.sha256_payload(draft)


def _change_boundary_inputs(
    _pipeline: ModuleType,
    _draft: Any,
    _discovery: Any,
    evidence: Any,
) -> None:
    evidence["boundary"]["input_names"] = ["query"]


def _change_observation_index(
    _pipeline: ModuleType,
    _draft: Any,
    _discovery: Any,
    evidence: Any,
) -> None:
    evidence["timeline"][0]["observation_index"] = 999


def _change_milestone_link(
    _pipeline: ModuleType,
    _draft: Any,
    _discovery: Any,
    evidence: Any,
) -> None:
    evidence["timeline"][0]["milestone_id"] = "changed-milestone"


@pytest.mark.parametrize("mode", ["guided", "autonomous", "hybrid"])
def test_discovery_evidence_accepts_all_declared_modes(mode: str) -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=False, mode=mode)

    errors = pack.validate_discovery_evidence(evidence)

    assert errors == []


def test_hybrid_evidence_requires_both_operator_and_model_actions() -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=False)
    for entry in evidence["timeline"]:
        entry["actor"] = "operator"

    errors = pack.validate_discovery_evidence(evidence)

    assert "hybrid evidence must contain operator and model timeline entries" in errors


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("schema_version",), "unsupported", "schema_version must be"),
        (("session_id",), "Bad Session", "session_id must be"),
        (("recorded_at",), "yesterday", "recorded_at must be"),
        (("mode",), "video", "mode must be guided"),
        (("site", "name"), "", "site.name must be non-empty"),
        (
            ("site", "allowed_origins"),
            ["http://example.test"],
            "must use HTTPS",
        ),
        (
            ("site", "start_url"),
            "https://mail.google.com/mail?account=private",
            "must not contain credentials, query, or fragment",
        ),
        (("process", "objective"), "", "process.objective must be non-empty"),
        (("process", "out_of_scope"), [1], "out_of_scope must contain strings"),
        (("runtime", "controller"), "macro", "runtime.controller must be"),
        (
            ("authority", "authentication"),
            "model",
            "authority.authentication must be",
        ),
        (
            ("privacy", "private_evidence_retained"),
            True,
            "private_evidence_retained must be false",
        ),
        (("prompt_summary",), "", "prompt_summary must be non-empty"),
        (
            ("boundary", "input_names"),
            ["Not Valid"],
            "boundary.input_names must contain lower-case slugs",
        ),
        (("timeline", 0, "sequence"), 3, "timeline.sequence must be contiguous"),
        (("timeline", 0, "intent"), "", "timeline[0].intent must be non-empty"),
        (
            ("timeline", 0, "before", "path"),
            "/mail?private=value",
            "timeline[0].before.path must be query-free",
        ),
        (("branches",), [1], "branches must contain strings"),
        (("discovery_record_sha256",), "bad", "must be SHA-256"),
        (
            ("review", "approved_for_developer_transfer"),
            True,
            "developer transfer approval requires operator review",
        ),
    ],
)
def test_discovery_evidence_rejects_invalid_contract_fields(
    path: tuple[object, ...], value: object, expected: str
) -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=False)
    _set_nested(evidence, path, value)

    errors = pack.validate_discovery_evidence(evidence)

    assert any(expected in error for error in errors)


def test_discovery_evidence_rejects_private_material_and_unsafe_visual() -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=False)
    evidence["prompt_summary"] = "Send the result to person@example.com"
    evidence["visual_evidence"] = [
        {
            "path": "../private.png",
            "sha256": "a" * 64,
            "purpose": "Show one synthetic state.",
            "operator_selected": False,
            "reviewed_for_transfer": False,
            "contains_private_values": True,
        }
    ]

    errors = pack.validate_discovery_evidence(evidence)

    assert any("contains an email address" in error for error in errors)
    assert any("path is unsafe" in error for error in errors)
    assert any("operator_selected must be true" in error for error in errors)
    assert any("contains_private_values must be false" in error for error in errors)


def test_unreviewed_evidence_cannot_be_sealed(tmp_path: Path) -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=False)

    with pytest.raises(ValueError, match="not been reviewed"):
        pack.seal_developer_pack(
            _write_json(tmp_path / "evidence.json", evidence),
            _write_json(tmp_path / "discovery.json", discovery),
            _write_json(tmp_path / "draft.json", draft),
            tmp_path / "packs",
        )


def test_developer_pack_requires_exact_hashes_and_action_coverage(
    tmp_path: Path,
) -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=True)
    evidence["timeline"][0]["action_ids"] = ["unknown-action"]
    evidence["capability_draft_sha256"] = "a" * 64

    with pytest.raises(ValueError) as exc_info:
        pack.seal_developer_pack(
            _write_json(tmp_path / "evidence.json", evidence),
            _write_json(tmp_path / "discovery.json", discovery),
            _write_json(tmp_path / "draft.json", draft),
            tmp_path / "packs",
        )

    assert "evidence draft hash does not match the supplied capability" in str(
        exc_info.value
    )
    assert "developer evidence timeline does not cover every draft action" in str(
        exc_info.value
    )


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_change_evidence_site, "evidence site does not match"),
        (_change_draft_privacy, "draft privacy does not match"),
        (_change_boundary_inputs, "evidence boundary inputs do not match"),
        (_change_observation_index, "observation index is out of range"),
        (_change_milestone_link, "milestone does not match observation"),
    ],
)
def test_developer_pack_rejects_cross_lineage_changes(
    tmp_path: Path,
    mutate: Callable[[ModuleType, Any, Any, Any], None],
    expected: str,
) -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=True)
    mutate(pipeline, draft, discovery, evidence)

    with pytest.raises(ValueError, match=expected):
        pack.seal_developer_pack(
            _write_json(tmp_path / "evidence.json", evidence),
            _write_json(tmp_path / "discovery.json", discovery),
            _write_json(tmp_path / "draft.json", draft),
            tmp_path / "packs",
        )


def test_approved_pack_is_owner_only_hash_locked_and_verifiable(
    tmp_path: Path,
) -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=True)

    target = pack.seal_developer_pack(
        _write_json(tmp_path / "evidence.json", evidence),
        _write_json(tmp_path / "discovery.json", discovery),
        _write_json(tmp_path / "draft.json", draft),
        tmp_path / "packs",
    )

    assert pack.verify_developer_pack(target) == []
    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in target.rglob("*")
        if path.is_file()
    )
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        pack.seal_developer_pack(
            tmp_path / "evidence.json",
            tmp_path / "discovery.json",
            tmp_path / "draft.json",
            tmp_path / "packs",
        )


def test_pack_verification_detects_tampering_and_unlisted_files(tmp_path: Path) -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=True)
    target = pack.seal_developer_pack(
        _write_json(tmp_path / "evidence.json", evidence),
        _write_json(tmp_path / "discovery.json", discovery),
        _write_json(tmp_path / "draft.json", draft),
        tmp_path / "packs",
    )
    (target / "README.md").write_text("tampered", encoding="utf-8")
    (target / "unexpected.txt").write_text("unexpected", encoding="utf-8")

    errors = pack.verify_developer_pack(target)

    assert "developer pack file hash mismatch: README.md" in errors
    assert "developer pack contains unlisted file: unexpected.txt" in errors


def test_reviewed_visual_is_hash_checked_copied_and_verified(tmp_path: Path) -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=True)
    visual_path = tmp_path / "visual-evidence" / "synthetic-state.png"
    visual_path.parent.mkdir()
    visual_bytes = b"synthetic reviewed visual"
    visual_path.write_bytes(visual_bytes)
    evidence["visual_evidence"] = [
        {
            "path": "visual-evidence/synthetic-state.png",
            "sha256": hashlib.sha256(visual_bytes).hexdigest(),
            "purpose": "Show a synthetic control state with no private values.",
            "operator_selected": True,
            "reviewed_for_transfer": True,
            "contains_private_values": False,
        }
    ]

    target = pack.seal_developer_pack(
        _write_json(tmp_path / "evidence.json", evidence),
        _write_json(tmp_path / "discovery.json", discovery),
        _write_json(tmp_path / "draft.json", draft),
        tmp_path / "packs",
    )

    assert (
        target / "visual-evidence" / "synthetic-state.png"
    ).read_bytes() == visual_bytes
    assert pack.verify_developer_pack(target) == []


def test_visual_hash_mismatch_blocks_pack_sealing(tmp_path: Path) -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=True)
    visual_path = tmp_path / "visual-evidence" / "synthetic-state.png"
    visual_path.parent.mkdir()
    visual_path.write_bytes(b"unexpected bytes")
    evidence["visual_evidence"] = [
        {
            "path": "visual-evidence/synthetic-state.png",
            "sha256": "a" * 64,
            "purpose": "Show a synthetic state.",
            "operator_selected": True,
            "reviewed_for_transfer": True,
            "contains_private_values": False,
        }
    ]

    with pytest.raises(ValueError, match="visual evidence hash mismatch"):
        pack.seal_developer_pack(
            _write_json(tmp_path / "evidence.json", evidence),
            _write_json(tmp_path / "discovery.json", discovery),
            _write_json(tmp_path / "draft.json", draft),
            tmp_path / "packs",
        )


def test_discovery_pack_cli_validates_seals_and_verifies(tmp_path: Path) -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=True)
    evidence_path = _write_json(tmp_path / "evidence.json", evidence)
    discovery_path = _write_json(tmp_path / "discovery.json", discovery)
    draft_path = _write_json(tmp_path / "draft.json", draft)

    assert pack.main(["validate", str(evidence_path)]) == 0
    assert (
        pack.main(
            [
                "seal",
                "--evidence",
                str(evidence_path),
                "--discovery-record",
                str(discovery_path),
                "--capability-draft",
                str(draft_path),
                "--output-directory",
                str(tmp_path / "packs"),
            ]
        )
        == 0
    )
    target = tmp_path / "packs" / evidence["session_id"]
    assert pack.main(["verify", str(target)]) == 0

    evidence["schema_version"] = "unsupported"
    _write_json(tmp_path / "invalid.json", evidence)
    assert pack.main(["validate", str(tmp_path / "invalid.json")]) == 1


def test_transfer_approval_does_not_authorize_capability_promotion(
    tmp_path: Path,
) -> None:
    pipeline, pack = _modules()
    draft, discovery = _draft_and_discovery(pipeline)
    evidence = _evidence(pipeline, draft, discovery, approved=True)
    pack.seal_developer_pack(
        _write_json(tmp_path / "evidence.json", evidence),
        _write_json(tmp_path / "discovery.json", discovery),
        _write_json(tmp_path / "draft.json", draft),
        tmp_path / "packs",
    )

    with pytest.raises(ValueError, match="not been reviewed"):
        pipeline.promote_capability(
            tmp_path / "draft.json",
            tmp_path / "discovery.json",
            tmp_path / "promoted.json",
        )
