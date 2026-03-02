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
        openai: AsyncOpenAI = Depends(get_openai_client),
    ) -> QueryResponse:
        ...
"""

from functools import lru_cache

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
def get_openai_client() -> AsyncOpenAI:
    """
    Create and return an async OpenAI client (cached — created only once).

    OpenAI provides two capabilities we use:
    1. text-embedding-3-small: converts text to numbers (embeddings)
    2. gpt-4o-mini: generates natural-language answers from COBOL context

    AsyncOpenAI is the async version — it doesn't block while waiting
    for OpenAI's API response, so other requests can be handled meanwhile.

    Returns:
        A configured async OpenAI client ready to use.
    """
    settings = get_settings()
    return AsyncOpenAI(api_key=settings.openai_api_key)
