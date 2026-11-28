import { useState } from "react";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../../tests/test-utils";
import { EntityFilterToolbar } from "./EntityFilterToolbar";
import type { SessionContextValue } from "@/contexts/sessionContext";
import type { FilterState } from "@/types/filters";
import type { SavedFilterRead } from "@/types/generated/models/SavedFilterRead";
import { SavedFiltersService } from "@/types/generated/services/SavedFiltersService";

vi.mock("@/types/generated/services/SavedFiltersService", () => ({
  SavedFiltersService: {
    listSavedFilters: vi.fn(),
    createSavedFilter: vi.fn(),
    renameSavedFilter: vi.fn(),
    deleteSavedFilter: vi.fn(),
  },
}));

const personal: SavedFilterRead = {
  id: "personal-filter",
  name: "My open alerts",
  scope: "personal",
  queue: "alerts",
  filters: { search: "", status: ["NEW", "IN_PROGRESS"], sort_by: "created_at", sort_order: "desc" },
};

const organization: SavedFilterRead = {
  id: "org-filter",
  name: "Org triage",
  scope: "organization",
  queue: "alerts",
  filters: {
    search: "dns failure",
    status: ["NEW"],
    assignee: ["analyst"],
    include_tags: ["dns"],
    exclude_tags: ["training"],
    date_range: { start: "2026-05-09T00:00:00Z", end: "2026-06-08T00:00:00Z", preset: "-30d" },
    sort_by: "priority",
    sort_order: "asc",
  },
};

function renderToolbar(isAdmin = false, initialSearch = "") {
  const onSearchChange = vi.fn();
  const onFilterChange = vi.fn();

  function Toolbar() {
    const [filters, setFilters] = useState<FilterState>({
      search: initialSearch,
      status: ["NEW", "IN_PROGRESS"],
      assignee: null,
      includeTags: null,
      excludeTags: null,
      dateRange: null,
      sortBy: "created_at",
      sortOrder: "desc",
    });
    return (
      <EntityFilterToolbar
        filters={filters}
        onFilterChange={(next) => {
          onFilterChange(next);
          setFilters(next);
        }}
        onSearchChange={(search) => {
          onSearchChange(search);
          setFilters((previous) => ({ ...previous, search }));
        }}
        savedFilterQueue="alerts"
      />
    );
  }

  renderWithProviders(<Toolbar />, {
    sessionValue: {
      status: "authenticated",
      user: { id: "account-id", username: "analyst" },
      isAdmin,
    } as SessionContextValue,
  });
  return { onSearchChange, onFilterChange };
}

describe("Saved queue filters", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(SavedFiltersService.listSavedFilters).mockResolvedValue([personal, organization]);
  });
  afterEach(() => vi.useRealTimers());

  it("saves the live search input before its debounce and warns about organization visibility", async () => {
    const user = userEvent.setup();
    vi.mocked(SavedFiltersService.createSavedFilter).mockResolvedValue(organization);
    const { onSearchChange } = renderToolbar(true);
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await screen.findByRole("button", { name: "Apply Org triage" });

    fireEvent.change(screen.getByRole("textbox", { name: "Search this queue" }), {
      target: { value: "  vpn   outage  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save current filter" }));

    const dialog = within(screen.getByRole("dialog", { name: "Save current filter" }));
    expect(onSearchChange).not.toHaveBeenCalled();
    expect(dialog.getByText("This search will be included in the saved filter.")).toBeVisible();
    expect(dialog.getByText("vpn outage")).toBeVisible();
    await user.type(dialog.getByRole("textbox", { name: "Filter name" }), "VPN outages");
    await user.click(dialog.getByRole("radio", { name: "Org-wide" }));
    expect(dialog.getByText("This search text will be visible to everyone in your organization.")).toBeVisible();
    await user.click(dialog.getByRole("button", { name: "Save filter" }));

    await waitFor(() => expect(SavedFiltersService.createSavedFilter).toHaveBeenCalledWith({
      requestBody: {
        name: "VPN outages",
        queue: "alerts",
        scope: "organization",
        filters: {
          search: "vpn outage",
          status: ["NEW", "IN_PROGRESS"],
          assignee: null,
          include_tags: null,
          exclude_tags: null,
          date_range: null,
          sort_by: "created_at",
          sort_order: "desc",
        },
      },
    }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Save current filter" })).not.toBeInTheDocument());
  });

  it("validates invalid search text and gives non-admins a personal save only", async () => {
    const user = userEvent.setup();
    renderToolbar();
    await user.click(screen.getByRole("button", { name: "Filters" }));
    expect(await screen.findByRole("button", { name: "Rename My open alerts" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Delete My open alerts" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Rename Org triage" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete Org triage" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "Search this queue" }), {
      target: { value: "v" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save current filter" }));

    const dialog = within(screen.getByRole("dialog", { name: "Save current filter" }));
    await user.type(dialog.getByRole("textbox", { name: "Filter name" }), "Short query");
    expect(dialog.getByRole("alert")).toHaveTextContent("characters in the search box or clear it");
    expect(dialog.queryByRole("radio", { name: "Org-wide" })).not.toBeInTheDocument();
    expect(dialog.getByRole("button", { name: "Save filter" })).toBeDisabled();
    expect(SavedFiltersService.createSavedFilter).not.toHaveBeenCalled();
  });

  it("applies every part of a shared filter for a non-admin", async () => {
    const user = userEvent.setup();
    const { onFilterChange } = renderToolbar(false, "other query");
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.click(await screen.findByRole("button", { name: "Apply Org triage" }));

    expect(onFilterChange).toHaveBeenCalledWith({
      search: "dns failure",
      status: ["NEW"],
      assignee: ["analyst"],
      includeTags: ["dns"],
      excludeTags: ["training"],
      dateRange: organization.filters.date_range,
      sortBy: "priority",
      sortOrder: "asc",
    });
    expect(screen.getByRole("textbox", { name: "Search this queue" })).toHaveValue("dns failure");
    expect(screen.queryByRole("dialog", { name: "Queue filters" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    await user.click(await screen.findByRole("button", { name: "Apply My open alerts" }));
    expect(screen.getByRole("textbox", { name: "Search this queue" })).toHaveValue("");
  });

  it("cancels a pending edit when the chosen preset matches the current query", async () => {
    const user = userEvent.setup();
    const { onSearchChange } = renderToolbar(false, "dns failure");
    await user.click(screen.getByRole("button", { name: "Filters" }));
    const preset = await screen.findByRole("button", { name: "Apply Org triage" });
    vi.useFakeTimers();
    fireEvent.change(screen.getByRole("textbox", { name: "Search this queue" }), {
      target: { value: "stale edit" },
    });
    fireEvent.click(preset);
    act(() => vi.advanceTimersByTime(300));

    expect(onSearchChange).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "Search this queue" })).toHaveValue("dns failure");
  });

  it("allows administrators to rename and delete org-wide filters", async () => {
    const user = userEvent.setup();
    const renamed = { ...organization, name: "Shared DNS incidents" };
    vi.mocked(SavedFiltersService.listSavedFilters)
      .mockResolvedValueOnce([personal, organization])
      .mockResolvedValueOnce([personal, renamed])
      .mockResolvedValue([personal]);
    vi.mocked(SavedFiltersService.renameSavedFilter).mockResolvedValue(renamed);
    vi.mocked(SavedFiltersService.deleteSavedFilter).mockResolvedValue(undefined);
    renderToolbar(true);
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.click(await screen.findByRole("button", { name: "Rename Org triage" }));
    const renameDialog = within(screen.getByRole("dialog", { name: "Rename saved filter" }));
    const name = renameDialog.getByRole("textbox", { name: "Filter name" });
    expect(name).toHaveValue("Org triage");
    await user.clear(name);
    await user.type(name, "Shared DNS incidents");
    await user.click(renameDialog.getByRole("button", { name: "Rename filter" }));

    expect(SavedFiltersService.renameSavedFilter).toHaveBeenCalledWith({
      filterId: organization.id,
      requestBody: { name: "Shared DNS incidents" },
    });
    await user.click(await screen.findByRole("button", { name: "Delete Shared DNS incidents" }));
    await user.click(within(screen.getByRole("dialog", { name: "Delete saved filter" })).getByRole("button", { name: "Delete filter" }));

    expect(SavedFiltersService.deleteSavedFilter).toHaveBeenCalledWith({ filterId: organization.id });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Apply Shared DNS incidents" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Apply My open alerts" })).toBeVisible();
  });
});
