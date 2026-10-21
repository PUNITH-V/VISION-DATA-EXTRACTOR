"""POST /api/ingestion — index user reports into the vector store."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import AuthenticatedUser, get_current_user
from api.schemas import IngestionRequest, IngestionResponse
from api.services.ingestion_service import ingest_user_reports

router = APIRouter()


@router.post(
    "/ingestion",
    response_model=IngestionResponse,
    summary="Index reports into the vector store",
    tags=["Ingestion"],
)
def run_ingestion(
    body: IngestionRequest | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> IngestionResponse:
    """
    Embed and upsert the authenticated user's reports into ChromaDB.

    - If ``report_ids`` is provided, only those reports are indexed.
    - If omitted, all unindexed reports in the user's directory are processed.
    - Already-indexed reports are counted but not re-processed.
    - Every stored vector includes a ``user_id`` field for mandatory isolation.
    """
    report_ids = (body.report_ids if body else None)
    return ingest_user_reports(
        user_id=current_user.user_id,
        report_ids=report_ids,
    )
