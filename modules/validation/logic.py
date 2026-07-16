from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from modules.pdf_utils.pdf_utils import extract_pdf_rich

__all__ = [
    "build_upload_preview",
    "extract_research_text",
    "has_hyperlinks",
    "prepare_research_state",
]


def has_hyperlinks(pasted: str) -> bool:
    """Return True when pasted HTML contains hyperlinks."""

    if not pasted:
        return False
    return bool(BeautifulSoup(pasted, "html.parser").find("a", href=True))


def build_upload_preview(markdown: str) -> dict[str, str]:
    """Return a preview payload for rendering upload diagnostics."""

    preview = markdown[:500]
    return {"raw": preview, "rendered": preview}


def extract_research_text(uploaded: Any, pasted: str | None) -> tuple[str, dict[str, str] | None, str | None]:
    """Extract the research text from uploads or pasted input."""

    text = ""
    preview = None
    error = None
    if uploaded:
        if uploaded.type == "application/pdf":
            raw_md = extract_pdf_rich(uploaded)
            if not isinstance(raw_md, str):
                return "", None, "PDF extractor returned unexpected type"
            preview = build_upload_preview(raw_md)
            text = raw_md.replace("\f", "\n\n")
        else:
            text = uploaded.getvalue().decode("utf-8", errors="ignore")
    elif pasted:
        text = pasted
    return text, preview, error


def prepare_research_state(state: dict, user_text: str) -> dict:
    """Populate defaults for the validation workflow session state."""

    state.setdefault("results", None)
    state.setdefault("language", None)
    state.setdefault("claims_saved", False)
    state.setdefault("correction_prompt_llm", None)
    state.setdefault("claims_notified", False)
    state.setdefault("prompt_notified", False)
    state.setdefault("document_notified", False)

    doc_hash = hash(user_text.encode())
    if state.get("verified_for") != doc_hash:
        state["verified_for"] = doc_hash
        state["results"] = None
        state["claims_notified"] = False
        state["prompt_notified"] = False
        state["document_notified"] = False
    return state
