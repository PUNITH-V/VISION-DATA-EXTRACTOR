"""POST /api/extractions — upload an image and extract structured data."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from api.dependencies import AuthenticatedUser, get_current_user
from api.schemas import ExtractionResponse
from api.services.extraction_service import (
    ExtractionUpstreamError,
    ExtractionValidationError,
    extract_from_bytes,
)
from api.services.report_service import save_report

logger = logging.getLogger(__name__)

router = APIRouter()

# Accept only these declared content types.
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}


@router.post(
    "/extractions",
    response_model=ExtractionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image and extract structured data",
    tags=["Extractions"],
)
async def create_extraction(
    file: UploadFile,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ExtractionResponse:
    """
    Accept a JPEG or PNG upload, run the vision extraction pipeline,
    save the report under the authenticated user's directory, and
    return the structured report.

    - Returns 400 for invalid file type, size limit, or corrupt image.
    - Returns 401/503 when authentication is not available (Stage 2/3).
    - Returns 422 when the vision model returns unvalidatable JSON.
    - Returns 502 when the upstream vision API fails.
    """
    # Validate the declared content type before reading bytes.
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{content_type}'. Upload a JPEG or PNG.",
        )

    file_bytes = await file.read()

    # Sanitise the filename for display only — never used as a path.
    original_filename = (file.filename or "upload").strip()
    if not original_filename:
        original_filename = "upload"

    try:
        report = extract_from_bytes(
            file_bytes=file_bytes,
            content_type=content_type,
            original_filename=original_filename,
        )
    except ExtractionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ExtractionUpstreamError as exc:
        logger.error("Upstream error for user %s: %s", current_user.user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vision API error: {exc}",
        ) from exc
    except ValueError as exc:
        # parse_model_response validation failure.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Model response validation failed: {exc}",
        ) from exc

    saved = save_report(
        user_id=current_user.user_id,
        report=report,
        original_filename=original_filename,
    )
    return saved
