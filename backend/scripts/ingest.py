"""
ingest.py — CLI script to index all COBOL files into Pinecone.

This is the "load data" step that makes LegacyLens useful.
Without running this, the Pinecone index is empty and every
user query returns nothing.

Think of it like loading books into a library:
- scan_directory() finds all the COBOL "books"
- chunk_cobol_file() splits each book into chapters (paragraphs)
- embed_and_upsert() translates each chapter into a searchable
  fingerprint and stores it in the Pinecone "card catalog"

Usage (run from the backend/ directory):
    ../backend/.venv/bin/python scripts/ingest.py ../data/gnucobol-contrib

Or using the venv directly:
    cd /Users/shruti/Week3
    backend/.venv/bin/python backend/scripts/ingest.py data/gnucobol-contrib

Environment variables required (loaded from backend/.env):
    VOYAGE_API_KEY        — used to generate embeddings (voyage-code-2)
    PINECONE_API_KEY      — used to store vectors
    PINECONE_INDEX_NAME   — Pinecone index to write to (default: legacylens)
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

import voyageai
from pinecone import Pinecone, ServerlessSpec

# All app imports use the Settings from config.py, which reads from .env.
# Run this script from the backend/ directory so Python resolves "app.*" correctly
# and config.py finds "backend/.env".
from app.config import get_settings
from app.core.ingestion.chunker import chunk_cobol_file
from app.core.ingestion.embedder import EMBEDDING_DIMENSIONS, embed_and_upsert
from app.core.ingestion.file_scanner import scan_directory
from app.core.retrieval.pinecone_client import PineconeWrapper

# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest")

# Suppress noisy httpx / voyageai / pinecone transport logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("voyageai").setLevel(logging.WARNING)
logging.getLogger("pinecone").setLevel(logging.WARNING)


# ─────────────────────────────────────────────────────────────────────────────
# Main ingestion pipeline
# ─────────────────────────────────────────────────────────────────────────────


def _ensure_index_exists(pinecone_client: Pinecone, index_name: str) -> None:
    """
    Create the Pinecone index if it doesn't already exist.

    voyage-code-2 produces EMBEDDING_DIMENSIONS-dimensional vectors (1536).
    We use cosine similarity (standard for semantic search).
    Serverless on AWS us-east-1 is the Pinecone free-tier region.

    This is idempotent — safe to call even if the index already exists.

    Args:
        pinecone_client: Authenticated Pinecone client.
        index_name:      Name of the index to create (e.g., "legacylens").
    """
    existing = [idx.name for idx in pinecone_client.list_indexes()]
    if index_name in existing:
        logger.info("Pinecone index '%s' already exists — skipping creation.", index_name)
        return

    logger.info(
        "Creating Pinecone index '%s' (dim=%d, metric=cosine, serverless us-east-1) …",
        index_name,
        EMBEDDING_DIMENSIONS,
    )
    pinecone_client.create_index(
        name=index_name,
        dimension=EMBEDDING_DIMENSIONS,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )

    # Wait for the index to be ready before trying to connect to it
    logger.info("Waiting for index to become ready …")
    while True:
        status = pinecone_client.describe_index(index_name).status
        if status.get("ready"):
            break
        time.sleep(2)

    logger.info("Index '%s' is ready.", index_name)


async def ingest_all(cobol_root: Path) -> None:
    """
    Run the full LegacyLens ingestion pipeline against a directory of COBOL files.

    Pipeline steps:
      1. Validate the target directory exists
      2. Load settings (API keys) from .env
      3. Scan the directory for .cob / .cbl files
      4. For each file: chunk → embed → upsert into Pinecone
      5. Print a summary with total files, chunks, and vectors stored

    Args:
        cobol_root: Path to the directory containing COBOL source files.
                    Can contain subdirectories — scan_directory() is recursive.

    Raises:
        SystemExit: If the directory doesn't exist or if settings are missing.
    """
    if not cobol_root.is_dir():
        logger.error("Directory not found: %s", cobol_root)
        sys.exit(1)

    # ── Load settings (reads from backend/.env) ───────────────────────────
    logger.info("Loading settings from .env …")
    settings = get_settings()

    # ── Build API clients ─────────────────────────────────────────────────
    # voyage_client: Voyage AI voyage-code-2 generates code-aware embeddings.
    # OpenAI is no longer needed for ingestion — only GPT-4o-mini (query path) uses it.
    voyage_client = voyageai.Client(api_key=settings.voyage_api_key)
    pinecone_client = Pinecone(api_key=settings.pinecone_api_key)

    # ── Create Pinecone index if it doesn't exist yet ─────────────────────
    # voyage-code-2 produces 1536-dimensional vectors.
    # Serverless on AWS us-east-1 is the free-tier / lowest-cost option.
    _ensure_index_exists(pinecone_client, settings.pinecone_index_name)

    wrapper = PineconeWrapper(pinecone_client, settings.pinecone_index_name)

    logger.info(
        "Connected → Voyage model: voyage-code-2 (%d dims) | "
        "Pinecone index: %s",
        EMBEDDING_DIMENSIONS,
        settings.pinecone_index_name,
    )

    # ── Step 1: Scan for COBOL files ──────────────────────────────────────
    logger.info("Scanning %s …", cobol_root)
    cobol_files = scan_directory(cobol_root)

    if not cobol_files:
        logger.warning("No .cob or .cbl files found in %s — nothing to index.", cobol_root)
        return

    logger.info("Found %d COBOL files to process.", len(cobol_files))

    # ── Step 2: Chunk → Embed → Upsert for each file ──────────────────────
    total_files_ok = 0
    total_files_err = 0
    total_chunks = 0
    total_vectors = 0
    start_time = time.monotonic()

    for idx, file_info in enumerate(cobol_files, start=1):
        try:
            content = file_info.path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("[%d/%d] SKIP (read error): %s — %s", idx, len(cobol_files), file_info.path, exc)
            total_files_err += 1
            continue

        # Chunk the file into paragraph-level (or fallback) segments
        chunks = chunk_cobol_file(file_info.path, content)

        if not chunks:
            logger.debug("[%d/%d] SKIP (0 chunks): %s", idx, len(cobol_files), file_info.path)
            total_files_err += 1
            continue

        # Embed chunks via Voyage AI and upsert to Pinecone
        try:
            upserted = await embed_and_upsert(chunks, voyage_client, wrapper)
        except Exception as exc:  # log and continue so one bad file doesn't abort the run
            logger.error(
                "[%d/%d] ERROR embedding %s: %s",
                idx,
                len(cobol_files),
                file_info.path.name,
                exc,
            )
            total_files_err += 1
            continue

        total_files_ok += 1
        total_chunks += len(chunks)
        total_vectors += upserted

        logger.info(
            "[%d/%d] ✓ %s — %d chunks → %d vectors",
            idx,
            len(cobol_files),
            file_info.path.name,
            len(chunks),
            upserted,
        )

    # ── Summary ───────────────────────────────────────────────────────────
    elapsed = time.monotonic() - start_time
    logger.info("─" * 60)
    logger.info("Ingestion complete in %.1fs", elapsed)
    logger.info("  Files processed: %d OK, %d skipped/errors", total_files_ok, total_files_err)
    logger.info("  Total chunks:    %d", total_chunks)
    logger.info("  Total vectors:   %d stored in Pinecone", total_vectors)
    logger.info("─" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """
    Parse command-line arguments and kick off the ingestion pipeline.

    Usage:
        python scripts/ingest.py <path/to/cobol/directory>

    Example:
        python scripts/ingest.py ../data/gnucobol-contrib
    """
    if len(sys.argv) != 2:
        print("Usage: python scripts/ingest.py <path/to/cobol/directory>")
        print("Example: python scripts/ingest.py ../data/gnucobol-contrib")
        sys.exit(1)

    cobol_root = Path(sys.argv[1]).resolve()
    asyncio.run(ingest_all(cobol_root))


if __name__ == "__main__":
    main()
