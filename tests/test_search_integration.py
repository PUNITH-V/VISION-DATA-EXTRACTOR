"""Diagnostic: real ChromaDB + real TextEmbedder end-to-end search test."""

import json
import uuid
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.schemas import VisionExtractionReport, ExtractDataPoint
from app.ingestion import report_to_document
from embeddings.embedder import TextEmbedder
from vector_stores.chroma_store import ChromaStore


@pytest.fixture(scope="module")
def embedder():
    """Load the real embedding model once for all tests."""
    return TextEmbedder()


@pytest.fixture
def chroma_dir(tmp_path):
    """Create a temporary ChromaDB directory."""
    d = tmp_path / "chroma_test"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_report(
    description="A red sports car parked on a city street.",
    data=None,
    confidence="High",
):
    if data is None:
        data = [
            ExtractDataPoint(label="Vehicle Type", value="Sports Car"),
            ExtractDataPoint(label="Color", value="Red"),
            ExtractDataPoint(label="Location", value="City Street"),
        ]
    return VisionExtractionReport(
        image_description=description,
        extracted_data=data,
        confidence=confidence,
    )


class TestSearchPipelineIntegration:
    """Real ChromaDB + real embeddings — no mocks."""

    def test_document_text_is_meaningful(self):
        """The report_to_document function produces non-empty searchable text."""
        report = _make_report()
        doc = report_to_document(report)
        assert "Image description:" in doc
        assert "A red sports car" in doc
        assert "Vehicle Type: Sports Car" in doc
        assert "Color: Red" in doc
        assert len(doc.strip()) > 20

    def test_embedding_dimensions_match(self, embedder):
        """Both document and query embeddings have the same dimensions."""
        doc = report_to_document(_make_report())
        doc_emb = embedder.embed_text(doc)
        query_emb = embedder.embed_text("red car")
        assert len(doc_emb) == len(query_emb)
        assert len(doc_emb) == 384  # all-MiniLM-L6-v2

    def test_index_then_search_returns_results(self, embedder, chroma_dir):
        """The full pipeline: index a report, search, get results back."""
        report = _make_report()
        document = report_to_document(report)
        doc_embedding = embedder.embed_text(document)

        store = ChromaStore(persist_directory=str(chroma_dir))
        report_id = str(uuid.uuid4())
        user_id = "test-user-001"

        store.upsert_report(
            report_id=report_id,
            document=document,
            embedding=doc_embedding,
            metadata={
                "user_id": user_id,
                "image_filename": "red_car.jpg",
                "confidence": "High",
                "report_id": report_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert store.count() == 1

        # Search with a related query
        query = "red car on a street"
        query_embedding = embedder.embed_text(query)
        results = store.search(
            query_embedding=query_embedding,
            top_k=5,
            where={"user_id": user_id},
        )

        assert results["ids"][0], "Search should return at least one result"
        assert results["ids"][0][0] == report_id
        assert "red sports car" in results["documents"][0][0].lower()
        assert results["metadatas"][0][0]["user_id"] == user_id
        assert results["metadatas"][0][0]["image_filename"] == "red_car.jpg"

    def test_search_with_wrong_user_returns_empty(self, embedder, chroma_dir):
        """The where filter correctly isolates users."""
        report = _make_report()
        document = report_to_document(report)
        doc_embedding = embedder.embed_text(document)

        store = ChromaStore(persist_directory=str(chroma_dir))
        report_id = str(uuid.uuid4())

        store.upsert_report(
            report_id=report_id,
            document=document,
            embedding=doc_embedding,
            metadata={
                "user_id": "user-a",
                "image_filename": "car.jpg",
                "confidence": "High",
                "report_id": report_id,
                "created_at": "",
            },
        )

        query_embedding = embedder.embed_text("car")
        results = store.search(
            query_embedding=query_embedding,
            top_k=5,
            where={"user_id": "user-b"},  # wrong user
        )
        assert results["ids"][0] == [], "Wrong user should get no results"

    def test_search_after_recreate_store(self, embedder, chroma_dir):
        """Data persists across ChromaStore instances (simulates backend restart)."""
        report = _make_report()
        document = report_to_document(report)
        doc_embedding = embedder.embed_text(document)

        # First instance: index
        store1 = ChromaStore(persist_directory=str(chroma_dir))
        report_id = str(uuid.uuid4())
        store1.upsert_report(
            report_id=report_id,
            document=document,
            embedding=doc_embedding,
            metadata={
                "user_id": "persist-test",
                "image_filename": "test.jpg",
                "confidence": "High",
                "report_id": report_id,
                "created_at": "",
            },
        )
        assert store1.count() == 1

        # Second instance: search (simulates restart)
        store2 = ChromaStore(persist_directory=str(chroma_dir))
        assert store2.count() == 1, "Data must persist across ChromaStore instances"

        query_embedding = embedder.embed_text("red car")
        results = store2.search(
            query_embedding=query_embedding,
            top_k=5,
            where={"user_id": "persist-test"},
        )
        assert results["ids"][0], "Search should find the persisted record"
        assert results["ids"][0][0] == report_id

    def test_search_empty_collection_returns_empty(self, embedder, chroma_dir):
        """An empty collection returns empty results, not an error."""
        store = ChromaStore(persist_directory=str(chroma_dir))
        assert store.count() == 0

        query_embedding = embedder.embed_text("anything")
        results = store.search(
            query_embedding=query_embedding,
            top_k=5,
            where={"user_id": "nobody"},
        )
        assert results["ids"][0] == []
