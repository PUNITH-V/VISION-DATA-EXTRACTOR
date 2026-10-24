"""
Ingestion service.

Indexes user-owned reports into the ChromaDB collection.
Uses the user_id as both a report filter and a metadata field on every
vector, so that searches are scoped to the requesting user.

The existing app/ingestion.py is designed for a single-user CLI.
This service replaces its directory-scan logic with per-user report
directory access and adds the user_id field to every stored vector.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from api.schemas import IngestionResponse
from api.services.report_service import (
    _REPORT_ID_KEY,
    _FILENAME_KEY,
    _INDEX_FLAG_KEY,
    _CREATED_AT_KEY,
    _user_report_dir,
    _chroma_dir_for_user,
    _validate_report_id,
    mark_report_indexed,
)
# Note: the _-prefixed imports are intentional shared constants between
# these two sibling service modules. They are package-internal only.
from app.ingestion import report_to_document
from app.schemas import VisionExtractionReport
from embeddings.embedder import TextEmbedder
from vector_stores.chroma_store import ChromaStore

logger = logging.getLogger(__name__)


def ingest_user_reports(
    *,
    user_id: str,
    report_ids: list[str] | None = None,
) -> IngestionResponse:
    """
    Read validated reports from the user's report directory,
    embed them, and upsert into the shared ChromaDB collection.

    Every stored vector includes user_id in its metadata, enabling
    mandatory per-user filtering on retrieval.

    If report_ids is provided, only those reports are processed.
    Otherwise, all reports in the user's directory are considered.

    Already-indexed reports are counted but not re-embedded unless
    their _indexed flag is False.
    """
    report_dir = _user_report_dir(user_id)
    chroma_dir = _chroma_dir_for_user(user_id)

    embedder = TextEmbedder()
    store = ChromaStore(persist_directory=str(chroma_dir))

    summary = IngestionResponse(
        discovered=0,
        ingested=0,
        skipped=0,
        failed=0,
        already_indexed=0,
    )

    # Collect the report files to process.
    if report_ids is not None:
        # Validate each report_id as a UUID before constructing a filesystem path.
        # Invalid IDs are skipped (counted in summary.skipped) rather than
        # crashing the entire request.
        candidates = []
        for rid in report_ids:
            try:
                _validate_report_id(rid)
            except ValueError:
                logger.warning("Skipping invalid report_id in ingestion request: %r", rid)
                summary.skipped += 1
                continue
            candidates.append(report_dir / f"{rid}.json")
    else:
        candidates = sorted(report_dir.glob("*.json"), key=lambda p: p.name)

    summary.discovered = len(candidates)

    for report_path in candidates:
        if not report_path.exists():
            logger.warning("Report file not found: %s", report_path.name)
            summary.skipped += 1
            continue

        try:
            raw = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Cannot read %s: %s", report_path.name, exc)
            summary.failed += 1
            continue

        # Skip files not created by this service (no _report_id key).
        if _REPORT_ID_KEY not in raw:
            logger.info("Skipping legacy file %s (no _report_id)", report_path.name)
            summary.skipped += 1
            continue

        report_id = raw[_REPORT_ID_KEY]

        # Skip already-indexed reports.
        if raw.get(_INDEX_FLAG_KEY, False):
            summary.already_indexed += 1
            continue

        # Validate the domain data with the existing Pydantic schema.
        try:
            report = VisionExtractionReport.model_validate(raw)
        except ValidationError as exc:
            logger.warning("Validation failed for %s: %s", report_path.name, exc)
            summary.skipped += 1
            continue

        document = report_to_document(report)
        if not document.strip():
            logger.warning("Empty document for %s, skipping.", report_path.name)
            summary.skipped += 1
            continue

        try:
            embedding = embedder.embed_text(document)
        except Exception as exc:
            logger.error("Embedding failed for %s: %s", report_path.name, exc)
            summary.failed += 1
            continue

        metadata = {
            "user_id": user_id,                               # mandatory isolation field
            "image_filename": raw.get(_FILENAME_KEY, "unknown"),
            "confidence": raw.get("confidence", "Low"),
            "report_id": report_id,
            "created_at": raw.get(_CREATED_AT_KEY, ""),
        }

        try:
            store.upsert_report(
                report_id=report_id,
                document=document,
                embedding=embedding,
                metadata=metadata,
            )
        except Exception as exc:
            logger.error("ChromaDB upsert failed for %s: %s", report_id, exc)
            summary.failed += 1
            continue

        mark_report_indexed(user_id=user_id, report_id=report_id)
        summary.ingested += 1
        logger.info("Indexed report %s for user %s", report_id, user_id)

    return summary
