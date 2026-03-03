"""
FastAPI application factory.

This is the entry point for the backend server. It:
1. Creates the FastAPI app
2. Registers all middleware (CORS, rate limiting, auth)
3. Registers all API routes
4. Provides the health check endpoint

Why use an "app factory" (create_app function) instead of creating
the app at module level?

The factory pattern makes testing easier. In tests, we call create_app()
to get a fresh app instance with dependency overrides applied.
If we created the app at module level, those overrides wouldn't work.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

# Set up structured logging.
# Every log message will include the module name (__name__),
# making it easy to find where a log came from.
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Think of this like assembling a car:
    1. Get the chassis (FastAPI)
    2. Install the safety systems (middleware: CORS, rate limiting)
    3. Install the features (API routes: query, explain, etc.)
    4. Start the engine (uvicorn starts it externally)

    Returns:
        A fully configured FastAPI application ready to handle requests.
    """
    settings = get_settings()

    # Disable interactive API docs in production to reduce attack surface.
    # The /docs and /redoc endpoints expose the full API schema, which could
    # help an attacker enumerate endpoints. In development they're invaluable.
    # Set ENVIRONMENT=production in Railway env vars to disable them.
    is_production = settings.environment == "production"
    docs_url = None if is_production else "/docs"
    redoc_url = None if is_production else "/redoc"

    app = FastAPI(
        title="LegacyLens API",
        description=(
            "RAG-powered COBOL code intelligence. "
            "Ask questions about legacy COBOL code in plain English."
        ),
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
    )

    # ── CORS Middleware ──────────────────────────────────────────────────
    # CORS (Cross-Origin Resource Sharing) is a browser security feature.
    # By default, browsers block requests from different domains.
    # This middleware tells browsers "it's okay to send requests from our frontend."
    #
    # We ONLY allow our own frontend URL — not * (wildcard) which would
    # allow anyone to call our API from any website.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,   # Allow cookies (needed for auth)
        allow_methods=["GET", "POST"],  # Only methods we actually use
        allow_headers=["Authorization", "Content-Type"],
    )

    # ── API Routes ────────────────────────────────────────────────────────
    # Import and register all route handlers.
    # Each router handles one group of related endpoints.
    # Note: We import here (inside the function) to avoid circular imports.
    from app.api.v1.router import (
        api_router,
    )

    app.include_router(api_router, prefix="/api/v1")

    # ── Health Check ──────────────────────────────────────────────────────
    # A simple endpoint that returns "OK" when the server is running.
    # Used by Railway, Docker, and our CI to verify the server is alive.
    @app.get("/health", tags=["system"])
    async def health_check() -> dict[str, str]:
        """
        Health check endpoint — returns 200 OK if the server is running.

        Called by: Railway deployment health checks, Docker healthcheck,
        and our CI pipeline to verify the server started correctly.
        """
        return {"status": "ok", "service": "legacylens-api"}

    logger.info("LegacyLens API initialized successfully")
    return app


# ── Application Instance ───────────────────────────────────────────────────
# This is what uvicorn imports when starting the server:
#   uvicorn app.main:app --reload
#
# The create_app() call here runs once when the module is imported.
app = create_app()
