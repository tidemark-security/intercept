import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SessionContextValue } from "@/contexts/sessionContext";
import { renderWithProviders } from "../../tests/test-utils";
import AdminSettings from "./AdminSettings";

const adminServiceMock = vi.hoisted(() => ({
  getSettings: vi.fn(),
  getMaxMindDatabases: vi.fn(),
  getProviderStatuses: vi.fn(),
}));

const setupLangflow = vi.hoisted(() => vi.fn());

vi.mock("@/types/generated/services/AdminService", () => ({
  AdminService: {
    getAllSettingsApiV1AdminSettingsGet: adminServiceMock.getSettings,
    getMaxmindDatabaseStatusApiV1AdminEnrichmentsMaxmindDatabasesGet:
      adminServiceMock.getMaxMindDatabases,
    getProviderStatusesApiV1AdminEnrichmentsProvidersGet:
      adminServiceMock.getProviderStatuses,
  },
}));

vi.mock("@/types/generated/services/LangflowService", () => ({
  LangflowService: {
    setupInterceptMcpServerApiV1LangflowAdminSetupInterceptMcpPost: setupLangflow,
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

describe("AdminSettings MCP guidance", () => {
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

  it.each([
    { label: "deployment default", override: null, expectedBase: "http://backend:8000" },
    {
      label: "custom URL",
      override: "https://intercept.example/prefix/mcp/streamable/",
      expectedBase: "https://intercept.example/prefix",
    },
  ])("submits the Langflow MCP $label", async ({ override, expectedBase }) => {
    const defaultUrl = "http://backend:8000/mcp/streamable/";
    adminServiceMock.getSettings.mockResolvedValue([
      {
        key: "langflow.intercept_mcp_url",
        value: defaultUrl,
        local_only: true,
        source: "env",
      },
    ]);
    setupLangflow.mockResolvedValue({ success: true, steps: [] });
    renderWithProviders(<AdminSettings />, { sessionValue: adminSession });

    fireEvent.click(await screen.findByText("Open Wizard"));
    fireEvent.click(screen.getByText("Continue"));
    const input = screen.getByPlaceholderText(defaultUrl);
    expect(input).toHaveValue(defaultUrl);
    if (override) fireEvent.change(input, { target: { value: override } });
    fireEvent.click(screen.getByText("Run Setup"));

    await waitFor(() => expect(setupLangflow).toHaveBeenCalledWith({
      requestBody: { backend_api_base_url: expectedBase, nhi_username: "tidemark_ai" },
    }));
  });
});
