"""Public course entry instructions; no lesson execution or session data."""

from __future__ import annotations

import html
import json
from pathlib import Path

__all__ = ["add_course_start"]

COPY = {
    "it": {
        "heading": "Avvia questa lezione",
        "steps": [
            "Apri Codex sul computer con {product} installato e seleziona @{product} in una chat.",
            "Copia la richiesta qui sotto, incollala nella chat e inviala.",
            "Attiva la voce di Codex in questa chat. L’assistente ti guiderà ad aprire la seconda chat di lavoro in un’altra finestra: qui ascolti e fai domande, lì vedi il lavoro e i risultati.",
        ],
        "note": "I file fittizi della lezione sono già inclusi nel plugin. Puoi anche seguire la lezione per iscritto. Questo pulsante copia la richiesta: la lezione parte quando la invii in Codex.",
        "label": "Richiesta da inviare a {product}",
        "button": "Copia la richiesta",
        "copied": "Richiesta copiata. Incollala e inviala in Codex.",
        "fallback": "Seleziona e copia la richiesta, poi incollala in Codex.",
        "prompt": "{product}, avvia la lezione preparata «{title}» in italiano. Insegnami a usare questa funzione con i file fittizi inclusi. Usa questa chat per spiegarmi i passaggi e rispondere alle domande. Crea o riprendi una seconda chat di lavoro per eseguire il workflow corrente e guidami ad aprirla in un’altra finestra. Guidami ad attivare la voce. Mostrami i risultati effettivi e poi fammi provare l’esercizio.",
    },
    "en": {
        "heading": "Start this course",
        "steps": [
            "Open Codex on your computer with {product} installed and select @{product} in a chat.",
            "Copy the request below, paste it into the chat and send it.",
            "Turn on Codex voice in this chat. The assistant will guide you to open the second working chat in another window: listen and ask questions here, and watch the work and results there.",
        ],
        "note": "The fictional lesson files are already included in the plugin. You can also take the lesson in writing. This button copies the request; the lesson starts when you send it in Codex.",
        "label": "Request to send to {product}",
        "button": "Copy request",
        "copied": "Request copied. Paste and send it in Codex.",
        "fallback": "Select and copy the request, then paste it into Codex.",
        "prompt": "{product}, start the prepared lesson “{title}” in English. Teach me to use this function with the included fictional files. Use this chat to explain the steps and answer my questions. Create or resume a second working chat to run the current workflow, and guide me to open it in another window. Help me turn on voice. Show me the actual results, then let me try the practice exercise.",
    },
    "fr": {
        "heading": "Commencer cette leçon",
        "steps": [
            "Ouvrez Codex sur votre ordinateur avec {product} installé et sélectionnez @{product} dans une conversation.",
            "Copiez la demande ci-dessous, collez-la dans la conversation et envoyez-la.",
            "Activez la voix de Codex dans cette conversation. L’assistant vous guidera pour ouvrir la seconde conversation de travail dans une autre fenêtre : écoutez et posez vos questions ici, suivez le travail et les résultats là-bas.",
        ],
        "note": "Les fichiers fictifs de la leçon sont déjà inclus dans le plugin. Vous pouvez aussi suivre la leçon par écrit. Ce bouton copie la demande ; la leçon commence lorsque vous l’envoyez dans Codex.",
        "label": "Demande à envoyer à {product}",
        "button": "Copier la demande",
        "copied": "Demande copiée. Collez-la et envoyez-la dans Codex.",
        "fallback": "Sélectionnez et copiez la demande, puis collez-la dans Codex.",
        "prompt": "{product}, commence la leçon préparée « {title} » en français. Apprends-moi à utiliser cette fonction avec les fichiers fictifs inclus. Utilise cette conversation pour expliquer les étapes et répondre à mes questions. Crée ou reprends une seconde conversation de travail pour exécuter le workflow actuel et guide-moi pour l’ouvrir dans une autre fenêtre. Aide-moi à activer la voix. Montre-moi les résultats réels, puis fais-moi essayer l’exercice pratique.",
    },
    "de": {
        "heading": "Diese Lektion starten",
        "steps": [
            "Öffnen Sie Codex auf Ihrem Computer mit installiertem {product} und wählen Sie @{product} in einem Chat aus.",
            "Kopieren Sie die folgende Anfrage, fügen Sie sie in den Chat ein und senden Sie sie ab.",
            "Aktivieren Sie die Sprachfunktion von Codex in diesem Chat. Der Assistent hilft Ihnen, den zweiten Arbeitschat in einem weiteren Fenster zu öffnen: Hier hören Sie zu und stellen Fragen, dort verfolgen Sie die Arbeit und die Ergebnisse.",
        ],
        "note": "Die fiktiven Übungsdateien sind bereits im Plugin enthalten. Sie können die Lektion auch schriftlich durchgehen. Diese Schaltfläche kopiert die Anfrage; die Lektion beginnt, wenn Sie sie in Codex absenden.",
        "label": "Anfrage an {product}",
        "button": "Anfrage kopieren",
        "copied": "Anfrage kopiert. Fügen Sie sie in Codex ein und senden Sie sie ab.",
        "fallback": "Markieren und kopieren Sie die Anfrage und fügen Sie sie in Codex ein.",
        "prompt": "{product}, starte die vorbereitete Lektion „{title}“ auf Deutsch. Zeige mir anhand der enthaltenen fiktiven Dateien, wie ich diese Funktion nutze. Erkläre die Schritte und beantworte meine Fragen in diesem Chat. Erstelle oder öffne einen zweiten Arbeitschat, führe dort den aktuellen Workflow aus und hilf mir, ihn in einem weiteren Fenster zu öffnen. Hilf mir, die Sprachfunktion zu aktivieren. Zeige mir die tatsächlichen Ergebnisse und lass mich anschließend die Übung ausprobieren.",
    },
    "es": {
        "heading": "Empezar esta lección",
        "steps": [
            "Abre Codex en tu ordenador con {product} instalado y selecciona @{product} en un chat.",
            "Copia la solicitud de abajo, pégala en el chat y envíala.",
            "Activa la voz de Codex en este chat. El asistente te guiará para abrir el segundo chat de trabajo en otra ventana: aquí escuchas y haces preguntas; allí sigues el trabajo y los resultados.",
        ],
        "note": "Los archivos ficticios de la lección ya están incluidos en el plugin. También puedes seguir la lección por escrito. Este botón copia la solicitud; la lección empieza cuando la envías en Codex.",
        "label": "Solicitud para {product}",
        "button": "Copiar solicitud",
        "copied": "Solicitud copiada. Pégala y envíala en Codex.",
        "fallback": "Selecciona y copia la solicitud, y pégala en Codex.",
        "prompt": "{product}, inicia la lección preparada «{title}» en español. Enséñame a usar esta función con los archivos ficticios incluidos. Utiliza este chat para explicar los pasos y responder a mis preguntas. Crea o retoma un segundo chat de trabajo para ejecutar el workflow actual y guíame para abrirlo en otra ventana. Ayúdame a activar la voz. Muéstrame los resultados reales y después déjame hacer el ejercicio práctico.",
    },
}


def add_course_start(
    document: str, product: str, title: str, language: str, workflow: str = ""
) -> str:
    """Add localized, copyable entry instructions to a public lesson page."""
    copy = COPY[language]
    name = product.title()
    steps = "".join(
        f"<li>{html.escape(step.format(product=name))}</li>" for step in copy["steps"]
    )
    prompt = html.escape(copy["prompt"].format(product=name, title=title))
    section = (
        '<section class="course-start" aria-labelledby="course-start-heading">'
        f'<h2 id="course-start-heading">{html.escape(copy["heading"])}</h2><h3>Codex</h3><ol>{steps}</ol>'
        f'<label for="course-start-request">{html.escape(copy["label"].format(product=name))}</label>'
        f'<textarea id="course-start-request" readonly rows="7">{prompt}</textarea>'
        f'<button type="button" id="course-start-copy" data-copy-target="course-start-request" data-copy-status="course-start-status" data-copied="{html.escape(copy["copied"], quote=True)}" '
        f'data-fallback="{html.escape(copy["fallback"], quote=True)}">{html.escape(copy["button"])}</button>'
        '<p id="course-start-status" role="status" aria-live="polite"></p>'
        f'<p class="course-start-note">{html.escape(copy["note"])}</p></section>'
    )
    cowork = json.loads(
        (Path(__file__).parents[1] / "cowork_teaching/public-start.json").read_text(
            encoding="utf-8"
        )
    )[language]
    section += (
        '<section class="course-start" aria-labelledby="cowork-start-heading">'
        + f'<h2 id="cowork-start-heading">{html.escape(cowork["heading"])}</h2>'
    )
    if product == "clara" and workflow in {"deck-correction", "transcribe"}:
        section += f'<p>{html.escape(cowork["unavailable"])}</p>'
    else:
        section += (
            f'<p>{html.escape(cowork["steps"].format(product=name))}</p>'
            f'<label for="cowork-start-request">{html.escape(copy["label"].format(product=name))}</label>'
            f'<textarea id="cowork-start-request" readonly rows="6">{html.escape(cowork["prompt"].format(product=name, title=title))}</textarea>'
            f'<button type="button" data-copy-target="cowork-start-request" data-copy-status="cowork-start-status" data-copied="{html.escape(cowork["copied"], quote=True)}" data-fallback="{html.escape(cowork["fallback"], quote=True)}">{html.escape(cowork["button"])}</button>'
            '<p id="cowork-start-status" role="status" aria-live="polite"></p>'
        )
    section += "</section>"
    marker = "<aside class='paired'>"
    if marker not in document:
        raise ValueError("Expected a lesson introduction before startup instructions")
    return (
        document.replace(marker, section + marker, 1)
        .replace("default-src 'none';", "default-src 'none'; script-src 'self';", 1)
        .replace(
            "</head>",
            '<link rel="stylesheet" href="../../../course-start.css">'
            '<script src="../../../course-start.js" defer></script></head>',
            1,
        )
    )
