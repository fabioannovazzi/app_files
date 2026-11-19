"""Validate changed public pages without running unrelated product suites."""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import logging
import subprocess
import threading
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

__all__ = ["validate_page", "validate_benchmark", "browser_check", "main"]


def validate_page(page: Path, root: Path) -> None:
    """Check document metadata, unique anchors and local file links."""
    soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
    assert soup.title and soup.title.get_text(strip=True), f"Missing title: {page}"
    assert soup.find("meta", attrs={"name": "viewport"}), f"Missing viewport: {page}"
    ids = [node["id"] for node in soup.select("[id]")]
    assert len(ids) == len(set(ids)), f"Duplicate IDs: {page}"
    targets = {}
    for node in soup.select("a[href],script[src],link[href],img[src]"):
        value = node.get("href", node.get("src", ""))
        url = urlsplit(value)
        if url.scheme or url.netloc or not value or "{{" in value:
            continue
        path = unquote(url.path)
        target = (
            (root / path.lstrip("/")) if path.startswith("/") else page.parent / path
        )
        if not path:
            target = page
        # Server routes are outside this static-file check.
        if path and not Path(path).suffix:
            continue
        assert target.is_file(), f"Missing local asset: {page}: {value}"
        if url.fragment and target.suffix == ".html":
            if target not in targets:
                targets[target] = BeautifulSoup(
                    target.read_text(encoding="utf-8"), "html.parser"
                )
            document = targets[target]
            # Script-built anchors require the browser/manual interaction check.
            assert document.find(id=unquote(url.fragment)) or document.find(
                "script"
            ), f"Missing anchor: {page}: {value}"


def validate_benchmark(path: Path) -> None:
    """Recompute the published indicators from criteria and citation judgments."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert [case["number"] for case in cases] == list(range(1, 23))
    for case in cases:
        for system in ("vera", "codex"):
            points = case["points"]
            citations = [c for c in case["citations"] if c["system"].lower() == system]
            expected = {
                "content": {"n": sum(p[system] for p in points), "d": len(points)},
                "coverage": {
                    "n": sum(p["fonti_" + system] for p in points),
                    "d": sum(p[system] for p in points),
                },
                "citations": {
                    "n": sum(c["supported"] for c in citations),
                    "d": len(citations),
                },
            }
            assert (
                case["metrics"][system] == expected
            ), f"Metric mismatch: {case['number']} {system}"
            answer = case["answers"][system]
            assert (
                hashlib.sha256(answer["text"].encode()).hexdigest() == answer["sha256"]
            )
    for system in ("vera", "codex"):
        for metric in ("content", "coverage", "citations"):
            for part in ("n", "d"):
                assert data["totals"][system][metric][part] == sum(
                    c["metrics"][system][metric][part] for c in cases
                )


def browser_check(pages: list[Path], root: Path) -> None:
    """Render representative affected pages at desktop and mobile widths."""
    from playwright.sync_api import sync_playwright

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(root)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for width in (1280, 390):
                for path in pages[:12]:
                    page = browser.new_page(viewport={"width": width, "height": 900})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    response = page.goto(
                        f"http://127.0.0.1:{server.server_port}/{path.relative_to(root).as_posix()}",
                        wait_until="networkidle",
                    )
                    assert response and response.ok, path
                    assert not errors, (path, errors)
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    ), (path, width)
                    assert page.locator(
                        "h1"
                    ).count(), f"Missing visible heading: {path}"
                    page.close()
            browser.close()
    finally:
        server.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    names = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", args.base, "HEAD"],
        cwd=root,
        text=True,
    ).splitlines()
    changed = [root / name for name in names if name.startswith("static/")]
    pages = {p for p in changed if p.suffix == ".html"}
    # Follow actual asset references; unrelated sibling pages need not be tested.
    assets = {p.resolve() for p in changed if p.suffix != ".html"}
    if assets:
        for candidate in (root / "static").rglob("*.html"):
            document = BeautifulSoup(
                candidate.read_text(encoding="utf-8"), "html.parser"
            )
            for node in document.select("[href],[src]"):
                url = urlsplit(node.get("href", node.get("src", "")))
                if url.scheme or url.netloc or not url.path:
                    continue
                target = (
                    root / url.path.lstrip("/")
                    if url.path.startswith("/")
                    else candidate.parent / url.path
                )
                if target.resolve() in assets:
                    pages.add(candidate)
                    break
    for path in changed:
        if path.suffix == ".js":
            subprocess.run(["node", "--check", str(path)], check=True)
    for page in sorted(pages):
        validate_page(page, root)
    benchmark = root / "static/shared/vera/benchmark/legal-22-dati.json"
    if benchmark.exists():
        validate_benchmark(benchmark)
    if args.browser and pages:
        browser_check(sorted(pages), root)
    logging.basicConfig(level=logging.INFO)
    logging.info(
        "Validated %d affected HTML pages and benchmark counts; browser sample up to 12 pages at two widths.",
        len(pages),
    )


if __name__ == "__main__":
    main()
