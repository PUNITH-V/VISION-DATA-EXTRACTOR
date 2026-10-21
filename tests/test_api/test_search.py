"""
Tests for POST /api/search.

Critically includes a test proving User A cannot retrieve User B's
search results, even if both users have indexed data.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import AuthenticatedUser
from api.server import create_app


def _make_client(user_id: str) -> TestClient:
    app = create_app()
    from api.dependencies import get_current_user
    user = AuthenticatedUser(user_id=user_id)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _mock_search_result(user_id: str, report_id: str, filename: str) -> dict:
    """Build the dict returned by ChromaStore.search()."""
    return {
        "ids": [[report_id]],
        "documents": [["Image description: something relevant."]],
        "metadatas": [[{
            "user_id": user_id,
            "report_id": report_id,
            "image_filename": filename,
            "confidence": "High",
        }]],
        "distances": [[0.15]],
    }


class TestSearchRequest:
    def test_empty_query_returns_422(self):
        client = _make_client("user-a")
        response = client.post("/api/search", json={"query": ""})
        assert response.status_code == 422

    def test_top_k_above_max_returns_422(self):
        client = _make_client("user-a")
        response = client.post("/api/search", json={"query": "invoices", "top_k": 100})
        assert response.status_code == 422

    def test_valid_search_returns_200(self):
        client = _make_client("user-a")

        with (
            patch("api.services.search_service.ChromaStore") as MockStore,
            patch("api.services.search_service.TextEmbedder") as MockEmbedder,
        ):
            mock_store = MagicMock()
            mock_store.count.return_value = 1
            mock_store.search.return_value = _mock_search_result(
                "user-a", "rep-001", "invoice.jpg"
            )
            MockStore.return_value = mock_store
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384

            response = client.post("/api/search", json={"query": "invoices"})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["image_filename"] == "invoice.jpg"

    def test_cosine_distance_field_present(self):
        client = _make_client("user-a")

        with (
            patch("api.services.search_service.ChromaStore") as MockStore,
            patch("api.services.search_service.TextEmbedder") as MockEmbedder,
        ):
            mock_store = MagicMock()
            mock_store.count.return_value = 1
            mock_store.search.return_value = _mock_search_result(
                "user-a", "rep-001", "receipt.jpg"
            )
            MockStore.return_value = mock_store
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384

            response = client.post("/api/search", json={"query": "receipts"})

        result = response.json()["results"][0]
        assert "cosine_distance" in result
        assert isinstance(result["cosine_distance"], float)

    def test_empty_index_returns_empty_results(self):
        client = _make_client("user-a")

        with patch("api.services.search_service.ChromaStore") as MockStore:
            mock_store = MagicMock()
            mock_store.count.return_value = 0
            MockStore.return_value = mock_store

            response = client.post("/api/search", json={"query": "anything"})

        assert response.status_code == 200
        assert response.json()["results"] == []
        assert response.json()["total"] == 0


class TestSearchIsolation:
    def test_user_a_cannot_see_user_b_results(self):
        """
        This is a critical isolation test.

        User B's vector is stored with user_id='user-b' in metadata.
        User A searches for the same query.
        The ChromaDB `where` filter must ensure User A's query
        only returns User A's data.

        We simulate this by making ChromaStore.search return
        a result tagged with user-b's user_id when queried as user-a
        (simulating a misconfigured or unfiltered store), then verify
        the search service suppresses it.
        """
        client = _make_client("user-a")

        # Simulate a store that "leaked" User B's result to User A.
        leaked_result = {
            "ids": [["rep-b-999"]],
            "documents": [["User B's private invoice data."]],
            "metadatas": [[{
                "user_id": "user-b",           # WRONG user — should be suppressed
                "report_id": "rep-b-999",
                "image_filename": "user_b_invoice.jpg",
                "confidence": "High",
            }]],
            "distances": [[0.05]],
        }

        with (
            patch("api.services.search_service.ChromaStore") as MockStore,
            patch("api.services.search_service.TextEmbedder") as MockEmbedder,
        ):
            mock_store = MagicMock()
            mock_store.count.return_value = 1
            mock_store.search.return_value = leaked_result
            MockStore.return_value = mock_store
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384

            response = client.post("/api/search", json={"query": "invoices"})

        assert response.status_code == 200
        data = response.json()

        # The leaked result must be suppressed by the isolation check.
        assert data["total"] == 0, (
            "User A should see 0 results when the only match belongs to User B. "
            f"Got: {data}"
        )
        filenames = [r["image_filename"] for r in data["results"]]
        assert "user_b_invoice.jpg" not in filenames, (
            "User B's filename must never appear in User A's search results."
        )
