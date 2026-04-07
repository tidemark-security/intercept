import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";

import { ChangePasswordForm } from "@/components/auth/ChangePasswordForm";
import { type SessionContextValue } from "../../src/contexts/sessionContext";
import { AuthenticationService } from "../../src/types/generated/services/AuthenticationService";
import { ApiError } from "../../src/types/generated/core/ApiError";
import { renderWithProviders } from "../test-utils";

// Mock the AuthenticationService
vi.mock("../../src/types/generated/services/AuthenticationService", () => ({
  AuthenticationService: {
    changePasswordApiV1AuthPasswordChangePost: vi.fn(),
  },
}));

function createSessionValue(
  overrides: Partial<SessionContextValue> = {}
): SessionContextValue {
  return {
    status: "authenticated",
    user: {
      id: "1",
      username: "analyst",
      role: "ANALYST",
      status: "ACTIVE",
    },
    session: null,
    mustChangePassword: true,
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
    isAnalyst: true,
    isAuditor: false,
    ...overrides,
  };
}

describe("ChangePasswordForm - Forced Change", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders forced password change form with warning banner", () => {
    const sessionValue = createSessionValue();

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    expect(screen.getByText("Change Password Required")).toBeInTheDocument();
    expect(
      screen.getByText(/you must change your password to continue/i)
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/enter your current password/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter your new password")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Re-enter your new password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /change password/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument();
  });

  it("does not render warning banner for voluntary password change", () => {
    const sessionValue = createSessionValue({ mustChangePassword: false });

    renderWithProviders(<ChangePasswordForm forced={false} />, { sessionValue });

    expect(
      screen.queryByText(/you must change your password to continue/i)
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /logout/i })).not.toBeInTheDocument();
  });

  it("submits password change request with valid credentials", async () => {
    const setMustChangePassword = vi.fn();
    const sessionValue = createSessionValue({ setMustChangePassword });
    const changePasswordMock = vi.mocked(
      AuthenticationService.changePasswordApiV1AuthPasswordChangePost
    );
    changePasswordMock.mockResolvedValue(undefined);

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const user = userEvent.setup();
    const currentPasswordInput = screen.getByPlaceholderText("Enter your current password");
    const newPasswordInput = screen.getByPlaceholderText("Enter your new password");
    const confirmPasswordInput = screen.getByPlaceholderText("Re-enter your new password");

    await user.type(currentPasswordInput, "OldPassword123!");
    await user.type(newPasswordInput, "NewPassword456!");
    await user.type(confirmPasswordInput, "NewPassword456!");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    expect(changePasswordMock).toHaveBeenCalledWith({
      requestBody: {
        currentPassword: "OldPassword123!",
        newPassword: "NewPassword456!",
      },
    });

    await waitFor(() => {
      expect(setMustChangePassword).toHaveBeenCalledWith(false);
      expect(screen.getByText(/password changed successfully/i)).toBeInTheDocument();
    });
  });

  it("displays error when current password is incorrect", async () => {
    const sessionValue = createSessionValue();
    const changePasswordMock = vi.mocked(
      AuthenticationService.changePasswordApiV1AuthPasswordChangePost
    );
    changePasswordMock.mockRejectedValue(
      new ApiError(
        { method: "POST", url: "/api/v1/auth/password/change" } as any,
        {
          status: 401,
          statusText: "Unauthorized",
          body: { detail: "Invalid current password" },
        } as any,
        "Invalid current password"
      )
    );

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Enter your current password"), "WrongPassword123!");
    await user.type(screen.getByPlaceholderText("Enter your new password"), "NewPassword456!");
    await user.type(screen.getByPlaceholderText("Re-enter your new password"), "NewPassword456!");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(screen.getByText(/current password is incorrect/i)).toBeInTheDocument();
    });
  });

  it("validates that new password meets policy requirements", async () => {
    const sessionValue = createSessionValue();

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Enter your current password"), "OldPassword123!");
    await user.type(screen.getByPlaceholderText("Enter your new password"), "weak");
    await user.type(screen.getByPlaceholderText("Re-enter your new password"), "weak");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/password must be at least 12 characters long/i)
      ).toBeInTheDocument();
    });
  });

  it("validates that new passwords match", async () => {
    const sessionValue = createSessionValue();

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Enter your current password"), "OldPassword123!");
    await user.type(screen.getByPlaceholderText("Enter your new password"), "NewPassword456!");
    await user.type(screen.getByPlaceholderText("Re-enter your new password"), "DifferentPassword789!");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(screen.getByText(/new passwords do not match/i)).toBeInTheDocument();
    });
  });

  it("validates password complexity - uppercase required", async () => {
    const sessionValue = createSessionValue();

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Enter your current password"), "OldPassword123!");
    await user.type(screen.getByPlaceholderText("Enter your new password"), "newpassword123!");
    await user.type(screen.getByPlaceholderText("Re-enter your new password"), "newpassword123!");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/password must include at least one uppercase letter/i)
      ).toBeInTheDocument();
    });
  });

  it("validates password complexity - lowercase required", async () => {
    const sessionValue = createSessionValue();

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Enter your current password"), "OldPassword123!");
    await user.type(screen.getByPlaceholderText("Enter your new password"), "NEWPASSWORD123!");
    await user.type(screen.getByPlaceholderText("Re-enter your new password"), "NEWPASSWORD123!");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/password must include at least one lowercase letter/i)
      ).toBeInTheDocument();
    });
  });

  it("validates password complexity - number required", async () => {
    const sessionValue = createSessionValue();

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Enter your current password"), "OldPassword123!");
    await user.type(screen.getByPlaceholderText("Enter your new password"), "NewPassword!");
    await user.type(screen.getByPlaceholderText("Re-enter your new password"), "NewPassword!");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/password must include at least one number/i)
      ).toBeInTheDocument();
    });
  });

  it("validates password complexity - special character required", async () => {
    const sessionValue = createSessionValue();

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Enter your current password"), "OldPassword123!");
    await user.type(screen.getByPlaceholderText("Enter your new password"), "NewPassword123");
    await user.type(screen.getByPlaceholderText("Re-enter your new password"), "NewPassword123");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/password must include at least one special character/i)
      ).toBeInTheDocument();
    });
  });

  it("disables submit button when fields are empty", () => {
    const sessionValue = createSessionValue();

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const submitButton = screen.getByRole("button", { name: /change password/i });
    expect(submitButton).toBeDisabled();
  });

  it("shows loading state during password change submission", async () => {
    const sessionValue = createSessionValue();
    const changePasswordMock = vi.mocked(
      AuthenticationService.changePasswordApiV1AuthPasswordChangePost
    );
    // Make the API call take some time
    let resolvePromise: () => void;
    const pendingPromise = new Promise<void>((resolve) => {
      resolvePromise = resolve;
    });
    changePasswordMock.mockReturnValue(pendingPromise as any);

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Enter your current password"), "OldPassword123!");
    await user.type(screen.getByPlaceholderText("Enter your new password"), "NewPassword456!");
    await user.type(screen.getByPlaceholderText("Re-enter your new password"), "NewPassword456!");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    expect(screen.getByText(/changing password/i)).toBeInTheDocument();
    
    const submitButton = screen.getByRole("button", { name: /changing password/i });
    expect(submitButton).toBeDisabled();
    
    // Clean up by resolving the promise
    await act(async () => {
      resolvePromise!();
      await pendingPromise;
    });
  });

  it("calls logout when logout button is clicked", async () => {
    const logout = vi.fn().mockResolvedValue(undefined);
    const sessionValue = createSessionValue({ logout });

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /logout/i }));

    expect(logout).toHaveBeenCalled();
  });

  it("displays password policy requirements as help text", () => {
    const sessionValue = createSessionValue();

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    expect(
      screen.getByText(
        /minimum 12 characters with uppercase, lowercase, number, and special character/i
      )
    ).toBeInTheDocument();
  });

  it("clears error when user starts typing", async () => {
    const sessionValue = createSessionValue();
    const changePasswordMock = vi.mocked(
      AuthenticationService.changePasswordApiV1AuthPasswordChangePost
    );
    changePasswordMock.mockRejectedValueOnce(
      new ApiError(
        { method: "POST", url: "/api/v1/auth/password/change" } as any,
        {
          status: 401,
          statusText: "Unauthorized",
          body: { detail: "Invalid current password" },
        } as any,
        "Invalid current password"
      )
    );

    renderWithProviders(<ChangePasswordForm forced={true} />, { sessionValue });

    const user = userEvent.setup();
    
    // First submission with error
    await user.type(screen.getByPlaceholderText("Enter your current password"), "Wrong");
    await user.type(screen.getByPlaceholderText("Enter your new password"), "NewPassword456!");
    await user.type(screen.getByPlaceholderText("Re-enter your new password"), "NewPassword456!");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(screen.getByText(/current password is incorrect/i)).toBeInTheDocument();
    });

    // Start typing again - error should clear
    await user.clear(screen.getByPlaceholderText("Enter your current password"));
    await user.type(screen.getByPlaceholderText("Enter your current password"), "C");

    expect(screen.queryByText(/current password is incorrect/i)).not.toBeInTheDocument();
  });
});
