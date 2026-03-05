/**
 * TypeScript types for the LegacyLens FastAPI backend responses.
 *
 * These mirror the Pydantic models in backend/app/models/responses.py.
 * Keep in sync whenever the backend response shapes change.
 */

/** A single COBOL code snippet retrieved from the vector database. */
export interface CodeSnippet {
  /** Relative path to the COBOL source file (e.g. "payroll/calc.cob"). */
  file_path: string
  /** First line of the snippet — 1-indexed, inclusive. */
  start_line: number
  /** Last line of the snippet — 1-indexed, inclusive. */
  end_line: number
  /** Raw COBOL source code for this snippet. */
  content: string
  /** Cosine similarity score from Pinecone, 0.0–1.0. */
  score: number
}

/** Response body for POST /api/v1/query. */
export interface QueryResponse {
  /** GPT-4o-mini generated answer to the user's question. */
  answer: string
  /** COBOL code chunks used as context for the answer. */
  snippets: CodeSnippet[]
  /** Total end-to-end query time in milliseconds. */
  query_time_ms: number
}
