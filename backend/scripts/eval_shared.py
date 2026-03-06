"""
Shared types and logic for LegacyLens golden query evaluation.

Both evaluate.py (direct Pinecone) and evaluate_deployed.py (HTTP API) import
from here so there is a single source of truth for the data model and matching
logic. Neither script should define GoldenQuery, FailureMode, or the classifier
on its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class FailureMode(str, Enum):
    """
    Why a golden query did or did not pass.

    Distinguishing NO_RESULTS from NOT_RETRIEVED is critical for debugging:
    - NO_RESULTS means the API returned zero snippets. This usually means the
      backend's similarity threshold filtered everything out — check the
      SIMILARITY_THRESHOLD env var on Railway before assuming the file is missing.
      Fast response times (<300ms) are a reliable indicator of threshold filtering
      vs. a genuine missing file (which would still hit Pinecone and take >1s).
    - NOT_RETRIEVED means results came back (top_score > 0) but the expected
      chunk wasn't among them — fix by tuning chunking or reranking.
    """

    NO_RESULTS = "no_results"
    """top_score == 0.0 — API returned no snippets. Likely threshold filtering;
    confirm by checking SIMILARITY_THRESHOLD in Railway env before re-ingesting."""

    NOT_RETRIEVED = "not_retrieved"
    """top_score > 0.0 — results returned but expected chunk not in top-k."""

    BELOW_THRESHOLD = "below_threshold"
    """Expected chunk found in top-k but its score is below the golden min_score."""

    PASSED = "passed"
    """Expected chunk found in top-k and its score meets or exceeds min_score."""


@dataclass
class GoldenQuery:
    """
    One entry from tests/fixtures/golden_queries.json.

    Think of this like a test case for the retrieval system: given this query,
    we expect a specific file (and optionally a specific paragraph) to appear
    in the top-5 results with a score above min_score.
    """

    id: str
    query: str
    expected_paragraph: str | None
    """COBOL paragraph name. None means any chunk from the expected file is acceptable."""
    expected_file_pattern: str
    """Case-insensitive substring matched against the chunk's file_path metadata."""
    min_score: float
    """Minimum retrieval score the matched chunk must achieve to count as a pass."""
    category: str


def load_golden_queries(path: Path) -> list[GoldenQuery]:
    """
    Load golden query entries from a JSON fixture file.

    The fixture array starts with a metadata comment object (no "id" key) that
    is silently skipped. Only objects with an "id" field are loaded as queries.

    Args:
        path: Path to the golden_queries.json fixture file.

    Returns:
        List of GoldenQuery instances in fixture order.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    queries: list[GoldenQuery] = []
    for item in raw:
        if "id" not in item:
            continue
        queries.append(
            GoldenQuery(
                id=str(item["id"]),
                query=str(item["query"]),
                expected_paragraph=(
                    str(item["expected_paragraph"])
                    if item["expected_paragraph"] is not None
                    else None
                ),
                expected_file_pattern=str(item["expected_file_pattern"]),
                min_score=float(item["min_score"]),
                category=str(item["category"]),
            )
        )
    return queries


def snippet_matches(file_path: str, paragraph_name: str, golden: GoldenQuery) -> bool:
    """
    Return True when a retrieved chunk satisfies the golden query's expectation.

    Matching rules:
    1. file_path must contain expected_file_pattern (case-insensitive substring).
    2. If expected_paragraph is set, paragraph_name must match it exactly
       (case-insensitive). If expected_paragraph is None, the file match alone
       is sufficient.

    Args:
        file_path: The chunk's file_path metadata value from Pinecone or the API.
        paragraph_name: The chunk's paragraph_name metadata value.
        golden: The golden query entry to check against.

    Returns:
        True if the chunk satisfies both the file and paragraph criteria.
    """
    if golden.expected_file_pattern.lower() not in file_path.lower():
        return False
    if golden.expected_paragraph is None:
        return True
    return paragraph_name.upper() == golden.expected_paragraph.upper()


def classify_result(
    golden: GoldenQuery,
    snippets: list[tuple[str, str, float]],
    top_score: float,
) -> tuple[bool, float | None, FailureMode]:
    """
    Determine pass/fail and the specific failure mode for one golden query.

    This is the single evaluation function used by both scripts. It separates
    the four distinct outcomes so callers can tell apart indexing gaps from
    retrieval-quality gaps.

    Args:
        golden: The golden query entry being evaluated.
        snippets: List of (file_path, paragraph_name, score) tuples from the
                  retrieval system, ordered by score descending. May be empty.
        top_score: The score of the highest-ranked result (0.0 if no results).

    Returns:
        (passed, matched_score, failure_mode) where:
        - passed: True only when the right chunk is found at or above min_score.
        - matched_score: Score of the matching chunk, or None if not found.
        - failure_mode: One of the FailureMode enum values.
    """
    matched_score: float | None = None
    matched: tuple[str, str, float] | None = None

    for file_path, paragraph_name, score in snippets:
        if snippet_matches(file_path, paragraph_name, golden):
            matched = (file_path, paragraph_name, score)
            matched_score = score
            break

    if matched is None:
        if top_score == 0.0:
            return False, None, FailureMode.NO_RESULTS
        return False, None, FailureMode.NOT_RETRIEVED

    if matched_score is not None and matched_score < golden.min_score:
        return False, matched_score, FailureMode.BELOW_THRESHOLD

    return True, matched_score, FailureMode.PASSED
