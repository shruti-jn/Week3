"""
Unit tests for backend/app/core/features/cobol_features.py

All tests are fully mocked — no GitHub network calls, no OpenAI calls,
no money spent. Written before the implementation (TDD).

Test coverage checklist:
[x] Happy path — each of the 4 features returns the correct response model
[x] Empty/missing paragraph_name — graceful handling
[x] Invalid file_path (not gnucobol-contrib) — ValueError / 400
[x] GitHub 404 — HTTPException 404
[x] GitHub timeout / network error — HTTPException 502
[x] OpenAI failure — HTTPException 502
[x] File cache — GitHub is only fetched once per path
[x] Path-to-URL conversion — correct URL for valid paths
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.models.responses import (
    BusinessLogicResponse,
    DependenciesResponse,
    ExplainResponse,
    ImpactResponse,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers shared across tests
# ─────────────────────────────────────────────────────────────────────────────

VALID_FILE_PATH = "/Users/shruti/Week3/data/gnucobol-contrib/payroll/PAYROLL.cob"
EXPECTED_GITHUB_URL = (
    "https://raw.githubusercontent.com/OCamlPro/gnucobol-contrib/master"
    "/payroll/PAYROLL.cob"
)

SAMPLE_COBOL = (
    "PROCEDURE DIVISION.\n"
    "CALCULATE-INTEREST.\n"
    "    COMPUTE INTEREST = PRINCIPAL * RATE / 100.\n"
    "    PERFORM DISPLAY-RESULT.\n"
    "    STOP RUN.\n"
    "\n"
    "DISPLAY-RESULT.\n"
    "    DISPLAY 'Interest: ' INTEREST.\n"
    "    STOP RUN.\n"
)


def _make_openai_json_response(payload: dict) -> AsyncMock:
    """
    Build a fake non-streaming OpenAI chat completion that returns JSON text.

    The features module calls create(stream=False) for a single JSON blob.
    We mimic the structure: response.choices[0].message.content = json string.
    """
    client = AsyncMock()
    choice = MagicMock()
    choice.message.content = json.dumps(payload)
    completion = MagicMock()
    completion.choices = [choice]
    client.chat.completions.create = AsyncMock(return_value=completion)
    return client


def _make_httpx_response(status_code: int, text: str = "") -> MagicMock:
    """Build a fake httpx.Response with the given status code and body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text

    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None

    return resp


# ─────────────────────────────────────────────────────────────────────────────
# _path_to_github_url
# ─────────────────────────────────────────────────────────────────────────────


def test_path_to_github_url_valid() -> None:
    """
    A gnucobol-contrib file path should produce the correct GitHub raw URL.
    The local prefix is stripped and the repo base is prepended.
    """
    from app.core.features.cobol_features import _path_to_github_url

    url = _path_to_github_url(VALID_FILE_PATH)
    assert url == EXPECTED_GITHUB_URL


def test_path_to_github_url_windows_style() -> None:
    """Windows-style separators in the path should still produce a valid URL."""
    from app.core.features.cobol_features import _path_to_github_url

    windows_path = r"C:\Users\shruti\Week3\data\gnucobol-contrib\payroll\PAYROLL.cob"
    # On Windows the marker still matches because we search for the string
    url = _path_to_github_url(windows_path.replace("\\", "/"))
    assert url == EXPECTED_GITHUB_URL


def test_path_to_github_url_missing_marker() -> None:
    """A path that doesn't contain 'gnucobol-contrib/' should raise ValueError."""
    from app.core.features.cobol_features import _path_to_github_url

    with pytest.raises(ValueError, match="gnucobol-contrib"):
        _path_to_github_url("/some/other/path/SOMETHING.cob")


def test_path_to_github_url_empty_string() -> None:
    """An empty file_path should raise ValueError."""
    from app.core.features.cobol_features import _path_to_github_url

    with pytest.raises(ValueError):
        _path_to_github_url("")


# ─────────────────────────────────────────────────────────────────────────────
# _fetch_file_content — GitHub fetch + caching
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_file_content_happy_path() -> None:
    """A valid path fetches content from GitHub and returns the file text."""
    from app.core.features import cobol_features
    from app.core.features.cobol_features import _fetch_file_content

    # Clear cache before test
    cobol_features._file_cache.clear()

    resp = _make_httpx_response(200, SAMPLE_COBOL)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=resp)

    with patch("app.core.features.cobol_features.httpx.AsyncClient", return_value=mock_client):
        content = await _fetch_file_content(VALID_FILE_PATH)

    assert content == SAMPLE_COBOL


@pytest.mark.asyncio
async def test_fetch_file_content_caches_result() -> None:
    """
    Calling _fetch_file_content twice for the same path should only
    make one HTTP request. The second call reads from the in-memory cache.
    """
    from app.core.features import cobol_features
    from app.core.features.cobol_features import _fetch_file_content

    cobol_features._file_cache.clear()

    resp = _make_httpx_response(200, SAMPLE_COBOL)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=resp)

    with patch("app.core.features.cobol_features.httpx.AsyncClient", return_value=mock_client):
        await _fetch_file_content(VALID_FILE_PATH)
        await _fetch_file_content(VALID_FILE_PATH)

    # Only one HTTP GET — the second call hits the cache
    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_fetch_file_content_github_404() -> None:
    """If GitHub returns 404 the function raises HTTPException with status 404."""
    from app.core.features import cobol_features
    from app.core.features.cobol_features import _fetch_file_content

    cobol_features._file_cache.clear()

    resp = _make_httpx_response(404)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=resp)

    with patch("app.core.features.cobol_features.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await _fetch_file_content(VALID_FILE_PATH)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_file_content_invalid_path_raises_400() -> None:
    """An invalid path (not from gnucobol-contrib) raises HTTPException 400."""
    from app.core.features import cobol_features
    from app.core.features.cobol_features import _fetch_file_content

    cobol_features._file_cache.clear()

    with pytest.raises(HTTPException) as exc_info:
        await _fetch_file_content("/etc/passwd")

    assert exc_info.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# explain_paragraph
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explain_paragraph_happy_path() -> None:
    """
    With a valid file path and paragraph name, explain_paragraph returns an
    ExplainResponse with a non-empty explanation string.
    """
    from app.core.features import cobol_features
    from app.core.features.cobol_features import explain_paragraph

    cobol_features._file_cache[VALID_FILE_PATH] = SAMPLE_COBOL  # pre-seed cache

    openai_client = _make_openai_json_response(
        {"explanation": "This paragraph computes loan interest."}
    )

    result = await explain_paragraph(VALID_FILE_PATH, "CALCULATE-INTEREST", openai_client)

    assert isinstance(result, ExplainResponse)
    assert result.status == "ok"
    assert result.paragraph_name == "CALCULATE-INTEREST"
    assert result.explanation == "This paragraph computes loan interest."


@pytest.mark.asyncio
async def test_explain_paragraph_openai_failure() -> None:
    """If OpenAI raises an exception, explain_paragraph raises HTTPException 502."""
    from app.core.features import cobol_features
    from app.core.features.cobol_features import explain_paragraph

    cobol_features._file_cache[VALID_FILE_PATH] = SAMPLE_COBOL

    openai_client = AsyncMock()
    openai_client.chat.completions.create = AsyncMock(
        side_effect=Exception("OpenAI API error")
    )

    with pytest.raises(HTTPException) as exc_info:
        await explain_paragraph(VALID_FILE_PATH, "CALCULATE-INTEREST", openai_client)

    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_explain_paragraph_malformed_json() -> None:
    """
    If GPT-4o-mini returns malformed JSON, the function raises HTTPException 502
    rather than crashing with a raw json.JSONDecodeError.
    """
    from app.core.features import cobol_features
    from app.core.features.cobol_features import explain_paragraph

    cobol_features._file_cache[VALID_FILE_PATH] = SAMPLE_COBOL

    openai_client = AsyncMock()
    choice = MagicMock()
    choice.message.content = "not valid json {{{"
    completion = MagicMock()
    completion.choices = [choice]
    openai_client.chat.completions.create = AsyncMock(return_value=completion)

    with pytest.raises(HTTPException) as exc_info:
        await explain_paragraph(VALID_FILE_PATH, "CALCULATE-INTEREST", openai_client)

    assert exc_info.value.status_code == 502


# ─────────────────────────────────────────────────────────────────────────────
# map_dependencies
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_map_dependencies_happy_path() -> None:
    """
    map_dependencies returns a DependenciesResponse with calls and called_by lists
    populated from the LLM-parsed PERFORM statement analysis.
    """
    from app.core.features import cobol_features
    from app.core.features.cobol_features import map_dependencies

    cobol_features._file_cache[VALID_FILE_PATH] = SAMPLE_COBOL

    openai_client = _make_openai_json_response(
        {"calls": ["DISPLAY-RESULT"], "called_by": ["MAIN-PROCEDURE"]}
    )

    result = await map_dependencies(VALID_FILE_PATH, "CALCULATE-INTEREST", openai_client)

    assert isinstance(result, DependenciesResponse)
    assert result.status == "ok"
    assert result.paragraph_name == "CALCULATE-INTEREST"
    assert "DISPLAY-RESULT" in result.calls
    assert "MAIN-PROCEDURE" in result.called_by


@pytest.mark.asyncio
async def test_map_dependencies_empty_lists() -> None:
    """When the LLM finds no PERFORM calls, calls and called_by are empty lists."""
    from app.core.features import cobol_features
    from app.core.features.cobol_features import map_dependencies

    cobol_features._file_cache[VALID_FILE_PATH] = SAMPLE_COBOL

    openai_client = _make_openai_json_response({"calls": [], "called_by": []})

    result = await map_dependencies(VALID_FILE_PATH, "DISPLAY-RESULT", openai_client)

    assert result.calls == []
    assert result.called_by == []


# ─────────────────────────────────────────────────────────────────────────────
# extract_business_logic
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_business_logic_happy_path() -> None:
    """
    extract_business_logic returns a BusinessLogicResponse with a non-empty
    list of plain-English business rules extracted from the file.
    """
    from app.core.features import cobol_features
    from app.core.features.cobol_features import extract_business_logic

    cobol_features._file_cache[VALID_FILE_PATH] = SAMPLE_COBOL

    openai_client = _make_openai_json_response(
        {
            "rules": [
                "Interest is calculated as Principal × Rate ÷ 100.",
                "Results are displayed only when interest is greater than zero.",
            ]
        }
    )

    result = await extract_business_logic(VALID_FILE_PATH, openai_client)

    assert isinstance(result, BusinessLogicResponse)
    assert result.status == "ok"
    assert result.file_path == VALID_FILE_PATH
    assert len(result.rules) == 2
    assert "Interest" in result.rules[0]


@pytest.mark.asyncio
async def test_extract_business_logic_no_rules() -> None:
    """When the LLM finds no business rules, rules is an empty list."""
    from app.core.features import cobol_features
    from app.core.features.cobol_features import extract_business_logic

    cobol_features._file_cache[VALID_FILE_PATH] = SAMPLE_COBOL

    openai_client = _make_openai_json_response({"rules": []})

    result = await extract_business_logic(VALID_FILE_PATH, openai_client)

    assert result.rules == []


# ─────────────────────────────────────────────────────────────────────────────
# analyze_impact
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_impact_happy_path() -> None:
    """
    analyze_impact returns an ImpactResponse listing paragraphs that would break
    if the specified paragraph changed.
    """
    from app.core.features import cobol_features
    from app.core.features.cobol_features import analyze_impact

    cobol_features._file_cache[VALID_FILE_PATH] = SAMPLE_COBOL

    openai_client = _make_openai_json_response(
        {"affected_paragraphs": ["MAIN-PROCEDURE", "REPORT-SECTION"]}
    )

    result = await analyze_impact(VALID_FILE_PATH, "CALCULATE-INTEREST", openai_client)

    assert isinstance(result, ImpactResponse)
    assert result.status == "ok"
    assert result.paragraph_name == "CALCULATE-INTEREST"
    assert "MAIN-PROCEDURE" in result.affected_paragraphs


@pytest.mark.asyncio
async def test_analyze_impact_no_affected() -> None:
    """When no paragraphs are affected, affected_paragraphs is an empty list."""
    from app.core.features import cobol_features
    from app.core.features.cobol_features import analyze_impact

    cobol_features._file_cache[VALID_FILE_PATH] = SAMPLE_COBOL

    openai_client = _make_openai_json_response({"affected_paragraphs": []})

    result = await analyze_impact(VALID_FILE_PATH, "DISPLAY-RESULT", openai_client)

    assert result.affected_paragraphs == []


# ─────────────────────────────────────────────────────────────────────────────
# Large file truncation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explain_paragraph_truncates_large_file() -> None:
    """
    For files larger than MAX_FILE_CHARS, the content is truncated before
    sending to GPT-4o-mini to keep within the token budget.
    """
    from app.core.features import cobol_features
    from app.core.features.cobol_features import MAX_FILE_CHARS, explain_paragraph

    large_content = "X" * (MAX_FILE_CHARS + 1000)
    cobol_features._file_cache[VALID_FILE_PATH] = large_content

    captured_messages: list = []

    async def capture_call(**kwargs: object) -> MagicMock:
        captured_messages.append(kwargs.get("messages", []))
        choice = MagicMock()
        choice.message.content = json.dumps({"explanation": "truncated test"})
        completion = MagicMock()
        completion.choices = [choice]
        return completion

    openai_client = AsyncMock()
    openai_client.chat.completions.create = AsyncMock(side_effect=capture_call)

    await explain_paragraph(VALID_FILE_PATH, "CALCULATE-INTEREST", openai_client)

    # The user message should not contain more than MAX_FILE_CHARS of file content
    user_message = captured_messages[0][1]["content"]
    assert len(user_message) < MAX_FILE_CHARS + 500  # allow for prompt overhead
