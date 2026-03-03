/**
 * Unit tests for the AuthButton component.
 *
 * AuthButton shows different UI based on the user's authentication state:
 * - loading: renders nothing (prevents flash of wrong state)
 * - unauthenticated: renders a "Sign in with GitHub" button
 * - authenticated: renders the user's name and a "Sign out" button
 *
 * All tests mock next-auth/react so no real session infrastructure is needed.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { useSession, signIn, signOut } from "next-auth/react";
import AuthButton from "../AuthButton";

// Mock next-auth/react so tests don't need a real NextAuth provider
jest.mock("next-auth/react");

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;
const mockSignIn = signIn as jest.MockedFunction<typeof signIn>;
const mockSignOut = signOut as jest.MockedFunction<typeof signOut>;

describe("AuthButton", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ── Loading state ────────────────────────────────────────────────────────

  it("renders nothing when status is loading", () => {
    mockUseSession.mockReturnValue({
      data: null,
      status: "loading",
      update: jest.fn(),
    });

    const { container } = render(<AuthButton />);
    expect(container.firstChild).toBeNull();
  });

  // ── Unauthenticated state ────────────────────────────────────────────────

  it("shows sign-in button when user is not authenticated", () => {
    mockUseSession.mockReturnValue({
      data: null,
      status: "unauthenticated",
      update: jest.fn(),
    });

    render(<AuthButton />);
    expect(
      screen.getByRole("button", { name: /sign in with github/i })
    ).toBeInTheDocument();
  });

  it("calls signIn('github') when sign-in button is clicked", () => {
    mockUseSession.mockReturnValue({
      data: null,
      status: "unauthenticated",
      update: jest.fn(),
    });
    mockSignIn.mockResolvedValue(undefined);

    render(<AuthButton />);
    fireEvent.click(screen.getByRole("button", { name: /sign in with github/i }));

    expect(mockSignIn).toHaveBeenCalledWith("github");
  });

  // ── Authenticated state ──────────────────────────────────────────────────

  it("shows user name and sign-out button when authenticated", () => {
    mockUseSession.mockReturnValue({
      data: {
        user: { name: "Alice", email: "alice@example.com" },
        expires: "2099-01-01",
      },
      status: "authenticated",
      update: jest.fn(),
    });

    render(<AuthButton />);
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });

  it("falls back to email when name is not available", () => {
    mockUseSession.mockReturnValue({
      data: {
        user: { name: null, email: "bob@example.com" },
        expires: "2099-01-01",
      },
      status: "authenticated",
      update: jest.fn(),
    });

    render(<AuthButton />);
    expect(screen.getByText("bob@example.com")).toBeInTheDocument();
  });

  it("falls back to 'User' when neither name nor email is available", () => {
    mockUseSession.mockReturnValue({
      data: {
        user: { name: null, email: null },
        expires: "2099-01-01",
      },
      status: "authenticated",
      update: jest.fn(),
    });

    render(<AuthButton />);
    expect(screen.getByText("User")).toBeInTheDocument();
  });

  it("calls signOut with /login callback when sign-out button is clicked", () => {
    mockUseSession.mockReturnValue({
      data: {
        user: { name: "Alice", email: "alice@example.com" },
        expires: "2099-01-01",
      },
      status: "authenticated",
      update: jest.fn(),
    });
    mockSignOut.mockResolvedValue({ url: "/login" });

    render(<AuthButton />);
    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));

    expect(mockSignOut).toHaveBeenCalledWith({ callbackUrl: "/login" });
  });

  // ── className prop ───────────────────────────────────────────────────────

  it("applies className to wrapper when unauthenticated", () => {
    mockUseSession.mockReturnValue({
      data: null,
      status: "unauthenticated",
      update: jest.fn(),
    });

    const { container } = render(<AuthButton className="test-class" />);
    expect(container.firstChild).toHaveClass("test-class");
  });

  it("applies className to wrapper when authenticated", () => {
    mockUseSession.mockReturnValue({
      data: {
        user: { name: "Alice", email: "alice@example.com" },
        expires: "2099-01-01",
      },
      status: "authenticated",
      update: jest.fn(),
    });

    const { container } = render(<AuthButton className="test-class" />);
    expect(container.firstChild).toHaveClass("test-class");
  });
});
