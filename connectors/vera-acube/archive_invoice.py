"""Import one provider XML into its exact local Studio Archive engagement."""

from __future__ import annotations

import json
import os
import re
import sys
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

__all__ = ["main"]
ROOT = Path(__file__).resolve().parents[2]


class ImportIssue(ValueError):
    """A bounded failure which may be returned to the host."""


def main() -> dict[str, str]:
    """Verify the FatturaPA party and use Archive's existing receipt and deduplication."""
    fiscal_id, direction, document_id, engagement_id, environment = sys.argv[1:]
    if environment == "sandbox":
        # Synthetic invoices have a separate Archive configuration and profile.
        defaults = Path.home() / ".vera-acube" / "sandbox"
        sandbox = Path(os.environ.get("VERA_ACUBE_SANDBOX_HOME", defaults))
        # Restore the approved sandbox root from its profile. Each MCP session
        # gets its own Archive configuration lease, separate from the setup CLI.
        session = os.environ["VERA_STUDIO_ARCHIVE_SESSION_ID"]
        scope = sha256(session.encode()).hexdigest()[:32]
        os.environ["VERA_STUDIO_ARCHIVE_STATE_DIR"] = str(sandbox / "sessions" / scope)
        os.environ["VERA_STUDIO_ARCHIVE_PROFILE_DIR"] = str(sandbox / "profile")
    elif environment != "production":
        raise ImportIssue("archive_import_failed")
    sys.path[:0] = [
        str(ROOT / "plugins" / p / "scripts")
        for p in ("studio-archive", "browser-automation")
    ]
    from ade_acquisition.artifacts import MAX_BYTES, inspect_invoice
    from ade_acquisition.contracts import AcquisitionError, Client
    from archive_core import (
        ArchiveError,
        import_studio_client_document,
        resolve_studio_client_identity,
    )

    data = sys.stdin.buffer.read(MAX_BYTES + 1)
    filename = f"acube-{environment}-{UUID(document_id)}.xml"
    party = {"incoming": "CessionarioCommittente", "outgoing": "CedentePrestatore"}[
        direction
    ]
    # The upstream MCP serves decoded text. Reject encodings we cannot preserve.
    encoding = re.match(rb"\s*<\?xml\s+[^?]*?encoding=['\"]([^'\"]+)", data[:512], re.I)
    if (
        encoding and encoding[1].lower() not in (b"utf-8", b"utf8")
    ) or b"\xef\xbf\xbd" in data:
        raise ImportIssue("invalid_invoice")
    try:
        identity = Client("A-Cube", fiscal_id, fiscal_id)
        info, _ = inspect_invoice(
            data,
            filename,
            identity,
            "ricevute" if direction == "incoming" else "emesse",
        )
        root = ElementTree.fromstring(data)
        party_node = root.find(f"{{*}}FatturaElettronicaHeader/{{*}}{party}")
        if party_node is None:
            raise ImportIssue("invoice_party_mismatch")
        # A representative or an unrelated nested identifier cannot establish ownership.
        records = [
            party_node,
            *party_node.findall("{*}DatiAnagrafici"),
            *party_node.findall("{*}IdentificativiFiscali"),
        ]
        identifiers = {
            record.findtext("{*}CodiceFiscale", "").strip() for record in records
        }
        for record in records:
            if record.findtext("{*}IdFiscaleIVA/{*}IdPaese", "").strip() == "IT":
                identifiers.add(
                    record.findtext("{*}IdFiscaleIVA/{*}IdCodice", "").strip()
                )
        if fiscal_id not in identifiers:
            raise ImportIssue("invoice_party_mismatch")
    except AcquisitionError as exc:
        raise ImportIssue(
            "invoice_party_mismatch"
            if exc.code == "invoice-client-mismatch"
            else "invalid_invoice"
        ) from exc
    except (DefusedXmlException, ParseError) as exc:
        raise ImportIssue("invalid_invoice") from exc
    try:
        scope = resolve_studio_client_identity("tax_identifier", fiscal_id)
        if not (
            scope["resolution_complete"]
            and scope["resolution_status"] == "exact_match"
            and scope["matches"][0]["registration_status"] == "registered"
        ):
            raise ImportIssue("client_not_resolved")
        client_id = scope["matches"][0]["client_id"]
        with TemporaryDirectory(prefix="vera-acube-") as folder:
            source = Path(folder).resolve(strict=True) / filename
            source.write_bytes(data)
            saved = import_studio_client_document(
                client_id,
                source,
                "source",
                engagement_id=engagement_id,
                expected_sha256=info["sha256"],
            )
        return {
            "status": saved["status"],
            "input_id": saved["input_id"],
            "path": saved["imported_path"],
            "sha256": info["sha256"],
        }
    except ArchiveError as exc:
        raise ImportIssue("archive_import_failed") from exc


if __name__ == "__main__":
    try:
        result = main()
    except ImportIssue as error:
        sys.stdout.write(json.dumps({"error": str(error)}))
        sys.exit(1)
    sys.stdout.write(json.dumps(result))
