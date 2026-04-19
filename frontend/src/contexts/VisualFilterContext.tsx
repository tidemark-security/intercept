import React from "react";

import {
  applyVisualFilterPreference,
  VISUAL_FILTER_DEFAULTS,
  getStoredVisualFilterPreference,
  normalizeVisualFilterPreference,
  setStoredVisualFilterPreference,
  type VisualFilterPreference,
} from "@/utils/visualFilterPreference";

interface VisualFilterContextValue {
  visualFilterPreference: VisualFilterPreference;
  setVisualFilterPreference: React.Dispatch<React.SetStateAction<VisualFilterPreference>>;
  resetVisualFilterPreference: () => void;
}

const VisualFilterContext = React.createContext<VisualFilterContextValue | null>(null);

export function VisualFilterProvider({ children }: { children: React.ReactNode }) {
  const [visualFilterPreference, setVisualFilterPreference] = React.useState<VisualFilterPreference>(
    () => normalizeVisualFilterPreference(getStoredVisualFilterPreference()),
  );

  React.useEffect(() => {
    const normalized = normalizeVisualFilterPreference(visualFilterPreference);
    setStoredVisualFilterPreference(normalized);
    applyVisualFilterPreference(normalized);
  }, [visualFilterPreference]);

  const resetVisualFilterPreference = React.useCallback(() => {
    setVisualFilterPreference({ ...VISUAL_FILTER_DEFAULTS });
  }, []);

  const value = React.useMemo<VisualFilterContextValue>(
    () => ({
      visualFilterPreference,
      setVisualFilterPreference,
      resetVisualFilterPreference,
    }),
    [visualFilterPreference, resetVisualFilterPreference],
  );

  return <VisualFilterContext.Provider value={value}>{children}</VisualFilterContext.Provider>;
}

export function useVisualFilterPreference(): VisualFilterContextValue {
  const context = React.useContext(VisualFilterContext);
  if (!context) {
    throw new Error("useVisualFilterPreference must be used within VisualFilterProvider");
  }

  return context;
}
