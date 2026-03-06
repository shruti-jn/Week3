"""
Tests for app.core.ingestion.chunk_filter — chunk quality filter.

Verifies that exit trampolines, single-line constants, separator-only chunks,
and other semantically empty COBOL paragraphs are excluded from indexing,
while real logic paragraphs pass through unmodified.

TDD: this file was written before chunk_filter.py existed.
"""

from __future__ import annotations

import pytest

from app.core.ingestion.chunker import COBOLChunk
from app.core.ingestion.chunk_filter import (
    _count_non_trivial_lines,
    _has_logic_verb,
    is_indexable,
    filter_chunks,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_chunk(
    content: str,
    is_fallback: bool = False,
    paragraph_name: str | None = "CALC-TOTAL",
) -> COBOLChunk:
    """
    Build a minimal COBOLChunk for testing.

    Only the fields that chunk_filter cares about are interesting here
    (content and is_fallback). The rest use throwaway defaults.
    """
    return COBOLChunk(
        file_path="programs/test.cob",
        paragraph_name=paragraph_name,
        start_line=1,
        end_line=1 + content.count("\n"),
        content=content,
        chunk_index=0,
        is_fallback=is_fallback,
    )


# ---------------------------------------------------------------------------
# _count_non_trivial_lines
# ---------------------------------------------------------------------------


def test_count_strips_label_line() -> None:
    """First line of a named chunk is the paragraph label — not counted."""
    content = "CALC-TOTAL.\n    MOVE A TO B.\n    MOVE C TO D.\n    MOVE E TO F.\n    MOVE G TO H."
    chunk = make_chunk(content, is_fallback=False)
    # Label line stripped → 4 MOVE lines remain
    assert _count_non_trivial_lines(chunk.content, chunk.is_fallback) == 4


def test_count_strips_comment_lines() -> None:
    """Lines starting with *> (free-format comment) are not counted."""
    content = (
        "CALC-TOTAL.\n"
        "*> This is a comment\n"
        "*> Another comment\n"
        "    MOVE A TO B.\n"
        "    MOVE C TO D.\n"
        "    MOVE E TO F.\n"
        "    MOVE G TO H."
    )
    chunk = make_chunk(content, is_fallback=False)
    # Label + 2 comments stripped → 4 real lines
    assert _count_non_trivial_lines(chunk.content, chunk.is_fallback) == 4


def test_count_strips_fixed_format_comments() -> None:
    """Lines with * at column 7 (fixed-format COBOL comment indicator) are not counted."""
    content = (
        "CALC-TOTAL.\n"
        "      * fixed-format comment\n"
        "    MOVE A TO B.\n"
        "    MOVE C TO D.\n"
        "    MOVE E TO F.\n"
        "    MOVE G TO H."
    )
    chunk = make_chunk(content, is_fallback=False)
    # Label + 1 fixed comment stripped → 4 real lines
    assert _count_non_trivial_lines(chunk.content, chunk.is_fallback) == 4


def test_count_strips_separator_lines() -> None:
    """Lines made up only of -, =, or * chars (separator decorators) are not counted."""
    content = (
        "CALC-TOTAL.\n"
        "*>----------------------------\n"
        "    MOVE A TO B.\n"
        "    MOVE C TO D.\n"
        "    MOVE E TO F.\n"
        "    MOVE G TO H."
    )
    chunk = make_chunk(content, is_fallback=False)
    # Label + separator stripped → 4 real lines
    assert _count_non_trivial_lines(chunk.content, chunk.is_fallback) == 4


def test_count_strips_plain_dash_separator() -> None:
    """A line of plain dashes (no *> prefix) is also a separator — not counted."""
    content = (
        "CALC-TOTAL.\n"
        "    --------\n"
        "    MOVE A TO B.\n"
        "    MOVE C TO D.\n"
        "    MOVE E TO F.\n"
        "    MOVE G TO H."
    )
    chunk = make_chunk(content, is_fallback=False)
    # Label + plain dash separator stripped → 4 real lines
    assert _count_non_trivial_lines(chunk.content, chunk.is_fallback) == 4


def test_count_strips_blank_lines() -> None:
    """Empty or whitespace-only lines are not counted."""
    content = (
        "CALC-TOTAL.\n"
        "\n"
        "   \n"
        "    MOVE A TO B.\n"
        "    MOVE C TO D.\n"
        "    MOVE E TO F.\n"
        "    MOVE G TO H."
    )
    chunk = make_chunk(content, is_fallback=False)
    # Label + 2 blank lines stripped → 4 real lines
    assert _count_non_trivial_lines(chunk.content, chunk.is_fallback) == 4


def test_count_real_code_lines() -> None:
    """Standard COBOL statements — MOVE, IF, END-IF — are counted."""
    content = (
        "CALC-TOTAL.\n"
        "    IF WS-AMOUNT > 0\n"
        "        MOVE WS-AMOUNT TO WS-TOTAL\n"
        "    END-IF."
    )
    chunk = make_chunk(content, is_fallback=False)
    # Label stripped → 3 real code lines
    assert _count_non_trivial_lines(chunk.content, chunk.is_fallback) == 3


def test_count_fallback_no_label_stripped() -> None:
    """Fallback chunks have no paragraph label, so the first line is real code."""
    content = (
        "    MOVE A TO B.\n"
        "    MOVE C TO D.\n"
        "    MOVE E TO F.\n"
        "    MOVE G TO H."
    )
    chunk = make_chunk(content, is_fallback=True)
    # No label to strip → all 4 lines counted
    assert _count_non_trivial_lines(chunk.content, chunk.is_fallback) == 4


def test_count_empty_string_returns_zero() -> None:
    """Empty content string returns 0 non-trivial lines."""
    assert _count_non_trivial_lines("", False) == 0


# ---------------------------------------------------------------------------
# _has_logic_verb
# ---------------------------------------------------------------------------


def test_has_move() -> None:
    """MOVE statement is a logic verb — returns True."""
    assert _has_logic_verb("    MOVE X TO Y.") is True


def test_has_compute() -> None:
    """COMPUTE statement is a logic verb — returns True."""
    assert _has_logic_verb("    COMPUTE WS-INT = WS-RATE * WS-PRINCIPAL.") is True


def test_has_perform() -> None:
    """PERFORM statement is a logic verb — returns True."""
    assert _has_logic_verb("    PERFORM CALC-TOTAL.") is True


def test_has_if() -> None:
    """IF statement is a logic verb — returns True."""
    assert _has_logic_verb("    IF WS-X > 0") is True


def test_exit_only_no_verb() -> None:
    """EXIT is not a logic verb — exit trampolines return False."""
    assert _has_logic_verb("    EXIT.") is False


def test_constant_only_no_verb() -> None:
    """A bare COBOL identifier or string literal is not a logic verb."""
    assert _has_logic_verb('    COB2CGI-LF\n    "<BR>"') is False


def test_separator_only_no_verb() -> None:
    """A separator line of dashes/stars contains no logic verb."""
    assert _has_logic_verb("*>----------------------------") is False


def test_verb_case_insensitive() -> None:
    """Verb matching is case-insensitive — lowercase 'move' counts."""
    assert _has_logic_verb("    move x to y.") is True


def test_partial_word_not_matched() -> None:
    """'REMOVAL' contains 'MOVE' as a substring — must NOT match (whole-word only)."""
    assert _has_logic_verb("    REMOVAL OF ITEM.") is False


# ---------------------------------------------------------------------------
# is_indexable
# ---------------------------------------------------------------------------


def test_real_paragraph_is_indexable() -> None:
    """A proper COBOL paragraph with logic is indexable."""
    content = (
        "CALC-INTEREST.\n"
        "    MOVE WS-PRINCIPAL TO WS-TEMP.\n"
        "    COMPUTE WS-INTEREST = WS-TEMP * WS-RATE.\n"
        "    IF WS-INTEREST > WS-MAX-INTEREST\n"
        "        MOVE WS-MAX-INTEREST TO WS-INTEREST\n"
        "    END-IF.\n"
        "    ADD WS-INTEREST TO WS-TOTAL.\n"
        "    PERFORM UPDATE-LEDGER.\n"
        "    MOVE WS-TOTAL TO WS-OUTPUT.\n"
        "    MOVE SPACES TO WS-TEMP."
    )
    assert is_indexable(make_chunk(content)) is True


def test_exit_trampoline_not_indexable() -> None:
    """Exit trampolines — paragraph label + EXIT. — are not indexable."""
    content = "PARA-EX.\n    EXIT."
    assert is_indexable(make_chunk(content)) is False


def test_single_constant_not_indexable() -> None:
    """A paragraph whose body is just a bare constant is not indexable."""
    content = "PARA.\n    COB2CGI-LF"
    assert is_indexable(make_chunk(content)) is False


def test_two_line_html_stub_not_indexable() -> None:
    """An HTML data stub (2 string literals) is not indexable."""
    content = 'PARA.\n    "COB2CGI-ENV-VALUE"\n    "<BR>"'
    assert is_indexable(make_chunk(content)) is False


def test_short_but_has_logic_not_indexable() -> None:
    """3 non-trivial lines with MOVE fails the line-count check (need >= 4)."""
    content = "PARA.\n    MOVE A TO B.\n    MOVE C TO D.\n    MOVE E TO F."
    assert is_indexable(make_chunk(content)) is False


def test_enough_lines_no_verb_not_indexable() -> None:
    """4+ non-trivial lines that contain only EXIT/data — no logic verb — are not indexable."""
    # These lines are non-trivial (not comments/blanks/separators) but contain no logic verbs.
    # DISPLAY is not in _LOGIC_VERBS, so it does NOT count.
    content = (
        "PARA.\n"
        "    EXIT.\n"
        "    COB2CGI-LF.\n"
        "    COB2CGI-CRLF.\n"
        "    COB2CGI-ENV-VALUE."
    )
    assert is_indexable(make_chunk(content)) is False


def test_fallback_chunk_real_code_indexable() -> None:
    """A fallback chunk with real COBOL logic is indexable."""
    content = (
        "    PERFORM CALC-INTEREST.\n"
        "    PERFORM UPDATE-LEDGER.\n"
        "    MOVE WS-RESULT TO WS-OUTPUT.\n"
        "    PERFORM CLOSE-FILES.\n"
        "    STOP RUN."
    )
    assert is_indexable(make_chunk(content, is_fallback=True)) is True


def test_fallback_chunk_stub_not_indexable() -> None:
    """A fallback chunk with only 2 lines and no verbs is not indexable."""
    content = "    COB2CGI-LF\n    COB2CGI-CRLF"
    assert is_indexable(make_chunk(content, is_fallback=True)) is False


def test_empty_content_not_indexable() -> None:
    """An empty content string is not indexable."""
    assert is_indexable(make_chunk("")) is False


# ---------------------------------------------------------------------------
# filter_chunks
# ---------------------------------------------------------------------------


def _real_chunk(name: str = "CALC-TOTAL") -> COBOLChunk:
    """Build a real (indexable) chunk with enough lines and a logic verb."""
    content = (
        f"{name}.\n"
        "    MOVE WS-PRINCIPAL TO WS-TEMP.\n"
        "    COMPUTE WS-INTEREST = WS-TEMP * WS-RATE.\n"
        "    IF WS-INTEREST > 0\n"
        "        MOVE WS-INTEREST TO WS-RESULT\n"
        "    END-IF."
    )
    return make_chunk(content, is_fallback=False, paragraph_name=name)


def _stub_chunk(name: str = "PARA-EX") -> COBOLChunk:
    """Build a stub (non-indexable) exit trampoline chunk."""
    return make_chunk(f"{name}.\n    EXIT.", is_fallback=False, paragraph_name=name)


def test_filter_removes_stubs() -> None:
    """A mix of real and stub chunks — stubs are removed, real ones kept."""
    chunks = [_real_chunk("A"), _stub_chunk("B-EX"), _real_chunk("C"), _stub_chunk("D-EX")]
    result = filter_chunks(chunks)
    names = [c.paragraph_name for c in result]
    assert names == ["A", "C"]


def test_filter_empty_list() -> None:
    """An empty input list returns an empty list."""
    assert filter_chunks([]) == []


def test_filter_all_real() -> None:
    """All real chunks pass through unchanged."""
    chunks = [_real_chunk("A"), _real_chunk("B"), _real_chunk("C")]
    assert filter_chunks(chunks) == chunks


def test_filter_all_stubs() -> None:
    """All stub chunks → empty result."""
    chunks = [_stub_chunk("A-EX"), _stub_chunk("B-EX")]
    assert filter_chunks(chunks) == []


def test_filter_preserves_order() -> None:
    """The order of the real chunks is preserved after filtering."""
    a = _real_chunk("ALPHA")
    b = _real_chunk("BETA")
    c = _real_chunk("GAMMA")
    stubs = [_stub_chunk("X-EX"), _stub_chunk("Y-EX")]
    # Interleave real and stubs
    mixed = [a, stubs[0], b, stubs[1], c]
    result = filter_chunks(mixed)
    assert result == [a, b, c]
