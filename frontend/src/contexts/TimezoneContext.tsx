/* eslint-disable react-refresh/only-export-components */

import React from "react";

import {
  getStoredTimezonePreference,
  setStoredTimezonePreference,
  type TimezonePreference,
} from "@/utils/timezonePreference";

interface TimezoneContextValue {
  timezonePreference: TimezonePreference;
  setTimezonePreference: (preference: TimezonePreference) => void;
}

const TimezoneContext = React.createContext<TimezoneContextValue | null>(null);

export function TimezoneProvider({ children }: { children: React.ReactNode }) {
  const [timezonePreference, setTimezonePreferenceState] = React.useState<TimezonePreference>(() =>
    getStoredTimezonePreference()
  );

  React.useEffect(() => {
    setStoredTimezonePreference(timezonePreference);
  }, [timezonePreference]);

  const value = React.useMemo<TimezoneContextValue>(
    () => ({
      timezonePreference,
      setTimezonePreference: setTimezonePreferenceState,
    }),
    [timezonePreference]
  );

  return <TimezoneContext.Provider value={value}>{children}</TimezoneContext.Provider>;
}

export function useTimezonePreference(): TimezoneContextValue {
  const context = React.useContext(TimezoneContext);
  if (!context) {
    throw new Error("useTimezonePreference must be used within TimezoneProvider");
  }
  return context;
}
