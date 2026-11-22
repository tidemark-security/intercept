import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { UnifiedTimeline } from "@/components/timeline/UnifiedTimeline";
import type { AlertRead } from "@/types/generated/models/AlertRead";
import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { CaseReadWithAlerts } from "@/types/generated/models/CaseReadWithAlerts";

const resolveLinkTemplatesMock = vi.hoisted(() => vi.fn());
const usePresenceMock = vi.hoisted(() => vi.fn<() => string[]>());

vi.mock("@/contexts/WebSocketContext", () => ({
  usePresence: usePresenceMock,
}));

vi.mock("@/types/generated/services/LinkTemplatesService", () => ({
  LinkTemplatesService: {
    resolveLinkTemplatesApiV1LinkTemplatesResolvePost: resolveLinkTemplatesMock,
  },
}));

beforeEach(() => {
  resolveLinkTemplatesMock.mockResolvedValue([]);
  usePresenceMock.mockReturnValue([]);
});

afterEach(() => {
  resolveLinkTemplatesMock.mockReset();
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

const baseAlert: AlertRead = {
  title: "Malware Signature Match",
  description: "Privileged user account exhibiting unusual behavior patterns.",
  priority: "EXTREME",
  source: "Threat Intelligence",
  id: 41,
  status: "IN_PROGRESS",
  assignee: null,
  triaged_at: null,
  triage_notes: null,
  case_id: null,
  linked_at: null,
  created_at: "2026-06-08T13:47:10+10:00",
  updated_at: "2026-06-08T22:10:10+10:00",
  timeline_items: null,
  tags: ["tmi_dummy_data", "apt"],
  triage_recommendation: null,
  human_id: "ALT-0000041",
};

const caseWithStagedTasks: CaseReadWithAlerts = {
  title: "Cryptocurrency Mining Malware Detection",
  description: "Case with staged response tasks.",
  priority: "HIGH",
  tags: [],
  id: 9,
  status: "IN_PROGRESS",
  assignee: "tidemark_ai",
  created_by: "admin",
  created_at: "2026-06-08T13:47:10+10:00",
  updated_at: "2026-06-08T22:10:10+10:00",
  closed_at: null,
  alerts: [],
  human_id: "CAS-0000009",
  timeline_items: {
    task_1: {
      id: "task_1",
      type: "task",
      task_id: 1,
      task_human_id: "TSK-0000001",
      title: "Collect endpoint evidence",
      description: "Collect endpoint evidence",
      status: "TODO",
      priority: "HIGH",
      assignee: "tidemark_ai",
      created_at: "2026-06-08T13:47:10+10:00",
      timestamp: "2026-06-08T13:47:10+10:00",
      created_by: "admin",
      picerl_stage: "Preparation",
      due_date: null,
      tags: [],
    },
  },
};

function persistSwimlaneViewForStagedCase() {
  window.localStorage.setItem(
    `intercept.timeline-view.case.${caseWithStagedTasks.id}`,
    "swimlane",
  );
}

function renderAlertTimeline(status: AlertStatus) {
  return renderWithProviders(
    <UnifiedTimeline
      entityDetail={{ ...baseAlert, status }}
      entityType="alert"
      selectedEntityId={baseAlert.id}
      currentUser="admin"
      isLoading={false}
      error={null}
      users={[]}
      usersLoading={false}
      mode="editable"
      onRequestTriage={vi.fn()}
      isTriageEnabled
    />,
  );
}

describe("UnifiedTimeline", () => {
  it("shows other viewers as named initials before the assignment button", () => {
    usePresenceMock.mockReturnValue([
      "observer", "Admin", "Analyst", "Analyst", "glenn.bolton@tidemarksecurity.com",
    ]);
    renderWithProviders(
      <UnifiedTimeline
        entityDetail={baseAlert}
        entityType="alert"
        selectedEntityId={baseAlert.id}
        currentUser="Observer"
        isLoading={false}
        error={null}
        users={[]}
        usersLoading={false}
        onAssignToMe={vi.fn()}
      />,
    );

    const viewers = screen.getByRole("group", { name: "Other viewers" });
    const avatars = within(viewers).getAllByRole("img");
    expect(avatars.map((avatar) => avatar.textContent)).toEqual(["A", "A", "GB"]);
    expect(avatars.map((avatar) => avatar.getAttribute("aria-label"))).toEqual([
      "Admin", "Analyst", "glenn.bolton@tidemarksecurity.com",
    ]);
    const assignment = within(screen.getByTitle("Assignee: Unassigned")).getByRole("button");
    expect(viewers.compareDocumentPosition(assignment) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText(/viewing this alert/)).not.toBeInTheDocument();
  });

  it("shows a truncatable title beneath the header ID and the full title in the metadata card", () => {
    renderWithProviders(
      <UnifiedTimeline
        entityDetail={baseAlert}
        entityType="alert"
        selectedEntityId={baseAlert.id}
        currentUser="admin"
        isLoading={false}
        error={null}
        users={[]}
        usersLoading={false}
        onAssignToMe={vi.fn()}
      />,
    );

    const content = screen.getByLabelText("alert timeline content");
    const headerId = screen.getByRole("heading", { level: 1, name: baseAlert.human_id });
    expect(headerId).toBeVisible();
    expect(headerId.nextElementSibling).toHaveTextContent(baseAlert.title);
    expect(headerId.nextElementSibling).toHaveClass("truncate");
    expect(within(content).queryByText(baseAlert.human_id)).not.toBeInTheDocument();
    expect(within(content).getByRole("heading", { name: baseAlert.title })).toBeVisible();
    expect(within(content).getByText("Unassigned")).toBeVisible();
    expect(within(content).queryByRole("button", { name: /assign/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /\bUnassigned$/ })).toBeVisible();
  });

  it("resolves parent entity header links with the entity surface and core case context", async () => {
    resolveLinkTemplatesMock.mockResolvedValue([
      {
        id: 99,
        visibility: "PUBLIC",
        template_id: "case-console",
        name: "Case Console",
        icon_name: "Link2",
        tooltip: "Open CAS-0000009",
        url: "https://console.example/cases/CAS-0000009",
        display_order: 1,
      },
    ]);

    renderWithProviders(
      <UnifiedTimeline
        entityDetail={caseWithStagedTasks}
        entityType="case"
        selectedEntityId={caseWithStagedTasks.id}
        currentUser="admin"
        isLoading={false}
        error={null}
        users={[]}
        usersLoading={false}
        mode="editable"
      />,
    );

    await waitFor(() =>
      expect(resolveLinkTemplatesMock).toHaveBeenCalledWith({
        requestBody: {
          surface: "entity",
          entity_type: "case",
          item: expect.objectContaining({
            surface: "entity",
            entity_type: "case",
            id: caseWithStagedTasks.id,
            entity_id: caseWithStagedTasks.id,
            human_id: caseWithStagedTasks.human_id,
            title: caseWithStagedTasks.title,
            status: caseWithStagedTasks.status,
            priority: caseWithStagedTasks.priority,
            assignee: caseWithStagedTasks.assignee,
            tags: caseWithStagedTasks.tags,
            created_at: caseWithStagedTasks.created_at,
            updated_at: caseWithStagedTasks.updated_at,
          }),
        },
      }),
    );
    expect(await screen.findByRole("button", { name: "Open CAS-0000009" })).toBeInTheDocument();
  });

  it("shows the AI triage request card for open alerts without a recommendation", () => {
    renderAlertTimeline("IN_PROGRESS");

    const triage = screen.getByRole("region", { name: "AI Triage Available" });
    expect(within(triage).getByRole("button", { name: "Start" })).toBeInTheDocument();
  });

  it("embeds triage, analyst context, and the full description after the alert tags", () => {
    const description = [
      "## Evidence",
      "",
      "```text",
      ...Array.from({ length: 20 }, (_, index) => `event-${index + 1}`),
      "```",
    ].join("\n");
    renderWithProviders(
      <UnifiedTimeline
        entityDetail={{
          ...baseAlert,
          description,
          context: {
            total_count: 1,
            omitted_count: 0,
            items: [
              {
                id: 101,
                criteria: [],
                body: "Global alert context.",
                author: "admin",
                expires_at: "2026-07-01T00:00:00Z",
              },
            ],
          },
        }}
        entityType="alert"
        selectedEntityId={baseAlert.id}
        currentUser="admin"
        isLoading={false}
        error={null}
        users={[]}
        usersLoading={false}
        mode="editable"
        onRequestTriage={vi.fn()}
        isTriageEnabled
      />,
    );

    const metadataCard = screen.getByRole("heading", { name: baseAlert.title, level: 2 }).parentElement!;
    const tags = within(metadataCard).getByLabelText("Tags");
    const triageCard = within(metadataCard).getByRole("region", { name: "AI Triage Available" });
    const contextCard = within(metadataCard).getByRole("region", { name: "Analyst Context" });
    const descriptionSection = within(metadataCard).getByRole("region", { name: "Description" });

    expect(tags.compareDocumentPosition(triageCard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(triageCard.compareDocumentPosition(contextCard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(contextCard.compareDocumentPosition(descriptionSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(descriptionSection).getByText("event-20")).toBeVisible();
    expect(screen.getAllByRole("heading", { name: "Evidence" })).toHaveLength(1);
  });

  it("does not show the AI triage request card for closed alerts without a recommendation", () => {
    renderAlertTimeline("CLOSED_TP");

    expect(screen.queryByRole("region", { name: "AI Triage Available" })).not.toBeInTheDocument();
  });

  it("keeps normal center scrolling while bounding the swimlane section height", async () => {
    persistSwimlaneViewForStagedCase();

    renderWithProviders(
      <UnifiedTimeline
        entityDetail={caseWithStagedTasks}
        entityType="case"
        selectedEntityId={caseWithStagedTasks.id}
        currentUser="admin"
        isLoading={false}
        error={null}
        users={[]}
        usersLoading={false}
        mode="editable"
      />,
    );

    const scrollContainer = screen.getByLabelText("case timeline content");
    const swimlaneContainer = await screen.findByLabelText("PICERL swimlane");

    expect(scrollContainer).toHaveClass("overflow-auto");
    expect(scrollContainer).not.toHaveClass("overflow-hidden");
    expect(swimlaneContainer).toHaveClass("h-full");
    expect(swimlaneContainer).toHaveClass("overflow-hidden");
  });

  it("uses the PICERL carousel when swimlane space is constrained", async () => {
    persistSwimlaneViewForStagedCase();
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      width: 720,
      height: 600,
      top: 0,
      right: 720,
      bottom: 600,
      left: 0,
      toJSON: () => ({}),
    });

    renderWithProviders(
      <UnifiedTimeline
        entityDetail={caseWithStagedTasks}
        entityType="case"
        selectedEntityId={caseWithStagedTasks.id}
        currentUser="admin"
        isLoading={false}
        error={null}
        users={[]}
        usersLoading={false}
        mode="editable"
      />,
    );

    expect(await screen.findByRole("button", { name: /previous PICERL lane/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /next PICERL lane/i })).toBeInTheDocument();
    expect(screen.getByLabelText("PICERL swimlane")).toHaveClass("h-full");
    expect(screen.getByLabelText("PICERL swimlane")).toHaveClass("overflow-hidden");
  });

  it("shows zero counts for empty PICERL swimlane lanes", async () => {
    persistSwimlaneViewForStagedCase();
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      width: 1400,
      height: 600,
      top: 0,
      right: 1400,
      bottom: 600,
      left: 0,
      toJSON: () => ({}),
    });

    renderWithProviders(
      <UnifiedTimeline
        entityDetail={caseWithStagedTasks}
        entityType="case"
        selectedEntityId={caseWithStagedTasks.id}
        currentUser="admin"
        isLoading={false}
        error={null}
        users={[]}
        usersLoading={false}
        mode="editable"
      />,
    );

    expect(await screen.findByRole("button", { name: /0\. preparation\s+1/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1\. identification\s+0/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /2\. containment\s+0/i })).toBeInTheDocument();
  });

  it("keeps the swimlane task shell neutral when the task item is highlighted", async () => {
    persistSwimlaneViewForStagedCase();
    const highlightedCase = {
      ...caseWithStagedTasks,
      timeline_items: {
        task_1: {
          ...caseWithStagedTasks.timeline_items!.task_1,
          highlighted: true,
        },
      },
    };

    renderWithProviders(
      <UnifiedTimeline
        entityDetail={highlightedCase}
        entityType="case"
        selectedEntityId={highlightedCase.id}
        currentUser="admin"
        isLoading={false}
        error={null}
        users={[]}
        usersLoading={false}
        mode="editable"
      />,
    );

    const taskShell = (await screen.findByText("Collect endpoint evidence")).closest("button");

    expect(taskShell).toHaveClass("bg-neutral-0");
    expect(taskShell).not.toHaveClass("bg-warning-1100");
    expect(taskShell).not.toHaveClass("bg-warning-50/40");
    expect(taskShell).not.toHaveClass("border-warning-600");
    expect(taskShell).not.toHaveClass("border-warning-700");
  });
});
