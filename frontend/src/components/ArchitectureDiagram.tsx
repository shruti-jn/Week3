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

// ── Tooltip types ─────────────────────────────────────────────────────────────

interface TooltipState {
  x: number
  y: number
  title: string
  detail: string
}

// ── Node details map (keyed by Mermaid source node variable) ─────────────────
// Each entry maps the SVG node ID (e.g. "A1", "D4") to human-readable tooltip
// content. After mermaid.run() resolves, we attach mouseenter/mousemove/
// mouseleave listeners to each g.node SVG element and show this on hover.

const NODE_DETAILS: Record<string, { title: string; detail: string }> = {
  // ── Ingestion pipeline ────────────────────────────────────────────────────
  A1: {
    title: 'Scan COBOL corpus',
    detail: '577 .cob/.cbl files from gnucobol-contrib\nfile_scanner.py collects path, size, mtime',
  },
  A2: {
    title: 'Detect boundaries',
    detail:
      'chunker.py: scan for PROCEDURE DIVISION\nthen named paragraph labels:\n  single uppercase token + period, alone on line\nSECTION headers also detected',
  },
  D1: {
    title: 'Boundary found?',
    detail:
      'Named paragraphs/sections in PROCEDURE DIVISION?\nYES → semantic chunks\nNO  → 50-line fallback windows',
  },
  A3: {
    title: 'Semantic chunks',
    detail:
      'One chunk per named paragraph or SECTION\nSpan: label line → next boundary\nVector ID: file_path::PARAGRAPH-NAME',
  },
  A4: {
    title: 'Fallback chunks',
    detail:
      '50-line sliding windows · 10-line overlap\nis_fallback=True in metadata\nVector ID: file_path::chunk_N\nNo Q&A framing applied',
  },
  A5: {
    title: 'Quality filter',
    detail:
      'chunk_filter.py — must pass BOTH checks:\n① ≥4 non-trivial lines\n  (strip label, comments, blanks, separators)\n② ≥1 logic verb:\n  MOVE · COMPUTE · PERFORM · IF · EVALUATE\n  READ · WRITE · CALL · ADD · SUBTRACT ...',
  },
  D2: {
    title: 'Pass filter?',
    detail:
      'Chunk passes quality gate?\nYES → embed\nNO  → drop + log\nRejection: 50–86% on DB2/PostgreSQL files\n(exit trampolines account for ~50% of chunks)',
  },
  A6: {
    title: 'Drop + log',
    detail:
      'Chunk rejected — not indexed\nLogged: file path + paragraph name\nCommon rejects:\n  EXIT. trampolines\n  single-line constants\n  HTML stubs ("<BR>")',
  },
  D3: {
    title: 'Q&A signal?',
    detail:
      'Meaningful inline comment found?\n(*> free-format or column-7 *)\nYES → build Q&A text (+0.10 cosine boost)\nNO  → embed raw code',
  },
  A7: {
    title: 'Build Q&A text',
    detail:
      '"What does PARA do?\\nThe PARA..."\nBuilt from paragraph name + first *> comment\nCosine boost: ~0.69 → 0.77–0.82\nEmbedding-only; raw code stored in metadata',
  },
  A8: {
    title: 'Raw chunk text',
    detail: 'No Q&A enrichment\nRaw COBOL embedded as-is\nTypical scores: 0.45–0.55 for NL queries',
  },
  A9: {
    title: 'Embed document',
    detail:
      'Model: voyage-code-2\ninput_type="document" · 1536 dims\n$0.06/1M tokens · ~165ms p50\nTrained on NL ↔ code pairs\n(text-embedding-3-small scored 0.25–0.34 on COBOL)',
  },
  A10: {
    title: 'Vector ID',
    detail:
      'Named: file_path::PARAGRAPH-NAME\nFallback: file_path::chunk_N\nGuaranteed unique per Pinecone index',
  },
  A11: {
    title: 'Upsert Pinecone',
    detail:
      'Serverless Pinecone · cosine · 1536 dims\nMetadata: file_path, paragraph_name,\n  start_line, end_line, content,\n  chunk_index, is_fallback\nnull → "" (Pinecone rejects null values)\n10,029 vectors indexed (gnucobol-contrib)',
  },
  // ── Query pipeline ────────────────────────────────────────────────────────
  B1: {
    title: 'User query',
    detail:
      'Plain-English question about the COBOL codebase\ne.g. "How do I calculate interest?"\nAuthenticated via GitHub OAuth + JWT',
  },
  B2: {
    title: 'query_enrich()',
    detail:
      'Append " COBOL" if "cobol" absent (case-insensitive)\nFix for synonym gap:\n  "process" → retrieves "parse" paragraphs\nNo other enrichment in current impl',
  },
  B3: {
    title: 'Embed query',
    detail:
      'Model: voyage-code-2\ninput_type="query" (asymmetric retrieval)\n1536 dims · 165ms p50\nDifferent internal repr vs. document\n→ better recall vs. symmetric embedding',
  },
  B4: {
    title: 'Pinecone top_k=5',
    detail:
      'Cosine ANN search\ntop_k=5 (reduced from 10 → saves 150–300ms)\nReturns: vector IDs + cosine scores + metadata\nPinecone latency: 72ms',
  },
  B5: {
    title: 'Drop low cosine',
    detail:
      'Cosine threshold: 0.65\nCandidates below threshold dropped\nbefore reranking\nPrevents noisy chunks polluting results',
  },
  B6: {
    title: 'Rerank 0.7/0.3',
    detail:
      'combined = 0.7 × cosine + 0.3 × keyword_overlap\nKeyword: query terms (stopwords removed,\n  hyphens split) found in chunk content\nCOBOL verbs NOT stopwords\n  (COMPUTE/PERFORM are valid signal)\nReranker: <1ms',
  },
  B7: {
    title: 'SSE snippets event',
    detail:
      'snippets SSE event emitted to client\nTop-5 ranked results with:\n  file path · paragraph name\n  line numbers · combined score\nShown in UI before LLM answer arrives',
  },
  B8: {
    title: 'Confidence metrics',
    detail:
      'top_score = highest snippet combined score\navg_similarity = mean cosine score (top-5)\nInput to confidence gate\nTypical range: 0.56–0.82',
  },
  D4: {
    title: 'Confidence gate?',
    detail:
      'top_score ≥ 0.66 AND avg_similarity ≥ 0.60\nYES → send to LLM\nNO  → fallback response\nPrevents hallucination on weakly-grounded\nretrieval (no LLM call → saves cost)',
  },
  B9: {
    title: 'Fallback response',
    detail:
      '"I don\'t have enough relevant code context..."\nNo LLM call (saves latency + cost)\nNormal done SSE event still emitted\nfor observability',
  },
  B10: {
    title: 'Keep top 3',
    detail:
      'Context pruning: top-3 chunks → LLM\n(top-5 still shown in UI)\nCuts input tokens ~40%\nReduces TTFT without accuracy loss\n(reranker already ranked best-first)',
  },
  B11: {
    title: 'Generate answer',
    detail:
      'GPT-4o-mini · stream=True · max_tokens=100\ntemperature=0.1 · p50: 2,274ms\nSystem prompt enforces citation:\n  file + paragraph + line in answer',
  },
  B12: {
    title: 'SSE tokens',
    detail:
      'Token-by-token streaming via SSE\nClient appends tokens in real-time\nFirst token typically <500ms after retrieval\nNone delta.content chunks skipped',
  },
  B13: {
    title: 'SSE done + metrics',
    detail:
      'Final done SSE event\nLatency breakdown:\n  embed: 165ms · retrieve: 72ms\n  rerank: <1ms · LLM: 2,274ms\nSimilarity metrics for the query',
  },
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
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
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
  // After mermaid.run() resolves, we attach hover listeners to each g.node SVG
  // element so the tooltip fires with rich detail on mouseenter.
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
      void m.default
        .run({ querySelector: '.mermaid' })
        .then(() => {
          if (cancelled) return
          const container = containerRef.current
          if (!container) return
          // Mermaid renders each node as <g class="node" id="flowchart-A1-0">.
          // Extract the source node variable (A1, D4, B13...) from the ID to
          // look up rich tooltip content.
          container.querySelectorAll('g.node').forEach((nodeEl) => {
            const nodeId = nodeEl.id.match(/flowchart-([A-Z]\d+)-\d+/)?.[1]
            const info = nodeId ? NODE_DETAILS[nodeId] : undefined
            if (!info) return
            nodeEl.addEventListener('mouseenter', (e) => {
              if (cancelled) return
              const { clientX, clientY } = e as MouseEvent
              setTooltip({ x: clientX, y: clientY, ...info })
            })
            nodeEl.addEventListener('mousemove', (e) => {
              if (cancelled) return
              setTooltip((prev) =>
                prev
                  ? { ...prev, x: (e as MouseEvent).clientX, y: (e as MouseEvent).clientY }
                  : null
              )
            })
            nodeEl.addEventListener('mouseleave', () => {
              if (!cancelled) setTooltip(null)
            })
          })
        })
        .catch(() => {
          // Ignore mermaid render errors — diagram just won't display
        })
    })

    return (): void => {
      cancelled = true
      setTooltip(null)
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

      {/* ── Hover tooltip ────────────────────────────────────────────────────── */}
      {tooltip !== null && (
        <div
          className="pointer-events-none rounded border border-terminal-accent/40 bg-terminal-bg/95 p-3 text-xs shadow-xl"
          style={{
            position: 'fixed',
            left: tooltip.x + 14,
            top: tooltip.y + 14,
            maxWidth: '17rem',
            zIndex: 9999,
          }}
        >
          <p className="mb-1.5 font-semibold text-terminal-accent">{tooltip.title}</p>
          <p className="whitespace-pre-line leading-relaxed text-terminal-muted">
            {tooltip.detail}
          </p>
        </div>
      )}
    </div>
  )
}
