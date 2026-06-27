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

function alertWithContext() {
  return {
    ...baseAlert,
    context: {
      total_count: 5,
      omitted_count: 2,
      items: [
        {
          id: 11,
          body: "Customer DNS tunneling baseline elevated during scheduled backup windows.",
          author: "admin",
          expires_at: "2026-07-01T00:00:00Z",
          criteria: [
            { type: "ALERT_SOURCE", value: "EDR" },
            { type: "TAG", value: "credentials" },
          ],
        },
        {
          id: 12,
          body: "Prod resolver maintenance is active for this customer environment.",
          author: "secops",
          expires_at: "2026-07-02T00:00:00Z",
          criteria: [{ type: "SYSTEM", value: "prod-dns-*" }],
        },
        {
          id: 13,
          body: "Prior credential exfiltration case involved this dataset.",
          author: "admin",
          expires_at: "2026-07-03T00:00:00Z",
          criteria: [{ type: "OBSERVABLE", value: "customer-data" }],
        },
        {
          id: 14,
          body: "Hidden context item should not render in the collapsed card.",
          author: "admin",
          expires_at: "2026-07-04T00:00:00Z",
          criteria: [{ type: "ACTOR", value: "test-actor" }],
        },
      ],
    },
  } as AlertRead & {
    context: {
      total_count: number;
      omitted_count: number;
      items: Array<{
        id: number;
        body: string;
        author: string;
        expires_at: string;
        criteria: Array<{ type: string; value: string }>;
      }>;
    };
  };
}

describe("EntityMetadataCard", () => {
  it("renders prominent analyst context with the first three matched entries", () => {
    renderWithProviders(
      <EntityMetadataCard
        entity={alertWithContext()}
        entityType="alert"
      />,
    );

    expect(screen.getByText("Analyst Context")).toBeInTheDocument();
    expect(screen.getByText("5 active")).toBeInTheDocument();
    expect(screen.getByText("2 omitted")).toBeInTheDocument();
    expect(screen.getByText("Customer DNS tunneling baseline elevated during scheduled backup windows.")).toBeInTheDocument();
    expect(screen.getByText("Prod resolver maintenance is active for this customer environment.")).toBeInTheDocument();
    expect(screen.getByText("Prior credential exfiltration case involved this dataset.")).toBeInTheDocument();
    expect(screen.queryByText("Hidden context item should not render in the collapsed card.")).not.toBeInTheDocument();
    expect(screen.getByText("Alert Source: EDR")).toBeInTheDocument();
    expect(screen.getByText("Tag: credentials")).toBeInTheDocument();
    expect(screen.getByText("System: prod-dns-*")).toBeInTheDocument();
    expect(screen.getAllByText("Author:")).toHaveLength(3);
    expect(screen.getAllByText("Expires:")).toHaveLength(3);
  });

  it("links to the context page with matched ids in a new tab", () => {
    renderWithProviders(
      <EntityMetadataCard
        entity={alertWithContext()}
        entityType="alert"
      />,
    );

    const link = screen.getByRole("link", { name: /view all context/i });

    expect(link).toHaveAttribute("href", "/context-entries?include_expired=true&ids=11%2C12%2C13%2C14");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });

  it("omits the analyst context section when there are no matched context entries", () => {
    renderWithProviders(
      <EntityMetadataCard
        entity={baseAlert}
        entityType="alert"
      />,
    );

    expect(screen.queryByText("Analyst Context")).not.toBeInTheDocument();
  });
});
