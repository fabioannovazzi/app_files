"""Cryptographic authorization checks with no production identity or grant."""

from __future__ import annotations

import copy
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID
from patent_box.authorization import request_bytes, verify_authorization
from patent_box.contracts import ContractError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_formalities import AFTER, AT, BEFORE, authority, certificate, key, write


def signed(raw, cert, secret, root):
    return (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(raw)
        .add_signer(cert, secret, hashes.SHA256())
        .add_certificate(root)
        .sign(
            serialization.Encoding.DER,
            [pkcs7.PKCS7Options.Binary, pkcs7.PKCS7Options.DetachedSignature],
        )
    )


@pytest.fixture
def authorized(authority, tmp_path):
    a = authority
    secret = key()
    reviewer = certificate(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SYNTHETIC PROFESSIONAL")]),
        secret.public_key(),
        a["root_cert"].subject,
        a["root_key"],
    )
    scope = {
        "client_id": "TEST.CLIENT",
        "engagement_id": "TEST.ENGAGEMENT",
        "period": {"period_id": "P2025", "start": "2025-01-01", "end": "2025-12-31"},
    }
    policy = {
        "schema_version": "1.0",
        "policy_id": "SYNTHETIC.POLICY",
        "authority_name": "Test firm only",
        "demo": True,
        "admin_certificate_sha256": [
            a["signer_cert"].fingerprint(hashes.SHA256()).hex()
        ],
        "revoked_certificate_sha256": [],
        "revoked_mandate_ids": [],
    }
    mandate = {
        "schema_version": "1.0",
        "mandate_id": "TEST.MANDATE",
        "policy_id": policy["policy_id"],
        "demo": True,
        "scope": scope,
        "reviewer_name": "Synthetic Professional",
        "professional_reference": "Not a real professional registration",
        "reviewer_certificate_sha256": reviewer.fingerprint(hashes.SHA256()).hex(),
        "actions": [
            "REVIEW_CONTROLS",
            "REVIEW_RULES",
            "APPROVE_DOSSIER",
            "REOPEN_CASE",
        ],
        "valid_from": BEFORE.isoformat(),
        "valid_until": AFTER.isoformat(),
        "powers_evidence": [
            {"reference": "SYNTHETIC.MANDATE.DOCUMENT", "sha256": "a" * 64}
        ],
    }
    request = {
        "schema_version": "1.0",
        "request_id": "TEST.REQUEST",
        "action": "REVIEW_CONTROLS",
        "demo": True,
        "scope": copy.deepcopy(scope),
        "run_id": "TEST.RUN",
        "created_at": AT.isoformat(),
        "expires_at": (AT + timedelta(hours=1)).isoformat(),
        "statement": "Synthetic test review only",
        "bindings": {
            "proposal_sha256": "b" * 64,
            "evidence_sha256": "c" * 64,
            "rules_sha256": "d" * 64,
            "source_preflight_sha256": "e" * 64,
            "result_sha256": None,
            "artifacts_sha256": None,
            "prior_approval_sha256": None,
        },
    }
    grant_path = write(tmp_path / "mandate.json", request_bytes(mandate))
    grant_signature = write(
        tmp_path / "mandate.p7s",
        signed(
            grant_path.read_bytes(), a["signer_cert"], a["signer_key"], a["root_cert"]
        ),
    )
    signature = write(
        tmp_path / "review.p7s",
        signed(request_bytes(request), reviewer, secret, a["root_cert"]),
    )
    return dict(
        request=request,
        signature=signature,
        mandate=grant_path,
        mandate_signature=grant_signature,
        policy=policy,
        openssl=a["openssl"],
        trusted_roots=a["ca"],
        crls=a["crl"],
        at=AT,
    )


def test_signed_firm_mandate_authenticates_exact_review_and_bindings(authorized):
    result = verify_authorization(**authorized)
    assert result["identity_assurance"] == "CERTIFICATE_AND_FIRM_SIGNED_MANDATE"
    assert result["reviewer_name"] == "Synthetic Professional"
    assert result["request"]["bindings"]["proposal_sha256"] == "b" * 64
    assert result["review_verification"]["revocation"]["status"] == "PASS"
    assert (
        result["professional_status_basis"]
        == "ASSERTED_BY_FIRM_ADMINISTRATOR_NOT_AN_INDEPENDENT_REGISTRY_CHECK"
    )
    assert result["qualified_signature_status"] == "NOT_TESTED"


@pytest.mark.parametrize(
    "field",
    ["proposal_sha256", "evidence_sha256", "rules_sha256", "source_preflight_sha256"],
)
def test_changed_review_bindings_invalidate_real_signature(authorized, field):
    authorized["request"]["bindings"][field] = "f" * 64
    with pytest.raises(ContractError, match="signature_integrity"):
        verify_authorization(**authorized)


@pytest.mark.parametrize("field", ["client_id", "engagement_id"])
def test_review_for_other_client_or_engagement_is_rejected(authorized, field):
    authorized["request"]["scope"][field] = "OTHER"
    with pytest.raises(ContractError, match="exact client"):
        verify_authorization(**authorized)


def test_changed_fiscal_period_is_outside_mandate(authorized):
    authorized["request"]["scope"]["period"]["end"] = "2026-12-31"
    with pytest.raises(ContractError, match="exact client"):
        verify_authorization(**authorized)


def test_revoked_mandate_is_rejected(authorized):
    authorized["policy"]["revoked_mandate_ids"] = ["TEST.MANDATE"]
    with pytest.raises(ContractError, match="Mandate has been revoked"):
        verify_authorization(**authorized)


def test_unconfigured_firm_cannot_authenticate_a_professional(authorized):
    authorized["policy"]["admin_certificate_sha256"] = []
    with pytest.raises(ContractError, match="not configured"):
        verify_authorization(**authorized)


def test_different_admin_certificate_cannot_issue_mandate(authorized):
    authorized["policy"]["admin_certificate_sha256"] = ["0" * 64]
    with pytest.raises(ContractError, match="trusted firm administrator"):
        verify_authorization(**authorized)


def test_revoked_firm_administrator_is_rejected(authorized):
    authorized["policy"]["revoked_certificate_sha256"] = authorized["policy"][
        "admin_certificate_sha256"
    ]
    with pytest.raises(ContractError, match="trusted firm administrator"):
        verify_authorization(**authorized)


def test_synthetic_request_cannot_authorize_real_case(authorized):
    authorized["request"]["demo"] = False
    with pytest.raises(ContractError, match="cannot be mixed"):
        verify_authorization(**authorized)


def test_expired_request_cannot_be_replayed(authorized):
    authorized["at"] += timedelta(days=1)
    with pytest.raises(ContractError, match="expired"):
        verify_authorization(**authorized)


def test_substituted_mandate_bytes_invalidate_administrator_signature(authorized):
    raw = (
        authorized["mandate"]
        .read_bytes()
        .replace(b"Synthetic Professional", b"Another Professional")
    )
    authorized["mandate"].write_bytes(raw)
    with pytest.raises(ContractError, match="signature_integrity"):
        verify_authorization(**authorized)


def test_revoked_certificate_cannot_authorize_decision(authorized, authority):
    authorized["crls"] = authority["revoked"]
    with pytest.raises(ContractError, match="revocation"):
        verify_authorization(**authorized)


def test_final_approval_cannot_omit_result_artifacts_and_control_review(authorized):
    authorized["request"]["action"] = "APPROVE_DOSSIER"
    with pytest.raises(ContractError, match="Final approval must bind"):
        verify_authorization(**authorized)


def test_reopening_cannot_omit_previous_approved_version(authorized):
    authorized["request"]["action"] = "REOPEN_CASE"
    authorized["request"]["reopening"] = {
        "previous_proposal_sha256": "1" * 64,
        "reason": "Synthetic revision",
    }
    with pytest.raises(ContractError, match="preserved previous approval"):
        verify_authorization(**authorized)


def test_weak_signed_mandate_cannot_authorize_professional_review(
    authorized, authority, tmp_path
):
    import subprocess

    a = authority
    secret = write(
        tmp_path / "test-key.pem",
        a["signer_key"].private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    weak = tmp_path / "weak-mandate.der"
    subprocess.run(
        [
            str(a["openssl"]),
            "cms",
            "-sign",
            "-binary",
            "-in",
            str(authorized["mandate"]),
            "-signer",
            str(a["signer"]),
            "-inkey",
            str(secret),
            "-certfile",
            str(a["ca"]),
            "-md",
            "sha1",
            "-outform",
            "DER",
            "-out",
            str(weak),
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    authorized["mandate_signature"] = weak
    with pytest.raises(ContractError, match="signature_algorithm_policy"):
        verify_authorization(**authorized)
