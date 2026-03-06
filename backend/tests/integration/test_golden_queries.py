"""
Integration test: deployed API golden query Precision@5 gate.

This test calls the real deployed API and asserts that retrieval quality
meets the 70% Precision@5 target. It is marked `integration` so it is
excluded from the fast unit test suite and only runs in CI or manually.

Usage:
    # Requires live backend + env vars
    export BACKEND_URL=https://week3-production-e652.up.railway.app
    export NEXTAUTH_SECRET=<your-secret>
    backend/.venv/bin/pytest -m integration tests/integration/test_golden_queries.py -v -s --no-cov

    # --no-cov is required because this test calls a remote API — no local app/
    # code runs, so the coverage gate would report 0% and fail independently.

Environment variables:
    BACKEND_URL       — deployed backend base URL (required)
    NEXTAUTH_SECRET   — JWT signing secret shared with backend (required)
    EVAL_TIMEOUT_S    — per-request timeout in seconds (default: 60)
"""

from __future__ import annotations

import asyncio
import os

import pytest

from scripts.eval_shared import FailureMode

TARGET_PRECISION = 0.70
DEFAULT_TIMEOUT_S = 60.0


def _get_required_env(name: str) -> str:
    """Retrieve a required environment variable or skip the test with a clear message."""
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"Skipping: {name} environment variable is not set.")
    return value


@pytest.mark.integration
def test_precision_at_5_meets_target() -> None:
    """
    Deployed API must return the expected chunk in top-5 for ≥70% of golden queries.

    On failure the full per-query breakdown is printed so CI logs are self-explanatory
    without needing to download the JSON report artifact.
    """
    # Import here to keep the integration module isolated from unit test collection.
    from scripts.evaluate_deployed import _run_eval  # noqa: PLC0415

    backend_url = _get_required_env("BACKEND_URL")
    nextauth_secret = _get_required_env("NEXTAUTH_SECRET")
    timeout_s = float(os.environ.get("EVAL_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)))

    report = asyncio.run(
        _run_eval(
            backend_url=backend_url,
            nextauth_secret=nextauth_secret,
            timeout_s=timeout_s,
        )
    )

    precision = report["precision_at_5"]
    passed = report["passed_queries"]
    total = report["total_queries"]

    # Print full per-query breakdown so failures are self-explanatory in CI logs.
    print(f"\nPrecision@5: {precision:.4f} ({passed}/{total}) — target {TARGET_PRECISION:.2f}")
    print(
        f"{'Query':<48} {'Pass':<6} {'Matched':>8} {'Top':>7} "
        f"{'Failure Mode':<18} Reason"
    )
    print("-" * 80)
    for item in report["results"]:
        matched = "-" if item["matched_score"] is None else f"{item['matched_score']:.4f}"
        mark = "PASS" if item["passed"] else "FAIL"
        print(
            f"{item['query'][:48]:<48} {mark:<6} {matched:>8} {item['top_score']:>7.4f} "
            f"{item['failure_mode']:<18} {item['reason']}"
        )

    # Surface which failure modes are present for easier triage.
    no_results = [r for r in report["results"] if r["failure_mode"] == FailureMode.NO_RESULTS]
    not_retrieved = [
        r for r in report["results"] if r["failure_mode"] == FailureMode.NOT_RETRIEVED
    ]
    below_threshold = [
        r for r in report["results"] if r["failure_mode"] == FailureMode.BELOW_THRESHOLD
    ]

    if no_results:
        queries = ", ".join(r["query"] for r in no_results)
        print(
            f"\nno_results ({len(no_results)}): {queries} "
            "— API returned nothing; check SIMILARITY_THRESHOLD in Railway env first"
        )
    if not_retrieved:
        queries = ", ".join(r["query"] for r in not_retrieved)
        print(
            f"not_retrieved ({len(not_retrieved)}): {queries} "
            "— fix chunking/reranking; file is indexed but wrong chunk ranks higher"
        )
    if below_threshold:
        queries = ", ".join(r["query"] for r in below_threshold)
        print(
            f"below_threshold ({len(below_threshold)}): {queries} "
            "— right chunk found; consider lowering min_score or improving query phrasing"
        )

    assert precision >= TARGET_PRECISION, (
        f"Precision@5 {precision:.4f} ({passed}/{total}) is below the "
        f"{TARGET_PRECISION:.2f} target. See breakdown above."
    )
