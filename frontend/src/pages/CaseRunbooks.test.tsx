import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../tests/test-utils";
import type { SessionContextValue } from "@/contexts/sessionContext";
import type { CaseRunbookRead } from "@/types/caseRunbooks";
import CaseRunbooksPage from "./CaseRunbooks";

const mockCreateRunbook = vi.hoisted(() => vi.fn());
const mockUpdateRunbook = vi.hoisted(() => vi.fn());
const mockPublishRunbook = vi.hoisted(() => vi.fn());
const mockDisableRunbook = vi.hoisted(() => vi.fn());
const mockDeleteRunbook = vi.hoisted(() => vi.fn());

const runbooks: CaseRunbookRead[] = [
  {
    id: 7,
    human_id: "RUN-0000007",
    title: "Credential Theft Response",
    description: "Identity containment and recovery workflow",
    status: "PUBLISHED",
    case_tags: ["identity", "credential-theft"],
    runbook_tasks: [
      {
        title: "Review identity provider logs",
        description: "Check suspicious login events",
        picerl_stage: "Identification",
        relative_due_seconds: 3600,
        priority: "HIGH",
        tags: ["identity"],
      },
    ],
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    created_by: "admin",
    updated_by: "admin",
  },
];

vi.mock("@/hooks/useCaseRunbooks", () => ({
  useCaseRunbooks: () => ({
    data: {
      items: runbooks,
      total: runbooks.length,
      page: 1,
      size: 50,
      pages: 1,
    },
    isLoading: false,
    error: null,
  }),
  useCreateCaseRunbook: () => ({
    mutateAsync: mockCreateRunbook,
    isPending: false,
  }),
  useUpdateCaseRunbook: () => ({
    mutateAsync: mockUpdateRunbook,
    isPending: false,
  }),
  usePublishCaseRunbook: () => ({
    mutate: mockPublishRunbook,
    isPending: false,
  }),
  useDisableCaseRunbook: () => ({
    mutate: mockDisableRunbook,
    isPending: false,
  }),
  useDeleteCaseRunbook: () => ({
    mutate: mockDeleteRunbook,
    isPending: false,
  }),
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
  isAnalyst: true,
  isAuditor: false,
};

describe("CaseRunbooksPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCreateRunbook.mockResolvedValue({ ...runbooks[0], id: 99, human_id: "RUN-0000099" });
    mockUpdateRunbook.mockResolvedValue(runbooks[0]);
  });

  it("renders runbook language and read-only task detail", async () => {
    renderWithProviders(<CaseRunbooksPage />, { sessionValue: adminSession });

    expect(await screen.findByText("Case Runbooks")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New Runbook/ })).toBeInTheDocument();
    expect(screen.getAllByText("Credential Theft Response").length).toBeGreaterThan(0);
    expect(screen.getByText("RUN-0000007")).toBeInTheDocument();
    expect(screen.getByText("Review identity provider logs")).toBeInTheDocument();
    expect(screen.getAllByText("identity").length).toBeGreaterThan(0);
    expect(screen.getAllByText("credential-theft").length).toBeGreaterThan(0);
    expect(screen.queryByText("Case Templates")).not.toBeInTheDocument();
  });

  it("creates runbooks with runbook_tasks from the editor rail", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CaseRunbooksPage />, { sessionValue: adminSession });

    await user.click(await screen.findByRole("button", { name: /New Runbook/ }));
    await user.type(screen.getByPlaceholderText("Credential theft response"), "Malware Response");
    await user.type(screen.getByPlaceholderText("When to use this runbook and what it covers"), "Containment workflow");
    await user.type(screen.getByPlaceholderText("Review identity provider logs"), "Isolate host");
    await user.click(screen.getByRole("button", { name: /Create Runbook/ }));

    await waitFor(() => {
      expect(mockCreateRunbook).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Malware Response",
          description: "Containment workflow",
          runbook_tasks: [
            expect.objectContaining({
              title: "Isolate host",
              picerl_stage: "Preparation",
            }),
          ],
        }),
      );
    });
  });
});
