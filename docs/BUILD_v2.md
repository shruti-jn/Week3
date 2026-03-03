# LegacyLens — Build Order (BUILD_v2)

> **One rule before every branch:** Tell Claude "Plan [feature name]" and get a
> written plan approved. Never start coding without an approved plan.
>
> **Key files to know:**
> - `PRD.md` — full architecture, endpoint specs, auth flow
> - `CLAUDE.md` — coding rules, TDD mandate, commit format
> - `docs/scopes/SCOPE_TEMPLATE.md` — fill this before starting each branch
> - `.github/PULL_REQUEST_TEMPLATE.md` — fill this on every PR

---

## Phase 1 — MVP (Tuesday, 24 hours)

**Goal:** A working, deployed system end-to-end. Rough edges are OK.
**Hard gate:** All MVP Done Criteria below must pass before moving to Phase 2.

| # | What to build | Git branch | Blocked by |
|---|--------------|------------|------------|
| 1 | Clone gnucobol-contrib + verify file structure | `chore/project-scaffold` | nothing — do this first |
| 2 | GitHub OAuth login + FastAPI JWT validation | `feature/frontend-auth` | nothing |
| 3 | File scanner — find all .cob / .cbl files | `feature/ingestion-file-scanner` | nothing |
| 4 | Pinecone client wrapper (upsert + query) | `feature/retrieval-pinecone-client` | nothing |
| 5 | API scaffold — stub endpoints returning hardcoded responses | `feature/api-scaffold` | nothing |
| 6 | ⚠️ COBOL chunker — paragraph-level split + fixed-size fallback | `feature/ingestion-cobol-chunker` | #3 file-scanner |
| 7 | Embedding generator — OpenAI batched calls + Pinecone upsert | `feature/ingestion-embedder` | #6 chunker |
| 8 | Reranker — keyword overlap scoring + 0.75 similarity threshold | `feature/retrieval-reranker` | #4 pinecone-client |
| 9 | Answer generator — GPT-4o-mini streaming via SSE | `feature/generation-answer` | nothing |
| 10 | Wire full backend pipeline — replace stubs with real logic | `feature/api-full-pipeline` | #7 #8 #9 |
| 11 | Query UI — search input + results display | `feature/frontend-query-ui` | #2 auth, #5 scaffold |
| 12 | Connect frontend to live API — replace mocks with real calls | `feature/frontend-results-display` | #10 #11 |
| 13 | Deploy — Railway (backend) + Vercel (frontend) | `chore/deployment-config` | #12 |

### What to start right now (no dependencies)
Items **1, 2, 3, 4, 5** can all run in parallel immediately.
Open five branches, plan each one, and work them simultaneously.

### Highest-risk item
Item **6 — COBOL chunker** is the hardest and most likely to take longer than expected.
Plan it early. Give it the most time. Do not leave it until the end.

### Phase 1 Done Criteria
Every box must be checked before Tuesday deadline:
- [ ] All .cob files in gnucobol-contrib are indexed in Pinecone
- [ ] A query returns a code snippet with file path + line number
- [ ] GPT-4o-mini generates an answer with citation
- [ ] Web UI is live and protected by GitHub OAuth login
- [ ] Backend running on Railway, frontend running on Vercel
- [ ] End-to-end query latency < 3 seconds

---

## Phase 2 — G4 Polish (Wednesday, 3 days total)

**Goal:** Syntax-aware chunking, all 4 code-understanding features, evaluation metrics, submission docs.

| # | What to build | Git branch |
|---|--------------|------------|
| 14 | Replace naive chunking with syntax-aware COBOL paragraph parser | `feature/ingestion-syntax-refinement` |
| 15 | Code Explanation feature (plain-English description of a paragraph) | `feature/api-code-features` |
| 16 | Dependency Mapping feature (call graph with file + line refs) | `feature/api-code-features` |
| 17 | Business Logic Extraction feature (identify business rules) | `feature/api-code-features` |
| 18 | Impact Analysis feature (what breaks if X changes) | `feature/api-code-features` |
| 19 | Feature UI panels — tabbed interface for all 4 features | `feature/frontend-feature-tabs` |
| 20 | Golden query evaluation — run 20 queries, measure Precision@5 | `feature/evaluation` |
| 21 | RAG Architecture document (1–2 pages for submission) | `docs/architecture-doc` |
| 22 | AI Cost Analysis (dev spend + 100/1K/10K/100K user projections) | update `docs/COST_LOG.md` |

### Phase 2 Done Criteria
- [ ] Precision@5 > 70% on all 20 golden queries
- [ ] All 4 code-understanding features working end-to-end
- [ ] Syntax-aware chunking deployed and measurably better than naive
- [ ] RAG Architecture doc written and in repo
- [ ] Cost analysis complete with user-scale projections

---

## Phase 3 — GFA Final Submission (Sunday 10:59 PM CT)

**Goal:** Polish, record demo, complete all deliverables, submit.

| # | What to do |
|---|-----------|
| 23 | Fix any failure modes found during Phase 2 evaluation |
| 24 | Finalize observability logging (latency, cost per request) |
| 25 | Record 3–5 minute demo video |
| 26 | Write final Pre-Search document |
| 27 | Write social post (X or LinkedIn, tag @GauntletAI, include screenshots) |
| 28 | Final deployment check — all links live, OAuth works, no 500 errors |

### Submission Checklist (all required)
- [ ] GitHub repo — setup guide + deployed link in README
- [ ] Deployed app — publicly accessible, no login errors
- [ ] Demo video — 3–5 min, shows queries + answers + features
- [ ] Pre-Search document — all 16 items completed
- [ ] RAG Architecture doc — 1–2 pages
- [ ] AI Cost Analysis — dev spend + scale projections
- [ ] Social post — published and live

---

## Parallel Work Map (Visual)

```
Hour 0–2    [chore/project-scaffold] ──────────── merge this before anything else
                       │
Hour 2–6    ┌──────────┼──────────────────────────────────┐
            │          │              │                    │
     [file-scanner] [pinecone-client] [api-scaffold] [frontend-auth]
            │          │
Hour 6–14  [cobol-chunker ⚠️]  [reranker]  [answer-generator]
                  │
Hour 14–18 [embedder]                [frontend-query-ui]
                  │                          │
Hour 18–22 [────────── api-full-pipeline ────┘]
                  │
Hour 22–24 [frontend-results-display] → [deployment] → 🚀 MVP LIVE
```

---

## How to Start Any Branch (the 8-step ritual)

```
1.  git checkout dev && git pull origin dev
2.  git checkout -b feature/<name>
3.  Tell Claude: "Plan feature/<name>"     ← get written plan approved FIRST
4.  Write failing tests ONLY               ← STOP. Show the test file and wait.
    → Wait for explicit approval: "Tests look good, proceed with implementation"
5.  Write implementation to pass the tests
6.  Run locally: cd backend && backend/.venv/bin/pytest -m "not integration" tests/unit/ -v
                 bash scripts/check_coverage.sh
7.  Open PR (DO NOT merge it)              ← Show the PR diff. Wait for approval.
8.  After explicit approval: squash merge to dev
```

**MANDATORY STOP POINTS (agents must never skip these):**
- After step 4: share the test file content and wait for a "proceed" before writing code
- After step 7: share the PR link and wait for approval before merging

Never skip step 3. The plan takes 5 minutes. Skipping it costs hours.
An agent that merges without approval wastes more time than it saves.

---

## Quick Reference — Key Decisions Already Made

| Decision | Choice | Why |
|----------|--------|-----|
| Vector DB | Pinecone serverless | Railway has no persistent disk for ChromaDB |
| Embedding model | text-embedding-3-small (1536 dims) | 5x cheaper than large; quality sufficient |
| LLM | GPT-4o-mini | 15x cheaper than GPT-4o; citation enforcement works equally well |
| Target codebase | OpenCOBOL Contrib | Real business COBOL (payroll/loans) — best demo narrative |
| Chunking strategy | Paragraph-level primary + fixed-size fallback | COBOL paragraphs are natural semantic units |
| Similarity threshold | 0.75 | Below this = not confident enough to answer |
| Answer top-k | 5 chunks | Enough context without hitting token limits |
