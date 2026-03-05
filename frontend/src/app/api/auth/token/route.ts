/**
 * GET /api/auth/token — issues an HS256-signed JWT for the FastAPI backend.
 *
 * WHY THIS ENDPOINT EXISTS:
 * NextAuth v4 stores sessions as JWE (JSON Web Encryption, 5-part token) by
 * default. FastAPI uses python-jose's jwt.decode() which expects a plain
 * HS256-signed JWS (3-part token). Sending the raw NextAuth JWE to FastAPI
 * results in a 401 "Invalid authentication token" error.
 *
 * This endpoint bridges that gap:
 * 1. Decode the NextAuth JWE session via getToken() — NextAuth handles decryption
 * 2. Re-sign the payload as a plain HS256 JWS using NEXTAUTH_SECRET
 * 3. Return the HS256 token so the browser can send it to FastAPI
 *
 * FastAPI can then verify this token with jose.jwt.decode(token, NEXTAUTH_SECRET,
 * algorithms=["HS256"]) — which is exactly what jwt_validator.py does.
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

import { getToken } from 'next-auth/jwt'
import { SignJWT } from 'jose'
import { type NextRequest, NextResponse } from 'next/server'

export async function GET(req: NextRequest): Promise<NextResponse> {
  // Decode the NextAuth JWE session cookie — getToken() without raw:true
  // returns the decrypted payload as a plain object.
  const payload = await getToken({
    req,
    secret: process.env.NEXTAUTH_SECRET,
  })

  if (!payload) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })
  }

  // Re-sign the decoded payload as a plain HS256 JWT that FastAPI can verify.
  // We use the same NEXTAUTH_SECRET so both sides share the same key.
  const secret = process.env.NEXTAUTH_SECRET ?? ''
  const encoder = new TextEncoder()
  const key = encoder.encode(secret)

  const token = await new SignJWT(payload as Record<string, unknown>)
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('1h')
    .sign(key)

  return NextResponse.json({ token })
}
