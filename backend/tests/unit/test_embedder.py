"""
Unit tests for the embedder module.

The embedder is the bridge between raw COBOL chunks and the Pinecone vector store.
It converts text into numbers (embeddings) using OpenAI, then stores those numbers
in Pinecone so we can later find similar chunks by meaning.

Think of embeddings like GPS coordinates for words -- two pieces of text that mean
similar things get similar coordinates. The embedder computes those coordinates.

Test strategy:
- All OpenAI and Pinecone calls are mocked (no real API calls, no money spent)
- Edge cases: empty input, single chunk, large batches, fallback chunks
- Error paths: OpenAI failure propagates; empty list skips the API entirely
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.ingestion.chunker import COBOLChunk
from app.core.ingestion.embedder import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    embed_and_upsert,
    embed_chunks,
    embed_query,
)
from app.core.retrieval.pinecone_client import PineconeWrapper

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures -- shared helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_chunk(
    file_path: str = "programs/loan-calc.cob",
    paragraph_name: str | None = "CALCULATE-INTEREST",
    start_line: int = 14,
    end_line: int = 22,
    content: str = "CALCULATE-INTEREST.\n    COMPUTE INTEREST = PRINCIPAL * RATE.",
    chunk_index: int = 0,
    is_fallback: bool = False,
) -> COBOLChunk:
    """
    Build a test COBOLChunk with sensible defaults.

    Keeps test bodies short by letting tests only override the field they care about.
    """
    return COBOLChunk(
        file_path=file_path,
        paragraph_name=paragraph_name,
        start_line=start_line,
        end_line=end_line,
        content=content,
        chunk_index=chunk_index,
        is_fallback=is_fallback,
    )


def make_mock_openai(n_per_call: int | None = None) -> AsyncMock:
    """
    Build a mock OpenAI client whose embeddings.create() returns N embeddings.

    If n_per_call is None, the mock automatically returns as many embeddings
    as there are texts in the `input` argument (realistic behaviour).
    If n_per_call is given, it always returns exactly that many embeddings.

    Each fake embedding is 1536 floats with value 0.1 (matches the conftest mock).
    """
    client = AsyncMock()

    async def create_embeddings(
        model: str,
        input: list[str],
        **kwargs: object,
    ) -> MagicMock:
        n = n_per_call if n_per_call is not None else len(input)
        response = MagicMock()
        response.data = [
            MagicMock(embedding=[0.1] * EMBEDDING_DIMENSIONS) for _ in range(n)
        ]
        return response

    client.embeddings.create = AsyncMock(side_effect=create_embeddings)
    return client


def make_mock_pinecone_wrapper(upsert_return: int = 0) -> AsyncMock:
    """
    Build a mock PineconeWrapper whose upsert_batch() returns a fixed count.

    The count is what embed_and_upsert() returns -- the number of vectors stored.
    """
    wrapper = AsyncMock(spec=PineconeWrapper)
    wrapper.upsert_batch = AsyncMock(return_value=upsert_return)
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# embed_chunks -- normal cases
# ─────────────────────────────────────────────────────────────────────────────


async def test_embed_chunks_happy_path() -> None:
    """Three chunks -> three ChunkVectors with correct structure."""
    chunks = [
        make_chunk(paragraph_name="CALC-INTEREST", chunk_index=0),
        make_chunk(paragraph_name="DISPLAY-RESULT", chunk_index=1),
        make_chunk(paragraph_name="VALIDATE-INPUT", chunk_index=2),
    ]
    openai_client = make_mock_openai()

    result = await embed_chunks(chunks, openai_client)

    assert len(result) == 3
    assert all(len(v.embedding) == EMBEDDING_DIMENSIONS for v in result)


async def test_embed_chunks_empty_list_returns_empty_without_api_call() -> None:
    """Empty input -> return [] and never call the OpenAI API."""
    openai_client = make_mock_openai()

    result = await embed_chunks([], openai_client)

    assert result == []
    openai_client.embeddings.create.assert_not_called()


async def test_embed_chunks_single_chunk() -> None:
    """One chunk in, one ChunkVector out."""
    chunks = [make_chunk(chunk_index=0)]
    openai_client = make_mock_openai()

    result = await embed_chunks(chunks, openai_client)

    assert len(result) == 1
    assert result[0].embedding == [0.1] * EMBEDDING_DIMENSIONS


async def test_embed_chunks_large_batch_splits_into_multiple_api_calls() -> None:
    """150 chunks with batch_size=100 must produce exactly 2 OpenAI API calls."""
    chunks = [make_chunk(chunk_index=i) for i in range(150)]
    openai_client = make_mock_openai()

    result = await embed_chunks(chunks, openai_client, batch_size=100)

    # 150 chunks / 100 per batch = 2 calls (100 + 50)
    assert openai_client.embeddings.create.call_count == 2
    assert len(result) == 150


async def test_embed_chunks_batch_boundary_exact_multiple() -> None:
    """4 chunks with batch_size=2 -> exactly 2 API calls (perfect split)."""
    chunks = [make_chunk(chunk_index=i) for i in range(4)]
    openai_client = make_mock_openai()

    result = await embed_chunks(chunks, openai_client, batch_size=2)

    assert openai_client.embeddings.create.call_count == 2
    assert len(result) == 4


async def test_embed_chunks_preserves_chunk_order() -> None:
    """Chunks must come back in the same order they went in."""
    chunks = [
        make_chunk(paragraph_name=f"PARA-{i}", chunk_index=i) for i in range(5)
    ]
    openai_client = make_mock_openai()

    result = await embed_chunks(chunks, openai_client)

    result_ids = [v.id for v in result]
    expected_prefix = "programs/loan-calc.cob::PARA-"
    assert result_ids == [f"{expected_prefix}{i}" for i in range(5)]


# ─────────────────────────────────────────────────────────────────────────────
# embed_chunks -- vector ID format
# ─────────────────────────────────────────────────────────────────────────────


async def test_embed_chunks_vector_id_named_paragraph() -> None:
    """Named paragraph -> ID is 'file_path::PARA-NAME'."""
    chunk = make_chunk(
        file_path="programs/payroll.cob",
        paragraph_name="COMPUTE-TAX",
        chunk_index=0,
    )
    openai_client = make_mock_openai()

    result = await embed_chunks([chunk], openai_client)

    assert result[0].id == "programs/payroll.cob::COMPUTE-TAX"


async def test_embed_chunks_vector_id_fallback_chunk() -> None:
    """Fallback chunk (no paragraph name) -> ID is 'file_path::chunk_N'."""
    chunk = make_chunk(
        file_path="programs/old-payroll.cob",
        paragraph_name=None,
        chunk_index=3,
        is_fallback=True,
    )
    openai_client = make_mock_openai()

    result = await embed_chunks([chunk], openai_client)

    assert result[0].id == "programs/old-payroll.cob::chunk_3"


# ─────────────────────────────────────────────────────────────────────────────
# embed_chunks -- metadata correctness
# ─────────────────────────────────────────────────────────────────────────────


async def test_embed_chunks_metadata_contains_all_required_fields() -> None:
    """Metadata stored in Pinecone must contain all fields needed for citation."""
    chunk = make_chunk(
        file_path="programs/loan-calc.cob",
        paragraph_name="CALCULATE-INTEREST",
        start_line=14,
        end_line=22,
        content="CALCULATE-INTEREST.\n    COMPUTE INTEREST = PRINCIPAL * RATE.",
        chunk_index=0,
        is_fallback=False,
    )
    openai_client = make_mock_openai()

    result = await embed_chunks([chunk], openai_client)

    meta = result[0].metadata
    assert meta["file_path"] == "programs/loan-calc.cob"
    assert meta["paragraph_name"] == "CALCULATE-INTEREST"
    assert meta["start_line"] == 14
    assert meta["end_line"] == 22
    assert meta["content"] == chunk.content
    assert meta["chunk_index"] == 0
    assert meta["is_fallback"] is False


async def test_embed_chunks_metadata_fallback_paragraph_name_empty_string() -> None:
    """Fallback chunks store paragraph_name as empty string (not None) in metadata."""
    chunk = make_chunk(paragraph_name=None, is_fallback=True)
    openai_client = make_mock_openai()

    result = await embed_chunks([chunk], openai_client)

    # Pinecone metadata values must be strings -- None is not valid
    assert result[0].metadata["paragraph_name"] == ""
    assert result[0].metadata["is_fallback"] is True


async def test_embed_chunks_embedding_values_match_openai_response() -> None:
    """Embedding in ChunkVector must be exactly what OpenAI returned."""
    chunk = make_chunk()
    openai_client = make_mock_openai()

    result = await embed_chunks([chunk], openai_client)

    assert result[0].embedding == [0.1] * EMBEDDING_DIMENSIONS


# ─────────────────────────────────────────────────────────────────────────────
# embed_chunks -- error propagation
# ─────────────────────────────────────────────────────────────────────────────


async def test_embed_chunks_openai_error_propagates_after_retries() -> None:
    """When OpenAI raises on every retry attempt, the error bubbles up."""
    chunk = make_chunk()
    client = AsyncMock()
    client.embeddings.create = AsyncMock(side_effect=RuntimeError("OpenAI rate limit"))

    # Mock asyncio.sleep so retry backoff doesn't slow down the test suite
    with patch("app.core.ingestion.embedder.asyncio.sleep"):
        with pytest.raises(RuntimeError, match="OpenAI rate limit"):
            await embed_chunks([chunk], client, batch_size=100)


async def test_embed_chunks_openai_error_on_second_batch_propagates() -> None:
    """Error that persists across all retries on batch 2 propagates correctly."""
    chunks = [make_chunk(chunk_index=i) for i in range(4)]
    client = AsyncMock()
    call_count = 0

    async def create_side_effect(
        model: str, input: list[str], **kwargs: object
    ) -> MagicMock:
        nonlocal call_count
        call_count += 1
        # First call (batch 1) succeeds; all subsequent calls (batch 2 +
        # its retries) fail. Using > 1 ensures every retry attempt also
        # fails so the error isn't swallowed by the retry logic.
        if call_count > 1:
            raise RuntimeError("batch 2 failed")
        response = MagicMock()
        response.data = [
            MagicMock(embedding=[0.1] * EMBEDDING_DIMENSIONS) for _ in input
        ]
        return response

    client.embeddings.create = AsyncMock(side_effect=create_side_effect)

    # Mock asyncio.sleep so retry backoff doesn't slow down the test suite
    with patch("app.core.ingestion.embedder.asyncio.sleep"):
        with pytest.raises(RuntimeError, match="batch 2 failed"):
            await embed_chunks(chunks, client, batch_size=2)


# ─────────────────────────────────────────────────────────────────────────────
# embed_query -- convert a user's question into an embedding
# ─────────────────────────────────────────────────────────────────────────────


async def test_embed_query_happy_path() -> None:
    """Query text -> list of 1536 floats."""
    openai_client = make_mock_openai()

    result = await embed_query("How does the interest calculation work?", openai_client)

    assert len(result) == EMBEDDING_DIMENSIONS
    assert isinstance(result[0], float)


async def test_embed_query_uses_correct_model() -> None:
    """embed_query must use text-embedding-3-small (our chosen model)."""
    openai_client = make_mock_openai()

    await embed_query("some query", openai_client)

    call_kwargs = openai_client.embeddings.create.call_args
    used_model = call_kwargs.kwargs.get("model") or (
        call_kwargs.args[0] if call_kwargs.args else None
    )
    assert used_model == EMBEDDING_MODEL


async def test_embed_query_raises_on_empty_string() -> None:
    """Empty query string must raise ValueError before calling OpenAI."""
    openai_client = make_mock_openai()

    with pytest.raises(ValueError, match="empty"):
        await embed_query("", openai_client)

    openai_client.embeddings.create.assert_not_called()


async def test_embed_query_raises_on_whitespace_only() -> None:
    """Whitespace-only query is effectively empty -- raise ValueError."""
    openai_client = make_mock_openai()

    with pytest.raises(ValueError, match="empty"):
        await embed_query("   \t\n  ", openai_client)

    openai_client.embeddings.create.assert_not_called()


async def test_embed_query_returns_first_embedding_from_response() -> None:
    """embed_query wraps the text in a list but returns data[0].embedding."""
    openai_client = make_mock_openai()

    result = await embed_query("test query", openai_client)

    # We sent a list of 1 item; we get back data[0] -- a flat list of floats
    assert result == [0.1] * EMBEDDING_DIMENSIONS


# ─────────────────────────────────────────────────────────────────────────────
# embed_and_upsert -- full pipeline (embed + store)
# ─────────────────────────────────────────────────────────────────────────────


async def test_embed_and_upsert_happy_path_returns_vector_count() -> None:
    """embed_and_upsert returns the number of vectors stored in Pinecone."""
    chunks = [make_chunk(chunk_index=i) for i in range(3)]
    openai_client = make_mock_openai()
    pinecone_wrapper = make_mock_pinecone_wrapper(upsert_return=3)

    count = await embed_and_upsert(chunks, openai_client, pinecone_wrapper)

    assert count == 3


async def test_embed_and_upsert_empty_list_returns_zero_without_api_calls() -> None:
    """Empty chunk list -> 0 returned, neither OpenAI nor Pinecone called."""
    openai_client = make_mock_openai()
    pinecone_wrapper = make_mock_pinecone_wrapper(upsert_return=0)

    count = await embed_and_upsert([], openai_client, pinecone_wrapper)

    assert count == 0
    openai_client.embeddings.create.assert_not_called()
    pinecone_wrapper.upsert_batch.assert_not_called()


async def test_embed_and_upsert_passes_all_vectors_to_pinecone() -> None:
    """embed_and_upsert calls upsert_batch with a vector for every chunk."""
    chunks = [
        make_chunk(paragraph_name=f"PARA-{i}", chunk_index=i) for i in range(5)
    ]
    openai_client = make_mock_openai()
    pinecone_wrapper = make_mock_pinecone_wrapper(upsert_return=5)

    await embed_and_upsert(chunks, openai_client, pinecone_wrapper)

    call_args = pinecone_wrapper.upsert_batch.call_args
    vectors_passed = call_args.args[0]
    assert len(vectors_passed) == 5


async def test_embed_and_upsert_single_chunk() -> None:
    """Single chunk flow works end-to-end."""
    chunks = [make_chunk()]
    openai_client = make_mock_openai()
    pinecone_wrapper = make_mock_pinecone_wrapper(upsert_return=1)

    count = await embed_and_upsert(chunks, openai_client, pinecone_wrapper)

    assert count == 1
    pinecone_wrapper.upsert_batch.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Module constants -- sanity checks
# ─────────────────────────────────────────────────────────────────────────────


def test_embedding_model_constant_is_correct_model_name() -> None:
    """The embedding model constant must match our architecture decision."""
    assert EMBEDDING_MODEL == "text-embedding-3-small"


def test_embedding_dimensions_constant_matches_model() -> None:
    """text-embedding-3-small outputs 1536-dimensional vectors."""
    assert EMBEDDING_DIMENSIONS == 1536
