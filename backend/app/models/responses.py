"""
Pydantic models for outgoing API response bodies.

These models define the exact shape of every response the API sends.
Using Pydantic models (instead of raw dicts) ensures:
1. Type safety — mypy can verify the response matches its declared type
2. Automatic OpenAPI docs — FastAPI generates correct response schemas
3. Serialization consistency — dates, floats, nested objects are handled correctly

Sub-models (like CodeSnippet) are defined first so the top-level response
models can reference them.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Shared sub-models
# ─────────────────────────────────────────────────────────────────────────────


class CodeSnippet(BaseModel):
    """
    A single COBOL code snippet retrieved from the vector database.

    Think of this like a search result card in Google — it shows you where
    to find the relevant code (file + line numbers) and what the code says.

    Each snippet has a similarity score: 1.0 means a perfect match,
    0.75 is our minimum threshold (anything lower is ignored).
    """

    file_path: str = Field(
        ...,
        min_length=1,
        description="Relative path to the COBOL source file.",
    )
    start_line: int = Field(
        ...,
        ge=1,
        description="First line of the snippet (1-indexed, inclusive).",
    )
    end_line: int = Field(
        ...,
        ge=1,
        description="Last line of the snippet (1-indexed, inclusive).",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Raw COBOL source code for this snippet.",
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Cosine similarity score from Pinecone (0.0–1.0).",
    )

    def model_post_init(self, __context: object) -> None:
        """
        Validate that end_line is not before start_line.

        A snippet where the last line comes before the first line
        is a data corruption bug — we catch it here rather than
        letting it silently produce nonsense output.
        """
        if self.end_line < self.start_line:
            msg = f"end_line ({self.end_line}) must be >= start_line ({self.start_line})."
            raise ValueError(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Primary response models
# ─────────────────────────────────────────────────────────────────────────────


class QueryResponse(BaseModel):
    """
    Response body for POST /api/v1/query.

    Contains the LLM-generated answer plus the COBOL code snippets
    that were used as context to produce that answer.

    The query_time_ms field lets the frontend show latency to the user
    and lets us monitor whether we're hitting the <3 second target.
    """

    answer: str = Field(
        ...,
        min_length=1,
        description="GPT-4o-mini generated answer to the user's question.",
    )
    snippets: list[CodeSnippet] = Field(
        default_factory=list,
        description="COBOL code chunks used as context for the answer.",
    )
    query_time_ms: float = Field(
        ...,
        ge=0.0,
        description="Total end-to-end query time in milliseconds.",
    )


class HealthResponse(BaseModel):
    """
    Response body for GET /health.

    Used by Railway, Docker, and CI to verify the server is alive.
    The status field is always "ok" when healthy.
    """

    status: str = Field(..., description='Always "ok" when healthy.')
    service: str = Field(..., description="Service name identifier.")


class StubResponse(BaseModel):
    """
    Temporary response body for unimplemented endpoints.

    Used as a placeholder while the real implementation is being built.
    The status field is always "stub" so the frontend can detect this case.

    All stub endpoints will be replaced in feature/api-full-pipeline.
    """

    status: str = Field(..., description='"stub" for unimplemented endpoints.')
    message: str = Field(..., description="Human-readable explanation.")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 feature response models (stubs for now, real data in Phase 2)
# ─────────────────────────────────────────────────────────────────────────────


class ExplainResponse(BaseModel):
    """
    Response body for POST /api/v1/explain — Feature 1: Code Explanation.

    When the feature is implemented, 'explanation' contains a plain-English
    summary of what the COBOL paragraph does. During Phase 1 it is None.
    """

    status: str
    message: str
    paragraph_name: str
    explanation: Optional[str] = None


class DependenciesResponse(BaseModel):
    """
    Response body for POST /api/v1/dependencies — Feature 2: Dependency Mapping.

    When implemented, 'calls' lists paragraphs this paragraph PERFORMs,
    and 'called_by' lists paragraphs that PERFORM this one.
    """

    status: str
    message: str
    paragraph_name: str
    calls: list[str] = Field(default_factory=list)
    called_by: list[str] = Field(default_factory=list)


class BusinessLogicResponse(BaseModel):
    """
    Response body for POST /api/v1/business-logic — Feature 3.

    When implemented, 'rules' is a list of plain-English business rules
    extracted from the COBOL file (e.g., "Overtime applies after 40 hours").
    """

    status: str
    message: str
    file_path: str
    rules: list[str] = Field(default_factory=list)


class ImpactResponse(BaseModel):
    """
    Response body for POST /api/v1/impact — Feature 4: Impact Analysis.

    When implemented, 'affected_paragraphs' lists all paragraphs that
    would be impacted if the specified paragraph were changed.
    """

    status: str
    message: str
    paragraph_name: str
    affected_paragraphs: list[str] = Field(default_factory=list)
