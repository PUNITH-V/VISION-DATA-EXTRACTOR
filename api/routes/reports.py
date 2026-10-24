"""GET /api/reports, GET /api/reports/{report_id}, DELETE /api/reports/{report_id}"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from api.dependencies import AuthenticatedUser, get_current_user
from api.schemas import ReportDetail, ReportSummary
from api.services.report_service import (
    InvalidReportIdError,
    delete_report,
    get_report,
    list_reports,
    _chroma_dir_for_user,
)
from vector_stores.chroma_store import ChromaStore

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_id_or_404(report_id: str) -> None:
    """Validate report_id as a UUID. Returns 404 on failure (no info leak)."""
    try:
        uuid.UUID(report_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )


@router.get(
    "/reports",
    response_model=list[ReportSummary],
    summary="List all reports for the authenticated user",
    tags=["Reports"],
)
def get_reports(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[ReportSummary]:
    """Return summary metadata for every extraction report belonging to the user."""
    return list_reports(user_id=current_user.user_id)


@router.get(
    "/reports/{report_id}",
    response_model=ReportDetail,
    summary="Get a single report by ID",
    tags=["Reports"],
)
def get_report_by_id(
    report_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ReportDetail:
    """
    Return the full extraction report for the given report_id,
    provided it belongs to the authenticated user.
    Returns 404 when not found (avoids leaking IDs from other users).
    """
    _validate_id_or_404(report_id)
    try:
        report = get_report(user_id=current_user.user_id, report_id=report_id)
    except InvalidReportIdError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report not found.",
        )
    return report


class DeleteResponse(BaseModel):
    """Response body for partial or full deletion."""
    deleted: bool
    vector_cleaned: bool
    detail: str | None = None


@router.delete(
    "/reports/{report_id}",
    status_code=status.HTTP_200_OK,
    response_model=DeleteResponse,
    summary="Delete a report and its ChromaDB vector",
    tags=["Reports"],
)
def delete_report_by_id(
    report_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DeleteResponse:
    """
    Delete a saved extraction report and its corresponding ChromaDB vector.

    Ownership is enforced: only reports in the authenticated user's directory
    can be deleted. Returns 404 for non-existent or invalid IDs.

    Returns a DeleteResponse indicating whether both the JSON and the
    ChromaDB vector were successfully removed. If vector cleanup fails,
    the JSON is still deleted (data hygiene) but `vector_cleaned` is False
    and a warning detail is included. The orphaned vector contains only
    metadata (report_id, image_filename, confidence) — no image data.
    """
    _validate_id_or_404(report_id)

    # Step 1: verify ownership
    try:
        existing = get_report(user_id=current_user.user_id, report_id=report_id)
    except InvalidReportIdError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )

    # Step 2: remove from ChromaDB if the report was indexed
    vector_cleaned = True
    if existing.indexed:
        try:
            chroma_dir = _chroma_dir_for_user(current_user.user_id)
            store = ChromaStore(persist_directory=str(chroma_dir))
            store.delete_report(report_id)
            logger.info(
                "Deleted ChromaDB vector %s for user %s",
                report_id, current_user.user_id,
            )
        except Exception as exc:
            # Vector cleanup failed — log and mark as not cleaned.
            # Proceed with JSON deletion (data hygiene) but report honestly.
            vector_cleaned = False
            logger.error(
                "ChromaDB vector deletion FAILED for report %s (user %s): %s. "
                "JSON will still be deleted. Orphaned vector contains only "
                "metadata — no image data.",
                report_id, current_user.user_id, exc,
            )

    # Step 3: delete the JSON file
    try:
        deleted = delete_report(user_id=current_user.user_id, report_id=report_id)
    except InvalidReportIdError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )
    except OSError as exc:
        logger.error("Failed to delete report file: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete the report file.",
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )

    # Step 4: return honest result
    detail = None
    if not vector_cleaned:
        detail = (
            "Report file deleted, but ChromaDB vector cleanup failed. "
            "The report will not appear in Reports, but may still appear "
            "in search results until reindexed. Contact admin if this persists."
        )

    return DeleteResponse(
        deleted=True,
        vector_cleaned=vector_cleaned,
        detail=detail,
    )
