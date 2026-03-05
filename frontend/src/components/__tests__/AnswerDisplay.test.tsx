/**
 * Unit tests for the AnswerDisplay component.
 *
 * AnswerDisplay shows the GPT-4o-mini generated answer after a query.
 * It has three visual states:
 * 1. Loading — shows a skeleton while the search is in progress
 * 2. Answer present — shows the answer text (and optional query time)
 * 3. Empty — shows nothing when there is no answer and not loading
 */

import { render, screen } from '@testing-library/react'
import { AnswerDisplay } from '../AnswerDisplay'

describe('AnswerDisplay', () => {
  // ── Loading state ─────────────────────────────────────────────────────────

  it('shows a loading indicator while isLoading is true', () => {
    render(<AnswerDisplay answer="" isLoading={true} />)
    // Any test-id, aria-label, or text that signals loading is acceptable
    expect(
      screen.getByRole('status') ||
        screen.queryByTestId('answer-loading') ||
        screen.queryByLabelText(/loading/i) ||
        document.querySelector('[data-testid="answer-loading"]')
    ).toBeTruthy()
  })

  it('does not show answer text while loading', () => {
    render(<AnswerDisplay answer="partial text" isLoading={true} />)
    // If loading, we should not display stale/partial answer text
    expect(screen.queryByText('partial text')).not.toBeInTheDocument()
  })

  // ── Answer state ──────────────────────────────────────────────────────────

  it('renders the answer text when not loading', () => {
    const answer = 'The CALC-INTEREST paragraph multiplies principal by the annual rate.'
    render(<AnswerDisplay answer={answer} isLoading={false} />)
    expect(screen.getByText(answer)).toBeInTheDocument()
  })

  it('renders multiline answer text', () => {
    const answer = 'First sentence.\nSecond sentence.'
    render(<AnswerDisplay answer={answer} isLoading={false} />)
    // Both lines should be present in the DOM
    expect(screen.getByText(/First sentence/)).toBeInTheDocument()
    expect(screen.getByText(/Second sentence/)).toBeInTheDocument()
  })

  it('shows query time when provided', () => {
    render(<AnswerDisplay answer="test answer" isLoading={false} queryTimeMs={1234} />)
    // Should display the timing somewhere (1.23 s or 1234 ms etc.)
    expect(screen.getByText(/1[,.]?234|1\.23/)).toBeInTheDocument()
  })

  it('does not show query time when not provided', () => {
    render(<AnswerDisplay answer="test answer" isLoading={false} />)
    // No timing indicator should appear
    expect(screen.queryByText(/ms|seconds/i)).not.toBeInTheDocument()
  })

  // ── Empty state ───────────────────────────────────────────────────────────

  it('renders without crashing when answer is empty and not loading', () => {
    const { container } = render(<AnswerDisplay answer="" isLoading={false} />)
    expect(container).toBeTruthy()
  })

  it('does not show loading indicator when not loading', () => {
    render(<AnswerDisplay answer="some answer" isLoading={false} />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByTestId('answer-loading')).not.toBeInTheDocument()
  })

  // ── Long answer ───────────────────────────────────────────────────────────

  it('renders a very long answer without crashing', () => {
    const longAnswer = 'word '.repeat(500).trim()
    render(<AnswerDisplay answer={longAnswer} isLoading={false} />)
    expect(screen.getByText(longAnswer)).toBeInTheDocument()
  })
})
