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

import logging
from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel used to detect when Langfuse keys are not configured.
# We use a module-level constant so the Settings class can reference it.
_LANGFUSE_NOT_SET = ""
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    All application configuration in one place.

    Every attribute here MUST exist as an environment variable (or in .env).
    If a required variable is missing, the app crashes immediately on startup
    with a clear error message — better to fail fast than to run broken.

    See backend/.env.example for a template of all required variables.
    """

    # ── OpenAI ────────────────────────────────────────────────────────────
    # Used for: answer generation only (gpt-4o-mini). Embeddings moved to Voyage AI.
    openai_api_key: str = Field(description="OpenAI API key — starts with sk-")

    # ── Voyage AI ─────────────────────────────────────────────────────────
    # Used for: generating embeddings (voyage-code-2, 1024 dims).
    # voyage-code-2 is code-specific and scores +0.17 to +0.29 higher than
    # text-embedding-3-small on COBOL ↔ natural-language retrieval tasks.
    voyage_api_key: str = Field(description="Voyage AI API key — starts with pk-live-")

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
    nextauth_secret: str = Field(
        description="NextAuth.js secret — used to sign JWT tokens"
    )

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

    # ── Deployment Environment ────────────────────────────────────────────
    # Controls environment-specific behavior (e.g., disabling /docs in production).
    # Set ENVIRONMENT=production on Railway to harden the deployed service.
    environment: str = Field(
        default="development",
        description='Runtime environment: "development" or "production"',
    )

    # ── Retrieval Tuning ──────────────────────────────────────────────────
    # These control how the RAG pipeline behaves.
    # Higher top_k = more candidates to rerank = slightly slower but better results
    retrieval_top_k: int = Field(
        default=5,
        description="Number of chunks to retrieve from Pinecone before reranking",
    )
    # Minimum similarity score to consider a chunk "relevant enough" to answer from.
    # Below this threshold, we return a fallback — no answer beats a wrong one.
    similarity_threshold: float = Field(
        default=0.75,
        description="Minimum Pinecone similarity score to use a chunk (0.0 to 1.0)",
    )

    # ── Langfuse Observability (optional) ─────────────────────────────────
    # Langfuse traces every query — embed, retrieve, rerank, and LLM steps —
    # so you can see latency breakdowns and debug slow or failed queries.
    # Leave these empty to run without tracing (the app works fine without them).
    langfuse_secret_key: str = Field(
        default=_LANGFUSE_NOT_SET,
        description="Langfuse secret key (sk-lf-...). Leave empty to disable tracing.",
    )
    langfuse_public_key: str = Field(
        default=_LANGFUSE_NOT_SET,
        description="Langfuse public key (pk-lf-...). Leave empty to disable tracing.",
    )
    langfuse_base_url: str = Field(
        default="https://cloud.langfuse.com",
        description="Langfuse host URL. Override for self-hosted instances.",
    )

    @property
    def langfuse_enabled(self) -> bool:
        """True when both Langfuse keys are configured."""
        return bool(self.langfuse_secret_key and self.langfuse_public_key)

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
    try:
        return Settings()  # type: ignore[call-arg]  # pydantic-settings reads from env vars, not constructor args
    except ValidationError as exc:
        missing_fields = [
            err["loc"][0]
            for err in exc.errors()
            if err.get("type") == "missing" and err.get("loc")
        ]
        missing_env_vars = sorted(
            {str(field_name).upper() for field_name in missing_fields}
        )

        if missing_env_vars:
            missing_list = ", ".join(missing_env_vars)
            message = (
                "Missing required environment variables: "
                f"{missing_list}. "
                "Set these in your deployment environment or backend/.env."
            )
            logger.error(message)
            raise RuntimeError(message) from exc
        raise
