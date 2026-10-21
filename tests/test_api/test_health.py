"""
Tests for GET /api/health.

Health is the only unauthenticated endpoint in Stage 2.
We test both the happy path and the degraded path.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.server import create_app

client = TestClient(create_app())


def test_health_returns_200():
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_response_structure():
    response = client.get("/api/health")
    data = response.json()
    assert "status" in data
    assert "services" in data
    services = data["services"]
    assert "embedding_model" in services
    assert "vector_store" in services
    assert "llm_api" in services


def test_health_ok_when_all_services_ready(tmp_path, monkeypatch):
    """If the embedding model loads and ChromaDB dir is accessible, status is ok."""
    monkeypatch.setenv("CHROMA_BASE_DIR", str(tmp_path))

    # TextEmbedder is imported inside the route function body (lazy import),
    # so we patch it at the embedder module level.
    with patch("embeddings.embedder.SentenceTransformer"):
        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    # LLM API key is set (from .env loaded by settings), so llm_api should be configured.
    assert data["services"]["llm_api"] == "configured"


def test_health_degraded_when_embedding_model_fails():
    """A broken embedding import degrades the status without crashing."""
    # Patch SentenceTransformer (loaded inside TextEmbedder.__init__) to raise.
    with patch(
        "embeddings.embedder.SentenceTransformer",
        side_effect=RuntimeError("model load failed"),
    ):
        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["services"]["embedding_model"] == "unavailable"
