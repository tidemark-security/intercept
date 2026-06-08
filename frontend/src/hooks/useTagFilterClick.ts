import { useCallback } from "react";

type TagFilterMode = "include" | "exclude";

type TagFilterable = {
  includeTags?: string[] | null;
  excludeTags?: string[] | null;
};

export function useTagFilterClick<T extends TagFilterable>(
  filters: T,
  setFilters: (filters: T) => void,
) {
  return useCallback((tag: string, mode: TagFilterMode) => {
    const key = mode === "include" ? "includeTags" : "excludeTags";
    const current = filters[key] || [];
    if (current.includes(tag)) {
      return;
    }

    setFilters({
      ...filters,
      [key]: [...current, tag],
    });
  }, [filters, setFilters]);
}
