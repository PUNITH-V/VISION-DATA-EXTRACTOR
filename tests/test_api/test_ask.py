"""
Tests for POST /api/ask (RAG endpoint).

Includes the critical isolation test: User A cannot retrieve
User B's data through the RAG pipeline.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import AuthenticatedUser
from api.server import create_app
from app.llm_client import LLMClientError


def _make_client(user_id: str) -> TestClient:
    app = create_app()
    from api.dependencies import get_current_user
    user = AuthenticatedUser(user_id=user_id)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _mock_store_with_data(user_id: str, report_id: str, filename: str) -> MagicMock:
    mock_store = MagicMock()
    mock_store.count.return_value = 1
    mock_store.search.return_value = {
        "ids": [[report_id]],
        "documents": [["Image description: GitHub logo with text GitHub."]],
        "metadatas": [[{
            "user_id": user_id,
            "report_id": report_id,
            "image_filename": filename,
            "confidence": "High",
        }]],
        "distances": [[0.18]],
    }
    return mock_store


class TestAskRequest:
    def test_empty_question_returns_422(self):
        client = _make_client("user-a")
        response = client.post("/api/ask", json={"question": ""})
        assert response.status_code == 422

    def test_missing_question_returns_422(self):
        client = _make_client("user-a")
        response = client.post("/api/ask", json={})
        assert response.status_code == 422

    def test_empty_index_returns_grounded_false(self):
        client = _make_client("user-a")

        with patch("api.services.rag_service.ChromaStore") as MockStore:
            mock_store = MagicMock()
            mock_store.count.return_value = 0
            MockStore.return_value = mock_store

            response = client.post("/api/ask", json={"question": "What is in my images?"})

        assert response.status_code == 200
        data = response.json()
        assert data["grounded"] is False
        assert data["sources"] == []


class TestAskResponse:
    def test_successful_answer_returns_sources(self):
        client = _make_client("user-a")

        with (
            patch("api.services.rag_service.ChromaStore") as MockStore,
            patch("api.services.rag_service.TextEmbedder") as MockEmbedder,
            patch("api.services.rag_service.LLMClient") as MockLLM,
        ):
            MockStore.return_value = _mock_store_with_data("user-a", "rep-001", "logo.jpg")
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384
            MockLLM.return_value.generate.return_value = (
                "The image shows a GitHub logo. Source: rep-001 (logo.jpg)"
            )

            response = client.post("/api/ask", json={"question": "What logo is shown?"})

        assert response.status_code == 200
        data = response.json()
        assert "GitHub" in data["answer"]
        assert len(data["sources"]) == 1
        assert data["sources"][0]["image_filename"] == "logo.jpg"

    def test_llm_error_returns_502(self):
        client = _make_client("user-a")

        with (
            patch("api.services.rag_service.ChromaStore") as MockStore,
            patch("api.services.rag_service.TextEmbedder") as MockEmbedder,
            patch("api.services.rag_service.LLMClient") as MockLLM,
        ):
            MockStore.return_value = _mock_store_with_data("user-a", "rep-001", "logo.jpg")
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384
            MockLLM.return_value.generate.side_effect = LLMClientError("Rate limit")

            response = client.post("/api/ask", json={"question": "What is in the image?"})

        assert response.status_code == 502
        assert "Rate limit" in response.json()["detail"]


class TestRAGIsolation:
    def test_user_a_cannot_retrieve_user_b_context(self):
        """
        Critical: RAG must not surface User B's document content to User A.

        We simulate ChromaStore returning a record tagged with user-b's
        user_id to user-a's query. The rag_service must suppress it,
        returning an empty-context response rather than passing B's data
        to the LLM.
        """
        client = _make_client("user-a")

        leaked_store = MagicMock()
        leaked_store.count.return_value = 1
        leaked_store.search.return_value = {
            "ids": [["rep-b-secret"]],
            "documents": [["User B's highly confidential invoice: Total: $999,000"]],
            "metadatas": [[{
                "user_id": "user-b",           # belongs to user-b, not user-a
                "report_id": "rep-b-secret",
                "image_filename": "secret_invoice.jpg",
                "confidence": "High",
            }]],
            "distances": [[0.05]],
        }

        with (
            patch("api.services.rag_service.ChromaStore", return_value=leaked_store),
            patch("api.services.rag_service.TextEmbedder") as MockEmbedder,
            patch("api.services.rag_service.LLMClient") as MockLLM,
        ):
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384

            response = client.post(
                "/api/ask",
                json={"question": "What are the invoice totals?"},
            )

        assert response.status_code == 200
        data = response.json()

        # The leaked context was suppressed, so no sources should appear.
        assert data["sources"] == [], (
            "User A should not see User B's sources in the RAG response. "
            f"Got sources: {data['sources']}"
        )

        # The LLM must not have been called with User B's confidential content.
        MockLLM.return_value.generate.assert_not_called(), (
            "The LLM must not receive User B's context when User A asks a question."
        )

        assert data["grounded"] is False, (
            "When all context is suppressed, grounded must be False."
        )
