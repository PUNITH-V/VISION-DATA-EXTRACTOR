"""
Tests for POST /api/extractions.

Because AUTH_ENABLED=false in Stage 2, these tests mock the auth
dependency to inject a fake authenticated user, letting us test
the extraction logic without a real Supabase token.

This is the correct pattern: test the route logic independently
from the auth mechanism, which has its own tests.
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import AuthenticatedUser
from api.server import create_app
from api.services.extraction_service import (
    ExtractionUpstreamError,
    ExtractionValidationError,
)
from app.schemas import ExtractDataPoint, VisionExtractionReport


FAKE_USER = AuthenticatedUser(user_id="user-test-001", email="test@example.com")

VALID_REPORT = VisionExtractionReport(
    image_description="A GitHub logo on a white background.",
    extracted_data=[ExtractDataPoint(label="Text", value="GitHub")],
    confidence="High",
)


def _make_client_with_fake_auth() -> TestClient:
    """Create a TestClient with the auth dependency overridden."""
    app = create_app()
    from api.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    return TestClient(app)


# ── Valid upload ─────────────────────────────────────────────────────────────

def test_valid_jpeg_upload_returns_201(tmp_path):
    client = _make_client_with_fake_auth()

    with (
        patch("api.routes.extractions.extract_from_bytes", return_value=VALID_REPORT),
        patch("api.routes.extractions.save_report") as mock_save,
    ):
        from datetime import datetime, timezone
        from api.schemas import ExtractionResponse, ExtractedField
        mock_save.return_value = ExtractionResponse(
            report_id="abc-123",
            image_filename="test.jpg",
            image_description=VALID_REPORT.image_description,
            extracted_data=[ExtractedField(label="Text", value="GitHub")],
            confidence="High",
            created_at=datetime.now(timezone.utc),
        )

        response = client.post(
            "/api/extractions",
            files={"file": ("test.jpg", io.BytesIO(b"fake-image"), "image/jpeg")},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["report_id"] == "abc-123"
    assert data["confidence"] == "High"


# ── Content-type validation ───────────────────────────────────────────────────

@pytest.mark.parametrize("content_type", ["image/gif", "application/pdf", "text/plain"])
def test_unsupported_content_type_returns_400(content_type):
    client = _make_client_with_fake_auth()

    response = client.post(
        "/api/extractions",
        files={"file": ("bad.gif", io.BytesIO(b"data"), content_type)},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


# ── Extraction errors ─────────────────────────────────────────────────────────

def test_image_validation_failure_returns_400():
    client = _make_client_with_fake_auth()

    with patch(
        "api.routes.extractions.extract_from_bytes",
        side_effect=ExtractionValidationError("Image validation failed: corrupt PNG"),
    ):
        response = client.post(
            "/api/extractions",
            files={"file": ("bad.png", io.BytesIO(b"not an image"), "image/png")},
        )

    assert response.status_code == 400
    assert "corrupt PNG" in response.json()["detail"]


def test_upstream_api_error_returns_502():
    client = _make_client_with_fake_auth()

    with patch(
        "api.routes.extractions.extract_from_bytes",
        side_effect=ExtractionUpstreamError("Rate limit reached"),
    ):
        response = client.post(
            "/api/extractions",
            files={"file": ("img.jpg", io.BytesIO(b"data"), "image/jpeg")},
        )

    assert response.status_code == 502
    assert "Rate limit" in response.json()["detail"]


def test_model_validation_failure_returns_422():
    client = _make_client_with_fake_auth()

    with patch(
        "api.routes.extractions.extract_from_bytes",
        side_effect=ValueError("Schema validation failed: confidence must be High/Medium/Low"),
    ):
        response = client.post(
            "/api/extractions",
            files={"file": ("img.jpg", io.BytesIO(b"data"), "image/jpeg")},
        )

    assert response.status_code == 422
