import { useSyncExternalStore } from "react";

export const alertDetailPositions = ["before", "embed", "after"] as const;

export type AlertDetailPosition = (typeof alertDetailPositions)[number];

export type AlertDetailLayout = {
  triage: AlertDetailPosition;
  context: AlertDetailPosition;
};

const layoutChangeEvent = "intercept:alert-detail-layout";

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(layoutChangeEvent, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(layoutChangeEvent, onChange);
  };
}

function useAlertDetailPosition(userId: string | undefined, panel: keyof AlertDetailLayout) {
  // Separate keys let each panel be updated independently, including across tabs.
  const key = userId ? `intercept.alert-detail.layout.${userId}.${panel}` : null;
  const position = useSyncExternalStore(subscribe, (): AlertDetailPosition => {
    try {
      const value = key && window.localStorage.getItem(key);
      return value === "before" || value === "after" ? value : "embed";
    } catch {
      return "embed";
    }
  });

  function setPosition(value: string) {
    if (!key || !alertDetailPositions.some((position) => position === value)) return;
    try {
      window.localStorage.setItem(key, value);
    } catch {
      return;
    }
    window.dispatchEvent(new Event(layoutChangeEvent));
  }

  return [position, setPosition] as const;
}

export function useAlertDetailLayout(userId: string | undefined) {
  const [triage, setTriage] = useAlertDetailPosition(userId, "triage");
  const [context, setContext] = useAlertDetailPosition(userId, "context");
  return { layout: { triage, context }, setTriage, setContext };
}
