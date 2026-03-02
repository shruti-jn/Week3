# LegacyLens

> Ask questions about 40-year-old COBOL code. Get answers with citations.

A RAG-powered code intelligence system for querying legacy COBOL codebases
in natural language. Built for Gauntlet AI Week 3.

---

## What It Does

LegacyLens lets developers ask plain-English questions about COBOL code and
get back the exact code snippet, file name, and line number — like a search
engine for legacy systems.

**Example queries:**
- "Where is interest calculated?"
- "What does the CALCULATE-MONTHLY-PAYMENT paragraph do?"
- "What business rules govern the payroll calculation?"
- "If I change the TAX-RATE variable, what else would break?"

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12 + FastAPI |
| Frontend | Next.js 14 (App Router) + TypeScript |
| Vector DB | Pinecone (serverless, cosine similarity) |
| Embeddings | OpenAI text-embedding-3-small (1536 dims) |
| LLM | GPT-4o-mini (streaming) |
| Auth | GitHub OAuth via NextAuth.js |
| Deployment | Railway (backend) + Vercel (frontend) |

---

## Project Structure

```
legacylens/
├── backend/          Python FastAPI backend
├── frontend/         Next.js frontend
├── docs/             Architecture docs, cost analysis, scope documents
├── data/             Local COBOL codebase (gitignored — clone separately)
├── CLAUDE.md         AI assistant rules for this project
└── .cursorrules      Cursor AI code generation rules
```

---

## Quick Start (Local Development)

### Prerequisites
- Python 3.12+
- Node.js 20+
- API keys: OpenAI, Pinecone, GitHub OAuth App

### Backend Setup

```bash
cd backend

# Copy environment template and fill in your API keys
cp .env.example .env
# Edit .env with your real keys

# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Install pre-commit hooks (runs quality checks before every git commit)
pre-commit install

# Start the development server
uvicorn app.main:app --reload --port 8000
# API docs available at: http://localhost:8000/docs
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Copy environment template
cp .env.example .env.local
# Edit .env.local with your values

# Start the development server
npm run dev
# App available at: http://localhost:3000
```

### Using Docker Compose (Both Services Together)

```bash
# Start everything
docker compose up

# Backend: http://localhost:8000
# Frontend: http://localhost:3000
```

---

## Development Workflow

This project uses a strict quality workflow to maintain A+ code quality.

### Branch Strategy

```
main          Production (auto-deploys to Railway + Vercel)
dev           Integration branch (all PRs target this)
feature/*     Feature branches (one logical change per branch)
fix/*         Bug fix branches
chore/*       Tooling and config changes
```

### TDD (Test-Driven Development)

**Write the test first, always.** Every implementation must be preceded by
a failing test that defines what "done" looks like.

```bash
# Run fast unit tests (no API keys needed)
cd backend && pytest -m "not integration" tests/unit/ -v

# Run with coverage
cd backend && pytest -m "not integration" tests/unit/ --cov=app

# Run frontend tests
cd frontend && npm test
```

### Code Quality

Pre-commit hooks run automatically on every `git commit`:
- Python: ruff (lint + format) + mypy (types) + pytest unit suite
- TypeScript: ESLint + Prettier + tsc
- Security: gitleaks (secret scanning)

Manual checks:
```bash
# Python
cd backend && ruff check . && ruff format --check . && mypy app/ --strict

# TypeScript
cd frontend && npm run lint && npm run format:check && npm run type-check
```

### Commit Message Format

```
feat(chunker): add paragraph-level COBOL boundary detection
fix(retrieval): handle empty Pinecone result set gracefully
test(chunker): add edge cases for Windows line endings
chore(ci): add mutation testing to CI pipeline
```

---

## Ingesting the COBOL Codebase

```bash
# Clone the target codebase
git clone https://github.com/OCamlPro/gnucobol-contrib data/gnucobol-contrib

# Run the ingestion pipeline
cd backend
python scripts/ingest.py --source ../data/gnucobol-contrib
```

---

## Running Tests

```bash
# Backend unit tests (fast, no API keys)
cd backend && pytest -m "not integration" tests/unit/ -v

# Backend integration tests (requires live Pinecone + OpenAI keys)
cd backend && pytest -m integration tests/integration/ -v

# Mutation testing (checks if tests catch bugs)
cd backend && mutmut run --paths-to-mutate app/core/ingestion/chunker.py

# Frontend tests
cd frontend && npm test

# Frontend tests with coverage
cd frontend && npm run test:coverage
```

---

## Deployment

- **Frontend:** Deploy to Vercel — connect the GitHub repo, set env vars in Vercel dashboard
- **Backend:** Deploy to Railway — connect the GitHub repo, set env vars in Railway dashboard
- **Pinecone:** Create index in Pinecone console (1536 dims, cosine similarity, serverless)

---

## Deliverables (Submission Checklist)

- [ ] GitHub repository (this repo) with setup guide
- [ ] Deployed application (publicly accessible link)
- [ ] Demo video (3-5 min)
- [ ] Pre-Search document (`docs/PRE_SEARCH.md`)
- [ ] RAG Architecture document (`docs/ARCHITECTURE.md`)
- [ ] AI Cost Analysis (`docs/COST_LOG.md`)
- [ ] Social post (X/LinkedIn with screenshots, tag @GauntletAI)
