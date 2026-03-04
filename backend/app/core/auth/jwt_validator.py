"""
JWT validation for NextAuth.js tokens.

When a user logs in via GitHub OAuth on the frontend, NextAuth creates a
JWT (JSON Web Token) signed with a secret key (NEXTAUTH_SECRET). The frontend
sends this token in every API request via the Authorization header.

This module verifies those tokens on the backend to ensure:
1. The token was signed by our frontend (not a fake/forged token)
2. The token hasn't expired (users must re-authenticate periodically)
3. The token has the required claims (sub = user ID must be present)

Think of this like a bouncer at a club:
- The club issues wristbands (JWT tokens) when you show your ID (GitHub OAuth)
- Every time you want to enter (API request), the bouncer checks the wristband
- Fake wristbands (wrong secret) are rejected
- Expired wristbands are rejected
- Valid wristbands get you in (API processes your request)

This is used as a FastAPI dependency — see app/api/v1/dependencies.py.
"""

import logging
from typing import Any

from fastapi import HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt

logger = logging.getLogger(__name__)

# JWT algorithm used by NextAuth.js default configuration.
# HS256 = HMAC with SHA-256 — a symmetric algorithm (same secret to sign + verify).
_ALGORITHM = "HS256"


def validate_nextauth_token(token: str, secret: str) -> dict[str, Any]:
    """
    Validate a JWT token issued by NextAuth.js and return its decoded payload.

    Performs three checks:
    1. Signature is valid (token was signed with our NEXTAUTH_SECRET)
    2. Token is not expired (the 'exp' claim is in the future)
    3. Required claim 'sub' (user ID) is present

    Args:
        token:  The JWT string from the Authorization header (without "Bearer " prefix).
        secret: The NEXTAUTH_SECRET from app settings. Must match what NextAuth
                used to sign.

    Returns:
        Decoded JWT payload as a plain dict. Contains at minimum:
        - sub: GitHub user ID (e.g., "github-12345")
        - exp: expiry timestamp
        - iat: issued-at timestamp
        - May also contain: name, email, image (from GitHub profile)

    Raises:
        HTTPException(401): If the token is expired, has an invalid signature,
                            is malformed, or is missing required claims.
                            The 401 status tells the frontend to redirect to login.

    Example:
        payload = validate_nextauth_token(token_string, settings.nextauth_secret)
        user_id = payload["sub"]  # "github-12345"
    """
    if not token:
        logger.warning("JWT validation failed: empty token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # jose.jwt.decode() verifies the signature AND the expiry ('exp' claim).
        # It raises JWTError for invalid signatures and ExpiredSignatureError for
        # expired tokens. We require 'exp' to be present via options below.
        payload: dict[str, Any] = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            options={
                "require_exp": True,  # Token must have an expiry claim
                "verify_exp": True,  # Actually check that it hasn't expired
            },
        )
    except ExpiredSignatureError as exc:
        logger.warning("JWT validation failed: token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except JWTError as exc:
        # JWTError covers: invalid signature, malformed token, wrong algorithm, etc.
        logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Require 'sub' (subject = user ID) — this is the GitHub user ID.
    # Without it we can't identify who made the request.
    if "sub" not in payload or not payload["sub"]:
        logger.warning("JWT validation failed: missing 'sub' claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user identifier",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug("JWT validated successfully for user: %s", payload.get("sub"))
    return payload
