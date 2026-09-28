"""Retain verified Clara presentations with only their own installed runtime."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path

__all__ = ["deck_files", "deck_csp"]


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[str] = []
        self.current: list[str] | None = None
        self.executable = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"iframe", "object", "embed", "form", "base"} or any(
            key.startswith("on") for key in values
        ):
            raise ValueError("Unsupported active presentation content")
        if any(key in values for key in {"src", "srcdoc"}):
            raise ValueError("Presentation must be self-contained")
        if "href" in values and not (values["href"] or "").startswith("#"):
            raise ValueError("Presentation links must stay inside the deck")
        if tag == "script":
            self.current = []
            self.executable = values.get("type", "").lower() != "application/json"

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.current is not None:
            content = "".join(self.current)
            if self.executable:
                self.scripts.append(content)
            else:
                json.loads(content)
            self.current = None


def _scripts(text: str) -> list[str]:
    parser = _Scripts()
    parser.feed(text)
    parser.close()
    return parser.scripts


def deck_csp(text: str) -> str:
    """Sandbox the validated copy and permit only its exact inline runtime bytes."""
    hashes = " ".join(
        "'sha256-"
        + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()
        + "'"
        for s in _scripts(text)
    )
    return (
        "sandbox allow-scripts; default-src 'none'; script-src "
        + (hashes or "'none'")
        + "; style-src 'unsafe-inline'; img-src data:; font-src data:; "
        "base-uri 'none'; form-action 'none'"
    )


def deck_files(
    lesson: Path, execution: dict, plugin_root: Path
) -> dict[Path, tuple[str, str]]:
    """Bind each deck to native validation and the current installed Clara scripts."""
    runtime_path = plugin_root / "scripts/html_deck_runtime.py"
    spec = importlib.util.spec_from_file_location("course_deck_runtime", runtime_path)
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    expected = sorted(
        [
            runtime.fixed_16_9_deck_js().strip(),
            (plugin_root / "skills/html-deck/assets/deck-engine/deck.js")
            .read_text()
            .strip(),
        ]
    )
    validations = []
    for record in execution["native_records"]:
        path = lesson / record["path"]
        if path.suffix == ".json":
            data = json.loads(path.read_text())
            if (
                isinstance(data, dict)
                and data.get("schema_version") == "clara.html_deck_validation.v1"
            ):
                validations.append(data)
    result = {}
    entries = [(True, n, item) for n, item in enumerate(execution["outputs"], 1)]
    entries += [(False, n, item) for n, item in enumerate(execution["inputs"], 1)]
    output_count = 0
    for is_output, index, item in entries:
        path = lesson / item["path"]
        if path.suffix != ".html":
            continue
        text = path.read_text()
        if not is_output and 'data-clara-deck-mode="stage"' not in text:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"] or (
            is_output
            and not any(
                v.get("result") == "pass"
                and v.get("profile") == "stage"
                and v.get("input", {}).get("sha256") == digest
                for v in validations
            )
        ):
            raise ValueError("Presentation needs native validation for its exact bytes")
        runtime.assert_html_deck_runtime(text, label=path.name, profile="stage")
        if sorted(s.strip() for s in _scripts(text)) != expected:
            raise ValueError(
                "Presentation scripts differ from the installed Clara runtime"
            )
        prefix = "result" if is_output else "source"
        result[path] = (f"decks/{prefix}-{index:02d}.html", digest)
        output_count += int(is_output)
    if not output_count:
        raise ValueError("Presentation execution has no validated HTML deck")
    return result
