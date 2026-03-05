'use client'

/**
 * AuthButton — shows sign-in or sign-out button based on authentication state.
 *
 * Terminal-themed: dark background, green accent border, monospace type.
 * - Not authenticated: "Sign in with GitHub" with GitHub SVG logo
 * - Authenticated: username + "↩ sign out" inline
 * - Loading: skeleton placeholder (prevents flicker)
 *
 * @param className - Optional CSS classes to apply to the wrapper div
 */

import { signIn, signOut, useSession } from 'next-auth/react'

interface AuthButtonProps {
  /** Optional CSS classes to apply to the container div. */
  className?: string
}

export default function AuthButton({ className }: AuthButtonProps): React.JSX.Element | null {
  const { data: session, status } = useSession()

  // During session check, show a skeleton to prevent layout shift.
  if (status === 'loading') {
    return (
      <div
        className={`h-9 animate-pulse rounded border border-terminal-border bg-terminal-bg ${className ?? ''}`}
      />
    )
  }

  // User is not authenticated — show the GitHub sign-in button
  if (!session) {
    return (
      <div className={className}>
        <button
          onClick={() => void signIn('github', { callbackUrl: '/search' })}
          className="accent-glow-sm inline-flex w-full items-center justify-center gap-3 rounded border border-terminal-border bg-terminal-bg px-4 py-2.5 text-sm font-medium text-terminal-text transition-all duration-150 hover:border-terminal-accent hover:text-terminal-accent focus:outline-none focus:ring-1 focus:ring-terminal-accent"
          aria-label="Sign in with GitHub"
        >
          {/* GitHub logo SVG */}
          <svg
            className="h-4 w-4 flex-shrink-0"
            fill="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.942.359.31.678.921.678 1.856 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
              clipRule="evenodd"
            />
          </svg>
          Sign in with GitHub
        </button>
      </div>
    )
  }

  // User is authenticated — show their name and a sign-out button
  return (
    <div className={`flex items-center gap-3 ${className ?? ''}`}>
      <span className="text-sm text-terminal-accent">
        {session.user?.name ?? session.user?.email ?? 'user'}
      </span>
      <button
        onClick={() => void signOut({ callbackUrl: '/login' })}
        className="rounded border border-terminal-border px-3 py-1 text-xs text-terminal-muted transition-all hover:border-terminal-accent hover:text-terminal-accent focus:outline-none"
        aria-label="Sign out"
      >
        ↩ sign out
      </button>
    </div>
  )
}
