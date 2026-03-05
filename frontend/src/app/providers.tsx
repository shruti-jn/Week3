'use client'

/**
 * Providers — wraps the app with all React context providers.
 *
 * This is a Client Component because SessionProvider uses React context,
 * which requires the browser. By isolating providers in this component,
 * we keep the root layout.tsx as a Server Component for better performance.
 *
 * Think of this like an electrical junction box:
 * all the "power lines" (context providers) connect here, then feed
 * into every room (page) in the house.
 *
 * To add a new context provider in the future:
 * 1. Import it here
 * 2. Wrap {children} with it
 * Example:
 *   <ThemeProvider>
 *     <SessionProvider session={session}>
 *       {children}
 *     </SessionProvider>
 *   </ThemeProvider>
 *
 * @param children - The rest of the app (all pages and layouts)
 */

import { SessionProvider } from 'next-auth/react'

export default function Providers({ children }: { children: React.ReactNode }): React.JSX.Element {
  return <SessionProvider>{children}</SessionProvider>
}
