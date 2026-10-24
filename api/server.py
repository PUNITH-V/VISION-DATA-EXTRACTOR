"""
FastAPI application factory.

Usage (from project root with venv active):
    uvicorn api.server:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import ALLOWED_ORIGINS, AUTH_ENABLED
from api.routes import health, extractions, reports, ingestion, search, ask

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Startup / shutdown lifecycle.
    Logs clearly whether authentication is active so you can see
    the security posture at a glance in server logs.
    """
    auth_state = "ENABLED" if AUTH_ENABLED else "DISABLED (Stage 2 — endpoints return 503)"
    logger.info("Vision Extractor API starting. Authentication: %s", auth_state)
    logger.info("Allowed CORS origins: %s", ALLOWED_ORIGINS)
    yield
    logger.info("Vision Extractor API shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Vision Extractor API",
        version="0.2.0",
        description=(
            "FastAPI layer over the Vision Data Extractor backend. "
            "Authentication is required for all protected endpoints (Stage 3)."
        ),
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    # Wildcard origins are not used. ALLOWED_ORIGINS comes from the env.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # ── Routes ────────────────────────────────────────────────────────────
    prefix = "/api"
    app.include_router(health.router, prefix=prefix)
    app.include_router(extractions.router, prefix=prefix)
    app.include_router(reports.router, prefix=prefix)
    app.include_router(ingestion.router, prefix=prefix)
    app.include_router(search.router, prefix=prefix)
    app.include_router(ask.router, prefix=prefix)

    return app


app = create_app()
