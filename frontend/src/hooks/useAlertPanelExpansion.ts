import { useState } from "react";

type AlertPanel = "analyst-context" | "triage-recommendation";

export function useAlertPanelExpansion(panel: AlertPanel, defaultExpanded: boolean) {
  // These keys intentionally do not include an alert or recommendation ID.
  const key = `intercept.alert-detail.${panel}.expansion`;
  const [preference, setPreference] = useState<boolean | null>(() => {
    try {
      const stored = window.localStorage.getItem(key);
      if (stored === "expanded") return true;
      if (stored === "collapsed") return false;
    } catch {
      // The panel is still usable when browser storage is blocked.
    }
    return null;
  });

  function setExpanded(expanded: boolean) {
    setPreference(expanded);
    try {
      window.localStorage.setItem(key, expanded ? "expanded" : "collapsed");
    } catch {
      // Keep the user's choice for the currently mounted panel.
    }
  }

  return [preference ?? defaultExpanded, setExpanded] as const;
}
