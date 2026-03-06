"""
Unit tests for the embedder module.

The embedder is the bridge between raw COBOL chunks and the Pinecone vector store.
It converts text into numbers (embeddings) using Voyage AI, then stores those numbers
in Pinecone so we can later find similar chunks by meaning.

Think of embeddings like GPS coordinates for words -- two pieces of text that mean
similar things get similar coordinates. The embedder computes those coordinates.

Test strategy:
- All Voyage and Pinecone calls are mocked (no real API calls, no money spent)
- Edge cases: empty input, single chunk, large batches, fallback chunks
- Error paths: Voyage failure propagates; empty list skips the API entirely
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.ingestion.chunker import COBOLChunk
from app.core.ingestion.embedder import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    _extract_first_comment,
    build_embedding_text,
    embed_and_upsert,
    embed_chunks,
    embed_query,
)
from app.core.retrieval.pinecone_client import PineconeWrapper

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures -- shared helpers
# ─────────────────────────────────────────────────────────────────────────────

# Minimal COBOL paragraph content that passes the chunk quality filter.
# Needs ≥4 non-trivial body lines and at least one logic verb.
_INDEXABLE_CONTENT = (
    "CALCULATE-INTEREST.\n"
    "    MOVE WS-PRINCIPAL TO WS-TEMP.\n"
    "    COMPUTE WS-INTEREST = WS-TEMP * WS-RATE.\n"
    "    IF WS-INTEREST > 0\n"
    "        MOVE WS-INTEREST TO WS-RESULT\n"
    "    END-IF."
)


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


def make_mock_voyage(n_per_call: int | None = None) -> MagicMock:
    """
    Build a mock Voyage AI client whose embed() returns N embeddings.

    Voyage's client is synchronous (voyageai.Client). The embedder wraps it
    in asyncio.to_thread() so the async event loop stays unblocked.

    If n_per_call is None, the mock automatically returns as many embeddings
    as there are texts in the first argument (realistic behaviour).
    If n_per_call is given, it always returns exactly that many embeddings.

    Each fake embedding is EMBEDDING_DIMENSIONS floats with value 0.1.

    Returns:
        A synchronous MagicMock that simulates voyageai.Client.
    """
    client = MagicMock()

    def embed_side_effect(
        texts: list[str],
        model: str,
        input_type: str = "document",
    ) -> MagicMock:
        n = n_per_call if n_per_call is not None else len(texts)
        response = MagicMock()
        response.embeddings = [[0.1] * EMBEDDING_DIMENSIONS for _ in range(n)]
        return response

    client.embed = MagicMock(side_effect=embed_side_effect)
    return client


def make_mock_pinecone_wrapper(upsert_return: int = 0) -> MagicMock:
    """
    Build a mock PineconeWrapper whose upsert_batch() returns a fixed count.

    The count is what embed_and_upsert() returns -- the number of vectors stored.
    """
    from unittest.mock import AsyncMock

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
    voyage_client = make_mock_voyage()

    result = await embed_chunks(chunks, voyage_client)

    assert len(result) == 3
    assert all(len(v.embedding) == EMBEDDING_DIMENSIONS for v in result)


async def test_embed_chunks_empty_list_returns_empty_without_api_call() -> None:
    """Empty input -> return [] and never call the Voyage API."""
    voyage_client = make_mock_voyage()

    result = await embed_chunks([], voyage_client)

    assert result == []
    voyage_client.embed.assert_not_called()


async def test_embed_chunks_single_chunk() -> None:
    """One chunk in, one ChunkVector out."""
    chunks = [make_chunk(chunk_index=0)]
    voyage_client = make_mock_voyage()

    result = await embed_chunks(chunks, voyage_client)

    assert len(result) == 1
    assert result[0].embedding == [0.1] * EMBEDDING_DIMENSIONS


async def test_embed_chunks_large_batch_splits_into_multiple_api_calls() -> None:
    """150 chunks with batch_size=100 must produce exactly 2 Voyage API calls."""
    chunks = [make_chunk(chunk_index=i) for i in range(150)]
    voyage_client = make_mock_voyage()

    result = await embed_chunks(chunks, voyage_client, batch_size=100)

    # 150 chunks / 100 per batch = 2 calls (100 + 50)
    assert voyage_client.embed.call_count == 2
    assert len(result) == 150


async def test_embed_chunks_batch_boundary_exact_multiple() -> None:
    """4 chunks with batch_size=2 -> exactly 2 API calls (perfect split)."""
    chunks = [make_chunk(chunk_index=i) for i in range(4)]
    voyage_client = make_mock_voyage()

    result = await embed_chunks(chunks, voyage_client, batch_size=2)

    assert voyage_client.embed.call_count == 2
    assert len(result) == 4


async def test_embed_chunks_preserves_chunk_order() -> None:
    """Chunks must come back in the same order they went in."""
    chunks = [
        make_chunk(paragraph_name=f"PARA-{i}", chunk_index=i) for i in range(5)
    ]
    voyage_client = make_mock_voyage()

    result = await embed_chunks(chunks, voyage_client)

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
    voyage_client = make_mock_voyage()

    result = await embed_chunks([chunk], voyage_client)

    assert result[0].id == "programs/payroll.cob::COMPUTE-TAX"


async def test_embed_chunks_vector_id_fallback_chunk() -> None:
    """Fallback chunk (no paragraph name) -> ID is 'file_path::chunk_N'."""
    chunk = make_chunk(
        file_path="programs/old-payroll.cob",
        paragraph_name=None,
        chunk_index=3,
        is_fallback=True,
    )
    voyage_client = make_mock_voyage()

    result = await embed_chunks([chunk], voyage_client)

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
    voyage_client = make_mock_voyage()

    result = await embed_chunks([chunk], voyage_client)

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
    voyage_client = make_mock_voyage()

    result = await embed_chunks([chunk], voyage_client)

    # Pinecone metadata values must be strings -- None is not valid
    assert result[0].metadata["paragraph_name"] == ""
    assert result[0].metadata["is_fallback"] is True


async def test_embed_chunks_embedding_values_match_voyage_response() -> None:
    """Embedding in ChunkVector must be exactly what Voyage returned."""
    chunk = make_chunk()
    voyage_client = make_mock_voyage()

    result = await embed_chunks([chunk], voyage_client)

    assert result[0].embedding == [0.1] * EMBEDDING_DIMENSIONS


# ─────────────────────────────────────────────────────────────────────────────
# embed_chunks -- error propagation
# ─────────────────────────────────────────────────────────────────────────────


async def test_embed_chunks_voyage_error_propagates_after_retries() -> None:
    """When Voyage raises on every retry attempt, the error bubbles up."""
    chunk = make_chunk()
    client = MagicMock()
    client.embed = MagicMock(side_effect=RuntimeError("Voyage rate limit"))

    # Mock asyncio.sleep so retry backoff doesn't slow down the test suite
    with patch("app.core.ingestion.embedder.asyncio.sleep"):
        with pytest.raises(RuntimeError, match="Voyage rate limit"):
            await embed_chunks([chunk], client, batch_size=100)


async def test_embed_chunks_voyage_error_on_second_batch_propagates() -> None:
    """Error that persists across all retries on batch 2 propagates correctly."""
    chunks = [make_chunk(chunk_index=i) for i in range(4)]
    client = MagicMock()
    call_count = 0

    def embed_side_effect(
        texts: list[str], model: str, input_type: str = "document"
    ) -> MagicMock:
        nonlocal call_count
        call_count += 1
        # First call (batch 1) succeeds; all subsequent calls (batch 2 +
        # its retries) fail. Using > 1 ensures every retry attempt also
        # fails so the error isn't swallowed by the retry logic.
        if call_count > 1:
            raise RuntimeError("batch 2 failed")
        response = MagicMock()
        response.embeddings = [[0.1] * EMBEDDING_DIMENSIONS for _ in texts]
        return response

    client.embed = MagicMock(side_effect=embed_side_effect)

    # Mock asyncio.sleep so retry backoff doesn't slow down the test suite
    with patch("app.core.ingestion.embedder.asyncio.sleep"):
        with pytest.raises(RuntimeError, match="batch 2 failed"):
            await embed_chunks(chunks, client, batch_size=2)


# ─────────────────────────────────────────────────────────────────────────────
# embed_query -- convert a user's question into an embedding
# ─────────────────────────────────────────────────────────────────────────────


async def test_embed_query_happy_path() -> None:
    """Query text -> list of 1024 floats (voyage-code-2 dimensions)."""
    voyage_client = make_mock_voyage()

    result = await embed_query("How does the interest calculation work?", voyage_client)

    assert len(result) == EMBEDDING_DIMENSIONS
    assert isinstance(result[0], float)


async def test_embed_query_uses_correct_model() -> None:
    """embed_query must use voyage-code-2 (our chosen model)."""
    voyage_client = make_mock_voyage()

    await embed_query("some query", voyage_client)

    call_kwargs = voyage_client.embed.call_args
    used_model = call_kwargs.kwargs.get("model") or (
        call_kwargs.args[1] if len(call_kwargs.args) > 1 else None
    )
    assert used_model == EMBEDDING_MODEL


async def test_embed_query_uses_query_input_type() -> None:
    """embed_query must pass input_type='query' for asymmetric retrieval."""
    voyage_client = make_mock_voyage()

    await embed_query("some query", voyage_client)

    call_kwargs = voyage_client.embed.call_args
    used_input_type = call_kwargs.kwargs.get("input_type")
    assert used_input_type == "query"


async def test_embed_query_raises_on_empty_string() -> None:
    """Empty query string must raise ValueError before calling Voyage."""
    voyage_client = make_mock_voyage()

    with pytest.raises(ValueError, match="empty"):
        await embed_query("", voyage_client)

    voyage_client.embed.assert_not_called()


async def test_embed_query_raises_on_whitespace_only() -> None:
    """Whitespace-only query is effectively empty -- raise ValueError."""
    voyage_client = make_mock_voyage()

    with pytest.raises(ValueError, match="empty"):
        await embed_query("   \t\n  ", voyage_client)

    voyage_client.embed.assert_not_called()


async def test_embed_query_returns_first_embedding_from_response() -> None:
    """embed_query wraps the text in a list but returns embeddings[0]."""
    voyage_client = make_mock_voyage()

    result = await embed_query("test query", voyage_client)

    # We sent a list of 1 item; we get back embeddings[0] -- a flat list of floats
    assert result == [0.1] * EMBEDDING_DIMENSIONS


# ─────────────────────────────────────────────────────────────────────────────
# embed_and_upsert -- full pipeline (embed + store)
# ─────────────────────────────────────────────────────────────────────────────


async def test_embed_and_upsert_happy_path_returns_vector_count() -> None:
    """embed_and_upsert returns the number of vectors stored in Pinecone."""
    chunks = [make_chunk(content=_INDEXABLE_CONTENT, chunk_index=i) for i in range(3)]
    voyage_client = make_mock_voyage()
    pinecone_wrapper = make_mock_pinecone_wrapper(upsert_return=3)

    count = await embed_and_upsert(chunks, voyage_client, pinecone_wrapper)

    assert count == 3


async def test_embed_and_upsert_empty_list_returns_zero_without_api_calls() -> None:
    """Empty chunk list -> 0 returned, neither Voyage nor Pinecone called."""
    voyage_client = make_mock_voyage()
    pinecone_wrapper = make_mock_pinecone_wrapper(upsert_return=0)

    count = await embed_and_upsert([], voyage_client, pinecone_wrapper)

    assert count == 0
    voyage_client.embed.assert_not_called()
    pinecone_wrapper.upsert_batch.assert_not_called()


async def test_embed_and_upsert_passes_all_vectors_to_pinecone() -> None:
    """embed_and_upsert calls upsert_batch with a vector for every chunk."""
    chunks = [
        make_chunk(content=_INDEXABLE_CONTENT, paragraph_name=f"PARA-{i}", chunk_index=i)
        for i in range(5)
    ]
    voyage_client = make_mock_voyage()
    pinecone_wrapper = make_mock_pinecone_wrapper(upsert_return=5)

    await embed_and_upsert(chunks, voyage_client, pinecone_wrapper)

    call_args = pinecone_wrapper.upsert_batch.call_args
    vectors_passed = call_args.args[0]
    assert len(vectors_passed) == 5


async def test_embed_and_upsert_single_chunk() -> None:
    """Single chunk flow works end-to-end."""
    chunks = [make_chunk(content=_INDEXABLE_CONTENT)]
    voyage_client = make_mock_voyage()
    pinecone_wrapper = make_mock_pinecone_wrapper(upsert_return=1)

    count = await embed_and_upsert(chunks, voyage_client, pinecone_wrapper)

    assert count == 1
    pinecone_wrapper.upsert_batch.assert_called_once()


async def test_embed_and_upsert_filters_stub_chunks() -> None:
    """Stub chunks are excluded by filter_chunks; only real chunks are embedded."""
    real_chunk = make_chunk(
        content=(
            "CALC-INTEREST.\n"
            "    MOVE WS-PRINCIPAL TO WS-TEMP.\n"
            "    COMPUTE WS-INTEREST = WS-TEMP * WS-RATE.\n"
            "    IF WS-INTEREST > 0\n"
            "        MOVE WS-INTEREST TO WS-RESULT\n"
            "    END-IF."
        ),
        paragraph_name="CALC-INTEREST",
        chunk_index=0,
    )
    stub_chunk = make_chunk(
        content="PARA-EX.\n    EXIT.",
        paragraph_name="PARA-EX",
        chunk_index=1,
    )
    voyage_client = make_mock_voyage()
    pinecone_wrapper = make_mock_pinecone_wrapper(upsert_return=1)

    count = await embed_and_upsert([real_chunk, stub_chunk], voyage_client, pinecone_wrapper)

    # Only 1 real chunk embedded; stub is filtered out
    assert count == 1
    call_args = pinecone_wrapper.upsert_batch.call_args
    vectors_passed = call_args.args[0]
    assert len(vectors_passed) == 1


async def test_embed_and_upsert_all_filtered_returns_zero() -> None:
    """When all chunks are stubs, filter_chunks removes them all — 0 returned, no API calls."""
    stub1 = make_chunk(content="PARA-EX.\n    EXIT.", paragraph_name="PARA-EX", chunk_index=0)
    stub2 = make_chunk(content="PARA2-EX.\n    EXIT.", paragraph_name="PARA2-EX", chunk_index=1)
    voyage_client = make_mock_voyage()
    pinecone_wrapper = make_mock_pinecone_wrapper(upsert_return=0)

    count = await embed_and_upsert([stub1, stub2], voyage_client, pinecone_wrapper)

    assert count == 0
    voyage_client.embed.assert_not_called()
    pinecone_wrapper.upsert_batch.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Module constants -- sanity checks
# ─────────────────────────────────────────────────────────────────────────────


def test_embedding_model_constant_is_correct_model_name() -> None:
    """The embedding model constant must match our architecture decision."""
    assert EMBEDDING_MODEL == "voyage-code-2"


def test_embedding_dimensions_constant_matches_model() -> None:
    """voyage-code-2 outputs 1536-dimensional vectors."""
    assert EMBEDDING_DIMENSIONS == 1536


# ─────────────────────────────────────────────────────────────────────────────
# build_embedding_text -- enriched text sent to Voyage for indexing
# ─────────────────────────────────────────────────────────────────────────────
# Why test this separately?
# This function controls what semantic meaning Voyage embeds.
# If it only embeds raw COBOL, natural-language queries like
# "how is interest calculated?" can't match "COMPUTE WS-INT = WS-PRIN * RATE".
# By prepending the file stem and readable paragraph name, we bridge the gap
# between English queries and COBOL identifiers.
# ─────────────────────────────────────────────────────────────────────────────


def test_build_embedding_text_named_paragraph_includes_file_stem() -> None:
    """Named paragraph -> output includes the file stem (not full path)."""
    chunk = make_chunk(
        file_path="programs/loan-calc.cob",
        paragraph_name="CALCULATE-INTEREST",
        content="    COMPUTE WS-INTEREST = WS-PRINCIPAL * RATE.",
    )
    text = build_embedding_text(chunk)
    assert "loan-calc" in text


def test_build_embedding_text_named_paragraph_includes_cobol_name() -> None:
    """Named paragraph -> output includes the COBOL paragraph name verbatim."""
    chunk = make_chunk(
        file_path="programs/loan-calc.cob",
        paragraph_name="CALCULATE-INTEREST",
        content="    COMPUTE WS-INTEREST = WS-PRINCIPAL * RATE.",
    )
    text = build_embedding_text(chunk)
    assert "CALCULATE-INTEREST" in text


def test_build_embedding_text_named_paragraph_includes_readable_form() -> None:
    """Named paragraph -> hyphens converted to spaces + lowercased for NLP matching.

    "CALCULATE-INTEREST" → "calculate interest" so that queries like
    "how is interest calculated?" semantically align with this chunk.
    """
    chunk = make_chunk(
        file_path="programs/loan-calc.cob",
        paragraph_name="CALCULATE-INTEREST",
        content="    COMPUTE WS-INTEREST = WS-PRINCIPAL * RATE.",
    )
    text = build_embedding_text(chunk)
    assert "calculate interest" in text


def test_build_embedding_text_named_paragraph_includes_code_content() -> None:
    """Output always contains the original COBOL code — never discards it."""
    chunk = make_chunk(
        file_path="programs/loan-calc.cob",
        paragraph_name="CALCULATE-INTEREST",
        content="    COMPUTE WS-INTEREST = WS-PRINCIPAL * RATE.",
    )
    text = build_embedding_text(chunk)
    assert "COMPUTE WS-INTEREST" in text


def test_build_embedding_text_fallback_chunk_no_paragraph() -> None:
    """Fallback chunk (paragraph_name=None) -> no paragraph line, code still included."""
    chunk = make_chunk(
        file_path="programs/old-payroll.cob",
        paragraph_name=None,
        content="    MOVE WS-GROSS TO WS-PAY.",
        is_fallback=True,
    )
    text = build_embedding_text(chunk)
    # File context still present
    assert "old-payroll" in text
    # No paragraph section (nothing to contribute)
    assert "Paragraph:" not in text
    # Code content still present
    assert "MOVE WS-GROSS" in text


def test_build_embedding_text_does_not_include_full_absolute_path() -> None:
    """Full absolute path is NOT embedded — only the short file stem is used.

    Embedding '/Users/shruti/Week3/data/...' adds noise, not signal.
    The short stem like 'GC53CALENDAR' is what's semantically useful.
    """
    chunk = make_chunk(
        file_path="/Users/shruti/Week3/data/gnucobol-contrib/tools/TUI-TOOLS/GC53CALENDAR.COB",
        paragraph_name="DISPLAY-CALENDAR",
        content="    DISPLAY WS-MONTH.",
    )
    text = build_embedding_text(chunk)
    assert "/Users/shruti" not in text
    assert "GC53CALENDAR" in text


def test_build_embedding_text_multi_word_paragraph_name() -> None:
    """Multi-hyphen COBOL name converts all hyphens to spaces."""
    chunk = make_chunk(
        paragraph_name="COMPUTE-NET-PAY-DEDUCTIONS",
        content="    SUBTRACT WS-TAX FROM WS-GROSS.",
    )
    text = build_embedding_text(chunk)
    assert "compute net pay deductions" in text


def test_embed_chunks_sends_enriched_text_not_raw_code() -> None:
    """embed_chunks must pass enriched text (file+para+code) to Voyage, not just code.

    This is the critical integration test: the text Voyage receives should
    include the paragraph name as a semantic hint alongside the code.
    """
    chunk = make_chunk(
        file_path="programs/loan-calc.cob",
        paragraph_name="CALCULATE-INTEREST",
        content="    COMPUTE WS-INTEREST = WS-PRINCIPAL * RATE.",
    )
    voyage_client = make_mock_voyage()

    import asyncio
    asyncio.get_event_loop().run_until_complete(embed_chunks([chunk], voyage_client))

    call_kwargs = voyage_client.embed.call_args
    # texts is the first positional arg to voyage_client.embed(texts, model=..., input_type=...)
    sent_texts: list[str] = call_kwargs.args[0]
    sent_text = sent_texts[0]

    # Must include human-readable context — not just the raw COBOL line
    assert "loan-calc" in sent_text
    assert "CALCULATE-INTEREST" in sent_text
    assert "calculate interest" in sent_text
    # Code content must still be there
    assert "COMPUTE WS-INTEREST" in sent_text


# ─────────────────────────────────────────────────────────────────────────────
# _extract_first_comment -- helper that finds the first meaningful comment
# ─────────────────────────────────────────────────────────────────────────────


def test_extract_first_comment_free_format_returns_text() -> None:
    """Free-format *> comment of >=20 chars returns the comment text."""
    content = (
        "CALCULATE-INTEREST.\n"
        "   *> Computes the total interest charged on the outstanding loan balance.\n"
        "       COMPUTE WS-INT = WS-PRIN * RATE."
    )
    result = _extract_first_comment(content)
    assert "interest charged" in result
    # The *> marker is stripped from the returned text
    assert "*>" not in result


def test_extract_first_comment_fixed_format_returns_text() -> None:
    """Fixed-format comment (* at column 7 / index 6) is also detected."""
    # Build a line where column 7 (0-indexed col 6) is '*'
    # COBOL fixed format: cols 1-6 are sequence/indicator, col 7 is indicator
    line = "      * Applies state income tax to gross pay for the current pay period."
    content = f"CALCULATE-STATE-TAX.\n{line}\n       COMPUTE WS-TAX = WS-PAY * 0.05."
    result = _extract_first_comment(content)
    assert "state income tax" in result


def test_extract_first_comment_separator_line_is_skipped() -> None:
    """Separator lines made entirely of dashes or equals are not meaningful comments."""
    content = (
        "COMPUTE-GROSS-PAY.\n"
        "   *> -----------------------------------------------------------\n"
        "   *> Calculates the total gross pay earned by the employee for the period.\n"
        "       COMPUTE WS-GROSS = WS-HOURS * WS-RATE."
    )
    result = _extract_first_comment(content)
    # Separator is skipped; the meaningful comment is returned instead
    assert "gross pay earned" in result
    assert "---" not in result


def test_extract_first_comment_no_comment_returns_empty_string() -> None:
    """Content with no comment lines returns an empty string."""
    content = (
        "CALCULATE-INTEREST.\n"
        "       COMPUTE WS-INT = WS-PRIN * RATE.\n"
        "       MOVE WS-INT TO WS-RESULT."
    )
    result = _extract_first_comment(content)
    assert result == ""


def test_extract_first_comment_short_comment_is_skipped() -> None:
    """Comments shorter than 20 characters are too brief to be useful — skip them."""
    content = (
        "INIT-VARS.\n"
        "   *> Set up.\n"  # 8 chars — too short
        "   *> Initializes all working storage variables to their default values.\n"
        "       MOVE ZEROS TO WS-AMOUNT."
    )
    result = _extract_first_comment(content)
    # Short comment is skipped; longer comment is returned
    assert "working storage variables" in result


def test_extract_first_comment_equals_separator_is_skipped() -> None:
    """Lines of all equals signs (another separator style) are also skipped."""
    content = (
        "MAIN-PROCEDURE.\n"
        "   *> ============================================================\n"
        "   *> Entry point for the main procedure. Controls overall flow.\n"
        "       PERFORM SETUP-VARS."
    )
    result = _extract_first_comment(content)
    assert "Entry point" in result


def test_extract_first_comment_returns_first_not_second() -> None:
    """Returns the first meaningful comment, not the second."""
    content = (
        "PROCESS-PAYMENT.\n"
        "   *> Credits a customer payment against the oldest open invoice first.\n"
        "   *> This is the second comment that should NOT be returned.\n"
        "       SUBTRACT WS-PAYMENT FROM WS-BALANCE."
    )
    result = _extract_first_comment(content)
    assert "oldest open invoice" in result
    assert "second comment" not in result


def test_extract_first_comment_empty_content_returns_empty_string() -> None:
    """Empty content string returns an empty string (no crash)."""
    result = _extract_first_comment("")
    assert result == ""


# ─────────────────────────────────────────────────────────────────────────────
# build_embedding_text -- Q&A format (when first comment is present)
# ─────────────────────────────────────────────────────────────────────────────


def test_build_embedding_text_with_comment_includes_qa_lead() -> None:
    """Named paragraph with a *> comment → Q&A lead line prepended to output."""
    chunk = make_chunk(
        file_path="data/financial-cobol/loan-calculator.cob",
        paragraph_name="CALCULATE-INTEREST",
        content=(
            "CALCULATE-INTEREST.\n"
            "   *> Computes the total interest charged over the life of the loan.\n"
            "       COMPUTE WS-INT = WS-PRIN * RATE."
        ),
    )
    text = build_embedding_text(chunk)
    # Q&A question part
    assert "What does the CALCULATE-INTEREST paragraph do?" in text
    # Q&A answer part
    assert "The CALCULATE-INTEREST paragraph" in text
    # The comment text should appear (lowercased) in the answer
    assert "computes the total interest" in text


def test_build_embedding_text_with_comment_still_includes_code() -> None:
    """Q&A format does not discard the raw COBOL code content."""
    chunk = make_chunk(
        file_path="data/financial-cobol/loan-calculator.cob",
        paragraph_name="CALCULATE-INTEREST",
        content=(
            "CALCULATE-INTEREST.\n"
            "   *> Computes the total interest charged over the life of the loan.\n"
            "       COMPUTE WS-INT = WS-PRIN * RATE."
        ),
    )
    text = build_embedding_text(chunk)
    assert "COMPUTE WS-INT" in text


def test_build_embedding_text_without_comment_no_qa_lead() -> None:
    """Named paragraph WITHOUT a *> comment → no Q&A lead line, just program/para/code."""
    chunk = make_chunk(
        file_path="programs/loan-calc.cob",
        paragraph_name="CALCULATE-INTEREST",
        content="    COMPUTE WS-INTEREST = WS-PRINCIPAL * RATE.",
    )
    text = build_embedding_text(chunk)
    # No Q&A lead when there is no comment to use as the answer
    assert "What does the" not in text
    # Standard header lines are still present
    assert "COBOL program: loan-calc" in text
    assert "Paragraph: CALCULATE-INTEREST" in text


def test_build_embedding_text_qa_answer_is_lowercased() -> None:
    """The first comment in the Q&A answer sentence is lowercased."""
    chunk = make_chunk(
        file_path="programs/payroll.cob",
        paragraph_name="COMPUTE-GROSS-PAY",
        content=(
            "COMPUTE-GROSS-PAY.\n"
            "   *> Calculates the total gross pay earned by the employee for the period.\n"
            "       COMPUTE WS-GROSS = WS-HOURS * WS-RATE."
        ),
    )
    text = build_embedding_text(chunk)
    # Comment text appears in lowercase in the answer
    assert "calculates the total gross pay" in text


def test_build_embedding_text_fallback_chunk_no_qa_lead() -> None:
    """Fallback chunk (no paragraph name) never gets a Q&A lead, even with comments."""
    chunk = make_chunk(
        file_path="programs/old-payroll.cob",
        paragraph_name=None,
        content=(
            "   *> This is a comment in a fallback chunk without a paragraph name.\n"
            "       MOVE WS-GROSS TO WS-PAY."
        ),
        is_fallback=True,
    )
    text = build_embedding_text(chunk)
    # Fallback chunks get no Q&A framing — no paragraph name to build from
    assert "What does the" not in text
    assert "Paragraph:" not in text
    # Code and file context are still present
    assert "old-payroll" in text
    assert "MOVE WS-GROSS" in text
