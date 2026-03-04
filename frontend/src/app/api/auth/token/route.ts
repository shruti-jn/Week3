/**
 * GET /api/auth/token — returns the raw NextAuth JWT for use by the FastAPI backend.
 *
 * WHY THIS ENDPOINT EXISTS:
 * The frontend's `session.accessToken` (stored in the NextAuth session) is the
 * GitHub OAuth access token — it proves the user logged in with GitHub. But that's
 * NOT what the FastAPI backend verifies. FastAPI uses `python-jose` to verify an
 * HS256 JWT signed with NEXTAUTH_SECRET. That's the raw NextAuth JWT from the
 * session cookie, not the GitHub token.
 *
 * This endpoint bridges that gap:
 * 1. It reads the raw NextAuth JWT from the session cookie using `getToken({ raw: true })`
 * 2. Returns it as JSON so client-side code can include it in `Authorization: Bearer <token>`
 *    headers when calling FastAPI.
 *
 * SECURITY NOTE:
 * This endpoint is protected by the Next.js middleware (requires a valid session).
 * It only returns the token to already-authenticated users.
 *
 * Usage in client code:
 *   const { token } = await fetch("/api/auth/token").then(r => r.json());
 *   fetch("https://api.example.com/api/v1/query", {
 *     headers: { "Authorization": `Bearer ${token}` }
 *   });
 */

import { getToken } from "next-auth/jwt";
import { type NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest): Promise<NextResponse> {
  // `raw: true` returns the JWT as a signed string (what FastAPI needs).
  // Without `raw: true`, getToken() returns the decoded payload object.
  const rawToken = await getToken({
    req,
    secret: process.env.NEXTAUTH_SECRET,
    raw: true,
  });

  if (!rawToken) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  return NextResponse.json({ token: rawToken });
}
