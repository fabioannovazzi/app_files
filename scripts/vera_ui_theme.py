"""Embed the canonical workflow theme into self-contained UI resources."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

__all__ = [
    "THEME_PATH",
    "theme_css",
    "theme_html",
    "theme_package_resources",
    "theme_course_page",
]

THEME_PATH = Path(__file__).resolve().parents[1] / "plugins/_shared/ui/vera-theme.css"
START = (
    "/* VERA_SHARED_THEME_START — generated; edit plugins/_shared/ui/vera-theme.css */"
)
END = "/* VERA_SHARED_THEME_END */"


def theme_css(css: str, *, theme: str | None = None) -> str:
    """Replace the generated theme without changing surface-specific layout CSS."""
    css = re.sub(re.escape(START) + r".*?" + re.escape(END), "", css, flags=re.S)
    shared = THEME_PATH.read_text(encoding="utf-8") if theme is None else theme
    return f"{css.rstrip()}\n\n{START}\n{shared.rstrip()}\n{END}\n"


def theme_html(html: str, *, theme: str | None = None) -> str:
    """Embed after the first style block's local rules; preserve markup and JS."""
    pattern = re.compile(r"(<style(?:\s[^>]*)?>)(.*?)(</style>)", re.S | re.I)
    if not pattern.search(html):
        raise ValueError("Vera UI resource has no inline style block")
    return pattern.sub(
        lambda match: match[1] + theme_css(match[2], theme=theme) + match[3],
        html,
        count=1,
    )


def theme_package_resources(entries: dict[str, bytes], prefix: str) -> None:
    """Compile the latest theme into product host resources before integrity hashes."""
    theme = THEME_PATH.read_text(encoding="utf-8")
    css_resources = {
        "ui/workspace.css",
        "ui/research-sources.css",
        "modules/browser-automation/ui/agenzia.css",
        "modules/bilancio-xbrl-it/ui/workspace.css",
        "modules/treasury-forecast/assets/review.css",
    }
    if prefix.rstrip("/").split("/")[-1] == "vera":
        css_resources.update(
            {
                "vendor/modules/courseware/assets/course.css",
                "vendor/modules/courseware/assets/legacy-course.css",
            }
        )
    html_resources = {
        "modules/adeguati-assetti/assets/construction-intake.html",
        "modules/prompt-optimizer/assets/legal-tax-model.html",
        "vendor/modules/courseware/assets/chat.html",
        "assets/playbook-editor.html",
        "modules/apertura-pratica/assets/apertura-pratica-review.html",
    }
    original_resources: dict[str, bytes] = {}
    for name in list(entries):
        if not name.startswith(prefix):
            continue
        relative = name.removeprefix(prefix)
        is_widget = (
            relative.startswith("modules/")
            and "/assets/" in relative
            and relative.endswith("-review-widget.html")
        )
        if relative in css_resources:
            original_resources[relative] = entries[name]
            entries[name] = theme_css(
                entries[name].decode("utf-8"), theme=theme
            ).encode()
        elif relative in html_resources or is_widget:
            original_resources[relative] = entries[name]
            entries[name] = theme_html(
                entries[name].decode("utf-8"), theme=theme
            ).encode()
    # Lessons pin their UI sources. Bind the exact themed bytes while retaining
    # their reviewed source hashes; never accept a stale source-course binding.
    index_path = prefix + "assets/courses/index.json"
    if index_path in entries:
        index = json.loads(entries[index_path])
        for workflow, record in index["courses"].items():
            path = prefix + f"assets/courses/{workflow}/course.json"
            original = entries[path]
            original_hash = hashlib.sha256(original).hexdigest()
            if record["sha256"] != original_hash:
                raise ValueError(f"Stale course index: {workflow}")
            course = json.loads(original)
            changed = False
            for source in course["sources"]:
                relative = source["path"]
                if relative not in original_resources:
                    continue
                before = original_resources[relative]
                if source["sha256"] != hashlib.sha256(before).hexdigest():
                    raise ValueError(f"Stale course source: {relative}")
                after = entries[prefix + relative]
                if before != after:
                    source["source_sha256"] = source["sha256"]
                    source["sha256"] = hashlib.sha256(after).hexdigest()
                    changed = True
            if changed:
                content = (
                    json.dumps(course, ensure_ascii=False, indent=2) + "\n"
                ).encode()
                entries[path] = content
                record["source_sha256"] = original_hash
                record["sha256"] = hashlib.sha256(content).hexdigest()
        entries[index_path] = (
            json.dumps(index, ensure_ascii=False, indent=2) + "\n"
        ).encode()
    entries[prefix + "ui/theme.css"] = theme.encode("utf-8")


def theme_course_page(html: str) -> str:
    """Theme the lesson shell only; never restyle linked reports or input artifacts."""
    html = html.replace(
        'href="workflow-theme.css"', 'href="../../../workflow-theme.css"'
    )
    link = '<link rel="stylesheet" href="../../../workflow-theme.css">'
    if link in html or 'href="/static/shared/courses/workflow-theme.css"' in html:
        return html
    return html.replace("</head>", link + "</head>", 1)
