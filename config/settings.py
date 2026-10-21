import os
import pathlib
from dotenv import load_dotenv

load_dotenv()

# ── OpenRouter ─────────────────────────────────────────────────────────────
API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
BASE_URL = "https://openrouter.ai/api/v1"

if not API_KEY:
    raise ValueError(
        "OPENROUTER_API_KEY is missing. "
        "Add it to your .env file."
    )

# ── FastAPI / server ────────────────────────────────────────────────────────
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

UPLOAD_MAX_BYTES: int = int(os.getenv("UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))

# ── Storage paths ───────────────────────────────────────────────────────────
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS_BASE_DIR = pathlib.Path(
    os.getenv("REPORTS_BASE_DIR", str(PROJECT_ROOT / "output"))
)
CHROMA_BASE_DIR = pathlib.Path(
    os.getenv("CHROMA_BASE_DIR", str(PROJECT_ROOT / "chroma_data"))
)

# ── Supabase authentication ─────────────────────────────────────────────────
#
# SUPABASE_URL:
#   Your project URL, e.g. https://xxxxxxxxxxxx.supabase.co
#   Required when AUTH_ENABLED=true. Used to:
#     • Derive the JWKS endpoint: {SUPABASE_URL}/auth/v1/.well-known/jwks.json
#     • Validate the JWT "iss" (issuer) claim: {SUPABASE_URL}/auth/v1
#
# SUPABASE_JWT_SECRET:
#   The legacy HS256 shared secret, found at:
#     Dashboard → Settings → Authentication → JWT Settings → "JWT Secret"
#   Required ONLY if your project still accepts HS256-signed tokens
#   (tokens signed before the ES256 key rotation completed).
#   Optional if your project has revoked the legacy key.
#
# AUTH_ENABLED:
#   Set to "true" once SUPABASE_URL is configured and Stage 3 is ready.
#   Defaults to "false" so the server starts safely without credentials.
#
SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
SUPABASE_JWT_SECRET: str | None = os.getenv("SUPABASE_JWT_SECRET")
AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "false").lower() == "true"

# Derived — not a separate env var to avoid sync errors.
# The JWKS endpoint is always at this path for Supabase-hosted projects.
SUPABASE_JWKS_URL: str | None = (
    f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
    if SUPABASE_URL
    else None
)

# The expected JWT issuer claim. Supabase always uses this form.
SUPABASE_JWT_ISSUER: str | None = (
    f"{SUPABASE_URL.rstrip('/')}/auth/v1"
    if SUPABASE_URL
    else None
)

# Algorithms accepted by this server, in priority order.
# ES256 = current Supabase key (ECC P-256, asymmetric).
# HS256 = legacy key, retained for unexpired tokens during transition.
# No other algorithms are accepted.
ALLOWED_JWT_ALGORITHMS: list[str] = ["ES256", "HS256"]

# JWKS cache TTL in seconds. Keys are re-fetched after this period
# or immediately on a key-ID miss (to handle key rotation).
JWKS_CACHE_TTL_SECONDS: int = int(os.getenv("JWKS_CACHE_TTL_SECONDS", "600"))
