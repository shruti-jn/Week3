"""
Application configuration — loads all settings from environment variables.

Why do we do it this way?
Think of environment variables like a secret lockbox. The code doesn't
have the keys baked in — instead, it asks the lockbox for the keys at
runtime. This means:
- We can't accidentally commit API keys to GitHub
- We can use different keys for dev vs production without changing code
- If a key is compromised, we only change the lockbox, not the code

Pydantic-settings automatically reads from .env files during development
and from real environment variables in production (Railway, Vercel).
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All application configuration in one place.

    Every attribute here MUST exist as an environment variable (or in .env).
    If a required variable is missing, the app crashes immediately on startup
    with a clear error message — better to fail fast than to run broken.

    See backend/.env.example for a template of all required variables.
    """

    # ── OpenAI ────────────────────────────────────────────────────────────
    # Used for: generating embeddings (text-embedding-3-small) and answers (gpt-4o-mini)
    openai_api_key: str = Field(description="OpenAI API key — starts with sk-")

    # ── Pinecone ──────────────────────────────────────────────────────────
    # Used for: storing and searching COBOL code embeddings
    pinecone_api_key: str = Field(description="Pinecone API key")
    pinecone_index_name: str = Field(
        default="legacylens",
        description="Name of the Pinecone index to use",
    )

    # ── Auth (NextAuth secrets) ────────────────────────────────────────────
    # Used for: validating JWT tokens sent by the Next.js frontend
    # The frontend signs tokens with nextauth_secret; the backend verifies them
    github_client_id: str = Field(description="GitHub OAuth App client ID")
    github_client_secret: str = Field(description="GitHub OAuth App client secret")
    nextauth_secret: str = Field(description="NextAuth.js secret — used to sign JWT tokens")

    # ── CORS ──────────────────────────────────────────────────────────────
    # Restricts which domains can call our API.
    # In dev: ["http://localhost:3000"]
    # In production: ["https://legacylens.vercel.app"]
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins — restrict to frontend URL only",
    )

    # ── Rate Limiting ──────────────────────────────────────────────────────
    # How many API requests a single user can make per minute.
    # Prevents abuse and controls OpenAI API costs.
    rate_limit_per_minute: int = Field(
        default=20,
        description="Max requests per user per minute (default: 20)",
    )

    # ── Retrieval Tuning ──────────────────────────────────────────────────
    # These control how the RAG pipeline behaves.
    # Higher top_k = more candidates to rerank = slightly slower but better results
    retrieval_top_k: int = Field(
        default=10,
        description="Number of chunks to retrieve from Pinecone before reranking",
    )
    # Minimum similarity score to consider a chunk "relevant enough" to answer from.
    # Below this threshold, we return a safe fallback instead of a potentially wrong answer.
    similarity_threshold: float = Field(
        default=0.75,
        description="Minimum Pinecone similarity score to use a chunk (0.0 to 1.0)",
    )

    # Pydantic-settings configuration:
    # - env_file: read from .env file in the backend directory during development
    # - env_file_encoding: use UTF-8 so international characters work
    # - case_sensitive: False means OPENAI_API_KEY and openai_api_key both work
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    """
    Return the application settings object (cached after first call).

    @lru_cache means this function only creates the Settings object ONCE,
    no matter how many times it's called. This is important because:
    1. Reading from .env files and validating all fields takes time
    2. We want the same Settings instance everywhere in the app

    Usage:
        settings = get_settings()
        api_key = settings.openai_api_key
    """
    return Settings()
