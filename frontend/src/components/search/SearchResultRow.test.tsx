import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { SearchResultRow } from "@/components/search/SearchResultRow";
import type { ExtendedSearchResultItem } from "@/components/search/searchUtils";

function makeResult(overrides: Partial<ExtendedSearchResultItem> = {}): ExtendedSearchResultItem {
  return {
    entity_type: "case",
    entity_id: 6,
    human_id: "CAS-0000006",
    title: "Cloud Infrastructure Breach",
    snippet: "Cloud Infrastructure Breach analysis",
    score: 0,
    created_at: "2026-06-08T15:34:19+10:00",
    updated_at: "2026-06-08T15:34:19+10:00",
    assignee: "tidemark_ai",
    status: "in_progress",
    priority: "low",
    tags: ["tmi_dummy_data", "authentication", "malware"],
    tag_matches: [],
    ...overrides,
  };
}

function expectTagP4(name: string) {
  const tag = screen.getByText(name);
  expect(tag.closest(".bg-p4")).toBeInTheDocument();
}

function expectAnyTagP4(name: string) {
  const tags = screen.getAllByText(name);
  expect(tags.some((tag) => tag.closest(".bg-p4"))).toBe(true);
}

describe("SearchResultRow", () => {
  it("highlights entity tags that match active tag filters", () => {
    renderWithProviders(
      <SearchResultRow
        item={makeResult({ tags: ["credentials"] })}
        onClick={vi.fn()}
        selectedTags={["cred"]}
      />,
    );

    expectTagP4("credentials");
  });

  it("appends timeline tag matches to the main tag strip with a child indicator", () => {
    const { container } = renderWithProviders(
      <SearchResultRow
        item={makeResult({
          tag_matches: [
            {
              source: "timeline",
              tag: "credentials",
              filter: "credentials",
              timeline_item_id: "note-1",
              timeline_item_type: "note",
              timeline_item_label: "Credential harvesting observed",
            },
          ],
        })}
        onClick={vi.fn()}
        selectedTags={["credentials"]}
      />,
    );

    expect(screen.queryByText(/Timeline .* tag/)).not.toBeInTheDocument();
    expect(screen.queryByText("Credential harvesting observed")).not.toBeInTheDocument();
    expect(container.querySelector(".lucide-list-tree")).toBeInTheDocument();
    expectTagP4("credentials");
  });

  it("appends tags from embedded timeline item snippets for free text matches", () => {
    const { container } = renderWithProviders(
      <SearchResultRow
        item={makeResult({
          tags: ["tmi_dummy_data", "authentication"],
          snippet: JSON.stringify({
            id: "registry-1",
            type: "registry_change",
            registry_key: "HKLM\\System\\CurrentControlSet\\Services",
            registry_value: "MaliciousEntry51",
            tags: ["credentials", "malware"],
          }),
        })}
        onClick={vi.fn()}
        searchQuery="malware"
      />,
    );

    expect(container.querySelectorAll(".lucide-list-tree")).toHaveLength(2);
    expect(screen.getByText("credentials")).toBeInTheDocument();
    expectAnyTagP4("malware");
  });

  it("appends tags from truncated embedded timeline item snippets", () => {
    const { container } = renderWithProviders(
      <SearchResultRow
        item={makeResult({
          tags: ["tmi_dummy_data", "authentication"],
          snippet: '{"id":"registry-1","type":"registry_change","description":"Registry hit","tags":["credentials","critical"],',
        })}
        onClick={vi.fn()}
        searchQuery="critical"
      />,
    );

    expect(container.querySelectorAll(".lucide-list-tree")).toHaveLength(2);
    expect(screen.getByText("credentials")).toBeInTheDocument();
    expectTagP4("critical");
  });

  it("highlights entity tags that match free text search terms", () => {
    renderWithProviders(
      <SearchResultRow
        item={makeResult({ tags: ["malware"] })}
        onClick={vi.fn()}
        searchQuery="malware"
      />,
    );

    expectTagP4("malware");
  });

  it("does not append child tag indicators for entity-only tag matches", () => {
    const { container } = renderWithProviders(
      <SearchResultRow
        item={makeResult({
          tags: ["credentials"],
          tag_matches: [{ source: "entity", tag: "credentials", filter: "credentials" }],
        })}
        onClick={vi.fn()}
        selectedTags={["credentials"]}
      />,
    );

    expect(screen.queryByText(/Timeline .* tag/)).not.toBeInTheDocument();
    expect(container.querySelector(".lucide-list-tree")).not.toBeInTheDocument();
    expectTagP4("credentials");
  });

  it("highlights multiple entity tags that match multiple active filters", () => {
    renderWithProviders(
      <SearchResultRow
        item={makeResult({ tags: ["customer-data", "credentials"] })}
        onClick={vi.fn()}
        selectedTags={["customer", "cred"]}
      />,
    );

    expectTagP4("customer-data");
    expectTagP4("credentials");
  });
});
