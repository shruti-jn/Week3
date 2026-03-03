"""
Unit tests for app/core/generation/answer_generator.py.

These tests verify that the answer generator:
1. Yields streaming tokens from GPT-4o-mini for normal queries
2. Short-circuits with a fallback message when no snippets are found
3. Skips None delta content chunks (OpenAI sends these at stream end)
4. Builds prompt messages that include citations and context
5. Propagates API errors so callers can handle them
6. collect_answer() assembles the full text from the stream

All OpenAI calls are mocked — no real API calls, no money spent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.generation.answer_generator import (
    NO_CONTEXT_RESPONSE,
    _build_messages,
    _format_snippets,
    collect_answer,
    generate_answer,
)
from app.models.responses import CodeSnippet

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def snippet_one() -> CodeSnippet:
    """A single COBOL snippet representing a loan-interest paragraph."""
    return CodeSnippet(
        file_path="programs/loan-calc.cob",
        start_line=14,
        end_line=22,
        content="CALCULATE-INTEREST.\n    COMPUTE INTEREST = PRINCIPAL * RATE / 100.",
        score=0.92,
    )


@pytest.fixture
def snippet_two() -> CodeSnippet:
    """A second COBOL snippet representing a payroll-tax paragraph."""
    return CodeSnippet(
        file_path="programs/payroll.cob",
        start_line=45,
        end_line=58,
        content="COMPUTE-TAX.\n    MULTIPLY GROSS-PAY BY TAX-RATE GIVING TAX-AMOUNT.",
        score=0.81,
    )


@pytest.fixture
def two_snippets(
    snippet_one: CodeSnippet, snippet_two: CodeSnippet
) -> list[CodeSnippet]:
    """Two snippets — the typical case when retrieval finds good results."""
    return [snippet_one, snippet_two]


def _make_streaming_client(words: list[str | None]) -> AsyncMock:
    """
    Build a minimal mock OpenAI client whose stream yields the given words.

    Each word becomes a streaming chunk with choices[0].delta.content set
    to that word. None entries simulate end-of-stream chunks where
    delta.content is None (which the real OpenAI SDK sends occasionally).

    We use a concrete _FakeStream class rather than a MagicMock with
    __aiter__ overridden, because MagicMock passes `self` when calling
    magic methods through its wrapper, which breaks zero-argument async
    generator functions.

    Args:
        words: Tokens to stream. Use None to simulate empty delta chunks.

    Returns:
        An AsyncMock that can be passed to generate_answer / collect_answer.
    """

    class _FakeStream:
        """
        Minimal async iterable that yields pre-canned ChatCompletionChunk-like mocks.

        The real OpenAI SDK's chat.completions.create(stream=True) returns an
        AsyncStream[ChatCompletionChunk] — directly async-iterable, no context
        manager needed. This class mimics that interface.
        """

        def __aiter__(self):  # type: ignore[override]
            return self._gen()

        async def _gen(self):  # type: ignore[return]
            for word in words:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = word
                yield chunk

    client = AsyncMock()
    # create is awaited in the implementation, so AsyncMock is correct here.
    client.chat.completions.create = AsyncMock(return_value=_FakeStream())
    return client


# ─────────────────────────────────────────────────────────────────────────────
# generate_answer — happy path
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_answer_yields_tokens(two_snippets: list[CodeSnippet]) -> None:
    """
    Happy path: generate_answer yields each non-None token from the stream.

    The mock streams ["How", " does", " COBOL", " work?"]. We expect those
    four tokens to be yielded in order.
    """
    client = _make_streaming_client(["How", " does", " COBOL", " work?"])
    tokens = []
    async for token in generate_answer("How does COBOL work?", two_snippets, client):
        tokens.append(token)

    assert tokens == ["How", " does", " COBOL", " work?"]


@pytest.mark.asyncio
async def test_generate_answer_calls_stream_once(
    two_snippets: list[CodeSnippet],
) -> None:
    """
    The implementation must call openai_client.chat.completions.create exactly
    once per generate_answer invocation (not once per yielded token).
    """
    client = _make_streaming_client(["ok"])
    async for _ in generate_answer("test query", two_snippets, client):
        pass

    client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_answer_single_snippet(snippet_one: CodeSnippet) -> None:
    """Works correctly with exactly one snippet (the minimum useful case)."""
    client = _make_streaming_client(["answer"])
    tokens = []
    async for token in generate_answer("query", [snippet_one], client):
        tokens.append(token)

    assert tokens == ["answer"]


# ─────────────────────────────────────────────────────────────────────────────
# generate_answer — empty snippets (no retrieval results)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_answer_empty_snippets_returns_fallback() -> None:
    """
    When no snippets are found, generate_answer yields the NO_CONTEXT_RESPONSE
    constant immediately, without calling OpenAI at all.

    We verify this by passing a client whose stream raises — if the client is
    called, the test would fail with an exception.
    """
    client = AsyncMock()
    client.chat.completions.create.side_effect = RuntimeError("should not be called")

    tokens = []
    async for token in generate_answer("anything", [], client):
        tokens.append(token)

    full_text = "".join(tokens)
    assert full_text == NO_CONTEXT_RESPONSE
    client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_generate_answer_empty_snippets_yields_non_empty_message() -> None:
    """The fallback message must be non-empty and mention inability to find context."""
    client = AsyncMock()
    tokens = []
    async for token in generate_answer("irrelevant", [], client):
        tokens.append(token)

    combined = "".join(tokens)
    assert len(combined) > 10
    assert NO_CONTEXT_RESPONSE  # constant itself is non-empty


# ─────────────────────────────────────────────────────────────────────────────
# generate_answer — None delta.content filtering
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_answer_skips_none_content(snippet_one: CodeSnippet) -> None:
    """
    OpenAI's streaming API sometimes sends chunks where delta.content is None
    (for the role chunk at the start and the stop chunk at the end).

    generate_answer must silently skip those — they should not appear in output.
    """
    client = _make_streaming_client(["hello", None, " world", None])
    tokens = []
    async for token in generate_answer("query", [snippet_one], client):
        tokens.append(token)

    assert tokens == ["hello", " world"]
    assert None not in tokens


@pytest.mark.asyncio
async def test_generate_answer_all_none_content_yields_nothing(
    snippet_one: CodeSnippet,
) -> None:
    """
    Edge case: if every chunk has delta.content=None, no tokens are yielded
    (not even an empty string).
    """
    client = _make_streaming_client([None, None, None])
    tokens = []
    async for token in generate_answer("query", [snippet_one], client):
        tokens.append(token)

    assert tokens == []


# ─────────────────────────────────────────────────────────────────────────────
# generate_answer — prompt content verification
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_answer_stream_called_with_correct_model(
    two_snippets: list[CodeSnippet],
) -> None:
    """The stream must be invoked with model='gpt-4o-mini' — our cost/latency target."""
    client = _make_streaming_client(["ok"])
    async for _ in generate_answer("query", two_snippets, client):
        pass

    call_kwargs = client.chat.completions.create.call_args
    assert call_kwargs.kwargs.get("model") == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_generate_answer_messages_contain_query(
    snippet_one: CodeSnippet,
) -> None:
    """The user's query must appear somewhere in the messages sent to OpenAI."""
    client = _make_streaming_client(["ok"])
    query = "How is tax calculated?"
    async for _ in generate_answer(query, [snippet_one], client):
        pass

    call_kwargs = client.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages", [])
    all_content = " ".join(m["content"] for m in messages if m.get("content"))
    assert query in all_content


@pytest.mark.asyncio
async def test_generate_answer_messages_contain_file_paths(
    two_snippets: list[CodeSnippet],
) -> None:
    """File paths from the retrieved snippets must appear in the prompt context."""
    client = _make_streaming_client(["ok"])
    async for _ in generate_answer("query", two_snippets, client):
        pass

    call_kwargs = client.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages", [])
    all_content = " ".join(m["content"] for m in messages if m.get("content"))
    assert "programs/loan-calc.cob" in all_content
    assert "programs/payroll.cob" in all_content


@pytest.mark.asyncio
async def test_generate_answer_messages_contain_line_numbers(
    snippet_one: CodeSnippet,
) -> None:
    """Line numbers must be in the context so the LLM can produce citations."""
    client = _make_streaming_client(["ok"])
    async for _ in generate_answer("query", [snippet_one], client):
        pass

    call_kwargs = client.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages", [])
    all_content = " ".join(m["content"] for m in messages if m.get("content"))
    assert "14" in all_content  # start_line
    assert "22" in all_content  # end_line


@pytest.mark.asyncio
async def test_generate_answer_messages_contain_snippet_content(
    snippet_one: CodeSnippet,
) -> None:
    """The raw COBOL code from the snippet must be included in the prompt."""
    client = _make_streaming_client(["ok"])
    async for _ in generate_answer("query", [snippet_one], client):
        pass

    call_kwargs = client.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages", [])
    all_content = " ".join(m["content"] for m in messages if m.get("content"))
    assert "COMPUTE INTEREST = PRINCIPAL * RATE / 100." in all_content


@pytest.mark.asyncio
async def test_generate_answer_system_message_present(
    snippet_one: CodeSnippet,
) -> None:
    """A system-role message must be the first message sent to the model."""
    client = _make_streaming_client(["ok"])
    async for _ in generate_answer("query", [snippet_one], client):
        pass

    call_kwargs = client.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages", [])
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 20


# ─────────────────────────────────────────────────────────────────────────────
# generate_answer — error propagation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_answer_propagates_api_error(snippet_one: CodeSnippet) -> None:
    """
    If the OpenAI streaming call raises, the exception must propagate out of
    generate_answer so the caller (the API endpoint) can catch it and return
    an appropriate HTTP 503.

    We use AsyncMock with side_effect so the exception is raised when the
    coroutine is awaited — matching the real SDK behavior for create().
    """
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("OpenAI unreachable")
    )

    with pytest.raises(RuntimeError, match="OpenAI unreachable"):
        async for _ in generate_answer("query", [snippet_one], client):
            pass


# ─────────────────────────────────────────────────────────────────────────────
# collect_answer
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_collect_answer_joins_all_tokens(two_snippets: list[CodeSnippet]) -> None:
    """
    collect_answer must concatenate every yielded token into one string —
    like joining puzzle pieces into a complete picture.
    """
    client = _make_streaming_client(["The", " interest", " is", " computed", "."])
    result = await collect_answer("How is interest computed?", two_snippets, client)
    assert result == "The interest is computed."


@pytest.mark.asyncio
async def test_collect_answer_empty_snippets_returns_fallback() -> None:
    """
    collect_answer with no snippets returns the NO_CONTEXT_RESPONSE constant.
    No OpenAI call is made.
    """
    client = AsyncMock()
    client.chat.completions.create.side_effect = RuntimeError("should not be called")

    result = await collect_answer("anything", [], client)
    assert result == NO_CONTEXT_RESPONSE


@pytest.mark.asyncio
async def test_collect_answer_skips_none_tokens(snippet_one: CodeSnippet) -> None:
    """collect_answer must not include None tokens in the concatenated result."""
    client = _make_streaming_client(["hello", None, " world"])
    result = await collect_answer("query", [snippet_one], client)
    assert result == "hello world"


# ─────────────────────────────────────────────────────────────────────────────
# _format_snippets — internal helper
# ─────────────────────────────────────────────────────────────────────────────


def test_format_snippets_empty_returns_empty_string() -> None:
    """Formatting an empty list returns an empty string (no context block)."""
    result = _format_snippets([])
    assert result == ""


def test_format_snippets_includes_file_path(snippet_one: CodeSnippet) -> None:
    """The formatted context must include the snippet's file path."""
    result = _format_snippets([snippet_one])
    assert "programs/loan-calc.cob" in result


def test_format_snippets_includes_line_numbers(snippet_one: CodeSnippet) -> None:
    """The formatted context must include start and end line numbers."""
    result = _format_snippets([snippet_one])
    assert "14" in result
    assert "22" in result


def test_format_snippets_includes_code_content(snippet_one: CodeSnippet) -> None:
    """The raw COBOL code must appear in the formatted context block."""
    result = _format_snippets([snippet_one])
    assert "COMPUTE INTEREST = PRINCIPAL * RATE / 100." in result


def test_format_snippets_numbers_each_snippet(
    snippet_one: CodeSnippet, snippet_two: CodeSnippet
) -> None:
    """Multiple snippets should be numbered so the LLM can reference them."""
    result = _format_snippets([snippet_one, snippet_two])
    assert "[1]" in result
    assert "[2]" in result


def test_format_snippets_includes_all_file_paths(
    snippet_one: CodeSnippet, snippet_two: CodeSnippet
) -> None:
    """All snippets' file paths must appear when multiple are formatted."""
    result = _format_snippets([snippet_one, snippet_two])
    assert "programs/loan-calc.cob" in result
    assert "programs/payroll.cob" in result


# ─────────────────────────────────────────────────────────────────────────────
# _build_messages — internal helper
# ─────────────────────────────────────────────────────────────────────────────


def test_build_messages_returns_two_messages(snippet_one: CodeSnippet) -> None:
    """Messages list must have exactly 2 items: system + user."""
    messages = _build_messages("query", [snippet_one])
    assert len(messages) == 2


def test_build_messages_first_is_system(snippet_one: CodeSnippet) -> None:
    """The first message must have role='system'."""
    messages = _build_messages("query", [snippet_one])
    assert messages[0]["role"] == "system"


def test_build_messages_second_is_user(snippet_one: CodeSnippet) -> None:
    """The second message must have role='user'."""
    messages = _build_messages("query", [snippet_one])
    assert messages[1]["role"] == "user"


def test_build_messages_user_contains_query(snippet_one: CodeSnippet) -> None:
    """The user message must contain the caller's query verbatim."""
    query = "What does CALCULATE-INTEREST do?"
    messages = _build_messages(query, [snippet_one])
    assert query in messages[1]["content"]


def test_build_messages_system_mentions_citations(snippet_one: CodeSnippet) -> None:
    """
    The system prompt must instruct the model to cite sources.
    We check for 'cite' or 'citation' in the system message content.
    """
    messages = _build_messages("query", [snippet_one])
    system_content = messages[0]["content"].lower()
    assert "cite" in system_content or "citation" in system_content


def test_build_messages_user_contains_snippet_content(snippet_one: CodeSnippet) -> None:
    """The user message must include the formatted snippet content."""
    messages = _build_messages("query", [snippet_one])
    assert "COMPUTE INTEREST = PRINCIPAL * RATE / 100." in messages[1]["content"]
