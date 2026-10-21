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
        _write_report(
            tmp_path / "user-b",
            "rep-77",
            _make_report_payload("rep-77"),
        )

        client = _make_client("user-b")
        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            response = client.get("/api/reports/rep-77")

        assert response.status_code == 200
        assert response.json()["report_id"] == "rep-77"

    def test_missing_report_returns_404(self, tmp_path):
        client = _make_client("user-c")
        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            response = client.get("/api/reports/does-not-exist")
        assert response.status_code == 404

    def test_other_users_report_returns_404(self, tmp_path):
        """
        User A requests User B's report_id.
        Because User A's directory does not contain it, the result is 404.
        This avoids confirming the existence of records belonging to others.
        """
        # Write report only in User B's directory.
        _write_report(
            tmp_path / "user-b",
            "secret-report",
            _make_report_payload("secret-report"),
        )

        # User A tries to access User B's report ID.
        client = _make_client("user-a")
        with patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path):
            response = client.get("/api/reports/secret-report")

        assert response.status_code == 404, (
            "User A should NOT be able to access User B's report. "
            f"Got {response.status_code}: {response.text}"
        )
