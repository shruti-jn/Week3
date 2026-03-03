# ─────────────────────────────────────────────────────────────────────────────
# LegacyLens Backend — Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Builds a production-ready Python image for the FastAPI backend.
#
# Used by:
#   - docker compose up  (local development, build context: ./backend/)
#   - Railway            (production, build context: backend/ via railway.toml)
#
# Why single-stage (not multi-stage)?
#   The app uses "pip install -e ." (editable install). Editable installs create
#   a path record pointing to the source directory. Copying site-packages between
#   Docker stages can be fragile with editable installs if the recorded source path
#   shifts. Single-stage avoids this entirely. Image size difference is small
#   (~30 MB) and acceptable for a backend service.
#
# Layer caching strategy:
#   Copy pyproject.toml → pip install → copy app/ source
#   Result: pip install is cached when only source code changes, not deps.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# Install curl — used by docker-compose and Railway health checks.
# --no-install-recommends skips optional packages to keep the image small.
# Combine update + install + cleanup in one RUN layer to minimize layer count.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the project descriptor FIRST, before the source code.
# Docker caches each RUN instruction as a layer. By copying pyproject.toml
# separately, the expensive "pip install" layer is reused as long as
# pyproject.toml doesn't change — even when app/ code changes.
COPY pyproject.toml ./

# Install runtime dependencies only (no pytest/mypy/ruff in production).
# --no-cache-dir reduces image size by skipping pip's local download cache.
# "pip install -e ." installs the package in editable mode:
#   - All dependencies listed in pyproject.toml are installed
#   - Python can import from app/ without adding it to PYTHONPATH manually
RUN pip install --no-cache-dir -e .

# Copy the application source code AFTER pip install.
# Code-only changes (no new dependencies) don't bust the pip cache.
COPY app/ ./app/

# Document the port the server listens on.
# Railway maps $PORT → this port. docker-compose maps 8000:8000.
EXPOSE 8000

# Start the FastAPI server with Uvicorn.
#
# --host 0.0.0.0  Bind to all network interfaces (required inside Docker).
#                 Without this, uvicorn only listens on 127.0.0.1 (loopback),
#                 which is unreachable from outside the container.
# --port 8000     Default port for docker-compose.
#                 Railway overrides this with $PORT via railway.toml startCommand.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
