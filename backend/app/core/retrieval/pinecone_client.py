"""
Pinecone client wrapper — handles upsert and query operations.

This module provides a thin, tested wrapper around the Pinecone SDK.
It separates two concerns:
1. Business logic (what vectors to store, what scores are acceptable)
2. Pinecone SDK details (how to call the API, how to batch requests)

Think of it like a librarian:
- upsert_batch() is like shelving new books (storing embeddings)
- query() is like asking the librarian to find books on a topic (searching)

The raw Pinecone SDK is injected via __init__ so tests can swap in a mock.
This means we never make real Pinecone API calls in unit tests.

Pipeline position:
    file_scanner → chunker → embedder → [pinecone_client upsert]
    user query → embedder → [pinecone_client query] → reranker → answer
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChunkVector:
    """
    A single COBOL code chunk ready to be stored in Pinecone.

    Think of this like a library card for a code snippet:
    - id: the unique shelf number (file path + paragraph name)
    - embedding: the 1536-dimension fingerprint of the code's meaning
    - metadata: human-readable info stored alongside the vector

    Attributes:
        id:        Unique identifier for this chunk. Convention: "file.cob::PARA-NAME"
        embedding: 1536-float vector produced by text-embedding-3-small.
        metadata:  Dict of strings stored alongside the embedding in Pinecone.
                   Must contain at least file_path, start_line, end_line, content.
    """

    id: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """
    A single result returned by query() after filtering by score threshold.

    Think of this like a search result card — it tells you which piece
    of COBOL code matched your query and how confident we are about it.

    Attributes:
        chunk_id:  The Pinecone vector ID (e.g., "programs/payroll.cob::CALC-GROSS").
        score:     Cosine similarity score (0.0–1.0). Higher = more relevant.
        metadata:  The stored metadata dict (file_path, start_line, etc.).
    """

    chunk_id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class PineconeWrapper:
    """
    Thin wrapper around the Pinecone SDK providing upsert and query operations.

    Why a wrapper instead of using the SDK directly?
    1. Testability: we can inject a mock client for unit tests
    2. Batching: Pinecone has a max of 100 vectors per upsert call
    3. Filtering: query() applies score threshold filtering that the SDK doesn't do
    4. Logging: every operation is logged with structured context

    Usage:
        from app.dependencies import get_pinecone_client
        from app.config import get_settings

        client = get_pinecone_client()
        settings = get_settings()
        wrapper = PineconeWrapper(client=client, index_name=settings.pinecone_index_name)

        results = await wrapper.query(embedding, top_k=5, min_score=0.75)
    """

    def __init__(self, client: Any, index_name: str) -> None:
        """
        Initialize the wrapper and connect to the named Pinecone index.

        Args:
            client:     A Pinecone client instance (real or mock).
            index_name: Name of the Pinecone index to use (e.g., "legacylens").
        """
        self._index = client.Index(index_name)
        self._index_name = index_name
        logger.info("PineconeWrapper connected to index: %s", index_name)

    async def upsert_batch(
        self,
        vectors: list[ChunkVector],
        batch_size: int = 100,
    ) -> int:
        """
        Store a list of chunk vectors into Pinecone, in batches.

        Pinecone has a hard limit of 100 vectors per API call. This method
        automatically splits larger lists into batches and calls upsert
        once per batch. Batches are processed sequentially to avoid rate limits.

        Think of it like moving books to a library shelf — you carry 100 at a
        time because that's what fits on the cart.

        Args:
            vectors:    List of ChunkVector objects to store. Can be empty.
            batch_size: Max vectors per Pinecone upsert call (default: 100).
                        Reduce this if you're hitting Pinecone rate limits.

        Returns:
            Total number of vectors successfully upserted. 0 if list is empty.

        Example:
            chunks = [ChunkVector(id="f.cob::PARA", embedding=[...], metadata={...})]
            count = await wrapper.upsert_batch(chunks)
            # count == 1
        """
        if not vectors:
            logger.debug("upsert_batch called with empty list — skipping")
            return 0

        total_upserted = 0

        # Split into batches of batch_size
        for batch_start in range(0, len(vectors), batch_size):
            batch = vectors[batch_start : batch_start + batch_size]

            # Convert ChunkVector objects to the format Pinecone expects:
            # a list of tuples (id, values, metadata) or dicts
            pinecone_records = [
                {"id": v.id, "values": v.embedding, "metadata": v.metadata}
                for v in batch
            ]

            # Run the synchronous Pinecone SDK call in an executor so it
            # doesn't block the async event loop
            await asyncio.get_event_loop().run_in_executor(
                None,  # Use default thread pool
                lambda records=pinecone_records: self._index.upsert(vectors=records),
            )

            total_upserted += len(batch)
            logger.debug(
                "Upserted batch %d–%d (%d vectors) to index '%s'",
                batch_start,
                batch_start + len(batch) - 1,
                len(batch),
                self._index_name,
            )

        logger.info(
            "upsert_batch complete: %d vectors in %d batches",
            total_upserted,
            (len(vectors) + batch_size - 1) // batch_size,
        )
        return total_upserted

    async def query(
        self,
        embedding: list[float],
        top_k: int,
        min_score: float,
    ) -> list[SearchResult]:
        """
        Find the most similar COBOL chunks to a query embedding.

        Calls Pinecone's vector similarity search, then filters out any
        results below the min_score threshold (our confidence cutoff).
        Results are returned sorted by score descending (most relevant first).

        Think of it like a Google search — you get back the top matches,
        but we discard any that aren't relevant enough to be trustworthy.

        Args:
            embedding:  The query embedding vector (1536 floats from OpenAI).
            top_k:      How many candidates to request from Pinecone (1–20).
                        More candidates = slightly better results but more cost.
            min_score:  Minimum cosine similarity to include in results (0.0–1.0).
                        Below this threshold, the code is not relevant enough.
                        Project default: 0.75 (from config.similarity_threshold).

        Returns:
            List of SearchResult objects sorted by score descending.
            Empty list if no results meet the min_score threshold.

        Example:
            query_vec = [0.1] * 1536  # from OpenAI embeddings API
            results = await wrapper.query(query_vec, top_k=5, min_score=0.75)
            for r in results:
                print(r.chunk_id, r.score)
            # loan-calc.cob::CALCULATE-INTEREST 0.92
            # payroll.cob::COMPUTE-TAX 0.81
        """
        logger.debug(
            "Querying Pinecone index '%s' with top_k=%d, min_score=%.2f",
            self._index_name,
            top_k,
            min_score,
        )

        # Run the synchronous Pinecone SDK call in an executor
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._index.query(
                vector=embedding,
                top_k=top_k,
                include_metadata=True,
            ),
        )

        # Convert Pinecone response objects to our SearchResult dataclass
        # and filter out matches below the score threshold
        results: list[SearchResult] = []
        for match in response.matches:
            if match.score < min_score:
                logger.debug(
                    "Filtered out chunk '%s' (score %.3f < threshold %.2f)",
                    match.id,
                    match.score,
                    min_score,
                )
                continue

            results.append(
                SearchResult(
                    chunk_id=match.id,
                    score=match.score,
                    metadata=dict(match.metadata) if match.metadata else {},
                )
            )

        # Sort by score descending (highest relevance first)
        # Pinecone usually returns results sorted, but we enforce it here
        results.sort(key=lambda r: r.score, reverse=True)

        logger.info(
            "query returned %d results (above %.2f threshold) from %d candidates",
            len(results),
            min_score,
            len(response.matches),
        )
        return results
