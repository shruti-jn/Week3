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
import type { JWT } from 'next-auth/jwt'
import GithubProvider from 'next-auth/providers/github'
import { SignJWT, jwtVerify } from 'jose'

const SESSION_MAX_AGE = 24 * 60 * 60 // 24 hours in seconds

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
   * Override JWT encode/decode to produce plain HS256-signed JWS tokens.
   *
   * By default, NextAuth v4 uses JWE (JSON Web Encryption, 5-part token) to
   * protect session data. The FastAPI backend uses python-jose's jwt.decode()
   * which expects a plain HS256-signed JWT (JWS, 3-part token). Sending a JWE
   * token to FastAPI results in a 401 "Invalid authentication token" error.
   *
   * This override makes NextAuth produce tokens that FastAPI can verify:
   * - encode: sign the payload with HS256 using NEXTAUTH_SECRET
   * - decode: verify the HS256 signature and return the payload
   *
   * Both Vercel (frontend) and Railway (backend) must have the same
   * NEXTAUTH_SECRET value for the signature to verify correctly.
   */
  jwt: {
    encode: async ({ secret, token, maxAge }) => {
      const key = new TextEncoder().encode(secret as string)
      return new SignJWT(token as Record<string, unknown>)
        .setProtectedHeader({ alg: 'HS256' })
        .setIssuedAt()
        .setExpirationTime(Math.floor(Date.now() / 1000) + (maxAge ?? SESSION_MAX_AGE))
        .sign(key)
    },
    decode: async ({ secret, token }) => {
      if (!token) return null
      const key = new TextEncoder().encode(secret as string)
      try {
        const { payload } = await jwtVerify(token, key)
        return payload as JWT
      } catch {
        return null
      }
    },
  },

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
    maxAge: SESSION_MAX_AGE,
  },
}
