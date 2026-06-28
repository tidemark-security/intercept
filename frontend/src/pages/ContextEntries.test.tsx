import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../tests/test-utils";
import type { SessionContextValue } from "@/contexts/sessionContext";
import type { ContextEntry } from "@/services/contextEntriesApi";
import { listContextEntries } from "@/services/contextEntriesApi";
import ContextEntries from "./ContextEntries";

vi.mock("@/services/contextEntriesApi", async () => {
  const actual = await vi.importActual<typeof import("@/services/contextEntriesApi")>("@/services/contextEntriesApi");
  return {
    ...actual,
    listContextEntries: vi.fn(),
    createContextEntry: vi.fn(),
    updateContextEntry: vi.fn(),
    expireContextEntry: vi.fn(),
  };
});

const sessionValue: SessionContextValue = {
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
  isAnalyst: true,
  isAuditor: false,
};

const entries: ContextEntry[] = [
  {
    id: 11,
    criteria: [{ type: "ALERT_SOURCE", value: "EDR" }],
    body: "Customer DNS backup window context",
    author: "admin",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    expires_at: "2026-07-01T00:00:00Z",
    expired_at: null,
  },
  {
    id: 12,
    criteria: [{ type: "SYSTEM", value: "prod-dns-*" }],
    body: "Prod resolver maintenance context",
    author: "secops",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    expires_at: "2026-07-02T00:00:00Z",
    expired_at: null,
  },
  {
    id: 99,
    criteria: [{ type: "TAG", value: "unrelated" }],
    body: "Unrelated context entry",
    author: "admin",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    expires_at: "2026-07-03T00:00:00Z",
    expired_at: null,
  },
];

function renderContextEntriesAt(path: string) {
  window.history.pushState({}, "", path);

  return renderWithProviders(<ContextEntries />, { sessionValue });
}

describe("ContextEntries URL filters", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listContextEntries).mockResolvedValue(entries);
  });

  it("filters visible entries by ids from the URL", async () => {
    renderContextEntriesAt("/context-entries?ids=11,12");

    expect(await screen.findByText("Customer DNS backup window context")).toBeInTheDocument();
    expect(screen.getByText("Prod resolver maintenance context")).toBeInTheDocument();
    expect(screen.queryByText("Unrelated context entry")).not.toBeInTheDocument();
    expect(screen.getByText("Filtered context ids")).toBeInTheDocument();
    expect(screen.getByText("11")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("initializes search from the q URL parameter", async () => {
    renderContextEntriesAt("/context-entries?q=resolver");

    expect(await screen.findByDisplayValue("resolver")).toBeInTheDocument();
    expect(await screen.findByText("Prod resolver maintenance context")).toBeInTheDocument();
    expect(screen.queryByText("Customer DNS backup window context")).not.toBeInTheDocument();
  });

  it("initializes the expired toggle and query from include_expired=true", async () => {
    renderContextEntriesAt("/context-entries?include_expired=true");

    await waitFor(() => {
      expect(listContextEntries).toHaveBeenCalledWith(true);
    });
    expect(screen.getByRole("switch", { name: "Show expired context entries" })).toBeChecked();
  });
});
