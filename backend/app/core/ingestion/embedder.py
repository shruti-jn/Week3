"""
Embedding generator -- converts COBOL chunks to vector embeddings for Pinecone.

This module is the bridge between raw COBOL text and the vector database.
Think of it like a translation service:
- Input: human-readable COBOL source code
- Output: lists of 1536 numbers that encode the *meaning* of that code

Those numbers let us search by meaning, not just keywords. Two COBOL paragraphs
that both compute interest will have similar numbers even if they use different
variable names, so a query like "how is interest calculated?" finds both.

Pipeline position:
    file_scanner -> chunker -> [embedder] -> pinecone_client (upsert)
    user query -> [embedder.embed_query] -> pinecone_client (query) -> reranker

Public API:
    embed_chunks()      -- batch-embed a list of COBOLChunks into ChunkVectors
    embed_query()       -- embed a single user query string for retrieval
    embed_and_upsert()  -- full pipeline: embed chunks then store them in Pinecone
"""

from __future__ import annotations

import asyncio
import logging

from openai import AsyncOpenAI
from openai.types import CreateEmbeddingResponse

from app.core.ingestion.chunker import COBOLChunk
from app.core.retrieval.pinecone_client import ChunkVector, PineconeWrapper

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# The OpenAI model we use for embedding. Architecture decision:
# text-embedding-3-small gives 1536-dimensional vectors at ~5x lower cost
# than text-embedding-3-large, with sufficient quality for paragraph-level COBOL.
EMBEDDING_MODEL: str = "text-embedding-3-small"

# Number of floats in each embedding vector. Must match the Pinecone index dimension.
EMBEDDING_DIMENSIONS: int = 1536


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_vector_id(chunk: COBOLChunk) -> str:
    """
    Build a unique Pinecone vector ID for a COBOL chunk.

    Convention: "file_path::PARAGRAPH-NAME" for named paragraphs,
                "file_path::chunk_N" for fallback (unnamed) chunks.

    Examples:
        Named:    "programs/loan-calc.cob::CALCULATE-INTEREST"
        Fallback: "programs/old-payroll.cob::chunk_3"

    Args:
        chunk: The COBOLChunk whose ID we're generating.

    Returns:
        A unique string identifier for this chunk within Pinecone.
    """
    if chunk.paragraph_name is not None:
        return f"{chunk.file_path}::{chunk.paragraph_name}"
    return f"{chunk.file_path}::chunk_{chunk.chunk_index}"


def _make_metadata(chunk: COBOLChunk) -> dict[str, str | int | bool]:
    """
    Build the metadata dict stored alongside a vector in Pinecone.

    Pinecone lets us store arbitrary key-value data next to each vector.
    We store everything needed to show the user a useful citation:
    the file, the line range, the paragraph name, and the raw source.

    Pinecone metadata values must be strings, numbers, or booleans -- not None.
    So paragraph_name is stored as "" when the chunk has no paragraph name.

    Args:
        chunk: The COBOLChunk whose metadata we're building.

    Returns:
        Dict with all fields needed to display a search result citation.
    """
    # Store "" instead of None -- Pinecone doesn't accept null metadata values
    para_name: str = chunk.paragraph_name if chunk.paragraph_name is not None else ""
    return {
        "file_path": chunk.file_path,
        "paragraph_name": para_name,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "content": chunk.content,
        "chunk_index": chunk.chunk_index,
        "is_fallback": chunk.is_fallback,
    }


async def _call_embed_api(
    openai_client: AsyncOpenAI,
    texts: list[str],
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
) -> CreateEmbeddingResponse:
    """
    Call the OpenAI embeddings API with exponential-backoff retry.

    If the call fails, we wait and try again. Each retry waits twice as long:
    attempt 1 fails -> wait 1s, attempt 2 fails -> wait 2s, attempt 3 -> raise.

    This handles transient OpenAI errors: rate-limit (429) and server errors (500).

    Think of it like pressing a crosswalk button -- if the light doesn't
    change, wait a bit longer and press again. Don't press 100 times immediately.

    Args:
        openai_client:      Async OpenAI client (real or mock for tests).
        texts:              List of strings to embed in one API call.
        max_attempts:       Maximum number of attempts before giving up.
        base_delay_seconds: Wait time for the first retry. Doubles each attempt.

    Returns:
        CreateEmbeddingResponse with one embedding per input text.

    Raises:
        The last exception raised after all attempts are exhausted.
    """
    last_exc: BaseException | None = None

    for attempt in range(max_attempts):
        try:
            return await openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts,
            )
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = base_delay_seconds * (2**attempt)
                logger.warning(
                    "OpenAI embeddings call failed (attempt %d/%d): %s. "
                    "Retrying in %.1fs...",
                    attempt + 1,
                    max_attempts,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable: max_attempts must be >= 1")  # pragma: no cover


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def embed_chunks(
    chunks: list[COBOLChunk],
    openai_client: AsyncOpenAI,
    batch_size: int = 100,
) -> list[ChunkVector]:
    """
    Convert a list of COBOL chunks into ChunkVector objects ready for Pinecone.

    This is where plain COBOL text becomes searchable numbers. We send chunk
    content to OpenAI's embeddings API in batches (up to batch_size texts per
    API call) to stay within rate limits and maximise throughput.

    Each returned ChunkVector contains:
    - A unique ID (file_path::PARA-NAME or file_path::chunk_N)
    - A 1536-float embedding vector from OpenAI
    - Metadata (file_path, start_line, end_line, content, etc.)

    Args:
        chunks:        List of COBOLChunk objects from the chunker.
        openai_client: Async OpenAI client (real or mock for tests).
        batch_size:    Max texts per OpenAI API call. Default 100 stays well
                       within OpenAI's limits and avoids rate-limit errors.

    Returns:
        List of ChunkVector objects in the same order as the input chunks.
        Empty list if chunks is empty (no API call is made).

    Raises:
        openai.APIError: If all retry attempts fail (e.g. invalid API key,
                         sustained rate limit). The original error is re-raised.
    """
    if not chunks:
        logger.debug("embed_chunks: no chunks to embed -- returning empty list")
        return []

    vectors: list[ChunkVector] = []

    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        texts = [chunk.content for chunk in batch]

        logger.debug(
            "embed_chunks: embedding batch %d-%d (%d chunks)",
            batch_start,
            batch_start + len(batch) - 1,
            len(batch),
        )

        response = await _call_embed_api(openai_client, texts)

        # response.data[i].embedding corresponds to texts[i].
        # OpenAI guarantees one embedding per input text, so lengths always match.
        # B905: strict= kwarg requires Python 3.10+; dev runtime is Python 3.9
        for chunk, embedding_obj in zip(batch, response.data):  # noqa: B905
            vectors.append(
                ChunkVector(
                    id=_make_vector_id(chunk),
                    embedding=embedding_obj.embedding,
                    metadata=_make_metadata(chunk),
                )
            )

    logger.info(
        "embed_chunks: produced %d vectors from %d chunks",
        len(vectors),
        len(chunks),
    )
    return vectors


async def embed_query(
    query_text: str,
    openai_client: AsyncOpenAI,
) -> list[float]:
    """
    Convert a user's plain-English query into a 1536-float embedding vector.

    This embedding is used by the retrieval layer to find the most semantically
    similar COBOL chunks in Pinecone (via cosine similarity).

    Think of this as translating a question into the same "coordinate space"
    as the stored code -- so "how is tax computed?" gets placed near all the
    paragraphs that handle tax calculations.

    Args:
        query_text:    The raw user question (e.g. "How does interest get computed?").
                       Must be non-empty (whitespace-only is rejected too).
        openai_client: Async OpenAI client (real or mock for tests).

    Returns:
        A list of 1536 floats representing the query in embedding space.

    Raises:
        ValueError: If query_text is empty or whitespace-only.
        openai.APIError: If all retry attempts fail.
    """
    if not query_text.strip():
        raise ValueError(
            "query_text must not be empty or whitespace-only. "
            "Provide a meaningful search query."
        )

    logger.debug("embed_query: embedding query of length %d chars", len(query_text))

    response = await _call_embed_api(openai_client, [query_text])

    embedding: list[float] = response.data[0].embedding
    logger.debug("embed_query: got %d-dim embedding", len(embedding))
    return embedding


async def embed_and_upsert(
    chunks: list[COBOLChunk],
    openai_client: AsyncOpenAI,
    pinecone_wrapper: PineconeWrapper,
    batch_size: int = 100,
) -> int:
    """
    Full ingestion pipeline: embed COBOL chunks and store them in Pinecone.

    This function orchestrates two steps:
    1. embed_chunks() -- convert text to vectors (calls OpenAI)
    2. pinecone_wrapper.upsert_batch() -- store vectors (calls Pinecone)

    Use this as the single entry point when ingesting a COBOL file's chunks.
    It handles batching, retries, and logging internally.

    Args:
        chunks:           COBOLChunk objects from the chunker. Can be empty
                          (returns 0 without making any API calls).
        openai_client:    Async OpenAI client (real or mock for tests).
        pinecone_wrapper: PineconeWrapper instance connected to the target index.
        batch_size:       Max texts per OpenAI embedding call (default 100).

    Returns:
        Total number of vectors successfully stored in Pinecone. 0 if empty.

    Raises:
        openai.APIError:       If embedding calls fail after retries.
        pinecone.ApiException: If Pinecone upsert fails.
    """
    if not chunks:
        logger.debug("embed_and_upsert: no chunks provided -- skipping")
        return 0

    logger.info("embed_and_upsert: processing %d chunks", len(chunks))

    vectors = await embed_chunks(chunks, openai_client, batch_size=batch_size)
    upserted = await pinecone_wrapper.upsert_batch(vectors)

    logger.info("embed_and_upsert: stored %d vectors in Pinecone", upserted)
    return upserted
