# Scope Document — feature/retrieval-reranker

## Branch Name
`feature/retrieval-reranker`

## WHAT ARE WE BUILDING?
After Pinecone returns up to 10 code snippets that are *mathematically similar* to
the user's query, we need a second pass to figure out which ones are *actually about*
the same topic. The reranker is like a second judge: it reads the actual words in each
snippet and counts how many of the user's search terms appear there. Snippets with
better word overlap get bumped up; snippets that don't match the query's vocabulary
get pushed down or cut out entirely.

In concrete terms: if the user asks "how is interest calculated?", a snippet with
the word "INTEREST" and "COMPUTE" in it should outrank a snippet that is
geometrically close in embedding space but talks about something else entirely.

## WHY DOES IT MATTER?
Without the reranker, the query pipeline only uses cosine similarity, which can
promote semantically adjacent but topically wrong chunks. The reranker adds a
lexical signal that corrects these mis-rankings before the LLM sees the context —
if skipped, the answer generator may cite the wrong code.

## WHAT DOES "DONE" LOOK LIKE?

- [x] `compute_keyword_score(query, content)` returns 0.0–1.0 keyword overlap
- [x] Score is case-insensitive (COBOL is uppercase, queries are lowercase)
- [x] Common English stopwords are ignored (they add noise, not signal)
- [x] COBOL keywords are NOT removed (COMPUTE, PERFORM, etc. are meaningful)
- [x] `rerank(query, candidates, top_k, min_score)` filters out results whose
      cosine score < 0.75 (the similarity threshold) and re-sorts the rest
- [x] Combined score = 0.7 × cosine + 0.3 × keyword
- [x] Returns at most `top_k` (default 5) results sorted by combined score desc
- [x] Returns empty list when all candidates are below threshold
- [x] Returns empty list when candidates list is empty
- [x] `RankedResult` dataclass exposes chunk_id, cosine_score, keyword_score,
      combined_score, and metadata
- [x] All unit tests pass (`pytest -m "not integration"`)
- [x] Coverage ≥ 80% for new code

## WHAT COULD GO WRONG?

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Keyword weight tuned wrong — degrades retrieval quality | Med | Start at 0.3; expose as config param for easy tuning |
| Content field missing from metadata | Low | Default to empty string → keyword_score = 0.0 |
| Very short queries (1 word) skew overlap to 0.0 or 1.0 | Med | score is per query token, so 1-word query hitting content = 1.0 — acceptable |

## WHAT ARE THE DEPENDENCIES?

- [x] Depends on: `feature/retrieval-pinecone-client` (merged ✅)
- [x] External: none — pure Python, no API calls, no mocks needed

## IS THERE EXISTING CODE TO REUSE?

- [x] Checked for existing patterns: `SearchResult` dataclass in `pinecone_client.py`
- Relevant existing code: `app.core.retrieval.pinecone_client.SearchResult` — imported
  as the input type to `rerank()`

## IS THIS ON THE MVP CRITICAL PATH?

- On critical path: yes
- MVP simplification: ship with fixed keyword_weight=0.3; no BM25 or TF-IDF
- Full implementation: swap in BM25 scoring post-MVP if Precision@5 < 70%

## ESTIMATED COMPLEXITY

Estimated complexity: Small (1–2 hours)

## TECH DEBT TO WATCH FOR

- Avoid: using regex-heavy tokenization that breaks on COBOL identifiers (e.g.
  `CALC-INTEREST` should tokenize to `calc` + `interest`, not to `calc` + `-` + `interest`)
  → split on non-alphanumeric chars and drop empty tokens: this handles hyphens cleanly
