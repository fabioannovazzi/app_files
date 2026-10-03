"""Real CMS checks against fictional catalog-role grants; no real tax authority."""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes

PLUGIN = Path(__file__).resolve().parents[2] / "plugins/lipe"
sys.path.insert(0, str(PLUGIN / "scripts"))
import lipe_catalog_authorization
from lipe_authorization import request_bytes
from lipe_catalog import (
    create_catalog,
    dispute,
    history,
    record,
    resolve_dispute,
    revoke,
)
from lipe_catalog_authorization import prepare_decision
from lipe_core import ContractError, read_json
from test_lipe_approval import crypto, sign
from test_lipe_catalog import entry


def studio(root, crypto, monkeypatch, *, scope="STUDIO"):
    """Install a fictional independent policy, not a user or professional credential."""
    path = root / "catalog/catalog.sqlite3"
    metadata = create_catalog(path, "fictional-studio", "0.80", data_origin="REAL")
    value = entry(path.parent, scope=scope)
    value["review"]["reviewer"] = "FICTIONAL PROFESSIONAL"
    if scope == "CENTRAL":
        value["curator_review"]["reviewer"] = "FICTIONAL CURATOR"
        value["disclosure_review"]["reviewer"] = "FICTIONAL CURATOR"
    authority = crypto["authority"]
    config = {
        "schema_version": "lipe.catalog.authority.v1",
        "policy_id": "fictional-catalog-policy",
        **{key: metadata[key] for key in ("catalog_id", "studio_id", "data_origin")},
        **{
            key: str(authority[key].resolve())
            for key in ("openssl", "trusted_roots", "crls")
        },
        "revoked_certificate_sha256": [],
        "signers": [
            {
                "name": "FICTIONAL PROFESSIONAL",
                "certificate_sha256": crypto["certs"]["reviewer"]
                .fingerprint(hashes.SHA256())
                .hex(),
                "roles": ["PROFESSIONAL"],
                "scopes": ["CLIENT", "STUDIO", "CENTRAL"],
                "all_clients": False,
                "client_ids": ["client-a"],
            },
            {
                "name": "FICTIONAL CURATOR",
                "certificate_sha256": crypto["certs"]["admin"]
                .fingerprint(hashes.SHA256())
                .hex(),
                "roles": ["CURATOR", "DISCLOSURE_REVIEWER"],
                "scopes": ["CENTRAL"],
                "all_clients": False,
                "client_ids": [],
            },
        ],
    }
    config_path = root / "host-authority.json"
    config_path.write_bytes(request_bytes(config))
    monkeypatch.setenv("VERA_LIPE_CATALOG_AUTHORITY_CONFIG", str(config_path))
    return path, value, config_path


def operation(value):
    return {
        "kind": "RECORD",
        "entry_id": value["entry_id"],
        "entry": value,
        "supersedes": None,
    }


def approval(path, operation, crypto, *, who=("reviewer",), label="packet"):
    folder = prepare_decision(path, operation, path.parent / label)
    for person in who:
        sign(
            (folder / "request.json").read_bytes(),
            folder / f"decision-{person}.p7s",
            crypto,
            person,
        )
    return folder


def add(path, value, packet=None):
    return record(
        path,
        value,
        path.parent,
        expected_head=history(path)["head_hash"],
        approval=packet,
    )


def test_real_catalog_requires_signatures_even_when_every_reviewer_name_is_filled(
    tmp_path, crypto, monkeypatch
):
    path, value, _ = studio(tmp_path, crypto, monkeypatch)

    with pytest.raises(ContractError, match="externally signed"):
        add(path, value)

    assert history(path)["events"] == []
    assert history(path)["metadata"]["require_signatures"] is True


@pytest.mark.parametrize("location", ["missing", "inside-catalog", "inside-packet"])
def test_authority_cannot_be_invented_inside_selected_evidence(
    tmp_path, crypto, monkeypatch, location
):
    path, value, config_path = studio(tmp_path, crypto, monkeypatch)
    packet = path.parent / "packet"
    if location == "missing":
        monkeypatch.delenv("VERA_LIPE_CATALOG_AUTHORITY_CONFIG")
    else:
        target = (
            path.parent / "case-policy.json"
            if location == "inside-catalog"
            else tmp_path / "external-packet/policy.json"
        )
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(config_path.read_bytes())
        monkeypatch.setenv("VERA_LIPE_CATALOG_AUTHORITY_CONFIG", str(target))
        if location == "inside-packet":
            packet = target.parent

    with pytest.raises(ContractError, match="authority"):
        prepare_decision(path, operation(value), packet)

    assert history(path)["events"] == []


@pytest.mark.parametrize(
    "scope,signers",
    [
        ("CLIENT", ("reviewer",)),
        ("STUDIO", ("reviewer",)),
        ("CENTRAL", ("reviewer", "admin")),
    ],
)
def test_authorized_roles_preserve_originals_and_commit_exact_reviewed_entry(
    tmp_path, crypto, monkeypatch, scope, signers
):
    path, value, _ = studio(tmp_path, crypto, monkeypatch, scope=scope)
    packet = approval(path, operation(value), crypto, who=signers)

    result = add(path, value, packet)

    proof = result["event"]["authorization"]
    assert result["event"]["entry"] == value
    assert proof["status"] == "ROLES_VERIFIED_AT_COMMIT"
    assert proof["qualified_signature_status"] == "NOT_TESTED"
    assert proof["remote_sharing"] is False
    assert len(proof["verification"]) == len(signers)
    preserved = next(
        item for item in proof["artifacts"] if item["file"].endswith("-request.json")
    )
    assert (
        path.parent / (path.name + ".authorizations") / preserved["file"]
    ).read_bytes() == (packet / "request.json").read_bytes()
    assert len(history(path)["events"]) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "unsigned-curator",
        "missing-disclosure-role",
        "revoked-certificate",
        "crl-revoked",
        "different-name",
        "changed-class",
        "changed-request",
        "expired",
        "foreign-catalog",
        "duplicate-grant",
        "duplicate-signature",
    ],
)
def test_central_decision_rejects_unauthorized_or_changed_evidence_before_commit(
    tmp_path, crypto, monkeypatch, mutation
):
    path, value, config_path = studio(tmp_path, crypto, monkeypatch, scope="CENTRAL")
    packet = approval(path, operation(value), crypto, who=("reviewer", "admin"))
    config = read_json(config_path)
    if mutation == "unsigned-curator":
        (packet / "decision-admin.p7s").unlink()
    elif mutation == "missing-disclosure-role":
        config["signers"][1]["roles"] = ["CURATOR"]
    elif mutation == "revoked-certificate":
        config["revoked_certificate_sha256"] = [
            config["signers"][1]["certificate_sha256"]
        ]
    elif mutation == "crl-revoked":
        config["crls"] = str(crypto["revoked"])
    elif mutation == "different-name":
        config["signers"][1]["name"] = "UNRELATED PERSON"
    elif mutation == "changed-class":
        value["tax_class"]["treatment"] = "SALE_EXCLUDED"
    elif mutation == "changed-request":
        request = read_json(packet / "request.json")
        request["operation"]["entry"]["description"] = "Altered after signing"
        (packet / "request.json").write_bytes(request_bytes(request))
    elif mutation == "expired":
        request = read_json(packet / "request.json")
        request["created_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=25)
        ).isoformat()
        request["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        (packet / "request.json").write_bytes(request_bytes(request))
        sign(
            (packet / "request.json").read_bytes(),
            packet / "decision-reviewer.p7s",
            crypto,
            "reviewer",
        )
        sign(
            (packet / "request.json").read_bytes(),
            packet / "decision-admin.p7s",
            crypto,
            "admin",
        )
    elif mutation == "foreign-catalog":
        config["catalog_id"] = "11111111-1111-4111-8111-111111111111"
    elif mutation == "duplicate-grant":
        config["signers"].append(copy.deepcopy(config["signers"][0]))
    else:
        (packet / "decision-copy.p7s").write_bytes(
            (packet / "decision-reviewer.p7s").read_bytes()
        )
    config_path.write_bytes(request_bytes(config))

    with pytest.raises(ContractError):
        add(path, value, packet)

    assert history(path)["events"] == []


@pytest.mark.parametrize(
    "scope,client,allowed",
    [
        ("CLIENT", "client-a", True),
        ("CLIENT", "client-b", False),
        ("STUDIO", None, False),
        ("CENTRAL", None, False),
    ],
)
def test_client_limited_professional_cannot_write_other_clients_or_shared_scopes(
    tmp_path, crypto, monkeypatch, scope, client, allowed
):
    path, value, config_path = studio(tmp_path, crypto, monkeypatch, scope=scope)
    value["client_id"] = client
    config = read_json(config_path)
    config["signers"][0]["scopes"] = ["CLIENT"]
    config_path.write_bytes(request_bytes(config))
    packet = approval(
        path,
        operation(value),
        crypto,
        who=("reviewer", "admin") if scope == "CENTRAL" else ("reviewer",),
    )

    if allowed:
        result = add(path, value, packet)
        assert result["event"]["entry"]["client_id"] == "client-a"
    else:
        with pytest.raises(ContractError, match="role or client permission"):
            add(path, value, packet)
        assert history(path)["events"] == []


def test_concurrent_head_change_requires_a_new_signed_operation(
    tmp_path, crypto, monkeypatch
):
    path, value, _ = studio(tmp_path, crypto, monkeypatch)
    packet = approval(path, operation(value), crypto)
    alternative = copy.deepcopy(value)
    alternative["entry_id"] = "different-entry"
    other = approval(path, operation(alternative), crypto, label="other-packet")
    add(path, alternative, other)

    with pytest.raises(ContractError, match="stale"):
        add(path, value, packet)

    assert len(history(path)["events"]) == 1


def test_historical_authentication_evidence_cannot_disappear_silently(
    tmp_path, crypto, monkeypatch
):
    path, value, _ = studio(tmp_path, crypto, monkeypatch)
    result = add(path, value, approval(path, operation(value), crypto))
    evidence = result["event"]["authorization"]["artifacts"][0]
    stored = path.parent / (path.name + ".authorizations") / evidence["file"]
    stored.write_bytes(b"Changed original authority evidence")

    with pytest.raises(ContractError, match="missing or changed"):
        history(path)


def test_authority_change_during_signature_verification_prevents_commit(
    tmp_path, crypto, monkeypatch
):
    path, value, config_path = studio(tmp_path, crypto, monkeypatch)
    packet = approval(path, operation(value), crypto)
    verify = lipe_catalog_authorization.verify_cms_document

    def change_authority(*args, **kwargs):
        result = verify(*args, **kwargs)
        config = read_json(config_path)
        config["revoked_certificate_sha256"] = [
            config["signers"][0]["certificate_sha256"]
        ]
        config_path.write_bytes(request_bytes(config))
        return result

    monkeypatch.setattr(
        lipe_catalog_authorization, "verify_cms_document", change_authority
    )

    with pytest.raises(ContractError, match="authority changed"):
        add(path, value, packet)

    assert history(path)["events"] == []


def test_mutating_callers_input_during_verification_cannot_replace_signed_content(
    tmp_path, crypto, monkeypatch
):
    path, value, _ = studio(tmp_path, crypto, monkeypatch)
    original = copy.deepcopy(value)
    packet = approval(path, operation(value), crypto)
    verify = lipe_catalog_authorization.verify_cms_document

    def change_input(*args, **kwargs):
        value["tax_class"]["treatment"] = "SALE_EXCLUDED"
        return verify(*args, **kwargs)

    monkeypatch.setattr(lipe_catalog_authorization, "verify_cms_document", change_input)

    result = add(path, value, packet)

    assert result["event"]["entry"] == original
    assert history(path)["events"][0]["event"]["entry"] == original


def test_central_revocation_requires_the_curator_signature_and_exact_fallback_choice(
    tmp_path, crypto, monkeypatch
):
    path, value, _ = studio(tmp_path, crypto, monkeypatch, scope="CENTRAL")
    original = add(
        path, value, approval(path, operation(value), crypto, who=("reviewer", "admin"))
    )
    review = value["curator_review"]
    op = {
        "kind": "REVOKE",
        "entry_id": value["entry_id"],
        "revoked_revision": original["event_hash"],
        "allow_fallback": False,
        "review": review,
    }
    packet = approval(path, op, crypto, who=("admin",), label="revoke")

    result = revoke(
        path,
        value["entry_id"],
        review,
        expected_head=history(path)["head_hash"],
        revision=original["event_hash"],
        approval=packet,
    )

    assert result["event"]["kind"] == "REVOKE"
    assert result["event"]["allow_fallback"] is False
    assert result["event"]["authorization"]["signers"][0]["name"] == "FICTIONAL CURATOR"


def test_dispute_and_curator_resolution_preserve_distinct_authorized_decisions(
    tmp_path, crypto, monkeypatch
):
    path, value, _ = studio(tmp_path, crypto, monkeypatch, scope="CENTRAL")
    original = add(
        path, value, approval(path, operation(value), crypto, who=("reviewer", "admin"))
    )
    op = {
        "kind": "DISPUTE",
        "key": {key: value[key] for key in ("software", "side", "code")},
        "sources": value["sources"],
        "evidence": value["evidence"],
        "review": value["review"],
    }
    packet = approval(path, op, crypto, label="dispute")
    flagged = dispute(
        path,
        value,
        path.parent,
        value["review"],
        expected_head=history(path)["head_hash"],
        approval=packet,
    )
    op = {
        "kind": "RESOLVE_DISPUTE",
        "dispute_hash": flagged["event_hash"],
        "selected_revision": original["event_hash"],
        "curator_review": value["curator_review"],
    }
    packet = approval(path, op, crypto, who=("admin",), label="resolution")

    result = resolve_dispute(
        path,
        flagged["event_hash"],
        value["curator_review"],
        expected_head=history(path)["head_hash"],
        selected_revision=original["event_hash"],
        approval=packet,
    )

    assert result["event"]["kind"] == "RESOLVE_DISPUTE"
    assert len(history(path)["events"]) == 3
