"""
API-level Pydantic models for request validation and response serialisation.

These are distinct from app/schemas.py (the extraction report model).
Both live alongside each other: the extraction schemas define what the
vision model produces; these define what the HTTP API accepts and returns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Shared ──────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Returned for all 4xx / 5xx responses."""
    detail: str


# ── Health ──────────────────────────────────────────────────────────────────

class ServiceStatus(BaseModel):
    embedding_model: Literal["loaded", "unavailable"]
    vector_store: Literal["reachable", "unreachable"]
    llm_api: Literal["configured", "missing_key"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    services: ServiceStatus


# ── Extraction ───────────────────────────────────────────────────────────────

class ExtractedField(BaseModel):
    label: str
    value: str


class ExtractionResponse(BaseModel):
    report_id: str = Field(description="Server-assigned UUID for this report.")
    image_filename: str = Field(description="Sanitised original filename (display only).")
    image_description: str
    extracted_data: list[ExtractedField]
    confidence: Literal["High", "Medium", "Low"]
    created_at: datetime


# ── Reports ──────────────────────────────────────────────────────────────────

class ReportSummary(BaseModel):
    report_id: str
    image_filename: str
    confidence: Literal["High", "Medium", "Low"]
    field_count: int
    created_at: datetime
    indexed: bool


class ReportDetail(BaseModel):
    report_id: str
    image_filename: str
    image_description: str
    extracted_data: list[ExtractedField]
    confidence: Literal["High", "Medium", "Low"]
    created_at: datetime
    indexed: bool


# ── Ingestion ────────────────────────────────────────────────────────────────

class IngestionRequest(BaseModel):
    """Optional: index only a subset of reports by ID."""
    report_ids: list[str] | None = Field(
        default=None,
        description="If omitted, all unindexed reports for the user are indexed.",
    )


class IngestionResponse(BaseModel):
    discovered: int
    ingested: int
    skipped: int
    failed: int
    already_indexed: int


# ── Search ───────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    report_id: str
    image_filename: str
    snippet: str
    cosine_distance: float = Field(
        description=(
            "Cosine distance in [0, 2]. Lower means more similar. "
            "This is NOT a probability or percentage."
        )
    )
    confidence: str


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query: str
    total: int


# ── RAG / Ask ────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=10)


class AskSource(BaseModel):
    report_id: str
    image_filename: str
    cosine_distance: float


class AskResponse(BaseModel):
    answer: str
    sources: list[AskSource]
    grounded: bool = Field(
        description="False when the index is empty or the LLM indicated uncertainty."
    )
