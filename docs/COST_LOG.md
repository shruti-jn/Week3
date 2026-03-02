# LegacyLens — AI Cost Log

This document tracks every AI API call made during development.
It serves two purposes:
1. **Budget awareness** — keeps spending visible so we don't get surprised
2. **Submission deliverable** — Gauntlet AI requires an AI Cost Analysis document

Fill this in as you work. Every OpenAI API call counts.

---

## How to Track Costs

After any significant AI usage session, add a row to the Development Spend table.

**Where to find token counts:**
- OpenAI API: check the Usage dashboard at platform.openai.com/usage
- Claude: check console.anthropic.com/usage
- Pinecone: embedding calls count as OpenAI tokens (we embed, then store)

**Token cost reference (as of 2025):**
| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| gpt-4o-mini | $0.15 | $0.60 |
| text-embedding-3-small | $0.02 | N/A |
| claude-sonnet-4-6 (dev tool) | $3.00 | $15.00 |
| claude-haiku-4-5 (dev tool) | $0.25 | $1.25 |

---

## Development Spend

| Date | Task | Model | Input Tokens | Output Tokens | Cost (USD) |
|------|------|-------|-------------|---------------|------------|
| 2026-03-02 | Project scaffold + config setup | claude-sonnet-4-6 | — | — | — |
| | | | | **Total Dev:** | $0.00 |

---

## Ingestion Spend (One-Time)

These are the costs to index the gnucobol-contrib codebase into Pinecone.
This runs once — embeddings are stored and reused for all queries.

| Run # | Date | Files Indexed | Total LOC | Chunks Created | Embedding Tokens | Cost |
|-------|------|--------------|-----------|----------------|-----------------|------|
| 1 | — | — | — | — | — | — |

**Actual codebase stats (cloned 2026-03-02):**
- Source: https://github.com/OCamlPro/gnucobol-contrib
- .cob files: 331 | .cbl files: 246 | .cpy copybooks: 214
- Total COBOL source files (cob + cbl): 577
- Total lines of code: 251,881

**Expected cost estimate (revised):**
- 577 COBOL files → ~6,300 chunks (at ~40 lines/chunk, paragraph-level)
- Each chunk: ~200 tokens average
- Total embedding tokens: 6,300 × 200 = 1,260,000 tokens
- Cost: 1,260,000 / 1,000,000 × $0.02 = **~$0.025** (essentially free)

---

## Per-Query Costs (Production Estimates)

Each user query involves:
1. Embed the query: ~20 tokens × $0.02/M = $0.0000004
2. Pinecone search: free (included in Pinecone tier)
3. GPT-4o-mini answer generation:
   - Input: ~2,000 tokens (system prompt + retrieved COBOL context)
   - Output: ~300 tokens (the answer)
   - Cost: (2,000 × $0.15 + 300 × $0.60) / 1,000,000 = **$0.000480**

**Effective cost per query: ~$0.0005 (half a cent)**

---

## Monthly Cost Projections

Assumptions:
- 5 queries per user per day
- Average tokens per query: 2,300 input + 300 output (as above)
- Pinecone serverless: $0.096/hour per namespace + storage

| Users | Queries/Month | Embedding Cost | LLM Cost | Pinecone Cost | **Total/Month** |
|-------|--------------|----------------|----------|---------------|-----------------|
| 100 | 15,000 | $0.00 | $7.20 | ~$5.00 | **~$12.20** |
| 1,000 | 150,000 | $0.00 | $72.00 | ~$15.00 | **~$87.00** |
| 10,000 | 1,500,000 | $0.01 | $720.00 | ~$50.00 | **~$770.00** |
| 100,000 | 15,000,000 | $0.06 | $7,200.00 | ~$200.00 | **~$7,400.00** |

**Key insight:** At scale, LLM answer generation dominates the cost.
The main lever for cost reduction is:
- Caching repeated queries (same question → same answer, free)
- Using prompt caching for the large system prompt
- Reducing top_k from 10 to 5 (cuts context tokens ~40%)

---

## Cost Reduction Strategies

Already implemented:
- [ ] text-embedding-3-small instead of large (5x cheaper)
- [ ] GPT-4o-mini instead of GPT-4o (15x cheaper)
- [ ] top_k=5 for answer generation (not 10) — limits context tokens

Planned for G4:
- [ ] OpenAI prompt caching (saves ~50% on repeated system prompt)
- [ ] Query result caching with Redis (same query → skip Pinecone + LLM)
- [ ] Similarity threshold filtering (don't call GPT-4o-mini if no good results)
