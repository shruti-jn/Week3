"""
Unit tests for the API v1 router endpoints.

These tests verify that:
- Each endpoint accepts correctly shaped input
- Each endpoint returns correctly shaped output
- Invalid input is rejected with 422 (validation error), not 500
- Protected endpoints return 401 when no auth token is provided
- The /health endpoint responds correctly

We use the `test_client` fixture from conftest.py which already wires up
the FastAPI app with mocked OpenAI, Pinecone, and auth dependencies.

For the code-understanding feature endpoints (/explain, /dependencies,
/business-logic, /impact), the feature functions are patched at the router
level so these tests verify routing + schema validation without making
GitHub or OpenAI calls.

No real API calls are made — all external services are mocked.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.responses import (
    BusinessLogicResponse,
    DependenciesResponse,
    ExplainResponse,
    ImpactResponse,
)

# Valid gnucobol-contrib path used across feature endpoint tests
_VALID_PATH = "/data/gnucobol-contrib/payroll/PAYROLL.cob"

# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_check(test_client: AsyncClient) -> None:
    """Health endpoint returns 200 with status=ok."""
    response = await test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "service" in data


# ─────────────────────────────────────────────────────────────────────────────
# Query endpoint
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_stub_returns_stub_status(test_client: AsyncClient) -> None:
    """Query endpoint with valid input returns 200 with SSE stream.

    The /query endpoint is no longer a stub — it runs the full RAG pipeline.
    It returns a Server-Sent Events stream (text/event-stream), not JSON.
    """
    response = await test_client.post(
        "/api/v1/query",
        json={"query": "How does payroll calculation work?"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_query_stub_accepts_custom_top_k(test_client: AsyncClient) -> None:
    """Query endpoint accepts valid top_k values."""
    response = await test_client.post(
        "/api/v1/query",
        json={"query": "Find loan processing logic", "top_k": 10},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_query_stub_empty_query_rejected(test_client: AsyncClient) -> None:
    """Query endpoint rejects empty query string with 422."""
    response = await test_client.post(
        "/api/v1/query",
        json={"query": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_stub_missing_query_rejected(test_client: AsyncClient) -> None:
    """Query endpoint rejects request with no query field."""
    response = await test_client.post("/api/v1/query", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_stub_top_k_out_of_range_rejected(test_client: AsyncClient) -> None:
    """Query endpoint rejects top_k values outside 1-20 range."""
    response_low = await test_client.post(
        "/api/v1/query",
        json={"query": "test", "top_k": 0},
    )
    response_high = await test_client.post(
        "/api/v1/query",
        json={"query": "test", "top_k": 999},
    )
    assert response_low.status_code == 422
    assert response_high.status_code == 422


@pytest.mark.asyncio
async def test_query_stub_whitespace_only_rejected(test_client: AsyncClient) -> None:
    """Query endpoint rejects whitespace-only query strings."""
    response = await test_client.post(
        "/api/v1/query",
        json={"query": "   "},
    )
    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Explain endpoint
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explain_endpoint_valid_input(test_client: AsyncClient) -> None:
    """Explain endpoint calls explain_paragraph and returns its response."""
    mock_response = ExplainResponse(
        status="ok",
        message="ok",
        paragraph_name="CALC-GROSS-PAY",
        explanation="This paragraph calculates gross pay.",
    )
    with patch(
        "app.api.v1.router.explain_paragraph",
        new=AsyncMock(return_value=mock_response),
    ):
        response = await test_client.post(
            "/api/v1/explain",
            json={
                "file_path": _VALID_PATH,
                "paragraph_name": "CALC-GROSS-PAY",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["paragraph_name"] == "CALC-GROSS-PAY"
    assert data["explanation"] == "This paragraph calculates gross pay."


@pytest.mark.asyncio
async def test_explain_stub_missing_fields_rejected(test_client: AsyncClient) -> None:
    """Explain endpoint rejects requests with missing required fields."""
    response = await test_client.post(
        "/api/v1/explain",
        json={"file_path": "samples/payroll.cob"},  # missing paragraph_name
    )
    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Dependencies endpoint
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dependencies_endpoint_valid_input(test_client: AsyncClient) -> None:
    """Dependencies endpoint calls map_dependencies and returns its response."""
    mock_response = DependenciesResponse(
        status="ok",
        message="ok",
        paragraph_name="CALC-NET-PAY",
        calls=["COMPUTE-DEDUCTIONS"],
        called_by=["PROCESS-EMPLOYEE"],
    )
    with patch(
        "app.api.v1.router.map_dependencies",
        new=AsyncMock(return_value=mock_response),
    ):
        response = await test_client.post(
            "/api/v1/dependencies",
            json={
                "file_path": _VALID_PATH,
                "paragraph_name": "CALC-NET-PAY",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "COMPUTE-DEDUCTIONS" in data["calls"]


@pytest.mark.asyncio
async def test_dependencies_stub_missing_field_rejected(
    test_client: AsyncClient,
) -> None:
    """Dependencies endpoint rejects request missing paragraph_name."""
    response = await test_client.post(
        "/api/v1/dependencies",
        json={"file_path": "samples/payroll.cob"},
    )
    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Business Logic endpoint
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_business_logic_endpoint_valid_input(test_client: AsyncClient) -> None:
    """Business logic endpoint calls extract_business_logic and returns its response."""
    mock_response = BusinessLogicResponse(
        status="ok",
        message="ok",
        file_path=_VALID_PATH,
        rules=["Tax is withheld at 15%."],
    )
    with patch(
        "app.api.v1.router.extract_business_logic",
        new=AsyncMock(return_value=mock_response),
    ):
        response = await test_client.post(
            "/api/v1/business-logic",
            json={"file_path": _VALID_PATH},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert len(data["rules"]) == 1


@pytest.mark.asyncio
async def test_business_logic_stub_missing_file_rejected(
    test_client: AsyncClient,
) -> None:
    """Business logic endpoint rejects empty request body."""
    response = await test_client.post("/api/v1/business-logic", json={})
    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Impact endpoint
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_impact_endpoint_valid_input(test_client: AsyncClient) -> None:
    """Impact endpoint calls analyze_impact and returns its response."""
    mock_response = ImpactResponse(
        status="ok",
        message="ok",
        paragraph_name="CALC-OVERTIME",
        affected_paragraphs=["MAIN-PROCEDURE"],
    )
    with patch(
        "app.api.v1.router.analyze_impact",
        new=AsyncMock(return_value=mock_response),
    ):
        response = await test_client.post(
            "/api/v1/impact",
            json={
                "file_path": _VALID_PATH,
                "paragraph_name": "CALC-OVERTIME",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["paragraph_name"] == "CALC-OVERTIME"
    assert "MAIN-PROCEDURE" in data["affected_paragraphs"]


@pytest.mark.asyncio
async def test_impact_stub_missing_fields_rejected(test_client: AsyncClient) -> None:
    """Impact endpoint rejects request with missing fields."""
    response = await test_client.post(
        "/api/v1/impact",
        json={"file_path": "samples/payroll.cob"},  # missing paragraph_name
    )
    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Auth enforcement tests
# These use a raw client WITHOUT the auth override to verify 401 behavior
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_without_token_returns_401() -> None:
    """Protected /query endpoint returns 401 when no Bearer token is provided."""
    import os
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")
    os.environ.setdefault("PINECONE_API_KEY", "pctest-fake")
    os.environ.setdefault("GITHUB_CLIENT_ID", "test-id")
    os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-secret")
    os.environ.setdefault("NEXTAUTH_SECRET", "test-nextauth-secret-32chars-long!!")

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/query",
            json={"query": "test query"},
            # No Authorization header
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_endpoint_does_not_require_auth() -> None:
    """The /health endpoint is public — no auth token needed."""
    import os
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")
    os.environ.setdefault("PINECONE_API_KEY", "pctest-fake")
    os.environ.setdefault("GITHUB_CLIENT_ID", "test-id")
    os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-secret")
    os.environ.setdefault("NEXTAUTH_SECRET", "test-nextauth-secret-32chars-long!!")

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_query_with_valid_bearer_token_succeeds() -> None:
    """
    A valid HS256 JWT signed with NEXTAUTH_SECRET is accepted by get_current_user.

    This exercises the get_current_user dependency body (lines that were
    previously uncovered because test_client overrides the dependency).
    The token is created with the same secret the backend uses to verify.
    """
    import os
    import time as time_module

    from jose import jwt as jose_jwt

    secret = "test-nextauth-secret-32chars-long!!"
    os.environ["NEXTAUTH_SECRET"] = secret
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")
    os.environ.setdefault("PINECONE_API_KEY", "pctest-fake")
    os.environ.setdefault("GITHUB_CLIENT_ID", "test-id")
    os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-secret")

    # Create a valid JWT signed with the same secret the backend uses
    token = jose_jwt.encode(
        {"sub": "github-99999", "exp": int(time_module.time()) + 3600},
        secret,
        algorithm="HS256",
    )

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/query",
            json={"query": "test query"},
            headers={"Authorization": f"Bearer {token}"},
        )

    # Stub endpoint returns 200 for authenticated requests
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_docs_disabled_in_production() -> None:
    """
    /docs returns 404 when ENVIRONMENT=production.

    Interactive API docs expose the full endpoint schema, which is useful
    in development but reduces the attack surface in production.
    """
    import os
    os.environ["ENVIRONMENT"] = "production"
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")
    os.environ.setdefault("PINECONE_API_KEY", "pctest-fake")
    os.environ.setdefault("GITHUB_CLIENT_ID", "test-id")
    os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-secret")
    os.environ.setdefault("NEXTAUTH_SECRET", "test-nextauth-secret-32chars-long!!")

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    try:
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            docs_response = await client.get("/docs")
            redoc_response = await client.get("/redoc")

        assert docs_response.status_code == 404
        assert redoc_response.status_code == 404
    finally:
        # Restore to development so other tests aren't affected
        os.environ.pop("ENVIRONMENT", None)
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_docs_enabled_in_development() -> None:
    """
    /docs returns 200 when ENVIRONMENT=development (the default).

    Developers need interactive API docs during local development and CI.
    """
    import os
    os.environ.pop("ENVIRONMENT", None)  # Ensure default (development)
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")
    os.environ.setdefault("PINECONE_API_KEY", "pctest-fake")
    os.environ.setdefault("GITHUB_CLIENT_ID", "test-id")
    os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-secret")
    os.environ.setdefault("NEXTAUTH_SECRET", "test-nextauth-secret-32chars-long!!")

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/docs")

    assert response.status_code == 200
