"""
Unit tests for the wired /api/v1/query SSE pipeline.

These tests verify the full RAG pipeline end-to-end inside a single HTTP call:
    embed → retrieve → rerank → stream snippets → stream answer tokens → done

All external services (OpenAI, Pinecone) are mocked — no real API calls are made.

SSE response format expected:
    event: snippets\ndata: <JSON array>\n\n
    event: token\ndata: <token_text>\n\n  (one per LLM token)
    event: done\ndata: {
        "query_time_ms": N,
        "embed_ms": N, "retrieve_ms": N, "rerank_ms": N, "llm_ms": N,
        "chunks_count": N, "top_score": N, "avg_similarity": N, "files_hit": N
    }\n\n

On pipeline error:
    event: error\ndata: {"message": "..."}\n\n

The conftest `test_client` fixture is used for the happy-path tests.
Error-path tests build their own app with failure-inducing mocks.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def parse_sse_events(body: str) -> list[dict[str, str]]:
    """
    Parse a raw SSE response body into a list of event dicts.

    Each SSE event block is separated by a blank line. Each block has
    lines like "event: snippets" and "data: [...]".

    Returns a list of dicts with keys "event" and "data".
    Empty blocks (heartbeats) are skipped.

    Example:
        body = "event: token\\ndata: Hello\\n\\nevent: done\\ndata: {}\\n\\n"
        parse_sse_events(body)
        # [{"event": "token", "data": "Hello"}, {"event": "done", "data": "{}"}]
    """
    events: list[dict[str, str]] = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        ev: dict[str, str] = {}
        for line in block.split("\n"):
            if line.startswith("event:"):
                ev["event"] = line[len("event:"):].strip()
            elif line.startswith("data:"):
                ev["data"] = line[len("data:"):].strip()
        if ev:
            events.append(ev)
    return events


def _make_app_with_overrides(
    voyage_override: Any,
    openai_override: Any,
    pinecone_override: Any,
) -> Any:
    """
    Build a fresh FastAPI app with the given dependency overrides.

    Used by error-path tests that need broken mocks (raising exceptions).
    Clears the lru_cache before each call so Settings re-reads env vars.
    """
    from app.api.v1.dependencies import get_current_user
    from app.config import get_settings
    from app.dependencies import get_openai_client, get_pinecone_client, get_voyage_client
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_voyage_client] = lambda: voyage_override
    app.dependency_overrides[get_openai_client] = lambda: openai_override
    app.dependency_overrides[get_pinecone_client] = lambda: pinecone_override
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user-123",
        "email": "test@example.com",
    }
    return app


async def _collect_response(
    test_client: AsyncClient,
    query: str = "How is interest calculated?",
    top_k: int = 5,
) -> tuple[int, str, str]:
    """
    POST /api/v1/query and return (status_code, content_type, body_text).

    The body_text contains the raw SSE stream (all events concatenated).
    """
    response = await test_client.post(
        "/api/v1/query",
        json={"query": query, "top_k": top_k},
    )
    return response.status_code, response.headers.get("content-type", ""), response.text


# ─────────────────────────────────────────────────────────────────────────────
# Happy-path tests (uses conftest test_client with standard mocks)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_returns_200_with_sse_content_type(
    test_client: AsyncClient,
) -> None:
    """
    A valid query returns HTTP 200 with text/event-stream content type.

    SSE requires the content-type header to be 'text/event-stream' so that
    browsers and EventSource clients know to read the response as a stream.
    """
    status, content_type, _ = await _collect_response(test_client)
    assert status == 200
    assert "text/event-stream" in content_type


@pytest.mark.asyncio
async def test_query_sse_has_snippets_event(test_client: AsyncClient) -> None:
    """
    The SSE stream contains exactly one 'snippets' event with a JSON array.

    Snippets are sent before answer tokens so the frontend can render the
    source citations immediately while the answer streams in.
    """
    _, _, body = await _collect_response(test_client)
    events = parse_sse_events(body)
    snippet_events = [e for e in events if e.get("event") == "snippets"]
    assert len(snippet_events) == 1, f"Expected 1 snippets event, got: {snippet_events}"
    snippets = json.loads(snippet_events[0]["data"])
    assert isinstance(snippets, list)


@pytest.mark.asyncio
async def test_query_sse_has_token_events(test_client: AsyncClient) -> None:
    """
    The SSE stream contains at least one 'token' event with non-empty text.

    Token events are the LLM's answer arriving word by word (the typewriter
    effect). Our mock generates 6 tokens: "This is a mocked answer."
    """
    _, _, body = await _collect_response(test_client)
    events = parse_sse_events(body)
    token_events = [e for e in events if e.get("event") == "token"]
    assert len(token_events) >= 1, f"Expected >=1 token events, got: {events}"


@pytest.mark.asyncio
async def test_query_sse_has_done_event_with_timing(test_client: AsyncClient) -> None:
    """
    The SSE stream ends with a 'done' event containing query_time_ms.

    The 'done' event signals to the frontend that streaming is finished
    and provides latency information for performance monitoring.
    """
    _, _, body = await _collect_response(test_client)
    events = parse_sse_events(body)
    done_events = [e for e in events if e.get("event") == "done"]
    assert len(done_events) == 1, f"Expected 1 done event, got: {events}"
    done_data = json.loads(done_events[0]["data"])
    assert "query_time_ms" in done_data
    assert done_data["query_time_ms"] >= 0.0


@pytest.mark.asyncio
async def test_query_done_event_has_full_metrics_payload(test_client: AsyncClient) -> None:
    """
    The 'done' event includes all analytics fields, not just query_time_ms.

    These fields power the frontend metrics bar and session query log:
    sub-step timings (embed/retrieve/rerank/llm), chunk count, similarity
    scores, and the number of unique files hit.
    """
    _, _, body = await _collect_response(test_client)
    events = parse_sse_events(body)
    done_events = [e for e in events if e.get("event") == "done"]
    assert len(done_events) == 1
    d = json.loads(done_events[0]["data"])

    required_fields = [
        "query_time_ms",
        "embed_ms",
        "retrieve_ms",
        "rerank_ms",
        "llm_ms",
        "chunks_count",
        "top_score",
        "avg_similarity",
        "files_hit",
    ]
    for field in required_fields:
        assert field in d, f"Missing field '{field}' in done payload: {d}"

    assert d["query_time_ms"] >= 0.0
    assert d["embed_ms"] >= 0.0
    assert d["retrieve_ms"] >= 0.0
    assert d["rerank_ms"] >= 0.0
    assert d["llm_ms"] >= 0.0
    assert isinstance(d["chunks_count"], int) and d["chunks_count"] >= 0
    assert 0.0 <= d["top_score"] <= 1.0
    assert 0.0 <= d["avg_similarity"] <= 1.0
    assert isinstance(d["files_hit"], int) and d["files_hit"] >= 0


@pytest.mark.asyncio
async def test_query_done_metrics_are_consistent_with_snippets(
    test_client: AsyncClient,
) -> None:
    """
    The done payload metrics are consistent with the returned snippets.

    chunks_count must equal the number of snippets in the snippets event.
    files_hit must equal the number of unique file_path values.
    top_score must equal the max snippet score.
    avg_similarity must equal the mean snippet score.
    """
    _, _, body = await _collect_response(test_client)
    events = parse_sse_events(body)

    snippets_data = json.loads(
        next(e["data"] for e in events if e.get("event") == "snippets")
    )
    done_data = json.loads(
        next(e["data"] for e in events if e.get("event") == "done")
    )

    if snippets_data:
        scores = [s["score"] for s in snippets_data]
        assert done_data["chunks_count"] == len(snippets_data)
        assert done_data["files_hit"] == len({s["file_path"] for s in snippets_data})
        assert abs(done_data["top_score"] - max(scores)) < 0.001
        assert abs(done_data["avg_similarity"] - sum(scores) / len(scores)) < 0.001
    else:
        assert done_data["chunks_count"] == 0
        assert done_data["top_score"] == 0.0
        assert done_data["avg_similarity"] == 0.0
        assert done_data["files_hit"] == 0


@pytest.mark.asyncio
async def test_query_snippet_fields_are_correct(test_client: AsyncClient) -> None:
    """
    Each snippet in the 'snippets' event has the required fields.

    The conftest mock_pinecone_client returns two results:
    - loan-calc.cob::CALCULATE-INTEREST (score 0.92)
    - payroll.cob::COMPUTE-TAX (score 0.81)
    Both are above the 0.75 threshold so both should appear.
    """
    _, _, body = await _collect_response(test_client)
    events = parse_sse_events(body)
    snippet_events = [e for e in events if e.get("event") == "snippets"]
    snippets = json.loads(snippet_events[0]["data"])
    assert len(snippets) >= 1
    for snippet in snippets:
        assert "file_path" in snippet
        assert "start_line" in snippet
        assert "end_line" in snippet
        assert "content" in snippet
        assert "score" in snippet
        assert "chunk_type" in snippet, f"Missing chunk_type in snippet: {snippet}"
        assert snippet["start_line"] >= 1
        assert snippet["end_line"] >= snippet["start_line"]
        assert 0.0 <= snippet["score"] <= 1.0
        assert snippet["chunk_type"] in ("paragraph", "fixed"), (
            f"chunk_type must be 'paragraph' or 'fixed', got: {snippet['chunk_type']}"
        )


@pytest.mark.asyncio
async def test_query_event_order_is_snippets_tokens_done(
    test_client: AsyncClient,
) -> None:
    """
    SSE events arrive in the correct order: snippets first, then tokens, then done.

    This order matters for the frontend: snippets appear immediately, then the
    answer streams in, and 'done' signals completion.
    """
    _, _, body = await _collect_response(test_client)
    events = parse_sse_events(body)
    event_types = [e.get("event") for e in events]

    assert event_types[0] == "snippets", f"First event should be snippets, got: {event_types}"
    assert event_types[-1] == "done", f"Last event should be done, got: {event_types}"
    # All middle events should be tokens
    middle = event_types[1:-1]
    assert all(t == "token" for t in middle), f"Middle events should be tokens, got: {middle}"


# ─────────────────────────────────────────────────────────────────────────────
# Empty results path (no COBOL code above the 0.75 threshold)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
async def empty_results_client(
    mock_voyage_client: MagicMock,
    mock_openai_client: AsyncMock,
    mock_pinecone_empty: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Test client where Pinecone returns zero results.

    Used to verify that the "no matching code" path works:
    - snippets event has an empty array
    - answer contains the fallback message (not an LLM call)
    """
    app = _make_app_with_overrides(mock_voyage_client, mock_openai_client, mock_pinecone_empty)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_query_no_results_has_empty_snippets(
    empty_results_client: AsyncClient,
) -> None:
    """
    When Pinecone returns no matching code, the snippets event contains [].

    An empty snippets list signals to the frontend that no source citations
    will be shown — the answer is a graceful fallback, not grounded code.
    """
    _, _, body = await _collect_response(empty_results_client)
    events = parse_sse_events(body)
    snippet_events = [e for e in events if e.get("event") == "snippets"]
    assert len(snippet_events) == 1
    assert json.loads(snippet_events[0]["data"]) == []


@pytest.mark.asyncio
async def test_query_no_results_has_fallback_token(
    empty_results_client: AsyncClient,
) -> None:
    """
    When no code matches, answer tokens contain the NO_CONTEXT_RESPONSE.

    The answer_generator short-circuits when snippets is empty — it yields
    a single token with a human-readable explanation and makes no LLM call.
    This saves API cost and avoids hallucinated answers.
    """
    from app.core.generation.answer_generator import NO_CONTEXT_RESPONSE

    _, _, body = await _collect_response(empty_results_client)
    events = parse_sse_events(body)
    token_events = [e for e in events if e.get("event") == "token"]
    full_answer = "".join(e["data"] for e in token_events)
    # The fallback message should appear somewhere in the concatenated tokens
    assert NO_CONTEXT_RESPONSE in full_answer


@pytest.mark.asyncio
async def test_query_no_results_still_has_done_event(
    empty_results_client: AsyncClient,
) -> None:
    """
    Even with no results, the SSE stream still ends with a done event.

    The frontend always needs the done event to know streaming finished —
    regardless of whether results were found.
    """
    _, _, body = await _collect_response(empty_results_client)
    events = parse_sse_events(body)
    done_events = [e for e in events if e.get("event") == "done"]
    assert len(done_events) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Error paths — pipeline failures yield event: error
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
async def failing_embed_client(
    mock_openai_client: AsyncMock,
    mock_pinecone_client: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Test client where Voyage embedding fails.

    Used to verify that embedding failures are surfaced as SSE error events
    rather than crashing the server or hanging the connection.

    voyageai.Client is synchronous, so the embed method is a regular MagicMock
    with a side_effect that raises immediately. asyncio.to_thread runs it in a
    thread pool — the raised exception propagates back to the async caller.
    """
    broken_voyage = MagicMock()
    broken_voyage.embed = MagicMock(
        side_effect=RuntimeError("Voyage embeddings unavailable")
    )
    app = _make_app_with_overrides(broken_voyage, mock_openai_client, mock_pinecone_client)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_query_embedding_failure_yields_error_event(
    failing_embed_client: AsyncClient,
) -> None:
    """
    When Voyage embedding fails, the stream yields event: error.

    SSE connections are already open when errors occur, so we cannot
    return an HTTP 503. Instead we send an error event and close the stream.
    """
    status, _, body = await _collect_response(failing_embed_client)
    assert status == 200  # SSE connection opened before the error
    events = parse_sse_events(body)
    error_events = [e for e in events if e.get("event") == "error"]
    assert len(error_events) >= 1, f"Expected error event, got: {events}"
    error_data = json.loads(error_events[0]["data"])
    assert "message" in error_data


@pytest.fixture
async def failing_pinecone_client(
    mock_voyage_client: MagicMock,
    mock_openai_client: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Test client where Pinecone.query raises an exception.

    Used to verify that retrieval failures are surfaced as SSE error events.
    The embedder (Voyage) succeeds; only the Pinecone step fails.
    """
    broken_pinecone = MagicMock()
    broken_index = MagicMock()

    def mock_failing_query(**kwargs: object) -> None:
        raise RuntimeError("Pinecone service unavailable")

    broken_index.query = mock_failing_query
    broken_pinecone.Index = MagicMock(return_value=broken_index)

    app = _make_app_with_overrides(mock_voyage_client, mock_openai_client, broken_pinecone)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_query_pinecone_failure_yields_error_event(
    failing_pinecone_client: AsyncClient,
) -> None:
    """
    When Pinecone query fails (after retries), the stream yields event: error.

    The Pinecone wrapper retries internally up to 3 times before raising.
    Once raised, the pipeline generator catches it and yields an error event.
    """
    status, _, body = await _collect_response(failing_pinecone_client)
    assert status == 200  # SSE connection opened before the error
    events = parse_sse_events(body)
    error_events = [e for e in events if e.get("event") == "error"]
    assert len(error_events) >= 1, f"Expected error event, got: {events}"
    error_data = json.loads(error_events[0]["data"])
    assert "message" in error_data


# ─────────────────────────────────────────────────────────────────────────────
# Validation regression tests (must still return 422, not 200)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_empty_query_still_rejected_422(
    test_client: AsyncClient,
) -> None:
    """
    An empty query string is still rejected with 422 after the stub is replaced.

    Pydantic validation happens before the route handler runs — the pipeline
    never executes for invalid input.
    """
    response = await test_client.post("/api/v1/query", json={"query": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_whitespace_query_still_rejected_422(
    test_client: AsyncClient,
) -> None:
    """
    A whitespace-only query is rejected with 422 (custom field_validator).
    """
    response = await test_client.post("/api/v1/query", json={"query": "   "})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_missing_query_field_still_rejected_422(
    test_client: AsyncClient,
) -> None:
    """A request with no 'query' field is rejected with 422."""
    response = await test_client.post("/api/v1/query", json={"top_k": 5})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_top_k_out_of_range_still_rejected_422(
    test_client: AsyncClient,
) -> None:
    """top_k values outside [1, 20] are rejected with 422."""
    r_low = await test_client.post(
        "/api/v1/query", json={"query": "test", "top_k": 0}
    )
    r_high = await test_client.post(
        "/api/v1/query", json={"query": "test", "top_k": 999}
    )
    assert r_low.status_code == 422
    assert r_high.status_code == 422
