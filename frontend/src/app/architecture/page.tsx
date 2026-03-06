/**
 * ArchitecturePage — RAG pipeline visualizer for LegacyLens.
 *
 * This is a Server Component. It reads docs/RAG_ARCHITECTURE.md at request
 * time, extracts the Mermaid flowchart blocks, strips the original light-themed
 * classDef declarations, and injects terminal-themed replacements.
 *
 * The processed Mermaid strings are passed as props to the ArchitectureDiagram
 * Client Component, which renders them using mermaid.js in the browser.
 *
 * Why read the file here (not in the client component)?
 *   - Server Components can use Node.js `fs` directly; Client Components cannot.
 *   - Reading on the server keeps the raw markdown out of the browser bundle.
 *   - The diagram auto-updates on every server request when the doc changes.
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

/**
 * Replace the original light-themed classDef declarations in a Mermaid string
 * with terminal-themed equivalents (dark background, green/amber/red accents).
 *
 * The classDef lines in RAG_ARCHITECTURE.md use cyan/orange fills designed for
 * a white background. This function strips them and appends new definitions
 * that match the LegacyLens CRT aesthetic.
 *
 * Node types mapped:
 *   proc     → dark surface, green border + text (processing steps)
 *   gate     → dark surface, amber border + text (decision diamonds)
 *   drop     → dark red bg, red border + text (rejected/dropped chunks)
 *   event    → dark green bg, bright green border (SSE output events)
 *   fallback → dark red bg, red border + text (fallback responses)
 */
function applyTerminalTheme(mermaid: string): string {
  // Strip step identifiers (e.g. "A1 ", "B12 ") from quoted node label strings
  const withoutIds = mermaid.replace(/"[A-Z]\d+ /g, '"')

  // Strip all existing classDef and class assignment lines
  const stripped = withoutIds
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

  // Re-add the class assignments that were stripped (they reference node IDs,
  // not colors, so they still need to be present for mermaid to apply styles).
  const classAssignments = mermaid
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
