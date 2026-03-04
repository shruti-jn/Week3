"use client";

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

import { useState, useRef, useEffect, type FormEvent } from "react";
import { useSession } from "next-auth/react";
import type { Session } from "next-auth";
import AuthButton from "@/components/AuthButton";
import { streamQuery, type CodeSnippet, type QueryMetrics } from "@/lib/api";

/** Extends the default NextAuth session type to include our access token. */
interface LegacySession extends Session {
  accessToken?: string;
}

/**
 * One entry in the session query log.
 *
 * Persisted to localStorage so the log survives page reloads within
 * the same browser session.
 */
interface QueryLogEntry {
  id: number;
  query: string;
  timestamp: number;
  metrics: QueryMetrics;
}

const SESSION_LOG_KEY = "legacylens_query_log";
const MAX_LOG_ENTRIES = 20;

// ── localStorage helpers ──────────────────────────────────────────────────────

function loadQueryLog(): QueryLogEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(SESSION_LOG_KEY);
    return raw ? (JSON.parse(raw) as QueryLogEntry[]) : [];
  } catch {
    return [];
  }
}

function saveQueryLog(log: QueryLogEntry[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(SESSION_LOG_KEY, JSON.stringify(log));
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
  content: string;
  startLine: number;
}): React.JSX.Element {
  const lines = content.split("\n");
  return (
    <div className="code-block overflow-x-auto rounded-b">
      <table className="w-full border-collapse">
        <tbody>
          {lines.map((line, i) => (
            <tr key={i} className="hover:bg-white/5">
              <td className="code-line-number select-none px-3 py-0.5 text-right text-xs">
                {startLine + i}
              </td>
              <td className="px-3 py-0.5 text-xs">
                <pre className="whitespace-pre font-mono">{line || " "}</pre>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A single result card showing a matched COBOL code snippet. */
function SnippetCard({
  snippet,
  index,
}: {
  snippet: CodeSnippet;
  index: number;
}): React.JSX.Element {
  const [expanded, setExpanded] = useState(index === 0); // first result open by default

  const fileName = snippet.file_path.split("/").pop() ?? snippet.file_path;
  const paragraphLines = snippet.content
    .split("\n")
    .slice(0, 2)
    .join(" ")
    .trim();
  const paragraphName =
    paragraphLines.match(/^([A-Z0-9-]+)\./)?.[1] ??
    fileName.replace(".cob", "").toUpperCase();

  return (
    <div className="fade-in rounded-lg border border-terminal-border bg-terminal-surface overflow-hidden">
      {/* Card header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-white/5 transition-colors"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-terminal-accent font-bold text-sm flex-shrink-0">
            ●
          </span>
          <span className="text-terminal-text font-semibold text-sm tracking-wide truncate">
            {paragraphName}
          </span>
          {/* chunk_type badge */}
          <span
            className={`flex-shrink-0 rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider ${
              snippet.chunk_type === "paragraph"
                ? "bg-terminal-accent/15 text-terminal-accent border border-terminal-accent/30"
                : "bg-terminal-muted/15 text-terminal-muted border border-terminal-muted/30"
            }`}
            title={
              snippet.chunk_type === "paragraph"
                ? "Split at a COBOL paragraph boundary"
                : "Fixed-size chunk (no paragraph boundary found)"
            }
          >
            {snippet.chunk_type === "paragraph" ? "para" : "fixed"}
          </span>
          <span className="hidden sm:block text-terminal-muted text-xs truncate">
            {snippet.file_path}
            <span className="text-terminal-dim">
              {" "}
              · lines {snippet.start_line}–{snippet.end_line}
            </span>
          </span>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0 ml-3">
          <span className="text-xs font-mono">
            <span className="text-terminal-muted">score: </span>
            <span className="text-terminal-accent">
              {snippet.score.toFixed(3)}
            </span>
          </span>
          <span className="text-terminal-muted text-xs">
            {expanded ? "▲" : "▼"}
          </span>
        </div>
      </button>

      {/* File path on mobile */}
      <div className="sm:hidden px-4 pb-2 text-xs text-terminal-muted truncate">
        {snippet.file_path} · lines {snippet.start_line}–{snippet.end_line}
      </div>

      {/* Code body */}
      {expanded && (
        <CodeBlock content={snippet.content} startLine={snippet.start_line} />
      )}
    </div>
  );
}

/**
 * MetricsBar — compact pipeline analytics strip shown after each query.
 *
 * Two rows:
 *   Row 1: total time · top score · avg similarity · files hit · chunk count
 *   Row 2: step-level timings (embed / retrieve / rerank / llm)
 */
function MetricsBar({ metrics }: { metrics: QueryMetrics }): React.JSX.Element {
  const totalSec = (metrics.query_time_ms / 1000).toFixed(2);

  return (
    <div className="fade-in rounded-lg border border-terminal-border bg-terminal-surface/60 px-4 py-3 text-xs font-mono">
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
          value={(metrics.top_score * 100).toFixed(1) + "%"}
          highlight={metrics.top_score >= 0.85}
          title="Highest similarity score among returned snippets"
        />
        <MetricPill
          label="avg sim"
          value={(metrics.avg_similarity * 100).toFixed(1) + "%"}
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
  );
}

function MetricPill({
  label,
  value,
  highlight = false,
  title,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  title?: string;
}): React.JSX.Element {
  return (
    <span className="flex items-center gap-1.5" title={title}>
      <span className="text-terminal-dim">{label}:</span>
      <span
        className={
          highlight ? "text-terminal-accent font-semibold" : "text-terminal-text"
        }
      >
        {value}
      </span>
    </span>
  );
}

function StepTiming({
  label,
  ms,
}: {
  label: string;
  ms: number;
}): React.JSX.Element {
  return (
    <span>
      <span className="text-terminal-dim">{label} </span>
      <span className="text-terminal-muted">{ms.toFixed(0)}ms</span>
    </span>
  );
}

/** Streaming answer panel — shows GPT answer as it arrives token by token. */
function AnswerPanel({
  answer,
  loading,
  metrics,
}: {
  answer: string;
  loading: boolean;
  metrics: QueryMetrics | null;
}): React.JSX.Element | null {
  if (!answer && !loading) return null;

  return (
    <div className="fade-in rounded-lg border border-terminal-border bg-terminal-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-terminal-accent text-sm font-semibold">
          ▶ Answer
        </span>
        {loading && (
          <span className="inline-flex gap-1">
            <span
              className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce"
              style={{ animationDelay: "0ms" }}
            />
            <span
              className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce"
              style={{ animationDelay: "150ms" }}
            />
            <span
              className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce"
              style={{ animationDelay: "300ms" }}
            />
          </span>
        )}
        {!loading && metrics !== null && (
          <span className="text-xs text-terminal-muted">
            {(metrics.query_time_ms / 1000).toFixed(2)}s
          </span>
        )}
      </div>
      <p className="text-sm text-terminal-text leading-relaxed whitespace-pre-wrap">
        {answer}
        {loading && <span className="cursor-blink" />}
      </p>
    </div>
  );
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
  log: QueryLogEntry[];
  onClear: () => void;
}): React.JSX.Element | null {
  if (log.length < 2) return null;

  return (
    <div className="fade-in mt-6">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs text-terminal-muted font-mono">
          {"// "}session query log ({log.length} queries)
        </p>
        <button
          onClick={onClear}
          className="text-[10px] text-terminal-dim hover:text-terminal-muted transition-colors font-mono"
          title="Clear session log"
        >
          clear
        </button>
      </div>
      <div className="rounded-lg border border-terminal-border bg-terminal-surface overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-terminal-border bg-terminal-bg/40">
                <th className="px-3 py-2 text-left text-terminal-dim font-normal w-6">
                  #
                </th>
                <th className="px-3 py-2 text-left text-terminal-dim font-normal">
                  query
                </th>
                <th className="px-3 py-2 text-right text-terminal-dim font-normal whitespace-nowrap">
                  time
                </th>
                <th className="px-3 py-2 text-right text-terminal-dim font-normal whitespace-nowrap">
                  top
                </th>
                <th className="px-3 py-2 text-right text-terminal-dim font-normal whitespace-nowrap">
                  avg
                </th>
                <th className="px-3 py-2 text-right text-terminal-dim font-normal whitespace-nowrap">
                  files
                </th>
                <th className="px-3 py-2 text-right text-terminal-dim font-normal whitespace-nowrap">
                  chunks
                </th>
              </tr>
            </thead>
            <tbody>
              {log.map((entry, i) => (
                <tr
                  key={entry.id}
                  className={`border-b border-terminal-border/40 last:border-0 ${
                    i === 0 ? "bg-terminal-accent/5" : ""
                  }`}
                >
                  <td className="px-3 py-2 text-terminal-dim">{entry.id}</td>
                  <td className="px-3 py-2 text-terminal-text max-w-[200px] truncate">
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
  );
}

// ── Suggested queries — from golden eval set, min_score ≥ 0.70 ────────────────
const EXAMPLE_QUERIES = [
  "How do you sort a file in COBOL?",
  "DES encryption algorithm implementation",
  "How do you insert a record into a database?",
  "Parse HTML form data in a CGI COBOL program",
];

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SearchPage(): React.JSX.Element {
  const { data: rawSession } = useSession();
  const session = rawSession as LegacySession | null;

  const [query, setQuery] = useState("");
  const [snippets, setSnippets] = useState<CodeSnippet[]>([]);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [metrics, setMetrics] = useState<QueryMetrics | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [queryLog, setQueryLog] = useState<QueryLogEntry[]>([]);

  // Keep a ref to the latest answer so the closure in streamQuery always
  // appends to the most recent value (avoids stale closure issue).
  const answerRef = useRef("");

  // Load persisted query log from localStorage on mount
  useEffect(() => {
    setQueryLog(loadQueryLog());
  }, []);

  const handleSubmit = async (q?: string): Promise<void> => {
    const finalQuery = (q ?? query).trim();
    if (!finalQuery || loading) return;

    const token = session?.accessToken ?? "";

    setLoading(true);
    setSnippets([]);
    setAnswer("");
    setError("");
    setMetrics(null);
    setSubmittedQuery(finalQuery);
    answerRef.current = "";

    try {
      await streamQuery(finalQuery, token, {
        onSnippets: (s) => setSnippets(s),
        onToken: (t) => {
          answerRef.current += t;
          setAnswer(answerRef.current);
        },
        onDone: (m) => {
          setLoading(false);
          setMetrics(m);

          // Append to session query log (newest first, cap at MAX_LOG_ENTRIES)
          setQueryLog((prev) => {
            const nextId = prev.length > 0 ? prev[0].id + 1 : 1;
            const entry: QueryLogEntry = {
              id: nextId,
              query: finalQuery,
              timestamp: Date.now(),
              metrics: m,
            };
            const updated = [entry, ...prev].slice(0, MAX_LOG_ENTRIES);
            saveQueryLog(updated);
            return updated;
          });
        },
        onError: (msg) => {
          setError(msg);
          setLoading(false);
        },
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Connection failed";
      setError(message);
      setLoading(false);
    }
  };

  const onFormSubmit = (e: FormEvent): void => {
    e.preventDefault();
    void handleSubmit();
  };

  const onExampleClick = (ex: string): void => {
    setQuery(ex);
    void handleSubmit(ex);
  };

  const clearLog = (): void => {
    setQueryLog([]);
    saveQueryLog([]);
  };

  const hasResults = snippets.length > 0 || answer || loading;

  return (
    <div className="flex min-h-screen flex-col bg-terminal-bg font-mono">
      {/* ── Header bar ───────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between border-b border-terminal-border bg-terminal-surface px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="text-terminal-accent font-semibold tracking-tight cursor-blink">
            LegacyLens
          </span>
          <span className="hidden sm:block text-terminal-dim text-xs">
            · COBOL code intelligence
          </span>
        </div>
        <AuthButton />
      </header>

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <main className="flex-1 px-4 py-8 max-w-4xl mx-auto w-full">
        {/* Command prompt header */}
        {!hasResults && (
          <div className="mb-6 fade-in">
            <div className="text-terminal-muted text-sm mb-1">
              <span className="text-terminal-accent">$</span>{" "}
              query_cobol_codebase --index legacylens
            </div>
            <h2 className="text-terminal-text text-lg font-semibold">
              Ask anything about the COBOL codebase
            </h2>
            <p className="mt-1 text-xs text-terminal-muted">
              Natural language → exact code snippets with file paths + line
              numbers
            </p>
          </div>
        )}

        {/* ── Query input ────────────────────────────────────────────────── */}
        <form onSubmit={onFormSubmit} className="mb-6">
          <div className="flex items-center gap-2 rounded-lg border border-terminal-border bg-terminal-surface px-3 py-2 transition-all focus-within:border-terminal-accent focus-within:accent-glow-sm">
            <span className="text-terminal-accent font-bold flex-shrink-0 text-sm select-none">
              {">"}
            </span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="How does interest calculation work?"
              disabled={loading}
              className="flex-1 bg-transparent text-terminal-text placeholder-terminal-dim text-sm focus:outline-none disabled:opacity-50"
              autoFocus
              aria-label="Query input"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="flex-shrink-0 rounded border border-terminal-border px-3 py-1 text-xs font-medium text-terminal-text transition-all hover:border-terminal-accent hover:text-terminal-accent disabled:opacity-30 disabled:cursor-not-allowed"
              aria-label="Run query"
            >
              {loading ? "···" : "run →"}
            </button>
          </div>
        </form>

        {/* ── Example queries (shown when idle) ─────────────────────────── */}
        {!hasResults && !loading && (
          <div className="mb-8 fade-in">
            <p className="mb-3 text-xs text-terminal-muted">
              {"// example queries:"}
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {EXAMPLE_QUERIES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => onExampleClick(ex)}
                  className="rounded border border-terminal-border bg-terminal-surface px-3 py-2 text-left text-xs text-terminal-muted transition-all hover:border-terminal-accent hover:text-terminal-accent hover:bg-terminal-accent-dark"
                >
                  <span className="text-terminal-dim mr-1">$</span> {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Error banner ──────────────────────────────────────────────── */}
        {error && (
          <div className="mb-4 fade-in rounded border border-terminal-error/40 bg-terminal-error/10 px-4 py-3">
            <span className="text-terminal-error text-xs font-semibold">
              ERROR:{" "}
            </span>
            <span className="text-terminal-text text-xs">{error}</span>
          </div>
        )}

        {/* ── Results section ───────────────────────────────────────────── */}
        {hasResults && (
          <div className="space-y-4">
            {/* Query echo */}
            <div className="text-xs text-terminal-muted mb-2 fade-in">
              <span className="text-terminal-accent">$</span> query:{" "}
              <span className="text-terminal-text">
                &quot;{submittedQuery}&quot;
              </span>
            </div>

            {/* ── Metrics bar (shown as soon as done event arrives) ─────── */}
            {metrics !== null && <MetricsBar metrics={metrics} />}

            {/* Loading state — no snippets yet */}
            {loading && snippets.length === 0 && (
              <div className="fade-in flex items-center gap-3 text-sm text-terminal-muted py-4">
                <span className="inline-flex gap-1">
                  <span
                    className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce"
                    style={{ animationDelay: "0ms" }}
                  />
                  <span
                    className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce"
                    style={{ animationDelay: "150ms" }}
                  />
                  <span
                    className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce"
                    style={{ animationDelay: "300ms" }}
                  />
                </span>
                <span>searching codebase...</span>
              </div>
            )}

            {/* Snippets */}
            {snippets.length > 0 && (
              <div>
                <p className="mb-3 text-xs text-terminal-muted">
                  {"// "}
                  {snippets.length} snippet
                  {snippets.length !== 1 ? "s" : ""} retrieved
                </p>
                <div className="space-y-3">
                  {snippets.map((s, i) => (
                    <SnippetCard
                      key={`${s.file_path}-${s.start_line}`}
                      snippet={s}
                      index={i}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* No results */}
            {!loading && snippets.length === 0 && !error && (
              <div className="fade-in rounded border border-terminal-border bg-terminal-surface px-4 py-6 text-center">
                <p className="text-sm text-terminal-muted">
                  {"// no matching code found"}
                </p>
                <p className="mt-1 text-xs text-terminal-dim">
                  The codebase may not be indexed yet, or no snippets met the
                  relevance threshold.
                </p>
              </div>
            )}

            {/* Streaming answer */}
            <AnswerPanel
              answer={answer}
              loading={loading}
              metrics={metrics}
            />
          </div>
        )}

        {/* ── Session query log (shown after 2+ queries) ────────────────── */}
        <SessionQueryLog log={queryLog} onClear={clearLog} />
      </main>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <footer className="border-t border-terminal-border px-4 py-2">
        <p className="text-center text-xs text-terminal-dim">
          LegacyLens · Gauntlet AI Week 3 ·{" "}
          <span className="text-terminal-accent">
            gpt-4o-mini + voyage-code-2 + pinecone
          </span>
        </p>
      </footer>
    </div>
  );
}
