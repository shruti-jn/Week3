/**
 * Root page (/) — redirects to /login.
 *
 * The middleware protects all routes except /login and /api/auth/*.
 * This means if you're not logged in, the middleware already redirects you
 * to /login before this page renders.
 *
 * If you ARE logged in, this page redirects to /search (the main app).
 * We use Next.js server-side redirect for instant navigation without flash.
 */

import { redirect } from 'next/navigation'

export default function HomePage(): never {
  // Always redirect to /search — the middleware handles unauthenticated users.
  // Logged-in users land here briefly then go to /search.
  redirect('/search')
}
