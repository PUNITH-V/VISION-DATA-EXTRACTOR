"""
Tests for deferred indexing, idempotent indexing, and duplicate recovery.

These tests exercise:
  1. Indexing a saved report by its report_id (deferred — after leaving the page).
  2. Idempotency: indexing the same report twice is safe (already_indexed count
     increases, ingested count stays at 0, no duplicate vectors).
  3. Ingesting a report_ids list containing a non-owned ID silently skips it
     (covered by the existing cross-user isolation tests in test_auth.py).
  4. POST /api/ingestion without a body indexes all unindexed reports.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import AuthenticatedUser
from api.server import create_app
from api.services.report_service import (
    _REPORT_ID_KEY,
    _FILENAME_KEY,
    _INDEX_FLAG_KEY,
    _CREATED_AT_KEY,
    _ensure_user_report_dir,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

_TEST_USER_ID = "cccccccc-0000-4000-8000-cccccccccccc"


def _make_client(user_id: str = _TEST_USER_ID) -> TestClient:
    app = create_app()
    from api.dependencies import get_current_user
    with patch("api.dependencies.AUTH_ENABLED", True):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(user_id=user_id)
    return TestClient(app, raise_server_exceptions=True)


def _write_report(
    base_dir: Path,
    user_id: str,
    filename: str = "test.jpg",
    confidence: str = "High",
    indexed: bool = False,
) -> str:
    """Write a minimal valid report file and return its report_id."""
    report_id = str(uuid.uuid4())
    user_dir = base_dir / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        _REPORT_ID_KEY:  report_id,
        _FILENAME_KEY:   filename,
        _CREATED_AT_KEY: datetime.now(timezone.utc).isoformat(),
        _INDEX_FLAG_KEY: indexed,
        "image_description": "A test image.",
        "extracted_data": [{"label": "Test", "value": "Value"}],
        "confidence":    confidence,
    }
    (user_dir / f"{report_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    return report_id


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDeferredIndexing:
    """A report can be indexed after the extraction session has ended."""

    def test_index_saved_report_by_id_succeeds(self, tmp_path):
        """
        POST /api/ingestion with a specific report_id that exists in the
        user's directory should successfully ingest it into ChromaDB.
        """
        report_id = _write_report(tmp_path, _TEST_USER_ID)
        client = _make_client()

        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
            patch("api.services.ingestion_service.TextEmbedder") as MockEmbedder,
            patch("api.services.ingestion_service.ChromaStore") as MockStore,
        ):
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384
            MockStore.return_value.upsert_report.return_value = None

            response = client.post(
                "/api/ingestion",
                json={"report_ids": [report_id]},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["ingested"] == 1, f"Expected 1 ingested, got {data}"
        assert data["failed"] == 0

    def test_index_all_unindexed_reports(self, tmp_path):
        """
        POST /api/ingestion with no body indexes all unindexed reports for the user.
        """
        # Write two unindexed and one already-indexed report
        id1 = _write_report(tmp_path, _TEST_USER_ID, filename="img1.jpg", indexed=False)
        id2 = _write_report(tmp_path, _TEST_USER_ID, filename="img2.jpg", indexed=False)
        _write_report(tmp_path, _TEST_USER_ID, filename="img3.jpg", indexed=True)

        client = _make_client()

        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
            patch("api.services.ingestion_service.TextEmbedder") as MockEmbedder,
            patch("api.services.ingestion_service.ChromaStore") as MockStore,
        ):
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384
            MockStore.return_value.upsert_report.return_value = None

            response = client.post("/api/ingestion")  # no body

        assert response.status_code == 200
        data = response.json()
        assert data["discovered"] == 3
        assert data["ingested"] == 2
        assert data["already_indexed"] == 1


class TestIdempotentIndexing:
    """Indexing the same report twice is safe and does not create duplicates."""

    def test_re_indexing_increments_already_indexed_not_ingested(self, tmp_path):
        """
        Indexing a report whose _indexed flag is True increments already_indexed,
        NOT ingested. No second call to upsert_report is made.
        """
        report_id = _write_report(tmp_path, _TEST_USER_ID, indexed=True)
        client = _make_client()

        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
            patch("api.services.ingestion_service.TextEmbedder") as MockEmbedder,
            patch("api.services.ingestion_service.ChromaStore") as MockStore,
        ):
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384

            response = client.post(
                "/api/ingestion",
                json={"report_ids": [report_id]},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["already_indexed"] == 1
        assert data["ingested"] == 0
        # ChromaDB upsert must NOT be called for an already-indexed report
        MockStore.return_value.upsert_report.assert_not_called()

    def test_chromadb_upsert_is_idempotent(self, tmp_path):
        """
        ChromaStore.upsert_report uses ChromaDB's upsert (not insert), so
        calling it twice with the same report_id updates the record safely.
        Verify the service calls upsert_report exactly once per new ingestion.
        """
        report_id = _write_report(tmp_path, _TEST_USER_ID, indexed=False)
        client = _make_client()

        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
            patch("api.services.ingestion_service.TextEmbedder") as MockEmbedder,
            patch("api.services.ingestion_service.ChromaStore") as MockStore,
        ):
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384
            MockStore.return_value.upsert_report.return_value = None

            r = client.post("/api/ingestion", json={"report_ids": [report_id]})
            assert r.json()["ingested"] == 1
            MockStore.return_value.upsert_report.assert_called_once()

            # Now the _indexed flag is True — second call must NOT re-upsert
            r2 = client.post("/api/ingestion", json={"report_ids": [report_id]})
            assert r2.json()["already_indexed"] == 1
            # Still only called once total
            MockStore.return_value.upsert_report.assert_called_once()


class TestIndexingStatusInReports:
    """GET /api/reports returns accurate indexed flag for each report."""

    def test_unindexed_report_shows_indexed_false(self, tmp_path):
        _write_report(tmp_path, _TEST_USER_ID, indexed=False)
        client = _make_client()

        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            response = client.get("/api/reports")

        assert response.status_code == 200
        reports = response.json()
        assert len(reports) == 1
        assert reports[0]["indexed"] is False

    def test_indexed_report_shows_indexed_true(self, tmp_path):
        _write_report(tmp_path, _TEST_USER_ID, indexed=True)
        client = _make_client()

        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            response = client.get("/api/reports")

        assert response.status_code == 200
        reports = response.json()
        assert len(reports) == 1
        assert reports[0]["indexed"] is True

    def test_indexed_flag_updates_after_ingestion(self, tmp_path):
        """After a successful ingestion the _indexed flag on disk becomes True."""
        report_id = _write_report(tmp_path, _TEST_USER_ID, indexed=False)
        client = _make_client()

        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
            patch("api.services.ingestion_service.TextEmbedder") as MockEmbedder,
            patch("api.services.ingestion_service.ChromaStore") as MockStore,
        ):
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384
            MockStore.return_value.upsert_report.return_value = None

            client.post("/api/ingestion", json={"report_ids": [report_id]})

        # Check the persisted JSON on disk
        report_path = tmp_path / _TEST_USER_ID / f"{report_id}.json"
        saved = json.loads(report_path.read_text(encoding="utf-8"))
        assert saved[_INDEX_FLAG_KEY] is True, (
            "The _indexed flag must be set to True in the persisted JSON after ingestion."
        )
