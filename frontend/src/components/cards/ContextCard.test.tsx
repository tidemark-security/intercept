import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { ContextCard } from "@/components/cards/ContextCard";
import type { MatchedContextSection } from "@/types/generated/models/MatchedContextSection";

function contextFixture(): MatchedContextSection {
  return {
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
  };
}

describe("ContextCard", () => {
  it("renders prominent analyst context with the first three matched entries", () => {
    renderWithProviders(<ContextCard context={contextFixture()} />);

    expect(screen.getByText("Analyst Context")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /view all context/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Matched Context", { exact: true })).not.toBeInTheDocument();
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
    expect(screen.getAllByRole("button", { name: /^(Expires|Expired) / })).toHaveLength(3);
  });

  it("keeps the full Markdown note visible with a compact, copyable expiry", async () => {
    const user = userEvent.setup();
    const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
    renderWithProviders(<ContextCard context={{ items: [{
      id: 11,
      body: "# Test context\n\nThis applies to **all alerts**.",
      author: "analyst",
      expires_at: expiresAt,
      criteria: [],
    }] }} />);

    expect(screen.getByRole("heading", { name: "Test context" })).toBeVisible();
    expect(screen.getByText("all alerts", { selector: "strong" })).toBeVisible();
    expect(screen.getByText("Global")).toBeVisible();

    const expiry = screen.getByRole("button", { name: "Expires in 7 days" });
    const exactTimestamp = expiry.title.replace("Click to copy: ", "");
    expect(exactTimestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expiry.focus();
    await user.keyboard("{Enter}");
    await expect(navigator.clipboard.readText()).resolves.toBe(exactTimestamp);
  });

  it("collapses and expands analyst context", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ContextCard context={contextFixture()} />);

    await user.click(screen.getByRole("button", { name: /collapse analyst context/i }));

    expect(screen.getByText("Analyst Context")).toBeInTheDocument();
    expect(screen.getByText("5 active")).toBeInTheDocument();
    expect(screen.queryByText("Prod resolver maintenance is active for this customer environment.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /expand analyst context/i })).toHaveAttribute("aria-expanded", "false");

    await user.click(screen.getByRole("button", { name: /expand analyst context/i }));

    expect(screen.getByRole("button", { name: /collapse analyst context/i })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Prod resolver maintenance is active for this customer environment.")).toBeInTheDocument();
  });

  it("omits the card when there are no matched context entries", () => {
    const { container } = renderWithProviders(
      <ContextCard context={{ items: [], total_count: 0, omitted_count: 0 }} />,
    );

    expect(screen.queryByText("Analyst Context")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });
});
