"""
Unit tests for app/dependencies.py — the dependency injection providers.

Think of dependency injection like a vending machine:
instead of each function going to buy its own ingredients,
the vending machine (dependency system) hands them out on demand.

These tests verify that:
1. The vending machine creates the right type of item (Pinecone or AsyncOpenAI client)
2. The vending machine is smart enough to reuse the same item (caching)

We patch the Pinecone and AsyncOpenAI constructors so tests run without
making real API connections or requiring real API keys.
"""

from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# get_pinecone_client tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetPineconeClient:
    """Tests for the get_pinecone_client() dependency provider."""

    def setup_method(self) -> None:
        """
        Clear the LRU cache before each test.

        @lru_cache makes functions remember their previous result.
        If we don't clear it, the second test would get the cached result
        from the first test — which could be a mock we didn't intend to share.

        Clearing the cache forces each test to run the function body fresh,
        so lines 48-49 and 67-68 of dependencies.py actually execute.
        """
        from app.config import get_settings
        from app.dependencies import get_openai_client, get_pinecone_client

        get_pinecone_client.cache_clear()
        get_openai_client.cache_clear()
        get_settings.cache_clear()

    @patch("app.dependencies.Pinecone")
    def test_get_pinecone_client_returns_pinecone_instance(
        self, mock_pinecone_class: MagicMock
    ) -> None:
        """
        Calling get_pinecone_client() creates and returns a Pinecone client.

        We patch the Pinecone constructor so no real network connection is made.
        The test verifies that:
        - The constructor is called exactly once
        - The returned object is whatever Pinecone() produces

        This covers lines 48-49 in app/dependencies.py.
        """
        from app.dependencies import get_pinecone_client

        # Call the function directly — not through a dependency override
        client = get_pinecone_client()

        # The Pinecone constructor should have been called once
        mock_pinecone_class.assert_called_once()

        # The returned value is the mock instance Pinecone() produced
        assert client is mock_pinecone_class.return_value

    @patch("app.dependencies.Pinecone")
    def test_get_pinecone_client_passes_api_key(
        self, mock_pinecone_class: MagicMock
    ) -> None:
        """
        get_pinecone_client() passes the API key from settings to Pinecone().

        The API key comes from the PINECONE_API_KEY environment variable
        (set to a fake value in conftest.py for unit tests).
        We verify the right key was forwarded to the constructor.
        """
        from app.dependencies import get_pinecone_client

        get_pinecone_client()

        # Verify the api_key was passed as a keyword argument
        call_kwargs = mock_pinecone_class.call_args.kwargs
        assert "api_key" in call_kwargs
        # The fake key set in conftest.py
        assert call_kwargs["api_key"] == "pctest-fake-key-for-unit-tests"

    @patch("app.dependencies.Pinecone")
    def test_get_pinecone_client_cached(self, mock_pinecone_class: MagicMock) -> None:
        """
        Calling get_pinecone_client() twice returns the same object.

        @lru_cache ensures the Pinecone client is created only once,
        no matter how many times the function is called. This is important
        because creating a new Pinecone connection on every request would be
        slow and wasteful.

        This is like a coffee machine that brews once and keeps it warm —
        you don't brew a fresh pot every time someone refills their cup.
        """
        from app.dependencies import get_pinecone_client

        client_first = get_pinecone_client()
        client_second = get_pinecone_client()

        # Same object in memory — only one Pinecone() constructor call
        assert client_first is client_second
        mock_pinecone_class.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# get_openai_client tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetOpenAIClient:
    """Tests for the get_openai_client() dependency provider."""

    def setup_method(self) -> None:
        """Clear LRU caches before each test (same reason as TestGetPineconeClient)."""
        from app.config import get_settings
        from app.dependencies import get_openai_client, get_pinecone_client

        get_pinecone_client.cache_clear()
        get_openai_client.cache_clear()
        get_settings.cache_clear()

    @patch("app.dependencies.AsyncOpenAI")
    def test_get_openai_client_returns_openai_instance(
        self, mock_openai_class: MagicMock
    ) -> None:
        """
        Calling get_openai_client() creates and returns an AsyncOpenAI client.

        AsyncOpenAI is the non-blocking version of the OpenAI client.
        "Async" means it can wait for OpenAI's response without freezing
        the whole server — other users can still make requests while we wait.

        This covers lines 67-68 in app/dependencies.py.
        """
        from app.dependencies import get_openai_client

        client = get_openai_client()

        # The AsyncOpenAI constructor should have been called once
        mock_openai_class.assert_called_once()

        # The returned value is the mock instance AsyncOpenAI() produced
        assert client is mock_openai_class.return_value

    @patch("app.dependencies.AsyncOpenAI")
    def test_get_openai_client_passes_api_key(
        self, mock_openai_class: MagicMock
    ) -> None:
        """
        get_openai_client() passes the API key from settings to AsyncOpenAI().

        The API key comes from the OPENAI_API_KEY environment variable
        (set to a fake value in conftest.py for unit tests).
        """
        from app.dependencies import get_openai_client

        get_openai_client()

        call_kwargs = mock_openai_class.call_args.kwargs
        assert "api_key" in call_kwargs
        # The fake key set in conftest.py
        assert call_kwargs["api_key"] == "sk-test-fake-key-for-unit-tests"

    @patch("app.dependencies.AsyncOpenAI")
    def test_get_openai_client_cached(self, mock_openai_class: MagicMock) -> None:
        """
        Calling get_openai_client() twice returns the same object.

        Same caching logic as get_pinecone_client() — one connection per app lifetime.
        Opening a new connection to OpenAI on every request would add latency
        and waste resources.
        """
        from app.dependencies import get_openai_client

        client_first = get_openai_client()
        client_second = get_openai_client()

        assert client_first is client_second
        mock_openai_class.assert_called_once()
