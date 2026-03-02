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

from fastapi import APIRouter

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
    QueryResponse,
    StubResponse,
)

api_router = APIRouter()


# ── Placeholder: Query endpoint ──────────────────────────────────────────────
# This stub accepts a proper typed request body while the real implementation
# is being built in feature/api-full-pipeline.
#
# Replaced by: feature/api-full-pipeline
@api_router.post("/query", response_model=StubResponse, tags=["query"])
async def query_stub(request: QueryRequest) -> StubResponse:
    """
    Stub: Query the COBOL codebase with a natural language question.

    TEMPORARY: Returns a hardcoded stub response. Input validation via
    QueryRequest is live — the full pipeline (embedding, retrieval, generation)
    is wired in feature/api-full-pipeline.

    Args:
        request: Validated query with plain-English question and top_k setting.

    Returns:
        StubResponse with status="stub" until the pipeline is implemented.
    """
    # Log the query so we can see it in Railway logs even during the stub phase
    _ = request  # will be used when real logic is wired
    return StubResponse(
        status="stub",
        message="Query endpoint not yet implemented — this is a scaffold stub",
    )


# ── Placeholder: Explain endpoint ─────────────────────────────────────────────
@api_router.post("/explain", response_model=ExplainResponse, tags=["features"])
async def explain_stub(request: ExplainRequest) -> ExplainResponse:
    """Stub: Code Explanation feature (Feature 1). Replaced in feature/api-code-features."""
    _ = request
    return ExplainResponse(
        status="stub",
        message="Not yet implemented",
        paragraph_name=request.paragraph_name,
    )


# ── Placeholder: Dependencies endpoint ────────────────────────────────────────
@api_router.post(
    "/dependencies", response_model=DependenciesResponse, tags=["features"]
)
async def dependencies_stub(request: DependenciesRequest) -> DependenciesResponse:
    """Stub: Dependency Mapping feature (Feature 2). Replaced in feature/api-code-features."""
    _ = request
    return DependenciesResponse(
        status="stub",
        message="Not yet implemented",
        paragraph_name=request.paragraph_name,
    )


# ── Placeholder: Business Logic endpoint ──────────────────────────────────────
@api_router.post(
    "/business-logic", response_model=BusinessLogicResponse, tags=["features"]
)
async def business_logic_stub(request: BusinessLogicRequest) -> BusinessLogicResponse:
    """Stub: Business Logic Extraction feature (Feature 3). Replaced in feature/api-code-features."""
    _ = request
    return BusinessLogicResponse(
        status="stub",
        message="Not yet implemented",
        file_path=request.file_path,
    )


# ── Placeholder: Impact Analysis endpoint ─────────────────────────────────────
@api_router.post("/impact", response_model=ImpactResponse, tags=["features"])
async def impact_stub(request: ImpactRequest) -> ImpactResponse:
    """Stub: Impact Analysis feature (Feature 4). Replaced in feature/api-code-features."""
    _ = request
    return ImpactResponse(
        status="stub",
        message="Not yet implemented",
        paragraph_name=request.paragraph_name,
    )
