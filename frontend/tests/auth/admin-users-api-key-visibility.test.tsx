import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminUsers from "../../src/pages/AdminUsers";
import { AdminService } from "../../src/types/generated/services/AdminService";
import { ApiKeysService } from "../../src/types/generated/services/ApiKeysService";
import { renderWithProviders } from "../test-utils";

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

vi.mock("@/types/generated/services/AdminService", () => ({
  AdminService: {
    createNhiAccountApiV1AdminAuthUsersNhiPost: vi.fn(),
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
  return renderWithProviders(<AdminUsers />);
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
      AdminService.createNhiAccountApiV1AdminAuthUsersNhiPost,
    ).mockResolvedValue({
      userId: "created-nhi-id",
      username: "svc.least-privilege",
      role: "ANALYST",
      apiKey: {
        id: "created-api-key-id",
        user_id: "created-nhi-id",
        name: "production-key",
        prefix: "tmi_created",
        key: "tmi_created-secret",
        expires_at: "2030-01-01T00:00:00Z",
        scopes: ["api:read"],
      },
    } as any);
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

  it("creates the initial NHI key with an explicit least-privilege scope", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("human.user");
    await user.click(screen.getByRole("button", { name: /add user/i }));
    await user.click(screen.getByRole("button", { name: /service \(nhi\)/i }));

    expect(screen.getByText("Permissions")).toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: "Remove Read API" }),
    ).toBeChecked();

    await user.type(screen.getByPlaceholderText("svc.integration"), "svc.least-privilege");
    await user.type(screen.getByPlaceholderText("production-key"), "production-key");
    const expirationInput = document.querySelector<HTMLInputElement>(
      'input[type="datetime-local"]',
    );
    expect(expirationInput).not.toBeNull();
    fireEvent.change(expirationInput as HTMLInputElement, {
      target: { value: "2030-01-01T00:00" },
    });

    await user.click(
      screen.getByRole("button", { name: /create service account/i }),
    );

    await waitFor(() => {
      expect(
        AdminService.createNhiAccountApiV1AdminAuthUsersNhiPost,
      ).toHaveBeenCalledWith({
        requestBody: expect.objectContaining({
          initial_api_key_scopes: ["api:read"],
        }),
      });
    });
  });
});
