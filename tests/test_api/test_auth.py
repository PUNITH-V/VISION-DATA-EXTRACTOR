"""
Stage 3 authentication tests.

These tests exercise the real JWT verification logic in
api/auth/token_verifier.py using ephemeral test keys.
They never connect to Supabase or use real credentials.

Coverage:
  ✅ Valid ES256 token → verified claims
  ✅ Valid HS256 token (with secret configured) → verified claims
  ✅ Expired ES256 token → TokenVerificationError
  ✅ Expired HS256 token → TokenVerificationError
  ✅ Missing Authorization header → 401
  ✅ Wrong Bearer format → 401
  ✅ ES256 token with wrong signature → TokenVerificationError
  ✅ ES256 token with wrong issuer → TokenVerificationError
  ✅ ES256 token missing sub claim → TokenVerificationError
  ✅ ES256 token with non-UUID sub claim → TokenVerificationError
  ✅ ES256 token missing kid → TokenVerificationError
  ✅ ES256 token with unknown kid → TokenVerificationError
  ✅ HS256 token when secret not configured → TokenVerificationError
  ✅ Unsupported algorithm (RS256 not in allowlist) → TokenVerificationError
  ✅ AUTH_ENABLED=false → 503 on protected endpoint
  ✅ AUTH_ENABLED=true, SUPABASE_URL missing → TokenVerificationError
  ✅ Full route integration: valid token → 200 on protected endpoint
  ✅ Full route integration: invalid token → 401 on protected endpoint
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import (
    SECP256R1,
    generate_private_key,
)
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

from api.auth.token_verifier import TokenVerificationError, verify_supabase_token
from api.server import create_app
from tests.conftest import (
    TEST_ISSUER,
    TEST_JWT_SECRET,
    TEST_USER_A_ID,
    TEST_USER_B_ID,
    make_es256_token,
    make_hs256_token,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patch_jwks(public_jwk: dict):
    """Context manager: make the JWKS cache return a single test public key."""
    return patch(
        "api.auth.token_verifier.jwks_cache.get_key_for_kid",
        return_value=public_jwk,
    )


def _patch_settings(
    *,
    supabase_url: str | None = "https://test-project.supabase.co",
    jwt_secret: str | None = None,
    jwks_url: str | None = "https://test-project.supabase.co/auth/v1/.well-known/jwks.json",
    jwt_issuer: str | None = TEST_ISSUER,
    allowed_algorithms: list[str] | None = None,
):
    """
    Patch the settings used by token_verifier at call time.
    This lets individual tests control the auth configuration precisely.
    """
    patches = [
        patch("api.auth.token_verifier.SUPABASE_JWKS_URL", jwks_url),
        patch("api.auth.token_verifier.SUPABASE_JWT_ISSUER", jwt_issuer),
        patch("api.auth.token_verifier.SUPABASE_JWT_SECRET", jwt_secret),
        patch("api.auth.token_verifier.ALLOWED_JWT_ALGORITHMS",
              allowed_algorithms or ["ES256", "HS256"]),
    ]
    return patches


def _apply_patches(patches):
    """Enter a list of patch context managers and return their mock objects."""
    mocks = [p.__enter__() for p in patches]
    return patches, mocks


def _exit_patches(patches):
    for p in patches:
        p.__exit__(None, None, None)


# ── Unit tests: verify_supabase_token() ─────────────────────────────────────

class TestES256Verification:
    """Tests for the ES256 (asymmetric) verification path."""

    def test_valid_es256_token_returns_claims(self, ec_private_key, ec_public_jwk):
        token = make_es256_token(ec_private_key, user_id=TEST_USER_A_ID)
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with _patch_jwks(ec_public_jwk):
                result = verify_supabase_token(token)
        finally:
            _exit_patches(ps)

        assert result.user_id == TEST_USER_A_ID
        assert result.email == "user@example.com"

    def test_expired_es256_token_raises(self, ec_private_key, ec_public_jwk):
        token = make_es256_token(ec_private_key, exp_offset=-60)
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with _patch_jwks(ec_public_jwk):
                with pytest.raises(TokenVerificationError, match="expired"):
                    verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_wrong_issuer_raises(self, ec_private_key, ec_public_jwk):
        token = make_es256_token(
            ec_private_key,
            issuer="https://evil.supabase.co/auth/v1",
        )
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with _patch_jwks(ec_public_jwk):
                with pytest.raises(TokenVerificationError, match="claims invalid|verification failed"):
                    verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_wrong_signature_raises(self, ec_public_jwk):
        # Sign with a different key, verify with ec_public_jwk → mismatch.
        other_key = generate_private_key(SECP256R1(), backend=default_backend())
        token = make_es256_token(other_key)  # signed with different key
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with _patch_jwks(ec_public_jwk):
                with pytest.raises(TokenVerificationError):
                    verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_missing_kid_raises(self, ec_private_key):
        # Mint token without kid header.
        now = int(time.time())
        token = jose_jwt.encode(
            {"sub": TEST_USER_A_ID, "iss": TEST_ISSUER, "exp": now + 3600},
            ec_private_key,
            algorithm="ES256",
            # no headers= means no kid
        )
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with pytest.raises(TokenVerificationError, match="kid"):
                verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_unknown_kid_raises(self, ec_private_key):
        token = make_es256_token(ec_private_key, kid="unknown-kid-xyz")
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with patch(
                "api.auth.token_verifier.jwks_cache.get_key_for_kid",
                return_value=None,  # kid not found in JWKS
            ):
                with pytest.raises(TokenVerificationError, match="not found in JWKS"):
                    verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_missing_sub_claim_raises(self, ec_private_key, ec_public_jwk):
        now = int(time.time())
        token = jose_jwt.encode(
            {"iss": TEST_ISSUER, "exp": now + 3600},  # no "sub"
            ec_private_key,
            algorithm="ES256",
            headers={"kid": "test-ec-kid-001"},
        )
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with _patch_jwks(ec_public_jwk):
                with pytest.raises(TokenVerificationError, match="sub"):
                    verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_non_uuid_sub_raises(self, ec_private_key, ec_public_jwk):
        now = int(time.time())
        token = jose_jwt.encode(
            {"sub": "not-a-uuid", "iss": TEST_ISSUER, "exp": now + 3600},
            ec_private_key,
            algorithm="ES256",
            headers={"kid": "test-ec-kid-001"},
        )
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with _patch_jwks(ec_public_jwk):
                with pytest.raises(TokenVerificationError, match="UUID"):
                    verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_supabase_url_missing_raises(self, ec_private_key, ec_public_jwk):
        """When SUPABASE_URL is not configured, fail closed."""
        token = make_es256_token(ec_private_key)
        patches = _patch_settings(supabase_url=None, jwks_url=None, jwt_issuer=None)
        ps, _ = _apply_patches(patches)
        try:
            with pytest.raises(TokenVerificationError, match="SUPABASE_URL"):
                verify_supabase_token(token)
        finally:
            _exit_patches(ps)


class TestHS256Verification:
    """Tests for the HS256 (legacy symmetric) verification path."""

    def test_valid_hs256_with_secret_configured_returns_claims(self):
        token = make_hs256_token(user_id=TEST_USER_A_ID, secret=TEST_JWT_SECRET)
        patches = _patch_settings(jwt_secret=TEST_JWT_SECRET)
        ps, _ = _apply_patches(patches)
        try:
            result = verify_supabase_token(token)
        finally:
            _exit_patches(ps)

        assert result.user_id == TEST_USER_A_ID

    def test_hs256_without_secret_configured_raises(self):
        """If SUPABASE_JWT_SECRET is not in .env, HS256 tokens MUST be rejected."""
        token = make_hs256_token(user_id=TEST_USER_A_ID, secret=TEST_JWT_SECRET)
        patches = _patch_settings(jwt_secret=None)
        ps, _ = _apply_patches(patches)
        try:
            with pytest.raises(TokenVerificationError, match="SUPABASE_JWT_SECRET"):
                verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_expired_hs256_token_raises(self):
        token = make_hs256_token(exp_offset=-60, secret=TEST_JWT_SECRET)
        patches = _patch_settings(jwt_secret=TEST_JWT_SECRET)
        ps, _ = _apply_patches(patches)
        try:
            with pytest.raises(TokenVerificationError, match="expired"):
                verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_hs256_wrong_secret_raises(self):
        token = make_hs256_token(secret="correct-secret-here-padding-000000000")
        patches = _patch_settings(jwt_secret="wrong-secret-here-padding-00000000000")
        ps, _ = _apply_patches(patches)
        try:
            with pytest.raises(TokenVerificationError):
                verify_supabase_token(token)
        finally:
            _exit_patches(ps)


class TestAlgorithmGuards:
    """Tests that the algorithm allowlist is enforced strictly."""

    def test_unsupported_algorithm_is_rejected(self):
        """RS256 is not in our allowlist, even though it is a valid JWT algorithm."""
        # We can't easily mint an RS256 token without a full RSA key, so we
        # forge a fake header with RS256 to test the allowlist check directly
        # before any key lookup is attempted.
        now = int(time.time())
        # Generate a minimal RS256-looking token (won't have valid signature,
        # but we want to confirm it's rejected before signature check)
        fake_alg = "RS256"
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            # Patch _check_algorithm_allowed to test it was called, or
            # directly test the validation function:
            from api.auth.token_verifier import _check_algorithm_allowed
            with pytest.raises(TokenVerificationError, match="not permitted"):
                _check_algorithm_allowed(fake_alg)
        finally:
            _exit_patches(ps)

    def test_none_algorithm_is_rejected(self):
        """'none' algorithm (common JWT attack) must be rejected."""
        from api.auth.token_verifier import _check_algorithm_allowed
        with pytest.raises(TokenVerificationError, match="not permitted"):
            _check_algorithm_allowed("none")

    def test_empty_token_raises(self):
        with pytest.raises(TokenVerificationError):
            verify_supabase_token("")

    def test_garbage_token_raises(self):
        with pytest.raises(TokenVerificationError):
            verify_supabase_token("not.a.jwt")


# ── Integration tests: FastAPI routes with auth enabled ──────────────────────

def _make_authed_client(
    ec_private_key,
    ec_public_jwk: dict,
    *,
    user_id: str = TEST_USER_A_ID,
    exp_offset: int = 3600,
) -> tuple[TestClient, str]:
    """
    Create a TestClient with AUTH_ENABLED=true and a valid Bearer token.
    Returns (client, token).
    """
    app = create_app()
    token = make_es256_token(ec_private_key, user_id=user_id, exp_offset=exp_offset)
    return TestClient(app, raise_server_exceptions=False), token


class TestRouteAuthentication:
    """Integration tests: valid and invalid tokens on real FastAPI routes."""

    def test_valid_token_reaches_route(self, ec_private_key, ec_public_jwk, tmp_path):
        app = create_app()
        token = make_es256_token(ec_private_key, user_id=TEST_USER_A_ID)

        with (
            patch("api.dependencies.AUTH_ENABLED", True),
            patch("api.auth.token_verifier.SUPABASE_JWKS_URL", "https://test.supabase.co/auth/v1/.well-known/jwks.json"),
            patch("api.auth.token_verifier.SUPABASE_JWT_ISSUER", TEST_ISSUER),
            patch("api.auth.token_verifier.SUPABASE_JWT_SECRET", None),
            patch("api.auth.token_verifier.ALLOWED_JWT_ALGORITHMS", ["ES256", "HS256"]),
            patch("api.auth.token_verifier.jwks_cache.get_key_for_kid", return_value=ec_public_jwk),
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get(
                "/api/reports",
                headers={"Authorization": f"Bearer {token}"},
            )

        # The route is reached and returns an empty list (no reports yet).
        assert response.status_code == 200
        assert response.json() == []

    def test_missing_token_returns_401(self, ec_private_key, ec_public_jwk):
        app = create_app()

        with (
            patch("api.dependencies.AUTH_ENABLED", True),
            patch("api.auth.token_verifier.SUPABASE_JWKS_URL", "https://test.supabase.co/auth/v1/.well-known/jwks.json"),
            patch("api.auth.token_verifier.SUPABASE_JWT_ISSUER", TEST_ISSUER),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/reports")  # no Authorization header

        assert response.status_code == 401

    def test_invalid_token_returns_401(self, ec_private_key, ec_public_jwk):
        app = create_app()

        with (
            patch("api.dependencies.AUTH_ENABLED", True),
            patch("api.auth.token_verifier.SUPABASE_JWKS_URL", "https://test.supabase.co/auth/v1/.well-known/jwks.json"),
            patch("api.auth.token_verifier.SUPABASE_JWT_ISSUER", TEST_ISSUER),
            patch("api.auth.token_verifier.SUPABASE_JWT_SECRET", None),
            patch("api.auth.token_verifier.ALLOWED_JWT_ALGORITHMS", ["ES256", "HS256"]),
            patch("api.auth.token_verifier.jwks_cache.get_key_for_kid", return_value=None),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(
                "/api/reports",
                headers={"Authorization": "Bearer this.is.garbage"},
            )

        assert response.status_code == 401

    def test_expired_token_returns_401(self, ec_private_key, ec_public_jwk, tmp_path):
        app = create_app()
        expired_token = make_es256_token(ec_private_key, exp_offset=-120)  # 2 min ago

        with (
            patch("api.dependencies.AUTH_ENABLED", True),
            patch("api.auth.token_verifier.SUPABASE_JWKS_URL", "https://test.supabase.co/auth/v1/.well-known/jwks.json"),
            patch("api.auth.token_verifier.SUPABASE_JWT_ISSUER", TEST_ISSUER),
            patch("api.auth.token_verifier.SUPABASE_JWT_SECRET", None),
            patch("api.auth.token_verifier.ALLOWED_JWT_ALGORITHMS", ["ES256", "HS256"]),
            patch("api.auth.token_verifier.jwks_cache.get_key_for_kid", return_value=ec_public_jwk),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(
                "/api/reports",
                headers={"Authorization": f"Bearer {expired_token}"},
            )

        assert response.status_code == 401

    def test_auth_disabled_returns_503_not_401(self):
        """With AUTH_ENABLED=false, the response is 503, not 401."""
        app = create_app()
        with patch("api.dependencies.AUTH_ENABLED", False):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(
                "/api/reports",
                headers={"Authorization": "Bearer some.token.here"},
            )
        assert response.status_code == 503


# ── Cross-user isolation tests (auth-enabled) ────────────────────────────────

class TestCrossUserIsolation:
    """
    Critical: User A cannot access User B's data when auth is enabled.
    These tests use real token verification (with test keys) and the
    real route handlers.
    """

    def _setup(self, ec_private_key, ec_public_jwk, tmp_path):
        """Create app and tokens for both test users."""
        app = create_app()
        token_a = make_es256_token(ec_private_key, user_id=TEST_USER_A_ID)
        token_b = make_es256_token(ec_private_key, user_id=TEST_USER_B_ID)
        return app, token_a, token_b

    def test_user_a_cannot_read_user_b_report(
        self, ec_private_key, ec_public_jwk, tmp_path
    ):
        import json
        from datetime import datetime, timezone
        from api.services.report_service import (
            _REPORT_ID_KEY, _FILENAME_KEY, _INDEX_FLAG_KEY, _CREATED_AT_KEY,
        )

        app, token_a, token_b = self._setup(ec_private_key, ec_public_jwk, tmp_path)

        # Write User B's report directly into User B's directory.
        report_id = str(uuid.uuid4())
        user_b_dir = tmp_path / TEST_USER_B_ID
        user_b_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            _REPORT_ID_KEY: report_id,
            _FILENAME_KEY: "user_b_secret.jpg",
            _CREATED_AT_KEY: datetime.now(timezone.utc).isoformat(),
            _INDEX_FLAG_KEY: False,
            "image_description": "User B's confidential image.",
            "extracted_data": [{"label": "Secret", "value": "B_data"}],
            "confidence": "High",
        }
        (user_b_dir / f"{report_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        with (
            patch("api.dependencies.AUTH_ENABLED", True),
            patch("api.auth.token_verifier.SUPABASE_JWKS_URL", "https://t.co"),
            patch("api.auth.token_verifier.SUPABASE_JWT_ISSUER", TEST_ISSUER),
            patch("api.auth.token_verifier.SUPABASE_JWT_SECRET", None),
            patch("api.auth.token_verifier.ALLOWED_JWT_ALGORITHMS", ["ES256", "HS256"]),
            patch("api.auth.token_verifier.jwks_cache.get_key_for_kid", return_value=ec_public_jwk),
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
        ):
            client = TestClient(app, raise_server_exceptions=True)

            # User A tries to read User B's specific report by ID.
            response_a = client.get(
                f"/api/reports/{report_id}",
                headers={"Authorization": f"Bearer {token_a}"},
            )

        assert response_a.status_code == 404, (
            "User A must get 404, not 200, when requesting User B's report ID. "
            f"Got {response_a.status_code}: {response_a.text}"
        )

    def test_user_a_search_cannot_return_user_b_vectors(
        self, ec_private_key, ec_public_jwk, tmp_path
    ):
        """User A's search must not surface User B's indexed documents."""
        app, token_a, _ = self._setup(ec_private_key, ec_public_jwk, tmp_path)

        # Simulate a ChromaDB search that "leaks" User B's result.
        leaked_result = {
            "ids": [["rep-b-leaked"]],
            "documents": [["User B's private extraction text."]],
            "metadatas": [[{
                "user_id": TEST_USER_B_ID,   # belongs to User B
                "report_id": "rep-b-leaked",
                "image_filename": "user_b_file.jpg",
                "confidence": "High",
            }]],
            "distances": [[0.05]],
        }

        with (
            patch("api.dependencies.AUTH_ENABLED", True),
            patch("api.auth.token_verifier.SUPABASE_JWKS_URL", "https://t.co"),
            patch("api.auth.token_verifier.SUPABASE_JWT_ISSUER", TEST_ISSUER),
            patch("api.auth.token_verifier.SUPABASE_JWT_SECRET", None),
            patch("api.auth.token_verifier.ALLOWED_JWT_ALGORITHMS", ["ES256", "HS256"]),
            patch("api.auth.token_verifier.jwks_cache.get_key_for_kid", return_value=ec_public_jwk),
            patch("api.services.search_service.ChromaStore") as MockStore,
            patch("api.services.search_service.TextEmbedder") as MockEmbedder,
        ):
            mock_store = MockStore.return_value
            mock_store.count.return_value = 1
            mock_store.search.return_value = leaked_result
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384

            client = TestClient(app, raise_server_exceptions=True)
            response = client.post(
                "/api/search",
                json={"query": "invoices"},
                headers={"Authorization": f"Bearer {token_a}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0, (
            "User A's search must return 0 results when the only match belongs to User B. "
            f"Got: {data}"
        )

    def test_user_a_rag_cannot_receive_user_b_context(
        self, ec_private_key, ec_public_jwk, tmp_path
    ):
        """User B's document content must never be passed to the LLM for User A."""
        app, token_a, _ = self._setup(ec_private_key, ec_public_jwk, tmp_path)

        leaked_store_result = {
            "ids": [["rep-b-secret"]],
            "documents": [["User B: $999,000 invoice — confidential."]],
            "metadatas": [[{
                "user_id": TEST_USER_B_ID,   # User B's data
                "report_id": "rep-b-secret",
                "image_filename": "b_invoice.jpg",
                "confidence": "High",
            }]],
            "distances": [[0.03]],
        }

        with (
            patch("api.dependencies.AUTH_ENABLED", True),
            patch("api.auth.token_verifier.SUPABASE_JWKS_URL", "https://t.co"),
            patch("api.auth.token_verifier.SUPABASE_JWT_ISSUER", TEST_ISSUER),
            patch("api.auth.token_verifier.SUPABASE_JWT_SECRET", None),
            patch("api.auth.token_verifier.ALLOWED_JWT_ALGORITHMS", ["ES256", "HS256"]),
            patch("api.auth.token_verifier.jwks_cache.get_key_for_kid", return_value=ec_public_jwk),
            patch("api.services.rag_service.ChromaStore") as MockStore,
            patch("api.services.rag_service.TextEmbedder") as MockEmbedder,
            patch("api.services.rag_service.LLMClient") as MockLLM,
        ):
            mock_store = MockStore.return_value
            mock_store.count.return_value = 1
            mock_store.search.return_value = leaked_store_result
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384

            client = TestClient(app, raise_server_exceptions=True)
            response = client.post(
                "/api/ask",
                json={"question": "What are the invoice totals?"},
                headers={"Authorization": f"Bearer {token_a}"},
            )

        assert response.status_code == 200
        data = response.json()

        # LLM must NOT have been called with User B's content.
        MockLLM.return_value.generate.assert_not_called(), (
            "The LLM must never receive User B's context when User A asks a question."
        )
        assert data["grounded"] is False
        assert data["sources"] == [], (
            "User B's sources must not appear in User A's RAG response."
        )


# ── New tests added by minimal-fixes pass ────────────────────────────────────


class TestAudienceValidation:
    """
    Tests that audience validation is enforced correctly in both paths.
    Source: https://supabase.com/docs/guides/auth/jwt-fields
    Supabase access tokens always carry `aud: "authenticated"`.
    """

    def test_es256_wrong_audience_is_rejected(self, ec_private_key, ec_public_jwk):
        """A token with aud='service_role' (or any value != 'authenticated') is rejected."""
        token = make_es256_token(
            ec_private_key,
            audience="service_role",   # wrong — service-role tokens must never be accepted
        )
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with _patch_jwks(ec_public_jwk):
                with pytest.raises(TokenVerificationError, match="claims invalid|verification failed"):
                    verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_es256_anon_audience_is_rejected(self, ec_private_key, ec_public_jwk):
        """Anonymous tokens (aud='anon') must not pass the audience check."""
        token = make_es256_token(
            ec_private_key,
            audience="anon",
        )
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with _patch_jwks(ec_public_jwk):
                with pytest.raises(TokenVerificationError, match="claims invalid|verification failed"):
                    verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_hs256_wrong_audience_is_rejected(self):
        """HS256 tokens with wrong audience are rejected even if signature is valid."""
        token = make_hs256_token(
            secret=TEST_JWT_SECRET,
            audience="service_role",
        )
        patches = _patch_settings(jwt_secret=TEST_JWT_SECRET)
        ps, _ = _apply_patches(patches)
        try:
            with pytest.raises(TokenVerificationError, match="claims invalid|verification failed"):
                verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_es256_correct_audience_is_accepted(self, ec_private_key, ec_public_jwk):
        """Confirm the happy path still works after enabling audience verification."""
        token = make_es256_token(ec_private_key, audience="authenticated")
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with _patch_jwks(ec_public_jwk):
                result = verify_supabase_token(token)
        finally:
            _exit_patches(ps)
        assert result.user_id == TEST_USER_A_ID


class TestHS256WrongIssuer:
    """
    Tests that the issuer claim is validated in the HS256 path.
    The existing test suite covered wrong-issuer for ES256 only.
    """

    def test_hs256_wrong_issuer_is_rejected(self):
        """
        An HS256 token from a different project (different iss claim)
        must be rejected even when signed with the correct secret.
        """
        token = make_hs256_token(
            secret=TEST_JWT_SECRET,
            issuer="https://evil-other-project.supabase.co/auth/v1",
        )
        patches = _patch_settings(jwt_secret=TEST_JWT_SECRET)
        ps, _ = _apply_patches(patches)
        try:
            with pytest.raises(TokenVerificationError, match="claims invalid|verification failed"):
                verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_hs256_correct_issuer_is_accepted(self):
        """Confirm the HS256 happy path still works after the aud fix."""
        token = make_hs256_token(
            secret=TEST_JWT_SECRET,
            issuer=TEST_ISSUER,
        )
        patches = _patch_settings(jwt_secret=TEST_JWT_SECRET)
        ps, _ = _apply_patches(patches)
        try:
            result = verify_supabase_token(token)
        finally:
            _exit_patches(ps)
        assert result.user_id == TEST_USER_A_ID


class TestJWKSNetworkFailure:
    """
    Tests that JWKS network failures result in a safe 401 response,
    never a 500 or a successful authentication bypass.
    """

    def test_jwks_fetch_failure_returns_401_on_route(
        self, ec_private_key, ec_public_jwk
    ):
        """
        When the JWKS endpoint is unreachable during verification,
        the protected route must return 401, not 200 or 500.
        """
        import httpx
        from api.auth.jwks_cache import JWKSFetchError

        app = create_app()
        token = make_es256_token(ec_private_key)

        with (
            patch("api.dependencies.AUTH_ENABLED", True),
            patch(
                "api.auth.token_verifier.SUPABASE_JWKS_URL",
                "https://test.supabase.co/auth/v1/.well-known/jwks.json",
            ),
            patch("api.auth.token_verifier.SUPABASE_JWT_ISSUER", TEST_ISSUER),
            patch("api.auth.token_verifier.SUPABASE_JWT_SECRET", None),
            patch("api.auth.token_verifier.ALLOWED_JWT_ALGORITHMS", ["ES256", "HS256"]),
            # Simulate a network failure: get_key_for_kid raises JWKSFetchError.
            patch(
                "api.auth.token_verifier.jwks_cache.get_key_for_kid",
                side_effect=JWKSFetchError("Connection refused"),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(
                "/api/reports",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 401, (
            "A JWKS network failure must result in 401 (fail closed), "
            f"got {response.status_code}: {response.text}"
        )

    def test_jwks_fetch_failure_is_not_a_bypass(self, ec_private_key):
        """
        JWKS failure must raise TokenVerificationError, not return None or
        silently succeed. This test exercises verify_supabase_token directly.
        """
        from api.auth.jwks_cache import JWKSFetchError

        token = make_es256_token(ec_private_key)
        patches = _patch_settings()
        ps, _ = _apply_patches(patches)
        try:
            with patch(
                "api.auth.token_verifier.jwks_cache.get_key_for_kid",
                side_effect=JWKSFetchError("Timeout"),
            ):
                with pytest.raises(
                    TokenVerificationError,
                    match="JWKS fetch failed",
                ):
                    verify_supabase_token(token)
        finally:
            _exit_patches(ps)

    def test_http_jwks_url_is_rejected(self, ec_private_key):
        """
        A misconfigured HTTP (not HTTPS) JWKS URL must be rejected before
        any network request is made.
        """
        from api.auth.jwks_cache import JWKSFetchError, _JWKSCache

        cache = _JWKSCache()
        # Temporarily override the module-level URL to an http:// one.
        with patch(
            "api.auth.jwks_cache.SUPABASE_JWKS_URL",
            "http://test.supabase.co/auth/v1/.well-known/jwks.json",
        ):
            with pytest.raises(JWKSFetchError, match="HTTPS"):
                cache._fetch()


class TestIngestionCrossUserIsolation:
    """
    Tests that the ingestion endpoint cannot be used to index
    another user's report files.
    Covers the gap identified in the Stage 3 audit.
    """

    def test_ingestion_ignores_other_users_report_ids(self, tmp_path):
        """
        User A submits a report_ids list containing User B's report UUID.
        The service looks for that file under User A's directory, finds
        nothing, and counts it as skipped — never touching User B's data.
        """
        import json
        from datetime import datetime, timezone
        from api.services.report_service import (
            _REPORT_ID_KEY, _FILENAME_KEY, _INDEX_FLAG_KEY, _CREATED_AT_KEY,
        )
        from api.services.ingestion_service import ingest_user_reports

        # Write User B's report under User B's directory.
        user_b_report_id = str(uuid.uuid4())
        user_b_dir = tmp_path / TEST_USER_B_ID
        user_b_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            _REPORT_ID_KEY: user_b_report_id,
            _FILENAME_KEY: "b_secret.jpg",
            _CREATED_AT_KEY: datetime.now(timezone.utc).isoformat(),
            _INDEX_FLAG_KEY: False,
            "image_description": "User B's private report.",
            "extracted_data": [{"label": "Key", "value": "Secret"}],
            "confidence": "High",
        }
        (user_b_dir / f"{user_b_report_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        # User A attempts to ingest User B's report_id.
        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
        ):
            result = ingest_user_reports(
                user_id=TEST_USER_A_ID,
                report_ids=[user_b_report_id],
            )

        # The file is not in User A's directory, so it is skipped.
        assert result.ingested == 0, (
            "Ingestion must not index a report that belongs to another user. "
            f"Got ingested={result.ingested}"
        )
        assert result.skipped == 1, (
            f"Expected 1 skipped, got {result.skipped}"
        )

        # User B's _indexed flag must remain False (file untouched).
        saved = json.loads(
            (user_b_dir / f"{user_b_report_id}.json").read_text(encoding="utf-8")
        )
        assert saved[_INDEX_FLAG_KEY] is False, (
            "User B's report must not have been marked as indexed by User A's ingestion."
        )

    def test_ingestion_processes_own_reports_correctly(self, tmp_path):
        """
        Confirm the ingestion service still works for a user's own reports
        after the isolation check, so the guard doesn't break normal use.
        """
        import json
        from datetime import datetime, timezone
        from api.services.report_service import (
            _REPORT_ID_KEY, _FILENAME_KEY, _INDEX_FLAG_KEY, _CREATED_AT_KEY,
        )
        from api.services.ingestion_service import ingest_user_reports

        # Write User A's own report in User A's directory.
        own_report_id = str(uuid.uuid4())
        user_a_dir = tmp_path / TEST_USER_A_ID
        user_a_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            _REPORT_ID_KEY: own_report_id,
            _FILENAME_KEY: "a_own.jpg",
            _CREATED_AT_KEY: datetime.now(timezone.utc).isoformat(),
            _INDEX_FLAG_KEY: False,
            "image_description": "User A's own image.",
            "extracted_data": [{"label": "Item", "value": "Value"}],
            "confidence": "High",
        }
        (user_a_dir / f"{own_report_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        with (
            patch("api.services.report_service.REPORTS_BASE_DIR", tmp_path),
            patch("api.services.report_service.CHROMA_BASE_DIR", tmp_path / "chroma"),
            # Prevent real embedding model from loading in this unit test.
            patch("api.services.ingestion_service.TextEmbedder") as MockEmbedder,
            patch("api.services.ingestion_service.ChromaStore") as MockStore,
        ):
            MockEmbedder.return_value.embed_text.return_value = [0.1] * 384
            mock_store = MockStore.return_value
            mock_store.upsert_report.return_value = None

            result = ingest_user_reports(
                user_id=TEST_USER_A_ID,
                report_ids=[own_report_id],
            )

        assert result.ingested == 1, (
            f"User A's own report should have been ingested. Got {result}"
        )
