/**
 * Root layout — wraps every page in the app with the terminal theme.
 *
 * Imports globals.css which sets up Tailwind + our dark terminal aesthetic.
 * SessionProvider lives in Providers (a Client Component) so this file
 * can remain a Server Component.
 */

import type { Metadata } from 'next'
import { JetBrains_Mono } from 'next/font/google'
import './globals.css'
import Providers from './providers'

const jetBrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600'],
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'LegacyLens — COBOL Code Intelligence',
  description:
    'Ask plain-English questions about COBOL codebases. Get exact code snippets with file paths and line numbers.',
}

export default function RootLayout({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <html lang="en" className="h-full">
      <body
        className={`${jetBrainsMono.className} scanlines h-full bg-terminal-bg text-terminal-text`}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
