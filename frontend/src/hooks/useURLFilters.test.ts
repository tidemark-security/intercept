import { describe, expect, it } from "vitest";

import { filtersToURLParams, parseFiltersFromURL } from "@/hooks/useURLFilters";
import type { FilterState } from "@/types/filters";

describe("useURLFilters helpers", () => {
  it("parses alert include and exclude tag filters from URL params", () => {
    const filters = parseFiltersFromURL(
      new URLSearchParams("include_tags=phishing&include_tags=vip,finance&exclude_tags=noisy")
    ) as Partial<FilterState>;

    expect(filters.includeTags).toEqual(["phishing", "vip", "finance"]);
    expect(filters.excludeTags).toEqual(["noisy"]);
  });

  it("serializes alert tag filters with backend-compatible parameter names", () => {
    const filters: FilterState = {
      search: "",
      assignee: null,
      status: ["NEW", "IN_PROGRESS"],
      includeTags: ["phishing", "vip"],
      excludeTags: ["noisy"],
      dateRange: null,
    };

    const params = filtersToURLParams(filters, 2);

    expect(params.get("status")).toBe("NEW,IN_PROGRESS");
    expect(params.getAll("include_tags")).toEqual(["phishing", "vip"]);
    expect(params.getAll("exclude_tags")).toEqual(["noisy"]);
    expect(params.get("page")).toBe("2");
  });

  it("parses and serializes queue sort params", () => {
    const parsed = parseFiltersFromURL(
      new URLSearchParams("sort_by=created_at&sort_order=asc")
    ) as Partial<FilterState>;

    expect(parsed.sortBy).toBe("created_at");
    expect(parsed.sortOrder).toBe("asc");

    const filters: FilterState = {
      search: "",
      assignee: null,
      status: ["NEW", "IN_PROGRESS"],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
      sortBy: "priority",
      sortOrder: "desc",
    };

    const params = filtersToURLParams(filters);

    expect(params.get("sort_by")).toBe("priority");
    expect(params.get("sort_order")).toBe("desc");
  });

  it("serializes preset date ranges as timeframe params", () => {
    const filters: FilterState = {
      search: "",
      assignee: null,
      status: ["NEW", "IN_PROGRESS"],
      includeTags: null,
      excludeTags: null,
      dateRange: {
        start: "2026-05-09T00:00:00Z",
        end: "2026-06-08T00:00:00Z",
        preset: "-30d",
      },
    };

    const params = filtersToURLParams(filters);

    expect(params.get("timeframe")).toBe("-30d");
    expect(params.has("start_date")).toBe(false);
    expect(params.has("end_date")).toBe(false);
  });

  it("parses preset timeframe params into a date range with preset metadata", () => {
    const filters = parseFiltersFromURL(
      new URLSearchParams("timeframe=-30d")
    ) as Partial<FilterState>;

    expect(filters.dateRange?.preset).toBe("-30d");
    expect(filters.dateRange?.start).toBeTruthy();
    expect(filters.dateRange?.end).toBeTruthy();
  });

  it("serializes custom date ranges with explicit start and end params", () => {
    const filters: FilterState = {
      search: "",
      assignee: null,
      status: null,
      includeTags: null,
      excludeTags: null,
      dateRange: {
        start: "2026-06-01T00:00:00Z",
        end: "2026-06-08T00:00:00Z",
        preset: "custom",
      },
    };

    const params = filtersToURLParams(filters);

    expect(params.get("start_date")).toBe("2026-06-01T00:00:00Z");
    expect(params.get("end_date")).toBe("2026-06-08T00:00:00Z");
    expect(params.has("timeframe")).toBe(false);
  });
});
