"""
Tests for DELETE /api/reports/{report_id}.

Updated for the new 200+JSON response format (was 204+empty).

Covers:
  - Successful deletion returns 200 with deleted=True.
  - Deletion of an indexed report also calls ChromaDB delete.
  - Attempting to delete a non-existent report returns 404.
  - User A cannot delete User B's report (ownership isolation).
  - Deletion is idempotent: second call returns 404.
  - ChromaDB failure is reported honestly (vector_cleaned=False) but
    does not prevent JSON file deletion.
  - Path-traversal strings return 404 (not 500 or 200).
  - Malformed / non-UUID IDs return 404.
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
)

_USER_A = "aaaaaaaa-1111-4000-8000-aaaaaaaaaaaa"
_USER_B = "bbbbbbbb-2222-4000-8000-bbbbbbbbbbbb"


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_client(user_id: str) -> TestClient:
    app = create_app()
    from api.dependencies import get_current_user
    with patch("api.dependencies.AUTH_ENABLED", True):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(user_id=user_id)
    return TestClient(app, raise_server_exceptions=True)


def _write_report(base: Path, user_id: str, indexed: bool = False) -> str:
    rid = str(uuid.uuid4())
    d = base / user_id
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        _REPORT_ID_KEY: rid,
        _FILENAME_KEY: "test.jpg",
        _CREATED_AT_KEY: datetime.now(timezone.utc).isoformat(),
        _INDEX_FLAG_KEY: indexed,
        "image_description": "A test image.",
        "extracted_data": [{"label": "Key", "value": "Val"}],
        "confidence": "High",
    }
    (d / f"{rid}.json").write_text(json.dumps(payload), encoding="utf-8")
    return rid


# ── core deletion tests ───────────────────────────────────────────────────────

class TestDeleteReport:

    def test_delete_existing_report_returns_200_with_body(self, tmp_path):
        rid = _write_report(tmp_path, _USER_A)
        client = _make_client(_USER_A)

        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            resp = client.delete(f"/api/reports/{rid}")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["deleted"] is True
        assert data["vector_cleaned"] is True

    def test_delete_removes_json_file(self, tmp_path):
        rid = _write_report(tmp_path, _USER_A)
        report_path = tmp_path / _USER_A / f"{rid}.json"
        assert report_path.exists()

        client = _make_client(_USER_A)
        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            client.delete(f"/api/reports/{rid}")

        assert not report_path.exists(), "JSON file must be deleted after DELETE request"

    def test_delete_indexed_report_calls_chroma_delete(self, tmp_path):
        rid = _write_report(tmp_path, _USER_A, indexed=True)
        client = _make_client(_USER_A)

        mock_store = MagicMock()
        mock_store.delete_report.return_value = None

        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
            patch("api.routes.reports.ChromaStore", return_value=mock_store),
        ):
            resp = client.delete(f"/api/reports/{rid}")

        assert resp.status_code == 200
        assert resp.json()["vector_cleaned"] is True
        mock_store.delete_report.assert_called_once_with(rid)

    def test_delete_unindexed_report_does_not_call_chroma(self, tmp_path):
        rid = _write_report(tmp_path, _USER_A, indexed=False)
        client = _make_client(_USER_A)

        mock_store = MagicMock()
        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            resp = client.delete(f"/api/reports/{rid}")

        assert resp.status_code == 200
        assert resp.json()["vector_cleaned"] is True  # nothing to clean
        mock_store.delete_report.assert_not_called()

    def test_delete_nonexistent_report_returns_404(self, tmp_path):
        client = _make_client(_USER_A)
        fake_id = str(uuid.uuid4())

        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            resp = client.delete(f"/api/reports/{fake_id}")

        assert resp.status_code == 404

    def test_delete_is_idempotent_second_call_returns_404(self, tmp_path):
        rid = _write_report(tmp_path, _USER_A)
        client = _make_client(_USER_A)

        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            first  = client.delete(f"/api/reports/{rid}")
            second = client.delete(f"/api/reports/{rid}")

        assert first.status_code  == 200
        assert second.status_code == 404, "Second DELETE must return 404 — report is gone"

    def test_user_a_cannot_delete_user_b_report(self, tmp_path):
        """Ownership isolation: User A gets 404 when trying to delete User B's report."""
        rid = _write_report(tmp_path, _USER_B)
        client_a = _make_client(_USER_A)

        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            resp = client_a.delete(f"/api/reports/{rid}")

        assert resp.status_code == 404, (
            f"User A must get 404, not {resp.status_code}, "
            "when attempting to delete User B's report."
        )
        assert (tmp_path / _USER_B / f"{rid}.json").exists(), (
            "User B's report must not be deleted by User A's request."
        )


# ── deletion-consistency tests ────────────────────────────────────────────────

class TestDeletionConsistency:

    def test_chroma_failure_still_deletes_json(self, tmp_path):
        """
        If ChromaDB deletion fails, the JSON file is still deleted and the
        response honestly reports vector_cleaned=False with a detail message.
        """
        rid = _write_report(tmp_path, _USER_A, indexed=True)
        report_path = tmp_path / _USER_A / f"{rid}.json"
        client = _make_client(_USER_A)

        mock_store = MagicMock()
        mock_store.delete_report.side_effect = RuntimeError("ChromaDB unavailable")

        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
            patch("api.routes.reports.ChromaStore", return_value=mock_store),
        ):
            resp = client.delete(f"/api/reports/{rid}")

        assert resp.status_code == 200, (
            f"ChromaDB failure must not block deletion, got {resp.status_code}"
        )
        assert not report_path.exists(), (
            "JSON file must be deleted even when ChromaDB fails"
        )
        data = resp.json()
        assert data["deleted"] is True
        assert data["vector_cleaned"] is False, (
            "Response must honestly report that vector cleanup failed"
        )
        assert data["detail"] is not None, (
            "A warning detail message must be included when vector cleanup fails"
        )
        assert "search" in data["detail"].lower() or "vector" in data["detail"].lower(), (
            "Detail should mention the search/vector impact"
        )

    def test_chroma_failure_response_does_not_claim_complete_deletion(self, tmp_path):
        """
        The response MUST NOT claim vector_cleaned=True when ChromaDB failed.
        This is the core honesty requirement for deletion consistency.
        """
        rid = _write_report(tmp_path, _USER_A, indexed=True)
        client = _make_client(_USER_A)

        mock_store = MagicMock()
        mock_store.delete_report.side_effect = Exception("any error")

        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
            patch("api.routes.reports.ChromaStore", return_value=mock_store),
        ):
            resp = client.delete(f"/api/reports/{rid}")

        assert resp.status_code == 200
        assert resp.json()["vector_cleaned"] is not True, (
            "CRITICAL: vector_cleaned must be False when ChromaDB deletion failed. "
            "Claiming True would silently leave an orphaned vector."
        )


# ── path traversal and UUID validation tests ─────────────────────────────────

class TestPathTraversalPrevention:
    """
    Regression tests for the path traversal vulnerability where a
    client-supplied report_id containing path separators could escape
    the user's report directory.
    """

    @pytest.mark.parametrize("malicious_id", [
        "../../etc/passwd",
        "../other-user-uuid/victim-report-id",
        "../../root/.ssh/id_rsa",
        "%2e%2e%2fetc%2fpasswd",        # URL-encoded ../
        "....//....//etc//passwd",
        "/etc/passwd",
        "C:\\Windows\\System32",
        "a/b",
        "./local",
        "../sibling",
        # Note: null-byte (\x00) is rejected by HTTP client before reaching server.
        # Note: empty string ("") routes to DELETE /api/reports/ → 405 (no route),
        #       which is also safe; not included here as it tests a different endpoint.
    ])
    def test_traversal_string_returns_404_not_500(self, malicious_id, tmp_path):
        """
        Path traversal strings must return 404, never 500 or 200.
        A 500 would indicate the traversal reached the filesystem.
        """
        client = _make_client(_USER_A)

        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            resp = client.delete(f"/api/reports/{malicious_id}")

        assert resp.status_code in (404, 422), (
            f"Traversal string {malicious_id!r} returned {resp.status_code} — "
            f"must be 404 or 422, never 200 or 500."
        )
        assert resp.status_code != 200
        assert resp.status_code != 500

    @pytest.mark.parametrize("bad_id", [
        "not-a-uuid",
        "12345",
        "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "00000000000040008000000000000000",   # no hyphens
        "{}",
        "<script>alert(1)</script>",
        "a" * 1000,
    ])
    def test_malformed_uuid_returns_404(self, bad_id, tmp_path):
        """Non-UUID report IDs must return 404, not 500."""
        client = _make_client(_USER_A)

        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            resp = client.delete(f"/api/reports/{bad_id}")

        assert resp.status_code in (404, 422), (
            f"Malformed ID {bad_id!r} returned {resp.status_code} — "
            f"expected 404 or 422."
        )
        assert resp.status_code != 500

    def test_traversal_does_not_expose_filesystem_path_in_error(self, tmp_path):
        """
        Error responses for traversal attempts must not include filesystem paths.
        """
        client = _make_client(_USER_A)

        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            resp = client.delete("/api/reports/../../etc/passwd")

        body = resp.text.lower()
        assert str(tmp_path).lower() not in body, (
            "Filesystem path must not appear in error response"
        )
        assert "etc/passwd" not in body, (
            "Traversal target must not appear in error response"
        )

    def test_valid_uuid_for_nonexistent_report_returns_404(self, tmp_path):
        """A valid UUID for a report that doesn't exist returns 404."""
        client = _make_client(_USER_A)
        valid_uuid = str(uuid.uuid4())

        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            resp = client.delete(f"/api/reports/{valid_uuid}")

        assert resp.status_code == 404


# ── GET endpoint traversal tests ─────────────────────────────────────────────

class TestGetReportTraversalPrevention:
    """Same protections for GET /api/reports/{report_id}."""

    @pytest.mark.parametrize("malicious_id", [
        "../../etc/passwd",
        "../other-user/report",
        "/absolute/path",
        "a/b/c",
    ])
    def test_traversal_on_get_returns_404(self, malicious_id, tmp_path):
        client = _make_client(_USER_A)

        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            resp = client.get(f"/api/reports/{malicious_id}")

        assert resp.status_code in (404, 422), (
            f"GET traversal {malicious_id!r} returned {resp.status_code}"
        )
        assert resp.status_code != 500


# ── Ingestion traversal tests ─────────────────────────────────────────────────

class TestIngestionTraversalPrevention:
    """Traversal strings in POST /api/ingestion report_ids must be skipped."""

    def test_traversal_in_ingestion_report_ids_is_skipped(self, tmp_path):
        """
        Passing a traversal string in report_ids must not reach the filesystem.
        The invalid ID must be counted as skipped, not cause a 500.
        """
        from api.server import create_app as _create_app
        app = _create_app()
        from api.dependencies import get_current_user
        with patch("api.dependencies.AUTH_ENABLED", True):
            app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(user_id=_USER_A)
        client = TestClient(app, raise_server_exceptions=True)

        # The traversal ID and the legitimate UUID are both submitted
        legitimate_uuid = str(uuid.uuid4())  # doesn't exist, will be skipped as not-found
        traversal_id = "../../etc/passwd"

        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
            patch("api.services.ingestion_service.TextEmbedder"),
            patch("api.services.ingestion_service.ChromaStore"),
        ):
            resp = client.post(
                "/api/ingestion",
                json={"report_ids": [traversal_id, legitimate_uuid]},
            )

        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        data = resp.json()
        # The traversal ID must be counted as skipped, not cause a failure
        assert data["skipped"] >= 1, (
            "Traversal ID must be counted as skipped, not cause a pipeline failure"
        )
        assert data["failed"] == 0, (
            "Traversal ID must not count as a pipeline failure"
        )

    @pytest.mark.parametrize("bad_id", [
        "../../secret",
        "../other-user/report",
        "not-a-uuid",
    ])
    def test_invalid_ids_in_ingestion_are_skipped_not_500(self, bad_id, tmp_path):
        from api.server import create_app as _create_app
        app = _create_app()
        from api.dependencies import get_current_user
        with patch("api.dependencies.AUTH_ENABLED", True):
            app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(user_id=_USER_A)
        client = TestClient(app, raise_server_exceptions=True)

        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
            patch("api.services.ingestion_service.TextEmbedder"),
            patch("api.services.ingestion_service.ChromaStore"),
        ):
            resp = client.post(
                "/api/ingestion",
                json={"report_ids": [bad_id]},
            )

        assert resp.status_code == 200
        assert resp.status_code != 500
