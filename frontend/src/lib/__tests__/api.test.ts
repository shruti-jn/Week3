/**
 * Unit tests for src/lib/api.ts
 *
 * Tests the three public functions:
 * - streamQuery()   — POSTs to /api/v1/query and reads SSE stream
 * - callFeature()   — POSTs to /api/v1/<endpoint> for JSON feature responses
 * - fetchFile()     — GETs /api/v1/file?path=... for full COBOL source
 *
 * All network calls are mocked with jest — no real servers needed.
 */

import { TextEncoder, TextDecoder } from 'util'
import { streamQuery, callFeature, fetchFile } from '../api'
import type { CodeSnippet, QueryMetrics, FileContent, StreamCallbacks } from '../api'

// jsdom doesn't include TextEncoder/TextDecoder — polyfill from Node util
global.TextEncoder = TextEncoder as unknown as typeof global.TextEncoder
global.TextDecoder = TextDecoder as unknown as typeof global.TextDecoder

// ── Test data ────────────────────────────────────────────────────────────────

const MOCK_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test'
const API_BASE = 'http://localhost:8000'

const MOCK_SNIPPET: CodeSnippet = {
  file_path: 'loans/calc.cob',
  start_line: 42,
  end_line: 58,
  content: '       CALC-INTEREST.\n           COMPUTE INTEREST = PRINCIPAL * RATE.',
  score: 0.91,
  chunk_type: 'paragraph',
  paragraph_name: 'CALC-INTEREST',
}

const MOCK_METRICS: QueryMetrics = {
  query_time_ms: 1234,
  embed_ms: 42,
  retrieve_ms: 180,
  rerank_ms: 3,
  llm_ms: 1005,
  chunks_count: 1,
  top_score: 0.91,
  avg_similarity: 0.85,
  files_hit: 1,
}

const MOCK_FILE: FileContent = {
  file_path: 'loans/calc.cob',
  content: '       CALC-INTEREST.\n           COMPUTE INTEREST = PRINCIPAL * RATE.',
  line_count: 2,
}

// ── SSE mock helpers ──────────────────────────────────────────────────────────

/** Builds one SSE event block (with trailing \n\n delimiter). */
function sseEvent(type: string, data: unknown): string {
  return `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`
}

/**
 * Build a mock body.getReader() that yields each SSE string as a Uint8Array
 * chunk, then signals done. Avoids needing ReadableStream (not in jsdom).
 */
function makeSSEBody(...events: string[]): {
  getReader: () => { read: () => Promise<{ done: boolean; value?: Uint8Array }> }
} {
  const enc = new TextEncoder()
  const chunks: Array<{ done: boolean; value?: Uint8Array }> = [
    ...events.map((e) => ({ done: false, value: enc.encode(e) })),
    { done: true },
  ]
  let i = 0
  return { getReader: () => ({ read: () => Promise.resolve(chunks[i++] ?? { done: true }) }) }
}

/** Build a mock SSE Response. */
function makeSSEResponse(...events: string[]): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    body: makeSSEBody(...events),
    text: () => Promise.resolve(''),
  } as unknown as Response
}

/** Build a mock JSON Response for fetch spy. */
function makeJsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
    body: null,
  } as unknown as Response
}

// ── streamQuery ───────────────────────────────────────────────────────────────

describe('streamQuery', () => {
  let fetchSpy: jest.SpyInstance
  let callbacks: StreamCallbacks

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = API_BASE
    fetchSpy = jest.spyOn(global, 'fetch')
    callbacks = {
      onSnippets: jest.fn(),
      onToken: jest.fn(),
      onDone: jest.fn(),
      onError: jest.fn(),
    }
  })

  afterEach(() => {
    fetchSpy.mockRestore()
    delete process.env.NEXT_PUBLIC_API_URL
  })

  it('sends a POST to NEXT_PUBLIC_API_URL/api/v1/query', async () => {
    fetchSpy.mockResolvedValueOnce(makeSSEResponse(sseEvent('done', MOCK_METRICS)))

    await streamQuery('how does interest work?', MOCK_TOKEN, callbacks)

    expect(fetchSpy).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/query`,
      expect.objectContaining({ method: 'POST' })
    )
  })

  it('sends Authorization Bearer token header', async () => {
    fetchSpy.mockResolvedValueOnce(makeSSEResponse(sseEvent('done', MOCK_METRICS)))

    await streamQuery('test query', MOCK_TOKEN, callbacks)

    const [, opts] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect((opts.headers as Record<string, string>)['Authorization']).toBe(`Bearer ${MOCK_TOKEN}`)
  })

  it('sends Content-Type application/json', async () => {
    fetchSpy.mockResolvedValueOnce(makeSSEResponse(sseEvent('done', MOCK_METRICS)))

    await streamQuery('test query', MOCK_TOKEN, callbacks)

    const [, opts] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect((opts.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('includes query and top_k in the request body', async () => {
    fetchSpy.mockResolvedValueOnce(makeSSEResponse(sseEvent('done', MOCK_METRICS)))

    await streamQuery('test query', MOCK_TOKEN, callbacks, 3)

    const [, opts] = fetchSpy.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(opts.body as string) as { query: string; top_k: number }
    expect(body).toEqual({ query: 'test query', top_k: 3 })
  })

  it('defaults top_k to 5 when not specified', async () => {
    fetchSpy.mockResolvedValueOnce(makeSSEResponse(sseEvent('done', MOCK_METRICS)))

    await streamQuery('test query', MOCK_TOKEN, callbacks)

    const [, opts] = fetchSpy.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(opts.body as string) as { query: string; top_k: number }
    expect(body.top_k).toBe(5)
  })

  it('calls onSnippets when snippets SSE event arrives', async () => {
    fetchSpy.mockResolvedValueOnce(
      makeSSEResponse(sseEvent('snippets', [MOCK_SNIPPET]), sseEvent('done', MOCK_METRICS))
    )

    await streamQuery('test query', MOCK_TOKEN, callbacks)

    expect(callbacks.onSnippets).toHaveBeenCalledWith([MOCK_SNIPPET])
  })

  it('calls onToken for each token SSE event', async () => {
    fetchSpy.mockResolvedValueOnce(
      makeSSEResponse(
        sseEvent('token', 'Hello'),
        sseEvent('token', ' world'),
        sseEvent('done', MOCK_METRICS)
      )
    )

    await streamQuery('test query', MOCK_TOKEN, callbacks)

    expect(callbacks.onToken).toHaveBeenCalledTimes(2)
    expect(callbacks.onToken).toHaveBeenNthCalledWith(1, '"Hello"')
    expect(callbacks.onToken).toHaveBeenNthCalledWith(2, '" world"')
  })

  it('calls onDone with metrics when done SSE event arrives', async () => {
    fetchSpy.mockResolvedValueOnce(makeSSEResponse(sseEvent('done', MOCK_METRICS)))

    await streamQuery('test query', MOCK_TOKEN, callbacks)

    expect(callbacks.onDone).toHaveBeenCalledWith(MOCK_METRICS)
  })

  it('calls onError when error SSE event arrives', async () => {
    fetchSpy.mockResolvedValueOnce(
      makeSSEResponse(sseEvent('error', { message: 'Pinecone unavailable' }))
    )

    await streamQuery('test query', MOCK_TOKEN, callbacks)

    expect(callbacks.onError).toHaveBeenCalledWith('Pinecone unavailable')
  })

  it('throws when HTTP response is not ok', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      text: () => Promise.resolve('Unauthorized'),
    } as unknown as Response)

    await expect(streamQuery('test query', MOCK_TOKEN, callbacks)).rejects.toThrow('HTTP 401')
  })

  it('falls back to http://localhost:8000 when NEXT_PUBLIC_API_URL is not set', async () => {
    delete process.env.NEXT_PUBLIC_API_URL
    fetchSpy.mockResolvedValueOnce(makeSSEResponse(sseEvent('done', MOCK_METRICS)))

    await streamQuery('test query', MOCK_TOKEN, callbacks)

    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://localhost:8000/api/v1/query')
  })
})

// ── callFeature ───────────────────────────────────────────────────────────────

describe('callFeature', () => {
  let fetchSpy: jest.SpyInstance

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = API_BASE
    fetchSpy = jest.spyOn(global, 'fetch')
  })

  afterEach(() => {
    fetchSpy.mockRestore()
    delete process.env.NEXT_PUBLIC_API_URL
  })

  it('sends POST to the correct feature endpoint', async () => {
    fetchSpy.mockResolvedValueOnce(makeJsonResponse({ explanation: 'computes interest' }))

    await callFeature(
      'explain',
      { file_path: 'loans/calc.cob', paragraph_name: 'CALC-INTEREST' },
      MOCK_TOKEN
    )

    expect(fetchSpy).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/explain`,
      expect.objectContaining({ method: 'POST' })
    )
  })

  it('sends Authorization Bearer token', async () => {
    fetchSpy.mockResolvedValueOnce(makeJsonResponse({ rules: [] }))

    await callFeature('business-logic', { file_path: 'loans/calc.cob' }, MOCK_TOKEN)

    const [, opts] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect((opts.headers as Record<string, string>)['Authorization']).toBe(`Bearer ${MOCK_TOKEN}`)
  })

  it('returns parsed JSON response', async () => {
    const mockResponse = { paragraph_name: 'CALC-INTEREST', explanation: 'computes interest' }
    fetchSpy.mockResolvedValueOnce(makeJsonResponse(mockResponse))

    const result = await callFeature<typeof mockResponse>(
      'explain',
      { file_path: 'loans/calc.cob', paragraph_name: 'CALC-INTEREST' },
      MOCK_TOKEN
    )

    expect(result).toEqual(mockResponse)
  })

  it('throws when HTTP response is not ok', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: () => Promise.resolve('Internal Server Error'),
    } as unknown as Response)

    await expect(
      callFeature('explain', { file_path: 'x.cob', paragraph_name: 'PARA' }, MOCK_TOKEN)
    ).rejects.toThrow('HTTP 500')
  })
})

// ── fetchFile ─────────────────────────────────────────────────────────────────

describe('fetchFile', () => {
  let fetchSpy: jest.SpyInstance

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = API_BASE
    fetchSpy = jest.spyOn(global, 'fetch')
  })

  afterEach(() => {
    fetchSpy.mockRestore()
    delete process.env.NEXT_PUBLIC_API_URL
  })

  it('sends GET to /api/v1/file with encoded path', async () => {
    fetchSpy.mockResolvedValueOnce(makeJsonResponse(MOCK_FILE))

    await fetchFile('loans/calc.cob', MOCK_TOKEN)

    expect(fetchSpy).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/file?path=${encodeURIComponent('loans/calc.cob')}`,
      expect.objectContaining({ headers: { Authorization: `Bearer ${MOCK_TOKEN}` } })
    )
  })

  it('returns parsed FileContent on success', async () => {
    fetchSpy.mockResolvedValueOnce(makeJsonResponse(MOCK_FILE))

    const result = await fetchFile('loans/calc.cob', MOCK_TOKEN)

    expect(result).toEqual(MOCK_FILE)
  })

  it('throws when HTTP response is not ok', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      text: () => Promise.resolve('Not Found'),
    } as unknown as Response)

    await expect(fetchFile('missing.cob', MOCK_TOKEN)).rejects.toThrow('HTTP 404')
  })

  it('falls back to localhost when NEXT_PUBLIC_API_URL is not set', async () => {
    delete process.env.NEXT_PUBLIC_API_URL
    fetchSpy.mockResolvedValueOnce(makeJsonResponse(MOCK_FILE))

    await fetchFile('loans/calc.cob', MOCK_TOKEN)

    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('http://localhost:8000/api/v1/file')
  })
})
