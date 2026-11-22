import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { EntityMetadataCard } from "@/components/cards/EntityMetadataCard";
import type { AlertRead } from "@/types/generated/models/AlertRead";
import type { CaseRead } from "@/types/generated/models/CaseRead";
import type { TaskRead } from "@/types/generated/models/TaskRead";

const baseAlert: AlertRead = {
  title: "Suspicious DNS queries",
  description: "Suspicious DNS queries indicating potential data exfiltration through DNS tunneling",
  priority: "CRITICAL",
  source: "EDR",
  id: 42,
  status: "IN_PROGRESS",
  assignee: "admin",
  triaged_at: null,
  triage_notes: null,
  case_id: null,
  linked_at: null,
  created_at: "2026-06-08T22:04:19+10:00",
  updated_at: "2026-06-27T13:01:29+10:00",
  timeline_items: null,
  tags: ["tmi_dummy_data", "customer-data", "credentials"],
  triage_recommendation: null,
  human_id: "AL-0000042",
};

describe("EntityMetadataCard", () => {
  it("renders alert metadata without embedding analyst context", () => {
    renderWithProviders(
      <EntityMetadataCard
        entity={{
          ...baseAlert,
          context: {
            total_count: 1,
            omitted_count: 0,
            items: [
              {
                id: 11,
                body: "Context belongs in ContextCard.",
                author: "admin",
                expires_at: "2026-07-01T00:00:00Z",
                criteria: [],
              },
            ],
          },
        }}
        entityType="alert"
      />,
    );

    expect(screen.getAllByText("In Progress").length).toBeGreaterThan(0);
    expect(screen.getByText("EDR")).toBeInTheDocument();
    expect(screen.queryByText("Created By")).not.toBeInTheDocument();
    expect(screen.queryByText("Analyst Context")).not.toBeInTheDocument();
    expect(screen.queryByText("Context belongs in ContextCard.")).not.toBeInTheDocument();
    const description = screen.getByText(baseAlert.description as string);
    expect(description.closest(".border-t")).toBeInTheDocument();
  });

  it("renders Markdown tables and the final line of a long code block in the description", () => {
    const description = [
      "## Evidence",
      "",
      "| Host | Result |",
      "| --- | --- |",
      "| DC-07 | Denied |",
      "",
      "```text",
      ...Array.from({ length: 20 }, (_, index) => `event-${index + 1}`),
      "```",
      "",
      "## Review notes",
      "Confirm the account owner.",
    ].join("\n");

    renderWithProviders(<EntityMetadataCard entity={{ ...baseAlert, description }} entityType="alert" />);

    expect(screen.getByRole("cell", { name: "DC-07" })).toBeVisible();
    expect(screen.getByText("event-20")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Review notes" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /expand|show full description/i })).not.toBeInTheDocument();
  });

  it.each(["case", "task"] as const)("shows the creator and description icon for a %s", (entityType) => {
    const shared = {
      id: 42,
      title: "Review DNS activity",
      description: "Confirm the DNS activity.",
      assignee: "analyst",
      created_by: "creator",
      created_at: baseAlert.created_at,
      updated_at: baseAlert.updated_at,
    };
    const entity: CaseRead | TaskRead = entityType === "case"
      ? { ...shared, status: "IN_PROGRESS", human_id: "CAS-0000042" }
      : { ...shared, status: "TODO", human_id: "TSK-0000042" };

    renderWithProviders(<EntityMetadataCard entity={entity} entityType={entityType} />);

    expect(screen.getByText("Created By")).toBeVisible();
    expect(screen.getByText("creator")).toBeVisible();
    const heading = screen.getByRole("heading", { name: "Description" });
    expect(heading.querySelector(".lucide-file-text")).toHaveAttribute("aria-hidden", "true");
  });
});
