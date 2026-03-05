"""
COBOL code understanding features — LLM-powered analysis of COBOL source.

This module implements the four Phase 2 code intelligence features:
  1. explain_paragraph   — plain-English explanation of a COBOL paragraph
  2. map_dependencies    — PERFORM call graph (what this calls and what calls it)
  3. extract_business_logic — business rules extracted from an entire file
  4. analyze_impact      — which paragraphs break if a given paragraph changes

All four features work the same way:
  1. Fetch the full COBOL source file from GitHub raw URL (cached in memory)
  2. Build a task-specific prompt with the file content and paragraph name
  3. Call GPT-4o-mini in JSON mode (no streaming — we need the full reply at once)
  4. Parse the JSON and return the correct Pydantic response model

File content is fetched from GitHub rather than local disk so these features
work identically on localhost and on Railway (no disk dependency).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import httpx
from fastapi import HTTPException

from app.models.responses import (
    BusinessLogicResponse,
    DependenciesResponse,
    ExplainResponse,
    ImpactResponse,
)

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Base URL for fetching raw COBOL source files from GitHub.
# All gnucobol-contrib files are public — no auth required.
GITHUB_RAW_BASE: str = (
    "https://raw.githubusercontent.com/OCamlPro/gnucobol-contrib/master"
)

# The string that identifies the gnucobol-contrib directory in a stored file path.
# Stored paths look like: /Users/shruti/Week3/data/gnucobol-contrib/payroll/PAYROLL.cob
# We strip everything up to and including this marker to get the relative path.
_MARKER: str = "gnucobol-contrib/"

# GPT-4o-mini model used for all feature analysis.
# Chosen for its cost efficiency — 15x cheaper than GPT-4o with equivalent quality
# for structured COBOL code analysis tasks.
_FEATURE_MODEL: str = "gpt-4o-mini"

# Maximum characters of file content to send to GPT-4o-mini.
# Most gnucobol-contrib files are 200-500 lines (~8,000 chars) so this rarely triggers.
# Large files (>8,000 chars) are truncated to stay within the token budget.
MAX_FILE_CHARS: int = 8_000

# Simple in-memory cache: file_path -> raw COBOL source text.
# Populated on first fetch; cleared between test runs by the test suite.
# In production this lives as long as the Railway process is running.
_file_cache: dict[str, str] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _path_to_github_url(file_path: str) -> str:
    """
    Convert a stored absolute file path to a GitHub raw content URL.

    Stored paths look like:
        /Users/shruti/Week3/data/gnucobol-contrib/payroll/PAYROLL.cob

    We strip everything up to and including "gnucobol-contrib/" to get:
        payroll/PAYROLL.cob

    Then prepend the GitHub raw base URL to get:
        https://raw.githubusercontent.com/OCamlPro/gnucobol-contrib/master/payroll/PAYROLL.cob

    Args:
        file_path: Absolute (or relative) path as stored in Pinecone metadata.

    Returns:
        Full GitHub raw content URL for the file.

    Raises:
        ValueError: If the path does not contain the gnucobol-contrib marker,
                    meaning it's not a file we know how to fetch.
    """
    idx = file_path.find(_MARKER)
    if idx == -1:
        raise ValueError(
            f"Cannot construct GitHub URL — path does not contain "
            f"'{_MARKER}': {file_path!r}"
        )
    relative = file_path[idx + len(_MARKER) :]
    return f"{GITHUB_RAW_BASE}/{relative}"


async def _fetch_file_content(file_path: str) -> str:
    """
    Fetch the full COBOL source text for a file from GitHub raw content.

    Results are cached in memory (_file_cache) so repeated calls for the
    same file (e.g., Explain then Dependencies on the same snippet) only
    make one HTTP request.

    Args:
        file_path: Stored path from Pinecone metadata (absolute local path).

    Returns:
        Full raw COBOL source text.

    Raises:
        HTTPException(400): If file_path is not from gnucobol-contrib.
        HTTPException(404): If the file doesn't exist on GitHub.
        HTTPException(502): If the GitHub request fails for any other reason.
    """
    if file_path in _file_cache:
        logger.debug("cobol_features: cache hit for %s", file_path)
        return _file_cache[file_path]

    # Convert local path to GitHub URL — raises ValueError for invalid paths
    try:
        url = _path_to_github_url(file_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.debug("cobol_features: fetching %s", url)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
    except httpx.RequestError as exc:
        logger.error("cobol_features: GitHub fetch failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch file from GitHub: {exc}",
        ) from exc

    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"File not found on GitHub: {file_path}",
        )

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("cobol_features: GitHub returned %d for %s", resp.status_code, url)
        raise HTTPException(
            status_code=502,
            detail=f"GitHub returned {resp.status_code} for {file_path}",
        ) from exc

    content = resp.text
    _file_cache[file_path] = content
    return content


def _truncate(content: str) -> str:
    """
    Truncate file content to MAX_FILE_CHARS if it's very large.

    Most gnucobol-contrib files are well under this limit. This guard
    exists for the rare oversized files that would blow the token budget.
    """
    if len(content) <= MAX_FILE_CHARS:
        return content
    logger.debug(
        "cobol_features: truncating file content from %d to %d chars",
        len(content),
        MAX_FILE_CHARS,
    )
    return content[:MAX_FILE_CHARS] + "\n... (truncated)"


async def _call_openai_json(
    messages: list[dict[str, str]],
    openai_client: AsyncOpenAI,
) -> dict:  # type: ignore[type-arg]
    """
    Call GPT-4o-mini in JSON mode and return the parsed response dict.

    We use response_format={"type": "json_object"} so the model is
    constrained to return valid JSON — no parsing gymnastics required.

    Args:
        messages:      List of {"role": ..., "content": ...} message dicts.
        openai_client: Async OpenAI client.

    Returns:
        Parsed JSON dict from GPT-4o-mini.

    Raises:
        HTTPException(502): If the API call fails or the response is not valid JSON.
    """
    try:
        response = await openai_client.chat.completions.create(  # type: ignore[call-overload]
            model=_FEATURE_MODEL,
            messages=messages,  # TypedDict vs dict[str, str] — safe at runtime
            temperature=0.1,  # Low temperature for consistent, factual responses
            max_tokens=500,  # Features need slightly more tokens than search answers
            # JSON mode: forces GPT-4o-mini to return valid JSON
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        return dict(json.loads(raw))
    except json.JSONDecodeError as exc:
        logger.error("cobol_features: GPT-4o-mini returned non-JSON: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="LLM returned malformed JSON — please try again.",
        ) from exc
    except Exception as exc:
        logger.error("cobol_features: OpenAI API error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"LLM API error: {exc}",
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Public feature functions
# ─────────────────────────────────────────────────────────────────────────────


async def explain_paragraph(
    file_path: str,
    paragraph_name: str,
    openai_client: AsyncOpenAI,
) -> ExplainResponse:
    """
    Explain what a COBOL paragraph does in plain English.

    Think of this like asking a COBOL expert: "In one paragraph, what does
    CALCULATE-INTEREST actually do?" — you get back a clear, concise answer
    without needing to read the raw code yourself.

    Args:
        file_path:      Pinecone-stored path to the COBOL source file.
        paragraph_name: Name of the COBOL paragraph to explain
                        (e.g. CALCULATE-INTEREST).
        openai_client:  Async OpenAI client (real or mock).

    Returns:
        ExplainResponse with a plain-English explanation of the paragraph.

    Raises:
        HTTPException(400): If file_path is not from gnucobol-contrib.
        HTTPException(404): If the file doesn't exist on GitHub.
        HTTPException(502): If the LLM call fails.
    """
    content = await _fetch_file_content(file_path)
    truncated = _truncate(content)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert COBOL analyst. Explain what the specified COBOL "
                "paragraph does in 2-4 plain-English sentences. Focus on business "
                "purpose, not syntax. Respond with ONLY valid JSON "
                "in this exact format: "
                '{"explanation": "your explanation here"}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"File: {file_path}\n"
                f"Paragraph to explain: {paragraph_name}\n\n"
                f"Full file content:\n```cobol\n{truncated}\n```"
            ),
        },
    ]

    data = await _call_openai_json(messages, openai_client)
    return ExplainResponse(
        status="ok",
        message="ok",
        paragraph_name=paragraph_name,
        explanation=str(data.get("explanation", "")),
    )


async def map_dependencies(
    file_path: str,
    paragraph_name: str,
    openai_client: AsyncOpenAI,
) -> DependenciesResponse:
    """
    Map the PERFORM call graph for a COBOL paragraph.

    In COBOL, paragraphs call each other using PERFORM statements.
    This feature identifies:
    - calls:     paragraphs that THIS paragraph PERFORMs
    - called_by: paragraphs that PERFORM THIS paragraph

    This is like a dependency graph — it shows you upstream and downstream
    relationships without having to trace PERFORM statements by hand.

    Args:
        file_path:      Pinecone-stored path to the COBOL source file.
        paragraph_name: Target paragraph to analyse.
        openai_client:  Async OpenAI client (real or mock).

    Returns:
        DependenciesResponse with calls and called_by lists.

    Raises:
        HTTPException(400/404/502): Same as explain_paragraph.
    """
    content = await _fetch_file_content(file_path)
    truncated = _truncate(content)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a COBOL dependency analyser. Analyse PERFORM statements in "
                "the file to identify the call graph for the specified paragraph. "
                "Respond with ONLY valid JSON in this exact format: "
                '{"calls": ["PARA-A", "PARA-B"], "called_by": ["PARA-C"]}'
                "\nReturn empty lists if no PERFORM relationships are found."
            ),
        },
        {
            "role": "user",
            "content": (
                f"File: {file_path}\n"
                f"Target paragraph: {paragraph_name}\n\n"
                f"Full file content:\n```cobol\n{truncated}\n```"
            ),
        },
    ]

    data = await _call_openai_json(messages, openai_client)
    calls = [str(p) for p in data.get("calls", []) if isinstance(p, str)]
    called_by = [str(p) for p in data.get("called_by", []) if isinstance(p, str)]
    return DependenciesResponse(
        status="ok",
        message="ok",
        paragraph_name=paragraph_name,
        calls=calls,
        called_by=called_by,
    )


async def extract_business_logic(
    file_path: str,
    openai_client: AsyncOpenAI,
) -> BusinessLogicResponse:
    """
    Extract plain-English business rules from an entire COBOL file.

    Unlike the paragraph-level features, this one looks at the whole file
    to identify the business rules it encodes — things like:
    "Overtime applies after 40 hours" or "Tax is withheld at 15%."

    These rules are buried in COMPUTE, IF, and EVALUATE statements.
    The LLM reads them and converts them to human-readable bullet points.

    Args:
        file_path:     Pinecone-stored path to the COBOL source file.
        openai_client: Async OpenAI client (real or mock).

    Returns:
        BusinessLogicResponse with a list of plain-English business rules.

    Raises:
        HTTPException(400/404/502): Same as explain_paragraph.
    """
    content = await _fetch_file_content(file_path)
    truncated = _truncate(content)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a business analyst specialising in COBOL systems. "
                "Extract the business rules encoded in this COBOL program. "
                "Each rule should be one plain-English sentence describing "
                "a real business constraint or calculation (e.g. 'Overtime pay "
                "applies after 40 hours per week'). Ignore pure COBOL mechanics "
                "(OPEN FILE, CLOSE FILE, etc.) — focus on business logic. "
                "Respond with ONLY valid JSON in this exact format: "
                '{"rules": ["Rule 1", "Rule 2", "Rule 3"]}'
                "\nReturn an empty list if no business rules are found."
            ),
        },
        {
            "role": "user",
            "content": (
                f"File: {file_path}\n\nFull file content:\n```cobol\n{truncated}\n```"
            ),
        },
    ]

    data = await _call_openai_json(messages, openai_client)
    rules = [str(r) for r in data.get("rules", []) if isinstance(r, str)]
    return BusinessLogicResponse(
        status="ok",
        message="ok",
        file_path=file_path,
        rules=rules,
    )


async def analyze_impact(
    file_path: str,
    paragraph_name: str,
    openai_client: AsyncOpenAI,
) -> ImpactResponse:
    """
    Identify which COBOL paragraphs would be affected if a given paragraph changed.

    This is a "what breaks if I touch this?" analysis — useful before refactoring
    a COBOL paragraph. The LLM reads the full file and identifies all paragraphs
    that directly or indirectly PERFORM the target paragraph.

    Think of it like a "find all usages" in an IDE, but for COBOL.

    Args:
        file_path:      Pinecone-stored path to the COBOL source file.
        paragraph_name: The paragraph you're considering changing.
        openai_client:  Async OpenAI client (real or mock).

    Returns:
        ImpactResponse with a list of affected paragraph names.

    Raises:
        HTTPException(400/404/502): Same as explain_paragraph.
    """
    content = await _fetch_file_content(file_path)
    truncated = _truncate(content)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a COBOL impact analyst. Given a target paragraph, identify "
                "all other paragraphs in the file that PERFORM it (directly or as "
                "part of a call chain). These are the paragraphs that could break "
                "if the target paragraph changes. "
                "Respond with ONLY valid JSON in this exact format: "
                '{"affected_paragraphs": ["PARA-A", "PARA-B"]}'
                "\nReturn an empty list if no paragraphs are affected."
            ),
        },
        {
            "role": "user",
            "content": (
                f"File: {file_path}\n"
                f"Target paragraph (the one that might change): {paragraph_name}\n\n"
                f"Full file content:\n```cobol\n{truncated}\n```"
            ),
        },
    ]

    data = await _call_openai_json(messages, openai_client)
    raw_affected = data.get("affected_paragraphs", [])
    affected = [str(p) for p in raw_affected if isinstance(p, str)]
    return ImpactResponse(
        status="ok",
        message="ok",
        paragraph_name=paragraph_name,
        affected_paragraphs=affected,
    )
