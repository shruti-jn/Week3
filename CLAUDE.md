# LegacyLens — Claude Code Rules

## Project Context

LegacyLens is a RAG-powered COBOL code intelligence system built for Gauntlet AI Week 3.
It lets developers ask plain-English questions about old COBOL codebases and get back
the exact code snippet, file name, and line number — like a search engine for legacy code.

- **Backend:** Python 3.12 + FastAPI (deployed to Railway, port 8000)
- **Frontend:** Next.js 14 App Router + TypeScript (deployed to Vercel, port 3000)
- **Vector DB:** Pinecone (serverless, cosine similarity, 1536 dimensions)
- **Embeddings:** OpenAI text-embedding-3-small
- **LLM:** GPT-4o-mini (streaming answers via SSE)
- **Auth:** GitHub OAuth via NextAuth.js
- **Deadlines:** MVP Tuesday (24h) → G4 Wednesday → Final Sunday 10:59 PM CT

---

## Code Quality — Non-Negotiable

All Python code must pass before committing:
- `ruff check .` (linting — catches bugs and bad patterns)
- `ruff format --check .` (formatting — consistent style)
- `mypy app/ --strict` (type checking — no guessing about data types)

All TypeScript code must pass before committing:
- `eslint src/ --max-warnings 0`
- `prettier --check src/`
- `tsc --noEmit`

**Never commit code with type errors.** If a type is genuinely unknown, add a
`# type: ignore` comment with a reason. Never use bare `any` in TypeScript without a comment.

---

## TDD Mandate (Test-Driven Development)

**Write the test first. Always. No exceptions.**

The workflow for every new function or module:
1. Create the test file with failing tests (the tests describe what "done" looks like)
2. Run the tests — they should fail (proves the tests are real)
3. Write the minimum code to make the tests pass
4. Refactor if needed (tests must still pass after refactoring)

Test file locations:
- Python: `backend/tests/unit/test_<module_name>.py`
- TypeScript: `frontend/__tests__/<ComponentName>.test.tsx` or `lib/<file>.test.ts`

### Test Edge Case Checklist
Before marking any test file complete, verify tests exist for:
- [ ] Normal case (happy path — everything works as expected)
- [ ] Empty or None input (what happens with nothing?)
- [ ] Single-element case (edge of the normal range)
- [ ] Very large input (does it crash on 10,000 items?)
- [ ] Boundary values (first item, last item, middle item)
- [ ] Invalid type input (wrong data type passed in)
- [ ] Expected failure / exception path (what should blow up, does blow up correctly)

Run only unit tests (fast, no API keys needed):
```
pytest -m "not integration" tests/unit/ -q
```

Run integration tests (needs live Pinecone + OpenAI keys in .env):
```
pytest -m integration tests/integration/
```

Minimum coverage for new code: **80%**

---

## Commenting Standard — The "5th Grader Rule"

Every function, class, and non-obvious code block must be understandable by someone
who has never seen this code before — ideally explained like you're talking to a
10-year-old (minus the condescension).

### Docstring Template (Python)

```python
def my_function(arg1: str, arg2: int) -> list[str]:
    """
    One-line summary: what this does in plain English.

    Longer explanation: describe what this actually accomplishes and why it
    exists. Use an analogy if the concept is abstract. For example:
    "This is like a table of contents — it maps each chapter name to the
    page it starts on."

    Args:
        arg1: What this argument is (not its type — the type is in the signature).
              Include the expected format/range if relevant.
        arg2: What this argument is and why the caller provides it.

    Returns:
        Description of what comes back. For lists/dicts, describe what each
        element contains.

    Raises:
        ValueError: When this is raised and why.
        KeyError: When this is raised and why.
    """
```

### Inline Comment Standard

```python
# BAD: Comments that just repeat what the code says
result = []  # initialize empty list

# GOOD: Comments that explain WHY or clarify something non-obvious
# COBOL paragraphs must start at column 8 (the "Area B" rule from the COBOL standard).
# Anything at columns 1-7 is a DIVISION/SECTION header — we skip those.
PARAGRAPH_COLUMN_START = 8
```

### TypeScript JSDoc Template

```tsx
/**
 * ComponentName — One-sentence description of what this shows or does.
 *
 * Longer explanation: describe what problem this solves for the user.
 * Use an analogy. For example: "Like a search result card in Google,
 * but for COBOL code snippets."
 *
 * @param propName - What this prop is and why it's needed
 * @param onAction - What triggers this callback and what the caller should do with it
 */
```

---

## Commit Message Format (Conventional Commits)

Format: `<type>(<scope>): <description>`

**Types:**
- `feat` — new feature or capability
- `fix` — bug fix
- `test` — adding or fixing tests
- `chore` — tooling, config, dependencies, CI
- `docs` — documentation only
- `refactor` — code restructuring without behavior change
- `perf` — performance improvement

**Scopes for this project:**
`ingestion` | `retrieval` | `api` | `frontend` | `auth` | `infra` | `chunker` | `embedder`

**Examples:**
```
feat(chunker): add paragraph-level COBOL boundary detection
fix(retrieval): handle empty Pinecone result set gracefully
test(chunker): add edge cases for malformed COBOL paragraph labels
chore(ci): add mutation testing step to backend pipeline
docs(architecture): document chunking strategy tradeoffs
refactor(reranker): extract keyword scoring to standalone function
perf(embedder): switch to batched embedding calls (100 chunks/request)
```

**Rules:**
- Description is lowercase, no period at the end
- Max 72 characters in the subject line
- Body (optional) explains WHY, not what (the diff shows what)
- Breaking changes: add `!` after scope — `feat(api)!: change query response schema`

---

## PR Rules

- PRs are **small and atomic** — one logical change per PR
- If a PR takes more than 10 minutes to review, it's too big: split it
- Every PR must have the GitHub PR template filled out completely
- Link to the failing test that your implementation fixes (proves TDD was followed)
- No PR merges with red CI (all checks must be green)

---

## Architecture Rules

**Backend:**
- All business logic lives in `app/core/` — never in `app/api/`
- The API layer (`app/api/v1/`) only does three things: validate input → call core function → return response
- No direct Pinecone or OpenAI calls from route handlers — always go through core modules
- All request and response shapes are Pydantic models in `app/models/` — no raw dicts in the API layer
- Secrets come only from environment variables via `app/config.py` Settings class
- No hardcoded strings for API keys, endpoint URLs, model names, or index names

**FastAPI patterns:**
- Use dependency injection for all shared resources (Pinecone client, OpenAI client)
- All endpoint functions are `async def`
- Raise `HTTPException` with specific status codes — never return error dicts
- Rate limiting is applied as middleware, not per-endpoint

**Python patterns:**
- Use `dataclasses` or `Pydantic` models — not plain dicts for structured data
- Use `pathlib.Path` instead of `os.path`
- Use `logging.getLogger(__name__)` — never use `print()`
- Log at `DEBUG` for internal state, `INFO` for request lifecycle events
- All external API calls (OpenAI, Pinecone) must have retry logic with exponential backoff

**Frontend (Next.js):**
- App Router only — no Pages Router patterns
- Fetch initial data in Server Components; use Client Components only when interactivity requires it
- All API calls to FastAPI go through `src/lib/api.ts` — never use raw `fetch()` inline in components
- No hardcoded API URLs — always use `NEXT_PUBLIC_API_URL` environment variable
- Named exports only, except for Next.js page/layout files (which require default exports)

---

## What NOT To Do

- Do not use `any` as a TypeScript type without a comment explaining why
- Do not make OpenAI or Pinecone API calls in unit tests — always mock them
- Do not commit `.env`, `.env.local`, or any secrets file
- Do not use `print()` in Python — use the `logging` module
- Do not create TODO comments in code — open a GitHub issue instead
- Do not suppress linting errors with `# noqa` or `// eslint-disable` without a reason comment
- Do not merge a PR with failing tests or type errors

---

## Context Window Management — Hard Limit: 40%

**Context must never exceed 40% during any agent session.**

Context is like a whiteboard: once full, earlier work gets erased and the AI starts
"forgetting" decisions that were made. Staying under 40% ensures clear thinking
throughout the entire session without any information loss.

### How to Stay Under 40%

1. **One feature = one fresh session.**
   Every new feature branch starts with `/clear` or a new terminal session.
   Never carry work from one feature into the next in the same session.

2. **Subagents do all codebase research.**
   Never explore multiple files in the main session context.
   Always use a Task (Explore) subagent for any search that touches more than 2 files.
   Subagents run in their own isolated context window — they have zero impact on the main session.

3. **Max 2 files read per step in the main session.**
   Always name the exact files needed. Never say "look at the codebase."
   Reading 10 files = 10x context consumed.

4. **Compact proactively, not reactively.**
   Run `/compact` after finishing research/planning and before starting implementation.
   Do not wait until the limit is hit — compact while there is still room.

5. **Keep CLAUDE.md under 200 lines.**
   This file is loaded into every session. If it grows too large, it eats context on startup.

### Context Usage Guide

| Usage | Action |
|-------|--------|
| < 30% | Continue normally |
| 30–40% | Finish current step, then `/compact` |
| > 40% | `/compact` immediately — do not start a new step |
| > 60% | `/clear` and start a fresh session |

---

## Prompt Efficiency Rules

When asking Claude Code to help, be specific to save time and tokens:

```
GOOD: "Read backend/app/core/ingestion/chunker.py and the failing test in
      tests/unit/test_chunker.py. The test_fallback_fixed_size test is failing.
      Fix chunker.py to pass it."

BAD:  "Look at the codebase and fix the chunker."
```

- Always specify exact file paths — never say "look at the codebase"
- For search tasks: provide the search term and the directory to look in
- For implementation: provide the function signature and docstring first, then ask for the body
- For debugging: provide the error message, the failing test, and the relevant source file
- One task per prompt — don't mix "explain this" with "fix this"

---

## Model Selection Hints

| Task | Best Model | Why |
|------|-----------|-----|
| Research / codebase exploration | Haiku (parallel agents) | Fast and cheap for read-only work |
| Writing boilerplate / scaffold code | Haiku | Well-defined patterns, no deep reasoning needed |
| Writing tests | Sonnet | Needs to understand intent + edge cases |
| Implementation (functions, modules) | Sonnet | Good balance of quality and speed |
| Debugging complex issues | Opus | Multi-step reasoning across multiple files |
| Architecture decisions / tradeoffs | Opus | Handles ambiguity and deep context |
| Code review (small diff) | Haiku | Pattern matching is sufficient |
| Code review (architectural change) | Opus | Needs full context |
| Plan approval conversations | Sonnet | Balanced reasoning + speed |
| Documentation / comments | Haiku | Clear instructions, repetitive patterns |

---

## Architecture Decisions Log

Add to this section when a significant technical choice is made.
Format: `[DATE]: [DECISION] because [REASON]`

- [2026-03-02]: Chose Pinecone over ChromaDB because Railway (our backend host)
  doesn't support persistent disk storage — ChromaDB needs local files. Pinecone is
  fully managed with no infrastructure overhead.

- [2026-03-02]: Using text-embedding-3-small (not large) because 1536 dimensions is
  sufficient for COBOL paragraph-level granularity. 5x cheaper than large; latency
  difference is negligible at our query volume.

- [2026-03-02]: GPT-4o-mini chosen over GPT-4o — citation enforcement works equally
  well on both, but mini is 15x cheaper and makes the <3 second latency target easier.

- [2026-03-02]: OpenCOBOL Contrib chosen as target codebase over GnuCOBOL compiler
  because it contains real business-logic COBOL (payroll, loans, inventory) which
  creates a compelling demo narrative and makes the 4 code-understanding features
  much more interesting to show.

---

## Known Tech Debt

Add to this section when a shortcut is taken under time pressure.
Format: `[DATE] [FILE] [SHORTCUT TAKEN] — fix by [milestone]`

<!-- Example:
- [2026-03-02] chunker.py: Fixed-size fallback doesn't respect COBOL statement
  boundaries. Good enough for MVP. Fix before G4 if Precision@5 < 70%.
- [2026-03-02] rate_limit.py: In-memory rate limiting resets on server restart.
  Acceptable for demo. Fix with Redis before production.
-->

---

## Scope Checklist (Answer Before Starting Any Feature)

Before opening a code editor for a new feature, answer these:

1. What are we building? (explain it like you're describing it to a 10-year-old)
2. Why does it matter? (what breaks if we skip this?)
3. What does "done" look like? (write the acceptance criteria)
4. What could go wrong? (list 2-3 risks and how to handle them)
5. What are the dependencies? (what must be merged before this branch starts?)
6. Is there existing code to reuse? (grep the codebase before writing new code)
7. Is this on the MVP critical path? (if yes, do the simplest version first)
