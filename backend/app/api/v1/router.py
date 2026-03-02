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

# Import individual feature routers
# (These files will be created as we build each feature branch)

api_router = APIRouter()


# ── Placeholder: Query endpoint ──────────────────────────────────────────────
# This stub returns a hardcoded response while the real implementation
# is being built. This lets the frontend connect and test the API contract
# even before the retrieval pipeline is ready.
#
# TODO (feature/api-full-pipeline): Replace stub with real implementation
@api_router.post("/query", tags=["query"])
async def query_stub() -> dict[str, str]:
    """
    Stub: Query the COBOL codebase with a natural language question.

    TEMPORARY: Returns a hardcoded response.
    Replace with the real implementation in feature/api-full-pipeline.
    """
    return {
        "status": "stub",
        "message": "Query endpoint not yet implemented — this is a scaffold stub",
        "answer": "",
        "chunks": "[]",
    }


# ── Placeholder: Explain endpoint ─────────────────────────────────────────────
@api_router.post("/explain", tags=["features"])
async def explain_stub() -> dict[str, str]:
    """Stub: Code Explanation feature (Feature 1). Replace in feature/api-feature-endpoints."""
    return {"status": "stub", "message": "Not yet implemented"}


# ── Placeholder: Dependencies endpoint ────────────────────────────────────────
@api_router.post("/dependencies", tags=["features"])
async def dependencies_stub() -> dict[str, str]:
    """Stub: Dependency Mapping feature (Feature 2). Replace in feature/api-feature-endpoints."""
    return {"status": "stub", "message": "Not yet implemented"}


# ── Placeholder: Business Logic endpoint ──────────────────────────────────────
@api_router.post("/business-logic", tags=["features"])
async def business_logic_stub() -> dict[str, str]:
    """Stub: Business Logic Extraction feature (Feature 3). Replace in feature/api-feature-endpoints."""
    return {"status": "stub", "message": "Not yet implemented"}


# ── Placeholder: Impact Analysis endpoint ─────────────────────────────────────
@api_router.post("/impact", tags=["features"])
async def impact_stub() -> dict[str, str]:
    """Stub: Impact Analysis feature (Feature 4). Replace in feature/api-feature-endpoints."""
    return {"status": "stub", "message": "Not yet implemented"}
