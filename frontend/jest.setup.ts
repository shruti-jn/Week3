/**
 * Jest setup file — runs before every test suite.
 *
 * This file adds extra tools and global mocks that every test needs.
 * Think of it like setting up your workbench before you start a project:
 * you lay out all the tools you'll need so you don't have to search
 * for them mid-project.
 */

// Polyfill fetch for the jsdom test environment.
// NextAuth's SessionProvider makes fetch calls to /api/auth/session.
// This mock prevents "ReferenceError: fetch is not defined" in tests.
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(""),
    status: 200,
  } as Response)
)

// Adds extra matchers to Jest like:
// expect(element).toBeInTheDocument()
// expect(element).toHaveTextContent('hello')
// These matchers make React component tests much more readable.
import '@testing-library/jest-dom'

// ─────────────────────────────────────────────────────────────────────────────
// Mock: NextAuth
// ─────────────────────────────────────────────────────────────────────────────
// Our app requires users to be logged in via GitHub OAuth.
// In tests, we don't want to actually go through GitHub's login flow.
// This mock pretends there's always a logged-in user named "Test User".
jest.mock('next-auth/react', () => ({
  useSession: jest.fn(() => ({
    data: {
      user: {
        name: 'Test User',
        email: 'testuser@github.com',
        image: 'https://avatars.githubusercontent.com/u/1?v=4',
      },
      expires: '2099-01-01T00:00:00.000Z',
    },
    status: 'authenticated', // Pretend the user is always logged in
  })),
  signIn: jest.fn(),  // Stub the sign-in function (doesn't actually sign in)
  signOut: jest.fn(), // Stub the sign-out function
  SessionProvider: ({ children }: { children: React.ReactNode }) => children,
}))

// ─────────────────────────────────────────────────────────────────────────────
// Mock: Next.js Navigation
// ─────────────────────────────────────────────────────────────────────────────
// Next.js's useRouter() doesn't work in the jsdom test environment.
// This mock replaces it with a simple stub that records calls.
// Tests can verify: expect(mockRouter.push).toHaveBeenCalledWith('/dashboard')
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    refresh: jest.fn(),
    back: jest.fn(),
    prefetch: jest.fn(),
  })),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
  redirect: jest.fn(),
}))

// ─────────────────────────────────────────────────────────────────────────────
// Mock: next/image
// ─────────────────────────────────────────────────────────────────────────────
// Next.js's Image component does complex optimization that doesn't work in jsdom.
// Replace it with a plain <img> tag for tests.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const React = require('react')
jest.mock('next/image', () => ({
  __esModule: true,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: (props: any) => {
    // Use React.createElement instead of JSX since this is a .ts file
    // eslint-disable-next-line @next/next/no-img-element
    return React.createElement('img', props)
  },
}))

// ─────────────────────────────────────────────────────────────────────────────
// Global: suppress console.error for expected React errors
// ─────────────────────────────────────────────────────────────────────────────
// Some tests intentionally trigger error states (e.g., missing required props).
// React prints console.error for these even though it's expected behavior.
// We suppress those to keep test output clean — real unexpected errors still show.
const originalConsoleError = console.error
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    // Only suppress specific known React warnings, not all errors
    if (
      typeof args[0] === 'string' &&
      (args[0].includes('Warning: ReactDOM.render') ||
        args[0].includes('Warning: An update to'))
    ) {
      return
    }
    originalConsoleError(...args)
  }
})

afterAll(() => {
  console.error = originalConsoleError
})
