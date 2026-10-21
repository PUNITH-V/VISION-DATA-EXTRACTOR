"""
RAG service.

Retrieves user-scoped context from ChromaDB, then passes it to the LLM.
All retrieval applies the mandatory user_id filter — the existing
app/rag.py does not scope by user, so we replicate its logic here
with the isolation layer applied.
"""

from __future__ import annotations

import logging

from api.schemas import AskResponse, AskSource
from api.services.report_service import _chroma_dir_for_user
from app.llm_client import LLMClient, LLMClientError
from app.rag import SYSTEM_PROMPT
from config.settings import API_KEY, BASE_URL, MODEL
from embeddings.embedder import TextEmbedder
from vector_stores.chroma_store import ChromaStore

logger = logging.getLogger(__name__)


def ask_user_question(
    *,
    user_id: str,
    question: str,
    top_k: int = 3,
) -> AskResponse:
    """
    Answer a question grounded in the user's indexed reports.

    Returns AskResponse with grounded=False if the index is empty
    or the LLM signals insufficient context.
    Propagates LLMClientError to the route so it can return 502.
    """
    chroma_dir = _chroma_dir_for_user(user_id)
    store = ChromaStore(persist_directory=str(chroma_dir))

    if store.count() == 0:
        return AskResponse(
            answer=(
                "No reports are indexed yet for your account. "
                "Upload images and run ingestion first."
            ),
            sources=[],
            grounded=False,
        )

    embedder = TextEmbedder()
    query_embedding = embedder.embed_text(question)

    raw = store.search(
        query_embedding=query_embedding,
        top_k=top_k,
        where={"user_id": user_id},
    )

    ids = raw.get("ids", [[]])[0]
    docs = raw.get("documents", [[]])[0]
    metas = raw.get("metadatas", [[]])[0]
    distances = raw.get("distances", [[]])[0]

    # Build context sections, enforcing isolation defensively.
    context_sections: list[str] = []
    sources: list[AskSource] = []

    for report_id, doc, meta, dist in zip(ids, docs, metas, distances):
        if meta.get("user_id") != user_id:
            logger.error(
                "ISOLATION VIOLATION in RAG: result user_id=%s != "
                "requesting user_id=%s. Suppressing.",
                meta.get("user_id"),
                user_id,
            )
            continue

        stable_id = meta.get("report_id", report_id)
        filename = meta.get("image_filename", "unknown")

        context_sections.append(
            f"Source report: {stable_id}\n"
            f"Image filename: {filename}\n"
            f"Extraction confidence: {meta.get('confidence', 'Unknown')}\n"
            f"Cosine distance: {dist:.4f}\n"
            f"Report content:\n{doc}"
        )
        sources.append(
            AskSource(
                report_id=stable_id,
                image_filename=filename,
                cosine_distance=round(float(dist), 4),
            )
        )

    if not context_sections:
        return AskResponse(
            answer="No relevant reports were found in your index for this question.",
            sources=[],
            grounded=False,
        )

    context = "\n\n---\n\n".join(context_sections)
    user_prompt = f"""
Question:
{question}

Retrieved evidence:
<context>
{context}
</context>

Answer the question using the retrieved evidence.
Mention the source report filename(s).
If the evidence is insufficient, say so clearly.
"""

    llm = LLMClient(api_key=API_KEY, base_url=BASE_URL, model=MODEL)
    # LLMClientError propagates — the route converts it to 502.
    answer_text = llm.generate(SYSTEM_PROMPT, user_prompt)

    # Heuristic: treat uncertainty phrases as ungrounded.
    uncertainty_phrases = (
        "i don't have",
        "cannot determine",
        "not enough evidence",
        "evidence is insufficient",
        "no information",
    )
    grounded = not any(
        phrase in answer_text.lower() for phrase in uncertainty_phrases
    )

    return AskResponse(answer=answer_text, sources=sources, grounded=grounded)
