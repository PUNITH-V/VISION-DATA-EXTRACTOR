"""
JWKS cache for Supabase ES256 (and optionally RS256) key verification.

Responsibilities:
- Fetch the JWKS document from the Supabase JWKS endpoint.
- Cache it for JWKS_CACHE_TTL_SECONDS to avoid a network call on
  every request. The cache is per-process and thread-safe via a lock.
- Invalidate and re-fetch if a JWT presents a `kid` not found in the
  current cache (handles key rotation without restart).
- Fail closed: if the JWKS cannot be fetched, raise an error rather
  than falling back silently.

This module has no side effects on import. The cache is populated lazily
on first token verification and replaced transparently on rotation.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from config.settings import JWKS_CACHE_TTL_SECONDS, SUPABASE_JWKS_URL

logger = logging.getLogger(__name__)


class JWKSFetchError(RuntimeError):
    """Raised when the JWKS document cannot be fetched or parsed."""


class _JWKSCache:
    """Thread-safe in-process JWKS cache with TTL and kid-miss refresh."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: list[dict[str, Any]] = []
        self._fetched_at: float = 0.0

    def _is_expired(self) -> bool:
        return (time.monotonic() - self._fetched_at) > JWKS_CACHE_TTL_SECONDS

    def _fetch(self) -> list[dict[str, Any]]:
        """Fetch the JWKS document. Raises JWKSFetchError on failure."""
        if not SUPABASE_JWKS_URL:
            raise JWKSFetchError(
                "SUPABASE_URL is not configured. "
                "Set it in .env to enable JWT verification."
            )

        if not SUPABASE_JWKS_URL.startswith("https://"):
            raise JWKSFetchError(
                f"JWKS URL must use HTTPS, got: {SUPABASE_JWKS_URL!r}. "
                "Check the SUPABASE_URL in your .env file."
            )

        logger.info("Fetching JWKS from %s", SUPABASE_JWKS_URL)
        try:
            response = httpx.get(SUPABASE_JWKS_URL, timeout=10.0)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise JWKSFetchError(
                f"Failed to fetch JWKS from {SUPABASE_JWKS_URL}: {exc}"
            ) from exc
        except Exception as exc:
            raise JWKSFetchError(
                f"Unexpected error fetching JWKS: {exc}"
            ) from exc

        keys = data.get("keys")
        if not isinstance(keys, list) or len(keys) == 0:
            raise JWKSFetchError(
                "JWKS document contained no keys. "
                "Check the Supabase project URL."
            )

        return keys

    def _refresh(self) -> None:
        """Unconditionally re-fetch and replace the cache."""
        keys = self._fetch()
        with self._lock:
            self._keys = keys
            self._fetched_at = time.monotonic()

    def get_keys(self) -> list[dict[str, Any]]:
        """Return cached keys, refreshing if TTL has expired."""
        with self._lock:
            if self._is_expired() or not self._keys:
                keys = self._fetch()
                self._keys = keys
                self._fetched_at = time.monotonic()
            return list(self._keys)

    def get_key_for_kid(self, kid: str) -> dict[str, Any] | None:
        """
        Return the JWK matching the given key ID, or None.

        If the kid is not found in the current cache, the cache is
        refreshed once (to handle recently rotated keys) before
        returning None if still not found.
        """
        keys = self.get_keys()
        match = next((k for k in keys if k.get("kid") == kid), None)
        if match is not None:
            return match

        # kid not in cache — refresh once and retry.
        logger.info("kid %r not found in JWKS cache, refreshing.", kid)
        try:
            self._refresh()
        except JWKSFetchError as exc:
            logger.error("JWKS refresh failed on kid miss: %s", exc)
            return None

        with self._lock:
            return next((k for k in self._keys if k.get("kid") == kid), None)


# Module-level singleton — shared across all requests in the same process.
jwks_cache = _JWKSCache()
