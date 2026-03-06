"""
Deployed API golden-query evaluator for LegacyLens.

This runner validates real production behavior by calling the deployed
/api/v1/query endpoint (SSE) instead of querying Pinecone directly.
It computes Precision@5, captures per-query failure modes and reasons,
and summarizes latency from the "done" SSE payload.

Authentication:
    NEXTAUTH_SECRET is read from the NEXTAUTH_SECRET environment variable.
    Pass --nextauth-secret only to override (e.g. for one-off local runs).
    Never put the secret in shell history via --nextauth-secret in CI.

Intended usage:
    cd backend
    NEXTAUTH_SECRET=<secret> python scripts/evaluate_deployed.py \\
        --backend-url https://your-app.up.railway.app
"""

from __future__ import annotations

import asyncio
import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from jose import jwt

# Ensure `backend/` is on sys.path so `scripts.eval_shared` is importable whether
# this file is run as `python scripts/evaluate_deployed.py` or `python -m scripts.evaluate_deployed`.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from scripts.eval_shared import (
    FailureMode,
    GoldenQuery,
    classify_result,
    load_golden_queries,
)

TOP_K = 5
FIXTURE_PATH = Path("tests/fixtures/golden_queries.json")
DEFAULT_RESULTS_DIR = Path("eval_results")
TARGET_PRECISION = 0.70
TARGET_LATENCY_MS = 3000
JWT_ALGORITHM = "HS256"
SCORE_METRIC = "combined_score"
SCORE_METRIC_FORMULA = "0.7*cosine + 0.3*keyword_overlap"


@dataclass
class Snippet:
    """Top-k snippet returned by the deployed query endpoint."""

    file_path: str
    paragraph_name: str
    score: float


@dataclass
class QueryEvalResult:
    """Evaluation result for one golden query."""

    id: str
    query: str
    category: str
    passed: bool
    threshold: float
    matched_score: float | None
    top_score: float
    top_file_path: str | None
    failure_mode: str
    reason: str
    query_time_ms: float | None
    request_wall_time_ms: float


def _build_bearer_token(nextauth_secret: str) -> str:
    """Create a short-lived JWT accepted by backend NextAuth token validator."""
    now = datetime.now(UTC)
    payload = {
        "sub": "prod-eval-runner",
        "name": "Prod Eval Runner",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=20)).timestamp()),
    }
    return jwt.encode(payload, nextauth_secret, algorithm=JWT_ALGORITHM)


def _parse_sse(raw_text: str) -> dict[str, Any]:
    """
    Parse SSE blocks into event payloads keyed by event name.

    Splits on double-newline block boundaries, then extracts the "event:"
    and "data:" lines within each block. Only the structured events
    (snippets, done, error) are JSON-decoded; token events are stored raw.
    """
    events: dict[str, Any] = {}
    for block in raw_text.split("\n\n"):
        if not block.strip():
            continue
        event_type = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data = line[6:].strip()

        if not event_type or not data:
            continue

        if event_type in {"snippets", "done", "error"}:
            try:
                events[event_type] = json.loads(data)
            except json.JSONDecodeError:
                events[event_type] = data
        else:
            events[event_type] = data
    return events


async def _call_deployed_query(
    client: httpx.AsyncClient,
    backend_url: str,
    token: str,
    query: str,
) -> tuple[list[Snippet], dict[str, Any], str | None, float]:
    """Call deployed /api/v1/query endpoint and parse SSE response."""
    started = time.perf_counter()
    response = await client.post(
        f"{backend_url.rstrip('/')}/api/v1/query",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"query": query, "top_k": TOP_K},
    )
    wall_time_ms = (time.perf_counter() - started) * 1000.0

    response.raise_for_status()
    events = _parse_sse(response.text)

    error_payload = events.get("error")
    if error_payload:
        if isinstance(error_payload, dict):
            return [], {}, str(error_payload.get("message", "unknown error")), wall_time_ms
        return [], {}, str(error_payload), wall_time_ms

    snippets_raw = events.get("snippets", [])
    done_payload = events.get("done", {})
    snippets: list[Snippet] = []
    if isinstance(snippets_raw, list):
        for item in snippets_raw:
            if not isinstance(item, dict):
                continue
            snippets.append(
                Snippet(
                    file_path=str(item.get("file_path", "")),
                    paragraph_name=str(item.get("paragraph_name", "")),
                    score=float(item.get("score", 0.0)),
                )
            )
    return snippets, done_payload if isinstance(done_payload, dict) else {}, None, wall_time_ms


def _evaluate_one(
    golden: GoldenQuery,
    snippets: list[Snippet],
    error_message: str | None,
    query_time_ms: float | None,
    wall_ms: float,
) -> QueryEvalResult:
    """
    Evaluate a single golden query result and return a structured outcome.

    Converts API Snippet objects into the (file_path, paragraph_name, score)
    tuples that classify_result expects.
    """
    reason_map = {
        FailureMode.NO_RESULTS: "no snippets returned — check SIMILARITY_THRESHOLD in Railway env",
        FailureMode.NOT_RETRIEVED: "expected chunk not in top-5",
        FailureMode.BELOW_THRESHOLD: "expected chunk found but below threshold",
        FailureMode.PASSED: "expected chunk found and passed threshold",
    }

    if error_message is not None:
        return QueryEvalResult(
            id=golden.id,
            query=golden.query,
            category=golden.category,
            passed=False,
            threshold=golden.min_score,
            matched_score=None,
            top_score=0.0,
            top_file_path=None,
            failure_mode=FailureMode.NO_RESULTS.value,
            reason=f"endpoint_error: {error_message}",
            query_time_ms=query_time_ms,
            request_wall_time_ms=wall_ms,
        )

    top = snippets[0] if snippets else None
    top_score = float(top.score) if top else 0.0

    snippet_tuples = [(s.file_path, s.paragraph_name, s.score) for s in snippets]
    passed, matched_score, failure_mode = classify_result(golden, snippet_tuples, top_score)

    return QueryEvalResult(
        id=golden.id,
        query=golden.query,
        category=golden.category,
        passed=passed,
        threshold=golden.min_score,
        matched_score=matched_score,
        top_score=top_score,
        top_file_path=top.file_path if top else None,
        failure_mode=failure_mode.value,
        reason=reason_map[failure_mode],
        query_time_ms=query_time_ms,
        request_wall_time_ms=wall_ms,
    )


def _build_markdown_report(report: dict[str, Any]) -> str:
    """Render a markdown summary suitable for sharing evidence quickly."""
    latency = report["latency_ms"]
    lines: list[str] = [
        "# Deployed API Golden Evaluation",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Backend URL: `{report['backend_url']}`",
        f"- Score metric used: `{report['score_metric']}` "
        f"({report['score_metric_formula']})",
        f"- Top-k: `{report['top_k']}`",
        f"- Precision@5: `{report['precision_at_5']:.4f}` "
        f"({report['passed_queries']}/{report['total_queries']})",
        f"- Precision target: `{report['target_precision_at_5']:.2f}`",
        f"- Latency p50 (query_time_ms): `{latency['query_time_ms_p50']:.2f}` ms",
        f"- Latency p95 (query_time_ms): `{latency['query_time_ms_p95']:.2f}` ms",
        f"- Latency target: `< {TARGET_LATENCY_MS}` ms",
        "",
        "| ID | Pass | Matched | Threshold | Top | Query ms | Failure Mode | Reason |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for item in report["results"]:
        matched = "-" if item["matched_score"] is None else f"{item['matched_score']:.4f}"
        query_ms = "-" if item["query_time_ms"] is None else f"{item['query_time_ms']:.2f}"
        lines.append(
            f"| {item['id']} | {'PASS' if item['passed'] else 'FAIL'} | "
            f"{matched} | {item['threshold']:.2f} | {item['top_score']:.4f} | "
            f"{query_ms} | {item['failure_mode']} | {item['reason']} |"
        )
    return "\n".join(lines) + "\n"


def _percentile(values: list[float], p: float) -> float:
    """Return percentile using inclusive quantiles for small samples."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    quantiles = statistics.quantiles(ordered, n=100, method="inclusive")
    index = min(max(int(p) - 1, 0), len(quantiles) - 1)
    return quantiles[index]


async def _run_eval(backend_url: str, nextauth_secret: str, timeout_s: float) -> dict[str, Any]:
    """Run deployed API evaluation across the golden query set."""
    token = _build_bearer_token(nextauth_secret)
    golden_queries = load_golden_queries(FIXTURE_PATH)
    query_results: list[QueryEvalResult] = []

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        for golden in golden_queries:
            snippets, done_payload, error_message, wall_ms = await _call_deployed_query(
                client=client,
                backend_url=backend_url,
                token=token,
                query=golden.query,
            )
            query_time_ms = (
                float(done_payload.get("query_time_ms"))
                if isinstance(done_payload.get("query_time_ms"), (int, float))
                else None
            )
            query_results.append(
                _evaluate_one(golden, snippets, error_message, query_time_ms, wall_ms)
            )

    passed_queries = sum(1 for result in query_results if result.passed)
    total_queries = len(query_results)
    precision_at_5 = (passed_queries / total_queries) if total_queries else 0.0
    query_time_values = [
        float(result.query_time_ms)
        for result in query_results
        if result.query_time_ms is not None
    ]
    wall_values = [float(result.request_wall_time_ms) for result in query_results]

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "backend_url": backend_url,
        "score_metric": SCORE_METRIC,
        "score_metric_formula": SCORE_METRIC_FORMULA,
        "top_k": TOP_K,
        "total_queries": total_queries,
        "passed_queries": passed_queries,
        "precision_at_5": round(precision_at_5, 4),
        "target_precision_at_5": TARGET_PRECISION,
        "latency_target_ms": TARGET_LATENCY_MS,
        "latency_ms": {
            "query_time_ms_p50": round(statistics.median(query_time_values), 2)
            if query_time_values
            else 0.0,
            "query_time_ms_p95": round(_percentile(query_time_values, 95), 2)
            if query_time_values
            else 0.0,
            "request_wall_time_ms_p50": round(statistics.median(wall_values), 2)
            if wall_values
            else 0.0,
            "request_wall_time_ms_p95": round(_percentile(wall_values, 95), 2)
            if wall_values
            else 0.0,
        },
        "results": [asdict(result) for result in query_results],
    }


def _make_output_path(cli_path: str | None) -> Path:
    """Build output path, defaulting to timestamped report under eval_results/."""
    if cli_path:
        return Path(cli_path)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_RESULTS_DIR / f"deployed_eval_{stamp}.json"


def _resolve_nextauth_secret(cli_value: str | None) -> str:
    """
    Resolve the NEXTAUTH_SECRET from environment or CLI override.

    Prefer the environment variable so the secret never appears in shell
    history or process listings. The CLI arg is accepted as a fallback for
    local one-off runs only — never use it in CI.

    Args:
        cli_value: Value from --nextauth-secret, or None if not provided.

    Returns:
        The resolved secret string.

    Raises:
        SystemExit: If neither the env var nor the CLI arg is set.
    """
    secret = os.environ.get("NEXTAUTH_SECRET", "").strip() or (cli_value or "").strip()
    if not secret:
        raise SystemExit(
            "Error: NEXTAUTH_SECRET is required.\n"
            "Set it via the environment variable:\n"
            "  export NEXTAUTH_SECRET=<your-secret>\n"
            "Or pass --nextauth-secret (not recommended — leaks into shell history)."
        )
    return secret


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Run deployed API golden query eval.")
    parser.add_argument(
        "--backend-url",
        type=str,
        required=True,
        help="Deployed backend base URL (e.g. https://your-app.up.railway.app)",
    )
    parser.add_argument(
        "--nextauth-secret",
        type=str,
        default=None,
        help=(
            "NEXTAUTH_SECRET override (optional — prefer setting the "
            "NEXTAUTH_SECRET env var instead to avoid shell history leakage)."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="HTTP timeout for each deployed query request.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Path to write JSON report "
            "(default: eval_results/deployed_eval_<timestamp>.json)"
        ),
    )
    parser.add_argument(
        "--markdown-output",
        type=str,
        default=None,
        help="Optional path to write markdown summary report.",
    )
    args = parser.parse_args()

    nextauth_secret = _resolve_nextauth_secret(args.nextauth_secret)

    report = asyncio.run(
        _run_eval(
            backend_url=args.backend_url,
            nextauth_secret=nextauth_secret,
            timeout_s=args.timeout_seconds,
        )
    )

    output_path = _make_output_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    markdown = _build_markdown_report(report)
    if args.markdown_output:
        md_path = Path(args.markdown_output)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    print(f"JSON report written to: {output_path}")


if __name__ == "__main__":
    main()
