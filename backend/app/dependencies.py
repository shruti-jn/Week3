"""
FastAPI dependency injection providers.

Dependency injection is a design pattern where components receive their
dependencies from an outside source rather than creating them themselves.

Think of it like a restaurant: the chef (route handler) doesn't go buy
ingredients themselves — the kitchen manager (dependency system) provides
them. This makes it easy to swap ingredients during testing (use fake
ingredients instead of real, expensive ones).

FastAPI's Depends() system calls these functions automatically and passes
the results to route handlers.

Usage in a route:
    @router.post("/query")
    async def query(
        request: QueryRequest,
        pinecone: Pinecone = Depends(get_pinecone_client),
        voyage: voyageai.Client = Depends(get_voyage_client),
    ) -> QueryResponse:
        ...
"""

from functools import lru_cache

import voyageai
from openai import AsyncOpenAI
from pinecone import Pinecone

from app.config import get_settings


@lru_cache
def get_pinecone_client() -> Pinecone:
    """
    Create and return a Pinecone client (cached — created only once).

    Pinecone is our vector database. This client is how we:
    - Store COBOL code embeddings (during ingestion)
    - Search for similar embeddings (during query answering)

    @lru_cache means the same client object is reused across all requests,
    rather than creating a new connection for every API call.

    Returns:
        A configured Pinecone client ready to use.
    """
    settings = get_settings()
    return Pinecone(api_key=settings.pinecone_api_key)


@lru_cache
def get_voyage_client() -> voyageai.Client:  # type: ignore[name-defined]  # no stubs
    """
    Create and return a Voyage AI embedding client (cached — created only once).

    Voyage AI provides voyage-code-2, a code-specific embedding model trained
    to bridge the gap between natural-language queries and code constructs
    (SQL, COBOL, identifiers). It scores +0.17 to +0.29 higher than
    text-embedding-3-small on COBOL ↔ natural-language retrieval tasks.

    voyageai.Client is synchronous. The embedder module wraps calls in
    asyncio.to_thread() so the FastAPI async event loop stays unblocked.

    Returns:
        A configured Voyage AI client ready to use.
    """
    settings = get_settings()
    return voyageai.Client(api_key=settings.voyage_api_key)  # type: ignore[attr-defined]  # no stubs


@lru_cache
def get_openai_client() -> AsyncOpenAI:
    """
    Create and return an async OpenAI client (cached — created only once).

    After switching embeddings to Voyage AI, OpenAI is used only for:
    - gpt-4o-mini: generates natural-language answers from COBOL context (streaming)

    AsyncOpenAI is the async version — it doesn't block while waiting
    for OpenAI's API response, so other requests can be handled meanwhile.

    Returns:
        A configured async OpenAI client ready to use.
    """
    settings = get_settings()
    return AsyncOpenAI(api_key=settings.openai_api_key)
