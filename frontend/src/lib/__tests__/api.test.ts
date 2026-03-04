/**
 * Unit tests for src/lib/api.ts
 *
 * Tests the two public functions:
 * - getAuthToken(): fetches the NextAuth JWT from /api/auth/token
 * - searchQuery():  POSTs to the FastAPI /api/v1/query endpoint
 *
 * All network calls are mocked with jest — no real servers needed.
 */

import { getAuthToken, searchQuery } from "../api";
import type { QueryResponse } from "../../types/api";

// ── Test data ────────────────────────────────────────────────────────────────

const MOCK_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test";

const MOCK_QUERY_RESPONSE: QueryResponse = {
  answer: "The CALC-INTEREST paragraph computes annual interest by multiplying principal by rate.",
  snippets: [
    {
      file_path: "loans/calc.cob",
      start_line: 42,
      end_line: 58,
      content: "       CALC-INTEREST.\n           COMPUTE INTEREST = PRINCIPAL * RATE.",
      score: 0.91,
    },
  ],
  query_time_ms: 1234.5,
};

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Build a mock Response-like object for jest.spyOn(global, 'fetch'). */
function makeFetchResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response;
}

// ── getAuthToken ─────────────────────────────────────────────────────────────

describe("getAuthToken", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("returns token string from /api/auth/token", async () => {
    fetchSpy.mockResolvedValueOnce(makeFetchResponse({ token: MOCK_TOKEN }));

    const token = await getAuthToken();

    expect(token).toBe(MOCK_TOKEN);
    expect(fetchSpy).toHaveBeenCalledWith("/api/auth/token");
  });

  it("throws when the token endpoint returns a non-ok status", async () => {
    fetchSpy.mockResolvedValueOnce(makeFetchResponse({ error: "Not authenticated" }, 401));

    await expect(getAuthToken()).rejects.toThrow("Failed to fetch auth token: 401");
  });

  it("uses exactly one fetch call with no extra options", async () => {
    fetchSpy.mockResolvedValueOnce(makeFetchResponse({ token: MOCK_TOKEN }));

    await getAuthToken();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith("/api/auth/token");
  });
});

// ── searchQuery ───────────────────────────────────────────────────────────────

describe("searchQuery", () => {
  const API_BASE = "http://localhost:8000";
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = API_BASE;
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
    delete process.env.NEXT_PUBLIC_API_URL;
  });

  /** Stub both the token fetch and the query fetch. */
  function mockBothFetches(queryResponse: unknown = MOCK_QUERY_RESPONSE, queryStatus = 200): void {
    fetchSpy
      .mockResolvedValueOnce(makeFetchResponse({ token: MOCK_TOKEN })) // /api/auth/token
      .mockResolvedValueOnce(makeFetchResponse(queryResponse, queryStatus)); // /api/v1/query
  }

  it("sends a POST request to NEXT_PUBLIC_API_URL/api/v1/query", async () => {
    mockBothFetches();

    await searchQuery("how does interest get calculated?");

    const [queryUrl] = fetchSpy.mock.calls[1] as [string, RequestInit];
    expect(queryUrl).toBe(`${API_BASE}/api/v1/query`);
  });

  it("sends the Authorization Bearer token in the request header", async () => {
    mockBothFetches();

    await searchQuery("how does interest get calculated?");

    const [, queryOptions] = fetchSpy.mock.calls[1] as [string, RequestInit];
    expect((queryOptions.headers as Record<string, string>)["Authorization"]).toBe(
      `Bearer ${MOCK_TOKEN}`
    );
  });

  it("sends Content-Type application/json", async () => {
    mockBothFetches();

    await searchQuery("how does interest get calculated?");

    const [, queryOptions] = fetchSpy.mock.calls[1] as [string, RequestInit];
    expect((queryOptions.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json"
    );
  });

  it("uses POST method", async () => {
    mockBothFetches();

    await searchQuery("how does interest get calculated?");

    const [, queryOptions] = fetchSpy.mock.calls[1] as [string, RequestInit];
    expect(queryOptions.method).toBe("POST");
  });

  it("includes query and top_k in the request body", async () => {
    mockBothFetches();

    await searchQuery("how does interest get calculated?", 3);

    const [, queryOptions] = fetchSpy.mock.calls[1] as [string, RequestInit];
    const body = JSON.parse(queryOptions.body as string) as { query: string; top_k: number };
    expect(body).toEqual({ query: "how does interest get calculated?", top_k: 3 });
  });

  it("defaults to top_k of 5 when not specified", async () => {
    mockBothFetches();

    await searchQuery("how does interest get calculated?");

    const [, queryOptions] = fetchSpy.mock.calls[1] as [string, RequestInit];
    const body = JSON.parse(queryOptions.body as string) as { query: string; top_k: number };
    expect(body.top_k).toBe(5);
  });

  it("returns the parsed QueryResponse on success", async () => {
    mockBothFetches();

    const result = await searchQuery("how does interest get calculated?");

    expect(result).toEqual(MOCK_QUERY_RESPONSE);
  });

  it("throws when the query endpoint returns a non-ok status", async () => {
    fetchSpy
      .mockResolvedValueOnce(makeFetchResponse({ token: MOCK_TOKEN }))
      .mockResolvedValueOnce(makeFetchResponse({ detail: "Unauthorized" }, 401));

    await expect(searchQuery("test query")).rejects.toThrow("Query failed: 401");
  });

  it("falls back to http://localhost:8000 when NEXT_PUBLIC_API_URL is not set", async () => {
    delete process.env.NEXT_PUBLIC_API_URL;
    mockBothFetches();

    await searchQuery("test query");

    const [queryUrl] = fetchSpy.mock.calls[1] as [string, RequestInit];
    expect(queryUrl).toBe("http://localhost:8000/api/v1/query");
  });
});
