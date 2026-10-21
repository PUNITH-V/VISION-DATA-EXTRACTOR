"""
Report persistence service.

Manages per-user report storage under REPORTS_BASE_DIR/{user_id}/.
Report IDs are server-assigned UUIDs — client-supplied filenames are
never used as filesystem paths.

Isolation guarantees:
  - user_id is validated as a UUID at the API dependency layer before
    it reaches this service. Services assume it is safe but do not
    re-validate (single responsibility).
  - The user's directory is only created on write operations (save,
    mark_indexed). Read operations (list, get) return empty/None if
    the directory does not exist rather than creating it.
  - Report IDs are UUIDs. Path construction is:
      REPORTS_BASE_DIR / <uuid-user-id> / <uuid-report-id>.json
    Neither component comes from client input.

Legacy data:
  Existing flat files in output/ (no _report_id) are ignored by every
  function here. They are not deleted or migrated.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import VisionExtractionReport
from api.schemas import ExtractionResponse, ExtractedField, ReportDetail, ReportSummary
from config.settings import CHROMA_BASE_DIR, REPORTS_BASE_DIR

logger = logging.getLogger(__name__)

# Keys in the persisted JSON that are service metadata, not domain data.
_REPORT_ID_KEY = "_report_id"
_CREATED_AT_KEY = "_created_at"
_FILENAME_KEY = "_image_filename"
_INDEX_FLAG_KEY = "_indexed"


# ── Path helpers (no side-effects on read paths) ────────────────────────────

def _user_report_dir(user_id: str) -> Path:
    """Return the report directory path for a user. Does NOT create it."""
    return REPORTS_BASE_DIR / user_id


def _ensure_user_report_dir(user_id: str) -> Path:
    """Return the report directory for a user, creating it if absent.
    Called only from write operations."""
    path = REPORTS_BASE_DIR / user_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _chroma_dir_for_user(user_id: str) -> Path:
    """Return the ChromaDB persistence directory for a user.
    Creates the directory — only called from write/query operations."""
    path = CHROMA_BASE_DIR / user_id
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── Write operations ─────────────────────────────────────────────────────────

def save_report(
    *,
    user_id: str,
    report: VisionExtractionReport,
    original_filename: str,
) -> ExtractionResponse:
    """
    Persist a validated extraction report and return its API representation.

    Writes to REPORTS_BASE_DIR/{user_id}/{report_id}.json.
    Uses an atomic temp-file rename to avoid partial writes.
    """
    report_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)

    report_dir = _ensure_user_report_dir(user_id)
    report_path = report_dir / f"{report_id}.json"

    payload = report.model_dump()
    payload[_REPORT_ID_KEY] = report_id
    payload[_CREATED_AT_KEY] = created_at.isoformat()
    payload[_FILENAME_KEY] = original_filename
    payload[_INDEX_FLAG_KEY] = False

    temp_path = report_path.with_suffix(".json.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(report_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    logger.info("Saved report %s for user %s", report_id, user_id)

    return ExtractionResponse(
        report_id=report_id,
        image_filename=original_filename,
        image_description=report.image_description,
        extracted_data=[
            ExtractedField(label=d.label, value=d.value)
            for d in report.extracted_data
        ],
        confidence=report.confidence,
        created_at=created_at,
    )


def mark_report_indexed(user_id: str, report_id: str) -> bool:
    """
    Update the _indexed flag in the stored JSON. Returns True on success.
    Called by ingestion_service after a successful vector upsert.
    """
    report_path = _user_report_dir(user_id) / f"{report_id}.json"
    if not report_path.exists():
        return False

    payload = _load_report_payload(report_path)
    if payload is None:
        return False

    payload[_INDEX_FLAG_KEY] = True

    temp_path = report_path.with_suffix(".json.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(report_path)
        return True
    except OSError as exc:
        logger.error("Could not update index flag for %s: %s", report_id, exc)
        if temp_path.exists():
            temp_path.unlink()
        return False


# ── Read operations ──────────────────────────────────────────────────────────

def _load_report_payload(report_path: Path) -> dict | None:
    """Load a raw JSON report from disk. Returns None if unreadable."""
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read report %s: %s", report_path, exc)
        return None


def list_reports(user_id: str) -> list[ReportSummary]:
    """
    Return summary metadata for all valid reports belonging to the user.
    Returns an empty list if the user's directory does not exist
    (first-time user with no reports yet).
    """
    report_dir = _user_report_dir(user_id)
    if not report_dir.exists():
        return []

    summaries: list[ReportSummary] = []
    for report_path in sorted(report_dir.glob("*.json"), key=lambda p: p.name):
        payload = _load_report_payload(report_path)
        if payload is None:
            continue
        if _REPORT_ID_KEY not in payload:
            continue  # legacy file without service metadata — skip
        try:
            summaries.append(
                ReportSummary(
                    report_id=payload[_REPORT_ID_KEY],
                    image_filename=payload.get(_FILENAME_KEY, "unknown"),
                    confidence=payload.get("confidence", "Low"),
                    field_count=len(payload.get("extracted_data", [])),
                    created_at=datetime.fromisoformat(payload[_CREATED_AT_KEY]),
                    indexed=bool(payload.get(_INDEX_FLAG_KEY, False)),
                )
            )
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed report %s: %s", report_path.name, exc)

    return summaries


def get_report(user_id: str, report_id: str) -> ReportDetail | None:
    """
    Return full report detail for a given user + report_id.

    Returns None if the report does not exist for this user.
    This intentionally returns the same value whether the report_id
    belongs to another user or genuinely does not exist, preventing
    enumeration of other users' IDs.
    """
    report_path = _user_report_dir(user_id) / f"{report_id}.json"
    if not report_path.exists():
        return None

    payload = _load_report_payload(report_path)
    if payload is None or _REPORT_ID_KEY not in payload:
        return None

    try:
        return ReportDetail(
            report_id=payload[_REPORT_ID_KEY],
            image_filename=payload.get(_FILENAME_KEY, "unknown"),
            image_description=payload.get("image_description", ""),
            extracted_data=[
                ExtractedField(label=d["label"], value=d["value"])
                for d in payload.get("extracted_data", [])
            ],
            confidence=payload.get("confidence", "Low"),
            created_at=datetime.fromisoformat(payload[_CREATED_AT_KEY]),
            indexed=bool(payload.get(_INDEX_FLAG_KEY, False)),
        )
    except (KeyError, ValueError) as exc:
        logger.warning("Malformed report %s: %s", report_id, exc)
        return None
