/**
 * /search — The main search page for LegacyLens.
 *
 * Protected by middleware (unauthenticated users are redirected to /login).
 * This page renders the SearchContainer which holds the full search UX.
 *
 * This is a Server Component — the SearchContainer handles its own
 * interactivity via "use client" and useState internally.
 */

import { SearchContainer } from "@/components/SearchContainer";

export const metadata = {
  title: "Search — LegacyLens",
  description: "Ask plain-English questions about your COBOL codebase",
};

export default function SearchPage() {
  return (
    <main className="min-h-screen bg-gray-50 py-10">
      <div className="mx-auto max-w-3xl px-4">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">LegacyLens</h1>
        <p className="mb-8 text-sm text-gray-600">
          Ask a plain-English question about the COBOL codebase and get back
          the exact code snippet, file name, and line number.
        </p>
        <SearchContainer />
      </div>
    </main>
  );
}
