import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useTagFilterClick } from "@/hooks/useTagFilterClick";

describe("useTagFilterClick", () => {
  it("adds included tags and removes them from exclude filters", () => {
    const setFilters = vi.fn();
    const { result } = renderHook(() =>
      useTagFilterClick(
        {
          includeTags: ["vip"],
          excludeTags: ["phishing"],
        },
        setFilters,
      ),
    );

    result.current("phishing", "include");

    expect(setFilters).toHaveBeenCalledWith({
      includeTags: ["vip", "phishing"],
      excludeTags: [],
    });
  });

  it("adds excluded tags and removes them from include filters", () => {
    const setFilters = vi.fn();
    const { result } = renderHook(() =>
      useTagFilterClick(
        {
          includeTags: ["phishing"],
          excludeTags: ["noisy"],
        },
        setFilters,
      ),
    );

    result.current("phishing", "exclude");

    expect(setFilters).toHaveBeenCalledWith({
      includeTags: [],
      excludeTags: ["noisy", "phishing"],
    });
  });
});
