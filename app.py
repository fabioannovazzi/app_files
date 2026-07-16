from __future__ import annotations

"""FastAPI entry wrapper for the deployment target."""

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Fabio Annovazzi

from src.fastapi_app_entry import app, create_app

__all__ = ["app", "create_app"]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.fastapi_app_entry:app", host="0.0.0.0", port=8000, reload=True)
