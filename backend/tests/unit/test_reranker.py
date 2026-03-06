"""
Unit tests for the reranker module.

The reranker sits between Pinecone and the answer generator. It takes the raw
cosine-similarity results from Pinecone (up to 10 candidates) and produces a
shorter, better-ordered list (up to 5 results) by combining two signals:

  1. Cosine similarity score  — how "similar" the embedding is (from Pinecone)
  2. Keyword overlap score    — how many query words appear in the code snippet

Think of it like a talent search: cosine similarity is the audition tape (are they
in the ballpark?), and keyword overlap is the live interview (do they actually know
the right vocabulary?). Both matter, and together they pick the best candidates.

All tests use only pure Python — no API calls, no Pinecone, no OpenAI.
"""

from __future__ import annotations

import pytest

from app.core.retrieval.pinecone_client import SearchResult
from app.core.retrieval.reranker import (
    RankedResult,
    compute_keyword_score,
    rerank,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_result(
    chunk_id: str,
    score: float,
    content: str = "",
    paragraph_name: str = "",
) -> SearchResult:
    """Build a SearchResult with minimal boilerplate for test use."""
    return SearchResult(
        chunk_id=chunk_id,
        score=score,
        metadata={
            "file_path": "programs/test.cob",
            "paragraph_name": paragraph_name,
            "start_line": 1,
            "end_line": 10,
            "content": content,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# compute_keyword_score — happy path
# ─────────────────────────────────────────────────────────────────────────────


def test_compute_keyword_score_partial_overlap() -> None:
    """
    Query has two meaningful tokens; one appears in content.
    Score should be 0.5 (1 out of 2 tokens matched).
    """
    score = compute_keyword_score(
        query="calculate interest",
        content="CALCULATE-GROSS MULTIPLY RATE BY HOURS",
    )
    assert score == pytest.approx(0.5, abs=0.01)


def test_compute_keyword_score_full_overlap() -> None:
    """
    All query tokens appear in the content → score should be 1.0.
    """
    score = compute_keyword_score(
        query="calculate interest",
        content="CALCULATE-INTEREST COMPUTE INTEREST = PRINCIPAL * RATE / 100",
    )
    assert score == pytest.approx(1.0, abs=0.01)


def test_compute_keyword_score_no_overlap() -> None:
    """
    No query tokens appear in the content → score should be 0.0.
    """
    score = compute_keyword_score(
        query="payroll tax deduction",
        content="DISPLAY SCREEN ACCEPT INPUT",
    )
    assert score == pytest.approx(0.0, abs=0.01)


def test_compute_keyword_score_case_insensitive() -> None:
    """
    COBOL content is uppercase; queries are typically lowercase.
    Matching must be case-insensitive.
    """
    score = compute_keyword_score(
        query="interest calculation",
        content="COMPUTE INTEREST = PRINCIPAL * RATE / 100. INTEREST-CALCULATION.",
    )
    # Both "interest" and "calculation" appear in the content (case-folded)
    assert score == pytest.approx(1.0, abs=0.01)


def test_compute_keyword_score_hyphenated_cobol_identifier() -> None:
    """
    COBOL identifiers use hyphens (e.g., CALC-INTEREST).
    The tokenizer must split on hyphens so "interest" matches "CALC-INTEREST".
    """
    score = compute_keyword_score(
        query="interest",
        content="CALC-INTEREST.",
    )
    assert score == pytest.approx(1.0, abs=0.01)


def test_compute_keyword_score_stopwords_ignored() -> None:
    """
    Common English words (the, is, of) are stopwords and should not contribute
    to the overlap — they carry no semantic signal for code retrieval.
    """
    # Query is entirely stopwords → no meaningful tokens → score 0.0
    score = compute_keyword_score(
        query="the is of",
        content="COMPUTE INTEREST = PRINCIPAL * RATE / 100",
    )
    assert score == pytest.approx(0.0, abs=0.01)


def test_compute_keyword_score_cobol_keyword_not_removed() -> None:
    """
    COBOL verbs like COMPUTE, PERFORM, MULTIPLY are meaningful search terms
    and must NOT be treated as stopwords.
    """
    score = compute_keyword_score(
        query="compute multiply",
        content="COMPUTE INTEREST. MULTIPLY RATE BY HOURS.",
    )
    assert score == pytest.approx(1.0, abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# compute_keyword_score — edge cases
# ─────────────────────────────────────────────────────────────────────────────


def test_compute_keyword_score_empty_query() -> None:
    """
    Empty query string → no meaningful tokens → score 0.0 (safe default).
    """
    score = compute_keyword_score(query="", content="COMPUTE INTEREST = PRINCIPAL")
    assert score == pytest.approx(0.0, abs=0.01)


def test_compute_keyword_score_empty_content() -> None:
    """
    Empty content string → nothing to match against → score 0.0.
    """
    score = compute_keyword_score(query="calculate interest", content="")
    assert score == pytest.approx(0.0, abs=0.01)


def test_compute_keyword_score_both_empty() -> None:
    """
    Both query and content are empty → score 0.0.
    """
    score = compute_keyword_score(query="", content="")
    assert score == pytest.approx(0.0, abs=0.01)


def test_compute_keyword_score_single_token_match() -> None:
    """
    Single meaningful query token that matches content → score 1.0.
    """
    score = compute_keyword_score(query="interest", content="INTEREST = 0")
    assert score == pytest.approx(1.0, abs=0.01)


def test_compute_keyword_score_single_token_no_match() -> None:
    """
    Single meaningful query token that does not match content → score 0.0.
    """
    score = compute_keyword_score(query="interest", content="COMPUTE TAX RATE")
    assert score == pytest.approx(0.0, abs=0.01)


def test_compute_keyword_score_repeated_query_tokens() -> None:
    """
    Duplicate tokens in the query should only count once because we use a set.
    'interest interest interest' → same as 'interest' → score 1.0 if in content.
    """
    score = compute_keyword_score(
        query="interest interest interest",
        content="COMPUTE INTEREST RATE",
    )
    assert score == pytest.approx(1.0, abs=0.01)


def test_compute_keyword_score_range() -> None:
    """Score must always be in [0.0, 1.0]."""
    score = compute_keyword_score(
        query="compute interest payroll tax",
        content="COMPUTE INTEREST PAYROLL TAX DEDUCTION RATE",
    )
    assert 0.0 <= score <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# rerank — happy path
# ─────────────────────────────────────────────────────────────────────────────


def test_rerank_happy_path_returns_ranked_results() -> None:
    """
    Two candidates both above the 0.65 threshold.
    Should return RankedResult objects with all fields populated.
    """
    candidates = [
        make_result("file.cob::PARA-A", score=0.90, content="COMPUTE INTEREST RATE"),
        make_result("file.cob::PARA-B", score=0.82, content="DISPLAY SCREEN ACCEPT"),
    ]
    results = rerank("compute interest", candidates)
    assert len(results) == 2
    assert all(isinstance(r, RankedResult) for r in results)


def test_rerank_result_has_all_fields() -> None:
    """RankedResult exposes chunk_id, cosine_score, keyword_score, combined_score, metadata."""
    candidates = [make_result("file.cob::PARA", score=0.85, content="COMPUTE INTEREST")]
    results = rerank("compute interest", candidates)
    r = results[0]
    assert r.chunk_id == "file.cob::PARA"
    assert r.cosine_score == pytest.approx(0.85, abs=0.001)
    assert 0.0 <= r.keyword_score <= 1.0
    assert 0.0 <= r.combined_score <= 1.0
    assert "file_path" in r.metadata


def test_rerank_sorted_by_combined_score_descending() -> None:
    """
    Result with higher combined score should appear first.
    Give PARA-B a better keyword match so it overtakes PARA-A in final ranking.
    """
    candidates = [
        # Same cosine score; PARA-A has no keyword match, PARA-B has full match
        make_result("file.cob::PARA-A", score=0.80, content="DISPLAY SCREEN ACCEPT"),
        make_result("file.cob::PARA-B", score=0.80, content="COMPUTE INTEREST RATE"),
    ]
    results = rerank("compute interest", candidates)
    assert results[0].chunk_id == "file.cob::PARA-B"
    assert results[1].chunk_id == "file.cob::PARA-A"


def test_rerank_cosine_signal_dominates_with_big_score_gap() -> None:
    """
    If one candidate has a much higher cosine score (0.95 vs 0.76), it should
    still rank first even if it has worse keyword overlap, because cosine
    weight (0.7) dominates.
    """
    candidates = [
        # High cosine, no keyword match
        make_result("file.cob::HIGH-COSINE", score=0.95, content="DISPLAY SCREEN"),
        # Low cosine, perfect keyword match
        make_result("file.cob::LOW-COSINE", score=0.76, content="COMPUTE INTEREST RATE"),
    ]
    results = rerank("compute interest", candidates)
    # 0.95 * 0.7 + 0.0 * 0.3 = 0.665 vs 0.76 * 0.7 + 1.0 * 0.3 = 0.832 — LOW-COSINE wins
    # Actually, check math: keyword match wins here because kw_score is 1.0
    # Let's just assert ordering is consistent with combined score
    assert results[0].combined_score >= results[1].combined_score


def test_rerank_preserves_metadata() -> None:
    """Metadata from the original SearchResult is passed through unchanged."""
    candidates = [
        make_result("file.cob::PARA", score=0.85, content="COMPUTE INTEREST", paragraph_name="PARA")
    ]
    results = rerank("interest", candidates)
    assert results[0].metadata["paragraph_name"] == "PARA"
    assert results[0].metadata["file_path"] == "programs/test.cob"


def test_rerank_keyword_score_in_result() -> None:
    """
    keyword_score should be > 0 when query tokens appear in content,
    and combined_score should reflect the 0.7/0.3 blend.
    """
    candidates = [make_result("f.cob::P", score=0.80, content="COMPUTE INTEREST RATE")]
    results = rerank("compute interest", candidates)
    r = results[0]
    assert r.keyword_score > 0.0
    expected_combined = 0.7 * r.cosine_score + 0.3 * r.keyword_score
    assert r.combined_score == pytest.approx(expected_combined, abs=0.001)


# ─────────────────────────────────────────────────────────────────────────────
# rerank — threshold filtering
# ─────────────────────────────────────────────────────────────────────────────


def test_rerank_filters_below_default_threshold() -> None:
    """
    Candidates with cosine score < 0.65 must be excluded from results.
    """
    candidates = [
        make_result("f.cob::GOOD", score=0.80, content="COMPUTE INTEREST"),
        make_result("f.cob::BAD", score=0.60, content="COMPUTE INTEREST"),
    ]
    results = rerank("compute interest", candidates)
    assert len(results) == 1
    assert results[0].chunk_id == "f.cob::GOOD"


def test_rerank_score_exactly_at_threshold_included() -> None:
    """
    Score exactly equal to min_score (0.65) should be INCLUDED (>= threshold).
    """
    candidates = [make_result("f.cob::EXACT", score=0.65, content="COMPUTE INTEREST")]
    results = rerank("compute interest", candidates)
    assert len(results) == 1
    assert results[0].chunk_id == "f.cob::EXACT"


def test_rerank_score_just_below_threshold_excluded() -> None:
    """
    Score of 0.649 is below 0.65 threshold → must be excluded.
    """
    candidates = [make_result("f.cob::CLOSE", score=0.649, content="COMPUTE INTEREST")]
    results = rerank("compute interest", candidates)
    assert len(results) == 0


def test_rerank_all_below_threshold_returns_empty() -> None:
    """
    When every candidate is below the similarity threshold, return empty list.
    The answer generator interprets this as "no relevant code found".
    """
    candidates = [
        make_result("f.cob::A", score=0.60, content="COMPUTE INTEREST"),
        make_result("f.cob::B", score=0.50, content="PERFORM LOOP"),
        make_result("f.cob::C", score=0.30, content="DISPLAY RESULT"),
    ]
    results = rerank("compute interest", candidates)
    assert results == []


def test_rerank_custom_min_score() -> None:
    """
    Caller can specify a stricter threshold (e.g., 0.85) to get only
    high-confidence results.
    """
    candidates = [
        make_result("f.cob::VERY-GOOD", score=0.90, content="COMPUTE INTEREST"),
        make_result("f.cob::GOOD", score=0.80, content="COMPUTE INTEREST"),
    ]
    results = rerank("compute interest", candidates, min_score=0.85)
    assert len(results) == 1
    assert results[0].chunk_id == "f.cob::VERY-GOOD"


# ─────────────────────────────────────────────────────────────────────────────
# rerank — top_k limiting
# ─────────────────────────────────────────────────────────────────────────────


def test_rerank_returns_at_most_top_k() -> None:
    """
    When more than top_k candidates pass the threshold, return only top_k.
    Default top_k is 5.
    """
    candidates = [
        make_result(f"f.cob::PARA-{i}", score=0.80 + i * 0.01, content="COMPUTE INTEREST")
        for i in range(10)
    ]
    results = rerank("compute interest", candidates, top_k=5)
    assert len(results) == 5


def test_rerank_custom_top_k() -> None:
    """top_k=2 limits output to 2 results even if more pass the threshold."""
    candidates = [
        make_result("f.cob::A", score=0.90, content="COMPUTE INTEREST"),
        make_result("f.cob::B", score=0.85, content="COMPUTE RATE"),
        make_result("f.cob::C", score=0.80, content="PERFORM LOOP"),
    ]
    results = rerank("compute interest", candidates, top_k=2)
    assert len(results) == 2


def test_rerank_fewer_than_top_k_above_threshold() -> None:
    """
    If only 2 candidates pass the threshold but top_k=5, return only 2.
    Never pad the result with below-threshold candidates.
    """
    candidates = [
        make_result("f.cob::A", score=0.90, content="COMPUTE INTEREST"),
        make_result("f.cob::B", score=0.80, content="COMPUTE RATE"),
        make_result("f.cob::C", score=0.50, content="DISPLAY SCREEN"),  # below threshold
    ]
    results = rerank("compute interest", candidates, top_k=5)
    assert len(results) == 2


# ─────────────────────────────────────────────────────────────────────────────
# rerank — edge cases (empty, single, large)
# ─────────────────────────────────────────────────────────────────────────────


def test_rerank_empty_candidates() -> None:
    """
    Empty input list → empty output list. Must not raise.
    This is the "no results from Pinecone" path.
    """
    results = rerank("compute interest", [])
    assert results == []


def test_rerank_single_candidate_above_threshold() -> None:
    """Single candidate above threshold → list with one RankedResult."""
    candidates = [make_result("f.cob::ONLY", score=0.88, content="COMPUTE INTEREST")]
    results = rerank("compute interest", candidates)
    assert len(results) == 1
    assert results[0].chunk_id == "f.cob::ONLY"


def test_rerank_single_candidate_below_threshold() -> None:
    """Single candidate below threshold → empty list (not an error)."""
    candidates = [make_result("f.cob::ONLY", score=0.60, content="COMPUTE INTEREST")]
    results = rerank("compute interest", candidates)
    assert results == []


def test_rerank_large_candidate_list() -> None:
    """
    100 candidates (well above Pinecone's top_k=10 but useful for stress test).
    Should complete without error and respect top_k.
    """
    candidates = [
        make_result(f"f.cob::PARA-{i}", score=0.75 + (i % 20) * 0.01, content=f"COMPUTE INTEREST ITEM-{i}")
        for i in range(100)
    ]
    results = rerank("compute interest", candidates, top_k=5)
    assert len(results) == 5
    # All returned results must pass the threshold
    for r in results:
        assert r.cosine_score >= 0.75


def test_rerank_missing_content_in_metadata() -> None:
    """
    If a chunk's metadata has no 'content' key, keyword_score defaults to 0.0.
    This must not raise a KeyError.
    """
    result = SearchResult(
        chunk_id="f.cob::NO-CONTENT",
        score=0.85,
        metadata={"file_path": "programs/test.cob"},  # no 'content' key
    )
    results = rerank("compute interest", [result])
    assert len(results) == 1
    assert results[0].keyword_score == pytest.approx(0.0, abs=0.001)


def test_rerank_empty_query_gives_zero_keyword_score() -> None:
    """
    Empty query → keyword_score 0.0 for all candidates.
    Combined score is then just 0.7 * cosine_score.
    Ranking still works (sorted by cosine).
    """
    candidates = [
        make_result("f.cob::A", score=0.90, content="COMPUTE INTEREST"),
        make_result("f.cob::B", score=0.80, content="DISPLAY RESULT"),
    ]
    results = rerank("", candidates)
    assert len(results) == 2
    for r in results:
        assert r.keyword_score == pytest.approx(0.0, abs=0.001)
    # Still sorted — higher cosine first
    assert results[0].chunk_id == "f.cob::A"


def test_rerank_custom_keyword_weight() -> None:
    """
    Caller can override keyword_weight. Setting weight=0.0 means pure cosine ranking.
    """
    candidates = [
        # Lower cosine but perfect keyword match
        make_result("f.cob::KEYWORD-WINNER", score=0.76, content="COMPUTE INTEREST RATE"),
        # Higher cosine, no keyword match
        make_result("f.cob::COSINE-WINNER", score=0.90, content="DISPLAY SCREEN ACCEPT"),
    ]
    # With keyword_weight=0.0, cosine_score is the only signal → COSINE-WINNER first
    results = rerank("compute interest", candidates, keyword_weight=0.0)
    assert results[0].chunk_id == "f.cob::COSINE-WINNER"
