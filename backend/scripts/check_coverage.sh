#!/usr/bin/env bash
# check_coverage.sh — Per-file coverage enforcement for LegacyLens backend.
#
# Why does this exist?
# The --cov-fail-under=80 flag in pyproject.toml checks the AGGREGATE total only.
# A single file at 40% can be hidden by 20 other files at 100%, giving a passing
# aggregate. This script checks EVERY file in app/ individually, so nothing hides.
#
# Think of it like a restaurant health inspection: the overall score doesn't matter
# if one section (kitchen) fails — you need to pass each section separately.
#
# Usage:
#   Run this after: pytest --cov=app (which generates the .coverage data file)
#   bash backend/scripts/check_coverage.sh
#
# Exit codes:
#   0 — all app/ files meet 80% coverage minimum
#   1 — one or more app/ files are below 80%
#
# Required: Run from the Week3/backend/ directory, with the .venv activated
#   or with COVERAGE_BIN set to the coverage binary path.

set -euo pipefail

THRESHOLD=80
# Use the venv's coverage binary if available, otherwise fall back to PATH
if [ -f "$(dirname "$0")/../.venv/bin/coverage" ]; then
    COVERAGE_BIN="$(dirname "$0")/../.venv/bin/coverage"
else
    COVERAGE_BIN="${COVERAGE_BIN:-coverage}"
fi
REPORT_FILE="/tmp/legacylens_coverage_report.json"

# Export the .coverage data file to JSON for per-file inspection
"$COVERAGE_BIN" json -o "$REPORT_FILE" --quiet

# Detect Python — prefer the venv Python for consistency
if [ -f "$(dirname "$0")/../.venv/bin/python3" ]; then
    PYTHON_BIN="$(dirname "$0")/../.venv/bin/python3"
else
    PYTHON_BIN="python3"
fi

# Parse per-file results and fail if any app/ file is below threshold
"$PYTHON_BIN" - << 'PYEOF'
import json
import sys

THRESHOLD = 80
REPORT_FILE = "/tmp/legacylens_coverage_report.json"

with open(REPORT_FILE) as f:
    data = json.load(f)

failed = []
for filepath, info in data["files"].items():
    # Only check files in our application code (not tests, not venv)
    # Normalize path separators for cross-platform compatibility
    normalized = filepath.replace("\\", "/")
    if "app/" not in normalized:
        continue
    # Skip __init__.py files — they're typically empty and just mark directories
    if normalized.endswith("__init__.py"):
        continue

    pct = info["summary"]["percent_covered"]
    if pct < THRESHOLD:
        failed.append((filepath, pct))

if failed:
    print(f"COVERAGE FAILURES — files below {THRESHOLD}% line coverage:")
    for path, pct in sorted(failed):
        print(f"  {path}: {pct:.1f}%")
    print()
    print(f"Each file in app/ must reach {THRESHOLD}% coverage.")
    print("Fix: add tests for the lines listed in the Missing column of pytest --cov output.")
    sys.exit(1)
else:
    print(f"All app/ files meet {THRESHOLD}% coverage minimum.")
    sys.exit(0)
PYEOF
