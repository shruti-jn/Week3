"""
Unit tests for the JWT validator module.

The JWT validator ensures that API requests come from authenticated users.
It verifies tokens issued by NextAuth.js (our frontend auth library).

How JWT auth works in LegacyLens:
1. User logs in via GitHub OAuth on the frontend
2. NextAuth creates a JWT signed with NEXTAUTH_SECRET
3. Frontend sends this JWT in every API request header
4. Backend verifies the JWT signature and expiry before processing

We test every failure mode because auth bugs can be catastrophic:
- expired tokens must be rejected (not just accepted)
- wrong secrets must be rejected (can't trust a token you didn't sign)
- malformed tokens must be rejected gracefully (not crash with 500)
"""

import time
from typing import Any

import pytest
from fastapi import HTTPException
from jose import jwt

from app.core.auth.jwt_validator import validate_nextauth_token

# The secret used to sign test tokens.
# In production this comes from settings.nextauth_secret
TEST_SECRET = "test-nextauth-secret-32chars-long!!"
ALGORITHM = "HS256"


def make_token(
    payload: dict[str, Any],
    secret: str = TEST_SECRET,
    algorithm: str = ALGORITHM,
) -> str:
    """
    Helper: create a signed JWT for testing.

    Args:
        payload:   Claims to include in the token.
        secret:    Secret to sign the token with.
        algorithm: JWT algorithm (default HS256).

    Returns:
        A signed JWT string.
    """
    return jwt.encode(payload, secret, algorithm=algorithm)


# ─────────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────────


def test_valid_token_returns_payload() -> None:
    """A valid, non-expired token returns the decoded payload."""
    payload = {
        "sub": "user-123",
        "name": "Test User",
        "email": "test@example.com",
        "exp": int(time.time()) + 3600,  # 1 hour from now
        "iat": int(time.time()),
    }
    token = make_token(payload)

    result = validate_nextauth_token(token, TEST_SECRET)

    assert result["sub"] == "user-123"
    assert result["email"] == "test@example.com"


def test_valid_token_with_github_data() -> None:
    """Token with GitHub-specific claims (as NextAuth would produce) is accepted."""
    payload = {
        "sub": "github-user-98765",
        "name": "Jane Developer",
        "email": "jane@github.com",
        "image": "https://avatars.githubusercontent.com/u/98765",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    token = make_token(payload)

    result = validate_nextauth_token(token, TEST_SECRET)

    assert result["name"] == "Jane Developer"


# ─────────────────────────────────────────────────────────────────────────────
# Expired tokens
# ─────────────────────────────────────────────────────────────────────────────


def test_expired_token_raises_401() -> None:
    """An expired token must raise HTTPException with 401 status."""
    payload = {
        "sub": "user-123",
        "exp": int(time.time()) - 60,  # expired 1 minute ago
        "iat": int(time.time()) - 120,
    }
    token = make_token(payload)

    with pytest.raises(HTTPException) as exc_info:
        validate_nextauth_token(token, TEST_SECRET)

    assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Wrong secret
# ─────────────────────────────────────────────────────────────────────────────


def test_wrong_secret_raises_401() -> None:
    """A token signed with a different secret must raise HTTPException 401."""
    payload = {
        "sub": "user-123",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    token = make_token(payload, secret="WRONG-SECRET-that-backend-doesnt-know")

    with pytest.raises(HTTPException) as exc_info:
        validate_nextauth_token(token, TEST_SECRET)

    assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Malformed tokens
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_string_token_raises_401() -> None:
    """An empty string is not a valid token."""
    with pytest.raises(HTTPException) as exc_info:
        validate_nextauth_token("", TEST_SECRET)
    assert exc_info.value.status_code == 401


def test_garbage_token_raises_401() -> None:
    """Random garbage string is not a valid JWT."""
    with pytest.raises(HTTPException) as exc_info:
        validate_nextauth_token("not.a.real.jwt.token.at.all", TEST_SECRET)
    assert exc_info.value.status_code == 401


def test_missing_dots_raises_401() -> None:
    """A string without the two JWT dots (header.payload.signature) is rejected."""
    with pytest.raises(HTTPException) as exc_info:
        validate_nextauth_token("justaplainstring", TEST_SECRET)
    assert exc_info.value.status_code == 401


def test_truncated_token_raises_401() -> None:
    """A token with only two parts (missing signature) is rejected."""
    payload = {"sub": "user", "exp": int(time.time()) + 3600}
    full_token = make_token(payload)
    # Remove the signature part
    truncated = ".".join(full_token.split(".")[:2])

    with pytest.raises(HTTPException) as exc_info:
        validate_nextauth_token(truncated, TEST_SECRET)
    assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Missing required claims
# ─────────────────────────────────────────────────────────────────────────────


def test_token_without_exp_raises_401() -> None:
    """A token without the 'exp' (expiry) claim must be rejected."""
    # No exp field — can't verify it hasn't expired
    payload = {"sub": "user-123", "iat": int(time.time())}
    token = make_token(payload)

    with pytest.raises(HTTPException) as exc_info:
        validate_nextauth_token(token, TEST_SECRET)
    assert exc_info.value.status_code == 401


def test_token_without_sub_raises_401() -> None:
    """A token without the 'sub' (subject/user ID) claim must be rejected."""
    payload = {
        "email": "user@example.com",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    token = make_token(payload)

    with pytest.raises(HTTPException) as exc_info:
        validate_nextauth_token(token, TEST_SECRET)
    assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Token payload is returned correctly
# ─────────────────────────────────────────────────────────────────────────────


def test_returns_dict_not_model(  ) -> None:
    """validate_nextauth_token returns a plain dict, not a model or object."""
    payload = {
        "sub": "user-123",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    token = make_token(payload)
    result = validate_nextauth_token(token, TEST_SECRET)
    assert isinstance(result, dict)


def test_returned_payload_has_sub() -> None:
    """The returned payload must contain the 'sub' (user ID) field."""
    payload = {
        "sub": "github-12345",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    token = make_token(payload)
    result = validate_nextauth_token(token, TEST_SECRET)
    assert "sub" in result
    assert result["sub"] == "github-12345"


# ─────────────────────────────────────────────────────────────────────────────
# Token just about to expire (boundary)
# ─────────────────────────────────────────────────────────────────────────────


def test_token_expiring_in_one_second_is_valid() -> None:
    """A token expiring 1 second in the future is still valid."""
    payload = {
        "sub": "user-boundary",
        "exp": int(time.time()) + 1,
        "iat": int(time.time()),
    }
    token = make_token(payload)
    # Should not raise
    result = validate_nextauth_token(token, TEST_SECRET)
    assert result["sub"] == "user-boundary"
