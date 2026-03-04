# Plan: Wire `/api/v1/query` to SSE streaming pipeline

**Goal:** Replace the query stub with a real implementation that returns an SSE stream so `backend/tests/unit/test_query_pipeline.py` passes (15/15).

**Root cause:** The router still has `query_stub` returning `StubResponse` (JSON). The tests expect `text/event-stream` with events: `snippets` → `token`(s) → `done`, or `error` on failure.

---

## 1. SSE contract (from tests)

- **Success:**  
  `event: snippets` + `data: <JSON array of snippet objects>`  
  then one or more `event: token` + `data: <token text>`  
  then `event: done` + `data: {"query_time_ms": N}`.
- **Error (embedding/Pinecone failure):**  
  `event: error` + `data: {"message": "..."}`.  
  HTTP status remains 200 (stream already opened).
- **Snippet shape:** Each snippet in the `snippets` event must have: `file_path`, `start_line`, `end_line`, `content`, `score` (0.0–1.0), with `end_line >= start_line >= 1`.

---

## 2. Pipeline flow (already implemented in core)

1. **Embed:** `embed_query(query, openai_client)` → `list[float]`
2. **Retrieve:** `PineconeWrapper(pinecone_client, index_name).query(embedding, top_k, min_score)` → `list[SearchResult]`
3. **Rerank:** `rerank(query, candidates, top_k=request.top_k, min_score=settings.similarity_threshold)` → `list[RankedResult]`
4. **To snippets:** Map each `RankedResult` to `CodeSnippet`: `file_path`, `start_line`, `end_line`, `content` from `metadata`; `score` = `combined_score`.
5. **Generate:** `generate_answer(query, snippets, openai_client)` → async generator of `str` tokens.

The route must run steps 1–4, then stream: one `snippets` event, then `token` events from step 5, then `done` with `query_time_ms`. On any exception in 1–4 or 5, yield one `error` event (with `message`) then stop.

---

## 3. Implementation steps

### 3.1 Add a core “query pipeline” module (optional but recommended)

- **File:** `backend/app/core/query_pipeline.py` (or keep logic in the route).
- **Purpose:** One async generator that:
  - Takes: `query: str`, `top_k: int`, `openai_client`, `pinecone_client`, `settings`.
  - Runs embed → PineconeWrapper.query → rerank.
  - Converts `RankedResult` list to `list[CodeSnippet]` (helper or inline).
  - Yields SSE event strings in order: `snippets`, then each `token` from `generate_answer`, then `done`.
  - Catches exceptions and yields a single `error` event (with `message`) then re-raises or returns.
- **Why:** Keeps the route thin (validate → call pipeline → return `StreamingResponse`). Easier to unit-test the pipeline and to reuse from other entry points later.

### 3.2 Implement the route handler

- **File:** `backend/app/api/v1/router.py` (or a dedicated `backend/app/api/v1/endpoints/query.py` and register in router).
- **Change:** Replace `query_stub` with an endpoint that:
  - Accepts `QueryRequest` and uses `Depends(get_current_user)`, `Depends(get_openai_client)`, `Depends(get_pinecone_client)`, and `get_settings()`.
  - Builds `PineconeWrapper(pinecone_client, settings.pinecone_index_name)`.
  - Calls the pipeline generator (from 3.1) or inlines the same flow.
  - Returns `StreamingResponse(
        pipeline_generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )`.
- **No `response_model=StubResponse`:** Use `StreamingResponse`; no Pydantic response model for this endpoint.

### 3.3 SSE event formatting

- **Snippets:** One block: `event: snippets\ndata: <json.dumps([{...}, ...])>\n\n`. Each dict has `file_path`, `start_line`, `end_line`, `content`, `score`.
- **Token:** For each token from `generate_answer`: `event: token\ndata: <escaped token>\n\n`. (Newlines in token: escape or use JSON string in `data` so the test’s parser still sees a single `data` line per event; tests join token data with `"".join(e["data"] for e in token_events)`.)
- **Done:** `event: done\ndata: {"query_time_ms": <float>}\n\n`. Measure time from start of request (or start of pipeline) to after the last token.
- **Error:** `event: error\ndata: {"message": "<str>"}\n\n`. Use the exception message (or a safe generic message for unexpected errors).

### 3.4 RankedResult → CodeSnippet

- **Where:** In the pipeline (or route) after `rerank()`.
- **Mapping:** For each `RankedResult r`:  
  `CodeSnippet(file_path=r.metadata["file_path"], start_line=r.metadata["start_line"], end_line=r.metadata["end_line"], content=r.metadata["content"], score=r.combined_score)`.
- **Validation:** Ensure `metadata` has required keys; if not, skip the result or log and skip. Tests expect at least one snippet in the happy path.

### 3.5 Fix conftest OpenAI mock for streaming

- **Issue:** `answer_generator.generate_answer()` uses `openai_client.chat.completions.create(..., stream=True)` and iterates the returned stream. The current conftest mocks `client.chat.completions.stream`, so the real code never uses the mock when streaming.
- **Change:** In `backend/tests/conftest.py`, in `mock_openai_client`:
  - Mock `chat.completions.create` (instead of or in addition to `stream`) so that when called with `stream=True` it returns an async iterable that yields chunks with `chunk.choices[0].delta.content` set to the mock tokens (e.g. `["This", " is", " a", " mocked", " answer", "."]`).
  - Ensure the returned object is an async generator or an object that supports `__aiter__` and yields MagicMocks with `.choices[0].delta.content` set, so `async for chunk in stream` in `generate_answer` works.

After this, the happy-path tests that expect `token` events and the fallback-message test should see the correct behavior.

---

## 4. Error handling

- **Embedding failure** (e.g. `embed_query` raises): Catch in the pipeline/route, yield `event: error` + `data: {"message": "<exception message>"}`, then stop the generator. Tests expect status 200 and at least one `error` event.
- **Pinecone failure** (e.g. `wrapper.query` raises): Same: yield `error` event with message, then stop.
- **Rerank:** Synchronous; let any exception propagate and be caught by the same error path.
- **generate_answer** (OpenAI) failure: Catch in the streaming loop, yield `error` event, then stop.

Do not return HTTP 503 for these once the stream has started; the tests assert status 200 and the presence of an `error` event.

---

## 5. Validation (unchanged)

- Keep existing Pydantic validation for `QueryRequest` (query non-empty, non-whitespace, top_k 1–20). Invalid requests still return 422 before any pipeline code runs. No changes needed for the four validation tests.

---

## 6. Files to touch (summary)

| File | Action |
|------|--------|
| `backend/app/api/v1/router.py` | Replace query stub with SSE endpoint; use pipeline generator + `StreamingResponse`. |
| `backend/app/core/query_pipeline.py` | **New.** Async generator: embed → query → rerank → map to CodeSnippet → yield SSE events (snippets, tokens from generate_answer, done; on exception yield error). |
| `backend/app/core/retrieval/reranker.py` | No change (already returns `list[RankedResult]`). |
| `backend/app/core/generation/answer_generator.py` | No change (already yields tokens; uses `create(..., stream=True)`). |
| `backend/tests/conftest.py` | Fix OpenAI mock: make `chat.completions.create` with `stream=True` return an async iterable yielding chunks with `.choices[0].delta.content`. |
| `backend/app/dependencies.py` | Optional: add `get_pinecone_wrapper()` that returns `PineconeWrapper(get_pinecone_client(), get_settings().pinecone_index_name)` so the route doesn’t construct it. Or build the wrapper inside the pipeline/route. |

---

## 7. Test run

After implementation:

```bash
cd backend && .venv/bin/pytest tests/unit/test_query_pipeline.py -v -m "not integration"
```

All 15 tests should pass. Run the full unit suite and coverage to ensure no regressions; if coverage fails due to new code, add targeted unit tests for the pipeline generator (e.g. event order, error event on embed failure).

---

## 8. Order of work

1. Fix conftest OpenAI mock (`create` with `stream=True` returning async iterable).
2. Add `query_pipeline.py`: pipeline generator + RankedResult → CodeSnippet + SSE formatting.
3. Replace query stub in router with endpoint that calls the pipeline and returns `StreamingResponse`.
4. Run `test_query_pipeline.py`; fix any mismatches (e.g. token escaping, event names, `query_time_ms`).
5. Run full unit suite and coverage; fix any regressions or coverage gaps.
