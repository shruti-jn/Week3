"""
Pydantic models for incoming API request bodies.

These models act as the "entry gate" for all data coming into the API.
Think of them like a form with specific fields — Pydantic automatically
checks that each field has the right type and value before the code runs.

If a caller sends the wrong data (e.g., an empty query or a top_k of 999),
the API returns a clear 422 Unprocessable Entity error — not a cryptic 500.

All models live here in app/models/ so other modules can import the types
without importing business logic.
"""

from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    """
    Request body for POST /api/v1/query — the main search endpoint.

    The caller asks a plain-English question about a COBOL codebase
    and optionally controls how many code snippets to retrieve.

    Example:
        {"query": "How does payroll calculation work?", "top_k": 5}
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Plain-English question about the COBOL codebase.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of code chunks to retrieve from Pinecone (1-20).",
    )

    @field_validator("query")
    @classmethod
    def query_not_whitespace(cls, value: str) -> str:
        """
        Reject queries that contain only spaces or tabs.

        A whitespace-only query would hit the vector DB and return noise.
        Better to fail fast with a clear validation error.
        """
        if not value.strip():
            msg = "Query must contain at least one non-whitespace character."
            raise ValueError(msg)
        return value


class ExplainRequest(BaseModel):
    """
    Request body for POST /api/v1/explain — Feature 1: Code Explanation.

    The caller specifies which COBOL paragraph to explain in plain English.
    The paragraph is identified by its containing file and its label name.

    Example:
        {"file_path": "samples/payroll.cob", "paragraph_name": "CALC-GROSS-PAY"}
    """

    file_path: str = Field(
        ...,
        min_length=1,
        description="Relative path to the COBOL source file.",
    )
    paragraph_name: str = Field(
        ...,
        min_length=1,
        description="COBOL paragraph label (e.g., 'CALC-GROSS-PAY').",
    )


class DependenciesRequest(BaseModel):
    """
    Request body for POST /api/v1/dependencies — Feature 2: Dependency Mapping.

    The caller asks which paragraphs call a given paragraph (called_by)
    and which paragraphs that paragraph itself calls (calls).

    Example:
        {"file_path": "samples/payroll.cob", "paragraph_name": "CALC-NET-PAY"}
    """

    file_path: str = Field(
        ...,
        min_length=1,
        description="Relative path to the COBOL source file.",
    )
    paragraph_name: str = Field(
        ...,
        min_length=1,
        description="COBOL paragraph label to map dependencies for.",
    )


class BusinessLogicRequest(BaseModel):
    """
    Request body for POST /api/v1/business-logic — Feature 3: Business Logic Extraction.

    The caller asks the system to identify and explain the business rules
    encoded in a COBOL source file (e.g., overtime thresholds, tax brackets).

    Example:
        {"file_path": "samples/loans.cob"}
    """

    file_path: str = Field(
        ...,
        min_length=1,
        description="Relative path to the COBOL source file to analyze.",
    )


class ImpactRequest(BaseModel):
    """
    Request body for POST /api/v1/impact — Feature 4: Impact Analysis.

    The caller asks what other code would be affected if a given paragraph
    were modified or removed.

    Example:
        {"file_path": "samples/payroll.cob", "paragraph_name": "CALC-OVERTIME"}
    """

    file_path: str = Field(
        ...,
        min_length=1,
        description="Relative path to the COBOL source file.",
    )
    paragraph_name: str = Field(
        ...,
        min_length=1,
        description="COBOL paragraph label to run impact analysis on.",
    )
