"use client";

/**
 * AnswerDisplay — Shows the GPT-4o-mini generated answer to a COBOL query.
 *
 * Like the featured snippet at the top of a Google search, this shows an
 * AI-generated plain-English explanation of the relevant COBOL code.
 *
 * Three visual states:
 * 1. Loading   — shows a spinner / skeleton while the search is in progress
 * 2. Answer    — shows the answer text and optional query timing
 * 3. Empty     — renders nothing when there is no answer and we are not loading
 *
 * @param answer       - The GPT-4o-mini generated answer text.
 * @param isLoading    - True while the search request is in flight.
 * @param queryTimeMs  - Optional total query duration in milliseconds. Shown
 *                       as a small badge when provided.
 */

interface AnswerDisplayProps {
  answer: string;
  isLoading: boolean;
  queryTimeMs?: number;
}

export function AnswerDisplay({ answer, isLoading, queryTimeMs }: AnswerDisplayProps) {
  if (isLoading) {
    return (
      <div
        role="status"
        data-testid="answer-loading"
        aria-label="Loading answer"
        className="rounded border border-gray-200 bg-gray-50 p-4"
      >
        <div className="h-4 w-3/4 animate-pulse rounded bg-gray-300" />
        <div className="mt-2 h-4 w-1/2 animate-pulse rounded bg-gray-300" />
      </div>
    );
  }

  if (!answer) {
    return null;
  }

  return (
    <div className="rounded border border-blue-100 bg-blue-50 p-4">
      {/* The answer text — whitespace preserved so multiline answers render correctly */}
      <p className="whitespace-pre-wrap text-sm text-gray-800">{answer}</p>

      {/* Query timing badge — only shown when the caller provides a value */}
      {queryTimeMs !== undefined && (
        <p className="mt-2 text-xs text-gray-500">{queryTimeMs} ms</p>
      )}
    </div>
  );
}
