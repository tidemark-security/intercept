import { formatInTimeZone } from "date-fns-tz";

import { getUserTimezone } from "@/utils/dateFilters";

export type TimezonePreference = "local" | "utc";

export const TIMEZONE_PREFERENCE_STORAGE_KEY = "intercept.timezone-preference";

const VALID_TIMEZONE_PREFERENCES: TimezonePreference[] = ["local", "utc"];

export function isTimezonePreference(value: string | null | undefined): value is TimezonePreference {
  return (
    typeof value === "string" &&
    VALID_TIMEZONE_PREFERENCES.includes(value as TimezonePreference)
  );
}

export function getStoredTimezonePreference(): TimezonePreference {
  if (typeof window === "undefined") {
    return "local";
  }

  try {
    const storedPreference = window.localStorage.getItem(TIMEZONE_PREFERENCE_STORAGE_KEY);
    return isTimezonePreference(storedPreference) ? storedPreference : "local";
  } catch {
    return "local";
  }
}

export function setStoredTimezonePreference(preference: TimezonePreference): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(TIMEZONE_PREFERENCE_STORAGE_KEY, preference);
  } catch {
    // Ignore write failures (e.g., private mode restrictions)
  }
}

export function formatTimestampForPreference(date: Date, preference: TimezonePreference): string {
  if (preference === "utc") {
    return formatInTimeZone(date, "UTC", "yyyy-MM-dd'T'HH:mm:ss'Z'");
  }

  return formatInTimeZone(date, getUserTimezone(), "yyyy-MM-dd'T'HH:mm:ssXXX");
}
