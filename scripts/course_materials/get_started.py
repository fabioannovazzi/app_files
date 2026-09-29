"""Render Vera's introductory course without adding a professional workflow."""

from __future__ import annotations

import html
import json
from pathlib import Path

from course_start import add_course_start

__all__ = ["render_introduction"]

LANGUAGES = {
    "it": "Italiano",
    "en": "English",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
}


def render_introduction(root: Path, destination: Path) -> str:
    """Render authored guides and return the catalogue's opening section."""
    source = root / "plugins/vera/skills/learn-with-vera/references/get-started.json"
    locales = json.loads(source.read_text(encoding="utf-8"))
    if set(locales) != set(LANGUAGES):
        raise ValueError("The Vera introduction requires all five supported languages")
    links = []
    for language, name in LANGUAGES.items():
        copy = locales[language]
        title = html.escape(copy["title"])
        steps = "".join(
            f'<section id="step-{number}"><p class="eyebrow">{number:02}</p>'
            f'<h2>{html.escape(step["title"])}</h2><p>{html.escape(step["text"])}</p></section>'
            for number, step in enumerate(copy["steps"], 1)
        )
        document = (
            f'<!doctype html><html lang="{language}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'\">"
            f'<title>{title}</title><link rel="stylesheet" href="../../../course.css"></head><body>'
            '<header class="masthead"><b>Vera</b><span>5–8 min</span></header><main>'
            f'<p><a href="../../../index.html">← {html.escape(copy["back"])}</a></p>'
            f'<div class="hero"><h1>{title}</h1><p class="lead">{html.escape(copy["lead"])}</p>'
            f'<p>{html.escape(copy["duration"])}</p><p>{html.escape(copy["optional"])}</p></div>'
            f"<aside class='paired'><strong>{html.escape(copy['route'])}</strong></aside>"
            + steps
            + '<section id="model-data">'
            + f'<h2>{html.escape(copy["data_heading"])}</h2><p>{html.escape(copy["data"])}</p>'
            + "</section></main></body></html>"
        )
        folder = destination / "vera/get-started" / language
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "course.html").write_text(
            add_course_start(
                document,
                "vera",
                copy["title"],
                language,
                codex_prompt=copy["codex_prompt"],
                cowork_prompt=copy["cowork_prompt"],
            ),
            encoding="utf-8",
        )
        target = f"vera/get-started/{language}/course.html"
        links.append(f'<a href="{target}" lang="{language}">{name}</a>')
    return (
        '<section id="inizia-con-vera" aria-labelledby="inizia-con-vera-title">'
        '<h2 id="inizia-con-vera-title"><a href="vera/get-started/it/course.html">'
        "Inizia a usare Vera</a></h2>"
        '<p class="lead">Prova un lavoro con file fittizi già preparati: '
        "impara cosa chiedere, quali file fornire, come leggere il risultato e come modificarlo.</p>"
        "<p>Ti proponiamo 3–4 funzioni utili per il tuo lavoro e ne proviamo una sola. "
        "5–8 minuti di spiegazione e breve pratica, oltre ai tempi di elaborazione e alle domande. "
        "Introduzione facoltativa, in Codex o per iscritto in Cowork.</p>"
        '<nav aria-label="Lingua del corso introduttivo">'
        + " · ".join(links)
        + "</nav></section>"
    )
