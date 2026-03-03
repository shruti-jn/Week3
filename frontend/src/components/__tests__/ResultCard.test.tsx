/**
 * Unit tests for the ResultCard component.
 *
 * ResultCard renders one COBOL code snippet from the search results —
 * like a single Google result card but for COBOL. Tests verify:
 * - file path is shown
 * - line range is shown
 * - similarity score is shown
 * - rank number is shown
 * - COBOL content is rendered
 */

import { render, screen } from "@testing-library/react";
import { ResultCard } from "../ResultCard";
import type { CodeSnippet } from "../../types/api";

// react-syntax-highlighter does complex DOM work that doesn't matter for unit tests.
// We replace it with a simple <pre> so we can still assert on the content.
jest.mock("react-syntax-highlighter", () => ({
  Prism: ({ children }: { children: string }) => <pre data-testid="code-block">{children}</pre>,
}));
jest.mock("react-syntax-highlighter/dist/cjs/styles/prism", () => ({
  vscDarkPlus: {},
}));

const SAMPLE_SNIPPET: CodeSnippet = {
  file_path: "loans/calc.cob",
  start_line: 42,
  end_line: 58,
  content: "       CALC-INTEREST.\n           COMPUTE INTEREST = PRINCIPAL * RATE.",
  score: 0.91,
};

describe("ResultCard", () => {
  // ── File metadata ─────────────────────────────────────────────────────────

  it("renders the file path", () => {
    render(<ResultCard snippet={SAMPLE_SNIPPET} rank={1} />);
    expect(screen.getByText("loans/calc.cob")).toBeInTheDocument();
  });

  it("renders the line range", () => {
    render(<ResultCard snippet={SAMPLE_SNIPPET} rank={1} />);
    expect(screen.getByText(/42.*58|Lines 42.*58/)).toBeInTheDocument();
  });

  it("renders the similarity score as a percentage", () => {
    render(<ResultCard snippet={SAMPLE_SNIPPET} rank={1} />);
    // 0.91 → "91%" (rounded to nearest integer)
    expect(screen.getByText(/91%/)).toBeInTheDocument();
  });

  it("renders the rank number", () => {
    render(<ResultCard snippet={SAMPLE_SNIPPET} rank={3} />);
    expect(screen.getByText(/#3|3/)).toBeInTheDocument();
  });

  // ── Code content ──────────────────────────────────────────────────────────

  it("renders the COBOL code content", () => {
    render(<ResultCard snippet={SAMPLE_SNIPPET} rank={1} />);
    expect(screen.getByTestId("code-block")).toHaveTextContent(
      "CALC-INTEREST"
    );
  });

  // ── Edge cases ────────────────────────────────────────────────────────────

  it("handles a single-line snippet (start_line === end_line)", () => {
    const singleLine: CodeSnippet = {
      ...SAMPLE_SNIPPET,
      start_line: 10,
      end_line: 10,
      content: "           STOP RUN.",
    };
    render(<ResultCard snippet={singleLine} rank={1} />);
    // Should not crash and should show line 10
    expect(screen.getByText(/10/)).toBeInTheDocument();
  });

  it("handles a score of 1.0 (perfect match)", () => {
    const perfect: CodeSnippet = { ...SAMPLE_SNIPPET, score: 1.0 };
    render(<ResultCard snippet={perfect} rank={1} />);
    expect(screen.getByText(/100%/)).toBeInTheDocument();
  });

  it("handles a score at the minimum threshold (0.75)", () => {
    const threshold: CodeSnippet = { ...SAMPLE_SNIPPET, score: 0.75 };
    render(<ResultCard snippet={threshold} rank={1} />);
    expect(screen.getByText(/75%/)).toBeInTheDocument();
  });

  it("renders a long file path without crashing", () => {
    const deepPath: CodeSnippet = {
      ...SAMPLE_SNIPPET,
      file_path: "very/deeply/nested/directory/structure/for/a/cobol/file.cob",
    };
    render(<ResultCard snippet={deepPath} rank={1} />);
    expect(
      screen.getByText("very/deeply/nested/directory/structure/for/a/cobol/file.cob")
    ).toBeInTheDocument();
  });

  it("rank=1 result renders without crashing", () => {
    const { container } = render(<ResultCard snippet={SAMPLE_SNIPPET} rank={1} />);
    expect(container.firstChild).not.toBeNull();
  });
});
