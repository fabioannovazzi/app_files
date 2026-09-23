"""Render a local review catalogue and the compiled teaching guides it links to."""

from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from pathlib import Path

from build_catalog import ROOT, _eligible, build
from course_start import add_course_start

sys.path.insert(0, str(ROOT / "plugins/_shared/vendor/modules"))
from courseware.library import CourseLibrary  # noqa: E402
from courseware.policy import unavailable_local_workflows  # noqa: E402

__all__ = ["render", "main"]

LANGUAGE_NAMES = {
    "it": "Italiano",
    "en": "English",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
}


def render(destination: Path, *, preview: bool = False, public: bool = False) -> Path:
    """Build a fresh local review surface; never execute or approve a lesson."""
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Choose a fresh catalogue directory")
    if destination.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Render review artifacts outside the repository")
    build(require_complete=not preview, check=True)
    destination.mkdir(parents=True)
    assets = ROOT / "plugins/_shared/vendor/modules/courseware/assets"
    for name in (
        "course.css",
        "legacy-course.css",
        "InstrumentSans-Regular.ttf",
        "InstrumentSans-SemiBold.ttf",
        "OFL.txt",
    ):
        shutil.copyfile(assets / name, destination / name)
    if public:
        for name in ("course-start.css", "course-start.js"):
            shutil.copyfile(Path(__file__).parent / name, destination / name)
    sections = []
    for product in ("vera", "clara", "lucia"):
        product_root = ROOT / "plugins" / product
        library = CourseLibrary(product_root, _eligible(product))
        index = json.loads(
            (product_root / "assets/courses/index.json").read_text(encoding="utf-8")
        )
        groups = {"workflow": [], "supporting_task": []}
        for workflow, entry in index["courses"].items():
            default_language = (
                "it" if "it" in entry["languages"] else entry["languages"][0]
            )
            links = []
            for language in entry["languages"]:
                folder = destination / product / workflow / language
                library.render(workflow, language, folder)
                if public:
                    # Public guides contain fictional material, never local session paths.
                    (folder / "execution-request.json").unlink(missing_ok=True)
                    (folder / "course-provenance.json").write_text(
                        json.dumps(
                            {
                                "product": product,
                                "workflow": workflow,
                                "language": language,
                                "prepared_material_only": True,
                                "execution_receipt": False,
                                "understanding_confirmed": False,
                                "course": "course.html",
                                "teacher": "teacher.md",
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    page = folder / "course.html"
                    page.write_text(
                        add_course_start(
                            page.read_text(encoding="utf-8"),
                            product,
                            entry["titles"][language],
                            language,
                            workflow,
                        ).replace(
                            "<main>",
                            '<main><p><a href="../../../index.html#'
                            + product
                            + '">← Vera · Clara · Lucia</a></p>',
                            1,
                        ),
                        encoding="utf-8",
                    )
                    stylesheet = (
                        "legacy-course.css"
                        if entry.get("material") == "retained"
                        else "course.css"
                    )
                    for document in folder.glob("*.html"):
                        document.write_text(
                            document.read_text(encoding="utf-8").replace(
                                "href='course.css'", f"href='../../../{stylesheet}'"
                            ),
                            encoding="utf-8",
                        )
                    for shared in (
                        "course.css",
                        "InstrumentSans-Regular.ttf",
                        "InstrumentSans-SemiBold.ttf",
                        "OFL.txt",
                    ):
                        (folder / shared).unlink()
                target = (folder / "course.html").relative_to(destination).as_posix()
                links.append(
                    f'<a href="{html.escape(target, quote=True)}" lang="{language}">{LANGUAGE_NAMES[language]}</a>'
                )
            title = html.escape(entry["titles"][default_language])
            goal = html.escape(entry["goals"][default_language])
            groups[entry["group"]].append(
                f'<tr><td>{title}</td><td>{goal}</td><td>{" · ".join(links)}</td></tr>'
            )
        content = [f'<section id="{product}"><h2>{product.title()}</h2>']
        for group, label in (
            ("workflow", "Flussi di lavoro"),
            ("supporting_task", "Operazioni di supporto al nuovo cliente"),
        ):
            if groups[group]:
                content.append(
                    f'<h3>{label}</h3><div class="table-scroll"><table><thead><tr>'
                    "<th>Che cosa impari a fare</th><th>Obiettivo</th><th>Apri la lezione</th>"
                    f'</tr></thead><tbody>{"".join(groups[group])}</tbody></table></div>'
                )
        if unavailable_local_workflows(product):
            content.append(
                "<h3>Non disponibili nelle lezioni locali</h3>"
                "<p>Brand Fit, interviste ospitate e video di ricerca richiedono "
                "servizi ospitati. Restano funzioni di Clara, ma non sono incluse "
                "nelle lezioni locali e non vengono eseguite durante l’onboarding.</p>"
            )
        content.append("</section>")
        sections.append("".join(content))
    notice = (
        '<p class="caption">Anteprima incompleta per revisione. Contiene soltanto i kit già riscritti. '
        "Non è una pubblicazione e non certifica l’esecuzione o l’apprendimento.</p>"
        if preview
        else '<p class="caption">Materiali preparati per le lezioni. Aprire una guida non esegue il flusso e non completa una lezione.</p>'
    )
    document = (
        '<!doctype html><html lang="it"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'\">"
        '<title>Lezioni per usare Vera, Clara e Lucia</title><link rel="stylesheet" href="course.css"></head><body>'
        '<header class="masthead"><b>Vera · Clara · Lucia</b><span>Materiali delle lezioni</span></header><main>'
        '<div class="hero"><h1>Lezioni per usare i flussi di lavoro</h1>'
        '<p class="lead">Per ogni funzione: i file da fornire, una richiesta di esempio, i passaggi, '
        "il risultato da aprire e una breve prova da fare.</p>" + notice + "</div>"
        '<section id="come-iniziare"><h2>Come avviare una lezione</h2>'
        "<p>Scegli qui sotto una funzione e apri la lezione nella tua lingua. "
        "All’inizio della pagina trovi <strong>Avvia questa lezione</strong>: copia la richiesta, "
        "scegli Codex oppure Claude Cowork con il plugin indicato installato. In Codex seleziona @Vera, @Clara o @Lucia "
        "e invia la richiesta nella chat. Attiva la voce; l’assistente ti guiderà ad aprire "
        "la seconda chat di lavoro in un’altra finestra. In Cowork usa la richiesta dedicata: la lezione è scritta, "
        "in una sola conversazione, senza voce. I file fittizi sono inclusi nel plugin.</p></section>"
        '<div class="paired"><strong>Due chat durante la lezione in Codex</strong>'
        "<p>Nella chat di lavoro il flusso corrente usa i file fittizi e produce il risultato. "
        "Nella chat vocale l’assistente spiega ciò che sta avvenendo, apre i risultati effettivi e risponde alle domande. "
        "La guida prepara il percorso; il risultato viene eseguito dal vivo.</p></div>"
        '<nav aria-label="Prodotti"><a href="#vera">Vera</a><a href="#clara">Clara</a><a href="#lucia">Lucia</a></nav>'
        + "".join(sections)
        + "<footer>Le spiegazioni e la breve prova mirano a 5–8 minuti. Elaborazione e domande possono richiedere altro tempo. "
        "All’inizio si scelgono i 3–4 flussi più utili; in seguito si può chiedere una lezione quando serve. "
        "Le operazioni di supporto sono raggruppate con il nuovo cliente. La stessa funzione condivisa fra prodotti "
        "compare nel prodotto da cui viene utilizzata.</footer></main></body></html>"
    )
    target = destination / "index.html"
    target.write_text(document, encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--authoring-preview", action="store_true")
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args()
    print(render(args.output_dir, preview=args.authoring_preview, public=args.public))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
