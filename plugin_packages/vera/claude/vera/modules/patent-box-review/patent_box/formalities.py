"""Local cryptographic evidence, separate from professional or legal acceptance.

OpenSSL verifies signatures and chains; fixed byte bindings prevent substituting
another document. Neither certificate subjects nor valid signatures establish a
mandate, qualified status, a filing deadline or fiscal eligibility.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .contracts import ContractError, canonical_hash

__all__ = ["verify_cms", "verify_pdf", "verify_timestamp", "compare_deadline"]

MAX_BYTES = 16 * 1024 * 1024


def _read(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ContractError("Formalities require bounded regular files")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_BYTES:
        raise ContractError("Formalities file is empty or too large")
    return raw


def _time(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ContractError("Verification time requires a timezone")
    return value.astimezone(timezone.utc)


class _OpenSSL:
    """Run a host-selected executable, never a command supplied by client files."""

    def __init__(self, executable: Path, root: Path) -> None:
        if not executable.is_absolute() or not executable.resolve().is_file():
            raise ContractError("Configure an absolute installed OpenSSL 3 executable")
        self.executable = executable.resolve()
        self.root = root
        self.commands: list[dict[str, Any]] = []
        self.env = {
            key: os.environ[key]
            for key in ("SYSTEMROOT", "WINDIR")
            if key in os.environ
        }
        # Do not load user/provider configurations or inherited dynamic loaders.
        config = root / "openssl-empty.cnf"
        config.write_text("", encoding="ascii")
        self.env.update(OPENSSL_CONF=str(config), LC_ALL="C", LANG="C")
        code, version = self.run(["version"])
        if code or not re.match(r"OpenSSL 3\.[0-9]+\.[0-9]+\b", version):
            raise ContractError("Formalities require OpenSSL 3")
        self.version = version.strip()

    def run(self, arguments: list[str], *, text_limit: int = 32768) -> tuple[int, str]:
        try:
            proc = subprocess.run(  # no shell; fixed verbs/flags and private paths
                [str(self.executable), *arguments],
                cwd=self.root,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ContractError(
                "Local cryptographic provider unavailable or timed out"
            ) from exc
        output = proc.stdout.decode("utf-8", errors="replace")
        self.commands.append(
            {
                "arguments": arguments,
                "exit_code": proc.returncode,
                "output_sha256": hashlib.sha256(proc.stdout).hexdigest(),
            }
        )
        return proc.returncode, output[:text_limit]


def _write(root: Path, name: str, raw: bytes) -> str:
    path = root / name
    path.write_bytes(raw)
    path.chmod(0o600)
    return str(path)


def _outcome(status: str, detail: str) -> dict[str, str]:
    return {"status": status, "detail": detail}


def _binding(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _base(provider: _OpenSSL, at: datetime, inputs: dict[str, bytes]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "provider": provider.version,
        "validated_at": _time(at).isoformat(),
        "input_sha256": {key: _binding(raw) for key, raw in inputs.items()},
        "qualified_status": _outcome(
            "NOT_TESTED", "No trusted-list or qualified-provider assessment"
        ),
        "signer_powers": _outcome(
            "NOT_TESTED",
            "Mandate and powers require separate evidence and professional review",
        ),
        "retention": _outcome(
            "NOT_TESTED",
            "Local evidence retention does not prove statutory conservation",
        ),
        "professional_acceptance": False,
    }


def _seal(result: dict[str, Any], provider: _OpenSSL) -> dict[str, Any]:
    # Private temporary paths are not durable evidence and must not leak into output.
    result["provider_operations"] = [
        {
            **row,
            "arguments": [
                item.replace(str(provider.root), "<private-verification>")
                for item in row["arguments"]
            ],
        }
        for row in provider.commands
    ]
    result["verification_digest"] = canonical_hash(result)
    return result


def _verification_flags(at: datetime) -> list[str]:
    return [
        "-no-CAfile",
        "-no-CApath",
        "-no-CAstore",
        "-attime",
        str(int(_time(at).timestamp())),
        "-auth_level",
        "2",
        "-x509_strict",
    ]


def verify_cms(
    signature: Path,
    document: Path,
    *,
    openssl: Path,
    at: datetime,
    trusted_roots: Path | None = None,
    crls: Path | None = None,
    detached: bool = True,
) -> dict[str, Any]:
    """Check DER CMS and the exact expected document; no network or signing.

    Revocation requires supplied current CRLs for the complete chain. Absence of
    trust/revocation evidence is NOT_TESTED, never an implicit PASS.
    """
    inputs = {"signature": _read(signature), "document": _read(document)}
    if trusted_roots is not None:
        inputs["trusted_roots"] = _read(trusted_roots)
    if crls is not None:
        inputs["crls"] = _read(crls)
    with tempfile.TemporaryDirectory(prefix="patent-box-verify-") as directory:
        root = Path(directory)
        provider = _OpenSSL(openssl, root)
        result = _base(provider, at, inputs)
        result.update(format="CMS_DER", detached=detached, signers=[])
        result["certificate_chain"] = _outcome(
            "NOT_TESTED", "No configured trust roots"
        )
        result["revocation"] = _outcome("NOT_TESTED", "No complete CRL validation")
        cms = _write(root, "signature.der", inputs["signature"])
        data = _write(root, "document.bin", inputs["document"])
        verified, signers = root / "verified.bin", root / "signers.pem"
        args = [
            "cms",
            "-verify",
            "-binary",
            "-inform",
            "DER",
            "-in",
            cms,
            "-noverify",
            "-out",
            str(verified),
            "-signer",
            str(signers),
        ]
        if detached:
            args += ["-content", data]
        code, _ = provider.run(args)
        if code:
            result["signature_integrity"] = _outcome(
                "FAIL", "CMS signature or signed attributes do not verify"
            )
            result["document_binding"] = _outcome("BLOCKED", "No verified content")
            return _seal(result, provider)
        result["signature_integrity"] = _outcome(
            "PASS", "CMS signatures and signed attributes verified"
        )
        result["document_binding"] = _outcome(
            "PASS" if _read(verified) == inputs["document"] else "FAIL",
            "Verified content compared byte-for-byte with the selected document",
        )
        try:
            certificates = x509.load_pem_x509_certificates(_read(signers))
            embedded = pkcs7.load_der_pkcs7_certificates(inputs["signature"])
        except ValueError as exc:
            raise ContractError(
                "Provider returned an unreadable certificate set"
            ) from exc
        if not certificates or len(certificates) > 32 or len(embedded) > 64:
            raise ContractError("Signer certificate population is empty or excessive")
        _, algorithms = provider.run(
            ["cms", "-cmsout", "-print", "-inform", "DER", "-in", cms],
            text_limit=MAX_BYTES * 8,
        )
        digest_oids = re.findall(
            r"^\s+digestAlgorithm:\s*\n\s+algorithm: [^\n]+ \(([0-9.]+)\)",
            algorithms,
            re.MULTILINE,
        )
        result["message_digest_oids"] = digest_oids
        result["signature_algorithm_policy"] = _outcome(
            (
                "PASS"
                if len(digest_oids) == len(certificates)
                and all(
                    oid
                    in {
                        "2.16.840.1.101.3.4.2.1",
                        "2.16.840.1.101.3.4.2.2",
                        "2.16.840.1.101.3.4.2.3",
                    }
                    for oid in digest_oids
                )
                else "BLOCKED"
            ),
            "Approval requires a recognized SHA-256, SHA-384 or SHA-512 message digest for every signer",
        )
        chain_file = _write(
            root,
            "embedded.pem",
            b"".join(
                item.public_bytes(serialization.Encoding.PEM) for item in embedded
            ),
        )
        ca_file = (
            _write(root, "roots.pem", inputs["trusted_roots"])
            if trusted_roots
            else None
        )
        crl_file = _write(root, "crls.pem", inputs["crls"]) if crls else None
        for number, cert in enumerate(certificates):
            cert_file = _write(
                root,
                f"signer-{number}.pem",
                cert.public_bytes(serialization.Encoding.PEM),
            )
            try:
                usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
                key_usage = (
                    "PASS"
                    if usage.digital_signature or usage.content_commitment
                    else "FAIL"
                )
            except x509.ExtensionNotFound:
                key_usage = "NOT_TESTED"
            item = {
                "certificate_sha256": cert.fingerprint(hashes.SHA256()).hex(),
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "serial_number": str(cert.serial_number),
                "key_usage": key_usage,
                "valid_from": cert.not_valid_before_utc.isoformat(),
                "valid_until": cert.not_valid_after_utc.isoformat(),
                "chain": "NOT_TESTED",
                "revocation": "NOT_TESTED",
            }
            if ca_file:
                args = [
                    "verify",
                    *_verification_flags(at),
                    "-CAfile",
                    ca_file,
                    "-purpose",
                    "any",
                    "-untrusted",
                    chain_file,
                ]
                code, _ = provider.run([*args, cert_file])
                item["chain"] = "PASS" if code == 0 else "FAIL"
                if crl_file:
                    code, _ = provider.run(
                        [*args, "-CRLfile", crl_file, "-crl_check_all", cert_file]
                    )
                    item["revocation"] = "PASS" if code == 0 else "FAIL"
            result["signers"].append(item)
        if ca_file:
            result["certificate_chain"] = _outcome(
                (
                    "PASS"
                    if all(item["chain"] == "PASS" for item in result["signers"])
                    else "FAIL"
                ),
                "Chain/time/security checked against the explicit roots; no qualified-status conclusion",
            )
        if crl_file and ca_file:
            result["revocation"] = _outcome(
                (
                    "PASS"
                    if all(item["revocation"] == "PASS" for item in result["signers"])
                    else "FAIL"
                ),
                "Full-chain CRL verification at the stated validation time",
            )
        return _seal(result, provider)


def _der_contents(raw: bytes) -> bytes:
    """Remove only zero padding from a definite-length PDF CMS container."""
    if len(raw) < 2 or raw[0] != 0x30:
        raise ContractError("PDF signature needs a DER CMS sequence")
    width = raw[1] & 0x7F if raw[1] & 0x80 else 0
    if raw[1] == 0x80 or width > 4 or len(raw) < 2 + width:
        raise ContractError("Indefinite or excessive PDF CMS length is unsupported")
    length = int.from_bytes(raw[2 : 2 + width], "big") if width else raw[1]
    end = 2 + width + length
    if end > len(raw) or any(raw[end:]):
        raise ContractError(
            "PDF signature has truncated CMS or nonzero trailing content"
        )
    return raw[:end]


def verify_pdf(
    document: Path,
    *,
    openssl: Path,
    at: datetime,
    trusted_roots: Path | None = None,
    crls: Path | None = None,
) -> dict[str, Any]:
    """Verify detached PDF signatures without trusting visible signature labels.

    Earlier signed revisions retain their cryptographic result, but intervening
    changes are BLOCKED for current-document acceptance. This adapter does not
    implement DocMDP permissions, LT/LTA evidence or qualified-signature status.
    """
    raw = _read(document)
    try:
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted:
            raise ContractError("Encrypted PDF signature inspection is unsupported")
        fields = reader.get_fields() or {}
    except PdfReadError as exc:
        raise ContractError(
            "PDF structure cannot be read for signature verification"
        ) from exc
    if len(fields) > 1000:
        raise ContractError("PDF signature field population exceeds the bound")
    signatures = [
        field["/V"].get_object()
        for field in fields.values()
        if field.get("/FT") == "/Sig" and field.get("/V")
    ]
    if len(signatures) > 32:
        raise ContractError("Too many PDF signatures")
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "format": "PDF_DETACHED_CMS",
        "document_sha256": _binding(raw),
        "validated_at": _time(at).isoformat(),
        "signatures": [],
        "professional_acceptance": False,
        "document_binding": _outcome("NOT_TESTED", "No embedded signature found"),
    }
    with tempfile.TemporaryDirectory(prefix="patent-box-pdf-") as directory:
        root = Path(directory)
        for number, signature in enumerate(signatures):
            if str(signature.get("/SubFilter")) not in (
                "/adbe.pkcs7.detached",
                "/ETSI.CAdES.detached",
            ):
                result["signatures"].append(
                    {
                        "index": number,
                        "status": "BLOCKED",
                        "reason": "Unsupported PDF signature subfilter",
                    }
                )
                continue
            ranges = signature.get("/ByteRange")
            if (
                not isinstance(ranges, list)
                or len(ranges) != 4
                or any(
                    not isinstance(value, int) or isinstance(value, bool)
                    for value in ranges
                )
            ):
                raise ContractError("PDF signature ByteRange is malformed")
            start, first, second, count = map(int, ranges)
            if (
                start != 0
                or first <= 0
                or second <= first
                or count <= 0
                or second + count > len(raw)
            ):
                raise ContractError(
                    "PDF signature ByteRange excludes required document bytes"
                )
            gap = raw[first:second]
            if not re.fullmatch(rb"<[0-9a-fA-F\s]+>", gap):
                raise ContractError(
                    "PDF signature gap must contain only its hexadecimal Contents"
                )
            content_value = signature.get("/Contents")
            contents = (
                content_value
                if isinstance(content_value, bytes)
                else getattr(content_value, "original_bytes", None)
            )
            if contents is None or bytes.fromhex(gap[1:-1].decode("ascii")) != contents:
                raise ContractError(
                    "PDF signature gap differs from the selected signature Contents"
                )
            cms = Path(_write(root, f"signature-{number}.der", _der_contents(contents)))
            signed = Path(
                _write(
                    root,
                    f"signed-{number}.bin",
                    raw[:first] + raw[second : second + count],
                )
            )
            checked = verify_cms(
                cms,
                signed,
                openssl=openssl,
                at=at,
                trusted_roots=trusted_roots,
                crls=crls,
            )
            checked.update(
                index=number,
                byte_range=list(ranges),
                covers_current_document=second + count == len(raw),
            )
            checked["verification_digest"] = canonical_hash(
                {
                    key: value
                    for key, value in checked.items()
                    if key != "verification_digest"
                }
            )
            result["signatures"].append(checked)
    if signatures:
        current = [
            item for item in result["signatures"] if item.get("covers_current_document")
        ]
        if any(
            item["signature_integrity"]["status"] == "PASS"
            and item["document_binding"]["status"] == "PASS"
            for item in current
        ):
            result["document_binding"] = _outcome(
                "PASS",
                "A verified signature covers the complete current PDF except its own Contents",
            )
        else:
            result["document_binding"] = _outcome(
                "BLOCKED",
                "No verified signature covers the current PDF; later revisions require separate change-policy review",
            )
    result["verification_digest"] = canonical_hash(result)
    return result


def verify_timestamp(
    timestamp: Path,
    document: Path,
    *,
    openssl: Path,
    at: datetime,
    trusted_roots: Path,
    intermediates: Path | None = None,
    crls: Path | None = None,
    token: bool = False,
) -> dict[str, Any]:
    """Verify an RFC 3161 response/token against exact bytes and explicit TSA roots.

    Timestamping the CMS container binds the timestamp to that signature. A token
    for the unsigned document alone does not prove when its signature existed.
    """
    inputs = {
        "timestamp": _read(timestamp),
        "document": _read(document),
        "trusted_roots": _read(trusted_roots),
    }
    if intermediates:
        inputs["intermediates"] = _read(intermediates)
    if crls:
        inputs["crls"] = _read(crls)
    with tempfile.TemporaryDirectory(prefix="patent-box-timestamp-") as directory:
        root = Path(directory)
        provider = _OpenSSL(openssl, root)
        result = _base(provider, at, inputs)
        result.update(
            format="RFC3161_TOKEN" if token else "RFC3161_RESPONSE",
            timestamp_time=None,
            revocation=_outcome("NOT_TESTED", "No complete CRL validation"),
        )
        stamp = _write(root, "timestamp.der", inputs["timestamp"])
        data = _write(root, "document.bin", inputs["document"])
        roots = _write(root, "roots.pem", inputs["trusted_roots"])
        # ts lacks no-CApath/store on some OpenSSL 3 releases. Keep the
        # directory empty and bind both file/store loaders to selected roots;
        # OpenSSL 3.0 rejects an empty directory as a store URI.
        empty_ca = root / "empty-ca"
        empty_ca.mkdir()
        provider.env.update(SSL_CERT_DIR=str(empty_ca), SSL_CERT_FILE=roots)
        args = [
            "ts",
            "-verify",
            "-in",
            stamp,
            "-data",
            data,
            "-CAfile",
            roots,
            "-CApath",
            str(empty_ca),
            "-CAstore",
            roots,
            "-attime",
            str(int(_time(at).timestamp())),
            "-auth_level",
            "2",
            "-x509_strict",
        ]
        if token:
            args.append("-token_in")
        if intermediates:
            args += [
                "-untrusted",
                _write(root, "intermediates.pem", inputs["intermediates"]),
            ]
        code, _ = provider.run(args)
        result["timestamp_integrity_and_trust"] = _outcome(
            "PASS" if code == 0 else "FAIL",
            "RFC 3161 imprint, TSA signature, chain and purpose verification",
        )
        if code:
            return _seal(result, provider)
        if crls:
            # OpenSSL's CAfile supports PEM certificate and CRL objects.
            bundle = _write(
                root,
                "roots-with-crls.pem",
                inputs["trusted_roots"] + b"\n" + inputs["crls"],
            )
            revocation_args = list(args)
            revocation_args[revocation_args.index("-CAfile") + 1] = bundle
            code, _ = provider.run([*revocation_args, "-crl_check_all"])
            result["revocation"] = _outcome(
                "PASS" if code == 0 else "FAIL",
                "Full-chain TSA CRL verification at the stated validation time",
            )
        code, metadata = provider.run(
            ["ts", "-reply", "-in", stamp, "-text"] + (["-token_in"] if token else [])
        )
        times = re.findall(r"^Time stamp: (.+)$", metadata, re.MULTILINE)
        if code or len(times) != 1:
            raise ContractError("Verified timestamp time could not be read")
        try:
            fmt = (
                "%b %d %H:%M:%S.%f %Y GMT"
                if "." in times[0]
                else "%b %d %H:%M:%S %Y GMT"
            )
            parsed = datetime.strptime(times[0], fmt).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ContractError("Unsupported timestamp time format") from exc
        result["timestamp_time"] = parsed.isoformat()
        if parsed > _time(at):
            result["timestamp_integrity_and_trust"] = _outcome(
                "FAIL", "Timestamp is later than the validation time"
            )
        return _seal(result, provider)


def compare_deadline(
    verification: dict[str, Any],
    *,
    deadline: datetime,
    source_ids: list[str],
    rationale: str,
) -> dict[str, Any]:
    """Compare a verified time with a separately reviewed deadline, never select law."""
    body = {
        key: value
        for key, value in verification.items()
        if key != "verification_digest"
    }
    if canonical_hash(body) != verification.get("verification_digest"):
        raise ContractError("Timestamp verification record changed")
    if (
        not source_ids
        or not all(isinstance(item, str) and item.strip() for item in source_ids)
        or not rationale.strip()
    ):
        raise ContractError(
            "Deadline needs reviewed sources and case-specific rationale"
        )
    status = verification.get("timestamp_integrity_and_trust", {}).get("status")
    stamp = verification.get("timestamp_time")
    result = {
        "deadline": _time(deadline).isoformat(),
        "source_ids": source_ids,
        "rationale": rationale,
        "verification_digest": verification["verification_digest"],
    }
    if status != "PASS" or stamp is None:
        return {**result, "status": "BLOCKED", "reason": "No verified timestamp time"}
    at = datetime.fromisoformat(stamp)
    return {
        **result,
        "status": "PASS" if at <= _time(deadline) else "FAIL",
        "reason": "Time comparison only; deadline applicability requires professional review",
    }
