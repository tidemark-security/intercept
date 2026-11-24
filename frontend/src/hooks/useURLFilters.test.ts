import { act, renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { filtersToURLParams, parseFiltersFromURL, useURLFilters } from "@/hooks/useURLFilters";
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

describe("useURLFilters tab memory", () => {
  const defaults: FilterState = {
    search: "",
    assignee: null,
    status: ["NEW", "IN_PROGRESS"],
    dateRange: null,
  };

  function renderQueue(queue: "alerts" | "cases" | "tasks", url = `/${queue}`, userId = "analyst") {
    return renderHook(() => ({
      ...useURLFilters({ queue, defaults, userId }),
      location: useLocation(),
      navigate: useNavigate(),
    }), {
      wrapper: ({ children }: { children: ReactNode }) =>
        createElement(MemoryRouter, { initialEntries: [url] }, children),
    });
  }

  beforeEach(() => sessionStorage.clear());

  it("restores the full selection and starts on page one when returning", () => {
    const selection: FilterState = {
      ...defaults,
      search: "login",
      status: ["CLOSED_FP"],
      assignee: ["analyst"],
      includeTags: ["identity", "vpn"],
      excludeTags: ["noise"],
      dateRange: { start: "2026-06-01T00:00:00Z", end: "2026-06-08T00:00:00Z", preset: "custom" },
      sortBy: "priority",
      sortOrder: "asc",
    };
    const first = renderQueue("alerts");
    act(() => first.result.current.setFilters(selection));
    act(() => first.result.current.setCurrentPage(3));
    expect(first.result.current.currentPage).toBe(3);
    first.unmount();

    const { result } = renderQueue("alerts");
    expect(result.current.filters).toEqual(selection);
    expect(result.current.currentPage).toBe(1);
    expect(result.current.location.search).toBe(`?${filtersToURLParams(selection)}`);
  });

  it("keeps selections separate by queue and user", () => {
    const alerts = renderQueue("alerts");
    act(() => alerts.result.current.setSearch("phishing"));
    alerts.unmount();
    const cases = renderQueue("cases");
    act(() => cases.result.current.setSearch("outbound"));
    cases.unmount();

    expect(renderQueue("alerts").result.current.filters.search).toBe("phishing");
    expect(renderQueue("cases").result.current.filters.search).toBe("outbound");
    expect(renderQueue("tasks").result.current.filters.search).toBe("");
    expect(renderQueue("alerts", "/alerts", "another-user").result.current.filters.search).toBe("");
  });

  it("recalculates a relative date range even when applying the same filters again", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    try {
      vi.setSystemTime(new Date("2026-06-08T12:00:00Z"));
      const { result } = renderQueue("alerts", "/alerts?status=NEW%2CIN_PROGRESS&timeframe=-7d");
      const savedFilters = result.current.filters;
      expect(savedFilters.dateRange?.end).toBe("2026-06-08T12:00:00Z");

      vi.setSystemTime(new Date("2026-06-09T12:00:00Z"));
      act(() => result.current.setFilters(savedFilters));
      expect(result.current.location.search).toBe("?status=NEW%2CIN_PROGRESS&timeframe=-7d");
      expect(result.current.filters.dateRange?.end).toBe("2026-06-09T12:00:00Z");
    } finally {
      vi.useRealTimers();
    }
  });

  it("uses explicit URL filters and pagination without changing the saved selection", () => {
    const alerts = renderQueue("alerts");
    act(() => alerts.result.current.setSearch("phishing"));
    alerts.unmount();
    const { result } = renderQueue("alerts", "/alerts?status=NEW&page=2");

    expect(result.current.filters).toMatchObject({ search: "", status: ["NEW"] });
    expect(result.current.currentPage).toBe(2);
    act(() => result.current.navigate("/alerts"));
    expect(result.current.filters.search).toBe("phishing");
    expect(result.current.currentPage).toBe(1);
    act(() => result.current.navigate(-1));
    expect(result.current.filters).toMatchObject({ search: "", status: ["NEW"] });
    act(() => result.current.navigate(1));
    expect(result.current.filters.search).toBe("phishing");
  });

  it("keeps cleared filters and search cleared on return", () => {
    const alerts = renderQueue("alerts");
    act(() => alerts.result.current.setFilters({ ...defaults, status: ["CLOSED_FP"], search: "phishing" }));
    act(() => alerts.result.current.setFilters({ ...defaults, status: null, search: "phishing" }));
    act(() => alerts.result.current.setSearch(""));
    alerts.unmount();

    expect(renderQueue("alerts").result.current.filters).toMatchObject(defaults);
  });

  it("still updates the URL when session storage is unavailable", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("Storage blocked", "SecurityError");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Storage blocked", "SecurityError");
    });
    try {
      const { result } = renderQueue("alerts");
      act(() => result.current.setSearch("phishing"));
      expect(result.current.filters.search).toBe("phishing");
      expect(result.current.location.search).toBe("?search=phishing");
    } finally {
      getItem.mockRestore();
      setItem.mockRestore();
    }
  });
});
