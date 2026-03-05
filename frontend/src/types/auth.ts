/**
 * Type extensions for NextAuth.js session and JWT.
 *
 * NextAuth's default session type doesn't include the GitHub access token
 * or user ID. We extend it here so TypeScript knows these fields exist.
 *
 * Why do we need the access token?
 * When the frontend calls the FastAPI backend, it needs to pass a JWT so the
 * backend can verify the request came from an authenticated user. NextAuth
 * generates this JWT and we pass it in the Authorization header.
 */

import type { DefaultSession, DefaultUser } from 'next-auth'
import type { DefaultJWT } from 'next-auth/jwt'

declare module 'next-auth' {
  /**
   * Extends the built-in Session type to include the access token.
   * This is what useSession() returns in Client Components.
   */
  interface Session extends DefaultSession {
    /** The NextAuth JWT, used to authenticate API calls to FastAPI. */
    accessToken?: string
    user: {
      /** GitHub user ID (e.g., "github-12345") — the sub claim in the JWT. */
      id?: string
    } & DefaultSession['user']
  }

  /**
   * Extends the built-in User type returned after OAuth sign-in.
   */
  interface User extends DefaultUser {
    id: string
  }
}

declare module 'next-auth/jwt' {
  /**
   * Extends the built-in JWT type to carry the sub (user ID).
   */
  interface JWT extends DefaultJWT {
    sub?: string
  }
}
