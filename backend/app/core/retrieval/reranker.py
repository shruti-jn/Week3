"""
Reranker — combines cosine similarity with keyword overlap to produce a
better-ordered list of COBOL code candidates before they reach the LLM.

Why two signals instead of one?

  Cosine similarity (from Pinecone) measures how "close in meaning" two
  pieces of text are based on their embedding vectors. It's good at finding
  semantically related content, but it can occasionally rank an adjacent-but-
  wrong chunk above the correct one.

  Keyword overlap counts how many of the user's actual search terms appear
  in the code snippet. COBOL variable and paragraph names are literal words
  (CALCULATE-INTEREST, COMPUTE-TAX). If the user's query contains those same
  words, it's a strong signal — even if the embedding didn't catch it.

  Combined: final_score = 0.7 * cosine + 0.3 * keyword_overlap

Pipeline position:

    user query → embedder → pinecone query (top_k=10) → [this module] → answer generator

The reranker is the last filter before the LLM sees the context, so it must:
  1. Remove candidates whose cosine score is below the 0.75 confidence threshold
  2. Re-sort survivors by combined score (cosine + keyword)
  3. Return at most top_k results (default 5)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.retrieval.pinecone_client import SearchResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# How much each signal contributes to the final combined score.
# COBOL keyword names are highly distinctive, so keyword overlap is a
# meaningful signal worth 30% of the total score.
KEYWORD_WEIGHT: float = 0.3
COSINE_WEIGHT: float = 1.0 - KEYWORD_WEIGHT  # 0.7

# Common English function words that carry no semantic meaning for code search.
# COBOL verbs (COMPUTE, PERFORM, MULTIPLY, etc.) are intentionally NOT included
# here — they are meaningful search terms when a user asks "how is X computed?".
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "from",
        "with",
        "by",
        "as",
        "or",
        "and",
        "but",
        "not",
        "no",
        "it",
        "its",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "this",
        "that",
        "what",
        "which",
        "how",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RankedResult:
    """
    A COBOL code chunk after reranking, ready to be sent to the answer generator.

    Think of this like a search result card that has been scored twice:
    once by the vector database (cosine_score) and once by keyword matching
    (keyword_score). The combined_score is what determines the final ordering.

    Attributes:
        chunk_id:      Unique identifier from Pinecone (e.g., "payroll.cob::CALC-TAX").
        cosine_score:  Original cosine similarity score from Pinecone (0.0-1.0).
        keyword_score: Fraction of query tokens found in the chunk content (0.0-1.0).
        combined_score: Weighted blend: 0.7 * cosine + 0.3 * keyword (0.0-1.0).
        metadata:      Original metadata dict (file_path, start_line, end_line,
                       content, etc.).
    """

    chunk_id: str
    cosine_score: float
    keyword_score: float
    combined_score: float
    metadata: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _tokenize(text: str) -> frozenset[str]:
    """
    Split text into a set of meaningful lowercase tokens, ignoring stopwords.

    COBOL identifiers use hyphens (CALC-INTEREST). Splitting on any non-
    alphanumeric character handles hyphens, dots, and spaces uniformly:
    "CALC-INTEREST." → {"calc", "interest"}.

    Args:
        text: Any string — a user query or a COBOL code snippet.

    Returns:
        Frozenset of lowercase, non-empty, non-stopword tokens.
        Returns an empty frozenset for empty or stopword-only input.
    """
    # Split on any run of non-alphanumeric characters (hyphens, spaces, dots, etc.)
    raw_tokens = re.split(r"[^a-zA-Z0-9]+", text.lower())
    return frozenset(t for t in raw_tokens if t and t not in _STOPWORDS)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def compute_keyword_score(query: str, content: str) -> float:
    """
    Measure how many of the query's meaningful words appear in the content.

    This is like counting how many of your grocery list items are on the shelf.
    If you're looking for 3 things and 2 of them are there, your score is 2/3.

    Score formula:
        score = |query_tokens ∩ content_tokens| / |query_tokens|

    Range: [0.0, 1.0]
      - 0.0 means none of the query terms appear in the content
      - 1.0 means all query terms appear in the content

    Args:
        query:   The user's natural-language question
                 (e.g., "how is interest computed?").
        content: The COBOL code snippet text from chunk metadata.

    Returns:
        Keyword overlap score in [0.0, 1.0].
        Returns 0.0 if the query has no meaningful tokens after stopword removal.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        # No meaningful query terms → no basis for keyword scoring
        logger.debug("compute_keyword_score: empty query tokens → returning 0.0")
        return 0.0

    content_tokens = _tokenize(content)
    overlap_count = len(query_tokens & content_tokens)
    score = overlap_count / len(query_tokens)

    logger.debug(
        "keyword_score=%.3f (%d/%d tokens matched)",
        score,
        overlap_count,
        len(query_tokens),
    )
    return score


def rerank(
    query: str,
    candidates: list[SearchResult],
    top_k: int = 5,
    min_score: float = 0.75,
    keyword_weight: float = KEYWORD_WEIGHT,
) -> list[RankedResult]:
    """
    Rerank Pinecone search results using combined cosine + keyword signals.

    This is the "second opinion" step in the retrieval pipeline. Pinecone's
    cosine similarity is the first judge (measures semantic closeness). Keyword
    overlap is the second judge (checks if the user's actual words are present).

    Steps:
      1. Filter out any candidate whose cosine score < min_score threshold.
         Below 0.75 means "not confident enough to answer" (per PRD).
      2. For each surviving candidate, compute keyword_score using the chunk's
         'content' metadata field. Defaults to 0.0 if 'content' is missing.
      3. Compute combined_score =
         (1 - keyword_weight) * cosine + keyword_weight * keyword.
      4. Sort by combined_score descending, return top_k results.

    Args:
        query:          The user's natural-language question.
        candidates:     List of SearchResult objects from PineconeWrapper.query().
                        Typically up to top_k=10 candidates.
        top_k:          Maximum number of results to return (default: 5).
        min_score:      Minimum cosine similarity threshold (default: 0.75).
                        Candidates below this score are excluded before reranking.
        keyword_weight: Weight given to keyword overlap in the combined score
                        (default: 0.3). The cosine weight is 1 - keyword_weight.

    Returns:
        List of RankedResult objects, sorted by combined_score descending.
        At most top_k items. Empty list if no candidates pass the threshold.

    Example:
        results = await pinecone.query(embedding, top_k=10, min_score=0.0)
        ranked = rerank("how is interest calculated", results, top_k=5)
        for r in ranked:
            print(f"{r.chunk_id}: cosine={r.cosine_score:.2f} kw={r.keyword_score:.2f}")
        # loan-calc.cob::CALCULATE-INTEREST: cosine=0.92 keyword=0.80
        # payroll.cob::COMPUTE-TAX: cosine=0.81 keyword=0.20
    """
    if not candidates:
        logger.debug("rerank: empty candidates list — returning []")
        return []

    cosine_weight = 1.0 - keyword_weight
    ranked: list[RankedResult] = []

    for result in candidates:
        # Step 1: Apply cosine similarity threshold.
        # The PRD specifies: if top similarity score < 0.75 → return fallback.
        # We enforce this per-candidate so the LLM never sees weak matches.
        if result.score < min_score:
            logger.debug(
                "Reranker filtered '%s' (cosine=%.3f < threshold=%.2f)",
                result.chunk_id,
                result.score,
                min_score,
            )
            continue

        # Step 2: Compute keyword overlap for this candidate.
        # Fall back to empty string if 'content' is absent from metadata.
        content = str(result.metadata.get("content", ""))
        kw_score = compute_keyword_score(query, content)

        # Step 3: Blend the two scores into a single combined score.
        combined = cosine_weight * result.score + keyword_weight * kw_score

        ranked.append(
            RankedResult(
                chunk_id=result.chunk_id,
                cosine_score=result.score,
                keyword_score=kw_score,
                combined_score=combined,
                metadata=result.metadata,
            )
        )

    # Step 4: Sort survivors by combined score (best first), then take top_k.
    ranked.sort(key=lambda r: r.combined_score, reverse=True)
    result_list = ranked[:top_k]

    logger.info(
        "rerank: %d/%d candidates above threshold=%.2f → returning top %d",
        len(ranked),
        len(candidates),
        min_score,
        len(result_list),
    )
    return result_list
