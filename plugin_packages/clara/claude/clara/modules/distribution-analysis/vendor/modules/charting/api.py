from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from modules.pdp.language import get_navigation_label, get_page_copy, resolve_language

__all__ = ["router", "site_router"]

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/charting", tags=["charting"])
site_router = APIRouter(prefix="/charting")


@site_router.get("/page", include_in_schema=False)
def charting_page(request: Request) -> Any:
    lang = resolve_language(request)
    page_label = get_navigation_label(lang, "/charting/page")
    return templates.TemplateResponse(
        request,
        "charting.html",
        {
            "lang": lang,
            "page_label": page_label,
            "copy": get_page_copy("charting", lang),
        },
    )
