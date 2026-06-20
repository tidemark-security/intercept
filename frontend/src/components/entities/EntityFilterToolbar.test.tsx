import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { EntityFilterToolbar } from "@/components/entities/EntityFilterToolbar";
import type { FilterState } from "@/types/filters";
import type { app__api__routes__admin_auth__UserSummary } from "@/types/generated/models/app__api__routes__admin_auth__UserSummary";

const users: app__api__routes__admin_auth__UserSummary[] = [
  {
    userId: "u-1",
    username: "analyst",
    email: "analyst@example.com",
    role: "ANALYST",
    accountType: "HUMAN",
    assignable: true,
  },
];

function renderToolbar(
  filters: FilterState = {
    search: "",
    assignee: null,
    status: ["NEW", "IN_PROGRESS"],
    includeTags: null,
    excludeTags: null,
    dateRange: null,
  },
  onFilterChange = vi.fn(),
) {
  renderWithProviders(
    <EntityFilterToolbar
      filters={filters}
      onFilterChange={onFilterChange}
      assignees={users}
      assigneesLoading={false}
      showTagFilters
      availableTags={[
        { tag: "phishing", count: 3 },
        { tag: "vip", count: 1 },
      ]}
    />,
  );

  return { onFilterChange };
}

function getModifiedIndicator(button: HTMLElement) {
  return button.querySelector("[data-modified-indicator='true']");
}

describe("EntityFilterToolbar", () => {
  it("renders compact two-line toolbar values", () => {
    renderToolbar({
      search: "",
      assignee: ["analyst"],
      status: ["NEW", "IN_PROGRESS"],
      includeTags: ["phishing", "vip"],
      excludeTags: ["noisy"],
      dateRange: {
        start: "2026-05-09T00:00:00Z",
        end: "2026-06-08T00:00:00Z",
        preset: "-30d",
      },
    });

    expect(screen.getByRole("button", { name: /assignee analyst/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /status 2 statuses/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /time last 30 days/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /tags \+2 -1/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reset clear all/i })).toBeInTheDocument();
  });

  it("does not mark the default open statuses as modified", () => {
    renderToolbar();

    const statusButton = screen.getByRole("button", { name: /status 2 statuses/i });

    expect(getModifiedIndicator(statusButton)).not.toBeInTheDocument();
  });

  it("marks status as modified when it differs from the default open statuses", () => {
    renderToolbar({
      search: "",
      assignee: null,
      status: ["NEW"],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
    });

    const statusButton = screen.getByRole("button", { name: /status new/i });

    expect(getModifiedIndicator(statusButton)).toBeInTheDocument();
  });

  it("selects every open status and clears closed statuses from the status parent option", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderToolbar(
      {
        search: "",
        assignee: null,
        status: ["CLOSED_TP", "CLOSED_FP"],
        includeTags: null,
        excludeTags: null,
        dateRange: null,
      },
      onFilterChange,
    );

    await user.click(screen.getByRole("button", { name: /status 2 statuses/i }));
    await user.click(screen.getByRole("menuitem", { name: /all open/i }));

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "",
      assignee: null,
      status: ["NEW", "IN_PROGRESS"],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
    });
  });

  it("selects every closed status and clears open statuses from the status parent option", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderToolbar(undefined, onFilterChange);

    await user.click(screen.getByRole("button", { name: /status 2 statuses/i }));
    await user.click(screen.getByRole("menuitem", { name: /all closed/i }));

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "",
      assignee: null,
      status: [
        "CLOSED_TP",
        "CLOSED_BP",
        "CLOSED_FP",
        "CLOSED_UNRESOLVED",
        "CLOSED_DUPLICATE",
      ],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
    });
  });

  it("uses task status options for open and closed parent selections", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();

    renderWithProviders(
      <EntityFilterToolbar
        filters={{
          search: "",
          assignee: null,
          status: ["TODO", "IN_PROGRESS"],
          includeTags: null,
          excludeTags: null,
          dateRange: null,
        }}
        onFilterChange={onFilterChange}
        assignees={users}
        assigneesLoading={false}
        statusOptions={[
          { value: "TODO", label: "To Do" },
          { value: "IN_PROGRESS", label: "In Progress" },
          { value: "DONE", label: "Done" },
        ]}
      />,
    );

    await user.click(screen.getByRole("button", { name: /status 2 statuses/i }));
    await user.click(screen.getByRole("menuitem", { name: /all closed/i }));

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "",
      assignee: null,
      status: ["DONE"],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
    });
  });

  it("does not show the status clear selection control", async () => {
    const user = userEvent.setup();
    renderToolbar();

    await user.click(screen.getByRole("button", { name: /status 2 statuses/i }));

    expect(screen.queryByRole("menuitem", { name: /clear selection/i })).not.toBeInTheDocument();
  });

  it("clears every filter when reset is selected", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderToolbar(
      {
        search: "suspicious",
        assignee: ["analyst"],
        status: ["NEW"],
        includeTags: ["phishing"],
        excludeTags: ["noisy"],
        dateRange: {
          start: "2026-05-09T00:00:00Z",
          end: "2026-06-08T00:00:00Z",
          preset: "-30d",
        },
      },
      onFilterChange,
    );

    await user.click(screen.getByRole("button", { name: /reset clear all/i }));

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "",
      assignee: null,
      status: null,
      includeTags: null,
      excludeTags: null,
      dateRange: null,
    });
  });

  it("shows only visible-result tag suggestions with counts", async () => {
    const user = userEvent.setup();
    renderToolbar();

    await user.click(screen.getByRole("button", { name: /tags no tags/i }));

    const dropdown = screen.getByText("Tags in current results").closest("[data-radix-popper-content-wrapper]") ?? document.body;
    expect(screen.getByRole("button", { name: /phishing 3/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /vip 1/i })).toBeInTheDocument();
    expect(within(dropdown as HTMLElement).queryByText("credential-theft")).not.toBeInTheDocument();
  });
});
