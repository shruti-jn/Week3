"""
COBOL chunker — split a COBOL source file into semantic chunks for embedding.

Think of this like cutting a book into chapters.

COBOL programs contain named blocks of business logic called "paragraphs"
(e.g. CALCULATE-INTEREST, DISPLAY-RESULT). These are natural semantic units,
so we cut there first: each paragraph becomes one chunk.

If no paragraphs are found (old, unstructured, or non-standard COBOL),
we fall back to fixed-size windowed chunks — like cutting every 50 lines with
a 10-line overlap so no code is lost at a boundary.

Each chunk carries enough metadata (file path, paragraph name, start/end line)
that the retrieval layer can show the user exactly where in the codebase the
relevant code lives.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Regex pattern for a valid COBOL paragraph name.
# Rules:
#   - Must start with an uppercase letter (digits cannot start a paragraph name)
#   - May contain uppercase letters, digits, and hyphens
#   - Minimum length is 2 characters (single-letter identifiers are not real names)
#   - Does NOT include the trailing period (caller strips it before matching)
_PARAGRAPH_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Z][A-Z0-9-]+$")

# COBOL words that can appear alone on a line (with a trailing period) but are
# NOT paragraph labels. Without this exclusion list they would be false positives.
_COBOL_RESERVED_WORDS: frozenset[str] = frozenset(
    {
        # Scope terminators — appear on their own line in some coding styles
        "END-IF",
        "END-PERFORM",
        "END-READ",
        "END-WRITE",
        "END-REWRITE",
        "END-DELETE",
        "END-START",
        "END-EVALUATE",
        "END-SEARCH",
        "END-CALL",
        "END-STRING",
        "END-UNSTRING",
        "END-COMPUTE",
        "END-ADD",
        "END-SUBTRACT",
        "END-MULTIPLY",
        "END-DIVIDE",
        "END-RETURN",
        # Statements that can legitimately appear alone on a line
        "EXIT",
        "CONTINUE",
        "STOP",
        "RETURN",
        "RELEASE",
        # DECLARATIVES section markers
        "DECLARATIVES",
        "END-DECLARATIVES",
        # Debug / special markers
        "DEBUG",
        "END",
        "BEGIN",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Public dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class COBOLChunk:
    """
    A single chunk of COBOL source code ready for embedding and vector storage.

    Think of this like one chapter torn from a book — it contains the raw text
    of a contiguous block of COBOL source lines, plus enough metadata to trace
    it back to the exact location in the original file.

    Attributes:
        file_path: Relative path to the COBOL source file
                   (e.g. "programs/loan-calc.cob").
        paragraph_name: The COBOL paragraph label for this chunk
                        (e.g. "CALCULATE-INTEREST"), or None when this chunk
                        was produced by the fixed-size fallback strategy.
        start_line: 1-indexed line number where this chunk starts in the source file.
        end_line: 1-indexed line number where this chunk ends (inclusive).
        content: The raw source text of this chunk (newlines normalised to \\n).
        chunk_index: Position of this chunk within the file (0-indexed).
        is_fallback: True when fixed-size chunking was used; False when paragraph-based.
    """

    file_path: str
    paragraph_name: str | None
    start_line: int
    end_line: int
    content: str
    chunk_index: int
    is_fallback: bool


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def chunk_cobol_file(
    file_path: Path,
    content: str,
    fallback_chunk_size: int = 50,
    fallback_overlap: int = 10,
) -> list[COBOLChunk]:
    """
    Split a COBOL source file into semantic chunks suitable for embedding.

    This is the main entry point for the chunking pipeline. Two strategies:

    1. **Paragraph-level** (primary): Detect COBOL paragraph labels inside the
       PROCEDURE DIVISION and treat each paragraph as one chunk. This is the
       best strategy because COBOL paragraphs map directly to business functions
       (e.g. CALCULATE-INTEREST, VALIDATE-PAYMENT).

    2. **Fixed-size fallback**: If no paragraphs are found, split the whole file
       into overlapping windows of ``fallback_chunk_size`` lines with
       ``fallback_overlap`` lines of overlap between adjacent windows.

    Args:
        file_path: Path to the COBOL file. Used only for metadata — the file
                   is NOT read here; pass the content separately.
        content: Raw text content of the COBOL file.
        fallback_chunk_size: Lines per chunk when using the fixed-size fallback.
                             Must be >= 1.
        fallback_overlap: Lines shared between consecutive fallback chunks.
                         Must be < fallback_chunk_size.

    Returns:
        List of COBOLChunk objects ordered as they appear in the file.
        Returns an empty list if content is blank.

    Raises:
        ValueError: If fallback_chunk_size < 1 or
                   fallback_overlap >= fallback_chunk_size.
    """
    if fallback_chunk_size < 1:
        raise ValueError(f"fallback_chunk_size must be >= 1, got {fallback_chunk_size}")
    if fallback_overlap >= fallback_chunk_size:
        raise ValueError(
            f"fallback_overlap ({fallback_overlap}) must be < "
            f"fallback_chunk_size ({fallback_chunk_size})"
        )

    # Normalise Windows (\r\n) and old Mac (\r) line endings to Unix (\n)
    normalised = content.replace("\r\n", "\n").replace("\r", "\n")

    if not normalised.strip():
        logger.debug("chunk_cobol_file: content is blank, returning empty list")
        return []

    lines = normalised.splitlines()

    # Try paragraph-level chunking first
    chunks = _split_by_paragraphs(file_path, lines)
    if chunks:
        logger.info(
            "chunk_cobol_file: found %d paragraph(s) in %s",
            len(chunks),
            file_path,
        )
        return chunks

    # Fallback: fixed-size windowed chunking
    logger.info(
        "chunk_cobol_file: no paragraphs found in %s, using fixed-size fallback",
        file_path,
    )
    return _split_fixed_size(file_path, lines, fallback_chunk_size, fallback_overlap)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers — split strategies
# ─────────────────────────────────────────────────────────────────────────────


def _split_by_paragraphs(file_path: Path, lines: list[str]) -> list[COBOLChunk]:
    """
    Split COBOL lines into paragraph-level chunks.

    Scans the file to find the PROCEDURE DIVISION header, then collects
    every paragraph label after it. Each paragraph becomes one chunk;
    the chunk's content runs from the paragraph label line up to (but not
    including) the next paragraph label line.

    Trailing blank lines at the end of each chunk are stripped so that the
    chunk ends on the last meaningful line of code.

    Args:
        file_path: Used to populate COBOLChunk.file_path.
        lines: Source lines with normalised line endings, already split.

    Returns:
        List of COBOLChunk objects, one per paragraph.
        Empty list if no PROCEDURE DIVISION or no paragraph labels are found.
    """
    in_procedure_division = False
    # Each entry is (paragraph_name, 0-based line index)
    paragraph_boundaries: list[tuple[str, int]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip blank and comment lines for structural detection
        if not stripped or _is_comment_line(line):
            continue

        # Watch for the PROCEDURE DIVISION header
        if not in_procedure_division and _is_procedure_division_header(stripped):
            in_procedure_division = True
            continue

        # Once inside the PROCEDURE DIVISION, look for paragraph labels
        if in_procedure_division and _is_paragraph_header(line):
            name = stripped.rstrip(".")
            paragraph_boundaries.append((name, i))
            logger.debug("Found paragraph '%s' at line %d", name, i + 1)

    if not paragraph_boundaries:
        return []

    chunks: list[COBOLChunk] = []
    for idx, (para_name, start_idx) in enumerate(paragraph_boundaries):
        # End of this paragraph = line before the next paragraph label (or EOF)
        if idx + 1 < len(paragraph_boundaries):
            _, next_start_idx = paragraph_boundaries[idx + 1]
            end_idx = next_start_idx - 1
        else:
            end_idx = len(lines) - 1

        # Trim trailing blank lines so the chunk ends on meaningful code
        while end_idx > start_idx and not lines[end_idx].strip():
            end_idx -= 1

        chunk_lines = lines[start_idx : end_idx + 1]
        chunks.append(
            COBOLChunk(
                file_path=str(file_path),
                paragraph_name=para_name,
                start_line=start_idx + 1,  # convert 0-indexed to 1-indexed
                end_line=end_idx + 1,
                content="\n".join(chunk_lines),
                chunk_index=idx,
                is_fallback=False,
            )
        )

    return chunks


def _split_fixed_size(
    file_path: Path,
    lines: list[str],
    chunk_size: int,
    overlap: int,
) -> list[COBOLChunk]:
    """
    Split source lines into fixed-size overlapping windows.

    Used when no COBOL paragraph labels are found. The overlap ensures that
    code near chunk boundaries is represented in two adjacent chunks, so a
    query is less likely to miss relevant code that straddles a boundary.

    Example: chunk_size=50, overlap=10 → step=40.
    Chunk 0: lines 0..49, Chunk 1: lines 40..89, Chunk 2: lines 80..129, ...

    Args:
        file_path: Used to populate COBOLChunk.file_path.
        lines: All source lines.
        chunk_size: Maximum number of lines per chunk.
        overlap: Number of lines shared between consecutive chunks.

    Returns:
        List of COBOLChunk objects with is_fallback=True.
    """
    chunks: list[COBOLChunk] = []
    step = chunk_size - overlap
    chunk_idx = 0
    start = 0

    while start < len(lines):
        end = min(start + chunk_size, len(lines))
        chunk_lines = lines[start:end]
        chunks.append(
            COBOLChunk(
                file_path=str(file_path),
                paragraph_name=None,
                start_line=start + 1,  # 1-indexed
                end_line=end,  # end is exclusive in slice; last 1-indexed line = end
                content="\n".join(chunk_lines),
                chunk_index=chunk_idx,
                is_fallback=True,
            )
        )
        chunk_idx += 1
        start += step

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers — line classification
# ─────────────────────────────────────────────────────────────────────────────


def _is_procedure_division_header(stripped_line: str) -> bool:
    """
    Return True if the stripped line is the PROCEDURE DIVISION header.

    Receives a line that has already been stripped of leading/trailing
    whitespace. Handles the plain form and the USING variant used in
    called subprograms.

    Examples:
        "PROCEDURE DIVISION."                  → True
        "PROCEDURE DIVISION USING WS-DATA."    → True
        "DATA DIVISION."                       → False

    Args:
        stripped_line: A COBOL source line with leading/trailing whitespace removed.

    Returns:
        True if this line marks the start of the PROCEDURE DIVISION.
    """
    upper = stripped_line.upper()
    return upper.startswith("PROCEDURE DIVISION")


def _is_comment_line(line: str) -> bool:
    """
    Return True if a COBOL source line is a comment.

    Handles two comment conventions:
    - **Free-format** (modern): Line starts with ``*>`` after stripping spaces.
    - **Old-style asterisk**: Line starts with ``*`` after stripping spaces.
    - **Fixed-format**: The indicator area (column 7, 0-indexed index 6) contains
      ``*`` or ``/``. Fixed-format COBOL uses the raw original line for this check.

    Args:
        line: A COBOL source line in its original form (not stripped).

    Returns:
        True if this line is a comment and should be skipped.
    """
    stripped = line.lstrip()
    # Free-format and old-style comments: stripped line starts with * or /
    if stripped.startswith("*") or stripped.startswith("/"):
        return True
    # Fixed-format with sequence numbers: column 7 (0-indexed: index 6) is * or /
    if len(line) > 6 and line[6] in ("*", "/"):
        return True
    return False


def _is_paragraph_header(line: str) -> bool:
    """
    Return True if a COBOL source line is a paragraph label.

    A paragraph label is:
    - A single uppercase token (letters, digits, hyphens) that optionally
      ends with a period
    - Alone on its line (no other tokens follow it)
    - Not a comment line
    - Not a COBOL reserved word (EXIT, END-IF, CONTINUE, etc.)
    - At least 2 characters long (excluding the period)

    This function receives the ORIGINAL line (not stripped) so it can check
    the fixed-format indicator area at column 7 for comment detection.

    Examples:
        "CALCULATE-INTEREST."      → True
        "       CALCULATE-INTEREST." → True  (fixed-format indentation)
        "STOP RUN."                → False  (two tokens)
        "PROCEDURE DIVISION."      → False  (two tokens)
        "EXIT."                    → False  (reserved word)
        "*> CALCULATE-INTEREST."   → False  (comment)
        ""                         → False  (empty)

    Args:
        line: A COBOL source line in its original form (not stripped).

    Returns:
        True if this line is a paragraph label.
    """
    # Comment lines are never paragraph headers
    if _is_comment_line(line):
        return False

    stripped = line.strip()
    if not stripped:
        return False

    # A paragraph header has exactly one token (possibly ending with a period)
    tokens = stripped.split()
    if len(tokens) != 1:
        return False

    token = tokens[0]

    # Strip the trailing period; COBOL standard requires it but we want the name
    if token.endswith("."):
        token = token[:-1]

    if not token:
        return False

    # Must match the COBOL identifier pattern (uppercase letters, digits, hyphens)
    if not _PARAGRAPH_NAME_RE.match(token):
        return False

    # Exclude reserved words that can appear alone on a line but are not paragraphs
    if token in _COBOL_RESERVED_WORDS:
        return False

    return True
