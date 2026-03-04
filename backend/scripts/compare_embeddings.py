"""
compare_embeddings.py — Side-by-side comparison of voyage-code-2 vs
text-embedding-3-small on the 5 failing LegacyLens golden queries.

This is a LOCAL experiment only — nothing is written to Pinecone.
We chunk the relevant COBOL files, embed every chunk with both models,
then compute cosine similarity for each failing query and print a table.

Think of it like a taste test: same food (COBOL chunks), two judges
(embedding models), scored on the same scale (cosine similarity).

Usage (run from /Users/shruti/Week3/backend/):
    ../backend/.venv/bin/python scripts/compare_embeddings.py

Requirements in backend/.env:
    OPENAI_API_KEY=sk-...
    VOYAGE_API_KEY=pa-...  ← sign up at https://www.voyageai.com/
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# ── path setup ────────────────────────────────────────────────────────────────
# Add backend/ to sys.path so `app.*` imports resolve correctly.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _load_dotenv(env_path: Path) -> None:
    """
    Read a .env file and push each key=value pair into os.environ.

    Like a starter pistol for environment variables — runs before anything
    else so every subsequent import sees the right keys.

    Only sets variables that are NOT already in the environment, so real
    env vars (Railway, CI) always take priority over the file.

    Args:
        env_path: Path to the .env file to read. Silently skipped if missing.
    """
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        # Strip surrounding quotes that some editors add to values
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)


_load_dotenv(BACKEND_DIR / ".env")

# ── guarded imports (after .env is loaded) ───────────────────────────────────
import time  # noqa: E402

import numpy as np  # noqa: E402
import openai  # noqa: E402
import voyageai  # noqa: E402

from app.core.ingestion.chunker import COBOLChunk, chunk_cobol_file  # noqa: E402
from app.core.ingestion.embedder import build_embedding_text  # noqa: E402

# ── API key validation ────────────────────────────────────────────────────────
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
VOYAGE_KEY = os.environ.get("VOYAGE_API_KEY", "")

if not OPENAI_KEY:
    sys.exit("ERROR: OPENAI_API_KEY not found in backend/.env")
if not VOYAGE_KEY:
    sys.exit(
        "ERROR: VOYAGE_API_KEY not found in backend/.env\n"
        "  Sign up at https://www.voyageai.com/ (free tier is enough)\n"
        "  Then add: VOYAGE_API_KEY=pa-... to backend/.env"
    )

# ── clients ───────────────────────────────────────────────────────────────────
# Synchronous clients — simpler for a one-off comparison script.
oai_client = openai.OpenAI(api_key=OPENAI_KEY)
voyage_client = voyageai.Client(api_key=VOYAGE_KEY)

# Free-tier Voyage rate limit: 3 requests per minute.
# We sleep this many seconds before every Voyage API call to stay within it.
# 21s gives a comfortable margin (60s / 3 req = 20s minimum between calls).
_VOYAGE_RATE_LIMIT_SLEEP_S: float = 21.0
_last_voyage_call_ts: float = 0.0

# ── file paths ────────────────────────────────────────────────────────────────
SAMPLES_DIR = BACKEND_DIR.parent / "data" / "gnucobol-contrib" / "samples"

# The 4 failing golden queries that voyage-code-2 might help with.
# gq-002 (float edge at exactly 0.750) is excluded — the GCSORT files score
# reliably and the issue is floating-point precision, not model quality.
EXPERIMENTS: list[dict[str, Any]] = [
    {
        "query_id": "gq-004",
        "query": "how to set up encryption keys from a password",
        "threshold": 0.70,
        "baseline": 0.464,
        "file": SAMPLES_DIR / "cobdes" / "cobdes.cob",
        "note": "SETKEY section — PC1/PC2 permutation table, pure numbers, no English",
    },
    {
        "query_id": "gq-005",
        "query": "database connection SQL COBOL program",
        "threshold": 0.70,
        "baseline": 0.693,
        "file": SAMPLES_DIR / "DBsample" / "PostgreSQL" / "example1" / "PGMOD1.cbl",
        "note": "EXEC SQL CONNECT — only −0.007 from threshold",
    },
    {
        "query_id": "gq-006",
        "query": "how to insert a record into a database",
        "threshold": 0.70,
        "baseline": 0.491,
        "file": SAMPLES_DIR / "DBsample" / "PostgreSQL" / "example5" / "PGMOD5.cbl",
        "note": "EXEC SQL INSERT — NL↔SQL gap is the core challenge",
    },
    {
        "query_id": "gq-008",
        "query": "parse HTML form data CGI COBOL",
        "threshold": 0.65,
        "baseline": 0.634,
        "file": SAMPLES_DIR / "cgiform" / "cgiform.cob",
        "note": "COB2CGI-* sections — only −0.016 from threshold",
    },
]


# ── helpers ───────────────────────────────────────────────────────────────────


def cosine_sim(a: list[float], b: list[float]) -> float:
    """
    Compute the cosine similarity between two embedding vectors.

    Cosine similarity measures the angle between two vectors:
    - 1.0 means identical direction (same meaning)
    - 0.0 means perpendicular (unrelated)
    - −1.0 means opposite directions (rare in practice for embeddings)

    Both OpenAI and Voyage return normalised vectors, so this equals
    the dot product. We compute it explicitly to be safe.

    Args:
        a: First embedding vector (list of floats from any model).
        b: Second embedding vector (same dimensionality as a).

    Returns:
        Cosine similarity as a float in [−1.0, 1.0].
    """
    av = np.array(a)
    bv = np.array(b)
    return float(np.dot(av, bv) / (np.linalg.norm(av) * np.linalg.norm(bv)))


def embed_oai(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts with OpenAI text-embedding-3-small.

    Args:
        texts: List of strings to embed (queries or document chunks).

    Returns:
        List of 1536-float vectors, one per input text, in the same order.
    """
    response = oai_client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in response.data]


def embed_voyage(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """
    Embed a list of texts with Voyage voyage-code-2.

    voyage-code-2 is a code-specific model trained to align natural-language
    descriptions with programming constructs (SQL, COBOL, etc.).

    input_type="document" for chunks being indexed.
    input_type="query"    for the search query.
    Using the right type activates asymmetric retrieval optimisation.

    Rate limiting: the free Voyage tier allows 3 requests per minute.
    We track the timestamp of the last call and sleep long enough to stay
    within the limit before every call.

    Args:
        texts:      List of strings to embed.
        input_type: "document" (chunks) or "query" (search queries).

    Returns:
        List of float vectors (voyage-code-2 uses 1536 dims), one per input.
    """
    global _last_voyage_call_ts
    elapsed = time.monotonic() - _last_voyage_call_ts
    wait = _VOYAGE_RATE_LIMIT_SLEEP_S - elapsed
    if wait > 0:
        print(f"  [rate-limit] waiting {wait:.1f}s for Voyage free-tier (3 RPM)...",
              end=" ", flush=True)
        time.sleep(wait)
    _last_voyage_call_ts = time.monotonic()
    result = voyage_client.embed(texts, model="voyage-code-2", input_type=input_type)
    return result.embeddings  # type: ignore[no-any-return]


def load_and_chunk(file_path: Path) -> list[COBOLChunk]:
    """
    Read a COBOL file from disk and split it into paragraph-level chunks.

    Args:
        file_path: Absolute path to a .cob or .cbl file.

    Returns:
        List of COBOLChunk objects from the project's chunker.
    """
    content = file_path.read_text(errors="replace")
    return chunk_cobol_file(file_path, content)


# ── per-query experiment ──────────────────────────────────────────────────────

ExperimentResult = dict[str, Any]


def run_one(exp: dict[str, Any]) -> ExperimentResult:
    """
    Run one query comparison: chunk a file, embed with both models, score.

    Steps:
    1. Load and chunk the COBOL file specified in exp["file"]
    2. Build embedding text for every chunk (same text for both models)
    3. Embed all chunks with OpenAI + Voyage in parallel batches
    4. Embed the query with both models (using "query" input_type for Voyage)
    5. Compute cosine similarity for every chunk against the query
    6. Print top-3 results per model and a delta summary

    Args:
        exp: One entry from the EXPERIMENTS list (query, file, threshold, etc.)

    Returns:
        Dict with best scores, winning chunk names, delta, and pass/fail flags.
    """
    query_id: str = exp["query_id"]
    query: str = exp["query"]
    threshold: float = exp["threshold"]
    baseline: float = exp["baseline"]
    file_path: Path = exp["file"]
    note: str = exp["note"]

    print(f"\n{'=' * 74}")
    print(f"  {query_id}: \"{query}\"")
    print(f"  File:      {file_path.name}")
    print(f"  Threshold: {threshold}  |  Baseline (OpenAI, Pinecone): {baseline:.3f}")
    print(f"  Note:      {note}")
    print(f"{'=' * 74}")

    # ── chunk ────────────────────────────────────────────────────────────────
    chunks = load_and_chunk(file_path)
    print(f"  Chunks:  {len(chunks)}")

    # Build the enriched embedding text using the same function the ingestion
    # pipeline uses — this isolates the model comparison from text strategy.
    texts = [build_embedding_text(c) for c in chunks]

    # ── embed chunks ─────────────────────────────────────────────────────────
    print("  Embedding chunks with text-embedding-3-small ... ", end="", flush=True)
    oai_doc_vecs = embed_oai(texts)
    print("done")

    # For large files, the free-tier 10K TPM limit prevents embedding all chunks
    # in a single Voyage call. Pre-filter to the top-30 by OpenAI score and run
    # only those through Voyage. This still answers "does Voyage rank the best
    # chunk higher?" without requiring 245 chunks × ~400 tokens per call.
    _VOYAGE_MAX_CHUNKS = 30
    if len(chunks) > _VOYAGE_MAX_CHUNKS:
        # Score with OpenAI first to pick the most promising candidates
        oai_q_vec_preflight = embed_oai([query])[0]
        oai_pre = sorted(
            enumerate(oai_doc_vecs),
            key=lambda iv: cosine_sim(oai_q_vec_preflight, iv[1]),
            reverse=True,
        )
        top_indices = [idx for idx, _ in oai_pre[:_VOYAGE_MAX_CHUNKS]]
        voyage_texts = [texts[i] for i in top_indices]
        _voyage_subset: list[COBOLChunk] = [chunks[i] for i in top_indices]
        print(
            f"  (Large file: pre-filtering to top {_VOYAGE_MAX_CHUNKS} chunks "
            f"by OpenAI score for Voyage — free-tier 10K TPM limit)"
        )
    else:
        voyage_texts = texts
        _voyage_subset = chunks
        oai_q_vec_preflight = None  # will embed fresh below

    print("  Embedding chunks with voyage-code-2 ...          ", end="", flush=True)
    voyage_doc_vecs = embed_voyage(voyage_texts, input_type="document")
    print("done")

    # ── embed query ──────────────────────────────────────────────────────────
    print("  Embedding query ...                               ", end="", flush=True)
    # Reuse the preflight embedding if we already computed it above
    oai_q_vec: list[float] = oai_q_vec_preflight if oai_q_vec_preflight is not None else embed_oai([query])[0]
    # Voyage asymmetric retrieval: use "query" type for the search query
    voyage_q_vec = embed_voyage([query], input_type="query")[0]
    print("done")

    # ── score ────────────────────────────────────────────────────────────────
    oai_scored: list[tuple[float, COBOLChunk]] = sorted(
        ((cosine_sim(oai_q_vec, vec), chunks[i]) for i, vec in enumerate(oai_doc_vecs)),
        key=lambda t: t[0],
        reverse=True,
    )
    # voyage_scored covers only _voyage_subset (pre-filtered for large files)
    voyage_scored: list[tuple[float, COBOLChunk]] = sorted(
        (
            (cosine_sim(voyage_q_vec, vec), _voyage_subset[i])
            for i, vec in enumerate(voyage_doc_vecs)
        ),
        key=lambda t: t[0],
        reverse=True,
    )

    # ── print top-3 ──────────────────────────────────────────────────────────
    col_model = 26
    col_chunk = 34
    header = f"\n  {'Model':<{col_model}} {'Top Chunk':<{col_chunk}} {'Score':>8}  Pass?"
    divider = f"  {'-' * col_model} {'-' * col_chunk} {'-' * 8}  {'-' * 5}"
    print(header)
    print(divider)

    def _chunk_label(chunk: COBOLChunk) -> str:
        return chunk.paragraph_name or f"chunk_{chunk.chunk_index}"

    for score, chunk in oai_scored[:3]:
        passed = "✅" if score >= threshold else "❌"
        label = _chunk_label(chunk)[:col_chunk]
        print(f"  {'text-embedding-3-small':<{col_model}} {label:<{col_chunk}} {score:>8.4f}  {passed}")

    print()

    for score, chunk in voyage_scored[:3]:
        passed = "✅" if score >= threshold else "❌"
        label = _chunk_label(chunk)[:col_chunk]
        print(f"  {'voyage-code-2':<{col_model}} {label:<{col_chunk}} {score:>8.4f}  {passed}")

    # ── delta summary ────────────────────────────────────────────────────────
    oai_best_score = oai_scored[0][0]
    voyage_best_score = voyage_scored[0][0]
    delta = voyage_best_score - oai_best_score
    sign = "+" if delta >= 0 else ""
    verdict = (
        "→ voyage-code-2 PASSES threshold ✅"
        if voyage_best_score >= threshold
        else f"→ voyage best is {voyage_best_score:.4f}, threshold is {threshold}"
    )
    print(f"\n  Delta (voyage − openai):  {sign}{delta:.4f}  {verdict}")

    return {
        "query_id": query_id,
        "query": query,
        "threshold": threshold,
        "baseline": baseline,
        "oai_best_score": oai_best_score,
        "oai_best_chunk": _chunk_label(oai_scored[0][1]),
        "oai_passes": oai_best_score >= threshold,
        "voyage_best_score": voyage_best_score,
        "voyage_best_chunk": _chunk_label(voyage_scored[0][1]),
        "voyage_passes": voyage_best_score >= threshold,
        "delta": delta,
    }


# ── summary table ─────────────────────────────────────────────────────────────


def print_summary(results: list[ExperimentResult]) -> None:
    """
    Print a final cross-query summary table after all experiments complete.

    Shows per-query best scores, pass/fail, and winner for each row.
    Prints aggregate counts at the bottom.

    Args:
        results: List of ExperimentResult dicts from run_one().
    """
    print(f"\n\n{'=' * 90}")
    print("  FINAL SUMMARY — voyage-code-2 vs text-embedding-3-small")
    print(f"{'=' * 90}")
    print(
        f"  {'Query':<10} {'Baseline':>10} {'OpenAI':>12} {'Voyage':>12} "
        f"{'Delta':>9}  {'Threshold':>10}  Result"
    )
    print(
        f"  {'-' * 10} {'-' * 10} {'-' * 12} {'-' * 12} "
        f"{'-' * 9}  {'-' * 10}  {'-' * 20}"
    )

    for r in results:
        oai_str = f"{r['oai_best_score']:.4f} {'✅' if r['oai_passes'] else '❌'}"
        voy_str = f"{r['voyage_best_score']:.4f} {'✅' if r['voyage_passes'] else '❌'}"
        base_str = f"{r['baseline']:.4f}"
        delta_str = f"{'+' if r['delta'] >= 0 else ''}{r['delta']:.4f}"

        if r["voyage_passes"] and not r["oai_passes"]:
            result = "VOYAGE UNLOCKS ✅"
        elif r["oai_passes"] and not r["voyage_passes"]:
            result = "OPENAI only ✅"
        elif r["voyage_passes"] and r["oai_passes"]:
            result = "both pass ✅"
        elif r["voyage_best_score"] > r["oai_best_score"]:
            result = "voyage higher ↑ (both fail)"
        elif r["oai_best_score"] > r["voyage_best_score"]:
            result = "openai higher ↑ (both fail)"
        else:
            result = "tied (both fail)"

        print(
            f"  {r['query_id']:<10} {base_str:>10} {oai_str:>12} {voy_str:>12} "
            f"{delta_str:>9}  {r['threshold']:>10.2f}  {result}"
        )

    voyage_unlocks = sum(
        1 for r in results if r["voyage_passes"] and not r["oai_passes"]
    )
    voyage_higher = sum(1 for r in results if r["voyage_best_score"] > r["oai_best_score"])
    print()
    print(f"  Queries where voyage-code-2 crosses threshold (OpenAI didn't): {voyage_unlocks}/{len(results)}")
    print(f"  Queries where voyage-code-2 scored higher (regardless of pass): {voyage_higher}/{len(results)}")

    # ── recommendation ───────────────────────────────────────────────────────
    print(f"\n{'=' * 90}")
    print("  RECOMMENDATION")
    print(f"{'=' * 90}")
    if voyage_unlocks >= 2:
        print(
            "  Switch to voyage-code-2 and re-index. It unlocks ≥2 queries that OpenAI\n"
            "  couldn't reach. Cost increase: $0.02 → $0.06/1M tokens (3× for retrieval).\n"
            "  With ~100 queries/day, extra cost is negligible."
        )
    elif voyage_unlocks == 1:
        print(
            "  Marginal gain: voyage-code-2 unlocks 1 new query. The cost of re-indexing\n"
            "  and the 3× retrieval cost increase may not be worth 1 additional passing query.\n"
            "  Consider query tuning or targeted annotations instead."
        )
    elif voyage_higher >= 3:
        print(
            "  voyage-code-2 consistently scores higher but doesn't cross the threshold.\n"
            "  The bottleneck is the data (no English in SETKEY/DBsample), not the model.\n"
            "  Recommendation: targeted *> annotations on those sections, keep OpenAI."
        )
    else:
        print(
            "  voyage-code-2 shows no meaningful improvement. The embedding model is not\n"
            "  the bottleneck. Options: (1) targeted annotations on failing sections,\n"
            "  (2) replace SETKEY golden query with a more answerable target."
        )


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("LegacyLens — Embedding Model Comparison")
    print("voyage-code-2 vs text-embedding-3-small")
    print("Local cosine similarity test — no Pinecone reads or writes\n")

    # Previously recorded results for gq-004, gq-005, gq-006 (run earlier).
    # Hardcoded here so we can run only gq-008 without re-spending API tokens.
    results: list[ExperimentResult] = [
        {
            "query_id": "gq-004",
            "query": "how to set up encryption keys from a password",
            "threshold": 0.70,
            "baseline": 0.464,
            "oai_best_score": 0.4641,
            "oai_best_chunk": "SETKEY",
            "oai_passes": False,
            "voyage_best_score": 0.7371,
            "voyage_best_chunk": "SETKEY",
            "voyage_passes": True,
            "delta": 0.2730,
        },
        {
            "query_id": "gq-005",
            "query": "database connection SQL COBOL program",
            "threshold": 0.70,
            "baseline": 0.693,
            "oai_best_score": 0.6782,
            "oai_best_chunk": "SQL-CONNECT",
            "oai_passes": False,
            "voyage_best_score": 0.8518,
            "voyage_best_chunk": "SQL-CONNECT",
            "voyage_passes": True,
            "delta": 0.1736,
        },
        {
            "query_id": "gq-006",
            "query": "how to insert a record into a database",
            "threshold": 0.70,
            "baseline": 0.491,
            "oai_best_score": 0.4562,
            "oai_best_chunk": "SQL-INSERT-BOOK",
            "oai_passes": False,
            "voyage_best_score": 0.7451,
            "voyage_best_chunk": "INSERT-BOOK",
            "voyage_passes": True,
            "delta": 0.2889,
        },
    ]
    # Run only gq-008 (the remaining experiment)
    for exp in EXPERIMENTS:
        if exp["query_id"] == "gq-008":
            result = run_one(exp)
            results.append(result)

    print_summary(results)
    print("\nDone. Append results to docs/embedding-score-optimization.md (Phase 3 section).")
