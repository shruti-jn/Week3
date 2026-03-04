# Experiment Brief: voyage-code-2 vs text-embedding-3-small on COBOL Retrieval

**For:** Fresh agent session
**Context:** LegacyLens — RAG-powered COBOL code search (working dir: `/Users/shruti/Week3`)
**Goal:** Compare voyage-code-2 against text-embedding-3-small on the 5 failing golden queries.
Do NOT re-index all 577 files. This is a sample test only.

---

## Background (read this first)

LegacyLens indexes COBOL source files into Pinecone and answers developer queries
like "how does DES encryption work?" by retrieving the relevant code chunk.

Current embedding model: **OpenAI text-embedding-3-small** (1536 dims, cosine similarity)
Current vector DB: **Pinecone** (index: `legacylens`, serverless)

Current golden query results — 5/10 passing:

| Query | Score | Threshold | Pass? |
|-------|-------|-----------|-------|
| "file sort COBOL program" | 0.805 | 0.75 | ✅ |
| "how to sort a file in COBOL" | 0.750 | 0.75 | ❌ (float edge) |
| "DES encryption algorithm COBOL" | 0.711 | 0.70 | ✅ |
| **"how to set up encryption keys from a password"** | **0.464** | 0.70 | **❌** |
| **"database connection SQL COBOL program"** | **0.693** | 0.70 | **❌ (−0.007)** |
| **"how to insert a record into a database"** | **0.491** | 0.70 | **❌** |
| "file upload multipart COBOL CGI" | 0.733 | 0.70 | ✅ |
| **"parse HTML form data CGI COBOL"** | **0.634** | 0.65 | **❌** |
| "prime number test COBOL" | 0.661 | 0.65 | ✅ |
| "date calculation COBOL calendar" | 0.706 | 0.65 | ✅ |

The 5 failing queries are in **bold**. The hypothesis is that voyage-code-2
(a code-specific embedding model) may score higher because it was trained on
code ↔ natural-language pairs, which is exactly the gap we're trying to bridge.

---

## Why voyage-code-2 Might Help

The failing queries break down into two categories:

1. **SQL gap** (gq-005, gq-006): Queries use English ("insert a record into a database")
   but the code uses embedded SQL syntax (`EXEC SQL INSERT INTO books VALUES...`).
   voyage-code-2 was trained to align NL with SQL and other programming constructs.

2. **Terminology gap** (gq-004 SETKEY, gq-008 CGI): The code body has no English —
   either a PC1/PC2 permutation table (rows of bit-index numbers) or CGI handler code
   with opaque variable names (`COB2CGI-*`).

voyage-code-2 is unlikely to help gq-004 (SETKEY) — no model can bridge "encryption
keys from a password" and a table of numbers. But it might help gq-005, gq-006, gq-008.

---

## Files Involved in the Test

Focus on these COBOL files only — do NOT index the full 577-file corpus:

| Golden query | COBOL file | What to test |
|---|---|---|
| gq-004 "encryption keys password" | `data/gnucobol-contrib/samples/cobdes/cobdes.cob` | SETKEY section |
| gq-005 "database connection" | `data/gnucobol-contrib/samples/DBsample/PostgreSQL/example1/PGMOD1.cbl` | CONNECT section |
| gq-006 "insert a record" | `data/gnucobol-contrib/samples/DBsample/PostgreSQL/example5/PGMOD5.cbl` | INSERT-BOOK section |
| gq-008 "parse HTML form data" | `data/gnucobol-contrib/samples/cgiform/cgiform.cob` | COB2CGI-* sections |

---

## The Experiment

### Step 1: Get a voyage-code-2 API key

Sign up at https://www.voyageai.com/ — free tier is sufficient for this test (~100 embeddings).
Add to `backend/.env`:
```
VOYAGE_API_KEY=<your key here>
```

### Step 2: Install the voyageai client

```bash
/Users/shruti/Week3/backend/.venv/bin/pip install voyageai
```

### Step 3: Run the comparison script

Create a temporary script at `/Users/shruti/Week3/backend/scripts/compare_embeddings.py`.
The script should:

1. Read the 4 COBOL files listed above
2. Chunk them using the existing chunker (import `chunk_cobol_file` from `app.core.ingestion.chunker`)
3. For each chunk, embed with BOTH models:
   - `text-embedding-3-small` via OpenAI (use existing key from backend/.env)
   - `voyage-code-2` via voyageai
4. For each of the 5 failing queries, compute cosine similarity against all chunks from the relevant file
5. Report the top-3 results and their scores for each model

**Key imports and paths:**
```python
# CWD must be /Users/shruti/Week3/backend/ for config to find .env
# Or: sys.path.insert(0, '/Users/shruti/Week3/backend')
from app.core.ingestion.chunker import chunk_cobol_file
from app.core.ingestion.embedder import build_embedding_text
from pathlib import Path
```

The existing `build_embedding_text(chunk)` function in `backend/app/core/ingestion/embedder.py`
builds the Q&A-enriched embedding text. Use it for both models — this isolates the model
comparison from the text-building strategy.

Cosine similarity formula (both models use cosine, normalised vectors):
```python
import numpy as np
def cosine_sim(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
```

### Step 4: Report results

Print a table like this for each query:
```
Query: "how to insert a record into a database"
File: PGMOD5.cbl

Model                    | Chunk              | Score
-------------------------|--------------------|---------
text-embedding-3-small   | INSERT-BOOK        | 0.491
text-embedding-3-small   | INSERT-BOOK-EX     | 0.483
voyage-code-2            | INSERT-BOOK        | ???
voyage-code-2            | INSERT-BOOK-EX     | ???
```

### Step 5: Write findings to docs/embedding-score-optimization.md

Append a new section: **"Phase 3 — voyage-code-2 Experiment Results"**

Include:
- The full results table (text-embedding-3-small vs voyage-code-2 for each failing query)
- Whether voyage-code-2 would push any of the 5 failing queries above their threshold
- A recommendation: switch models / keep current / use hybrid search instead
- Cost comparison: text-embedding-3-small ($0.02/1M tokens) vs voyage-code-2 ($0.06/1M tokens retrieval)

---

## What NOT To Do

- Do NOT re-index Pinecone. This is a local cosine similarity test only.
- Do NOT modify any source files other than the new compare script.
- Do NOT change golden_queries.json.
- The existing Pinecone index has 5286 vectors from text-embedding-3-small. Leave it alone.

---

## Environment

- Python: `/Users/shruti/Week3/backend/.venv/bin/python` (Python 3.12)
- Backend config: `/Users/shruti/Week3/backend/.env` (has OPENAI_API_KEY, PINECONE_API_KEY)
- COBOL source: `/Users/shruti/Week3/data/gnucobol-contrib/`
- Key module: `backend/app/core/ingestion/chunker.py` — `chunk_cobol_file(path, content)`
- Key module: `backend/app/core/ingestion/embedder.py` — `build_embedding_text(chunk)`
- Run scripts from: `/Users/shruti/Week3/backend/` directory (so `.env` is found)

---

## Decision Criteria

After running the experiment, make a call:

| Outcome | Recommendation |
|---|---|
| voyage-code-2 scores 0.70+ on gq-005, gq-006, gq-008 | Switch models, re-index |
| voyage-code-2 scores 0.65–0.70 on those queries | Marginal gain, not worth the cost + re-index |
| voyage-code-2 scores same as text-embedding-3-small | DB is not the bottleneck — try query tuning or annotations |
| All models fail gq-004 SETKEY | Confirm SETKEY is unreachable, replace that golden query |
