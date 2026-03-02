/**
 * Root layout — wraps every page in the app.
 *
 * This is the outermost shell of the application. Every page rendered
 * in LegacyLens inherits from this layout.
 *
 * Why do we need SessionProvider here?
 * NextAuth's useSession() hook (used by AuthButton and other components)
 * reads the current session from a React context. SessionProvider sets up
 * that context. Without it, useSession() would throw an error.
 *
 * SessionProvider must be in a Client Component because it uses React context.
 * We wrap just the SessionProvider in a thin "Providers" client component
 * to keep the root layout as a Server Component for better performance.
 */

import type { Metadata } from "next";

import Providers from "./providers";

export const metadata: Metadata = {
  title: "LegacyLens — COBOL Code Intelligence",
  description:
    "Ask plain-English questions about COBOL codebases. Get exact code snippets with file paths and line numbers.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        {/*
         * Providers wraps the app with SessionProvider and any future
         * context providers (theme, toast notifications, etc.).
         */}
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
