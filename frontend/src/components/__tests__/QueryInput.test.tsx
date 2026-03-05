/**
 * Unit tests for the QueryInput component.
 *
 * QueryInput is the search bar — it lets the user type a question
 * and submit it. Tests verify:
 * - rendering the text field and button
 * - submit calls the onSubmit prop with the query text
 * - submit is blocked when loading or input is empty
 * - button label changes during loading
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { QueryInput } from '../QueryInput'

describe('QueryInput', () => {
  const noop = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  // ── Rendering ─────────────────────────────────────────────────────────────

  it('renders a text input', () => {
    render(<QueryInput onSubmit={noop} isLoading={false} />)
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it("renders a submit button with 'Search' label", () => {
    render(<QueryInput onSubmit={noop} isLoading={false} />)
    expect(screen.getByRole('button', { name: /search/i })).toBeInTheDocument()
  })

  it('shows placeholder text in the input', () => {
    render(<QueryInput onSubmit={noop} isLoading={false} />)
    expect(screen.getByPlaceholderText(/ask a question/i)).toBeInTheDocument()
  })

  // ── Loading state ─────────────────────────────────────────────────────────

  it('disables the submit button when isLoading is true', () => {
    render(<QueryInput onSubmit={noop} isLoading={true} />)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it("shows 'Searching...' button label while loading", () => {
    render(<QueryInput onSubmit={noop} isLoading={true} />)
    expect(screen.getByRole('button', { name: /searching/i })).toBeInTheDocument()
  })

  it('does not disable the input field while loading', () => {
    render(<QueryInput onSubmit={noop} isLoading={true} />)
    expect(screen.getByRole('textbox')).not.toBeDisabled()
  })

  // ── Submission ────────────────────────────────────────────────────────────

  it('calls onSubmit with the typed query when form is submitted', () => {
    const onSubmit = jest.fn()
    render(<QueryInput onSubmit={onSubmit} isLoading={false} />)

    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'how does payroll work?' } })
    fireEvent.submit(screen.getByRole('form'))

    expect(onSubmit).toHaveBeenCalledWith('how does payroll work?')
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('trims leading and trailing whitespace before calling onSubmit', () => {
    const onSubmit = jest.fn()
    render(<QueryInput onSubmit={onSubmit} isLoading={false} />)

    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: '  payroll calculation  ' } })
    fireEvent.submit(screen.getByRole('form'))

    expect(onSubmit).toHaveBeenCalledWith('payroll calculation')
  })

  it('does not call onSubmit when input is empty', () => {
    const onSubmit = jest.fn()
    render(<QueryInput onSubmit={onSubmit} isLoading={false} />)

    fireEvent.submit(screen.getByRole('form'))

    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('does not call onSubmit when input is only whitespace', () => {
    const onSubmit = jest.fn()
    render(<QueryInput onSubmit={onSubmit} isLoading={false} />)

    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.submit(screen.getByRole('form'))

    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('does not call onSubmit while isLoading is true', () => {
    const onSubmit = jest.fn()
    render(<QueryInput onSubmit={onSubmit} isLoading={true} />)

    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'test query' } })
    fireEvent.submit(screen.getByRole('form'))

    expect(onSubmit).not.toHaveBeenCalled()
  })

  // ── Input state ───────────────────────────────────────────────────────────

  it('updates the input value as the user types', () => {
    render(<QueryInput onSubmit={noop} isLoading={false} />)

    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'COBOL' } })

    expect(input).toHaveValue('COBOL')
  })
})
