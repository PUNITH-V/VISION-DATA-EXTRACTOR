"""
Extraction service.

Bridges the FastAPI upload endpoint and the existing vision pipeline.
Key responsibilities:
  - Accept raw bytes from an UploadFile (not a filesystem path).
  - Validate file type and size before touching the AI APIs.
  - Write bytes to a temp file so the existing image_loader can validate
    the image content with Pillow (it expects a filesystem path).
  - Reuse app.main.parse_model_response and app.vision_client.VisionClient.
  - Clean up temp files regardless of outcome.
  - Translate pipeline errors into typed exceptions the route can handle.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from app.image_loader import load_image
from app.main import parse_model_response
from app.schemas import VisionExtractionReport
from app.vision_client import VisionClient, VisionClientError
from config.settings import API_KEY, BASE_URL, MODEL, UPLOAD_MAX_BYTES

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
# Pillow/image_loader only accepts these suffixes.
_SUFFIX_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

EXTRACTION_PROMPT = """
Analyze the supplied image and extract information that is visibly
supported by the image.

Return exactly one JSON object with these fields:
{
  "image_description": "Brief description of the image",
  "extracted_data": [
    {
      "label": "Name of an extracted item",
      "value": "Its corresponding value"
    }
  ],
  "confidence": "High"
}

Requirements:
- confidence must be exactly "High", "Medium", or "Low".
- Use valid JSON with double quotes around keys and string values.
- Do not include Markdown fences or text outside the JSON object.
- Do not invent details that cannot be supported by the image.
"""


class ExtractionValidationError(ValueError):
    """Raised for client-side problems: bad file type, size, or corrupt image."""


class ExtractionUpstreamError(RuntimeError):
    """Raised when the upstream vision API fails."""


def extract_from_bytes(
    *,
    file_bytes: bytes,
    content_type: str,
    original_filename: str,
) -> VisionExtractionReport:
    """
    Validate the uploaded bytes, call the vision API, parse and return the report.

    Raises:
        ExtractionValidationError: file type, size, or image content problems.
        ExtractionUpstreamError: vision API or model failures.
        ValueError: model response fails schema validation.
    """
    # ── 1. Content-type validation ───────────────────────────────────────
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ExtractionValidationError(
            f"Unsupported file type '{content_type}'. "
            f"Upload a JPEG or PNG image."
        )

    # ── 2. Size validation ────────────────────────────────────────────────
    if len(file_bytes) > UPLOAD_MAX_BYTES:
        max_mb = UPLOAD_MAX_BYTES / (1024 * 1024)
        raise ExtractionValidationError(
            f"File exceeds the {max_mb:.0f} MB upload limit "
            f"({len(file_bytes) / (1024 * 1024):.1f} MB received)."
        )

    if len(file_bytes) == 0:
        raise ExtractionValidationError("Uploaded file is empty.")

    # ── 3. Image content validation via Pillow ────────────────────────────
    suffix = _SUFFIX_BY_CONTENT_TYPE[content_type]
    tmp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False
        ) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = Path(tmp_file.name)

        try:
            image_data = load_image(str(tmp_path))
        except (ValueError, FileNotFoundError) as exc:
            raise ExtractionValidationError(
                f"Image validation failed: {exc}"
            ) from exc

    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()

    # ── 4. Vision API call ────────────────────────────────────────────────
    vision_client = VisionClient(
        api_key=API_KEY,
        base_url=BASE_URL,
        model=MODEL,
    )

    try:
        raw_response = vision_client.analyze_image(
            image_base64=image_data["image_base64"],
            mime_type=image_data["mime_type"],
            prompt=EXTRACTION_PROMPT,
        )
    except VisionClientError as exc:
        logger.warning(
            "Vision API error for '%s': %s", original_filename, exc
        )
        raise ExtractionUpstreamError(str(exc)) from exc

    # ── 5. Parse and validate the model response ──────────────────────────
    # parse_model_response raises ValueError on bad JSON or schema mismatch.
    report = parse_model_response(raw_response)
    return report
