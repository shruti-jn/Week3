/**
 * Next.js middleware — runs before every request to protect routes.
 *
 * Think of this like a security guard at a building entrance:
 * - If you have a valid badge (session cookie), you get in
 * - If you don't have a badge, you're redirected to get one (login page)
 *
 * The matcher config at the bottom controls which routes are protected.
 * Public routes (like /login and /api/auth/*) are excluded so users
 * can reach the login page without already being logged in.
 *
 * NextAuth's withAuth middleware handles the session check automatically:
 * - It reads the NextAuth session cookie
 * - If valid, the request proceeds normally
 * - If invalid or missing, it redirects to the signIn page (defined in authOptions)
 */

import { withAuth } from "next-auth/middleware";

// In development, allow unauthenticated access to /search for demo purposes.
// Re-enable auth protection before deploying to production.
const isDev = process.env.NODE_ENV === "development";

export default isDev
  ? // eslint-disable-next-line @typescript-eslint/explicit-function-return-type
    function devMiddleware() {
      return; // pass-through — no auth check in dev
    }
  : withAuth({
      pages: {
        signIn: "/login",
      },
    });

/**
 * matcher controls which routes the middleware runs on.
 *
 * Protected routes (middleware runs):
 *   - Everything EXCEPT the excluded paths below
 *
 * Public routes (middleware skipped):
 *   - /login — the login page itself (can't protect the auth gate!)
 *   - /api/auth/* — NextAuth API endpoints (sign-in, callback, sign-out)
 *   - /_next/* — Next.js internal files (JS, CSS, images)
 *   - /favicon.ico — browser tab icon
 */
export const config = {
  matcher: [
    "/((?!login|api/auth|_next/static|_next/image|favicon.ico).*)",
  ],
};
