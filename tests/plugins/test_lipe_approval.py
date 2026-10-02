"""Front-page and exact-version authorization tests using fictional evidence only."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

PLUGIN = Path(__file__).resolve().parents[2] / "plugins/lipe"
sys.path.insert(0, str(PLUGIN / "scripts"))
import lipe_approval
from lipe import save_result
from lipe_approval import accept_review, current_bindings, main, prepare_review
from lipe_authorization import (
    load_authority,
    read_signed_json,
    request_bytes,
    verify_approval,
)
from lipe_core import ContractError, calculate, read_json
from lipe_frontpage import check_identifier, validate_frontpage

AT = datetime(2026, 10, 3, 10, tzinfo=timezone.utc)
BEFORE = datetime(2025, 1, 1, tzinfo=timezone.utc)
AFTER = datetime(2028, 1, 1, tzinfo=timezone.utc)


def frontpage(case: dict, root: Path, **overrides) -> dict:
    """Invent source text explicitly; this is not an Anagrafe registry response."""
    fields = {
        "CodiceFiscale": "RSSMRA80A01H501U",
        "AnnoImposta": case["tax_year"],
        "PartitaIVA": "12345678903",
        "CFDichiarante": None,
        "CodiceCaricaDichiarante": None,
        "CodiceFiscaleSocieta": None,
        "FirmaDichiarazione": "1",
        "CFIntermediario": None,
        "ImpegnoPresentazione": None,
        "DataImpegno": None,
        "FirmaIntermediario": None,
    }
    fields.update(overrides)
    review = {
        "status": "CONFIRMED",
        "reviewer": "FICTIONAL ACTOR — NOT PROFESSIONAL ACCEPTANCE",
        "reviewed_on": "2026-10-02",
        "reason": "Synthetic test declaration only.",
    }
    evidence = {
        name: {"source_id": "front", "page": 1, "quote": f"SYNTHETIC {name}: {value}."}
        for name, value in fields.items()
        if value is not None
        and name not in {"FirmaDichiarazione", "FirmaIntermediario"}
    }
    path = root / "front-source.txt"
    path.write_text(
        "\n".join(row["quote"] for row in evidence.values()), encoding="utf-8"
    )
    return {
        "schema_version": "lipe.frontpage.v1",
        "client_id": case["client_id"],
        "engagement_id": case["engagement_id"],
        "data_origin": case["data_origin"],
        "taxpayer_kind": "NATURAL_PERSON",
        "fields": fields,
        "sources": [
            {
                "source_id": "front",
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ],
        "field_evidence": evidence,
        "registry_checks": [
            {
                "field": name,
                "verified_on": "2026-10-01",
                "evidence": row,
                "review": copy.deepcopy(review),
            }
            for name, row in evidence.items()
            if name
            in {
                "CodiceFiscale",
                "PartitaIVA",
                "CFDichiarante",
                "CodiceFiscaleSocieta",
                "CFIntermediario",
            }
        ],
        "review": review,
    }


def example(root: Path) -> tuple[dict, dict, Path]:
    case = read_json(PLUGIN / "examples/synthetic-case.json")
    shutil.copy(PLUGIN / "examples/synthetic-registers.txt", root)
    front = frontpage(case, root)
    draft = save_result(case, calculate(case, root), root / "drafts")
    return case, front, draft


@pytest.mark.parametrize(
    "identifier,vat",
    [
        ("RSSMRA80A01H501U", False),
        ("12345678903", True),
        ("12345678903", False),
        ("RSSMRA80A01H50MM", False),
    ],
)
def test_identifier_checks_allow_valid_transcriptions_including_omocodia(
    identifier, vat
):
    assert check_identifier(identifier, vat=vat) is None


@pytest.mark.parametrize(
    "identifier,vat",
    [
        ("RSSMRA80A01H501A", False),
        ("12345678901", True),
        ("92345678906", True),
        ("rssmra80a01h501u", False),
        ("RSSMRA80A01H501U\n", False),
    ],
)
def test_identifier_checks_reject_invalid_checksum_or_syntax(identifier, vat):
    with pytest.raises(ContractError, match="identifier"):
        check_identifier(identifier, vat=vat)


def test_frontpage_review_reports_its_limits_without_claiming_registry_access(tmp_path):
    case, front, _ = example(tmp_path)
    result = validate_frontpage(front, case, tmp_path, on_date=AT.date())
    assert result["fields"]["CodiceFiscale"] == "RSSMRA80A01H501U"
    assert (
        result["registry_status"]
        == "SOURCE_BOUND_PROFESSIONAL_DECLARATION_NOT_A_LIVE_REGISTRY_CHECK"
    )
    assert result["professional_identity_authenticated"] is False
    assert result["network_calls"] is False


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("DataImpegno", "2021-12-31", "commitment date"),
        ("DataImpegno", "2026-10-04", "commitment date"),
        ("FirmaIntermediario", None, "complete together"),
        ("ImpegnoPresentazione", None, "complete together"),
    ],
)
def test_intermediary_incomplete_or_outside_date_window_is_rejected(
    tmp_path, field, value, message
):
    case = read_json(PLUGIN / "examples/synthetic-case.json")
    fields = dict(
        CFIntermediario="RSSMRA80A01H501U",
        ImpegnoPresentazione="1",
        DataImpegno="2026-10-01",
        FirmaIntermediario="1",
    )
    fields[field] = value
    front = frontpage(case, tmp_path, **fields)
    with pytest.raises(ContractError, match=message):
        validate_frontpage(front, case, tmp_path, on_date=AT.date())


def test_complete_intermediary_date_is_serialized_as_ddmmyyyy(tmp_path):
    case = read_json(PLUGIN / "examples/synthetic-case.json")
    front = frontpage(
        case,
        tmp_path,
        CFIntermediario="RSSMRA80A01H501U",
        ImpegnoPresentazione="2",
        DataImpegno="2022-01-01",
        FirmaIntermediario="1",
    )
    result = validate_frontpage(front, case, tmp_path, on_date=AT.date())
    assert result["fields"]["DataImpegno"] == "01012022"


@pytest.mark.parametrize(
    "mutation,message",
    [
        ("wrong-client", "different case"),
        ("wrong-year", "tax year differs"),
        ("unreviewed", "professional review"),
        ("future-review", "future"),
        ("missing-field-proof", "Every populated"),
        ("missing-registry", "one explicit"),
        ("duplicate-registry", "one explicit"),
        ("unreviewed-registry", "professionally confirmed"),
        ("future-registry", "dates are inconsistent"),
        ("wrong-quote", "absent"),
        ("group-field", "Additional properties"),
        ("other-without-declarant", "representative"),
        ("office-without-declarant", "supplied together"),
        ("numeric-declarant", "sixteen-character"),
    ],
)
def test_frontpage_missing_or_conflicting_evidence_is_rejected(
    tmp_path, mutation, message
):
    case = read_json(PLUGIN / "examples/synthetic-case.json")
    front = frontpage(case, tmp_path)
    if mutation == "wrong-client":
        front["client_id"] = "different"
    elif mutation == "wrong-year":
        front["fields"]["AnnoImposta"] = 2025
    elif mutation == "unreviewed":
        front["review"]["status"] = "PROPOSED"
    elif mutation == "future-review":
        front["review"]["reviewed_on"] = "2026-10-04"
    elif mutation == "missing-field-proof":
        del front["field_evidence"]["AnnoImposta"]
    elif mutation == "missing-registry":
        front["registry_checks"].pop()
    elif mutation == "duplicate-registry":
        front["registry_checks"].append(front["registry_checks"][0])
    elif mutation == "unreviewed-registry":
        front["registry_checks"][0]["review"]["status"] = "PROPOSED"
    elif mutation == "future-registry":
        front["registry_checks"][0]["verified_on"] = "2026-10-04"
    elif mutation == "wrong-quote":
        front["field_evidence"]["PartitaIVA"]["quote"] = "Unrelated source"
    elif mutation == "group-field":
        front["fields"]["PartitaIVAControllante"] = "12345678903"
    elif mutation == "other-without-declarant":
        front["taxpayer_kind"] = "OTHER"
    elif mutation == "office-without-declarant":
        front["fields"]["CodiceCaricaDichiarante"] = "1"
    elif mutation == "numeric-declarant":
        front["fields"]["CFDichiarante"] = "12345678903"
    with pytest.raises(ContractError, match=message):
        validate_frontpage(front, case, tmp_path, on_date=AT.date())


def certificate(name, subject_key, issuer, issuer_key, *, ca=False):
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer or subject)
        .public_key(subject_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(BEFORE)
        .not_valid_after(AFTER)
        .add_extension(
            x509.BasicConstraints(ca=ca, path_length=1 if ca else None), critical=True
        )
        .add_extension(
            x509.KeyUsage(not ca, not ca, False, False, False, ca, ca, False, False),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(subject_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),
            critical=False,
        )
    )
    if not ca:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]),
            critical=False,
        )
    return builder.sign(issuer_key, hashes.SHA256())


@pytest.fixture(scope="module")
def crypto(tmp_path_factory):
    """Use actual OpenSSL verification; the fixture fails if CI cannot exercise it."""
    executable = shutil.which("openssl")
    assert executable, "The LIPE crypto acceptance tests require OpenSSL 3"
    version = subprocess.run(
        [executable, "version"], capture_output=True, check=True, timeout=15
    )
    assert version.stdout.startswith(b"OpenSSL 3."), version.stdout
    root = tmp_path_factory.mktemp("fictional-lipe-authority")
    keys = {
        name: rsa.generate_private_key(public_exponent=65537, key_size=2048)
        for name in ("ca", "admin", "reviewer")
    }
    ca = certificate("SYNTHETIC LIPE CA", keys["ca"], None, keys["ca"], ca=True)
    certs = {
        name: certificate("SYNTHETIC " + name, key, ca.subject, keys["ca"])
        for name, key in keys.items()
        if name != "ca"
    }
    roots = root / "roots.pem"
    roots.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    crl = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(ca.subject)
        .last_update(BEFORE)
        .next_update(AFTER)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(keys["ca"].public_key()),
            critical=False,
        )
        .add_extension(x509.CRLNumber(1), critical=False)
    )
    crls = root / "crls.pem"
    crls.write_bytes(
        crl.sign(keys["ca"], hashes.SHA256()).public_bytes(serialization.Encoding.PEM)
    )
    revoked = root / "revoked.pem"
    revoked.write_bytes(
        crl.add_revoked_certificate(
            x509.RevokedCertificateBuilder()
            .serial_number(certs["reviewer"].serial_number)
            .revocation_date(BEFORE)
            .build()
        )
        .sign(keys["ca"], hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
    )
    policy = {
        "schema_version": "lipe.authority.v1",
        "policy_id": "fictional-policy",
        "studio_id": "fictional-studio",
        "authority_name": "FICTIONAL FIRM",
        "data_origin": "SYNTHETIC",
        "admin_certificate_sha256": [certs["admin"].fingerprint(hashes.SHA256()).hex()],
        "revoked_certificate_sha256": [],
        "revoked_mandate_ids": [],
    }
    return {
        "keys": keys,
        "certs": certs,
        "revoked": revoked,
        "authority": {
            "policy": policy,
            "openssl": Path(executable),
            "trusted_roots": roots,
            "crls": crls,
        },
    }


def sign(raw: bytes, path: Path, crypto: dict, who: str) -> Path:
    path.write_bytes(
        pkcs7.PKCS7SignatureBuilder()
        .set_data(raw)
        .add_signer(crypto["certs"][who], crypto["keys"][who], hashes.SHA256())
        .sign(
            serialization.Encoding.DER,
            [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary],
        )
    )
    return path


def signed_packet(root, crypto):
    case, front, draft = example(root)
    packet = prepare_review(case, front, draft, root, root / "packet", at=AT)
    request = read_json(packet / "request.json")
    mandate = {
        "schema_version": "lipe.mandate.v1",
        "policy_id": "fictional-policy",
        "mandate_id": "fictional-mandate",
        "scope": request["scope"],
        "reviewer_name": "FICTIONAL REVIEWER",
        "professional_reference": "SYNTHETIC ONLY",
        "reviewer_certificate_sha256": crypto["certs"]["reviewer"]
        .fingerprint(hashes.SHA256())
        .hex(),
        "actions": ["APPROVE_LIPE_EXPORT"],
        "valid_from": BEFORE.isoformat(),
        "valid_until": AFTER.isoformat(),
        "powers_evidence": [
            {"reference": "FICTIONAL MANDATE EVIDENCE", "sha256": "1" * 64}
        ],
    }
    mandate_path = root / "mandate.json"
    mandate_path.write_bytes(request_bytes(mandate))
    files = {
        "signature": sign(
            (packet / "request.json").read_bytes(),
            root / "decision.p7s",
            crypto,
            "reviewer",
        ),
        "mandate": mandate_path,
        "mandate_signature": sign(
            mandate_path.read_bytes(), root / "mandate.p7s", crypto, "admin"
        ),
    }
    return case, front, draft, packet, request, files


def test_real_cms_signatures_bind_professional_mandate_and_exact_review(
    tmp_path, crypto
):
    case, front, draft, packet, request, files = signed_packet(tmp_path, crypto)
    output = accept_review(
        case,
        front,
        draft,
        tmp_path,
        packet / "request.json",
        tmp_path / "accepted",
        at=AT,
        authority=crypto["authority"],
        **files,
    )
    proof = read_json(output / "approval.json")
    assert proof["request"] == request
    assert proof["review_verification"]["revocation"]["status"] == "PASS"
    assert proof["identity_assurance"] == "CERTIFICATE_AND_FIRM_SIGNED_MANDATE"
    assert proof["qualified_signature_status"] == "NOT_TESTED"
    assert proof["filing_status"] == "NOT_SIGNED_OR_TRANSMITTED"
    assert (output / "decision.p7s").read_bytes() == files["signature"].read_bytes()
    assert not list(output.glob("*.xml"))


@pytest.mark.parametrize(
    "mutation,message",
    [
        ("changed-request", "signature_integrity"),
        ("changed-mandate", "signature_integrity"),
        ("wrong-signer", "authorized professional"),
        ("untrusted-admin", "trusted firm administrator"),
        ("revoked-mandate", "revoked"),
        ("revoked-certificate", "authorized professional"),
        ("crl-revoked", "revocation"),
        ("expired", "expired"),
        ("future", "future"),
        ("overlong", "24 hours"),
        ("real-policy", "cannot be mixed"),
        ("provider-changed", "component changed"),
        ("wrong-scope", "exact case scope"),
    ],
)
def test_cryptographic_and_authority_failures_do_not_become_approval(
    tmp_path, crypto, mutation, message
):
    _, _, _, _, request, files = signed_packet(tmp_path, crypto)
    authority = copy.deepcopy(crypto["authority"])
    if mutation == "changed-request":
        request["bindings"]["result_hash"] = "f" * 64
    elif mutation == "changed-mandate":
        grant = read_json(files["mandate"])
        grant["reviewer_name"] = "ALTERED"
        files["mandate"].write_bytes(request_bytes(grant))
    elif mutation == "wrong-signer":
        sign(request_bytes(request), files["signature"], crypto, "admin")
    elif mutation == "untrusted-admin":
        authority["policy"]["admin_certificate_sha256"] = ["0" * 64]
    elif mutation == "revoked-mandate":
        authority["policy"]["revoked_mandate_ids"] = ["fictional-mandate"]
    elif mutation == "revoked-certificate":
        authority["policy"]["revoked_certificate_sha256"] = [
            crypto["certs"]["reviewer"].fingerprint(hashes.SHA256()).hex()
        ]
    elif mutation == "crl-revoked":
        authority["crls"] = crypto["revoked"]
    elif mutation == "expired":
        request["expires_at"] = AT.isoformat()
    elif mutation == "future":
        request["created_at"] = (AT + timedelta(hours=1)).isoformat()
    elif mutation == "overlong":
        request["expires_at"] = (AT + timedelta(hours=25)).isoformat()
    elif mutation == "real-policy":
        authority["policy"]["data_origin"] = "REAL"
    elif mutation == "provider-changed":
        request["bindings"]["crypto_provider_hash"] = "0" * 64
    elif mutation == "wrong-scope":
        request["scope"]["quarter"] = 3
    with pytest.raises(ContractError, match=message):
        verify_approval(request, at=AT, **files, **authority)


def test_artifact_change_during_signature_verification_rejects_approval(
    tmp_path, crypto, monkeypatch
):
    case, front, draft, packet, _, files = signed_packet(tmp_path, crypto)
    verify = lipe_approval.verify_approval

    def altered(*args, **kwargs):
        proof = verify(*args, **kwargs)
        (draft / "workpaper.md").write_text(
            "Replaced during verification", encoding="utf-8"
        )
        return proof

    monkeypatch.setattr(lipe_approval, "verify_approval", altered)
    with pytest.raises(ContractError, match="changed during verification"):
        accept_review(
            case,
            front,
            draft,
            tmp_path,
            packet / "request.json",
            tmp_path / "rejected",
            at=AT,
            authority=crypto["authority"],
            **files,
        )
    assert not (tmp_path / "rejected").exists()


def test_review_packet_cannot_modify_the_draft_it_binds(tmp_path):
    case, front, draft = example(tmp_path)
    with pytest.raises(ContractError, match="separate from the draft"):
        prepare_review(case, front, draft, tmp_path, draft / "packet", at=AT)
    assert not (draft / "packet").exists()


def test_preparation_has_no_approval_and_does_not_overwrite_packet(tmp_path):
    case, front, draft = example(tmp_path)
    packet = prepare_review(case, front, draft, tmp_path, tmp_path / "packet", at=AT)
    before = (packet / "request.json").read_bytes()
    with pytest.raises(FileExistsError):
        prepare_review(case, front, draft, tmp_path, packet, at=AT)
    assert (packet / "request.json").read_bytes() == before
    assert not (packet / "approval.json").exists()


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b"[]", b"\xff"])
def test_signed_json_rejects_ambiguous_or_malformed_content(tmp_path, raw):
    path = tmp_path / "signed.json"
    path.write_bytes(raw)
    with pytest.raises(ContractError):
        read_signed_json(path)


def test_case_cannot_supply_its_own_firm_authority_config(tmp_path, monkeypatch):
    path = tmp_path / "authority.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("VERA_LIPE_AUTHORITY_CONFIG", str(path))
    with pytest.raises(ContractError, match="outside client runs"):
        load_authority(excluded_roots=[tmp_path])


@pytest.mark.parametrize(
    "mutation,message",
    [
        ("artifact", "stale"),
        ("frontpage", "stale"),
        ("case", "Recalculation differs"),
        ("source", "Source changed"),
        ("request-bytes", "canonical request"),
        ("missing-artifact", "missing review artifacts"),
        ("extra-field", "authorization"),
    ],
)
def test_acceptance_rejects_changes_to_the_exact_reviewed_version(
    tmp_path, crypto, mutation, message
):
    case, front, draft, packet, _, files = signed_packet(tmp_path, crypto)
    if mutation == "artifact":
        (draft / "summary.pdf").write_bytes(b"Replacement report")
    elif mutation == "frontpage":
        front["review"]["reason"] = "Different scope of review"
    elif mutation == "case":
        case["scope_review"]["reason"] = "Different scope of review"
    elif mutation == "source":
        (tmp_path / "front-source.txt").write_text("Changed evidence", encoding="utf-8")
    elif mutation == "request-bytes":
        with (packet / "request.json").open("ab") as handle:
            handle.write(b" ")
    elif mutation == "missing-artifact":
        (draft / "summary.pdf").unlink()
    elif mutation == "extra-field":
        request = read_json(packet / "request.json")
        request["approved"] = True
        (packet / "request.json").write_bytes(request_bytes(request))
    with pytest.raises(ContractError, match=message):
        accept_review(
            case,
            front,
            draft,
            tmp_path,
            packet / "request.json",
            tmp_path / "rejected",
            at=AT,
            authority=crypto["authority"],
            **files,
        )
    assert not (tmp_path / "rejected").exists()


def test_approval_rechecks_original_signature_bytes_after_verification(
    tmp_path, crypto, monkeypatch
):
    case, front, draft, packet, _, files = signed_packet(tmp_path, crypto)
    verify = lipe_approval.verify_approval

    def altered(*args, **kwargs):
        proof = verify(*args, **kwargs)
        files["signature"].write_bytes(b"Replaced signature")
        return proof

    monkeypatch.setattr(lipe_approval, "verify_approval", altered)
    with pytest.raises(ContractError, match="evidence changed during"):
        accept_review(
            case,
            front,
            draft,
            tmp_path,
            packet / "request.json",
            tmp_path / "rejected",
            at=AT,
            authority=crypto["authority"],
            **files,
        )
    assert not (tmp_path / "rejected").exists()


def test_italian_year_boundary_controls_the_allowed_submission_window(tmp_path):
    case, front, _ = example(tmp_path)
    case["tax_year"] = front["fields"]["AnnoImposta"] = 2025
    front = frontpage(case, tmp_path)
    draft = save_result(case, calculate(case, tmp_path), tmp_path / "historical")
    # It is already 1 January 2027 in Italy, although still 31 December in UTC.
    with pytest.raises(ContractError, match="submission window"):
        current_bindings(
            case,
            front,
            draft,
            tmp_path,
            at=datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc),
        )


def test_non_natural_taxpayer_with_declarant_is_supported(tmp_path):
    case = read_json(PLUGIN / "examples/synthetic-case.json")
    front = frontpage(
        case,
        tmp_path,
        CodiceFiscale="12345678903",
        CFDichiarante="RSSMRA80A01H501U",
        CodiceCaricaDichiarante="1",
    )
    front["taxpayer_kind"] = "OTHER"
    result = validate_frontpage(front, case, tmp_path, on_date=AT.date())
    assert result["fields"]["CFDichiarante"] == "RSSMRA80A01H501U"


def load_test_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def disclosure(output: Path, run_id: str) -> Path:
    module = load_test_module(
        PLUGIN.parent / "vera/scripts/model_data_report.py", "lipe_report_fixture"
    )
    payload = {
        "schema_version": 1,
        "workflow_id": "lipe",
        "run_id": run_id,
        "runtime_profile": "openai-codex",
        "language": "it",
        "created_at": AT.isoformat(),
        "professional_purpose": "Synthetic automated validation only.",
        "phases": [
            {
                "phase_id": "calculation",
                "purpose": "Run synthetic local checks.",
                "outcome": "no_case_data",
                "evidence_basis": "workflow_receipt",
                "source_extent": [],
                "locally_processed": [],
                "model_visible": [],
                "remained_local": [],
                "reason": "No model is invoked by this automated fixture.",
                "evidence_files": [],
            }
        ],
        "improvement_assessment": {"status": "not_assessed", "candidates": []},
    }
    report, markdown = module.build_model_data_report(payload, evidence_root=output)
    path = output / "model_data_report.json"
    path.write_bytes(request_bytes(report))
    path.with_suffix(".md").write_text(markdown, encoding="utf-8")
    return path


def archive_example(tmp_path):
    """Exercise the REAL route with a real Archive ledger and fictional documents."""
    ledger = load_test_module(
        PLUGIN.parent / "studio-archive/scripts/client_ledger.py",
        "lipe_approval_archive_fixture",
    )
    customer = tmp_path / "Customer"
    customer.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(customer, client_id)
    engagement = ledger.create_engagement(
        customer, client_id, "Synthetic approval acceptance"
    )
    engagement_id = engagement["engagement_id"]
    case = read_json(PLUGIN / "examples/synthetic-case.json")
    case.update(data_origin="REAL", client_id=client_id, engagement_id=engagement_id)
    front = frontpage(case, tmp_path)
    inputs = []
    for obj, original in [
        (case, PLUGIN / "examples/synthetic-registers.txt"),
        (front, tmp_path / "front-source.txt"),
    ]:
        imported = ledger.import_document(
            customer, client_id, engagement_id, original, "source"
        )["receipt"]
        inputs.append(imported["input_id"])
        obj["sources"][0][
            "path"
        ] = f"imports/{imported['input_id']}/{Path(imported['relative_path']).name}"
    for name, obj in [("case", case), ("frontpage", front)]:
        path = tmp_path / (name + ".json")
        path.write_bytes(request_bytes(obj))
        imported = ledger.import_document(
            customer, client_id, engagement_id, path, "source"
        )["receipt"]
        inputs.append(imported["input_id"])
    prepared = ledger.prepare_run(
        customer, client_id, engagement_id, "lipe", "0.1.0", input_ids=inputs
    )
    running = ledger.start_run(customer, engagement_id, prepared["run"]["run_id"])
    context = running["context"]
    paths = {
        Path(item["path"]).name: Path(item["path"])
        for item in context["input_bindings"]
    }
    root, output = Path(context["run_root"]) / "inputs", Path(running["output_dir"])
    draft = save_result(case, calculate(case, root), output)
    report = disclosure(output, context["run_id"])
    return (
        case,
        front,
        draft,
        root,
        output,
        Path(running["context_path"]),
        paths,
        report,
    )


def test_real_cli_prepares_run_bound_review_with_actual_archive_receipts(tmp_path):
    _, _, draft, _, output, context, paths, _ = archive_example(tmp_path)
    status = main(
        [
            "prepare",
            "--case",
            str(paths["case.json"]),
            "--frontpage",
            str(paths["frontpage.json"]),
            "--draft",
            str(draft),
            "--client-engagement",
            str(context),
            "--output",
            str(output / "review"),
        ]
    )
    assert status == 0
    snapshot = read_json(output / "review/review-snapshot.json")
    assert "run/model_data_report.json" in snapshot["artifacts"]
    assert not (output / "review/approval.json").exists()


@pytest.mark.parametrize(
    "changed,message",
    [
        ("missing", "requires the selected run"),
        ("run", "different workflow run"),
        ("markdown", "readable disclosure"),
        ("json", "input hash"),
    ],
)
def test_real_review_rejects_missing_or_mismatched_disclosure(
    tmp_path, changed, message
):
    case, front, draft, root, _, context, _, report = archive_example(tmp_path)
    run_id = read_json(context)["run_id"]
    if changed == "missing":
        report = None
    elif changed == "run":
        run_id = "run_different"
    elif changed == "markdown":
        report.with_suffix(".md").write_text("Different report", encoding="utf-8")
    elif changed == "json":
        document = read_json(report)
        document["professional_purpose"] = "Different purpose"
        report.write_bytes(request_bytes(document))
    with pytest.raises(ContractError, match=message):
        prepare_review(
            case,
            front,
            draft,
            root,
            tmp_path / "rejected",
            at=AT,
            model_data_report=report,
            run_id=run_id,
        )
    assert not (tmp_path / "rejected").exists()


def test_real_cli_rejects_unreceipted_frontpage_before_writing(tmp_path):
    _, _, draft, _, output, context, paths, _ = archive_example(tmp_path)
    path = tmp_path / "external-front.json"
    shutil.copy(paths["frontpage.json"], path)
    with pytest.raises(ContractError, match="escapes archive inputs"):
        main(
            [
                "prepare",
                "--case",
                str(paths["case.json"]),
                "--frontpage",
                str(path),
                "--draft",
                str(draft),
                "--client-engagement",
                str(context),
                "--output",
                str(output / "rejected"),
            ]
        )
    assert not (output / "rejected").exists()


def test_real_cli_rejects_external_output_before_writing(tmp_path):
    _, _, draft, _, _, context, paths, _ = archive_example(tmp_path)
    with pytest.raises(ContractError, match="selected Archive output"):
        main(
            [
                "prepare",
                "--case",
                str(paths["case.json"]),
                "--frontpage",
                str(paths["frontpage.json"]),
                "--draft",
                str(draft),
                "--client-engagement",
                str(context),
                "--output",
                str(tmp_path / "external-output"),
            ]
        )
    assert not (tmp_path / "external-output").exists()


def test_accept_cli_uses_independent_host_authority_config(
    tmp_path, crypto, monkeypatch
):
    root = tmp_path / "case"
    root.mkdir()
    case, front, draft, packet, _, files = signed_packet(root, crypto)
    case_path, front_path = root / "case.json", root / "front.json"
    case_path.write_bytes(request_bytes(case))
    front_path.write_bytes(request_bytes(front))
    config = tmp_path / "host-authority.json"
    config.write_bytes(
        request_bytes(
            {
                name: str(value) if isinstance(value, Path) else value
                for name, value in crypto["authority"].items()
            }
        )
    )
    monkeypatch.setenv("VERA_LIPE_AUTHORITY_CONFIG", str(config))

    # Fix the clock at the signed request's actual validation time.
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return AT

    monkeypatch.setattr(lipe_approval, "datetime", Clock)
    status = main(
        [
            "accept",
            "--case",
            str(case_path),
            "--frontpage",
            str(front_path),
            "--draft",
            str(draft),
            "--source-root",
            str(root),
            "--request",
            str(packet / "request.json"),
            "--signature",
            str(files["signature"]),
            "--mandate",
            str(files["mandate"]),
            "--mandate-signature",
            str(files["mandate_signature"]),
            "--output",
            str(root / "accepted"),
        ]
    )
    assert status == 0
    assert (
        read_json(root / "accepted/approval.json")["reviewer_name"]
        == "FICTIONAL REVIEWER"
    )


def test_authority_must_match_the_case_catalog_studio(tmp_path, crypto):
    from lipe_catalog import create_catalog

    case, front, _ = example(tmp_path)
    catalog = tmp_path / "catalog.sqlite3"
    created = create_catalog(catalog, "different-studio", "0.80")
    case["catalog_context"] = {
        "catalog_id": created["catalog_id"],
        "studio_id": created["studio_id"],
    }
    draft = save_result(
        case, calculate(case, tmp_path, catalog), tmp_path / "catalog-draft"
    )
    packet = prepare_review(
        case, front, draft, tmp_path, tmp_path / "review", at=AT, catalog_path=catalog
    )
    with pytest.raises(ContractError, match="selected studio catalog"):
        accept_review(
            case,
            front,
            draft,
            tmp_path,
            packet / "request.json",
            tmp_path / "rejected",
            at=AT,
            catalog_path=catalog,
            authority=crypto["authority"],
            signature=tmp_path / "unused",
            mandate=tmp_path / "unused",
            mandate_signature=tmp_path / "unused",
        )
    assert not (tmp_path / "rejected").exists()
