"""
Tests for GET /api/reports and GET /api/reports/{report_id}.

Uses a temporary directory to exercise the real report_service
without touching the project's actual output/ directory.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

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


def _make_report_payload(
    report_id: str,
    filename: str = "test.jpg",
    confidence: str = "High",
    indexed: bool = False,
) -> dict:
    return {
        _REPORT_ID_KEY: report_id,
        _FILENAME_KEY: filename,
        _CREATED_AT_KEY: datetime.now(timezone.utc).isoformat(),
        _INDEX_FLAG_KEY: indexed,
        "image_description": "A test image.",
        "extracted_data": [{"label": "Text", "value": "Hello"}],
        "confidence": confidence,
    }


def _write_report(directory: Path, report_id: str, payload: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _make_client(user_id: str) -> TestClient:
    app = create_app()
    from api.dependencies import get_current_user
    user = AuthenticatedUser(user_id=user_id)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestListReports:
    def test_returns_empty_list_for_new_user(self, tmp_path):
        client = _make_client("user-a")
        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            response = client.get("/api/reports")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_own_reports_only(self, tmp_path):
        """User A's reports should not include User B's."""
        # Write User A's report
        _write_report(
            tmp_path / "user-a",
            "report-001",
            _make_report_payload("report-001"),
        )
        # Write User B's report
        _write_report(
            tmp_path / "user-b",
            "report-999",
            _make_report_payload("report-999", filename="other.jpg"),
        )

        client = _make_client("user-a")
        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            response = client.get("/api/reports")

        assert response.status_code == 200
        data = response.json()

        # User A sees exactly one report.
        assert len(data) == 1
        assert data[0]["report_id"] == "report-001"

        # User B's filename does not appear in User A's results.
        filenames = [r["image_filename"] for r in data]
        assert "other.jpg" not in filenames

    def test_report_summary_fields(self, tmp_path):
        _write_report(
            tmp_path / "user-x",
            "rep-42",
            _make_report_payload("rep-42", confidence="Medium", indexed=True),
        )

        client = _make_client("user-x")
        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            response = client.get("/api/reports")

        assert response.status_code == 200
        report = response.json()[0]

        assert report["report_id"] == "rep-42"
        assert report["confidence"] == "Medium"
        assert report["indexed"] is True
        assert report["field_count"] == 1


class TestGetReport:
    def test_own_report_returns_200(self, tmp_path):
        # Use a proper UUID-format report_id (the fix now requires this)
        report_id = "77777777-0000-4000-8000-777777777777"
        _write_report(
            tmp_path / "user-b",
            report_id,
            _make_report_payload(report_id),
        )

        client = _make_client("user-b")
        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            response = client.get(f"/api/reports/{report_id}")

        assert response.status_code == 200
        assert response.json()["report_id"] == report_id

    def test_missing_report_returns_404(self, tmp_path):
        import uuid as _uuid
        client = _make_client("user-c")
        valid_missing_uuid = str(_uuid.uuid4())
        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            response = client.get(f"/api/reports/{valid_missing_uuid}")
        assert response.status_code == 404

    def test_other_users_report_returns_404(self, tmp_path):
        """
        User A requests User B's report_id using a syntactically valid UUID.
        The request passes UUID validation and reaches the ownership check,
        where it must return 404 because the report lives in User B's directory.
        This confirms that isolation is enforced at the ownership layer,
        not merely at format validation.
        """
        # Use a stable UUID that is syntactically valid so UUID validation passes.
        user_b_report_id = "bbbb0000-0000-4000-8000-bbbbbbbbbbbb"

        # Write the report into User B's directory only.
        _write_report(
            tmp_path / "user-b",
            user_b_report_id,
            _make_report_payload(user_b_report_id),
        )

        # User A requests User B's report ID — must be 404 at the ownership check.
        client = _make_client("user-a")
        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            response = client.get(f"/api/reports/{user_b_report_id}")

        assert response.status_code == 404, (
            "User A should NOT be able to access User B's report. "
            f"Got {response.status_code}: {response.text}"
        )
