"""
Unit tests for the COBOL file scanner module.

The file scanner is responsible for finding all .cob and .cbl files
in a directory tree and returning metadata about each one.

Think of it like 'find . -name "*.cob"' but returning Python objects
with file size, line count, and path instead of just the file path.

All tests use pytest's tmp_path fixture which creates a temporary directory
that is automatically cleaned up after the test. No real COBOL files needed.
"""

from pathlib import Path

import pytest

from app.core.ingestion.file_scanner import COBOLFile, scan_directory


# ─────────────────────────────────────────────────────────────────────────────
# Happy path tests
# ─────────────────────────────────────────────────────────────────────────────


def test_finds_cob_files(tmp_path: Path) -> None:
    """Happy path: scanner finds .cob files in a flat directory."""
    (tmp_path / "payroll.cob").write_text("IDENTIFICATION DIVISION.\nPROGRAM-ID. PAY.\n")
    (tmp_path / "loans.cob").write_text("IDENTIFICATION DIVISION.\nPROGRAM-ID. LOANS.\n")

    results = scan_directory(tmp_path)

    assert len(results) == 2
    names = {r.path.name for r in results}
    assert names == {"payroll.cob", "loans.cob"}


def test_finds_cbl_files(tmp_path: Path) -> None:
    """Scanner finds .cbl files (alternate COBOL extension)."""
    (tmp_path / "inventory.cbl").write_text("IDENTIFICATION DIVISION.\n")

    results = scan_directory(tmp_path)

    assert len(results) == 1
    assert results[0].extension == ".cbl"


def test_finds_mixed_extensions(tmp_path: Path) -> None:
    """Scanner finds both .cob and .cbl files together."""
    (tmp_path / "a.cob").write_text("COBOL content\n")
    (tmp_path / "b.cbl").write_text("COBOL content\n")

    results = scan_directory(tmp_path)

    assert len(results) == 2
    extensions = {r.extension for r in results}
    assert extensions == {".cob", ".cbl"}


def test_finds_nested_files(tmp_path: Path) -> None:
    """Scanner recurses into subdirectories to find all COBOL files."""
    sub = tmp_path / "programs" / "payroll"
    sub.mkdir(parents=True)
    (sub / "payroll.cob").write_text("IDENTIFICATION DIVISION.\n")
    (tmp_path / "top-level.cob").write_text("IDENTIFICATION DIVISION.\n")

    results = scan_directory(tmp_path)

    assert len(results) == 2


def test_returns_correct_line_count(tmp_path: Path) -> None:
    """COBOLFile.line_count is the number of lines in the file."""
    content = "IDENTIFICATION DIVISION.\nPROGRAM-ID. TEST.\nDATA DIVISION.\n"
    (tmp_path / "test.cob").write_text(content)

    results = scan_directory(tmp_path)

    assert results[0].line_count == 3


def test_returns_correct_size_bytes(tmp_path: Path) -> None:
    """COBOLFile.size_bytes matches the actual file size."""
    content = "IDENTIFICATION DIVISION.\n"
    (tmp_path / "test.cob").write_bytes(content.encode("utf-8"))

    results = scan_directory(tmp_path)

    assert results[0].size_bytes == len(content.encode("utf-8"))


def test_returns_absolute_path(tmp_path: Path) -> None:
    """COBOLFile.path is an absolute Path object, not a relative string."""
    (tmp_path / "test.cob").write_text("content\n")

    results = scan_directory(tmp_path)

    assert results[0].path.is_absolute()


def test_results_sorted_by_path(tmp_path: Path) -> None:
    """Results are sorted by file path for deterministic ordering."""
    (tmp_path / "zebra.cob").write_text("content\n")
    (tmp_path / "alpha.cob").write_text("content\n")
    (tmp_path / "middle.cob").write_text("content\n")

    results = scan_directory(tmp_path)

    names = [r.path.name for r in results]
    assert names == sorted(names)


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_directory(tmp_path: Path) -> None:
    """Empty directory returns empty list, not an error."""
    results = scan_directory(tmp_path)
    assert results == []


def test_no_cobol_files(tmp_path: Path) -> None:
    """Directory with only non-COBOL files returns empty list."""
    (tmp_path / "readme.txt").write_text("This is a text file\n")
    (tmp_path / "script.sh").write_text("#!/bin/bash\n")
    (tmp_path / "data.json").write_text("{}\n")

    results = scan_directory(tmp_path)

    assert results == []


def test_ignores_python_and_other_files(tmp_path: Path) -> None:
    """Scanner only returns COBOL files, ignoring everything else."""
    (tmp_path / "payroll.cob").write_text("IDENTIFICATION DIVISION.\n")
    (tmp_path / "helper.py").write_text("print('helper')\n")
    (tmp_path / "notes.txt").write_text("some notes\n")

    results = scan_directory(tmp_path)

    assert len(results) == 1
    assert results[0].path.name == "payroll.cob"


def test_single_file(tmp_path: Path) -> None:
    """Single .cob file — the boundary condition for minimum valid input."""
    (tmp_path / "only.cob").write_text("IDENTIFICATION DIVISION.\n")

    results = scan_directory(tmp_path)

    assert len(results) == 1
    assert results[0].path.name == "only.cob"


def test_case_insensitive_extension_cob(tmp_path: Path) -> None:
    """Uppercase .COB extension should be found (COBOL files on Windows often use uppercase)."""
    (tmp_path / "PAYROLL.COB").write_text("IDENTIFICATION DIVISION.\n")

    results = scan_directory(tmp_path)

    assert len(results) == 1


def test_case_insensitive_extension_cbl(tmp_path: Path) -> None:
    """Uppercase .CBL extension should be found."""
    (tmp_path / "INVENTORY.CBL").write_text("IDENTIFICATION DIVISION.\n")

    results = scan_directory(tmp_path)

    assert len(results) == 1


def test_large_directory(tmp_path: Path) -> None:
    """Scanner handles a large number of files without crashing."""
    for i in range(200):
        (tmp_path / f"prog_{i:04d}.cob").write_text(f"PROGRAM-ID. PROG{i}.\n")

    results = scan_directory(tmp_path)

    assert len(results) == 200


def test_deeply_nested_directory(tmp_path: Path) -> None:
    """Scanner recurses through deeply nested directory structures (5 levels)."""
    deep = tmp_path / "a" / "b" / "c" / "d" / "e"
    deep.mkdir(parents=True)
    (deep / "deep.cob").write_text("IDENTIFICATION DIVISION.\n")

    results = scan_directory(tmp_path)

    assert len(results) == 1
    assert results[0].path.name == "deep.cob"


def test_empty_cobol_file(tmp_path: Path) -> None:
    """An empty .cob file (0 bytes) is valid — scanner includes it."""
    (tmp_path / "empty.cob").write_text("")

    results = scan_directory(tmp_path)

    assert len(results) == 1
    assert results[0].line_count == 0
    assert results[0].size_bytes == 0


def test_nonexistent_directory_raises(tmp_path: Path) -> None:
    """Scanner raises ValueError when given a path that doesn't exist."""
    bad_path = tmp_path / "does_not_exist"

    with pytest.raises((ValueError, OSError)):
        scan_directory(bad_path)


def test_file_path_given_instead_of_directory(tmp_path: Path) -> None:
    """Scanner raises ValueError when given a file path instead of a directory."""
    file_path = tmp_path / "test.cob"
    file_path.write_text("content\n")

    with pytest.raises((ValueError, OSError)):
        scan_directory(file_path)


# ─────────────────────────────────────────────────────────────────────────────
# COBOLFile dataclass tests
# ─────────────────────────────────────────────────────────────────────────────


def test_cobol_file_dataclass_fields(tmp_path: Path) -> None:
    """COBOLFile has all expected fields with correct types."""
    (tmp_path / "test.cob").write_text("IDENTIFICATION DIVISION.\n")

    results = scan_directory(tmp_path)
    f = results[0]

    assert isinstance(f.path, Path)
    assert isinstance(f.size_bytes, int)
    assert isinstance(f.line_count, int)
    assert isinstance(f.extension, str)


def test_cobol_file_extension_includes_dot(tmp_path: Path) -> None:
    """COBOLFile.extension includes the dot (e.g., '.cob', not 'cob')."""
    (tmp_path / "test.cob").write_text("IDENTIFICATION DIVISION.\n")

    results = scan_directory(tmp_path)

    assert results[0].extension.startswith(".")
