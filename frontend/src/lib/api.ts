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
 *   3. "done"     — pipeline finished, includes full metrics payload
 *   OR
 *   1. "error"    — something went wrong (skips snippets/token/done)
 */

/** A single COBOL code snippet returned by the retrieval pipeline. */
export interface CodeSnippet {
  /** Relative path to the COBOL file (e.g., "programs/payroll.cob") */
  file_path: string
  /** Line number where this snippet starts (1-indexed) */
  start_line: number
  /** Line number where this snippet ends (1-indexed) */
  end_line: number
  /** The raw COBOL source code for this snippet */
  content: string
  /** Backward-compatible alias of combined_score (0.0–1.0). */
  score: number
  /** Raw Pinecone cosine score before reranking blend (0.0–1.0). */
  cosine_score: number
  /** Final blended reranker score shown as primary relevance (0.0–1.0). */
  combined_score: number
  /**
   * How this chunk was split: "paragraph" means it was cut at a natural COBOL
   * paragraph boundary; "fixed" means it was cut at a fixed line count.
   * Paragraph chunks are usually more semantically coherent.
   */
  chunk_type: 'paragraph' | 'fixed'
  /**
   * COBOL paragraph name (e.g., "CALCULATE-INTEREST").
   * Empty string for fixed-size fallback chunks that have no paragraph label.
   * Non-empty means the feature buttons (Explain, Dependencies, etc.) will work.
   */
  paragraph_name: string
}

/**
 * Full metrics payload from the "done" SSE event.
 *
 * Contains timing for each pipeline step plus aggregate similarity stats.
 * This is the same data recorded in Langfuse traces — the frontend can use
 * it to show a metrics bar and build the session query log.
 */
export interface QueryMetrics {
  /** Total end-to-end wall-clock time in milliseconds */
  query_time_ms: number
  /** Time spent embedding the query with Voyage AI */
  embed_ms: number
  /** Time spent querying Pinecone */
  retrieve_ms: number
  /** Time spent reranking candidates */
  rerank_ms: number
  /** Time spent streaming the LLM answer */
  llm_ms: number
  /** Number of code snippets returned */
  chunks_count: number
  /** Highest similarity score among returned snippets (0.0–1.0) */
  top_score: number
  /** Mean similarity score across returned snippets (0.0–1.0) */
  avg_similarity: number
  /** Number of unique source files represented in the results */
  files_hit: number
}

/** Callbacks invoked as SSE events arrive from the backend. */
export interface StreamCallbacks {
  /** Called once when the code snippets are retrieved from Pinecone. */
  onSnippets: (snippets: CodeSnippet[]) => void
  /** Called for each streaming token of the GPT answer. */
  onToken: (token: string) => void
  /** Called when the full answer has been streamed, with full pipeline metrics. */
  onDone: (metrics: QueryMetrics) => void
  /** Called if the backend pipeline fails. */
  onError: (message: string) => void
}

/**
 * streamQuery — sends a query to the backend and streams the response.
 *
 * Uses the Fetch API with ReadableStream instead of EventSource because
 * EventSource doesn't support custom headers (we need Bearer token auth).
 *
 * @param query       - Plain-English question about the COBOL codebase
 * @param accessToken - NextAuth JWT token from session.accessToken
 * @param callbacks   - Handlers for each SSE event type
 * @param topK        - Max number of code snippets to retrieve (default: 5)
 *
 * @throws Error if the HTTP request itself fails (network error, 401, etc.)
 */
export async function streamQuery(
  query: string,
  accessToken: string,
  callbacks: StreamCallbacks,
  topK = 5
): Promise<void> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

  const response = await fetch(`${apiUrl}/api/v1/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ query, top_k: topK }),
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(`HTTP ${response.status}: ${text || response.statusText}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body from server')

  const decoder = new TextDecoder()
  let buffer = ''

  // Read the stream chunk by chunk
  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // SSE events are separated by double newlines (\n\n).
    // Split on that boundary and process complete events.
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? '' // keep incomplete trailing chunk

    for (const eventBlock of events) {
      if (!eventBlock.trim()) continue

      let eventType = ''
      let data = ''

      for (const line of eventBlock.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim()
        if (line.startsWith('data: ')) data = line.slice(6) // preserve leading spaces in tokens
      }

      if (!eventType || !data) continue

      switch (eventType) {
        case 'snippets': {
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
          const snippets = JSON.parse(data) as CodeSnippet[]
          callbacks.onSnippets(snippets)
          break
        }
        case 'token': {
          // Tokens may contain spaces that were encoded as "%20" — decode them.
          // The backend replaces newlines with spaces so tokens are one-liners.
          callbacks.onToken(data)
          break
        }
        case 'done': {
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
          const metrics = JSON.parse(data) as QueryMetrics
          callbacks.onDone(metrics)
          break
        }
        case 'error': {
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
          const payload = JSON.parse(data) as { message: string }
          callbacks.onError(payload.message ?? 'Unknown error')
          break
        }
      }
    }
  }
}

/**
 * callFeature — sends a POST to one of the four code-understanding feature
 * endpoints and returns the parsed JSON response.
 *
 * Unlike streamQuery, the feature endpoints return a single JSON object
 * (not SSE) — they wait for the full GPT-4o-mini reply before responding.
 *
 * @param endpoint    - The endpoint path after /api/v1/ (e.g. "explain")
 * @param body        - Request body (file_path, paragraph_name, etc.)
 * @param accessToken - NextAuth JWT token for Bearer auth
 *
 * @throws Error if the HTTP request fails (network error, 4xx, 5xx)
 */
export async function callFeature<T>(
  endpoint: string,
  body: Record<string, string>,
  accessToken: string
): Promise<T> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

  const response = await fetch(`${apiUrl}/api/v1/${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(`HTTP ${response.status}: ${text || response.statusText}`)
  }

  return response.json() as Promise<T>
}

/**
 * FileContent — the shape returned by the /file endpoint.
 *
 * Contains the full raw COBOL source text plus the line count so the
 * FileModal can show line numbers and scroll to the matched paragraph.
 */
export interface FileContent {
  /** Stored Pinecone path (same as CodeSnippet.file_path) */
  file_path: string
  /** Full raw COBOL source — one newline-delimited string */
  content: string
  /** Total lines in the file (used for line-number display) */
  line_count: number
}

/**
 * fetchFile — fetches the full raw COBOL source for one file from the backend.
 *
 * The backend proxies the request to GitHub raw content so the frontend
 * never makes cross-origin requests to GitHub directly.
 *
 * @param filePath    - The file_path as stored in Pinecone metadata
 * @param accessToken - NextAuth JWT token for Bearer auth
 *
 * @throws Error if the HTTP request fails (404 if file not found on GitHub)
 */
export async function fetchFile(filePath: string, accessToken: string): Promise<FileContent> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

  const response = await fetch(`${apiUrl}/api/v1/file?path=${encodeURIComponent(filePath)}`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(`HTTP ${response.status}: ${text || response.statusText}`)
  }

  return response.json() as Promise<FileContent>
}
