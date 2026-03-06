"""
chunk_filter — quality gate for COBOL chunks before Pinecone indexing.

Think of this module like a bouncer at a concert: only chunks that carry real
COBOL logic are allowed in. Exit trampolines, single-line constants, and
separator-only stubs are turned away at the door.

Why a separate module (not part of the chunker)?
- The chunker's job is boundary detection (where does one paragraph end
  and the next begin?).
- Deciding *whether* a chunk is worth indexing is a different concern —
  quality judgement.
- Keeping them apart means each module is easier to test and modify
  independently.

Public API:
    is_indexable(chunk)      → True if the chunk should be embedded and stored.
    filter_chunks(chunks)    → list of chunks that pass the quality gate.
"""

from __future__ import annotations

import re

from app.core.ingestion.chunker import COBOLChunk

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# COBOL reserved verbs that indicate real logic (not data stubs or trampolines).
# These are matched as whole words (not substrings) — "REMOVAL" must NOT match "MOVE".
_LOGIC_VERBS: frozenset[str] = frozenset(
    {
        "MOVE",
        "COMPUTE",
        "PERFORM",
        "IF",
        "EVALUATE",
        "READ",
        "WRITE",
        "REWRITE",
        "CALL",
        "ADD",
        "SUBTRACT",
        "MULTIPLY",
        "DIVIDE",
        "OPEN",
        "CLOSE",
        "INITIALIZE",
        "STRING",
        "UNSTRING",
        "INSPECT",
        "SEARCH",
        "SET",
        "STOP",
    }
)

# Pre-compiled pattern for whole-word verb matching (case-insensitive).
_VERB_PATTERN: re.Pattern[str] = re.compile(
    r"\b(" + "|".join(re.escape(v) for v in _LOGIC_VERBS) + r")\b",
    re.IGNORECASE,
)

# Minimum non-trivial lines required for a chunk to be considered indexable.
# 4 is conservative enough not to filter genuine short paragraphs
# (PERFORM + body + END-x).
_MIN_NON_TRIVIAL_LINES: int = 4


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _is_separator_line(line: str) -> bool:
    """
    Return True if a line is a visual separator — made up only of -, =, or * chars
    (after stripping the *> prefix and surrounding whitespace).

    For example: '*>----------------------------' and '=======' are separators.
    They carry no logic and should not count as real lines.
    """
    return all(c in "-=*" for c in line.strip())


def _is_trivial_line(line: str, is_fixed_format_comment: bool) -> bool:
    """
    Return True if a line carries no real content and should be excluded from
    the non-trivial line count.

    A line is trivial if it is:
    - Blank or whitespace-only
    - A free-format comment (stripped line starts with *>)
    - A fixed-format comment (character at index 6 is *)
    - A visual separator (only -, =, * chars after stripping *>)

    Args:
        line: A single source line (trailing newline already stripped).
        is_fixed_format_comment: Pre-computed flag (line[6] == '*') for this line.
    """
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("*>"):
        return True
    if is_fixed_format_comment:
        return True
    if _is_separator_line(stripped):
        return True
    return False


def _count_non_trivial_lines(content: str, is_fallback: bool) -> int:
    """
    Count the lines in a chunk that carry real COBOL code — not label, not comments,
    not blank lines, not visual separators.

    Think of it like counting the "meat" of a chapter after removing the chapter
    title, blank pages, and decorative dividers.

    For named (non-fallback) chunks the first line is always the paragraph label
    (e.g. "CALC-INTEREST.") and is excluded from the count.
    For fallback chunks there is no label — the first line is real code.

    Args:
        content:     Full text of the chunk (newline-separated lines).
        is_fallback: True when fixed-size chunking produced this chunk (no label line).

    Returns:
        Number of non-trivial lines in the body of the chunk.
    """
    lines = content.splitlines()
    if not lines:
        return 0

    # Skip the paragraph label line for named chunks
    body_lines = lines if is_fallback else lines[1:]

    count = 0
    for line in body_lines:
        # Detect fixed-format comment: character at position 6 (0-indexed) is '*'
        is_fixed_comment = len(line) > 6 and line[6] == "*"
        if not _is_trivial_line(line, is_fixed_comment):
            count += 1
    return count


def _has_logic_verb(content: str) -> bool:
    """
    Return True if the chunk body contains at least one COBOL logic verb as a
    whole word (case-insensitive).

    This filters out chunks whose bodies are purely constants, literals, or EXIT
    trampolines — none of which contain any of the verbs in _LOGIC_VERBS.

    Whole-word matching means 'REMOVAL' will NOT match 'MOVE', because 'MOVE'
    is not surrounded by word boundaries in that word.

    Args:
        content: Raw text of the chunk (all lines joined).

    Returns:
        True if at least one logic verb is found, False otherwise.
    """
    return bool(_VERB_PATTERN.search(content))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_indexable(chunk: COBOLChunk) -> bool:
    """
    Return True if a COBOL chunk is worth embedding and storing in Pinecone.

    A chunk passes the quality gate if and only if BOTH conditions hold:
    1. It has at least 4 non-trivial lines (body after stripping label, comments,
       blank lines, and separators).
    2. Its body contains at least one COBOL logic verb (MOVE, IF, COMPUTE, etc.).

    Exit trampolines (EXIT.), single-line constants, and separator-only stubs
    all fail one or both checks and are excluded.

    Args:
        chunk: A COBOLChunk produced by the chunker.

    Returns:
        True if the chunk should be indexed; False if it should be skipped.
    """
    if not chunk.content.strip():
        return False

    non_trivial = _count_non_trivial_lines(chunk.content, chunk.is_fallback)
    if non_trivial < _MIN_NON_TRIVIAL_LINES:
        return False

    return _has_logic_verb(chunk.content)


def filter_chunks(chunks: list[COBOLChunk]) -> list[COBOLChunk]:
    """
    Return only the chunks that pass the quality gate, preserving their order.

    This is the main entry point used by the embedder. Think of it like a
    conveyor belt with an inspector: chunks roll in, the inspector checks each
    one, and only the ones that pass get loaded onto the next stage.

    Args:
        chunks: All COBOLChunk objects from the chunker for a file (or batch).

    Returns:
        A new list containing only the indexable chunks, in the same order.
    """
    return [c for c in chunks if is_indexable(c)]
