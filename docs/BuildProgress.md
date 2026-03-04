# LegacyLens — Build Progress Log

> Running record of what has been built, branch by branch.
> Update this after every squash merge to dev.

---

## Phase 1 — MVP

| # | Feature | Branch | Status | Commit |
|---|---------|--------|--------|--------|
| 1 | Clone gnucobol-contrib + verify file structure | `chore/project-scaffold` | ✅ merged to dev | — |
| 2 | GitHub OAuth login + FastAPI JWT validation | `feature/frontend-auth` | ✅ merged to dev | `7fd2a89` |
| 3 | File scanner — find all .cob / .cbl files | `feature/ingestion-file-scanner` | ✅ merged to dev | `aba17f7` |
| 4 | Pinecone client wrapper (upsert + query) | `feature/retrieval-pinecone-client` | ✅ merged to dev | `ddebd4d` |
| 5 | API scaffold — stub endpoints | `feature/api-scaffold` | ✅ merged to dev | `1e85e1f` |
| — | Phase 1 audit fixes (items 1–5) | `fix/phase1-audit-items` | ✅ PR open | — |
| 6 | COBOL chunker — paragraph-level + fallback | `feature/ingestion-cobol-chunker` | ✅ merged to dev | `93d70e5` |
| 7 | Embedder — OpenAI batched + Pinecone upsert | `feature/ingestion-embedder` | ✅ on dev | `b56d6fe` |
| 8 | Reranker — keyword scoring + 0.75 threshold | `feature/retrieval-reranker` | 🔲 not started | — |
| 9 | Answer generator — GPT-4o-mini SSE | `feature/generation-answer` | 🔲 not started | — |
| 10 | Wire full backend pipeline | `feature/api-full-pipeline` | 🔲 blocked by 7+8+9 | — |
| 11 | Query UI — search input + results display | `feature/frontend-query-ui` | 🔲 not started | — |
| 12 | Connect frontend to live API | `feature/frontend-results-display` | 🔲 blocked by 10+11 | — |
| 13 | Deploy — Railway + Vercel | `chore/deployment-config` | 🔲 blocked by 12 | — |

---

## Item Summaries

### Phase 1 Audit Fixes (2026-03-02)
**Branch:** `fix/phase1-audit-items` → PR to dev

**What was fixed and why:**

| Fix | File(s) | Why it was needed |
|-----|---------|-------------------|
| `asyncio.get_running_loop()` | `pinecone_client.py` | `get_event_loop()` is deprecated in Python 3.10+ (raises `DeprecationWarning`). `get_running_loop()` is the correct API when called from inside an `async def`. |
| Retry logic with backoff | `pinecone_client.py` | CLAUDE.md mandates retry for all external API calls. Pinecone returns transient 429/503 errors that a single attempt would silently fail. Added `_upsert_with_retry` and `_query_with_retry` helpers (3 attempts, 1s/2s/4s backoff). |
| Production API docs gated | `config.py`, `main.py` | `/docs` and `/redoc` were unconditionally enabled. Exposing the full API schema in production lets attackers enumerate every endpoint. Added `environment` setting; docs disabled when `ENVIRONMENT=production`. |
| File scanner docstring | `file_scanner.py` | `_build_cobol_file` docstring said "reads the file twice" but `stat()` is an OS metadata call, not a file read. Only one read (`read_bytes()`) happens — misleading comment fixed. |
| Line count caveat documented | `file_scanner.py` (COBOLFile) | `line_count` counts `\n` chars (`wc -l` behaviour) — files without trailing newlines report one fewer than the visual line count. Documented clearly in the dataclass docstring so the chunker team doesn't misuse it. |
| PermissionError handling | `file_scanner.py` | `rglob` on a repo with restricted files raises `PermissionError` and aborts the whole scan. Changed to log a warning and skip the unreadable file instead. |
| Phase 2 response field validation | `responses.py` | `ExplainResponse`, `DependenciesResponse`, `BusinessLogicResponse`, `ImpactResponse` had bare `str` fields with no constraints. Added `min_length=1` to prevent empty strings from silently passing through the API layer. |
| Auth token mismatch (critical) | `frontend/src/lib/auth.ts`, new `frontend/src/app/api/auth/token/route.ts` | `session.accessToken` is the GitHub OAuth token — FastAPI cannot verify it with `NEXTAUTH_SECRET`. Created `/api/auth/token` endpoint that uses `getToken({ raw: true })` server-side to return the actual NextAuth-signed JWT, which is what `validate_nextauth_token()` expects. Clarified the distinction in `auth.ts` comments. |
| Frontend auth tests | `AuthButton.test.tsx`, `middleware.test.ts` | Auth components had zero test coverage. Added 10 tests for `AuthButton` (loading/auth/unauth states, signIn/signOut calls) and 9 tests for middleware matcher config. |
| get_current_user coverage | `test_router_scaffold.py` | `app/api/v1/dependencies.py` was at 82% — lines 68-69 (the `validate_nextauth_token` call) were never exercised. Added `test_query_with_valid_bearer_token_succeeds` which sends a real JWT through the full dependency without overrides. |
| Pinecone retry tests | `test_pinecone_client.py` | New retry methods need test coverage. Added 4 tests: transient failure + succeed on retry (upsert and query), and all-retries-exhausted raises `RuntimeError` (upsert and query). |
| Phase 2 model validation tests | `test_models.py` | New `min_length=1` constraints needed corresponding rejection tests. Added `TestFeatureResponseFieldValidation` with 7 tests. |
| PermissionError test | `test_file_scanner.py` | New `PermissionError` handler + `line_count` wc-l behaviour needed test coverage. Added 2 tests. |

**Quality after fixes:**
- Backend: 145+ unit tests, all passing
- Coverage: maintained above 95% across all modules
- Frontend: 19+ Jest tests added for auth components

---

### #6 — COBOL Chunker (2026-03-02)
**Branch:** `feature/ingestion-cobol-chunker` → squash merged to `dev` as `93d70e5`

**What it does:**
Splits a COBOL source file into semantic chunks ready for embedding. Two strategies:
1. **Paragraph-level** (primary) — detects the `PROCEDURE DIVISION` header, then finds every paragraph label (single uppercase identifier ending with `.`, alone on its own line). Each paragraph becomes one `COBOLChunk`.
2. **Fixed-size fallback** — when no paragraphs are found, produces overlapping 50-line windows with 10-line overlap.

**Key design decisions:**
- `COBOLChunk` dataclass: `file_path`, `paragraph_name`, `start_line`, `end_line`, `content`, `chunk_index`, `is_fallback`
- Comment detection handles both free-format (`*>`) and fixed-format (`*` at column 7 / index 6)
- Reserved-word exclusion list prevents false positives from `EXIT.`, `END-IF.`, `CONTINUE.`, etc.
- Trailing blank lines trimmed from each chunk so content ends on meaningful code
- Windows `\r\n` and old Mac `\r` line endings normalised to `\n`

**Files created:**
- `backend/app/core/ingestion/chunker.py` (437 lines)
- `backend/tests/unit/test_chunker.py` (491 lines)

**Quality:**
- 71 unit tests, all passing
- 97% coverage on `chunker.py`
- `ruff` lint + format: clean
- `mypy --strict`: clean

---

### #7 — Embedding Generator (2026-03-02)
**Branch:** `feature/ingestion-embedder` → committed directly to `dev` as `b56d6fe`

**What it does:**
Converts `COBOLChunk` objects into 1536-dimensional vector embeddings using OpenAI
`text-embedding-3-small`, then stores them in Pinecone. Also provides `embed_query()`
for embedding user questions at retrieval time.

**Public API:**
- `embed_chunks(chunks, openai_client, batch_size=100)` → `list[ChunkVector]`
  Calls OpenAI in batches of 100 texts per request. Returns one `ChunkVector` per input chunk.
- `embed_query(query_text, openai_client)` → `list[float]`
  Embeds a single user query string. Raises `ValueError` on empty/whitespace input.
- `embed_and_upsert(chunks, openai_client, pinecone_wrapper)` → `int`
  Full ingestion pipeline: embed chunks then upsert to Pinecone. Returns vector count.

**Key design decisions:**
- Vector IDs: `file_path::PARA-NAME` for named paragraphs, `file_path::chunk_N` for fallback
- Metadata stored in Pinecone: `file_path`, `paragraph_name` (`""` not `None`), `start_line`,
  `end_line`, `content`, `chunk_index`, `is_fallback` — all fields needed to show citations
- Retry: `_call_embed_api()` attempts 3 times with 1s/2s exponential backoff for OpenAI rate limits
- `zip(batch, response.data)` uses `# noqa: B905` — `strict=` requires Python 3.10+, dev runtime is 3.9

**Also fixed in this commit:**
- `pinecone_client.py`: replaced `lambda records=pinecone_records: ...` with
  `functools.partial(self._index.upsert, vectors=pinecone_records)` — fixes mypy `[misc]` and ruff B023.
  Also fixed pre-existing RUF001/RUF002 (EN DASH), E501, ANN401 lint errors.

**Files created:**
- `backend/app/core/ingestion/embedder.py` (262 lines)
- `backend/tests/unit/test_embedder.py` (440 lines)

**Quality:**
- 24 unit tests, all passing in 0.27s
- `ruff` lint + format: clean (on new files)
- `mypy --strict`: clean on `embedder.py` and `pinecone_client.py`
