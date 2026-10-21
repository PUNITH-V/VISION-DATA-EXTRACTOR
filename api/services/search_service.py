"""
Semantic search service.

All ChromaDB queries apply a mandatory `where={"user_id": user_id}` filter.
There is no code path that retrieves another user's vectors.
"""

from __future__ import annotations

import logging

from api.schemas import SearchResponse, SearchResult
from api.services.report_service import _chroma_dir_for_user
from embeddings.embedder import TextEmbedder
from vector_stores.chroma_store import ChromaStore

logger = logging.getLogger(__name__)


def search_user_reports(
    *,
    user_id: str,
    query: str,
    top_k: int = 5,
) -> SearchResponse:
    """
    Return the top_k semantically closest reports for this user.

    The ChromaDB query always includes the user_id filter.
    An empty index returns an empty result list, not an error.
    """
    chroma_dir = _chroma_dir_for_user(user_id)
    store = ChromaStore(persist_directory=str(chroma_dir))

    if store.count() == 0:
        return SearchResponse(results=[], query=query, total=0)

    embedder = TextEmbedder()
    query_embedding = embedder.embed_text(query)

    raw = store.search(
        query_embedding=query_embedding,
        top_k=top_k,
        where={"user_id": user_id},
    )

    results: list[SearchResult] = []
    ids = raw.get("ids", [[]])[0]
    docs = raw.get("documents", [[]])[0]
    metas = raw.get("metadatas", [[]])[0]
    distances = raw.get("distances", [[]])[0]

    for report_id, doc, meta, dist in zip(ids, docs, metas, distances):
        # Defensive check: never surface records belonging to another user.
        if meta.get("user_id") != user_id:
            logger.error(
                "ISOLATION VIOLATION: result user_id=%s does not match "
                "requesting user_id=%s for report %s. Suppressing.",
                meta.get("user_id"),
                user_id,
                report_id,
            )
            continue

        results.append(
            SearchResult(
                report_id=meta.get("report_id", report_id),
                image_filename=meta.get("image_filename", "unknown"),
                snippet=doc[:300],  # first 300 chars for the UI snippet
                cosine_distance=round(float(dist), 4),
                confidence=meta.get("confidence", "Low"),
            )
        )

    return SearchResponse(results=results, query=query, total=len(results))
