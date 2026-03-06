/**
 * Unit tests for the ArchitectureDiagram component.
 *
 * Mermaid is ESM-only; moduleNameMapper in jest.config.ts redirects it to
 * src/__mocks__/mermaid.ts which provides jest.fn() stubs.
 */

import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import mermaid from 'mermaid'
import { ArchitectureDiagram } from '../ArchitectureDiagram'

const mockInitialize = mermaid.initialize as jest.Mock
const mockRun = mermaid.run as jest.Mock

// ── Test data ──────────────────────────────────────────────────────────────

const INGESTION_MERMAID = `flowchart TB
    A1["A1 Scan COBOL corpus"] --> A2["A2 Detect boundaries"]
    classDef proc fill:#111111,stroke:#00ff88,color:#00ff88,stroke-width:1px;`

const QUERY_MERMAID = `flowchart TB
    B1["B1 User query"] --> B2["B2 query_enrich()"]
    classDef proc fill:#111111,stroke:#00ff88,color:#00ff88,stroke-width:1px;`

function renderDiagram(
  ingestion = INGESTION_MERMAID,
  query = QUERY_MERMAID
): ReturnType<typeof render> {
  return render(<ArchitectureDiagram ingestionMermaid={ingestion} queryMermaid={query} />)
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('ArchitectureDiagram', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockRun.mockResolvedValue(undefined)
  })

  // Tab switcher
  it('renders INGESTION PIPELINE tab as active by default', () => {
    renderDiagram()
    const btn = screen.getByRole('button', { name: /ingestion pipeline/i })
    expect(btn).toBeInTheDocument()
    expect(btn).toHaveAttribute('aria-pressed', 'true')
  })

  it('renders QUERY PIPELINE tab button', () => {
    renderDiagram()
    const btn = screen.getByRole('button', { name: /query pipeline/i })
    expect(btn).toBeInTheDocument()
    expect(btn).toHaveAttribute('aria-pressed', 'false')
  })

  it('switches active tab to QUERY when clicked', () => {
    renderDiagram()
    const queryBtn = screen.getByRole('button', { name: /query pipeline/i })
    fireEvent.click(queryBtn)
    expect(queryBtn).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /ingestion pipeline/i })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
  })

  it('switches back to INGESTION after clicking QUERY then INGESTION', () => {
    renderDiagram()
    fireEvent.click(screen.getByRole('button', { name: /query pipeline/i }))
    fireEvent.click(screen.getByRole('button', { name: /ingestion pipeline/i }))
    expect(screen.getByRole('button', { name: /ingestion pipeline/i })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
  })

  // Mermaid container
  it('renders a .mermaid container div', async () => {
    const { container } = renderDiagram()
    await waitFor(() => expect(container.querySelector('.mermaid')).toBeInTheDocument())
  })

  it('mermaid container contains ingestion content by default', async () => {
    const { container } = renderDiagram()
    await waitFor(() => {
      expect(container.querySelector('.mermaid')?.textContent).toContain('Scan COBOL corpus')
    })
  })

  it('mermaid container contains query content after tab switch', async () => {
    const { container } = renderDiagram()
    fireEvent.click(screen.getByRole('button', { name: /query pipeline/i }))
    await waitFor(() => {
      expect(container.querySelector('.mermaid')?.textContent).toContain('query_enrich')
    })
  })

  // Mermaid API calls
  it('calls mermaid.initialize with dark theme on mount', async () => {
    renderDiagram()
    await waitFor(() => {
      expect(mockInitialize).toHaveBeenCalledWith(
        expect.objectContaining({
          startOnLoad: false,
          theme: 'dark',
          themeVariables: expect.objectContaining({
            darkMode: true,
            primaryTextColor: '#00ff88',
            lineColor: '#00ff88',
          }),
        })
      )
    })
  })

  it('calls mermaid.run after initialization', async () => {
    renderDiagram()
    await waitFor(() => expect(mockRun).toHaveBeenCalled())
  })

  it('calls mermaid.run again when the active tab changes', async () => {
    renderDiagram()
    await waitFor(() => expect(mockRun).toHaveBeenCalledTimes(1))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /query pipeline/i }))
    })
    await waitFor(() => expect(mockRun).toHaveBeenCalledTimes(2))
  })

  // Metrics table
  it('renders the performance metrics section', () => {
    renderDiagram()
    expect(screen.getByText(/performance metrics/i)).toBeInTheDocument()
  })

  it('displays total vectors indexed in metrics', () => {
    renderDiagram()
    expect(screen.getByText(/10,029/)).toBeInTheDocument()
  })

  it('displays total files scanned in metrics', () => {
    renderDiagram()
    expect(screen.getByText(/577/)).toBeInTheDocument()
  })

  it('displays end-to-end latency in metrics', () => {
    renderDiagram()
    expect(screen.getByText(/2\.51s/)).toBeInTheDocument()
  })

  it('displays precision@5 label in metrics', () => {
    renderDiagram()
    expect(screen.getByText(/precision@5/i)).toBeInTheDocument()
  })

  // Edge cases
  it('renders without crashing when ingestionMermaid is empty', () => {
    expect(() => renderDiagram('', QUERY_MERMAID)).not.toThrow()
  })

  it('renders without crashing when queryMermaid is empty', () => {
    expect(() => renderDiagram(INGESTION_MERMAID, '')).not.toThrow()
  })

  it('renders without crashing when both strings are empty', () => {
    expect(() => renderDiagram('', '')).not.toThrow()
  })

  it('shows fallback message when both strings are empty', () => {
    renderDiagram('', '')
    expect(screen.getByText(/architecture document not found/i)).toBeInTheDocument()
  })

  it('shows page title "RAG Architecture"', () => {
    renderDiagram()
    expect(screen.getByText(/rag architecture/i)).toBeInTheDocument()
  })

  it('re-runs mermaid on each tab switch', async () => {
    renderDiagram()
    await waitFor(() => expect(mockRun).toHaveBeenCalledTimes(1))

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /query pipeline/i }))
    })
    await waitFor(() => expect(mockRun).toHaveBeenCalledTimes(2))

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /ingestion pipeline/i }))
    })
    await waitFor(() => expect(mockRun).toHaveBeenCalledTimes(3))
  })
})
