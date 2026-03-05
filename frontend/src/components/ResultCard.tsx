'use client'

/**
 * ResultCard — Displays one COBOL code snippet from the search results.
 *
 * Like a single Google result card, but for COBOL code. Shows the file name,
 * the line range where the code lives, a similarity score, and the actual
 * COBOL source with syntax highlighting.
 *
 * @param snippet - The COBOL code chunk returned by the vector database.
 * @param rank    - Position in the result list (1 = best match). Shown as "#1",
 *                  "#2", etc. so the user can see how confident the system is.
 */

import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism'
import type { CodeSnippet } from '../types/api'

interface ResultCardProps {
  snippet: CodeSnippet
  rank: number
}

export function ResultCard({ snippet, rank }: ResultCardProps): React.JSX.Element {
  // Convert 0.0–1.0 cosine score to a whole-number percentage (e.g. 0.91 → 91)
  const scorePercent = Math.round(snippet.score * 100)

  return (
    <div className="rounded border border-gray-200 bg-white p-4 shadow-sm">
      {/* Header row: rank badge, file path, line range, score */}
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <span className="rounded bg-blue-100 px-2 py-0.5 font-mono font-semibold text-blue-800">
          #{rank}
        </span>
        <span className="flex-1 break-all font-mono text-gray-800">{snippet.file_path}</span>
        <span className="text-gray-500">
          Lines {snippet.start_line}–{snippet.end_line}
        </span>
        <span className="rounded bg-green-100 px-2 py-0.5 text-green-800">{scorePercent}%</span>
      </div>

      {/* COBOL source code with syntax highlighting */}
      <SyntaxHighlighter
        language="cobol"
        style={vscDarkPlus}
        customStyle={{ margin: 0, borderRadius: '0.375rem', fontSize: '0.75rem' }}
      >
        {snippet.content}
      </SyntaxHighlighter>
    </div>
  )
}
