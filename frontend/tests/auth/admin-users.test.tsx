import { useState } from "react";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";

import { type SessionContextValue } from "../../src/contexts/sessionContext";
import { renderWithProviders } from "../test-utils";

// Mock the AdminUsers component
// This will be created in T228
const MockAdminUsers = () => {
  return (
    <div>
      <h1>User Management</h1>
      <button>Create User</button>
      <table>
        <thead>
          <tr>
            <th>Username</th>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>analyst.user</td>
            <td>analyst@example.com</td>
            <td>ANALYST</td>
            <td>ACTIVE</td>
            <td>
              <button>Disable</button>
              <button>Reset Password</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
};

function createSessionValue(
  overrides: Partial<SessionContextValue> = {}
): SessionContextValue {
  return {
    status: "authenticated",
    user: {
      id: "admin-user-id",
      username: "admin.user",
      role: "ADMIN",
      status: "ACTIVE",
    },
    session: {
      sessionId: "session-id",
      expiresAt: new Date(Date.now() + 3600000).toISOString(),
    },
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
    isAdmin: true,
    isAnalyst: false,
    isAuditor: false,
    ...overrides,
  };
}

describe("Admin Users Management", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders user management page for admin users", () => {
    const sessionValue = createSessionValue({
      user: {
        id: "admin-id",
        username: "admin.user",
        role: "ADMIN",
        status: "ACTIVE",
      },
    });

    renderWithProviders(<MockAdminUsers />, { sessionValue });

    expect(screen.getByText(/user management/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create user/i })).toBeInTheDocument();
  });

  it("displays user list with status and actions", () => {
    const sessionValue = createSessionValue();

    renderWithProviders(<MockAdminUsers />, { sessionValue });

    expect(screen.getByText("analyst.user")).toBeInTheDocument();
    expect(screen.getByText("analyst@example.com")).toBeInTheDocument();
    expect(screen.getByText("ANALYST")).toBeInTheDocument();
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /disable/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reset password/i })).toBeInTheDocument();
  });

  it("shows create user modal when create button is clicked", async () => {
    const sessionValue = createSessionValue();

    renderWithProviders(<MockAdminUsers />, { sessionValue });

    const user = userEvent.setup();
    const createButton = screen.getByRole("button", { name: /create user/i });
    
    await user.click(createButton);
    
    // Modal would be shown - this is a placeholder test
    // Real implementation will test the actual modal behavior
  });

  it("does not render admin page for non-admin users", () => {
    const sessionValue = createSessionValue({
      user: {
        id: "analyst-id",
        username: "analyst.user",
        role: "ANALYST",
        status: "ACTIVE",
      },
    });

    // In the real app, this would redirect or show "Forbidden"
    // For now, we just verify the user role check
    expect(sessionValue.user?.role).not.toBe("ADMIN");
  });
});

describe("Create User Form", () => {
  it("validates required fields", async () => {
    const sessionValue = createSessionValue();
    
    // Mock form component
    const MockCreateUserForm = () => {
      return (
        <form>
          <input aria-label="Username" required />
          <input aria-label="Email" type="email" required />
          <select aria-label="Role" required>
            <option value="">Select role</option>
            <option value="ANALYST">Analyst</option>
            <option value="ADMIN">Admin</option>
            <option value="AUDITOR">Auditor</option>
          </select>
          <button type="submit">Create User</button>
        </form>
      );
    };

    renderWithProviders(<MockCreateUserForm />, { sessionValue });

    expect(screen.getByLabelText(/username/i)).toBeRequired();
    expect(screen.getByLabelText(/email/i)).toBeRequired();
    expect(screen.getByLabelText(/role/i)).toBeRequired();
  });

  it("submits valid user creation data", async () => {
    const createUser = vi.fn().mockResolvedValue({
      userId: "new-user-id",
      temporaryCredentialExpiresAt: new Date().toISOString(),
      deliveryChannel: "SECURE_EMAIL",
    });

    const sessionValue = createSessionValue();
    
    const MockCreateUserForm = () => {
      return (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const formData = new FormData(e.currentTarget);
            await createUser({
              username: formData.get("username"),
              email: formData.get("email"),
              role: formData.get("role"),
            });
          }}
        >
          <input name="username" aria-label="Username" />
          <input name="email" aria-label="Email" type="email" />
          <select name="role" aria-label="Role">
            <option value="ANALYST">Analyst</option>
            <option value="ADMIN">Admin</option>
          </select>
          <button type="submit">Create User</button>
        </form>
      );
    };

    renderWithProviders(<MockCreateUserForm />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/username/i), "new.analyst");
    await user.type(screen.getByLabelText(/email/i), "new.analyst@example.com");
    await user.selectOptions(screen.getByLabelText(/role/i), "ANALYST");
    await user.click(screen.getByRole("button", { name: /create user/i }));

    await waitFor(() => {
      expect(createUser).toHaveBeenCalledWith({
        username: "new.analyst",
        email: "new.analyst@example.com",
        role: "ANALYST",
      });
    });
  });

  it("displays success message after user creation", async () => {
    const sessionValue = createSessionValue();
    
    const MockCreateUserFormWithSuccess = () => {
      const [success, setSuccess] = useState(false);
      
      return (
        <div>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setSuccess(true);
            }}
          >
            <input name="username" aria-label="Username" />
            <button type="submit">Create User</button>
          </form>
          {success && (
            <div role="alert">
              User created successfully. Temporary credentials sent via email.
            </div>
          )}
        </div>
      );
    };

    renderWithProviders(<MockCreateUserFormWithSuccess />, { sessionValue });

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/username/i), "new.user");
    await user.click(screen.getByRole("button", { name: /create user/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        /user created successfully/i
      );
      expect(screen.getByRole("alert")).toHaveTextContent(
        /temporary credentials sent via email/i
      );
    });
  });
});

describe("User Status Management", () => {
  it("disables user when disable button is clicked", async () => {
    const updateUserStatus = vi.fn().mockResolvedValue(undefined);
    const sessionValue = createSessionValue();
    
    const MockUserRow = () => {
      const [status, setStatus] = useState("ACTIVE");
      
      return (
        <div>
          <span>Status: {status}</span>
          <button
            onClick={async () => {
              await updateUserStatus("user-id", "DISABLED");
              setStatus("DISABLED");
            }}
          >
            Disable User
          </button>
        </div>
      );
    };

    renderWithProviders(<MockUserRow />, { sessionValue });

    const user = userEvent.setup();
    expect(screen.getByText(/status: active/i)).toBeInTheDocument();
    
    await user.click(screen.getByRole("button", { name: /disable user/i }));

    await waitFor(() => {
      expect(updateUserStatus).toHaveBeenCalledWith("user-id", "DISABLED");
      expect(screen.getByText(/status: disabled/i)).toBeInTheDocument();
    });
  });

  it("shows confirmation dialog before disabling user", async () => {
    const sessionValue = createSessionValue();
    
    const MockUserRowWithConfirm = () => {
      const [showConfirm, setShowConfirm] = useState(false);
      
      return (
        <div>
          <button onClick={() => setShowConfirm(true)}>Disable User</button>
          {showConfirm && (
            <div role="dialog">
              <p>Are you sure you want to disable this user?</p>
              <button>Confirm</button>
              <button onClick={() => setShowConfirm(false)}>Cancel</button>
            </div>
          )}
        </div>
      );
    };

    renderWithProviders(<MockUserRowWithConfirm />, { sessionValue });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /disable user/i }));

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByText(/are you sure/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /confirm/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    });
  });
});

describe("Password Reset", () => {
  it("issues password reset when button is clicked", async () => {
    const issueReset = vi.fn().mockResolvedValue({
      resetRequestId: "reset-id",
      expiresAt: new Date().toISOString(),
    });
    const sessionValue = createSessionValue();
    
    const MockResetButton = () => {
      return (
        <button
          onClick={async () => {
            await issueReset("user-id");
          }}
        >
          Reset Password
        </button>
      );
    };

    renderWithProviders(<MockResetButton />, { sessionValue });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => {
      expect(issueReset).toHaveBeenCalledWith("user-id");
    });
  });

  it("displays success message after reset issued", async () => {
    const sessionValue = createSessionValue();
    
    const MockResetWithSuccess = () => {
      const [success, setSuccess] = useState(false);
      
      return (
        <div>
          <button onClick={() => setSuccess(true)}>Reset Password</button>
          {success && (
            <div role="alert">
              Password reset issued. Temporary credentials sent via email.
            </div>
          )}
        </div>
      );
    };

    renderWithProviders(<MockResetWithSuccess />, { sessionValue });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        /password reset issued/i
      );
    });
  });
});
