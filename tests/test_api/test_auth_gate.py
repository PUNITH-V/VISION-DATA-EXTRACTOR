"""
Tests that every protected endpoint returns 503 in Stage 2
(AUTH_ENABLED=false) and never exposes data without authentication.

This covers the auth gate before Stage 3 is implemented.
"""

import io
import pytest
from fastapi.testclient import TestClient

from api.server import create_app

client = TestClient(create_app())

# All protected endpoints that must NOT be accessible in Stage 2.
PROTECTED_ENDPOINTS: list[tuple[str, str, dict]] = [
    ("POST", "/api/extractions", {}),
    ("GET",  "/api/reports",     {}),
    ("GET",  "/api/reports/some-id", {}),
    ("POST", "/api/ingestion",   {}),
    ("POST", "/api/search",      {"json": {"query": "test"}}),
    ("POST", "/api/ask",         {"json": {"question": "test"}}),
]


@pytest.mark.parametrize("method,path,kwargs", PROTECTED_ENDPOINTS)
def test_protected_endpoint_returns_503_without_auth(method, path, kwargs):
    """
    In Stage 2 (AUTH_ENABLED=false), protected endpoints must return
    503 Service Unavailable — not 200, 401, or any data.
    """
    response = client.request(method, path, **kwargs)
    assert response.status_code == 503, (
        f"{method} {path} should return 503 in Stage 2, "
        f"got {response.status_code}: {response.text}"
    )


@pytest.mark.parametrize("method,path,kwargs", PROTECTED_ENDPOINTS)
def test_protected_endpoint_includes_stage3_message(method, path, kwargs):
    """The 503 response body must mention Stage 3 so developers understand why."""
    response = client.request(method, path, **kwargs)
    body = response.json()
    assert "Stage 3" in body.get("detail", ""), (
        f"503 response for {method} {path} should mention 'Stage 3', "
        f"got: {body}"
    )


def test_health_is_not_protected():
    """Health endpoint must remain accessible without authentication."""
    response = client.get("/api/health")
    assert response.status_code == 200
