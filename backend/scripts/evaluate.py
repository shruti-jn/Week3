"""
Golden-query evaluation runner for LegacyLens retrieval quality.

This script runs the fixed golden query set against the live retrieval stack:
1) Embed each query with voyage-code-2
2) Retrieve top-5 chunks from Pinecone
3) Check whether the expected file/paragraph appears with enough score
4) Compute Precision@5 and write a JSON + Markdown report

Intended usage:
    python scripts/evaluate.py

CI usage:
    python scripts/evaluate.py --output eval_results/ci_latest.json \
      --markdown-output eval_results/ci_summary.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import voyageai
from pinecone import Pinecone

# Ensure `backend/` is on sys.path so `scripts.eval_shared` is importable whether
# this file is run as `python scripts/evaluate.py` or `python -m scripts.evaluate`.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.ingestion.embedder import embed_query
from app.core.retrieval.pinecone_client import PineconeWrapper
from app.core.retrieval.reranker import RankedResult, rerank
from scripts.eval_shared import (
    FailureMode,
    GoldenQuery,
    classify_result,
    load_golden_queries,
)

TOP_K = 5
FIXTURE_PATH = Path("tests/fixtures/golden_queries.json")
DEFAULT_RESULTS_DIR = Path("eval_results")
DEFAULT_SIMILARITY_THRESHOLD = 0.65
SCORE_METRIC = "combined_score"
SCORE_METRIC_FORMULA = "0.7*cosine + 0.3*keyword_overlap"


@dataclass
class QueryEvalResult:
    """Evaluation outcome for a single golden query."""

    id: str
    query: str
    category: str
    passed: bool
    threshold: float
    matched_score: float | None
    top_score: float
    top_chunk_id: str | None
    top_file_path: str | None
    failure_mode: str
    reason: str


def _evaluate_one(golden: GoldenQuery, ranked_results: list[RankedResult]) -> QueryEvalResult:
    """
    Score one query by checking whether the expected chunk is in the top-k results.

    Converts SearchResult objects into the (file_path, paragraph_name, score)
    tuples that classify_result expects, then maps the FailureMode back to
    human-readable reason strings for the report.
    """
    top = ranked_results[0] if ranked_results else None
    top_score = float(top.combined_score) if top else 0.0

    snippets = [
        (
            str(r.metadata.get("file_path", "")),
            str(r.metadata.get("paragraph_name", "")),
            float(r.combined_score),
        )
        for r in ranked_results
    ]

    passed, matched_score, failure_mode = classify_result(golden, snippets, top_score)

    reason_map = {
        FailureMode.NO_RESULTS: "no snippets returned — check SIMILARITY_THRESHOLD in Railway env",
        FailureMode.NOT_RETRIEVED: "expected chunk not in top-5",
        FailureMode.BELOW_THRESHOLD: "expected chunk found but below threshold",
        FailureMode.PASSED: "expected chunk found and passed threshold",
    }

    return QueryEvalResult(
        id=golden.id,
        query=golden.query,
        category=golden.category,
        passed=passed,
        threshold=golden.min_score,
        matched_score=matched_score,
        top_score=top_score,
        top_chunk_id=top.chunk_id if top else None,
        top_file_path=str(top.metadata.get("file_path", "")) if top else None,
        failure_mode=failure_mode.value,
        reason=reason_map[failure_mode],
    )


async def _run_eval() -> dict[str, Any]:
    """Execute the full golden set evaluation against live Voyage + Pinecone."""
    voyage_api_key = os.environ.get("VOYAGE_API_KEY", "").strip()
    pinecone_api_key = os.environ.get("PINECONE_API_KEY", "").strip()
    pinecone_index_name = os.environ.get("PINECONE_INDEX_NAME", "").strip()

    if not voyage_api_key:
        raise RuntimeError("Missing VOYAGE_API_KEY for Voyage-only golden eval.")
    if not pinecone_api_key:
        raise RuntimeError("Missing PINECONE_API_KEY for Voyage-only golden eval.")
    if not pinecone_index_name:
        raise RuntimeError("Missing PINECONE_INDEX_NAME for Voyage-only golden eval.")

    voyage_client = voyageai.Client(api_key=voyage_api_key)  # type: ignore[attr-defined]  # no stubs
    pinecone_client = Pinecone(api_key=pinecone_api_key)
    wrapper = PineconeWrapper(pinecone_client, pinecone_index_name)
    similarity_threshold = float(
        os.environ.get("SIMILARITY_THRESHOLD", str(DEFAULT_SIMILARITY_THRESHOLD))
    )

    golden_queries = load_golden_queries(FIXTURE_PATH)
    query_results: list[QueryEvalResult] = []

    for golden in golden_queries:
        query_embedding = await embed_query(golden.query, voyage_client)
        retrieved = await wrapper.query(
            query_embedding,
            top_k=TOP_K,
            min_score=similarity_threshold,
        )
        ranked = rerank(
            query=golden.query,
            candidates=retrieved,
            top_k=TOP_K,
            min_score=similarity_threshold,
        )
        query_results.append(_evaluate_one(golden, ranked))

    passed = sum(1 for result in query_results if result.passed)
    total = len(query_results)
    precision_at_5 = (passed / total) if total else 0.0

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "index_name": pinecone_index_name,
        "embedding_model": "voyage-code-2",
        "score_metric": SCORE_METRIC,
        "score_metric_formula": SCORE_METRIC_FORMULA,
        "similarity_threshold": similarity_threshold,
        "top_k": TOP_K,
        "total_queries": total,
        "passed_queries": passed,
        "precision_at_5": round(precision_at_5, 4),
        "target_precision_at_5": 0.70,
        "results": [asdict(result) for result in query_results],
    }


def _build_markdown_report(report: dict[str, Any]) -> str:
    """Render a compact markdown summary suitable for CI step summaries."""
    lines: list[str] = []
    lines.append("# Golden Query Evaluation")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Index: `{report['index_name']}`")
    lines.append(f"- Embedding model used: `{report['embedding_model']}`")
    lines.append(
        f"- Score metric used: `{report['score_metric']}` "
        f"({report['score_metric_formula']})"
    )
    lines.append(f"- Similarity threshold: `{report['similarity_threshold']:.2f}`")
    lines.append(f"- Top-k: `{report['top_k']}`")
    lines.append(
        f"- Precision@5: `{report['precision_at_5']:.4f}` "
        f"({report['passed_queries']}/{report['total_queries']})"
    )
    lines.append(f"- Target: `{report['target_precision_at_5']:.2f}`")
    lines.append("")
    lines.append("| Query | Pass | Matched | Threshold | Top | Failure Mode | Reason |")
    lines.append("|---|---|---:|---:|---:|---|---|")

    for item in report["results"]:
        matched_score = (
            f"{item['matched_score']:.4f}" if item["matched_score"] is not None else "-"
        )
        pass_mark = "PASS" if item["passed"] else "FAIL"
        lines.append(
            f"| {item['query']} | {pass_mark} | {matched_score} | "
            f"{item['threshold']:.2f} | {item['top_score']:.4f} | "
            f"{item['failure_mode']} | {item['reason']} |"
        )

    return "\n".join(lines) + "\n"


def _make_output_path(cli_path: str | None) -> Path:
    """
    Build the JSON output path.

    If caller did not provide --output, we create a timestamped filename under
    backend/eval_results/.
    """
    if cli_path:
        return Path(cli_path)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_RESULTS_DIR / f"golden_eval_{stamp}.json"


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Run LegacyLens golden query eval.")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Path to write JSON report "
            "(default: eval_results/golden_eval_<timestamp>.json)"
        ),
    )
    parser.add_argument(
        "--markdown-output",
        type=str,
        default=None,
        help="Optional path to write markdown summary report.",
    )
    args = parser.parse_args()

    report = asyncio.run(_run_eval())

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
