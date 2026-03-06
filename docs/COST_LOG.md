# LegacyLens - AI Cost Analysis

This file is the submission-ready AI cost analysis required by
`LegacyLensProject.md` and also acts as the running cost ledger for the project.

---

## 1) Scope and Method

This analysis covers:
- Development and testing spend
- One-time ingestion/indexing spend
- Per-query production unit economics
- Monthly projections at 100 / 1K / 10K / 100K users

All projections are formula-based so they are easy to audit and update.

---

## 2) Pricing Snapshot and Assumptions

### Model and infra assumptions
- Embeddings model: `voyage-code-2`
- Answer model: `gpt-4o-mini`
- Vector DB: Pinecone serverless
- Projection window: 30-day month

### Price assumptions used in this doc
- `voyage-code-2` embeddings: **$0.06 / 1M tokens**
- `gpt-4o-mini` input: **$0.15 / 1M tokens**
- `gpt-4o-mini` output: **$0.60 / 1M tokens**
- Pinecone monthly infra estimate by scale:
  - 100 users: **$5**
  - 1,000 users: **$15**
  - 10,000 users: **$50**
  - 100,000 users: **$200**

### Usage assumptions
- Queries per active user per day: **5**
- Query embedding tokens: **20**
- LLM input tokens per query: **2,000**
- LLM output tokens per query: **300**
- Incremental code ingestion (new code added monthly): **100,000 embedding tokens/month**

---

## 3) Development and Testing Costs

### 3.1 Logged development sessions

| Date Range | Task | Evidence Source | Token Basis | Cost (USD) |
|-----------|------|-----------------|-------------|------------|
| 2026-03-03 to 2026-03-06 | Golden and deployed eval runs | `backend/eval_results/*.json` (174 total queries logged) | 174 queries x $0.0004812/query | **$0.084** |
| 2026-03-03 | Model comparison experiment | `docs/embedding-score-optimization.md` Phase 3 + `backend/scripts/compare_embeddings.py` | Small local experiment on 4 files; bounded test spend | **~$0.01** |
| 2026-03-02 to 2026-03-05 | Iterative re-index/testing passes | `docs/BUILD_ORDER.md` cost model + ingestion notes | Multiple low-cost embedding-only passes | **~$0.01** |
| 2026-03-02 to 2026-03-06 | Pinecone dev usage | Project infra logs/notes | Serverless dev-scale usage | **~$0.00 to $5.00** |
| | | | **Estimated Development + Testing Total** | **~$0.10 to $5.10** |

This total is a reconstructed estimate from repository artifacts. It excludes any
non-project assistant subscription/tooling costs and should be treated as
project-run API spend only.

### 3.2 One-time indexing spend (measured + estimated)

Known corpus stats:
- Source: [gnucobol-contrib](https://github.com/OCamlPro/gnucobol-contrib)
- COBOL files (`.cob` + `.cbl`): **577**
- Lines of code: **251,881**
- Prior measured re-index estimate from experiments: **~793,000 tokens**

One-time embedding cost formula:
- `cost = (embedding_tokens / 1,000,000) * 0.06`
- `cost = (793,000 / 1,000,000) * 0.06 = $0.04758`

**One-time indexing spend: ~$0.05**

This is effectively negligible relative to monthly inference cost.

---

## 4) Per-Query Unit Economics

### 4.1 Embedding cost per query
- Formula: `(20 / 1,000,000) * 0.06`
- Result: **$0.0000012**

### 4.2 LLM generation cost per query
- Input: `(2,000 / 1,000,000) * 0.15 = $0.000300`
- Output: `(300 / 1,000,000) * 0.60 = $0.000180`
- Total LLM/query: **$0.000480**

### 4.3 Total variable AI cost per query
- Formula: `embedding/query + llm/query`
- Result: `0.0000012 + 0.000480 = $0.0004812`

**Effective variable cost/query: ~$0.00048**

---

## 5) Monthly Cost Projections (Required Scales)

### 5.1 Shared formulas
- `queries_per_month = users * 5 * 30`
- `query_variable_cost = queries_per_month * 0.0004812`
- `monthly_incremental_embedding = (100,000 / 1,000,000) * 0.06 = $0.006`
- `total_monthly = query_variable_cost + pinecone_monthly + monthly_incremental_embedding`

### 5.2 Projection table

| Users | Queries/Month | Query Variable Cost | Incremental Embedding | Pinecone | **Total/Month** |
|------:|--------------:|--------------------:|----------------------:|---------:|----------------:|
| 100 | 15,000 | $7.218 | $0.006 | $5.000 | **$12.224** |
| 1,000 | 150,000 | $72.180 | $0.006 | $15.000 | **$87.186** |
| 10,000 | 1,500,000 | $721.800 | $0.006 | $50.000 | **$771.806** |
| 100,000 | 15,000,000 | $7,218.000 | $0.006 | $200.000 | **$7,418.006** |

Note: totals are computed from unrounded formula outputs. If you present 2-decimal
currency in slides, use: $12.22, $87.19, $771.81, and $7,418.01.

---

## 6) Sensitivity Analysis (Query Volume)

To show how usage affects cost, this section varies only queries/user/day.

Assumptions:
- Same token profile and pricing
- 1,000 active users
- Pinecone fixed at $15/month for this scenario

| Scenario | Queries/User/Day | Queries/Month | Query Variable Cost | Total/Month |
|----------|------------------:|--------------:|--------------------:|------------:|
| Low | 2 | 60,000 | $28.87 | $43.88 |
| Base | 5 | 150,000 | $72.18 | $87.19 |
| High | 10 | 300,000 | $144.36 | $159.37 |

Key takeaway: inference traffic is the dominant cost driver; storage/infra is secondary.

---

## 7) Requirement Coverage

This doc maps directly to `LegacyLensProject.md` AI cost requirements:
- Development and testing costs: Section 3
- Embedding API costs: Sections 3.2, 4.1, and 5
- LLM API costs for answer generation: Sections 4.2 and 5
- Vector DB hosting/usage costs: Sections 2 and 5
- Monthly projections for 100/1K/10K/100K users: Section 5
- Assumptions and formulas: Sections 2 and 5.1

---

## 8) Cost Reduction Levers

Already implemented:
- Use `gpt-4o-mini` for generation (low per-token inference cost)
- Limit answer context to top-ranked chunks (reduces LLM input tokens)
- Keep embeddings compact and code-focused (`voyage-code-2`)

Planned next:
- Cache repeated query answers to avoid repeated LLM calls
- Add prompt caching where supported
- Skip generation when confidence gate fails
- Further tune prompt/context size based on latency-quality-cost tradeoff

---

## 9) Final Submission Notes

- If reviewers request strict accounting, append dashboard-exported usage CSVs to
  this document. Current Section 3.1 values are evidence-based reconstructed estimates.
- The project prompt does not enforce a specific filename, so `docs/COST_LOG.md` can be submitted as the AI Cost Analysis deliverable.

