/**
 * ArchitecturePage — RAG pipeline visualizer for LegacyLens.
 *
 * Server Component: reads docs/RAG_ARCHITECTURE.md at request time, extracts
 * the Mermaid flowchart blocks, and enriches each node label with a two-line
 * HTML format — bold title in the node's accent color + dim detail line — so
 * the diagram itself carries implementation specifics without needing tooltips.
 *
 * Preprocessing pipeline per diagram block:
 *   1. Enable htmlLabels in the %%{init}%% directive (needed for HTML labels)
 *   2. Strip step-number prefixes ("A1 ", "B12 ") from node label strings
 *   3. Inject HTML detail lines into every node label (main + dim secondary)
 *   4. Strip original light-themed classDef/class lines
 *   5. Append terminal-themed classDef replacements + original class assignments
 */

import fs from 'fs'
import path from 'path'
import Link from 'next/link'
import type { Metadata } from 'next'

import AuthButton from '@/components/AuthButton'
import { ArchitectureDiagram } from '@/components/ArchitectureDiagram'

export const metadata: Metadata = {
  title: 'Architecture — LegacyLens',
  description: 'Animated RAG pipeline flow diagram for LegacyLens ingestion and query paths.',
}

// ── Mermaid extraction ────────────────────────────────────────────────────────

/**
 * Extract all ```mermaid ... ``` code blocks from a markdown string.
 * Returns the raw inner content of each block (without the fence lines).
 */
function extractMermaidBlocks(markdown: string): string[] {
  // Use exec() loop instead of matchAll() to avoid the --downlevelIteration requirement.
  const re = /```mermaid\n([\s\S]*?)```/g
  const blocks: string[] = []
  let match: RegExpExecArray | null
  while ((match = re.exec(markdown)) !== null) {
    blocks.push(match[1].trim())
  }
  return blocks
}

// ── Node label enrichment ─────────────────────────────────────────────────────

/**
 * Title color for each node variable — matches the terminal classDef palette:
 *   proc  → #00ff88 (green)   gate → #ffaa00 (amber)
 *   drop/fallback → #ff4444 (red)   event → #00ff88 (green)
 *
 * Keyed by the Mermaid source node variable (A1, D1, B4, etc.).
 */
const NODE_COLORS: Record<string, string> = {
  // proc — green
  A1: '#00ff88',
  A2: '#00ff88',
  A3: '#00ff88',
  A4: '#00ff88',
  A5: '#00ff88',
  A7: '#00ff88',
  A8: '#00ff88',
  A9: '#00ff88',
  A10: '#00ff88',
  A11: '#00ff88',
  B1: '#00ff88',
  B2: '#00ff88',
  B3: '#00ff88',
  B4: '#00ff88',
  B5: '#00ff88',
  B6: '#00ff88',
  B8: '#00ff88',
  B10: '#00ff88',
  B11: '#00ff88',
  // gate — amber
  D1: '#ffaa00',
  D2: '#ffaa00',
  D3: '#ffaa00',
  D4: '#ffaa00',
  // drop / fallback — red
  A6: '#ff4444',
  B9: '#ff4444',
  // event — green
  B7: '#00ff88',
  B12: '#00ff88',
  B13: '#00ff88',
}

/**
 * One-line implementation detail shown below each node title in dim gray.
 * No double-quote characters — labels are wrapped in Mermaid double-quote
 * delimiters so embedded " would terminate the label early.
 * Single-quoted HTML attributes are safe inside double-quoted Mermaid labels.
 */
const NODE_DETAIL_LINES: Record<string, string> = {
  // ── Ingestion
  A1: '577 .cob/.cbl · gnucobol-contrib',
  A2: 'PROCEDURE DIV · para/sections',
  D1: 'single UPPERCASE. · alone on line',
  A3: 'para_name · line spans',
  A4: '50-line windows · 10-line overlap',
  A5: '≥4 lines + ≥1 logic verb',
  D2: '50–86% rejection · DB2/PG files',
  A6: 'EXIT. trampolines · constants · HTML stubs',
  D3: '*> or col-7 * comment found?',
  A7: 'built from para_name + first *> comment',
  A8: 'no framing · typical score 0.45–0.55',
  A9: 'voyage-code-2 · input_type=document · 1536d',
  A10: 'file::PARA or file::chunk_N',
  A11: 'cosine · 1536d · 10,029 vectors',
  // ── Query
  B1: 'GitHub OAuth + JWT · authenticated',
  B2: "append 'COBOL' if missing",
  B3: 'voyage-code-2 · input_type=query · 165ms',
  B4: 'cosine ANN · 72ms · top_k=5',
  B5: 'cosine threshold: 0.65',
  B6: '0.7×cosine + 0.3×keyword · ~1ms',
  B7: 'top-5 · file + para + line + score',
  B8: 'top_score + avg_similarity',
  D4: 'top ≥ 0.66 AND avg ≥ 0.60',
  B9: 'no LLM call · done SSE still fired',
  B10: '5→3 prune · cuts tokens ~40%',
  B11: 'GPT-4o-mini · max_tokens=100 · 2,274ms',
  B12: 'token-by-token streaming',
  B13: 'latency breakdown + similarity scores',
}

/**
 * Build a two-line HTML node label.
 *
 * Line 1 — main label in the node's accent color (bold).
 * Line 2 — implementation detail in dim gray (#9ca3af), smaller font.
 *
 * Uses single-quoted HTML attributes because Mermaid wraps node label
 * strings in double quotes: A1["..."] — any " inside would end the label.
 */
function buildRichLabel(nodeVar: string, label: string): string {
  const color = NODE_COLORS[nodeVar]
  const detail = NODE_DETAIL_LINES[nodeVar]
  if (!color || !detail) return label
  return (
    `<span style='font-weight:600;color:${color}'>${label}</span>` +
    `<br/>` +
    `<span style='font-size:10px;color:#9ca3af;font-weight:400;white-space:nowrap'>${detail}</span>`
  )
}

// ── Theme + enrichment pipeline ───────────────────────────────────────────────

/**
 * Transform a raw Mermaid string from RAG_ARCHITECTURE.md into a
 * terminal-themed, HTML-enriched diagram string ready for mermaid.run().
 *
 * Steps applied in order:
 *   1. Switch htmlLabels to true in the %%{init}%% directive so mermaid
 *      renders node labels as HTML (required for the two-line format).
 *   2. Strip step-number prefixes ("A1 ", "B12 ") from quoted label strings.
 *   3. Replace each node label with buildRichLabel() output.
 *   4. Strip original classDef + class assignment lines (light-themed).
 *   5. Append terminal classDefs + the original class assignments.
 */
function applyTerminalTheme(diagram: string): string {
  // 1. Enable HTML labels in the diagram's own init directive.
  //    The %%{init}%% directive overrides mermaid.initialize() settings,
  //    so we must flip it here — not only in the JS config.
  const withHtmlLabels = diagram.replace(/'htmlLabels'\s*:\s*false/, "'htmlLabels': true")

  // 2. Strip step-number prefixes from quoted node label strings.
  const withoutIds = withHtmlLabels.replace(/"[A-Z]\d+ /g, '"')

  // 3. Enrich rectangular ["label"] and diamond {"label"} node definitions.
  const withDetails = withoutIds
    .replace(
      /\b([A-Z]\d+)\["([^"]+)"\]/g,
      (_m, nodeVar: string, label: string) => `${nodeVar}["${buildRichLabel(nodeVar, label)}"]`
    )
    .replace(
      /\b([A-Z]\d+)\{"([^"]+)"\}/g,
      (_m, nodeVar: string, label: string) => `${nodeVar}{"${buildRichLabel(nodeVar, label)}"}`
    )

  // 4. Strip all existing classDef and class assignment lines.
  const stripped = withDetails
    .split('\n')
    .filter((line) => !/^\s*(classDef|class )\s/.test(line))
    .join('\n')
    .trim()

  const terminalClassDefs = [
    'classDef proc fill:#111111,stroke:#00ff88,color:#00ff88,stroke-width:1px;',
    'classDef gate fill:#111111,stroke:#ffaa00,color:#ffaa00,stroke-width:1px;',
    'classDef drop fill:#1a0505,stroke:#ff4444,color:#ff4444,stroke-width:1px;',
    'classDef event fill:#003d21,stroke:#00ff88,color:#00ff88,stroke-width:1px;',
    'classDef fallback fill:#1a0505,stroke:#ff4444,color:#ff4444,stroke-width:1px;',
  ].join('\n    ')

  // 5. Re-add class assignments from the original diagram (node variable names
  //    are unchanged; only label text was modified above).
  const classAssignments = diagram
    .split('\n')
    .filter((line) => /^\s*class /.test(line))
    .join('\n    ')

  return `${stripped}\n    ${terminalClassDefs}\n    ${classAssignments}`.trim()
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ArchitecturePage(): React.JSX.Element {
  // Read the architecture doc — path is relative to the Next.js project root
  // (frontend/), so ../docs/ resolves to the repo-level docs/ directory.
  let ingestionMermaid = ''
  let queryMermaid = ''

  try {
    const docPath = path.join(process.cwd(), '../docs/RAG_ARCHITECTURE.md')
    const raw = fs.readFileSync(docPath, 'utf-8')
    const blocks = extractMermaidBlocks(raw).map(applyTerminalTheme)
    ingestionMermaid = blocks[0] ?? ''
    queryMermaid = blocks[1] ?? ''
  } catch {
    // File not found or unreadable — ArchitectureDiagram renders a fallback UI
  }

  return (
    <div className="flex min-h-screen flex-col bg-terminal-bg font-mono text-terminal-text">
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between border-b border-terminal-border bg-terminal-surface px-4 py-3">
        <div className="flex items-center gap-3">
          <Link
            href="/search"
            className="font-semibold tracking-tight text-terminal-accent transition-colors hover:text-terminal-accent-dim"
          >
            LegacyLens
          </Link>
          <span className="hidden text-xs text-terminal-dim sm:block">· architecture</span>
        </div>
        <nav className="hidden items-center gap-6 sm:flex">
          <Link
            href="/search"
            className="text-xs text-terminal-muted transition-colors hover:text-terminal-accent"
          >
            search
          </Link>
        </nav>
        <AuthButton />
      </header>

      {/* ── Main ──────────────────────────────────────────────────────────── */}
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
        <ArchitectureDiagram ingestionMermaid={ingestionMermaid} queryMermaid={queryMermaid} />
      </main>

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
