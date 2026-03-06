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

from pydantic import BaseModel, Field, model_validator

# ─────────────────────────────────────────────────────────────────────────────
# Shared sub-models
# ─────────────────────────────────────────────────────────────────────────────


class CodeSnippet(BaseModel):
    """
    A single COBOL code snippet retrieved from the vector database.

    Think of this like a search result card in Google — it shows you where
    to find the relevant code (file + line numbers) and what the code says.

    Scores:
    - score / combined_score: final reranked score shown in UI
    - cosine_score: raw Pinecone cosine similarity before keyword blending

    chunk_type tells you whether this snippet was split at a natural COBOL
    paragraph boundary ("paragraph") or cut at a fixed line count ("fixed").
    Paragraph chunks are usually more semantically coherent.
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
        description=(
            "Final reranked score (0.0-1.0). This is the same value as "
            "combined_score and is kept for backward compatibility."
        ),
    )
    cosine_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Raw cosine similarity score from Pinecone (0.0-1.0), before "
            "keyword-overlap blending."
        ),
    )
    combined_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Final blended relevance score (0.0-1.0): "
            "0.7 * cosine_score + 0.3 * keyword_score."
        ),
    )
    chunk_type: str = Field(
        default="paragraph",
        description=(
            'Chunking strategy: "paragraph" = COBOL boundary, "fixed" = line count.'
        ),
    )
    paragraph_name: str = Field(
        default="",
        description=(
            "COBOL paragraph label (e.g. CALCULATE-INTEREST). "
            "Empty string for fixed-size fallback chunks."
        ),
    )

    def model_post_init(self, __context: object) -> None:
        """
        Validate that end_line is not before start_line.

        A snippet where the last line comes before the first line
        is a data corruption bug — we catch it here rather than
        letting it silently produce nonsense output.
        """
        if self.end_line < self.start_line:
            msg = (
                f"end_line ({self.end_line}) must be >= start_line ({self.start_line})."
            )
            raise ValueError(msg)

    @model_validator(mode="after")
    def _normalize_score_fields(self) -> CodeSnippet:
        """
        Keep score fields consistent for old and new clients.

        - score is the canonical backward-compatible field.
        - combined_score defaults to score if omitted.
        - cosine_score defaults to score if omitted (legacy payloads had only score).
        """
        if self.combined_score is None:
            self.combined_score = self.score
        if self.cosine_score is None:
            self.cosine_score = self.score
        return self


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

    status: str = Field(..., min_length=1, description="Response status.")
    message: str = Field(..., min_length=1, description="Human-readable status detail.")
    paragraph_name: str = Field(..., min_length=1, description="COBOL paragraph label.")
    explanation: Optional[str] = None  # noqa: UP045 -- str | None fails Pydantic on Python 3.9


class DependenciesResponse(BaseModel):
    """
    Response body for POST /api/v1/dependencies — Feature 2: Dependency Mapping.

    When implemented, 'calls' lists paragraphs this paragraph PERFORMs,
    and 'called_by' lists paragraphs that PERFORM this one.
    """

    status: str = Field(..., min_length=1, description="Response status.")
    message: str = Field(..., min_length=1, description="Human-readable status detail.")
    paragraph_name: str = Field(..., min_length=1, description="COBOL paragraph label.")
    calls: list[str] = Field(default_factory=list)
    called_by: list[str] = Field(default_factory=list)


class BusinessLogicResponse(BaseModel):
    """
    Response body for POST /api/v1/business-logic — Feature 3.

    When implemented, 'rules' is a list of plain-English business rules
    extracted from the COBOL file (e.g., "Overtime applies after 40 hours").
    """

    status: str = Field(..., min_length=1, description="Response status.")
    message: str = Field(..., min_length=1, description="Human-readable status detail.")
    file_path: str = Field(
        ..., min_length=1, description="Path to the COBOL source file."
    )
    rules: list[str] = Field(default_factory=list)


class ImpactResponse(BaseModel):
    """
    Response body for POST /api/v1/impact — Feature 4: Impact Analysis.

    When implemented, 'affected_paragraphs' lists all paragraphs that
    would be impacted if the specified paragraph were changed.
    """

    status: str = Field(..., min_length=1, description="Response status.")
    message: str = Field(..., min_length=1, description="Human-readable status detail.")
    paragraph_name: str = Field(..., min_length=1, description="COBOL paragraph label.")
    affected_paragraphs: list[str] = Field(default_factory=list)


class FileResponse(BaseModel):
    """
    Response body for GET /api/v1/file — Full File Context viewer.

    Returns the raw COBOL source text for a file so the frontend can render
    a full-file modal with the matched paragraph highlighted.

    The file is fetched from GitHub raw content at request time (no local disk
    required) so this works identically on localhost and on Railway.
    """

    file_path: str = Field(
        ...,
        min_length=1,
        description=(
            "Absolute or relative path identifying the file (as stored in Pinecone)."
        ),
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Full raw COBOL source text of the file.",
    )
    line_count: int = Field(
        ...,
        ge=1,
        description="Total number of lines in the file.",
    )
