/**
 * Unit tests for SearchContainer — the component that orchestrates
 * the full search experience.
 *
 * SearchContainer ties together:
 * - QueryInput  — receives the user's question
 * - searchQuery — calls the FastAPI backend
 * - AnswerDisplay — shows the GPT-4o-mini answer
 * - ResultCard list — shows ranked COBOL snippets
 *
 * The API module is fully mocked so no real network calls happen.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SearchContainer } from "../SearchContainer";
import * as api from "../../lib/api";
import type { QueryResponse } from "../../types/api";

// Mock the API module — SearchContainer should never call real fetch
jest.mock("../../lib/api");
// Mock syntax highlighter so tests stay fast
jest.mock("react-syntax-highlighter", () => ({
  Prism: ({ children }: { children: string }) => <pre data-testid="code-block">{children}</pre>,
}));
jest.mock("react-syntax-highlighter/dist/cjs/styles/prism", () => ({
  vscDarkPlus: {},
}));

const mockSearchQuery = api.searchQuery as jest.MockedFunction<typeof api.searchQuery>;

const MOCK_RESPONSE: QueryResponse = {
  answer: "The CALC-INTEREST paragraph computes annual interest.",
  snippets: [
    {
      file_path: "loans/calc.cob",
      start_line: 42,
      end_line: 58,
      content: "       CALC-INTEREST.\n           COMPUTE INTEREST = PRINCIPAL * RATE.",
      score: 0.91,
    },
    {
      file_path: "payroll/tax.cob",
      start_line: 100,
      end_line: 110,
      content: "       CALC-TAX.\n           COMPUTE TAX = GROSS * TAX-RATE.",
      score: 0.82,
    },
  ],
  query_time_ms: 987.6,
};

describe("SearchContainer", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ── Initial render ────────────────────────────────────────────────────────

  it("renders the QueryInput component on mount", () => {
    render(<SearchContainer />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /search/i })).toBeInTheDocument();
  });

  it("does not show any results before a search is made", () => {
    render(<SearchContainer />);
    expect(screen.queryByText(/loans\/calc\.cob/)).not.toBeInTheDocument();
    expect(screen.queryByText(/CALC-INTEREST/)).not.toBeInTheDocument();
  });

  // ── Successful search ─────────────────────────────────────────────────────

  it("calls searchQuery with the submitted query text", async () => {
    mockSearchQuery.mockResolvedValueOnce(MOCK_RESPONSE);
    render(<SearchContainer />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "how does interest work?" },
    });
    fireEvent.submit(screen.getByRole("form"));

    await waitFor(() => {
      expect(mockSearchQuery).toHaveBeenCalledWith("how does interest work?");
    });
  });

  it("displays the answer after a successful search", async () => {
    mockSearchQuery.mockResolvedValueOnce(MOCK_RESPONSE);
    render(<SearchContainer />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "how does interest work?" },
    });
    fireEvent.submit(screen.getByRole("form"));

    await waitFor(() => {
      expect(
        screen.getByText(/CALC-INTEREST paragraph computes annual interest/i)
      ).toBeInTheDocument();
    });
  });

  it("renders a ResultCard for each snippet in the response", async () => {
    mockSearchQuery.mockResolvedValueOnce(MOCK_RESPONSE);
    render(<SearchContainer />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "interest calculation" },
    });
    fireEvent.submit(screen.getByRole("form"));

    await waitFor(() => {
      expect(screen.getByText("loans/calc.cob")).toBeInTheDocument();
      expect(screen.getByText("payroll/tax.cob")).toBeInTheDocument();
    });
  });

  // ── Loading state ─────────────────────────────────────────────────────────

  it("shows a loading indicator while the search is in progress", async () => {
    // Never resolves during this test — keeps the loading state visible
    mockSearchQuery.mockReturnValueOnce(new Promise(() => undefined));
    render(<SearchContainer />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "loading test" },
    });
    fireEvent.submit(screen.getByRole("form"));

    // Button should be disabled while loading
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("re-enables the search button after the search completes", async () => {
    mockSearchQuery.mockResolvedValueOnce(MOCK_RESPONSE);
    render(<SearchContainer />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "test" },
    });
    fireEvent.submit(screen.getByRole("form"));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /search/i })).not.toBeDisabled();
    });
  });

  // ── Error state ───────────────────────────────────────────────────────────

  it("shows an error message when searchQuery throws", async () => {
    mockSearchQuery.mockRejectedValueOnce(new Error("Network error"));
    render(<SearchContainer />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "failing query" },
    });
    fireEvent.submit(screen.getByRole("form"));

    await waitFor(() => {
      expect(screen.getByText(/search failed|try again/i)).toBeInTheDocument();
    });
  });

  it("clears the error message on a subsequent successful search", async () => {
    mockSearchQuery
      .mockRejectedValueOnce(new Error("First call fails"))
      .mockResolvedValueOnce(MOCK_RESPONSE);

    render(<SearchContainer />);
    const input = screen.getByRole("textbox");

    // First search — fails
    fireEvent.change(input, { target: { value: "bad query" } });
    fireEvent.submit(screen.getByRole("form"));
    await waitFor(() => {
      expect(screen.getByText(/search failed|try again/i)).toBeInTheDocument();
    });

    // Second search — succeeds
    fireEvent.change(input, { target: { value: "good query" } });
    fireEvent.submit(screen.getByRole("form"));
    await waitFor(() => {
      expect(screen.queryByText(/search failed|try again/i)).not.toBeInTheDocument();
    });
  });

  // ── Empty snippets ────────────────────────────────────────────────────────

  it("shows the answer but no snippet cards when snippets array is empty", async () => {
    const noSnippets: QueryResponse = {
      ...MOCK_RESPONSE,
      snippets: [],
      answer: "No relevant COBOL code was found for your query.",
    };
    mockSearchQuery.mockResolvedValueOnce(noSnippets);
    render(<SearchContainer />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "unknown topic" },
    });
    fireEvent.submit(screen.getByRole("form"));

    await waitFor(() => {
      expect(
        screen.getByText(/No relevant COBOL code was found/i)
      ).toBeInTheDocument();
      expect(screen.queryByText(/loans\/calc\.cob/)).not.toBeInTheDocument();
    });
  });
});
