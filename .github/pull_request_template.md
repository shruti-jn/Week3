## Summary

<!-- One sentence: what does this PR do? What problem does it solve? -->

- **What changed:**
- **Why it changed:**
- **Scope (one logical change only):**

---

## Type of Change

- [ ] `feat` — new feature or capability
- [ ] `fix` — bug fix
- [ ] `test` — adding or fixing tests
- [ ] `chore` — tooling, config, dependencies, CI
- [ ] `docs` — documentation only
- [ ] `refactor` — code restructuring without behavior change
- [ ] `perf` — performance improvement

## Scope Area

- [ ] `backend/ingestion` — file scanning, chunking, embedding
- [ ] `backend/retrieval` — Pinecone search, reranking, context assembly
- [ ] `backend/api` — FastAPI route handlers
- [ ] `backend/features` — code explanation, dependency mapping, business logic, impact
- [ ] `frontend/auth` — GitHub OAuth, NextAuth
- [ ] `frontend/ui` — React components, pages
- [ ] `infra/ci` — GitHub Actions, pre-commit, deployment

---

## Task Link

- Task ID / GitHub Issue:
- Plan phase approved:

---

## TDD Evidence

<!-- Paste the pytest or Jest output showing tests were written FIRST and pass.
     Commit order matters: test file commit should appear before implementation commit in git log. -->

- [ ] Failing test written first (test committed before implementation)
- [ ] Minimal implementation added to pass the tests
- [ ] Refactor completed with all tests still green

```
paste test output here
```

---

## Tests Added

- **Unit tests:**
- **Integration tests (if any):**
- **Edge cases covered:**
  - [ ] Happy path (normal input works)
  - [ ] Empty / None input
  - [ ] Single-element case
  - [ ] Large input (no crash)
  - [ ] Boundary values (first, last, middle)
  - [ ] Invalid type input
  - [ ] Expected failure / exception path
- **Regression (if fixing a bug):**

---

## Quality Gates

- [ ] Lint passes (`ruff check` or `eslint` — zero warnings)
- [ ] Type check passes (`mypy --strict` or `tsc --noEmit`)
- [ ] Format check passes (`ruff format --check` or `prettier --check`)
- [ ] All unit tests pass (`pytest -m "not integration"` or `jest`)
- [ ] Coverage threshold met (≥ 80% for new code)
- [ ] Mutation score checked (if touching critical logic like chunker, reranker)

---

## Retrieval-Specific Checks (if applicable)

- [ ] File path + line number citations are correct in responses
- [ ] Precision@5 tracked against golden query set (if retrieval pipeline changed)
- [ ] End-to-end latency measured (target: < 3 seconds)
- [ ] Fallback behavior verified (what happens when score < 0.75)
- [ ] No hallucination: LLM only answers from retrieved context

---

## Self-Review Checklist

- [ ] **TDD order confirmed**: test commit appears before implementation commit
- [ ] **Docstrings written**: every new function/class has a "5th grader" explanation
- [ ] **Inline comments explain WHY**: not just what the code does
- [ ] **Type annotations complete**: all new functions have full type signatures
- [ ] **No secrets committed**: no API keys, tokens, or .env files in the diff
- [ ] **PR title follows Conventional Commits**: `feat(scope): description`
- [ ] **PR is atomic**: only one logical change (not multiple features bundled)
- [ ] **Architecture rules followed**: business logic in `core/`, thin API layer, Pydantic models
- [ ] **No `print()` statements**: uses `logging` module instead
- [ ] **No hardcoded strings**: API keys, URLs, model names come from env vars
- [ ] **CI is green**: all 5 jobs pass

---

## Risks

- **Technical risk:** (could this break something? how likely?)
- **Product risk:** (could this affect the user experience?)
- **Mitigation:** (what's the plan if it goes wrong?)
- **Rollback path:** (how do we revert this if needed?)

---

## Scope Document

<!--
For medium/large features: paste or link the scope doc from docs/scopes/
For small changes (single function, typo fix): write "N/A — trivial change"

Scope doc answers:
- What are we building? (plain English, 5th grader level)
- What does "done" look like? (acceptance criteria)
- What could go wrong? (risks)
- What are the dependencies? (what must be merged first)
-->
