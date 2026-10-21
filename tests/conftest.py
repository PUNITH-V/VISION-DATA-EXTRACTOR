"""
Shared pytest fixtures for the Vision Extractor test suite.

JWT test helpers
────────────────
Tests that exercise authentication create JWTs signed with ephemeral
test keys — they never use real Supabase credentials.

Two signing modes are available to match the real project configuration:
  - ES256: asymmetric (ECC P-256), matches the current Supabase key.
  - HS256: symmetric, matches the legacy retained key.

The helpers produce JWTs that are structurally identical to real
Supabase tokens (same claims layout), making the tests realistic
without requiring a live Supabase connection.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ec import (
    SECP256R1,
    generate_private_key,
)
from cryptography.hazmat.backends import default_backend
from jose import jwt as jose_jwt

# ── Shared test constants ────────────────────────────────────────────────────

TEST_ISSUER = "https://test-project.supabase.co/auth/v1"
TEST_JWT_SECRET = "test-hs256-secret-that-is-long-enough-for-hmac-sha256-000"
TEST_USER_A_ID = "aaaaaaaa-0000-4000-8000-aaaaaaaaaaaa"
TEST_USER_B_ID = "bbbbbbbb-0000-4000-8000-bbbbbbbbbbbb"


# ── EC key pair fixture (generated once per test session) ────────────────────

@pytest.fixture(scope="session")
def ec_private_key():
    """Generate a P-256 private key once for the entire test session."""
    return generate_private_key(SECP256R1(), backend=default_backend())


@pytest.fixture(scope="session")
def ec_public_jwk(ec_private_key) -> dict[str, Any]:
    """
    Export the public key as a JWK dict, matching the shape returned by
    the Supabase JWKS endpoint. Includes `kid` and `alg` fields.
    """
    import base64

    pub_numbers = ec_private_key.public_key().public_numbers()

    def _b64url(n: int, length: int = 32) -> str:
        return base64.urlsafe_b64encode(
            n.to_bytes(length, "big")
        ).rstrip(b"=").decode()

    return {
        "kty": "EC",
        "crv": "P-256",
        "alg": "ES256",
        "use": "sig",
        "kid": "test-ec-kid-001",
        "x": _b64url(pub_numbers.x),
        "y": _b64url(pub_numbers.y),
    }


# ── JWT factory helpers ───────────────────────────────────────────────────────

def make_es256_token(
    private_key,
    *,
    user_id: str = TEST_USER_A_ID,
    email: str = "user@example.com",
    issuer: str = TEST_ISSUER,
    kid: str = "test-ec-kid-001",
    exp_offset: int = 3600,          # seconds from now; negative = expired
    audience: str = "authenticated", # Supabase user access token audience
    extra_claims: dict | None = None,
) -> str:
    """
    Mint an ES256 JWT signed with the provided private key.

    exp_offset < 0 produces an expired token (for testing expiry rejection).
    audience defaults to "authenticated" (standard Supabase user token).
    """
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + exp_offset,
        "role": "authenticated",
    }
    if extra_claims:
        claims.update(extra_claims)

    return jose_jwt.encode(
        claims,
        private_key,
        algorithm="ES256",
        headers={"kid": kid},
    )


def make_hs256_token(
    *,
    user_id: str = TEST_USER_A_ID,
    email: str = "user@example.com",
    issuer: str = TEST_ISSUER,
    secret: str = TEST_JWT_SECRET,
    exp_offset: int = 3600,
    audience: str = "authenticated",  # Supabase user access token audience
    extra_claims: dict | None = None,
) -> str:
    """Mint an HS256 JWT signed with the provided secret."""
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + exp_offset,
        "role": "authenticated",
    }
    if extra_claims:
        claims.update(extra_claims)

    return jose_jwt.encode(claims, secret, algorithm="HS256")
