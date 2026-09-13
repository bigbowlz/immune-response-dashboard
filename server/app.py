"""FastAPI application. Serves the API and, when built, the frontend from one process on one port."""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from analysis.schema import ROOT
from server.routes import router

DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="Immune Response Dashboard API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(router)

if DIST.is_dir() and os.environ.get("SERVE_FRONTEND", "1") != "0":
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
