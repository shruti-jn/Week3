/**
 * Unit tests for the Next.js middleware route matcher pattern.
 *
 * The middleware (src/middleware.ts) uses a regex pattern to decide which
 * routes get protected (require a valid session) vs which are public.
 *
 * WHY WE TEST THE PATTERN DIRECTLY:
 * Importing middleware.ts pulls in next-auth/middleware which requires the
 * Next.js edge runtime — globals like `Request` aren't available in Jest's
 * jsdom environment. Instead, we copy the matcher pattern string and test
 * the regex directly. This is more portable and equally thorough.
 *
 * The pattern protects everything EXCEPT:
 *   - /login — the login page itself
 *   - /api/auth/* — NextAuth endpoints (sign-in, callback, sign-out)
 *   - /_next/static/* — Next.js bundled JS/CSS
 *   - /_next/image/* — Next.js image optimization
 *   - /favicon.ico — browser tab icon
 */

// Copied verbatim from src/middleware.ts config.matcher
// Keep in sync if the middleware matcher changes.
const MATCHER_PATTERN =
  "/((?!login|api/auth|_next/static|_next/image|favicon.ico).*)";

const regex = new RegExp(`^${MATCHER_PATTERN}$`);

/**
 * Returns true if the middleware WOULD run for this path.
 * (i.e., the path is protected and requires authentication)
 */
function isProtected(path: string): boolean {
  return regex.test(path);
}

describe("middleware matcher pattern", () => {
  // ── Protected routes — middleware SHOULD run ─────────────────────────────

  it("protects the root path /", () => {
    expect(isProtected("/")).toBe(true);
  });

  it("protects /dashboard", () => {
    expect(isProtected("/dashboard")).toBe(true);
  });

  it("protects nested protected routes like /dashboard/settings", () => {
    expect(isProtected("/dashboard/settings")).toBe(true);
  });

  it("protects /api routes that are not auth-related", () => {
    expect(isProtected("/api/v1/query")).toBe(true);
  });

  // ── Public routes — middleware SHOULD NOT run ────────────────────────────

  it("allows /login through without auth", () => {
    expect(isProtected("/login")).toBe(false);
  });

  it("allows /api/auth/signin through without auth", () => {
    expect(isProtected("/api/auth/signin")).toBe(false);
  });

  it("allows /api/auth/callback/github through without auth", () => {
    expect(isProtected("/api/auth/callback/github")).toBe(false);
  });

  it("allows /api/auth/signout through without auth", () => {
    expect(isProtected("/api/auth/signout")).toBe(false);
  });

  it("allows /_next/static/* through without auth", () => {
    expect(isProtected("/_next/static/chunks/main.js")).toBe(false);
  });

  it("allows /_next/image/* through without auth", () => {
    expect(isProtected("/_next/image?url=...")).toBe(false);
  });

  it("allows /favicon.ico through without auth", () => {
    expect(isProtected("/favicon.ico")).toBe(false);
  });
});
