import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { EntityFilterToolbar } from "@/components/entities/EntityFilterToolbar";
import type { FilterState, TaskFilterState } from "@/types/filters";
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
  const renderResult = renderWithProviders(
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
    {
      sessionValue: {
        status: "authenticated",
        session: null,
        user: { username: "analyst" },
      } as any,
    },
  );

  return { onFilterChange, ...renderResult };
}

function getModifiedIndicator(button: HTMLElement) {
  return button.matches("[data-modified-indicator='true']");
}

describe("EntityFilterToolbar", () => {
  it("summarizes only active filters and opens the editor on demand", async () => {
    const user = userEvent.setup();
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

    const trigger = screen.getByRole("button", { name: "Filters, 5 active" });
    expect(screen.queryByRole("dialog", { name: "Queue filters" })).not.toBeInTheDocument();
    const chips = within(screen.getByRole("group", { name: "Active filters" }));
    expect(chips.getByRole("button", { name: "Remove assignee analyst" })).toHaveTextContent("analyst");
    expect(chips.getByRole("button", { name: "Remove time filter: Last 30 days" })).toHaveTextContent("Last 30 days");
    expect(chips.getByRole("button", { name: "Remove include tag phishing" })).toHaveTextContent("+ phishing");
    expect(chips.getByRole("button", { name: "Remove exclude tag noisy" })).toHaveTextContent("− noisy");
    expect(chips.queryByRole("button", { name: /^Restore default statuses/ })).not.toBeInTheDocument();

    await user.click(trigger);
    expect(screen.getByRole("button", { name: /^assignee analyst$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /status 2 statuses/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /time last 30 days/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /tags \+2 -1/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("dialog", { name: "Queue filters" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("renders generic actions below the filter controls", () => {
    renderWithProviders(
      <EntityFilterToolbar
        filters={{
          search: "",
          assignee: null,
          status: ["NEW", "IN_PROGRESS"],
          includeTags: null,
          excludeTags: null,
          dateRange: null,
        }}
        onFilterChange={vi.fn()}
        assignees={users}
        assigneesLoading={false}
        actions={<button type="button">Bulk status</button>}
      />,
    );

    expect(screen.getByRole("button", { name: /bulk status/i })).toBeInTheDocument();
  });

  it("does not mark the default open statuses as modified", () => {
    renderToolbar();

    expect(screen.getByRole("button", { name: "Filters" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Active filters" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^clear/i })).not.toBeInTheDocument();
  });

  it("lets the status chip restore default open statuses without changing other filters", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderToolbar({
      search: "",
      assignee: ["__unassigned__", "analyst"],
      status: ["NEW"],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
    }, onFilterChange);

    expect(screen.getByRole("button", { name: "Filters, 3 active" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Restore default statuses/ }));
    expect(onFilterChange).toHaveBeenLastCalledWith(expect.objectContaining({
      assignee: ["__unassigned__", "analyst"], status: ["NEW", "IN_PROGRESS"],
    }));
    await user.click(screen.getByRole("button", { name: "Remove assignee Unassigned" }));
    expect(onFilterChange).toHaveBeenLastCalledWith(expect.objectContaining({ assignee: ["analyst"], status: ["NEW"] }));
  });

  it("selects every status from the all status parent option", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderToolbar(undefined, onFilterChange);

    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    await user.click(screen.getByRole("button", { name: /status 2 statuses/i }));
    await user.click(screen.getByRole("menuitem", { name: /^all$/i }));

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "",
      assignee: null,
      status: [
        "NEW",
        "IN_PROGRESS",
        "ESCALATED",
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

    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    await user.click(screen.getByRole("button", { name: /status 2 statuses/i }));
    await user.click(screen.getByRole("menuitem", { name: /all open/i }));

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "",
      assignee: null,
      status: ["NEW", "IN_PROGRESS", "ESCALATED"],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
    });
  });

  it("selects every closed status and clears open statuses from the status parent option", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderToolbar(undefined, onFilterChange);

    await user.click(screen.getByRole("button", { name: /^Filters/ }));
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

  it("keeps status grouping options mutually exclusive", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderToolbar(
      {
        search: "",
        assignee: null,
        status: [
          "NEW",
          "IN_PROGRESS",
          "CLOSED_TP",
          "CLOSED_BP",
          "CLOSED_FP",
          "CLOSED_UNRESOLVED",
          "CLOSED_DUPLICATE",
        ],
        includeTags: null,
        excludeTags: null,
        dateRange: null,
      },
      onFilterChange,
    );

    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    await user.click(screen.getByRole("button", { name: /status 7 statuses/i }));
    await user.click(screen.getByRole("menuitem", { name: /all open/i }));

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "",
      assignee: null,
      status: ["NEW", "IN_PROGRESS", "ESCALATED"],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
    });
  });

  it("uses task status options for open and closed parent selections", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    const taskFilters: TaskFilterState = {
      search: "",
      assignee: null,
      status: ["TODO", "IN_PROGRESS"],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
    };

    renderWithProviders(
      <EntityFilterToolbar
        filters={taskFilters as unknown as FilterState}
        onFilterChange={onFilterChange as unknown as (filters: FilterState) => void}
        assignees={users}
        assigneesLoading={false}
        statusOptions={[
          { value: "TODO", label: "To Do" },
          { value: "IN_PROGRESS", label: "In Progress" },
          { value: "DONE", label: "Done" },
        ]}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^Filters/ }));
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

    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    await user.click(screen.getByRole("button", { name: /status 2 statuses/i }));

    expect(screen.queryByRole("menuitem", { name: /clear selection/i })).not.toBeInTheDocument();
  });

  it("changes sort order from the reusable sort menu", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderWithProviders(
      <EntityFilterToolbar
        filters={{
          search: "",
          assignee: null,
          status: ["NEW", "IN_PROGRESS"],
          includeTags: null,
          excludeTags: null,
          dateRange: null,
          sortBy: "created_at",
          sortOrder: "desc",
        }}
        onFilterChange={onFilterChange}
        assignees={users}
        assigneesLoading={false}
        sortOptions={[
          {
            value: "created_at",
            label: "Created",
            directionLabel: { desc: "Newest first", asc: "Oldest first" },
          },
          {
            value: "priority",
            label: "Priority",
            directionLabel: { desc: "Highest priority", asc: "Lowest priority" },
          },
        ]}
      />,
    );

    await user.click(screen.getByRole("button", { name: /sort newest first/i }));
    await user.click(screen.getByRole("menuitem", { name: /oldest first/i }));

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "",
      assignee: null,
      status: ["NEW", "IN_PROGRESS"],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
      sortBy: "created_at",
      sortOrder: "asc",
    });
  });

  it("does not mark the default newest-first sort as modified", () => {
    renderWithProviders(
      <EntityFilterToolbar
        filters={{
          search: "",
          assignee: null,
          status: ["NEW", "IN_PROGRESS"],
          includeTags: null,
          excludeTags: null,
          dateRange: null,
          sortBy: "created_at",
          sortOrder: "desc",
        }}
        onFilterChange={vi.fn()}
        assignees={users}
        assigneesLoading={false}
        sortOptions={[
          {
            value: "created_at",
            label: "Created",
            directionLabel: { desc: "Newest first", asc: "Oldest first" },
          },
          {
            value: "priority",
            label: "Priority",
            directionLabel: { desc: "Highest priority", asc: "Lowest priority" },
          },
        ]}
      />,
    );

    const sortButton = screen.getByRole("button", { name: /sort newest first/i });

    expect(getModifiedIndicator(sortButton)).toBe(false);
  });

  it("marks sort as modified when it differs from newest first", () => {
    renderWithProviders(
      <EntityFilterToolbar
        filters={{
          search: "",
          assignee: null,
          status: ["NEW", "IN_PROGRESS"],
          includeTags: null,
          excludeTags: null,
          dateRange: null,
          sortBy: "created_at",
          sortOrder: "asc",
        }}
        onFilterChange={vi.fn()}
        assignees={users}
        assigneesLoading={false}
        sortOptions={[
          {
            value: "created_at",
            label: "Created",
            directionLabel: { desc: "Newest first", asc: "Oldest first" },
          },
          {
            value: "priority",
            label: "Priority",
            directionLabel: { desc: "Highest priority", asc: "Lowest priority" },
          },
        ]}
      />,
    );

    const sortButton = screen.getByRole("button", { name: /sort oldest first/i });

    expect(getModifiedIndicator(sortButton)).toBe(true);
    expect(screen.getByRole("button", { name: "Filters" })).toBeInTheDocument();
  });

  it("clears structured filters without resetting search or sort", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderToolbar(
      {
        search: "suspicious",
        assignee: ["analyst"],
        status: ["NEW"],
        sortBy: "created_at",
        sortOrder: "asc",
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

    await user.click(screen.getByRole("button", { name: "Clear" }));

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "suspicious",
      assignee: null,
      status: null,
      sortBy: "created_at",
      sortOrder: "asc",
      includeTags: null,
      excludeTags: null,
      dateRange: null,
    });
  });

  it("shows only visible-result tag suggestions with counts", async () => {
    const user = userEvent.setup();
    renderToolbar();

    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    await user.click(screen.getByRole("button", { name: /tags no tags/i }));

    const dropdown = screen.getByText("Tags in current results").closest("[data-radix-popper-content-wrapper]") ?? document.body;
    expect(screen.getByRole("button", { name: /phishing 3/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /vip 1/i })).toBeInTheDocument();
    expect(within(dropdown as HTMLElement).queryByText("credential-theft")).not.toBeInTheDocument();
  });
});
