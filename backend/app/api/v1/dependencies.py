"""
FastAPI dependency functions for the v1 API.

These are "dependencies" in FastAPI's sense — functions that run before
a route handler and provide it with validated, ready-to-use values.

Think of them like security guards:
- get_current_user() checks the Authorization header on every protected endpoint
- If the token is valid, the guard hands the route handler a dict with the user's info
- If the token is invalid or missing, the guard stops the request with a 401 error

Usage in route handlers:
    @router.post("/query")
    async def query(
        request: QueryRequest,
        current_user: dict = Depends(get_current_user),
    ) -> QueryResponse:
        user_id = current_user["sub"]
        ...

The actual token validation logic lives in app/core/auth/jwt_validator.py.
This module is just the FastAPI integration layer.
"""

import logging
from typing import Any

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.config import get_settings
from app.core.auth.jwt_validator import validate_nextauth_token

logger = logging.getLogger(__name__)

# OAuth2PasswordBearer tells FastAPI to look for a Bearer token in the
# Authorization header: "Authorization: Bearer <token>"
# The tokenUrl is not used for actual auth (we use GitHub OAuth, not password flow)
# but is required by the OpenAPI spec for the "Authorize" button to work in /docs.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> dict[str, Any]:
    """
    FastAPI dependency that validates the Bearer token and returns the user payload.

    This function is injected into protected route handlers via Depends().
    FastAPI automatically extracts the Bearer token from the Authorization header
    and passes it to this function.

    If validation succeeds, the route handler receives a dict with the user's
    claims (sub, name, email, etc.). If validation fails, this function raises
    an HTTPException and FastAPI returns 401 — the route handler is never called.

    Args:
        token: JWT Bearer token extracted from the Authorization header by
               OAuth2PasswordBearer. FastAPI handles the extraction automatically.

    Returns:
        Decoded JWT payload dict. Contains at minimum:
        - sub: GitHub user ID

    Raises:
        HTTPException(401): If the token is missing, expired, or invalid.
    """
    settings = get_settings()
    return validate_nextauth_token(token, settings.nextauth_secret)
