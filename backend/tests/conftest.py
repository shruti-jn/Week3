"""
Shared test fixtures for the LegacyLens backend test suite.

Think of this file like a prep station in a kitchen:
it gets all the common ingredients ready so every test
doesn't have to start from scratch.

pytest automatically loads this file before running any test.
Fixtures defined here are available to all test files in the
tests/ directory without needing to import them.
"""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ─────────────────────────────────────────────────────────────────────────────
# COBOL sample fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_cobol_content() -> str:
    """
    A small, realistic COBOL program for use in parser and chunker tests.

    This is a minimal payroll-style COBOL program with two paragraphs:
    - CALCULATE-INTEREST: computes interest on a principal amount
    - DISPLAY-RESULT: shows the result to the user

    Real COBOL programs have these same structural patterns, just much larger.
    This fixture lets tests run without needing to read real files from disk.
    """
    return (
        "IDENTIFICATION DIVISION.\n"
        "PROGRAM-ID. SAMPLE-PAYROLL.\n"
        "AUTHOR. LEGACYLENS-TESTS.\n"
        "\n"
        "ENVIRONMENT DIVISION.\n"
        "\n"
        "DATA DIVISION.\n"
        "WORKING-STORAGE SECTION.\n"
        "  01 PRINCIPAL     PIC 9(9)V99 VALUE 0.\n"
        "  01 RATE          PIC 9(3)V99 VALUE 0.\n"
        "  01 INTEREST      PIC 9(9)V99 VALUE 0.\n"
        "\n"
        "PROCEDURE DIVISION.\n"
        "CALCULATE-INTEREST.\n"
        "    COMPUTE INTEREST = PRINCIPAL * RATE / 100.\n"
        "    IF INTEREST > 0\n"
        "        PERFORM DISPLAY-RESULT\n"
        "    END-IF.\n"
        "    STOP RUN.\n"
        "\n"
        "DISPLAY-RESULT.\n"
        "    DISPLAY 'Interest: ' INTEREST.\n"
        "    STOP RUN.\n"
    )


@pytest.fixture
def sample_cobol_no_paragraphs() -> str:
    """
    A COBOL file with no identifiable paragraph labels.

    Used to test the fallback chunker that handles files without clear structure.
    This represents poorly-structured or very old COBOL code.
    """
    # 450 lines of MOVE statements — no paragraph labels anywhere
    lines = ["    MOVE ZERO TO WS-COUNTER."] * 450
    return "\n".join(lines)


@pytest.fixture
def sample_cobol_windows_line_endings() -> str:
    """
    A COBOL file with Windows-style line endings (\\r\\n instead of \\n).

    Windows uses \\r\\n for line endings; Unix/Mac use \\n.
    Our parser must handle both — this fixture tests that.
    """
    return (
        "PROCEDURE DIVISION.\r\n"
        "CALCULATE-INTEREST.\r\n"
        "    COMPUTE INTEREST = PRINCIPAL * RATE / 100.\r\n"
        "    STOP RUN.\r\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI Mock
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_openai_client() -> AsyncMock:
    """
    A fake OpenAI client that returns realistic-looking data without
    actually making any network calls or spending any money.

    This mock simulates two OpenAI capabilities:
    1. Embeddings: converts text into a list of 1536 numbers
    2. Chat completions: generates an answer to a question

    Without this mock, unit tests would:
    - Require a real OpenAI API key
    - Spend money on every test run
    - Be slow (network latency)
    - Be flaky (network failures, rate limits)

    Usage in tests:
        def test_something(mock_openai_client):
            result = await embed_query("find interest calculation", mock_openai_client)
            assert len(result) == 1536
    """
    client = AsyncMock()

    # Mock the embeddings endpoint
    # Normally returns: response.data[0].embedding = [0.12, -0.34, ...]
    # We return a list of 1536 zeros to simulate a real embedding vector
    mock_embedding_response = MagicMock()
    mock_embedding_response.data = [MagicMock(embedding=[0.1] * 1536)]
    client.embeddings.create = AsyncMock(return_value=mock_embedding_response)

    # Mock the chat completions endpoint (streaming)
    # Simulates GPT-4o-mini returning "This is a mocked answer." word by word
    async def mock_stream() -> AsyncGenerator[MagicMock, None]:
        words = ["This", " is", " a", " mocked", " answer", "."]
        for word in words:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = word
            yield chunk

    mock_stream_context = MagicMock()
    mock_stream_context.__aiter__ = mock_stream
    client.chat.completions.stream = MagicMock(return_value=mock_stream_context)

    return client


# ─────────────────────────────────────────────────────────────────────────────
# Pinecone Mock
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_pinecone_client() -> MagicMock:
    """
    A fake Pinecone client that returns realistic search results without
    connecting to the actual Pinecone vector database.

    Pinecone is our vector database — it stores the COBOL code embeddings
    and lets us find the most similar ones to a query.

    This mock returns two pre-canned search results:
    - CALCULATE-INTEREST paragraph from loan-calc.cob (score 0.92 — very relevant)
    - COMPUTE-TAX paragraph from payroll.cob (score 0.81 — also relevant)

    Usage in tests:
        def test_retrieval(mock_pinecone_client):
            results = await search_pinecone([0.1] * 1536, mock_pinecone_client)
            assert results[0].score == 0.92
    """
    client = MagicMock()
    index = MagicMock()

    # Simulate Pinecone index.query() returning two search results
    # Each result has: id, score (similarity), and metadata (our stored chunk info)
    def mock_query(vector: list[float], top_k: int = 10, **kwargs: object) -> MagicMock:
        response = MagicMock()
        response.matches = [
            MagicMock(
                id="loan-calc.cob::CALCULATE-INTEREST",
                score=0.92,
                metadata={
                    "file_path": "programs/loan-calc.cob",
                    "paragraph_name": "CALCULATE-INTEREST",
                    "start_line": 14,
                    "end_line": 22,
                    "content": "CALCULATE-INTEREST.\n    COMPUTE INTEREST = PRINCIPAL * RATE / 100.",
                    "division": "PROCEDURE",
                },
            ),
            MagicMock(
                id="payroll.cob::COMPUTE-TAX",
                score=0.81,
                metadata={
                    "file_path": "programs/payroll.cob",
                    "paragraph_name": "COMPUTE-TAX",
                    "start_line": 45,
                    "end_line": 58,
                    "content": "COMPUTE-TAX.\n    MULTIPLY GROSS-PAY BY TAX-RATE GIVING TAX-AMOUNT.",
                    "division": "PROCEDURE",
                },
            ),
        ]
        return response

    index.query = mock_query
    client.Index = MagicMock(return_value=index)

    return client


@pytest.fixture
def mock_pinecone_empty() -> MagicMock:
    """
    A Pinecone mock that returns zero results.

    Used to test the "no results found" path — when the AI can't find
    any code relevant enough to answer the question.
    The retrieval pipeline should return a graceful fallback, not crash.
    """
    client = MagicMock()
    index = MagicMock()

    def mock_empty_query(vector: list[float], top_k: int = 10, **kwargs: object) -> MagicMock:
        response = MagicMock()
        response.matches = []  # No results
        return response

    index.query = mock_empty_query
    client.Index = MagicMock(return_value=index)
    return client


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI Test Client
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
async def test_client(
    mock_openai_client: AsyncMock,
    mock_pinecone_client: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """
    An HTTP test client that can call our FastAPI endpoints in tests.

    This is like a fake browser that sends HTTP requests to our API
    without starting a real server. It's much faster than running
    a real server and doesn't require a network connection.

    The mock_openai_client and mock_pinecone_client fixtures are
    automatically injected so the API uses fake services, not real ones.

    Usage in tests:
        async def test_query_endpoint(test_client):
            response = await test_client.post("/api/v1/query", json={"query": "..."})
            assert response.status_code == 200
    """
    # We import here (not at top level) to avoid circular imports during testing
    from app.dependencies import get_openai_client, get_pinecone_client
    from app.main import create_app

    app = create_app()

    # Override the real dependency functions with our mocks
    # This is FastAPI's built-in "dependency override" feature
    app.dependency_overrides[get_openai_client] = lambda: mock_openai_client
    app.dependency_overrides[get_pinecone_client] = lambda: mock_pinecone_client

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    # Clean up overrides after the test
    app.dependency_overrides.clear()
