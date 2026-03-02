"""
Unit tests for the Pinecone client wrapper.

The PineconeWrapper provides two operations:
1. upsert_batch() — stores code chunks (with their embeddings) into Pinecone
2. query() — finds the most similar chunks to a query embedding

All tests use the mock_pinecone_client fixture from conftest.py.
No real Pinecone API calls are made — no API key needed, no money spent.

Think of these tests as verifying the "plumbing" that connects our
application logic to the Pinecone vector database.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.retrieval.pinecone_client import ChunkVector, PineconeWrapper, SearchResult


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def wrapper(mock_pinecone_client: MagicMock) -> PineconeWrapper:
    """A PineconeWrapper backed by the mock Pinecone client from conftest."""
    return PineconeWrapper(client=mock_pinecone_client, index_name="legacylens-test")


@pytest.fixture
def wrapper_empty(mock_pinecone_empty: MagicMock) -> PineconeWrapper:
    """A PineconeWrapper whose query always returns zero results."""
    return PineconeWrapper(client=mock_pinecone_empty, index_name="legacylens-test")


@pytest.fixture
def sample_embedding() -> list[float]:
    """A 1536-dimension embedding vector (all 0.1 — same as mock returns)."""
    return [0.1] * 1536


@pytest.fixture
def sample_vectors() -> list[ChunkVector]:
    """Three pre-built ChunkVector objects for upsert tests."""
    return [
        ChunkVector(
            id="loan-calc.cob::CALCULATE-INTEREST",
            embedding=[0.1] * 1536,
            metadata={
                "file_path": "programs/loan-calc.cob",
                "paragraph_name": "CALCULATE-INTEREST",
                "start_line": 14,
                "end_line": 22,
                "content": "CALCULATE-INTEREST.",
            },
        ),
        ChunkVector(
            id="payroll.cob::COMPUTE-TAX",
            embedding=[0.2] * 1536,
            metadata={
                "file_path": "programs/payroll.cob",
                "paragraph_name": "COMPUTE-TAX",
                "start_line": 45,
                "end_line": 58,
                "content": "COMPUTE-TAX.",
            },
        ),
        ChunkVector(
            id="payroll.cob::CALC-GROSS",
            embedding=[0.3] * 1536,
            metadata={
                "file_path": "programs/payroll.cob",
                "paragraph_name": "CALC-GROSS",
                "start_line": 30,
                "end_line": 44,
                "content": "CALC-GROSS.",
            },
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# ChunkVector dataclass tests
# ─────────────────────────────────────────────────────────────────────────────


def test_chunk_vector_fields() -> None:
    """ChunkVector has id, embedding, and metadata fields."""
    cv = ChunkVector(
        id="test.cob::PARA",
        embedding=[0.1] * 1536,
        metadata={"file_path": "test.cob"},
    )
    assert cv.id == "test.cob::PARA"
    assert len(cv.embedding) == 1536
    assert cv.metadata["file_path"] == "test.cob"


# ─────────────────────────────────────────────────────────────────────────────
# SearchResult dataclass tests
# ─────────────────────────────────────────────────────────────────────────────


def test_search_result_fields() -> None:
    """SearchResult has chunk_id, score, and metadata fields."""
    sr = SearchResult(
        chunk_id="loan-calc.cob::CALCULATE-INTEREST",
        score=0.92,
        metadata={"file_path": "programs/loan-calc.cob"},
    )
    assert sr.chunk_id == "loan-calc.cob::CALCULATE-INTEREST"
    assert sr.score == 0.92


# ─────────────────────────────────────────────────────────────────────────────
# PineconeWrapper initialization
# ─────────────────────────────────────────────────────────────────────────────


def test_wrapper_init(mock_pinecone_client: MagicMock) -> None:
    """PineconeWrapper initializes without error and connects to the index."""
    wrapper = PineconeWrapper(client=mock_pinecone_client, index_name="legacylens-test")
    # Should have called client.Index("legacylens-test") to get the index handle
    mock_pinecone_client.Index.assert_called_once_with("legacylens-test")
    assert wrapper is not None


# ─────────────────────────────────────────────────────────────────────────────
# upsert_batch() tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_batch_happy_path(
    wrapper: PineconeWrapper,
    sample_vectors: list[ChunkVector],
) -> None:
    """upsert_batch with 3 vectors returns the count upserted."""
    count = await wrapper.upsert_batch(sample_vectors)
    assert count == 3


@pytest.mark.asyncio
async def test_upsert_batch_empty_list(wrapper: PineconeWrapper) -> None:
    """upsert_batch with empty list returns 0 without error."""
    count = await wrapper.upsert_batch([])
    assert count == 0


@pytest.mark.asyncio
async def test_upsert_batch_single_vector(
    wrapper: PineconeWrapper,
    sample_vectors: list[ChunkVector],
) -> None:
    """upsert_batch with one vector upserts exactly one item."""
    count = await wrapper.upsert_batch([sample_vectors[0]])
    assert count == 1


@pytest.mark.asyncio
async def test_upsert_batch_respects_batch_size(
    mock_pinecone_client: MagicMock,
) -> None:
    """
    upsert_batch splits large input into batches of the specified size.

    If we have 250 vectors and batch_size=100, we expect 3 upsert calls:
    - Call 1: vectors 0–99 (100 items)
    - Call 2: vectors 100–199 (100 items)
    - Call 3: vectors 200–249 (50 items)
    """
    wrapper = PineconeWrapper(client=mock_pinecone_client, index_name="test")
    vectors = [
        ChunkVector(id=f"id-{i}", embedding=[0.1] * 1536, metadata={})
        for i in range(250)
    ]

    # Track how many times the underlying index.upsert was called
    index_mock = mock_pinecone_client.Index.return_value
    index_mock.upsert = MagicMock()

    count = await wrapper.upsert_batch(vectors, batch_size=100)

    assert count == 250
    assert index_mock.upsert.call_count == 3  # 3 batches


@pytest.mark.asyncio
async def test_upsert_batch_exactly_batch_size(
    mock_pinecone_client: MagicMock,
) -> None:
    """Exactly batch_size vectors results in exactly 1 upsert call."""
    wrapper = PineconeWrapper(client=mock_pinecone_client, index_name="test")
    vectors = [
        ChunkVector(id=f"id-{i}", embedding=[0.1] * 1536, metadata={})
        for i in range(100)
    ]
    index_mock = mock_pinecone_client.Index.return_value
    index_mock.upsert = MagicMock()

    count = await wrapper.upsert_batch(vectors, batch_size=100)

    assert count == 100
    assert index_mock.upsert.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# query() tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_returns_results(
    wrapper: PineconeWrapper,
    sample_embedding: list[float],
) -> None:
    """query() returns SearchResult objects when matches exist."""
    results = await wrapper.query(
        embedding=sample_embedding,
        top_k=5,
        min_score=0.70,
    )
    assert len(results) == 2
    assert isinstance(results[0], SearchResult)


@pytest.mark.asyncio
async def test_query_results_have_correct_fields(
    wrapper: PineconeWrapper,
    sample_embedding: list[float],
) -> None:
    """SearchResult objects returned by query() have chunk_id, score, metadata."""
    results = await wrapper.query(embedding=sample_embedding, top_k=5, min_score=0.70)

    first = results[0]
    assert first.chunk_id == "loan-calc.cob::CALCULATE-INTEREST"
    assert first.score == 0.92
    assert "file_path" in first.metadata


@pytest.mark.asyncio
async def test_query_filters_below_min_score(
    wrapper: PineconeWrapper,
    sample_embedding: list[float],
) -> None:
    """
    query() filters out results below the min_score threshold.

    The mock returns scores 0.92 and 0.81. With min_score=0.85,
    only the first result (0.92) should be returned.
    """
    results = await wrapper.query(
        embedding=sample_embedding,
        top_k=5,
        min_score=0.85,
    )
    assert len(results) == 1
    assert results[0].score == 0.92


@pytest.mark.asyncio
async def test_query_empty_results(
    wrapper_empty: PineconeWrapper,
    sample_embedding: list[float],
) -> None:
    """query() returns empty list when no matches exist — no error raised."""
    results = await wrapper_empty.query(
        embedding=sample_embedding,
        top_k=5,
        min_score=0.75,
    )
    assert results == []


@pytest.mark.asyncio
async def test_query_all_below_threshold_returns_empty(
    wrapper: PineconeWrapper,
    sample_embedding: list[float],
) -> None:
    """When all results are below min_score, empty list is returned."""
    results = await wrapper.query(
        embedding=sample_embedding,
        top_k=5,
        min_score=0.99,  # Both mock scores (0.92, 0.81) are below this
    )
    assert results == []


@pytest.mark.asyncio
async def test_query_passes_top_k_to_pinecone(
    mock_pinecone_client: MagicMock,
    sample_embedding: list[float],
) -> None:
    """query() passes the top_k parameter to Pinecone's query call."""
    index_mock = mock_pinecone_client.Index.return_value

    # Override the mock query to capture arguments
    captured_args: dict[str, object] = {}

    def capture_query(vector: list[float], top_k: int = 10, **kwargs: object) -> MagicMock:
        captured_args["top_k"] = top_k
        response = MagicMock()
        response.matches = []
        return response

    index_mock.query = capture_query

    wrapper = PineconeWrapper(client=mock_pinecone_client, index_name="test")
    await wrapper.query(embedding=sample_embedding, top_k=7, min_score=0.75)

    assert captured_args["top_k"] == 7


@pytest.mark.asyncio
async def test_query_results_sorted_by_score_descending(
    wrapper: PineconeWrapper,
    sample_embedding: list[float],
) -> None:
    """
    Results are ordered by score descending (highest similarity first).

    The mock returns scores [0.92, 0.81]. The wrapper should preserve this
    ordering so callers always get the most relevant result first.
    """
    results = await wrapper.query(
        embedding=sample_embedding,
        top_k=5,
        min_score=0.70,
    )
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_query_large_top_k(
    wrapper: PineconeWrapper,
    sample_embedding: list[float],
) -> None:
    """query() handles top_k=20 (the maximum allowed value) without error."""
    results = await wrapper.query(
        embedding=sample_embedding,
        top_k=20,
        min_score=0.70,
    )
    # Mock only has 2 results regardless of top_k
    assert len(results) <= 20


@pytest.mark.asyncio
async def test_query_min_score_boundary(
    wrapper: PineconeWrapper,
    sample_embedding: list[float],
) -> None:
    """A result with score exactly equal to min_score should be included."""
    # The mock returns scores 0.92 and 0.81
    # Setting min_score=0.81 should include both results
    results = await wrapper.query(
        embedding=sample_embedding,
        top_k=5,
        min_score=0.81,
    )
    assert len(results) == 2
