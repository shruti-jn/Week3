"""
Answer generator -- streams GPT-4o-mini responses for COBOL code questions.

This module is the final step in the RAG pipeline:
    user query
      -> [embedder]       convert query to a vector
      -> [pinecone_client] find the most similar COBOL chunks
      -> [reranker]       filter out low-confidence matches
      -> [answer_generator] build a prompt and stream a response  <-- this module

Think of it like a research assistant who has already pulled the relevant
textbook pages (the snippets). The assistant reads those pages, then writes
an answer to your question, citing each page as they go.

Public API:
    generate_answer()  -- async generator that yields string tokens (for SSE)
    collect_answer()   -- convenience wrapper that collects the full response
    _build_messages()  -- exposed for testing; builds the OpenAI message list
    _format_snippets() -- exposed for testing; formats snippets as context block
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, cast

from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletionChunk

from app.models.responses import CodeSnippet

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Architecture decision: GPT-4o-mini is 15x cheaper than GPT-4o.
# Citation enforcement and code explanation quality are equivalent for our use case.
ANSWER_MODEL: str = "gpt-4o-mini"

# Returned (as a single yielded token) when no relevant snippets were found.
# We yield rather than raise so the caller (SSE endpoint) can stream it
# to the browser just like any other response.
NO_CONTEXT_RESPONSE: str = (
    "I could not find any relevant COBOL code to answer your question. "
    "Try rephrasing or asking about a specific paragraph or file."
)

# System prompt that tells GPT-4o-mini its role and output rules.
# Kept as a module-level constant so tests can inspect it without calling the LLM.
_SYSTEM_PROMPT: str = """You are LegacyLens, an expert COBOL code analyst. \
You help developers understand legacy COBOL codebases by answering plain-English \
questions using only the code snippets provided.

Rules:
- Always cite the source file and line numbers for every claim you make. \
Use this format: [file_path:start_line-end_line]
- If the provided snippets do not contain enough information to answer the \
question, say so honestly rather than guessing.
- Use plain English. The user may not be a COBOL expert — explain concepts \
with analogies when helpful.
- Quote the relevant COBOL code when it helps clarify your explanation.
- Keep your answer concise and focused on the question asked."""


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _format_snippets(snippets: list[CodeSnippet]) -> str:
    """
    Format a list of retrieved COBOL snippets into a readable context block.

    This is like a bibliography section at the end of a research paper —
    it lists each source with its location and the relevant text, so the
    LLM knows exactly where each piece of code comes from.

    Output format for two snippets:
        [1] File: programs/loan-calc.cob, Lines 14-22
        ```
        CALCULATE-INTEREST.
            COMPUTE INTEREST = PRINCIPAL * RATE / 100.
        ```

        [2] File: programs/payroll.cob, Lines 45-58
        ```
        COMPUTE-TAX.
            MULTIPLY GROSS-PAY BY TAX-RATE GIVING TAX-AMOUNT.
        ```

    Args:
        snippets: List of CodeSnippet objects from the retrieval pipeline.
                  May be empty (returns "" so the caller can skip context).

    Returns:
        A multi-line string with all snippets numbered and formatted.
        Empty string if snippets is empty.
    """
    if not snippets:
        return ""

    parts: list[str] = []
    for i, snippet in enumerate(snippets, start=1):
        header = (
            f"[{i}] File: {snippet.file_path}, "
            f"Lines {snippet.start_line}-{snippet.end_line}"
        )
        block = f"{header}\n```\n{snippet.content}\n```"
        parts.append(block)

    return "\n\n".join(parts)


def _build_messages(
    query: str,
    snippets: list[CodeSnippet],
) -> list[dict[str, str]]:
    """
    Build the OpenAI chat messages list for a COBOL Q&A request.

    The message list always has exactly two entries:
    1. system: explains the AI's role and citation rules
    2. user: the developer's question + all the retrieved COBOL snippets

    This two-message structure is the standard RAG prompt pattern:
    give the model its instructions once (system), then present both
    the question and the context together (user) so it has everything
    it needs to respond.

    Args:
        query:    The developer's plain-English question.
        snippets: Retrieved COBOL code chunks to use as context.
                  Can be empty (context section is omitted from user message).

    Returns:
        List of {"role": ..., "content": ...} dicts ready for the OpenAI SDK.
    """
    context_block = _format_snippets(snippets)

    if context_block:
        user_content = f"Question: {query}\n\nCode context:\n{context_block}"
    else:
        # No snippets — let the model say it can't answer (guarded by
        # the empty-snippets short-circuit in generate_answer before we get here)
        user_content = f"Question: {query}"

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def generate_answer(
    query: str,
    snippets: list[CodeSnippet],
    openai_client: AsyncOpenAI,
) -> AsyncGenerator[str, None]:
    """
    Stream a GPT-4o-mini answer to a COBOL question using retrieved snippets.

    This is an async generator — each time the LLM sends a token, we yield
    it immediately so the frontend can display it progressively (like a
    typewriter effect). This is called Server-Sent Events (SSE) streaming.

    If no snippets were found, we skip the LLM entirely and yield a single
    fallback message. This saves API cost and avoids hallucinated answers.

    Pipeline position:
        reranker output (snippets) -> [generate_answer] -> SSE stream -> browser

    Args:
        query:         The developer's plain-English question.
        snippets:      COBOL code chunks retrieved and filtered by the reranker.
                       Pass an empty list if retrieval found nothing relevant.
        openai_client: Async OpenAI client (real or mock for tests).

    Yields:
        String tokens as they arrive from GPT-4o-mini. None content chunks
        from the OpenAI stream are silently skipped.

    Raises:
        openai.APIError: If the streaming call fails (caller should catch and
                         return HTTP 503).
        openai.RateLimitError: If the API is rate-limited.
    """
    # Short-circuit: no code found means we cannot give a grounded answer.
    # Yield the fallback message and stop — no LLM call needed.
    if not snippets:
        logger.info(
            "generate_answer: no snippets provided — returning fallback message"
        )
        yield NO_CONTEXT_RESPONSE
        return

    messages = _build_messages(query, snippets)

    logger.debug(
        "generate_answer: calling %s with %d snippet(s) for query of %d chars",
        ANSWER_MODEL,
        len(snippets),
        len(query),
    )

    # create(..., stream=True) returns AsyncStream[ChatCompletionChunk] — directly
    # async-iterable; each chunk has choices[0].delta.content (str | None).
    # We use `create` (not `.stream()`) because `.stream()` yields high-level
    # event objects (ContentDeltaEvent, etc.) rather than raw ChatCompletionChunks.
    # cast() is needed because mypy cannot resolve the create() overload when
    # stream=True is typed as bool (not Literal[True]) — it widens the return to
    # ChatCompletion | AsyncStream[ChatCompletionChunk]. We know it's AsyncStream.
    stream = cast(
        AsyncStream[ChatCompletionChunk],
        await openai_client.chat.completions.create(
            model=ANSWER_MODEL,
            messages=messages,  # type: ignore[arg-type]  # TypedDict vs dict[str, str]
            temperature=0.1,  # Low temperature: factual, citation-focused answers
            max_tokens=300,  # Cap answer length — prevents 10s+ responses (target < 3s)
            stream=True,
        ),
    )

    token_count = 0
    async for chunk in stream:
        content: str | None = chunk.choices[0].delta.content
        if content is not None:
            token_count += 1
            yield content

    logger.info(
        "generate_answer: streamed %d tokens for query: %.60s...",
        token_count,
        query,
    )


async def collect_answer(
    query: str,
    snippets: list[CodeSnippet],
    openai_client: AsyncOpenAI,
) -> str:
    """
    Collect the full GPT-4o-mini answer into a single string.

    This is a convenience wrapper around generate_answer() for callers
    that need the complete response at once rather than a streaming generator.
    Use generate_answer() directly for SSE endpoints; use this for:
    - Non-streaming API responses
    - Tests that want to assert on the full answer text
    - Logging or evaluation pipelines

    Args:
        query:         The developer's plain-English question.
        snippets:      Retrieved COBOL code chunks from the reranker.
        openai_client: Async OpenAI client (real or mock for tests).

    Returns:
        The complete LLM response as one string. Returns NO_CONTEXT_RESPONSE
        if snippets is empty (no LLM call is made).
    """
    parts: list[str] = []
    async for token in generate_answer(query, snippets, openai_client):
        parts.append(token)
    return "".join(parts)
