from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from .models import EvidenceBlob, FetchResult, RawEvidence


STORAGE_ROOT = Path(__file__).resolve().parents[2] / "reports" / "pdp"


def _sha256_text(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def _sha256_json(payload: object) -> str:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256()
    digest.update(serialized.encode("utf-8"))
    return digest.hexdigest()


class EvidenceStorage:
    """Persist HTML and JSON blobs for reproducibility."""

    def __init__(self, root: Path | None = None, persist_html: bool = True, persist_json: bool = True):
        self.root = root or STORAGE_ROOT
        self.persist_html = persist_html
        self.persist_json = persist_json

    def persist(
        self,
        retailer: str,
        parent_product_id: str,
        fetch_result: FetchResult,
        blobs: Iterable[EvidenceBlob],
    ) -> RawEvidence:
        if not self.persist_html and not self.persist_json:
            return RawEvidence()

        date_str = fetch_result.fetched_at.date().isoformat()
        html_path = None
        blob_paths: list[Path] = []
        blob_hashes: list[str] = []

        if self.persist_html:
            html_path = self.root / "html" / retailer / parent_product_id / date_str / "page.html"
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(fetch_result.html, encoding="utf-8")

        if self.persist_json:
            for blob in blobs:
                if blob.payload is None:
                    continue
                blob_dir = self.root / "json" / retailer / parent_product_id / date_str
                blob_dir.mkdir(parents=True, exist_ok=True)
                blob_path = blob_dir / f"blob-{blob.index:03d}.json"
                blob_path.write_text(
                    json.dumps(blob.payload, indent=2, sort_keys=True, ensure_ascii=False),
                    encoding="utf-8",
                )
                blob_paths.append(blob_path)
                blob_hashes.append(_sha256_json(blob.payload))

        html_hash = _sha256_text(fetch_result.html) if self.persist_html else None

        return RawEvidence(
            html_path=html_path,
            blob_paths=tuple(blob_paths),
            html_sha256=html_hash,
            blob_sha256=tuple(blob_hashes),
        )


__all__ = ["EvidenceStorage", "STORAGE_ROOT"]
