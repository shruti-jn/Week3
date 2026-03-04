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
 *   ● PAYMNT-CALC  score: 0.91  payroll/PAYROLL.cob · lines 142–178
 *   ────────────────────────────────────────────────
 *     142 │ PAYMNT-CALC.
 *     143 │     COMPUTE WS-GROSS-PAY = ...
 *   ────────────────────────────────────────────────
 *
 *   > Generating answer...
 *     The PAYMNT-CALC paragraph handles payroll calculation by...
 */

import { useState, useRef, type FormEvent } from "react";
import { useSession } from "next-auth/react";
import type { Session } from "next-auth";
import AuthButton from "@/components/AuthButton";
import { streamQuery, type CodeSnippet } from "@/lib/api";

/** Extends the default NextAuth session type to include our access token. */
interface LegacySession extends Session {
  accessToken?: string;
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

  // Extract the paragraph name from the chunk ID or file path
  const fileName = snippet.file_path.split("/").pop() ?? snippet.file_path;
  const paragraphLines = snippet.content
    .split("\n")
    .slice(0, 2)
    .join(" ")
    .trim();
  const paragraphName =
    paragraphLines.match(/^([A-Z0-9-]+)\./)?.[1] ?? fileName.replace(".cob", "").toUpperCase();

  return (
    <div className="fade-in rounded-lg border border-terminal-border bg-terminal-surface overflow-hidden">
      {/* Card header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-white/5 transition-colors"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-terminal-accent font-bold text-sm flex-shrink-0">●</span>
          <span className="text-terminal-text font-semibold text-sm tracking-wide truncate">
            {paragraphName}
          </span>
          <span className="hidden sm:block text-terminal-muted text-xs truncate">
            {snippet.file_path}
            <span className="text-terminal-dim">
              {" "}· lines {snippet.start_line}–{snippet.end_line}
            </span>
          </span>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0 ml-3">
          <span className="text-xs font-mono">
            <span className="text-terminal-muted">score: </span>
            <span className="text-terminal-accent">{snippet.score.toFixed(3)}</span>
          </span>
          <span className="text-terminal-muted text-xs">{expanded ? "▲" : "▼"}</span>
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

/** Streaming answer panel — shows GPT answer as it arrives token by token. */
function AnswerPanel({
  answer,
  loading,
  queryTimeMs,
}: {
  answer: string;
  loading: boolean;
  queryTimeMs: number | null;
}): React.JSX.Element | null {
  if (!answer && !loading) return null;

  return (
    <div className="fade-in rounded-lg border border-terminal-border bg-terminal-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-terminal-accent text-sm font-semibold">▶ Answer</span>
        {loading && (
          <span className="inline-flex gap-1">
            <span className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce" style={{ animationDelay: "0ms" }} />
            <span className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce" style={{ animationDelay: "150ms" }} />
            <span className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce" style={{ animationDelay: "300ms" }} />
          </span>
        )}
        {!loading && queryTimeMs !== null && (
          <span className="text-xs text-terminal-muted">
            {(queryTimeMs / 1000).toFixed(2)}s
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
  const [queryTimeMs, setQueryTimeMs] = useState<number | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState("");

  // Keep a ref to the latest answer so the closure in streamQuery always
  // appends to the most recent value (avoids stale closure issue).
  const answerRef = useRef("");

  const handleSubmit = async (q?: string): Promise<void> => {
    const finalQuery = (q ?? query).trim();
    if (!finalQuery || loading) return;

    const token = session?.accessToken ?? "";

    setLoading(true);
    setSnippets([]);
    setAnswer("");
    setError("");
    setQueryTimeMs(null);
    setSubmittedQuery(finalQuery);
    answerRef.current = "";

    try {
      await streamQuery(finalQuery, token, {
        onSnippets: (s) => setSnippets(s),
        onToken: (t) => {
          answerRef.current += t;
          setAnswer(answerRef.current);
        },
        onDone: (ms) => {
          setLoading(false);
          setQueryTimeMs(ms);
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
              Natural language → exact code snippets with file paths + line numbers
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
              // example queries:
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

            {/* Loading state — no snippets yet */}
            {loading && snippets.length === 0 && (
              <div className="fade-in flex items-center gap-3 text-sm text-terminal-muted py-4">
                <span className="inline-flex gap-1">
                  <span className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="h-1 w-1 rounded-full bg-terminal-accent animate-bounce" style={{ animationDelay: "300ms" }} />
                </span>
                <span>searching codebase...</span>
              </div>
            )}

            {/* Snippets */}
            {snippets.length > 0 && (
              <div>
                <p className="mb-3 text-xs text-terminal-muted">
                  // {snippets.length} snippet{snippets.length !== 1 ? "s" : ""} retrieved
                </p>
                <div className="space-y-3">
                  {snippets.map((s, i) => (
                    <SnippetCard key={`${s.file_path}-${s.start_line}`} snippet={s} index={i} />
                  ))}
                </div>
              </div>
            )}

            {/* No results */}
            {!loading && snippets.length === 0 && !error && (
              <div className="fade-in rounded border border-terminal-border bg-terminal-surface px-4 py-6 text-center">
                <p className="text-sm text-terminal-muted">
                  // no matching code found
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
              queryTimeMs={queryTimeMs}
            />
          </div>
        )}
      </main>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <footer className="border-t border-terminal-border px-4 py-2">
        <p className="text-center text-xs text-terminal-dim">
          LegacyLens · Gauntlet AI Week 3 ·{" "}
          <span className="text-terminal-accent">
            gpt-4o-mini + text-embedding-3-small + pinecone
          </span>
        </p>
      </footer>
    </div>
  );
}
