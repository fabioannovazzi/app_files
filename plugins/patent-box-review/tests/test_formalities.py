"""Actual OpenSSL checks using isolated synthetic certificates, not trust claims."""

from __future__ import annotations

import io
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from patent_box.contracts import ContractError
from patent_box.formalities import (
    compare_deadline,
    verify_cms,
    verify_pdf,
    verify_timestamp,
)
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

AT = datetime(2030, 1, 1, tzinfo=timezone.utc)
BEFORE = datetime(2025, 1, 1, tzinfo=timezone.utc)
AFTER = datetime(2035, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def openssl_failure_diagnostics(monkeypatch):
    """Retain synthetic provider errors so platform failures are actionable."""
    original = subprocess.run

    def run(*args, **kwargs):
        result = original(*args, **kwargs)
        command = args[0] if args else kwargs.get("args", [])
        if result.returncode and command and "openssl" in str(command[0]):
            logging.getLogger(__name__).warning(
                "Synthetic OpenSSL diagnostic: %s %s", result.stdout, result.stderr
            )
        return result

    monkeypatch.setattr(subprocess, "run", run)


def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def certificate(subject, public_key, issuer, issuer_key, *, ca=False, tsa=False):
    usage = x509.KeyUsage(not ca, not ca, False, False, False, ca, ca, False, False)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(BEFORE)
        .not_valid_after(AFTER)
        .add_extension(
            x509.BasicConstraints(ca=ca, path_length=1 if ca else None), critical=True
        )
        .add_extension(usage, critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),
            critical=False,
        )
    )
    if not ca:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage(
                [
                    (
                        ExtendedKeyUsageOID.TIME_STAMPING
                        if tsa
                        else ExtendedKeyUsageOID.EMAIL_PROTECTION
                    )
                ]
            ),
            critical=tsa,
        )
    return builder.sign(issuer_key, hashes.SHA256())


def crl(root_cert, root_key, revoked=None):
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(root_cert.subject)
        .last_update(BEFORE)
        .next_update(AFTER)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
            critical=False,
        )
        .add_extension(x509.CRLNumber(1), critical=False)
    )
    if revoked:
        builder = builder.add_revoked_certificate(
            x509.RevokedCertificateBuilder()
            .serial_number(revoked.serial_number)
            .revocation_date(BEFORE)
            .build()
        )
    return builder.sign(root_key, hashes.SHA256()).public_bytes(
        serialization.Encoding.PEM
    )


def write(path, raw):
    path.write_bytes(raw)
    return path


@pytest.fixture(scope="module")
def authority(tmp_path_factory):
    root = tmp_path_factory.mktemp("formalities")
    executable = shutil.which("openssl")
    if not executable or not subprocess.run(
        [executable, "version"], capture_output=True, check=True
    ).stdout.startswith(b"OpenSSL 3."):
        pytest.skip("Integration requires an installed OpenSSL 3 executable")
    root_key, signer_key, tsa_key = key(), key(), key()
    root_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "SYNTHETIC TEST ROOT")]
    )
    root_cert = certificate(
        root_name, root_key.public_key(), root_name, root_key, ca=True
    )
    signer = certificate(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SYNTHETIC SIGNER")]),
        signer_key.public_key(),
        root_name,
        root_key,
    )
    tsa = certificate(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SYNTHETIC TSA")]),
        tsa_key.public_key(),
        root_name,
        root_key,
        tsa=True,
    )
    pem = serialization.Encoding.PEM
    ca = write(root / "root.pem", root_cert.public_bytes(pem))
    signer_path = write(root / "signer.pem", signer.public_bytes(pem))
    tsa_path = write(root / "tsa.pem", tsa.public_bytes(pem))
    tsa_secret = write(
        root / "tsa-key.pem",
        tsa_key.private_bytes(
            pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ),
    )
    document = write(
        root / "document.bin", b"Synthetic dossier\r\nExact original bytes.\n"
    )
    builder = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(document.read_bytes())
        .add_signer(signer, signer_key, hashes.SHA256())
        .add_certificate(root_cert)
    )
    signature = write(
        root / "signature.der",
        builder.sign(
            serialization.Encoding.DER,
            [pkcs7.PKCS7Options.Binary, pkcs7.PKCS7Options.DetachedSignature],
        ),
    )
    attached = write(
        root / "attached.der",
        builder.sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary]),
    )
    valid_crl = write(root / "valid.crl", crl(root_cert, root_key))
    revoked_crl = write(root / "revoked.crl", crl(root_cert, root_key, signer))
    revoked_tsa = write(root / "revoked-tsa.crl", crl(root_cert, root_key, tsa))
    config = root / "tsa.cnf"
    config.write_text(
        f"""[tsa]
default_tsa = tsa_config
[tsa_config]
serial = {root / 'serial'}
crypto_device = builtin
signer_cert = {tsa_path}
certs = {ca}
signer_key = {tsa_secret}
signer_digest = sha256
default_policy = 1.2.3.4.1
digests = sha256,sha384,sha512
accuracy = secs:1
ordering = yes
tsa_name = yes
ess_cert_id_chain = no
ess_cert_id_alg = sha256
"""
    )
    (root / "serial").write_text("01")
    request, response, token = (
        root / "request.tsq",
        root / "response.tsr",
        root / "token.der",
    )
    for args in (
        [
            "ts",
            "-query",
            "-data",
            str(signature),
            "-sha256",
            "-cert",
            "-out",
            str(request),
        ],
        [
            "ts",
            "-reply",
            "-config",
            str(config),
            "-queryfile",
            str(request),
            "-out",
            str(response),
        ],
        ["ts", "-reply", "-in", str(response), "-token_out", "-out", str(token)],
    ):
        subprocess.run([executable, *args], capture_output=True, timeout=15, check=True)
    return dict(
        openssl=Path(executable),
        signer_key=signer_key,
        signer_cert=signer,
        root_cert=root_cert,
        root_key=root_key,
        document=document,
        signature=signature,
        attached=attached,
        ca=ca,
        signer=signer_path,
        crl=valid_crl,
        revoked=revoked_crl,
        revoked_tsa=revoked_tsa,
        response=response,
        token=token,
    )


def test_cms_verifies_exact_content_chain_and_crl_without_asserting_powers(authority):
    a = authority
    result = verify_cms(
        a["signature"],
        a["document"],
        openssl=a["openssl"],
        at=AT,
        trusted_roots=a["ca"],
        crls=a["crl"],
    )
    assert result["signature_integrity"]["status"] == "PASS"
    assert result["document_binding"]["status"] == "PASS"
    assert result["certificate_chain"]["status"] == "PASS"
    assert result["revocation"]["status"] == "PASS"
    assert result["signers"][0]["key_usage"] == "PASS"
    assert result["signer_powers"]["status"] == "NOT_TESTED"
    assert result["qualified_status"]["status"] == "NOT_TESTED"
    assert result["professional_acceptance"] is False


def test_attached_cms_requires_the_same_selected_document(authority, tmp_path):
    a = authority
    wrong = write(tmp_path / "wrong.txt", b"Different dossier")
    result = verify_cms(
        a["attached"], wrong, openssl=a["openssl"], at=AT, detached=False
    )
    assert result["signature_integrity"]["status"] == "PASS"
    assert result["document_binding"]["status"] == "FAIL"


def test_cms_without_roots_does_not_claim_trust_or_revocation(authority):
    a = authority
    result = verify_cms(
        a["attached"], a["document"], openssl=a["openssl"], at=AT, detached=False
    )
    assert result["document_binding"]["status"] == "PASS"
    assert result["certificate_chain"]["status"] == "NOT_TESTED"
    assert result["revocation"]["status"] == "NOT_TESTED"


def test_cms_detects_tampered_detached_content(authority, tmp_path):
    a = authority
    wrong = write(tmp_path / "tampered.txt", b"Modified dossier")
    result = verify_cms(a["signature"], wrong, openssl=a["openssl"], at=AT)
    assert result["signature_integrity"]["status"] == "FAIL"
    assert result["document_binding"]["status"] == "BLOCKED"


def test_cms_revoked_certificate_keeps_integrity_separate(authority):
    a = authority
    result = verify_cms(
        a["signature"],
        a["document"],
        openssl=a["openssl"],
        at=AT,
        trusted_roots=a["ca"],
        crls=a["revoked"],
    )
    assert result["signature_integrity"]["status"] == "PASS"
    assert result["certificate_chain"]["status"] == "PASS"
    assert result["revocation"]["status"] == "FAIL"


def test_cms_expired_chain_cannot_pass(authority):
    a = authority
    result = verify_cms(
        a["signature"],
        a["document"],
        openssl=a["openssl"],
        at=datetime(2040, 1, 1, tzinfo=timezone.utc),
        trusted_roots=a["ca"],
    )
    assert result["certificate_chain"]["status"] == "FAIL"


@pytest.mark.parametrize("token", [False, True])
def test_rfc3161_verifies_exact_signature_container_and_time(authority, token):
    a = authority
    result = verify_timestamp(
        a["token" if token else "response"],
        a["signature"],
        openssl=a["openssl"],
        at=AT,
        trusted_roots=a["ca"],
        crls=a["crl"],
        token=token,
    )
    assert result["timestamp_integrity_and_trust"]["status"] == "PASS"
    assert result["revocation"]["status"] == "PASS"
    assert BEFORE < datetime.fromisoformat(result["timestamp_time"]) < AT
    assert result["qualified_status"]["status"] == "NOT_TESTED"


def test_rfc3161_rejects_timestamp_for_different_bytes(authority):
    a = authority
    result = verify_timestamp(
        a["response"], a["document"], openssl=a["openssl"], at=AT, trusted_roots=a["ca"]
    )
    assert result["timestamp_integrity_and_trust"]["status"] == "FAIL"
    assert result["timestamp_time"] is None


def test_rfc3161_revoked_tsa_has_separate_failed_revocation(authority):
    a = authority
    result = verify_timestamp(
        a["response"],
        a["signature"],
        openssl=a["openssl"],
        at=AT,
        trusted_roots=a["ca"],
        crls=a["revoked_tsa"],
    )
    assert result["timestamp_integrity_and_trust"]["status"] == "PASS"
    assert result["revocation"]["status"] == "FAIL"


@pytest.mark.parametrize(("deadline", "expected"), [(BEFORE, "FAIL"), (AT, "PASS")])
def test_deadline_uses_reviewed_cutoff_and_preserves_source_rationale(
    authority, deadline, expected
):
    a = authority
    stamp = verify_timestamp(
        a["response"],
        a["signature"],
        openssl=a["openssl"],
        at=AT,
        trusted_roots=a["ca"],
    )
    result = compare_deadline(
        stamp,
        deadline=deadline,
        source_ids=["SOURCE.TEST"],
        rationale="Synthetic reviewed cutoff",
    )
    assert result["status"] == expected
    assert result["source_ids"] == ["SOURCE.TEST"]


def test_deadline_rejects_changed_verification(authority):
    a = authority
    stamp = verify_timestamp(
        a["response"],
        a["signature"],
        openssl=a["openssl"],
        at=AT,
        trusted_roots=a["ca"],
    )
    stamp["timestamp_time"] = BEFORE.isoformat()
    with pytest.raises(ContractError, match="record changed"):
        compare_deadline(
            stamp, deadline=AT, source_ids=["SOURCE.TEST"], rationale="Reviewed"
        )


def test_deadline_rejects_missing_legal_basis(authority):
    a = authority
    stamp = verify_timestamp(
        a["response"],
        a["signature"],
        openssl=a["openssl"],
        at=AT,
        trusted_roots=a["ca"],
    )
    with pytest.raises(ContractError, match="reviewed sources"):
        compare_deadline(stamp, deadline=AT, source_ids=[], rationale="")


def test_invalid_cms_is_a_failed_verification(authority, tmp_path):
    a = authority
    invalid = write(tmp_path / "invalid.der", b"not a CMS object")
    result = verify_cms(invalid, a["document"], openssl=a["openssl"], at=AT)
    assert result["signature_integrity"]["status"] == "FAIL"


def test_missing_provider_does_not_fall_back_to_a_hash(authority):
    a = authority
    with pytest.raises(ContractError, match="absolute installed"):
        verify_cms(a["signature"], a["document"], openssl=Path("openssl"), at=AT)


def signed_pdf(authority, path):
    """Produce a real detached PDF signature over a fixed byte-range placeholder."""
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    placeholder = b"a" * 8192
    signature = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Sig"),
            NameObject("/Filter"): NameObject("/Adobe.PPKLite"),
            NameObject("/SubFilter"): NameObject("/adbe.pkcs7.detached"),
            NameObject("/Contents"): ByteStringObject(placeholder),
            NameObject("/ByteRange"): ArrayObject([NumberObject(1111111111)] * 4),
        }
    )
    field = DictionaryObject(
        {
            NameObject("/FT"): NameObject("/Sig"),
            NameObject("/T"): TextStringObject("TestSignature"),
            NameObject("/V"): writer._add_object(signature),
        }
    )
    form = DictionaryObject(
        {NameObject("/Fields"): ArrayObject([writer._add_object(field)])}
    )
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(form)
    stream = io.BytesIO()
    writer.write(stream)
    raw = stream.getvalue()
    gap = b"<" + placeholder.hex().encode() + b">"
    begin = raw.index(gap)
    end = begin + len(gap)
    ranges = (
        b"["
        + b" ".join(str(v).encode() for v in (0, begin, end, len(raw) - end))
        + b"]"
    )
    match = re.search(rb"\[ 1111111111 1111111111 1111111111 1111111111 \]", raw)
    assert match is not None
    raw = raw[: match.start()] + ranges.ljust(len(match.group())) + raw[match.end() :]
    signed = raw[:begin] + raw[end:]
    cms = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(signed)
        .add_signer(authority["signer_cert"], authority["signer_key"], hashes.SHA256())
        .add_certificate(authority["root_cert"])
        .sign(
            serialization.Encoding.DER,
            [pkcs7.PKCS7Options.Binary, pkcs7.PKCS7Options.DetachedSignature],
        )
    )
    encoded = cms.hex().encode().ljust(len(gap) - 2, b"0")
    return write(path, raw[:begin] + b"<" + encoded + b">" + raw[end:])


def test_pdf_checks_signed_byte_ranges_and_current_document(authority, tmp_path):
    pdf = signed_pdf(authority, tmp_path / "signed.pdf")
    result = verify_pdf(
        pdf,
        openssl=authority["openssl"],
        at=AT,
        trusted_roots=authority["ca"],
        crls=authority["crl"],
    )
    assert result["document_binding"]["status"] == "PASS"
    assert result["signatures"][0]["signature_integrity"]["status"] == "PASS"
    assert result["signatures"][0]["certificate_chain"]["status"] == "PASS"
    assert result["signatures"][0]["revocation"]["status"] == "PASS"


def test_pdf_appended_bytes_preserve_old_signature_but_block_current_acceptance(
    authority, tmp_path
):
    pdf = signed_pdf(authority, tmp_path / "appended.pdf")
    pdf.write_bytes(pdf.read_bytes() + b"\n% unsigned later data\n")
    result = verify_pdf(pdf, openssl=authority["openssl"], at=AT)
    assert result["signatures"][0]["signature_integrity"]["status"] == "PASS"
    assert result["signatures"][0]["covers_current_document"] is False
    assert result["document_binding"]["status"] == "BLOCKED"


def test_pdf_changed_signed_content_fails_even_when_signature_is_visible(
    authority, tmp_path
):
    pdf = signed_pdf(authority, tmp_path / "altered.pdf")
    pdf.write_bytes(pdf.read_bytes().replace(b"TestSignature", b"FakeSignature"))
    result = verify_pdf(pdf, openssl=authority["openssl"], at=AT)
    assert result["signatures"][0]["signature_integrity"]["status"] == "FAIL"
    assert result["document_binding"]["status"] == "BLOCKED"


def test_pdf_unsigned_document_is_not_tested(authority, tmp_path):
    pdf = tmp_path / "unsigned.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(pdf)
    result = verify_pdf(pdf, openssl=authority["openssl"], at=AT)
    assert result["document_binding"]["status"] == "NOT_TESTED"
    assert result["signatures"] == []


def test_pdf_malicious_byte_range_cannot_exclude_another_region(authority, tmp_path):
    pdf = signed_pdf(authority, tmp_path / "bad-range.pdf")
    pdf.write_bytes(pdf.read_bytes().replace(b"/ByteRange [0 ", b"/ByteRange [1 "))
    with pytest.raises(ContractError, match="excludes required"):
        verify_pdf(pdf, openssl=authority["openssl"], at=AT)


def test_weak_cms_digest_is_distinct_from_mathematical_integrity(authority, tmp_path):
    a = authority
    secret = write(
        tmp_path / "test-key.pem",
        a["signer_key"].private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    weak = tmp_path / "weak.der"
    subprocess.run(
        [
            str(a["openssl"]),
            "cms",
            "-sign",
            "-binary",
            "-in",
            str(a["document"]),
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
    result = verify_cms(
        weak,
        a["document"],
        openssl=a["openssl"],
        at=AT,
        trusted_roots=a["ca"],
        crls=a["crl"],
    )
    assert result["signature_integrity"]["status"] == "PASS"
    assert result["signature_algorithm_policy"]["status"] == "BLOCKED"
    assert result["message_digest_oids"] == ["1.3.14.3.2.26"]
