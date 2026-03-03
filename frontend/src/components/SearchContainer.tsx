"use client";

/**
 * SearchContainer — The main orchestrator for the COBOL search experience.
 *
 * Think of this as the "conductor" of the search orchestra: it holds all the
 * state (what the user typed, whether a search is running, what the results
 * are) and passes the right pieces to each child component.
 *
 * Child components:
 * - QueryInput    — takes the user's question
 * - AnswerDisplay — shows the GPT-4o-mini generated answer
 * - ResultCard    — one card per COBOL snippet returned
 *
 * State machine:
 *   idle → loading (user submits) → done (results arrive) or error (fetch fails)
 */

import { useState } from "react";
import { QueryInput } from "./QueryInput";
import { AnswerDisplay } from "./AnswerDisplay";
import { ResultCard } from "./ResultCard";
import { searchQuery } from "../lib/api";
import type { QueryResponse } from "../types/api";

export function SearchContainer() {
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(query: string) {
    setIsLoading(true);
    setError(null); // Clear any previous error before the new search

    try {
      const result = await searchQuery(query);
      setResponse(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(`Search failed. Please try again. (${message})`);
      setResponse(null);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4">
      <QueryInput onSubmit={handleSearch} isLoading={isLoading} />

      {/* Error banner — shown when the API call throws */}
      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Answer from GPT-4o-mini */}
      <AnswerDisplay
        answer={response?.answer ?? ""}
        isLoading={isLoading}
        queryTimeMs={response?.query_time_ms}
      />

      {/* Ranked COBOL snippet cards */}
      {response && response.snippets.length > 0 && (
        <div className="space-y-4">
          {response.snippets.map((snippet, index) => (
            <ResultCard key={snippet.file_path + snippet.start_line} snippet={snippet} rank={index + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
