"use client";

/**
 * QueryInput — The search bar that lets users type a COBOL question.
 *
 * Like a Google search box, but for asking questions about old COBOL code.
 * The user types a plain-English question (e.g. "how does payroll tax work?"),
 * clicks Search, and the parent component handles fetching the answer.
 *
 * @param onSubmit  - Called with the trimmed query string when the user submits.
 *                    Not called if the input is empty or only whitespace.
 * @param isLoading - When true, disables the submit button and shows "Searching..."
 *                    so the user knows a search is already in progress.
 */

import { useState } from "react";

interface QueryInputProps {
  onSubmit: (query: string) => void;
  isLoading: boolean;
}

export function QueryInput({ onSubmit, isLoading }: QueryInputProps) {
  const [value, setValue] = useState("");

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = value.trim();
    // Block submission if the query is blank or a search is already running
    if (!trimmed || isLoading) return;
    onSubmit(trimmed);
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Search form" role="form">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Ask a question about the COBOL codebase..."
        className="w-full rounded border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <button
        type="submit"
        disabled={isLoading}
        className="mt-2 rounded bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isLoading ? "Searching..." : "Search"}
      </button>
    </form>
  );
}
