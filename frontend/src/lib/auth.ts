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
import { createHmac } from 'node:crypto'

const isLikelyJwt = (value: string): boolean => value.split('.').length === 3
const API_TOKEN_TTL_SECONDS = 24 * 60 * 60

type BackendTokenClaims = {
  sub: string
  name?: string | null
  email?: string | null
  picture?: string | null
}

/**
 * Create an HS256 JWT the FastAPI backend can verify with NEXTAUTH_SECRET.
 */
const createBackendAccessToken = (
  claims: BackendTokenClaims,
  secret: string,
  expiresInSeconds: number
): string => {
  const now = Math.floor(Date.now() / 1000)
  const header = { alg: 'HS256', typ: 'JWT' }
  const payload = { ...claims, iat: now, exp: now + expiresInSeconds }

  const encodedHeader = Buffer.from(JSON.stringify(header)).toString('base64url')
  const encodedPayload = Buffer.from(JSON.stringify(payload)).toString('base64url')
  const signingInput = `${encodedHeader}.${encodedPayload}`
  const signature = createHmac('sha256', secret).update(signingInput).digest('base64url')

  return `${signingInput}.${signature}`
}

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
      const tokenString = typeof token.accessToken === 'string' ? token.accessToken : ''

      if (account || !tokenString || !isLikelyJwt(tokenString)) {
        const secret = process.env.NEXTAUTH_SECRET
        if (!secret || !token.sub) {
          return token
        }

        // Issue a backend-compatible HS256 token from trusted session claims.
        token.accessToken = createBackendAccessToken(
          {
            sub: token.sub,
            name: token.name,
            email: token.email,
            picture: token.picture,
          },
          secret,
          API_TOKEN_TTL_SECONDS
        )
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
