# LegacyLens Demo Script (5 Minutes, Personable)

Use this as a spoken script. It is written to sound human, not robotic.

---

## 0:00-0:30 — Hook + Problem

"Hi, I built LegacyLens to solve a simple but painful problem: legacy COBOL systems run critical business logic, but onboarding into those codebases is slow and intimidating.

LegacyLens lets you ask plain-English questions and get grounded answers with exact file paths and line ranges, so you can move from 'Where is this logic?' to actual code in seconds."

---

## 0:30-1:30 — What the App Does (End-to-End)

"Here is the flow:

1) We ingest COBOL files.
2) We chunk them into meaningful units.
3) We embed those chunks and store them in Pinecone.
4) At query time, we embed the user question, retrieve top matches, rerank, and stream an answer with citations.

What matters is that the answer is grounded. You do not just get a summary; you get snippets plus file and line context so you can verify everything."

---

## 1:30-2:35 — Architecture Decisions and Tradeoffs

"Three decisions really shaped quality:

**Vector DB choice: Pinecone.**
I chose Pinecone because the backend is on Railway, which does not offer persistent local disk for embedded vector stores like Chroma in a stable way. Pinecone is managed, serverless, and fast to operate.
Tradeoff: Pinecone metadata does not allow null values, so optional fields like paragraph names use empty strings. That was acceptable.

**Chunking strategy: paragraph-first, fallback second.**
For COBOL, paragraphs and sections are natural business-logic boundaries, so they are ideal chunks.
Fallback is fixed windows with overlap for messy files, which keeps coverage high but lowers semantic precision.
Tradeoff: paragraph chunking is more parser work, but retrieval quality is much better than fixed-size only.

**Embedding model: moved from OpenAI text-embedding-3-small to voyage-code-2.**
We saw a hard mismatch on code-heavy queries. Voyage, trained for NL-to-code alignment, improved key failing cases by roughly +0.17 to +0.29 cosine on critical queries.
Tradeoff: 3x embedding token price, but total re-index cost was still negligible at our scale."

---

## 2:35-3:20 — Failures, How We Handle Them, and Performance

"I treated failure modes as first-class:

- If retrieval confidence is weak, we do not bluff. A confidence gate blocks speculative generation and returns a safe fallback.
- We filtered low-value chunks like 'EXIT.' trampolines that looked relevant by name but had no real logic.
- We addressed synonym gaps and noisy ranking with reranking and query-shaping choices.

On performance, we optimized for practical speed:
- Reduced retrieval top-k where it was redundant
- Trimmed LLM context from 5 chunks to 3
- Lowered max tokens
- Fixed async blocking (`await asyncio.sleep` in retry paths)
- Added frontend warmup ping to reduce cold start pain

Result: latency moved from roughly 8-10 seconds down to around 2.5 seconds on warm runs."

---

## 3:20-4:10 — Evaluation Results (Show Precision)

"I just re-ran evaluation against the live stack:

`backend/.venv/bin/python scripts/evaluate.py --output eval_results/latest_eval.json --markdown-output eval_results/latest_eval.md`

Current result:
- Precision@5: **1.0000**
- Passed queries: **21/21**
- Target: **0.70**

So the retriever is now clearing the project threshold with strong margin."

---

## 4:10-5:00 — Mindset, Pivots, and Personal Growth

"The biggest growth this week was how I handled ambiguity.

At first, I wanted to optimize everything at once. That did not work. I learned to run controlled experiments, isolate variables, and only keep changes that improved measurable outcomes.

A concrete pivot: I initially used a general embedding model because it was cheap and convenient. Once the failure pattern was clear on code/NL mismatch, I pivoted to voyage-code-2 and reindexed. That decision unlocked multiple previously failing queries.

Under pressure, my rule became: no hidden magic, no hand-wavy claims.
If confidence is low, say so.
If precision regresses, stop and debug.
If a decision has tradeoffs, document them.

What I learned about myself: I do better when I anchor uncertainty to evidence. The moment I switched from 'guessing the best path' to 'measuring each path,' execution got calmer and much faster."

---

## Rapid-Fire Short Answers (Interview Backup)

- Why Pinecone? Managed, Railway-friendly, low ops overhead, fast iteration.
- Chunking tradeoff? Paragraph chunks boost relevance; fallback windows protect coverage.
- Why voyage-code-2? Better NL-to-code alignment; major gains on previously failing queries.
- Retrieval failure handling? Confidence gate + safe fallback + chunk quality filtering.
- Performance decisions? Reduced top-k/context/tokens, fixed async blocking, warmed backend.
- Ambiguity approach? Convert unknowns into experiments with explicit pass/fail metrics.
- Pivot example? Swapped embedding model after evidence from failing-query analysis.
- Learned this week? I execute best with measurable checkpoints, not intuition alone.
- Pressure handling? Prioritize reliability first, then optimize; keep changes reversible and documented.

