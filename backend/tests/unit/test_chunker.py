"""
Tests for the COBOL chunker module.

These tests drive the implementation of chunker.py (TDD).
They were written BEFORE the implementation to define what "done" looks like.

The chunker has two strategies:
1. Paragraph-level split — the primary strategy for well-structured COBOL
2. Fixed-size fallback — for poorly-structured or paragraph-less COBOL

Test organisation:
- TestParagraphHeaderDetection   — unit tests for the paragraph-detection helper
- TestCommentLineDetection       — unit tests for the comment-detection helper
- TestProcedureDivisionDetection — unit tests for the PROCEDURE DIVISION detector
- TestChunkCobolFile             — integration-style tests for the main public function
"""

from pathlib import Path

import pytest

from app.core.ingestion.chunker import (
    COBOLChunk,
    _is_comment_line,
    _is_paragraph_header,
    _is_procedure_division_header,
    _is_section_header,
    chunk_cobol_file,
)

# Dummy path used wherever we don't care about the file path value
DUMMY_PATH = Path("programs/test.cob")


# ─────────────────────────────────────────────────────────────────────────────
# Paragraph header detection
# ─────────────────────────────────────────────────────────────────────────────


class TestParagraphHeaderDetection:
    """Unit tests for the _is_paragraph_header() helper function."""

    def test_valid_paragraph_with_period(self) -> None:
        """Canonical case: uppercase identifier + period, no indent."""
        assert _is_paragraph_header("CALCULATE-INTEREST.") is True

    def test_valid_paragraph_with_leading_spaces(self) -> None:
        """Fixed-format COBOL: paragraph name indented 7 spaces (Area A)."""
        assert _is_paragraph_header("       CALCULATE-INTEREST.") is True

    def test_valid_paragraph_without_period(self) -> None:
        """Some COBOL omits the trailing period on the paragraph label line."""
        assert _is_paragraph_header("CALCULATE-INTEREST") is True

    def test_valid_paragraph_with_digits(self) -> None:
        """Paragraph names may contain digits (e.g. PARA-01)."""
        assert _is_paragraph_header("PARA-001.") is True

    def test_multiple_tokens_not_paragraph(self) -> None:
        """'STOP RUN.' has two tokens — not a paragraph header."""
        assert _is_paragraph_header("STOP RUN.") is False

    def test_procedure_division_not_paragraph(self) -> None:
        """Division headers have two tokens (PROCEDURE + DIVISION)."""
        assert _is_paragraph_header("PROCEDURE DIVISION.") is False

    def test_data_division_not_paragraph(self) -> None:
        assert _is_paragraph_header("DATA DIVISION.") is False

    def test_statement_not_paragraph(self) -> None:
        """Multi-token COBOL statements must not be detected as paragraphs."""
        assert _is_paragraph_header("    MOVE ZERO TO WS-COUNTER.") is False

    def test_reserved_word_exit_not_paragraph(self) -> None:
        """EXIT. can appear alone on a line but is not a paragraph."""
        assert _is_paragraph_header("EXIT.") is False

    def test_reserved_word_continue_not_paragraph(self) -> None:
        assert _is_paragraph_header("CONTINUE.") is False

    def test_reserved_word_end_if_not_paragraph(self) -> None:
        """END-IF. can appear alone — must not be a false positive."""
        assert _is_paragraph_header("END-IF.") is False

    def test_empty_line_not_paragraph(self) -> None:
        assert _is_paragraph_header("") is False

    def test_blank_line_not_paragraph(self) -> None:
        assert _is_paragraph_header("   ") is False

    def test_free_format_comment_not_paragraph(self) -> None:
        """Lines starting with *> are free-format COBOL comments."""
        assert _is_paragraph_header("*> This is a comment.") is False

    def test_indented_comment_not_paragraph(self) -> None:
        """Comment lines with leading spaces before *> must be skipped."""
        assert _is_paragraph_header("      *> CALCULATE-INTEREST.") is False

    def test_fixed_format_comment_col7_not_paragraph(self) -> None:
        """Fixed-format: column 7 (0-indexed index 6) is '*' → comment."""
        assert _is_paragraph_header("      * old style comment") is False

    def test_single_char_identifier_not_paragraph(self) -> None:
        """Single-character identifiers are too short to be real paragraph names."""
        assert _is_paragraph_header("A.") is False

    def test_lowercase_identifier_not_paragraph(self) -> None:
        """COBOL paragraph names are always uppercase."""
        assert _is_paragraph_header("calculate-interest.") is False

    def test_numeric_start_not_paragraph(self) -> None:
        """Paragraph names must start with a letter, not a digit."""
        assert _is_paragraph_header("01-RECORD.") is False


# ─────────────────────────────────────────────────────────────────────────────
# Comment line detection
# ─────────────────────────────────────────────────────────────────────────────


class TestCommentLineDetection:
    """Unit tests for the _is_comment_line() helper function."""

    def test_free_format_comment(self) -> None:
        """*> is the modern free-format comment indicator."""
        assert _is_comment_line("*> this is a comment") is True

    def test_old_style_asterisk_comment(self) -> None:
        """A line starting with * (old-style) is also a comment."""
        assert _is_comment_line("* this is a comment") is True

    def test_indented_free_format_comment(self) -> None:
        """Indented *> comment lines must be recognised."""
        assert _is_comment_line("      *> comment") is True

    def test_fixed_format_comment_at_col7(self) -> None:
        """Fixed-format: when index 6 of the original line is '*'."""
        assert _is_comment_line("      * fixed comment") is True

    def test_regular_statement_not_comment(self) -> None:
        assert _is_comment_line("    MOVE ZERO TO WS-COUNTER.") is False

    def test_empty_line_not_comment(self) -> None:
        assert _is_comment_line("") is False

    def test_paragraph_header_not_comment(self) -> None:
        assert _is_comment_line("CALCULATE-INTEREST.") is False


# ─────────────────────────────────────────────────────────────────────────────
# PROCEDURE DIVISION header detection
# ─────────────────────────────────────────────────────────────────────────────


class TestProcedureDivisionDetection:
    """Unit tests for the _is_procedure_division_header() helper.

    This function receives lines that have already been stripped of
    leading and trailing whitespace.
    """

    def test_basic_procedure_division(self) -> None:
        assert _is_procedure_division_header("PROCEDURE DIVISION.") is True

    def test_procedure_division_without_period(self) -> None:
        assert _is_procedure_division_header("PROCEDURE DIVISION") is True

    def test_procedure_division_with_using_clause(self) -> None:
        """PROCEDURE DIVISION USING <param> is valid in called subprograms."""
        result = _is_procedure_division_header("PROCEDURE DIVISION USING WS-DATA.")
        assert result is True

    def test_data_division_not_procedure(self) -> None:
        assert _is_procedure_division_header("DATA DIVISION.") is False

    def test_identification_division_not_procedure(self) -> None:
        assert _is_procedure_division_header("IDENTIFICATION DIVISION.") is False

    def test_environment_division_not_procedure(self) -> None:
        assert _is_procedure_division_header("ENVIRONMENT DIVISION.") is False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION header detection
# ─────────────────────────────────────────────────────────────────────────────


class TestSectionHeaderDetection:
    """Unit tests for _is_section_header().

    COBOL sections use the pattern 'NAME SECTION.' and are common in
    gnucobol-contrib files (e.g. 'CRYPT SECTION.', 'SETKEY SECTION.').
    Sections act as named block boundaries just like paragraphs.
    """

    def test_basic_section_with_period(self) -> None:
        assert _is_section_header("CRYPT SECTION.") is True

    def test_section_without_period(self) -> None:
        assert _is_section_header("CRYPT SECTION") is True

    def test_section_with_leading_spaces(self) -> None:
        assert _is_section_header(" CRYPT SECTION.") is True

    def test_section_hyphenated_name(self) -> None:
        assert _is_section_header("READ-DATA SECTION.") is True

    def test_section_uppercase_only(self) -> None:
        """Section keyword must be uppercase."""
        assert _is_section_header("SETKEY SECTION.") is True

    def test_comment_line_not_section(self) -> None:
        assert _is_section_header("*> CRYPT SECTION.") is False

    def test_procedure_division_not_section(self) -> None:
        """PROCEDURE DIVISION uses DIVISION, not SECTION."""
        assert _is_section_header("PROCEDURE DIVISION.") is False

    def test_data_division_not_section(self) -> None:
        assert _is_section_header("DATA DIVISION.") is False

    def test_working_storage_section_not_procedure_section(self) -> None:
        """WORKING-STORAGE SECTION is a data section, not a procedure section.
        It IS a valid section header syntactically though — the caller filters
        by requiring PROCEDURE DIVISION to be active first."""
        assert _is_section_header("WORKING-STORAGE SECTION.") is True

    def test_single_token_not_section(self) -> None:
        """A bare paragraph name has only one token — not a section header."""
        assert _is_section_header("CRYPT.") is False

    def test_empty_line_not_section(self) -> None:
        assert _is_section_header("") is False

    def test_blank_line_not_section(self) -> None:
        assert _is_section_header("   ") is False

    def test_lowercase_name_not_section(self) -> None:
        assert _is_section_header("crypt SECTION.") is False

    def test_numeric_start_not_section(self) -> None:
        assert _is_section_header("01 SECTION.") is False


# ─────────────────────────────────────────────────────────────────────────────
# Main function: chunk_cobol_file
# ─────────────────────────────────────────────────────────────────────────────


class TestChunkCobolFile:
    """Tests for the main public function chunk_cobol_file()."""

    # ── Empty / trivial inputs ────────────────────────────────────────────────

    def test_empty_content_returns_empty_list(self) -> None:
        assert chunk_cobol_file(DUMMY_PATH, "") == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert chunk_cobol_file(DUMMY_PATH, "   \n   \n   ") == []

    # ── Paragraph-based chunking (happy path) ─────────────────────────────────

    def test_two_paragraphs_returns_two_chunks(self, sample_cobol_content: str) -> None:
        """The sample fixture has CALCULATE-INTEREST and DISPLAY-RESULT."""
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert len(chunks) == 2

    def test_paragraph_names_correct(self, sample_cobol_content: str) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert [c.paragraph_name for c in chunks] == [
            "CALCULATE-INTEREST",
            "DISPLAY-RESULT",
        ]

    def test_chunk_indices_are_sequential(self, sample_cobol_content: str) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert [c.chunk_index for c in chunks] == [0, 1]

    def test_paragraph_chunks_are_not_fallback(self, sample_cobol_content: str) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert all(not c.is_fallback for c in chunks)

    def test_file_path_stored_as_string(self, sample_cobol_content: str) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert all(c.file_path == str(DUMMY_PATH) for c in chunks)

    def test_chunk_is_cobol_chunk_dataclass(self, sample_cobol_content: str) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert all(isinstance(c, COBOLChunk) for c in chunks)

    # ── Line number correctness ───────────────────────────────────────────────
    # The conftest fixture starts with IDENTIFICATION DIVISION on line 1,
    # PROCEDURE DIVISION on line 13, CALCULATE-INTEREST on line 14,
    # and DISPLAY-RESULT on line 21.

    def test_first_chunk_start_line(self, sample_cobol_content: str) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert chunks[0].start_line == 14

    def test_first_chunk_end_line(self, sample_cobol_content: str) -> None:
        # STOP RUN. is the last non-blank line before DISPLAY-RESULT (line 19)
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert chunks[0].end_line == 19

    def test_second_chunk_start_line(self, sample_cobol_content: str) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert chunks[1].start_line == 21

    def test_second_chunk_end_line(self, sample_cobol_content: str) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert chunks[1].end_line == 23

    def test_start_line_le_end_line_for_all_chunks(
        self, sample_cobol_content: str
    ) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        for chunk in chunks:
            assert chunk.start_line <= chunk.end_line

    def test_line_numbers_are_1_indexed(self, sample_cobol_content: str) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert all(c.start_line >= 1 for c in chunks)
        assert all(c.end_line >= 1 for c in chunks)

    # ── Content correctness ───────────────────────────────────────────────────

    def test_first_chunk_includes_paragraph_header(
        self, sample_cobol_content: str
    ) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert "CALCULATE-INTEREST" in chunks[0].content

    def test_first_chunk_includes_body_statements(
        self, sample_cobol_content: str
    ) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert "COMPUTE INTEREST" in chunks[0].content

    def test_second_chunk_includes_display_statement(
        self, sample_cobol_content: str
    ) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert "DISPLAY 'Interest: ' INTEREST" in chunks[1].content

    def test_trailing_blank_lines_trimmed_from_chunk(
        self, sample_cobol_content: str
    ) -> None:
        """The blank line between paragraphs must not appear in chunk content."""
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        last_line_of_chunk_0 = chunks[0].content.split("\n")[-1]
        assert last_line_of_chunk_0.strip() != ""

    def test_content_does_not_contain_carriage_return(
        self, sample_cobol_content: str
    ) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_content)
        assert all("\r" not in c.content for c in chunks)

    # ── Single paragraph edge case ────────────────────────────────────────────

    def test_single_paragraph_returns_one_paragraph_chunk(self) -> None:
        content = (
            "PROCEDURE DIVISION.\n"
            "ONLY-PARA.\n"
            "    MOVE ZERO TO WS-COUNTER.\n"
            "    STOP RUN.\n"
        )
        chunks = chunk_cobol_file(DUMMY_PATH, content)
        assert len(chunks) == 1
        assert chunks[0].paragraph_name == "ONLY-PARA"
        assert not chunks[0].is_fallback

    def test_single_paragraph_line_numbers(self) -> None:
        content = (
            "PROCEDURE DIVISION.\n"  # line 1
            "ONLY-PARA.\n"  # line 2
            "    MOVE ZERO TO WS-COUNTER.\n"  # line 3
            "    STOP RUN.\n"  # line 4
        )
        chunks = chunk_cobol_file(DUMMY_PATH, content)
        assert chunks[0].start_line == 2
        assert chunks[0].end_line == 4

    # ── Windows line endings ──────────────────────────────────────────────────

    def test_windows_line_endings_produces_one_chunk(
        self, sample_cobol_windows_line_endings: str
    ) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_windows_line_endings)
        assert len(chunks) == 1

    def test_windows_line_endings_correct_paragraph_name(
        self, sample_cobol_windows_line_endings: str
    ) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_windows_line_endings)
        assert chunks[0].paragraph_name == "CALCULATE-INTEREST"

    def test_windows_line_endings_no_carriage_return_in_content(
        self, sample_cobol_windows_line_endings: str
    ) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_windows_line_endings)
        assert "\r" not in chunks[0].content

    # ── Fallback: no paragraphs found ─────────────────────────────────────────

    def test_no_paragraphs_uses_fallback(self, sample_cobol_no_paragraphs: str) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_no_paragraphs)
        assert all(c.is_fallback for c in chunks)

    def test_fallback_chunks_have_no_paragraph_name(
        self, sample_cobol_no_paragraphs: str
    ) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_no_paragraphs)
        assert all(c.paragraph_name is None for c in chunks)

    def test_fallback_chunk_count_450_lines(
        self, sample_cobol_no_paragraphs: str
    ) -> None:
        """450 lines, chunk_size=50, overlap=10 → step=40.
        Start positions: 0, 40, 80, ..., 440 → 12 chunks.
        """
        chunks = chunk_cobol_file(
            DUMMY_PATH,
            sample_cobol_no_paragraphs,
            fallback_chunk_size=50,
            fallback_overlap=10,
        )
        assert len(chunks) == 12

    def test_fallback_non_last_chunks_are_full_size(
        self, sample_cobol_no_paragraphs: str
    ) -> None:
        """Every chunk except the last must have exactly fallback_chunk_size lines."""
        chunks = chunk_cobol_file(
            DUMMY_PATH,
            sample_cobol_no_paragraphs,
            fallback_chunk_size=50,
            fallback_overlap=10,
        )
        for chunk in chunks[:-1]:
            assert len(chunk.content.splitlines()) == 50

    def test_fallback_chunk_indices_are_sequential(
        self, sample_cobol_no_paragraphs: str
    ) -> None:
        chunks = chunk_cobol_file(DUMMY_PATH, sample_cobol_no_paragraphs)
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_fallback_start_and_end_lines_correct(
        self, sample_cobol_no_paragraphs: str
    ) -> None:
        """First fallback chunk must start at line 1."""
        chunks = chunk_cobol_file(
            DUMMY_PATH,
            sample_cobol_no_paragraphs,
            fallback_chunk_size=50,
            fallback_overlap=10,
        )
        assert chunks[0].start_line == 1
        assert chunks[0].end_line == 50

    def test_no_procedure_division_uses_fallback(self) -> None:
        """A file with only DATA DIVISION and no PROCEDURE DIVISION → fallback."""
        content = "DATA DIVISION.\nWORKING-STORAGE SECTION.\n  01 WS-VAR PIC X(10).\n"
        chunks = chunk_cobol_file(DUMMY_PATH, content)
        assert len(chunks) >= 1
        assert all(c.is_fallback for c in chunks)

    # ── Large input ───────────────────────────────────────────────────────────

    def test_large_content_paragraph_chunking(self) -> None:
        """1,001-line file (1 header + 20 paragraphs x 50 lines) -> 20 chunks."""
        lines = ["PROCEDURE DIVISION."]
        for i in range(20):
            lines.append(f"PARA-{i:03d}.")
            lines.extend(["    MOVE ZERO TO WS-COUNTER."] * 49)
        content = "\n".join(lines)

        chunks = chunk_cobol_file(DUMMY_PATH, content)

        assert len(chunks) == 20
        assert chunks[0].paragraph_name == "PARA-000"
        assert chunks[19].paragraph_name == "PARA-019"

    def test_large_content_chunk_indices(self) -> None:
        """chunk_index must count 0..N-1 regardless of chunk count."""
        lines = ["PROCEDURE DIVISION."]
        for i in range(20):
            lines.append(f"PARA-{i:03d}.")
            lines.extend(["    MOVE ZERO TO WS-COUNTER."] * 49)
        content = "\n".join(lines)
        chunks = chunk_cobol_file(DUMMY_PATH, content)
        assert [c.chunk_index for c in chunks] == list(range(20))

    # ── Invalid parameter handling ────────────────────────────────────────────

    def test_invalid_chunk_size_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="fallback_chunk_size"):
            chunk_cobol_file(DUMMY_PATH, "some content", fallback_chunk_size=0)

    def test_invalid_chunk_size_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="fallback_chunk_size"):
            chunk_cobol_file(DUMMY_PATH, "some content", fallback_chunk_size=-1)

    def test_overlap_equal_to_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="fallback_overlap"):
            chunk_cobol_file(
                DUMMY_PATH,
                "some content",
                fallback_chunk_size=10,
                fallback_overlap=10,
            )

    def test_overlap_greater_than_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="fallback_overlap"):
            chunk_cobol_file(
                DUMMY_PATH,
                "some content",
                fallback_chunk_size=10,
                fallback_overlap=15,
            )

    # ── Custom fallback parameters ────────────────────────────────────────────

    def test_custom_fallback_chunk_size_respected(
        self, sample_cobol_no_paragraphs: str
    ) -> None:
        """chunk_size=100 on 450-line content → 5 starts: 0,90,180,270,360."""
        # step = 100 - 10 = 90; starts: 0, 90, 180, 270, 360, 450 → stop at 450
        chunks = chunk_cobol_file(
            DUMMY_PATH,
            sample_cobol_no_paragraphs,
            fallback_chunk_size=100,
            fallback_overlap=10,
        )
        assert len(chunks) == 5

    # ── Boundary: last chunk can be smaller ───────────────────────────────────

    def test_fallback_last_chunk_may_be_smaller(
        self, sample_cobol_no_paragraphs: str
    ) -> None:
        """With 450 lines and chunk_size=50, overlap=10, last chunk starts at line 441.
        450 - 440 = 10 lines → smaller than chunk_size.
        """
        chunks = chunk_cobol_file(
            DUMMY_PATH,
            sample_cobol_no_paragraphs,
            fallback_chunk_size=50,
            fallback_overlap=10,
        )
        last = chunks[-1]
        assert len(last.content.splitlines()) <= 50
        assert last.end_line == 450

    # ── COBOL SECTION header detection ───────────────────────────────────────

    def test_section_creates_named_chunk(self) -> None:
        """'CRYPT SECTION.' should create a chunk named 'CRYPT'."""
        content = (
            "PROCEDURE DIVISION.\n"
            " CRYPT SECTION.\n"
            "    COMPUTE WS-RESULT = WS-INPUT * 2.\n"
            " CRYPT-EX.\n"
            "    EXIT.\n"
        )
        chunks = chunk_cobol_file(DUMMY_PATH, content)
        names = [c.paragraph_name for c in chunks]
        assert "CRYPT" in names

    def test_section_chunk_contains_code(self) -> None:
        """The CRYPT section chunk should include the code before CRYPT-EX."""
        content = (
            "PROCEDURE DIVISION.\n"
            " CRYPT SECTION.\n"
            "    COMPUTE WS-RESULT = WS-INPUT * 2.\n"
            " CRYPT-EX.\n"
            "    EXIT.\n"
        )
        chunks = chunk_cobol_file(DUMMY_PATH, content)
        crypt_chunk = next(c for c in chunks if c.paragraph_name == "CRYPT")
        assert "COMPUTE WS-RESULT" in crypt_chunk.content

    def test_section_chunk_is_not_fallback(self) -> None:
        """Section-based chunks must have is_fallback=False."""
        content = (
            "PROCEDURE DIVISION.\n"
            " CRYPT SECTION.\n"
            "    COMPUTE WS-RESULT = WS-INPUT * 2.\n"
            " CRYPT-EX.\n"
            "    EXIT.\n"
        )
        chunks = chunk_cobol_file(DUMMY_PATH, content)
        crypt_chunk = next(c for c in chunks if c.paragraph_name == "CRYPT")
        assert not crypt_chunk.is_fallback

    def test_multiple_sections_produce_multiple_chunks(self) -> None:
        """Two sections (SETKEY and CRYPT) should produce at least two named chunks."""
        content = (
            "PROCEDURE DIVISION.\n"
            " SETKEY SECTION.\n"
            "    MOVE 1 TO WS-KEY.\n"
            " SETKEY-EX.\n"
            "    EXIT.\n"
            " CRYPT SECTION.\n"
            "    COMPUTE WS-CIPHER = WS-KEY + 1.\n"
            " CRYPT-EX.\n"
            "    EXIT.\n"
        )
        chunks = chunk_cobol_file(DUMMY_PATH, content)
        names = [c.paragraph_name for c in chunks]
        assert "SETKEY" in names
        assert "CRYPT" in names

    def test_section_and_paragraph_mixed(self) -> None:
        """Files with both SECTION headers and plain paragraphs should work."""
        content = (
            "PROCEDURE DIVISION.\n"
            " MAIN-PARA.\n"
            "    PERFORM CRYPT SECTION.\n"
            " CRYPT SECTION.\n"
            "    COMPUTE WS-RESULT = WS-INPUT * 2.\n"
            " CRYPT-EX.\n"
            "    EXIT.\n"
        )
        chunks = chunk_cobol_file(DUMMY_PATH, content)
        names = [c.paragraph_name for c in chunks]
        assert "MAIN-PARA" in names
        assert "CRYPT" in names
