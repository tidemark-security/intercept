import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { EntityMetadataCard } from "@/components/cards/EntityMetadataCard";
import type { AlertRead } from "@/types/generated/models/AlertRead";

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
    expect(screen.queryByText("Analyst Context")).not.toBeInTheDocument();
    expect(screen.queryByText("Context belongs in ContextCard.")).not.toBeInTheDocument();
    const description = screen.getByText(baseAlert.description as string);
    expect(description.closest(".border-t")).toBeInTheDocument();
  });
});
