# LegacyLens V3 — Executive Build Plan

> **Classification:** Engineering Leadership Review
> **Revision:** 1.0 | **Date:** 2026-03-02
> **Owner:** Principal Engineer / TPM
> **Status:** PENDING APPROVAL

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Scope and Non-Goals](#2-scope-and-non-goals)
3. [Assumptions, Constraints, and Unknowns](#3-assumptions-constraints-and-unknowns)
4. [Architecture Decision Record](#4-architecture-decision-record)
5. [Work Breakdown Structure](#5-work-breakdown-structure)
6. [Parallel Execution Plan](#6-parallel-execution-plan)
7. [Test Strategy](#7-test-strategy)
8. [Quality Engineering and Review System](#8-quality-engineering-and-review-system)
9. [Observability, Evaluation, and Metrics](#9-observability-evaluation-and-metrics)
10. [Cost Model and Scale Plan](#10-cost-model-and-scale-plan)
11. [Risk Register and Mitigations](#11-risk-register-and-mitigations)
12. [Delivery Timeline and Milestones](#12-delivery-timeline-and-milestones)
13. [Execution Runbook](#13-execution-runbook)
14. [Communication Plan](#14-communication-plan)
15. [Context and Token Management Protocol](#15-context-and-token-management-protocol)
16. [Final Approval Packet](#16-final-approval-packet)
17. [Appendix A — Top 10 Execution Mistakes to Avoid](#appendix-a--top-10-execution-mistakes-to-avoid)
18. [Appendix B — First 72-Hour Action Plan](#appendix-b--first-72-hour-action-plan)
19. [Appendix C — Prompt Pack for Claude and Cursor](#appendix-c--prompt-pack-for-claude-and-cursor)

---

## 1. Executive Summary

### Problem

Enterprises running COBOL on mainframes face a critical knowledge gap: codebases with 40+ years of embedded business logic, and almost no engineers who can read them. Onboarding to a legacy COBOL system takes weeks. A single paragraph in a 10,000-line COBOL program may encode millions of dollars of business logic — invisible unless you already know where to look.

### Approach

LegacyLens V3 is a Retrieval-Augmented Generation (RAG) system that makes large COBOL codebases queryable through plain English. Developers type questions; the system finds the exact code paragraph and explains it — with the file path and line numbers cited.

The system is built on a four-layer pipeline:
**Ingest → Embed → Retrieve → Explain**

All layers are syntax-aware: COBOL's DIVISION/SECTION/PARAGRAPH structure is preserved as the primary chunking unit, enabling retrieval at the exact grain of COBOL business logic. No speculative answers are generated; every response is grounded in retrieved code with explicit citations.

### Why This Plan Is Low-Risk and High-Confidence

- **Proven stack:** Every component (Pinecone, OpenAI, FastAPI, Next.js) is production-hardened with publicly documented APIs. No experimental dependencies.
- **Incremental delivery:** MVP (Tuesday) is independently deployable and demonstrable. Each subsequent phase adds on top of a working baseline.
- **TDD-first:** All critical components (chunker, reranker, retriever) have failing tests written before implementation — catching regressions early when the timeline is tight.
- **Explicit failure modes:** The system has defined fallback behavior for every failure scenario (no relevant chunks, low similarity, API timeout). There is no silent failure.
- **Cost-bounded:** Dev spend is under $5 for MVP. Scale projections are documented from 100 to 100,000 users with trigger thresholds for cost control.

### Top 5 Success Outcomes (Measurable)

| # | Outcome | Target | Measurement Method |
|---|---------|--------|--------------------|
| 1 | Query latency | < 3 seconds end-to-end | Logged per-request in backend; P95 target |
| 2 | Retrieval precision | Precision@5 > 70% | Golden query set, 20 queries, manual eval |
| 3 | Codebase coverage | 100% of .cob/.cbl/.cpy files indexed | File count in Pinecone vs. repo file count |
| 4 | Ingestion throughput | 10,000+ LOC in < 5 minutes | Timed during pipeline integration test |
| 5 | Feature completeness | 4 code-understanding features live | Manual demo walkthrough before submission |

---

## 2. Scope and Non-Goals

### In-Scope Deliverables

| Deliverable | Description | Milestone |
|-------------|-------------|-----------|
| Ingestion pipeline | File discovery, preprocessing, syntax-aware chunking, embedding, Pinecone upsert | Tuesday MVP |
| Query API | Embed query → retrieve chunks → rerank → LLM answer → SSE stream | Tuesday MVP |
| Web UI | Auth gate, query input, results display, syntax highlighting | Tuesday MVP |
| GitHub OAuth | NextAuth.js integration, FastAPI JWT validation, rate limiting | Tuesday MVP |
| Railway + Vercel deploy | Auto-deploy from main branch | Tuesday MVP |
| Syntax-aware chunker | COBOL DIVISION/SECTION/PARAGRAPH boundary detection, fixed-size fallback | Wednesday G4 |
| Reranker | Keyword overlap scoring on top of vector similarity | Wednesday G4 |
| Code Explanation (F1) | Paragraph/section explanation in plain English | Wednesday G4 |
| Dependency Mapping (F2) | CALL/PERFORM/COPY statement parsing, cross-file deps | Wednesday G4 |
| Business Logic Extraction (F3) | Financial rules, conditionals, validation logic summarized | Wednesday G4 |
| Impact Analysis (F4) | What breaks if this paragraph changes — reference search | Wednesday G4 |
| Evaluation set | 20 golden queries, Precision@5 measured and documented | Wednesday G4 |
| RAG Architecture doc | 1–2 page write-up per submission requirements | Sunday Final |
| AI Cost Analysis | Dev spend + projections doc | Sunday Final |
| Demo video | 3–5 min, shows all 4 features | Sunday Final |
| Social post | X or LinkedIn, tags @GauntletAI | Sunday Final |

### Explicit Non-Goals (Scope Creep Prevention)

| Non-Goal | Reason |
|----------|--------|
| Multi-codebase support | Out of scope for MVP; one primary codebase only |
| Real-time incremental indexing | Batch ingestion sufficient; re-indexing is manual |
| Full static analysis or call-graph correctness | Heuristic-based dependency mapping is sufficient |
| COBOL compilation or execution | We read and explain; we do not run |
| CLI interface | Web UI is the product; no parallel CLI track |
| Mobile-responsive UI | Desktop browser only for this sprint |
| Multi-language support (Fortran, etc.) | COBOL only; extensibility deferred |
| User-uploaded codebases | Fixed target codebase (gnucobol-contrib) only |
| Persistent user query history | No database for user data; stateless sessions |
| Admin dashboard / analytics UI | Internal logging is sufficient; no UI needed |

### Exit Criteria

**MVP (Tuesday):** System is publicly accessible at a Vercel URL. A grader can log in with GitHub, type a natural language question, and receive a response with at least one cited COBOL file path and line number within 3 seconds.

**Final (Sunday):** All 4 features are live and demonstrated. Precision@5 > 70% on the golden query set. RAG Architecture doc, Cost Analysis, demo video, and social post are all submitted. Pre-Search document is finalized.

---

## 3. Assumptions, Constraints, and Unknowns

| Item | Type | Impact (H/M/L) | Validation Method | Owner | Due Date |
|------|------|----------------|-------------------|-------|----------|
| gnucobol-contrib has 10k+ LOC / 50+ files in .cob/.cbl format | Assumption | H | `find data/gnucobol-contrib -name "*.cob" -o -name "*.cbl" \| wc -l && wc -l **/*.cob` | Eng | Day 1 Hour 1 |
| OpenAI API key has sufficient quota for ingestion + dev queries | Assumption | H | Check OpenAI usage dashboard before starting | Eng | Day 1 Hour 1 |
| Pinecone free tier supports 1536-dim index with 10k+ vectors | Assumption | M | Create index, verify limit in Pinecone console | Eng | Day 1 Hour 2 |
| Railway free/hobby tier supports long-running uvicorn process | Assumption | M | Deploy stub backend, verify uptime | Eng | Day 1 |
| GitHub OAuth callback URL registered for Vercel domain | Assumption | H | OAuth app created in GitHub settings before frontend deploy | Eng | Day 1 |
| COBOL files use standard DIVISION/SECTION/PARAGRAPH markers | Assumption | H | Manually inspect 5 files from gnucobol-contrib before writing chunker | Eng | Day 1 |
| GPT-4o-mini can enforce citation format reliably | Assumption | M | Test with 5 manually verified prompts before implementing streaming | Eng | Day 1 |
| text-embedding-3-small produces ≥ 0.75 cosine similarity for known-relevant chunks | Assumption | H | Run golden query test after first ingestion | Eng | Day 2 |
| Railway + Vercel deploy completes within 5 minutes | Constraint | M | Measure on first deploy; optimize Dockerfile if needed | Eng | Day 1 |
| Total dev spend must remain under $20 | Constraint | M | Track in docs/COST_LOG.md daily | Eng | Ongoing |
| Deadline is Sunday 10:59 PM CT — no extensions | Constraint | H | All submissions automated; do not rely on manual steps | Eng | Sunday |
| No team members; solo execution | Constraint | H | Strict parallel workstream discipline; no blocked-on-self tasks | Eng | Ongoing |
| Some COBOL files may use non-standard fixed-format columns | Unknown | M | Inspect column positions on 10 sample files; add column-stripping preprocessing | Eng | Day 1 |
| LLM citation compliance rate under adversarial prompts | Unknown | M | Test with ambiguous queries in golden set; add output parser if needed | Eng | Day 2 |
| Pinecone query latency under load (cold start) | Unknown | M | Benchmark with `time` wrapper during integration test | Eng | Day 2 |

---

## 4. Architecture Decision Record

### 4.1 Vector Database

**Decision:** Pinecone (Managed Serverless)

| Criterion | Pinecone | ChromaDB | Qdrant |
|-----------|----------|----------|--------|
| Persistent disk required | No (managed) | Yes (embedded) | No (self-hosted or cloud) |
| Railway compatibility | ✅ Full | ❌ No persistent disk on Railway | ✅ but adds infra |
| Free tier | ✅ Serverless | ✅ Local only | ✅ Cloud free tier |
| Setup time | ~10 minutes | ~5 minutes | ~30 minutes |
| Production reliability | High (Anthropic, OpenAI use it) | Low (research-grade) | Medium |
| Metadata filtering | ✅ Rich | ✅ Basic | ✅ Rich |

**Rejected:** ChromaDB — Railway has no persistent disk; ChromaDB's embedded mode requires local file storage, which resets on Railway redeploys.
**Rejected:** Qdrant self-hosted — adds Docker infra management overhead that consumes sprint time better spent on features.

---

### 4.2 Embedding Model

**Decision:** OpenAI `text-embedding-3-small` (1536 dimensions)

| Criterion | text-embedding-3-small | text-embedding-3-large | Voyage Code 2 |
|-----------|----------------------|----------------------|----------------|
| Dimensions | 1536 | 3072 | 1536 |
| Cost per 1M tokens | $0.02 | $0.13 | $0.12 |
| Code understanding quality | Sufficient for paragraph-level | Marginal gain for this scale | Optimized for code |
| API availability | ✅ Immediate | ✅ Immediate | Requires separate account |
| Pinecone dimension match | ✅ Native | Requires config change | ✅ Native |

**Rejected:** text-embedding-3-large — 6.5x more expensive; paragraph-level COBOL retrieval does not require the extra precision.
**Rejected:** Voyage Code 2 — requires separate API account and billing; marginal quality gain does not justify sprint time for account setup.

---

### 4.3 Retrieval / Reranking Strategy

**Decision:** Dense vector retrieval (Pinecone cosine, top-k=10) + keyword overlap reranker (custom)

| Criterion | Dense only | Dense + keyword reranker | Full hybrid (BM25 + dense) |
|-----------|------------|--------------------------|---------------------------|
| Implementation time | 1 hour | 2 hours | 4–6 hours |
| Handles COBOL-specific terms | Moderate | High (paragraph names boost) | High |
| Precision@5 expected | ~60% | ~75% | ~78% |
| Infrastructure required | Pinecone | Pinecone + custom code | Pinecone + sparse index |
| MVP feasibility | ✅ | ✅ | ❌ (time) |

**Rejected:** Dense-only — COBOL paragraph names (`CALCULATE-INTEREST`, `OPEN-MASTER-FILE`) are highly specific tokens that keyword scoring handles better than embeddings alone.
**Rejected:** Full BM25 hybrid — requires maintaining a separate sparse index (Pinecone sparse or external); doubles infrastructure complexity for ~3% precision gain.

---

### 4.4 Chunking Strategy

**Decision:** Primary — syntax-aware paragraph-level; Fallback — fixed-size 400 lines / 40-line overlap

| Criterion | Paragraph-level | Section-level | Fixed-size only |
|-----------|-----------------|---------------|-----------------|
| Business logic boundary | ✅ Perfect (COBOL paragraphs = business units) | Coarse (sections group many paragraphs) | ❌ Splits mid-logic |
| Metadata precision | ✅ paragraph_name, start_line, end_line | Moderate | Line numbers only |
| Parser complexity | Medium (regex + state machine) | Low | Low |
| Fallback needed | ✅ For irregular files | ✅ | No |
| Retrieval quality | Highest | Moderate | Lowest |

**Rejected:** Section-level only — too coarse; "PROCEDURE DIVISION" as a single chunk defeats the purpose of retrieval.
**Rejected:** Fixed-size only — slices through COBOL `PERFORM` loops and `MOVE` blocks mid-statement; citation line numbers become meaningless.

---

### 4.5 Backend Framework

**Decision:** Python 3.12 + FastAPI

| Criterion | FastAPI | Flask | Node.js/Express |
|-----------|---------|-------|-----------------|
| Async SSE streaming | ✅ Native `StreamingResponse` | Requires workaround | ✅ |
| Pydantic models | ✅ Built-in | External | External |
| Type safety | ✅ Full | Partial | TypeScript only |
| Python ML ecosystem | ✅ Direct | ✅ Direct | ❌ subprocess needed |
| Railway deploy | ✅ Dockerfile | ✅ | ✅ |

**Rejected:** Flask — no native async; SSE streaming requires hacks; no built-in request/response validation.
**Rejected:** Node.js/Express — Python ecosystem (LangChain, OpenAI SDK, numpy) is first-class; Node bridges add latency and complexity.

---

### 4.6 Frontend Framework

**Decision:** Next.js 14 App Router + TypeScript

| Criterion | Next.js 14 App Router | Vite + React SPA | Vanilla HTML |
|-----------|----------------------|------------------|--------------|
| Server Components (performance) | ✅ | ❌ | ❌ |
| Vercel deployment | ✅ Native | ✅ | ✅ |
| NextAuth.js support | ✅ Native | Requires adapter | ❌ |
| TypeScript | ✅ | ✅ | ❌ |
| Code splitting | ✅ Automatic | Manual | ❌ |

**Rejected:** Vite + React SPA — NextAuth.js has no official SPA adapter; implementing GitHub OAuth from scratch wastes sprint time.
**Rejected:** Vanilla HTML — no type safety, no component reuse, not credible for an A+ engineering submission.

---

### 4.7 Deployment Model

**Decision:** Railway (backend) + Vercel (frontend), auto-deploy from `main` branch

| Criterion | Railway+Vercel | AWS (ECS+S3) | Fly.io+Vercel |
|-----------|---------------|--------------|----------------|
| Time to first deploy | < 30 min | 2–3 hours | 1 hour |
| GitHub integration | ✅ Native | Manual CI/CD | ✅ |
| Cold start concern | Low (Railway keeps alive) | None (ECS) | Low |
| Cost (dev scale) | Free / $5 | $15–50/month | Free |
| Sprint overhead | Minimal | High | Low |

**Rejected:** AWS — IAM, ECS task definitions, and ALB configuration consumes 2–3 hours we do not have.
**Rejected:** Fly.io — less documentation for FastAPI; Railway is better documented for Python workloads.

---

### 4.8 Observability and Evaluation

**Decision:** Structured JSON logging (Python `logging` module) + manual golden query evaluation set

| Criterion | Structured logging | Datadog | Prometheus + Grafana |
|-----------|-------------------|---------|----------------------|
| Setup time | < 1 hour | 2–3 hours | 3–4 hours |
| Cost | Free | $15+/month | Self-host overhead |
| Retrieval quality measurement | Manual golden queries | No | No |
| Latency tracking | ✅ Per-request log | ✅ APM | ✅ |
| Sprint appropriate | ✅ | ❌ | ❌ |

**Rejected:** Datadog — cost and setup time disproportionate to sprint length; logs are sufficient for demo.
**Rejected:** Prometheus + Grafana — self-hosting adds infra overhead; we need time on features, not dashboards.

---

## 5. Work Breakdown Structure

### Phase 0 — Infrastructure (Day 1, Hours 0–4)

| Task ID | Description | Branch | Deps | Parallel? | Est (ideal / risk-adj hrs) | Owner Role | Artifact | Acceptance Criteria | Definition of Done |
|---------|-------------|--------|------|-----------|---------------------------|------------|----------|--------------------|--------------------|
| P0-1 | Clone gnucobol-contrib to data/ and audit file types + LOC count | — (local) | — | Y | 0.5 / 0.5 | Eng | LOC audit report in docs/ | File count ≥ 50, LOC ≥ 10,000 confirmed | Report committed |
| P0-2 | Create Pinecone index (1536 dims, cosine, serverless) | — | — | Y | 0.5 / 0.5 | Eng | Pinecone console screenshot | Index shows "Ready" status | Index name added to .env |
| P0-3 | Create GitHub OAuth App and record client ID/secret | — | — | Y | 0.5 / 0.5 | Eng | OAuth app in GitHub settings | Callback URL configured | Secrets in .env.local |
| P0-4 | Verify Railway + Vercel accounts and deploy stubs | codex/infra-deploy | P0-1 | N | 1.0 / 2.0 | Eng | Public URL for both services | Both return HTTP 200 | URLs recorded in README |
| P0-5 | Set all secrets in Railway + Vercel dashboards | — | P0-2,P0-3,P0-4 | N | 0.5 / 1.0 | Eng | Env vars configured | Backend can reach Pinecone + OpenAI | Integration smoke test passes |

---

### Phase 1 — Ingestion Pipeline (Day 1, Hours 4–16)

| Task ID | Description | Branch | Deps | Parallel? | Est (ideal / risk-adj hrs) | Owner Role | Artifact | Acceptance Criteria | Definition of Done |
|---------|-------------|--------|------|-----------|---------------------------|------------|----------|--------------------|--------------------|
| P1-1 | Write tests for file_scanner (discover .cob/.cbl/.cpy recursively) | codex/ingestion-scanner | P0-1 | N | 0.5 / 0.5 | Eng | `tests/unit/test_file_scanner.py` | Tests fail (red) | Test file committed, CI shows failing tests |
| P1-2 | Implement file_scanner to pass tests | codex/ingestion-scanner | P1-1 | N | 1.0 / 1.5 | Eng | `app/core/ingestion/file_scanner.py` | All P1-1 tests pass; scans data/ and returns correct file list | `pytest tests/unit/test_file_scanner.py` green |
| P1-3 | Write tests for preprocessor (encoding norm, whitespace, column stripping) | codex/ingestion-preprocessor | P0-1 | Y | 0.5 / 0.5 | Eng | `tests/unit/test_preprocessor.py` | Tests fail | Test file committed |
| P1-4 | Implement preprocessor to pass tests | codex/ingestion-preprocessor | P1-3 | N | 1.0 / 1.5 | Eng | `app/core/ingestion/preprocessor.py` | All P1-3 tests pass; handles EBCDIC, fixed columns, blank lines | Tests green |
| P1-5 | Write tests for naive chunker (fixed-size 400 lines, 40 overlap) | codex/ingestion-chunker-naive | P1-4 | N | 0.5 / 0.5 | Eng | `tests/unit/test_chunker_naive.py` | Tests fail | Test file committed |
| P1-6 | Implement naive chunker to pass tests | codex/ingestion-chunker-naive | P1-5 | N | 1.0 / 1.5 | Eng | `app/core/ingestion/chunker.py` | All tests pass; chunk metadata includes file_path, start_line, end_line | Tests green |
| P1-7 | Write tests for embedder (batch, retry, rate limit) | codex/ingestion-embedder | P1-2 | Y | 0.5 / 0.5 | Eng | `tests/unit/test_embedder.py` | Tests fail (mock OpenAI) | Test file committed |
| P1-8 | Implement embedder (OpenAI text-embedding-3-small, batch 100) | codex/ingestion-embedder | P1-7 | N | 1.5 / 2.0 | Eng | `app/core/ingestion/embedder.py` | All tests pass; batch size 100; exponential backoff on 429 | Tests green |
| P1-9 | Write tests for Pinecone upserter | codex/ingestion-upserter | P1-8 | Y | 0.5 / 0.5 | Eng | `tests/unit/test_upserter.py` | Tests fail (mock Pinecone) | Test file committed |
| P1-10 | Implement Pinecone upserter | codex/ingestion-upserter | P1-9 | N | 1.0 / 1.5 | Eng | `app/core/ingestion/upserter.py` | All tests pass; batches upserts; stores full metadata | Tests green |
| P1-11 | Write ingestion orchestration script | codex/ingestion-script | P1-2,P1-4,P1-6,P1-8,P1-10 | N | 1.0 / 1.5 | Eng | `scripts/ingest.py` | Script ingests gnucobol-contrib; Pinecone shows ≥ 500 vectors | `python scripts/ingest.py` exits 0 |
| P1-12 | Integration test: ingest sample.cob → verify in Pinecone | codex/ingestion-script | P1-11 | N | 1.0 / 1.5 | Eng | `tests/integration/test_ingestion.py` | sample.cob vectors appear in Pinecone with correct metadata | Integration test green (with live keys) |

---

### Phase 2 — Retrieval Pipeline (Day 1, Hours 12–20)

| Task ID | Description | Branch | Deps | Parallel? | Est (ideal / risk-adj hrs) | Owner Role | Artifact | Acceptance Criteria | Definition of Done |
|---------|-------------|--------|------|-----------|---------------------------|------------|----------|--------------------|--------------------|
| P2-1 | Write tests for query_embedder | codex/retrieval-core | P1-8 | Y | 0.25 / 0.5 | Eng | `tests/unit/test_query_embedder.py` | Tests fail | Test committed |
| P2-2 | Implement query_embedder (reuses embedder model) | codex/retrieval-core | P2-1 | N | 0.5 / 0.5 | Eng | `app/core/retrieval/query_embedder.py` | Tests green; returns 1536-dim vector | Tests green |
| P2-3 | Write tests for retriever (Pinecone query, top_k, metadata filter) | codex/retrieval-core | P2-2 | N | 0.5 / 0.5 | Eng | `tests/unit/test_retriever.py` | Tests fail | Test committed |
| P2-4 | Implement retriever | codex/retrieval-core | P2-3 | N | 1.0 / 1.5 | Eng | `app/core/retrieval/retriever.py` | Tests green; returns top-10 chunks with metadata | Tests green |
| P2-5 | Write tests for reranker (keyword overlap scoring) | codex/retrieval-reranker | P2-4 | Y | 0.5 / 0.5 | Eng | `tests/unit/test_reranker.py` | Tests fail; edge cases: empty results, no keyword overlap | Test committed |
| P2-6 | Implement reranker | codex/retrieval-reranker | P2-5 | N | 1.0 / 1.5 | Eng | `app/core/retrieval/reranker.py` | Tests green; mutation test coverage ≥ 70% | Tests + mutation tests green |
| P2-7 | Write tests for answer_generator (citation enforcement, fallback) | codex/retrieval-llm | P2-4 | Y | 0.5 / 0.5 | Eng | `tests/unit/test_answer_generator.py` | Tests fail; includes low-similarity fallback case | Test committed |
| P2-8 | Implement answer_generator (GPT-4o-mini, streaming, citations) | codex/retrieval-llm | P2-7 | N | 1.5 / 2.0 | Eng | `app/core/retrieval/answer_generator.py` | Tests green; fallback returns safe string when score < 0.75 | Tests green |
| P2-9 | Wire /api/v1/query endpoint (validate → retrieve → rerank → generate) | codex/api-query | P2-6,P2-8 | N | 1.0 / 1.5 | Eng | `app/api/v1/endpoints/query.py` | Curl request returns SSE stream with cited chunks | Manual curl test passes |
| P2-10 | Integration test: known query returns expected paragraph | codex/api-query | P2-9 | N | 1.0 / 1.5 | Eng | `tests/integration/test_retrieval.py` | "interest calculation" query returns CALCULATE-INTEREST chunk | Integration test green |

---

### Phase 3 — Authentication (Day 1, Hours 8–14, parallel with Phase 1)

| Task ID | Description | Branch | Deps | Parallel? | Est (ideal / risk-adj hrs) | Owner Role | Artifact | Acceptance Criteria | Definition of Done |
|---------|-------------|--------|------|-----------|---------------------------|------------|----------|--------------------|--------------------|
| P3-1 | Configure NextAuth.js with GitHub provider | codex/auth-nextauth | P0-3 | Y | 1.0 / 1.5 | Eng | `frontend/src/app/api/auth/[...nextauth]/route.ts` | GitHub OAuth login works locally | Login → redirect → session cookie set |
| P3-2 | Write FastAPI JWT validation middleware | codex/auth-fastapi | P3-1 | N | 1.0 / 1.5 | Eng | `app/core/auth/jwt_validator.py` | Unauthenticated request returns 401; valid token passes | Unit test + manual curl test |
| P3-3 | Implement rate limiting middleware (20 req/min per user) | codex/auth-ratelimit | P3-2 | N | 0.5 / 1.0 | Eng | `app/core/auth/rate_limiter.py` | 21st request returns 429 with Retry-After header | Unit test green |
| P3-4 | Add auth gate to frontend (redirect to login if no session) | codex/auth-nextauth | P3-1 | N | 0.5 / 0.5 | Eng | `frontend/src/middleware.ts` | Unauthenticated visit to / redirects to /auth/signin | Browser test passes |

---

### Phase 4 — Frontend MVP (Day 1, Hours 10–20)

| Task ID | Description | Branch | Deps | Parallel? | Est (ideal / risk-adj hrs) | Owner Role | Artifact | Acceptance Criteria | Definition of Done |
|---------|-------------|--------|------|-----------|---------------------------|------------|----------|--------------------|--------------------|
| P4-1 | Create query input page (Server Component shell + Client form) | codex/frontend-query | P3-1 | Y | 1.0 / 1.5 | Eng | `frontend/src/app/page.tsx` | Page renders with input field after login | Visual inspection |
| P4-2 | Implement SSE consumer hook (reads streaming response) | codex/frontend-query | P4-1 | N | 1.0 / 1.5 | Eng | `frontend/src/hooks/useQueryStream.ts` | Hook progressively appends tokens to state | Unit test with mocked EventSource |
| P4-3 | Create CodeResult component (snippet + file:line badge + similarity score) | codex/frontend-components | P4-1 | Y | 1.0 / 1.5 | Eng | `frontend/src/components/CodeResult.tsx` | Shows syntax-highlighted COBOL, file path, line range, score badge | Storybook or visual inspection |
| P4-4 | Wire query form → API call → streaming display | codex/frontend-query | P4-2,P4-3 | N | 1.0 / 1.5 | Eng | Updated `page.tsx` | Full round-trip: query → results + explanation visible | End-to-end browser test |
| P4-5 | Add COBOL syntax highlighting (prism.js or highlight.js) | codex/frontend-components | P4-3 | N | 0.5 / 0.5 | Eng | `frontend/src/lib/highlight.ts` | COBOL keywords render in distinct color | Visual inspection |

---

### Phase 5 — Syntax-Aware Chunker (Day 2, Wednesday G4)

| Task ID | Description | Branch | Deps | Parallel? | Est (ideal / risk-adj hrs) | Owner Role | Artifact | Acceptance Criteria | Definition of Done |
|---------|-------------|--------|------|-----------|---------------------------|------------|----------|--------------------|--------------------|
| P5-1 | Write comprehensive tests for COBOL parser (all DIVISION types, paragraph detection, fallback triggers) | codex/chunker-syntax | P1-6 | N | 1.5 / 2.0 | Eng | `tests/unit/test_chunker_syntax.py` | Tests fail; covers 7-item edge case checklist | Test committed; CI red |
| P5-2 | Implement COBOL syntax-aware chunker (regex + state machine) | codex/chunker-syntax | P5-1 | N | 3.0 / 4.5 | Eng | `app/core/ingestion/chunker.py` (updated) | All P5-1 tests pass; mutation score ≥ 70%; paragraph_name in metadata | Tests green; mutation test green |
| P5-3 | Re-run ingestion with syntax-aware chunker | codex/chunker-syntax | P5-2,P1-11 | N | 0.5 / 1.0 | Eng | Updated Pinecone index | Vector count increases (more granular chunks); spot-check 5 paragraphs | Console output shows new chunk count |
| P5-4 | Re-run golden query set and measure Precision@5 | codex/chunker-syntax | P5-3 | N | 1.0 / 1.5 | Eng | Updated `tests/fixtures/golden_queries.json` | Precision@5 ≥ 70% | Results documented in docs/ |

---

### Phase 6 — Code Understanding Features (Day 2–3)

| Task ID | Description | Branch | Deps | Parallel? | Est (ideal / risk-adj hrs) | Owner Role | Artifact | Acceptance Criteria | Definition of Done |
|---------|-------------|--------|------|-----------|---------------------------|------------|----------|--------------------|--------------------|
| P6-1 | Implement F1: Code Explanation endpoint + UI tab | codex/feature-explain | P2-9,P5-2 | N | 2.0 / 3.0 | Eng | `/api/v1/explain` + ExplainTab component | Given paragraph name, returns plain-English explanation with citations | Demo: "explain CALCULATE-INTEREST" → correct output |
| P6-2 | Write tests for F2: Dependency Mapping parser (CALL/PERFORM/COPY) | codex/feature-deps | P5-2 | Y | 1.0 / 1.5 | Eng | `tests/unit/test_dependency_mapper.py` | Tests fail | Test committed |
| P6-3 | Implement F2: Dependency Mapping (heuristic parser + endpoint + UI) | codex/feature-deps | P6-2 | N | 2.0 / 3.0 | Eng | `app/core/features/dependency_mapper.py` + UI | Parser extracts CALL/PERFORM/COPY references; returns dep list with file:line | Demo: "what does MAIN-PROCEDURE call?" → dep list |
| P6-4 | Implement F3: Business Logic Extraction (prompt template + endpoint + UI) | codex/feature-bizlogic | P2-9 | Y | 1.5 / 2.0 | Eng | `/api/v1/business-logic` + BizLogicTab | Returns business rule summary for financial COBOL paragraphs | Demo: "extract business rules from CALCULATE-TAX" → rule list |
| P6-5 | Write tests for F4: Impact Analysis (reference search across index) | codex/feature-impact | P2-4 | Y | 0.5 / 1.0 | Eng | `tests/unit/test_impact_analyzer.py` | Tests fail | Test committed |
| P6-6 | Implement F4: Impact Analysis (entity search + dependency reverse lookup) | codex/feature-impact | P6-5,P6-3 | N | 2.0 / 3.0 | Eng | `app/core/features/impact_analyzer.py` + UI | "what breaks if INTEREST-RATE changes" → affected file:line list | Demo walkthrough passes |
| P6-7 | Add feature tabs to UI (Explain / Dependencies / Business Logic / Impact) | codex/frontend-features | P6-1,P6-3,P6-4,P6-6 | N | 1.5 / 2.0 | Eng | Updated `page.tsx` + tab components | All 4 tabs switch cleanly; results render for each | Browser walkthrough |

---

### Phase 7 — Evaluation, Polish, and Submission (Day 3–5)

| Task ID | Description | Branch | Deps | Parallel? | Est (ideal / risk-adj hrs) | Owner Role | Artifact | Acceptance Criteria | Definition of Done |
|---------|-------------|--------|------|-----------|---------------------------|------------|----------|--------------------|--------------------|
| P7-1 | Write full golden query set (20 queries + expected results) | codex/evaluation | P5-4 | N | 1.5 / 2.0 | Eng | `tests/fixtures/golden_queries.json` (complete) | 20 queries, each with expected paragraph_name and file_path | File committed |
| P7-2 | Run automated Precision@5 evaluation script | codex/evaluation | P7-1 | N | 1.0 / 1.5 | Eng | `scripts/evaluate.py` | Script outputs Precision@5 score; target ≥ 70% | Score ≥ 70% printed and logged |
| P7-3 | Write RAG Architecture doc | — | P7-2 | Y | 1.5 / 2.0 | Eng | `docs/RAG_ARCHITECTURE.md` | Covers all 6 required sections from project spec | Doc committed |
| P7-4 | Write AI Cost Analysis | — | P7-2 | Y | 1.0 / 1.5 | Eng | `docs/COST_LOG.md` (finalized) | Dev spend + 100/1k/10k/100k projections | Doc committed |
| P7-5 | Record demo video (3–5 min) | — | P6-7 | N | 1.0 / 2.0 | Eng | Video file / YouTube link | Shows login, all 4 features, citations, latency | Link in README |
| P7-6 | Final deployment check (Railway + Vercel health) | — | P5-3,P6-7 | N | 0.5 / 1.0 | Eng | — | Both services healthy; end-to-end query completes | Manual smoke test |
| P7-7 | Social post (X or LinkedIn) | — | P7-5 | N | 0.5 / 0.5 | Eng | Post link | Posted with screenshots + @GauntletAI tag | Post URL in README |
| P7-8 | Submit Pre-Search document (finalized) | — | All | N | 1.0 / 1.0 | Eng | Pre-Search doc | All 16 checklist items answered | Submitted |

---

## 6. Parallel Execution Plan

### Critical Path

```
P0-1 → P1-1 → P1-2 → P1-5 → P1-6 → P1-11
                              ↓
P1-7 → P1-8 → P1-9 → P1-10 → P1-12
                              ↓
                    P2-1 → P2-2 → P2-3 → P2-4 → P2-5 → P2-6
                                                         ↓
                                          P2-7 → P2-8 → P2-9 → P2-10
                                                                ↓
                                                    P5-1 → P5-2 → P5-3 → P5-4
                                                                          ↓
                                                    P6-1 → P6-3 → P6-6 → P6-7
                                                                          ↓
                                                              P7-1 → P7-2 → P7-5
```

**Critical path length:** ~32 ideal hours (risk-adjusted: ~44 hours)
**Timeline fits:** Tuesday MVP by Hour 20; G4 features by Hour 40; Final by Hour 60+.

---

### Parallel Workstreams

```
Day 1 (Hours 0–20)
═══════════════════════════════════════════════════════════════
Stream A (Ingestion):    P0-1 → P1-1,P1-3,P1-7 (parallel) → P1-2,P1-4,P1-8 → P1-6 → P1-10 → P1-11
Stream B (Auth):         P0-3 → P3-1 → P3-2 → P3-3,P3-4 (parallel)
Stream C (Frontend):     P4-1 → P4-2,P4-3 (parallel) → P4-4 → P4-5
Stream D (Infra):        P0-2 → P0-4 → P0-5

Day 2 (Hours 20–40)
═══════════════════════════════════════════════════════════════
Stream A (Retrieval):    P2-1 → P2-2 → P2-3,P2-7 (parallel) → P2-4,P2-8 → P2-6,P2-9 → P2-10
Stream B (Chunker):      P5-1 → P5-2 → P5-3 → P5-4
Stream C (Features):     P6-2 → P6-3 (blocks P6-6)
                         P6-4 (parallel with P6-2)
                         P6-5 → P6-6

Day 3–5 (Hours 40–72+)
═══════════════════════════════════════════════════════════════
Stream A (Features):     P6-1 → P6-7
Stream B (Evaluation):   P7-1 → P7-2
Stream C (Docs):         P7-3, P7-4 (parallel)
Stream D (Demo+Submit):  P7-5 → P7-6 → P7-7 → P7-8
```

---

### Merge Integration Strategy

**Conflict Prevention Rules:**

1. **Branch isolation is strict.** No two branches touch the same file. If two features need to touch the same file, they are sequenced, not parallelized.
2. **`app/core/ingestion/chunker.py` is a hot zone.** P1-6 (naive chunker) creates it; P5-2 (syntax chunker) replaces it. These must be sequential — P5-1/P5-2 start only after P1-11 is merged.
3. **`app/api/v1/router.py` is a hot zone.** Each feature branch adds one route. Merge in strict order: P2-9, then P6-1, P6-3, P6-4, P6-6.
4. **Merge window:** All feature PRs merged to `dev` by 8 PM daily. `dev` → `main` merged by 9 PM.
5. **Rebase before PR.** Every branch rebases onto `dev` before opening a PR.
6. **No PR open for more than 4 hours.** If a PR is blocked, escalate immediately.

---

### Integration Checkpoints

| Checkpoint | When | Pass Criteria |
|------------|------|---------------|
| IC-1: Ingestion works | Day 1, Hour 12 | sample.cob in Pinecone with metadata |
| IC-2: Retrieval works | Day 1, Hour 18 | curl to /query returns chunks |
| IC-3: Full MVP deployed | Day 1, Hour 20 | Public URL shows query → answer |
| IC-4: Syntax chunker in production | Day 2, Hour 30 | Pinecone re-indexed; precision test run |
| IC-5: All 4 features live | Day 3, Hour 48 | All tabs working in browser |
| IC-6: Evaluation complete | Day 4 | Precision@5 ≥ 70% documented |
| IC-7: Final submission ready | Day 5 (Sunday) | All deliverables committed and linked |

---

## 7. Test Strategy

### TDD Workflow Policy

```
1. Engineer writes test file with all edge cases (file committed, CI shows red)
2. Engineer writes minimum code to pass tests
3. Run: pytest -m "not integration" -q → must be green
4. Run: ruff check . && ruff format --check . && mypy app/ --strict → must be clean
5. PR opened only when all checks green
6. Integration tests run in separate CI job (requires secrets)
```

### Test Pyramid

| Layer | Target % of total tests | Tools | Execution speed |
|-------|------------------------|-------|-----------------|
| Unit | 70% | pytest + unittest.mock | < 30 seconds |
| Integration | 20% | pytest + live Pinecone/OpenAI | 2–5 minutes |
| End-to-End | 10% | Playwright (browser smoke) | 5–10 minutes |

### Coverage Targets

| Component | Line Coverage | Branch Coverage | Critical Path Coverage |
|-----------|--------------|-----------------|----------------------|
| `chunker.py` | ≥ 90% | ≥ 85% | 100% (all DIVISION types) |
| `reranker.py` | ≥ 85% | ≥ 80% | 100% (empty, tie, single) |
| `answer_generator.py` | ≥ 80% | ≥ 75% | 100% (fallback path) |
| `retriever.py` | ≥ 80% | ≥ 75% | 100% |
| `embedder.py` | ≥ 80% | ≥ 70% | 100% (retry path) |
| Frontend components | ≥ 70% (Jest) | ≥ 65% | — |
| Overall backend | ≥ 80% | ≥ 75% | — |

### Mutation Testing Targets

| File | Mutation Score Target | Tool |
|------|-----------------------|------|
| `chunker.py` | ≥ 70% | mutmut |
| `reranker.py` | ≥ 70% | mutmut |
| `answer_generator.py` | ≥ 70% | mutmut |

Run: `mutmut run --paths-to-mutate app/core/` → `mutmut results`

### Edge-Case Matrix by Component

#### Chunker
| Case | Expected Behavior |
|------|------------------|
| Well-formed COBOL (4 DIVISIONs, N paragraphs) | N paragraph chunks + 3 division header chunks |
| File with PROCEDURE DIVISION only | All content as one chunk with fallback |
| Empty file | Returns empty list, no error |
| File with no paragraph labels | Fixed-size fallback triggered |
| File > 10,000 lines | Chunked correctly; no memory error |
| Non-COBOL file accidentally passed | ValueError raised with filename |
| COBOL with inline comments only | Comments preserved in chunk text |

#### Reranker
| Case | Expected Behavior |
|------|------------------|
| Query has exact paragraph name match | That chunk scores highest |
| Query has no keyword overlap | Original vector order preserved |
| Empty result list | Returns empty list |
| All chunks have same score | Order is deterministic (stable sort) |
| Single chunk in input | Returns that chunk |

#### Answer Generator
| Case | Expected Behavior |
|------|------------------|
| Top chunk score ≥ 0.75, context valid | Streaming answer with citations |
| Top chunk score < 0.75 | Safe fallback message, no answer generated |
| OpenAI API timeout | Retry once; then HTTPException 503 |
| Empty retrieved chunks | Fallback message |
| Context exceeds token budget | Truncate to last N chunks that fit |

### Golden Query Evaluation Set

20 queries covering all 4 feature types. Stored in `tests/fixtures/golden_queries.json`.

| Query Type | Count | Example Query | Expected Result |
|------------|-------|---------------|-----------------|
| Code Explanation | 5 | "Explain CALCULATE-INTEREST" | Interest calculation paragraph with formula |
| Dependency Mapping | 5 | "What does MAIN-PROCEDURE call?" | PERFORM targets listed with file:line |
| Business Logic | 5 | "What are the loan validation rules?" | Validation conditions extracted |
| Impact Analysis | 5 | "What breaks if INTEREST-RATE changes?" | Files/paragraphs that reference INTEREST-RATE |

**Target:** Precision@5 ≥ 70% = 14 of 20 queries return expected result in top 5.

### Required Quality Gates to Merge

| Gate | Tool | Required result |
|------|------|-----------------|
| Unit tests | pytest | 100% pass (zero failures) |
| Type check | mypy --strict | Zero errors |
| Linting | ruff check | Zero warnings |
| Format | ruff format --check | No diffs |
| Coverage | pytest-cov | ≥ 80% overall |
| TypeScript | tsc --noEmit | Zero errors |
| ESLint | eslint --max-warnings 0 | Zero warnings |
| Prettier | prettier --check | No diffs |
| Secret scan | gitleaks | No secrets detected |

---

## 8. Quality Engineering and Review System

### PR Size Policy

| PR Size | Lines changed | Review SLA |
|---------|--------------|------------|
| Small (preferred) | < 150 lines | 15 minutes |
| Medium | 150–400 lines | 30 minutes |
| Large (flag for split) | > 400 lines | Split before merge |

**Rule:** No PR merges until the author has self-reviewed the diff line-by-line.

### Required PR Template Fields

All PRs must complete:
1. **Scope doc reference** — link to `docs/scopes/` entry or inline answers to 7 scope questions
2. **Failing test link** — GitHub permalink to the committed failing test (proves TDD followed)
3. **Test edge cases covered** — checklist: happy path, empty, single, large, boundary, invalid type, failure path
4. **Manual test results** — screenshot or curl output showing the feature works
5. **Breaking changes** — explicit yes/no; if yes, describe migration
6. **CI status** — all green before merge (link to passing CI run)

### Static Analysis and Type Checks

| Check | Tool | Config |
|-------|------|--------|
| Python linting | ruff | `backend/pyproject.toml` |
| Python formatting | ruff format | `backend/pyproject.toml` |
| Python type check | mypy --strict | `backend/pyproject.toml` |
| TypeScript type check | tsc --noEmit | `frontend/tsconfig.json` |
| TypeScript linting | eslint | `frontend/.eslintrc.json` |
| TypeScript formatting | prettier | `frontend/.prettierrc` |

### Security Checks

| Check | Tool | Trigger |
|-------|------|---------|
| Secret scan | gitleaks | Pre-commit + CI |
| Dependency vulnerabilities | pip-audit (backend), npm audit (frontend) | CI weekly |
| Input sanitization | Pydantic validation | Per-request |
| CORS | FastAPI CORSMiddleware | Runtime; Vercel domain only |
| Auth enforcement | JWT middleware | Per-request |
| Rate limiting | In-memory rate limiter | Per-request |
| Query injection | Strip control chars, limit 512 tokens | Preprocessor |

### Reliability Checks

| Concern | Implementation | Verified By |
|---------|----------------|-------------|
| OpenAI timeout | 30s timeout + 3 retries, exponential backoff | Unit test with mock |
| Pinecone timeout | 10s timeout + 1 retry | Unit test with mock |
| Similarity threshold | < 0.75 → fallback, no LLM call | Unit test: low-score case |
| Rate limit | 429 + Retry-After header | Unit test: 21st request |
| Empty results | Returns fallback message | Unit test: empty input |
| Large file ingestion | No OOM on 10,000+ LOC file | Integration test |

### Release Readiness Checklist

Before merging `dev` → `main` (deploy):

- [ ] All CI checks green
- [ ] Integration checkpoint IC-N passed
- [ ] Railway backend deployed and returning 200 on /health
- [ ] Vercel frontend deployed and showing login page
- [ ] End-to-end query completes successfully from public URL
- [ ] No secrets in diff (gitleaks clean)
- [ ] COST_LOG.md updated with today's spend

---

## 9. Observability, Evaluation, and Metrics

### Structured Log Format (per request)

```json
{
  "request_id": "uuid",
  "user_id": "github_user_id",
  "query": "explain CALCULATE-INTEREST",
  "feature": "explain",
  "embed_latency_ms": 120,
  "pinecone_latency_ms": 85,
  "rerank_latency_ms": 5,
  "llm_latency_ms": 1800,
  "total_latency_ms": 2010,
  "top_score": 0.91,
  "chunks_retrieved": 10,
  "chunks_after_rerank": 5,
  "fallback_triggered": false,
  "input_tokens": 1200,
  "output_tokens": 320,
  "cost_usd": 0.000254,
  "status": "success"
}
```

### Dashboards and Alerts

| Metric | Baseline Target | Stop-Ship Threshold | Alert Trigger |
|--------|----------------|--------------------|--------------  |
| P50 total latency | < 2.0 seconds | > 5.0 seconds | P95 > 3.0 seconds |
| P95 total latency | < 3.0 seconds | > 6.0 seconds | 3 consecutive failures |
| Retrieval Precision@5 | > 70% | < 50% | Post-deploy eval run |
| Fallback rate | < 15% of queries | > 40% | Spike in 5-minute window |
| Citation correctness | > 90% | < 70% | Manual spot-check weekly |
| Ingestion throughput | > 2,000 LOC/min | < 500 LOC/min | Timed ingestion run |
| Error rate (5xx) | < 1% of requests | > 5% | Any 5xx in prod |
| Cost per query | < $0.005 | > $0.02 | Daily cost log review |

### Retrieval Improvement Experiment Design

| Experiment | Hypothesis | Control | Treatment | Success Metric |
|------------|------------|---------|-----------|----------------|
| Keyword reranker weight tuning | Higher COBOL keyword boost improves Precision@5 | weight = 0.3 | weight = 0.5 | Precision@5 delta |
| Context window expansion | ±20 lines context (vs ±10) improves LLM citation quality | ±10 lines | ±20 lines | Citation accuracy manual eval |
| Top-k variation | top_k=15 (vs 10) improves recall without hurting precision | top_k=10 | top_k=15 | Precision@5, latency |
| Similarity threshold | 0.70 threshold (vs 0.75) reduces unhelpful fallbacks | threshold=0.75 | threshold=0.70 | Fallback rate, user satisfaction |

---

## 10. Cost Model and Scale Plan

### Development Cost Tracking

All API calls logged with token count and cost to `docs/COST_LOG.md` daily.

**Estimate — Total Dev Spend:**
- Ingestion (one-time, 10k LOC, ~150k tokens at $0.02/1M): **$0.003**
- Dev queries during testing (~500 queries × 1,500 tokens LLM at GPT-4o-mini pricing $0.15/1M input, $0.60/1M output): **~$0.25**
- Re-ingestion runs (×3 for chunker iterations): **$0.009**
- Golden query evaluation (20 queries × 3 runs): **$0.10**
- **Total estimated dev spend: < $1.00**

### Monthly Production Cost Projections

Assumptions:
- 5 queries/user/day
- 1,200 tokens input (3–5 chunks + prompt) + 400 tokens output per query
- Embedding cost: $0.02/1M tokens; GPT-4o-mini: $0.15/1M input, $0.60/1M output
- Pinecone serverless: ~$0.096/1M read units, $0.08/1M write units

| Scale | Users | Queries/Day | Embed Cost/Mo | LLM Cost/Mo | Pinecone/Mo | Total/Mo |
|-------|-------|-------------|--------------|-------------|-------------|----------|
| Demo | 10 | 50 | < $0.01 | $0.15 | Free tier | < $1 |
| 100 users | 100 | 500 | $0.05 | $1.50 | $0.15 | ~$2–3 |
| 1k users | 1,000 | 5,000 | $0.50 | $15 | $1.50 | ~$18–25 |
| 10k users | 10,000 | 50,000 | $5 | $150 | $15 | ~$175–200 |
| 100k users | 100,000 | 500,000 | $50 | $1,500 | $150 | ~$1,700–2,000 |

### Sensitivity Analysis

| Scenario | Assumption Change | Impact on 1k-user monthly cost |
|----------|------------------|-------------------------------|
| Best case | 2 queries/user/day | ~$8/mo |
| Expected | 5 queries/user/day | ~$20/mo |
| Worst case | 20 queries/user/day + long context | ~$90/mo |

### Cost Control Levers and Trigger Thresholds

| Lever | Trigger | Action |
|-------|---------|--------|
| Cache embeddings for repeated queries | > 100 queries/day | Add Redis cache; skip re-embedding identical queries |
| Reduce top_k | Cost > $0.01/query | Drop from 10 to 5; accept minor precision loss |
| Switch to GPT-3.5-turbo | LLM cost > 80% of total | Evaluate quality degradation first |
| Upgrade Pinecone tier | Monthly Pinecone > $50 | Move to Pinecone Standard |
| Hard rate limit | Single user > 100 queries/day | Reduce per-user limit to 10/day |

---

## 11. Risk Register and Mitigations

| # | Risk | Likelihood | Impact | Detection Signal | Mitigation | Contingency / Rollback | Owner |
|---|------|------------|--------|-----------------|------------|----------------------|-------|
| R1 | COBOL parser misses paragraph boundaries on non-standard files | Medium | High | Precision@5 < 60% after ingestion | Inspect 10 files manually before writing parser; robust regex state machine | Fall back to fixed-size chunker; re-index; accept lower precision | Eng |
| R2 | Pinecone free tier quota hit during dev | Low | High | API returns 429 or "quota exceeded" | Monitor vector count daily; serverless billing is query-based | Upgrade to paid tier ($70 credit available) | Eng |
| R3 | Railway deploy fails (port, Dockerfile, env) | Medium | High | Deploy log shows build error | Test Dockerfile locally first; deploy stub backend on Day 1 | Revert to previous working Dockerfile; restore env vars | Eng |
| R4 | GitHub OAuth callback misconfigured | Medium | High | Login redirect returns 404 or "invalid callback" | Test OAuth locally with ngrok before deploying; use NextAuth debug mode | Temporarily disable auth for demo window; re-enable before submission | Eng |
| R5 | OpenAI rate limit (429) during ingestion | Medium | Medium | Ingestion script error logs | Exponential backoff already in embedder; batch size capped at 100 | Reduce batch size to 50; add sleep between batches | Eng |
| R6 | GPT-4o-mini citation compliance breaks under edge queries | Medium | Medium | Manual review of 5 demo queries shows hallucinated paths | Citation enforcement in system prompt; output parser validates format | Add post-processing regex to strip uncited claims | Eng |
| R7 | End-to-end latency exceeds 3 seconds | Medium | High | P95 latency log exceeds 3s | Profile per-component latency daily; target: embed < 200ms, Pinecone < 100ms, LLM < 2s | Cache top-5 most common queries; reduce context to 3 chunks | Eng |
| R8 | Pre-commit hook blocks commit during time crunch | Low | Low | Hook failure in terminal | All hooks tested on Day 1 against sample files | `git commit --no-verify` as emergency bypass (document the debt) | Eng |
| R9 | Demo video records a bug or poor retrieval result | Medium | Medium | Demo walkthrough shows wrong file:line | Record demo only after Precision@5 ≥ 70% confirmed; use known-good queries | Re-record with scripted query set | Eng |
| R10 | gnucobol-contrib has < 10,000 LOC | Low | High | LOC audit on Day 1 returns low count | Audit before writing any code | Add second COBOL repo (e.g., GnuCOBOL compiler itself) | Eng |
| R11 | Secret accidentally committed | Low | Critical | gitleaks pre-commit hook fires | All secrets in .env (gitignored); pre-commit hook enforced | Rotate all affected keys immediately; force-push to remove from history | Eng |
| R12 | Schedule slip: feature not done by Wednesday G4 | Medium | Medium | Daily planning review shows task backlog | Ruthless scope enforcement; non-goal list is enforced | Drop polish features; keep 4 features working, even if rough | Eng |

---

## 12. Delivery Timeline and Milestones

### Day-by-Day Plan

| Day | Hours | Focus | Key Deliverables | Milestone Gate |
|-----|-------|-------|-----------------|----------------|
| Day 1 (Mon/Tue) | 0–4 | Infrastructure, repo audit, secrets setup | Pinecone index, OAuth app, stubs deployed | IC-1: Both services return 200 |
| Day 1 (Mon/Tue) | 4–12 | Ingestion pipeline (scanner → preprocessor → chunker → embedder → upserter) | All ingestion unit tests green; gnucobol-contrib indexed | IC-2: Vectors visible in Pinecone |
| Day 1 (Mon/Tue) | 8–14 | Auth (parallel with ingestion) | NextAuth + FastAPI JWT + rate limiter | Auth round-trip works locally |
| Day 1 (Mon/Tue) | 12–20 | Retrieval API + Frontend MVP | /query endpoint streaming; basic UI deployed | **MVP GATE (Tuesday): Public URL live** |
| Day 2 (Wed) | 20–30 | Syntax-aware chunker + re-ingestion | Chunker tests green; Pinecone re-indexed | IC-4: Precision@5 measured |
| Day 2 (Wed) | 28–40 | All 4 code understanding features | F1–F4 endpoints + UI tabs | IC-5: All features demo-able |
| Day 3 (Thu) | 40–50 | Polish, error handling, UI improvements | Syntax highlighting, fallback UX, score badges | Demo walkthrough clean |
| Day 4 (Fri) | 50–58 | Evaluation, golden query set, documentation | Precision@5 ≥ 70%; RAG doc + Cost doc | IC-6: Evaluation complete |
| Day 5 (Sat) | 58–66 | Final deployment check, demo video | Video recorded; all docs committed | IC-7: Submission ready |
| Day 5 (Sun) | 66–72 | Submit, social post, buffer for issues | All deliverables submitted by 10:59 PM CT | **FINAL SUBMISSION** |

### Milestone Gates and Required Evidence

| Milestone | Required Evidence | Approval Before Next Phase |
|-----------|-------------------|--------------------------|
| MVP (Tuesday) | Public Vercel URL; curl shows query response with file:line | Manual smoke test by engineer |
| G4 (Wednesday) | All 4 feature tabs working in browser demo | Demo walkthrough with scripted queries |
| Evaluation | Precision@5 score ≥ 70% printed by evaluate.py | Score committed to docs/ |
| Final (Sunday) | GitHub repo, deployed URL, video link, pre-search doc, RAG doc, cost log all present | Checklist in Section 16 complete |

---

## 13. Execution Runbook

### Daily Planning Ritual (Every Morning, 10 minutes)

1. Check CI status on `dev` branch — is it green?
2. Review today's task IDs from WBS — what's in-progress?
3. Identify any blocked tasks — what's the unblock action?
4. Check COST_LOG.md — is spend within budget?
5. Check Pinecone console — is the index healthy?
6. Start first task. Set a 90-minute focus block.

### Daily Risk Review (Every Evening, 5 minutes)

1. Any R1–R12 risks showing detection signals?
2. Did all integration checkpoints planned for today pass?
3. Is CI green on `dev`?
4. Is the current task pace on schedule for the next milestone?
5. Update COST_LOG.md with today's actual spend.

### Merge Windows

- **12:00 PM:** Merge any morning PRs that are green
- **8:00 PM:** Merge all feature PRs to `dev`; run integration smoke test
- **9:00 PM:** If `dev` smoke test passes → merge `dev` → `main` → monitor Railway/Vercel deploy

### Demo Cadence

- **Day 1 end:** Demo the deployed MVP to yourself — full query round trip
- **Day 2 end:** Demo all 4 features with scripted queries
- **Day 4:** Record final demo video using the scripted query set

### Incident Handling — Broken Build

```
1. Do NOT push more commits to debug on main.
2. Identify failing CI job → read the log output in full.
3. Reproduce the failure locally: pytest / tsc / ruff.
4. Fix in a new branch: fix/<description>.
5. Push fix branch → wait for CI green.
6. Merge fix branch to dev → verify green → merge to main.
7. Incident note: add one line to docs/COST_LOG.md: "[DATE] Build broke because X, fixed by Y, cost Z hours."
```

### Incident Handling — Failed Deploy

```
1. Check Railway/Vercel deploy logs immediately.
2. Most common causes:
   a. Environment variable missing → add in Railway/Vercel dashboard → redeploy
   b. Dockerfile build error → fix locally, push fix branch
   c. Port mismatch → verify PORT=8000 in Railway config
3. Revert: if the broken deploy replaced a working one, push a revert commit.
4. Do not spend > 30 minutes on a deploy issue — simplify the config first.
```

---

## 14. Communication Plan

### Leadership Update Format (Weekly / Per Milestone)

```
Subject: LegacyLens — [Milestone] Status Update

STATUS: ON TRACK / AT RISK / BLOCKED

COMPLETED THIS PERIOD:
- [list of milestone deliverables done]

METRICS:
- Query latency P95: X ms (target: < 3,000 ms)
- Precision@5: X% (target: > 70%)
- Dev spend to date: $X (budget: $20)

RISKS:
- [any R1–R12 risks currently showing detection signals]

NEXT PERIOD:
- [next milestone deliverables]

DECISIONS NEEDED:
- [any open decision requiring approval]
```

### Engineering Update Format (Daily)

```
[DATE] Daily Standup

DONE:
- [task IDs completed with PR links]

IN PROGRESS:
- [task IDs in flight]

BLOCKED:
- [blocker description + unblock action]

CI STATUS: GREEN / RED (link to CI run)
SPEND TODAY: $X
```

### Decision Log Format

```
[DATE] DECISION: [what was decided]
CONTEXT: [why this decision was needed]
OPTIONS CONSIDERED: [A, B, C]
RATIONALE: [why this option was chosen]
OWNER: [who made the decision]
REVERSIBLE: [yes/no — and how to reverse if yes]
```

### Escalation Protocol

| Severity | Condition | Action | Time to resolve |
|----------|-----------|--------|----------------|
| P0 | Deployment is down, submission at risk | Drop all other work; fix immediately | < 2 hours |
| P1 | CI is red, blocking merges | Fix before any new feature work | < 4 hours |
| P2 | A risk shows its detection signal | Activate mitigation plan; note in daily update | < 24 hours |
| P3 | Metric below target but system is live | Log, schedule improvement, continue | < 48 hours |

---

## 15. Context and Token Management Protocol

### Canonical Context Files

| File | Contents | Update Rule |
|------|----------|------------|
| `CLAUDE.md` | Architecture decisions, TDD rules, quality standards, tech debt | Updated only when a decision changes; kept under 200 lines |
| `docs/BUILD_ORDER.md` | This document — task IDs, WBS, timeline | Updated at each milestone completion |
| `docs/COST_LOG.md` | Daily spend log, projection model | Updated daily |
| `docs/scopes/SCOPE_<feature>.md` | Per-feature scope doc | Created before coding each feature |
| `memory/MEMORY.md` | Cross-session project memory | Updated when a stable pattern is confirmed |

### What Goes in Prompt vs. What Is Linked

| What | How to reference |
|------|----------------|
| Current task (< 50 lines of code context) | Include inline in prompt |
| Existing file to modify | Use `Read backend/app/core/X.py` in same session |
| Architecture decisions | Reference CLAUDE.md section by name |
| Test fixtures | Reference by file path: `tests/fixtures/golden_queries.json` |
| Full WBS | Link to `docs/BUILD_ORDER.md — Section 5, Task P5-1` |
| Previous session work | Load from `memory/MEMORY.md` |

### Compact Handoff Format (Cross-Session Context Transfer)

When starting a new session for a new feature:

```
LEGACYLENS CONTEXT HANDOFF — [DATE]

STATUS: MVP deployed at [URL]. Syntax chunker done (P5-2 merged). Features in progress.
CURRENT TASK: P6-2 — dependency mapper tests.
BRANCH: codex/feature-deps
KEY FILES: backend/app/core/ingestion/chunker.py (completed), app/core/retrieval/retriever.py (completed)
OPEN RISK: R6 (citation compliance) — not yet triggered.
COST TO DATE: $X

DO NOT re-read: chunker.py, retriever.py, embedder.py (all done).
NEXT ACTION: Read tests/unit/test_dependency_mapper.py (current failing tests) and implement app/core/features/dependency_mapper.py.
```

### Anti-Bloat Prompt Rules

1. **Never say "look at the codebase"** — always specify the exact file path and line range.
2. **Never explain what you want and then ask for it** — state the task in the first sentence.
3. **Never include more than 2 files' worth of context in a single prompt** — use subagents for research.
4. **Never re-explain architecture that is documented in CLAUDE.md** — reference the document, do not repeat it.
5. **Compact after every research phase** — run `/compact` before writing any implementation code.
6. **One feature = one session** — do not carry Phase 1 implementation context into Phase 2.

---

## 16. Final Approval Packet

### Artifacts Required for Approval

| # | Artifact | Location | Status |
|---|----------|----------|--------|
| 1 | Public Vercel URL (MVP live) | README.md | Pending |
| 2 | Public Railway backend URL (/health returns 200) | README.md | Pending |
| 3 | All CI checks green on main | GitHub Actions | Pending |
| 4 | Demo video (3–5 min, all 4 features) | README.md or Google Drive link | Pending |
| 5 | Precision@5 score ≥ 70% (evaluate.py output) | `docs/RAG_ARCHITECTURE.md` | Pending |
| 6 | RAG Architecture doc (1–2 pages, all 6 sections) | `docs/RAG_ARCHITECTURE.md` | Pending |
| 7 | AI Cost Analysis (dev spend + projections) | `docs/COST_LOG.md` | Pending |
| 8 | Pre-Search document (all 16 checklist items) | Submitted separately | Pending |
| 9 | Social post (X or LinkedIn, @GauntletAI tagged) | Link in README.md | Pending |
| 10 | GitHub repo (public, setup guide, deployed link) | github.com/... | Pending |

### Go / No-Go Checklist (Objective Criteria)

| Criterion | Target | Method | Go? |
|-----------|--------|--------|-----|
| System is publicly accessible | Vercel URL returns 200 | curl | [ ] |
| GitHub OAuth login works | Login → session → query works | Browser test | [ ] |
| Query returns response in < 3 seconds | P95 latency < 3,000 ms | Log file | [ ] |
| All files indexed (100% coverage) | File count in Pinecone = file count in repo | Script output | [ ] |
| Precision@5 ≥ 70% | evaluate.py output ≥ 0.70 | Script | [ ] |
| All 4 features live and demo-able | Manual walkthrough clean | Demo video | [ ] |
| CI is fully green on main | GitHub Actions all green | CI link | [ ] |
| No secrets in repo | gitleaks CI job passes | CI | [ ] |
| All unit tests pass | pytest exit 0 | CI | [ ] |
| Cost within budget | Total spend ≤ $20 | COST_LOG.md | [ ] |
| RAG doc complete | All 6 sections present | Doc review | [ ] |
| Cost analysis complete | Projections for all 4 scales | Doc review | [ ] |
| Demo video submitted | Link in README | README check | [ ] |
| Social post published | Link in README | README check | [ ] |
| Pre-Search submitted | Submission confirmed | Email/form | [ ] |

---

## Appendix A — Top 10 Execution Mistakes to Avoid

1. **Starting feature work before infra is validated.** Deploy the stub backend to Railway on Day 1, Hour 1. If Railway deployment has friction, you want to know before you have 2,000 lines of code to deploy.

2. **Writing the implementation before the test.** The pre-commit hook enforces TDD, but it is tempting to skip under time pressure. Do not. A broken reranker caught by a test in 2 minutes beats a broken demo caught at submission.

3. **Using print() instead of logging.** You will regret this the first time you need to diagnose a latency issue in production. Use `logging.getLogger(__name__)` from the start.

4. **Ignoring type errors with bare `any` or `# type: ignore`.** Mypy strict mode is the guard rail. One untyped Pinecone result dict that you assumed was a list will cause a runtime error during the demo.

5. **Building the syntax-aware chunker before verifying the naive chunker works end-to-end.** The MVP uses naive chunking. Get it working, deployed, and indexed first. The syntax chunker is a Day 2 replacement, not a Day 1 prerequisite.

6. **Making Pinecone and OpenAI calls in unit tests.** Every test that hits a live API is slow, flaky, and costs money. Mock them. Use the fixtures in `tests/conftest.py`.

7. **Not testing the similarity threshold fallback.** The `score < 0.75 → safe message` path is a critical user-facing behavior. If this is untested and breaks, the system will silently hallucinate rather than saying "I don't know."

8. **Letting PRs pile up.** A PR open for 6 hours is a merge conflict waiting to happen. The 4-hour PR limit is strict. Merge or close.

9. **Recording the demo video before Precision@5 is confirmed.** Recording against a bad index makes a bad demo. Confirm ≥ 70% precision first, then record with the scripted query set.

10. **Not updating COST_LOG.md daily.** The cost analysis is a graded deliverable. Reconstructing spend from API dashboards at the end is unreliable. Log it daily, 2 minutes per entry.

---

## Appendix B — First 72-Hour Action Plan

### Hour 0–2: Kickoff (No Code Yet)

- [ ] Clone gnucobol-contrib → run `find . -name "*.cob" -o -name "*.cbl" | wc -l` and `wc -l **/*.cob` → confirm 50+ files, 10k+ LOC → commit audit to `docs/CODEBASE_AUDIT.md`
- [ ] Create Pinecone index: `legacylens-v3`, 1536 dims, cosine, serverless → paste index URL in `.env`
- [ ] Create GitHub OAuth App → callback: `http://localhost:3000/api/auth/callback/github` → paste client ID + secret in `.env.local`
- [ ] Open OpenAI dashboard → confirm API key has quota → paste in `.env`
- [ ] Verify Railway account → create project → note project ID

### Hour 2–6: Ingestion Foundation

- [ ] `git checkout -b codex/ingestion-scanner`
- [ ] Write `tests/unit/test_file_scanner.py` → commit → verify CI red
- [ ] Implement `app/core/ingestion/file_scanner.py` → tests green → PR to dev
- [ ] Parallel: `git checkout -b codex/ingestion-preprocessor` → write + implement preprocessor → PR to dev
- [ ] Merge both PRs → `git checkout -b codex/ingestion-chunker-naive` → write + implement naive chunker → PR

### Hour 6–10: Embedding + Pinecone

- [ ] Write + implement `embedder.py` (mocked tests, real batching)
- [ ] Write + implement `upserter.py` (mocked tests)
- [ ] Write `scripts/ingest.py` — orchestrate: scan → preprocess → chunk → embed → upsert
- [ ] Run ingestion locally against gnucobol-contrib → verify vectors in Pinecone console
- [ ] Commit count to `docs/COST_LOG.md` (first real API spend)

### Hour 10–14: Auth + Retrieval

- [ ] Configure NextAuth.js + GitHub provider → test local login
- [ ] Write + implement JWT validation middleware in FastAPI
- [ ] Write + implement rate limiter (20 req/min)
- [ ] Parallel: write + implement query_embedder, retriever, reranker (mocked tests)
- [ ] Write + implement answer_generator (streaming, citation enforcement, fallback)

### Hour 14–20: API Endpoint + Frontend MVP

- [ ] Wire `/api/v1/query` endpoint → test with curl
- [ ] Build frontend: query input form → SSE hook → CodeResult component → wire to API
- [ ] Deploy: push to main → Railway builds → Vercel builds → verify public URLs
- [ ] **MVP GATE:** Open public URL in browser → log in → query "explain CALCULATE-INTEREST" → verify response with file:line citation appears in < 3 seconds

### Hour 20–36: Syntax Chunker + Features

- [ ] Write comprehensive chunker tests (7-item edge case checklist)
- [ ] Implement syntax-aware COBOL parser (DIVISION/SECTION/PARAGRAPH state machine)
- [ ] Re-run ingestion → verify paragraph_name metadata in Pinecone
- [ ] Run golden query set (subset of 10) → measure initial Precision@5
- [ ] Implement F1 (Explain), F2 (Dependency), F3 (Business Logic), F4 (Impact) — sequential
- [ ] Wire all 4 feature tabs to UI

### Hour 36–72: Polish, Evaluate, Submit

- [ ] Complete 20-query golden set → run evaluate.py → confirm ≥ 70% precision
- [ ] Write RAG Architecture doc
- [ ] Finalize Cost Analysis (add projections to COST_LOG.md)
- [ ] Record 3–5 min demo video (scripted queries, all 4 features)
- [ ] Final deployment check → public URL smoke test
- [ ] Submit pre-search doc, post social, submit by 10:59 PM CT Sunday

---

## Appendix C — Prompt Pack for Claude and Cursor

> Copy-paste these exact prompts. Replace `[BRACKETED]` items with actuals.

---

### C1 — New Feature: Write Tests First

```
Read backend/tests/unit/test_[EXISTING_SIMILAR_TEST].py to understand the test style.
Read backend/app/core/ingestion/chunker.py to understand the module signature.

Now write backend/tests/unit/test_[NEW_MODULE].py.

This test file must:
1. Import the function/class to be implemented (it does not exist yet — the import will fail, proving TDD)
2. Test the happy path
3. Test empty input
4. Test single-element input
5. Test very large input (> 500 items)
6. Test boundary values
7. Test invalid type input (pass a string where int expected)
8. Test the expected failure/exception path

Use unittest.mock to mock all OpenAI and Pinecone calls.
Do not implement any production code. Only the test file.
```

---

### C2 — Implement to Pass Tests

```
Read backend/tests/unit/test_[MODULE].py — these are the failing tests.
Read backend/app/core/ingestion/[CLOSEST_EXISTING_MODULE].py — this is the code style to follow.

Now implement backend/app/core/[PATH]/[MODULE].py to make all tests pass.

Requirements:
- All functions must have docstrings following the 5th-grader rule in CLAUDE.md
- Use logging.getLogger(__name__) — no print()
- Use type annotations on all function signatures
- Use pathlib.Path not os.path
- Use exponential backoff for any external API call
- Do NOT write any tests — only production code

After writing the code, tell me what mypy --strict would flag so I can fix it proactively.
```

---

### C3 — Debug a Failing Test

```
The following test is failing:
[PASTE EXACT TEST FUNCTION]

The error output is:
[PASTE EXACT ERROR]

The implementation file is at backend/app/core/[PATH]/[MODULE].py.
Read that file.

Diagnose the root cause. Do not touch the test file — the tests define correct behavior.
Fix only the implementation file.
Explain your fix in one sentence before writing code.
```

---

### C4 — Wire a FastAPI Endpoint

```
Read backend/app/api/v1/router.py — understand how existing routes are registered.
Read backend/app/core/retrieval/retriever.py — understand the function signature.
Read backend/app/models/query.py — understand the request/response models.

Now implement backend/app/api/v1/endpoints/[FEATURE].py.

The endpoint must:
- Be async def
- Accept a Pydantic request model (not raw dict)
- Call the core function (not implement logic inline)
- Return a Pydantic response model or StreamingResponse for SSE
- Raise HTTPException with the correct status code on errors
- Not import Pinecone or OpenAI directly

Then add the route to router.py. Show me the exact line to add.
```

---

### C5 — Implement a React Component (Frontend)

```
Read frontend/src/components/[EXISTING_COMPONENT].tsx — understand the component style.
Read frontend/src/lib/api.ts — understand how API calls are made.

Now implement frontend/src/components/[NEW_COMPONENT].tsx.

Requirements:
- TypeScript: no bare `any` types
- Named export only (not default export)
- JSDoc comment following the style in CLAUDE.md
- Use Tailwind CSS for styling
- If it makes API calls, use the api.ts wrapper — no raw fetch()
- If it has state, it must be a Client Component with "use client"

Do not create additional helper files. Keep it in one component file.
```

---

### C6 — COBOL Chunker State Machine (Critical Component)

```
Read backend/tests/unit/test_chunker_syntax.py — these are the failing tests.
Read data/gnucobol-contrib/[SAMPLE_FILE].cob — this is real COBOL to understand structure.

Implement backend/app/core/ingestion/chunker.py with a syntax-aware COBOL parser.

The parser must:
1. Use a state machine with states: HEADER, IDENTIFICATION_DIV, ENVIRONMENT_DIV, DATA_DIV, PROCEDURE_DIV, PARAGRAPH
2. Detect DIVISION boundaries by matching "^\s{0,6}[A-Z]+ DIVISION\."
3. Detect PARAGRAPH labels by matching "^[A-Z][A-Z0-9-]+ SECTION\.|^[A-Z][A-Z0-9-]+\." at column 8+ (Area B)
4. Skip sequence numbers in columns 1–6 (fixed-format COBOL)
5. Include start_line, end_line, paragraph_name, division, section in every chunk's metadata
6. Fall back to fixed-size 400-line chunks with 40-line overlap when no structural markers are found
7. Raise ValueError with the filename if the input is not a string

All tests must pass. Mutation score target: ≥ 70%.
Use detailed inline comments explaining each regex pattern — as if explaining to someone who has never seen COBOL.
```

---

### C7 — Evaluation Script

```
Read tests/fixtures/golden_queries.json — understand the query + expected_result format.
Read backend/app/core/retrieval/retriever.py — understand the retriever interface.

Write scripts/evaluate.py.

The script must:
1. Load all queries from golden_queries.json
2. For each query, call the retriever with top_k=5
3. Check if the expected paragraph_name appears in any of the top 5 results' metadata
4. Calculate Precision@5 = (queries with expected result in top 5) / (total queries)
5. Print a summary table: query | expected | found | top result
6. Print final Precision@5 score
7. Exit 0 if Precision@5 ≥ 0.70, exit 1 otherwise

This script will be run in CI. It requires OPENAI_API_KEY and PINECONE_API_KEY to be set.
Do not mock anything — this is a live integration evaluation.
```

---

### C8 — Handoff Prompt (Start New Session)

```
I am continuing work on LegacyLens V3, a RAG system for COBOL code intelligence.

Current status: [PASTE C-HANDOFF FORMAT FROM SECTION 15]

Project rules are in /Users/shruti/Week3/CLAUDE.md — read the Architecture Rules section only (do not read the full file).
The complete task list is in docs/BUILD_ORDER.md — reference by Task ID, do not re-read the full document.

My current task is: [TASK ID] — [TASK DESCRIPTION]
Branch: [BRANCH NAME]

Read these two files to get context: [FILE 1], [FILE 2]
Then proceed with the task. Do not read any other files unless required.
```

---

*End of BUILD_ORDER.md*
*Document owner: Principal Engineer | Gauntlet AI Week 3 | LegacyLens V3*
*Last updated: 2026-03-02 | Next review: At each milestone gate*
