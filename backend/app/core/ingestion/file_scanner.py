"""
COBOL file scanner — finds all COBOL source files in a directory tree.

Think of this like the 'find' Unix command, but smarter:
- It knows which extensions count as COBOL (.cob, .cbl, case-insensitive)
- It returns structured metadata (path, size, line count) not just file paths
- It sorts results so the same directory always returns files in the same order

This module is called first in the ingestion pipeline. Before we can
embed any COBOL code, we need a list of all the files to process.

Pipeline position:
    [file_scanner] → chunker → embedder → pinecone upsert
"""

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# COBOL source file extensions we recognize (lowercase for comparison).
# .cob is the most common; .cbl is used by IBM and some older compilers.
# We match case-insensitively so PAYROLL.COB is treated the same as payroll.cob.
_COBOL_EXTENSIONS = frozenset({".cob", ".cbl"})


@dataclass(frozen=True)
class COBOLFile:
    """
    Metadata about a single COBOL source file found on disk.

    Think of this like a library catalog card:
    it tells you where the book is (path), how long it is (line_count),
    and how big it is (size_bytes) — without actually reading the whole book.

    Attributes:
        path:       Absolute path to the COBOL source file.
        size_bytes: File size in bytes. 0 for empty files.
        line_count: Number of newline-separated lines. 0 for empty files.
        extension:  Lowercase file extension including the dot (e.g., '.cob').
    """

    path: Path
    size_bytes: int
    line_count: int
    extension: str


def scan_directory(root: Path) -> list[COBOLFile]:
    """
    Recursively scan a directory and return metadata for all COBOL files.

    Walks the entire directory tree starting at root and collects every
    file with a .cob or .cbl extension (case-insensitive). Results are
    sorted by absolute path for deterministic ordering across runs.

    Think of this like a table of contents for a COBOL codebase:
    it gives you the full list of files before processing begins.

    Args:
        root: Path to the root directory to scan. Must be an existing directory,
              not a file. Usually points to the cloned gnucobol-contrib repo.

    Returns:
        List of COBOLFile objects sorted by path. Empty list if no COBOL
        files are found. Never returns None.

    Raises:
        ValueError: If root does not exist or is not a directory.

    Example:
        files = scan_directory(Path("data/gnucobol-contrib"))
        print(f"Found {len(files)} COBOL files")
        # Found 577 COBOL files
        for f in files[:3]:
            print(f.path, f.line_count, "lines")
    """
    if not root.exists():
        msg = f"Directory does not exist: {root}"
        raise ValueError(msg)
    if not root.is_dir():
        msg = f"Path is not a directory: {root}"
        raise ValueError(msg)

    logger.info("Scanning for COBOL files in: %s", root)

    results: list[COBOLFile] = []

    # rglob("*") walks every file and directory recursively.
    # We filter to only regular files with COBOL extensions.
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue  # Skip directories and symlinks

        # Check extension case-insensitively
        # (.COB, .Cob, .cob are all valid COBOL extensions)
        if file_path.suffix.lower() not in _COBOL_EXTENSIONS:
            continue

        try:
            results.append(_build_cobol_file(file_path))
        except PermissionError:
            # Some files in a repo may not be readable (e.g., chmod 000 in tests).
            # Log a warning and continue rather than aborting the entire scan.
            logger.warning("Permission denied reading %s — skipping", file_path)
            continue

    # Sort by absolute path string for deterministic output.
    # Without sorting, the order depends on the filesystem, which varies
    # between OS and file systems (HFS+ vs ext4 vs NTFS).
    results.sort(key=lambda f: str(f.path))

    logger.info("Found %d COBOL files in %s", len(results), root)
    return results


def _build_cobol_file(file_path: Path) -> COBOLFile:
    """
    Read a file and build a COBOLFile metadata object.

    Uses an OS-level stat() call to get the byte size (no file read needed),
    then reads the file once to count lines. For files up to ~10MB this is
    fast enough. Larger files are still handled correctly but may take longer.

    Note on line_count: we count b"\\n" bytes, which matches the behavior of
    `wc -l`. A file with no trailing newline will report one fewer line than
    the number of visible text lines. This is intentional and consistent with
    standard Unix tooling behavior.

    Args:
        file_path: Absolute path to an existing COBOL source file.

    Returns:
        COBOLFile with path, size_bytes, line_count, and extension populated.
    """
    size_bytes = file_path.stat().st_size

    # Count lines by reading the file content.
    # We read as bytes and count newlines to handle any encoding without
    # raising a UnicodeDecodeError on files with unusual encodings.
    if size_bytes == 0:
        line_count = 0
    else:
        raw_bytes = file_path.read_bytes()
        # Count newlines — this matches wc -l behavior
        line_count = raw_bytes.count(b"\n")

    return COBOLFile(
        path=file_path.resolve(),
        size_bytes=size_bytes,
        line_count=line_count,
        extension=file_path.suffix.lower(),
    )
