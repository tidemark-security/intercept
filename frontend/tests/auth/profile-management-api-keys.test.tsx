import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProfileManagement from "../../src/pages/ProfileManagement";
import { ApiKeysService } from "../../src/types/generated/services/ApiKeysService";
import { AuthenticationService } from "../../src/types/generated/services/AuthenticationService";
import { renderWithProviders } from "../test-utils";

const renderPage = () => {
  return renderWithProviders(<ProfileManagement />);
};

const showToast = vi.fn();

vi.mock("@/contexts/ToastContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/contexts/ToastContext")>();
  return {
    ...actual,
    useToast: () => ({ showToast }),
  };
});

vi.mock("@/types/generated/services/AuthenticationService", () => ({
  AuthenticationService: {
    listOwnPasskeysApiV1AuthPasskeysGet: vi.fn(),
    changePasswordApiV1AuthPasswordChangePost: vi.fn(),
    beginPasskeyRegistrationApiV1AuthPasskeysRegisterOptionsPost: vi.fn(),
    finishPasskeyRegistrationApiV1AuthPasskeysRegisterVerifyPost: vi.fn(),
    renameOwnPasskeyApiV1AuthPasskeysPasskeyIdPatch: vi.fn(),
    revokeOwnPasskeyApiV1AuthPasskeysPasskeyIdDelete: vi.fn(),
  },
}));

vi.mock("@/types/generated/services/ApiKeysService", () => ({
  ApiKeysService: {
    listApiKeysApiV1ApiKeysGet: vi.fn(),
    createApiKeyApiV1ApiKeysPost: vi.fn(),
    revokeApiKeyApiV1ApiKeysApiKeyIdDelete: vi.fn(),
  },
}));

describe("ProfileManagement API keys", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(AuthenticationService.listOwnPasskeysApiV1AuthPasskeysGet).mockResolvedValue([]);

    vi.mocked(ApiKeysService.listApiKeysApiV1ApiKeysGet).mockResolvedValue([
      {
        id: "key-1",
        user_id: "user-1",
        name: "primary-key",
        prefix: "ik_live_abc",
        expires_at: "2030-01-01T00:00:00Z",
        last_used_at: null,
        revoked_at: null,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
  });

  it("loads and displays own API keys", async () => {
    renderPage();

    await waitFor(() => {
      expect(ApiKeysService.listApiKeysApiV1ApiKeysGet).toHaveBeenCalledWith({
        includeRevoked: true,
      });
    });

    expect(await screen.findByText("primary-key")).toBeInTheDocument();
  });

  it("creates an API key for self without user_id", async () => {
    vi.mocked(ApiKeysService.createApiKeyApiV1ApiKeysPost).mockResolvedValue({
      id: "key-2",
      user_id: "user-1",
      name: "new-key",
      prefix: "ik_live_xyz",
      expires_at: "2030-02-01T00:00:00Z",
      last_used_at: null,
      revoked_at: null,
      created_at: "2026-02-01T00:00:00Z",
      key: "ik_live_xyz_secret",
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /create new api key/i }));
    await user.type(screen.getByPlaceholderText("Automation Key"), "new-key");
    await user.click(screen.getByRole("button", { name: /create key/i }));

    await waitFor(() => {
      expect(ApiKeysService.createApiKeyApiV1ApiKeysPost).toHaveBeenCalledTimes(1);
    });

    const createCallArg = vi.mocked(ApiKeysService.createApiKeyApiV1ApiKeysPost).mock.calls[0]?.[0];
    expect(createCallArg?.requestBody.name).toBe("new-key");
    expect(createCallArg?.requestBody.expires_at).toBeTruthy();
    expect(createCallArg?.requestBody).not.toHaveProperty("user_id");
  });

  it("revokes an existing own API key", async () => {
    vi.mocked(ApiKeysService.revokeApiKeyApiV1ApiKeysApiKeyIdDelete).mockResolvedValue(undefined);

    const user = userEvent.setup();
    renderPage();

    const keyName = await screen.findByText("primary-key");
    let cardContainer: HTMLElement | null = keyName.parentElement;
    while (cardContainer && cardContainer.querySelectorAll("button").length === 0) {
      cardContainer = cardContainer.parentElement;
    }

    const revokeButton = cardContainer?.querySelector("button");
    if (!revokeButton) {
      throw new Error("Could not find revoke API key button");
    }

    await user.click(revokeButton as HTMLButtonElement);

    await waitFor(() => {
      expect(ApiKeysService.revokeApiKeyApiV1ApiKeysApiKeyIdDelete).toHaveBeenCalledWith({
        apiKeyId: "key-1",
      });
    });
  });
});
