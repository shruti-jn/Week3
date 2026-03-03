# ─────────────────────────────────────────────────────────────────────────────
# LegacyLens Frontend — Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Builds a local development image for the Next.js frontend.
#
# Used by: docker compose up  (local development only)
#
# NOTE: Production deploys to Vercel (not this Dockerfile).
#       Vercel has its own build pipeline that runs "npm run build" automatically.
#       See frontend/vercel.json for Vercel configuration.
#
# How docker-compose uses this:
#   - The source code is mounted as a volume (./frontend:/app)
#   - node_modules and .next stay inside the container (not overwritten by mount)
#   - "npm run dev" gives hot-reload: code changes appear without rebuilding
#
# Build context: ./frontend/ directory (set in docker-compose.yml)
# ─────────────────────────────────────────────────────────────────────────────

FROM node:20-alpine

# Install curl for health checks and basic networking utilities.
# Alpine uses apk instead of apt-get.
RUN apk add --no-cache curl

WORKDIR /app

# Copy package files before source code.
# Docker caches this layer: npm ci only reruns when package.json or
# package-lock.json changes — not when source files change.
COPY package.json package-lock.json ./

# npm ci installs exactly what's in package-lock.json (reproducible).
# Unlike npm install, it never upgrades packages or modifies lock files.
# We include devDependencies because they're needed for "next dev" (TypeScript
# compilation, ESLint, etc. run during the dev server).
RUN npm ci

# Copy remaining source files.
# In docker-compose, this COPY is overridden by the volume mount,
# so source changes are live without rebuilding.
COPY . .

# Disable Next.js telemetry (anonymous usage stats sent to Vercel).
# Not strictly required, but avoids network calls during dev.
ENV NEXT_TELEMETRY_DISABLED=1

# The port Next.js listens on.
ENV PORT=3000

# Document the port so docker-compose and developers know where to connect.
EXPOSE 3000

# Start the development server with hot module replacement (HMR).
# Code changes in the mounted volume appear in the browser instantly.
CMD ["npm", "run", "dev"]
