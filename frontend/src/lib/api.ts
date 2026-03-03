/**
 * API client for the LegacyLens FastAPI backend.
 *
 * Think of this file as the "phone book" for all network calls in the app.
 * Every fetch to the backend goes through this module — never raw fetch() inline
 * in components. This keeps all HTTP logic in one place, easy to update.
 *
 * Two public functions:
 * - getAuthToken():  asks our own Next.js server for the signed JWT
 * - searchQuery():   sends a question to FastAPI and gets back ranked COBOL snippets
 */

import type { QueryResponse } from "../types/api";

/** Base URL of the FastAPI backend. Falls back to localhost for local dev. */
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Fetch the NextAuth-signed JWT from our own Next.js token endpoint.
 *
 * The FastAPI backend validates this token (not the raw GitHub OAuth token)
 * using the NEXTAUTH_SECRET environment variable. We need it to prove the
 * user is logged in when we call the backend.
 *
 * Returns:
 *   The JWT string, ready to use in an Authorization header.
 *
 * Raises:
 *   Error: If the token endpoint returns a non-2xx status.
 */
export async function getAuthToken(): Promise<string> {
  const response = await fetch("/api/auth/token");

  if (!response.ok) {
    throw new Error(`Failed to fetch auth token: ${response.status}`);
  }

  const data = (await response.json()) as { token: string };
  return data.token;
}

/**
 * Submit a plain-English question about the COBOL codebase and get back
 * ranked code snippets with a GPT-4o-mini generated answer.
 *
 * Like a search engine for legacy code: you ask "how does payroll tax work?"
 * and it returns the exact COBOL paragraphs that implement it, plus an
 * English explanation of what the code does.
 *
 * Args:
 *   query:  The user's plain-English question.
 *   top_k:  How many COBOL snippets to retrieve (default 5). More = richer
 *           context for the LLM, but slower response.
 *
 * Returns:
 *   QueryResponse with the generated answer, ranked code snippets, and timing.
 *
 * Raises:
 *   Error: If the auth token fetch fails or the query endpoint returns non-2xx.
 */
export async function searchQuery(
  query: string,
  top_k: number = 5
): Promise<QueryResponse> {
  const token = await getAuthToken();

  const response = await fetch(`${API_BASE}/api/v1/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ query, top_k }),
  });

  if (!response.ok) {
    throw new Error(`Query failed: ${response.status}`);
  }

  return (await response.json()) as QueryResponse;
}
