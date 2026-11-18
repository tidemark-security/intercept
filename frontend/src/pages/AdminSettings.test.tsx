import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SessionContextValue } from "@/contexts/sessionContext";
import { renderWithProviders } from "../../tests/test-utils";
import AdminSettings from "./AdminSettings";

const adminServiceMock = vi.hoisted(() => ({
  getSettings: vi.fn(),
  getMaxMindDatabases: vi.fn(),
  getProviderStatuses: vi.fn(),
}));

vi.mock("@/types/generated/services/AdminService", () => ({
  AdminService: {
    getAllSettingsApiV1AdminSettingsGet: adminServiceMock.getSettings,
    getMaxmindDatabaseStatusApiV1AdminEnrichmentsMaxmindDatabasesGet:
      adminServiceMock.getMaxMindDatabases,
    getProviderStatusesApiV1AdminEnrichmentsProvidersGet:
      adminServiceMock.getProviderStatuses,
  },
}));

const adminSession: SessionContextValue = {
  status: "authenticated",
  user: {
    id: "user-admin",
    username: "admin",
    role: "ADMIN",
    status: "ACTIVE",
  },
  session: null,
  mustChangePassword: false,
  localCredentialManagementAllowed: true,
  lockout: null,
  error: null,
  login: vi.fn(),
  loginWithPasskey: vi.fn(),
  logout: vi.fn(),
  refreshSession: vi.fn(),
  resolveError: vi.fn(),
  acknowledgeLockout: vi.fn(),
  setMustChangePassword: vi.fn(),
  isAdmin: true,
  isAnalyst: false,
  isAuditor: false,
};

describe("AdminSettings MCP authentication guidance", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    adminServiceMock.getSettings.mockResolvedValue([
      {
        key: "oidc.enabled",
        value: "false",
        value_type: "BOOLEAN",
        is_secret: false,
        local_only: false,
        category: "oidc",
        description: "Enable OpenID Connect single sign-on",
        source: "default",
      },
      {
        key: "mcp.oauth.enabled",
        value: "true",
        value_type: "BOOLEAN",
        is_secret: false,
        local_only: false,
        category: "mcp",
        description: "Enable MCP authentication",
        source: "default",
      },
    ]);
    adminServiceMock.getMaxMindDatabases.mockResolvedValue([]);
    adminServiceMock.getProviderStatuses.mockResolvedValue([]);
  });

  it("tells administrators that MCP auth topology changes need a backend restart", async () => {
    renderWithProviders(<AdminSettings />, { sessionValue: adminSession });

    expect(await screen.findByText("Backend restart required")).toBeVisible();
    expect(
      screen.getByText(/FastMCP selects its OIDC proxy or local OAuth provider/),
    ).toBeVisible();

    fireEvent.click(
      screen.getByRole("button", { name: /Mcp.*1 settings/i }),
    );
    expect(screen.getAllByText("Backend restart required")).toHaveLength(2);
  });
});
