"""POST /api/ask — RAG question answering over the user's indexed reports."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import AuthenticatedUser, get_current_user
from api.schemas import AskRequest, AskResponse
from api.services.rag_service import ask_user_question
from app.llm_client import LLMClientError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a question grounded in the user's indexed reports",
    tags=["RAG"],
)
def ask_question(
    body: AskRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AskResponse:
    """
    Retrieve relevant report context from the authenticated user's index
    and generate a grounded answer using the configured LLM.

    - ``grounded: false`` is returned (not an error) when the index is
      empty or the model indicates insufficient evidence.
    - Returns 502 when the upstream LLM API fails.
    - Source report IDs and filenames in the response are real —
      they come from indexed data, never fabricated.
    """
    try:
        return ask_user_question(
            user_id=current_user.user_id,
            question=body.question,
            top_k=body.top_k,
        )
    except LLMClientError as exc:
        logger.error(
            "LLM error for user %s: %s", current_user.user_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Language model error: {exc}",
        ) from exc
