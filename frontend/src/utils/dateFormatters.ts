import { format as formatDate } from "date-fns";
import { formatInTimeZone } from "date-fns-tz";

import type { TimezonePreference } from "./timezonePreference";

export { formatTimelineTimestamp, formatRelativeTime, getTimeGroup, TIME_GROUP_LABELS } from "@tidemark-security/ux";
export type { TimestampFormatOptions, TimeGroup } from "@tidemark-security/ux";

const DEFAULT_ABSOLUTE_FORMAT = "MMM d, yyyy h:mm a";

function toValidDate(value: Date | string | number): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatAbsoluteTime(
  timestamp: Date | string | number | null | undefined,
  formatString = DEFAULT_ABSOLUTE_FORMAT,
  timezonePreference: TimezonePreference = "local",
): string {
  if (timestamp === null || timestamp === undefined) {
    return "";
  }

  const date = toValidDate(timestamp);
  if (!date) {
    return "";
  }

  return timezonePreference === "utc"
    ? formatInTimeZone(date, "UTC", formatString)
    : formatDate(date, formatString);
}

export function formatHourOfDayForPreference(
  utcHourOfDay: number | null | undefined,
  timezonePreference: TimezonePreference,
): string {
  if (utcHourOfDay === null || utcHourOfDay === undefined || Number.isNaN(utcHourOfDay)) {
    return "";
  }

  const normalizedHour = ((Math.trunc(utcHourOfDay) % 24) + 24) % 24;
  const utcDate = new Date(Date.UTC(2024, 0, 1, normalizedHour));

  if (timezonePreference === "utc") {
    return formatInTimeZone(utcDate, "UTC", "H:00");
  }

  return `${formatDate(utcDate, "H")}:00`;
}

export function getHourOfDayForPreference(
  utcHourOfDay: number | null | undefined,
  timezonePreference: TimezonePreference,
): number | null {
  if (utcHourOfDay === null || utcHourOfDay === undefined || Number.isNaN(utcHourOfDay)) {
    return null;
  }

  const label = formatHourOfDayForPreference(utcHourOfDay, timezonePreference);
  const hour = Number.parseInt(label, 10);
  return Number.isNaN(hour) ? null : hour;
}
