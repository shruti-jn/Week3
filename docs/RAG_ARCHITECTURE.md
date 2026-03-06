# LegacyLens — RAG Architecture

**System:** Plain-English search over COBOL legacy codebases, returning exact file, paragraph, and line-number citations.

---

## Vector DB Selection

**Choice:** Pinecone serverless (cosine similarity, 1536 dimensions).

**Why Pinecone over ChromaDB:** Railway (the backend host) has no persistent disk. ChromaDB requires local file storage. Pinecone is fully managed with no infrastructure overhead. Serverless tier fits the query volume and keeps cost near zero at rest.

**Tradeoff accepted:** Pinecone metadata values cannot be null — empty strings are stored instead of `None` for optional fields like `paragraph_name`. Minor annoyance, no functional impact.

---

## Embedding Strategy

**Final model:** Voyage AI `voyage-code-2` (1536 dimensions).

**Why not OpenAI `text-embedding-3-small`:** The initial model. Scored 0.25–0.34 on COBOL queries — well below the 0.75 relevance threshold. The root cause: text-embedding-3-small was trained on natural language, not code. It cannot bridge "database connection" → `EXEC SQL CONNECT` or "encryption keys from a password" → a PC1/PC2 permutation table.

**Why voyage-code-2 wins:** Trained specifically on natural-language ↔ code pairs. On the four previously failing queries, voyage-code-2 scored +0.17 to +0.29 higher (0.46 → 0.74, 0.49 → 0.75, 0.63 → 0.83, 0.69 → 0.85). All four cleared their thresholds. Cost: 3× more per token ($0.06/1M vs $0.02/1M), but $0.05 total one-time re-index cost at our corpus size — negligible.

**Asymmetric retrieval:** Voyage uses different internal representations for stored documents vs. search queries. Chunks are embedded with `input_type="document"`; user queries use `input_type="query"`. This improves recall compared to symmetric embedding.

**Q&A framing (key breakthrough):** Raw COBOL code embedded as-is scores ~0.50–0.60 against natural-language queries. The fix: prepend a question-answer sentence to the embedding text:

```
What does the CALCULATE-INTEREST paragraph do?
The CALCULATE-INTEREST paragraph calculates the total interest charged on the loan amount.
COBOL program: loan-calculator
Paragraph: CALCULATE-INTEREST (calculate interest)
    COMPUTE WS-INTEREST = WS-PRINCIPAL * WS-RATE / 100.
```

The Q&A lead is built from the paragraph name + the first meaningful inline comment (`*>` or column-7 `*`). This format mirrors user queries, pushing cosine scores from ~0.69 → 0.77–0.82. The raw code is what gets stored in Pinecone metadata and shown to users — the enriched text is embedding-only.

---

## Chunking Approach

**Primary strategy — paragraph-level:** Scan for `PROCEDURE DIVISION`, then collect named paragraph labels (single uppercase token + period, alone on its line) and SECTION headers (`NAME SECTION.`). Each paragraph or section becomes one chunk with its content running to the next boundary.

**Why paragraphs:** COBOL paragraphs are named business-logic units (`CALCULATE-INTEREST`, `COMPUTE-TAX`). They map 1:1 to developer intent, making them ideal retrieval units.

**Key detection details:**
- Reserved words excluded: `EXIT`, `CONTINUE`, `END-IF`, `END-PERFORM`, and 20+ scope terminators that can appear alone on a line
- SECTION headers added after gnucobol-contrib revealed the SECTION + EXIT trampoline pattern (real code lives in the section; `CRYPT-EX.` EXIT. is the trampoline — both get chunks, but the section owns the code)
- Comment lines (column-7 `*`, free-format `*>`) skipped during boundary detection

**Fallback strategy — fixed-size windows:** When no paragraphs are found (unstructured COBOL or non-standard files), 50-line windows with 10-line overlap. No semantic meaning, but prevents data loss. Marked `is_fallback=True` in metadata; Q&A framing is not applied.

**Vector ID convention:** `file_path::PARAGRAPH-NAME` for named chunks, `file_path::chunk_N` for fallback.

### Chunk Quality Filter (ingestion gate)

Not every chunk produced by the chunker is worth indexing. Stub chunks pass the cosine similarity threshold at query time because their **paragraph names** contain domain vocabulary — even when their **bodies** are semantically empty. Observed in production:

| Stub type | Example | Why it scores high | Why it's useless |
|---|---|---|---|
| Exit trampoline | `COB2CGI-PROCESS-GET-EX. EXIT.` | "PROCESS" in name matches query | Body is one word: `EXIT.` |
| Single-line constant | `COB2CGI-LF` | "CGI" in name matches any CGI query | No logic whatsoever |
| HTML stub | `COB2CGI-ENV-VALUE / "<BR>"` | "CGI" + "VALUE" in name | Two-line data constant |

These polluted top-5 results for every CGI-related query, consuming 3 of 5 slots and causing vague LLM answers ("you typically handle...") because the context had no real code.

**Fix — `chunk_filter.py` (ingestion gate before embedding):**

A chunk must pass **both** checks to be indexed:

1. **Minimum non-trivial line count ≥ 4** — after stripping the paragraph label line, comment lines, separator lines (`*>---`), and blank lines. Catches exit trampolines and single-line constants.

2. **At least one logic verb** — the remaining lines must contain one of: `MOVE`, `COMPUTE`, `PERFORM`, `IF`, `EVALUATE`, `READ`, `WRITE`, `REWRITE`, `CALL`, `ADD`, `SUBTRACT`, `MULTIPLY`, `DIVIDE`, `OPEN`, `CLOSE`, `INITIALIZE`, `STRING`, `UNSTRING`, `INSPECT`, `SEARCH`, `SET`, `STOP RUN`. Catches data stubs that have enough lines but no executable logic.

This is general — it doesn't enumerate specific patterns. Any chunk without real logic fails, regardless of its name. Applied in `embed_and_upsert()` before the Voyage API call. Filtered count is logged so ingestion output shows how many stubs were skipped.

---

## Retrieval Pipeline

```
User query
  → query_enrich()         append "COBOL" if missing (case-insensitive)
  → embed_query()          voyage-code-2, input_type="query"
  → Pinecone.query()       top_k=5, cosine similarity
  → rerank()               cosine (0.7) + keyword overlap (0.3)
  → snippets SSE event     top 5 shown in UI
  → confidence_gate()      fallback if top_score < 0.66 OR avg_similarity < 0.60
  → generate_answer()      top 3 chunks to LLM (to reduce TTFT)
  → token SSE events       GPT-4o-mini, stream=True, max_tokens=100
  → done SSE event         latency breakdown + similarity metrics
```

**Reranker:** Combined score = `0.7 × cosine + 0.3 × keyword_overlap`. Keyword overlap counts query terms (after stopword removal and hyphen splitting) found in chunk content. COBOL verbs (COMPUTE, PERFORM) are deliberately not stopwords — they are valid search signals. Candidates below the cosine threshold are dropped before keyword scoring.

**Context pruning:** All 5 ranked results appear in the UI; only the top 3 go to the LLM. Cuts input tokens ~40%, reducing TTFT without accuracy loss (reranker already ranked best-first).

**Confidence gate before generation:** Retrieval can return non-empty snippets that are still weakly grounded (borderline scores, noisy context). Before calling the LLM, the pipeline computes:
- `top_score` = highest snippet score in this query
- `avg_similarity` = mean snippet score for this query

If `top_score < 0.66` OR `avg_similarity < 0.60`, LegacyLens does **not** generate a broad answer. It returns a fallback response ("I don't have enough relevant code context...") and still emits a normal `done` event for observability.

---

## Failure Modes

**1. Uncommented COBOL (most common):** gnucobol-contrib files rarely contain English prose comments. Without a meaningful `*>` comment, `_extract_first_comment()` returns empty, the Q&A framing is skipped, and scores land at 0.45–0.55. The SETKEY section (DES key schedule: 64 rows of bit-index numbers) is the clearest example — no text-to-meaning bridge exists.

**2. Semantic synonym gap (partially mitigated):** Users say "process", "get", "handle", "work with" — the COBOL code (and its Q&A framing) uses "parse", "compute", "perform". These live far apart in embedding space. Observed: "How do I process HTML form data COBOL" retrieved an exit trampoline as #1 result while the correct `COB2CGI-PARSE-GET-POST` chunk wasn't in the top 5 at all. The right chunk scored 0.675 for "parse" but fell below threshold for "process". Implemented mitigation: before embedding, append `" COBOL"` to the query when "cobol" is absent (case-insensitive). Future work: add richer synonym expansion (e.g. "process" → "parse handle read") or a low-cost LLM rewrite step to produce COBOL-friendly query wording.

**3. Low-level embedded SQL:** `EXEC SQL INSERT INTO books VALUES(...)` uses opaque C-style variable names. Natural-language queries like "insert a record into a database" don't align without a code-aware model. voyage-code-2 handles this; text-embedding-3-small cannot.

**4. Exit trampolines and stub chunks (mitigated by chunk_filter.py):** The SECTION + EXIT trampoline pattern and single-line constants scored above the cosine threshold because their paragraph names inherited domain vocabulary. Confirmed in production: `COB2CGI-PROCESS-GET-EX. EXIT.` ranked #1 for a CGI form query; `COB2CGI-LF` and `"<BR>"` constants filled the remaining slots. The chunk quality filter (see Chunking Approach) removes these at ingestion time. Without the filter, 3 of 5 result slots were noise and the LLM produced vague/hallucinated answers.

**5. Score compression — no signal separation:** All results in a typical query cluster between 0.56–0.68 (spread of ~0.12). This makes it hard for the reranker to distinguish a genuinely correct answer from a marginally relevant chunk. Both query runs on CGI form parsing showed this — exit trampolines scored within 0.06 of the correct result. The chunk filter helps by removing the lowest-quality items; query expansion helps by pushing the correct chunk's score higher.

**6. Float-edge threshold failures:** Scores like 0.750 can fall just below a `< 0.75` threshold check due to floating-point representation. Observed once in evaluation (gq-002). Threshold is now 0.65, reducing exposure to this.

**7. Fallback chunk quality:** Files that trigger fixed-size fallback produce chunks with no paragraph name, no Q&A framing, and lower average scores. Retrieval precision drops for these files. The chunk quality filter still applies (logic verb check) so empty fallback windows are also excluded.

---

## Performance Results

| Stage | Before optimization | After optimization |
|---|---|---|
| End-to-end latency | 8–10s | **2.51s** (warm dyno) |
| Embed | — | 165ms |
| Retrieve (Pinecone) | — | 72ms |
| Rerank | — | <1ms |
| LLM (GPT-4o-mini) | ~6,000ms | 2,274ms |

**Latency levers applied:**
- `top_k` 10 → 5 (saves 150–300ms, Pinecone fetch)
- `max_tokens` 300 → 100 (saves 300–600ms, LLM generation)
- LLM context chunks 5 → 3 (saves 400–800ms, TTFT)
- `asyncio.sleep` fix in retry logic (eliminates up to 7,000ms freeze on retries)
- Frontend warmup ping on page load (eliminates 2–4s cold-start penalty)

**Retrieval precision (10-query golden set, gnucobol-contrib corpus):**

| Stage | Queries passing threshold | Precision@5 | Key change |
|---|---|---|---|
| text-embedding-3-small, plain code | 0/10 | 0% | Baseline |
| + Q&A framing | 5/10 | 50% | Q&A embedding format |
| + voyage-code-2 | 9/10 (projected) | ~90% | Model swap |
| + chunk quality filter | TBD post re-index | Expected improvement | Stub chunks removed |

**Representative scores after voyage-code-2 + Q&A:**

| Query | Score | Top result quality |
|---|---|---|
| "file sort COBOL program" | 0.805 | ✅ Correct GCSORT logic |
| "DES encryption algorithm COBOL" | 0.737 | ✅ cobdes.cob cipher code |
| "database connection SQL COBOL" | 0.852 | ✅ EXEC SQL CONNECT section |
| "how to insert a record into a database" | 0.745 | ✅ EXEC SQL INSERT section |
| "parse HTML form data CGI COBOL" | 0.675 | ✅ COB2CGI-PARSE-GET-POST (correct, but 3 of 5 slots were stubs — fixed by chunk filter) |
| "How do I process HTML form data COBOL" | 0.627 | ❌ Exit trampoline ranked #1 (synonym gap + no filter) |

**Observed noise before chunk filter (same CGI query, two phrasings):**

Query 1 — "parse HTML...": slot 1 correct (0.675), slots 3–5 were exit trampoline + constants.
Query 2 — "process HTML...": slot 1 was exit trampoline (0.627), correct chunk absent from top 5.
LLM answer for Query 2: vague/hallucinated — no real code in context.
Root cause: both stub chunks and synonym gap. Chunk filter addresses the stub problem; query expansion addresses the synonym gap.
