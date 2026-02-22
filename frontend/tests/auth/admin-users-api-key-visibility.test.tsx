import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminUsers from "../../src/pages/AdminUsers";
import { AdminService } from "../../src/types/generated/services/AdminService";
import { ApiKeysService } from "../../src/types/generated/services/ApiKeysService";

vi.mock("@/contexts/sessionContext", () => ({
  useSession: () => ({
    user: {
      id: "admin-user-id",
      username: "admin.user",
      role: "ADMIN",
      status: "ACTIVE",
    },
  }),
}));

vi.mock("@/contexts/ThemeContext", () => ({
  useTheme: () => ({ resolvedTheme: "dark", themePreference: "dark", setThemePreference: vi.fn() }),
}));

vi.mock("@/types/generated/services/AdminService", () => ({
  AdminService: {
    listUsersApiV1AdminAuthUsersGet: vi.fn(),
    listUserPasskeysApiV1AdminAuthUsersUserIdPasskeysGet: vi.fn(),
  },
}));

vi.mock("@/types/generated/services/ApiKeysService", () => ({
  ApiKeysService: {
    listApiKeysApiV1ApiKeysGet: vi.fn(),
  },
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AdminUsers />
      </BrowserRouter>
    </QueryClientProvider>,
  );
}

describe("AdminUsers API key create visibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(AdminService.listUsersApiV1AdminAuthUsersGet).mockResolvedValue([
      {
        id: "human-id",
        username: "human.user",
        email: "human@example.com",
        accountType: "HUMAN",
        role: "ANALYST",
        status: "ACTIVE",
        mustChangePassword: false,
        lastLoginAt: null,
        createdAt: "2026-01-01T00:00:00Z",
      },
      {
        id: "nhi-id",
        username: "svc.integration",
        email: "",
        accountType: "NHI",
        role: "ANALYST",
        status: "ACTIVE",
        mustChangePassword: false,
        lastLoginAt: null,
        createdAt: "2026-01-01T00:00:00Z",
      },
    ] as any);

    vi.mocked(ApiKeysService.listApiKeysApiV1ApiKeysGet).mockResolvedValue([] as any);
    vi.mocked(
      AdminService.listUserPasskeysApiV1AdminAuthUsersUserIdPasskeysGet,
    ).mockResolvedValue([] as any);
  });

  it("shows create-key action only for NHI users in expanded security row", async () => {
    const user = userEvent.setup();
    renderPage();

    const humanName = await screen.findByText("human.user");
    await screen.findByText("svc.integration");

    const humanRow = humanName.closest("tr");
    const humanExpandButton = humanRow?.querySelector("button");
    expect(humanExpandButton).toBeTruthy();
    await user.click(humanExpandButton as HTMLButtonElement);

    await waitFor(() => {
      expect(
        screen.getByText("Human users create keys from Profile Management"),
      ).toBeInTheDocument();
    });

    const nhiName = screen.getByText("svc.integration");
    const nhiRow = nhiName.closest("tr");
    const nhiExpandButton = nhiRow?.querySelector("button");
    expect(nhiExpandButton).toBeTruthy();
    await user.click(nhiExpandButton as HTMLButtonElement);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /new key/i })).toBeInTheDocument();
    });
  });
});
