"""
Supabase JWT verification for the Vision Extractor FastAPI backend.

Your Supabase project currently uses:
  - Current signing key:   ES256 (ECC P-256, asymmetric) — verified via JWKS
  - Previously used key:   HS256 (shared secret) — retained for unexpired tokens

Verification rules
──────────────────
1. A JWT's `alg` header is validated against the ALLOWED_JWT_ALGORITHMS
   allowlist (ES256, HS256). Any other algorithm is rejected immediately.

2. ES256 tokens:
   - MUST have a `kid` header identifying which public key to use.
   - The public key is fetched from the Supabase JWKS endpoint and cached.
   - The signature is verified against that public key only.

3. HS256 tokens:
   - Accepted ONLY if SUPABASE_JWT_SECRET is configured, indicating the
     project still retains the legacy key for unexpired token verification.
   - If SUPABASE_JWT_SECRET is not set, HS256 tokens are REJECTED.
   - HS256 does NOT use the JWKS endpoint (symmetric keys are never in JWKS).

4. Algorithm confusion attacks are prevented: the algorithm is read from the
   JWT header and then re-validated against what the selected key supports
   before decoding. python-jose enforces this during decode.

5. ALL tokens must pass:
   - Valid signature
   - Expiry (`exp` claim, not expired)
   - Issuer (`iss` == SUPABASE_URL/auth/v1)
   - Audience (`aud` == "authenticated") — required for user access tokens
   - Subject (`sub` claim present, non-empty, valid UUID format)

6. Fail closed: any verification error raises TokenVerificationError.
   There is no silent fallback or partial-success path.

Audience claim
──────────────
Per the Supabase JWT Claims Reference (https://supabase.com/docs/guides/auth/jwt-fields),
the `aud` claim is a required field in all Supabase JWTs. For authenticated
user access tokens, its value is the string "authenticated". For anonymous
user tokens, it is "anon". Service-role tokens use "service_role".

This backend accepts only authenticated user tokens ("aud" == "authenticated").
Service-role tokens must never be sent by a browser and are rejected here.

To inspect the audience claim in a real token locally (without sharing it):
  1. Open a terminal in the project directory.
  2. Run:  python -c "
  import sys, base64, json
  token = sys.argv[1]
  payload_b64 = token.split('.')[1]
  payload_b64 += '=' * (-len(payload_b64) % 4)
  print(json.dumps(json.loads(base64.urlsafe_b64decode(payload_b64)), indent=2))
  " <your_access_token>
  3. Look for the \"aud\" field in the printed output.
  This decodes without verifying the signature and does not send data anywhere.

What to configure in .env
──────────────────────────
  SUPABASE_URL=https://your-project-ref.supabase.co
  AUTH_ENABLED=true

  # Required for HS256 legacy token acceptance (optional once fully rotated):
  SUPABASE_JWT_SECRET=your_jwt_secret_from_dashboard

  # How to find your JWT Secret (if still needed):
  #   Dashboard → your project → Settings → Authentication → JWT Settings
  #   The value is labeled "JWT Secret".
"""

from __future__ import annotations

import logging
import uuid as _uuid_module
from dataclasses import dataclass

from jose import JWTError, exceptions as jose_exc, jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError

from api.auth.jwks_cache import JWKSFetchError, jwks_cache
from config.settings import (
    ALLOWED_JWT_ALGORITHMS,
    SUPABASE_JWT_ISSUER,
    SUPABASE_JWT_SECRET,
    SUPABASE_JWKS_URL,
)

logger = logging.getLogger(__name__)

# Algorithms that require JWKS-based public key verification.
_ASYMMETRIC_ALGORITHMS = frozenset({"ES256", "RS256", "EdDSA"})
# Algorithms that use a shared secret (symmetric).
_SYMMETRIC_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})

# Expected audience for authenticated user access tokens.
# Source: https://supabase.com/docs/guides/auth/jwt-fields
# The `aud` claim is always present and is "authenticated" for user tokens.
# Service-role tokens ("service_role") and anonymous tokens ("anon") are
# explicitly rejected by this backend.
SUPABASE_JWT_AUDIENCE = "authenticated"


class TokenVerificationError(Exception):
    """
    Raised when JWT verification cannot be completed successfully.
    Always results in a 401 Unauthorized response to the client.
    The message is safe to log but must NOT be forwarded to the client
    verbatim (to avoid leaking internal details).
    """


@dataclass(frozen=True)
class VerifiedClaims:
    """Claims extracted from a successfully verified JWT."""
    user_id: str   # The `sub` claim — a Supabase UUID
    email: str | None


def _validate_user_id_format(sub: str) -> None:
    """
    Reject sub claims that are not valid UUIDs.

    Supabase always issues UUIDs as `sub`. Any other format indicates
    a malformed or forged token and must be rejected before the value
    is used in filesystem paths or database queries.
    """
    try:
        _uuid_module.UUID(sub)
    except (ValueError, AttributeError) as exc:
        raise TokenVerificationError(
            f"Token 'sub' claim is not a valid UUID: {sub!r}"
        ) from exc


def _get_unverified_header(token: str) -> dict:
    """
    Extract the JWT header without verifying the signature.
    The header contents are not trusted until signature verification succeeds.
    """
    try:
        return jwt.get_unverified_header(token)
    except JWTError as exc:
        raise TokenVerificationError(f"Cannot parse JWT header: {exc}") from exc


def _check_algorithm_allowed(alg: str) -> None:
    """Reject any algorithm not on the strict allowlist."""
    if alg not in ALLOWED_JWT_ALGORITHMS:
        raise TokenVerificationError(
            f"JWT algorithm '{alg}' is not permitted. "
            f"Allowed: {ALLOWED_JWT_ALGORITHMS}"
        )


def _verify_asymmetric(token: str, header: dict) -> dict:
    """
    Verify an ES256 (or other asymmetric) token using the JWKS endpoint.

    Requires:
    - `kid` in the JWT header to identify which public key to use.
    - A reachable Supabase JWKS endpoint.
    """
    if not SUPABASE_JWKS_URL:
        raise TokenVerificationError(
            "SUPABASE_URL is not configured. Cannot verify asymmetric JWT."
        )

    kid = header.get("kid")
    if not kid:
        raise TokenVerificationError(
            "Asymmetric JWT is missing 'kid' header. Cannot select verification key."
        )

    alg = header["alg"]

    try:
        public_key = jwks_cache.get_key_for_kid(kid)
    except JWKSFetchError as exc:
        # JWKS is unreachable — fail closed rather than allowing unauthenticated access.
        raise TokenVerificationError(
            f"JWT verification unavailable: JWKS fetch failed: {exc}"
        ) from exc

    if public_key is None:
        raise TokenVerificationError(
            f"JWT 'kid' {kid!r} not found in JWKS. Token may have been issued "
            "by a revoked key or the wrong project."
        )

    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=[alg],            # only the algorithm declared in the header
            issuer=SUPABASE_JWT_ISSUER,  # must match exactly
            audience=SUPABASE_JWT_AUDIENCE,  # must be "authenticated"
            options={
                "verify_aud": True,
                "verify_exp": True,
                "verify_iss": True,
            },
        )
    except ExpiredSignatureError as exc:
        raise TokenVerificationError("Token has expired.") from exc
    except JWTClaimsError as exc:
        raise TokenVerificationError(f"Token claims invalid: {exc}") from exc
    except JWTError as exc:
        raise TokenVerificationError(f"Asymmetric token verification failed: {exc}") from exc

    return claims


def _verify_symmetric(token: str, header: dict) -> dict:
    """
    Verify an HS256 token using the legacy JWT secret.

    Accepted only when SUPABASE_JWT_SECRET is configured, indicating
    the project still retains its legacy key for unexpired token verification.

    If SUPABASE_JWT_SECRET is not set in .env, HS256 tokens are REJECTED.
    This ensures that once you fully revoke the legacy key and remove the
    secret from .env, the backend immediately stops trusting HS256 tokens.
    """
    if not SUPABASE_JWT_SECRET:
        raise TokenVerificationError(
            "HS256 token received but SUPABASE_JWT_SECRET is not configured. "
            "This token cannot be verified. If your project has revoked the "
            "legacy key, this token is no longer valid."
        )

    alg = header["alg"]

    try:
        claims = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=[alg],            # HS256 only — no algorithm confusion
            issuer=SUPABASE_JWT_ISSUER,
            audience=SUPABASE_JWT_AUDIENCE,  # must be "authenticated"
            options={
                "verify_aud": True,
                "verify_exp": True,
                "verify_iss": True,
            },
        )
    except ExpiredSignatureError as exc:
        raise TokenVerificationError("Token has expired.") from exc
    except JWTClaimsError as exc:
        raise TokenVerificationError(f"Token claims invalid: {exc}") from exc
    except JWTError as exc:
        raise TokenVerificationError(f"HS256 token verification failed: {exc}") from exc

    return claims


def verify_supabase_token(token: str) -> VerifiedClaims:
    """
    Verify a Supabase-issued JWT and return its claims.

    Algorithm selection:
      ES256 → asymmetric verification via JWKS (current key)
      HS256 → symmetric verification via JWT secret (legacy key, if configured)
      Any other algorithm → rejected

    Raises TokenVerificationError for every failure case.
    Never returns partial or unverified claims.
    """
    if not token or not token.strip():
        raise TokenVerificationError("No token provided.")

    # Step 1: parse the header (untrusted until signature verified)
    header = _get_unverified_header(token)
    alg = header.get("alg", "")

    # Step 2: strict algorithm allowlist check
    _check_algorithm_allowed(alg)

    # Step 3: verify based on algorithm family
    if alg in _ASYMMETRIC_ALGORITHMS:
        claims = _verify_asymmetric(token, header)
    elif alg in _SYMMETRIC_ALGORITHMS:
        claims = _verify_symmetric(token, header)
    else:
        # Should be unreachable after step 2, but belt-and-suspenders.
        raise TokenVerificationError(f"Unhandled algorithm '{alg}'.")

    # Step 4: subject (user identity) must be present and a valid UUID
    sub = claims.get("sub", "")
    if not sub:
        raise TokenVerificationError("Token is missing the 'sub' claim.")
    _validate_user_id_format(sub)

    return VerifiedClaims(
        user_id=sub,
        email=claims.get("email"),
    )
