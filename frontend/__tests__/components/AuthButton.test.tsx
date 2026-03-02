/**
 * Tests for the AuthButton component.
 *
 * AuthButton shows different UI based on authentication state:
 * - Signed out: shows "Sign in with GitHub" button
 * - Signed in: shows user name + "Sign out" button
 * - Loading: shows nothing (avoids flash of wrong state)
 *
 * We use next-auth's testing utilities to mock the session state.
 */

import { render, screen } from "@testing-library/react";
import { SessionProvider } from "next-auth/react";
import React from "react";

import AuthButton from "@/components/AuthButton";

// Mock next-auth signIn and signOut
jest.mock("next-auth/react", () => {
  const actual = jest.requireActual("next-auth/react");
  return {
    ...actual,
    signIn: jest.fn(),
    signOut: jest.fn(),
    useSession: jest.fn(),
  };
});

const { useSession } = jest.requireMock<typeof import("next-auth/react")>(
  "next-auth/react"
);

// ─────────────────────────────────────────────────────────────────────────────
// Helper
// ─────────────────────────────────────────────────────────────────────────────

function renderAuthButton() {
  return render(
    <SessionProvider>
      <AuthButton />
    </SessionProvider>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Unauthenticated state
// ─────────────────────────────────────────────────────────────────────────────

describe("AuthButton — signed out", () => {
  beforeEach(() => {
    useSession.mockReturnValue({ data: null, status: "unauthenticated" });
  });

  it("renders the sign-in button", () => {
    renderAuthButton();
    expect(
      screen.getByRole("button", { name: /sign in with github/i })
    ).toBeInTheDocument();
  });

  it("does not render the sign-out button", () => {
    renderAuthButton();
    expect(
      screen.queryByRole("button", { name: /sign out/i })
    ).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Authenticated state
// ─────────────────────────────────────────────────────────────────────────────

describe("AuthButton — signed in", () => {
  beforeEach(() => {
    useSession.mockReturnValue({
      data: {
        user: { name: "Jane Developer", email: "jane@github.com" },
        expires: "2099-01-01",
      },
      status: "authenticated",
    });
  });

  it("renders the sign-out button", () => {
    renderAuthButton();
    expect(
      screen.getByRole("button", { name: /sign out/i })
    ).toBeInTheDocument();
  });

  it("displays the user name", () => {
    renderAuthButton();
    expect(screen.getByText(/jane developer/i)).toBeInTheDocument();
  });

  it("does not render the sign-in button", () => {
    renderAuthButton();
    expect(
      screen.queryByRole("button", { name: /sign in/i })
    ).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Loading state
// ─────────────────────────────────────────────────────────────────────────────

describe("AuthButton — loading", () => {
  beforeEach(() => {
    useSession.mockReturnValue({ data: null, status: "loading" });
  });

  it("renders nothing while loading (avoids flash of wrong state)", () => {
    const { container } = renderAuthButton();
    // During loading, neither button should be visible
    expect(
      screen.queryByRole("button", { name: /sign in/i })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /sign out/i })
    ).not.toBeInTheDocument();
  });
});
