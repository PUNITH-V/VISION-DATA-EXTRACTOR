"""
FastAPI authentication dependency.

Behaviour by AUTH_ENABLED flag:

  false (default, Stage 2):
    Every protected endpoint returns 503. No data is ever exposed.

  true (Stage 3+):
    - Missing or malformed Authorization header → 401
    - Token verification failure (bad sig, expired, wrong iss, etc.) → 401
    - Token valid → returns AuthenticatedUser with verified user_id and email

Fail-closed contract:
  If AUTH_ENABLED=true but SUPABASE_URL is absent, verification raises
  TokenVerificationError → 401. There is no path that succeeds without
  a fully verified token.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import AUTH_ENABLED

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    """
    Represents a session verified by Supabase JWT validation.

    `user_id` is the JWT `sub` claim, always a Supabase UUID.
    It is validated as a UUID before this object is created.
    It is used as the namespace for filesystem paths and ChromaDB filters.
    """

    def __init__(self, user_id: str, email: str | None = None) -> None:
        self.user_id = user_id
        self.email = email


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """
    FastAPI dependency: resolve and return the authenticated user.

    In Stage 2 (AUTH_ENABLED=false): always raises 503.
    In Stage 3+ (AUTH_ENABLED=true): verifies the Bearer JWT; raises
    401 on any verification failure.
    """
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Authentication is not yet configured. "
                "Stage 3 implementation is required before this endpoint is available."
            ),
        )

    # ── AUTH_ENABLED=true path ────────────────────────────────────────────
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from api.auth.token_verifier import TokenVerificationError, verify_supabase_token

    try:
        verified = verify_supabase_token(credentials.credentials)
    except TokenVerificationError as exc:
        # Log the technical reason internally; return a generic 401 to the client.
        logger.warning("Token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AuthenticatedUser(user_id=verified.user_id, email=verified.email)
