"""GET /api/health — service readiness check."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter

from api.schemas import HealthResponse, ServiceStatus
from config.settings import API_KEY, CHROMA_BASE_DIR

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    tags=["Health"],
)
def health_check() -> HealthResponse:
    """
    Return the readiness of each backend service component.

    Does not require authentication. Does not expose secrets.
    Checks:
      - embedding model: attempt to import and load SentenceTransformer.
      - vector_store: verify ChromaDB base directory is accessible.
      - llm_api: verify the API key env var is set (no network call).
    """
    # Embedding model
    try:
        from embeddings.embedder import TextEmbedder
        TextEmbedder()  # loads the model; cached after first call
        embedding_status = "loaded"
    except Exception as exc:
        logger.warning("Embedding model check failed: %s", exc)
        embedding_status = "unavailable"

    # Vector store (directory accessibility only — no network)
    try:
        CHROMA_BASE_DIR.mkdir(parents=True, exist_ok=True)
        vector_status = "reachable"
    except OSError as exc:
        logger.warning("ChromaDB directory check failed: %s", exc)
        vector_status = "unreachable"

    # LLM API key presence
    llm_status = "configured" if API_KEY else "missing_key"

    overall = (
        "ok"
        if embedding_status == "loaded"
        and vector_status == "reachable"
        and llm_status == "configured"
        else "degraded"
    )

    return HealthResponse(
        status=overall,
        services=ServiceStatus(
            embedding_model=embedding_status,
            vector_store=vector_status,
            llm_api=llm_status,
        ),
    )
