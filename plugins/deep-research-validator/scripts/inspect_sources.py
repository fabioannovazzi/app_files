"""Inspect cited sources for a Deep Research validation run."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

__all__ = ["inspect_sources", "write_source_inventory"]

URL_RE = re.compile(r"https?://[^\s)\]>\"']+", re.IGNORECASE)
ACCESS_BARRIER_SNIPPETS = (
    "access denied",
    "forbidden",
    "captcha",
    "verify you are human",
    "cloudflare",
    "enable javascript",
    "subscription",
    "sign in",
    "login",
)


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = item.strip().rstrip(".,;:!?)\\]}>'\"")
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_urls_from_inventory(path: Path) -> list[str]:
    payload = _read_json(path)
    urls = [str(url) for url in payload.get("urls", [])]
    for footnote in payload.get("footnotes", []):
        urls.extend(URL_RE.findall(str(footnote.get("text", ""))))
    for link in payload.get("markdown_links", []):
        urls.append(str(link.get("url", "")))
    return _ordered_unique(urls)


def _source_file_record(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {
        "kind": "file",
        "name": path.name,
        "path": str(path),
        "status": "available" if text.strip() else "empty",
        "character_count": len(text.strip()),
        "excerpt": re.sub(r"\s+", " ", text.strip())[:1200],
    }


def _looks_blocked(text: str) -> bool:
    sample = re.sub(r"\s+", " ", text).casefold()[:4000]
    return any(snippet in sample for snippet in ACCESS_BARRIER_SNIPPETS)


def _fetch_url_record(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "MparanzaDeepResearchValidator/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(1_000_000)
            text = raw.decode("utf-8", errors="ignore")
            status = int(getattr(response, "status", 0) or 0)
    except urllib.error.HTTPError as exc:
        return {
            "kind": "url",
            "url": url,
            "status": "http_error",
            "http_status": int(exc.code),
            "character_count": 0,
            "excerpt": "",
            "error": str(exc),
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "kind": "url",
            "url": url,
            "status": "unreachable",
            "http_status": 0,
            "character_count": 0,
            "excerpt": "",
            "error": str(exc),
        }

    cleaned = re.sub(
        r"<script\b.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL
    )
    cleaned = re.sub(
        r"<style\b.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL
    )
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    parse_status = "available"
    if len(cleaned) < 120:
        parse_status = "too_short"
    elif _looks_blocked(cleaned):
        parse_status = "access_barrier"
    return {
        "kind": "url",
        "url": url,
        "status": parse_status,
        "http_status": status,
        "character_count": len(cleaned),
        "excerpt": cleaned[:1200],
        "error": "",
    }


def inspect_sources(
    inventory_path: Path,
    *,
    source_files: list[Path] | None = None,
    timeout: float = 10.0,
    fetch_urls: bool = True,
) -> dict[str, Any]:
    """Return deterministic source inventory."""

    urls = _extract_urls_from_inventory(inventory_path)
    url_records = (
        [_fetch_url_record(url, timeout) for url in urls]
        if fetch_urls
        else [
            {
                "kind": "url",
                "url": url,
                "status": "listed_not_fetched",
                "http_status": 0,
                "character_count": 0,
                "excerpt": "",
                "error": "",
            }
            for url in urls
        ]
    )
    file_records = [
        _source_file_record(path)
        for path in (source_files or [])
        if path.exists() and path.is_file()
    ]
    return {
        "url_count": len(urls),
        "file_count": len(file_records),
        "sources": [*url_records, *file_records],
    }


def write_source_inventory(
    inventory_path: Path,
    output_dir: Path,
    *,
    source_files: list[Path] | None = None,
    timeout: float = 10.0,
    fetch_urls: bool = True,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = inspect_sources(
        inventory_path,
        source_files=source_files,
        timeout=timeout,
        fetch_urls=fetch_urls,
    )
    path = output_dir / "source_inventory.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"source_inventory": path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_inventory", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-file", type=Path, action="append", default=[])
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args()
    write_source_inventory(
        args.document_inventory,
        args.output_dir,
        source_files=args.source_file,
        timeout=args.timeout,
        fetch_urls=not args.no_fetch,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
