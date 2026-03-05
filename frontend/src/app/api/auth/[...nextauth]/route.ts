/**
 * NextAuth.js API route handler for Next.js App Router.
 *
 * This file handles ALL auth-related HTTP requests:
 * - GET  /api/auth/signin         — shows the sign-in page redirect
 * - GET  /api/auth/callback/github — handles GitHub OAuth callback
 * - GET  /api/auth/signout        — signs the user out
 * - GET  /api/auth/session        — returns the current session (used by useSession())
 * - GET  /api/auth/csrf           — returns the CSRF token
 *
 * The [...nextauth] filename is a "catch-all route" in Next.js App Router.
 * It matches any path under /api/auth/*, passing the path segments to NextAuth.
 *
 * Why do we export GET and POST separately?
 * Next.js App Router requires explicit HTTP method exports for route handlers.
 * NextAuth v4 wraps them in a single handler that we export as both.
 */

import NextAuth from 'next-auth'

import { authOptions } from '@/lib/auth'

// Create the NextAuth handler with our auth configuration
const handler = NextAuth(authOptions)

// Export as both GET and POST since NextAuth needs both
// - GET: for fetching session info, sign-in page, etc.
// - POST: for sign-in/sign-out actions with CSRF token
export { handler as GET, handler as POST }
