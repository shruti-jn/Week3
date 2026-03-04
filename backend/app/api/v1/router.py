"""
API v1 router — aggregates all route handlers into one router.

This file is like a switchboard: it connects all the individual
endpoint files (query, explain, etc.) into a single router that
the main app registers under the /api/v1 prefix.

To add a new endpoint:
1. Create the route file in backend/app/api/v1/
2. Import its router here
3. Include it with api_router.include_router(...)
"""

from typing import Any

import voyageai
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pinecone import Pinecone

from app.api.v1.dependencies import get_current_user
from app.config import get_settings
from app.core.query_pipeline import stream_query_sse
from app.dependencies import get_openai_client, get_pinecone_client, get_voyage_client
from app.models.requests import (
    BusinessLogicRequest,
    DependenciesRequest,
    ExplainRequest,
    ImpactRequest,
    QueryRequest,
)
from app.models.responses import (
    BusinessLogicResponse,
    DependenciesResponse,
    ExplainResponse,
    ImpactResponse,
)

api_router = APIRouter()


# ── Query endpoint — full SSE pipeline ───────────────────────────────────────
@api_router.post("/query", tags=["query"])
async def query_endpoint(
    request: QueryRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    voyage_client: voyageai.Client = Depends(get_voyage_client),  # noqa: B008  # type: ignore[name-defined]  # no stubs
    openai_client: AsyncOpenAI = Depends(get_openai_client),  # noqa: B008
    pinecone_client: Pinecone = Depends(get_pinecone_client),  # noqa: B008
) -> StreamingResponse:
    """
    Query the COBOL codebase with a natural language question.

    Returns a Server-Sent Events (SSE) stream in this order:
      1. event: snippets — list of matching COBOL code chunks (JSON array)
      2. event: token    — one chunk of the GPT answer (repeats many times)
      3. event: done     — pipeline finished
      OR
      1. event: error    — something failed

    Clients are injected via FastAPI Depends() so unit tests can swap them
    for mocks without hitting real APIs:
      - voyage_client: voyage-code-2 embeds the user query (sync, thread-wrapped)
      - openai_client: gpt-4o-mini generates the natural-language answer
      - pinecone_client: vector DB lookup for similar COBOL chunks

    Args:
        request:        Validated query with question and top_k setting.
        voyage_client:  Voyage AI client (injected).
        openai_client:  Async OpenAI client (injected).
        pinecone_client: Pinecone client (injected).

    Returns:
        StreamingResponse with media_type="text/event-stream".
    """
    settings = get_settings()
    _ = current_user  # auth enforced; user info not needed in pipeline

    return StreamingResponse(
        stream_query_sse(
            query=request.query,
            top_k=request.top_k,
            voyage_client=voyage_client,
            openai_client=openai_client,
            pinecone_client=pinecone_client,
            settings=settings,
        ),
        media_type="text/event-stream",
        headers={
            # Prevent proxies and CDNs from buffering the stream.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            # Allow the frontend to read these headers cross-origin.
            "Access-Control-Expose-Headers": "Content-Type",
        },
    )


# ── Placeholder: Explain endpoint ─────────────────────────────────────────────
@api_router.post("/explain", response_model=ExplainResponse, tags=["features"])
async def explain_stub(
    request: ExplainRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> ExplainResponse:
    """Stub: Code Explanation (Feature 1). Replaced in feature/api-code-features."""
    _ = current_user
    return ExplainResponse(
        status="stub",
        message="Not yet implemented",
        paragraph_name=request.paragraph_name,
    )


# ── Placeholder: Dependencies endpoint ────────────────────────────────────────
@api_router.post(
    "/dependencies", response_model=DependenciesResponse, tags=["features"]
)
async def dependencies_stub(
    request: DependenciesRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> DependenciesResponse:
    """Stub: Dependency Mapping (Feature 2). Replaced in feature/api-code-features."""
    _ = current_user
    return DependenciesResponse(
        status="stub",
        message="Not yet implemented",
        paragraph_name=request.paragraph_name,
    )


# ── Placeholder: Business Logic endpoint ──────────────────────────────────────
@api_router.post(
    "/business-logic", response_model=BusinessLogicResponse, tags=["features"]
)
async def business_logic_stub(
    request: BusinessLogicRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> BusinessLogicResponse:
    """Stub: Business Logic (Feature 3). Replaced in feature/api-code-features."""
    _ = current_user
    return BusinessLogicResponse(
        status="stub",
        message="Not yet implemented",
        file_path=request.file_path,
    )


# ── Placeholder: Impact Analysis endpoint ─────────────────────────────────────
@api_router.post("/impact", response_model=ImpactResponse, tags=["features"])
async def impact_stub(
    request: ImpactRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> ImpactResponse:
    """Stub: Impact Analysis (Feature 4). Replaced in feature/api-code-features."""
    _ = current_user
    return ImpactResponse(
        status="stub",
        message="Not yet implemented",
        paragraph_name=request.paragraph_name,
    )
