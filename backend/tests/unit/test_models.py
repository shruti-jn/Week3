"""
Unit tests for Pydantic request and response models.

These tests verify that:
- Models accept valid input and produce correct output
- Models reject invalid input with clear validation errors
- Default values behave as expected
- Serialization round-trips (dict → model → dict) work correctly

No external dependencies (OpenAI, Pinecone) needed — these are pure data-shape tests.
"""

import pytest
from pydantic import ValidationError

from app.models.requests import (
    BusinessLogicRequest,
    DependenciesRequest,
    ExplainRequest,
    ImpactRequest,
    QueryRequest,
)
from app.models.responses import (
    BusinessLogicResponse,
    CodeSnippet,
    DependenciesResponse,
    ExplainResponse,
    HealthResponse,
    ImpactResponse,
    QueryResponse,
    StubResponse,
)


# ─────────────────────────────────────────────────────────────────────────────
# QueryRequest
# ─────────────────────────────────────────────────────────────────────────────


class TestQueryRequest:
    """Tests for the main search request model."""

    def test_valid_query(self) -> None:
        """Happy path: a standard query with all defaults."""
        req = QueryRequest(query="How does the payroll calculation work?")
        assert req.query == "How does the payroll calculation work?"
        assert req.top_k == 5  # default

    def test_top_k_custom(self) -> None:
        """top_k can be overridden by the caller."""
        req = QueryRequest(query="Find loan processing logic", top_k=10)
        assert req.top_k == 10

    def test_query_empty_string_rejected(self) -> None:
        """Empty query string must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(query="")
        assert "query" in str(exc_info.value)

    def test_query_too_long_rejected(self) -> None:
        """Query longer than 500 characters must be rejected."""
        with pytest.raises(ValidationError):
            QueryRequest(query="x" * 501)

    def test_query_max_length_accepted(self) -> None:
        """Exactly 500 characters must be accepted."""
        req = QueryRequest(query="x" * 500)
        assert len(req.query) == 500

    def test_top_k_below_min_rejected(self) -> None:
        """top_k of 0 must be rejected (minimum is 1)."""
        with pytest.raises(ValidationError):
            QueryRequest(query="test", top_k=0)

    def test_top_k_above_max_rejected(self) -> None:
        """top_k above 20 must be rejected."""
        with pytest.raises(ValidationError):
            QueryRequest(query="test", top_k=21)

    def test_top_k_boundaries(self) -> None:
        """top_k of 1 and 20 (boundary values) must be accepted."""
        req_min = QueryRequest(query="test", top_k=1)
        req_max = QueryRequest(query="test", top_k=20)
        assert req_min.top_k == 1
        assert req_max.top_k == 20

    def test_top_k_wrong_type_rejected(self) -> None:
        """top_k must be an integer — float without decimal truncation rejected."""
        with pytest.raises(ValidationError):
            QueryRequest(query="test", top_k="not-an-int")  # type: ignore[arg-type]

    def test_query_whitespace_only_rejected(self) -> None:
        """A query that is only whitespace should be rejected."""
        with pytest.raises(ValidationError):
            QueryRequest(query="   ")

    def test_serialization_round_trip(self) -> None:
        """Model can be serialized to dict and back without data loss."""
        req = QueryRequest(query="Find COBOL paragraphs", top_k=7)
        as_dict = req.model_dump()
        restored = QueryRequest(**as_dict)
        assert restored == req


# ─────────────────────────────────────────────────────────────────────────────
# Feature Requests (Explain, Dependencies, BusinessLogic, Impact)
# ─────────────────────────────────────────────────────────────────────────────


class TestExplainRequest:
    """Tests for the code explanation request model."""

    def test_valid_request(self) -> None:
        req = ExplainRequest(
            file_path="samples/payroll.cob",
            paragraph_name="CALC-GROSS-PAY",
        )
        assert req.file_path == "samples/payroll.cob"
        assert req.paragraph_name == "CALC-GROSS-PAY"

    def test_missing_file_path_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExplainRequest(paragraph_name="CALC-GROSS-PAY")  # type: ignore[call-arg]

    def test_missing_paragraph_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExplainRequest(file_path="samples/payroll.cob")  # type: ignore[call-arg]

    def test_empty_file_path_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExplainRequest(file_path="", paragraph_name="PARA")

    def test_empty_paragraph_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExplainRequest(file_path="samples/payroll.cob", paragraph_name="")


class TestDependenciesRequest:
    """Tests for the dependency mapping request model."""

    def test_valid_request(self) -> None:
        req = DependenciesRequest(
            file_path="samples/payroll.cob",
            paragraph_name="CALC-NET-PAY",
        )
        assert req.paragraph_name == "CALC-NET-PAY"

    def test_missing_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DependenciesRequest(file_path="only-one-field.cob")  # type: ignore[call-arg]


class TestBusinessLogicRequest:
    """Tests for the business logic extraction request model."""

    def test_valid_request(self) -> None:
        req = BusinessLogicRequest(file_path="samples/loans.cob")
        assert req.file_path == "samples/loans.cob"

    def test_missing_file_path_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BusinessLogicRequest()  # type: ignore[call-arg]

    def test_empty_file_path_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BusinessLogicRequest(file_path="")


class TestImpactRequest:
    """Tests for the impact analysis request model."""

    def test_valid_request(self) -> None:
        req = ImpactRequest(
            file_path="samples/payroll.cob",
            paragraph_name="CALC-OVERTIME",
        )
        assert req.file_path == "samples/payroll.cob"
        assert req.paragraph_name == "CALC-OVERTIME"

    def test_missing_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ImpactRequest()  # type: ignore[call-arg]


# ─────────────────────────────────────────────────────────────────────────────
# CodeSnippet (shared sub-model)
# ─────────────────────────────────────────────────────────────────────────────


class TestCodeSnippet:
    """Tests for the code snippet sub-model returned inside query results."""

    def test_valid_snippet(self) -> None:
        """Happy path: a properly formed code snippet."""
        snippet = CodeSnippet(
            file_path="samples/payroll.cob",
            start_line=42,
            end_line=67,
            content="       CALC-GROSS-PAY.\n           MULTIPLY HOURS BY RATE GIVING GROSS-PAY.",
            score=0.92,
        )
        assert snippet.start_line == 42
        assert snippet.end_line == 67
        assert snippet.score == 0.92

    def test_start_line_zero_rejected(self) -> None:
        """Line numbers must be 1-indexed — 0 is invalid."""
        with pytest.raises(ValidationError):
            CodeSnippet(
                file_path="f.cob",
                start_line=0,
                end_line=10,
                content="x",
                score=0.9,
            )

    def test_end_before_start_rejected(self) -> None:
        """end_line must be >= start_line."""
        with pytest.raises(ValidationError):
            CodeSnippet(
                file_path="f.cob",
                start_line=50,
                end_line=10,
                content="x",
                score=0.9,
            )

    def test_score_above_one_rejected(self) -> None:
        """Cosine similarity score must be between 0 and 1."""
        with pytest.raises(ValidationError):
            CodeSnippet(
                file_path="f.cob",
                start_line=1,
                end_line=5,
                content="x",
                score=1.1,
            )

    def test_score_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CodeSnippet(
                file_path="f.cob",
                start_line=1,
                end_line=5,
                content="x",
                score=-0.1,
            )

    def test_empty_content_rejected(self) -> None:
        """A snippet with no code content is useless and should be rejected."""
        with pytest.raises(ValidationError):
            CodeSnippet(
                file_path="f.cob",
                start_line=1,
                end_line=5,
                content="",
                score=0.8,
            )

    def test_single_line_snippet(self) -> None:
        """start_line == end_line is valid for single-line snippets."""
        snippet = CodeSnippet(
            file_path="f.cob",
            start_line=10,
            end_line=10,
            content="       STOP RUN.",
            score=0.75,
        )
        assert snippet.start_line == snippet.end_line


# ─────────────────────────────────────────────────────────────────────────────
# Response Models
# ─────────────────────────────────────────────────────────────────────────────


class TestQueryResponse:
    """Tests for the main query response model."""

    def test_valid_response(self) -> None:
        """Happy path: a response with answer, snippets, and timing."""
        snippet = CodeSnippet(
            file_path="samples/payroll.cob",
            start_line=42,
            end_line=67,
            content="       CALC-GROSS-PAY.",
            score=0.92,
        )
        resp = QueryResponse(
            answer="The payroll calculation multiplies hours by rate.",
            snippets=[snippet],
            query_time_ms=1234.5,
        )
        assert len(resp.snippets) == 1
        assert resp.query_time_ms == 1234.5

    def test_empty_snippets_allowed(self) -> None:
        """A response with no snippets is valid (no matches found case)."""
        resp = QueryResponse(
            answer="No relevant COBOL code found.",
            snippets=[],
            query_time_ms=50.0,
        )
        assert resp.snippets == []

    def test_negative_query_time_rejected(self) -> None:
        """Query time in milliseconds cannot be negative."""
        with pytest.raises(ValidationError):
            QueryResponse(
                answer="test",
                snippets=[],
                query_time_ms=-1.0,
            )

    def test_empty_answer_rejected(self) -> None:
        """Answer cannot be empty — the LLM must produce something."""
        with pytest.raises(ValidationError):
            QueryResponse(
                answer="",
                snippets=[],
                query_time_ms=100.0,
            )

    def test_serialization_round_trip(self) -> None:
        """Response can be serialized to dict and back without data loss."""
        snippet = CodeSnippet(
            file_path="f.cob",
            start_line=1,
            end_line=5,
            content="code",
            score=0.85,
        )
        resp = QueryResponse(answer="result", snippets=[snippet], query_time_ms=200.0)
        as_dict = resp.model_dump()
        restored = QueryResponse(**as_dict)
        assert restored == resp


class TestHealthResponse:
    """Tests for the health check response model."""

    def test_valid_health_response(self) -> None:
        resp = HealthResponse(status="ok", service="legacylens-api")
        assert resp.status == "ok"

    def test_missing_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthResponse(service="legacylens-api")  # type: ignore[call-arg]


class TestStubResponse:
    """Tests for the temporary stub response model used by unimplemented endpoints."""

    def test_valid_stub_response(self) -> None:
        resp = StubResponse(
            status="stub",
            message="Not yet implemented",
        )
        assert resp.status == "stub"

    def test_default_message(self) -> None:
        """StubResponse should work with just a status field."""
        resp = StubResponse(status="stub", message="placeholder")
        assert resp.message == "placeholder"


class TestFeatureResponses:
    """Tests for Phase 2 feature response models (stub-level validation)."""

    def test_explain_response(self) -> None:
        resp = ExplainResponse(
            status="stub",
            message="Not yet implemented",
            paragraph_name="CALC-GROSS-PAY",
            explanation=None,
        )
        assert resp.paragraph_name == "CALC-GROSS-PAY"
        assert resp.explanation is None

    def test_dependencies_response(self) -> None:
        resp = DependenciesResponse(
            status="stub",
            message="Not yet implemented",
            paragraph_name="CALC-NET-PAY",
            calls=[],
            called_by=[],
        )
        assert resp.calls == []

    def test_business_logic_response(self) -> None:
        resp = BusinessLogicResponse(
            status="stub",
            message="Not yet implemented",
            file_path="samples/loans.cob",
            rules=[],
        )
        assert resp.rules == []

    def test_impact_response(self) -> None:
        resp = ImpactResponse(
            status="stub",
            message="Not yet implemented",
            paragraph_name="CALC-OVERTIME",
            affected_paragraphs=[],
        )
        assert resp.affected_paragraphs == []
