"""POST /api/search — semantic search over the user's indexed reports."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import AuthenticatedUser, get_current_user
from api.schemas import SearchRequest, SearchResponse
from api.services.search_service import search_user_reports

router = APIRouter()


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Semantic search over indexed reports",
    tags=["Search"],
)
def semantic_search(
    body: SearchRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SearchResponse:
    """
    Embed the query and retrieve the closest matching reports from the
    authenticated user's vector index.

    ``cosine_distance`` is a geometric distance in [0, 2].
    Lower values indicate greater semantic similarity.
    It is **not** a probability or percentage.

    Returns an empty ``results`` list when the index has no entries —
    this is not an error.
    """
    try:
        return search_user_reports(
            user_id=current_user.user_id,
            query=body.query,
            top_k=body.top_k,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
