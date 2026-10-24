"""
Tests that every protected endpoint returns 503 in Stage 2
(AUTH_ENABLED=false) and never exposes data without authentication.

These tests explicitly force AUTH_ENABLED=False so they remain valid
regardless of what is set in .env. They verify the Stage 2 guard logic,
not the live deployment configuration.
"""

import io
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from api.server import create_app

# All protected endpoints that must NOT be accessible when AUTH_ENABLED=false.
PROTECTED_ENDPOINTS: list[tuple[str, str, dict]] = [
    ("POST", "/api/extractions", {}),
    ("GET",  "/api/reports",     {}),
    ("GET",  "/api/reports/some-id", {}),
    ("POST", "/api/ingestion",   {}),
    ("POST", "/api/search",      {"json": {"query": "test"}}),
    ("POST", "/api/ask",         {"json": {"question": "test"}}),
]


def _client_with_auth_disabled():
    """Create a TestClient with AUTH_ENABLED explicitly patched to False."""
    app = create_app()
    with patch("api.dependencies.AUTH_ENABLED", False):
        return TestClient(app)


@pytest.mark.parametrize("method,path,kwargs", PROTECTED_ENDPOINTS)
def test_protected_endpoint_returns_503_without_auth(method, path, kwargs):
    """
    When AUTH_ENABLED=false, protected endpoints must return
    503 Service Unavailable — not 200, 401, or any data.
    """
    app = create_app()
    with patch("api.dependencies.AUTH_ENABLED", False):
        client = TestClient(app)
        response = client.request(method, path, **kwargs)
    assert response.status_code == 503, (
        f"{method} {path} should return 503 when AUTH_ENABLED=false, "
        f"got {response.status_code}: {response.text}"
    )


@pytest.mark.parametrize("method,path,kwargs", PROTECTED_ENDPOINTS)
def test_protected_endpoint_includes_stage3_message(method, path, kwargs):
    """The 503 response body must mention Stage 3 so developers understand why."""
    app = create_app()
    with patch("api.dependencies.AUTH_ENABLED", False):
        client = TestClient(app)
        response = client.request(method, path, **kwargs)
    body = response.json()
    assert "Stage 3" in body.get("detail", ""), (
        f"503 response for {method} {path} should mention 'Stage 3', "
        f"got: {body}"
    )


def test_health_is_not_protected():
    """Health endpoint must remain accessible without authentication."""
    app = create_app()
    with patch("api.dependencies.AUTH_ENABLED", False):
        client = TestClient(app)
        response = client.get("/api/health")
    assert response.status_code == 200


def test_protected_endpoint_returns_401_when_auth_enabled_no_token():
    """
    When AUTH_ENABLED=true but no token is provided, the response must
    be 401 Unauthorized (not 200 or 503).
    This test verifies the live-auth path without a real Supabase token.
    """
    app = create_app()
    with patch("api.dependencies.AUTH_ENABLED", True):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/reports")
    assert response.status_code == 401
