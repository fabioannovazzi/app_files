from __future__ import annotations

import io
import logging
from typing import Any, List

import polars as pl
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from modules.pdp.language import get_navigation_label, get_page_copy, resolve_language
from modules.utilities.utils import get_row_count, get_schema_and_column_names
from modules.hierarchy_fix.logic import (
    _build_chains,
    detect_hierarchies,
    order_hierarchy_pairs,
    resolve_hierarchies,
)

__all__ = ["router", "site_router"]

LOGGER = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/hierarchy", tags=["hierarchy fix"])
site_router = APIRouter(prefix="/hierarchy")


class HierarchyPair(BaseModel):
    child: str
    parent: str


class HierarchyPreviewResponse(BaseModel):
    columns: List[str]
    row_count: int
    pairs: List[HierarchyPair]
    chains: List[str]


def _read_frame(file_name: str, payload: bytes) -> pl.DataFrame:
    lower_name = (file_name or "").lower()
    if lower_name.endswith(".csv"):
        return pl.read_csv(io.BytesIO(payload))
    if lower_name.endswith(".parquet"):
        return pl.read_parquet(io.BytesIO(payload))
    if lower_name.endswith((".xlsx", ".xls")):
        return pl.read_excel(io.BytesIO(payload))
    raise ValueError("Unsupported file type. Upload a CSV, Parquet, or Excel file.")


@site_router.get("/page", include_in_schema=False)
def hierarchy_page(request: Request) -> Any:
    lang = resolve_language(request)
    page_label = get_navigation_label(lang, "/hierarchy/page")
    return templates.TemplateResponse(
        request,
        "hierarchy_fix.html",
        {
            "lang": lang,
            "page_label": page_label,
            "copy": get_page_copy("hierarchy_fix", lang),
        },
    )


@router.post("/preview", response_model=HierarchyPreviewResponse)
async def preview_hierarchy(
    data_file: UploadFile = File(...),
    ambiguous_pct: float = Form(0.0),
    allow_parent_more_uniques: bool = Form(True),
) -> HierarchyPreviewResponse:
    if not data_file.filename:
        raise HTTPException(status_code=400, detail="Upload a data file.")
    payload = await data_file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        frame = _read_frame(data_file.filename, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Failed to parse hierarchy file")
        raise HTTPException(status_code=500, detail="Failed to parse uploaded file.") from exc

    pairs_df = detect_hierarchies(
        frame,
        ambiguous_pct,
        allow_parent_more_uniques=allow_parent_more_uniques,
    )
    pairs = [HierarchyPair(**row) for row in pairs_df.to_dicts()]
    ordered_pairs = order_hierarchy_pairs([(pair.child, pair.parent) for pair in pairs])
    chains = [" ➜ ".join(reversed(chain)) for chain in _build_chains(ordered_pairs)]
    columns, _ = get_schema_and_column_names(frame)
    return HierarchyPreviewResponse(
        columns=columns,
        row_count=get_row_count(frame),
        pairs=pairs,
        chains=chains,
    )


@router.post("/resolve")
async def resolve_hierarchy(
    data_file: UploadFile = File(...),
    ambiguous_pct: float = Form(0.0),
    allow_parent_more_uniques: bool = Form(True),
    weight_col: str | None = Form(None),
) -> Response:
    if not data_file.filename:
        raise HTTPException(status_code=400, detail="Upload a data file.")
    payload = await data_file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        frame = _read_frame(data_file.filename, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Failed to parse hierarchy file")
        raise HTTPException(status_code=500, detail="Failed to parse uploaded file.") from exc

    pairs_df = detect_hierarchies(
        frame,
        ambiguous_pct,
        allow_parent_more_uniques=allow_parent_more_uniques,
    )
    pairs = [tuple(row.values()) for row in pairs_df.to_dicts()]
    ordered_pairs = order_hierarchy_pairs(pairs)
    resolved, _ = resolve_hierarchies(
        frame,
        pairs=ordered_pairs,
        weight_col=weight_col,
        ambiguous_pct=100,
        param_dict={},
        ambiguous_placeholder="N/A",
    )
    buffer = io.BytesIO()
    resolved.write_csv(buffer)
    buffer.seek(0)
    filename = f"hierarchy_fixed_{data_file.filename.rsplit('.', 1)[0]}.csv"
    return Response(
        buffer.read(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
