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
from app.core.features.cobol_features import (
    _fetch_file_content,
    analyze_impact,
    explain_paragraph,
    extract_business_logic,
    map_dependencies,
)
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
    FileResponse,
    ImpactResponse,
)

api_router = APIRouter()


# ── Query endpoint — full SSE pipeline ───────────────────────────────────────
@api_router.post("/query", tags=["query"])
async def query_endpoint(
    request: QueryRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    voyage_client: voyageai.Client = Depends(get_voyage_client),  # type: ignore[name-defined]  # noqa: B008  # no stubs
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


# ── Feature 1: Code Explanation ───────────────────────────────────────────────
@api_router.post("/explain", response_model=ExplainResponse, tags=["features"])
async def explain_endpoint(
    request: ExplainRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    openai_client: AsyncOpenAI = Depends(get_openai_client),  # noqa: B008
) -> ExplainResponse:
    """
    Explain what a COBOL paragraph does in plain English.

    Fetches the source file from GitHub, sends it to GPT-4o-mini with
    the paragraph name, and returns a 2-4 sentence plain-English explanation.

    Args:
        request: file_path (stored Pinecone path) + paragraph_name.

    Returns:
        ExplainResponse with explanation field populated.
    """
    _ = current_user
    return await explain_paragraph(
        request.file_path, request.paragraph_name, openai_client
    )


# ── Feature 2: Dependency Mapping ─────────────────────────────────────────────
@api_router.post(
    "/dependencies", response_model=DependenciesResponse, tags=["features"]
)
async def dependencies_endpoint(
    request: DependenciesRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    openai_client: AsyncOpenAI = Depends(get_openai_client),  # noqa: B008
) -> DependenciesResponse:
    """
    Map the PERFORM call graph for a COBOL paragraph.

    Returns which paragraphs this one calls (calls) and which call it (called_by).

    Args:
        request: file_path + paragraph_name.

    Returns:
        DependenciesResponse with calls and called_by lists.
    """
    _ = current_user
    return await map_dependencies(
        request.file_path, request.paragraph_name, openai_client
    )


# ── Feature 3: Business Logic Extraction ──────────────────────────────────────
@api_router.post(
    "/business-logic", response_model=BusinessLogicResponse, tags=["features"]
)
async def business_logic_endpoint(
    request: BusinessLogicRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    openai_client: AsyncOpenAI = Depends(get_openai_client),  # noqa: B008
) -> BusinessLogicResponse:
    """
    Extract plain-English business rules from an entire COBOL file.

    Reads the full file and returns a list of human-readable business rules
    encoded in the COBOL source (e.g. "Overtime applies after 40 hours").

    Args:
        request: file_path only (covers the whole file).

    Returns:
        BusinessLogicResponse with a list of business rule strings.
    """
    _ = current_user
    return await extract_business_logic(request.file_path, openai_client)


# ── Feature 4: Impact Analysis ────────────────────────────────────────────────
@api_router.post("/impact", response_model=ImpactResponse, tags=["features"])
async def impact_endpoint(
    request: ImpactRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    openai_client: AsyncOpenAI = Depends(get_openai_client),  # noqa: B008
) -> ImpactResponse:
    """
    Identify which COBOL paragraphs would break if a given paragraph changed.

    Returns a list of paragraph names that directly or indirectly PERFORM
    the target paragraph — i.e., the blast radius of a change.

    Args:
        request: file_path + paragraph_name.

    Returns:
        ImpactResponse with affected_paragraphs list.
    """
    _ = current_user
    return await analyze_impact(
        request.file_path, request.paragraph_name, openai_client
    )


# ── Full File Context: read raw source via GitHub ─────────────────────────────
@api_router.get("/file", response_model=FileResponse, tags=["features"])
async def file_endpoint(
    path: str,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> FileResponse:
    """
    Return the full raw COBOL source for a file (fetched from GitHub).

    Used by the frontend "View Full File" modal to display the complete source
    with the matched paragraph highlighted. Content is cached in memory so
    repeated requests for the same file are fast.

    Args:
        path: The file_path as stored in Pinecone metadata (absolute local path).
              Must contain 'gnucobol-contrib/' to be valid.

    Returns:
        FileResponse with content (raw source text) and line_count.
    """
    _ = current_user
    content = await _fetch_file_content(path)
    return FileResponse(
        file_path=path,
        content=content,
        line_count=content.count("\n") + 1,
    )
