/**
 * Date and time formatting utilities for timeline items
 * 
 * Provides consistent timestamp formatting across the application.
 * Uses relative time for recent events and absolute time for older events.
 */

import { formatDistanceToNow, format, parseISO, differenceInDays } from 'date-fns';

function normalizeRelativeTimeLabel(value: string): string {
  return value
    .replace(/\bless than\b/gi, '<')
    .replace(/\bover\b/gi, '>')
    .replace(/\balmost\b/gi, '~')
    .replace(/\babout\b/gi, '~')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

/**
 * Options for formatting timeline timestamps
 */
export interface TimestampFormatOptions {
  /** Show relative time (e.g., "2 hours ago") for recent events */
  useRelative?: boolean;
  /** Threshold in days for switching from relative to absolute time */
  relativeDaysThreshold?: number;
  /** Format string for absolute timestamps */
  absoluteFormat?: string;
}

/**
 * Default options for timestamp formatting
 */
const DEFAULT_OPTIONS: Required<TimestampFormatOptions> = {
  useRelative: true,
  relativeDaysThreshold: 7,
  absoluteFormat: 'MMM d, yyyy h:mm a',
};

/**
 * Format a timeline timestamp with intelligent relative/absolute switching.
 * 
 * - Events within the threshold (default 7 days) show relative time: "2 hours ago"
 * - Events beyond the threshold show absolute time: "Nov 1, 2024 3:45 PM"
 * 
 * @param timestamp - ISO 8601 timestamp string or Date object
 * @param options - Formatting options
 * @returns Formatted timestamp string
 * 
 * @example
 * ```tsx
 * formatTimelineTimestamp('2024-11-08T10:30:00Z') // "2 hours ago"
 * formatTimelineTimestamp('2024-10-01T10:30:00Z') // "Oct 1, 2024 10:30 AM"
 * ```
 */
export function formatTimelineTimestamp(
  timestamp: string | Date | undefined | null,
  options: TimestampFormatOptions = {}
): string {
  if (!timestamp) {
    return '';
  }

  const opts = { ...DEFAULT_OPTIONS, ...options };

  try {
    const date = typeof timestamp === 'string' ? parseISO(timestamp) : timestamp;
    const now = new Date();
    const daysDiff = Math.abs(differenceInDays(now, date));

    // Use relative time for recent events
    if (opts.useRelative && daysDiff <= opts.relativeDaysThreshold) {
      return normalizeRelativeTimeLabel(
        formatDistanceToNow(date, { addSuffix: true })
      );
    }

    // Use absolute time for older events
    return format(date, opts.absoluteFormat);
  } catch (error) {
    console.error('Error formatting timestamp:', error);
    return String(timestamp);
  }
}

/**
 * Format a timestamp as relative time only (e.g., "2 hours ago").
 * 
 * @param timestamp - ISO 8601 timestamp string or Date object
 * @returns Relative time string
 * 
 * @example
 * ```tsx
 * formatRelativeTime('2024-11-08T10:30:00Z') // "2 hours ago"
 * ```
 */
export function formatRelativeTime(
  timestamp: string | Date | undefined | null
): string {
  if (!timestamp) {
    return '';
  }

  try {
    const date = typeof timestamp === 'string' ? parseISO(timestamp) : timestamp;
    return normalizeRelativeTimeLabel(
      formatDistanceToNow(date, { addSuffix: true })
    );
  } catch (error) {
    console.error('Error formatting relative time:', error);
    return String(timestamp);
  }
}

/**
 * Format a timestamp as absolute time (e.g., "Nov 8, 2024 10:30 AM").
 * 
 * @param timestamp - ISO 8601 timestamp string or Date object
 * @param formatString - Optional format string (default: "MMM d, yyyy h:mm a")
 * @returns Formatted timestamp string
 * 
 * @example
 * ```tsx
 * formatAbsoluteTime('2024-11-08T10:30:00Z') // "Nov 8, 2024 10:30 AM"
 * formatAbsoluteTime('2024-11-08T10:30:00Z', 'yyyy-MM-dd') // "2024-11-08"
 * ```
 */
export function formatAbsoluteTime(
  timestamp: string | Date | undefined | null,
  formatString: string = 'MMM d, yyyy h:mm a'
): string {
  if (!timestamp) {
    return '';
  }

  try {
    const date = typeof timestamp === 'string' ? parseISO(timestamp) : timestamp;
    return format(date, formatString);
  } catch (error) {
    console.error('Error formatting absolute time:', error);
    return String(timestamp);
  }
}

/**
 * Time group categories for grouping items by recency
 */
export type TimeGroup = 'today' | 'yesterday' | 'week' | 'older';

/**
 * Labels for time groups
 */
export const TIME_GROUP_LABELS: Record<TimeGroup, string> = {
  today: 'Today',
  yesterday: 'Yesterday',
  week: 'Last 7 days',
  older: 'Older',
};

/**
 * Get the time group for a given date (Today, Yesterday, Last 7 days, Older)
 * 
 * @param timestamp - ISO 8601 timestamp string or Date object
 * @returns Time group category
 * 
 * @example
 * ```tsx
 * getTimeGroup('2024-11-08T10:30:00Z') // 'today' (if today is Nov 8)
 * getTimeGroup('2024-11-01T10:30:00Z') // 'week' (if within 7 days)
 * ```
 */
export function getTimeGroup(timestamp: string | Date): TimeGroup {
  const date = typeof timestamp === 'string' ? parseISO(timestamp) : timestamp;
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  if (date >= today) return 'today';
  if (date >= yesterday) return 'yesterday';
  if (date >= weekAgo) return 'week';
  return 'older';
}
