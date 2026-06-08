import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChangePasswordForm } from "./ChangePasswordForm";
import { AuthenticationService } from "@/types/generated/services/AuthenticationService";
import { ThemeProvider } from "@/contexts/ThemeContext";

const setMustChangePassword = vi.fn();
const logout = vi.fn();
const navigate = vi.fn();

vi.mock("@/contexts/sessionContext", () => ({
  useSession: () => ({
    setMustChangePassword,
    logout,
  }),
}));

vi.mock("@/hooks/useViewTransitionNavigate", () => ({
  useViewTransitionNavigate: () => navigate,
}));

vi.mock("@/types/generated/services/AuthenticationService", () => ({
  AuthenticationService: {
    changePasswordApiV1AuthPasswordChangePost: vi.fn(),
  },
}));

describe("ChangePasswordForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows new-password complexity errors on the new password field, not the current password field", async () => {
    const user = userEvent.setup();

    render(
      <ThemeProvider>
        <ChangePasswordForm forced />
      </ThemeProvider>,
    );

    await user.type(screen.getByPlaceholderText("Enter your current password"), "legacy-password");
    await user.type(screen.getByPlaceholderText("Enter your new password"), "lowercase123!");
    await user.type(screen.getByPlaceholderText("Re-enter your new password"), "lowercase123!");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    const currentPasswordField = screen.getByPlaceholderText("Enter your current password").closest("label");
    const newPasswordField = screen.getByPlaceholderText("Enter your new password").closest("label");

    expect(currentPasswordField).not.toHaveTextContent("Password must include at least one uppercase letter");
    expect(newPasswordField).toHaveTextContent("Password must include at least one uppercase letter");
    expect(AuthenticationService.changePasswordApiV1AuthPasswordChangePost).not.toHaveBeenCalled();
  });

  it("submits when the pre-existing password is non-complex but the new password meets policy", async () => {
    vi.mocked(AuthenticationService.changePasswordApiV1AuthPasswordChangePost).mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <ThemeProvider>
        <ChangePasswordForm forced />
      </ThemeProvider>,
    );

    await user.type(screen.getByPlaceholderText("Enter your current password"), "legacy-password");
    await user.type(screen.getByPlaceholderText("Enter your new password"), "NewPassword123!");
    await user.type(screen.getByPlaceholderText("Re-enter your new password"), "NewPassword123!");
    await user.click(screen.getByRole("button", { name: /change password/i }));

    expect(AuthenticationService.changePasswordApiV1AuthPasswordChangePost).toHaveBeenCalledWith({
      requestBody: {
        currentPassword: "legacy-password",
        newPassword: "NewPassword123!",
      },
    });
  });
});
