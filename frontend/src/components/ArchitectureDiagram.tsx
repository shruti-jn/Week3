'use client'

/**
 * ArchitectureDiagram — animated RAG pipeline visualizer for LegacyLens.
 *
 * Renders the two Mermaid flowcharts from docs/RAG_ARCHITECTURE.md inside
 * a terminal-themed page. The diagram content is passed in as props from the
 * Server Component parent (which reads the markdown file at request time),
 * so the diagram always reflects the current state of the doc.
 *
 * Two pipelines are displayed via a tab switcher:
 *   INGESTION — COBOL files → chunking → embedding → Pinecone upsert
 *   QUERY     — user query → embedding → retrieval → reranking → LLM → SSE
 *
 * Mermaid is dynamically imported (browser-only) to keep it out of the
 * SSR bundle. The dark theme + terminal-themed classDef overrides are
 * injected into the mermaid config so the diagram matches the CRT aesthetic.
 *
 * @param ingestionMermaid - Preprocessed Mermaid string for the ingestion pipeline
 * @param queryMermaid     - Preprocessed Mermaid string for the query pipeline
 */

import { useEffect, useRef, useState } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

type Pipeline = 'ingestion' | 'query'

interface Props {
  /** Mermaid flowchart string for the ingestion (offline) pipeline. */
  ingestionMermaid: string
  /** Mermaid flowchart string for the query (online) pipeline. */
  queryMermaid: string
}

// ── Metrics (sourced from RAG_ARCHITECTURE.md corpus stats) ──────────────────

const METRICS = [
  { label: 'vectors indexed', value: '10,029' },
  { label: 'COBOL files scanned', value: '577' },
  { label: 'embedding model', value: 'voyage-code-2 (1536 dims)' },
  { label: 'rerank weights', value: '0.7 × cosine + 0.3 × keyword' },
  { label: 'cosine threshold', value: '0.65' },
  { label: 'confidence gate', value: 'top ≥ 0.66 AND avg ≥ 0.60' },
  { label: 'precision@5', value: '~90% (voyage-code-2 + Q&A framing)' },
  { label: 'end-to-end latency', value: '2.51s (warm)' },
  { label: 'embed latency (p50)', value: '165ms' },
  { label: 'retrieve latency', value: '72ms (Pinecone)' },
  { label: 'LLM latency (p50)', value: '2,274ms (GPT-4o-mini)' },
] as const

// ── Mermaid config ────────────────────────────────────────────────────────────

const MERMAID_CONFIG = {
  startOnLoad: false,
  theme: 'dark' as const,
  themeVariables: {
    darkMode: true,
    background: '#0a0a0a',
    primaryColor: '#111111',
    primaryTextColor: '#00ff88',
    primaryBorderColor: '#00ff88',
    lineColor: '#00ff88',
    secondaryColor: '#111111',
    tertiaryColor: '#0a0a0a',
    edgeLabelBackground: '#0a0a0a',
    fontSize: '13px',
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    // Node text colors
    nodeBorder: '#00ff88',
    clusterBkg: '#111111',
    titleColor: '#00ff88',
  },
  flowchart: {
    useMaxWidth: true,
    htmlLabels: false,
    curve: 'linear' as const,
  },
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ArchitectureDiagram({ ingestionMermaid, queryMermaid }: Props): React.JSX.Element {
  const [activePipeline, setActivePipeline] = useState<Pipeline>('ingestion')
  const [renderKey, setRenderKey] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  // Both strings empty → the markdown file wasn't found or had no Mermaid blocks
  const hasContent = ingestionMermaid.length > 0 || queryMermaid.length > 0

  const activeMermaid = activePipeline === 'ingestion' ? ingestionMermaid : queryMermaid

  // Switch tab — bump renderKey to remount the mermaid div so the new diagram
  // is rendered fresh (mermaid mutates the div's innerHTML in-place).
  const handleTabSwitch = (pipeline: Pipeline): void => {
    setActivePipeline(pipeline)
    setRenderKey((k) => k + 1)
  }

  // Dynamic import of mermaid (browser-only). Re-runs whenever renderKey changes
  // (i.e., on every tab switch) to re-render the new diagram string.
  useEffect(() => {
    if (!hasContent || !activeMermaid) return
    if (typeof window === 'undefined') return

    let cancelled = false

    import('mermaid').then((m) => {
      if (cancelled) return
      m.default.initialize(MERMAID_CONFIG)
      // mermaid.run() looks for all .mermaid divs in the DOM and renders them.
      // The querySelector scopes it to only the div we care about so other
      // potential mermaid elements on the page are not disturbed.
      void m.default.run({ querySelector: '.mermaid' })
    })

    return (): void => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [renderKey])

  return (
    <div className="flex flex-col gap-8">
      {/* ── Page heading ────────────────────────────────────────────────────── */}
      <div>
        <h1 className="terminal-text text-xl font-semibold tracking-tight">RAG Architecture</h1>
        <p className="mt-1 text-sm text-terminal-muted">
          {'// pipeline flow diagram · sourced from docs/RAG_ARCHITECTURE.md'}
        </p>
      </div>

      {/* ── Fallback: doc not found ──────────────────────────────────────────── */}
      {!hasContent && (
        <div className="rounded border border-terminal-error/40 bg-terminal-bg p-6 text-center">
          <p className="text-terminal-error">architecture document not found</p>
          <p className="mt-1 text-xs text-terminal-muted">
            expected: docs/RAG_ARCHITECTURE.md (relative to repo root)
          </p>
        </div>
      )}

      {/* ── Diagram panel ───────────────────────────────────────────────────── */}
      {hasContent && (
        <div className="rounded border border-terminal-border bg-terminal-surface">
          {/* Tab switcher */}
          <div className="flex border-b border-terminal-border">
            {(
              [
                { id: 'ingestion' as const, label: 'INGESTION PIPELINE' },
                { id: 'query' as const, label: 'QUERY PIPELINE' },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                role="button"
                aria-pressed={activePipeline === tab.id}
                onClick={() => handleTabSwitch(tab.id)}
                className={[
                  'flex-1 px-4 py-2.5 text-xs font-medium tracking-wider transition-colors',
                  '-mb-px border-b-2',
                  activePipeline === tab.id
                    ? 'border-terminal-accent text-terminal-accent'
                    : 'border-transparent text-terminal-muted hover:text-terminal-text',
                ].join(' ')}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Mermaid render area */}
          <div className="mermaid-terminal overflow-x-auto p-6" ref={containerRef}>
            {/*
              The key forces React to unmount+remount this div on every tab switch,
              which clears the mermaid-rendered SVG and lets mermaid.run() start fresh.
            */}
            <div
              key={`mermaid-${activePipeline}-${renderKey}`}
              className="mermaid fade-in"
              data-testid="mermaid-container"
              suppressHydrationWarning
            >
              {activeMermaid}
            </div>
          </div>

          {/* Pipeline label */}
          <div className="border-t border-terminal-border px-6 py-2">
            <p className="text-xs text-terminal-dim">
              <span className="text-terminal-accent">{'>'}</span>{' '}
              {activePipeline === 'ingestion'
                ? 'LANE A: offline ingestion — runs once per corpus, re-run on updates'
                : 'LANE B: online query — runs per user request, ~2.51s end-to-end'}
            </p>
          </div>
        </div>
      )}

      {/* ── Performance metrics ──────────────────────────────────────────────── */}
      <div className="rounded border border-terminal-border bg-terminal-surface">
        <div className="border-b border-terminal-border px-4 py-2.5">
          <h2 className="text-xs font-medium tracking-wider text-terminal-accent">
            PERFORMANCE METRICS
          </h2>
          <p className="mt-0.5 text-xs text-terminal-dim">
            {'// gnucobol-contrib corpus · 2026-03-05'}
          </p>
        </div>
        <div className="p-4">
          <table className="w-full text-xs">
            <tbody>
              {METRICS.map(({ label, value }) => (
                <tr key={label} className="border-b border-terminal-border/40 last:border-0">
                  <td className="py-1.5 pr-6 text-terminal-muted">{label}</td>
                  <td className="py-1.5 font-medium text-terminal-accent">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
