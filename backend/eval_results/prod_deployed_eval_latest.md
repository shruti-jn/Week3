# Deployed API Golden Evaluation

- Generated at: `2026-03-05T20:42:41.858317+00:00`
- Backend URL: `https://week3-production-e652.up.railway.app`
- Top-k: `5`
- Precision@5: `0.5000` (5/10)
- Precision target: `0.70`
- Latency p50 (query_time_ms): `5216.90` ms
- Latency p95 (query_time_ms): `8523.54` ms
- Latency target: `< 3000` ms

| ID | Pass | Matched | Threshold | Top Score | Query ms | Reason |
|---|---|---:|---:|---:|---:|---|
| gq-001 | PASS | 0.8875 | 0.75 | 0.8875 | 5960.14 | expected chunk found and passed threshold |
| gq-002 | PASS | 0.8839 | 0.75 | 0.8839 | 5386.36 | expected chunk found and passed threshold |
| gq-003 | FAIL | 0.6550 | 0.70 | 0.7275 | 3948.33 | expected chunk found but below threshold |
| gq-004 | FAIL | - | 0.70 | 0.0000 | 176.74 | expected chunk not in top-5 |
| gq-005 | FAIL | - | 0.70 | 0.6563 | 5698.16 | expected chunk not in top-5 |
| gq-006 | FAIL | - | 0.70 | 0.0000 | 250.01 | expected chunk not in top-5 |
| gq-007 | FAIL | 0.6881 | 0.70 | 0.6906 | 4839.04 | expected chunk found but below threshold |
| gq-008 | PASS | 0.6826 | 0.65 | 0.6826 | 5356.44 | expected chunk found and passed threshold |
| gq-009 | PASS | 0.7720 | 0.65 | 0.7720 | 5077.35 | expected chunk found and passed threshold |
| gq-010 | PASS | 0.6516 | 0.65 | 0.6516 | 10620.87 | expected chunk found and passed threshold |

---

## Run History

| Date (UTC) | Run Type | Evidence File | Precision@5 | Pass Count | Latency | Notes |
|---|---|---|---:|---:|---|---|
| 2026-03-06T03:16:39Z | Local index eval | `backend/eval_results/latest_eval.json` | 1.0000 | 21/21 | N/A | Direct Pinecone eval with `voyage-code-2`. |
| 2026-03-06T03:21:23Z | Deployed API eval | `backend/eval_results/deployed_latest_eval.json` | 0.7143 | 15/21 | p50 1300.42 ms, p95 3318.96 ms | Precision target met; p95 latency missed <3000 ms target. |

### Local vs deployed delta (2026-03-06)

- Average matched-score drop: **-0.1044**
- Deployed failures: `gq-003`, `gq-004`, `gq-005`, `gq-007`, `gq-009`, `gq-016`
- Largest drops: `gq-007` (-0.2046), `gq-005` (-0.1956), `gq-003` (-0.1736)
