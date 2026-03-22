/**
 * Date utility functions for alert filtering
 * 
 * Key principles:
 * - All dates sent to backend are in UTC ISO8601 format with 'Z' suffix
 * - User inputs/displays are in local timezone
 * - Conversion happens at boundaries: local→UTC on Apply, UTC→local on display
 * - Storage in FilterState is always UTC
 */

import { 
  sub, 
  format, 
  parseISO, 
  isValid, 
  isBefore, 
  isAfter 
} from 'date-fns';
import { formatInTimeZone, toZonedTime, fromZonedTime } from 'date-fns-tz';

/**
 * Get the user's timezone identifier (e.g., "America/Los_Angeles")
 * Falls back to UTC offset if IANA timezone not available
 */
export function getUserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    // Fallback: calculate UTC offset
    const offset = -new Date().getTimezoneOffset();
    const hours = Math.floor(Math.abs(offset) / 60);
    const minutes = Math.abs(offset) % 60;
    const sign = offset >= 0 ? '+' : '-';
    return `UTC${sign}${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
  }
}

/**
 * Parse relative time expressions and return UTC date range
 * 
 * Supported formats:
 * - "-15m", "-15min" - 15 minutes ago
 * - "-1h", "-1hr" - 1 hour ago
 * - "-24h" - 24 hours ago
 * - "-7d" - 7 days ago
 * - "-30d" - 30 days ago
 * - "now" - current timestamp
 * 
 * @param input - Relative time expression
 * @returns Object with start and end UTC dates, or null if invalid
 */
export function parseRelativeTime(input: string): { start: Date; end: Date } | null {
  const trimmed = input.trim().toLowerCase();
  const now = new Date(); // Current time in UTC
  
  if (trimmed === 'now') {
    return { start: now, end: now };
  }
  
  // Parse relative expression like "-15m", "-1h", "-7d"
  const match = trimmed.match(/^-(\d+)(m|min|h|hr|d)$/);
  if (!match) {
    return null;
  }
  
  const amount = parseInt(match[1], 10);
  const unit = match[2];
  
  let start: Date;
  switch (unit) {
    case 'm':
    case 'min':
      start = sub(now, { minutes: amount });
      break;
    case 'h':
    case 'hr':
      start = sub(now, { hours: amount });
      break;
    case 'd':
      start = sub(now, { days: amount });
      break;
    default:
      return null;
  }
  
  return { start, end: now };
}

/**
 * Parse ISO8601 date string (with or without 'T' separator, with or without timezone)
 * If no timezone specified, treats input as local time
 * 
 * Supported formats:
 * - "2025-10-20T14:30:00Z" (UTC)
 * - "2025-10-20T14:30:00" (local)
 * - "2025-10-20 14:30:00" (local, space separator)
 * - "2025-10-20T14:30:00+02:00" (with offset)
 * 
 * @param input - ISO8601 date string
 * @returns Date object or null if invalid
 */
export function parseISO8601(input: string): Date | null {
  try {
    // Normalize space separator to 'T'
    const normalized = input.trim().replace(' ', 'T');
    
    // Try parsing with date-fns
    const date = parseISO(normalized);
    
    if (!isValid(date)) {
      return null;
    }
    
    return date;
  } catch {
    return null;
  }
}

/**
 * Convert local Date to UTC Date
 * Used when user enters a local time that needs to be converted to UTC
 * 
 * @param localDate - Date in user's local timezone
 * @returns Date object representing the same moment in UTC
 */
export function localToUTC(localDate: Date): Date {
  const userTz = getUserTimezone();
  // fromZonedTime interprets the date as being in the specified timezone
  // and converts it to UTC
  return fromZonedTime(localDate, userTz);
}

/**
 * Convert UTC Date to local Date
 * Used when displaying UTC dates to the user
 * 
 * @param utcDate - Date in UTC
 * @returns Date object in user's local timezone
 */
export function utcToLocal(utcDate: Date): Date {
  const userTz = getUserTimezone();
  // toZonedTime converts a UTC date to the specified timezone
  return toZonedTime(utcDate, userTz);
}

/**
 * Format Date as datetime-local input value (for display in input field)
 * Converts UTC date to local time for user input
 * Format: "YYYY-MM-DDTHH:mm" (no seconds, no timezone)
 * 
 * @param date - Date object (assumed to be UTC)
 * @returns String in datetime-local format
 */
export function formatForDatetimeLocal(date: Date): string {
  const userTz = getUserTimezone();
  // Format in user's timezone without seconds
  return formatInTimeZone(date, userTz, "yyyy-MM-dd'T'HH:mm");
}

/**
 * Normalize values between datetime-local input format and display format
 * - display: "YYYY-MM-DDTHH:mm" -> "YYYY-MM-DD HH:mm"
 * - input: "YYYY-MM-DD HH:mm" -> "YYYY-MM-DDTHH:mm"
 *
 * @param value - Input value to normalize
 * @param target - Target format
 * @returns Normalized value in target format
 */
export function normalizeDatetimeLocalValue(
  value: string,
  target: 'display' | 'input',
): string {
  if (!value) return '';
  return target === 'display' ? value.replace('T', ' ') : value.replace(' ', 'T');
}

/**
 * Format Date as UTC ISO8601 string for backend API
 * Always includes 'Z' suffix to indicate UTC
 * Format: "YYYY-MM-DDTHH:mm:ssZ"
 * 
 * @param date - Date object
 * @returns UTC ISO8601 string with 'Z' suffix
 */
export function formatForBackend(date: Date): string {
  // Format as UTC with 'Z' suffix
  return formatInTimeZone(date, 'UTC', "yyyy-MM-dd'T'HH:mm:ss'Z'");
}

/**
 * Format Date for display in UI (short format, local time)
 * Example: "Oct 13, 2:30 PM"
 * 
 * @param date - Date object (UTC)
 * @returns Formatted string in local time
 */
export function formatForDisplay(date: Date): string {
  const userTz = getUserTimezone();
  return formatInTimeZone(date, userTz, 'MMM d, h:mm a');
}

/**
 * Validate that end date is after start date
 * 
 * @param start - Start date
 * @param end - End date
 * @returns True if valid range (end > start)
 */
export function isValidDateRange(start: Date, end: Date): boolean {
  return isAfter(end, start) || start.getTime() === end.getTime();
}

/**
 * Generate a human-readable label from a relative time expression
 * @param relativeExpression - Relative time string like "-15m", "-1h", "-7d"
 * @returns Human-readable label like "Last 15 minutes", "Last hour", etc.
 */
export function getRelativeTimeLabel(relativeExpression: string): string {
  const trimmed = relativeExpression.trim().toLowerCase();
  
  // Parse the expression
  const match = trimmed.match(/^-(\d+)(m|min|h|hr|d)$/);
  if (!match) {
    return relativeExpression; // Return as-is if we can't parse
  }
  
  const amount = parseInt(match[1], 10);
  const unit = match[2];
  
  // Map unit to word
  let unitWord: string;
  switch (unit) {
    case 'm':
    case 'min':
      unitWord = amount === 1 ? 'minute' : 'minutes';
      break;
    case 'h':
    case 'hr':
      unitWord = amount === 1 ? 'hour' : 'hours';
      break;
    case 'd':
      unitWord = amount === 1 ? 'day' : 'days';
      break;
    default:
      return relativeExpression;
  }
  
  return `Last ${amount} ${unitWord}`;
}
