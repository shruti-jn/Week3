/**
 * NextAuth.js configuration options.
 *
 * This file defines HOW authentication works in LegacyLens:
 * - Which OAuth provider to use (GitHub)
 * - How to create the session (what data to store)
 * - How long sessions last
 *
 * Think of this file as the "ID card issuing office":
 * it defines what information goes on the ID card (session),
 * who is allowed to issue it (GitHub OAuth), and when it expires.
 *
 * This is imported by the NextAuth route handler and by server-side code
 * that needs to get the current session (e.g., Server Components).
 */

import type { NextAuthOptions } from 'next-auth'
import GithubProvider from 'next-auth/providers/github'

export const authOptions: NextAuthOptions = {
  /**
   * The OAuth providers users can sign in with.
   *
   * We use GitHub because:
   * 1. LegacyLens is a developer tool — our users all have GitHub accounts
   * 2. GitHub OAuth is simple to set up and well-trusted
   * 3. We can optionally use GitHub's API to get user profile data
   */
  providers: [
    GithubProvider({
      clientId: process.env.GITHUB_CLIENT_ID ?? '',
      clientSecret: process.env.GITHUB_CLIENT_SECRET ?? '',
    }),
  ],

  /**
   * Custom session callback — runs whenever a session is accessed.
   *
   * The default NextAuth session doesn't include the user ID or access token.
   * We extend it here so the frontend can pass auth info to FastAPI.
   */
  callbacks: {
    async jwt({ token, account }) {
      /**
       * jwt callback runs when a JWT is created or updated.
       * On first sign-in, 'account' is the OAuth account data from GitHub.
       * On subsequent requests, 'account' is null (token is from cookie).
       */
      if (account) {
        // Store the NextAuth-generated token so we can pass it to FastAPI
        token.accessToken = account.access_token
      }
      return token
    },

    async session({ session, token }) {
      /**
       * session callback runs when useSession() or getServerSession() is called.
       * We extend the session to include the user ID and access token
       * so Client Components can pass them to the FastAPI backend.
       */
      if (token.sub) {
        session.user.id = token.sub
      }
      if (token.accessToken) {
        ;(session as { accessToken?: string }).accessToken = token.accessToken as string
      }
      return session
    },
  },

  /**
   * Custom pages override NextAuth's default login page.
   *
   * We redirect to /login (our custom design) instead of NextAuth's
   * generic page at /api/auth/signin.
   */
  pages: {
    signIn: '/login',
  },

  /**
   * Session strategy: JWT (stateless) vs database.
   *
   * We use JWT because:
   * - No database needed for session storage
   * - Works well with Railway (stateless) + Vercel (edge)
   * - Sessions are self-contained — the JWT carries all user info
   */
  session: {
    strategy: 'jwt',
    maxAge: 24 * 60 * 60, // 24 hours — user must re-login daily
  },
}
