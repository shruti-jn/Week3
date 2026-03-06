# LegacyLens Demo Script (Architecture Walkthrough, 5-6 Minutes)

Use this as your spoken track while the `ArchitectureDiagram` component is open.

---

## 0:00-0:35 - Hook (Why this matters)

"LegacyLens solves a very practical problem: legacy COBOL systems run real business logic, but finding where that logic lives is painfully slow for modern engineers.

The goal is simple: ask a plain-English question, and get back grounded COBOL evidence with file names, paragraph names, and line numbers."

---

## 0:35-2:20 - Walkthrough Lane A (Ingestion pipeline)

"I will start on the left lane in the diagram: this is offline ingestion, which runs when we index or re-index a corpus.

At A1 and A2, we scan COBOL files and detect boundaries in PROCEDURE DIVISION.
This was a key design choice: paragraph-level chunking beats fixed windows because paragraph names often map to business intent, like `CALCULATE-INTEREST` or `EXEC-SQL-INSERT`.

At D1, if boundaries are found, we go to A3 semantic chunks. If not, we fall back to A4 fixed-size windows with overlap so we never lose coverage.
That fallback is less precise, but it is robust on messy files.

A5 and D2 are one of the biggest roadblock fixes.
Early on, we were indexing lots of junk chunks, especially `EXIT.` trampolines and tiny constants.
They scored high because of paragraph names, but had no real logic.
So we added a quality gate: minimum non-trivial lines plus at least one COBOL logic verb.
If it fails, A6 drops and logs it.

At D3/A7, we apply Q&A framing when we have meaningful comments.
This was another major breakthrough: raw COBOL text often did not align with natural-language queries.
By prepending a tiny Q&A sentence, we gave embeddings semantic signal without changing what users see.
Raw code remains the source shown in citations.

Then A9 through A11: embed with `voyage-code-2`, create deterministic vector IDs, and upsert to Pinecone.
Reason for Pinecone: Railway does not give us reliable persistent disk for local vector stores.
Tradeoff accepted: Pinecone metadata does not allow null, so optional fields are stored as empty strings."

---

## 2:20-4:05 - Walkthrough Lane B (Query pipeline + latency)

"Now switch to the right lane: this is online query flow, executed per request.

B1 starts with a user question.
B2 does lightweight query enrichment, appending `COBOL` when missing to reduce synonym gaps.

At B3 and B4, we embed the query and retrieve top candidates from Pinecone.
B5 drops low-cosine results, and B6 reranks with a blended score:
0.7 cosine plus 0.3 keyword overlap.
This blend improved retrieval stability when semantic and lexical signals disagreed.

B7 emits snippets immediately over SSE, so users see evidence before the final answer.
B8 computes confidence metrics, and D4 is our anti-hallucination gate.
If confidence is weak, B9 returns a safe fallback response instead of pretending certainty.
If confidence is good, B10 keeps top 3 chunks for generation and B11 streams the answer from GPT-4o-mini.

How did we get latency down?
We treated latency as a budget, not one number.
We moved from roughly 8-10 seconds to about 2.51 seconds warm by stacking small wins:
- top_k from 10 to 5
- LLM context from 5 chunks to 3
- max tokens from 300 to 100
- fixed async retry sleep behavior to avoid accidental stalls
- frontend warmup ping to reduce cold-start pain

Current warm-stage numbers in the diagram are about:
embed 165ms, retrieve 72ms, rerank under 1ms, LLM about 2274ms.
The LLM is still the largest block, which is expected."

---

## 4:05-5:10 - Evals story + exactly how to run evals

"We do not claim quality without evals.
We maintain a golden query set and measure Precision@5 against expected chunks.

There are two eval modes:

1) **Retrieval-stack eval (direct Pinecone + reranker)**  
From `backend/`:
`.venv/bin/python scripts/evaluate.py --output eval_results/latest_eval.json --markdown-output eval_results/latest_eval.md`

Required env vars:
`VOYAGE_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`

2) **Deployed API eval (full real endpoint over SSE)**  
From `backend/`:
`NEXTAUTH_SECRET=<your-secret> .venv/bin/python scripts/evaluate_deployed.py --backend-url https://<your-railway-url> --output eval_results/prod_eval.json --markdown-output eval_results/prod_eval.md`

This mode measures both relevance and production latency from the `done` SSE payload, including p50 and p95 query times.

Our target is Precision@5 >= 0.70, and the recent run is well above that threshold."

---

## 5:10-5:40 - Close (Roadblocks + why this architecture)

"The biggest roadblocks were semantic mismatch, noisy chunks, and latency.
Each architecture decision maps directly to one of those:
- Q&A framing + code-focused embeddings for semantic mismatch
- chunk quality filter + confidence gate for noisy or weak grounding
- top-k/context/token tuning + streaming for latency

So this is not just a diagram of components; it is a diagram of lessons learned under real constraints."

---

## 30-Second Backup Version

"LegacyLens indexes COBOL by paragraph-level logic, filters low-value chunks, and embeds with a code-specialized model in Pinecone.
At query time, we retrieve, rerank, stream snippets first, then gate generation on confidence to prevent bluffing.
That design improved relevance and reduced warm latency from 8-10s to about 2.5s.
We verify it with golden-query evals locally and against deployed SSE endpoints."
