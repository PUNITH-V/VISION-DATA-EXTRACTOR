"""GET /api/reports and GET /api/reports/{report_id}"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import AuthenticatedUser, get_current_user
from api.schemas import ReportDetail, ReportSummary
from api.services.report_service import get_report, list_reports

router = APIRouter()


@router.get(
    "/reports",
    response_model=list[ReportSummary],
    summary="List all reports for the authenticated user",
    tags=["Reports"],
)
def get_reports(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[ReportSummary]:
    """
    Return summary metadata for every extraction report belonging to
    the authenticated user. Never returns another user's reports.
    """
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

    - Returns 404 when the report does not exist.
    - Returns 403 is not raised separately here: if a report_id does
      not exist in the user's directory, it simply returns 404.
      This avoids leaking whether a given ID belongs to someone else.
    """
    report = get_report(user_id=current_user.user_id, report_id=report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )
    return report
