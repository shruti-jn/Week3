"""
Embedding generator -- converts COBOL chunks to vector embeddings for Pinecone.

This module is the bridge between raw COBOL text and the vector database.
Think of it like a translation service:
- Input: human-readable COBOL source code
- Output: lists of 1024 numbers that encode the *meaning* of that code

Those numbers let us search by meaning, not just keywords. Two COBOL paragraphs
that both compute interest will have similar numbers even if they use different
variable names, so a query like "how is interest calculated?" finds both.

Embedding model: voyage-code-2 (Voyage AI)
- Code-specific model trained on NL ↔ code pairs
- Scores +0.17 to +0.29 higher than text-embedding-3-small on COBOL retrieval
- Uses asymmetric retrieval: input_type="document" for chunks, "query" for queries
- voyageai.Client is synchronous; we wrap in asyncio.to_thread() to stay async

Pipeline position:
    file_scanner -> chunker -> [embedder] -> pinecone_client (upsert)
    user query -> [embedder.embed_query] -> pinecone_client (query) -> reranker

Public API:
    build_embedding_text() -- build the enriched text string sent to Voyage
    embed_chunks()         -- batch-embed a list of COBOLChunks into ChunkVectors
    embed_query()          -- embed a single user query string for retrieval
    embed_and_upsert()     -- full pipeline: embed chunks then store them in Pinecone
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import voyageai

from app.core.ingestion.chunk_filter import filter_chunks
from app.core.ingestion.chunker import COBOLChunk
from app.core.retrieval.pinecone_client import ChunkVector, PineconeWrapper

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# The Voyage AI model we use for embedding. Architecture decision (2026-03-03):
# voyage-code-2 is trained specifically on code ↔ natural-language pairs.
# It bridges the gap between "how does database connection work?" and
# `EXEC SQL CONNECT` — something text-embedding-3-small cannot do reliably.
EMBEDDING_MODEL: str = "voyage-code-2"

# Number of floats in each embedding vector. Must match the Pinecone index dimension.
# voyage-code-2 outputs 1536-dimensional vectors (same as text-embedding-3-small).
EMBEDDING_DIMENSIONS: int = 1536


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────


def _extract_first_comment(content: str) -> str:
    """
    Extract the first meaningful comment line from a COBOL chunk's content.

    COBOL comments begin with *> (free-format) or * in column 7 (fixed-format).
    This function scans the chunk content for the first non-trivial comment line
    and returns its text, stripped of the comment marker and leading whitespace.

    Used by build_embedding_text to generate the Q&A lead sentence that
    significantly improves semantic similarity scores for natural-language queries.

    Args:
        content: Raw content of a COBOLChunk (may include COBOL code + comments).

    Returns:
        First non-trivial comment text (>= 20 chars), or empty string if none found.
    """
    for line in content.splitlines():
        stripped = line.lstrip()
        # Free-format *> comment
        if stripped.startswith("*>"):
            text = stripped[2:].strip()
            if text and len(text) >= 20 and not all(c in "-=" for c in text):
                return text
        # Fixed-format: * at column 7 (index 6)
        elif len(line) > 6 and line[6] == "*":
            text = line[7:].strip()
            if text and len(text) >= 20 and not all(c in "-=" for c in text):
                return text
    return ""


def build_embedding_text(chunk: COBOLChunk) -> str:
    """
    Build the enriched text string sent to Voyage AI when embedding a COBOL chunk.

    Raw COBOL code alone is hard for a language model to match against plain-
    English queries. "COMPUTE WS-INT = WS-PRIN * RATE" doesn't look anything
    like "how is interest calculated?" — so cosine similarity stays very low.

    For named paragraphs, this function uses a Q&A format that mirrors how users
    actually phrase queries: "What does the CALCULATE-INTEREST paragraph do?
    The CALCULATE-INTEREST paragraph computes the total interest charged..."

    This Q&A framing works because the embedding model sees both the question
    and the answer in the same vector space as user queries, pushing cosine
    similarity scores well above the 0.75 relevance threshold.

    For fallback chunks (no paragraph name), the format is simpler: just the
    file context plus the raw COBOL content.

    The metadata stored in Pinecone still contains the raw code — this
    enriched text is ONLY used at embedding time, not at display time.

    Args:
        chunk: The COBOLChunk to build embedding text for.

    Returns:
        A multi-line string with Q&A framing (for named paragraphs) or
        file context + content (for fallback chunks).

    Examples:
        Named paragraph with a first comment:
            "What does the CALCULATE-INTEREST paragraph do?\\n"
            "The CALCULATE-INTEREST paragraph computes the total interest...\\n"
            "COBOL program: loan-calc\\n"
            "Paragraph: CALCULATE-INTEREST (calculate interest)\\n"
            "    COMPUTE WS-INTEREST = WS-PRINCIPAL * RATE."

        Named paragraph without a comment:
            "COBOL program: loan-calc\\n"
            "Paragraph: CALCULATE-INTEREST (calculate interest)\\n"
            "    COMPUTE WS-INTEREST = WS-PRINCIPAL * RATE."

        Fallback chunk (no paragraph):
            "COBOL program: old-payroll\\n"
            "    MOVE WS-GROSS TO WS-PAY."
    """
    parts: list[str] = []

    # Use just the file stem — the short name without directory or extension.
    # "loan-calc" is semantically useful; "/Users/shruti/Week3/data/..." is noise.
    file_stem = Path(str(chunk.file_path)).stem

    if chunk.paragraph_name:
        # Convert COBOL-HYPHEN-NAME to "cobol hyphen name" for NLP matching.
        readable = chunk.paragraph_name.replace("-", " ").lower()

        # Build Q&A lead: "What does PARA-NAME paragraph do?
        # The PARA-NAME paragraph [description]"
        # This format mirrors typical user queries and dramatically improves cosine
        # similarity above the 0.75 threshold versus plain code + header embedding.
        first_comment = _extract_first_comment(chunk.content)
        if first_comment:
            parts.append(
                f"What does the {chunk.paragraph_name} paragraph do? "
                f"The {chunk.paragraph_name} paragraph {first_comment.lower()}"
            )

        parts.append(f"COBOL program: {file_stem}")
        parts.append(f"Paragraph: {chunk.paragraph_name} ({readable})")
    else:
        parts.append(f"COBOL program: {file_stem}")

    # Always include the actual COBOL code — it provides specific keyword signals
    # (COMPUTE, PERFORM, MOVE, etc.) that supplement the semantic context above.
    parts.append(chunk.content)

    return "\n".join(parts)


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
    voyage_client: voyageai.Client,  # type: ignore[name-defined]  # no stubs
    texts: list[str],
    input_type: str = "document",
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
) -> list[list[float]]:
    """
    Call the Voyage AI embeddings API with exponential-backoff retry.

    voyageai.Client is synchronous. We run it in a thread pool via
    asyncio.to_thread() so the FastAPI event loop stays unblocked during
    the network call. The thread pool handles blocking I/O without stalling
    other in-flight requests.

    Voyage uses asymmetric retrieval:
    - input_type="document" for COBOL chunks being indexed
    - input_type="query"    for user search queries

    If the call fails, we wait and try again. Each retry waits twice as long:
    attempt 1 fails -> wait 1s, attempt 2 fails -> wait 2s, attempt 3 -> raise.

    Args:
        voyage_client:      Voyage AI client (real or mock for tests).
        texts:              List of strings to embed in one API call.
        input_type:         "document" for chunks, "query" for search queries.
        max_attempts:       Maximum number of attempts before giving up.
        base_delay_seconds: Wait time for the first retry. Doubles each attempt.

    Returns:
        List of embedding vectors (one list[float] per input text).

    Raises:
        The last exception raised after all attempts are exhausted.
    """
    last_exc: BaseException | None = None

    for attempt in range(max_attempts):
        try:
            # Run synchronous Voyage client in a thread pool so the async
            # event loop is free to handle other requests during the API call.
            result: Any = await asyncio.to_thread(
                voyage_client.embed,
                texts,
                model=EMBEDDING_MODEL,
                input_type=input_type,
            )
            embeddings: list[list[float]] = result.embeddings
            return embeddings
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = base_delay_seconds * (2**attempt)
                logger.warning(
                    "Voyage embeddings call failed (attempt %d/%d): %s. "
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
    voyage_client: voyageai.Client,  # type: ignore[name-defined]  # no stubs
    batch_size: int = 100,
) -> list[ChunkVector]:
    """
    Convert a list of COBOL chunks into ChunkVector objects ready for Pinecone.

    This is where plain COBOL text becomes searchable numbers. We send chunk
    content to Voyage AI's embeddings API in batches (up to batch_size texts per
    API call) to stay within rate limits and maximise throughput.

    Each returned ChunkVector contains:
    - A unique ID (file_path::PARA-NAME or file_path::chunk_N)
    - A 1024-float embedding vector from Voyage AI
    - Metadata (file_path, start_line, end_line, content, etc.)

    Args:
        chunks:        List of COBOLChunk objects from the chunker.
        voyage_client: Voyage AI client (real or mock for tests).
        batch_size:    Max texts per Voyage API call. Default 100 stays well
                       within typical rate limits.

    Returns:
        List of ChunkVector objects in the same order as the input chunks.
        Empty list if chunks is empty (no API call is made).

    Raises:
        Exception: If all retry attempts fail (e.g. invalid API key,
                   sustained rate limit). The original error is re-raised.
    """
    if not chunks:
        logger.debug("embed_chunks: no chunks to embed -- returning empty list")
        return []

    vectors: list[ChunkVector] = []

    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        # Use enriched text (file stem + paragraph name + code) rather than
        # raw code alone. This bridges English queries to COBOL identifiers.
        # See build_embedding_text() for details on why this matters.
        texts = [build_embedding_text(chunk) for chunk in batch]

        logger.debug(
            "embed_chunks: embedding batch %d-%d (%d chunks)",
            batch_start,
            batch_start + len(batch) - 1,
            len(batch),
        )

        # input_type="document" tells Voyage to optimise for indexed content
        # (as opposed to "query" which optimises for search queries).
        embeddings = await _call_embed_api(voyage_client, texts, input_type="document")

        # embeddings[i] corresponds to texts[i] (and batch[i]).
        # Voyage guarantees one embedding per input text.
        # B905: strict= kwarg requires Python 3.10+; dev runtime is Python 3.9
        for chunk, embedding in zip(batch, embeddings):  # noqa: B905
            vectors.append(
                ChunkVector(
                    id=_make_vector_id(chunk),
                    embedding=embedding,
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
    voyage_client: voyageai.Client,  # type: ignore[name-defined]  # no stubs
) -> list[float]:
    """
    Convert a user's plain-English query into a 1024-float embedding vector.

    This embedding is used by the retrieval layer to find the most semantically
    similar COBOL chunks in Pinecone (via cosine similarity).

    Think of this as translating a question into the same "coordinate space"
    as the stored code -- so "how is tax computed?" gets placed near all the
    paragraphs that handle tax calculations.

    Uses input_type="query" for Voyage asymmetric retrieval: query embeddings
    and document embeddings are optimised differently, improving precision.

    Args:
        query_text:    The raw user question (e.g. "How does interest get computed?").
                       Must be non-empty (whitespace-only is rejected too).
        voyage_client: Voyage AI client (real or mock for tests).

    Returns:
        A list of 1024 floats representing the query in embedding space.

    Raises:
        ValueError: If query_text is empty or whitespace-only.
        Exception:  If all retry attempts fail.
    """
    if not query_text.strip():
        raise ValueError(
            "query_text must not be empty or whitespace-only. "
            "Provide a meaningful search query."
        )

    logger.debug("embed_query: embedding query of length %d chars", len(query_text))

    # input_type="query" activates Voyage's asymmetric retrieval optimisation:
    # queries and documents are embedded differently to improve recall.
    embeddings = await _call_embed_api(voyage_client, [query_text], input_type="query")

    embedding: list[float] = embeddings[0]
    logger.debug("embed_query: got %d-dim embedding", len(embedding))
    return embedding


async def embed_and_upsert(
    chunks: list[COBOLChunk],
    voyage_client: voyageai.Client,  # type: ignore[name-defined]  # no stubs
    pinecone_wrapper: PineconeWrapper,
    batch_size: int = 100,
) -> int:
    """
    Full ingestion pipeline: embed COBOL chunks and store them in Pinecone.

    This function orchestrates two steps:
    1. embed_chunks() -- convert text to vectors (calls Voyage AI)
    2. pinecone_wrapper.upsert_batch() -- store vectors (calls Pinecone)

    Use this as the single entry point when ingesting a COBOL file's chunks.
    It handles batching, retries, and logging internally.

    Args:
        chunks:           COBOLChunk objects from the chunker. Can be empty
                          (returns 0 without making any API calls).
        voyage_client:    Voyage AI client (real or mock for tests).
        pinecone_wrapper: PineconeWrapper instance connected to the target index.
        batch_size:       Max texts per Voyage embedding call (default 100).

    Returns:
        Total number of vectors successfully stored in Pinecone. 0 if empty.

    Raises:
        Exception:             If embedding calls fail after retries.
        pinecone.ApiException: If Pinecone upsert fails.
    """
    if not chunks:
        logger.debug("embed_and_upsert: no chunks provided -- skipping")
        return 0

    # Filter out stub chunks (exit trampolines, constants, separators)
    # before embedding — they degrade retrieval quality without adding value.
    indexable = filter_chunks(chunks)
    skipped = len(chunks) - len(indexable)
    if skipped:
        logger.info(
            "embed_and_upsert: filtered %d stub chunks (kept %d/%d)",
            skipped,
            len(indexable),
            len(chunks),
        )
    if not indexable:
        logger.info("embed_and_upsert: no indexable chunks after filtering")
        return 0

    logger.info("embed_and_upsert: processing %d chunks", len(indexable))

    vectors = await embed_chunks(indexable, voyage_client, batch_size=batch_size)
    upserted = await pinecone_wrapper.upsert_batch(vectors)

    logger.info("embed_and_upsert: stored %d vectors in Pinecone", upserted)
    return upserted
