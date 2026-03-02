# LegacyLens — Product Requirements Document

## 1. Overview

**LegacyLens** is a RAG-powered code intelligence system that makes large legacy COBOL codebases queryable and understandable through natural language. It indexes a COBOL repository using syntax-aware chunking, stores embeddings in a vector database, retrieves relevant code with file and line references, and generates grounded explanations via LLM.

**One-line pitch:** Ask questions about 40-year-old COBOL code. Get answers with citations.

---

## 2. Problem Statement

Enterprise systems running on COBOL power critical banking, insurance, and government infrastructure. These codebases contain decades of irreplaceable business logic, but few engineers understand them. Onboarding to a legacy codebase takes weeks. LegacyLens reduces that to minutes.

---

## 3. Goals

- Enable developers to find and understand legacy code via natural-language questions
- Return actionable results: relevant snippets + file paths + exact line numbers
- Demonstrate strong RAG architecture with measurable retrieval quality
- Ship a deployed, publicly accessible application within deadline

---

## 4. Non-Goals

- Full code execution, compilation, or runtime tracing
- Complete static analysis or call-graph correctness
- Supporting multiple codebases in MVP (one primary codebase)
- Real-time incremental indexing (batch only for MVP)

---

## 5. Target Users

Engineers new to a legacy COBOL repo who need to quickly locate entry points, understand business logic, trace data flow, and assess change impact.

---

## 6. Success Metrics

| Metric | Target |
|--------|--------|
| Query latency (end-to-end) | < 3 seconds |
| Retrieval precision (Precision@5) | > 70% relevant chunks |
| Codebase coverage | 100% of files indexed |
| Ingestion throughput | 10,000+ LOC in < 5 minutes |
| Answer accuracy | Correct file/line references |

---

## 7. MVP Hard Gate Requirements (24 Hours — Tuesday)

All items required to pass:

- [ ] Ingest GnuCOBOL Contrib codebase (10k+ LOC, 50+ files)
- [ ] Syntax-aware chunking (paragraph-level + fallback)
- [ ] Embeddings generated for all chunks
- [ ] Embeddings stored in Pinecone with metadata
- [ ] Semantic search across the codebase
- [ ] Natural language query interface (web UI)
- [ ] Return relevant code snippets with file path + line numbers
- [ ] Basic answer generation using retrieved context
- [ ] Deployed and publicly accessible

---

## 8. Target Codebase

**GnuCOBOL (OpenCOBOL) Contrib**
- Repository: https://github.com/OCamlPro/gnucobol-contrib
- Language: COBOL (.cob, .cbl, .cpy)
- Scale: 10,000+ LOC across 50+ files
- Why: Real business-style COBOL with clear structural boundaries (DIVISION/SECTION/PARAGRAPH), ideal for syntax-aware chunking and meaningful code understanding demos

---

## 9. System Architecture

### 9.1 Ingestion Pipeline

```
COBOL Files
    ↓
File Discovery (recursive scan, filter .cob/.cbl/.cpy)
    ↓
Preprocessing (encoding normalization, whitespace, comment extraction)
    ↓
Syntax-Aware Chunking (paragraph-level → fallback fixed-size)
    ↓
Metadata Extraction (file_path, start_line, end_line, division, section, paragraph_name)
    ↓
Embedding Generation (OpenAI text-embedding-3-small, batched + parallel)
    ↓
Pinecone Upsert (vectors + metadata)
```

### 9.2 Retrieval Pipeline

```
User Query (natural language)
    ↓
Query Embedding (same model as ingestion)
    ↓
Pinecone Search (top_k=10, optional metadata filtering)
    ↓
Reranking (keyword overlap scoring)
    ↓
Top 5 Selected + Context Expansion (±10 lines)
    ↓
Similarity Threshold Check (≥ 0.75 cosine — else: safe fallback)
    ↓
LLM Answer Generation (GPT-4o-mini, citation-enforced)
    ↓
Response (answer + cited file:line references + code snippets)
```

---

## 10. Chunking Strategy

### Primary: Syntax-Aware (Paragraph-Level)
- Split by COBOL `IDENTIFICATION DIVISION`, `ENVIRONMENT DIVISION`, `DATA DIVISION`, `PROCEDURE DIVISION`
- Within `PROCEDURE DIVISION`: split at paragraph labels (e.g., `CALCULATE-INTEREST.`)
- Preserve complete logical business units
- Store exact `start_line` and `end_line` per chunk

### Fallback: Fixed-Size + Overlap
Triggered when structural boundaries are ambiguous or parsing fails:
- **Chunk size**: 400 lines
- **Overlap**: 40 lines (10%)
- Prevents context fragmentation across irregular legacy formatting

---

## 11. Vector Database

**Pinecone (Managed Serverless)**

| Setting | Value |
|---------|-------|
| Similarity metric | Cosine |
| Dimensions | 1536 (matching text-embedding-3-small) |
| Metadata fields | `repo`, `file_path`, `start_line`, `end_line`, `division`, `section`, `paragraph_name`, `language` |

Metadata filtering used to restrict retrieval by file, division, or paragraph when relevant.

Hybrid search not implemented for MVP; lexical reranking approximates hybrid behavior while maintaining simplicity.

---

## 12. Embedding Model

**OpenAI `text-embedding-3-small`**
- Dimensions: 1536
- Cost: $0.02 per 1M tokens
- Single model used for both code chunks and user queries (ensures semantic alignment)
- Batched API calls with parallelization to meet <5-minute ingestion target

---

## 13. LLM and Answer Generation

**GPT-4o-mini (OpenAI API)**

### Guardrails
- Only use retrieved context — no speculative answers
- Always cite `file_path:start_line-end_line` in responses
- If top similarity score < 0.75 → return: `"No relevant logic found in indexed code."`
- Streaming enabled for responsive UI experience

---

## 14. Framework

**LangChain (Selective Use) + Custom Components**

| Component | Approach |
|-----------|----------|
| Pinecone integration | LangChain `PineconeVectorStore` |
| Retriever wrapper | LangChain retriever |
| Chunking | Custom (syntax-aware COBOL parser + fallback) |
| Reranking | Custom (keyword overlap scoring) |
| Prompt template | Custom (enforces citations, prevents hallucination) |
| Logging | Custom (explicit latency + cost tracking) |

LangChain accelerates integration without sacrificing architectural control or transparency.

---

## 15. Code Understanding Features (4 Required)

### F1: Code Explanation
Natural language explanation of what a selected COBOL paragraph or section does.
- Input: paragraph name or file:line range
- Output: plain-English description grounded in retrieved context

### F2: Dependency Mapping
Show what calls what and trace data flow between modules.
- Heuristic-based: parse `CALL`, `PERFORM`, `COPY` statements
- Output: dependency list with file/line references

### F3: Business Logic Extraction
Identify and explain business rules embedded in COBOL code.
- Target: financial calculations, conditional logic, data validation
- Output: plain-English business rule summary + source citations

### F4: Impact Analysis
Given a paragraph or data item, identify what would be affected if it changes.
- Heuristic-based: search for references to the named entity across the codebase
- Output: list of dependent files/paragraphs with line references

---

## 16. Authentication

**Strategy: GitHub OAuth via NextAuth.js**

Target users are developers — all have GitHub accounts. GitHub OAuth requires zero extra infra, provides real user identity for rate limiting, and is appropriate for a developer tool.

### Auth Flow

```
User visits app
    ↓
NextAuth.js (Next.js) initiates GitHub OAuth
    ↓
GitHub redirects back with auth code
    ↓
NextAuth exchanges code → issues session JWT (stored in httpOnly cookie)
    ↓
Frontend includes session token in API requests to FastAPI
    ↓
FastAPI validates token on every request
    ↓
Authenticated user identity used for per-user rate limiting
```

### Rate Limiting

- **Limit**: 20 requests per user per minute (FastAPI middleware)
- Keyed on GitHub user ID from session token
- Exceeding limit returns `429 Too Many Requests` with retry-after header
- Rationale: Protects OpenAI API costs without blocking legitimate usage during grading

### Session Management
- Sessions stored in NextAuth (JWT strategy, no database needed)
- Session token passed as `Authorization: Bearer <token>` header to FastAPI
- FastAPI verifies token signature — no database lookup required
- Session expiry: 30 days (configurable)

---

## 17. Developer Interaction Model

**Primary interface: Web UI only.**

Developers interact exclusively through the browser-based query interface. No CLI or separate REST API documentation is exposed. The UI is the product.

### User Journey

```
1. Visit app URL
2. Sign in with GitHub (one click)
3. Enter natural language query in search bar
4. View retrieved COBOL snippets with file:line citations
5. Read LLM-generated explanation
6. Click any result to drill down into full file context
7. Use feature tabs for Dependency Map / Business Logic / Impact Analysis
```

### UI Features
- Natural language text input with example queries
- Code snippet display with COBOL syntax highlighting
- File path + line number shown per result
- Relevance/similarity score badge per chunk
- LLM-generated explanation with streaming display
- Drill-down into full file context for any result
- Feature tabs: Explain / Dependencies / Business Logic / Impact Analysis

---

## 18. Technical Stack

| Layer | Technology |
|-------|------------|
| Codebase | GnuCOBOL Contrib |
| Vector DB | Pinecone (Serverless) |
| Embeddings | OpenAI `text-embedding-3-small` |
| LLM | GPT-4o-mini |
| RAG Framework | LangChain (selective) + custom pipeline |
| Backend | Python + FastAPI |
| Frontend | Next.js (React) |
| Auth | NextAuth.js (GitHub OAuth provider) |
| Frontend Deployment | Vercel |
| Backend Deployment | Railway |
| Local Dev | Docker Compose |
| Secrets | `.env` locally; Railway + Vercel env vars in production |

---

## 19. Deployment Architecture

### Production

```
User Browser
    ↓ HTTPS
Vercel (Next.js + NextAuth.js)
    ↓ Bearer token
Railway (FastAPI Backend)
    ↓                    ↓
Pinecone             OpenAI API
(vector store)   (embeddings + LLM)
```

### CI/CD

- **Trigger**: Push to `main` branch
- **Frontend**: Vercel auto-deploys on every push (native GitHub integration)
- **Backend**: Railway auto-deploys on every push (native GitHub integration)
- No manual deploy steps — merge to main = live

### Branch Strategy

```
main          → production (auto-deploy)
dev           → integration branch
feature/*     → individual feature branches
```

PRs merge to `dev` → tested manually → merge `dev` → `main` to deploy.

### Local Development

Docker Compose spins up the full backend stack locally:

```yaml
# docker-compose.yml (local dev)
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
    volumes:
      - ./backend:/app   # hot reload
```

Frontend runs separately: `npm run dev` (Next.js dev server on port 3000).

Matches Railway container config — no environment drift between local and prod.

### Environment Configuration

| Variable | Where set | Used by |
|----------|-----------|---------|
| `OPENAI_API_KEY` | `.env` / Railway | Backend |
| `PINECONE_API_KEY` | `.env` / Railway | Backend |
| `PINECONE_INDEX` | `.env` / Railway | Backend |
| `NEXTAUTH_SECRET` | `.env.local` / Vercel | Frontend |
| `GITHUB_CLIENT_ID` | `.env.local` / Vercel | Frontend |
| `GITHUB_CLIENT_SECRET` | `.env.local` / Vercel | Frontend |
| `NEXT_PUBLIC_API_URL` | `.env.local` / Vercel | Frontend |

---

## 20. Security Practices

### Secrets Management
- All API keys stored in environment variables — never hardcoded or committed to git
- `.env` and `.env.local` listed in `.gitignore`
- Production secrets set via Railway and Vercel dashboards (not config files)

### API Key Protection
- OpenAI and Pinecone keys are **backend-only** — never sent to the browser
- Frontend communicates only with the FastAPI backend
- Session tokens are `httpOnly` cookies (not accessible to JavaScript)

### Input Handling
- User queries sanitized before embedding (strip control characters, limit length to 512 tokens)
- No raw query string passed to shell or filesystem operations
- FastAPI input validation via Pydantic models on all endpoints

### CORS
- FastAPI CORS restricted to the Vercel frontend domain only
- No wildcard `*` origin in production

### Authentication Enforcement
- All FastAPI routes require a valid session token (middleware-level check)
- Unauthenticated requests return `401 Unauthorized`
- Rate limiting applied after authentication (keyed on GitHub user ID)

---

## 21. Development Workflow

### Local Setup

```bash
# 1. Clone repo
git clone <repo-url>

# 2. Backend
cp backend/.env.example backend/.env   # fill in API keys
docker-compose up --build              # starts FastAPI on :8000

# 3. Frontend
cp frontend/.env.example frontend/.env.local   # fill in OAuth + API URL
cd frontend && npm install && npm run dev      # starts Next.js on :3000
```

### Ingestion (one-time, run locally)

```bash
# Clone target codebase
git clone https://github.com/OCamlPro/gnucobol-contrib ./data/gnucobol

# Run ingestion pipeline
docker-compose run backend python -m scripts.ingest --path ./data/gnucobol
```

Ingestion is a one-time offline script — not part of the web app runtime. Re-run only when the codebase changes.

### Git Workflow

```
1. Branch off dev:   git checkout -b feature/chunking-parser
2. Develop + test locally
3. Open PR → dev
4. Manual smoke test on dev branch
5. Merge to main → auto-deploys to production
```

### Code Quality
- Python: `black` for formatting, `ruff` for linting
- TypeScript: ESLint + Prettier (Next.js defaults)
- Pre-commit hooks for formatting (optional but recommended)

---

## 22. Testing Strategy

### Layer 1: Unit Tests (pytest — chunking logic)

Target: the COBOL parser and fallback chunker, which are the highest-risk custom components.

```
tests/
  test_chunker.py       # paragraph boundary detection
  test_fallback.py      # fixed-size + overlap behavior
  test_metadata.py      # line number extraction accuracy
```

Run: `pytest tests/unit/`

Key assertions:
- Paragraph boundaries are detected correctly for well-formed COBOL
- Fallback triggers when structure is absent
- `start_line` and `end_line` metadata is accurate
- No chunk exceeds max token budget

### Layer 2: Integration Test (retrieval pipeline)

End-to-end smoke test: ingest a small known COBOL sample → query → verify expected chunk is returned.

```python
# tests/integration/test_pipeline.py
def test_retrieve_known_paragraph():
    # Given: CALCULATE-INTEREST paragraph is indexed
    # When: query "interest calculation logic"
    # Then: top result contains CALCULATE-INTEREST chunk
    assert result.metadata["paragraph_name"] == "CALCULATE-INTEREST"
    assert result.score >= 0.75
```

Run: `pytest tests/integration/` (requires live Pinecone + OpenAI keys)

### Layer 3: Golden Query Set (manual evaluation)

20 developer-centric queries with known expected file/paragraph results. Measured after full ingestion.

| Query | Expected result |
|-------|----------------|
| "Where is the main entry point?" | File X, MAIN-PROCEDURE paragraph |
| "Find all file I/O operations" | Files with OPEN/READ/WRITE statements |
| "Explain CALCULATE-INTEREST" | Interest calculation paragraph |
| ... | ... |

**Metric**: Precision@5 > 70% (≥14 of 20 queries return expected result in top 5).

### What Is NOT Tested
- LLM answer quality (non-deterministic — evaluated manually during demo)
- Pinecone availability (external dependency — monitored via Railway logs)
- Frontend UI behavior (manual smoke test before submission)

---

## 24. Observability & Logging

Every request logs:
- Embedding latency (ms)
- Vector query latency (ms)
- LLM generation latency (ms)
- Total response latency (ms)
- Similarity scores of retrieved chunks
- Token usage per request (input + output)

Enables performance optimization and cost transparency at scale.

---

## 25. Failure Modes

| Scenario | Handling |
|----------|----------|
| No relevant chunks (score < 0.75) | Return safe fallback: "No relevant logic found in indexed code." |
| Ambiguous query | Prompt user to specify module or paragraph name |
| Pinecone timeout | Retry once; then fail gracefully with error message |
| Low similarity results | Do not generate speculative answers |
| OpenAI rate limit | Retry with exponential backoff |

---

## 26. Evaluation Strategy

- **Golden query set**: 10–20 developer-centric prompts with known expected results
- **Ground truth**: Manual file inspection and paragraph mapping per query
- **Metrics**: Precision@5, end-to-end latency, failure rate
- **Example queries tested**:
  - "Where is the main entry point of this program?"
  - "What functions modify the CUSTOMER-RECORD?"
  - "Explain what the CALCULATE-INTEREST paragraph does."
  - "Find all file I/O operations."
  - "What are the dependencies of MODULE-X?"
  - "Show me error handling patterns."

---

## 27. Cost Analysis

### Assumptions
- 1,000 internal developers
- 5 queries per user per day → ~5,000 queries/day
- ~1,500 tokens per query (3–5 chunks + prompt)

### Projected Monthly Costs (Enterprise Scale)

| Scale | Users | Queries/Day | Est. Monthly Cost |
|-------|-------|-------------|-------------------|
| MVP / Demo | 1–10 | 10–50 | < $1 |
| Small team | 100 | 500 | ~$15–$30 |
| Enterprise | 1,000 | 5,000 | ~$150–$300 |

Cost scales primarily with token volume (LLM generation) and query frequency.

---

## 28. Milestones & Build Order

### Tuesday MVP (24 Hours) — Hard Gate
1. Clone and scan GnuCOBOL Contrib repo
2. Set up Docker Compose (local backend) + Next.js frontend skeleton
3. Configure GitHub OAuth (NextAuth.js) + FastAPI token validation
4. Implement basic ingestion (file reading + naive chunking)
5. Generate embeddings + upsert to Pinecone
6. Build query endpoint (embed → retrieve → return raw chunks)
7. Add LLM answer generation on top
8. Wire up minimal web UI behind auth (query input + results display)
9. Deploy backend to Railway + frontend to Vercel (auto-deploy from main)

### Wednesday Final G4 (3 Days) — Polish
8. Implement syntax-aware COBOL chunking (replace naive chunking)
9. Add reranking + similarity threshold
10. Implement 4 code understanding features (Explanation, Dependency Mapping, Business Logic, Impact Analysis)
11. Polish UI (syntax highlighting, scores, drill-down)
12. Build evaluation set (20 golden queries, measure Precision@5)
13. Write RAG Architecture doc + AI Cost Analysis

### Sunday Final GFA (5 Days) — Full Submission
14. Fix failure modes identified in evaluation
15. Finalize observability logging
16. Record 3–5 min demo video
17. Write Pre-Search document (final version)
18. Create social post (X / LinkedIn)
19. Final deployment check

---

## 29. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| COBOL parsing edge cases | Implement robust fallback chunking; document failure modes |
| Retrieval returns irrelevant chunks | Prioritize chunking quality + golden set evaluation early |
| LLM latency exceeds 3s | Cache embeddings; reduce context size; tune top-k |
| Pinecone free tier limits | Monitor usage; serverless billing is query-based |
| Deployment friction | Deploy backend + frontend incrementally, not at the end |
| GitHub OAuth misconfigured | Test OAuth locally before deploying; use NextAuth debug mode |
| API keys leaked | `.gitignore` enforced; pre-commit hook to scan for secrets |
| Rate limiter blocks grader | Keep limit generous (20 req/min); disable for demo window if needed |

---

## 30. Deliverables

| Deliverable | Requirement |
|-------------|-------------|
| GitHub repo | Setup guide, architecture overview, deployed link |
| Deployed app | Publicly accessible query interface |
| Demo video | 3–5 min: show queries, retrieval results, answer generation |
| Pre-Search document | Completed checklist (all 16 items) |
| RAG Architecture doc | 1–2 pages: vector DB, embeddings, chunking, retrieval, failures, performance |
| AI Cost Analysis | Dev spend + projections for 100/1K/10K/100K users |
| Social post | X or LinkedIn with screenshots/demo, tag @GauntletAI |
