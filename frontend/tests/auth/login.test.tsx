import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import Login from "../../src/pages/Login";
import { type SessionContextValue } from "../../src/contexts/sessionContext";
import { renderWithProviders } from "../test-utils";

function createSessionValue(
  overrides: Partial<SessionContextValue> = {}
): SessionContextValue {
  return {
    status: "unauthenticated",
    user: null,
    session: null,
    mustChangePassword: false,
    lockout: null,
    error: null,
    login: vi.fn().mockResolvedValue(undefined),
    loginWithPasskey: vi.fn().mockResolvedValue("failed"),
    logout: vi.fn().mockResolvedValue(undefined),
    refreshSession: vi.fn().mockResolvedValue(undefined),
    resolveError: vi.fn(),
    acknowledgeLockout: vi.fn(),
    setMustChangePassword: vi.fn(),
    isAdmin: false,
    isAnalyst: false,
    isAuditor: false,
    ...overrides,
  };
}

describe("Login page", () => {
  it("shows password step when no passkey is available", async () => {
    const loginWithPasskey = vi.fn().mockResolvedValue("password_required");
    const sessionValue = createSessionValue({ loginWithPasskey });

    renderWithProviders(<Login />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/username/i), "analyst");
    await user.click(screen.getByRole("button", { name: /continue/i }));

    expect(loginWithPasskey).toHaveBeenCalledWith("analyst");
    await screen.findByPlaceholderText(/enter your password/i);
  });

  it("submits credentials through the session context after continue", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    const loginWithPasskey = vi.fn().mockResolvedValue("password_required");
    const sessionValue = createSessionValue({ login, loginWithPasskey });

    renderWithProviders(<Login />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/username/i), "analyst");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    const passwordInput = await screen.findByPlaceholderText(/enter your password/i);
    await user.type(passwordInput, "TestPassword123!");
    await user.keyboard("{Enter}");

    expect(login).toHaveBeenCalledWith({ username: "analyst", password: "TestPassword123!" });
  });

  it("returns to username step when passkey prompt is cancelled", async () => {
    const loginWithPasskey = vi.fn().mockResolvedValue("cancelled");
    const sessionValue = createSessionValue({
      loginWithPasskey,
    });

    renderWithProviders(<Login />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/username/i), "analyst");
    await user.click(screen.getByRole("button", { name: /continue/i }));

    expect(loginWithPasskey).toHaveBeenCalledWith("analyst");
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
  });
});
