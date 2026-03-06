# Deployed API Golden Evaluation

- Generated at: `2026-03-06T04:55:54.467744+00:00`
- Backend URL: `https://week3-production-e652.up.railway.app`
- Score metric used: `combined_score` (0.7*cosine + 0.3*keyword_overlap)
- Top-k: `5`
- Precision@5: `0.7727` (17/22)
- Precision target: `0.70`
- Latency p50 (query_time_ms): `2154.90` ms
- Latency p95 (query_time_ms): `3022.50` ms
- Latency target: `< 3000` ms

| ID | Pass | Matched | Threshold | Top | Query ms | Failure Mode | Reason |
|---|---|---:|---:|---:|---:|---|---|
| gq-001 | PASS | 0.8875 | 0.65 | 0.8875 | 2245.80 | passed | expected chunk found and passed threshold |
| gq-002 | PASS | 0.8839 | 0.65 | 0.8839 | 2737.16 | passed | expected chunk found and passed threshold |
| gq-003 | FAIL | 0.6550 | 0.70 | 0.7275 | 2717.22 | below_threshold | expected chunk found but below threshold |
| gq-004 | FAIL | 0.6257 | 0.70 | 0.6675 | 184.10 | below_threshold | expected chunk found but below threshold |
| gq-005 | FAIL | 0.6563 | 0.70 | 0.6563 | 168.37 | below_threshold | expected chunk found but below threshold |
| gq-006 | PASS | 0.7351 | 0.70 | 0.7351 | 1937.36 | passed | expected chunk found and passed threshold |
| gq-007 | FAIL | 0.6375 | 0.70 | 0.6386 | 203.40 | below_threshold | expected chunk found but below threshold |
| gq-008 | PASS | 0.6826 | 0.65 | 0.6826 | 4394.58 | passed | expected chunk found and passed threshold |
| gq-009 | FAIL | 0.6275 | 0.65 | 0.6541 | 186.65 | below_threshold | expected chunk found but below threshold |
| gq-010 | PASS | 0.6516 | 0.65 | 0.6516 | 171.71 | passed | expected chunk found and passed threshold |
| gq-011 | PASS | 0.7148 | 0.60 | 0.7148 | 3036.93 | passed | expected chunk found and passed threshold |
| gq-012 | PASS | 0.6533 | 0.60 | 0.6786 | 2700.70 | passed | expected chunk found and passed threshold |
| gq-013 | PASS | 0.7186 | 0.60 | 0.7186 | 1997.58 | passed | expected chunk found and passed threshold |
| gq-014 | PASS | 0.7217 | 0.60 | 0.7217 | 1905.63 | passed | expected chunk found and passed threshold |
| gq-015 | PASS | 0.7585 | 0.60 | 0.7585 | 2684.07 | passed | expected chunk found and passed threshold |
| gq-016 | PASS | 0.6941 | 0.60 | 0.6941 | 178.71 | passed | expected chunk found and passed threshold |
| gq-017 | PASS | 0.6980 | 0.60 | 0.6980 | 2580.08 | passed | expected chunk found and passed threshold |
| gq-018 | PASS | 0.6949 | 0.60 | 0.6949 | 538.55 | passed | expected chunk found and passed threshold |
| gq-019 | PASS | 0.7921 | 0.60 | 0.7921 | 2748.41 | passed | expected chunk found and passed threshold |
| gq-020 | PASS | 0.7189 | 0.60 | 0.7189 | 2634.17 | passed | expected chunk found and passed threshold |
| gq-021 | PASS | 0.7649 | 0.65 | 0.7649 | 2081.40 | passed | expected chunk found and passed threshold |
| gq-022 | PASS | 0.6401 | 0.60 | 0.7151 | 2228.41 | passed | expected chunk found and passed threshold |
