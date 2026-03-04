/**
 * API client — handles all communication with the LegacyLens FastAPI backend.
 *
 * The backend's /query endpoint returns Server-Sent Events (SSE), a streaming
 * protocol where the server pushes data as it becomes available. This is like
 * a ticker tape: the server sends results one by one as it finds them, rather
 * than making you wait for everything at once.
 *
 * SSE event order from the backend:
 *   1. "snippets" — list of matching COBOL code chunks (arrives first, fast)
 *   2. "token"    — one chunk of the GPT answer (arrives many times, streaming)
 *   3. "done"     — pipeline finished, includes query_time_ms
 *   OR
 *   1. "error"    — something went wrong (skips snippets/token/done)
 */

/** A single COBOL code snippet returned by the retrieval pipeline. */
export interface CodeSnippet {
  /** Relative path to the COBOL file (e.g., "programs/payroll.cob") */
  file_path: string;
  /** Line number where this snippet starts (1-indexed) */
  start_line: number;
  /** Line number where this snippet ends (1-indexed) */
  end_line: number;
  /** The raw COBOL source code for this snippet */
  content: string;
  /** Combined relevance score (0.0–1.0, higher = more relevant) */
  score: number;
}

/** Callbacks invoked as SSE events arrive from the backend. */
export interface StreamCallbacks {
  /** Called once when the code snippets are retrieved from Pinecone. */
  onSnippets: (snippets: CodeSnippet[]) => void;
  /** Called for each streaming token of the GPT answer. */
  onToken: (token: string) => void;
  /** Called when the full answer has been streamed. */
  onDone: (queryTimeMs: number) => void;
  /** Called if the backend pipeline fails. */
  onError: (message: string) => void;
}

/**
 * streamQuery — sends a query to the backend and streams the response.
 *
 * Uses the Fetch API with ReadableStream instead of EventSource because
 * EventSource doesn't support custom headers (we need Bearer token auth).
 *
 * @param query       - Plain-English question about the COBOL codebase
 * @param accessToken - NextAuth JWT token from session.accessToken
 * @param topK        - Max number of code snippets to retrieve (default: 5)
 * @param callbacks   - Handlers for each SSE event type
 *
 * @throws Error if the HTTP request itself fails (network error, 401, etc.)
 */
export async function streamQuery(
  query: string,
  accessToken: string,
  callbacks: StreamCallbacks,
  topK = 5,
): Promise<void> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const response = await fetch(`${apiUrl}/api/v1/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ query, top_k: topK }),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body from server");

  const decoder = new TextDecoder();
  let buffer = "";

  // Read the stream chunk by chunk
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE events are separated by double newlines (\n\n).
    // Split on that boundary and process complete events.
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? ""; // keep incomplete trailing chunk

    for (const eventBlock of events) {
      if (!eventBlock.trim()) continue;

      let eventType = "";
      let data = "";

      for (const line of eventBlock.split("\n")) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        if (line.startsWith("data: ")) data = line.slice(6).trim();
      }

      if (!eventType || !data) continue;

      switch (eventType) {
        case "snippets": {
          const snippets = JSON.parse(data) as CodeSnippet[];
          callbacks.onSnippets(snippets);
          break;
        }
        case "token": {
          // Tokens may contain spaces that were encoded as "%20" — decode them.
          // The backend replaces newlines with spaces so tokens are one-liners.
          callbacks.onToken(data);
          break;
        }
        case "done": {
          const payload = JSON.parse(data) as { query_time_ms: number };
          callbacks.onDone(payload.query_time_ms);
          break;
        }
        case "error": {
          const payload = JSON.parse(data) as { message: string };
          callbacks.onError(payload.message ?? "Unknown error");
          break;
        }
      }
    }
  }
}
