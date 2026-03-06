'use client'

/**
 * SearchPage — the main query interface for LegacyLens.
 *
 * Terminal-aesthetic layout:
 *   ┌─ header bar ─────────────────────────────────────────────────────────┐
 *   │  > LegacyLens_                              user@github  ↩ sign out  │
 *   └───────────────────────────────────────────────────────────────────────┘
 *   $ query_cobol_codebase --index legacylens
 *   > [  input box  ]  [→ run]
 *
 *   ── Pipeline metrics bar ──────────────────────────────────────────────
 *   ⏱ 1.23s  ↑ 0.921  ~ 0.847  📄 2 files  # 3 chunks
 *   embed 42ms · retrieve 180ms · rerank 3ms · llm 1005ms
 *
 *   ● PAYMNT-CALC  [PARA]  score: 0.91  payroll/PAYROLL.cob · lines 142–178
 *   ────────────────────────────────────────────────
 *     142 │ PAYMNT-CALC.
 *     143 │     COMPUTE WS-GROSS-PAY = ...
 *   ────────────────────────────────────────────────
 *
 *   > Generating answer...
 *     The PAYMNT-CALC paragraph handles payroll calculation by...
 *
 *   ── Session query log (after 2+ queries) ─────────────────────────────
 *   #  Query                    Time    Top     Avg     Files  Chunks
 *   1  How is interest calc...  1.23s   0.921   0.847   2      3
 */

import { useState, useRef, useEffect, useCallback, type FormEvent } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useSession } from 'next-auth/react'
import type { Session } from 'next-auth'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism'
import AuthButton from '@/components/AuthButton'
import {
  streamQuery,
  callFeature,
  fetchFile,
  type CodeSnippet,
  type QueryMetrics,
  type FileContent,
} from '@/lib/api'

/** Extends the default NextAuth session type to include our access token. */
interface LegacySession extends Session {
  accessToken?: string
}

/**
 * One entry in the session query log.
 *
 * Persisted to localStorage so the log survives page reloads within
 * the same browser session.
 */
interface QueryLogEntry {
  id: number
  query: string
  timestamp: number
  metrics: QueryMetrics
}

const SESSION_LOG_KEY = 'legacylens_query_log'
const MAX_LOG_ENTRIES = 20

// ── localStorage helpers ──────────────────────────────────────────────────────

function loadQueryLog(): QueryLogEntry[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(SESSION_LOG_KEY)
    return raw ? (JSON.parse(raw) as QueryLogEntry[]) : []
  } catch {
    return []
  }
}

function saveQueryLog(log: QueryLogEntry[]): void {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(SESSION_LOG_KEY, JSON.stringify(log))
  } catch {
    // localStorage quota exceeded — silently ignore
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

/** Syntax-highlighted COBOL code block with line numbers. */
function CodeBlock({
  content,
  startLine,
}: {
  content: string
  startLine: number
}): React.JSX.Element {
  return (
    <div className="code-block overflow-x-auto rounded-b">
      <SyntaxHighlighter
        language="cobol"
        style={vscDarkPlus}
        showLineNumbers
        lineNumberStart={startLine}
        wrapLongLines
        lineNumberStyle={{
          color: 'var(--terminal-dim)',
          minWidth: '2.75rem',
          paddingRight: '1rem',
          textAlign: 'right',
          userSelect: 'none',
          fontSize: '0.75rem',
        }}
        customStyle={{
          margin: 0,
          padding: '0.75rem',
          background: 'transparent',
          fontSize: '0.75rem',
          borderRadius: 0,
        }}
      >
        {content}
      </SyntaxHighlighter>
    </div>
  )
}

/** A single result card showing a matched COBOL code snippet. */
function SnippetCard({
  snippet,
  index,
  accessToken,
  onViewFile,
}: {
  snippet: CodeSnippet
  index: number
  /** JWT token for authenticated feature API calls. */
  accessToken: string
  /** Called when the user clicks "View Full File" — triggers the FileModal. */
  onViewFile: (snippet: CodeSnippet) => void
}): React.JSX.Element {
  const [expanded, setExpanded] = useState(index === 0) // first result open by default
  const [activeFeature, setActiveFeature] = useState<FeatureType | null>(null)
  const [featureResult, setFeatureResult] = useState<FeatureResult | null>(null)
  const [featureLoading, setFeatureLoading] = useState(false)
  const [featureError, setFeatureError] = useState('')

  const fileName = snippet.file_path.split('/').pop() ?? snippet.file_path
  // Prefer the API-supplied paragraph_name; fall back to regex extraction for display
  const displayName =
    snippet.paragraph_name ||
    snippet.content
      .split('\n')
      .slice(0, 2)
      .join(' ')
      .trim()
      .match(/^([A-Z0-9-]+)\./)?.[1] ||
    fileName.replace('.cob', '').toUpperCase()

  const handleFeature = useCallback(
    async (feature: FeatureType): Promise<void> => {
      // Toggle off if same button clicked again
      if (activeFeature === feature && featureResult !== null) {
        setActiveFeature(null)
        setFeatureResult(null)
        return
      }

      setActiveFeature(feature)
      setFeatureLoading(true)
      setFeatureError('')
      setFeatureResult(null)

      try {
        const body: Record<string, string> =
          feature === 'business-logic'
            ? { file_path: snippet.file_path }
            : { file_path: snippet.file_path, paragraph_name: snippet.paragraph_name }

        if (feature === 'explain') {
          const data = await callFeature<ExplainResponse>(feature, body, accessToken)
          setFeatureResult({ type: 'explain', data })
        } else if (feature === 'dependencies') {
          const data = await callFeature<DependenciesResponse>(feature, body, accessToken)
          setFeatureResult({ type: 'dependencies', data })
        } else if (feature === 'business-logic') {
          const data = await callFeature<BusinessLogicResponse>(feature, body, accessToken)
          setFeatureResult({ type: 'business-logic', data })
        } else {
          const data = await callFeature<ImpactResponse>(feature, body, accessToken)
          setFeatureResult({ type: 'impact', data })
        }
      } catch (err) {
        setFeatureError(err instanceof Error ? err.message : 'Feature call failed')
      } finally {
        setFeatureLoading(false)
      }
    },
    [activeFeature, featureResult, snippet, accessToken]
  )

  const FEATURE_BUTTONS: { id: FeatureType; label: string; title: string }[] = [
    { id: 'explain', label: 'Explain', title: 'Plain-English explanation of this paragraph' },
    { id: 'dependencies', label: 'Dependencies', title: 'PERFORM call graph (calls / called-by)' },
    { id: 'business-logic', label: 'Business Logic', title: 'Business rules encoded in this file' },
    { id: 'impact', label: 'Impact', title: 'Which paragraphs break if this one changes' },
  ]

  return (
    <div className="fade-in overflow-hidden rounded-lg border border-terminal-border bg-terminal-surface">
      {/* Card header */}
      <div className="flex w-full items-center justify-between px-4 py-3 transition-colors hover:bg-white/5">
        {/* Left: toggle + name + badges */}
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          aria-expanded={expanded}
        >
          <span
            className="flex-shrink-0 text-sm font-bold text-terminal-accent"
            title={
              snippet.chunk_type === 'paragraph' ? 'COBOL paragraph chunk' : 'Fixed-size chunk'
            }
          >
            ●
          </span>
          <span
            className="truncate text-sm font-semibold tracking-wide text-terminal-text"
            title={snippet.paragraph_name || displayName}
          >
            {displayName}
          </span>
          {/* chunk_type badge */}
          <span
            className={`flex-shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider ${
              snippet.chunk_type === 'paragraph'
                ? 'border border-terminal-accent/30 bg-terminal-accent/15 text-terminal-accent'
                : 'border border-terminal-muted/30 bg-terminal-muted/15 text-terminal-muted'
            }`}
            title={
              snippet.chunk_type === 'paragraph'
                ? 'Split at a COBOL paragraph boundary'
                : 'Fixed-size chunk (no paragraph boundary found)'
            }
          >
            {snippet.chunk_type === 'paragraph' ? 'para' : 'fixed'}
          </span>
          <span
            className="hidden truncate text-xs text-terminal-muted sm:block"
            title={`${snippet.file_path} · lines ${snippet.start_line}–${snippet.end_line}`}
          >
            {fileName}
            <span className="text-terminal-dim">
              {' '}
              · lines {snippet.start_line}–{snippet.end_line}
            </span>
          </span>
        </button>

        {/* Right: score + view file + expand */}
        <div className="ml-3 flex flex-shrink-0 items-center gap-3">
          <span
            className="font-mono text-xs"
            title={`Cosine similarity score: ${snippet.score.toFixed(4)} (1.0 = perfect match)`}
          >
            <span className="text-terminal-muted">score: </span>
            <span className="text-terminal-accent">{snippet.score.toFixed(3)}</span>
          </span>
          {/* View Full File button */}
          <button
            onClick={(e) => {
              e.stopPropagation()
              onViewFile(snippet)
            }}
            className="hidden rounded border border-terminal-border px-2 py-0.5 font-mono text-[10px] text-terminal-dim transition-colors hover:border-terminal-accent hover:text-terminal-accent sm:block"
            title="View full COBOL source file"
          >
            view file
          </button>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-terminal-muted"
            aria-label={expanded ? 'Collapse' : 'Expand'}
            title={expanded ? 'Collapse code' : 'Expand code'}
          >
            {expanded ? '▲' : '▼'}
          </button>
        </div>
      </div>

      {/* File path on mobile */}
      <div className="flex items-center justify-between px-4 pb-1 text-xs text-terminal-muted sm:hidden">
        <span className="truncate">
          {snippet.file_path} · lines {snippet.start_line}–{snippet.end_line}
        </span>
        <button
          onClick={() => onViewFile(snippet)}
          className="ml-2 flex-shrink-0 font-mono text-[10px] text-terminal-dim transition-colors hover:text-terminal-accent"
        >
          view file
        </button>
      </div>

      {/* Code body */}
      {expanded && (
        <>
          <CodeBlock content={snippet.content} startLine={snippet.start_line} />

          {/* Feature tabs — only for paragraph chunks with a known name */}
          {snippet.paragraph_name && (
            <div className="border-t border-terminal-border">
              {/* Button row */}
              <div className="flex flex-wrap gap-1.5 bg-terminal-bg/40 px-4 py-2.5">
                {FEATURE_BUTTONS.map(({ id, label, title }) => (
                  <button
                    key={id}
                    onClick={() => void handleFeature(id)}
                    disabled={featureLoading && activeFeature !== id}
                    title={title}
                    className={`rounded border px-2.5 py-1 font-mono text-[10px] font-medium transition-colors ${
                      activeFeature === id
                        ? 'border-terminal-accent bg-terminal-accent/10 text-terminal-accent'
                        : 'border-terminal-border text-terminal-muted hover:border-terminal-accent hover:text-terminal-accent'
                    } disabled:opacity-40`}
                  >
                    {featureLoading && activeFeature === id ? '···' : label}
                  </button>
                ))}
              </div>

              {/* Feature error */}
              {featureError && (
                <div className="border-t border-terminal-border px-4 py-2 font-mono text-xs text-terminal-error">
                  error: {featureError}
                </div>
              )}

              {/* Feature result */}
              {featureResult && !featureLoading && <FeaturePanel result={featureResult} />}
            </div>
          )}
        </>
      )}
    </div>
  )
}

/**
 * MetricsBar — compact pipeline analytics strip shown after each query.
 *
 * Two rows:
 *   Row 1: total time · top score · avg similarity · files hit · chunk count
 *   Row 2: step-level timings (embed / retrieve / rerank / llm)
 */
function MetricsBar({ metrics }: { metrics: QueryMetrics }): React.JSX.Element {
  const totalSec = (metrics.query_time_ms / 1000).toFixed(2)

  return (
    <div className="fade-in rounded-lg border border-terminal-border bg-terminal-surface/60 px-4 py-3 font-mono text-xs">
      {/* Row 1: key metrics */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
        <MetricPill
          label="total"
          value={`${totalSec}s`}
          highlight
          title="End-to-end query latency"
        />
        <MetricPill
          label="top score"
          value={(metrics.top_score * 100).toFixed(1) + '%'}
          highlight={metrics.top_score >= 0.85}
          title="Highest similarity score among returned snippets"
        />
        <MetricPill
          label="avg sim"
          value={(metrics.avg_similarity * 100).toFixed(1) + '%'}
          title="Mean similarity score across all returned snippets"
        />
        <MetricPill
          label="files"
          value={String(metrics.files_hit)}
          title="Number of unique COBOL source files in results"
        />
        <MetricPill
          label="chunks"
          value={String(metrics.chunks_count)}
          title="Number of code snippets returned"
        />
      </div>

      {/* Row 2: step timings */}
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-terminal-dim">
        <StepTiming label="embed" ms={metrics.embed_ms} />
        <span className="text-terminal-border">·</span>
        <StepTiming label="retrieve" ms={metrics.retrieve_ms} />
        <span className="text-terminal-border">·</span>
        <StepTiming label="rerank" ms={metrics.rerank_ms} />
        <span className="text-terminal-border">·</span>
        <StepTiming label="llm" ms={metrics.llm_ms} />
      </div>
    </div>
  )
}

function MetricPill({
  label,
  value,
  highlight = false,
  title,
}: {
  label: string
  value: string
  highlight?: boolean
  title?: string
}): React.JSX.Element {
  return (
    <span className="flex items-center gap-1.5" title={title}>
      <span className="text-terminal-dim">{label}:</span>
      <span className={highlight ? 'font-semibold text-terminal-accent' : 'text-terminal-text'}>
        {value}
      </span>
    </span>
  )
}

function StepTiming({ label, ms }: { label: string; ms: number }): React.JSX.Element {
  return (
    <span>
      <span className="text-terminal-dim">{label} </span>
      <span className="text-terminal-muted">{ms.toFixed(0)}ms</span>
    </span>
  )
}

/** Streaming answer panel — shows GPT answer as it arrives token by token. */
function AnswerPanel({
  answer,
  loading,
  metrics,
}: {
  answer: string
  loading: boolean
  metrics: QueryMetrics | null
}): React.JSX.Element | null {
  if (!answer && !loading) return null

  return (
    <div className="fade-in rounded-lg border border-terminal-border bg-terminal-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-sm font-semibold text-terminal-accent">▶ Answer</span>
        {loading && (
          <span className="inline-flex gap-1">
            <span
              className="h-1 w-1 animate-bounce rounded-full bg-terminal-accent"
              style={{ animationDelay: '0ms' }}
            />
            <span
              className="h-1 w-1 animate-bounce rounded-full bg-terminal-accent"
              style={{ animationDelay: '150ms' }}
            />
            <span
              className="h-1 w-1 animate-bounce rounded-full bg-terminal-accent"
              style={{ animationDelay: '300ms' }}
            />
          </span>
        )}
        {!loading && metrics !== null && (
          <span className="text-xs text-terminal-muted">
            {(metrics.query_time_ms / 1000).toFixed(2)}s
          </span>
        )}
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-terminal-text">
        {answer}
        {loading && <span className="cursor-blink" />}
      </p>
    </div>
  )
}

/**
 * SessionQueryLog — compact table of recent queries in this session.
 *
 * Only shown when there are 2 or more entries so it doesn't clutter
 * the UI after a single query.
 */
function SessionQueryLog({
  log,
  onClear,
}: {
  log: QueryLogEntry[]
  onClear: () => void
}): React.JSX.Element | null {
  if (log.length < 2) return null

  return (
    <div className="fade-in mt-6">
      <div className="mb-2 flex items-center justify-between">
        <p className="font-mono text-xs text-terminal-muted">
          {'// '}session query log ({log.length} queries)
        </p>
        <button
          onClick={onClear}
          className="font-mono text-[10px] text-terminal-dim transition-colors hover:text-terminal-muted"
          title="Clear session log"
        >
          clear
        </button>
      </div>
      <div className="overflow-hidden rounded-lg border border-terminal-border bg-terminal-surface">
        <div className="overflow-x-auto">
          <table className="w-full font-mono text-xs">
            <thead>
              <tr className="border-b border-terminal-border bg-terminal-bg/40">
                <th className="w-6 px-3 py-2 text-left font-normal text-terminal-dim">#</th>
                <th className="px-3 py-2 text-left font-normal text-terminal-dim">query</th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-normal text-terminal-dim">
                  time
                </th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-normal text-terminal-dim">
                  top
                </th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-normal text-terminal-dim">
                  avg
                </th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-normal text-terminal-dim">
                  files
                </th>
                <th className="whitespace-nowrap px-3 py-2 text-right font-normal text-terminal-dim">
                  chunks
                </th>
              </tr>
            </thead>
            <tbody>
              {log.map((entry, i) => (
                <tr
                  key={entry.id}
                  className={`border-b border-terminal-border/40 last:border-0 ${
                    i === 0 ? 'bg-terminal-accent/5' : ''
                  }`}
                >
                  <td className="px-3 py-2 text-terminal-dim">{entry.id}</td>
                  <td className="max-w-[200px] truncate px-3 py-2 text-terminal-text">
                    {entry.query}
                  </td>
                  <td className="px-3 py-2 text-right text-terminal-accent">
                    {(entry.metrics.query_time_ms / 1000).toFixed(2)}s
                  </td>
                  <td className="px-3 py-2 text-right text-terminal-text">
                    {(entry.metrics.top_score * 100).toFixed(0)}%
                  </td>
                  <td className="px-3 py-2 text-right text-terminal-muted">
                    {(entry.metrics.avg_similarity * 100).toFixed(0)}%
                  </td>
                  <td className="px-3 py-2 text-right text-terminal-muted">
                    {entry.metrics.files_hit}
                  </td>
                  <td className="px-3 py-2 text-right text-terminal-muted">
                    {entry.metrics.chunks_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ── Feature response types ────────────────────────────────────────────────────

/** Shape returned by POST /api/v1/explain */
interface ExplainResponse {
  paragraph_name: string
  explanation: string
}

/** Shape returned by POST /api/v1/dependencies */
interface DependenciesResponse {
  paragraph_name: string
  calls: string[]
  called_by: string[]
}

/** Shape returned by POST /api/v1/business-logic */
interface BusinessLogicResponse {
  file_path: string
  rules: string[]
}

/** Shape returned by POST /api/v1/impact */
interface ImpactResponse {
  paragraph_name: string
  affected_paragraphs: string[]
}

type FeatureType = 'explain' | 'dependencies' | 'business-logic' | 'impact'
type FeatureResult =
  | { type: 'explain'; data: ExplainResponse }
  | { type: 'dependencies'; data: DependenciesResponse }
  | { type: 'business-logic'; data: BusinessLogicResponse }
  | { type: 'impact'; data: ImpactResponse }

// ── FeaturePanel — renders the result of a code-understanding feature call ────

/**
 * FeaturePanel — displays the result of one of the four LLM-powered features.
 *
 * Renders inside an expanded SnippetCard below the code block. The visual
 * style matches the terminal theme: dark background, monospace font, green
 * accents for the feature name, bullet-point lists for multi-item results.
 */
function FeaturePanel({ result }: { result: FeatureResult }): React.JSX.Element {
  if (result.type === 'explain') {
    return (
      <div className="border-t border-terminal-border bg-terminal-bg/60 px-4 py-3 text-xs">
        <p className="mb-1 font-mono font-semibold text-terminal-accent">
          {'// '}explain: {result.data.paragraph_name}
        </p>
        <p className="whitespace-pre-wrap leading-relaxed text-terminal-text">
          {result.data.explanation}
        </p>
      </div>
    )
  }

  if (result.type === 'dependencies') {
    return (
      <div className="border-t border-terminal-border bg-terminal-bg/60 px-4 py-3 font-mono text-xs">
        <p className="mb-2 font-semibold text-terminal-accent">
          {'// '}dependencies: {result.data.paragraph_name}
        </p>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="mb-1 text-terminal-dim">calls (PERFORM):</p>
            {result.data.calls.length === 0 ? (
              <p className="italic text-terminal-muted">none</p>
            ) : (
              <ul className="space-y-0.5">
                {result.data.calls.map((p) => (
                  <li key={p} className="text-terminal-text">
                    → {p}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <p className="mb-1 text-terminal-dim">called by:</p>
            {result.data.called_by.length === 0 ? (
              <p className="italic text-terminal-muted">none</p>
            ) : (
              <ul className="space-y-0.5">
                {result.data.called_by.map((p) => (
                  <li key={p} className="text-terminal-text">
                    ← {p}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    )
  }

  if (result.type === 'business-logic') {
    return (
      <div className="border-t border-terminal-border bg-terminal-bg/60 px-4 py-3 font-mono text-xs">
        <p className="mb-2 font-semibold text-terminal-accent">{'// '}business rules</p>
        {result.data.rules.length === 0 ? (
          <p className="italic text-terminal-muted">No business rules found.</p>
        ) : (
          <ul className="space-y-1">
            {result.data.rules.map((rule, i) => (
              <li key={i} className="flex gap-2 text-terminal-text">
                <span className="flex-shrink-0 text-terminal-accent">•</span>
                <span>{rule}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  // impact
  return (
    <div className="border-t border-terminal-border bg-terminal-bg/60 px-4 py-3 font-mono text-xs">
      <p className="mb-2 font-semibold text-terminal-accent">
        {'// '}impact: if {result.data.paragraph_name} changes
      </p>
      {result.data.affected_paragraphs.length === 0 ? (
        <p className="italic text-terminal-muted">No affected paragraphs.</p>
      ) : (
        <ul className="space-y-0.5">
          {result.data.affected_paragraphs.map((p) => (
            <li key={p} className="text-terminal-text">
              ⚠ {p}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── FileModal — full COBOL source view with matched paragraph highlighted ──────

/**
 * FileModal — displays the full raw COBOL source for a file in an overlay.
 *
 * Opens when the user clicks "View Full File" on a SnippetCard. Shows the
 * complete file with line numbers and scrolls to + highlights the matched
 * paragraph (the lines from snippet.start_line to snippet.end_line).
 *
 * @param fileContent - The fetched file content and metadata
 * @param snippet     - The matched snippet so we know which lines to highlight
 * @param onClose     - Callback to close the modal
 */
function FileModal({
  fileContent,
  snippet,
  onClose,
}: {
  fileContent: FileContent
  snippet: CodeSnippet
  onClose: () => void
}): React.JSX.Element {
  const highlightRef = useRef<HTMLTableRowElement>(null)

  // Scroll to highlighted paragraph as soon as the modal mounts
  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [])

  const lines = fileContent.content.split('\n')
  const fileName = fileContent.file_path.split('/').pop() ?? fileContent.file_path

  return (
    /* Overlay */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
      onClick={(e) => {
        // Close on backdrop click only
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {/* Modal panel */}
      <div
        className="relative flex flex-col rounded-lg border border-terminal-border bg-terminal-surface"
        style={{ width: '90vw', height: '85vh' }}
      >
        {/* Header */}
        <div className="flex flex-shrink-0 items-center justify-between border-b border-terminal-border px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="text-sm font-semibold text-terminal-accent">📄</span>
            <span className="truncate font-mono text-sm font-semibold text-terminal-text">
              {fileName}
            </span>
            <span className="font-mono text-xs text-terminal-dim">
              {fileContent.line_count} lines
            </span>
            {snippet.paragraph_name && (
              <span className="hidden truncate font-mono text-xs text-terminal-muted sm:block">
                · highlighted:{' '}
                <span className="text-terminal-accent">{snippet.paragraph_name}</span> (lines{' '}
                {snippet.start_line}–{snippet.end_line})
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="ml-3 flex-shrink-0 rounded border border-terminal-border px-2 py-1 text-xs text-terminal-muted transition-colors hover:border-terminal-accent hover:text-terminal-accent"
            aria-label="Close file view"
          >
            ✕ close
          </button>
        </div>

        {/* File content — scrollable */}
        <div className="flex-1 overflow-y-auto">
          <table className="w-full border-collapse font-mono text-xs">
            <tbody>
              {lines.map((line, i) => {
                const lineNum = i + 1
                const isHighlighted = lineNum >= snippet.start_line && lineNum <= snippet.end_line
                return (
                  <tr
                    key={lineNum}
                    ref={isHighlighted && lineNum === snippet.start_line ? highlightRef : undefined}
                    className={
                      isHighlighted
                        ? 'border-l-2 border-terminal-accent bg-terminal-accent/10'
                        : 'hover:bg-white/5'
                    }
                  >
                    <td className="w-12 select-none border-r border-terminal-border/30 px-3 py-0.5 text-right text-terminal-dim">
                      {lineNum}
                    </td>
                    <td className="px-3 py-0.5">
                      <pre
                        className={`whitespace-pre ${isHighlighted ? 'text-terminal-text' : 'text-terminal-muted'}`}
                      >
                        {line || ' '}
                      </pre>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ── Suggested queries — from golden eval set, min_score ≥ 0.70 ────────────────
const EXAMPLE_QUERIES = [
  'How do you sort a file in COBOL?',
  'DES encryption algorithm implementation',
  'How do you insert a record into a database?',
  'Parse HTML form data in a CGI COBOL program',
  'What does the CHECK-CONTENT-DISPOSITION paragraph do?',
]

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SearchPage(): React.JSX.Element {
  const { data: rawSession } = useSession()
  const session = rawSession as LegacySession | null
  const router = useRouter()
  const searchParams = useSearchParams()

  const [query, setQuery] = useState('')
  const [snippets, setSnippets] = useState<CodeSnippet[]>([])
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [metrics, setMetrics] = useState<QueryMetrics | null>(null)
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [queryLog, setQueryLog] = useState<QueryLogEntry[]>([])
  // Raw NextAuth JWT (signed with NEXTAUTH_SECRET) — required by FastAPI's HS256 validator.
  // session.accessToken is the GitHub OAuth token (opaque), not a JWT; this fetches
  // the actual signed session cookie JWT via the /api/auth/token route.
  const [backendToken, setBackendToken] = useState('')

  /**
   * openFile — state for the FileModal overlay.
   *
   * null means the modal is closed. When set, it holds:
   *   - snippet: the card that triggered "View Full File" (for line highlighting)
   *   - content: the fetched FileContent (null while loading)
   *   - loading: true while the /file request is in-flight
   */
  const [openFile, setOpenFile] = useState<{
    snippet: CodeSnippet
    content: FileContent | null
    loading: boolean
  } | null>(null)

  // Keep a ref to the latest answer so the closure in streamQuery always
  // appends to the most recent value (avoids stale closure issue).
  const answerRef = useRef('')
  // Prevent the URL-param auto-submit from firing more than once per page load.
  const hasAutoSubmittedRef = useRef(false)

  // Load persisted query log from localStorage on mount
  useEffect(() => {
    setQueryLog(loadQueryLog())
  }, [])

  // Fetch the raw NextAuth JWT once the session is established.
  // FastAPI verifies HS256 tokens signed with NEXTAUTH_SECRET — this is the
  // session cookie JWT, not the GitHub OAuth access token in session.accessToken.
  useEffect(() => {
    if (!session) return
    fetch('/api/auth/token')
      .then((r) => r.json())
      .then(({ token }: { token?: string }) => {
        if (token) setBackendToken(token)
      })
      .catch(() => {
        // Silently ignore — the query will surface a 401 if auth fails
      })
  }, [session])

  // Auto-submit from ?q= URL param — waits for backendToken; ref gate prevents double-fires.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- handleSubmit omitted intentionally: changes every render; ref gate prevents double-fires
  useEffect(() => {
    if (hasAutoSubmittedRef.current) return
    const urlQuery = searchParams.get('q')
    if (!urlQuery || !backendToken) return
    hasAutoSubmittedRef.current = true
    setQuery(urlQuery)
    void handleSubmit(urlQuery)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- handleSubmit is not useCallback-wrapped; adding it would cause an infinite loop
  }, [backendToken, searchParams])

  // Wake the Railway dyno early — free-tier dynos sleep after inactivity.
  // Firing on page load gives the backend ~2 seconds to warm up before the
  // user submits their first query.
  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/health`).catch(() => {
      // Best-effort warmup — ignore failures silently, don't block the UI
    })
  }, [])

  const handleSubmit = async (q?: string): Promise<void> => {
    const finalQuery = (q ?? query).trim()
    if (!finalQuery || loading) return

    const token = backendToken

    setLoading(true)
    setSnippets([])
    setAnswer('')
    setError('')
    setMetrics(null)
    setSubmittedQuery(finalQuery)
    answerRef.current = ''
    // Reflect the query in the URL so it can be bookmarked / shared.
    router.replace(`/search?q=${encodeURIComponent(finalQuery)}`, { scroll: false })

    try {
      await streamQuery(finalQuery, token, {
        onSnippets: (s) => setSnippets(s),
        onToken: (t) => {
          answerRef.current += t
          setAnswer(answerRef.current)
        },
        onDone: (m) => {
          setLoading(false)
          setMetrics(m)

          // Append to session query log (newest first, cap at MAX_LOG_ENTRIES)
          setQueryLog((prev) => {
            const nextId = prev.length > 0 ? prev[0].id + 1 : 1
            const entry: QueryLogEntry = {
              id: nextId,
              query: finalQuery,
              timestamp: Date.now(),
              metrics: m,
            }
            const updated = [entry, ...prev].slice(0, MAX_LOG_ENTRIES)
            saveQueryLog(updated)
            return updated
          })
        },
        onError: (msg) => {
          setError(msg)
          setLoading(false)
        },
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Connection failed'
      setError(message)
      setLoading(false)
    }
  }

  const onFormSubmit = (e: FormEvent): void => {
    e.preventDefault()
    void handleSubmit()
  }

  const onExampleClick = (ex: string): void => {
    setQuery(ex)
    void handleSubmit(ex)
  }

  const clearLog = (): void => {
    setQueryLog([])
    saveQueryLog([])
  }

  /** Reset all query state back to the clean initial view. */
  const handleClear = (): void => {
    setQuery('')
    setSnippets([])
    setAnswer('')
    setError('')
    setMetrics(null)
    setSubmittedQuery('')
    answerRef.current = ''
    hasAutoSubmittedRef.current = false
    router.replace('/search', { scroll: false })
  }

  /**
   * handleViewFile — triggered when the user clicks "view file" on a SnippetCard.
   *
   * Opens the FileModal immediately in a loading state, then fires the /file
   * request. On success the modal shows the full source with the matched
   * paragraph highlighted; on failure an error toast replaces the spinner.
   */
  const handleViewFile = useCallback(
    async (snippet: CodeSnippet): Promise<void> => {
      const token = backendToken
      // Show the modal right away with a loading indicator
      setOpenFile({ snippet, content: null, loading: true })
      try {
        const content = await fetchFile(snippet.file_path, token)
        setOpenFile({ snippet, content, loading: false })
      } catch (err) {
        // Close the modal and surface the error in the main error banner
        setOpenFile(null)
        setError(
          err instanceof Error ? `Failed to load file: ${err.message}` : 'Failed to load file'
        )
      }
    },
    [backendToken]
  )

  const hasResults = snippets.length > 0 || answer || loading

  return (
    <div className="flex min-h-screen flex-col bg-terminal-bg font-mono">
      {/* ── Header bar ───────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between border-b border-terminal-border bg-terminal-surface px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="cursor-blink font-semibold tracking-tight text-terminal-accent">
            LegacyLens
          </span>
          <span className="hidden text-xs text-terminal-dim sm:block">
            · COBOL code intelligence
          </span>
        </div>
        <AuthButton />
      </header>

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">
        {/* Command prompt header */}
        {!hasResults && (
          <div className="fade-in mb-6">
            <div className="mb-1 text-sm text-terminal-muted">
              <span className="text-terminal-accent">$</span> query_cobol_codebase --index
              legacylens
            </div>
            <h2 className="text-lg font-semibold text-terminal-text">
              Ask anything about the COBOL codebase
            </h2>
            <p className="mt-1 text-xs text-terminal-muted">
              Natural language → exact code snippets with file paths + line numbers
            </p>
          </div>
        )}

        {/* ── Query input ────────────────────────────────────────────────── */}
        <form onSubmit={onFormSubmit} className="mb-6">
          <div className="focus-within:accent-glow-sm flex items-center gap-2 rounded-lg border border-terminal-border bg-terminal-surface px-3 py-2 transition-all focus-within:border-terminal-accent">
            <span className="flex-shrink-0 select-none text-sm font-bold text-terminal-accent">
              {'>'}
            </span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="How does interest calculation work?"
              disabled={loading}
              className="flex-1 bg-transparent text-sm text-terminal-text placeholder-terminal-dim focus:outline-none disabled:opacity-50"
              autoFocus
              aria-label="Query input"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="flex-shrink-0 rounded border border-terminal-border px-3 py-1 text-xs font-medium text-terminal-text transition-all hover:border-terminal-accent hover:text-terminal-accent disabled:cursor-not-allowed disabled:opacity-30"
              aria-label="Run query"
            >
              {loading ? '···' : 'run →'}
            </button>
          </div>
        </form>

        {/* ── Example queries (shown when idle) ─────────────────────────── */}
        {!hasResults && !loading && (
          <div className="fade-in mb-8">
            <p className="mb-3 text-xs text-terminal-muted">{'// example queries:'}</p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {EXAMPLE_QUERIES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => onExampleClick(ex)}
                  className="rounded border border-terminal-border bg-terminal-surface px-3 py-2 text-left text-xs text-terminal-muted transition-all hover:border-terminal-accent hover:bg-terminal-accent-dark hover:text-terminal-accent"
                >
                  <span className="mr-1 text-terminal-dim">$</span> {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Error banner ──────────────────────────────────────────────── */}
        {error && (
          <div className="fade-in mb-4 rounded border border-terminal-error/40 bg-terminal-error/10 px-4 py-3">
            <span className="text-xs font-semibold text-terminal-error">ERROR: </span>
            <span className="text-xs text-terminal-text">{error}</span>
          </div>
        )}

        {/* ── Results section ───────────────────────────────────────────── */}
        {hasResults && (
          <div className="space-y-4">
            {/* Query echo + new search button */}
            <div className="fade-in mb-2 flex items-center justify-between text-xs text-terminal-muted">
              <div>
                <span className="text-terminal-accent">$</span> query:{' '}
                <span className="text-terminal-text">&quot;{submittedQuery}&quot;</span>
              </div>
              <button
                onClick={handleClear}
                disabled={loading}
                className="rounded border border-terminal-border px-2 py-0.5 font-mono text-[10px] text-terminal-dim transition-colors hover:border-terminal-accent hover:text-terminal-accent disabled:opacity-30"
                title="Clear results and start a new search"
              >
                ↩ new search
              </button>
            </div>

            {/* ── Metrics bar (shown as soon as done event arrives) ─────── */}
            {metrics !== null && <MetricsBar metrics={metrics} />}

            {/* Loading state — no snippets yet */}
            {loading && snippets.length === 0 && (
              <div className="fade-in flex items-center gap-3 py-4 text-sm text-terminal-muted">
                <span className="inline-flex gap-1">
                  <span
                    className="h-1 w-1 animate-bounce rounded-full bg-terminal-accent"
                    style={{ animationDelay: '0ms' }}
                  />
                  <span
                    className="h-1 w-1 animate-bounce rounded-full bg-terminal-accent"
                    style={{ animationDelay: '150ms' }}
                  />
                  <span
                    className="h-1 w-1 animate-bounce rounded-full bg-terminal-accent"
                    style={{ animationDelay: '300ms' }}
                  />
                </span>
                <span>searching codebase...</span>
              </div>
            )}

            {/* Snippets */}
            {snippets.length > 0 && (
              <div>
                <p className="mb-3 text-xs text-terminal-muted">
                  {'// '}
                  {snippets.length} snippet
                  {snippets.length !== 1 ? 's' : ''} retrieved
                </p>
                <div className="space-y-3">
                  {snippets.map((s, i) => (
                    <SnippetCard
                      key={`${s.file_path}-${s.start_line}`}
                      snippet={s}
                      index={i}
                      accessToken={backendToken}
                      onViewFile={(snippet) => void handleViewFile(snippet)}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* No results */}
            {!loading && snippets.length === 0 && !error && (
              <div className="fade-in rounded border border-terminal-border bg-terminal-surface px-4 py-6 text-center">
                <p className="text-sm text-terminal-muted">{'// no matching code found'}</p>
                <p className="mt-1 text-xs text-terminal-dim">
                  The codebase may not be indexed yet, or no snippets met the relevance threshold.
                </p>
              </div>
            )}

            {/* Streaming answer */}
            <AnswerPanel answer={answer} loading={loading} metrics={metrics} />
          </div>
        )}

        {/* ── Session query log (shown after 2+ queries) ────────────────── */}
        <SessionQueryLog log={queryLog} onClear={clearLog} />
      </main>

      {/* ── FileModal overlay ─────────────────────────────────────────────── */}
      {openFile !== null &&
        (openFile.loading ? (
          /* Loading state — dim overlay with spinner while /file fetches */
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75">
            <div className="flex flex-col items-center gap-3">
              <span className="inline-flex gap-1.5">
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="h-2 w-2 animate-bounce rounded-full bg-terminal-accent"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </span>
              <p className="font-mono text-xs text-terminal-muted">
                loading {openFile.snippet.file_path.split('/').pop()}…
              </p>
            </div>
          </div>
        ) : openFile.content !== null ? (
          /* Loaded — show the full file with matched paragraph highlighted */
          <FileModal
            fileContent={openFile.content}
            snippet={openFile.snippet}
            onClose={() => setOpenFile(null)}
          />
        ) : null)}

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <footer className="border-t border-terminal-border px-4 py-2">
        <p className="text-center text-xs text-terminal-dim">
          LegacyLens · Gauntlet AI Week 3 ·{' '}
          <span className="text-terminal-accent">gpt-4o-mini + voyage-code-2 + pinecone</span>
        </p>
      </footer>
    </div>
  )
}
