"""
Unit tests for the API v1 router scaffold endpoints.

These tests verify that:
- Each stub endpoint accepts correctly shaped input
- Each stub endpoint returns correctly shaped output
- Invalid input is rejected with 422 (validation error), not 500
- Protected endpoints return 401 when no auth token is provided
- The /health endpoint responds correctly

We use the `test_client` fixture from conftest.py which already wires up
the FastAPI app with mocked OpenAI, Pinecone, and auth dependencies.

No real API calls are made — all external services are mocked.
"""

import pytest
from httpx import ASGITransport, AsyncClient

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
    """Query endpoint with valid input returns stub status."""
    response = await test_client.post(
        "/api/v1/query",
        json={"query": "How does payroll calculation work?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stub"


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
async def test_explain_stub_valid_input(test_client: AsyncClient) -> None:
    """Explain endpoint with valid input returns stub with paragraph name echoed."""
    response = await test_client.post(
        "/api/v1/explain",
        json={
            "file_path": "samples/payroll.cob",
            "paragraph_name": "CALC-GROSS-PAY",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stub"
    assert data["paragraph_name"] == "CALC-GROSS-PAY"


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
async def test_dependencies_stub_valid_input(test_client: AsyncClient) -> None:
    """Dependencies endpoint with valid input returns stub response."""
    response = await test_client.post(
        "/api/v1/dependencies",
        json={
            "file_path": "samples/payroll.cob",
            "paragraph_name": "CALC-NET-PAY",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stub"
    assert data["calls"] == []
    assert data["called_by"] == []


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
async def test_business_logic_stub_valid_input(test_client: AsyncClient) -> None:
    """Business logic endpoint returns stub with file_path echoed."""
    response = await test_client.post(
        "/api/v1/business-logic",
        json={"file_path": "samples/loans.cob"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stub"
    assert data["file_path"] == "samples/loans.cob"
    assert data["rules"] == []


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
async def test_impact_stub_valid_input(test_client: AsyncClient) -> None:
    """Impact endpoint returns stub with paragraph_name echoed."""
    response = await test_client.post(
        "/api/v1/impact",
        json={
            "file_path": "samples/payroll.cob",
            "paragraph_name": "CALC-OVERTIME",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stub"
    assert data["paragraph_name"] == "CALC-OVERTIME"
    assert data["affected_paragraphs"] == []


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
