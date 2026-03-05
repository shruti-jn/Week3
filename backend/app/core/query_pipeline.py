"""
Query pipeline -- runs the full RAG flow and yields SSE events.

This module is the single place that orchestrates:
    embed -> retrieve (Pinecone) -> rerank -> snippets -> generate_answer (stream)

The route handler is thin: validate request -> call this generator -> return
StreamingResponse. Keeping the pipeline here makes it easy to unit-test
event order and error handling without hitting the API layer.

Pipeline position:
    POST /api/v1/query -> [this module] -> SSE stream (snippets, token..., done | error)

Observability:
    When LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY are set, every query is
    traced in Langfuse with one trace per request and child spans for embed,
    retrieve, rerank, and generate_answer. The same metrics sent in the "done"
    SSE event are also recorded as trace metadata so the Langfuse dashboard
    shows latency breakdowns and similarity scores.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import voyageai

from app.core.generation.answer_generator import generate_answer
from app.core.ingestion.embedder import embed_query
from app.core.retrieval.pinecone_client import PineconeWrapper
from app.core.retrieval.reranker import RankedResult, rerank
from app.models.responses import CodeSnippet

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Required metadata keys for RankedResult -> CodeSnippet. Skip results missing any.
_REQUIRED_META = ("file_path", "start_line", "end_line", "content")


# -- Langfuse tracing helpers --------------------------------------------------


class _Span:
    """
    A thin wrapper around a Langfuse span (or a no-op when Langfuse is off).

    Using a wrapper means the pipeline code never needs to check
    "is Langfuse enabled?" -- it just calls span.end() and the wrapper
    handles the real vs no-op case transparently.
    """

    def __init__(self, span: Any) -> None:  # noqa: ANN401 -- Langfuse type not importable
        self._span = span

    def end(self, output: dict[str, Any] | None = None) -> None:
        """End this span, optionally recording output metadata."""
        if self._span is None:
            return
        try:
            if output is not None:
                self._span.end(output=output)
            else:
                self._span.end()
        except Exception:
            logger.debug("langfuse: span.end() failed (non-fatal)")

    def error(self, message: str) -> None:
        """Mark this span as failed with an error message."""
        if self._span is None:
            return
        try:
            self._span.end(level="ERROR", status_message=message)
        except Exception:
            logger.debug("langfuse: span.error() failed (non-fatal)")


class _Tracer:
    """
    One Langfuse trace per query request (or a no-op when Langfuse is off).

    Wraps the Langfuse StatefulTraceClient so the pipeline can call
    tracer.span("embed") without caring whether Langfuse is configured.
    All failures are caught and logged at DEBUG -- tracing must never
    break the query pipeline.
    """

    def __init__(self, trace: Any) -> None:  # noqa: ANN401 -- Langfuse type not importable
        self._trace = trace

    def span(self, name: str, input_data: dict[str, Any] | None = None) -> _Span:
        """Start a child span on this trace."""
        if self._trace is None:
            return _Span(None)
        try:
            kwargs: dict[str, Any] = {"name": name}
            if input_data is not None:
                kwargs["input"] = input_data
            return _Span(self._trace.span(**kwargs))
        except Exception:
            logger.debug("langfuse: trace.span() failed (non-fatal)")
            return _Span(None)

    def finish(self, output: dict[str, Any] | None = None) -> None:
        """Finalise the trace with output metadata."""
        if self._trace is None:
            return
        try:
            if output is not None:
                self._trace.update(output=output)
        except Exception:
            logger.debug("langfuse: trace.update() failed (non-fatal)")

    def error(self, message: str) -> None:
        """Mark the trace as failed."""
        if self._trace is None:
            return
        try:
            self._trace.update(level="ERROR", status_message=message)
        except Exception:
            logger.debug("langfuse: trace.update(error) failed (non-fatal)")


def _make_tracer(
    query: str,
    top_k: int,
    settings: Any,  # noqa: ANN401 -- Settings type causes circular import
) -> _Tracer:
    """
    Build a Langfuse tracer for one query, or a no-op tracer if disabled.

    Langfuse is disabled when either key is missing from settings.
    This function never raises -- if Langfuse init fails for any reason,
    it returns a no-op tracer so the pipeline continues unaffected.
    """
    if not getattr(settings, "langfuse_enabled", False):
        return _Tracer(None)

    try:
        from langfuse import Langfuse  # import inside function to keep it optional

        lf = Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_base_url,
        )
        trace = lf.trace(  # type: ignore[attr-defined]  # Langfuse SDK; no stubs
            name="legacylens-query",
            input={"query": query, "top_k": top_k},
        )
        return _Tracer(trace)
    except Exception:
        logger.debug("langfuse: failed to create tracer (non-fatal)")
        return _Tracer(None)


# -- Core pipeline helpers -----------------------------------------------------


def _ranked_to_snippet(r: RankedResult) -> CodeSnippet | None:
    """
    Map a RankedResult to a CodeSnippet for the snippets SSE event.

    Skips (returns None) if metadata is missing required keys so we never
    send invalid snippet shapes to the client.
    """
    meta = r.metadata
    for key in _REQUIRED_META:
        if key not in meta:
            logger.warning(
                "query_pipeline: skipping result '%s' -- missing metadata key '%s'",
                r.chunk_id,
                key,
            )
            return None
    try:
        # Derive chunk_type from Pinecone metadata: if paragraph_name is present
        # and non-empty the chunk was split at a COBOL paragraph boundary;
        # otherwise it was a fixed-size fallback cut.
        paragraph_name = meta.get("paragraph_name", "")
        chunk_type = (
            "fixed" if (not paragraph_name or meta.get("is_fallback")) else "paragraph"
        )
        return CodeSnippet(
            file_path=str(meta["file_path"]),
            start_line=int(meta["start_line"]),
            end_line=int(meta["end_line"]),
            content=str(meta["content"]),
            score=round(r.combined_score, 4),
            chunk_type=chunk_type,
            paragraph_name=paragraph_name,
        )
    except (ValueError, TypeError) as e:
        logger.warning(
            "query_pipeline: skipping result '%s' -- invalid metadata: %s",
            r.chunk_id,
            e,
        )
        return None


def _sse_event(event: str, data: str | list[Any] | dict[str, Any]) -> str:
    """Format one SSE block: event: <name>\\ndata: <payload>\\n\\n."""
    if isinstance(data, (dict, list)):
        data_str = json.dumps(data)
    else:
        data_str = data
    return f"event: {event}\ndata: {data_str}\n\n"


def _now_ms() -> float:
    """Return current time in milliseconds (monotonic clock)."""
    return time.perf_counter() * 1000.0


# -- Main pipeline -------------------------------------------------------------


async def stream_query_sse(
    query: str,
    top_k: int,
    voyage_client: voyageai.Client,  # type: ignore[name-defined]  # no stubs
    openai_client: AsyncOpenAI,
    pinecone_client: Any,  # noqa: ANN401 -- Pinecone type not importable without circular dep
    settings: Any,  # noqa: ANN401 -- Settings type causes circular import
) -> AsyncGenerator[str, None]:
    """
    Run the full RAG pipeline and yield SSE event strings in order.

    Success: snippets -> token (one or more) -> done.
    Failure: error (with message), then stop.

    The "done" event carries a full metrics payload so the frontend can
    display per-query analytics without a separate API call:
        query_time_ms   -- total wall-clock time
        embed_ms        -- time spent embedding the query
        retrieve_ms     -- time spent querying Pinecone
        rerank_ms       -- time spent reranking candidates
        llm_ms          -- time spent streaming the LLM answer
        chunks_count    -- number of snippets returned
        top_score       -- highest similarity score (0-1)
        avg_similarity  -- mean similarity across returned snippets
        files_hit       -- number of unique source files in results

    Args:
        query:           Plain-English question (already validated non-empty).
        top_k:           Max snippets to return (1-20 from request).
        voyage_client:   Voyage AI client for embedding the query (voyage-code-2).
        openai_client:   Async OpenAI client for answer generation (gpt-4o-mini).
        pinecone_client: Pinecone client (real or mock).
        settings:        App settings (index name, thresholds).

    Yields:
        SSE-formatted strings: "event: X\\ndata: Y\\n\\n".
    """
    t_start = _now_ms()
    tracer = _make_tracer(query, top_k, settings)

    try:
        # 1. Embed query -- Voyage voyage-code-2 with input_type="query" for
        # asymmetric retrieval (query vs document embeddings differ by design).
        t0 = _now_ms()
        embed_span = tracer.span("embed", {"query": query})
        embedding = await embed_query(query, voyage_client)
        embed_ms = round(_now_ms() - t0, 2)
        embed_span.end({"embed_ms": embed_ms, "dims": len(embedding)})

        # 2. Retrieve from Pinecone
        t0 = _now_ms()
        retrieve_span = tracer.span(
            "retrieve",
            {
                "top_k": settings.retrieval_top_k,
                "min_score": settings.similarity_threshold,
            },
        )
        wrapper = PineconeWrapper(
            client=pinecone_client,
            index_name=settings.pinecone_index_name,
        )
        candidates = await wrapper.query(
            embedding,
            top_k=settings.retrieval_top_k,
            min_score=settings.similarity_threshold,
        )
        retrieve_ms = round(_now_ms() - t0, 2)
        retrieve_span.end({"retrieve_ms": retrieve_ms, "candidates": len(candidates)})

        # 3. Rerank and take top_k
        t0 = _now_ms()
        rerank_span = tracer.span("rerank", {"top_k": top_k})
        ranked = rerank(
            query,
            candidates,
            top_k=top_k,
            min_score=settings.similarity_threshold,
        )
        rerank_ms = round(_now_ms() - t0, 2)
        rerank_span.end({"rerank_ms": rerank_ms, "ranked": len(ranked)})

        # 4. Map to CodeSnippet list (skip invalid)
        snippets: list[CodeSnippet] = []
        for r in ranked:
            snip = _ranked_to_snippet(r)
            if snip is not None:
                snippets.append(snip)

        # 5. Emit snippets event (list of dicts for JSON)
        snippets_payload = [s.model_dump() for s in snippets]
        yield _sse_event("snippets", snippets_payload)

        # 6. Stream answer tokens -- measure total LLM time
        t0 = _now_ms()
        llm_span = tracer.span(
            "generate_answer",
            {"model": "gpt-4o-mini", "chunks": len(snippets)},
        )
        # Pass only the top 3 snippets to the LLM — the remaining context
        # cuts input tokens by ~40%, reducing TTFT on GPT-4o-mini without
        # meaningful accuracy loss (reranker already ranked best-first).
        llm_snippets = snippets[:3]
        async for token in generate_answer(query, llm_snippets, openai_client):
            # One data line per event so SSE parsers that keep only the last
            # data line work correctly.
            token_one_line = token.replace("\n", " ").replace("\r", " ")
            yield _sse_event("token", token_one_line)
        llm_ms = round(_now_ms() - t0, 2)
        llm_span.end({"llm_ms": llm_ms})

        # 7. Compute per-query analytics from the returned snippets
        scores = [s.score for s in snippets]
        top_score = round(max(scores), 4) if scores else 0.0
        avg_similarity = round(sum(scores) / len(scores), 4) if scores else 0.0
        files_hit = len({s.file_path for s in snippets})
        total_ms = round(_now_ms() - t_start, 2)

        done_payload: dict[str, Any] = {
            "query_time_ms": total_ms,
            "embed_ms": embed_ms,
            "retrieve_ms": retrieve_ms,
            "rerank_ms": rerank_ms,
            "llm_ms": llm_ms,
            "chunks_count": len(snippets),
            "top_score": top_score,
            "avg_similarity": avg_similarity,
            "files_hit": files_hit,
        }
        tracer.finish(done_payload)
        yield _sse_event("done", done_payload)

    except Exception as exc:
        logger.exception("query_pipeline: pipeline failed")
        message = str(exc) if str(exc) else "An unexpected error occurred."
        tracer.error(message)
        yield _sse_event("error", {"message": message})
