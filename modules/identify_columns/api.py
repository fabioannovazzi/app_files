from __future__ import annotations

from typing import Any, Dict, List, Optional

import polars as pl
from fastapi import APIRouter
from pydantic import BaseModel, Field

from modules.identify_columns.logic import (
    cogs_col_found,
    indirect_costs_col_found,
    show_input_data,
)

__all__ = ["router"]

router = APIRouter(prefix="/identify-columns", tags=["identify columns"])


class IdentifyColumnsRequest(BaseModel):
    param_dict: Dict[str, Any] = Field(..., description="Column detection flags and metadata.")


class IdentifyColumnsMessage(BaseModel):
    level: str
    text: str
    icon: Optional[str] = None


class IdentifyColumnsResponse(BaseModel):
    param_dict: Dict[str, Any]
    messages: List[IdentifyColumnsMessage]


def _build_messages(payload: List[tuple[str, str, str | None]]) -> List[IdentifyColumnsMessage]:
    return [
        IdentifyColumnsMessage(level=level, text=text, icon=icon) for level, text, icon in payload
    ]


@router.post("/messages", response_model=IdentifyColumnsResponse)
def identify_columns_messages(payload: IdentifyColumnsRequest) -> IdentifyColumnsResponse:
    """Return column detection messages for a data upload."""
    _, updated, messages = show_input_data(pl.LazyFrame(), payload.param_dict)
    return IdentifyColumnsResponse(param_dict=updated, messages=_build_messages(messages))


@router.post("/cogs", response_model=IdentifyColumnsResponse)
def identify_cogs_columns(payload: IdentifyColumnsRequest) -> IdentifyColumnsResponse:
    """Return COGS column detection messages."""
    updated, messages = cogs_col_found(payload.param_dict)
    return IdentifyColumnsResponse(param_dict=updated, messages=_build_messages(messages))


@router.post("/indirect-costs", response_model=IdentifyColumnsResponse)
def identify_indirect_costs_columns(payload: IdentifyColumnsRequest) -> IdentifyColumnsResponse:
    """Return indirect costs column detection messages."""
    updated, messages = indirect_costs_col_found(payload.param_dict)
    return IdentifyColumnsResponse(param_dict=updated, messages=_build_messages(messages))
