/**
 * Login page — terminal-aesthetic entry point for LegacyLens.
 *
 * Presents the GitHub OAuth sign-in inside a minimal "terminal card"
 * with a blinking cursor and green phosphor accent. The design signals
 * "developer tool" immediately — no marketing fluff.
 */

import AuthButton from '@/components/AuthButton'
import { authOptions } from '@/lib/auth'
import { getServerSession } from 'next-auth'
import { redirect } from 'next/navigation'

export default async function LoginPage(): Promise<React.JSX.Element> {
  const session = await getServerSession(authOptions)
  if (session) {
    redirect('/search')
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Terminal window chrome */}
        <div className="mb-1 flex items-center gap-2 px-4 py-2">
          <span className="h-3 w-3 rounded-full bg-[#ff5f56] opacity-80" />
          <span className="h-3 w-3 rounded-full bg-[#ffbd2e] opacity-80" />
          <span className="h-3 w-3 rounded-full bg-terminal-accent opacity-80" />
          <span className="ml-2 text-xs text-terminal-muted">legacylens — bash</span>
        </div>

        {/* Main card */}
        <div className="accent-glow rounded-lg border border-terminal-border bg-terminal-surface p-8">
          {/* Logo / wordmark */}
          <div className="mb-8">
            <h1 className="cursor-blink terminal-text text-2xl font-semibold tracking-tight">
              LegacyLens
            </h1>
            <p className="mt-2 text-sm text-terminal-muted">
              COBOL code intelligence for the modern developer
            </p>
          </div>

          {/* System info block */}
          <div className="mb-6 space-y-1 rounded border border-terminal-border bg-terminal-bg px-3 py-2 text-xs text-terminal-muted">
            <div>
              <span className="text-terminal-accent">$</span>{' '}
              <span>legacylens --version 0.1.0</span>
            </div>
            <div>
              <span className="text-terminal-accent">→</span>{' '}
              <span>vector index: legacylens (pinecone)</span>
            </div>
            <div>
              <span className="text-terminal-accent">→</span>{' '}
              <span>model: gpt-4o-mini · text-embedding-3-small</span>
            </div>
            <div>
              <span className="text-terminal-accent">→</span>{' '}
              <span className="text-terminal-accent">auth required — connect with GitHub</span>
            </div>
          </div>

          {/* Auth action */}
          <AuthButton className="w-full" />

          {/* Footer */}
          <p className="mt-6 text-center text-xs text-terminal-dim">
            read-only access · no repository write permissions
          </p>
        </div>

        {/* Below card hint */}
        <p className="mt-4 text-center text-xs text-terminal-dim">
          {'// Gauntlet AI Week 3 · RAG-powered COBOL Intelligence'}
        </p>
      </div>
    </main>
  )
}
