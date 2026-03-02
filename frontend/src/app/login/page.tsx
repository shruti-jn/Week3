/**
 * Login page (/login) — the entry point for unauthenticated users.
 *
 * This is a Server Component (no "use client" directive).
 * The interactive sign-in button is in the AuthButton Client Component.
 *
 * Layout:
 * - Centered card with LegacyLens branding
 * - Short description of what the tool does
 * - AuthButton with "Sign in with GitHub"
 *
 * When the user clicks "Sign in with GitHub":
 * 1. NextAuth redirects to GitHub's OAuth page
 * 2. User authorizes the app
 * 3. GitHub redirects back to /api/auth/callback/github
 * 4. NextAuth creates a session cookie
 * 5. User is redirected to / (which then goes to /search)
 */

import AuthButton from "@/components/AuthButton";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
        {/* Branding */}
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-gray-900">LegacyLens</h1>
          <p className="mt-2 text-sm text-gray-500">
            Ask plain-English questions about COBOL code.
            <br />
            Get exact snippets with file paths and line numbers.
          </p>
        </div>

        {/* Sign-in button */}
        <div className="flex justify-center">
          <AuthButton />
        </div>

        {/* Footer note */}
        <p className="mt-6 text-center text-xs text-gray-400">
          Sign in with your GitHub account to continue.
          <br />
          We only request read access to your profile.
        </p>
      </div>
    </main>
  );
}
